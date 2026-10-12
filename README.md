# Subline — local subtitle studio

A Chinese → English subtitle workflow with a local React review studio, FastAPI + SQLite terminology memory, drafts from an OpenAI-compatible LLM API, and a separate YouTube subtitle overlay. The workspace and terminology database stay local; transcript chunks are sent to the configured LLM API for translation.

## Run locally

Requires Python **3.12+**, Node.js **22+**, Chrome, and access to an OpenAI-compatible Chat Completions API that supports JSON Schema structured output. Commands below run from this repository root in PowerShell. Using `npm.cmd` avoids PowerShell script execution-policy issues.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
npm.cmd ci
```

Configure the API in the terminal that will run the backend. `OPENAI_BASE_URL` must include the API version prefix used by your provider (usually `/v1`):

```powershell
$env:OPENAI_BASE_URL = 'https://your-provider.example/v1'
$env:OPENAI_API_KEY = 'your-api-key'
$env:OPENAI_MODEL = 'your-model-id'
```

In separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. API documentation: **http://127.0.0.1:8000/docs**. The frontend proxies `/api` to the backend. Keep both servers bound to loopback; this is a single-user local app without authentication.

1. Create a project with a title, exact series name, and optional YouTube watch URL.
2. Choose the transcript language. Paste `[HH:MM:SS] Chinese text`, optionally with millisecond fractions, or import Chinese SRT to translate. Choose **English — ready to display** to import timestamped English text or English SRT directly; it is immediately ready for export and the YouTube overlay, without calling the LLM API.
3. For Chinese imports, select or enter an API model ID and translate. Review low-confidence lines.
4. Edit any cue. Check **Save as terminology rule** to remember a term. Enter individual source variants separated by `|`, and the exact English **term**, rather than an entire sentence when only one name needs locking.
5. Download SRT, copy/download JSON, or send the finished subtitles to the Chrome extension.

The four Zeztz examples are seeded once, using the terminology supplied in the brief. They are editable examples, not independently verified official references. No sample projects or fake translations are inserted into your workspace.

For timestamped-text imports, consecutive lines with the same timestamp are treated as simultaneous dialogue and combined into one multiline subtitle cue. This preserves both speakers and keeps the overlay synchronized. Timestamped lines that go backward still need to be reordered.

## Chrome extension

```powershell
npm.cmd run build
```

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select **`extension/dist`**. Reload any already-open YouTube tabs after installing.

- Open a project's linked YouTube video. The popup lists projects matching its video ID. Choose one and click **Load subtitles**.
- Alternatively, copy the extension ID from `chrome://extensions` into the studio's Export & watch page and click **Send to browser extension**.
- Enable/disable the overlay and adjust delay in **0.1-second** increments. Positive delay displays subtitles later.
- Cues are cached per video in Chrome local storage, so loaded subtitles work with the backend stopped. A new export/load replaces that video's cached project.
- The content script loads on all YouTube pages to handle YouTube's single-page navigation, but only displays overlays on `/watch`. It hides during detected ads, follows seeks, and uses `video.currentTime`. YouTube's own captions are never changed.
- The extension accepts studio messages only from `localhost:5173` and `127.0.0.1:5173`. It requests only storage, active-tab access, and the local backend hosts. There is no cloud service.

## Persistent memory and translation behavior

SQLite is the source of truth, stored in **`data/subtitles.sqlite3`**. Corrections are saved transactionally with optional rules, including source snapshots that survive transcript replacement. Manual cue saves also record correction history. Back up the `data` directory with the server stopped. Do not delete it when upgrading.

- A rule can be global, series-specific, or episode-specific. Episode rules override series rules, which override global rules for the same source variant. Newer rules resolve duplicate variants within the same scope. Longer matching variants take precedence over contained variants.
- Each 30-cue translation chunk includes up to three neighboring cues on each side, resolved applicable rules per cue, and relevant prior corrections for the project/series. Temperature is `0.1`.
- The configured API receives a JSON Schema structured-output request through `/chat/completions`. Responses are validated for exact cue indexes/order, confidence bounds, concise subtitle text, commentary markers, and applicable locked terms. Invalid output retries twice, then fails without saving any part of the new draft. Original timing is never taken from the model.
- A project revision check prevents a translation from overwriting edits or transcript imports completed while it was running. Re-translation explicitly replaces the draft after confirmation; saved rules and correction history remain.
- Timestamp-only transcripts lack end times. Ends are inferred as the next start or six seconds later, whichever is earlier; the last cue lasts four seconds. SRT import preserves supplied start/end milliseconds and multiline text. Strictly increasing starts are required. Overlapping SRT cues are supported; the overlay chooses the most recently started active cue.
- Model output is a **draft**. Structured-output validation cannot guarantee semantic accuracy or detect every form of commentary. Long lines are rejected, and ambiguous lines require a note. Official attack names or catchphrases may need manual verification. Japanese subtitles/audio and verified reference inputs remain future work.

Optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUBTITLES_DB` | `data/subtitles.sqlite3` | SQLite file path |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL, including `/v1` when required |
| `OPENAI_API_KEY` | empty | Bearer token; may be omitted for an unauthenticated local-compatible API |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Default model ID shown in the studio and used when the API request omits one |

The studio model field is saved in browser local storage. Values already saved there take precedence over `OPENAI_MODEL`; clear the saved field or enter the new model ID when switching providers.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd test
npm.cmd run build
```

Backend tests cover parsing, SRT round trips, rule precedence, persistent/atomic corrections, replacement safeguards, API isolation, locked-term validation, structured OpenAI-compatible requests/retries/chunks using a mock transport, and concurrent review edits. Extension tests cover boundary times, gaps, seeking, delays, overlaps, and payload validation. Real model quality and YouTube/Chrome integration also require a manual smoke test with the configured API and the unpacked extension running.

## Implementation notes

`backend/` contains the API, parser, SQLite schema and LLM client. `src/` contains the React studio. `extension/` contains the Manifest V3 service worker, TypeScript overlay, and React popup. `npm run build` emits the studio in `dist/` and the unpacked extension in `extension/dist/`. The studio build needs a server proxying `/api` to FastAPI; the supplied Vite dev command already does this.

The API includes all endpoints from the brief, plus `GET /projects`, `GET /health`, and `POST /transcript/preview`. The schema adds source variants, episode scope, model notes, revision tracking, and correction source snapshots. Semantic embeddings are not needed for deterministic terminology matching and remain optional future work.

Protocol references: [OpenAI-compatible Chat Completions and structured outputs](https://platform.openai.com/docs/guides/structured-outputs), [Chrome extension messaging](https://developer.chrome.com/docs/extensions/develop/concepts/messaging).

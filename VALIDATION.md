# Verification record

- Backend: **12 tests passed** with Python 3.14.6. The code targets Python 3.12+, but this workspace does not have a Python 3.12 interpreter for a separate compatibility run.
- Frontend and extension: TypeScript check, Vite production build, and Manifest V3 esbuild bundles passed with Node 22.20.0.
- Extension: **3 tests passed** covering synchronization boundaries, gaps, seeks, signed delay, overlapping cues, and payload validation.
- Dependency installation: npm reported **0 vulnerabilities**.
- The OpenAI-compatible Chat Completions request shape, bearer authentication, JSON Schema response format, validation retry, and 30-cue chunking are covered with a mock HTTP transport. A live provider smoke test requires `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` to be configured.
- Earlier local-model smoke testing exposed untranslated Chinese in the English field; explicit rejection of remaining Chinese/Japanese text remains covered by a regression assertion. Model quality still requires human review.
- Backend startup and local HTTP health endpoint verified.
- English timestamped text is covered by an API test: its text is stored as ready subtitle output, exports as SRT without a translation request, and the translation endpoint rejects the already-English project.
- Consecutive duplicate timestamps in timestamped-text imports are covered by a parser test: they become one multiline cue rather than a zero-duration cue.
- No browser connection was available in this session. Visual UI verification and installation/playback of the unpacked extension on real YouTube remain **unverified**. Automated timing tests do not substitute for that integration check.
- Two upstream test-client deprecation warnings remain (Starlette/httpx and AnyIO alias). They do not affect the passing tests.

Manual acceptance check: create a project linked to a YouTube video; preview/import a Chinese transcript; translate with an installed model; correct a line and save a series rule; restart the backend and verify the rule persists; export SRT/JSON; load `extension/dist` in Chrome and select the project; seek across cue boundaries, toggle subtitles, adjust delay, and navigate to another video to verify isolation. Stop the backend and confirm the loaded video's cached subtitles continue working.

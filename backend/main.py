import json
import os
import re
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .db import connect, init_db, now, rule_dict, uid
from .parser import export_srt, parse_transcript
from .translation import api_base_url, api_headers, translate


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title='Subline — local subtitle studio', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
                   allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Content-Type'])


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class ProjectInput(Input):
    title: str = Field(min_length=1, max_length=200)
    series: str | None = Field(default=None, max_length=200)
    youtube_url: str | None = None


class TranscriptInput(Input):
    text: str = Field(min_length=1, max_length=2_000_000)
    format: Literal['text', 'srt'] = 'text'
    language: Literal['chinese', 'english'] = 'chinese'
    replace: bool = False


class TranslateInput(Input):
    model: str = Field(default_factory=lambda: os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), min_length=1, max_length=200)


class RuleInput(Input):
    series: str | None = None
    project_id: str | None = None
    source_variants: list[str] = Field(min_length=1, max_length=30)
    target_term: str = Field(min_length=1, max_length=160)
    source_language: str = 'auto'
    rule_type: Literal['locked', 'preferred'] = 'locked'
    note: str | None = None

    @model_validator(mode='after')
    def clean(self):
        self.source_variants = list(dict.fromkeys(v.strip() for v in self.source_variants))
        if any(not v or len(v) > 200 for v in self.source_variants):
            raise ValueError('Source variants must contain 1–200 characters.')
        self.series = self.series or None
        self.project_id = self.project_id or None
        return self


class CorrectionInput(Input):
    cue_id: str
    corrected_translation: str = Field(min_length=1, max_length=500)
    reason: str | None = None
    save_as_glossary_rule: bool = False
    source_variants: list[str] = Field(default_factory=list)
    target_term: str | None = None
    series: str | None = None
    scope: Literal['global', 'series', 'episode'] = 'series'
    rule_type: Literal['locked', 'preferred'] = 'locked'


class CueInput(Input):
    translated_text: str = Field(min_length=1, max_length=500)


def project(db, project_id):
    row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Project not found.')
    return dict(row)


def cues_for(db, project_id):
    return [dict(r) for r in db.execute('SELECT * FROM subtitle_cues WHERE project_id=? ORDER BY cue_index', (project_id,))]


def video_id(value):
    if not value:
        return None
    if re.fullmatch(r'[\w-]{11}', value):
        return value
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    candidate = parsed.path.strip('/') if host == 'youtu.be' else (
        parse_qs(parsed.query).get('v', [''])[0] if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com') else '')
    if parsed.scheme not in ('https', 'http') or not re.fullmatch(r'[\w-]{11}', candidate):
        raise HTTPException(422, 'Use a YouTube watch URL, youtu.be URL, or 11-character video ID.')
    return candidate


@app.get('/health')
async def health():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(api_base_url() + '/models', headers=api_headers())
            response.raise_for_status()
            models = [m['id'] for m in response.json().get('data', [])
                      if isinstance(m, dict) and isinstance(m.get('id'), str)]
            return dict(status='ok', llm=True, models=models,
                        default_model=os.getenv('OPENAI_MODEL') or (models[0] if models else 'gpt-4.1-mini'))
    except (httpx.HTTPError, ValueError, KeyError):
        return dict(status='ok', llm=False, models=[],
                    default_model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'))


@app.get('/projects')
def list_projects(youtube_video_id: str | None = None):
    with connect() as db:
        rows = db.execute('''SELECT p.*, count(c.id) AS cue_count,
          count(c.translated_text) AS translated_count FROM projects p
          LEFT JOIN subtitle_cues c ON c.project_id=p.id
          WHERE (? IS NULL OR p.youtube_video_id=?) GROUP BY p.id ORDER BY p.created_at DESC''',
                          (youtube_video_id, youtube_video_id))
        return [dict(r) for r in rows]


@app.post('/projects', status_code=201)
def create_project(body: ProjectInput):
    with connect() as db:
        id = uid()
        db.execute('''INSERT INTO projects
          (id,title,series,youtube_video_id,transcript_language,revision,created_at)
          VALUES (?,?,?,?,?,?,?)''',
                   (id, body.title, body.series or None, video_id(body.youtube_url), 'chinese', 0, now()))
        return project(db, id)


@app.get('/projects/{project_id}')
def get_project(project_id: str):
    with connect() as db:
        return {**project(db, project_id), 'cues': cues_for(db, project_id)}


@app.post('/transcript/preview')
def preview(body: TranscriptInput):
    try:
        return parse_transcript(body.text, body.format)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post('/projects/{project_id}/transcript')
def import_transcript(project_id: str, body: TranscriptInput):
    cues = preview(body)
    with connect() as db:
        project(db, project_id)
        if cues_for(db, project_id) and not body.replace:
            raise HTTPException(409, 'This project has cues. Confirm replacement to import again.')
        db.execute('DELETE FROM subtitle_cues WHERE project_id=?', (project_id,))
        for c in cues:
            translated = c['source_text'] if body.language == 'english' else None
            notes = 'Imported English transcript' if body.language == 'english' else None
            confidence = 1.0 if body.language == 'english' else None
            db.execute('''INSERT INTO subtitle_cues
              (id,project_id,cue_index,start_ms,end_ms,source_text,translated_text,confidence,notes)
              VALUES (?,?,?,?,?,?,?,?,?)''',
                       (uid(), project_id, c['cue_index'], c['start_ms'], c['end_ms'], c['source_text'],
                        translated, confidence, notes))
        db.execute('UPDATE projects SET transcript_language=?,revision=revision+1 WHERE id=?',
                   (body.language, project_id))
        return cues_for(db, project_id)


@app.post('/projects/{project_id}/translate')
async def translate_project(project_id: str, body: TranslateInput):
    with connect() as db:
        p = project(db, project_id)
        cues = cues_for(db, project_id)
        rules = [rule_dict(r) for r in db.execute('''SELECT * FROM glossary_rules WHERE
          project_id=? OR (project_id IS NULL AND (series IS NULL OR series=?))''', (project_id, p['series']))]
        corrections = [dict(r) for r in db.execute('''SELECT h.source_text,h.corrected_translation,h.reason
          FROM correction_history h JOIN projects p ON h.project_id=p.id
          WHERE p.id=? OR (? IS NOT NULL AND p.series=?) ORDER BY h.created_at DESC LIMIT 500''',
                                                   (project_id, p['series'], p['series']))]
    if not cues:
        raise HTTPException(422, 'Import a transcript first.')
    if p['transcript_language'] == 'english':
        raise HTTPException(422, 'This project already contains ready-to-display English subtitles.')
    try:
        results = await translate(cues, rules, corrections, body.model)
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'LLM API request failed. Check the OpenAI-compatible API URL, key, and model.') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if project(db, project_id)['revision'] != p['revision']:
            raise HTTPException(409, 'Cues changed during translation. Your edits were preserved; retry translation.')
        for result, cue in zip(results, cues):
            db.execute('UPDATE subtitle_cues SET translated_text=?,confidence=?,notes=? WHERE id=?',
                       (result.english, result.confidence, result.notes, cue['id']))
        db.execute('UPDATE projects SET revision=revision+1 WHERE id=?', (project_id,))
        return cues_for(db, project_id)


@app.get('/projects/{project_id}/subtitles')
def subtitles(project_id: str):
    with connect() as db:
        p = project(db, project_id)
        return dict(version=1, project=p, cues=cues_for(db, project_id))


@app.post('/projects/{project_id}/export/srt')
def srt(project_id: str):
    try:
        text = export_srt(subtitles(project_id)['cues'])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(text, media_type='application/x-subrip',
                    headers={'Content-Disposition': 'attachment; filename="subtitles.srt"'})


def save_rule(db, body, id=None):
    if body.project_id:
        p = project(db, body.project_id)
        body.series = p['series']
    id = id or uid()
    values = (body.series, body.project_id, body.source_variants[0], json.dumps(body.source_variants, ensure_ascii=False),
              body.target_term, body.source_language, body.rule_type, body.note, now())
    db.execute('''INSERT INTO glossary_rules (series,project_id,source_term,source_variants,target_term,
      source_language,rule_type,note,updated_at,id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET series=excluded.series,project_id=excluded.project_id,
      source_term=excluded.source_term,source_variants=excluded.source_variants,target_term=excluded.target_term,
      source_language=excluded.source_language,rule_type=excluded.rule_type,note=excluded.note,updated_at=excluded.updated_at''',
               (*values, id, now()))
    return rule_dict(db.execute('SELECT * FROM glossary_rules WHERE id=?', (id,)).fetchone())


@app.get('/glossary')
def glossary(series: str | None = None, project_id: str | None = None):
    with connect() as db:
        rows = db.execute('''SELECT * FROM glossary_rules WHERE (? IS NULL OR series=? OR series IS NULL)
          AND (? IS NULL OR project_id=? OR project_id IS NULL) ORDER BY updated_at DESC''',
                          (series, series, project_id, project_id))
        return [rule_dict(r) for r in rows]


@app.post('/glossary', status_code=201)
def add_rule(body: RuleInput):
    with connect() as db:
        return save_rule(db, body)


@app.put('/glossary/{rule_id}')
def edit_rule(rule_id: str, body: RuleInput):
    with connect() as db:
        if not db.execute('SELECT 1 FROM glossary_rules WHERE id=?', (rule_id,)).fetchone():
            raise HTTPException(404, 'Rule not found.')
        return save_rule(db, body, rule_id)


@app.delete('/glossary/{rule_id}')
def delete_rule(rule_id: str):
    with connect() as db:
        if not db.execute('DELETE FROM glossary_rules WHERE id=?', (rule_id,)).rowcount:
            raise HTTPException(404, 'Rule not found.')
        return {'deleted': True}


def save_correction(db, body):
    row = db.execute('SELECT * FROM subtitle_cues WHERE id=?', (body.cue_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Cue not found.')
    cue = dict(row)
    p = project(db, cue['project_id'])
    rule = None
    if body.save_as_glossary_rule:
        series = body.series or p['series']
        if body.scope == 'series' and not series:
            raise HTTPException(422, 'Specify a series or choose global / episode scope.')
        try:
            rule = RuleInput(series=series if body.scope == 'series' else None,
                             project_id=p['id'] if body.scope == 'episode' else None,
                             source_variants=body.source_variants,
                             target_term=body.target_term or body.corrected_translation,
                             rule_type=body.rule_type, note=body.reason)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        rule = save_rule(db, rule)
    db.execute('INSERT INTO correction_history VALUES (?,?,?,?,?,?,?,?,?)',
               (uid(), p['id'], cue['id'], cue['source_text'], cue['translated_text'] or '',
                body.corrected_translation, body.reason, int(body.save_as_glossary_rule), now()))
    db.execute('UPDATE subtitle_cues SET translated_text=?,confidence=NULL,notes=? WHERE id=?',
               (body.corrected_translation, 'Reviewed by user', cue['id']))
    db.execute('UPDATE projects SET revision=revision+1 WHERE id=?', (p['id'],))
    return dict(cue=dict(db.execute('SELECT * FROM subtitle_cues WHERE id=?', (cue['id'],)).fetchone()), rule=rule)


@app.post('/corrections')
def correct(body: CorrectionInput):
    with connect() as db:
        return save_correction(db, body)


@app.put('/projects/{project_id}/cues/{cue_id}')
def edit_cue(project_id: str, cue_id: str, body: CueInput):
    with connect() as db:
        project(db, project_id)
        if not db.execute('SELECT 1 FROM subtitle_cues WHERE id=? AND project_id=?', (cue_id, project_id)).fetchone():
            raise HTTPException(404, 'Cue not found in this project.')
        return save_correction(db, CorrectionInput(cue_id=cue_id, corrected_translation=body.translated_text))['cue']

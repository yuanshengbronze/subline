import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


@contextmanager
def connect():
    path = Path(os.getenv('SUBTITLES_DB', 'data/subtitles.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, series TEXT, youtube_video_id TEXT,
          transcript_language TEXT NOT NULL DEFAULT 'chinese' CHECK(transcript_language IN ('chinese','english')),
          revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS subtitle_cues (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          cue_index INTEGER NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
          source_text TEXT NOT NULL, translated_text TEXT, confidence REAL, notes TEXT,
          UNIQUE(project_id, cue_index));
        CREATE TABLE IF NOT EXISTS glossary_rules (
          id TEXT PRIMARY KEY, series TEXT, project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
          source_term TEXT NOT NULL, source_variants TEXT NOT NULL, target_term TEXT NOT NULL,
          source_language TEXT DEFAULT 'auto', rule_type TEXT NOT NULL CHECK(rule_type IN ('locked','preferred')),
          note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS correction_history (
          id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id),
          cue_id TEXT REFERENCES subtitle_cues(id) ON DELETE SET NULL, source_text TEXT NOT NULL,
          original_translation TEXT NOT NULL, corrected_translation TEXT NOT NULL, reason TEXT,
          saved_as_glossary_rule INTEGER DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        # Keep existing local workspaces compatible with English-ready imports.
        project_columns = {row['name'] for row in db.execute('PRAGMA table_info(projects)')}
        if 'transcript_language' not in project_columns:
            db.execute("ALTER TABLE projects ADD COLUMN transcript_language TEXT NOT NULL DEFAULT 'chinese' "
                       "CHECK(transcript_language IN ('chinese','english'))")
        if not db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
            for variants, target, note in [
                (['騎士', '骑士', 'ライダー'], 'Rider', 'Never translate as Superhero.'),
                (['衝擊消亡', '冲击消亡', 'インパクト消滅'], 'Impact Banish!', 'Never use Impact Extinction.'),
                (['夢魘', '梦魇', 'ナイトメア'], 'Nightmare', None),
                (['CODE'], 'CODE', None),
            ]:
                db.execute('INSERT INTO glossary_rules VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (uid(), 'Kamen Rider Zeztz', None, variants[0], json.dumps(variants, ensure_ascii=False),
                            target, 'auto', 'locked', note, now(), now()))
            db.execute("INSERT INTO settings VALUES ('seeded','1')")


def rule_dict(row):
    result = dict(row)
    result['source_variants'] = json.loads(result['source_variants'])
    return result

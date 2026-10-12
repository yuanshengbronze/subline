"""Strict timestamp and SRT parsing. All internal timing is integer milliseconds."""
import re

STAMP = r"(\d{2,}):([0-5]\d):([0-5]\d)(?:[,.](\d{1,3}))?"


def milliseconds(parts):
    h, m, s, fraction = parts
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int((fraction or '0').ljust(3, '0'))


def parse_transcript(text: str, format: str = 'text') -> list[dict]:
    text = text.lstrip('\ufeff').replace('\r\n', '\n').strip()
    if not text:
        raise ValueError('Paste a transcript first.')
    cues = []
    if format == 'srt':
        for block in re.split(r'\n\s*\n', text):
            lines = block.splitlines()
            if lines and lines[0].strip().isdigit():
                lines.pop(0)
            match = re.fullmatch(STAMP + r'\s+-->\s+' + STAMP, lines[0].strip()) if lines else None
            if not match or len(lines) < 2:
                raise ValueError(f'Invalid SRT block {len(cues) + 1}.')
            start, end = milliseconds(match.groups()[:4]), milliseconds(match.groups()[4:])
            source = '\n'.join(lines[1:]).strip()
            if end <= start or not source:
                raise ValueError('SRT cues need text and an end after their start.')
            cues.append(dict(start_ms=start, end_ms=end, source_text=source))
    else:
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            match = re.fullmatch(r'\s*\[' + STAMP + r'\]\s*(.+)', line)
            if not match or not match.group(5).strip():
                raise ValueError(f'Line {number}: expected [HH:MM:SS] dialogue.')
            cues.append(dict(start_ms=milliseconds(match.groups()[:4]), end_ms=None,
                             source_text=match.group(5).strip()))

        # Timestamp-only transcripts often put overlapping speakers on separate
        # lines with the same start. A cue cannot have a zero-length inferred
        # duration, so keep both utterances as one multiline subtitle. This is
        # also the format the overlay uses for simultaneous dialogue.
        merged = []
        for cue in cues:
            if merged and cue['start_ms'] == merged[-1]['start_ms']:
                merged[-1]['source_text'] += '\n' + cue['source_text']
            else:
                merged.append(cue)
        cues = merged
    for i, cue in enumerate(cues):
        if i and cue['start_ms'] < cues[i - 1]['start_ms']:
            raise ValueError('Cue start times must be in chronological order.')
        if cue['end_ms'] is None:
            next_start = cues[i + 1]['start_ms'] if i + 1 < len(cues) else cue['start_ms'] + 4000
            cue['end_ms'] = min(next_start, cue['start_ms'] + 6000)
        cue['cue_index'] = i + 1
    if len(cues) > 10000:
        raise ValueError('A project can contain at most 10,000 cues.')
    return cues


def timestamp(ms: int) -> str:
    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02},{millis:03}'


def export_srt(cues: list[dict]) -> str:
    if not cues or any(not c['translated_text'] for c in cues):
        raise ValueError('Translate or edit every cue before exporting English SRT.')
    return '\n\n'.join(f"{c['cue_index']}\n{timestamp(c['start_ms'])} --> {timestamp(c['end_ms'])}\n{c['translated_text']}"
                       for c in cues) + '\n'

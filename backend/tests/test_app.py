import json

import pytest
from fastapi.testclient import TestClient

from backend.db import connect, init_db
from backend.main import app
from backend.parser import parse_transcript, export_srt
from backend.translation import Batch, applicable_rules, validate_batch


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('SUBTITLES_DB', str(tmp_path / 'test.sqlite3'))
    with TestClient(app) as client:
        yield client


def make_project(client, series='Kamen Rider Zeztz', text='[00:17:43] 騎士\n[00:18:11] 變身'):
    p = client.post('/projects', json={'title': 'Episode 1', 'series': series,
                                     'youtube_url': 'https://youtu.be/dQw4w9WgXcQ'}).json()
    cues = client.post(f"/projects/{p['id']}/transcript", json={'text': text}).json()
    return p, cues


def test_parser_preserves_timing_and_infers_ends():
    cues = parse_transcript('[00:17:43.125] 變身\n[00:18:11] 早晨 騎士')
    assert cues[0]['start_ms'] == 1063125
    assert cues[0]['end_ms'] == 1069125
    assert cues[1]['end_ms'] == 1095000
    with pytest.raises(ValueError):
        parse_transcript('[00:00:02] 甲\n[00:00:01] 乙')
    with pytest.raises(ValueError):
        parse_transcript('[00:99:00] 甲')
    with pytest.raises(ValueError):
        parse_transcript('[00:00:00] 甲\ninvalid')


def test_parser_merges_same_time_dialogue_into_one_multiline_cue():
    cues = parse_transcript('[00:00:10] First speaker\n[00:00:10] Second speaker\n[00:00:13] Next line')
    assert len(cues) == 2
    assert cues[0]['source_text'] == 'First speaker\nSecond speaker'
    assert cues[0]['start_ms'] == 10000
    assert cues[0]['end_ms'] == 13000
    assert cues[1]['cue_index'] == 2


def test_srt_roundtrip():
    original = '1\n00:00:01,234 --> 00:00:03,456\nHello\nRider\n\n2\n00:00:03,456 --> 00:00:04,789\nGo!\n'
    cues = parse_transcript(original, 'srt')
    for c in cues:
        c['translated_text'] = c['source_text']
    assert export_srt(cues) == original


def test_english_import_is_ready_without_translation(client, monkeypatch):
    p = client.post('/projects', json={'title': 'English episode'}).json()
    response = client.post(f"/projects/{p['id']}/transcript", json={
        'text': '[00:00:01] Hello there!\n[00:00:03.500] Let\'s go.', 'language': 'english'})
    assert response.status_code == 200
    cues = response.json()
    assert [cue['translated_text'] for cue in cues] == ['Hello there!', "Let's go."]
    assert [cue['confidence'] for cue in cues] == [1.0, 1.0]
    assert client.get(f"/projects/{p['id']}").json()['transcript_language'] == 'english'
    assert client.post(f"/projects/{p['id']}/export/srt").status_code == 200
    assert client.post(f"/projects/{p['id']}/translate", json={}).status_code == 422


def test_correction_and_rule_are_persistent_and_atomic(client):
    p, cues = make_project(client)
    body = dict(cue_id=cues[0]['id'], corrected_translation='Rider!', save_as_glossary_rule=True,
                source_variants=['騎士', 'ライダー'], target_term='Rider', scope='episode')
    result = client.post('/corrections', json=body)
    assert result.status_code == 200
    assert result.json()['rule']['project_id'] == p['id']
    init_db()  # Restart initialization must not reset memory or duplicate seeds.
    assert len(client.get('/glossary').json()) == 5
    assert client.get(f"/projects/{p['id']}").json()['cues'][0]['translated_text'] == 'Rider!'
    body.update(source_variants=[], corrected_translation='Should not save')
    assert client.post('/corrections', json=body).status_code == 422
    assert client.get(f"/projects/{p['id']}").json()['cues'][0]['translated_text'] == 'Rider!'
    with connect() as db:
        assert db.execute('SELECT count(*) FROM correction_history').fetchone()[0] == 1


def test_import_requires_explicit_replacement_and_keeps_history(client):
    p, cues = make_project(client)
    client.post('/corrections', json={'cue_id': cues[0]['id'], 'corrected_translation': 'Rider'})
    url = f"/projects/{p['id']}/transcript"
    assert client.post(url, json={'text': '[00:00:01] 好'}).status_code == 409
    assert client.post(url, json={'text': '[00:00:01] 好', 'replace': True}).status_code == 200
    with connect() as db:
        row = dict(db.execute('SELECT * FROM correction_history').fetchone())
        assert row['source_text'] == '騎士'
        assert row['cue_id'] is None


def test_glossary_crud_and_project_isolation(client):
    p, cues = make_project(client)
    p2, _ = make_project(client, series='Another show')
    body = dict(source_variants=['你好'], target_term='Hello', rule_type='preferred')
    r = client.post('/glossary', json=body).json()
    assert client.put('/glossary/' + r['id'], json={**body, 'target_term': 'Hi'}).json()['target_term'] == 'Hi'
    assert client.put(f"/projects/{p2['id']}/cues/{cues[0]['id']}", json={'translated_text': 'Oops'}).status_code == 404
    assert client.delete('/glossary/' + r['id']).status_code == 200
    assert client.delete('/glossary/' + r['id']).status_code == 404
    assert client.get('/projects?youtube_video_id=dQw4w9WgXcQ').status_code == 200
    assert client.get('/projects/missing').status_code == 404
    assert client.post('/projects', json={'title': 'Bad', 'youtube_url': 'https://evil.test/watch?v=dQw4w9WgXcQ'}).status_code == 422


def test_model_output_validation(client):
    _, cues = make_project(client)
    rules = client.get('/glossary').json()
    batch = Batch.model_validate({'cues': [dict(cue_index=1, english='Rider', confidence=.9),
                                           dict(cue_index=2, english='Transform!', confidence=.8)]})
    assert len(validate_batch(batch, cues, rules)) == 2
    batch.cues[0].english = '騎士 Rider'
    with pytest.raises(ValueError, match='localize it into English'):
        validate_batch(batch, cues, rules)
    batch.cues[0].english = 'Superhero'
    with pytest.raises(ValueError, match='locked term'):
        validate_batch(batch, cues, rules)
    batch.cues[0].english = 'Riders'
    with pytest.raises(ValueError, match='locked term'):
        validate_batch(batch, cues, rules)
    batch.cues[0].english = 'Rider'
    batch.cues[0].confidence = .5
    with pytest.raises(ValueError, match='ambiguity note'):
        validate_batch(batch, cues, rules)
    batch.cues.reverse()
    with pytest.raises(ValueError, match='indexes'):
        validate_batch(batch, cues, rules)
    with pytest.raises(ValueError):
        Batch.model_validate({'cues': [dict(cue_index=1, english='Hello', confidence=.9, start_ms=0)]})


def test_scope_precedence_and_longest_variants():
    base = dict(project_id=None, series=None, updated_at='1', rule_type='locked')
    rules = [{**base, 'source_variants': ['騎士'], 'target_term': 'Knight'},
             {**base, 'series': 'Show', 'source_variants': ['騎士'], 'target_term': 'Rider'},
             {**base, 'project_id': 'ep', 'source_variants': ['騎士'], 'target_term': 'Masked Rider'},
             {**base, 'source_variants': ['黑暗騎士'], 'target_term': 'Dark Rider'}]
    assert [r['target_term'] for r in applicable_rules({'source_text': '騎士'}, rules)] == ['Masked Rider']
    assert [r['target_term'] for r in applicable_rules({'source_text': '黑暗騎士'}, rules)] == ['Dark Rider']


def test_translation_atomic_commit_and_concurrent_edit(client, monkeypatch):
    from backend import main
    p, cues = make_project(client)
    async def fake(cues, rules, corrections, model):
        return Batch.model_validate({'cues': [dict(cue_index=c['cue_index'], english='Rider!', confidence=.9) for c in cues]}).cues
    monkeypatch.setattr(main, 'translate', fake)
    assert client.post(f"/projects/{p['id']}/translate", json={}).status_code == 200
    before = client.get(f"/projects/{p['id']}").json()['cues']
    assert [(c['start_ms'], c['end_ms']) for c in before] == [(c['start_ms'], c['end_ms']) for c in cues]
    assert client.post(f"/projects/{p['id']}/export/srt").status_code == 200
    async def concurrent(*args):
        import asyncio
        await asyncio.to_thread(client.post, '/corrections', json={'cue_id': cues[0]['id'], 'corrected_translation': 'User wins'})
        return await fake(*args)
    monkeypatch.setattr(main, 'translate', concurrent)
    assert client.post(f"/projects/{p['id']}/translate", json={}).status_code == 409
    assert client.get(f"/projects/{p['id']}").json()['cues'][0]['translated_text'] == 'User wins'


def test_openai_compatible_client_chunks_and_retries(monkeypatch):
    import asyncio
    import httpx
    from backend import translation
    cues = parse_transcript('\n'.join(f'[00:00:{i:02}] 你好' for i in range(35)))
    calls = []
    async def handler(request):
        payload = json.loads(request.content)
        calls.append((request, payload))
        prompt = payload['messages'][1]['content'].split('\nPrevious attempt')[0]
        data = json.loads(prompt)
        items = data['cues']
        # First generation fails exact cue validation, then succeeds on retry.
        if len(calls) == 1:
            items = items[:-1]
        content = json.dumps({'cues': [dict(cue_index=c['cue_index'], english='Hello', confidence=.95) for c in items]})
        return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
    original = httpx.AsyncClient
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://llm.example.test/v1/')
    monkeypatch.setenv('OPENAI_API_KEY', 'secret-test-key')
    monkeypatch.setattr(translation.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(translation.translate(cues, [], [], 'test-model'))
    assert len(result) == 35
    assert len(calls) == 3
    request, first = calls[0]
    assert str(request.url) == 'https://llm.example.test/v1/chat/completions'
    assert request.headers['authorization'] == 'Bearer secret-test-key'
    assert first['stream'] is False
    assert first['temperature'] == .1
    assert first['response_format']['type'] == 'json_schema'
    assert first['response_format']['json_schema']['schema']['type'] == 'object'
    final = json.loads(calls[-1][1]['messages'][1]['content'])
    assert len(final['preceding']) == 3
    assert len(final['cues']) == 5


def test_cors_and_partial_export(client):
    p, _ = make_project(client)
    assert client.post(f"/projects/{p['id']}/export/srt").status_code == 422
    assert client.options('/projects', headers={'Origin': 'https://evil.test', 'Access-Control-Request-Method': 'POST'}).status_code == 400

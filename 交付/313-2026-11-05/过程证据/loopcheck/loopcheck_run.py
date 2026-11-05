"""Walk the product's real chain: feedback -> wrong item -> correction -> topic -> review.

Real configured model is used wherever the product calls one (agent ingest, photo annotation).
Everything else is the product's own HTTP API driven from a loopback client against a throwaway
temp store created by the product's own test fixture. No product code is patched except the model
transport seam (family_llm._chat_json), exactly like work/realrun/run_real_model.py.
"""
import datetime as dt
import hashlib
import http.client as httpc
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from pathlib import Path

REPO = Path('/Users/joyrush/.local/share/family-learning/public-integration-20260926')
WORK = Path('/Users/joyrush/Documents/deepseek-harness/default-workspace/work/loopcheck')
PACK = WORK / 'knowledge' / 'cn-math-taxonomy-e0f931b'
EVID = WORK / 'evidence'
EVID.mkdir(parents=True, exist_ok=True)
CONF = Path('/Users/joyrush/.local/share/family-learning/application/private/model.json')
NODE = '/Users/joyrush/.node/bin/node'
DAY = '2026-11-04'
DUE = '2026-11-05'
TRACE = []
MODEL_CALLS = []


def _scrub(value):
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if k not in ('token', 'api_key')}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def ev(name, obj):
    p = EVID / name
    p.write_text(json.dumps(_scrub(obj), ensure_ascii=False, indent=2))
    return str(p.relative_to(WORK))


def rk():
    return uuid.uuid4().hex  # 32 chars, matches [A-Za-z0-9_-]{16,128}


# ---------------------------------------------------------------- real model setup
conf = json.loads(CONF.read_text())
os.environ['FAMILY_LLM_BASE_URL'] = conf['base_url']
os.environ['FAMILY_LLM_MODEL'] = conf['model']
os.environ['FAMILY_LLM_LIGHT_MODEL'] = conf.get('light_model') or ''
os.environ['FAMILY_LLM_API_KEY'] = conf['api_key']
os.environ['FAMILY_LLM_REASONING_EFFORT'] = conf.get('reasoning_effort') or ''
# Diagnostic (see evidence/pre-run-failures/light-effort-none.json): the selection draft on the light
# model burns its 45s budget on reasoning output (2x timeout, 1x incomplete "status!=completed").
# Pinning the light tier to effort=none is a configuration-only mitigation (no product code change):
# same request then completes in ~7s and creates the day's tasks from the real model.
os.environ.setdefault('FAMILY_LLM_LIGHT_REASONING_EFFORT', 'none')
os.environ['FAMILY_TAXONOMY_DIR'] = str(PACK)
os.chdir(REPO)
sys.path.insert(0, str(REPO))

import family_llm  # noqa: E402
ORIGINAL = family_llm._chat_json


def real_model(messages, schema, name, timeout=60, *, data_path=None):
    last = messages[-1]['content'] if messages else ''
    try:
        ctx = json.loads(last)
        brief = {k: ctx[k] for k in ('evidence',) if k in ctx}
    except Exception:
        if isinstance(last, list):
            brief = {'parts': len(last),
                     'images': sum(1 for part in last if isinstance(part, dict)
                                   and part.get('type') in ('image_url', 'input_image')),
                     'text_chars': sum(len(part.get('text') or '') for part in last
                                       if isinstance(part, dict))}
        else:
            brief = {'prompt_chars': len(last)}
    entry = {'call_index': len(MODEL_CALLS) + 1, 'name': name, 'model': conf['model'],
             'timeout_s': timeout, 'request_brief': brief,
             'started': dt.datetime.now().isoformat()}
    t0 = time.time()
    try:
        result = ORIGINAL(messages, schema, name, timeout, data_path=data_path)
    except Exception as e:
        entry.update(ok=False, error=f'{type(e).__name__}: {e}', duration_s=round(time.time() - t0, 2))
        MODEL_CALLS.append(entry)
        raise
    entry.update(ok=True, duration_s=round(time.time() - t0, 2), result=result)
    MODEL_CALLS.append(entry)
    return result


def node_engine(job, tag):
    job = dict(job, engine=str(PACK / 'diagnose' / 'engine.js'))
    jp = EVID / f'{tag}.job.json'
    jp.write_text(json.dumps(job, ensure_ascii=False))
    out = subprocess.run([NODE, str(WORK / 'engine_answer.js'), str(jp)],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f'engine driver failed: {out.stderr[:600]}')
    res = json.loads(out.stdout)
    ev(f'{tag}.result.json', res)
    return res


import family_agent as agent  # noqa: E402
import test_daily_list_whole_day as W  # noqa: E402


# ---------------------------------------------------------------- fixture + server
case = W.WholeDayTests('runTest')
case.setUp()
case.model.side_effect = real_model
payload, refs = case._ingest()
run_attempts = []
run_result = {}
run_now = case.now
SKIP_INGEST = os.environ.get('LOOPCHECK_SKIP_INGEST') == '1'
for attempt in range(1, 5 if not SKIP_INGEST else 1):
    t0 = time.time()
    before = len(MODEL_CALLS)
    if SKIP_INGEST:
        run_attempts.append({'attempt': 0, 'now': run_now.isoformat(),
                             'result': {'skipped': 'LOOPCHECK_SKIP_INGEST=1'}})
        break
    run_result = agent.run_once(case.app, run_now)
    run_attempts.append({'attempt': attempt, 'now': run_now.isoformat(),
                         'result': {k: run_result.get(k) for k in ('failed', 'processed', 'created')},
                         'duration_s': round(time.time() - t0, 1),
                         'model_calls': [{k: c.get(k) for k in ('call_index', 'name', 'ok', 'error', 'duration_s')}
                                         for c in MODEL_CALLS[before:]]})
    if run_result.get('created'):
        break
    run_now = run_now + dt.timedelta(minutes=10)
    time.sleep(2)
ev('00-agent-run.json', {'ingested_messages': len(payload.get('messages', [])),
                        'attempts': run_attempts,
                        'root': str(case.app.ROOT), 'data_dir': str(case.app.DATA),
                        'now': case.now.isoformat()})
ev('00b-model-calls.json', MODEL_CALLS)
BOOTSTRAP_NEEDED = not bool(run_result.get('created'))


class QuietHandler(case.app.Handler):
    def log_message(self, *a):
        pass


server = __import__('http.server', fromlist=['ThreadingHTTPServer']).ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
TOKEN = case.app.TOKEN


def http(method, path, body=None, headers=None, raw_body=None, step=''):
    conn = httpc.HTTPConnection('127.0.0.1', PORT, timeout=240)
    h = {'X-Family-Token': TOKEN}
    data = raw_body
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        h['Content-Type'] = 'application/json'
    if headers:
        h.update(headers)
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    b = r.read()
    ct = r.getheader('Content-Type', '')
    try:
        obj = json.loads(b) if 'json' in ct else {'bytes': len(b)}
    except Exception:
        obj = {'raw_head': b[:400].decode('utf-8', 'replace')}
    conn.close()
    entry = {'step': step, 'method': method, 'path': path,
             'request': body if body is not None else ('<binary %d bytes>' % len(raw_body) if raw_body else None),
             'status': r.status, 'response': obj}
    TRACE.append(entry)
    return r.status, obj


# Starting data. The brief allows starting from the archived real-model run; live selection
# timed out at the product's hard 45s limit (see 00-agent-run.json), so replay its saved tasks
# through the product's own manual-entry endpoint (POST /api/task/new), no fabricated content.
BOOTSTRAP = None
if BOOTSTRAP_NEEDED:
    archive = json.loads((Path('/Users/joyrush/Documents/deepseek-harness/default-workspace/work/realrun/real-model-run.json')).read_text())
    created = []
    for index, row in enumerate(archive['saved'], 1):
        body = {'child': row['child'], 'title': row['title'], 'due': row['due'],
                'action': row['action'], 'box': 'inbox',
                'request_key': 'loopcheck-boot-%02d' % index}
        status, result = http('POST', '/api/task/new', body, step='bootstrap-task')
        created.append({'request': body, 'status': status,
                        'response': result if status == 200 else result})
    BOOTSTRAP = {'source': 'work/realrun/real-model-run.json (archived real-model output)',
                 'reason': 'live family_agent_selection timed out at the product hard limit of 45s (4 attempts)',
                 'tasks': created}
    ev('00-agent-run.json', {'ingested_messages': len(payload.get('messages', [])),
                             'attempts': run_attempts,
                             'bootstrap': BOOTSTRAP,
                             'root': str(case.app.ROOT), 'data_dir': str(case.app.DATA),
                             'now': case.now.isoformat()})


def http_raw(path, step=''):
    conn = httpc.HTTPConnection('127.0.0.1', PORT, timeout=240)
    conn.request('GET', path, headers={'X-Family-Token': TOKEN})
    r = conn.getresponse()
    b = r.read()
    conn.close()
    TRACE.append({'step': step, 'method': 'GET', 'path': path, 'request': None,
                  'status': r.status, 'response': {'bytes': len(b),
                                                   'sha256': hashlib.sha256(b).hexdigest()}})
    return r.status, b


def q(sql, args=()):
    with case.app.connect() as c:
        return [dict(r) for r in c.execute(sql, args)]


def learning_view_of(child, day=DAY):
    st, view = http('GET', f'/api/day?child_id={urllib.parse.quote(child)}&day={day}', step='read-day')
    return st, view


def find_math_task():
    rows = q('SELECT * FROM manual_tasks ORDER BY rowid')
    for r in rows:
        if '练习册' in r['title'] or '第12页' in r['title']:
            return r
    raise RuntimeError('math task not found: ' + json.dumps(rows, ensure_ascii=False)[:800])


def find_task_update(task_id):
    rows = q('SELECT * FROM task_updates WHERE id=?', (task_id,))
    return rows[0]['updated'] if rows else ''


# ---------------------------------------------------------------- step 1: feedback
def step1():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (900, 520), 'white')
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 54)
    small = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 28)
    d.text((60, 46), '数学 · 练习册 第12页（全虚构）', font=small, fill=(60, 60, 60))
    d.text((60, 140), '第2题  2+3=6', font=font, fill=(10, 10, 10))
    d.text((60, 260), '第3题  5+4=9', font=font, fill=(10, 10, 10))
    d.text((60, 380), '第4题  3+3=6', font=font, fill=(10, 10, 10))
    photo = WORK / 'evidence' / 'fake-homework-page.png'
    img.save(photo)

    task = MATH_TASK
    child = task['child']
    fb_key = rk()
    resp = {}
    st, up = http('POST', '/api/upload', raw_body=photo.read_bytes(), step='1-upload',
                  headers={'X-File-Name': urllib.parse.quote(photo.name),
                           'X-Request-Key': rk(),
                           'Content-Type': 'image/png'})
    resp['upload_status'] = st
    resp['upload'] = up
    attach = (up.get('attachment') or up.get('upload') or {}).get('id')
    if not attach:
        raise RuntimeError('upload id missing: ' + json.dumps(up, ensure_ascii=False)[:400])
    expected = find_task_update(task['id'])
    body = {
        'task_id': task['id'], 'child': child, 'day': DAY, 'complete': False,
        'completion_note': '数学练习册第12页第2至4题：第3、4题完成，第2题 2+3 写成了 6；拍照留档，待订正。',
        'note': '数学练习册第12页第2至4题：第3、4题完成，第2题 2+3 写成了 6；拍照留档，待订正。',
        'category': '学习进展', 'subject': '数学', 'attachments': [attach], 'request_key': fb_key,
    }
    if expected:
        body['expected_updated'] = expected
    st, fb = http('POST', '/api/task/feedback', body, step='1-feedback')
    resp['feedback_status'] = st
    resp['feedback'] = fb
    if st != 200:
        raise RuntimeError('feedback failed: ' + json.dumps(fb, ensure_ascii=False)[:600])
    rec = fb['feedback']
    ev('01-feedback.json', resp)
    return {'task': task, 'child': child, 'attachment': attach, 'feedback_record': rec,
            'photo': str(photo.relative_to(WORK))}


# ---------------------------------------------------------------- step 2: wrong item
def step2(s1):
    task, child, attach = s1['task'], s1['child'], s1['attachment']
    st, draft = http('POST', '/api/wrong/annotate',
                     {'child': child, 'subject_hint': '数学', 'attachments': [attach]}, step='2-annotate')
    if st != 200:
        raise RuntimeError('annotate failed: ' + json.dumps(draft, ensure_ascii=False)[:800])
    region = None
    page = (draft.get('pages') or [{}])[0]
    for r in page.get('regions') or []:
        if r.get('kind') == 'wrong_item':
            region = r
            break
    region = region or {}
    item = {
        'attachment': attach,
        'label': region.get('label') or '第2题',
        'text': region.get('text') or '第2题 2+3=？',
        'answer': region.get('answer') or '6',
        'correction': region.get('correction') or '2+3=5',
        'note': '家长核对：照片上是全虚构练习页；第2题 2+3 写成 6，正确是 5。',
        'topic_hint': region.get('topic_hint') or '5以内的加法',
        'error_hint': region.get('error_hint') or '加法计算错误',
    }
    fb = s1['feedback_record']
    body = {'child': child, 'day': DAY, 'subject': '数学', 'task_id': task['id'],
            'feedback_record_id': fb['record_id'], 'feedback_created': fb['created'],
            'feedback_linked_at': fb.get('linked_task_at') or '',
            'request_key': rk(), 'items': [item]}
    st, saved = http('POST', '/api/wrong/save', body, step='2-wrong-save')
    if st != 200:
        raise RuntimeError('wrong save failed: ' + json.dumps(saved, ensure_ascii=False)[:800])
    rows = q("SELECT id,child,day,subject,title,note,source,related_record_id,linked_task_id,linked_task_at,followup_kind FROM records WHERE source='错题照片核对' ORDER BY id")
    wrong = rows[-1]
    st2, state = http('GET', f'/api/state', step='2-state')
    stv, day_view = learning_view_of(CHILD_ID)
    ev('02-wrong.json', {'annotate_raw': draft, 'model_used_region': bool(region), 'item_sent': item,
                         'save_response': saved, 'wrong_rows': rows, 'day_view': day_view})
    return {'wrong': wrong, 'state': state, 'day_view': day_view, 'annotate': draft,
            'saved': saved, 'item': item}


def learning_evidence(day_view):
    """Pull the wrong-item evidence cards out of a /api/day learning view."""
    out = []
    for subj in ((day_view.get('learning') or {}).get('subjects') or []):
        for e in subj.get('evidence') or []:
            out.append(e)
    return out


# ---------------------------------------------------------------- step 3: correction
def step3(s1, s2):
    task, child, wrong = s1['task'], s1['child'], s2['wrong']
    body = {'child': child, 'day': DAY, 'category': '学习进展', 'subject': '数学',
            'title': '订正：练习册第12页第2题 2+3',
            'note': '订正说明：2+3=5。孩子重摆小棒数出 5 根，并口述“3 和 2 合起来是 5”。家长核对正确。',
            'followup_kind': '订正', 'related_record_id': wrong['id'], 'request_key': rk()}
    st, saved = http('POST', '/api/record', body, step='3-correction')
    if st != 200:
        raise RuntimeError('correction failed: ' + json.dumps(saved, ensure_ascii=False)[:800])
    corr_id = saved.get('record_id') or (saved.get('record') or {}).get('id')
    rows = q("SELECT id,child,day,title,source,related_record_id,linked_task_id,linked_task_at,followup_kind FROM records WHERE id=?", (corr_id,))
    corr = rows[0]
    stv, day_view = learning_view_of(CHILD_ID)
    ev('03-correction.json', {'save_response': saved, 'correction_row': corr,
                              'all_records': q("SELECT id,title,source,related_record_id,linked_task_id,followup_kind,created FROM records ORDER BY id"),
                              'day_view': day_view})
    return {'correction': corr, 'saved': saved, 'day_view': day_view}


# ---------------------------------------------------------------- step 4: topic
def step4(s2, s3):
    child = s2['wrong']['child']
    wrong = s2['wrong']
    base = {'child_id': CHILD_ID, 'record_id': wrong['id']}
    st, state = http('POST', '/api/topic/state', base, step='4-topic-state')
    if st == 200 and not (state.get('pack') or {}).get('installed'):
        # /api/topic/state is a POST; first call may create tables; report pack status either way
        pass
    # The model writes a prose hint ("10以内加法计算"); the fixed pack has names like
    # "10以内的加法". Try the hint, then the plain concept name, then a broad word, and pick
    # from the product's own candidate list (a parent confirming a candidate).
    hint = (s2['item'].get('topic_hint') or '').strip()
    queries, searches = [], []
    for query in (hint, '10以内加法', '加法'):
        if query and query not in queries:
            queries.append(query)
    cands = []
    for query in queries:
        st_search, search = http('POST', '/api/topic/search',
                                 dict(base, query=query), step='4-topic-search')
        searches.append({'query': query, 'status': st_search, 'response': search})
        cands = (search or {}).get('candidates') or []
        if cands:
            break
    if not cands:
        raise RuntimeError('no topic candidate: ' + json.dumps(searches, ensure_ascii=False)[:600])
    preferred = [c for c in cands if c.get('name') in
                 ('10以内的加法', '5以内的加法', '20以内不进位加法')]
    topic = (preferred or cands)[0]
    st, linked = http('POST', '/api/topic/link',
                      dict(base, topic_id=topic['id'], state='confirmed', request_id=rk(),
                           note='家长确认：错在「%s」' % topic['name']), step='4-topic-link')
    if st != 200:
        raise RuntimeError('topic link failed: ' + json.dumps(linked, ensure_ascii=False)[:800])
    st_engine, engine_bytes = http_raw('/api/topic/engine.js', '4-engine-js')
    local_engine = (PACK / 'diagnose' / 'engine.js').read_bytes()
    engine_check = {'status': st_engine, 'served_bytes': len(engine_bytes),
                    'served_sha256': hashlib.sha256(engine_bytes).hexdigest(),
                    'pack_sha256': hashlib.sha256(local_engine).hexdigest(),
                    'identical': engine_bytes == local_engine}
    (EVID / 'engine-served.js').write_bytes(engine_bytes)
    st, started = http('POST', '/api/topic/diagnosis/start',
                       dict(base, topic_id=topic['id'], request_id=rk()), step='4-topic-start')
    if st != 200:
        raise RuntimeError('diagnosis start failed: ' + json.dumps(started, ensure_ascii=False)[:800])
    diag = (started.get('diagnoses') or [{}])[0]
    graph = started.get('graph') or {}
    # Drive the product's own browser engine exactly like topic-diagnosis.js; first item is answered
    # with the child's original wrong answer 6 (2+3=6), then correct answers until the engine finishes.
    drive = node_engine({'mode': 'diagnosis', 'graph': graph, 'topic_id': topic['id'],
                         'opts': diag.get('opts') or {'limit': 8, 'seed': 'x'},
                         'script': [{'kind': 'answer', 'text': '@wrong'},
                                    {'kind': 'answer', 'text': '@auto'},
                                    {'kind': 'answer', 'text': '@auto'},
                                    {'kind': 'answer', 'text': '@auto'},
                                    {'kind': 'answer', 'text': '@auto'},
                                    {'kind': 'answer', 'text': '@auto'}]}, '4-engine')
    answers = []
    for step in drive.get('steps') or []:
        st, res = http('POST', '/api/topic/diagnosis/answer',
                       dict(base, diagnosis_id=diag['id'], seq=step['seq'], topic_id=step['topic_id'],
                            qid=step['qid'], kind='answer', answer=step['text'], verdict=step['verdict'],
                            engine_result=step['engine_result'], session=step['session'],
                            summary=step['summary']), step=f'4-answer-{step["seq"]}')
        answers.append({'sent': {k: step[k] for k in ('seq', 'qid', 'topic_id', 'text', 'verdict')},
                        'status': st, 'response_ok': (res or {}).get('ok'),
                        'error': (res or {}).get('error')})
        if st != 200:
            raise RuntimeError('answer failed: ' + json.dumps(res, ensure_ascii=False)[:800])
    st, final = http('POST', '/api/topic/state', base, step='4-topic-state-final')
    links = q('SELECT * FROM topic_links WHERE record_id=?', (str(wrong['id']),))
    diags = q('SELECT id,topic_id,state,summary FROM topic_diagnoses WHERE record_id=?', (str(wrong['id']),))
    items = q('SELECT diagnosis_id,seq,topic_id,qid,verdict FROM topic_diagnosis_items ORDER BY id')
    stv, day_view = learning_view_of(CHILD_ID)
    ev('04-topic.json', {'state_open': state, 'searches': searches, 'chosen_topic': topic,
                         'engine_check': engine_check,
                         'link_response': linked, 'start_response_keys': sorted(started.keys()),
                         'diagnosis_initial': diag, 'engine_drive': drive, 'answers': answers,
                         'state_final': final, 'db_links': links, 'db_diagnoses': diags,
                         'db_items': items, 'day_view': day_view})
    return {'topic': topic, 'state': final, 'links': links, 'diagnoses': diags,
            'answers': answers, 'day_view': day_view}


# ---------------------------------------------------------------- step 5: review
def step5(s2, s3, s4):
    wrong = s2['wrong']
    child = s2['wrong']['child']
    basis = (s4['state'].get('record') or {}).get('basis')
    task_id = s2['wrong'].get('linked_task_id') or ''
    review = {'child_id': CHILD_ID, 'record_id': wrong['id'], 'topic_id': s4['topic']['id'],
              'task_id': task_id, 'basis': basis}
    eid = uuid.uuid4().hex
    event = {'id': eid, 'version': 0, 'child_ids': [CHILD_ID],
             'title': '家庭复习：数学练习册第12页第2题', 'category': 'study',
             'day': DUE, 'start_time': '19:30', 'end_time': '19:50', 'location': '',
             'note': '按错题重做 2+3，并口述计算过程。', 'status': 'confirmed',
             'repeat': 'none', 'until': '', 'review': review}
    st, saved = http('POST', '/api/calendar/save', event, step='5-review-save')
    if st != 200:
        raise RuntimeError('review save failed: ' + json.dumps(saved, ensure_ascii=False)[:800])
    st, cal = http('GET', f'/api/calendar?start={DUE}&end={DUE}', step='5-calendar-read')
    stv, dayv = learning_view_of(CHILD_ID, DUE)
    st_day, dayv_day = http('GET', f'/api/day?child_id={CHILD_ID}&day={DUE}', step='5-day-read')
    # The review day arrives: mark the calendar event completed, then file the second-round feedback.
    event2 = dict(event, version=1, status='completed', note='复习已完成：重做 2+3=5，口述“2 和 3 合起来是 5”。')
    st, done = http('POST', '/api/calendar/save', event2, step='5-review-complete')
    body = {'child': child, 'day': DUE, 'category': '学习进展', 'subject': '数学',
            'title': '复习反馈：家庭复习·数学第12页第2题',
            'note': '到期复习：独立重做 2+3，写出 2+3=5，并说出“2 和 3 合起来是 5”。家长核对正确。',
            'followup_kind': '复测', 'related_record_id': wrong['id'], 'request_key': rk()}
    st, second = http('POST', '/api/record', body, step='5-review-feedback')
    if st != 200:
        raise RuntimeError('review feedback failed: ' + json.dumps(second, ensure_ascii=False)[:800])
    st2, day_after = learning_view_of(CHILD_ID, DUE)
    stv2, day_today = learning_view_of(CHILD_ID, DAY)
    # "再练": show a fresh question via the product's own retry selection, then submit it. The private
    # DeepTutor grader is not configured on this machine; capture the product's own refusal verbatim.
    base = {'child_id': CHILD_ID, 'record_id': wrong['id']}
    st_g, guided = http('POST', '/api/wrong/remediate',
                        {'child_id': CHILD_ID, 'record_id': wrong['id'], 'request_key': rk()},
                        step='5-guided-draft')
    guided_probe = {'status': st_g, 'ok': (guided or {}).get('ok'),
                    'session_id': (guided or {}).get('session_id'),
                    'reused': (guided or {}).get('reused'),
                    'error': (guided or {}).get('error')}
    st_state, state_now = http('POST', '/api/topic/state', base, step='5-topic-state')
    diag = (state_now.get('diagnoses') or [{}])[0]
    retry = node_engine({'mode': 'retry', 'graph': state_now.get('graph') or {},
                         'topic_id': diag.get('topic_id'), 'diagnosis_id': diag.get('id'),
                         'seen': state_now.get('seen_qids') or []}, '5-retry-item')
    retry_probe = {'item': retry.get('item'), 'remaining': retry.get('remaining')}
    if retry.get('item'):
        it = retry['item']
        stm, marked = http('POST', '/api/topic/diagnosis/mark',
                           dict(base, diagnosis_id=diag['id'], action='shown', mode='retry', qid=it['qid']),
                           step='5-retry-mark')
        retry_probe['mark_status'] = stm
        retry_probe['mark_response_ok'] = (marked or {}).get('ok')
        retry_probe['mark_error'] = (marked or {}).get('error')
        if stm == 200:
            st5, r5 = http('POST', '/api/topic/diagnosis/retry',
                           dict(base, diagnosis_id=diag['id'], qid=it['qid'], answer='5',
                                verdict='correct', request_id=rk()), step='5-retry-submit')
            retry_probe.update(status=st5, response=r5)
    ev('05-review.json', {'review_saved': saved, 'calendar': cal, 'day_view_due': dayv_day,
                          'day_view_due_learning': dayv, 'review_completed': done,
                          'second_round_record': second, 'day_view_after': day_after,
                          'day_view_today_after': day_today, 'topic_state_final': state_now,
                          'retry_probe': retry_probe, 'guided_probe': guided_probe,
                          'all_records': q("SELECT id,title,source,related_record_id,linked_task_id,followup_kind,day,created FROM records ORDER BY id")})
    return {'event': event, 'saved': saved, 'calendar': cal, 'day_due': dayv_day,
            'second': second, 'day_after': day_after, 'retry': retry_probe,
            'state': state_now, 'guided_probe': guided_probe}


# ---------------------------------------------------------------- main
def main():
    global MATH_TASK, CHILD_ID
    MATH_TASK = find_math_task()
    with case.app.connect() as _c:
        _profiles = [dict(p) for p in case.app.profiles(_c)]
    CHILD_ID = next(p['id'] for p in _profiles if p['name'] == MATH_TASK['child'])
    ev('00b-tasks.json', {'math_task': MATH_TASK, 'profiles': _profiles})
    result = {'day': DAY, 'due': DUE, 'model_conf_model': conf['model'], 'profile_id': CHILD_ID}
    s1 = step1()
    result['step1_feedback'] = {'task': s1['task'], 'feedback_record': s1['feedback_record'],
                                'attachment': s1['attachment']}
    s2 = step2(s1)
    result['step2_wrong'] = {'wrong': s2['wrong'], 'saved': s2['saved']}
    s3 = step3(s1, s2)
    result['step3_correction'] = {'correction': s3['correction']}
    s4 = step4(s2, s3)
    result['step4_topic'] = {'topic': s4['topic'], 'links': s4['links'],
                             'diagnoses': s4['diagnoses'], 'answers': s4['answers']}
    s5 = step5(s2, s3, s4)
    result['step5_review'] = {'event': s5['event'], 'second': s5['second'],
                              'retry': s5['retry'], 'guided': s5['guided_probe']}
    result['learning_state_today'] = [(e.get('record_id'), e.get('state'), e.get('topics'), e.get('next'))
                                      for e in learning_evidence(s3['day_view'])]
    result['learning_state_after_review'] = [(e.get('record_id'), e.get('state'))
                                             for e in learning_evidence(s5['day_after'])]
    result['db'] = {
        'records': q("SELECT id,child,day,category,title,source,related_record_id,linked_task_id,followup_kind,created,note FROM records ORDER BY id"),
        'topic_links': q('SELECT * FROM topic_links ORDER BY id'),
        'topic_diagnoses': q('SELECT * FROM topic_diagnoses ORDER BY id'),
        'topic_diagnosis_items': q('SELECT * FROM topic_diagnosis_items ORDER BY id'),
        'calendar': q('SELECT id,title,day,status,review,version FROM calendar_events ORDER BY rowid'),
        'uploads': q('SELECT id,name,size,mime FROM uploads ORDER BY rowid'),
    }
    result['model_calls'] = MODEL_CALLS
    ev('00b-model-calls.json', MODEL_CALLS)
    result['http_trace'] = TRACE
    ev('report-data.json', result)
    # audit copies
    for name in ('family.sqlite3',):
        src = Path(case.app.DATA) / name
        if src.exists():
            (EVID / name).write_bytes(src.read_bytes())
    print(json.dumps({'steps': {k: result[k] for k in result if k.startswith('step')},
                      'learning_state_today': result['learning_state_today'],
                      'learning_state_after_review': result['learning_state_after_review'],
                      'model_calls': [{k: c.get(k) for k in ('call_index', 'name', 'ok', 'duration_s')} for c in MODEL_CALLS],
                      'retry': s5['retry']}, ensure_ascii=False, indent=2)[:6000])


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        ev('failure.json', {'trace': traceback.format_exc(), 'model_calls': MODEL_CALLS,
                            'http_trace': TRACE})
        raise
    finally:
        try:
            globals().get('server').shutdown()
        except Exception:
            pass

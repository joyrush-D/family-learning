"""Run the 18-message multi-channel handoff fixture through the product's own ingest -> run_once path
with the REAL configured model (Volcano Ark doubao), then dump every observable state for reconciliation.

Only fictional data. Credential is read from the product's model.json into the process env and never printed.
Attachment reading state is injected exactly as the fixture's attachment_contract says (no real bytes, no
decoding/vision test): the english PDF page receipt carries the fixture's instruction text through the
product's own pdf-material page-reader port (same shape as test_daily_list_frozen U02), and the chinese jpg
stays unread because family_media.prepare_draft is the fixture's patched external reader.
"""
import copy
import datetime as dt
import io
import json
import os
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import quote

REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
CONF_PATH = Path('/Users/joyrush/.local/share/family-learning/application/private/model.json')
BASE = Path('/Users/joyrush/Documents/deepseek-harness/default-workspace')
FIXTURE = BASE / 'work/handoff-20261104/extract/DeepSeek-Harness-交接-20261104/附件/全虚构验收材料/FIXTURE.json'
OUT = BASE / 'work/merge18'
DAY = '2026-11-04'

os.chdir(REPO)
sys.path.insert(0, REPO)

conf = json.loads(CONF_PATH.read_text())
os.environ['FAMILY_LLM_BASE_URL'] = conf['base_url']
os.environ['FAMILY_LLM_MODEL'] = conf['model']
os.environ['FAMILY_LLM_LIGHT_MODEL'] = conf.get('light_model') or ''
os.environ['FAMILY_LLM_API_KEY'] = conf['api_key']
os.environ['FAMILY_LLM_REASONING_EFFORT'] = conf.get('reasoning_effort') or ''
# The light screening tier keeps its own effort: 'none' is what makes a selection batch return in seconds instead of
# spending the 45s request budget on reasoning (the private model file is not edited; this only overrides in-process).
os.environ['FAMILY_LLM_LIGHT_REASONING_EFFORT'] = 'none'

import family_llm  # noqa: E402
ORIGINAL = family_llm._chat_json

import family_agent as agent  # noqa: E402
import test_daily_list_whole_day as W  # noqa: E402
import test_pdf  # noqa: E402
import test_pdf_material  # noqa: E402

CALLS = []
TICKS = []


def real_model(messages, schema, name, timeout=60, *, data_path=None):
    started = time.time()
    call = dict(index=len(CALLS), name=name, model=conf['model'],
                at=dt.datetime.now().astimezone().isoformat(timespec='seconds'))
    try:
        context = json.loads(messages[-1]['content'])
        call['request'] = context
    except Exception:
        call['request_raw'] = messages[-1]['content'][:4000]
    try:
        result = ORIGINAL(messages, schema, name, timeout, data_path=data_path)
        call['ok'] = True
        call['response'] = result
        return result
    except Exception as exc:  # keep the raw failure for the report, then re-raise
        call['ok'] = False
        call['error'] = repr(exc)
        raise
    finally:
        call['elapsed_s'] = round(time.time() - started, 2)
        try:  # the product's own usage ledger records what this call cost, including output tokens
            import sqlite3
            ledger = Path(data_path if data_path is not None else os.environ.get('FAMILY_DATA', '')) / 'family.sqlite3'
            with sqlite3.connect(ledger, timeout=5) as db:
                row = db.execute('SELECT state,elapsed_ms,input_tokens,output_tokens,total_tokens,reported_model'
                                 ' FROM llm_usage_ledger ORDER BY id DESC LIMIT 1').fetchone()
            if row:
                call.update(ledger_state=row[0], ledger_ms=row[1], input_tokens=row[2],
                            output_tokens=row[3], total_tokens=row[4], reported_model=row[5])
        except Exception as exc:
            call['ledger_error'] = repr(exc)
        CALLS.append(call)


SOURCES = [
    dict(id='qa-qq-a4', platform='qq', child_id='child-1', name='虚构四年级A班', cursor='0', enabled=True),
    dict(id='qa-wx-a4', platform='wechat', child_id='child-1', name='虚构四年级A班提醒群', cursor='0', enabled=True),
    dict(id='qa-qq-b2', platform='qq', child_id='child-2', name='虚构二年级B班', cursor='0', enabled=True),
    dict(id='qa-wx-b2', platform='wechat', child_id='child-2', name='虚构二年级B班提醒群', cursor='0', enabled=True),
    dict(id='qa-manual-a', platform='wechat', child_id='child-1', name='虚构家庭手动补录（甲）', cursor='0', enabled=True),
    dict(id='qa-manual-b', platform='wechat', child_id='child-2', name='虚构家庭手动补录（乙）', cursor='0', enabled=True),
]


def product_source(message):
    if message['source_id'] == 'qa-family-manual':
        return 'qa-manual-a' if message['child_scope'] == ['qa-heldout-child-a'] else 'qa-manual-b'
    return message['source_id']


def sender_of(fixture, message):
    publisher = next(p for p in fixture['publishers'] if p['id'] == message['publisher_id'])
    accounts = publisher.get('verified_channel_accounts') or {}
    sender_id = accounts.get(message['source_id']) or publisher['id']
    return publisher, sender_id


def build_payloads(fixture):
    children = {'qa-heldout-child-a': 'child-1', 'qa-heldout-child-b': 'child-2'}
    payloads = []
    for source in SOURCES:
        rows = []
        index = 0
        for message in fixture['messages']:
            if product_source(message) != source['id']:
                continue
            index += 1
            publisher, sender_id = sender_of(fixture, message)
            rows.append(dict(id=message['id'], message_order=str(index), time=message['sent_at'], kind='text',
                             sender=publisher['display_name'], sender_id=sender_id,
                             text=message['text'], unread=False))
        if not rows:
            continue
        payloads.append(dict(source_id=source['id'], expected_cursor='0', cursor=str(len(rows)),
                             checked_at=rows[-1]['time'], last_message_time=rows[-1]['time'],
                             messages=rows, error=''))
    return payloads


def snapshot(store, app, now):
    with store._db() as c:
        items = [dict(r) for r in c.execute('SELECT * FROM agent_items ORDER BY created, id')]
        tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
        messages = [dict(source_id=r['source_id'], message_id=r['id'], processed=r['processed'],
                         payload=json.loads(r['payload']))
                    for r in c.execute('SELECT source_id, id, payload, processed FROM agent_messages ORDER BY rowid')]
        jobs = [dict(r) for r in c.execute('SELECT * FROM agent_jobs')]
        pdfs = [dict(r) for r in c.execute('SELECT * FROM agent_pdf_material')]
        drafts = [dict(r) for r in c.execute('SELECT * FROM agent_message_drafts')]
    day = app.calendar_snapshot(DAY, DAY)
    nxt = app.calendar_snapshot('2026-11-05', '2026-11-05')
    return dict(now=now.isoformat(), items=items, tasks=tasks, messages=messages, jobs=jobs,
                pdf_material=pdfs, drafts=drafts, day=day, next_day=nxt)


def main(ticks=30):
    fixture = json.loads(FIXTURE.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    case = W.WholeDayTests('runTest')
    case.setUp()
    case.model.side_effect = real_model  # every product model call goes to the real configured model

    (case.store.data / 'agent.json').write_text(json.dumps(dict(enabled=True, sources=SOURCES), ensure_ascii=False))

    payloads = build_payloads(fixture)
    for payload in payloads:
        case.store.ingest(payload)
    print('ingested', sum(len(p['messages']) for p in payloads), 'messages across', len(payloads), 'sources', flush=True)

    # ---- attachments: english pdf = injected 'read' page receipt (fixture has no bytes), chinese jpg = unread
    english = next(a for a in fixture['attachments'] if a['id'] == 'h18-att-english-read')
    chinese = next(a for a in fixture['attachments'] if a['id'] == 'h18-att-chinese-unread')
    raw_pdf = test_pdf.build_pdf(1)
    pdf_upload = case.app.save_upload(io.BytesIO(raw_pdf), len(raw_pdf), quote(english['display_name']))
    case.store.message_attachment(dict(child_id='child-1', source_id='qa-qq-a4', message_id=english['message_id'],
                                       attachment_id=pdf_upload['id'], action='attach'), case.app.upload_info)
    image = None
    try:
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (600, 300), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', 28)
        draw.text((20, 20), '识字小卡（虚构）', fill='black', font=font)
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG')
        raw_jpg = buffer.getvalue()
    except Exception:
        raw_jpg = None
    if raw_jpg is None:
        raw_jpg = bytes.fromhex('ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707'
                                '0709090a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837'
                                '292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000'
                                '010501010101010100000000000000000102030405060708090a0bffda0008010100003f00d2cf20')
    jpg_upload = case.app.save_upload(io.BytesIO(raw_jpg), len(raw_jpg), quote(chinese['display_name']))
    case.store.message_attachment(dict(child_id='child-2', source_id='qa-qq-b2', message_id=chinese['message_id'],
                                       attachment_id=jpg_upload['id'], action='attach'), case.app.upload_info)
    print('attachments:', pdf_upload['id'], pdf_upload['mime'], '|', jpg_upload['id'], jpg_upload['mime'], flush=True)

    requirement = english['reading_evidence']['text']
    lines = [part.strip() for part in requirement.splitlines() if part.strip()]
    page = dict(originals=[dict(upload_id=pdf_upload['id'], title=lines[0],
                                note='老师写明的英语练习要求，未见孩子作答。', uncertainties=[],
                                requirements=lines[1:], deferred_contexts=[])])

    ticks_int = int(ticks)
    last_signature = None
    stable = 0
    with test_pdf_material.renderer(page_count=1), test_pdf_material.page_model([page] * 40):
        for index in range(ticks_int):
            now = case.now + dt.timedelta(minutes=7 * index)
            entry = dict(index=index, now=now.isoformat())
            try:
                result = agent.run_once(case.app, now)
                entry['result'] = {k: result.get(k) for k in ('state', 'created', 'processed', 'failed', 'media',
                                                              'teacher_public', 'qq_fragment')}
            except Exception:
                entry['error'] = traceback.format_exc()
                TICKS.append(entry)
                print('TICK', index, 'ERROR', entry['error'].splitlines()[-1], flush=True)
                break
            state = snapshot(case.store, case.app, now)
            entry['state'] = state
            TICKS.append(entry)
            unprocessed = sum(1 for m in state['messages'] if not m['processed'])
            pending = sum(1 for i in state['items'] if i['state'] == 'pending')
            pdf_states = [(p.get('message_id'), p.get('state')) for p in state['pdf_material']]
            tick_items = len(state['items'])
            jobs = [dict(id=j['id'], attempts=j['attempts'], done=j['done'], error=(j.get('error') or '')[:60])
                    for j in state['jobs'] if j['id'].startswith('messages:')]
            print('TICK', index, now.strftime('%H:%M'), 'created', entry['result']['created'],
                  'processed', entry['result']['processed'], 'failed', entry['result']['failed'],
                  '| unprocessed', unprocessed, 'pending', pending, 'items', tick_items,
                  'tasks', len(state['tasks']), 'pdf', pdf_states, 'jobs', jobs, flush=True)
            signature = (tuple(sorted((i['id'], i['state'], i.get('task_id') or '') for i in state['items'])),
                         tuple(sorted((t['id'], t['title']) for t in state['tasks'])),
                         tuple(sorted(pdf_states)), unprocessed,
                         len(state['day'].get('inbox') or []))
            if signature == last_signature and unprocessed == 0:
                stable += 1
            else:
                stable = 0
            last_signature = signature
            if stable >= 3:
                print('stable after', index + 1, 'ticks', flush=True)
                break

    final = snapshot(case.store, case.app, case.now + dt.timedelta(minutes=7 * max(0, len(TICKS) - 1)))
    # Optional: keep the fixture's own data directory (sqlite + uploads + agent.json) as a runnable demo snapshot.
    snapshot_dir = os.environ.get('MERGE18_SNAPSHOT')
    if snapshot_dir:
        import shutil
        target = Path(snapshot_dir)
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        shutil.copytree(case.store.data, target / 'data',
                        ignore=shutil.ignore_patterns('__pycache__', '.agent.lock', '*.lock', '-wal', '-shm'))
        shutil.copy2(case.fixture.root / '家庭运行规则.md', target / '家庭运行规则.md')
        print('snapshot data dir ->', target, flush=True)
    calls_lite = [{k: v for k, v in call.items() if k not in ('request', 'response')} for call in CALLS]
    (OUT / 'run.json').write_text(json.dumps(dict(
        fixture=str(FIXTURE), model=conf['model'], sources=SOURCES,
        attachment_injection=dict(english=dict(upload_id=pdf_upload['id'], name=english['display_name'],
                                               mode='injected read page receipt (fixture text, no bytes)'),
                                  chinese=dict(upload_id=jpg_upload['id'], name=chinese['display_name'],
                                               mode='attached, reader left pending (fixture unread state)')),
        page_receipt=page, payloads=payloads, calls=calls_lite, ticks=[{k: v for k, v in t.items() if k != 'state'} for t in TICKS],
        final=final), ensure_ascii=False, indent=1))
    (OUT / 'model-calls.json').write_text(json.dumps(CALLS, ensure_ascii=False, indent=1))
    (OUT / 'states.json').write_text(json.dumps(dict(ticks=[t.get('state') for t in TICKS], final=final),
                                                ensure_ascii=False, indent=1))
    print('\nmodel calls:', len(CALLS), '| names:', sorted({c['name'] for c in CALLS}), flush=True)
    for call in CALLS:
        print('  -', call['index'], call['name'], call.get('elapsed_s'), 'ok' if call.get('ok') else 'FAIL', flush=True)
    print('\nfinal tasks:', len(final['tasks']), flush=True)
    for task in final['tasks']:
        print('  *', task['id'], '|', task['child'], '|', task['title'], '| due', task['due'], flush=True)
    print('\nfinal items:', flush=True)
    for item in final['items']:
        print('  #', item['id'], item['child_id'], item['state'], '|', item['title'], '| task', item.get('task_id'), flush=True)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 30)

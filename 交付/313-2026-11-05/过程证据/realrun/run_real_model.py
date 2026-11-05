"""Drive the REAL configured model through the product's own ingest -> run_once -> save -> list path.

Isolated fictional data only: the store and app live in a throwaway temp dir (test_agent fixtures),
the sources are the frozen six-message whole-day set, and the credential comes from the product's
own model.json (read into the process env, never printed).

A pass here shows what the configured model actually proposes for those six teacher messages and what
the product then saves/lists -- not a new expectation, just the observation.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
CONF_PATH = Path('/Users/joyrush/.local/share/family-learning/application/private/model.json')
OUT = Path(__file__).resolve().parent

os.chdir(REPO)
sys.path.insert(0, REPO)

conf = json.loads(CONF_PATH.read_text())
os.environ['FAMILY_LLM_BASE_URL'] = conf['base_url']
os.environ['FAMILY_LLM_MODEL'] = conf['model']
os.environ['FAMILY_LLM_LIGHT_MODEL'] = conf.get('light_model') or ''
os.environ['FAMILY_LLM_API_KEY'] = conf['api_key']
os.environ['FAMILY_LLM_REASONING_EFFORT'] = conf.get('reasoning_effort') or ''

import family_llm  # noqa: E402
ORIGINAL = family_llm._chat_json

import family_agent as agent  # noqa: E402
import test_daily_list_whole_day as W  # noqa: E402

CALLS = []


def real_model(messages, schema, name, timeout=60, *, data_path=None):
    context = json.loads(messages[-1]['content'])
    CALLS.append(dict(name=name, model=conf['model'], evidence=[e.get('ref') for e in context.get('evidence', [])]))
    result = ORIGINAL(messages, schema, name, timeout, data_path=data_path)
    CALLS[-1]['ok'] = True
    CALLS[-1]['result'] = result
    return result


def main():
    case = W.WholeDayTests('runTest')
    case.setUp()
    case.model.side_effect = real_model
    payload, refs = case._ingest()
    print('ingested', len(payload['messages']), 'messages from one source')
    result = agent.run_once(case.app, case.now)
    print('run_once ->', json.dumps({k: result.get(k) for k in ('failed', 'processed', 'created')}, ensure_ascii=False))

    with case.app.connect() as c:
        rows = [dict(r) for r in c.execute('SELECT child,title,due,action,original_status FROM manual_tasks')]
    print('\n保存下来的事项 %d 条:' % len(rows))
    for row in rows:
        print(' -', row['child'], '|', row['title'], '| due', row['due'] or '(无)', '|', row['original_status'])

    snapshot = case.app.calendar_snapshot(W.DAY, W.DAY)
    mine = [i for i in snapshot['inbox'] if i['child_ids'] == ['child-1'] and i['kind'] in ('task', 'school')]
    print('\n当天清单 %d 条:' % len(mine))
    for item in mine:
        print(' ---')
        print('  title:', item['title'])
        print('  due  :', item.get('due') or '(无)', '| kind:', item['kind'])
        body = (item.get('body') or '').replace('\n', ' / ')
        print('  body :', body[:220])

    (OUT / 'real-model-run.json').write_text(json.dumps(
        dict(calls=CALLS, saved=rows, listed=[dict(title=i['title'], due=i.get('due'), body=i.get('body')) for i in mine]),
        ensure_ascii=False, indent=2))
    print('\n模型调用 %d 次（明细见 real-model-run.json）' % len(CALLS))
    for call in CALLS:
        print('  -', call['name'], '| evidence', len(call.get('evidence') or []), '| ok', call.get('ok'))


if __name__ == '__main__':
    main()

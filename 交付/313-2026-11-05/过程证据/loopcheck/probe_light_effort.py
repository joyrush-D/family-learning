"""Probe: one live family_agent_selection run with light_reasoning_effort=none (config-only mitigation)."""
import datetime as dt, json, os, sys, time
from pathlib import Path
WORK = Path(__file__).resolve().parent
REPO = Path('/Users/joyrush/.local/share/family-learning/public-integration-20260926')
EVID = WORK / 'evidence' / 'pre-run-failures'; EVID.mkdir(parents=True, exist_ok=True)
conf = json.loads(Path('/Users/joyrush/.local/share/family-learning/application/private/model.json').read_text())
os.environ['FAMILY_LLM_BASE_URL'] = conf['base_url']
os.environ['FAMILY_LLM_MODEL'] = conf['model']
os.environ['FAMILY_LLM_LIGHT_MODEL'] = conf.get('light_model') or ''
os.environ['FAMILY_LLM_API_KEY'] = conf['api_key']
os.environ['FAMILY_LLM_REASONING_EFFORT'] = conf.get('reasoning_effort') or ''
os.environ['FAMILY_LLM_LIGHT_REASONING_EFFORT'] = 'none'
os.environ['FAMILY_TAXONOMY_DIR'] = str(WORK / 'knowledge' / 'cn-math-taxonomy-e0f931b')
os.chdir(REPO); sys.path.insert(0, str(REPO))
import family_llm, family_agent as agent, test_daily_list_whole_day as W
ORIG = family_llm._chat_json
CALLS = []
def run_model(messages, schema, name, timeout=60, *, data_path=None):
    entry = {'name': name, 'timeout': timeout, 'started': dt.datetime.now().isoformat()}
    t0 = time.time()
    try:
        result = ORIG(messages, schema, name, timeout, data_path=data_path)
    except Exception as e:
        entry.update(ok=False, error=f'{type(e).__name__}: {e}', duration_s=round(time.time()-t0, 2))
        CALLS.append(entry); raise
    entry.update(ok=True, duration_s=round(time.time()-t0, 2),
                 result={k: result.get(k) for k in ('proposals', 'created', 'ok')} if isinstance(result, dict) else None)
    CALLS.append(entry); return result
case = W.WholeDayTests('runTest'); case.setUp(); case.model.side_effect = run_model
payload, refs = case._ingest()
res = agent.run_once(case.app, case.now)
out = {'light_reasoning_effort': 'none', 'run_once': res, 'calls': CALLS,
       'tasks': [dict(r) for r in case.app.connect().execute(
           'SELECT id,title,due,child FROM manual_tasks ORDER BY rowid')]}
(EVID / 'light-effort-none.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps({'run_once': res, 'calls': [{k: c.get(k) for k in ('name','ok','duration_s','error')} for c in CALLS],
                  'tasks': [(t['id'], t['title']) for t in out['tasks']]}, ensure_ascii=False))

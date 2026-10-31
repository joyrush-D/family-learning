"""Synthetic mixed native/web regression. Build the App first, then opt in to a visible window on a separate test Mac.
All records are fictional; no model, household, printer, login or collection is used.
"""
from pathlib import Path
import sys, os, json, subprocess, tempfile, time, urllib.request, shutil
import argparse, signal, hashlib, select


def serve_fixture(source):
    # Import only after selecting a new temporary private store; the source supplies static code, never family records.
    with tempfile.TemporaryDirectory(prefix='synthetic-native-topic-') as tmp:
        os.environ['FAMILY_DATA']=tmp
        sys.path.insert(0,str(source))
        import app, family_llm
        def forbidden(*args,**kwargs): raise AssertionError('synthetic native-topic QA must never call a product model')
        family_llm._chat_json=forbidden
        app.DATA=Path(tmp);app.DB=app.DATA/'family.sqlite3'
        docs={
          '家庭运行规则.md':'| child-1 | 示例甲 | — | 12岁 | 七年级 |\n| child-2 | 示例乙 | — | 10岁 | 五年级 |\n',
          '跟踪台账.md':'| T01 | 示例甲 | 虚构数学作业：有理数加法 | 2026-10-28 | 待跟进 | 虚构学校通知 | 完成两道加法并检查 |\n',
          '学习与成长.md':'全虚构软件验收，不代表家长体验。','消息来源.md':''}
        app.read=lambda name:docs.get(name,'')
        f=app.save_task_feedback(dict(task_id='T01',child='示例甲',day='2026-10-28',note='虚构：第一题加法符号算错',request_key='synthetic-native-topic-feedback-01'))
        w=app.save_record(dict(child='示例甲',day='2026-10-28',category='学习进展',subject='数学',title='虚构加法错题',note='题面：(-8)+5=?\n学生原答：-13\n可见订正/正确答案：-3',source='错题照片核对',related_record_id=f['record_id'],followup_kind='补充观察'))
        app.save_record(dict(child='示例乙',day='2026-10-28',category='学习进展',subject='数学',title='另一孩子虚构错题',note='题面：1+1\n学生原答：3',source='错题照片核对'))
        app.prepare_assets();server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        print(json.dumps(dict(url='http://127.0.0.1:'+str(server.server_address[1]),wrong_id=w['record_id'],feedback_id=f['record_id'],db=str(app.DB),token=app.TOKEN)),flush=True)
        try:server.serve_forever()
        finally:server.server_close()


if __name__ == '__main__':
    if sys.argv[1:2]==['--fixture']:
        if os.environ.get('FAMILY_NATIVE_TOPIC_FIXTURE')!='1':raise SystemExit('fixture mode needs the test runner')
        serve_fixture(Path(sys.argv[2]).resolve());raise SystemExit()

    parser=argparse.ArgumentParser(description='Synthetic real Mac SwiftUI → WK diagnosis → saved retry → SwiftUI/reopen. Opens a test window only with explicit opt-in; use a separate test Mac.')
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--app',type=Path,required=True,help='App built from this committed source (the .app bundle or executable)')
    parser.add_argument('--python',type=Path,default=Path(sys.executable),help='Python >=3.11 with pydantic 2 for the existing DeepTutor sidecar')
    parser.add_argument('--knowledge-pack',type=Path,required=True,help='The existing fixed e0f931b pack, locally installed with its original license')
    parser.add_argument('--output',type=Path,required=True,help='A new private QA directory; no family data is used')
    parser.add_argument('--allow-visible-test-window',action='store_true')
    args=parser.parse_args()
    if not args.allow_visible_test_window:parser.error('This opens a test window. Run only on a separate test Mac with --allow-visible-test-window; keep the household computer silent.')
    repo=args.repo.resolve();py=args.python.resolve();pack=args.knowledge_pack.resolve();out=args.output.resolve()
    exe=args.app.resolve();exe=exe/'Contents/MacOS/YiqiChengzhang' if exe.suffix=='.app' else exe
    assert sys.platform=='darwin' and exe.is_file() and py.is_file() and pack.is_dir()
    r=subprocess.run([str(py),'-c','import sys,pydantic;assert sys.version_info>=(3,11) and int(pydantic.__version__.split(".")[0])==2'],capture_output=True,text=True)
    assert r.returncode==0,'The test needs the existing Python >=3.11 + pydantic2 runtime; no installer or provider is invoked.'
    out.mkdir(mode=0o700,exist_ok=False)
    head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain'], cwd=repo, text=True).strip()
    env = {k:v for k,v in os.environ.items() if not k.startswith('FAMILY_')}
    env.update(FAMILY_TAXONOMY_DIR=str(pack), FAMILY_DEEPTUTOR_PYTHON=str(py),FAMILY_NATIVE_TOPIC_FIXTURE='1')
    fixture=None; app=None; events=[]; result={'commit':head,'passed':False,'all_fictional':True,'product_model_calls':0,'visible_test_explicitly_allowed':True,'app_binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
    HAND={'cnm_010_q1':'-3，-7','cnm_010_q2':'D','cnm_010_q3':'-1/2','cnm_010_q4':'-2'}
    def web(name, js='', until='', **kw):
     return dict(name=name,web_step={'js':js or 'return {ok:true}',**({'until':until} if until else {}),'timeout':30},**kw)
    def click(sel):return f"const b=document.querySelector({json.dumps(sel)});if(!b)return {{ok:false,error:'button absent'}};b.click();return {{ok:true}}"
    def ready(sel):return f"return {{ok:!!document.querySelector({json.dumps(sel)})}}"
    box='[data-topic-diagnosis="2"]'
    try:
     fixture=subprocess.Popen([str(py),str(Path(__file__).resolve()),'--fixture',str(repo)],env=env,stdout=subprocess.PIPE,stderr=(out/'fixture.log').open('wb'),text=True)
     # This read is bounded by the outer runner; an early fixture exit gives an empty line and fails below.
     first=fixture.stdout.readline(); info=json.loads(first); origin=info['url']; rid=info['wrong_id'];box=f'[data-topic-diagnosis="{rid}"]'
     with urllib.request.urlopen(origin+'/api/day?child_id=child-1',timeout=10) as r:day=json.load(r)
     item=next(i for g in day['groups'] for i in g['items'] if i.get('task_id')=='T01')
     steps=[{'name':'original row','until':'row-'+item['id']},{'name':'select original','click':'row-'+item['id']},{'name':'history button','until':'history-web'},
     {'name':'open same-task history','click':'history-web'},{'name':'native bridge state','native':'state'},
     web('same wrong card',until=ready(box+' [data-topic-open]')),
     {'name':'first web page ready','native':'state'},
     web('open diagnosis',click(box+' [data-topic-open]'),ready(box+' [data-topic-input="search"]')),
     web('find topic',f"const x=document.querySelector('{box} [data-topic-input=search]');x.value='有理数的加法法则';x.dispatchEvent(new Event('input',{{bubbles:true}}));document.querySelector('{box} [data-topic-search]').click();return {{ok:true}}",ready(box+' [data-topic-confirm="cnm_010"]')),
     web('link topic',click(box+' [data-topic-confirm="cnm_010"]'),ready(box+' [data-topic-start]')),
     # Linked, not yet diagnosed: the Mac's own learning entry names the pack's topic and says it waits for a diagnosis.
     {'name':'back to native after linking','key':'0','modifiers':['command']},{'name':'learning entry','click':'mode-学习进展'},
     {'name':'linked topic by its pack name','until':'learning-'+str(rid),'contains':'已关联知识点 有理数的加法法则 · ','timeout':20},
     {'name':'linked topic pending diagnosis','until':'learning-'+str(rid),'contains':'家长确认关联，待诊断','timeout':10},
     {'name':'linked topic snapshot','native':'snapshot'},
     {'name':'calendar entry again','click':'mode-日历'},{'name':'select original again','click':'row-'+item['id']},{'name':'history button again','until':'history-web'},
     {'name':'reopen same-task history','click':'history-web'},
     web('linked card reopened',f"const b=document.querySelector('{box} [data-topic-open]');if(b)b.click();return {{ok:true}}",ready(box+' [data-topic-start]')),
     web('start engine',click(box+' [data-topic-start]'),ready(box+' [data-topic-form="answer"]')),
     web('type an unsaved question answer',f"const f=document.querySelector('{box} [data-topic-form=answer]');const x=f.querySelector('input[data-topic-input]:not([type=radio])');if(x){{x.value='10000';x.dispatchEvent(new Event('input',{{bubbles:true}}));}}else{{const r=f.querySelector('input[type=radio]');if(!r)return {{ok:false,error:'question input missing'}};r.click();}}return {{ok:true}}"),
     {'name':'try leaving with question draft','key':'0','modifiers':['command']},{'name':'question draft keeps web open','native':'state'},
     web('unsaved answer retained',until=f"return {{ok:document.querySelector('{box} [data-topic-form=answer] input[data-topic-input]:not([type=radio])')?.value==='10000'||!!document.querySelector('{box} [data-topic-form=answer] input[type=radio]:checked')}}"),
     web('save diagnostic answer',f"const f=document.querySelector('{box} [data-topic-form=answer]');const q=f.dataset.qid;globalThis.rootFirst=q;const r=f.querySelector('input[type=radio]');if(r)r.click();else{{const x=f.querySelector('input[data-topic-input]');x.value='10000';x.dispatchEvent(new Event('input',{{bubbles:true}}));}}f.querySelector('[data-topic-submit]').click();return {{ok:true,qid:q}}",ready(box+' [data-topic-item="1"]')),
     web('pause',click(box+' [data-topic-pause]'),ready(box+' [data-topic-help="1"]')),
     web('read explanation',click(box+' [data-topic-help="1"]'),f"return {{ok:document.querySelector('{box} [data-topic-item=\"1\"]')?.textContent.includes('看过说明')}}"),
     web('new unseen question',click(box+' [data-topic-retry]'),ready(box+' [data-topic-form="retry"]')),
     web('save fresh independent answer',f"const f=document.querySelector('{box} [data-topic-form=retry]');const q=f.dataset.qid;const answer=({json.dumps(HAND,ensure_ascii=False)})[q];if(!answer||q===globalThis.rootFirst)return {{ok:false,error:'not an independently known fresh question',qid:q}};globalThis.rootRetry={{qid:q,answer}};const r=[...f.querySelectorAll('input[type=radio]')].find(x=>x.value===answer);if(r)r.click();else{{const x=f.querySelector('input[data-topic-input]');x.value=answer;x.dispatchEvent(new Event('input',{{bubbles:true}}));}}f.querySelector('[data-topic-submit]').click();return {{ok:true,qid:q,answer}}",ready(box+' [data-topic-retry-result="independent_correct"]')),
     {'name':'back to native after saved attempt','key':'0','modifiers':['command']},{'name':'fresh native result after saving','find_text':'独立再试1次','timeout':20},
     {'name':'open saved history fresh','click':'history-web'},
     web('saved wrong card reopened',f"const b=document.querySelector('{box} [data-topic-open]');if(b)b.click();return {{ok:true}}",ready(box+' [data-topic-retry-result="independent_correct"]')),
     {'name':'saved web page ready','native':'state'},
     web('current result card',js="return {ok:true}",until="const v=document.querySelector('#taskFeedbackHistory [data-retry-view]');const lines=v?[...v.querySelectorAll('dl>div')].map(x=>x.textContent):[];return {ok:!!v&&v.dataset.retryState==='current'&&lines.some(x=>x.includes('孩子原答'))&&lines.some(x=>x.includes('本次结果'))&&lines.some(x=>x.includes('原错题')),lines}",width=360),
     web('phone card in view',"document.querySelector('#taskFeedbackHistory [data-retry-view]').scrollIntoView({block:'center'});return {ok:true}","return {ok:document.documentElement.scrollWidth<=innerWidth+2,width:innerWidth}",width=360),
     {'name':'phone actual WK card','native':'snapshot'},
     web('desktop actual WK card',"return {ok:true}","return {ok:document.documentElement.scrollWidth<=innerWidth+2,width:innerWidth}",width=1440),
     {'name':'desktop actual WK card snapshot','native':'snapshot'},
     {'name':'return native via menu','key':'0','modifiers':['command']},{'name':'native result after web save','find_text':'独立再试1次','timeout':20},
     {'name':'native shared structured result','click':'row-'+item['id']},{'name':'native result card','find_text':'孩子原答','timeout':15},
     {'name':'native current state','native':'state'},{'name':'native saved result snapshot','native':'snapshot'},
     {'name':'native reload','native':'reopen'},{'name':'native reread saved retry','find_text':'独立再试1次','timeout':15},
     {'name':'reopen history again','click':'history-web'},
     web('reopen saved diagnosis',f"const b=document.querySelector('{box} [data-topic-open]');if(b)b.click();return {{ok:true}}",ready(box+' [data-topic-retry-result="independent_correct"]')),
     {'name':'final saved surface','native':'state'}]
     # Feedback=1, wrong=2, other-child=3, actual retry=4. No additional setup records in this M4 fixture.
     (out/'steps.json').write_text(json.dumps(steps,ensure_ascii=False,indent=2))
     support=out/'support';support.mkdir(mode=0o700);(support/'desktop.json').write_text(json.dumps({'service_origin':origin}))
     shots=out/'screenshots';shots.mkdir()
     runenv={**env,'FAMILY_DESKTOP_SUPPORT_DIR':str(support),'FAMILY_DESKTOP_TEST_ORIGIN':origin,'FAMILY_DESKTOP_TEST_SURFACE':'native','FAMILY_DESKTOP_TEST_NATIVE_STEPS':str(out/'steps.json'),'FAMILY_DESKTOP_TEST_SNAPSHOT_DIR':str(shots)}
     start=time.time()
     with (out/'native.jsonl').open('wb') as f,(out/'native.stderr').open('wb') as e:
      app=subprocess.Popen([str(exe),'--smoke-test'],env=runenv,stdout=f,stderr=e)
      try:code=app.wait(timeout=300)
      except subprocess.TimeoutExpired:app.terminate();app.wait(timeout=10);raise AssertionError('owned test App timeout')
     for line in (out/'native.jsonl').read_text(errors='replace').splitlines():
      try:events.append(json.loads(line))
      except ValueError:pass
     done=[x for x in events if x.get('state')=='native_step_done']; bad=[x for x in done if x.get('result',{}).get('ok') is not True]
     assert code==0 and len(done)==len(steps) and not bad,(code,len(done),len(steps),bad)
     rows={x['name']:x['result'] for x in done};assert rows['native bridge state']['selection']==item['id']
     assert rows['first web page ready']['web_visible'] and rows['saved web page ready']['web_visible']
     assert rows['question draft keeps web open']['surface']=='web' and rows['question draft keeps web open']['web_visible']
     assert rows['native current state']['native_visible'] and rows['native current state']['selection']==item['id']
     for child in ['child-1','child-2']:
      with urllib.request.urlopen(origin+'/api/day?child_id='+child,timeout=10) as r:view=json.load(r)
      items=[i for g in view['groups'] for i in g['items']]
      if child=='child-1':
       t=next(i for i in items if i.get('task_id')=='T01');assert t['progress']['retries']==1;assert any(z.get('retry',{}).get('state')=='current' for z in t['records'])
      else:assert all(i.get('task_id')!='T01' for i in items)
     result.update(passed=True,steps=len(done),elapsed_s=round(time.time()-start,2),native_to_actual_WK_and_back=True,child_isolation=True)
    except BaseException as e:
     import traceback
     result['error']=str(e);(out/'FAILURE.txt').write_text(traceback.format_exc())
    finally:
     if app is not None and app.poll() is None:app.terminate();app.wait(timeout=10)
     if fixture is not None:
      if fixture.poll() is None:
       import sqlite3
       try:
        a=sqlite3.connect('file:'+info['db']+'?mode=ro',uri=True);b=sqlite3.connect(str(out/'fictional.sqlite3'));a.backup(b);b.close();a.close()
       except Exception:pass
       fixture.send_signal(signal.SIGINT);fixture.wait(timeout=10)
     (out/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False));sys.exit(0 if result['passed'] else 1)

"""Synthetic mixed native/web regression. Build the App first, then opt in to a visible window on a separate test Mac.
All records are fictional; no model, household, printer, login or collection is used.
"""
from pathlib import Path
import sys, os, json, subprocess, tempfile, time, urllib.request, shutil
import argparse, signal, hashlib, select, zlib, struct


def fictional_png():
    # A tiny fictional photo (4x4 coral pixels): only its exact bytes matter for the original-preservation check.
    raw=b''.join(b'\x00'+bytes([200,60,40]*4) for _ in range(4))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',4,4,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


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
          '家庭运行规则.md':'| child-1 | 示例甲 | — | 12岁 | 七年级 |\n| child-2 | 示例乙 | — | 10岁 | 五年级 |\n| child-3 | 示例丙 | — | 9岁 | 四年级 |\n',
          '跟踪台账.md':'| T01 | 示例甲 | 虚构数学作业：有理数加法 | 2026-10-28 | 待跟进 | 虚构学校通知 | 完成两道加法并检查 |\n',
          '学习与成长.md':'全虚构软件验收，不代表家长体验。','消息来源.md':''}
        app.read=lambda name:docs.get(name,'')
        import family_wrong_review
        # One server refusal (503) for 示例丙's first standalone save, before anything is written: the sheet keeps the input for a retry.
        real_store=app.wrong_review_store;unavailable=[True]
        class OnceUnavailable:
            def __init__(self,inner):self.inner=inner
            def __getattr__(self,name):return getattr(self.inner,name)
            def save(self,obj):
                if unavailable and isinstance(obj,dict) and obj.get('child')=='示例丙':
                    unavailable.clear();raise family_wrong_review.WrongReviewError('虚构：后台暂时不可用，这次没有保存。',503,'synthetic_unavailable')
                return self.inner.save(obj)
        app.wrong_review_store=lambda:OnceUnavailable(real_store())
        f=app.save_task_feedback(dict(task_id='T01',child='示例甲',day='2026-10-28',note='虚构：第一题加法符号算错',request_key='synthetic-native-topic-feedback-01'))
        w=app.save_record(dict(child='示例甲',day='2026-10-28',category='学习进展',subject='数学',title='虚构加法错题',note='题面：(-8)+5=?\n学生原答：-13\n可见订正/正确答案：-3',source='错题照片核对',related_record_id=f['record_id'],followup_kind='补充观察'))
        app.save_record(dict(child='示例乙',day='2026-10-28',category='学习进展',subject='数学',title='另一孩子虚构错题',note='题面：1+1\n学生原答：3',source='错题照片核对'))
        # An older wrong question with no original task (a legitimate unlinked note); 示例丙 has an empty notebook.
        u=app.save_record(dict(child='示例甲',day='2026-10-20',category='学习进展',subject='数学',title='虚构未关联错题',note='题面：(-6)+2=?\n学生原答：-8\n可见订正/正确答案：-4',source='错题照片核对'))
        app.prepare_assets();server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        print(json.dumps(dict(url='http://127.0.0.1:'+str(server.server_address[1]),wrong_id=w['record_id'],unlinked_id=u['record_id'],feedback_id=f['record_id'],db=str(app.DB),token=app.TOKEN)),flush=True)
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
     first=fixture.stdout.readline(); info=json.loads(first); origin=info['url']; rid=info['wrong_id'];uid=info['unlinked_id'];box=f'[data-topic-diagnosis="{rid}"]'
     focus=f'[data-record-topic="{uid}"] [data-topic-diagnosis="{uid}"]'
     with urllib.request.urlopen(origin+'/api/day?child_id=child-1',timeout=10) as r:day=json.load(r)
     item=next(i for g in day['groups'] for i in g['items'] if i.get('task_id')=='T01')
     photo=out/'fictional-wrong-photo.png';photo.write_bytes(fictional_png());photo_sha=hashlib.sha256(photo.read_bytes()).hexdigest()
     LABEL='虚构单独错题第7题';TEXT='(-9)+4=?';ANSWER='-13'
     frame_steps=[]
     for size,box_ in (('1440',[37,61,1440,820]),('900',[83,97,900,760])):
      frame_steps+=[{'name':f'set frame {size}','native':'set_frame','frame':box_},{'name':f'frame {size} 日历','native':'frame','ids':['list-mode','mode-日历']}]
      for m in ['错题本','学习进展','日历','错题本','日历']:frame_steps+=[{'name':f'click {size} {m} '+str(len(frame_steps)),'click':'mode-'+m},{'name':f'frame {size} {m} '+str(len(frame_steps)),'native':'frame','ids':['list-mode','mode-日历']}]
     steps=frame_steps+[{'name':'original row','until':'row-'+item['id']},{'name':'select original','click':'row-'+item['id']},{'name':'history button','until':'history-web'},
     {'name':'open same-task history','click':'history-web'},{'name':'native bridge state','native':'state'},
     web('same wrong card',until=ready(box+' [data-topic-open]')),
     {'name':'first web page ready','native':'state'},
     web('open diagnosis',click(box+' [data-topic-open]'),ready(box+' [data-topic-input="search"]')),
     web('find topic',f"const x=document.querySelector('{box} [data-topic-input=search]');x.value='有理数加法';x.dispatchEvent(new Event('input',{{bubbles:true}}));document.querySelector('{box} [data-topic-search]').click();return {{ok:true}}",ready(box+' [data-topic-confirm="cnm_010"]')),
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
     web('paused: one primary action, quiet restart, no technical ids',until=f"const b=document.querySelector('{box}');const p=[...b.querySelectorAll('.topic-actions button.primary')];const t=b.textContent;return {{ok:p.length===1&&p[0].hasAttribute('data-topic-resume')&&!!b.querySelector('.topic-actions [data-topic-start].topic-quiet')&&!/cnm_|e0f931b/.test(t)&&(b.querySelector('[data-topic-source]')?.textContent||'').includes('CC BY-NC 4.0'),primary:p.map(x=>x.textContent)}}"),
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
     {'name':'final saved surface','native':'state'},
     # The notebook journey: an unlinked older question is selected by its own id, opens its own focused 知识点与练习 panel and
     # comes back to the same selection; the learning entry selects THAT record; 回原作业 selects the same task in the calendar.
     {'name':'back to native for notebook','key':'0','modifiers':['command']},{'name':'notebook entry','click':'mode-错题本'},
     {'name':'unlinked row','click':'wrong-row-'+str(uid)},{'name':'unlinked detail','until':'wrong-detail-'+str(uid),'contains':'虚构未关联错题'},
     {'name':'unlinked detail says no task','until':'wrong-detail-'+str(uid),'contains':'未关联原作业'},{'name':'notebook detail snapshot','native':'snapshot'},
     {'name':'open focused topic','click':'record-topic-'+str(uid)},
     web('focused panel names the record',until=f"const p=document.querySelector('[data-record-topic=\"{uid}\"]');return {{ok:!!p&&p.textContent.includes('虚构未关联错题')&&!!p.querySelector('[data-topic-diagnosis=\"{uid}\"]')}}"),
     web('focused panel ready',until=ready(focus+' [data-topic-input="search"]')),
     # A broad everyday word: the stated grade (七年级) comes first and is marked, other grades stay as choices; picking 七年级 lists only its chapters.
     web('focused broad query',f"const x=document.querySelector('{focus} [data-topic-input=search]');x.value='加法';x.dispatchEvent(new Event('input',{{bubbles:true}}));document.querySelector('{focus} [data-topic-search]').click();return {{ok:true}}",
         f"const b=document.querySelector('{focus}');const g=b.querySelector('[data-topic-grade=\"7\"]');const all=[...b.querySelectorAll('[data-topic-grade]')];const others=all.filter(x=>!['','7'].includes(x.dataset.topicGrade));return {{ok:!!g&&g.textContent.includes('七年级')&&g.textContent.includes('孩子年级')&&others.length>0&&!!b.querySelector('[data-topic-confirm=\"cnm_010\"]'),grades:all.map(x=>x.textContent)}}"),
     {'name':'focused broad query snapshot','native':'snapshot'},
     web('focused relevant grade',click(focus+' [data-topic-grade="7"]'),f"const b=document.querySelector('{focus}');const rows=[...b.querySelectorAll('[data-topic-confirm]')].map(x=>x.closest('li').textContent);return {{ok:b.querySelector('[data-topic-grade=\"7\"]')?.getAttribute('aria-pressed')==='true'&&rows.length>0&&rows.every(r=>/七[上下]/.test(r))&&!!b.querySelector('[data-topic-confirm=\"cnm_010\"]'),rows}}"),
     web('focused link topic',click(focus+' [data-topic-confirm="cnm_010"]'),ready(focus+' [data-topic-start]')),
     {'name':'focused topic snapshot','native':'snapshot'},
     # The focused practice screen itself: one question answered and paused, then one primary next step, no technical ids, one source/caution line.
     web('focused start',click(focus+' [data-topic-start]'),ready(focus+' [data-topic-form="answer"]')),
     web('focused answer',f"const f=document.querySelector('{focus} [data-topic-form=answer]');const r=f.querySelector('input[type=radio]');if(r)r.click();else{{const x=f.querySelector('input[data-topic-input]');x.value='10000';x.dispatchEvent(new Event('input',{{bubbles:true}}));}}f.querySelector('[data-topic-submit]').click();return {{ok:true}}",ready(focus+' [data-topic-item="1"]')),
     web('focused next question shown',until=ready(focus+' [data-topic-form="answer"] [data-topic-pause]')),
     web('focused pause',click(focus+' [data-topic-pause]'),ready(focus+' [data-topic-resume]')),
     web('focused practice screen',until=f"const d=document.querySelector('[data-record-topic=\"{uid}\"]');const b=d.querySelector('[data-topic-diagnosis]');const p=[...b.querySelectorAll('.topic-actions button.primary')];const t=d.textContent;return {{ok:p.length===1&&p[0].hasAttribute('data-topic-resume')&&!!b.querySelector('.topic-actions [data-topic-start].topic-quiet')&&!/cnm_|e0f931b/.test(t)&&!t.includes('返回清单')&&(t.match(/未经教师审核/g)||[]).length===1&&(b.querySelector('[data-topic-source]')?.textContent||'').includes('CC BY-NC 4.0')&&(b.querySelector('[data-topic-linked]')?.textContent||'').includes('七上 第二章 有理数的运算'),primary:p.map(x=>x.textContent)}}"),
     {'name':'focused practice snapshot','native':'snapshot'},
     {'name':'back to native after focused link','key':'0','modifiers':['command']},{'name':'notebook back state','native':'state'},
     {'name':'same record still selected','until':'wrong-detail-'+str(uid),'contains':'虚构未关联错题'},
     {'name':'learning entry for notebook','click':'mode-学习进展'},{'name':'unlinked learning topic','until':'learning-'+str(uid),'contains':'有理数的加法法则','timeout':20},
     {'name':'learning selects exact record','click':'learning-wrong-'+str(rid)},{'name':'exact record detail','until':'wrong-detail-'+str(rid),'contains':'虚构加法错题'},
     {'name':'exact record state','native':'state'},
     {'name':'back to original task','click':'record-task-'+str(rid)},{'name':'back to task state','native':'state'},{'name':'original task snapshot','native':'snapshot'},
     {'name':'empty notebook child','click':'child-child-3'},{'name':'empty notebook entry','click':'mode-错题本'},
     {'name':'empty notebook action','until':'wrong-add'},{'name':'empty notebook snapshot','native':'snapshot'},
     {'name':'open add wrong','click':'wrong-add'},{'name':'empty notebook add state','native':'state'},
     # The empty sheet closes by its own 取消 (real click). Then the first standalone wrong is actually typed, photographed (a declared
     # file-pick result, NOT the system picker), refused once by the server (503), loses one reply (unknown), and saves by the same submission.
     {'name':'cancel empty add sheet','click':'sheet-cancel'},{'name':'empty add sheet closed','native':'state'},
     {'name':'reopen add wrong','click':'wrong-add'},
     {'name':'focus label','click':'wrong-add-label'},{'name':'type label','type':LABEL,'into':'wrong-add-label'},
     {'name':'focus text','click':'wrong-add-text'},{'name':'type text','type':TEXT,'into':'wrong-add-text'},
     {'name':'focus answer','click':'wrong-add-answer'},{'name':'type answer','type':ANSWER,'into':'wrong-add-answer'},
     {'name':'declare photo pick','pick':[str(photo)]},{'name':'choose photo','click':'wrong-add-photo'},{'name':'photo chosen','until':'wrong-add-photo-name','contains':photo.name,'timeout':10},
     {'name':'save meets 503','click':'sheet-save'},{'name':'503 reason shown','until':'sheet-status','contains':'后台暂时不可用','timeout':15},{'name':'503 state','native':'state'},
     {'name':'lose next reply','faults':['drop_reply']},{'name':'retry loses reply','click':'sheet-save'},
     {'name':'unknown reason shown','until':'sheet-status','contains':'不确定是否已保存','timeout':15},{'name':'unknown state','native':'state'},
     {'name':'retry same submission','click':'sheet-save'},{'name':'saved notice shown','until':'workspace-notice','contains':'错题已记进错题本','timeout':15},
     {'name':'new record state','native':'state'},{'name':'new record detail','find_text':TEXT,'timeout':10},
     {'name':'unknown subject reason','find_text':'没写科目','timeout':10},{'name':'new record snapshot','native':'snapshot'},
     {'name':'open original photo','click_prefix':'record-original-'},{'name':'original document','native':'documents'},
     {'name':'close original','native':'close_document'},{'name':'same record after original','native':'state'}]
     # Feedback=1, wrong=2, other-child=3, unlinked=4, actual retry=5. No additional setup records in this M4 fixture.
     (out/'steps.json').write_text(json.dumps(steps,ensure_ascii=False,indent=2))
     support=out/'support';support.mkdir(mode=0o700);(support/'desktop.json').write_text(json.dumps({'service_origin':origin}))
     shots=out/'screenshots';shots.mkdir()
     runenv={**env,'FAMILY_DESKTOP_SUPPORT_DIR':str(support),'FAMILY_DESKTOP_TEST_ORIGIN':origin,'FAMILY_DESKTOP_TEST_SURFACE':'native','FAMILY_DESKTOP_TEST_NATIVE_STEPS':str(out/'steps.json'),'FAMILY_DESKTOP_TEST_SNAPSHOT_DIR':str(shots)}
     start=time.time()
     def stop(proc,first):
      # Owned test processes only: ask first, then end it, so a hung App or fixture can't leave an orphan or skip RESULT.json.
      first()
      try:proc.wait(timeout=10)
      except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
     with (out/'native.jsonl').open('wb') as f,(out/'native.stderr').open('wb') as e:
      app=subprocess.Popen([str(exe),'--smoke-test'],env=runenv,stdout=f,stderr=e)
      try:code=app.wait(timeout=300)
      except subprocess.TimeoutExpired:stop(app,app.terminate);raise AssertionError('owned test App timeout')
     for line in (out/'native.jsonl').read_text(errors='replace').splitlines():
      try:events.append(json.loads(line))
      except ValueError:pass
     done=[x for x in events if x.get('state')=='native_step_done']; bad=[x for x in done if x.get('result',{}).get('ok') is not True]
     rows={x['name']:x['result'] for x in done}
     # Frame proof first, so an old build's counterexample is recorded even when a later step stops the run.
     frames={k:dict(window=v.get('window_frame'),mode=v.get('mode'),anchors=v.get('anchors')) for k,v in rows.items() if k.startswith('frame ') or k.startswith('set frame ')}
     stable={}
     for size in ('1440','900'):
      seen=[v for k,v in frames.items() if k.startswith(f'frame {size} ')]
      stable[size]=dict(count=len(seen),window=len({json.dumps(v['window']) for v in seen})==1 and len(seen)==6,switch=len({json.dumps((v['anchors'] or {}).get('list-mode')) for v in seen})==1,set=frames.get(f'set frame {size}',{}).get('window'),
                        windows=sorted({json.dumps(v['window']) for v in seen}),switch_frames=sorted({json.dumps((v['anchors'] or {}).get('list-mode')) for v in seen}))
     result.update(frames=frames,frame_stable=stable)
     assert all(v['window'] and v['switch'] and json.dumps(v['set'])==v['windows'][0] for v in stable.values()),stable
     assert code==0 and len(done)==len(steps) and not bad,(code,len(done),len(steps),bad)
     assert rows['native bridge state']['selection']==item['id']
     assert rows['notebook back state']['surface']=='native' and rows['notebook back state']['mode']=='错题本',rows['notebook back state']
     assert rows['exact record state']['mode']=='错题本' and rows['back to task state']['mode']=='日历' and rows['back to task state']['selection']==item['id'],rows['back to task state']
     assert rows['empty notebook add state']['child']=='child-3' and rows['empty notebook add state']['sheet']=='wrong-add',rows['empty notebook add state']
     req=urllib.request.Request(origin+'/api/topic/state',data=json.dumps(dict(child_id='child-1',record_id=uid)).encode(),headers={'Content-Type':'application/json','X-Family-Token':info['token']})
     with urllib.request.urlopen(req,timeout=10) as r:linked=json.load(r)
     assert [x.get('topic_id') for x in linked['links'] if x.get('basis')=='current']==['cnm_010'],linked['links']
     assert any(d.get('basis')=='current' and d.get('topic_id')=='cnm_010' and len(d.get('items') or [])==1 and d.get('state')=='paused' for d in linked['diagnoses']),linked['diagnoses']
     result.update(discovery={k:rows[k] for k in ('focused broad query','focused relevant grade','paused: one primary action, quiet restart, no technical ids','focused practice screen')})
     assert rows['first web page ready']['web_visible'] and rows['saved web page ready']['web_visible']
     assert rows['question draft keeps web open']['surface']=='web' and rows['question draft keeps web open']['web_visible']
     assert rows['native current state']['native_visible'] and rows['native current state']['selection']==item['id']
     for child in ['child-1','child-2']:
      with urllib.request.urlopen(origin+'/api/day?child_id='+child,timeout=10) as r:view=json.load(r)
      items=[i for g in view['groups'] for i in g['items']]
      if child=='child-1':
       t=next(i for i in items if i.get('task_id')=='T01');assert t['progress']['retries']==1;assert any(z.get('retry',{}).get('state')=='current' for z in t['records'])
      else:assert all(i.get('task_id')!='T01' for i in items)
     # The first standalone wrong: real input, exactly one record for the selected child, the original photo byte-for-byte, the returned id selected.
     exits=[x for x in events if x.get('state')=='exiting'];assert len(exits)==1 and exits[0].get('sheet_open')=='',exits
     assert rows['empty add sheet closed']['sheet']=='' and rows['empty add sheet closed']['child']=='child-3',rows['empty add sheet closed']
     assert rows['503 state']['sheet']=='wrong-add' and rows['503 state']['dirty'] and rows['unknown state']['sheet']=='wrong-add' and rows['unknown state']['dirty'],(rows['503 state'],rows['unknown state'])
     import sqlite3
     db=sqlite3.connect('file:'+info['db']+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
     mine=[dict(r) for r in db.execute("SELECT * FROM records WHERE child='示例丙'")]
     ids=json.loads(mine[0]['attachments'] or '[]') if len(mine)==1 else []
     up=db.execute('SELECT * FROM uploads WHERE id=?',(ids[0],)).fetchone() if len(ids)==1 else None
     db.close()
     assert len(mine)==1 and len(ids)==1 and up is not None and up['mime']=='image/png',(mine,ids)
     new=mine[0]
     assert (new['subject'] or '')=='' and TEXT in new['note'] and ANSWER in new['note'] and not new.get('related_record_id'),new
     assert hashlib.sha256((Path(info['db']).parent/'uploads'/ids[0]).read_bytes()).hexdigest()==photo_sha
     with urllib.request.urlopen(urllib.request.Request(origin+'/upload/'+ids[0],headers={'X-Family-Token':info['token']}),timeout=10) as r:served=r.read();served_type=r.headers.get('Content-Type','')
     assert hashlib.sha256(served).hexdigest()==photo_sha and served_type.startswith('image/png'),served_type
     st=rows['new record state'];assert st['sheet']=='' and st['mode']=='错题本' and st['child']=='child-3' and st['record']==new['id'] and st['notice']=='错题已记进错题本。',st
     docs=rows['original document']['documents'];assert len(docs)==1 and docs[0]['path']=='/upload/'+ids[0] and json.loads(docs[0]['page'] or '{}').get('type')=='image/png',docs
     back=rows['same record after original'];assert back['record']==new['id'] and back['mode']=='错题本' and back['child']=='child-3' and back['windows']==st['windows'],back
     result.update(standalone_wrong=dict(record_id=new['id'],attachment=ids[0],photo_sha256=photo_sha,served_type=served_type,mime=up['mime'],title=new['title']))
     result.update(passed=True,steps=len(done),elapsed_s=round(time.time()-start,2),native_to_actual_WK_and_back=True,child_isolation=True)
    except BaseException as e:
     import traceback
     result['error']=str(e);(out/'FAILURE.txt').write_text(traceback.format_exc())
    finally:
     if app is not None and app.poll() is None:
      try:app.terminate();app.wait(timeout=10)
      except subprocess.TimeoutExpired:app.kill();app.wait(timeout=5)
     if fixture is not None:
      if fixture.poll() is None:
       import sqlite3
       try:
        a=sqlite3.connect('file:'+info['db']+'?mode=ro',uri=True);b=sqlite3.connect(str(out/'fictional.sqlite3'));a.backup(b);b.close();a.close()
       except Exception:pass
       fixture.send_signal(signal.SIGINT)
       try:fixture.wait(timeout=10)
       except subprocess.TimeoutExpired:
        fixture.terminate()
        try:fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:fixture.kill();fixture.wait(timeout=5)
        result['fixture_forced_stop']=True
     (out/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False));sys.exit(0 if result['passed'] else 1)

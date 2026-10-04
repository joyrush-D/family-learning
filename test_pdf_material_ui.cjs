// Synthetic browser + real local API checks for the PDF/Word page-group panel in the school original dialog; no real family, CLI or model calls.
// The backend fixture links real synthetic 11-page PDFs and picture-bearing synthetic DOCX files, then runs family_pdf_material.prepare with stand-ins for the model, the Word conversion (returns the synthetic PDF) and poppler when absent.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{once}=require('node:events'),net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function until(check,label){for(let i=0;i<200;i++){if(await check())return;await delay(50)}throw Error(label)}
// Same failure/lost-receipt/replay checks as test_homework_feedback_review_ui.cjs.
async function threeAttemptSave(page,path,button,error,success,read){
 const bodies=[],results=[],before=await read();
 await page.route('**'+path,async route=>{
  bodies.push(route.request().postDataJSON());
  if(bodies.length===1)return route.fulfill({status:503,json:{error:'虚构未写入失败'}});
  const response=await route.fetch(),value=await response.json();assert.equal(response.status(),200);results.push(value);
  return bodies.length===2?route.fulfill({status:503,json:{error:'虚构写入成功但回执丢失'}}):route.fulfill({response,json:value});
 });
 try{
  await button.click();await until(error,'no-write failure');assert.deepEqual((await read()).records,before.records);
  await button.click();await until(error,'lost receipt retained');assert.equal((await read()).records.length,before.records.length+1);
  await button.click();await until(success,'same numbered retry saved');
 }finally{await page.unroute('**'+path)}
 assert.equal(bodies.length,3);assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[1],bodies[2]);assert(bodies[0].request_key);
 const id=value=>path==='/api/wrong/save'?value.saved?.[0]?.id:value.record_id??value.id;
 assert(Number.isInteger(id(results[1])));assert.equal(id(results[0]),id(results[1]));assert.equal(path==='/api/wrong/save'?results[1].saved?.[0]?.existing:results[1].replayed,true);
 assert.equal((await read()).records.length,before.records.length+1);return {record_id:id(results[1]),request_key:bodies[0].request_key};
}
async function fits(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no document overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(items=>items.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
 assert.equal(await page.locator('#schoolOriginalDialog button:visible').evaluateAll(items=>items.some(b=>b.getBoundingClientRect().height<40)),false,'dialog actions are usable touch targets');
}
async function proof(page,name){if(process.env.AGENT_UI_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.AGENT_UI_PROOF_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.AGENT_UI_PROOF_DIR,name+'.png')})}}
const fixture=String.raw`
import tempfile,os,json,datetime,io,struct,zlib,base64,contextlib,hashlib
from pathlib import Path
from unittest.mock import patch
with tempfile.TemporaryDirectory(prefix='synthetic-pdf-ui-') as tmp:
 os.environ['FAMILY_DATA']=tmp
 os.environ['FAMILY_HOST']='family.test';os.environ['FAMILY_USER']='synthetic-parent'
 import app,family_agent,family_llm,family_media,family_pdf,family_pdf_material,family_qq_capture,test_media,test_pdf
 app.DATA=Path(tmp).resolve();app.DB=app.DATA/'family.sqlite3'
 docs={'家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n'}
 app.read=lambda name:docs.get(name,'')
 app.connect().close()
 (app.DATA/'agent.json').write_text(json.dumps({'enabled':True,'sources':[{'id':'synthetic','platform':'wechat','child_id':'child-1','name':'虚构班级通知','cursor':'','enabled':True},{'id':'qq:123456','platform':'qq','child_id':'child-1','name':'虚构QQ资料群','cursor':'','enabled':True}]}))
 store=app.agent_store();now=datetime.datetime.now(family_agent.TZ)
 def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 pixels=b''.join(b'\x00'+bytes([30+(row%2)*40,120,220,255])*96 for row in range(64))
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',96,64,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
 app.save_upload(io.BytesIO(png),len(png),'synthetic-existing.png')
 PDF=test_pdf.build_pdf(11);(app.DATA/'uploads').mkdir(exist_ok=True)
 DOCX_LAYOUT=test_media.docx(test_media.para('虚构练习卷，题目见下图')+'<w:p><w:r><w:drawing/></w:r></w:p>');DOCX_PLAIN=test_media.docx(test_media.para('虚构纯文字通知：完成练习卷。'))
 DOCX_FIELD=test_media.docx(test_media.para('虚构正文')+'<w:p><w:r><w:instrText>DATE</w:instrText></w:r></w:p>')
 PPTX=test_media.pptx(1,[('ppt/media/picture.png',png)])
 PPTX_UNSAFE=test_media.pptx(1,[('ppt/media/video.mp4',b'synthetic')])
 XLSX=test_media.xlsx()
 XLSX_UNSAFE=test_media.xlsx([('xl/worksheets/sheet1.xml','<worksheet><sheetData><f>1+1</f></sheetData></worksheet>')])
 app.save_upload(io.BytesIO(DOCX_LAYOUT),len(DOCX_LAYOUT),'synthetic-extra.docx');app.save_upload(io.BytesIO(DOCX_PLAIN),len(DOCX_PLAIN),'synthetic-plain.docx')
 def renderer():
  if test_pdf.TOOLS_AVAILABLE: return contextlib.nullcontext()
  stack=contextlib.ExitStack();stack.enter_context(patch.object(family_pdf.shutil,'which',lambda name:'/synthetic/'+name));stack.enter_context(patch.object(family_pdf,'_run',test_pdf.fake_run_factory(page_count=11)));return stack
 def model(text,images,**kw):
  pages=json.loads(text)['original_pdf']['pages']
  return dict(title='虚构页组 '+'-'.join(str(p) for p in pages),note='题目与参考答案为老师材料，未见孩子作答。<img src=x onerror=alert(1)>',uncertainties=['发送日期未知 <b>'])
 step=[0]
 def rounds(n,fail=False):
  for _ in range(n):
   step[0]+=1
   with renderer(),patch.object(family_media,'docx_pdf',side_effect=lambda body,**kw:PDF),patch.object(family_llm,'extract_draft',**({'side_effect':family_llm.LLMDraftError('合成模型超时')} if fail else {'side_effect':model})):
    assert family_pdf_material.prepare(store,now+datetime.timedelta(minutes=step[0]))==dict(used=1,failed=int(fail)),'pdf round'
 for width in (360,1440):
  for kind,done,failed in (('ready',4,False),('error',1,True),('unknown',0,False),('docx-ready',4,False),('docx-error',1,True),('docx-unknown',0,False)):
   docx=kind.startswith('docx');label='Word' if docx else 'PDF';body=DOCX_LAYOUT if docx else PDF;mime=family_media.DOCX_MIME if docx else 'application/pdf'
   text='截图本机文字识别（可能有误，请对照原图）：\n虚构学校'+label+'资料 '+kind+' '+str(width)+'：附练习卷。'
   reply=family_qq_capture.save_fragment(store,dict(source_id='qq:123456',child_id='child-1',captured_at=now.isoformat(),text=text,png=base64.b64encode(png).decode()))
   ident=reply['message_id'];ref='message:qq:123456:'+ident
   store._save('pdf:'+kind+':'+str(width),'fixture',[dict(child_id='child-1',kind='school',title='虚构'+label+'资料 '+kind+' '+str(width),body='核对原要求',evidence=[dict(ref=ref,text=text)])],now)
   upload_id=hashlib.md5((kind+str(width)).encode()).hexdigest();(app.DATA/'uploads'/upload_id).write_bytes(body)
   with store._db() as c: c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',(upload_id,'虚构练习卷-'+kind+'-'+str(width)+('.docx' if docx else '.pdf'),len(body),mime,now.isoformat()))
   store.message_attachment(dict(child_id='child-1',source_id='qq:123456',message_id=ident,attachment_id=upload_id,action='attach'),dict)
   rounds(done)
   if failed: rounds(1,True)
 native=[dict(id='native-'+str(w),time=now.isoformat(),kind='text',sender='虚构来源',text='请核对所附虚构PDF原件',unread=True) for w in (360,1440)]
 native += [dict(id='native-field-'+str(w),time=now.isoformat(),kind='text',sender='虚构来源',text='请核对所附虚构Word原件',unread=True) for w in (360,1440)]
 native += [dict(id='native-pptx-'+str(w),time=now.isoformat(),kind='text',sender='虚构来源',text='请核对所附虚构演示文稿',unread=True) for w in (360,1440)]
 native += [dict(id='native-pptx-refused-'+str(w),time=now.isoformat(),kind='text',sender='虚构来源',text='请核对所附虚构不安全演示文稿',unread=True) for w in (360,1440)]
 native += [dict(id='native-xlsx-'+str(w),time=now.isoformat(),kind='text',sender='虚构来源',text='请核对所附虚构表格',unread=True) for w in (360,1440)]
 native += [dict(id='native-xlsx-refused-'+str(w),time=now.isoformat(),kind='text',sender='虚构来源',text='请核对所附虚构不安全表格',unread=True) for w in (360,1440)]
 native += [dict(id='native-auto-'+str(w),time=now.isoformat(),kind='text',sender='虚构语文老师',text='请核对本条两份原件，各自要求以对应原件为准。',unread=True) for w in (360,1440)]
 native += [dict(id='native-text-'+str(w),time=now.isoformat(),kind='text',sender='虚构数学老师',text='今天完成练习第1至3题，第4题选做；拍照提交。',unread=False) for w in (360,1440)]
 store.ingest(dict(source_id='qq:123456',expected_cursor='',cursor='native-1',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=native))
 for w in (360,1440):
  message=native[0 if w==360 else 1];ref='message:qq:123456:'+message['id']
  store._save('native:'+str(w),'fixture',[dict(child_id='child-1',kind='school',title='虚构QQ原生PDF资料 '+str(w),body='待核对原件',evidence=[dict(ref=ref,text=message['text'])])],now)
  upload_id=hashlib.md5(('native-pdf-'+str(w)).encode()).hexdigest();(app.DATA/'uploads'/upload_id).write_bytes(PDF)
  with store._db() as c:c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',(upload_id,'虚构原生PDF-'+str(w)+'.pdf',len(PDF),'application/pdf',now.isoformat()))
  store.message_attachment(dict(child_id='child-1',source_id='qq:123456',message_id=message['id'],attachment_id=upload_id,action='attach'),dict)
  with store._db() as c:
   source=next(s for s in store._config(c)['sources'] if s['id']=='qq:123456');value=family_pdf_material.pdf_input(store,c,source,message)
   c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',('qq:123456',message['id'],value['fingerprint'],1,json.dumps([1,2,3]),11,json.dumps(dict(kind='school_material',title='虚构已读页组',note='原件前3页待核对',uncertainties=[]),ensure_ascii=False),now.isoformat()))
 for w in (360,1440):
  app.new_task(dict(child='示例星星',title='虚构已有部分整理的作业 '+str(w),category='homework',source='message:qq:123456:native-'+str(w),due=now.date().isoformat(),action='核对所附练习卷，保留未读页。',request_key='synthetic-prepared-task-'+str(w)))
  app.new_task(dict(child='示例星星',title='虚构已归纳文字作业 '+str(w),category='homework',source='message:qq:123456:native-text-'+str(w),due=now.date().isoformat(),action='必做第1至3题，第4题选做；拍照提交。',request_key='synthetic-text-task-'+str(w)))
 for w in (360,1440):
  for refused in (False,True):
   kind='native-pptx-refused' if refused else 'native-pptx';message=next(m for m in native if m['id']==kind+'-'+str(w))
   body=PPTX_UNSAFE if refused else PPTX;upload_id=hashlib.md5((kind+str(w)).encode()).hexdigest()
   (app.DATA/'uploads'/upload_id).write_bytes(body)
   with store._db() as c:c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',(upload_id,'虚构演示文稿-'+kind+'-'+str(w)+'.pptx',len(body),family_media.PPTX_MIME,now.isoformat()))
   store.message_attachment(dict(child_id='child-1',source_id='qq:123456',message_id=message['id'],attachment_id=upload_id,action='attach'),dict)
   if not refused:
    with store._db() as c:
     source=next(s for s in store._config(c)['sources'] if s['id']=='qq:123456');value=family_pdf_material.pdf_input(store,c,source,message)
     c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',('qq:123456',message['id'],value['fingerprint'],1,json.dumps([1]),1,json.dumps(dict(kind='school_material',title='虚构演示文稿页',note='仅供家长核对',uncertainties=[]),ensure_ascii=False),now.isoformat()))
 for w in (360,1440):
  for refused in (False,True):
   kind='native-xlsx-refused' if refused else 'native-xlsx';message=next(m for m in native if m['id']==kind+'-'+str(w))
   body=XLSX_UNSAFE if refused else XLSX;upload_id=hashlib.md5((kind+str(w)).encode()).hexdigest()
   (app.DATA/'uploads'/upload_id).write_bytes(body)
   with store._db() as c:c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',(upload_id,'虚构表格-'+kind+'-'+str(w)+'.xlsx',len(body),family_media.XLSX_MIME,now.isoformat()))
   store.message_attachment(dict(child_id='child-1',source_id='qq:123456',message_id=message['id'],attachment_id=upload_id,action='attach'),dict)
   if not refused:
    with store._db() as c:
     source=next(s for s in store._config(c)['sources'] if s['id']=='qq:123456');value=family_pdf_material.pdf_input(store,c,source,message)
     c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',('qq:123456',message['id'],value['fingerprint'],1,json.dumps([1]),1,json.dumps(dict(kind='school_material',title='虚构表格页',note='仅供家长核对',uncertainties=[]),ensure_ascii=False),now.isoformat()))
 for w in (360,1440):
  message=next(m for m in native if m['id']=='native-field-'+str(w));ref='message:qq:123456:'+message['id']
  store._save('native-field:'+str(w),'fixture',[dict(child_id='child-1',kind='school',title='虚构不安全Word资料 '+str(w),body='待核对原件',evidence=[dict(ref=ref,text=message['text'])])],now)
  upload_id=hashlib.md5(('native-field-'+str(w)).encode()).hexdigest();(app.DATA/'uploads'/upload_id).write_bytes(DOCX_FIELD)
  with store._db() as c:c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',(upload_id,'虚构含动态字段Word-'+str(w)+'.docx',len(DOCX_FIELD),family_media.DOCX_MIME,now.isoformat()))
  store.message_attachment(dict(child_id='child-1',source_id='qq:123456',message_id=message['id'],attachment_id=upload_id,action='attach'),dict)
 store.ingest(dict(source_id='synthetic',expected_cursor='',cursor='cursor-1',checked_at=now.isoformat(),last_message_time=now.isoformat(),error='',messages=[dict(id='notice-'+str(w),time=now.isoformat(),kind='text',sender='虚构老师',text='虚构老师通知 '+str(w)+'：请核对所附练习卷。',unread=True) for w in (360,1440)]))
 for w in (360,1440): store._save('notice-'+str(w),'fixture',[dict(child_id='child-1',kind='school',title='虚构文字通知 '+str(w),body='核对原要求',evidence=[dict(ref='message:synthetic:notice-'+str(w),text='虚构老师通知 '+str(w)+'：请核对所附练习卷。')])],now)
 # Two complete originals in one current message become independent actions through
 # the real bounded Agent path. Only the model reply is fixed synthetic data.
 for index,w in enumerate((360,1440)):
  message=next(m for m in native if m['id']=='native-auto-'+str(w));ref='message:qq:123456:'+message['id']
  upload_id=hashlib.md5(('native-auto-pdf-'+str(w)).encode()).hexdigest()
  receipt_id=hashlib.md5(('native-auto-receipt-'+str(w)).encode()).hexdigest()
  for ident,name in [(upload_id,'虚构自动收录语文-'+str(w)+'.pdf'),(receipt_id,'虚构自动收录独立回执-'+str(w)+'.pdf')]:
   (app.DATA/'uploads'/ident).write_bytes(PDF)
   with store._db() as c:c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',(ident,name,len(PDF),'application/pdf',now.isoformat()))
   store.message_attachment(dict(child_id='child-1',source_id='qq:123456',message_id=message['id'],attachment_id=ident,action='attach'),dict)
  title='语文：完成虚构练习第1至11页 '+str(w);goal=now.date().isoformat()+'前完成虚构语文练习第1至11页，做完检查。'
  receipt_title='事务：签字交回虚构独立活动回执 '+str(w);receipt_goal=now.date().isoformat()+'前签字交回独立活动回执。'
  prepared_at=now+datetime.timedelta(seconds=10+index)
  with store._db() as c:
   source=next(s for s in store._config(c)['sources'] if s['id']=='qq:123456')
   # Compute fingerprints only after both files are linked: each PDF depends on the complete set.
   for ident,note,label in [(upload_id,goal,'虚构语文'),(receipt_id,receipt_goal,'虚构独立回执')]:
    value=family_pdf_material.pdf_input(store,c,source,message,upload_id=ident)
    for pages in ([1,2,3],[4,5,6],[7,8,9],[10,11]):
     payload=dict(kind='school_material',title=label+'第'+str(pages[0])+'至'+str(pages[-1])+'页',note=note,uncertainties=[])
     c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',('qq:123456',message['id'],value['fingerprint'],pages[0],json.dumps(pages),11,json.dumps(payload,ensure_ascii=False),now.isoformat()))
  store._save('native-auto:'+str(w),'fixture',[dict(child_id='child-1',kind='school',title='待理解虚构语文原件 '+str(w),body=family_agent.FOCUS['school'],due=now.date().isoformat(),evidence=[dict(ref=ref,text=message['text'])],plan=dict(school_messages=[dict(source_id='qq:123456',message_id=message['id'])]))],prepared_at)
  brief=dict(title=title,goal=goal,advice='',state='ready',reason='对应原件写明本项要求与完成日期，全部11页已整理。',purpose='learning',submission='',change='new',target_id='',learning_subject='语文',learning_goal_id='')
  receipt_brief=dict(brief,title=receipt_title,goal=receipt_goal,purpose='admin',learning_subject='')
  def ready_original(messages,*args,**kwargs):
   context=json.loads(messages[-1]['content']);assert context['evidence'][0]['ref']==ref,'only this current original is processed'
   assert {d['upload_id'] for d in context['pdf_material']}=={upload_id,receipt_id},'both current original IDs reach the Agent'
   assert all(d['complete'] and len(d['groups'])==4 for d in context['pdf_material']),'all groups of both originals reach the Agent'
   return dict(actions=[dict(brief,due=now.date().isoformat(),existing_item_id=context['candidate_id'],basis=[dict(part='pdf:'+upload_id+':1@'+ref,text=goal)]),dict(receipt_brief,due=now.date().isoformat(),existing_item_id='',basis=[dict(part='pdf:'+receipt_id+':1@'+ref,text=receipt_goal)])])
  with patch.object(family_llm,'_chat_json',side_effect=ready_original) as calls:
   assert family_agent._refresh_school(app,store,prepared_at,1)==dict(used=1,failed=0,created=2),'both independent actions auto-collected'
   assert calls.call_count==1,'one bounded understanding call'
  with store._db() as c:
   for expected_title,expected_id in [(title,upload_id),(receipt_title,receipt_id)]:
    row=c.execute('SELECT * FROM agent_items WHERE title=? AND child_id=?',(expected_title,'child-1')).fetchone();plan=json.loads(row['plan'])
    assert row['state']=='accepted' and plan['school_task']['auto_added'] is True,'both actions collected without parent acceptance'
    assert {u for a in plan['school_original_action']['anchors'] for u in a['upload_ids']}=={expected_id},'each action retains only its own original'
    task=c.execute('SELECT * FROM manual_tasks WHERE id=?',(row['task_id'],)).fetchone()
    assert task['title']==expected_title and task['child']=='示例星星' and task['due']==now.date().isoformat(),'original child and each explicit deadline retained'
    assert task['original_status']=='待跟进' and ref in task['source'],'collection preserves source without completion'
 store._runtime('ready',now)
 for child,source in [('示例小宇','message:qq:123456:native-360'),('示例星星','message:qq:123456:missing')]:
  try: app.new_task(dict(child=child,title='不应写入的虚构作业',source=source,request_key='synthetic-ref-guard-'+('other' if child=='示例小宇' else 'missing')))
  except app.TaskError: pass
  else: raise AssertionError('invalid source ref accepted')
 app.prepare_assets()
 server=app.ThreadingHTTPServer(('127.0.0.1',int(os.environ['TEST_AGENT_PORT'])),app.Handler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
`;
(async()=>{let proc,browser;try{
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));const url='http://127.0.0.1:'+port+'/',origin='http://family.test:'+port+'/',env={...process.env,TEST_AGENT_PORT:String(port)};for(const k of Object.keys(env))if(k.startsWith('FAMILY_'))delete env[k];
 proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});let errors='';proc.stderr.on('data',b=>{errors+=b});proc.on('error',e=>errors+=e.message);
 await until(async()=>{if(proc.exitCode!==null)throw Error(errors);try{return(await fetch(url)).ok}catch{return false}},'server startup');const state=async()=>await(await fetch(url+'api/state')).json();
 const readView=async identity=>await(await fetch(url+'api/agent/message?'+new URLSearchParams(identity))).json();
 browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP family.test 127.0.0.1'],...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
 for(const width of [360,1440]){
  const page=await browser.newPage({viewport:{width,height:820},extraHTTPHeaders:{'Tailscale-User-Login':'synthetic-parent'}}),pageErrors=[],alerts=[];page.on('pageerror',e=>pageErrors.push(e.message));page.on('dialog',async d=>{alerts.push(d.message());await d.dismiss()});
  await page.goto(origin);await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  const before=await state(),facts=s=>JSON.stringify([s.tasks,s.records,s.agent.items.map(x=>[x.id,x.state])]);let factsBefore=facts(before);
  const item=kind=>before.agent.items.find(x=>x.title==='虚构'+(kind.startsWith('docx')?'Word':'PDF')+'资料 '+kind+' '+width),ref=kind=>item(kind).evidence[0].ref,identity=kind=>({child_id:'child-1',source_id:'qq:123456',message_id:ref(kind).slice('message:qq:123456:'.length)});
  const existing=before.uploads.find(x=>x.name==='synthetic-existing.png');
  const dialog=page.locator('#schoolOriginalDialog'),panel=dialog.locator('[data-school-pdf-material]'),batches=dialog.locator('[data-school-pdf-batch]'),refresh=dialog.locator('[data-school-pdf-refresh]'),retry=dialog.locator('[data-school-pdf-retry]');
  const open=async ref=>{await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('[data-agent-item] [data-school-original-ref="'+ref+'"]').first().click();await dialog.locator('[data-school-original-files]').waitFor({state:'attached'});await dialog.locator('[data-school-original-upload]').waitFor()};
  const close=async()=>{await dialog.locator('[data-school-original-close]').click();await until(async()=>!(await dialog.isVisible()),'dialog closed')};
  const automatic=before.tasks.find(t=>t.title==='语文：完成虚构练习第1至11页 '+width),autoReceiptTask=before.tasks.find(t=>t.title==='事务：签字交回虚构独立活动回执 '+width),autoRef='message:qq:123456:native-auto-'+width;
  const autoExerciseFile=before.uploads.find(x=>x.name==='虚构自动收录语文-'+width+'.pdf'),autoReceiptFile=before.uploads.find(x=>x.name==='虚构自动收录独立回执-'+width+'.pdf');
  const autoExerciseGoal=before.today+'前完成虚构语文练习第1至11页，做完检查。',autoReceiptGoal=before.today+'前签字交回独立活动回执。',autoIdentity={child_id:'child-1',source_id:'qq:123456',message_id:'native-auto-'+width};
  assert.ok(automatic,'the bounded Agent produced the native-original task');assert.equal(automatic.child,'示例星星');assert.equal(automatic.due,before.today);
  assert.ok(autoReceiptTask,'the same bounded call produced the independent receipt task');assert.notEqual(autoReceiptTask.id,automatic.id);assert.equal(autoReceiptTask.child,automatic.child);assert.equal(autoReceiptTask.due,before.today);
  assert.equal(automatic.action,autoExerciseGoal);assert.equal(autoReceiptTask.action,autoReceiptGoal);assert(automatic.school_origin&&autoReceiptTask.school_origin);assert(autoExerciseFile&&autoReceiptFile);
  const autoCard=page.locator('[data-query-target="task:'+automatic.id+'"]');await autoCard.waitFor();
  assert.match(await autoCard.innerText(),/语文：完成虚构练习第1至11页/);
  await autoCard.locator('[data-school-original-ref="'+autoRef+'"]').click();await until(async()=>await panel.count()===2,'the full original keeps both complete PDFs');
  assert.match(await dialog.innerText(),/虚构语文老师/);assert.equal(await batches.count(),8);
  for(const text of await panel.allTextContents()){
   assert.match(text,/全部 11 页已整理/);
   assert.doesNotMatch(text,/待家长核对/,'complete understood requirements do not ask the parent to repeat the Agent classification');
   assert.match(text,/以上为AI整理，要求以老师原件为准/,'summaries stay distinct from teacher originals');
  }
  for(const file of [autoExerciseFile,autoReceiptFile])assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+file.id+'"]').count(),1,'the full original retains both actual files');
  assert.equal(await dialog.locator('[data-school-homework-new]').count(),0,'the originals are already linked to their collected tasks');
  await fits(page);await proof(page,'auto-original-collected-'+width);await close();
  const autoFeedback=page.locator('#taskDialog'),autoResources=autoFeedback.locator('#taskSchoolResources'),autoNote='虚构自动收录作业反馈 '+width+'：练习已尝试，第6题待订正。';
  const assertAutoScope=async(task,own,other,quote,otherQuote)=>{
   const basis=autoResources.locator('[data-task-material-scope="action"]');await basis.waitFor();
   assert.match(await basis.innerText(),/AI 已整理 · 本项资料/);
   assert.equal(await basis.locator('.task-material-text').count(),0,'the task conclusion is not repeated as raw source quotes');
   assert.match(await basis.locator('[data-task-material-pages]').innerText(),/第 1、2、3 页/);
   assert.equal(await autoResources.locator('[data-school-pdf-document]').count(),1,'one task keeps only its own original preparation');
   assert.match(await autoResources.innerText(),/原件整理：全部 11 页已整理/);
   assert((await autoResources.innerText()).includes(own.name));assert(!(await autoResources.innerText()).includes(other.name));assert(!(await autoResources.innerText()).includes(otherQuote));
   assert.equal((await autoResources.innerText()).split(own.name).length,2,'one filename appears once beside its download action');
   assert(!(await autoResources.innerText()).includes(quote),'the complete requirement remains in the task heading without a duplicate paragraph');
   assert(!(await autoResources.innerText()).includes('虚构QQ资料群'),'a single-child task does not repeat the known class/group label');
   assert.equal(await autoResources.locator('.task-record-files a').count(),1,'this task exposes exactly one original');assert.equal(await autoResources.locator('.task-record-files a[href*="'+own.id+'"]').count(),1);assert.equal(await autoResources.locator('a[href*="'+other.id+'"]').count(),0,'the sibling original has no download link in this task');
   assert.equal(await autoResources.locator('details,[data-school-pdf-retry],[data-school-page-read],[data-school-material-retry]').count(),0,'the task shows its own prepared requirement without disclosure or processing');
   const view=await readView({...autoIdentity,task_id:task.id});assert.equal(view.task_id,task.id);assert.equal(view.action_material.scoped,true);assert.deepEqual(view.attachments.map(a=>a.id),[own.id]);assert.deepEqual(view.pdf_material.documents.map(d=>d.upload_id),[own.id]);assert.deepEqual(view.action_material.quotes.map(q=>q.text),[quote]);
  };
  await page.locator('[data-query-target="task:'+autoReceiptTask.id+'"] [data-task]').first().click();await assertAutoScope(autoReceiptTask,autoReceiptFile,autoExerciseFile,autoReceiptGoal,autoExerciseGoal);
  await fits(page);await proof(page,'auto-receipt-scoped-'+width);await autoFeedback.locator('[data-close=taskDialog]').click();
  await page.reload();await page.locator('body[data-page="home"]').waitFor();await page.locator('[data-query-target="task:'+autoReceiptTask.id+'"] [data-task]').first().click();await assertAutoScope(autoReceiptTask,autoReceiptFile,autoExerciseFile,autoReceiptGoal,autoExerciseGoal);
  assert.deepEqual((await state()).tasks.find(t=>t.id===autoReceiptTask.id).update,autoReceiptTask.update,'reading and reopening do not complete the receipt');await fits(page);await proof(page,'auto-receipt-scoped-reopened-'+width);await autoFeedback.locator('[data-close=taskDialog]').click();assert.equal(facts(await state()),factsBefore,'reading both action scopes writes no task, record or decision');
  await autoCard.locator('[data-task="'+automatic.id+'"]').first().click();await assertAutoScope(automatic,autoExerciseFile,autoReceiptFile,autoExerciseGoal,autoReceiptGoal);
  await autoFeedback.locator('#taskForm [name=note]').fill(autoNote);
  await autoResources.getByRole('button',{name:'查看老师原消息'}).click();await until(async()=>await dialog.locator('[data-school-pdf-document]').count()===2,'the source preview retains both originals outside the action scope');
  for(const file of [autoExerciseFile,autoReceiptFile])assert.equal(await dialog.locator('.task-record-files a[href*="'+file.id+'"]').count(),1);
  assert((await dialog.innerText()).includes(autoExerciseGoal)&&(await dialog.innerText()).includes(autoReceiptGoal));assert.equal(await dialog.locator('[data-school-pdf-retry],[data-print-upload],[data-school-original-attach]').count(),0,'full source preview remains read-only');
  const fullAutoView=await readView(autoIdentity);assert.deepEqual(fullAutoView.attachments.map(a=>a.id).sort(),[autoExerciseFile.id,autoReceiptFile.id].sort());assert.equal(fullAutoView.action_material,undefined);
  await fits(page);await proof(page,'auto-action-full-original-preview-'+width);await close();assert.equal(await autoFeedback.locator('#taskForm [name=note]').inputValue(),autoNote,'viewing the full source preserves this action feedback draft');await assertAutoScope(automatic,autoExerciseFile,autoReceiptFile,autoExerciseGoal,autoReceiptGoal);
  const feedbackCalls=[];await page.route('**/api/task/feedback',async route=>{feedbackCalls.push(route.request().postDataJSON());if(feedbackCalls.length===1)return route.fulfill({status:503,json:{error:'虚构自动收录反馈暂不可保存'}});return route.continue()});
  await autoFeedback.locator('#saveTaskFeedback').click();await autoFeedback.locator('#taskError').getByText(/虚构自动收录反馈暂不可保存/).waitFor();
  assert.equal((await state()).records.length,before.records.length,'failed feedback save is zero-write');
  assert.equal(await autoFeedback.locator('#taskForm [name=note]').inputValue(),autoNote,'failure keeps feedback under the same original task');
  await autoFeedback.locator('#saveTaskFeedback').click();await until(async()=>/反馈已保存/.test(await autoFeedback.locator('#taskFeedbackStatus').innerText()),'automatic original feedback retry saved');
  assert.equal(feedbackCalls.length,2);assert.deepEqual(feedbackCalls[1],feedbackCalls[0],'feedback retry preserves the original submission number and body');await page.unroute('**/api/task/feedback');
  let autoSaved=await state(),autoRecords=autoSaved.records.filter(r=>r.source==='事项:'+automatic.id);
  assert.equal(autoRecords.length,1);assert.equal(autoRecords[0].note,autoNote);assert.equal(autoRecords[0].child,'示例星星');assert.equal(autoSaved.tasks.length,before.tasks.length,'feedback does not create another task');
  assert.deepEqual(autoSaved.tasks.find(t=>t.id===automatic.id).update,automatic.update,'saving feedback does not imply completion');
  assert.equal(autoSaved.records.filter(r=>r.source==='事项:'+autoReceiptTask.id).length,0,'practice feedback is not copied to the independent receipt');assert.deepEqual(autoSaved.tasks.find(t=>t.id===autoReceiptTask.id).update,autoReceiptTask.update,'practice feedback does not complete the receipt');
  await fits(page);await proof(page,'auto-original-feedback-'+width);await autoFeedback.locator('[data-close=taskDialog]').click();
  await page.reload();await page.locator('body[data-page="home"]').waitFor();await autoCard.locator('[data-task="'+automatic.id+'"]').first().click();
  await autoFeedback.locator('#taskFeedbackHistory').getByText(autoNote,{exact:true}).waitFor();await assertAutoScope(automatic,autoExerciseFile,autoReceiptFile,autoExerciseGoal,autoReceiptGoal);
  assert.match(await autoFeedback.locator('#taskTitle').innerText(),/示例星星.*语文：完成虚构练习第1至11页/);
  autoSaved=await state();autoRecords=autoSaved.records.filter(r=>r.source==='事项:'+automatic.id);assert.equal(autoRecords.length,1);assert.equal(autoSaved.tasks.filter(t=>t.id===automatic.id).length,1,'reopening preserves one task and one feedback');
  await fits(page);await proof(page,'auto-original-feedback-reopened-'+width);
  // Continue from the real saved feedback: handwritten wrong item and correction use
  // the ordinary APIs, with no model, printer enqueue or separate synthetic task.
  const autoLoopBefore=await state(),autoTaskBefore=autoLoopBefore.tasks.find(t=>t.id===automatic.id),autoReceiptBefore=autoLoopBefore.tasks.find(t=>t.id===autoReceiptTask.id),autoPrintIds=autoLoopBefore.printing.jobs.map(j=>j.id).sort(),autoFeedbackId=autoRecords[0].id;
  const assertAutoPrintSources=async()=>{
   const response=await fetch(url+'api/print/homework/materials?task_id='+encodeURIComponent(automatic.id)),out=await response.json();assert.equal(response.status,200,JSON.stringify(out));
   assert.deepEqual(out.task,{id:automatic.id,child:automatic.child});assert.equal(out.school_error,'');assert.deepEqual(out.files.map(f=>f.source),[{type:'upload',id:autoExerciseFile.id}]);assert.equal(out.files[0].origin,'school');assert.equal(out.files[0].name,autoExerciseFile.name);
  };
  await assertAutoPrintSources();assert.equal(facts(await state()),facts(autoLoopBefore),'reading print sources does not write business records');assert.deepEqual((await state()).printing.jobs.map(j=>j.id).sort(),autoPrintIds,'reading sources creates no print job');
  const autoWrong=autoFeedback.locator('[data-task-wrong-form="'+autoFeedbackId+'"]'),autoWrongLabel='虚构语文练习第6题';await autoWrong.locator(':scope > summary').click();assert.equal(await autoWrong.locator('[data-task-wrong-photo]').count(),0);
  await autoWrong.locator('[data-wrong-field=label]').fill(autoWrongLabel);await autoWrong.locator('[data-wrong-field=text]').fill('虚构第6题：选择与原文相符的一项。');await autoWrong.locator('[data-wrong-field=answer]').fill('A（虚构）');await autoWrong.locator('[data-wrong-field=correction]').fill('B（虚构）');
  const autoWrongSaved=await threeAttemptSave(page,'/api/wrong/save',autoWrong.locator('[data-task-wrong-save]'),async()=>/结果尚未核对/.test(await autoWrong.innerText()),async()=>/错题已保存在这份作业下/.test(await autoFeedback.locator('#taskFeedbackStatus').innerText()),state);
  const autoWrongCard=autoFeedback.locator('#taskFeedbackHistory .task-feedback-record').filter({has:page.locator('[data-record="'+autoWrongSaved.record_id+'"]')});await autoWrongCard.locator('[data-followup]').click();await page.locator('#recordDialog[open]').waitFor();assert.equal(await autoFeedback.evaluate(x=>x.open),false,'the original homework view closes before correction entry');
  const autoCorrectionForm=page.locator('#recordForm'),autoCorrectionNote='虚构自动收录语文订正 '+width+'：第6题按原文线索重选，独立复测待做。';assert.equal(await autoCorrectionForm.locator('[name=followup_kind]').inputValue(),'订正');assert.equal(await autoCorrectionForm.locator('[name=related_record_id]').inputValue(),String(autoWrongSaved.record_id));await autoCorrectionForm.locator('[name=note]').fill(autoCorrectionNote);
  const autoCorrection=await threeAttemptSave(page,'/api/record',autoCorrectionForm.locator('[type=submit]'),async()=>/虚构/.test(await page.locator('#recordError').innerText()),async()=>!await page.locator('#recordDialog').evaluate(x=>x.open),state);
  assert.equal(await page.locator('dialog[open]').count(),0,'saved correction closes its page before reopening the original homework');
  await page.reload();await page.locator('body[data-page="home"]').waitFor();await autoCard.locator('[data-task="'+automatic.id+'"]').first().click();await assertAutoScope(automatic,autoExerciseFile,autoReceiptFile,autoExerciseGoal,autoReceiptGoal);
  assert.equal(await autoFeedback.locator('#taskRequirement').innerText(),autoExerciseGoal);await autoFeedback.locator('#taskFeedbackHistory').getByText(autoNote,{exact:true}).waitFor();await autoFeedback.locator('#taskFeedbackHistory').getByText(autoCorrectionNote,{exact:true}).waitFor();await until(async()=> (await autoFeedback.locator('#taskFeedbackHistory .task-feedback-record').filter({has:page.locator('[data-record="'+autoWrongSaved.record_id+'"]')}).innerText()).includes(autoWrongLabel),'the saved wrong item stays under this original homework');
  const autoLoopAfter=await state(),autoWrongRecord=autoLoopAfter.records.find(r=>r.id===autoWrongSaved.record_id),autoCorrectionRecord=autoLoopAfter.records.find(r=>r.id===autoCorrection.record_id);
  assert.equal(autoLoopAfter.records.length,autoLoopBefore.records.length+2,'wrong-item and correction retries create exactly two additional records');assert.equal(autoWrongRecord.related_record_id,autoFeedbackId);assert.equal(autoCorrectionRecord.related_record_id,autoWrongSaved.record_id);assert.equal(autoCorrectionRecord.followup_kind,'订正');
  for(const record of [autoWrongRecord,autoCorrectionRecord]){assert.equal(record.child,automatic.child);assert.equal(record.linked_task_id,automatic.id)}
  assert.deepEqual(autoLoopAfter.tasks.find(t=>t.id===automatic.id),autoTaskBefore,'the feedback chain preserves the same task, original and completion state');assert.deepEqual(autoLoopAfter.tasks.find(t=>t.id===autoReceiptTask.id),autoReceiptBefore,'the independent receipt remains unchanged');assert.equal(autoLoopAfter.records.filter(r=>r.source==='事项:'+autoReceiptTask.id||r.linked_task_id===autoReceiptTask.id).length,0,'the receipt receives no feedback, wrong item or correction');assert.equal(autoLoopAfter.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===automatic.id&&r.related_record_id===autoFeedbackId).length,1,'lost wrong-item receipt does not duplicate the item');
  await assertAutoPrintSources();assert.deepEqual((await state()).printing.jobs.map(j=>j.id).sort(),autoPrintIds,'the entire manual feedback chain starts no print job');
  await autoResources.getByRole('button',{name:'查看老师原消息'}).click();await until(async()=>await dialog.locator('[data-school-pdf-document]').count()===2,'the reopened feedback chain returns to both full originals');for(const file of [autoExerciseFile,autoReceiptFile])assert.equal(await dialog.locator('.task-record-files a[href*="'+file.id+'"]').count(),1);await fits(page);await proof(page,'auto-original-closed-loop-source-'+width);await close();await assertAutoScope(automatic,autoExerciseFile,autoReceiptFile,autoExerciseGoal,autoReceiptGoal);
  await fits(page);await proof(page,'auto-original-closed-loop-reopened-'+width);await autoFeedback.locator('[data-close=taskDialog]').click();factsBefore=facts(await state());
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();
  const fileList=page.locator('[data-qq-files]');await fileList.locator('summary').click();
  assert.match(await fileList.innerText(),/虚构原生PDF-360\.pdf/);assert.match(await fileList.innerText(),/虚构原生PDF-1440\.pdf/);
  await fileList.locator('[data-school-original-ref="message:qq:123456:native-'+width+'"]').click();await panel.waitFor();
  assert.match(await panel.innerText(),/虚构原生PDF-[\s\S]*已整理 3 \/ 11 页/);
  assert.equal(await dialog.locator('[data-school-homework-new]').count(),0,'a pending school item should be reviewed first');await fits(page);
  await close();
  await open('message:qq:123456:native-field-'+width);await panel.waitFor();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'unavailable');
  assert.match(await panel.innerText(),/不能安全转换[\s\S]*另存为PDF/);assert.equal(await retry.count(),0);
  assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+before.uploads.find(x=>x.name==='虚构含动态字段Word-'+width+'.docx').id+'"]').count(),1);
  await fits(page);await proof(page,'school-docx-refused-'+width);await close();
  if(!(await fileList.evaluate(e=>e.open)))await fileList.locator('summary').click();
  await fileList.locator('[data-school-original-ref="message:qq:123456:native-pptx-'+width+'"]').click();await panel.waitFor();
  assert.equal(await panel.getAttribute('data-school-pdf-original'),'pptx');
  assert.match(await panel.innerText(),/演示文稿逐页整理[\s\S]*全部 1 页已整理/);
  assert.match(await panel.innerText(),/动画、声音和备注未读取/);
  assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+before.uploads.find(x=>x.name==='虚构演示文稿-native-pptx-'+width+'.pptx').id+'"]').count(),1);
  await refresh.click();await panel.waitFor();await until(async()=>!(await dialog.locator('[data-school-pdf-notice]').innerText()).includes('正在读取'),'PPTX refresh settled');
  assert.equal(await panel.getAttribute('data-school-pdf-original'),'pptx');
  await fits(page);await proof(page,'school-pptx-ready-'+width);
  const sourceRef='message:qq:123456:native-pptx-'+width,taskCount=before.tasks.length;
  await dialog.locator('[data-school-homework-new]').click();
  const taskForm=page.locator('#newTaskForm'),taskDialog=page.locator('#newTaskDialog');await taskDialog.waitFor({state:'visible'});
  assert.equal(await taskForm.locator('[name="source"]').inputValue(),sourceRef);
  assert.equal(await taskForm.locator('[name="source"]').getAttribute('readonly'),'');
  assert.equal(await taskForm.locator('[name="child"] option').count(),1);
  for(const name of ['box','child','category','source'])assert.equal(await taskForm.locator(`[name="${name}"]`).locator('xpath=..').isVisible(),false,`${name} is fixed by the original`);
  assert.match(await taskDialog.innerText(),/为示例星星记作业/);
  assert.match(await taskForm.locator('#newTaskDetailsSummary').innerText(),/截止日期/);
  await fits(page);await proof(page,'linked-homework-form-'+width);
  assert.equal(await taskForm.locator('[name="due"]').inputValue(),'','an old file must not become today by default');
  assert.equal(await taskForm.locator('[name="due"]').getAttribute('required'),null,'unknown school deadline can stay unknown');
  await taskForm.locator('[name="title"]').fill('虚构原件核对后作业 '+width);
  await taskForm.locator('[name="action"]').fill('家长核对后完成虚构练习');
  await taskForm.locator('[name="due"]').fill(before.today);
  const requestKey=await taskForm.locator('[name="request_key"]').inputValue();
  await page.route('**/api/task/new',route=>route.fulfill({status:503,json:{error:'虚构暂不可保存'}}));
  await taskForm.locator('[type="submit"]').click();await page.locator('#newTaskError').getByText('虚构暂不可保存').waitFor();
  assert.equal(await taskForm.locator('[name="request_key"]').inputValue(),requestKey);
  assert.equal(await taskForm.locator('[name="title"]').inputValue(),'虚构原件核对后作业 '+width);
  await page.unroute('**/api/task/new');await taskForm.locator('[type="submit"]').click();
  await taskDialog.waitFor({state:'hidden'});
  const saved=(await state()).tasks.find(t=>t.title==='虚构原件核对后作业 '+width);
  assert.ok(saved);assert.equal(saved.source,sourceRef);assert.equal(saved.child,'示例星星');
  assert.equal((await state()).tasks.length,taskCount+1);
  factsBefore=facts(await state());
  await page.locator('nav [data-page="home"]').click();
  await page.locator('nav [data-page="tasks"]').click();
  await page.locator('#content [data-new-task="yes"]').first().click();await taskDialog.waitFor({state:'visible'});
  for(const name of ['box','child','category'])assert.equal(await taskForm.locator(`[name="${name}"]`).locator('xpath=..').isVisible(),true,`${name} returns for manual entry`);
  assert.equal(await taskForm.locator('[name="source"]').locator('xpath=..').evaluate(e=>e.classList.contains('hide')),false,'manual source remains available under details');
  assert.equal(await taskForm.locator('[name="due"]').getAttribute('required'),null);
  await taskDialog.locator('[data-close="newTaskDialog"]').click();
  await page.locator('nav [data-page="home"]').click();
  const taskCard=page.locator('[data-query-target="task:'+saved.id+'"]');await taskCard.waitFor();
  await taskCard.locator('[data-school-original-ref="'+sourceRef+'"]').click();await panel.waitFor();
  assert.equal(await dialog.locator('[data-school-homework-new]').count(),0,'the same source is not offered as a new task again');
  await fits(page);await close();
  // The task itself reads existing preparation; no re-upload, model, collection or record write.
  const feedback=page.locator('#taskDialog'),resources=feedback.locator('#taskSchoolResources');let resourceReads=0;
  await page.route('**/api/agent/message?*',route=>{resourceReads++;return route.fulfill({status:503,json:{error:'虚构资料读取失败'}})});
  await taskCard.locator('[data-task]').click();await resources.getByText(/虚构资料读取失败/).waitFor();
  assert.equal(resourceReads,1,'failed resource read is not automatically repeated');
  await feedback.locator('#taskForm [name=note]').fill('这次草稿仍保留');
  await page.unroute('**/api/agent/message?*');await resources.getByRole('button',{name:'重试读取资料'}).click();
  await resources.locator('[data-task-material-state]').waitFor();assert.match(await resources.innerText(),/AI 已整理[\s\S]*1 \/ 1 页/);assert.match(await resources.innerText(),/不是孩子作答或已完成/);
  assert.equal(await feedback.locator('#taskForm [name=note]').inputValue(),'这次草稿仍保留');
  await resources.getByRole('button',{name:'查看老师原消息'}).click();await dialog.waitFor({state:'visible'});
  await dialog.getByText(/AI 已整理/).waitFor();
  assert.equal(await dialog.locator('[data-print-upload],[data-school-original-ref],[data-school-original-upload],[data-school-original-attach]').count(),0,'original preview cannot print or edit while feedback is open');
  assert.equal(await dialog.locator('[data-task-material-state="ready"]').count(),1);
  await dialog.locator('[data-school-original-close]').click();
  assert.equal(await feedback.locator('#taskForm [name=note]').inputValue(),'这次草稿仍保留');
  assert.equal(await resources.locator('[data-school-pdf-retry],[data-school-page-read],[data-school-material-retry]').count(),0,'reading does not expose a processing action');
  assert.equal(await resources.locator('img[onerror]').count(),0);await fits(page);await proof(page,'task-prepared-resource-'+width);
  await feedback.locator('#taskForm [name=note]').fill('');await feedback.locator('[data-close=taskDialog]').click();
  await page.reload();await page.locator('body[data-page=home]').waitFor();
  const partial=before.tasks.find(t=>t.title==='虚构已有部分整理的作业 '+width);
  await page.locator('[data-query-target="task:'+partial.id+'"] [data-task]').click();
  await resources.locator('[data-task-material-unread]').waitFor();assert.match(await resources.innerText(),/AI 已整理[\s\S]*3 \/ 11 页[\s\S]*未读页：4、5、6、7、8、9、10、11[\s\S]*原件前3页待核对/);
  assert.equal(await resources.locator('[data-task-material-state]').count(),1);
  assert.equal(await resources.locator('details').count(),0,'prepared text and teacher originals need no nested disclosure');
  assert.doesNotMatch(await resources.innerText(),/独立Agent.*每轮/,'task resources omit backend scheduling boilerplate');
  assert.equal(await resources.getByText('原件前3页待核对',{exact:true}).isVisible(),true);
  await fits(page);await proof(page,'task-partial-resource-'+width);
  await feedback.locator('[data-close=taskDialog]').click();
  const wrongView=await readView({child_id:'child-1',source_id:'qq:123456',message_id:'native-'+width});
  const textTask=before.tasks.find(t=>t.title==='虚构已归纳文字作业 '+width);
  const textView=await readView({child_id:'child-1',source_id:'qq:123456',message_id:'native-text-'+width});
  assert.deepEqual(textView.attachments,[]);assert.equal(textView.pdf_material,null);assert.equal(textView.material_draft,null);
  await page.locator('[data-query-target="task:'+textTask.id+'"] [data-task]').click();
  await resources.getByRole('button',{name:'查看老师原消息'}).waitFor();
  assert.equal(await resources.locator('[data-task-material-state="text"]').count(),1,'a text-only task has no unread-original claim');
  assert.doesNotMatch(await resources.innerText(),/原件已保存不代表内容已理解|尚未整理完成|本次未读取/);
  assert.equal(await feedback.locator('#taskForm [name=note]').inputValue(),'');
  await fits(page);await proof(page,'task-text-material-'+width);
  await feedback.locator('#taskForm [name=note]').fill('查看原消息时保留这份虚构反馈草稿');
  await page.route('**/api/agent/message?*',route=>route.fulfill({status:503,json:{error:'虚构原消息读取失败'}}));
  await resources.getByRole('button',{name:'查看老师原消息'}).click();
  await dialog.waitFor({state:'visible'});
  await dialog.getByText(/虚构原消息读取失败/).waitFor();
  assert.equal(await feedback.evaluate(e=>e.open),true,'original preview leaves the same task open');
  assert.equal(await dialog.locator('[data-school-original-upload],[data-school-original-attach],[data-school-teacher-open],[data-school-homework-new]').count(),0,'task original preview is read-only');
  await page.unroute('**/api/agent/message?*');
  await dialog.locator('[data-school-original-retry]').click();
  await dialog.getByText(textView.message.text,{exact:true}).waitFor();
  assert.equal(await dialog.locator('[data-task-material-state="text"]').count(),1);
  await fits(page);await proof(page,'task-original-preview-'+width);
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
  assert.equal(await feedback.locator('#taskForm [name=note]').inputValue(),'查看原消息时保留这份虚构反馈草稿');
  assert.equal(await feedback.evaluate(e=>e.open),true,'Escape closes only the original preview');
  for(const bad of [{child_id:'child-2'},{message_id:'native-'+width}]){
   const button=resources.getByRole('button',{name:'查看老师原消息'});
   await button.evaluate((element,bad)=>{if(bad.child_id)element.dataset.schoolOriginalChild=bad.child_id;else element.dataset.schoolOriginalRef='message:qq:123456:'+bad.message_id},bad);
   await button.click();assert.equal(await dialog.evaluate(e=>e.open),false,'unrelated child or ref cannot open over this task');
   await button.evaluate((element,width)=>{element.dataset.schoolOriginalChild='child-1';element.dataset.schoolOriginalRef='message:qq:123456:native-text-'+width},width);
  }
  for(const failure of [false,true]){
   let release,entered=false,calls=0;
   await page.route('**/api/agent/message?*',async route=>{calls++;if(calls===1){entered=true;await new Promise(resolve=>release=resolve);await route.fulfill(failure?{status:503,json:{error:'过期虚构失败'}}:{json:{...textView,child_id:'child-2'}})}else await route.fulfill({json:textView})});
   await resources.getByRole('button',{name:'查看老师原消息'}).click();await until(async()=>entered,'delayed original GET began');
   await dialog.evaluate(e=>e.close());
   await resources.getByRole('button',{name:'查看老师原消息'}).click();
   await dialog.getByText(textView.message.text,{exact:true}).waitFor();
   release();await delay(100);
   assert.doesNotMatch(await dialog.innerText(),/过期虚构失败|归属暂时无法核对/,'old success or failure cannot change reopened source');
   assert.equal(await feedback.locator('#taskForm [name=note]').inputValue(),'查看原消息时保留这份虚构反馈草稿');
   await dialog.locator('[data-school-original-close]').click();await page.unroute('**/api/agent/message?*');
  }
  // State saving may close the parent task: do not open a child preview during that save.
  let finishStateSave,stateSaveEntered=false,previewReads=0;
  await page.route('**/api/task',async route=>{stateSaveEntered=true;await new Promise(resolve=>finishStateSave=resolve);await route.fulfill({status:503,json:{error:'虚构状态保存失败'}})});
  await page.route('**/api/agent/message?*',route=>{previewReads++;return route.fulfill({json:textView})});
  await feedback.locator('#taskStatusDetails summary').click();
  await feedback.locator('#taskForm [type=submit]').click();await until(async()=>stateSaveEntered,'task status save began');
  await resources.getByRole('button',{name:'查看老师原消息'}).click();
  assert.equal(await dialog.evaluate(e=>e.open),false,'saving the parent cannot open a source preview that outlives it');
  assert.equal(previewReads,0,'busy source click makes no GET');
  finishStateSave();await feedback.locator('#taskError').getByText(/虚构状态保存失败/).waitFor();
  assert.equal(await feedback.locator('#taskForm [name=note]').inputValue(),'查看原消息时保留这份虚构反馈草稿');
  await resources.getByRole('button',{name:'查看老师原消息'}).click();await dialog.getByText(textView.message.text,{exact:true}).waitFor();
  assert.equal(previewReads,1,'after a failed save the original preview is usable again');
  await dialog.locator('[data-school-original-close]').click();await page.unroute('**/api/task');await page.unroute('**/api/agent/message?*');
  await feedback.locator('#taskForm [name=note]').fill('');
  await feedback.locator('[data-close=taskDialog]').click();
  await page.locator('[data-query-target="task:'+textTask.id+'"] [data-task]').click();
  await resources.locator('[data-task-material-state="text"]').waitFor();
  await feedback.locator('[data-close=taskDialog]').click();
  const pageOnly={...textView,pages:[{original_url:'https://example.test/text-only',url:'https://example.test/text-only',fetched_at:textView.message.time,text:'虚构网页内容 <img src=x onerror=alert(1)>',text_truncated:true}]};
  await page.route('**/api/agent/message?*',route=>route.fulfill({json:pageOnly}));
  await page.locator('[data-query-target="task:'+textTask.id+'"] [data-task]').click();
  await resources.getByText(/超过6000字的部分未保存/).waitFor();
  assert.equal(await resources.locator('[data-task-material-state="pages"]').count(),1);
  assert.doesNotMatch(await resources.innerText(),/原件已保存不代表内容已理解|AI 已整理/,'saved static text does not claim AI or complete reading');
  assert.equal(await resources.locator('img[onerror]').count(),0);
  await fits(page);await proof(page,'task-static-material-'+width);
  await feedback.locator('[data-close=taskDialog]').click();await page.unroute('**/api/agent/message?*');
  const combinedView={...pageOnly,message:{...pageOnly.message,kind:'qq_window_fragment',unread:true,text:'截图文字 https://example.test/text-only https://example.test/not-saved'}};
  await page.route('**/api/agent/message?*',route=>route.fulfill({json:combinedView}));
  await page.locator('[data-query-target="task:'+textTask.id+'"] [data-task]').click();
  await resources.locator('[data-task-material-state="pages"]').waitFor();
  assert.match(await resources.locator('[data-task-source-gap="fragment"]').innerText(),/完整原消息与附件仍待补充/);
  assert.match(await resources.locator('[data-task-source-gap="unread"]').innerText(),/另有未读资料/);
  assert.equal(await resources.locator('[data-task-source-gap="links"]').innerText(),'未读网页：https://example.test/not-saved','only the missing linked page is named');
  assert.equal(await resources.locator('[data-task-material-state="text"]').count(),0);
  await fits(page);await proof(page,'task-combined-material-gaps-'+width);
  await feedback.locator('[data-close=taskDialog]').click();await page.unroute('**/api/agent/message?*');
  await page.route('**/api/agent/message?*',route=>route.fulfill({json:{...textView,message:{...textView.message,text:'虚构网页 https://example.test/not-saved'}}}));
  await page.locator('[data-query-target="task:'+textTask.id+'"] [data-task]').click();
  await resources.getByText(/网页内容尚未在此保存/).waitFor();
  assert.equal(await resources.locator('[data-task-material-state="text"]').count(),0,'an unread link never becomes complete text');
  await feedback.locator('[data-close=taskDialog]').click();await page.unroute('**/api/agent/message?*');
  for(const kind of ['unread','fragment']){
   const gapView={...textView,message:{...textView.message,kind:kind==='fragment'?'qq_window_fragment':'text',unread:kind==='unread'},unavailable_attachment_ids:kind==='unread'?['synthetic-unavailable']:[]};
   await page.route('**/api/agent/message?*',route=>route.fulfill({json:gapView}));
   await page.locator('[data-query-target="task:'+textTask.id+'"] [data-task]').click();
   await resources.getByRole('button',{name:'查看老师原消息'}).waitFor();
   assert.equal(await resources.locator('[data-task-material-state="text"]').count(),0,'reading gaps never become complete text');
   assert.equal(await resources.locator('[data-task-material-state="'+kind+'"]').count(),1);
   assert.match(await resources.innerText(),kind==='fragment'?/截图识别文字/:/原件暂不可读取/);
   await feedback.locator('[data-close=taskDialog]').click();await page.unroute('**/api/agent/message?*');
  }
  const pageView={...wrongView,pages:[{original_url:'https://example.test/worksheet',url:'https://example.test/worksheet',fetched_at:wrongView.message.time,text:'虚构题目见下图 <img src=x onerror=alert(1)>',text_truncated:false}]};
  await page.route('**/api/agent/message?*',route=>route.fulfill({json:pageView}));
  await page.locator('[data-query-target="task:'+partial.id+'"] [data-task]').click();
  await resources.getByText(/图片、附件、动态或登录后的内容未读取/).waitFor();
  assert.match(await resources.innerText(),/https:\/\/example.test\/worksheet[\s\S]*读取于[\s\S]*题目见下图/);
  assert.equal(await resources.locator('img[onerror]').count(),0);
  await feedback.locator('[data-close=taskDialog]').click();await page.unroute('**/api/agent/message?*');
  await page.route('**/api/agent/message?*',route=>route.fulfill({json:{...wrongView,child_id:'child-2'}}));
  await page.locator('[data-query-target="task:'+partial.id+'"] [data-task]').click();await resources.getByText(/归属暂时无法核对/).waitFor();assert.equal(await resources.locator('[data-task-material-state]').count(),0,'wrong child response reveals no material');
  await feedback.locator('[data-close=taskDialog]').click();await page.unroute('**/api/agent/message?*');
  assert.equal(facts(await state()),factsBefore,'task resource preview and failed retry are read-only');
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();
  if(!(await fileList.evaluate(e=>e.open)))await fileList.locator('summary').click();
  await fileList.locator('[data-school-original-ref="message:qq:123456:native-pptx-refused-'+width+'"]').click();await panel.waitFor();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'unavailable');
  assert.match(await panel.innerText(),/不能安全完整转换[\s\S]*另存为PDF/);assert.equal(await retry.count(),0);
  assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+before.uploads.find(x=>x.name==='虚构演示文稿-native-pptx-refused-'+width+'.pptx').id+'"]').count(),1);
  await fits(page);await proof(page,'school-pptx-refused-'+width);await close();
  if(!(await fileList.evaluate(e=>e.open)))await fileList.locator('summary').click();
  await fileList.locator('[data-school-original-ref="message:qq:123456:native-xlsx-'+width+'"]').click();await panel.waitFor();
  assert.equal(await panel.getAttribute('data-school-pdf-original'),'xlsx');
  assert.match(await panel.innerText(),/表格逐页整理[\s\S]*全部 1 页已整理/);
  assert.match(await panel.innerText(),/核对数值、版式和要求/);
  assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+before.uploads.find(x=>x.name==='虚构表格-native-xlsx-'+width+'.xlsx').id+'"]').count(),1);
  await refresh.click();await until(async()=>!(await dialog.locator('[data-school-pdf-notice]').innerText()).includes('正在读取'),'XLSX refresh settled');
  await fits(page);await proof(page,'school-xlsx-ready-'+width);
  const unknownRef='message:qq:123456:native-xlsx-'+width;
  await dialog.locator('[data-school-homework-new]').click();await taskDialog.waitFor({state:'visible'});
  assert.equal(await taskForm.locator('[name="due"]').getAttribute('required'),null);
  await taskForm.locator('[name="title"]').fill('虚构日期未明作业 '+width);
  await taskForm.locator('[name="action"]').fill('先核对原件要求，截止日期待确认');
  await taskForm.locator('[type="submit"]').click();await taskDialog.waitFor({state:'hidden'});
  const unknownTask=(await state()).tasks.find(t=>t.title==='虚构日期未明作业 '+width);
  assert.ok(unknownTask);assert.equal(unknownTask.source,unknownRef);assert.equal(unknownTask.due,'无明确截止');
  await page.locator('nav [data-page="home"]').click();
  assert.doesNotMatch(await page.locator('.today-task-groups').innerText(),/虚构日期未明作业/,'undated history is not today homework');
  await page.locator('nav [data-page="tasks"]').click();assert.match(await page.locator('#content').innerText(),/虚构日期未明作业/);
  factsBefore=facts(await state());
  await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();
  if(!(await fileList.evaluate(e=>e.open)))await fileList.locator('summary').click();
  await fileList.locator('[data-school-original-ref="message:qq:123456:native-xlsx-refused-'+width+'"]').click();await panel.waitFor();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'unavailable');
  assert.match(await panel.innerText(),/不能完整安全转换[\s\S]*另存为PDF/);assert.equal(await retry.count(),0);
  assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+before.uploads.find(x=>x.name==='虚构表格-native-xlsx-refused-'+width+'.xlsx').id+'"]').count(),1);
  await fits(page);await proof(page,'school-xlsx-refused-'+width);await close();
  const isMessage=u=>u.pathname==='/api/agent/message';
  // Routed replies that still need the real server go through node, so the family.test host is rewritten the way test_message_page_ui.cjs does.
  const real=route=>route.fetch({url:route.request().url().replace('family.test','127.0.0.1'),headers:{...route.request().headers(),host:'family.test:'+port}});
  const linked=async kind=>{const v=await readView(identity(kind)),pdf=v.pdf_material?.upload_id||null,ids=v.attachments.map(a=>a.id);return{pdf,screenshot:ids.find(id=>id!==pdf)||null,ids:[...ids].sort()}};
  const detachIDs=async()=>(await dialog.locator('[data-school-original-detach]').evaluateAll(items=>items.map(b=>b.dataset.schoolOriginalDetach))).sort();
  await page.route('**/api/parent/login',async route=>{assert.deepEqual(route.request().postDataJSON(),{username:'synthetic-parent',password:'synthetic-password'});await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})})});
  const login=async()=>{await page.locator('#parentLoginDialog[open]').waitFor();await page.locator('#parentLoginForm [name=username]').fill('synthetic-parent');await page.locator('#parentLoginForm [name=password]').fill('synthetic-password');await page.locator('#parentLoginSubmit').click();await page.locator('#parentLoginDialog').waitFor({state:'hidden'})};
  // 1. Linked PDF whose total is still unknown: no page count is implied, the old "PDF unsupported" note is not shown beside it.
  await open(ref('unknown'));await panel.waitFor();let text=await panel.innerText();
  assert.match(text,/总页数尚未核对/);assert.doesNotMatch(text,/全部 \d+ 页已整理/);assert.doesNotMatch(text,/未读页/);assert.equal(await batches.count(),0);
  assert.doesNotMatch(await dialog.innerText(),/尚不支持自动整理/,'old PDF-unsupported note is hidden when pdf_material is present');
  assert.equal(await dialog.locator('[data-school-material-record],[data-school-material-draft],[data-school-material-status]').count(),0);
  assert.equal(await retry.count(),0);const unknownLinks=await linked('unknown');assert.equal(typeof unknownLinks.pdf,'string');assert.equal(typeof unknownLinks.screenshot,'string','the fragment screenshot is linked beside the PDF');assert.equal(unknownLinks.ids.length,2);assert.deepEqual(await detachIDs(),unknownLinks.ids,'PDF original and the fragment screenshot both stay linked and removable');
  await fits(page);await proof(page,'school-pdf-unknown-'+width);await close();
  // 2. 11 pages with pages 1-3 saved and a failed later batch: processed and unread pages are explicit, drafts are escaped.
  await open(ref('error'));await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'error');
  assert.match(text,/已整理 3 \/ 11 页/);assert.match(text,/未读页：4、5、6、7、8、9、10、11（共 8 页）/);assert.match(text,/暂未成功/);assert.match(text,/虚构练习卷-error-\d+\.pdf/);
  assert.equal(await batches.count(),1);assert.match(await batches.first().innerText(),/第 1、2、3 页[\s\S]*虚构页组 1-2-3[\s\S]*未见孩子作答。<img src=x onerror=alert\(1\)>[\s\S]*待核对：发送日期未知 <b>/);
  assert.equal(await dialog.locator('[data-school-pdf-batch] img,[data-school-pdf-batch] b').count(),0,'draft text is escaped');assert.equal(alerts.length,0);
  assert.equal(await dialog.locator('[data-school-material-record]').count(),0,'typed PDF drafts never offer a learning record');
  await fits(page);await proof(page,'school-pdf-error-'+width);
  // Retry: a failed attempt keeps the groups and can be retried; a double click queues exactly one retry; nothing is rendered or modelled.
  const actionCalls=[];await page.route('**/api/agent/action',async route=>{actionCalls.push(route.request().postDataJSON());if(actionCalls.length===1)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构重试暂时失败'})});await delay(300);await route.continue()});
  await retry.click();await until(async()=>/虚构重试暂时失败/.test(await panel.innerText()),'failed retry reported');
  assert.equal(await batches.count(),1,'failed retry keeps processed groups');assert.equal(await retry.isEnabled(),true,'retry stays available after failure');
  await retry.dispatchEvent('click');await retry.dispatchEvent('click');
  await until(async()=>/已安排后台重试/.test(await panel.innerText()),'retry queued');assert.equal(actionCalls.length,2,'double click sends one retry');
  assert.deepEqual(actionCalls[1],{action:'retry',id:(await readView(identity('error'))).pdf_material.job_id});assert.equal(await batches.count(),1);
  await page.unroute('**/api/agent/action');
  await refresh.click();await until(async()=>/独立Agent将按每轮最多3页/.test(await panel.innerText()),'refresh reads the queued state');
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'pending');assert.equal(await retry.count(),0);assert.equal(await batches.count(),1);assert.match(await panel.innerText(),/已整理 3 \/ 11 页/);
  assert.equal((await readView(identity('error'))).pdf_material.processed_pages.join(','),'1,2,3','queueing a retry does not process pages');
  // Network failure and 401 keep the shown progress and the original selection.
  await dialog.locator('[name="attachment_id"]').selectOption(existing.id);
  const dropped=route=>route.abort('connectionreset');await page.route(isMessage,dropped);
  await refresh.click();await until(async()=>/已显示的进度和填写内容保留/.test(await panel.innerText()),'network failure reported');
  assert.equal(await batches.count(),1);assert.match(await panel.innerText(),/已整理 3 \/ 11 页/);assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),existing.id,'selection survives a failed refresh');
  await page.unroute(isMessage,dropped);
  const denied=route=>route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:'请先登录'})});await page.route(isMessage,denied);
  await refresh.click();await until(async()=>/请先重新登录/.test(await panel.innerText()),'401 reported');
  assert.equal(await batches.count(),1,'401 keeps shown progress');assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),existing.id);
  await page.unroute(isMessage,denied);await login();
  await refresh.click();await until(async()=>/已读取最新进度/.test(await panel.innerText()),'refresh recovers');assert.equal(await batches.count(),1);
  // A late reply never lands in another dialog: the dialog stays open while a read is in flight, and reopening starts clean.
  const slow=async route=>{await delay(400);await route.continue()};await page.route(isMessage,slow);
  await refresh.click();assert.equal(await dialog.locator('[data-school-original-close]').isDisabled(),true);await page.keyboard.press('Escape');assert.equal(await dialog.isVisible(),true,'busy dialog cannot be closed');
  await until(async()=>/已读取最新进度/.test(await panel.innerText()),'slow reply lands in the same dialog');await page.unroute(isMessage,slow);
  // A reply held for a dialog that was force-closed is dropped: the notice opened meanwhile stays exactly as it was (pattern from test_message_page_ui.cjs).
  let release;const held=new Promise(r=>release=r);await page.route(isMessage,async route=>{await held;await route.continue()},{times:1});
  await refresh.click();await until(async()=>/正在读取最新进度/.test(await panel.innerText()),'refresh held');
  await page.evaluate(()=>document.querySelector('#schoolOriginalDialog').close());
  await open(ref('unknown'));await panel.waitFor();const unknownText=await dialog.innerText();assert.equal(await batches.count(),0);
  release();await delay(500);
  assert.equal(await dialog.innerText(),unknownText,'late reply for the force-closed notice never lands in the current dialog');assert.equal(await batches.count(),0,'error groups never leak into the unknown notice');assert.equal(await dialog.locator('[data-school-original-close]').isEnabled(),true);
  await close();await open(ref('unknown'));await panel.waitFor();assert.doesNotMatch(await panel.innerText(),/已读取最新进度|已安排后台重试/,'reopened dialog carries no old notice');assert.equal(await batches.count(),0);await close();
  // 3. Complete 11 pages: four groups, completeness only from the backend, still there after reload.
  await open(ref('ready'));await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'ready');assert.match(text,/全部 11 页已整理/);assert.doesNotMatch(text,/未读页|暂未成功/);assert.equal(await batches.count(),4);assert.equal(await retry.count(),0);
  assert.match(await batches.nth(3).innerText(),/第 10、11 页[\s\S]*虚构页组 10-11/);await fits(page);await proof(page,'school-pdf-ready-'+width);await close();
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await open(ref('ready'));await panel.waitFor();assert.equal(await batches.count(),4);assert.match(await panel.innerText(),/全部 11 页已整理/);
  // Withdrawn authorization (fictional GET reply) hides the old groups; a real re-read restores them; detaching the PDF removes the panel.
  const withdrawn=async route=>{const body=await(await real(route)).json();body.pdf_material={state:'unavailable',kind:'school_material',explanation:'虚构撤权说明 <img src=x onerror=alert(1)>'};await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})};
  await page.route(isMessage,withdrawn);await refresh.click();await until(async()=>/虚构撤权说明/.test(await panel.innerText()),'unavailable state shown');
  assert.equal(await batches.count(),0,'old groups are cleared on unavailable');assert.equal(await retry.count(),0);assert.equal(await panel.locator('img').count(),0);const readyLinks=await linked('ready');assert.equal(readyLinks.ids.length,2,'fragment screenshot and PDF are both linked');assert.deepEqual(await detachIDs(),readyLinks.ids,'both originals stay listed');
  await page.unroute(isMessage,withdrawn);await refresh.click();await until(async()=>await batches.count()===4,'real re-read restores groups');
  const readyUpload=readyLinks.pdf;assert.equal((await readView(identity('ready'))).pdf_material.upload_id,readyUpload);
  await dialog.locator('[data-school-original-detach="'+readyUpload+'"]').click();await until(async()=>await panel.count()===0,'detached PDF removes the panel');
  assert.equal((await readView(identity('ready'))).pdf_material,null);assert.deepEqual(await detachIDs(),[readyLinks.screenshot],'the fragment screenshot stays linked after the PDF is detached');assert.deepEqual((await readView(identity('ready'))).attachments.map(a=>a.id),[readyLinks.screenshot]);assert.doesNotMatch(await dialog.innerText(),/还没有关联原件/,'one original remains, so the empty note is not shown');
  await dialog.locator('[name="attachment_id"]').selectOption(readyUpload);await dialog.locator('[data-school-original-attach]').click();await until(async()=>await batches.count()===4,'re-linked PDF continues from saved groups');assert.deepEqual(await detachIDs(),readyLinks.ids,'both originals are linked again');await close();
  // 5. Word originals (backend original='docx'): the panel names Word, lists the converted copy's page numbers with a hint, keeps the fragment screenshot and the Word download, and never claims a native PDF. Nothing converts, renders or calls a model from the browser.
  await open(ref('docx-unknown'));await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-original'),'docx');assert.match(text,/Word逐页整理/);assert.doesNotMatch(text,/PDF逐页整理|PDF原件|全部 \d+ 页已整理|未读页/);assert.match(text,/虚构练习卷-docx-unknown-\d+\.docx/);assert.match(text,/总页数尚未核对/);assert.match(text,/页码可能与Word里显示的分页不同/);
  assert.equal(await batches.count(),0);assert.equal(await retry.count(),0);assert.equal(await dialog.locator('[data-school-material-record],[data-school-material-draft],[data-school-material-status]').count(),0,'no old draft or learning-record entry beside a Word page path');
  const docxUnknown=await linked('docx-unknown');assert.equal(typeof docxUnknown.pdf,'string');assert.equal(typeof docxUnknown.screenshot,'string','the fragment screenshot stays linked beside the Word original');assert.deepEqual(await detachIDs(),docxUnknown.ids);
  assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+docxUnknown.pdf+'"]').count(),1,'the original Word file keeps its download link');
  await fits(page);await proof(page,'school-docx-unknown-'+width);await close();
  // Word with pages 1-3 saved and a failed later round: converted page numbers are explicit, drafts are escaped, retry only queues the existing job and every refresh is a GET.
  await open(ref('docx-error'));await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'error');assert.equal(await panel.getAttribute('data-school-pdf-original'),'docx');assert.match(text,/Word逐页整理/);assert.match(text,/虚构练习卷-docx-error-\d+\.docx/);assert.match(text,/已整理 3 \/ 11 页/);assert.match(text,/未读页：4、5、6、7、8、9、10、11（共 8 页）/);assert.match(text,/Word原件转换或页组整理暂未成功/);assert.match(text,/页码可能与Word里显示的分页不同/);assert.doesNotMatch(text,/PDF逐页整理/);
  assert.equal(await batches.count(),1);assert.match(await batches.first().innerText(),/第 1、2、3 页[\s\S]*虚构页组 1-2-3[\s\S]*未见孩子作答。<img src=x onerror=alert\(1\)>[\s\S]*待核对：发送日期未知 <b>/);assert.equal(await panel.locator('img,b').count(),0,'Word drafts are escaped');
  assert.equal(await dialog.locator('[data-school-material-record],[data-school-material-draft],[data-school-material-status]').count(),0);await fits(page);await proof(page,'school-docx-error-'+width);
  const docxActions=[];await page.route('**/api/agent/action',async route=>{docxActions.push(route.request().postDataJSON());if(docxActions.length===1)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'虚构Word重试暂时失败'})});await delay(300);await route.continue()});
  await retry.click();await until(async()=>/虚构Word重试暂时失败/.test(await panel.innerText()),'failed Word retry reported');assert.equal(await batches.count(),1);assert.equal(await retry.isEnabled(),true);
  await retry.dispatchEvent('click');await retry.dispatchEvent('click');await until(async()=>/已安排后台重试/.test(await panel.innerText()),'Word retry queued');assert.equal(docxActions.length,2,'double click queues one Word retry');
  assert.deepEqual(docxActions[1],{action:'retry',id:(await readView(identity('docx-error'))).pdf_material.job_id});
  await refresh.click();await until(async()=>/独立Agent将把该Word原件/.test(await panel.innerText()),'refresh reads the queued Word state');
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'pending');assert.equal(await retry.count(),0);assert.equal(await batches.count(),1);assert.match(await panel.innerText(),/已整理 3 \/ 11 页/);
  const docxView=(await readView(identity('docx-error'))).pdf_material;assert.equal(docxView.original,'docx');assert.equal(docxView.processed_pages.join(','),'1,2,3','queueing a Word retry converts or processes nothing');
  await page.route(isMessage,dropped);await refresh.click();await until(async()=>/已显示的进度和填写内容保留/.test(await panel.innerText()),'Word network failure reported');assert.equal(await batches.count(),1);assert.match(await panel.innerText(),/Word逐页整理[\s\S]*已整理 3 \/ 11 页/);await page.unroute(isMessage,dropped);
  await page.route(isMessage,denied);await refresh.click();await until(async()=>/请先重新登录/.test(await panel.innerText()),'Word 401 reported');assert.equal(await batches.count(),1,'401 keeps the shown Word progress');await page.unroute(isMessage,denied);await login();
  await refresh.click();await until(async()=>/已读取最新进度/.test(await panel.innerText()),'Word refresh recovers');assert.equal(await batches.count(),1);assert.equal(docxActions.length,2,'refreshes, the failed read and the login recovery sent no action');await page.unroute('**/api/agent/action');
  // Closing and opening another notice carries no receipt from this one; reopening starts clean as well.
  await close();await open(ref('docx-unknown'));await panel.waitFor();assert.doesNotMatch(await panel.innerText(),/已读取最新进度|已安排后台重试|虚构Word重试暂时失败/,'the Word unknown notice carries no receipt from the error notice');assert.equal(await batches.count(),0);
  await close();await open(ref('docx-error'));await panel.waitFor();assert.doesNotMatch(await panel.innerText(),/已读取最新进度|已安排后台重试/,'reopened Word notice carries no old receipt');assert.equal(await batches.count(),1);await close();
  // Complete Word: four groups by converted page numbers, still there after reload. A second Word file makes the backend refuse the set without naming a kind: the panel names neither PDF nor Word, both files stay listed, removing the extra one restores the groups.
  await open(ref('docx-ready'));await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-state'),'ready');assert.match(text,/Word逐页整理/);assert.match(text,/虚构练习卷-docx-ready-\d+\.docx/);assert.match(text,/全部 11 页已整理/);assert.match(text,/页码可能与Word里显示的分页不同/);assert.doesNotMatch(text,/未读页|暂未成功|PDF逐页整理/);assert.equal(await batches.count(),4);assert.equal(await retry.count(),0);
  assert.match(await batches.nth(3).innerText(),/第 10、11 页[\s\S]*虚构页组 10-11/);await fits(page);await proof(page,'school-docx-ready-'+width);await close();
  await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();await open(ref('docx-ready'));await panel.waitFor();assert.equal(await batches.count(),4);assert.match(await panel.innerText(),/Word逐页整理[\s\S]*全部 11 页已整理/);
  const extraDocx=before.uploads.find(x=>x.name==='synthetic-extra.docx'),readyDocx=await linked('docx-ready');
  await dialog.locator('[name="attachment_id"]').selectOption(extraDocx.id);await dialog.locator('[data-school-original-attach]').click();await until(async()=>(await panel.getAttribute('data-school-pdf-state'))==='unavailable','a second Word original is refused');text=await panel.innerText();
  assert.match(text,/关联了多个DOCX原件/);assert.match(text,/学校资料 · 本次未整理/);assert.doesNotMatch(text,/PDF资料|Word资料|逐页整理|已整理|全部 \d+ 页/,'a refusal without a kind claims neither a native PDF nor a finished conversion');assert.equal(await batches.count(),0);assert.equal(await retry.count(),0);
  assert.deepEqual(await detachIDs(),[...readyDocx.ids,extraDocx.id].sort(),'both Word files and the screenshot stay listed');assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+readyDocx.pdf+'"]').count(),1,'the first Word file keeps its download link while refused');
  await dialog.locator('[data-school-original-detach="'+extraDocx.id+'"]').click();await until(async()=>await batches.count()===4,'removing the extra Word original restores the saved groups');assert.match(await panel.innerText(),/Word逐页整理[\s\S]*全部 11 页已整理/);assert.deepEqual(await detachIDs(),readyDocx.ids);await close();
  // 4. Text notice without a PDF: a real open shows no panel. A fictional reply installed before the next open carries a pending PDF plus a stale ready untyped draft: the PDF panel shows escaped name/title and the old draft (with its learning-record entry) is suppressed entirely. The teacher draft survives refresh, 401, login recovery and the real null reply that hides the panel.
  const notice=before.agent.items.find(x=>x.title==='虚构文字通知 '+width),noticeIdentity={child_id:'child-1',source_id:'synthetic',message_id:'notice-'+width},plainDocx=before.uploads.find(x=>x.name==='synthetic-plain.docx');await open(notice.evidence[0].ref);assert.equal(await panel.count(),0);
  // A plain-text Word file keeps the old draft path: no page panel, the file stays listed and downloadable.
  await dialog.locator('[name="attachment_id"]').selectOption(plainDocx.id);await dialog.locator('[data-school-original-attach]').click();await dialog.locator('[data-school-original-detach="'+plainDocx.id+'"]').waitFor();
  assert.equal((await readView(noticeIdentity)).pdf_material,null,'a plain-text Word file never enters the page-group path');assert.equal(await panel.count(),0);assert.equal(await dialog.locator('[data-school-original-files] a[href*="'+plainDocx.id+'"]').count(),1);
  await dialog.locator('[data-school-original-detach="'+plainDocx.id+'"]').click();await until(async()=>await dialog.locator('[data-school-original-detach]').count()===0,'plain Word file detached again');await close();
  const staleDraft={state:'ready',draft:{title:'虚构旧图片草稿 <b>',subject:'语文',score:null,total:null,note:'虚构旧说明',uncertainties:[]},explanation:''};
  const fictionalPDF={state:'pending',kind:'school_material',upload_id:'x',name:'虚构<练习卷>.pdf',job_id:'pdf:fictional',page_count:11,processed_pages:[1,2,3],pending_pages:[4,5,6,7,8,9,10,11],complete:false,batches:[{pages:[1,2,3],draft:{title:'虚构<标题>',note:'虚构说明',uncertainties:[]},updated:'2026-01-01T00:00:00+08:00'}],explanation:'虚构等待说明'};
  const fictional=async route=>{const body=await(await real(route)).json();body.material_draft=staleDraft;body.pdf_material=fictionalPDF;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})};
  const generic=async route=>{const body=await(await real(route)).json();body.material_draft=staleDraft;body.pdf_material=null;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})};
  await page.route('**/api/teachers',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({teachers:[{id:'synthetic-teacher',display_name:'虚构老师',subject:'语文',child_ids:['child-1'],source_ids:['synthetic'],archived:false}]})}));
  await page.route(isMessage,fictional);await open(notice.evidence[0].ref);await panel.waitFor();
  assert.match(await panel.innerText(),/虚构等待说明/);assert.match(await panel.innerText(),/虚构<练习卷>\.pdf[\s\S]*已整理 3 \/ 11 页[\s\S]*虚构<标题>/);assert.equal(await panel.locator('img,b').count(),0);
  assert.equal(await dialog.locator('[data-school-material-draft],[data-school-material-record],[data-school-material-status]').count(),0,'a stale ready untyped draft is suppressed entirely while pdf_material is present');assert.doesNotMatch(await dialog.innerText(),/虚构旧图片草稿|核对并填入学习记录/,'no learning-record consumer beside a typed PDF');
  await dialog.locator('[data-school-teacher-open]').click();const teacherForm=dialog.locator('[data-school-teacher-form]');await teacherForm.waitFor();
  await teacherForm.locator('[name="teacher_id"]').selectOption('synthetic-teacher');await teacherForm.locator('[name="target"]').selectOption('class');await teacherForm.locator('[name="quote"]').fill('家长尚未保存的老师要求草稿');
  const teacherFields=await teacherForm.evaluate(f=>Object.fromEntries(new FormData(f))),teacherNow=async()=>await teacherForm.evaluate(f=>Object.fromEntries(new FormData(f)));assert.equal(teacherFields.quote,'家长尚未保存的老师要求草稿');
  await refresh.click();await until(async()=>/已读取最新进度/.test(await panel.innerText()),'fictional refresh');assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives a refresh');
  await page.unroute(isMessage,fictional);await page.route(isMessage,denied);await refresh.click();await until(async()=>/请先重新登录/.test(await panel.innerText()),'401 on the text notice');
  assert.equal(await panel.count(),1,'401 keeps the shown PDF panel');assert.equal(await dialog.locator('[data-school-material-record]').count(),0);assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives 401');
  await page.unroute(isMessage,denied);await login();assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives the login recovery');
  await refresh.click();await until(async()=>await panel.count()===0,'real null reply hides the panel');
  assert.match(await dialog.locator('[data-school-original-status]').innerText(),/没有可整理的PDF原件/);assert.equal(await dialog.locator('[data-school-material-draft],[data-school-material-record]').count(),0,'the fictional stale draft leaves with the real reply');assert.deepEqual(await teacherNow(),teacherFields,'teacher draft survives the real null refresh');await close();
  // Without a PDF the same generic ready draft still shows with its learning-record entry, so the guard only applies while pdf_material is present.
  await page.route(isMessage,generic);await open(notice.evidence[0].ref);assert.equal(await panel.count(),0);
  await until(async()=>await dialog.locator('[data-school-material-draft]').count()===1,'generic draft shows without a PDF');assert.equal(await dialog.locator('[data-school-material-record]').count(),1);assert.equal(await dialog.locator('[data-school-material-draft] b').count(),0,'generic draft is escaped');assert.match(await dialog.innerText(),/虚构旧图片草稿 <b>/);
  await page.unroute(isMessage,generic);await close();
  // A fictional Word reply on the same text notice: the kind comes from original='docx', not from the name, and the raw conversion note is not shown; the teacher draft typed beside it survives refresh, 401, login recovery and the real null reply.
  const fictionalDocx={...fictionalPDF,original:'docx',mime:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',name:'虚构<讲义>',conversion:'虚构转换说明',explanation:'虚构Word等待说明'};
  const fictionalWord=async route=>{const body=await(await real(route)).json();body.material_draft=staleDraft;body.pdf_material=fictionalDocx;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})};
  await page.route(isMessage,fictionalWord);await open(notice.evidence[0].ref);await panel.waitFor();text=await panel.innerText();
  assert.equal(await panel.getAttribute('data-school-pdf-original'),'docx');assert.match(text,/Word逐页整理/);assert.match(text,/虚构<讲义>[\s\S]*已整理 3 \/ 11 页[\s\S]*虚构Word等待说明[\s\S]*虚构<标题>/);assert.match(text,/页码可能与Word里显示的分页不同/);assert.doesNotMatch(text,/PDF逐页整理|PDF原件|虚构转换说明/);assert.equal(await panel.locator('img,b').count(),0);
  assert.equal(await dialog.locator('[data-school-material-draft],[data-school-material-record],[data-school-material-status]').count(),0,'the stale untyped draft stays hidden beside a Word page path');
  await dialog.locator('[data-school-teacher-open]').click();await teacherForm.waitFor();await teacherForm.locator('[name="teacher_id"]').selectOption('synthetic-teacher');await teacherForm.locator('[name="target"]').selectOption('class');await teacherForm.locator('[name="quote"]').fill('Word通知下尚未保存的老师要求');
  const wordFields=await teacherNow();assert.equal(wordFields.quote,'Word通知下尚未保存的老师要求');
  await refresh.click();await until(async()=>/已读取最新进度/.test(await panel.innerText()),'fictional Word refresh');assert.deepEqual(await teacherNow(),wordFields,'teacher draft survives a Word refresh');
  await page.unroute(isMessage,fictionalWord);await page.route(isMessage,denied);await refresh.click();await until(async()=>/请先重新登录/.test(await panel.innerText()),'401 on the Word notice');assert.equal(await panel.count(),1);assert.match(await panel.innerText(),/Word逐页整理/);assert.deepEqual(await teacherNow(),wordFields,'teacher draft survives 401 beside a Word panel');
  await page.unroute(isMessage,denied);await login();assert.deepEqual(await teacherNow(),wordFields,'teacher draft survives the login recovery beside a Word panel');
  await refresh.click();await until(async()=>await panel.count()===0,'real null reply hides the Word panel');assert.match(await dialog.locator('[data-school-original-status]').innerText(),/没有可整理的Word原件/);assert.equal(await dialog.locator('[data-school-material-draft],[data-school-material-record]').count(),0);assert.deepEqual(await teacherNow(),wordFields,'teacher draft survives the real null refresh');await close();
  // Multiple PDFs from one message keep names, progress and local page groups separate in all three consumers.
  // These are routed synthetic saved views; no model, PDF processing or agent action reaches the server.
  const firstPDF={...fictionalPDF,original:'pdf',state:'error',upload_id:before.uploads.find(a=>a.name==='虚构练习卷-error-'+width+'.pdf').id,name:'虚构<题目卷>.pdf',job_id:'pdf:synthetic-questions:'+width,page_count:4,processed_pages:[1,2],pending_pages:[3,4],batches:[{pages:[1,2],draft:{title:'虚构题目页组',note:'第1、2页为题目 <img src=x onerror=alert(1)>',uncertainties:[]}}],explanation:'虚构题目卷后两页读取失败'};
  const secondPDF={...fictionalPDF,original:'pdf',state:'error',upload_id:before.uploads.find(a=>a.name==='虚构练习卷-ready-'+width+'.pdf').id,name:'虚构<家长参考>.pdf',job_id:'pdf:synthetic-reference:'+width,page_count:2,processed_pages:[1],pending_pages:[2],batches:[{pages:[1],draft:{title:'虚构参考页组',note:'本份第1页为家长参考，不能代替孩子作答',uncertainties:['第2页尚未读出 <b>']}}],explanation:'虚构参考第2页读取失败'};
  const multiPDF={state:'error',kind:'school_material',original:'pdf',mime:'application/pdf',complete:false,fingerprint:'synthetic-two-pdfs-'+width,documents:[firstPDF,secondPDF],explanation:'两份原件分别整理'};
  let multiView=multiPDF;
  const multiFiles=[firstPDF,secondPDF].map(doc=>({...before.uploads.find(a=>a.id===doc.upload_id),name:doc.name}));
  const withMulti=body=>({...body,attachments:multiFiles,material_draft:staleDraft,pdf_material:multiView});
  const multiReply=async route=>route.fulfill({status:200,json:withMulti(await(await real(route)).json())});
  const firstPanel=dialog.locator('[data-school-pdf-material][data-school-pdf-document="'+firstPDF.job_id+'"]'),secondPanel=dialog.locator('[data-school-pdf-material][data-school-pdf-document="'+secondPDF.job_id+'"]');
  await page.route(isMessage,multiReply);await open(notice.evidence[0].ref);await until(async()=>await panel.count()===2,'both PDF panels show');
  assert.match(await firstPanel.innerText(),/虚构<题目卷>\.pdf[\s\S]*已整理 2 \/ 4 页[\s\S]*未读页：3、4[\s\S]*题目卷后两页读取失败[\s\S]*第 1、2 页[\s\S]*虚构题目页组/);
  assert.match(await secondPanel.innerText(),/虚构<家长参考>\.pdf[\s\S]*已整理 1 \/ 2 页[\s\S]*未读页：2[\s\S]*参考第2页读取失败[\s\S]*第 1 页[\s\S]*虚构参考页组/);
  assert.doesNotMatch(await firstPanel.innerText(),/虚构参考页组/);assert.doesNotMatch(await secondPanel.innerText(),/虚构题目页组|第 3 页/);
  assert.equal(await dialog.locator('[data-school-pdf-material] details').count(),0,'each PDF is visible without another disclosure');assert.equal(await dialog.locator('[data-school-pdf-material] img,[data-school-pdf-material] b').count(),0,'both PDF names and drafts are escaped');
  assert.equal(await dialog.locator('[data-school-material-record],[data-school-material-draft],[data-school-material-status]').count(),0,'multiple PDFs suppress the stale image draft too');
  await dialog.locator('[name="attachment_id"]').selectOption(existing.id);
  await dialog.locator('[data-school-teacher-open]').click();await teacherForm.waitFor();await teacherForm.locator('[name="teacher_id"]').selectOption('synthetic-teacher');await teacherForm.locator('[name="target"]').selectOption('class');await teacherForm.locator('[name="quote"]').fill('双PDF旁尚未保存的老师要求');const multiFields=await teacherNow();
  const multiActions=[];let releaseRetry;const retryHeld=new Promise(resolve=>releaseRetry=resolve);
  await page.route('**/api/agent/action',async route=>{multiActions.push(route.request().postDataJSON());assert.ok(route.request().headers()['x-family-token'],'retry retains the parent token');if(multiActions.length===1)return route.fulfill({status:503,json:{error:'虚构第二份重试失败'}});if(multiActions.length===3)await retryHeld;else await delay(300);return route.fulfill({status:200,json:{ok:true}})});
  await secondPanel.locator('[data-school-pdf-retry]').click();await until(async()=>/虚构第二份重试失败/.test(await secondPanel.innerText()),'second PDF retry failure stays on that PDF');
  assert.deepEqual(multiActions,[{action:'retry',id:secondPDF.job_id}]);assert.doesNotMatch(await firstPanel.innerText(),/虚构第二份重试失败|正在安排重试/);assert.equal(await batches.count(),2);assert.deepEqual(await teacherNow(),multiFields);assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),existing.id);
  await secondPanel.locator('[data-school-pdf-retry]').dispatchEvent('click');await secondPanel.locator('[data-school-pdf-retry]').dispatchEvent('click');await until(async()=>/已安排后台重试/.test(await secondPanel.innerText()),'only the second PDF retry is queued');
  assert.deepEqual(multiActions,[{action:'retry',id:secondPDF.job_id},{action:'retry',id:secondPDF.job_id}],'a double click sends only one additional retry for the second job');assert.doesNotMatch(await firstPanel.innerText(),/已安排后台重试/);assert.equal(await batches.count(),2);
  // An invalid or removed document ID must never fall back to the first original's job.
  await firstPanel.locator('[data-school-pdf-retry]').evaluate(b=>{const id=b.dataset.schoolPdfRetry;b.dataset.schoolPdfRetry='pdf:other-child:not-in-this-message';b.click();b.dataset.schoolPdfRetry=id});assert.equal(multiActions.length,2);
  multiView={...multiPDF,documents:[firstPDF,{...secondPDF,state:'pending',explanation:'虚构第二份等待继续整理'}]};await firstPanel.locator('[data-school-pdf-refresh]').click();await until(async()=>await secondPanel.getAttribute('data-school-pdf-state')==='pending','refresh updates only the second saved state');assert.equal(await retry.count(),1,'the first error still has its own retry');assert.equal(await batches.count(),2);
  await page.route(isMessage,dropped);await firstPanel.locator('[data-school-pdf-refresh]').click();await until(async()=>/已显示的进度和填写内容保留/.test(await secondPanel.innerText()),'failed multi-PDF refresh keeps both documents');assert.equal(await panel.count(),2);assert.equal(await batches.count(),2);assert.deepEqual(await teacherNow(),multiFields);assert.equal(await dialog.locator('[name="attachment_id"]').inputValue(),existing.id);await page.unroute(isMessage,dropped);
  multiView={...multiPDF,documents:[firstPDF]};await firstPanel.locator('[data-school-pdf-refresh]').click();await until(async()=>await panel.count()===1,'removed document leaves the current saved view');
  await dialog.evaluate((d,job)=>{const b=document.createElement('button');b.dataset.schoolPdfRetry=job;d.append(b);b.click();b.remove()},secondPDF.job_id);assert.equal(multiActions.length,2,'a stale second-document button queues nothing');
  await firstPanel.locator('[data-school-pdf-retry]').click();await until(async()=>multiActions.length===3,'first-document receipt held');assert.deepEqual(multiActions[2],{action:'retry',id:firstPDF.job_id});
  await page.evaluate(()=>document.querySelector('#schoolOriginalDialog').close());await page.unroute(isMessage,multiReply);await open(ref('unknown'));await panel.waitFor();const afterMultiClose=await dialog.innerText();releaseRetry();await delay(500);assert.equal(await dialog.innerText(),afterMultiClose,'a late per-document receipt cannot enter another message');assert.equal(await panel.count(),1);await page.unroute('**/api/agent/action');await close();
  // Existing task and its nested read-only source preview show both saved preparations directly and keep the feedback draft.
  multiView=multiPDF;await page.route(isMessage,multiReply);await page.locator('nav [data-page="home"]').click();await page.locator('[data-query-target="task:'+partial.id+'"] [data-task]').click();await until(async()=>await resources.locator('[data-task-material-state]').count()===2,'task shows both saved PDF preparations');
  assert.match(await resources.locator('[data-school-pdf-document="'+firstPDF.job_id+'"]').innerText(),/虚构<题目卷>\.pdf[\s\S]*2 \/ 4 页[\s\S]*未读页：3、4[\s\S]*虚构题目页组/);assert.match(await resources.locator('[data-school-pdf-document="'+secondPDF.job_id+'"]').innerText(),/虚构<家长参考>\.pdf[\s\S]*1 \/ 2 页[\s\S]*未读页：2[\s\S]*虚构参考页组/);
  assert.equal(await resources.locator('details,[data-school-pdf-retry],[data-school-page-read],[data-school-material-retry]').count(),0,'task PDFs need no extra disclosure or processing action');await feedback.locator('#taskForm [name=note]').fill('双PDF原消息回看时保留的虚构反馈');
  await resources.getByRole('button',{name:'查看老师原消息'}).click();await until(async()=>await dialog.locator('[data-task-material-state]').count()===2,'read-only source preview shows both PDFs');assert.equal(await dialog.locator('[data-school-pdf-retry],[data-print-upload],[data-school-original-attach]').count(),0);await fits(page);await proof(page,'task-multiple-pdf-preview-'+width);await close();assert.equal(await feedback.locator('#taskForm [name=note]').inputValue(),'双PDF原消息回看时保留的虚构反馈');await feedback.locator('#taskForm [name=note]').fill('');await feedback.locator('[data-close=taskDialog]').click();await page.unroute(isMessage,multiReply);
  // The publication message opens once; its two originals and batches are not folded into a global page count.
  const publicationReply=async route=>{const body=await(await real(route)).json(),view=withMulti(await readView(noticeIdentity));body.groups=[{sender:'虚构英语老师',source:'虚构通知来源',publisher:'synthetic-publisher',messages:[{...view,items:[]}]}];body.total=1;body.offset=0;body.next_offset=null;return route.fulfill({status:200,json:body})};
  await page.route('**/api/agent/messages?*',publicationReply);await page.locator('nav [data-page="more"]').click();await page.locator('#content [data-page="agent"]').click();await page.locator('[data-school-inbox-read]').click();const publication=page.locator('[data-school-message="'+noticeIdentity.message_id+'"]');await publication.waitFor();await publication.locator(':scope > summary').click();
  assert.equal(await publication.locator('[data-school-pdf-document]').count(),2);assert.match(await publication.locator('[data-school-pdf-document="'+firstPDF.job_id+'"]').innerText(),/虚构<题目卷>\.pdf[\s\S]*已整理 2 \/ 4 页[\s\S]*第 1、2 页：虚构题目页组/);assert.match(await publication.locator('[data-school-pdf-document="'+secondPDF.job_id+'"]').innerText(),/虚构<家长参考>\.pdf[\s\S]*已整理 1 \/ 2 页[\s\S]*第 1 页：虚构参考页组/);assert.equal(await publication.locator('details').count(),0,'no per-PDF disclosure inside the message');assert.equal(await publication.locator('img,b').count(),0);await fits(page);await proof(page,'school-multiple-pdf-publication-'+width);await page.unroute('**/api/agent/messages?*',publicationReply);
  const native=before.agent.items.find(x=>x.title==='虚构QQ原生PDF资料 '+width),nativeIdentity={child_id:'child-1',source_id:'qq:123456',message_id:'native-'+width};
  await open(native.evidence[0].ref);await panel.waitFor();assert.match(await panel.innerText(),/已整理 3 \/ 11 页[\s\S]*虚构已读页组/);
  assert.equal((await readView(nativeIdentity)).attachments.length,1,'the native QQ file needs no screenshot');
  await fits(page);await close();await page.reload();await page.locator('body[data-page="home"] [data-task-all="todo"]').waitFor();
  await open(native.evidence[0].ref);await panel.waitFor();assert.match(await panel.innerText(),/虚构原生PDF-[\s\S]*已整理 3 \/ 11 页/);await close();
  assert.equal(facts(await state()),factsBefore,'no task, record or item changed');assert.deepEqual(pageErrors,[]);assert.deepEqual(alerts,[]);
  await page.close();
 }
 console.log('pdf material ui checks passed');
}finally{if(browser)await browser.close();if(proc&&proc.exitCode===null)proc.kill('SIGINT')}})().catch(e=>{console.error(e);process.exit(1)});

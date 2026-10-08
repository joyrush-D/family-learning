// Disposable synthetic Word/TXT answer journey through the real shared validator.
// Optional: PLAYWRIGHT_MODULE, PLAYWRIGHT_CHANNEL, FAMILY_TEST_PYTHON,
// HOMEWORK_TEXT_PROOF_DIR. Output paths come only from the caller; no real printer/model/data.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const net=require('node:net'),{setTimeout:delay}=require('node:timers/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
// The served bundle keeps app helpers private, so build the same question markup from the exact app.js source in an isolated VM and let the real page lay it out.
const appSource=require('node:fs').readFileSync(require('node:path').join(__dirname,'app.js'),'utf8'),vm=require('node:vm');
const appFunction=name=>{const m=new RegExp('^function '+name+'\\(.*\\n(?:.*\\n)*?\\}$','m').exec(appSource);assert(m,'app.js defines '+name);return m[0]};
const reviewQuestionHTML=vm.runInNewContext(appFunction('homeworkReviewReferenceHTML')+'\n'+appFunction('homeworkReviewQuestionHTML')+'\nhomeworkReviewQuestionHTML',{esc:vm.runInNewContext(/(?:^|[\s,;])esc=(s=>.*?\}\[c\]\)\))/m.exec(appSource)[1])});
// Root's held-out red case and its controls run against the exact app.js scope helper; the exact c62 helper is kept only to show the red case catches it.
const scopeText=vm.runInNewContext(appFunction('homeworkReviewScopeText')+'\nhomeworkReviewScopeText');
const c62ScopeText=vm.runInNewContext(String.raw`function homeworkReviewScopeText(coverage,comparison){
 const scope=typeof coverage==='string'?coverage.replace(/^本次(?=\d)/,'').replace(/。；/g,'；').replace(/》：本次读取/g,'》：读取'):'模型未说明题号范围，请补充后复核。';
 return {coverage:'本次检查范围：'+scope+'\n仅本次所选资料，未判定和未检查部分不算已完成。',comparison:comparison?'本次复核：'+comparison.replace(/^本次(?=\d)|^本次复核(?=以)/,''):''};
}`+'\nhomeworkReviewScopeText');
function scopeCases(scopeText,c62ScopeText,assert){
 const tail='\n仅本次所选资料，未判定和未检查部分不算已完成。',red='本次2题，1题仍未判定。实际读取范围：《虚构参考。；第1卷.txt》：本次读取完整文字。；教师参考未核明。',redComparison='本次1题未判定，请保留原件。';
 assert.match(c62ScopeText(red,redComparison).coverage,/《虚构参考；第1卷\.txt》/,'the exact c62 helper rewrote a legal source name');
 for(const text of [undefined,'']){const v=scopeText(red,redComparison,text);assert.equal(v.coverage,'本次检查范围：2题，1题仍未判定。实际读取范围：《虚构参考。；第1卷.txt》：本次读取完整文字。；教师参考未核明。'+tail,'unproven structure stays verbatim');assert.equal(v.comparison,'本次复核：本次1题未判定，请保留原件。','an unknown comparison keeps its own wording')}
 const odd='《教师参考》第2卷》：本次读取完整文字。；教师参考《乙.txt',entries=['题目/孩子作答《虚构答卷.docx》：本次读取完整文字。','教师参考《虚构参考。；第1卷.txt》：本次读取完整文字。','教师参考《'+odd+'》：本次读取完整文字。','上一轮待复核意见《作业批改参考-7.txt》：本次读取最新检查；较早草稿保留在原件，未作为本次复核输入。','题目/孩子作答《虚构卷.pdf》：共11页，本次第1-7页；未读取页：8-11。','教师参考《虚构照片.jpg》：本次读取整张照片。'];
 const block=list=>'虚构第1题：未判定。\n\n实际读取范围（程序核对）：\n'+list.join('\n')+'\n仅核对本次所选材料；未读取页及无法对应的题目保持未判定。\n\n本次复核比较（待家长核对）：\n虚构比较。',head='本次3题，1题仍未判定。未列入本次逐题结果的题目和资料范围仍未检查；模型原覆盖说明尚未核明。',raw=head+'\n实际读取范围：'+entries.join('；');
 const tidy=scopeText(raw,'本次1题未判定，不能沿用上一轮对这些题的确定判定。其他题目以本次逐题结果为准；教师参考和孩子作答分别保留，旧AI意见不作答案依据。',block(entries));
 assert.equal(tidy.coverage,'本次检查范围：3题，1题仍未判定。未列入本次逐题结果的题目和资料范围仍未检查；模型原覆盖说明尚未核明。\n实际读取范围：题目/孩子作答《虚构答卷.docx》：读取完整文字；教师参考《虚构参考。；第1卷.txt》：读取完整文字；教师参考《'+odd+'》：读取完整文字；上一轮待复核意见《作业批改参考-7.txt》：读取最新检查；较早草稿保留在原件，未作为本次复核输入；题目/孩子作答《虚构卷.pdf》：共11页，本次第1-7页；未读取页：8-11；教师参考《虚构照片.jpg》：读取整张照片。'+tail,'proven generator joins are tidied while every name stays verbatim');
 assert.equal(tidy.comparison,'本次复核：1题未判定，不能沿用上一轮对这些题的确定判定。其他题目以本次逐题结果为准；教师参考和孩子作答分别保留，旧AI意见不作答案依据。');
 assert.equal(scopeText('本次2题，0题仍未判定。','本次复核以逐题结果为准；未列题目仍未检查，旧AI意见不作答案依据。').comparison,'本次复核：以逐题结果为准；未列题目仍未检查，旧AI意见不作答案依据。');
 const quoted='仅核对“字面。；符号”所在一页；作文未提供。',pair=entries.slice(0,2),q=scopeText(quoted+'\n实际读取范围：'+pair.join('；'),'后补参考“字面。；符号”后仍未判定。',block(pair));
 assert.equal(q.coverage,'本次检查范围：'+quoted+'\n实际读取范围：题目/孩子作答《虚构答卷.docx》：读取完整文字；教师参考《虚构参考。；第1卷.txt》：读取完整文字。'+tail,'a quote elsewhere stays literal');assert.equal(q.comparison,'本次复核：后补参考“字面。；符号”后仍未判定。');
 const rawPair=head+'\n实际读取范围：'+pair.join('；');
 for(const text of [block(pair.slice().reverse()),block(pair).replace('仅核对本次所选材料；',''),block([pair[0]+'x',pair[1]])])assert.equal(scopeText(rawPair,'',text).coverage,'本次检查范围：'+rawPair.slice(2)+tail,'entries that draft.text does not prove stay verbatim');
 assert.match(c62ScopeText(raw,'').coverage,/《《教师参考》第2卷》：读取完整文字；教师参考《乙\.txt》/,'c62 also rewrote a name holding book-title brackets and a source word');
}
scopeCases(scopeText,c62ScopeText,assert);
// The stage line under the count, the note under the fill button and the right-hand save status, read together with the count.
const reviewStage=panel=>panel.evaluate(el=>{const result=el.querySelector('[data-homework-review-result]');return {stage:result.querySelector('.homework-review-stage')?.textContent??null,hint:result.querySelector('.homework-review-next>p')?.textContent??null,questions:!!result.querySelector('.homework-review-questions'),counts:result.querySelector('.homework-review-counts')?.textContent??null,status:document.querySelector('#taskFeedbackStatus').textContent}});
// After filling, the unsaved note and the original save button must both be whole, at least 12px clear (outside the button's focus ring), where a parent can see them: the viewport, the modal task dialog and every clipping ancestor inside it, above its sticky close bar.
const savePairView=page=>page.evaluate(()=>{const nodes=['#taskFeedbackStatus','#saveTaskFeedback'].map(s=>document.querySelector(s)),dialog=document.querySelector('#taskDialog'),box={top:0,left:0,bottom:innerHeight,right:innerWidth};
 for(let x=nodes[1].parentElement;x&&x!==dialog.parentElement;x=x.parentElement){const s=getComputedStyle(x);if(x===dialog||s.overflowX!=='visible'||s.overflowY!=='visible'){const r=x.getBoundingClientRect(),top=r.top+x.clientTop,left=r.left+x.clientLeft;box.top=Math.max(box.top,top);box.left=Math.max(box.left,left);box.bottom=Math.min(box.bottom,top+x.clientHeight);box.right=Math.min(box.right,left+x.clientWidth)}}
 const bar=dialog.querySelector(':scope>form>.actions');if(bar&&!bar.contains(nodes[1])&&getComputedStyle(bar).position==='sticky')box.bottom=Math.min(box.bottom,bar.getBoundingClientRect().top);
 const style=getComputedStyle(nodes[1]),ring=style.outlineStyle==='none'?0:parseFloat(style.outlineWidth)+Math.max(0,parseFloat(style.outlineOffset)||0),gap=12,rects=nodes.map((n,i)=>{const r=n.getBoundingClientRect(),e=i?ring:0;return {top:r.top-e,left:r.left-e,bottom:r.bottom+e,right:r.right+e}});
 return {box,rects,ring,gap,focus:document.activeElement?.id,modal:dialog.matches(':modal'),inside:dialog.matches(':modal')&&nodes.every(n=>dialog.contains(n))&&rects.every(r=>r.bottom>r.top&&r.top>=box.top+gap-.5&&r.left>=box.left+gap-.5&&r.bottom<=box.bottom-gap+.5&&r.right<=box.right-gap+.5)}});
// Every visible original print button sits in one right-hand column per list, level with its file name; long names wrap on the left.
const printColumn=page=>page.evaluate(()=>{const lists=[];return [...document.querySelectorAll('#taskDialog .upload-item')].filter(x=>x.querySelector(':scope>[data-print-upload]')&&x.getClientRects().length).map(x=>{const n=x.querySelector(':scope>.upload-name').getBoundingClientRect(),b=x.querySelector(':scope>[data-print-upload]').getBoundingClientRect();if(!lists.includes(x.parentElement))lists.push(x.parentElement);return {list:lists.indexOf(x.parentElement),name:x.querySelector('a').textContent,beside:b.top<n.bottom&&n.top<b.bottom&&n.right<=b.left,right:Math.round(b.right),w:b.width,h:b.height}})});
async function eventually(fn,label){for(let n=0;n<250;n++){if(await fn())return;await delay(40)}throw Error('Timed out: '+label)}
async function fit(page){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no page overflow');
 assert.equal(await page.locator('dialog[open]').evaluateAll(ds=>ds.some(d=>d.scrollWidth>d.clientWidth)),false,'no dialog overflow');
 assert.equal(await page.locator('iframe').count(),0,'no iframe');
}
async function proof(page,name){
 if(!process.env.HOMEWORK_TEXT_PROOF_DIR)return;
 const fs=require('node:fs/promises'),path=require('node:path');await fs.mkdir(process.env.HOMEWORK_TEXT_PROOF_DIR,{recursive:true});
 await page.screenshot({path:path.join(process.env.HOMEWORK_TEXT_PROOF_DIR,name+'.png'),fullPage:true});
}
const fixture=String.raw`
import runpy,sys,copy,json,tempfile,os,io,zipfile,base64
from xml.sax.saxutils import escape
bootstrap=tempfile.TemporaryDirectory(prefix='synthetic-text-bootstrap-');os.environ['FAMILY_DATA']=bootstrap.name
import app,family_media
validator=app.family_llm.homework_reference_draft;docx_reader=family_media.docx_text;calls=[];responses=[]
mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
paper='虚构文字卷\n第1题：2+3=?。孩子最终作答：5。\n第2题：6-2=?。孩子最终作答：3。\n第3题：9-1=?。孩子最终作答：未提供。'
teacher='TEACHER_ONLY_CANARY：虚构文字卷第1题：5；第2题：4；第3题：8。'
png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC')
def docx(kind):
 body=''.join('<w:p><w:r><w:t>'+escape(line)+'</w:t></w:r></w:p>' for line in paper.splitlines())
 extras={}
 if kind=='picture':body+='<w:p><w:r><w:drawing/></w:r></w:p>';extras['word/media/picture.png']=png
 if kind=='object':body+='<w:p><w:r><w:object/></w:r></w:p>';extras['word/embeddings/object.bin']=b'SYNTHETIC_OBJECT_NEVER_EXECUTED'
 if kind=='formula':body+='<w:p><m:oMath><m:r><m:t>x+1</m:t></m:r></m:oMath></w:p>'
 assert kind in ('safe','picture','object','formula')
 parts={'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="'+mime+'.main+xml"/></Types>',
        '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml':'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>'+body+'</w:body></w:document>',**extras}
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
  for name,data in parts.items():
   info=zipfile.ZipInfo(name,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,data)
 return output.getvalue()
def question(label,judgment,text,student,answer,uncertainty=''):
 return dict(label=label,judgment=judgment,question=text,student_answer=student,answer='教师参考：'+answer,question_kind='objective',
             error_reason='孩子作答3与教师参考4不同。' if judgment=='incorrect' else '',possible_cause='',steps='',uncertainty=uncertainty)
raw_template=dict(items=[question('虚构文字卷第1题','correct','2+3=?','5','5'),question('虚构文字卷第2题','incorrect','6-2=?','3','4'),
                         question('虚构文字卷第3题','unknown','9-1=?','','8','原作答未提供，不能把教师参考8当成孩子作答。')],
                  coverage='仅本次虚构文字卷三题；第3题未提供作答，保持未判定。')
def model(messages,schema,name,timeout,**kwargs):
 assert app.DATA.name.startswith('family-demo-') and name=='family_homework_reference'
 assert app.family_llm.homework_reference_draft is validator and family_media.docx_text is docx_reader
 content=messages[-1]['content'];assert not any(p.get('type')=='image_url' for p in content),'text-only review must use zero images'
 texts=[p['text'] for p in content if p.get('type')=='text']
 questions=[text for text in texts if text.startswith('题目/孩子作答原文')]
 references=[text for text in texts if text.startswith('教师参考原文')]
 assert len(calls)<5
 phase=('transport_error','valid_word','valid_txt','missing_teacher','ai_derived')[len(calls)]
 supplied_teacher=phase not in ('missing_teacher','ai_derived')
 assert len(questions)==1 and len(references)==int(supplied_teacher)
 question_documents=json.loads(questions[0][questions[0].index('['):]);reference_documents=json.loads(references[0][references[0].index('['):]) if references else []
 assert len(question_documents)==1 and set(question_documents[0])=={'name','text'} and question_documents[0]['text']==paper
 if supplied_teacher:
  assert len(reference_documents)==1 and set(reference_documents[0])=={'name','text'} and reference_documents[0]['text']==teacher
  assert questions[0]!=references[0] and 'TEACHER_ONLY_CANARY' in references[0] and '孩子最终作答' not in references[0]
 else:
  prior=[text for text in texts if text.startswith('上一轮待复核意见原文（不是教师参考，不作答案依据）')]
  assert len(prior)==1 and '教师参考：' in prior[0],'old teacher claims remain previous opinions, never teacher input'
 assert '第1题：2+3=?' in questions[0] and '孩子最终作答：3' in questions[0] and '第3题：9-1=?' in questions[0]
 assert 'TEACHER_ONLY_CANARY' not in questions[0] and 'PARENT_NOTE_ONLY_CANARY' not in questions[0]
 assert any('原作答家长说明' in text and 'PARENT_NOTE_ONLY_CANARY' in text for text in texts)
 assert ('.txt' if phase in ('valid_txt','missing_teacher','ai_derived') else '.docx') in questions[0]
 raw=None if phase=='transport_error' else copy.deepcopy(raw_template)
 if phase=='ai_derived':
  for item in raw['items']:item['answer']=item['answer'].replace('教师参考：','AI自行推导：')
  raw['items'][1]['error_reason']='孩子作答3与核对答案4不同。'
  raw['items'][2]['uncertainty']='原作答未提供，不能推测孩子作答。'
 calls.append(dict(phase=phase,question_documents=question_documents,reference_documents=reference_documents,question_documents_segment=questions[0],teacher_segment=references[0] if references else '',image_count=0,raw=raw,original=copy.deepcopy(raw)))
 if phase=='transport_error':raise app.family_llm.LLMDraftError('虚构模型传输失败；本次未返回检查结果')
 return raw
app.family_llm._chat_json=model
reply=app.Handler.reply
def observe_reply(self,code,body,*args,**kwargs):
 if self.path=='/api/print/homework/draft':responses.append(dict(status=code,body=copy.deepcopy(body)))
 return reply(self,code,body,*args,**kwargs)
app.Handler.reply=observe_reply
get=app.Handler.do_GET
def fixture_get(self):
 if self.path.startswith('/__fixture/word/'):
  kind=self.path.rsplit('/',1)[1]
  if kind not in ('safe','picture','object','formula'):return self.reply(404,dict(error='Unknown synthetic document'))
  return self.reply(200,docx(kind),mime)
 if self.path!='/__fixture/text':return get(self)
 assert app.DATA.name.startswith('family-demo-') and app.family_llm.homework_reference_draft is validator and family_media.docx_text is docx_reader
 assert all(call['raw']==call['original'] for call in calls),'raw model replies must remain unchanged'
 with app.connect_read_only() as c:
  tables={}
  for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
   name=row['name'];rows=[{k:(v.hex() if isinstance(v,bytes) else v) for k,v in dict(r).items()} for r in c.execute('SELECT * FROM "'+name.replace('"','""')+'"')]
   tables[name]=sorted(rows,key=lambda r:json.dumps(r,sort_keys=True))
 return self.reply(200,dict(synthetic_only=True,shared_validator=True,shared_docx_guard=True,real_model_calls=0,raw_unchanged=True,calls=calls,responses=responses,tables=tables,paper=paper,teacher=teacher))
app.Handler.do_GET=fixture_get;sys.argv=['demo.py','--port',sys.argv[1]]
try:runpy.run_path('demo.py',run_name='__main__')
finally:bootstrap.cleanup()
`;
async function startServer(){
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
 const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('FAMILY_'))delete env[key];
 const proc=spawn(process.env.FAMILY_TEST_PYTHON||'python3',['-c',fixture,String(port)],{cwd:__dirname,env,stdio:['ignore','ignore','pipe']});
 let error,stderr='';proc.on('error',e=>error=e);proc.stderr.on('data',s=>stderr=(stderr+s).slice(-12000));
 const stop=async()=>{if(error||proc.exitCode!==null||proc.signalCode!==null)return;const done=once(proc,'exit');proc.kill('SIGINT');await Promise.race([done,delay(2500)]);if(proc.exitCode===null&&proc.signalCode===null){proc.kill('SIGKILL');await Promise.race([done,delay(2500)])}};
 const url='http://127.0.0.1:'+port+'/';
 try{await eventually(async()=>{if(error)throw error;if(proc.exitCode!==null)throw Error('Demo exited: '+stderr);try{return(await fetch(url,{signal:AbortSignal.timeout(400)})).ok}catch{return false}},'isolated demo startup');return {url,stop}}
 catch(e){await stop();throw e}
}
(async()=>{
 let browser,server,page;const results=[];
 try{
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  for(const width of [360,1440]){
   server=await startServer();const read=async path=>{const r=await fetch(server.url+path);assert.equal(r.status,200);return r.json()},state=()=>read('api/state'),audit=()=>read('__fixture/text');
   const errors=[],foreign=[],forbidden=[],posts=[],bodies=[],replies=[];
   page=await browser.newPage({viewport:{width,height:850}});page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
   await page.route('**/*',async route=>{const r=route.request(),url=new URL(r.url());if(url.origin!==new URL(server.url).origin){foreign.push(r.url());return route.abort()}if(r.method()==='POST'&&url.pathname.startsWith('/api/print/')&&url.pathname!=='/api/print/homework/draft'){forbidden.push(url.pathname);return route.abort()}await route.continue()});
   await page.route('**/api/print/homework/draft',async route=>{bodies.push(route.request().postDataJSON());const response=await route.fetch();replies.push({status:response.status(),body:await response.json()});await route.fulfill({response})});
   await page.goto(server.url,{waitUntil:'load'});await page.locator('[data-homework-new]').first().waitFor();await page.locator('[data-homework-new]').first().click();
   const title='虚构纯文字试卷 '+width,entry=page.locator('#homeworkInputDialog'),item=entry.locator('[data-homework-item="0"]');
   await item.locator('[name=title]').fill(title);await item.locator('[name=goal]').fill('按本卷已保存的完整题干、实际作答和独立老师参考核对。');await item.locator('[type=submit]').click();await entry.locator('.homework-saved').waitFor();await entry.locator('[data-homework-close]').click();
   let value=await state();const task=value.tasks.find(t=>t.title===title);assert(task);const child=task.child;
   await page.locator('[data-task="'+task.id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();
   const content=await audit(),wordName='synthetic-answer-'+width+'.docx',txtName='synthetic-question-'+width+'.txt',teacherName='synthetic-teacher-'+width+'.txt';
   const upload=async(name,mime,buffer)=>{await page.locator('#fileInput').setInputFiles({name,mimeType:mime,buffer});await page.locator('#pendingUploads').getByRole('link',{name,exact:true}).waitFor()};
   const wordBytes=async kind=>{const response=await fetch(server.url+'__fixture/word/'+kind);assert.equal(response.status,200);return Buffer.from(await response.arrayBuffer())};
   await page.locator('#taskForm [name=note]').fill('PARENT_NOTE_ONLY_CANARY：仅说明这是虚构文字卷；作答证据请看原Word/TXT，不凭这句判断答案。');
   await upload(wordName,DOCX,await wordBytes('safe'));await upload(txtName,'text/plain',Buffer.from(content.paper));await upload(teacherName,'text/plain',Buffer.from(content.teacher));
   for(const kind of ['picture','object','formula'])await upload('synthetic-'+kind+'.docx',DOCX,await wordBytes(kind));
   await page.locator('#saveTaskFeedback').click();await eventually(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'Word/TXT-only original answer saved');
   value=await state();const original=value.records.find(r=>r.source==='事项:'+task.id),before=value;assert.equal(original.attachments.length,6);
   const source=name=>value.uploads.find(a=>a.name===name),word=source(wordName),txt=source(txtName),teacher=source(teacherName),unsafe=['picture','object','formula'].map(k=>source('synthetic-'+k+'.docx'));assert(word&&txt&&teacher&&unsafe.every(Boolean));
   assert(original.attachments.every(id=>!value.uploads.find(a=>a.id===id).mime.startsWith('image/')),'the entry must not depend on a temporary photo');
   let panel=page.locator('[data-homework-review="'+original.id+'"]');await panel.waitFor();assert.equal(await page.locator('[data-homework-review]').count(),1,'pure electronic originals expose the real check entry');
   const open=async()=>{if(!await panel.locator(':scope > details').evaluate(e=>e.open))await panel.locator(':scope > details > summary').click()};await open();
   const choose=async(file,checked,role)=>{const row=panel.locator('[data-review-source="'+file.id+'"]');await row.waitFor();if(role){const details=row.locator('.homework-material-options');if(!await details.evaluate(e=>e.open))await details.locator(':scope > summary').click();await row.locator('[data-homework-review-role]').selectOption(role);await details.locator(':scope > summary').click()}await row.locator('[data-homework-review-photo]')[checked?'check':'uncheck']()};
   await choose(word,true,'question');await choose(teacher,true,'reference');const baseline=await audit();let run=panel.locator('[data-homework-review-run]');
   for(let n=0;n<unsafe.length;n++){
    await choose(word,false);await choose(unsafe[n],true,'question');await run.click();await eventually(async()=>replies.length===n+1&&await run.isEnabled()&&/读取|完整|图片|公式|嵌入|Word|DOCX/.test(await panel.locator('[data-homework-review-status]').innerText()),'unsafe Word rejected '+n);
    assert.equal(replies[n].status,400);assert.equal(replies[n].body.draft,undefined);assert.deepEqual(bodies[n].question_sources,[{type:'upload',id:unsafe[n].id}]);assert.deepEqual(bodies[n].reference_sources,[{type:'upload',id:teacher.id}]);
    assert.equal(await panel.locator('[data-review-source="'+unsafe[n].id+'"] [data-homework-review-photo]').isChecked(),true);assert.equal(await panel.locator('[data-review-source="'+teacher.id+'"] [data-homework-review-photo]').isChecked(),true);
    assert.equal(await panel.locator('.homework-question,[data-homework-review-result] textarea').count(),0);const evidence=await audit();assert.equal(evidence.calls.length,0);assert.deepEqual(evidence.tables,baseline.tables,'unsafe parse fails before model or any SQLite write');
    assert.deepEqual((await state()).records,before.records);await fit(page);await proof(page,'unsafe-'+['picture','object','formula'][n]+'-'+width);await choose(unsafe[n],false);await choose(word,true,'question');
   }
   await run.click();await eventually(async()=>replies.length===4&&/虚构模型传输失败/.test(await panel.locator('[data-homework-review-status]').innerText())&&await run.isEnabled(),'real transport failure');assert.equal(replies[3].status,503);
   assert.equal(await panel.locator('.homework-question,[data-homework-review-result] textarea').count(),0);assert.equal(await panel.locator('[data-review-source="'+word.id+'"] [data-homework-review-photo]').isChecked(),true);assert.equal(await panel.locator('[data-review-source="'+teacher.id+'"] [data-homework-review-role]').inputValue(),'reference');
   assert.equal((await audit()).calls.length,1);assert.deepEqual((await audit()).tables,baseline.tables);await proof(page,'transport-failure-'+width);
   await run.click();await panel.locator('.homework-question').first().waitFor();assert.equal(replies.length,5);assert.equal(replies[4].status,200);assert.deepEqual(bodies[4],bodies[3]);
   assert.deepEqual(bodies[4].question_sources,[{type:'upload',id:word.id}]);assert.deepEqual(bodies[4].reference_sources,[{type:'upload',id:teacher.id}]);assert.deepEqual(bodies[4].previous_sources,[]);assert.equal(bodies[4].record_id,original.id);
   const draft=replies[4].body.draft;assert.equal(draft.items,3);assert.equal(draft.wrong_items,1);assert.equal(draft.unknown_items,1);assert.deepEqual(draft.questions.map(q=>[q.label,q.judgment,q.student_answer]),[['虚构文字卷第1题','correct','5'],['虚构文字卷第2题','incorrect','3'],['虚构文字卷第3题','unknown','']]);
   assert.deepEqual(await panel.locator('.homework-question h4').allTextContents(),['虚构文字卷第1题 · 与答案一致','虚构文字卷第2题 · 需要订正','虚构文字卷第3题 · 未判定']);assert.match(await panel.locator('.homework-review-counts').innerText(),/3题 · 1题需订正 · 1题未判定/);
   assert.equal(await panel.locator('[data-homework-review-status]').innerText(),'','the count is shown once, not repeated in the status line');assert.match(await panel.locator('[data-homework-review-result] .homework-review-stage').innerText(),/检查意见待核对，尚未保存/);assert.doesNotMatch(await page.locator('#taskFeedbackStatus').innerText(),/^反馈已保存/,'an earlier saved feedback never speaks for the new draft');
   const rows=await panel.locator('[data-homework-review-result] .homework-question').allInnerTexts();assert.equal(rows.length,3);for(const row of rows)assert.match(row,/孩子作答：/);assert.match(rows[2],/孩子作答：未能辨认/,'an unknown answer stays unknown');
   const longReference='教师参考：'+'6个零件。应写出2×3=6，并说明2表示每轮处理的零件数、3表示已经完成的轮数。'.repeat(4)+'\n不能只写一个数字；结果单位是“个零件”。';
   const referenceMarkup={quiet:reviewQuestionHTML({label:'虚构长参考题',judgment:'unknown',student_answer:'6',answer:longReference}),reasoned:reviewQuestionHTML({label:'虚构长参考题',judgment:'unknown',student_answer:'6',answer:longReference,uncertainty:'虚构待核原因'}),short:[reviewQuestionHTML({judgment:'correct',student_answer:'5',answer:'教师参考：5'}),reviewQuestionHTML({judgment:'correct',student_answer:'5',answer:'AI自行推导：5'}),reviewQuestionHTML({judgment:'unknown',student_answer:'',answer:'5'})]};
   const shapes=await panel.evaluate((el,markup)=>{const box=document.createElement('div');box.className='homework-review-questions';el.querySelector('[data-homework-review-result]').append(box);const html=x=>{box.innerHTML=x;return box.firstElementChild};
    const quiet=html(markup.quiet),d=quiet.querySelector('details.homework-reference'),p=d?.querySelector('.homework-reference-text'),style=p&&getComputedStyle(p);
    const out={open:d?.open,summary:d?.querySelector('summary').textContent,full:p?.textContent,clipped:!p||p.scrollHeight>p.clientHeight+1||style.webkitLineClamp!=='none'||style.textOverflow==='ellipsis'||style.maxHeight!=='none'};
    out.reasoned=html(markup.reasoned).querySelector('details.homework-reference').open;
    out.texts=markup.short.map(x=>html(x).querySelector('.homework-reference').textContent);box.remove();return out},referenceMarkup);
   assert.deepEqual(shapes,{open:true,summary:'完整教师参考 · '+[...longReference.slice(5)].length+'字',full:longReference.slice(5),clipped:false,reasoned:false,texts:['教师参考：5','AI自行推导：5','参考内容：5']},'long references open in place verbatim when no reason is shown; short ones keep one source label');for(const t of await panel.locator('[data-homework-review-result] .homework-reference').allInnerTexts())assert.doesNotMatch(t,/参考答案：|^[^：\n]*：(教师参考|AI自行推导)：/,'one source label per reference');
   const text=await panel.locator('[data-homework-review-result] textarea').inputValue();assert.equal(text,draft.text);assert.match(text,/与参考一致1题/);assert.equal(await panel.locator('[data-homework-review-confirm]').isChecked(),false);assert.deepEqual((await audit()).tables,baseline.tables,'valid text-only draft changes no row');await fit(page);await proof(page,'word-three-judgments-'+width);
   await panel.locator('[data-homework-review-confirm]').check();await panel.locator('[data-homework-review-apply]').click();await eventually(async()=>/已填入反馈，尚未保存/.test(await panel.locator('[data-homework-review-status]').innerText()),'parent adopts Word result explicitly');assert.deepEqual((await state()).records,before.records);
   assert.match(await page.locator('#taskFeedbackStatus').innerText(),/检查意见已填入，尚未保存/);assert.equal(await page.evaluate(()=>document.activeElement?.id),'saveTaskFeedback','focus moves to the one original save button');{const v=await reviewStage(panel);assert.deepEqual(v,{stage:'检查意见已填入，尚未保存',hint:'检查意见已填入，尚未保存；请保存这次反馈。',questions:true,counts:v.counts,status:'检查意见已填入，尚未保存；请保存这次反馈。'},'after a real fill the stage line, the next-step note and the save status all say filled and not saved');assert.match(v.counts,/3题 · 1题需订正 · 1题未判定/,'filling leaves the count and the unknown question unknown')}assert.deepEqual(await panel.locator('.homework-question h4').allTextContents(),['虚构文字卷第1题 · 与答案一致','虚构文字卷第2题 · 需要订正','虚构文字卷第3题 · 未判定'],'filling never turns a judgment into done or known');{const view=await savePairView(page);assert(view.inside,'the unsaved note and the original save button are whole and at least 12px inside the viewport, the task dialog and its clipping ancestors, above a sticky close bar: '+JSON.stringify(view))}
   {const c=panel.locator('[data-homework-review-result] > [data-homework-review-coverage]'),raw=await c.getAttribute('data-homework-review-coverage'),text=await c.innerText(),draft=await panel.locator('[data-homework-review-result] > details textarea').inputValue();assert.equal(text,scopeText(raw,undefined,draft).coverage);assert.doesNotMatch(text,/。；|本次检查范围：本次/,'joins between the plain synthetic names are proven by draft.text and tidied');for(const name of [wordName,teacherName])assert(raw.includes('《'+name+'》')&&text.includes('《'+name+'》'),'scope keeps the source name '+name);for(const fact of ['仍未判定','仍未检查','尚未核明'])if(raw.includes(fact))assert(text.includes(fact),'scope keeps '+fact)}
   {const rows=await printColumn(page);assert(rows.length,'print rows are visible');for(const r of rows){assert(r.beside,'print stays level with its file name: '+r.name);assert(r.h>=44&&r.w>=44,'print keeps its 44px target')}for(const list of new Set(rows.map(r=>r.list)))assert.equal(new Set(rows.filter(r=>r.list===list).map(r=>r.right)).size,1,'one print column per list');await fit(page)}
   const saveBefore=await audit(),saveBodies=[],saveReplies=[];await page.route('**/api/task/feedback',async route=>{saveBodies.push(route.request().postDataJSON());if(saveBodies.length===1)return route.fulfill({status:503,json:{error:'虚构反馈零写入503'}});const response=await route.fetch();assert.equal(response.status(),200);saveReplies.push(await response.json());return saveBodies.length===2?route.fulfill({status:503,json:{error:'虚构反馈已写入但回执丢失'}}):route.fulfill({response})});
   const save=page.locator('#saveTaskFeedback');await save.click();await eventually(async()=>/虚构反馈零写入503/.test(await page.locator('#taskError').innerText()),'no-write feedback failure');assert.deepEqual((await audit()).tables,saveBefore.tables);
   await save.click();await eventually(async()=>/虚构反馈已写入但回执丢失/.test(await page.locator('#taskError').innerText()),'lost receipt after real save');assert.equal((await state()).records.length,before.records.length+1);
   await save.click();await eventually(async()=>/反馈已保存/.test(await page.locator('#taskFeedbackStatus').innerText()),'same numbered feedback retry');await page.unroute('**/api/task/feedback');assert.deepEqual(saveBodies[1],saveBodies[0]);assert.deepEqual(saveBodies[2],saveBodies[0]);assert.ok(saveBodies[0].request_key);assert.equal(saveReplies[1].replayed,true);assert.equal(saveReplies[1].record_id,saveReplies[0].record_id);
   value=await state();const saved=value.records.find(r=>r.id===saveReplies[1].record_id);assert.equal(saved.related_record_id,original.id);assert.equal(saved.followup_kind,'作业检查');assert.equal(saved.child,child);assert.equal(saved.source,'事项:'+task.id);assert.deepEqual(saved.attachments.filter(id=>id===word.id||id===teacher.id).sort(),[word.id,teacher.id].sort());
   assert.deepEqual(value.records.find(r=>r.id===original.id),original);assert.deepEqual(value.tasks,before.tasks);assert.equal(value.records.filter(r=>r.source==='错题照片核对'&&r.linked_task_id===task.id).length,0);assert.equal(value.records.filter(r=>r.source==='事项:'+task.id).length,2);for(const file of [word,txt,teacher,...unsafe])assert.deepEqual(value.uploads.find(a=>a.id===file.id),file);
   const savedTables=(await audit()).tables;await page.locator('#taskDialog [data-close=taskDialog]').click();await page.reload({waitUntil:'load'});await page.locator('[data-task="'+task.id+'"]').first().click();await page.locator('#taskDialog[open]').waitFor();
   const savedText=page.locator('[data-saved-homework-review="'+saved.id+'"] [data-saved-review-text]');await eventually(async()=>await savedText.textContent()===text,'saved text reopens exactly');assert.equal(await page.locator('#taskForm [name=id]').inputValue(),task.id);assert.equal(await page.locator('#taskForm [name=status]').inputValue(),'待跟进');
   {const look=()=>savedText.evaluate(el=>({visible:(c=>{c.querySelectorAll('.saved-review-redundant').forEach(x=>x.remove());return c.textContent})(el.cloneNode(true)),hidden:[...el.querySelectorAll('.saved-review-redundant')].map(x=>{const r=x.getBoundingClientRect();return [x.textContent,r.width,r.height]}),questions:[...el.querySelectorAll('.saved-review-question')].map(x=>x.textContent),judgments:[...el.querySelectorAll('.saved-review-judgment')].map(x=>[x.textContent,x.dataset.judgment]),fits:el.scrollHeight<=el.clientHeight+1}));
    const view=await look();assert.equal(await savedText.innerText(),text,'every saved character stays in the reopened check for copy, find and screen readers');
    assert.deepEqual(view.questions,['虚构文字卷第1题','虚构文字卷第2题','虚构文字卷第3题']);assert.deepEqual(view.judgments,[[' · 与参考一致','correct'],[' · 需订正','incorrect'],[' · 未判定','unknown']],'the saved judgment words are shown, not re-graded');
    assert.deepEqual(view.hidden,[['参考答案：',0,0],['参考答案：',0,0],['\n订正建议：',0,0],['参考答案：',0,0]],'only the generic label before a teacher source and the empty correction label are kept but not shown');
    assert.equal(view.visible,text.replaceAll('\n参考答案：教师参考：','\n教师参考：').replace(/\n订正建议：(?=\n)/,''));assert.match(view.visible,/\n教师参考：4\n错误依据：孩子作答3与教师参考4不同。\n\n虚构文字卷第3题 · 未判定\n/);assert.match(view.visible,/\n卷面作答：未能确认\n/,'the unknown answer stays unknown');assert.ok(view.fits,'the saved check flows in the dialog, no hidden inner scroll');
    const sizes=await page.locator('#taskFeedbackHistory .upload-item .upload-name .muted').allTextContents();assert(sizes.length,'saved originals show a size');for(const s of sizes)assert.match(s,/^(?:\d+ B|\d+(?:\.\d)? KB|\d+\.\d\d MB)$/);assert(!sizes.includes('0.00 MB'),'small originals no longer read 0.00 MB');
    await savedText.evaluate(el=>{const panel=el.closest('[data-saved-homework-review]');delete panel.dataset.loaded;panel.querySelector('button').click()});await eventually(async()=>await savedText.evaluate(el=>el.closest('[data-saved-homework-review]').dataset.loaded==='true'),'second read of the same saved check');assert.equal(await savedText.textContent(),text);assert.deepEqual(await look(),view,'a second read replaces the view, never stacks it');
    const appSource=require('fs').readFileSync(require('path').join(__dirname,'app.js'),'utf8'),partsOf=new Function(appSource.slice(appSource.indexOf('function savedHomeworkReviewParts(text){'),appSource.indexOf('\nasync function loadSavedHomeworkReview'))+';return savedHomeworkReviewParts')(),odd=['第1题 · 需订正\n题面：1+1=?\n卷面作答：3\n参考答案：教师参考：2\n错误依据：与教师参考2不同。\n订正建议：\n家长补充：明天再做一遍','《虚构参考。；第1卷.txt》 · 第3题 · 未判定\n题面：未提供，题目要求未核\n卷面作答：未能确认\n参考答案：AI自行推导：12\n不确定：作答未能辨认，未判定'].map(t=>partsOf(t).map(x=>[x.kind,x.text]));
    assert.deepEqual(odd[0],[['','第1题 · 需订正\n题面：1+1=?\n卷面作答：3\n参考答案：教师参考：2\n错误依据：与教师参考2不同。\n订正建议：\n家长补充：明天再做一遍']],'a parent-edited block is not proven and stays verbatim');
    assert.deepEqual(odd[1],[['question','《虚构参考。；第1卷.txt》 · 第3题'],['judgment',' · 未判定'],['','\n'],['field','题面：'],['','未提供，题目要求未核'],['','\n'],['field','卷面作答：'],['','未能确认'],['','\n'],['redundant','参考答案：'],['field','AI自行推导：'],['','12'],['','\n'],['field','不确定：'],['','作答未能辨认，未判定']],'a punctuated label stays whole and the unknown stays unknown')}
   assert.deepEqual((await state()).records,value.records);assert.deepEqual((await state()).uploads,value.uploads);assert.deepEqual((await audit()).tables,savedTables,'reopening writes no row');await fit(page);await proof(page,'word-check-reopened-'+width);
   panel=page.locator('[data-homework-review="'+original.id+'"]');await panel.waitFor();await open();run=panel.locator('[data-homework-review-run]');const reportId=saved.attachments.find(id=>id!==word.id&&id!==teacher.id);assert(reportId);
   const previous=panel.locator('[data-review-source="'+reportId+'"]');await previous.waitFor();assert.deepEqual(await previous.locator('[data-homework-review-role] option').evaluateAll(xs=>xs.map(x=>x.value)),['previous'],'known AI report has no question/reference option');assert.equal(await previous.locator('[data-homework-review-role]').inputValue(),'previous');
   const guardResponses=[];for(const role of ['question','reference']){
    const body={...bodies[4],question_sources:[{type:'upload',id:role==='question'?reportId:word.id}],reference_sources:[{type:'upload',id:role==='reference'?reportId:teacher.id}],previous_sources:[]};
    const response=await fetch(server.url+'api/print/homework/draft',{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':value.token},body:JSON.stringify(body)});const payload=await response.json();guardResponses.push({status:response.status,body:payload});assert.equal(response.status,403);assert.match(payload.error,/上一轮|先前|检查意见|教师参考|作答/);assert.equal((await audit()).calls.length,2);assert.deepEqual((await audit()).tables,savedTables,'reclassifying known AI text is rejected before model/write');
   }
   await choose(txt,true,'question');await choose(teacher,true,'reference');await choose(word,false);await run.click();await panel.locator('.homework-question').first().waitFor();assert.equal(replies.length,6);assert.equal(replies[5].status,200);assert.deepEqual(bodies[5].question_sources,[{type:'upload',id:txt.id}]);assert.deepEqual(bodies[5].reference_sources,[{type:'upload',id:teacher.id}]);assert.deepEqual(bodies[5].previous_sources,[]);assert.deepEqual(replies[5].body.draft.questions,draft.questions);
   assert.equal(await savedText.textContent(),text);assert.deepEqual((await state()).records,value.records);assert.deepEqual((await state()).tasks,before.tasks);assert.deepEqual((await audit()).tables,savedTables,'TXT-only retry also remains read-only');await fit(page);await proof(page,'txt-only-check-'+width);
   let recheckConfirmations=0;page.on('dialog',async dialog=>{assert.equal(dialog.type(),'confirm');assert.match(dialog.message(),/再次检查会保留当前结果/);recheckConfirmations++;await dialog.accept()});
   await choose(teacher,false);await choose({id:reportId},true,'previous');await run.click();await eventually(async()=>replies.length===7&&replies[6].status===503&&await run.isEnabled()&&/未提供.*教师参考/.test(await panel.locator('[data-homework-review-status]').innerText()),'text teacher claim refused without original');
   assert.equal(replies[6].body.draft,undefined);assert.deepEqual(bodies[6].question_sources,[{type:'upload',id:txt.id}]);assert.deepEqual(bodies[6].reference_sources,[]);assert.deepEqual(bodies[6].previous_sources,[{type:'upload',id:reportId}]);assert.equal(await panel.locator('[data-homework-review-result] textarea').inputValue(),replies[5].body.draft.text,'failed source claim keeps prior draft');assert.equal(await savedText.textContent(),text);assert.deepEqual((await audit()).tables,savedTables,'false teacher claim writes no row');await fit(page);await proof(page,'text-teacher-claim-rejected-'+width);
   await run.click();await eventually(async()=>replies.length===8&&replies[7].status===200&&await run.isEnabled(),'retry accepts independent AI derivation');assert.deepEqual(bodies[7],bodies[6]);const derived=replies[7].body.draft;assert.equal(derived.wrong_items,1);assert.equal(derived.unknown_items,1);assert(derived.questions.every(q=>q.answer.startsWith('AI自行推导：')));assert.equal(await panel.locator('[data-homework-review-result] textarea').inputValue(),derived.text);assert.equal(await panel.locator('[data-homework-review-result] [data-homework-review-confirm]').isChecked(),false);assert.equal(await savedText.textContent(),text);
   assert.equal(recheckConfirmations,2);const final=await audit();assert.deepEqual(final.tables,savedTables,'successful AI retry remains a read-only draft');assert.deepEqual(final.calls.map(c=>c.phase),['transport_error','valid_word','valid_txt','missing_teacher','ai_derived']);assert(final.calls.every(c=>c.image_count===0));assert.equal(final.raw_unchanged,true);assert.equal(final.shared_validator,true);assert.equal(final.shared_docx_guard,true);assert.equal(final.real_model_calls,0);
   assert.deepEqual(final.responses,[...replies.slice(0,5),...guardResponses,...replies.slice(5)]);assert.deepEqual(errors,[]);assert.deepEqual(foreign,[]);assert.deepEqual(forbidden,[]);const counts={};for(const path of posts)counts[path]=(counts[path]||0)+1;assert.deepEqual(counts,{'/api/study/item':1,'/api/upload':7,'/api/task/feedback':4,'/api/print/homework/draft':8});await fit(page);await proof(page,'text-ai-derivation-retry-'+width);
   results.push({width,synthetic_only:true,unsafe_word_rejected_before_model:3,transport_failures:1,valid_word:1,valid_txt:1,known_ai_roles_rejected:2,missing_teacher_claim_rejected:1,ai_derived_retry:1,actual_model_calls:0,raw_unchanged:true,original_record_id:original.id,check_record_id:saved.id,same_number_retry:true});
   await page.close();page=null;await server.stop();server=null;
  }
  if(process.env.HOMEWORK_TEXT_PROOF_DIR){const fs=require('node:fs/promises'),path=require('node:path');await fs.writeFile(path.join(process.env.HOMEWORK_TEXT_PROOF_DIR,'result.json'),JSON.stringify(results,null,2)+'\n')}
  console.log(JSON.stringify(results,null,2));
 }catch(error){
  if(server)try{const failed=await(await fetch(server.url+'__fixture/text')).json();console.error(JSON.stringify({phases:failed.calls.map(c=>c.phase),responses:failed.responses.slice(-2),status:page?await page.locator('[data-homework-review-status]').first().innerText():''},null,2))}catch{}
  if(page)try{await proof(page,'failure-'+page.viewportSize().width)}catch{}throw error
 }
 finally{if(page)await Promise.race([page.close().catch(()=>{}),delay(3000)]);if(server)await server.stop();if(browser)await Promise.race([browser.close().catch(()=>{}),delay(5000)])}
})().catch(error=>{console.error(error);process.exitCode=1});

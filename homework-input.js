// Shared parent/child capture; only explicit saves create homework.
(() => {
 'use strict';
 // ponytail: unfinished drafts live in this page; warn before closing, persist only confirmed inputs.
 const views=new Map(),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let dialog,ctx,current,busy=false,recorder=null,stream=null,micPending=false,timer,generation=0;
 const uuid=()=>crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
 const field=(name,label,value='',limit=200)=>`<label>${label}<input name="${name}" maxlength="${limit}" value="${esc(value)}" ${name==='title'?'required':''}></label>`;
 const dirty=()=>[...views.values()].some(v=>v.transcript|| (v.items.length?v.items.some(i=>!i.saved):v.text||v.explanation||v.files.length));
 function remember(){
  if(!dialog||!current)return;
  const source=dialog.querySelector('[data-homework-source]');if(source){current.text=source.elements.text.value;current.explanation=source.elements.explanation.value}
  const transcript=dialog.querySelector('[data-homework-transcript]');if(transcript)current.transcript=transcript.value;
  for(const form of dialog.querySelectorAll('[data-homework-item]')){const row=current.items[Number(form.dataset.homeworkItem)];if(!row||row.saved||row.pending)continue;Object.assign(row,Object.fromEntries(new FormData(form)),{reviewed:form.elements.reviewed.checked})}
 }
 function paint(){
  const frozen=current.items.length>0;
  dialog.innerHTML=`<header><h2 id="homeworkInputTitle">报功课</h2><p>${esc(ctx.child_name)} · ${esc(ctx.day)}${ctx.child?' · 告诉家长后一起核对':''}</p></header><form data-homework-source><fieldset ${frozen?'disabled':''}><label>登记本原文 / 孩子原话<textarea name="text" maxlength="6000" rows="3" placeholder="照原样记，缩写也保留。可以使用键盘语音输入。">${esc(current.text)}</textarea></label><label>孩子怎样解释缩写 · 可选<textarea name="explanation" maxlength="3000" rows="2" placeholder="例如：小练3是小练习册第3页，不是做3遍。">${esc(current.explanation)}</textarea></label><div class="homework-tools"><label class="homework-file">照片 / 录音<input type="file" data-homework-files multiple accept="image/jpeg,image/png,image/webp,audio/*"></label><label class="homework-file">拍登记本<input type="file" data-homework-files accept="image/*" capture="environment"></label><button type="button" data-homework-record>${recorder?'结束录音':'录一段话'}</button></div></fieldset></form><div class="homework-files">${current.files.map((f,i)=>`<div><span>${esc(f.name)}</span>${f.id?'<small>原件已保存</small>':`<small>${esc(f.error||'待上传')}</small><button type="button" data-homework-retry-file="${i}">重试上传</button>`}${f.id&&f.mime?.startsWith('audio/')?`<audio controls preload="none" src="${esc(ctx.fileURL(f.id))}"></audio>${!frozen?`<button type="button" data-homework-transcribe="${i}">转成文字供核对</button>`:''}`:''}${!frozen?`<button type="button" data-homework-remove-file="${i}">移除关联</button>`:''}</div>`).join('')}</div>${current.transcript!==null&&!frozen?`<section class="homework-transcript"><label>听原音，核对文字<textarea data-homework-transcript maxlength="6000">${esc(current.transcript)}</textarea></label><button type="button" data-homework-use-transcript>放入原话</button></section>`:''}<p class="homework-status" role="status" aria-live="polite">${esc(current.message)}</p>${!frozen?'<div class="homework-tools"><button type="button" class="primary" data-homework-draft>整理成作业</button><button type="button" data-homework-manual>直接填写一项</button></div>':`<div class="homework-tools"><button type="button" data-homework-edit-source>修改原文并重新整理</button><button type="button" data-homework-manual>再填一项</button></div>`}${current.uncertainties.length?`<div class="homework-uncertainties"><strong>这些还要核对</strong><ul>${current.uncertainties.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}<div class="homework-candidates">${current.items.map((row,i)=>row.saved?`<article class="homework-saved"><strong>${esc(row.title)}</strong><p>${ctx.child?'已告诉家长，要求仍待核对':'已加入这天的作业'} · 尚未完成</p></article>`:`<form data-homework-item="${i}"><fieldset ${row.pending?'disabled':''}>${field('title','这项要做什么',row.title)}<label>做到怎样算完成<textarea name="goal" maxlength="2000" rows="2">${esc(row.goal)}</textarea></label><div class="homework-columns">${field('subject','科目 · 可留空',row.subject,80)}<label>预计分钟 · 可留空<input type="number" name="planned_minutes" min="0" max="1440" step="1" value="${esc(row.planned_minutes??'')}"></label></div>${row.excerpt?`<details><summary>核对识别片段</summary><p>${esc(row.excerpt)}</p></details>`:''}<label class="homework-check"><input type="checkbox" name="reviewed" required ${row.reviewed?'checked':''}><span>${ctx.child?'我核对了这项内容':'我核对了作业要求'}</span></label></fieldset><p class="homework-status" role="status">${esc(row.error||'')}</p><button class="primary" type="submit">${row.pending?'核对并重试这次保存':ctx.child?'告诉家长':'确认加入这天'}</button></form>`).join('')}</div><footer><small>加入只记录要做的事，不代表完成。原文、解释和原件随功课保留。</small><button type="button" data-homework-close>返回功课</button></footer>`;
  if(busy||micPending||recorder)for(const el of dialog.querySelectorAll('input,textarea,button'))el.disabled=!(recorder&&el.hasAttribute('data-homework-record'));
 }
 function status(message){current.message=message;paint()}
 async function upload(entry){
  try{if(!entry.file?.size||entry.file.size>20*1024*1024)throw Error('文件为空或超过20MB');const r=await ctx.upload(entry.file);if(!/^[a-f0-9]{32}$/.test(r?.attachment?.id))throw Error('上传回执无法核对');Object.assign(entry,r.attachment,{error:''});entry.file=null}
  catch(e){entry.error=e.message||'上传未完成'}
 }
 async function addFiles(files){
  if(busy)return;remember();if(current.files.length+files.length>3){status('每次最多三份照片或录音，请分次核对。');return}
  busy=true;paint();const gen=generation;
  for(const file of files){const entry={file,name:file.name,id:'',error:''};current.files.push(entry);await upload(entry);if(gen!==generation)return}
  busy=false;status('成功上传的原件已保留，尚未加入功课；未成功的文件可重试。');
 }
 function candidate(values={}){return {title:'',goal:'',subject:'',excerpt:'',planned_minutes:'',...values,request_key:uuid(),pending:null,saved:false}}
 function source(){return {text:current.text,explanation:current.explanation,attachments:current.files.map(f=>f.id)}}
 async function draft(){
  remember();if(current.files.some(f=>!f.id)){status('请先完成或移除未成功的上传。');return}busy=true;status('正在按这次材料整理，完成后请核对。');const gen=generation;
  try{const r=await ctx.request('draft',source());if(gen!==generation)return;if(!Array.isArray(r?.draft?.items)||!Array.isArray(r.draft.uncertainties))throw Error('整理回执无法核对');current.items=r.draft.items.map(candidate);current.uncertainties=r.draft.uncertainties;current.message=current.items.length?'下面是草稿，标题和目标都可以修改。':'没有读到明确的可执行功课，请补充解释或直接填写。'}catch(e){if(gen!==generation)return;current.message=e.message||'整理暂不可用，仍可直接填写。'}finally{if(gen===generation){busy=false;paint()}}
 }
 async function save(form){
  remember();const row=current.items[Number(form.dataset.homeworkItem)];if(!row||row.saved||!form.reportValidity())return;if(current.files.some(f=>!f.id)){status('请先完成或移除未成功的上传。');return}
  row.pending ||= {title:row.title,subject:row.subject,planned_minutes:row.planned_minutes===''?null:Number(row.planned_minutes),version:0,request_key:row.request_key,report:{...source(),excerpt:row.excerpt,goal:row.goal}};
  busy=true;row.error='正在保存…';paint();const gen=generation;
  try{const r=await ctx.request('item',row.pending);if(gen!==generation)return;if(!r?.ok||!r.saved_item_id||!r.items?.some(i=>i.id===r.saved_item_id))throw Error('保存回执尚未核对');row.saved=true;row.pending=null;row.error='';current.message='已保存这项功课。';await ctx.onSaved?.()}
  catch(e){if(gen!==generation)return;if([400,403,404,422].includes(e.status))row.pending=null;row.error=(e.message||'保存未完成')+'；内容保留，请核对后重试。'}finally{if(gen===generation){busy=false;paint()}}
 }
 async function record(){
  if(recorder){recorder.stop();return}remember();if(current.files.length>=3){status('这次已有三份原件，请分次记录。');return}
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){status('此浏览器不能录音，可用键盘语音输入或上传录音。');return}
  const gen=generation;micPending=true;paint();
  try{const activeStream=await navigator.mediaDevices.getUserMedia({audio:true});if(gen!==generation){activeStream.getTracks().forEach(t=>t.stop());return}stream=activeStream;const mime=['audio/webm','audio/mp4','audio/ogg'].find(m=>MediaRecorder.isTypeSupported(m));const currentRecorder=new MediaRecorder(activeStream,mime?{mimeType:mime}:undefined),chunks=[];recorder=currentRecorder;micPending=false;
   currentRecorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};currentRecorder.onerror=()=>{if(gen===generation)current.message='录音遇到问题，请核对原件或重新录音。'};
   currentRecorder.onstop=async()=>{activeStream.getTracks().forEach(t=>t.stop());if(gen!==generation)return;clearTimeout(timer);recorder=null;stream=null;const type=currentRecorder.mimeType.split(';')[0],ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':'webm';if(chunks.length)await addFiles([new File(chunks,'功课原话.'+ext,{type})]);else status('没有录到声音，请重试或填写文字。')};
   currentRecorder.start(1000);timer=setTimeout(()=>{if(currentRecorder.state==='recording')currentRecorder.stop()},180000);status('正在录音，最长三分钟。');
  }catch{if(gen!==generation)return;micPending=false;stream?.getTracks().forEach(t=>t.stop());stream=null;status('未能开启麦克风，可用键盘语音输入或上传录音。')}
 }
 async function click(e){
  const b=e.target.closest('button');if(!b||busy||micPending)return;if(recorder&&!b.hasAttribute('data-homework-record'))return;remember();
  if(b.hasAttribute('data-homework-close')){dialog.close();return}
  if(b.hasAttribute('data-homework-record'))return record();
  if(b.hasAttribute('data-homework-draft'))return draft();
  if(b.hasAttribute('data-homework-edit-source')){if(current.items.some(i=>i.pending)){status('请先核对上次保存结果，再修改原文。');return}if(current.items.some(i=>!i.saved&&(i.title||i.goal))&&!confirm('重新整理会清除尚未保存的作业草稿，已保存的功课保留。继续吗？'))return;current.items=[];current.uncertainties=[];current.message='已保存的功课保留；未保存草稿重新整理。';paint();return}
  if(b.hasAttribute('data-homework-manual')){if(current.items.length>=12){status('每次最多十二项，请分次录入。');return}current.items.push(candidate());paint();dialog.querySelector('[data-homework-item]:last-child input')?.focus();return}
  if(b.dataset.homeworkRemoveFile!==undefined){current.files.splice(Number(b.dataset.homeworkRemoveFile),1);paint();return}
  if(b.dataset.homeworkRetryFile!==undefined){busy=true;paint();const gen=generation;await upload(current.files[Number(b.dataset.homeworkRetryFile)]);if(gen===generation){busy=false;paint()}return}
  if(b.dataset.homeworkTranscribe!==undefined){busy=true;paint();const gen=generation;try{const r=await ctx.transcribe(current.files[Number(b.dataset.homeworkTranscribe)].id);if(gen!==generation)return;current.transcript=r.text;current.message='请先听原音核对，再放入原话。'}catch(e){if(gen===generation)current.message=e.message||'转写失败，原音保留。'}finally{if(gen===generation){busy=false;paint()}}return}
  if(b.hasAttribute('data-homework-use-transcript')){const text=[current.text,dialog.querySelector('[data-homework-transcript]').value].filter(Boolean).join('\n');if(text.length>6000){status('合并后超过6000字，请精简。');return}current.text=text;current.transcript=null;paint()}
 }
 function open(options){
  if(busy||recorder||micPending)return false;
  if(!dialog){dialog=document.createElement('dialog');dialog.id='homeworkInputDialog';dialog.setAttribute('aria-labelledby','homeworkInputTitle');document.body.append(dialog);dialog.addEventListener('click',click);dialog.addEventListener('input',remember);dialog.addEventListener('change',e=>{if(e.target.matches('[data-homework-files]'))addFiles([...e.target.files])});dialog.addEventListener('submit',e=>{e.preventDefault();if(!busy&&e.target.matches('[data-homework-item]'))save(e.target)});dialog.addEventListener('cancel',e=>{if(busy||recorder||micPending)e.preventDefault();else remember()})}
  ctx=options;if(!views.has(ctx.key))views.set(ctx.key,{text:'',explanation:'',files:[],items:[],uncertainties:[],transcript:null,message:''});current=views.get(ctx.key);paint();dialog.showModal();return true;
 }
 function clear(){generation++;clearTimeout(timer);stream?.getTracks().forEach(t=>t.stop());stream=null;recorder=null;micPending=false;busy=false;views.clear();current=null;ctx=null;dialog?.close();dialog?.replaceChildren()}
 window.addEventListener('beforeunload',e=>{remember();if(dirty()||busy||recorder||micPending){e.preventDefault();e.returnValue=''}});
 function reportHTML(report,fileURL){if(!report||!Object.keys(report).length)return '';return `<details class="study-report"><summary>${report.actor==='child'&&!report.confirmed_at?'孩子报来的要求 · 待家长核对':'查看原登记与解释'}</summary>${report.text?`<p><strong>原话 / 登记原文：</strong>${esc(report.text)}</p>`:''}${report.explanation?`<p><strong>孩子的解释：</strong>${esc(report.explanation)}</p>`:''}${report.excerpt?`<p><strong>当时核对的识别片段：</strong>${esc(report.excerpt)}</p>`:''}${report.attachments?.map((id,n)=>`<a href="${esc(fileURL(id))}" target="_blank" rel="noopener noreferrer">原件 ${n+1}</a>`).join('')||''}${report.confirmed_at?'<p>家长已核对要求，不代表已完成。</p>':''}</details>`}
 window.FamilyHomework={open,clear,reportHTML};
})();

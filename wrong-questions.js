// 错题照片核对入库：上传照片 → 模型标注草稿 → 家长在照片上逐题核对/编辑 → 保存为错题记录。
// 只有家长确认才成事实；标注只是草稿，转写与归属以原件为准。
(() => {
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const views=new Map();
 let dialog,ctx,current,busy=false,generation=0;
 const STYLE=`<style>
  #wrongQDialog{max-width:900px;width:calc(100vw - 24px);border:1px solid var(--line,#ccc);border-radius:12px;padding:16px;color:inherit}
  #wrongQDialog::backdrop{background:rgba(0,0,0,.4)}
  .wq-tools{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
  .wq-tools button,.wq-file{min-height:44px}
  .wq-file{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line,#ccc);border-radius:8px;padding:0 12px;cursor:pointer}
  .wq-page{margin:14px 0;border-top:1px solid var(--line,#eee);padding-top:12px}
  .wq-canvas{position:relative;display:inline-block;max-width:100%;line-height:0}
  .wq-canvas img{max-width:100%;height:auto;display:block}
  .wq-box{position:absolute;box-sizing:border-box;border:2px solid #c0392b;border-radius:3px;background:rgba(192,57,43,.08);font-size:11px;color:#c0392b}
  .wq-box.wq-layout{border-color:#2f5aa0;background:rgba(47,90,160,.06);color:#2f5aa0}
  .wq-box.wq-handwriting{border-color:#1f6a4d;background:rgba(31,106,77,.06);color:#1f6a4d}
  .wq-box>span{position:absolute;top:-14px;left:-2px;background:inherit;padding:0 3px;white-space:nowrap}
  .wq-item{border:1px solid var(--line,#ddd);border-radius:8px;padding:10px;margin:8px 0}
  .wq-item label{display:block;margin:6px 0}
  .wq-item textarea,.wq-item input{width:100%;box-sizing:border-box}
  .wq-uncertain{color:#8a6d1a;font-size:13px}
  .wq-status{min-height:20px}
  @media(max-width:640px){.wq-item textarea{rows:2}}
 </style>`;

 function boxStyle(b){return `left:${b.x/10}%;top:${b.y/10}%;width:${b.w/10}%;height:${b.h/10}%`;}

 function pageHTML(page,fileURL){
  const img=current.imageById[page.upload_id];
  const boxes=page.regions.map(r=>`<div class="wq-box wq-${esc(r.kind)}" style="${boxStyle(r.box)}"><span>${esc(r.label||({wrong_item:'错题',handwriting:'手写',layout:'版面'}[r.kind]||''))}</span></div>`).join('');
  return `<div class="wq-page"><p class="small">第 ${page.page} 页${img?'':' · 原件缺失'}</p>`+
   (img?`<div class="wq-canvas"><img src="${esc(fileURL(page.upload_id))}" alt="错题照片第${page.page}页">${boxes}</div>`:'')+`</div>`;
 }

 function itemHTML(it,i){
  return `<form class="wq-item" data-wq-item="${i}"><label><input type="checkbox" data-wq-field="include" ${it.include?'checked':''}> 收录这道错题（第${it.page}页${it.uncertain?' · 模型标记待核对':''}）</label>`+
   `<label>题号/区域 <input data-wq-field="label" maxlength="80" value="${esc(it.label)}"></label>`+
   `<label>题面转写 <textarea data-wq-field="text" rows="2" maxlength="2000">${esc(it.text)}</textarea></label>`+
   `<label>学生作答 <input data-wq-field="answer" maxlength="1000" value="${esc(it.answer)}"></label>`+
   `<label>订正/正确答案 <input data-wq-field="correction" maxlength="1000" value="${esc(it.correction)}"></label>`+
   `<label>知识点（可选，待核对）<input data-wq-field="topic_hint" maxlength="80" value="${esc(it.topic_hint)}"></label>`+
   `<label>错误类型（可选，待核对）<input data-wq-field="error_hint" maxlength="80" value="${esc(it.error_hint)}"></label></form>`;
 }

 function paint(){
  if(!dialog)return;
  const fileURL=ctx.fileURL;
  const canAnnotate=current.files.some(f=>f.id)&&!busy;
  const canSave=current.items.some(it=>it.include)&&!busy;
  dialog.innerHTML=STYLE+`<header><h2 id="wrongQTitle">报错题照片</h2><p>${esc(ctx.child_name)} · ${esc(ctx.day)}${ctx.subject?' · '+esc(ctx.subject):''}</p></header>`+
   `<div class="wq-tools"><label class="wq-file">选照片（最多3张）<input type="file" data-wq-files multiple accept="image/jpeg,image/png,image/webp"></label>`+
   `<label class="wq-file">拍作业/试卷<input type="file" data-wq-files accept="image/*" capture="environment"></label></div>`+
   `<div>${current.files.map((f,i)=>`<div class="small">${esc(f.name||'照片')} · ${f.id?'已上传':esc(f.error||'待上传')} ${!busy?`<button type="button" data-wq-remove="${i}">移除</button>`:''}</div>`).join('')}</div>`+
   `<div class="wq-tools"><button type="button" class="primary" data-wq-annotate ${canAnnotate?'':'disabled'}>标注错题</button><button type="button" data-wq-save ${canSave?'':'disabled'}>保存收录的错题</button></div>`+
   `<p class="wq-status" role="status" aria-live="polite">${esc(current.message)}</p>`+
   (current.uncertainties.length?`<div class="wq-uncertain"><strong>模型提示需核对：</strong><ul>${current.uncertainties.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:'')+
   `<div data-wq-pages>${current.pages.map(p=>pageHTML(p,fileURL)).join('')}</div>`+
   `<div data-wq-items>${current.items.map(itemHTML).join('')}</div>`+
   `<footer><small>标注只是待核对草稿，不写入任何数据；仅收录并保存后才成为错题学习记录。</small><button type="button" data-wq-close>关闭</button></footer>`;
  for(const el of busy?dialog.querySelectorAll('input,textarea,button'):[])el.disabled=true;
 }

 async function upload(entry){
  try{
   if(!entry.file?.size||entry.file.size>20*1024*1024)throw Error('文件为空或超过20MB');
   const r=await ctx.upload(entry.file);
   if(!/^[a-f0-9]{32}$/.test(r?.attachment?.id))throw Error('上传回执无法核对');
   Object.assign(entry,r.attachment,{error:''});entry.file=null;
  }catch(e){entry.error=e.message||'上传失败';}
 }
 async function addFiles(files){
  const gen=generation;
  for(const file of files){
   if(current.files.length>=3){current.message='每次最多3张照片。';break;}
   const entry={file,name:file.name,id:'',error:''};current.files.push(entry);await upload(entry);
   if(gen!==generation)return;
  }
  if(gen===generation)paint();
 }
 async function annotate(){
  const ids=current.files.filter(f=>f.id).map(f=>f.id);
  if(!ids.length)return;
  busy=true;current.message='正在标注（读取照片，不保存）…';paint();const gen=generation;
  try{
   const r=await ctx.request('annotate',{child_id:ctx.child_id,subject_hint:ctx.subject||'',attachments:ids});
   if(gen!==generation)return;
   const order=Array.isArray(r?.attachments)?r.attachments:ids;
   const pages=(r?.draft?.pages||[]).map(p=>({page:p.page,upload_id:order[p.page-1]||'',regions:Array.isArray(p.regions)?p.regions:[]}));
   current.pages=pages;current.imageById=Object.fromEntries(current.files.filter(f=>f.id).map(f=>[f.id,true]));
   current.uncertainties=Array.isArray(r?.draft?.uncertainties)?r.draft.uncertainties:[];
   const items=[];
   for(const p of pages)for(const rg of p.regions)if(rg.kind==='wrong_item')
    items.push({page:p.page,upload_id:p.upload_id,box:rg.box,uncertain:!!rg.uncertain,include:!rg.uncertain,
                label:rg.label||'',text:rg.text||'',answer:rg.answer||'',correction:rg.correction||'',topic_hint:'',error_hint:''});
   current.items=items;
   current.message=items.length?'下面是草稿：请逐题核对、编辑，勾选要收录的，再保存。':'没有读到明确的错题，可换清晰照片或直接不收录。';
  }catch(e){if(gen===generation)current.message=e.message||'标注暂不可用，可稍后重试或不收录。';}
  finally{if(gen===generation){busy=false;paint();}}
 }
 async function save(){
  const items=current.items.filter(it=>it.include).map(it=>({label:it.label,text:it.text,answer:it.answer,
    correction:it.correction,topic_hint:it.topic_hint,error_hint:it.error_hint,upload_id:it.upload_id}));
  if(!items.length)return;
  busy=true;current.message='正在保存…';paint();const gen=generation;
  try{
   const r=await ctx.request('save',{child_id:ctx.child_id,day:ctx.day,subject:ctx.subject||'',request_key:key(),items});
   if(gen!==generation)return;
   if(!r?.ok||!Array.isArray(r.saved))throw Error('保存回执无法核对');
   current.items=[];current.pages=[];current.uncertainties=[];current.files=[];current.imageById={};
   current.message='已保存 '+r.saved.length+' 道错题为学习记录。';
   await ctx.onSaved?.();
  }catch(e){if(gen===generation)current.message=e.message||'保存失败，草稿仍在，请重试。';}
  finally{if(gen===generation){busy=false;paint();}}
 }
 function key(){return 'wrongq-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10);}

 function onInput(e){
  const form=e.target.closest('[data-wq-item]');if(!form)return;
  const it=current.items[Number(form.dataset.wqItem)];if(!it)return;
  const f=e.target.dataset.wqField;if(!f)return;
  it[f]=e.target.type==='checkbox'?e.target.checked:e.target.value;
  if(f==='include'){const save=dialog.querySelector('[data-wq-save]');if(save)save.disabled=!current.items.some(x=>x.include)||busy;}
 }
 function onClick(e){
  const b=e.target.closest('button');if(!b||busy)return;
  if(b.hasAttribute('data-wq-annotate'))return annotate();
  if(b.hasAttribute('data-wq-save'))return save();
  if(b.hasAttribute('data-wq-close'))return dialog.close();
  if(b.dataset.wqRemove!==undefined){current.files.splice(Number(b.dataset.wqRemove),1);paint();return;}
 }
 function open(options){
  if(busy)return false;
  if(!dialog){
   dialog=document.createElement('dialog');dialog.id='wrongQDialog';dialog.setAttribute('aria-labelledby','wrongQTitle');
   document.body.append(dialog);
   dialog.addEventListener('click',onClick);
   dialog.addEventListener('input',onInput);
   dialog.addEventListener('change',e=>{if(e.target.matches('[data-wq-files]'))addFiles([...e.target.files]);});
  }
  ctx=options;
  if(!views.has(ctx.key))views.set(ctx.key,{files:[],pages:[],items:[],uncertainties:[],imageById:{},message:'上传作业或试卷照片，点“标注错题”。'});
  current=views.get(ctx.key);paint();dialog.showModal();return true;
 }
 function clear(){generation++;busy=false;views.clear();current=null;ctx=null;dialog?.close();dialog?.replaceChildren();}
 window.FamilyWrongQuestions={open,clear};
})();

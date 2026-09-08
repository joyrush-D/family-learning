// Parent controls use the existing authenticated API and native dialog.
let childAccessBusy=false,childAccessOpen=0;
async function childAccessRequest(action,obj){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{
  const r=await apiFetch('/api/child-access'+(action?'/'+action:''),{signal:controller.signal,...(action?{method:'POST',headers:{'Content-Type':'application/json','X-Family-Token':data.token},body:JSON.stringify(obj)}:{})});
  const result=await r.json();if(!r.ok)throw Error(result.error||'暂时无法更新孩子入口');return result;
 }catch(e){if(e.name==='AbortError')throw Error('等待超时，请重新核对入口状态。');if(['TypeError','SyntaxError'].includes(e.name))throw Error('读取未成功，请检查连接或重新登录家长入口。');throw e}
 finally{clearTimeout(timer)}
}
async function openChildAccess(id){
 if(childAccessBusy||readingBusy)return;
 const profile=data.children.find(c=>c.id===id);if(!profile)return;
 const ticket=++childAccessOpen;
 readingDialog(`<h2>${esc(profile.name)}的独立入口</h2><p>正在核对入口与分享范围…</p><p id="childAccessError" role="status"></p><button type="button" data-close="readingDialog">关闭</button>`);
 try{
  const state=await childAccessRequest(),current=state.children.find(c=>c.child_id===id);
  if(ticket!==childAccessOpen||!$('#readingDialog').open)return;
  if(!current)throw Error('孩子档案已变化，请刷新后核对。');
  const shared=new Set(current.shared_task_ids),ts=readingTasks().filter(t=>t.child_id===id&&t.state!=='草案');
  $('#readingDialogBody').innerHTML=`<h2>${esc(profile.name)}的独立入口</h2><p class="muted">把邀请链接交给孩子，在孩子自己的设备或独立浏览器打开。不要交出家长账号，也不要使用仍保存着家长登录的浏览器。</p><h3>每天的功课</h3><label class="child-share-option"><input type="checkbox" data-child-study="${esc(id)}" ${current.study_enabled?'checked':''}><span><strong>让孩子自己报功课、计时和反馈</strong><br><span class="small source">分享这个孩子的每日功课、行动要求和时间安排。孩子说完成后，仍由家长核对；原始群消息和其他成长记录不分享。</span></span></label><h3>阅读任务</h3><p class="small muted">勾选后分享书名、阅读范围、表达方式、完成条件、当前作品及这项任务的印章。家长核对备注、原始群消息和其他成长记录不在分享范围。</p><div id="childShareList">${ts.map(t=>`<label class="child-share-option"><input type="checkbox" data-child-share="${esc(t.id)}" data-child-id="${esc(id)}" ${shared.has(t.id)?'checked':''}><span><strong>${esc(t.book)}</strong> · ${esc(t.state)}<br><span class="small source">${esc(t.scope)}${t.attachments.length?' · 含 '+t.attachments.length+' 份当前作品原件':''}</span></span></label>`).join('')||empty('先到阅读营地约定一个任务，并点“一起开始”，再来选择分享。')}</div><p class="small muted">取消勾选会停止孩子对该任务的访问；已提交的作品仍留在家长记录中。</p><h3>登录邀请</h3><p>${current.has_access?'已有尚未到期的邀请或登录。':'目前没有可用的邀请或登录。'} 邀请24小时内可用一次；登录保持7天。</p><div class="toolbar"><button type="button" data-child-invite="${esc(id)}">生成新的邀请链接</button><button type="button" data-child-revoke="${esc(id)}">停用全部邀请和登录</button></div><div id="childInviteResult"></div><p id="childAccessError" class="error" role="status"></p><div class="actions"><button type="button" data-close="readingDialog">关闭</button></div>`;
 }catch(e){if(ticket===childAccessOpen&&$('#childAccessError'))$('#childAccessError').textContent=e.message}
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.childAccess)return openChildAccess(b.dataset.childAccess);
 if(!b.dataset.childInvite&&!b.dataset.childRevoke)return;
 if(childAccessBusy)return;childAccessBusy=true;b.disabled=true;
 const out=$('#childInviteResult'),error=$('#childAccessError');error.textContent='';out.replaceChildren();
 try{
  if(b.dataset.childInvite){
   const r=await childAccessRequest('invite',{child_id:b.dataset.childInvite});
   if(!out.isConnected||!$('#readingDialog').open)return;
   const link=new URL(r.entry_url||endpoint('/child/'),location.origin);link.hash='invite='+encodeURIComponent(r.invite);
   out.innerHTML='<label>仅交给这个孩子的邀请链接<input id="childInviteLink" readonly></label><p class="small muted">旧的未使用邀请已失效。链接只在这里显示；关闭前请复制，勿发到班级群。登录后链接不能再次使用。</p>';
   $('#childInviteLink').value=link.href;$('#childInviteLink').focus();$('#childInviteLink').select();
  }else{await childAccessRequest('revoke',{child_id:b.dataset.childRevoke});out.textContent='已停用这个孩子的全部邀请和登录。已保存作品仍保留。'}
 }catch(err){error.textContent=err.message+' 如生成邀请的结果不明，可再生成一次，旧邀请将失效。'}
 finally{childAccessBusy=false;b.disabled=false}
});
$('#readingDialog').addEventListener('close',()=>{childAccessOpen++;const result=$('#childInviteResult');if(result)result.replaceChildren()});
document.addEventListener('change',async e=>{
 const el=e.target;if(!el.dataset.childShare&&!el.dataset.childStudy)return;
 const desired=el.checked;el.checked=!desired;if(childAccessBusy)return;
 childAccessBusy=true;el.disabled=true;$('#childAccessError').textContent='';
 try{await childAccessRequest(el.dataset.childStudy?'study':'share',el.dataset.childStudy?{child_id:el.dataset.childStudy,enabled:desired}:{child_id:el.dataset.childId,task_id:el.dataset.childShare,shared:desired});el.checked=desired;toast(el.dataset.childStudy?(desired?'已开启孩子的功课入口':'已关闭功课入口，原记录保留'):(desired?'这项任务已分享给孩子':'已停止分享，作品记录保留'))}
 catch(err){$('#childAccessError').textContent=err.message+' 请关闭后重新打开，核对当前分享状态。'}
 finally{childAccessBusy=false;el.disabled=false}
});

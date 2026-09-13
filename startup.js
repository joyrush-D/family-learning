// Independent of the application bundle: missing scripts still leave a way back.
(() => {
  let failure='';
  const pages=['home','calendar','tasks','more','ask','settings'];
  document.addEventListener('click',event=>{
    const button=event.target.closest('nav[aria-label="主导航"] button[data-page], .top-actions button[data-page]');
    const root=document.getElementById('content');
    if(!button||!root||root.dataset.ready==='true'||!pages.includes(button.dataset.page))return;
    document.body.dataset.startupPage=button.dataset.page;
    document.querySelectorAll('nav button[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===button.dataset.page||(b.dataset.page==='more'&&!['home','calendar','tasks'].includes(button.dataset.page))));
    if(root.querySelector('[data-startup-error]'))return;
    const message=document.createElement('p');message.setAttribute('role','status');
    message.textContent='正在准备“'+button.textContent+'”，读取家庭记录后打开。';root.replaceChildren(message);
  });
  document.querySelectorAll('nav button[data-page], .top-actions button[data-page]').forEach(b=>{if(pages.includes(b.dataset.page))b.disabled=false});
  function show(message){
    const root=document.getElementById('content');
    if(!root||root.dataset.ready==='true'||root.querySelector('[data-startup-error]'))return;
    root.innerHTML='<section class="card" data-startup-error role="alert"><h1>页面暂未加载成功</h1><p></p><form method="get"><button class="primary" type="submit" data-startup-retry>重新加载页面</button></form></section>';
    root.querySelector('p').textContent=message;
  }
  window.addEventListener('error',event=>{
    const source=event.target?.src||event.filename||'';
    if(source.split('?')[0].endsWith('/app.bundle.js')){
      failure='页面程序未能加载，请检查连接后重新加载。';show(failure);
    }
  },true);
  window.addEventListener('DOMContentLoaded',()=>{if(failure)show(failure)},{once:true});
  setTimeout(()=>show('页面加载超时，请检查连接后重新加载。'),20000);
})();

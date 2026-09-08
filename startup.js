// Independent of the application bundle: missing scripts still leave a way back.
(() => {
  let failure='';
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

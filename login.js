// Credentials remain in the form and this same-origin request only.
(() => {
  const form=document.getElementById('loginForm'),username=document.getElementById('username'),password=document.getElementById('password');
  const submit=document.getElementById('loginSubmit'),show=document.getElementById('showPassword'),status=document.getElementById('loginStatus');
  let pending=false;
  // The server serves this page only for the configured HTTPS or direct LAN host.
  const canLogin=['https:','http:'].includes(location.protocol);
  submit.disabled=!canLogin;
  if(!canLogin)status.textContent='请从配置的家庭入口打开此页后登录。';
  // The app's own home-network HTTPS: phones install the family CA once, then recording and calendar subscriptions work.
  const host=location.hostname,homeHost=/^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)\d+\.\d+$/.test(host)||host.endsWith('.local');
  document.getElementById('certificateHint').hidden=!(location.protocol==='https:'&&homeHost);
  show.addEventListener('click',()=>{
    const visible=password.type==='password';password.type=visible?'text':'password';
    show.textContent=visible?'隐藏':'显示';show.setAttribute('aria-pressed',String(visible));
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(pending||!canLogin||!form.reportValidity())return;
    pending=true;submit.disabled=true;username.readOnly=true;password.readOnly=true;show.disabled=true;
    status.dataset.pending='true';status.textContent='正在登录…';form.setAttribute('aria-busy','true');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(new URL('./api/parent/login',location.href),{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json','X-Family-Login':'1'},body:JSON.stringify({username:username.value,password:password.value})});
      let result;try{result=await response.json()}catch{throw Error('登录服务未正确响应，请稍后重试。')}
      if(!response.ok||result.ok!==true)throw Error(typeof result.error==='string'?result.error:'登录未成功，请核对账号与密码。');
      password.value='';password.type='password';show.textContent='显示';show.setAttribute('aria-pressed','false');
      status.textContent='已登录，正在打开家庭空间…';
      const home=new URL('./',location.href);home.hash=location.hash;location.replace(home.href);
    }catch(error){
      delete status.dataset.pending;
      status.textContent=error.name==='AbortError'?'登录等待超时，请检查连接后重试。':error instanceof TypeError?'未能连接登录服务，请检查网络后重试。':error.message;
    }finally{
      clearTimeout(timer);pending=false;submit.disabled=false;username.readOnly=false;password.readOnly=false;show.disabled=false;form.removeAttribute('aria-busy');
    }
  });
})();

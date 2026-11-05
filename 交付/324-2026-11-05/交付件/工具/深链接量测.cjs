const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
const fs=require('fs');
const OUT=process.env.OUT||'/tmp/deep6-322';
fs.mkdirSync(OUT,{recursive:true});
const BASE=process.env.BASE||'http://127.0.0.1:8801/';
const TASK=process.env.TASK_ID||'MANUAL-78101ae37dd7e5251c01';
const CHILD=process.env.CHILD_ID||'child-1';
const DAY=process.env.DAY||'2026-11-04';
const failures=[]; const ck=(ok,msg)=>{if(!ok)failures.push(msg)};
const q=(u,extra)=>{const url=new URL(u);for(const[k,v]of Object.entries(extra))url.searchParams.set(k,v);return url.href};
const WIDTHS=[[360,800],[390,844],[768,900],[1024,900],[1200,860],[1440,860]];
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const metrics={};
 for(const [w,h] of WIDTHS){
  // 今天页
  const p1=await browser.newPage({viewport:{width:w,height:h}});
  const err1=[]; p1.on('pageerror',e=>err1.push(String(e)));
  await p1.goto(q(BASE,{child_id:CHILD,day:DAY}),{waitUntil:'domcontentloaded'});
  await p1.waitForSelector('#task-groups',{timeout:20000}).catch(()=>{});
  await p1.waitForTimeout(1200);
  const base=await p1.evaluate(()=>{const s=document.querySelector('.grove-stack'),sc=document.querySelector('.grove-board-scroll');const r=s? s.getBoundingClientRect():null;return {rect:r?{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}:null,scrollTop:sc?sc.scrollTop:0,docH:document.documentElement.scrollHeight,rows:document.querySelectorAll('#task-groups article.grove-row').length,title:document.querySelector('#groveListTitle')?.innerText||'',hscroll:document.documentElement.scrollWidth-document.documentElement.clientWidth,ready:document.querySelector('#content')?.getAttribute('data-ready')}});
  await p1.screenshot({path:`${OUT}/w${w}-list.png`,fullPage:false});
  await p1.close();
  // 深链接：详情+核对
  const p2=await browser.newPage({viewport:{width:w,height:h}});
  const err2=[],nonGet=[];
  p2.on('pageerror',e=>err2.push(String(e)));
  p2.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))nonGet.push(r.method()+' '+r.url())});
  const url=q(BASE,{child_id:CHILD,day:DAY,task:TASK,checkup:'1'})+'#checkup';
  await p2.goto(url,{waitUntil:'domcontentloaded'});
  const opened=await p2.waitForSelector('#groveCheckup:not([hidden])',{timeout:20000}).then(()=>true).catch(()=>false);
  await p2.waitForSelector('[data-checkup-photos]',{timeout:10000}).catch(()=>{});
  await p2.waitForTimeout(800);
  const deep=await p2.evaluate(()=>{const s=document.querySelector('.grove-stack'),sc=document.querySelector('.grove-board-scroll');const r=s? s.getBoundingClientRect():null;const panel=document.getElementById('groveCheckup');const d=document.querySelector('.grove-detail');return {rect:r?{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}:null,scrollTop:sc?sc.scrollTop:0,docH:document.documentElement.scrollHeight,rows:document.querySelectorAll('#task-groups article.grove-row').length,step:panel?.dataset.step||'',text:panel?.innerText||'',notice:document.querySelector('[data-grove-deep-notice]')?.innerText||'',url:location.search+location.hash,detailVisible:(()=>{if(!d)return null;const rr=d.getBoundingClientRect();return rr.width>50&&getComputedStyle(d).visibility!=='hidden'})(),photos:!!panel?.querySelector('[data-checkup-photos]'),pick:!!panel?.querySelector('[data-checkup-photo-input]'),startDisabled:panel?.querySelector('[data-checkup-run]')?.disabled===true,hscroll:document.documentElement.scrollWidth-document.documentElement.clientWidth,outline:panel?getComputedStyle(panel).outlineStyle:null,title:document.querySelector('#groveCheckupTitle')?.innerText||document.querySelector('#groveCheckup h2')?.innerText||''}});
  await p2.screenshot({path:`${OUT}/w${w}-checkup.png`,fullPage:false});
  ck(base.rows>0,w+' today list rows>0');
  ck(opened&&deep.photos&&deep.step==='photos',w+' deep link opens checkup photos step');
  ck(/选作业照片/.test(deep.text),w+' checkup shows 选作业照片');
  ck(deep.pick&&deep.startDisabled,w+' photo picker visible & start disabled');
  ck(nonGet.length===0,w+' nonGet empty :: '+JSON.stringify(nonGet));
  ck(!/[?&](task|checkup)=/.test(deep.url)&&!/#checkup/.test(deep.url),w+' url stripped :: '+deep.url);
  ck(!deep.notice,w+' no missing notice');
  ck(JSON.stringify(deep.rect)===JSON.stringify(base.rect)&&deep.scrollTop===base.scrollTop&&deep.docH===base.docH,w+` list unchanged :: base ${JSON.stringify(base)} vs deep ${JSON.stringify({rect:deep.rect,scrollTop:deep.scrollTop,docH:deep.docH})}`);
  ck(deep.rows===base.rows,w+` rows unchanged :: ${base.rows} vs ${deep.rows}`);
  ck(err1.length===0&&err2.length===0,w+' no pageerror :: '+JSON.stringify([...err1,...err2]));
  ck(deep.hscroll<=0,w+' no hscroll');
  ck(deep.outline==='none'||deep.outline===null,w+' checkup outline none :: '+deep.outline);
  metrics[w]={base,deep,nonGet,errors:[...err1,...err2]};
  await p2.close();
 }
 fs.writeFileSync(`${OUT}/metrics.json`,JSON.stringify({failures,widths:metrics},null,2));
 console.log(JSON.stringify({failures},null,2));
 await browser.close();
 if(failures.length)process.exit(1);
})().catch(e=>{console.error(e);process.exit(2)});

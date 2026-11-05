const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
const fs=require('fs');
const OUT=process.env.OUT||'/Users/joyrush/Documents/deepseek-harness/default-workspace/work/surface-evidence/ui7';
const BASE=process.env.BASE||'http://127.0.0.1:8801/?child_id=child-1';
fs.mkdirSync(OUT,{recursive:true});
const widths=[[360,780],[390,844],[768,900],[1024,900],[1200,860],[1440,860]];
const failures=[];const metrics={};const hit={};const spans={};
const ck=(ok,msg)=>{if(!ok)failures.push(msg)};
(async()=>{
const browser=await chromium.launch({headless:true,channel:'chrome'});
for(const [w,h] of widths){
 const page=await browser.newPage({viewport:{width:w,height:h}});
 const errors=[];const nonGet=[];
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))nonGet.push(r.method()+' '+r.url())});
 await page.goto(BASE,{waitUntil:'networkidle'});
 await page.waitForSelector('.grove-stack',{timeout:12000});
 await page.waitForTimeout(300);
 const before=await page.evaluate(()=>{
   const rd=e=>{const b=e.getBoundingClientRect();return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)}};
   const stack=document.querySelector('.grove-stack'),scroll=document.querySelector('.grove-board-scroll'),first=document.querySelector('#task-groups article.grove-row');
   return {rect:rd(stack),scrollRect:rd(scroll),scrollTop:scroll?scroll.scrollTop:0,docH:document.documentElement.scrollHeight,
     first:first?rd(first):null, firstTop:first?Math.round(first.getBoundingClientRect().top):null,
     rows:document.querySelectorAll('#task-groups article.grove-row').length,
     states:[...document.querySelectorAll('#task-groups article.grove-row')].map(x=>(x.querySelector('.grove-state')||{}).dataset?.state||''),
     dots:document.querySelectorAll('#task-groups .grove-state').length,
     legend:document.querySelector('.grove-legend')?.innerText||'',
     countLine:document.querySelector('[data-grove-count]')?.innerText||'',
     title:document.querySelector('#groveListTitle')?.innerText||'',
     hscroll:document.documentElement.scrollWidth-document.documentElement.clientWidth,
     asideW:(document.querySelector('aside')||{}).getBoundingClientRect?Math.round(document.querySelector('aside').getBoundingClientRect().width):0,
     boardW:Math.round(document.querySelector('.grove-board').getBoundingClientRect().width),
     boardX:Math.round(document.querySelector('.grove-board').getBoundingClientRect().x),
     countChips:document.querySelectorAll('[data-grove-count]').length,
     spans:[...document.querySelectorAll('#task-groups article.grove-row')].map(a=>{const sp=a.querySelector('.grove-span');return {key:(a.querySelector('.grove-card-k')?.innerText||'').split('\n')[0],title:a.querySelector('.grove-title')?.innerText||'',span:a.dataset.span||'',days:a.dataset.spanDays||'',bar:a.querySelectorAll('[data-span-bar] i').length,text:sp?sp.innerText:''}}),
     cancelBars:[...document.querySelectorAll('#groveCancelled article')].map(a=>({t:a.innerText.slice(0,24),bar:!!a.querySelector('[data-span-bar]')}))};
 });
 await page.screenshot({path:`${OUT}/w${w}-list.png`});
 // 列表滚到 160 再打开浮层，验证打开前后列表 scrollTop/rect 不变
 await page.evaluate(()=>{const s=document.querySelector('.grove-board-scroll');if(s)s.scrollTop=160});
 await page.waitForTimeout(120);
 const scrollBefore=await page.evaluate(()=>document.querySelector('.grove-board-scroll')?.scrollTop||0);
 await page.locator('[data-grove-open]').first().click();
 await page.waitForTimeout(350);
 const after=await page.evaluate(()=>{
   const rd=e=>{const b=e.getBoundingClientRect();return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)}};
   const stack=document.querySelector('.grove-stack'),scroll=document.querySelector('.grove-board-scroll'),d=document.querySelector('#groveDetail'),bd=document.querySelector('.grove-detail-backdrop');
   const facts=[...document.querySelectorAll('#groveDetail .grove-fact')].map(f=>({role:f.dataset.fact,label:f.querySelector('span')?.innerText||'',strong:f.querySelector('strong')?.innerText||'',rel:f.querySelector('.grove-fact-rel')?.innerText||''}));
   return {view:document.querySelector('.grove3').dataset.view,rect:rd(stack),scrollTop:scroll?scroll.scrollTop:0,docH:document.documentElement.scrollHeight,
     detail:d?{...rd(d),display:getComputedStyle(d).display}:null,
     backdrop:bd?{...rd(bd),display:getComputedStyle(bd).display,opacity:getComputedStyle(bd).backgroundColor}:null,
     title:document.querySelector('[data-detail-title]')?.innerText||document.querySelector('#groveDetail h2')?.innerText||'',
     steps:document.querySelectorAll('#groveDetail [data-detail-line]').length,
     anchors:{title:!!document.querySelector('[data-detail-title]'),lines:document.querySelectorAll('#groveDetail [data-detail-line]').length,plan:!!document.querySelector('#groveDetail [data-family-plan]'),follow:!!document.querySelector('#groveDetail [data-follow-ups]'),source:!!document.querySelector('#groveDetail [data-source-open]'),feedback:!!document.querySelector('#groveDetail [data-feedback-new]'),mark:!!document.querySelector('#groveDetail [data-mark-complete]')},
     facts,timeline:(()=>{const s=document.querySelector('#groveDetail [data-timeline]');return s?{text:s.innerText,span:s.dataset.timelineSpan||'',days:s.dataset.timelineDays||''}:null})(),
     bodyText:(document.querySelector('#groveDetail')?.innerText||'').slice(0,400)};
 });
 await page.screenshot({path:`${OUT}/w${w}-overlay.png`});
 await page.evaluate(()=>document.querySelector('.grove-detail-close')?.click());
 await page.waitForTimeout(220);
 const closed=await page.evaluate(()=>document.querySelector('.grove3')?.dataset.view);
 ck(closed==='list',`${w} overlay did not close: ${closed}`);
 const moved=JSON.stringify(before.rect)!==JSON.stringify(after.rect)||scrollBefore!==after.scrollTop||before.docH!==after.docH;
 ck(!moved,`${w} list rect/scrollTop changed by overlay`);
 ck(errors.length===0,`${w} pageerrors: ${errors.join('|')}`);
 ck(nonGet.length===0,`${w} non-GET: ${nonGet.join('|')}`);
 ck(before.hscroll<=0,`${w} horizontal scroll ${before.hscroll}`);
 ck(after.anchors.title&&after.anchors.lines>0&&after.anchors.feedback&&after.anchors.mark,`${w} detail anchors missing ${JSON.stringify(after.anchors)}`);
 ck(!!after.timeline,`${w} detail timeline missing`);
 if(after.timeline)ck(/布置|今天/.test(after.timeline.text)&&/截止|交回|检查|完成/.test(after.timeline.text),`${w} timeline nodes ${JSON.stringify(after.timeline)}`);
 ck(!/。；/.test(after.bodyText),`${w} 。； in detail`);
 ck(before.dots===before.rows,`${w} state dots ${before.dots} != rows ${before.rows}`);
 const txt=r=>(r.key||'')+' '+(r.title||'');const mathRow=before.spans.find(r=>/数学/.test(txt(r))),engRow=before.spans.find(r=>/英语/.test(txt(r))),readRow=before.spans.find(r=>/朗读/.test(txt(r))),single=before.spans.find(r=>/识字小卡/.test(txt(r)));
 if(w===1440){ck(mathRow&&mathRow.days==='3'&&mathRow.bar>=2,`1440 math span ${JSON.stringify(mathRow)}`);ck(engRow&&engRow.days==='2',`1440 english span ${JSON.stringify(engRow)}`);ck(readRow&&readRow.days==='2',`1440 read span ${JSON.stringify(readRow)}`);ck(single&&!single.days&&single.bar===0,`1440 single-day no bar ${JSON.stringify(single)}`);ck(before.cancelBars.every(c=>!c.bar),`1440 cancelled bars ${JSON.stringify(before.cancelBars)}`);}
 for(const r of before.spans){if(r.days)ck(r.bar>=2&&r.bar<=10,`${w} span bar dots ${JSON.stringify(r)}`)}
 spans[w]=before.spans;
 if(w>=1200){ck(after.detail.w===430,`${w} overlay width ${after.detail.w}`);ck(after.detail.x+after.detail.w<=w+1,`${w} overlay offscreen ${JSON.stringify(after.detail)}`)}
 else if(w<=768){ck(after.detail.h/h>=0.54&&after.detail.h/h<=0.66,`${w} drawer ratio ${after.detail.h}/${h}`)}
 // facts relative (D): find due fact
 const due=after.facts.find(f=>f.role==='due');
 if(due){ck(/^\d{4}-\d{2}-\d{2}$/.test(due.strong),`${w} due strong not ISO: ${JSON.stringify(due)}`);ck(!!due.rel,`${w} due relative missing ${JSON.stringify(due)}`)}
 const complete=after.facts.find(f=>f.role==='complete');
 if(complete){ck(/^(\d{4}-\d{2}-\d{2}|今天 \d{4}-\d{2}-\d{2})$/.test(complete.strong),`${w} complete strong ${complete.strong}`)}
 metrics[w]={mode:w>=1200?'desktop':w>=900?'medium':'phone',viewport:[w,h],firstTop:before.firstTop,firstX:before.first.x,firstW:before.first.w,
   board:{x:before.boardX,w:before.boardW},asideW:before.asideW,rows:before.rows,states:before.states,dots:before.dots,
   legend:before.legend,title:before.title,countLine:before.countLine,countChips:before.countChips,
   stack:{before:before.rect,after:after.rect},scrollTop:[before.scrollTop,after.scrollTop],docH:[before.docH,after.docH],listMoved:moved,
   overlay:after.detail,backdrop:after.backdrop,detailAnchors:after.anchors,detailFacts:after.facts,timeline:after.timeline,spans:before.spans,
   hscroll:before.hscroll,errors,nonGet};
 // hit boxes phone: child filter / chips / day button / tabs
 if(w<=899){
   hit[w]=await page.evaluate(async()=>{
     const box=el=>{const b=el.getBoundingClientRect();return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)}};
     const ok=el=>{const b=el.getBoundingClientRect();const cx=b.left+b.width/2,cy=b.top+b.height/2;const hit=document.elementFromPoint(cx,cy);const four=[[-21,0],[21,0],[0,-21],[0,21]].every(([dx,dy])=>el.contains(document.elementFromPoint(cx+dx,cy+dy)));return {el,hit:el.contains(hit),four,h:Math.round(b.height),box:box(el)}};
     const settle=ms=>new Promise(r=>setTimeout(r,ms));
     const focus=async el=>{el.scrollIntoView({block:'nearest',inline:'center'});await settle(120)};
     const out={};
     const cf=document.querySelector('[data-child-filter]');if(cf){await focus(cf);out.childFilter=ok(cf)}
     const chip=document.querySelector('.grove-chips-row [data-grove-set]');if(chip){await focus(chip);out.setChip=ok(chip)}
     const day=document.querySelector('.grove-bar-later');if(day){await focus(day);out.dayBtn=ok(day)}
     const tab=document.querySelector('.grove-cal-top [data-grove-tab]')||document.querySelector('.grove-cal [data-grove-tab]');if(tab){await focus(tab);out.tab=ok(tab)}
     const add=document.querySelector('.grove-chip.is-add');if(add){await focus(add);out.add=ok(add)}
     const t2=document.querySelector('.grove-chip[data-page="calendar"]');if(t2){await focus(t2);out.calChip=ok(t2)}
     return Object.fromEntries(Object.entries(out).map(([k,v])=>[k,{hit:v.hit,four:v.four,h:v.h,box:v.box}]));
   });
 }
 // close for next iteration
 await page.keyboard.press('Escape');
 await page.close();
}
console.log(JSON.stringify({failures,metrics,hit},null,1));
fs.writeFileSync(`${OUT}/metrics.json`,JSON.stringify({failures,metrics,hit,spans},null,1));
await browser.close();
})().catch(e=>{console.error('FATAL',e);process.exit(1)});

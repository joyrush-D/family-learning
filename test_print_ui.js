// Run: node --test test_print_ui.js. Isolated browser state and HTTP; no printer I/O.
const test=require('node:test'),assert=require('node:assert/strict');
const {readFileSync}=require('node:fs'),vm=require('node:vm'),{randomUUID}=require('node:crypto');
const appSource=readFileSync(__dirname+'/app.js','utf8'),start=appSource.indexOf('let printBusy=');
assert.ok(start>=0,'Printing UI section is present');
const source=appSource.slice(start),copy=x=>JSON.parse(JSON.stringify(x));
const reply=value=>({ok:true,status:200,json:async()=>value});
const preparation=i=>({id:String(i+1).repeat(32),name:['first.pdf','second.pdf'][i],pdf_sha256:'a'.repeat(64),page_count:i?4:8,preview_url:'/api/print/preview/'+String(i+1).repeat(32)});
function harness(storage=new Map()){
  let ctx,html='';const h={calls:[],storage};
  h.fetch=async(path,options)=>{
    const b=options?.body?JSON.parse(options.body):null;
    if(path.endsWith('/prepare'))return reply({preparation:preparation(b.source.name==='first.pdf'?0:1)});
    if(path.endsWith('/enqueue'))return reply({job:{...b,id:b.preparation_id,status:'queued',name:'synthetic.pdf'}});
    return reply({jobs:[]});
  };
  ctx=vm.createContext({page:'print',basePath:'/family/',sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},data:{token:'synthetic-token',attachments:['first.pdf','second.pdf'],uploads:[],printing:{printers:[{name:'Synthetic_Printer',label:'Synthetic',color:true,duplex:true}],jobs:[]}},crypto:{randomUUID},document:{addEventListener(){},querySelectorAll(){return[]}},$:()=>null,endpoint:path=>'/family/'+path.replace(/^\//,''),esc:value=>String(value??'').replaceAll('"','&quot;'),empty:value=>value,toast(){},render:()=>{if(ctx.page==='print')html=ctx.printHTML()},AbortController,setTimeout,clearTimeout,apiFetch:async(path,options)=>{h.calls.push({path,body:options?.body?JSON.parse(options.body):null});return h.fetch(path,options)}});
  vm.runInContext(source,ctx);html=ctx.printHTML();
  Object.assign(h,{ctx,html:()=>html,select(i,checked=true){ctx.selectPrintSource(ctx.printSources()[i].source,checked)},draft(i){return vm.runInContext('printDrafts',ctx).get(JSON.stringify(ctx.printSources()[i].source))},defaults:()=>vm.runInContext('printDefaults',ctx),submit:()=>ctx.submitPrintBatch(),busy:()=>vm.runInContext('printBusy',ctx)});return h;
}
test('page ranges are bounded and invalid input cannot loop',()=>{
  const count=harness().ctx.countPrintPages;
  assert.equal(count('',8),8);assert.equal(count('all',8),8);assert.equal(count('3,1-2,2',8),3);
  for(const v of ['0','01','2-1','9','1,','1 2','1-99999999999999999999',null,[]])assert.throws(()=>count(v,8));
  assert.throws(()=>count('',201));
});
test('one submit prepares all selected files, then enqueues exact page and duplex choices without preview',async()=>{
  const h=harness();h.select(0);h.select(1);h.defaults().sides='two-sided-long-edge';h.draft(0).settings.pages='1-3,5';h.draft(1).settings.pages='2';
  await h.submit();assert.deepEqual(h.calls.map(c=>c.path.split('/').at(-1)),['prepare','prepare','enqueue','enqueue']);
  const jobs=h.calls.filter(c=>c.path.endsWith('/enqueue')).map(c=>c.body);
  assert.equal(jobs[0].pages,'1-3,5');assert.equal(jobs[1].pages,'2');
  for(const j of jobs){assert.equal(j.sides,'two-sided-long-edge');assert.equal(j.copies,1);assert.equal(j.color,'monochrome');assert.equal(j.confirmed,true)}
  assert.notEqual(jobs[0].idempotency_key,jobs[1].idempotency_key);
  assert.equal(h.html().includes('<iframe'),false);assert.equal(h.html().includes('name="confirmed"'),false);
  assert.equal(h.draft(0).submitted,true);assert.equal(h.draft(1).submitted,true);assert.equal(h.busy(),false);
  await h.submit();h.select(0,false);h.select(0);await h.submit();assert.equal(h.calls.length,4);
});
test('a later preparation or page-range failure enqueues nothing and keeps selection',async()=>{
  for(const failure of ['prepare','pages']){
    const h=harness();h.select(0);h.select(1);if(failure==='pages')h.draft(1).settings.pages='5';
    const normal=h.fetch;h.fetch=async(path,options)=>{if(failure==='prepare'&&path.endsWith('/prepare')&&JSON.parse(options.body).source.name==='second.pdf')throw Error('synthetic preparation failed');return normal(path,options)};
    await h.submit();assert.equal(h.calls.filter(c=>c.path.endsWith('/enqueue')).length,0);assert.equal(h.ctx.selectedPrintDrafts().length,2);assert.equal(h.busy(),false);assert.ok(h.draft(1).error);
  }
});
test('partial success and lost reply survive reload; only unresolved payload retries with original key',async()=>{
  const h=harness();h.select(0);h.select(1);h.draft(1).settings.pages='2-3';const normal=h.fetch;let lost;
  h.fetch=async(path,options)=>{if(path.endsWith('/enqueue')&&JSON.parse(options.body).preparation_id===preparation(1).id){lost=JSON.parse(options.body);throw Error('synthetic response lost')}return normal(path,options)};
  await h.submit();assert.equal(h.draft(0).submitted,true);assert.ok(h.draft(1).pending);
  const restored=harness(h.storage);assert.equal(restored.draft(0).submitted,true);assert.deepEqual(copy(restored.draft(1).pending),lost);
  await restored.submit();assert.equal(restored.calls.length,1);assert.deepEqual(restored.calls[0].body,lost);assert.equal(restored.draft(1).submitted,true);
  assert.equal([...h.storage.values()].join('').includes('synthetic-token'),false);
});
test('progress reconciliation survives navigation and a late failed response',async()=>{
  const h=harness();h.select(0);const normal=h.fetch;let reject;
  h.fetch=(path,options)=>path.endsWith('/enqueue')?new Promise((yes,no)=>{reject=no}):normal(path,options);
  const pending=h.submit();while(!reject)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.busy(),true);h.ctx.page='home';
  h.fetch=async()=>reply({jobs:[{id:'c'.repeat(32),preparation_id:preparation(0).id,status:'queued',name:'synthetic.pdf'}]});
  await h.ctx.refreshPrintJobs();reject(Error('synthetic late loss'));await pending;
  assert.equal(h.draft(0).submitted,true);assert.equal(h.draft(0).pending,null);assert.equal(h.draft(0).error,'');assert.equal(h.busy(),false);
});
test('unavailable storage or no authorized printer never enqueues a job',async()=>{
  for(const mode of ['storage','printer']){
    const h=harness();h.select(0);if(mode==='storage')h.storage.set=()=>{throw Error('disabled storage')};else h.ctx.data.printing.printers=[];
    await h.submit();assert.equal(h.calls.filter(c=>c.path.endsWith('/enqueue')).length,0);assert.equal(h.busy(),false);
  }
});
test('legacy v1 single-file pending draft migrates without changing its payload',async()=>{
  const storage=new Map(),src={type:'attachment',name:'first.pdf'},p=preparation(0),settings={printer:'Synthetic_Printer',copies:'2',pages:'1-2',sides:'one-sided',color:'monochrome',confirmed:true};
  const pending={...settings,copies:2,confirmed:true,preparation_id:p.id,pdf_sha256:p.pdf_sha256,idempotency_key:'synthetic-old-enqueue'};
  storage.set('family-print-drafts:v1:/family/',JSON.stringify({selected:JSON.stringify(src),drafts:[[JSON.stringify(src),{source:src,preparation:p,prepareKey:'synthetic-old-prepare',enqueueKey:pending.idempotency_key,submitted:false,pending,settings}]]}));
  const h=harness(storage);assert.equal(h.ctx.selectedPrintDrafts().length,1);await h.submit();assert.equal(h.calls.length,1);assert.deepEqual(h.calls[0].body,pending);
});

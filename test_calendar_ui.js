// Synthetic calendar UI checks. No family API, external service or persistent data.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {readFileSync}=require('node:fs'),{randomUUID}=require('node:crypto');
const source=readFileSync(__dirname+'/calendar.js','utf8');
const clean=x=>JSON.parse(JSON.stringify(x));
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function harness(){
 const elements=new Map(),handlers={},h={calls:[],notices:[],renders:0};
 const names=['id','version','title','category','day','start_time','end_time','location','note','status','repeat','until'];
 const get=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',disabled:false,open:false,classList:{toggle(){}},setAttribute(){},addEventListener(){},showModal(){this.open=true},close(){this.open=false},reset(){},elements:Object.fromEntries(names.map(n=>[n,{value:'',disabled:false}]))});return elements.get(id)};
 h.reply=async()=>({ok:true,status:200,json:async()=>({events:[],timetables:[],source_error:''})});
 const ctx=vm.createContext({data:{today:'2026-09-08',token:'synthetic-first-token',children:[{id:'child-a',name:'小溪'},{id:'child-b',name:'小岚'}],tasks:[]},page:'calendar',child:'',window:{addEventListener(){}},document:{addEventListener(k,f){handlers[k]=f},querySelectorAll(){return[]}},$:get,esc:escape,endpoint:p=>'/family/'+p.replace(/^\//,''),status:t=>t.update.status,taskDismissed:t=>['不参加','不适用'].includes(t.update.status),taskStatusLabel:v=>v==='不适用'?'无需处理':v,render:()=>h.renders++,toast:s=>h.notices.push(s),crypto:{randomUUID},AbortController,setTimeout,clearTimeout,apiFetch:async(p,o)=>{h.calls.push({path:p,...o});return h.reply(p,o)},load:async()=>{},FormData:class{constructor(){return Object.entries(Object.fromEntries(names.map(n=>[n,get('#calendarForm').elements[n].value])))} }});
 vm.runInContext(source,ctx);ctx.calendarHTML();Object.assign(h,{ctx,get,state:()=>vm.runInContext('calendarState',ctx),pending:()=>vm.runInContext('calendarPending',ctx),click:handlers.click});return h;
}
const event=(extra={})=>({id:'a'.repeat(32),version:1,child_ids:['child-a','child-b'],title:'虚构共同阅读',category:'family',day:'2026-09-12',series_day:'2026-09-05',start_time:'',end_time:'',location:'',note:'',status:'tentative',repeat:'weekly',until:'',editable:true,source:'',task_id:'',...extra});
test('date navigation crosses month/year and leap day without local timezone shifts',()=>{
 const h=harness();assert.equal(h.ctx.calendarMonday('2027-01-01'),'2026-12-28');assert.equal(h.ctx.calendarAdd('2024-02-28',1),'2024-02-29');assert.equal(h.ctx.calendarAdd('2026-12-31',1),'2027-01-01');
 h.ctx.calendarNavigate('2027-01-03');assert.deepEqual(clean(h.ctx.calendarDays()),['2026-12-28','2026-12-29','2026-12-30','2026-12-31','2027-01-01','2027-01-02','2027-01-03']);
});
test('shared activities appear once per selected child; read-only schools link to current task',()=>{
 const h=harness(),s=h.state(),items=[event(),event({id:'b'.repeat(32),child_ids:['child-b']})];s.childID='child-a';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,1);s.childID='child-b';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,2);s.childID='';assert.equal(h.ctx.calendarItems(items,'2026-09-12').length,2);
 h.ctx.data.tasks=[{id:'X1',child:'小溪',update:{status:'不适用'}}];const html=h.ctx.calendarEventHTML(event({id:'source:x',task_id:'X1',editable:false,status:'confirmed'}));assert.match(html,/核对原事项/);assert.match(html,/小溪：无需处理/);assert.match(html,/calendar-confirmed/);assert.doesNotMatch(html,/小岚：无需处理|学校已取消/);assert.doesNotMatch(html,/data-calendar-edit/);h.ctx.data.tasks[0].update.status='不参加';assert.match(h.ctx.calendarEventHTML(event({task_id:'X1'})),/小溪：不参加/);h.ctx.data.tasks[0].child='未知归属';assert.doesNotMatch(h.ctx.calendarEventHTML(event({task_id:'X1'})),/家庭决定|：不参加/);
});
test('source/title fields are escaped, missing weekday tables stay explicit and weekend has no missing warning',()=>{
 const h=harness();h.state().result={events:[],timetables:[],source_error:''};assert.match(h.ctx.calendarDayHTML('2026-09-08',1),/尚未提供当天课表/);assert.doesNotMatch(h.ctx.calendarDayHTML('2026-09-12',5),/calendar-missing/);
 const html=h.ctx.calendarEventHTML(event({title:'<img src=x onerror="bad()">',note:'<script>bad()</script>',source:'"<&',status:'cancelled'}));assert.doesNotMatch(html,/<img|<script>/);assert.match(html,/已取消/);assert.match(html,/&lt;img/);assert.match(html,/时间未填写/);
});
test('preparation stays outside collapsed metadata, even without a source',()=>{
 const h=harness(),note='先领取材料\n带上水杯和已经签字的回执',html=h.ctx.calendarEventHTML(event({note,source:'虚构通知'}));
 assert.ok(html.indexOf('class="source calendar-requirements"')<html.indexOf('<details>'));
 assert.ok(html.indexOf(note)<html.indexOf('<details>'));
 assert.ok(html.indexOf('出处：虚构通知')>html.indexOf('<details>'));
 const ordinary=h.ctx.calendarEventHTML(event({note,repeat:'none',source:''}));assert.match(ordinary,/calendar-requirements/);assert.doesNotMatch(ordinary,/<details>/);
 assert.match(h.ctx.calendarEventHTML(event({note:'',source:''})),/起点 2026-09-05/,'weekly rules remain reachable without a source');
});
test('editing a weekly instance starts at the series date and weekend suggestions only open a tentative draft',async()=>{
 const h=harness();h.ctx.calendarOpen(event());assert.equal(h.get('#calendarForm').elements.day.value,'2026-09-05');assert.match(h.get('#calendarEditNote').textContent,/整条/);assert.equal(h.calls.length,0);
 h.get('#calendarWeekendDay').value='2026-09-13';const b={dataset:{calendarDraft:'运动'},hasAttribute(){return false}};await h.click({target:{closest:()=>b}});assert.equal(h.get('#calendarForm').elements.day.value,'2026-09-13');assert.equal(h.get('#calendarForm').elements.status.value,'tentative');assert.equal(h.calls.length,0);
});
test('a late response from a previous week cannot replace the selected week',async()=>{
 const h=harness(),pending=[];h.reply=()=>new Promise(resolve=>pending.push(resolve));const first=h.ctx.calendarRead();h.ctx.calendarNavigate('2026-09-15');const second=h.ctx.calendarRead();
 pending[1]({ok:true,json:async()=>({events:[event({title:'new week'})],timetables:[],source_error:''})});await second;
 pending[0]({ok:true,json:async()=>({events:[event({title:'old week'})],timetables:[],source_error:''})});await first;assert.equal(h.state().result.events[0].title,'new week');assert.equal(h.state().range,'2026-09-14/2026-09-20');
});
test('lost save response preserves body and id; after token refresh retry uses the same body',async()=>{
 const h=harness(),payload={id:'a'.repeat(32),version:0,child_ids:['child-a'],title:'虚构散步'};h.reply=async()=>{throw Error('lost reply')};await assert.rejects(h.ctx.calendarRequest(payload));const body=h.calls[0].body;assert.equal(h.pending(),body);
 h.reply=async()=>({ok:false,status:403,json:async()=>({error:'synthetic auth expired'})});await assert.rejects(h.ctx.calendarRequest({...payload,title:'must not replace pending'}));assert.equal(h.pending(),body);
 // Closing the dialog leaves the pending operation intact. Global load updates data.token.
 h.get('#calendarDialog').close();h.ctx.data.token='synthetic-refreshed-token';h.reply=async()=>({ok:true,status:200,json:async()=>({event:{id:payload.id,version:1}})});await h.ctx.calendarRequest(payload);
 assert.ok(h.calls.every(c=>c.body===body));assert.equal(h.calls.at(-1).headers['X-Family-Token'],'synthetic-refreshed-token');assert.equal(h.pending(),null);
});
test('a definite validation/conflict response permits correction and failed reads can be retried',async()=>{
 const h=harness();for(const status of [400,409]){h.reply=async()=>({ok:false,status,json:async()=>({error:'synthetic rejection'})});await assert.rejects(h.ctx.calendarRequest({id:'a'.repeat(32),version:0}));assert.equal(h.pending(),null)}
 h.reply=async()=>{throw Error('synthetic unavailable')};await h.ctx.calendarRead();assert.match(h.state().error,/unavailable/);h.ctx.calendarInvalidate();h.reply=async()=>({ok:true,json:async()=>({events:[],timetables:[],source_error:'synthetic source gap'})});await h.ctx.calendarRead();assert.equal(h.state().error,'');assert.match(h.ctx.calendarAgendaHTML(),/synthetic source gap/);
});

// Run: node test_reading_ui.js. No real household API, model or printer calls.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {readFileSync}=require('node:fs'),{randomUUID}=require('node:crypto');
const source=readFileSync(__dirname+'/reading.js','utf8');
function harness(storage=new Map()){
 const elements=new Map(),h={calls:[],notices:[],storage};
 h.reply=async()=>({ok:true,status:200,json:async()=>({task:{id:'synthetic-task'}})});
 const context=vm.createContext({basePath:'/family/',crypto:{randomUUID},data:{token:'old-token',children:[]},document:{addEventListener(){},querySelectorAll(){return[]}},$:id=>{if(!elements.has(id))elements.set(id,{onclick(){},onsubmit(){},addEventListener(){},insertAdjacentHTML(where,html){h.notices.push(html)}});return elements.get(id)},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},AbortController,setTimeout,clearTimeout,toast:s=>h.notices.push(s),load:()=>h.load(),apiFetch:async(path,options)=>{h.calls.push({path,...options});if(path==='/api/state')return{ok:true,json:async()=>({token:'fresh-token',children:[]})};return h.reply(path,options)}});
 h.load=async()=>{};vm.runInContext(source,context);h.context=context;h.pending=()=>vm.runInContext('readingPending',context);h.post=(retry=false)=>context.readingRequest('reserve',{child_id:'child-1',reward:'Example walk',cost:1,note:'Synthetic agreement'},retry);return h;
}
test('lost response keeps payload; authorization recovery refreshes token and retains the same key',async()=>{
 const h=harness();h.reply=async()=>{throw Error('response lost')};await assert.rejects(h.post());const body=h.calls[0].body;
 assert.ok(h.pending());await assert.rejects(h.post(),/上次操作/);assert.equal(h.calls.length,1);
 assert.equal([...h.storage.values()].join('').includes('old-token'),false);
 const restored=harness(h.storage);restored.reply=async()=>({ok:false,status:403,json:async()=>({error:'authorization changed'})});await assert.rejects(restored.post(true));assert.equal(restored.pending().obj.request_key,JSON.parse(body).request_key);
 restored.reply=async()=>({ok:true,status:200,json:async()=>({redemption:{id:'synthetic-existing'}})});await restored.post(true);
 const posts=restored.calls.filter(c=>c.body);assert.equal(posts.length,2);assert.ok(posts.every(c=>c.body===body&&c.headers['X-Family-Token']==='fresh-token'));assert.equal(restored.pending(),null);assert.equal(h.storage.size,0);
});
test('known validation errors clear the operation; login errors retain it',async()=>{
 for(const status of [400,401,409]){const h=harness();h.reply=async()=>({ok:false,status,json:async()=>({error:'synthetic error'})});await assert.rejects(h.post());assert.equal(!!h.pending(),status===401)}
});
test('unavailable storage cannot dispatch a mutation',async()=>{
 const h=harness();vm.runInContext('sessionStorage.setItem=()=>{throw Error("storage denied")}',h.context);await assert.rejects(h.post(),/存储/);assert.equal(h.calls.length,0);
});
test('successful save with failed refresh remains visible outside a closed dialog',async()=>{
 const h=harness();h.load=async()=>{throw Error('state unavailable')};await h.context.readingSaved('作品已提交');assert.ok(h.notices.some(s=>s.includes('作品已提交')));assert.ok(h.notices.some(s=>s.includes('data-reading-refresh')));
});

test('reading agreement actions stay visible while source, work and history stay separate',()=>{
 const h=harness();Object.assign(h.context,{esc:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),recordUploads:()=>'',empty:s=>'<p>'+s+'</p>'});h.context.data.tasks=[];
 const task={id:'synthetic-reading',child:'小溪',state:'进行中',book:'虚构叶片观察',scope:'第一节',method:'讲述或画图',criteria:'分享一个发现\n用自己的观察说明',planned_on:'2026-09-12',stamps:1,attachments:[],history:[],work_text:'虚构作品',edition:'虚构版本'};
 const html=h.context.readingCard(task),collapsed=html.indexOf('<details');assert.ok(collapsed>0);
 for(const text of [task.method,task.criteria,task.planned_on])assert.ok(html.indexOf(text)<collapsed,text+' must precede collapsed work');
 assert.ok(html.indexOf(task.work_text)>collapsed);assert.ok(html.indexOf(task.edition)>collapsed);assert.match(html,/<summary>作品、出处与记录<\/summary>/);
 assert.doesNotMatch(h.context.readingCard({...task,method:'<img>',criteria:'<script>'}),/<img>|<script>/);
});

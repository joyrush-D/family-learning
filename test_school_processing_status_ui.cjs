// Fictional data only: the today notice for unprocessed school messages leads to the agent status page and never
// presents the global failed_jobs count as the current child's school batch having stopped.
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const core=fs.readFileSync(__dirname+'/app.js','utf8');
const ctx={data:null,currentChild:()=>ctx.data.children[0]};vm.createContext(ctx);
vm.runInContext(core.slice(core.indexOf('const currentSources='),core.indexOf('function collectionCheckHTML(')),ctx);
const run=agent=>{ctx.data={children:[{id:'SYNTHETIC-A'},{id:'SYNTHETIC-B'}],agent};return vm.runInContext('schoolProcessingHTML()',ctx)};
const src=(child_id,n)=>({id:'src-'+child_id,child_id,pending_message_count:n});
// 1: read succeeded, 6 messages wait for their first processing; no stop is claimed.
let html=run({failed_jobs:0,sources:[src('SYNTHETIC-A',6)]});
assert.match(html,/还有 6 条学校消息尚未整理，作业清单可能不完整。原消息已保存。/);
assert.match(html,/<button data-page="agent">查看整理状态<\/button>/);assert.doesNotMatch(html,/data-page="sources"|自动尝试上限/);
// 3: only the other child has pending messages and a failure; the current child shows nothing.
assert.strictEqual(run({failed_jobs:2,last_error:'另一孩子失败',sources:[src('SYNTHETIC-A',0),src('SYNTHETIC-B',4)]}),'');
// 4: current child pending while a global exhausted count exists; scope stays explicit, never asserted as stopped.
html=run({failed_jobs:1,sources:[src('SYNTHETIC-A',6),src('SYNTHETIC-B',3)]});
assert.match(html,/还有 6 条/);assert.match(html,/另有 1 批资料已达3次自动尝试上限（全部孩子与资料类型合计，未确认是否含这些消息）/);
assert.doesNotMatch(html,/另一孩子|已停止整理这些消息/);
// 5: processing finished, the notice disappears.
assert.strictEqual(run({failed_jobs:0,sources:[src('SYNTHETIC-A',0)]}),'');
// The shared status component keeps the original manual retry and labels its global scope.
const status=core.slice(core.indexOf('function agentStatusHTML('),core.indexOf('let schoolInbox='));
assert.match(status,/批资料仍未整理成功（全部孩子与资料类型合计）：已达3次自动尝试上限，不会自动恢复；原资料保留。 <button data-agent-retry>重新尝试<\/button>/);
console.log('school processing status ok');

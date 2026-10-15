// Fictional SYNTHETIC ORCHARD TEST scope through the exact app.js display helpers; no browser, server, model or real data.
const assert=require('node:assert/strict'),vm=require('node:vm');
const appSource=require('node:fs').readFileSync(require('node:path').join(__dirname,'app.js'),'utf8');
const appFunction=name=>{const m=new RegExp('^function '+name+'\\(.*\\n(?:.*\\n)*?\\}$','m').exec(appSource);assert(m,'app.js defines '+name);return m[0]};
// A minimal element: enough for append/textContent/className, so the rows and the exact text can be read back.
class El{constructor(){this.className='';this.kids=[]}append(...xs){this.kids.push(...xs)}set textContent(v){this.kids=[String(v)]}get textContent(){return this.kids.map(x=>typeof x==='string'?x:x.textContent).join('')}find(name){return this.kids.flatMap(x=>typeof x==='string'?[]:[...(x.className===name?[x]:[]),...x.find(name)])}}
const ctx={document:{createElement:()=>new El()}};
const {homeworkReviewScopeText,homeworkReviewScopeNodes,savedHomeworkReviewParts}=vm.runInNewContext(['homeworkReviewScopeText','homeworkReviewScopeNodes','savedHomeworkReviewParts','savedHomeworkReviewScopeLabel'].map(appFunction).join('\n')+'\n({homeworkReviewScopeText,homeworkReviewScopeNodes,savedHomeworkReviewParts})',ctx);
const pdf='SYNTHETIC ORCHARD TEST.pdf',entries=['题目/孩子作答《'+pdf+'》：共2页，本次第1页；未读取页：2。','教师参考《'+pdf+'》：共2页，本次第2页；未读取页：1。','教师参考《教师附注 SYNTHETIC.txt》：本次读取完整文字。','上一轮待复核意见《作业批改参考-7.txt》：本次读取最新检查；较早草稿保留在原件，未作为本次复核输入。'];
const block=['实际读取范围（程序核对）：',...entries,'仅核对本次所选材料；未读取页及无法对应的题目保持未判定。'].join('\n');
const head='本次1题，0题仍未判定。未列入本次逐题结果的题目和资料范围仍未检查；模型原覆盖说明尚未核明。',coverage=head+'\n实际读取范围：'+entries.join('；');
const text='本次核对1题：需订正1题，与参考一致0题，未判定0题。\n\nSYNTHETIC ORCHARD TEST 第1题 · 需订正\n题面：2+3=?\n卷面作答：4\n参考答案：教师参考：5\n错误依据：4与教师参考5不同。\n订正建议：\n\n覆盖说明：'+head+'\n\n'+block+'\n\n请对照原题核对后保存；本轮结果不代表作业已完成或已经掌握。';
// 1-2) Live structured result: the paragraph text is exactly the old coverage; four materials are four rows, uses and pages complete.
const scope=homeworkReviewScopeText(coverage,'',text),p=new El();homeworkReviewScopeNodes(p,scope,{items:1,unknown_items:0});
assert.equal(p.textContent,scope.coverage,'live scope text stays exactly the same');
const rows=p.find('homework-review-read');assert.equal(rows.length,4,'one row per material use');
assert.deepEqual(rows.map(r=>r.find('homework-review-read-use')[0].textContent),['题目/孩子作答','教师参考','教师参考','上一轮待复核意见']);
assert.match(rows[0].textContent,/共2页，本次第1页；未读取页：2；$/);assert.match(rows[1].textContent,/共2页，本次第2页；未读取页：1；$/);
assert.deepEqual(p.find('homework-review-read-gap').map(x=>x.textContent),['；未读取页：2','；未读取页：1'],'every unread page range stays visible');
assert.deepEqual(p.find('homework-review-redundant').map(x=>x.textContent),['1题，0题仍未判定。'],'only the count equal to the count line is not shown twice');
assert.match(p.textContent,/资料范围仍未检查；模型原覆盖说明尚未核明。/);assert.match(p.textContent,/仅本次所选资料，未判定和未检查部分不算已完成。$/);
// A count that differs, or no structured count, stays shown; an unproven read list stays one verbatim text.
for(const counts of [{items:2,unknown_items:0},false]){const q=new El();homeworkReviewScopeNodes(q,scope,counts);assert.equal(q.textContent,scope.coverage);assert.equal(q.find('homework-review-redundant').length,0)}
const raw=homeworkReviewScopeText(coverage,'',text.replace('上一轮待复核意见','家长改写')),r=new El();homeworkReviewScopeNodes(r,raw,{items:1,unknown_items:0});assert.equal(r.textContent,raw.coverage);assert.equal(r.find('homework-review-read').length,0,'unproven entries are not split');
const noModel=homeworkReviewScopeText(undefined,'',''),n=new El();homeworkReviewScopeNodes(n,noModel,false);assert.equal(n.textContent,noModel.coverage);
// 3) Saved TXT: every character is kept, repeated reads do not add anything, and only the exact program block gets use/gap marks.
const flat=parts=>parts.map(x=>x.parts?flat(x.parts):x.text).join('');
for(let i=0;i<2;i++){const parts=savedHomeworkReviewParts(text);assert.equal(parts.map(x=>x.text).join(''),text);assert.equal(flat(parts),text,'nested parts are verbatim');
 const scopeParts=parts.find(x=>x.kind==='scope').parts;assert.deepEqual(scopeParts.filter(x=>x.kind==='scope-use').map(x=>x.text),['题目/孩子作答','教师参考','教师参考','上一轮待复核意见']);assert.deepEqual(scopeParts.filter(x=>x.kind==='scope-gap').map(x=>x.text),['；未读取页：2。','；未读取页：1。'])}
// 4) Old formats and parent rewrites keep the original as plain text: no use/gap marks and nothing promoted from a prefix.
for(const edited of [text.replace('本次第1页','第1页'),text.replace('实际读取范围（程序核对）：','实际读取范围：'),text.replace('；未读取页：2。','；未读取页：2（家长补）')]){const parts=savedHomeworkReviewParts(edited);assert.equal(flat(parts),edited);assert(!JSON.stringify(parts).includes('scope-gap'),'edited block stays plain')}
const none=text.replace('；未读取页：2。','；未读取页：无。').replace('；未读取页：1。','；未读取页：无。'),noneParts=savedHomeworkReviewParts(none);assert.equal(flat(noneParts),none);assert(!JSON.stringify(noneParts).includes('scope-gap'),'nothing unread, nothing marked');
console.log('review scope display: ok');

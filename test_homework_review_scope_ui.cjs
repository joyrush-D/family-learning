// Fictional SYNTHETIC ORCHARD TEST scope through the exact app.js display helpers; no browser, server, model or real data.
// Real rendering of the same rows is checked by test_homework_text_ui.cjs and test_homework_context_ui.cjs.
const assert=require('node:assert/strict'),vm=require('node:vm');
const appSource=require('node:fs').readFileSync(require('node:path').join(__dirname,'app.js'),'utf8');
const appFunction=name=>{const m=new RegExp('^function '+name+'\\(.*\\n(?:.*\\n)*?\\}$','m').exec(appSource);assert(m,'app.js defines '+name);return m[0]};
// A minimal element: enough for append/textContent/className, so the rows and the exact text can be read back.
class El{constructor(){this.className='';this.dataset={};this.kids=[]}append(...xs){this.kids.push(...xs)}set textContent(v){this.kids=[String(v)]}get textContent(){return this.kids.map(x=>typeof x==='string'?x:x.textContent).join('')}find(name){return this.kids.flatMap(x=>typeof x==='string'?[]:[...(x.className===name?[x]:[]),...x.find(name)])}}
const ctx={document:{createElement:()=>new El()}};
const names=['homeworkReviewScopeText','homeworkReviewScopeNodes','homeworkReviewComparisonNodes','savedHomeworkReviewParts','savedHomeworkReviewScopeLabel','savedHomeworkReviewCount','homeworkReviewCoverageFacts','homeworkReviewComparisonFacts','homeworkReviewReadParts','homeworkReviewNode'];
const app=vm.runInNewContext(names.map(appFunction).join('\n')+'\n({'+names.join(',')+'})',ctx);
// The helpers run in their own VM realm, so their arrays are copied here before deep comparison.
const list=xs=>Array.from(xs,x=>x.textContent??x.text);
const pdf='SYNTHETIC ORCHARD TEST.pdf',entries=['题目/孩子作答《'+pdf+'》：共2页，本次第1页；未读取页：2。','教师参考《'+pdf+'》：共2页，本次第2页；未读取页：1。','教师参考《教师附注 SYNTHETIC.txt》：本次读取完整文字。','上一轮待复核意见《作业批改参考-7.txt》：本次读取最新检查；较早草稿保留在原件，未作为本次复核输入。'];
const block=['实际读取范围（程序核对）：',...entries,'仅核对本次所选材料；未读取页及无法对应的题目保持未判定。'].join('\n');
const facts=['未列入本次逐题结果的题目和资料范围仍未检查；','模型原覆盖说明尚未核明。','已核对所选文字原件的1个明确题号；不代表图片、PDF或未核明题号的完整覆盖。'],head='本次1题，0题仍未判定。'+facts.join(''),coverage=head+'\n实际读取范围：'+entries.join('；');
const text='本次核对1题：需订正1题，与参考一致0题，未判定0题。\n\nSYNTHETIC ORCHARD TEST 第1题 · 需订正\n题面：2+3=?\n卷面作答：4\n参考答案：教师参考：5\n错误依据：4与教师参考5不同。\n订正建议：\n\n覆盖说明：'+head+'\n\n'+block+'\n\n请对照原题核对后保存；本轮结果不代表作业已完成或已经掌握。';
// 1-2) Live structured result: the paragraph text is exactly the old coverage; the validator's facts are short rows and the four material uses are four rows.
const scope=app.homeworkReviewScopeText(coverage,'',text),p=new El();app.homeworkReviewScopeNodes(p,scope,{items:1,unknown_items:0});
assert.equal(p.textContent,scope.coverage,'live scope text stays exactly the same');
assert.deepEqual(list(p.find('homework-review-scope-fact')),[...facts,'仅本次所选资料，未判定和未检查部分不算已完成。'],'one row per fact');
const rows=p.find('homework-review-read');assert.equal(rows.length,4,'one row per material use');
assert.deepEqual(list(rows.map(r=>r.find('homework-review-read-use')[0])),['题目/孩子作答','教师参考','教师参考','上一轮待复核意见']);
assert.deepEqual(list(rows.map(r=>r.find('homework-review-read-name')[0])),['《'+pdf+'》：','《'+pdf+'》：','《教师附注 SYNTHETIC.txt》：','《作业批改参考-7.txt》：'],'full names');
assert.deepEqual(list(rows.map(r=>r.find('homework-review-read-pages')[0])),['共2页，本次第1页；未读取页：2；','共2页，本次第2页；未读取页：1；','读取完整文字；','读取最新检查；较早草稿保留在原件，未作为本次复核输入。'],'total, read and unread pages on their own row');
assert.deepEqual(list(p.find('homework-review-read-gap')),['未读取页：2','未读取页：1'],'every unread page range stays visible');
assert.deepEqual(list(p.find('homework-review-redundant')),['1题，0题仍未判定。'],'only the count equal to the count line is not shown twice');
// A count that differs, or no structured count, stays shown as its own row; an unproven read list stays one verbatim text.
for(const counts of [{items:2,unknown_items:0},false]){const q=new El();app.homeworkReviewScopeNodes(q,scope,counts);assert.equal(q.textContent,scope.coverage);assert.equal(q.find('homework-review-redundant').length,0);assert.deepEqual(list(q.find('homework-review-scope-count')),['1题，0题仍未判定。'])}
const odd=app.homeworkReviewScopeText(coverage.replace('模型原覆盖说明尚未核明。','模型说全部核对完毕。'),'',text),o=new El();app.homeworkReviewScopeNodes(o,odd,{items:1,unknown_items:0});assert.equal(o.textContent,odd.coverage);assert.deepEqual(list(o.find('homework-review-scope-fact')),['未列入本次逐题结果的题目和资料范围仍未检查；模型说全部核对完毕。已核对所选文字原件的1个明确题号；不代表图片、PDF或未核明题号的完整覆盖。','仅本次所选资料，未判定和未检查部分不算已完成。'],'an unknown sentence keeps its facts as one verbatim row');
const raw=app.homeworkReviewScopeText(coverage,'',text.replace('上一轮待复核意见','家长改写')),r=new El();app.homeworkReviewScopeNodes(r,raw,{items:1,unknown_items:0});assert.equal(r.textContent,raw.coverage);assert.equal(r.find('homework-review-read').length,0,'unproven entries are not split');assert.equal(r.find('homework-review-scope-fact').length,0);
const noModel=app.homeworkReviewScopeText(undefined,'',''),n=new El();app.homeworkReviewScopeNodes(n,noModel,false);assert.equal(n.textContent,noModel.coverage);
// 3) Saved TXT: every character is kept, repeated reads add nothing, and the exact program paragraphs become the same rows.
const flat=parts=>parts.map(x=>x.parts?flat(x.parts):x.text).join('');
const kinds=(parts,kind)=>parts.flatMap(x=>[...(x.kind===kind?[x]:[]),...(x.parts?kinds(x.parts,kind):[])]);
for(let i=0;i<2;i++){const parts=app.savedHomeworkReviewParts(text);assert.equal(parts.map(x=>x.text).join(''),text);assert.equal(flat(parts),text,'nested parts are verbatim');
 const s=parts.find(x=>x.kind==='scope').parts;assert.deepEqual(list(kinds(s,'scope-use')),['题目/孩子作答','教师参考','教师参考','上一轮待复核意见']);assert.deepEqual(list(kinds(s,'scope-gap')),['未读取页：2','未读取页：1']);
 assert.deepEqual(list(kinds(s,'scope-label')),['覆盖说明：','实际读取范围（程序核对）：']);assert.deepEqual(list(kinds(s,'scope-fact')),[...facts,'仅核对本次所选材料；未读取页及无法对应的题目保持未判定。','请对照原题核对后保存；本轮结果不代表作业已完成或已经掌握。']);
 // The coverage count equals the exact count line, which is always shown: it is kept in the text but shown once.
 assert.deepEqual(list(kinds(s,'redundant')),['本次1题，0题仍未判定。']);assert.equal(kinds(s,'scope-count').length,0);assert.equal(parts[0].kind,'summary')}
// No equivalent count: a count line that differs, or a text that no longer parses exactly, shows both counts.
for(const other of [text.replace('覆盖说明：本次1题，0题','覆盖说明：本次2题，0题'),text.replace('卷面作答：4','卷面作答：4\n家长补充：看错了')]){const parts=app.savedHomeworkReviewParts(other);assert.equal(flat(parts),other);assert.equal(kinds(parts,'redundant').filter(x=>/仍未判定/.test(x.text)).length,0,'no equivalent count, nothing hidden');assert.equal(kinds(parts,'scope-count').length,1)}
// 4) Old formats and parent rewrites keep the original as plain text: no rows, no marks and nothing promoted from a prefix.
for(const edited of [text.replace('本次第1页','第1页'),text.replace('实际读取范围（程序核对）：','实际读取范围：'),text.replace('；未读取页：2。','；未读取页：2（家长补）'),text.replace('模型原覆盖说明尚未核明。','模型原覆盖说明已核明。')]){const parts=app.savedHomeworkReviewParts(edited);assert.equal(flat(parts),edited);const changed=parts.find(x=>x.text.includes('第1页')&&x.text.includes('《')&&!x.kind)||parts.find(x=>x.text.startsWith('覆盖说明：')&&!x.kind);assert(changed,'the edited paragraph stays one plain part')}
const old='作业检查结果\n第1题：孩子写4，参考5，需订正。\n覆盖说明：本次1题，0题仍未判定。',oldParts=app.savedHomeworkReviewParts(old);assert.equal(flat(oldParts),old);assert.deepEqual(Array.from(oldParts,x=>x.kind),[''],'an old format stays one neutral text');
const none=text.replace('；未读取页：2。','；未读取页：无。').replace('；未读取页：1。','；未读取页：无。'),noneParts=app.savedHomeworkReviewParts(none);assert.equal(flat(noneParts),none);assert.equal(kinds(noneParts,'scope-gap').length,0,'nothing unread, nothing marked');
// 5) The comparison: only the validator's two fixed comparisons become short rows, live and saved; other wording stays one text.
const compare='本次1题未判定，不能沿用上一轮对这些题的确定判定。其他题目以本次逐题结果为准；教师参考和孩子作答分别保留，旧AI意见不作答案依据。',plain='本次复核以逐题结果为准；未列题目仍未检查，旧AI意见不作答案依据。';
for(const [raw,rows] of [[compare,['1题未判定，不能沿用上一轮对这些题的确定判定。','其他题目以本次逐题结果为准；','教师参考和孩子作答分别保留，旧AI意见不作答案依据。']],[plain,['以逐题结果为准；','未列题目仍未检查，旧AI意见不作答案依据。']]]){
 const shown=app.homeworkReviewScopeText(coverage,raw,text).comparison,c=new El();app.homeworkReviewComparisonNodes(c,shown);assert.equal(c.textContent,shown,'the comparison text stays exact');assert.deepEqual(list(c.find('homework-review-scope-fact')),rows);assert.deepEqual(list(c.find('homework-review-scope-label')),['本次复核：']);
 const saved=text.replace('\n\n请对照原题','\n\n本次复核比较（待家长核对）：\n'+raw+'\n\n请对照原题'),parts=app.savedHomeworkReviewParts(saved),s=parts.find(x=>x.kind==='scope').parts;assert.equal(flat(parts),saved);assert.deepEqual(list(kinds(s,'scope-fact')).slice(-rows.length-1,-1),[raw.slice(0,raw.length-rows.slice(1).join('').length),...rows.slice(1)],'the saved comparison is the same rows, its "本次" kept')}
for(const other of ['本次1题未判定，模型说其余都对。','后补参考“字面。；符号”后仍未判定。']){const shown=app.homeworkReviewScopeText(coverage,other,text).comparison,c=new El();app.homeworkReviewComparisonNodes(c,shown);assert.equal(c.textContent,shown);assert.equal(c.find('homework-review-scope-fact').length,0,'other wording stays one text')}
// 6) All matching or all undecided: the count line still opens the text and stays shown, whether or not the focus row has buttons.
for(const [judgment,word,line] of [['correct','与参考一致','本次核对1题：需订正0题，与参考一致1题，未判定0题。'],['unknown','未判定','本次核对1题：需订正0题，与参考一致0题，未判定1题。']]){
 const one=line+'\n\nSYNTHETIC ORCHARD TEST 第1题 · '+word+'\n题面：2+3=?\n卷面作答：5\n参考答案：教师参考：5'+(judgment==='unknown'?'\n不确定：照片中的内容本次无法确认。':'')+'\n\n覆盖说明：本次1题，'+(judgment==='unknown'?1:0)+'题仍未判定。'+facts.join('')+'\n\n'+block+'\n\n请对照原题核对后保存；本轮结果不代表作业已完成或已经掌握。';
 const parts=app.savedHomeworkReviewParts(one);assert.equal(flat(parts),one);assert.deepEqual([parts[0].kind,parts[0].text],['summary',line],'the complete count line stays shown');assert.deepEqual(list(kinds(parts,'redundant')).filter(x=>/仍未判定/.test(x)),['本次1题，'+(judgment==='unknown'?1:0)+'题仍未判定。'],'the coverage count is shown once, by the count line')}
console.log('review scope display: ok');

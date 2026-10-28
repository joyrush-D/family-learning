// 真实上游engine.js（固定e0f931b知识包）+ topic-diagnosis.js逻辑层的契约测试。
// Node：FAMILY_TAXONOMY_DIR=<包目录> node test_topic_diagnosis_ui.cjs
// macOS jsc：jsc test_topic_diagnosis_ui.cjs -- <包目录> <本仓库目录>
// 浏览器360/1440宽度与保存重开/失败重试的界面走查不在本文件，由Root用Playwright另做。
const node = typeof require === 'function';
const argv = node ? [] : (typeof arguments !== 'undefined' ? Array.from(arguments) : []);
const PACK = node ? process.env.FAMILY_TAXONOMY_DIR : argv[0];
const HERE = node ? __dirname : argv[1];
if (!PACK) throw new Error('需要固定知识包目录');
const read = node ? (p => require('fs').readFileSync(p, 'utf8')) : (p => readFile(p));
const say = node ? console.log : print;
let E, T;
if (node) { E = require(PACK + '/diagnose/engine.js'); T = require(HERE + '/topic-diagnosis.js'); }
else { load(PACK + '/diagnose/engine.js'); load(HERE + '/topic-diagnosis.js'); E = globalThis.DiagEngine; T = globalThis.FamilyTopicDiagnosis; }
let passed = 0;
function ok(cond, name) { if (!cond) throw new Error('FAIL: ' + name); passed++; say('ok - ' + name); }

const topics = JSON.parse(read(PACK + '/data/topics.json'));
const deps = JSON.parse(read(PACK + '/data/dependencies.json'));
const questions = JSON.parse(read(PACK + '/data/questions.json'));
const TARGET = 'cnm_010';
// 与family_taxonomy.graph_payload相同：目标点及全部先修，保持文件原顺序。
const pre = {}; deps.forEach(d => (pre[d.topicId] = pre[d.topicId] || []).push(d.prerequisiteId));
const ids = new Set(); const stack = [TARGET];
while (stack.length) { const t = stack.pop(); if (ids.has(t)) continue; ids.add(t); (pre[t] || []).forEach(p => stack.push(p)); }
const sub = E.buildGraph(topics.filter(t => ids.has(t.id)), deps.filter(d => ids.has(d.topicId) && ids.has(d.prerequisiteId)), questions.filter(q => ids.has(q.topicId)));
const full = E.buildGraph(topics, deps, questions);
ok(E.DEFAULT_CONFIRM === 3, 'upstream default confirm is 3 consecutive correct answers');
ok(['createSession', 'nextItem', 'judgeQuestion', 'applyAnswer', 'summarize', 'replay', 'questionById'].every(k => typeof E[k] === 'function'), 'engine exports the functions the panel calls');

const opts = { limit: 8, seed: 'contract-seed-0001' };
let s = E.createSession(sub, [TARGET], opts), f = E.createSession(full, [TARGET], opts);
const script = ['wrong', 'wrong', 'correct', 'skip', 'correct', 'correct', 'correct', 'wrong'];
const facts = [];
for (const r of script) {
  const a = E.nextItem(sub, s), b = E.nextItem(full, f);
  if (!a) break;
  ok(b && a.question.id === b.question.id, 'subgraph payload picks the same question as the full pack: ' + a.question.id);
  const text = r === 'correct' ? String(a.question.answer) : r === 'wrong' ? '___' : '';
  const j = T.judge(E, a.question, r === 'skip' ? 'skip' : 'answer', text);
  s = E.applyAnswer(sub, s, a.topicId, j.engine, { text }); f = E.applyAnswer(full, f, b.topicId, j.engine, { text });
  facts.push({ seq: facts.length + 1, topic_id: a.topicId, qid: a.question.id, engine_result: j.engine, answer: text, verdict: j.verdict });
}
ok(facts.length > 0 && facts.every(x => ['correct', 'wrong', 'skip'].includes(x.engine_result)), 'every saved item maps to an upstream result');
const diag = { id: 7, topic_id: TARGET, opts, items: facts, retries: [] };
const restored = T.restore(E, sub, diag);
ok(restored && JSON.stringify(restored.answers) === JSON.stringify(s.answers), 'refresh restores the same upstream session from saved items');
ok(T.restore(E, sub, { ...diag, items: facts.map((x, k) => k ? x : { ...x, qid: 'cnm_x_q9' }) }) === null, 'a saved qid the engine would not pick blocks continuing');
const sum = E.summarize(sub, s), lines = T.summaryLines(sub, s, E);
ok(lines.length > 0 && lines.every(l => !/已掌握|掌握了/.test(l.label)), 'summary wording never says mastered: ' + lines.map(l => l.label).join(' | '));
ok(!sum.mastered.some(id => s.status[id].src === 'inferred') || lines.some(l => l.label === T.STATUS.mastered_inferred), 'inferred ancestors are labelled as graph inference');
ok(T.judge(E, { type: 'self', prompt: 'x' }, 'answer', 'x').engine === 'skip', 'manual verdict goes to the engine as skip, never as correct');
ok(T.judge(E, { type: 'numeric', answer: '0.5' }, 'answer', '1/2').verdict === 'correct', 'upstream numeric judge accepts 1/2 for 0.5 (a case DeepTutor text grading can disagree with)');
// 新题再试：真实原题集先滤掉同孩历次见过的题号（服务端state.seen_qids），再交原buildGraph/createSession/nextItem。
const raw = { topics: topics.filter(t => ids.has(t.id)), dependencies: deps.filter(d => ids.has(d.topicId) && ids.has(d.prerequisiteId)), questions: questions.filter(q => ids.has(q.topicId)) };
const seen1 = T.seenQids({ seen_qids: facts.map(x => x.qid) });
const r1 = T.retryItem(E, raw, sub, diag, seen1);
ok(r1 && !seen1.has(r1.question.id), 'retry offers a question this child never saw in any diagnosis: ' + (r1 && r1.question.id));
const earlier = new Set([...seen1, r1.question.id]);
const r2 = T.retryItem(E, raw, sub, diag, earlier);
ok(!r2 || !earlier.has(r2.question.id), 'a question shown in an earlier diagnosis is never offered as new again: ' + (r2 && r2.question.id));
const bank = sub.bank[TARGET].map(q => q.id);
const allButLast = new Set(bank.slice(0, -1));
const avoidOnly = E.nextItem(sub, E.createSession(sub, [TARGET], { limit: 1, seed: 'retry-7', avoid: [...allButLast] }));
const r3 = T.retryItem(E, raw, sub, diag, allButLast);
ok(r3 && !allButLast.has(r3.question.id), 'with unseen questions left the filtered bank still offers one (avoid-only picked ' + (avoidOnly && avoidOnly.question.id) + ', filtered picked ' + (r3 && r3.question.id) + ')');
ok(T.retryItem(E, raw, sub, diag, new Set(bank)) === null, 'when every target question was seen there is no new question (no seed change)');
const one = E.buildGraph(raw.topics, raw.dependencies, raw.questions.filter(q => q.topicId !== TARGET || q.id === bank[bank.length - 1]));
ok(E.needConfirm(sub, null, TARGET) === 3 && E.needConfirm(one, null, TARGET) === 1, 'filtering changes upstream needConfirm (3 -> 1), so a single retry only records this attempt');
// 原答上限：真实judgeQuestion对cnm_010_q4的501字A/B（同前缀只差末字）与500字边界都判错；服务端整笔保存或整笔400，不截断。
const q4 = E.questionById(full, 'cnm_010_q4');
ok(T.ANSWER_MAX === 500 && ['0'.repeat(500) + '1', '0'.repeat(500) + '2', '0'.repeat(499) + '1'].every(t => E.judgeQuestion(q4, t).verdict === 'wrong'), 'real judgeQuestion: q4 501-char A/B and the 500-char boundary answer are all wrong');
const panelCode = read(HERE + '/topic-diagnosis.js').split('\n').filter(l => !l.trim().startsWith('//')).join('\n');
ok(!/上游判题|DeepTutor判定|两个判题器|上游：|DeepTutor：/.test(panelCode) && panelCode.includes("field(p,k,'写答案',ANSWER_MAX)") && panelCode.includes(' maxlength="${max}"'), 'panel says 题库核对/复核结果/两项检查; answer inputs carry maxlength=500');
say(passed + ' passed');

// Drive the product's browser diagnosis engine (knowledge pack engine.js) exactly like topic-diagnosis.js does.
const fs = require('fs');
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
function wrongAnswer(q) {
  if (q.type === 'choice') {
    const ans = String(q.answer == null ? '' : q.answer).trim().toUpperCase();
    return ['A', 'B', 'C', 'D', 'E', 'F'].find(c => c !== ans) || 'A';
  }
  const n = Number(q.answer);
  return Number.isFinite(n) ? String(n + 1) : '0';
}
const E = require(job.engine);
const full = E.buildGraph(job.graph.topics, job.graph.dependencies, job.graph.questions);
let out = { ok: true };
if (job.mode === 'retry') {
  const seen = new Set(job.seen || []);
  const qs = job.graph.questions.filter(q => !seen.has(q.id));
  const g = E.buildGraph(job.graph.topics, job.graph.dependencies, qs);
  const s = E.createSession(g, [job.topic_id], { limit: 1, seed: 'retry-' + job.diagnosis_id });
  const it = E.nextItem(g, s);
  const orig = it && E.questionById(full, it.question.id);
  out.item = it && !seen.has(it.question.id) && orig && orig.prompt === it.question.prompt
    ? { qid: it.question.id, topic_id: it.topicId, prompt: it.question.prompt, type: it.question.type, answer: it.question.answer }
    : null;
  out.remaining = qs.length;
} else {
  let s = E.createSession(full, [job.topic_id], job.opts || { limit: 8, seed: job.seed });
  const steps = [];
  for (const a of (job.script || [])) {
    const it = E.nextItem(full, s);
    if (!it) break;
    const text = a.text === '@auto' ? String(it.question.answer == null ? '' : it.question.answer)
      : a.text === '@wrong' ? wrongAnswer(it.question) : String(a.text);
    const v = E.judgeQuestion(it.question, text).verdict;
    const er = v === 'manual' ? 'skip' : v;
    s = E.applyAnswer(full, JSON.parse(JSON.stringify(s)), it.topicId, er, { text });
    const summary = E.summarize(full, s);
    steps.push({ seq: steps.length + 1, topic_id: it.topicId, qid: it.question.id, prompt: it.question.prompt,
      type: it.question.type, expected: it.question.answer, text, verdict: v, engine_result: er,
      session: s, summary });
    if (summary.finished) break;
  }
  out.steps = steps;
  out.summary = E.summarize(full, s);
}
console.log(JSON.stringify(out));

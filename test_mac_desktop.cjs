// 一起成长桌面入口（packaging/macos，AppKit + WKWebView）内部候选验收。Disposable synthetic demo only;
// no family data, LAN, model, printer, TCC permission or service control. Needs macOS with a logged-in GUI session
// and the system swiftc. The app runs in its explicit test mode: separate Support directory, a declared fictional
// origin, non-persistent WebKit data and no saved window frame. Optional FAMILY_DESKTOP_EVIDENCE_DIR keeps the
// line log and WebKit/native snapshots; optional PLAYWRIGHT_MODULE / PLAYWRIGHT_CHANNEL for the Chrome baseline.
// The homework flow uses the current original entry, as in test_homework_feedback_review_ui.cjs: [data-homework-new] →
// #homeworkInputDialog → saved task → #taskDialog feedback → hand-written wrong item → [data-followup] correction → reopen.
const assert = require('node:assert/strict');
const {spawn, execFileSync} = require('node:child_process');
const {once} = require('node:events');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const {setTimeout: delay} = require('node:timers/promises');

const root = __dirname;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'synthetic-mac-desktop-'));
const evidence = process.env.FAMILY_DESKTOP_EVIDENCE_DIR || '';
const log = {};

async function freePort() {
  const s = net.createServer(); s.listen(0, '127.0.0.1'); await once(s, 'listening');
  const port = s.address().port; await new Promise(r => s.close(r)); return port;
}
async function get(url) {
  return new Promise(resolve => http.get(url, {agent: false}, res => { let body = ''; res.on('data', d => body += d); res.on('end', () => resolve({status: res.statusCode, body})); })
    .on('error', () => resolve(null)));
}
function supportDir(name, origin, extra = {}) {
  const dir = path.join(tmp, name); fs.mkdirSync(dir, {recursive: true});
  if (origin) fs.writeFileSync(path.join(dir, 'desktop.json'), JSON.stringify({service_origin: origin, ...extra}));
  return dir;
}
const configured = dir => fs.existsSync(path.join(dir, 'desktop.json')) ? JSON.parse(fs.readFileSync(path.join(dir, 'desktop.json'), 'utf8')) : null;
const mode = p => { try { return fs.statSync(p).mode & 0o777; } catch { return null; } };
const privateModes = dir => [mode(dir), mode(path.join(dir, 'desktop.json'))];
// Runs the real .app executable; every JSON line it prints is collected. Never kills anything but itself.
// Ends with the exit code, 'timeout' (overall limit) or 'stalled after …' (no line for `idle` ms); its timers are cleared when it ends.
function runApp(exe, name, dir, env = {}, onLine = () => {}, {limit = 90000, idle = 60000} = {}) {
  const shots = evidence ? path.join(evidence, 'snapshots', name) : '';
  if (shots) fs.mkdirSync(shots, {recursive: true});
  const proc = spawn(exe, ['--smoke-test'], {env: {...process.env, FAMILY_DESKTOP_SUPPORT_DIR: dir, FAMILY_DESKTOP_TEST_SNAPSHOT_DIR: shots, ...env}, stdio: ['ignore', 'pipe', 'pipe']});
  const lines = []; let buffer = '', total, quiet;
  const done = new Promise(resolve => {
    const end = value => { clearTimeout(total); clearTimeout(quiet); resolve(value); };
    const kill = reason => { proc.kill('SIGKILL'); end(reason); };
    const watch = () => { clearTimeout(quiet); quiet = setTimeout(() => { const l = lines.at(-1) || {}; kill(`stalled after ${l.state || 'start'} ${l.name || ''}`.trim()); }, idle); };
    total = setTimeout(() => kill('timeout'), limit);
    watch();
    proc.stdout.on('data', d => { watch(); buffer += d; let i; while ((i = buffer.indexOf('\n')) >= 0) { const line = buffer.slice(0, i); buffer = buffer.slice(i + 1);
      try { const value = JSON.parse(line); lines.push(value); onLine(value); } catch {} } });
    proc.once('close', code => end(code));
  });
  log[name] = lines;
  return {proc, lines, done};
}
async function exitWithin(proc, ms) {
  let timer; const late = new Promise(r => { timer = setTimeout(r, ms, 'late'); });
  const result = await Promise.race([once(proc, 'exit').then(() => 'exited'), late]); clearTimeout(timer); return result;
}
const states = run => run.lines.map(l => l.state);
// Parent-facing native text never exposes the internal file, its format or developer commands.
function plainMessages(run, dir) {
  for (const l of run.lines) for (const text of [l.message || '', l.typed || ''])
    assert(!/desktop\.json|Application Support|service_origin|[{}]|python|launchctl/.test(text) && !text.includes(dir), 'internal detail shown: ' + text);
}

// Steps run by the app inside the isolated script world of the real WKWebView (original page, fictional data). Each step's
// js acts once; the app then polls `until` natively within `timeout` seconds and reports the real state on failure.
const TITLE = w => '虚构口头作业 ' + w;
const GOAL = '朗读第三课两遍，家长听后签字';
const NOTE = w => '虚构反馈：已朗读两遍（' + w + '）';
const CORRECTION = w => '虚构订正：第二段补读一遍（' + w + '）';
const DRAFT = '虚构未保存的反馈草稿';
const FILE_NAME = '虚构-口头作业照片.png';
const q = JSON.stringify;
const LAYOUT = 'width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,visibility:document.visibilityState';
const SET = "const set=(el,v)=>{el.focus();el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}))};";
const TEXT = "const text=x=>x.innerText.replace(/\\s+/g,' ').trim();";
const ITEM = "const d=document.querySelector('#homeworkInputDialog');const item=d&&(d.querySelector('form[data-homework-item=\"0\"]')||d.querySelector('form[data-homework-item]'));";
// Read-only lookup of the saved homework through the original API; every write below goes through the original forms.
const STATE = title => `const st=await (await fetch('/api/state',{cache:'no-store'})).json();const task=st.tasks.find(t=>t.title===${q(title)});if(!task)return {ok:false,reason:'homework not in api/state'};`;
// Select the actual list row first; the feedback entry now belongs to its own detail (phone: list -> detail).
const openTask = title => `${STATE(title)}const back=document.querySelector('[data-grove-back]');if(back?.offsetParent){back.click();await new Promise(r=>setTimeout(r,100));}const row=[...document.querySelectorAll('[data-grove-open="'+task.id+'"]')].find(x=>x.offsetParent);if(row){row.click();await new Promise(r=>setTimeout(r,100));}const b=[...document.querySelectorAll('#groveDetail [data-task="'+task.id+'"], [data-task="'+task.id+'"]')].find(x=>x.offsetParent);if(!b)return {ok:false,reason:'no visible own detail feedback entry',id:task.id};b.click();return {ok:true,id:task.id};`;
const reopenCheck = w => `${STATE(TITLE(w))}const answer=st.records.find(r=>r.source==='事项:'+task.id),wrong=st.records.find(r=>r.source==='错题照片核对'&&r.linked_task_id===task.id),corr=wrong&&st.records.find(r=>r.related_record_id===wrong.id);
const h=document.querySelector('#taskFeedbackHistory').innerText;
return {ok:document.querySelector('#taskDialog').open&&h.includes(${q(NOTE(w))})&&h.includes(${q(CORRECTION(w))}),history_has_note:h.includes(${q(NOTE(w))}),history_has_correction:h.includes(${q(CORRECTION(w))}),history_has_wrong:/错题/.test(h),
wrong_related_to_answer:!!answer&&!!wrong&&wrong.related_record_id===answer.id,correction_kind:corr?corr.followup_kind:'',correction_note:corr?corr.note:'',task_update:task.update??null,${LAYOUT}};`;

function flowSteps(w, guard) {
  const title = TITLE(w);
  return [
    // Page visibility in this session (an occluded window makes WebKit treat the page as hidden); recorded, never required.
    {name: 'page_state_' + w, required: false, timeout: 10, js: "return {ok:true,visibility:document.visibilityState,raf:await Promise.race([new Promise(r=>requestAnimationFrame(()=>r(true))),new Promise(r=>setTimeout(()=>r(false),1500))])};"},
    {name: 'homework_open_' + w, width: w,
     js: "const b=[...document.querySelectorAll('button[data-homework-new]')].find(x=>x.offsetParent&&!x.disabled);if(!b)return {ok:false,reason:'no visible [data-homework-new]'};b.click();return {ok:true,via:b.textContent.trim()};",
     until: `${ITEM}return {ok:!!(d&&d.open&&item&&item.querySelector('[name=title]').offsetParent),item:item?item.dataset.homeworkItem:'',is_record_dialog:document.querySelector('#recordDialog').open,${LAYOUT}};`},
    {name: 'homework_fill_' + w,
     js: `${SET}${ITEM}if(!item)return {ok:false,reason:'no [data-homework-item] form'};set(item.querySelector('[name=title]'),${q(title)});set(item.querySelector('[name=goal]'),${q(GOAL)});return {ok:item.querySelector('[name=title]').value===${q(title)},item:item.dataset.homeworkItem};`},
    {name: 'homework_file_' + w, required: false,
     js: "const f=document.querySelector('#homeworkInputDialog input[type=file][data-homework-files]');if(!f)return {ok:false,reason:'no [data-homework-files]'};f.click();return {ok:true};",
     until: `${TEXT}const rows=[...document.querySelectorAll('#homeworkInputDialog .homework-files > div')].map(text);return {ok:rows.some(t=>t.includes(${q(FILE_NAME)})&&/原件已保存/.test(t)),rows};`},
    {name: 'homework_save_' + w,
     js: `const d=document.querySelector('#homeworkInputDialog'),item=[...d.querySelectorAll('form[data-homework-item]')].find(f=>f.querySelector('[name=title]').value===${q(title)});if(!item)return {ok:false,reason:'the filled homework form is gone',forms:d.querySelectorAll('form[data-homework-item]').length};item.querySelector('[type=submit]').click();return {ok:true,item:item.dataset.homeworkItem};`,
     until: `${TEXT}const d=document.querySelector('#homeworkInputDialog'),s=[...d.querySelectorAll('.homework-saved')].find(x=>x.innerText.includes(${q(title)}));return {ok:!!s,saved:s?text(s):'',files:[...d.querySelectorAll('.homework-files > div')].map(text),
dialog:text(d).slice(0,700),invalid:[...d.querySelectorAll('form[data-homework-item] [name]')].filter(e=>e.willValidate&&!e.checkValidity()).map(e=>e.name+':'+e.validationMessage),${LAYOUT}};`},
    {name: w + '-homework-saved', native: 'snapshot'},
    {name: 'homework_close_' + w, js: "document.querySelector('#homeworkInputDialog [data-homework-close]').click();return {ok:true};",
     until: "return {ok:!document.querySelector('#homeworkInputDialog').open};"},
    {name: 'task_open_' + w, js: openTask(title),
     until: `return {ok:document.querySelector('#taskDialog').open&&!!document.querySelector('#taskForm textarea[name=note]').offsetParent,heading:document.querySelector('#taskTitle').textContent,${LAYOUT}};`},
    // Microphone only in the visible feedback form: the test app always denies, and the same form must stay usable.
    {name: 'mic_denied_' + w, required: false,
     js: "if(document.visibilityState!=='visible')return {ok:false,skipped:'page hidden (window occluded in this session): WebKit holds the capture request until the page is visible, so the denial cannot be exercised here',visibility:document.visibilityState};const b=document.querySelector('#taskDialog #recordAudio');if(!b||!b.offsetParent)return {ok:false,reason:'no visible #recordAudio in the open #taskDialog'};b.click();return {ok:true};",
     until: "const s=document.querySelector('#uploadStatus'),b=document.querySelector('#taskDialog #recordAudio');return {ok:/未能开启麦克风|暂不支持录音/.test(s.textContent),status:s.textContent,record_enabled:!b.disabled,save_enabled:!document.querySelector('#saveTaskFeedback').disabled,note_enabled:!document.querySelector('#taskForm textarea[name=note]').disabled,dialog_open:document.querySelector('#taskDialog').open};"},
    {name: w + '-task-mic-denied', native: 'snapshot'},
    ...(guard ? [
      {name: 'draft_typed_' + w, js: `${SET}set(document.querySelector('#taskForm textarea[name=note]'),${q(DRAFT)});return {ok:true};`},
      {name: 'change_address_keep', native: 'change_address'},
      {name: 'close_esc_quit', native: 'close_attempts'},
      {name: 'draft_kept_' + w, js: `const n=document.querySelector('#taskForm textarea[name=note]');return {ok:document.querySelector('#taskDialog').open&&n.value===${q(DRAFT)},note:n.value,${LAYOUT}};`},
    ] : []),
    {name: 'feedback_save_' + w, js: `${SET}set(document.querySelector('#taskForm textarea[name=note]'),${q(NOTE(w))});document.querySelector('#saveTaskFeedback').click();return {ok:true};`,
     until: "const s=document.querySelector('#taskFeedbackStatus').textContent,f=document.querySelector('#taskFeedbackHistory [data-task-wrong-form]');return {ok:/反馈已保存/.test(s)&&!!f,status:s,error:document.querySelector('#taskError').textContent,feedback_id:f?f.dataset.taskWrongForm:''};"},
    {name: 'wrong_save_' + w,
     js: `${SET}const f=document.querySelector('#taskFeedbackHistory [data-task-wrong-form]');if(!f)return {ok:false,reason:'no [data-task-wrong-form]'};if(!f.open)f.querySelector(':scope > summary').click();set(f.querySelector('[data-wrong-field="label"]'),'第二段');set(f.querySelector('[data-wrong-field="answer"]'),'漏读一句');set(f.querySelector('[data-wrong-field="correction"]'),'补读整段');f.querySelector('[data-task-wrong-save]').click();return {ok:true,feedback_id:f.dataset.taskWrongForm};`,
     until: "const s=document.querySelector('#taskFeedbackStatus').textContent;return {ok:/错题已保存在这份作业下/.test(s),status:s};"},
    // As in the reference flow, the same original homework is reopened and the saved wrong item shows as its own card.
    {name: 'wrong_card_' + w, js: `document.querySelector('#taskDialog [data-close="taskDialog"]').click();${openTask(title)}`,
     until: `${STATE(title)}const wrong=st.records.find(r=>r.source==='错题照片核对'&&r.linked_task_id===task.id),answer=st.records.find(r=>r.source==='事项:'+task.id);const card=wrong&&[...document.querySelectorAll('#taskFeedbackHistory .task-feedback-record')].find(c=>c.querySelector('[data-record="'+wrong.id+'"]'));
return {ok:document.querySelector('#taskDialog').open&&!!card&&!!card.querySelector('[data-followup]'),wrong_id:wrong?wrong.id:null,wrong_related_to_answer:!!wrong&&!!answer&&wrong.related_record_id===answer.id,card:card?card.innerText.replace(/\\s+/g,' ').slice(0,200):''};`},
    {name: 'correction_open_' + w,
     js: `${STATE(title)}const wrong=st.records.find(r=>r.source==='错题照片核对'&&r.linked_task_id===task.id);if(!wrong)return {ok:false,reason:'wrong item not in api/state'};const card=[...document.querySelectorAll('#taskFeedbackHistory .task-feedback-record')].find(c=>c.querySelector('[data-record="'+wrong.id+'"]'));const b=card&&([...card.querySelectorAll('[data-followup]')].find(x=>x.dataset.followupKind==='订正')||card.querySelector('[data-followup]'));if(!b)return {ok:false,reason:'no [data-followup] on the wrong-item card',wrong_id:wrong.id};b.click();return {ok:true,wrong_id:wrong.id,kind:b.dataset.followupKind||''};`,
     until: `const f=document.querySelector('#recordForm'),t=document.querySelector('#recordFollowupTask');return {ok:document.querySelector('#recordDialog').open&&!document.querySelector('#taskDialog').open,followup_kind:f.elements.followup_kind.value,related:f.elements.related_record_id.value,task:t?t.innerText:'',${LAYOUT}};`},
    {name: w + '-correction-form', native: 'snapshot'},
    {name: 'correction_save_' + w, js: `${SET}set(document.querySelector('#recordForm [name=note]'),${q(CORRECTION(w))});document.querySelector('#recordForm [type=submit]').click();return {ok:true};`,
     until: "const e=document.querySelector('#recordError');return {ok:!document.querySelector('#recordDialog').open,error:e?e.textContent:''};"},
    {name: 'reopen_' + w, js: openTask(title), until: reopenCheck(w)},
    {name: w + '-reopened', native: 'snapshot'},
    {name: 'reopen_close_' + w, js: "document.querySelector('#taskDialog [data-close=\"taskDialog\"]').click();return {ok:true};",
     until: "return {ok:!document.querySelector('#taskDialog').open};"},
  ];
}

(async () => {
  let demo, other;
  const problems = [];
  const check = (ok, message) => { if (!ok) problems.push(message); };
  const unverified = [];  // checks this session cannot exercise (reported, never counted as passed)
  const same = (a, b) => { try { assert.deepEqual(a, b); return true; } catch { return false; } };
  try {
    const out = path.join(tmp, 'build');
    const app = execFileSync(path.join(root, 'packaging/macos/build.sh'), [out], {encoding: 'utf8'}).trim().split('\n').pop();
    const exe = path.join(app, 'Contents/MacOS/YiqiChengzhang');
    const selfTest = JSON.parse(execFileSync(exe, ['--self-test'], {encoding: 'utf8'}));
    assert.equal(selfTest.self_test, 'pass', JSON.stringify(selfTest));

    const port = await freePort(), origin = `http://127.0.0.1:${port}`;
    // The demo gets a minimal environment: no family paths and no model credentials from the caller.
    const env = {}; for (const k of ['PATH', 'HOME', 'TMPDIR', 'LANG']) if (process.env[k]) env[k] = process.env[k];
    demo = spawn(process.env.FAMILY_TEST_PYTHON || 'python3', ['demo.py', '--port', String(port)], {cwd: root, env, stdio: ['ignore', 'ignore', 'pipe']});
    for (let n = 0; n < 200 && !(await get(origin + '/'))?.status; n++) await delay(100);
    assert.equal((await get(origin + '/')).status, 200);
    process.env.FAMILY_DESKTOP_TEST_ORIGIN = origin;
    const closed = await freePort();
    const otherPort = await freePort();
    other = http.createServer((q, r) => r.end('hello')).listen(otherPort, '127.0.0.1'); await once(other, 'listening');

    // 0. Test mode refuses the user's default Support directory, a missing one, or an undeclared origin.
    const defaultSupport = path.join(os.homedir(), 'Library/Application Support/local.yiqichengzhang.desktop');
    for (const [label, extra] of [['no-dir', {FAMILY_DESKTOP_SUPPORT_DIR: ''}], ['default-dir', {FAMILY_DESKTOP_SUPPORT_DIR: defaultSupport}],
                                  ['no-origin', {FAMILY_DESKTOP_SUPPORT_DIR: path.join(tmp, 'refused'), FAMILY_DESKTOP_TEST_ORIGIN: ''}]]) {
      const refused = execFileSync('/bin/sh', ['-c', '"$0" --smoke-test; echo "exit=$?"', exe], {env: {...process.env, ...extra}, encoding: 'utf8'});
      assert.match(refused, /"test_mode_refused"[\s\S]*exit=2/, label);
    }
    assert(!fs.existsSync(path.join(tmp, 'refused')), 'refused test mode created no Support directory');

    // 1. Configured origin opens directly in a real WKWebView; second launch only focuses the first instance.
    const dir = supportDir('main', origin);
    let second;
    const first = runApp(exe, 'configured', dir, {FAMILY_DESKTOP_SMOKE_HOLD: '4'}, line => {
      if (line.state === 'loaded') second = runApp(exe, 'second-instance', dir);
    });
    assert.equal(await first.done, 0, JSON.stringify(first.lines));
    const loaded = first.lines.find(l => l.state === 'loaded');
    assert(loaded, 'loaded: ' + JSON.stringify(first.lines));
    assert(!states(first).includes('setup_shown'), 'a valid saved address opens without the form');
    assert.equal(loaded.origin, origin);
    assert.deepEqual(loaded.widths.map(w => w.width), [360, 1440], 'actual WKWebView innerWidth');
    for (const w of loaded.widths) {
      assert.equal(w.overflow, false, 'no horizontal overflow at ' + w.width);
      assert(w.child_filters >= 1 && w.buttons >= 1, 'single-child list controls at ' + w.width);
      assert.equal(w.all_children, false);
      assert(w.href.startsWith(origin + '/'));
    }
    assert.equal(loaded.location_origin_after_attempts, origin, 'blocked navigations leave the original page');
    // file: is refused by WebKit itself before the policy delegate; the unchanged origin above covers it.
    for (const target of ['data:text/html,x', `@example.invalid`, `:${port + 1}/`, 'x-apple.systempreferences:'])
      assert(loaded.blocked.some(u => u.includes(target)), 'blocked ' + target + ' ' + JSON.stringify(loaded.blocked));
    assert.equal(loaded.unsaved_after_steps, false);
    assert.deepEqual(loaded.isolation, {data_store_persistent: false, frame_autosave: '', marker_seen_at_start: false, support_is_default: false});
    assert(second, 'second instance launched');
    assert.equal(await second.done, 0);
    assert.deepEqual(second.lines, [{state: 'focused_existing_instance'}]);
    assert.equal(first.lines.at(-1).main_frame_loads, 1, 'second open did not reload the first window');
    assert.equal((await get(origin + '/'))?.status, 200, 'quitting the desktop entry leaves the service running');
    assert.equal(demo.exitCode, null);
    check(same(privateModes(dir), [0o700, 0o600]), 'existing Support directory/settings tightened to 0700/0600: ' + privateModes(dir).map(m => m?.toString(8)));

    // 2. No service on the configured port: bounded retries, never another port or a new service.
    const down = runApp(exe, 'down', supportDir('down', `http://127.0.0.1:${closed}`), {FAMILY_DESKTOP_RETRY_SECONDS: '0.2', FAMILY_DESKTOP_MAX_RETRIES: '3'});
    assert.equal(await down.done, 0);
    assert.equal(down.lines.find(l => l.state === 'unavailable')?.attempts, 3);
    assert.equal(await get(`http://127.0.0.1:${closed}/`), null, 'no service was started on the configured port');

    // 3. First use with nothing saved: the native form offers the default local address; nothing is written until verified.
    const noneDir = supportDir('none');
    const none = runApp(exe, 'first-use-idle', noneDir);
    assert.equal(await none.done, 0);
    assert.deepEqual(none.lines.find(l => l.state === 'setup_shown'), {state: 'setup_shown', typed: 'http://127.0.0.1:8765', message: ''});
    assert.equal(configured(noneDir), null);
    plainMessages(none, noneDir);
    const wrong = runApp(exe, 'other-program', supportDir('other', `http://127.0.0.1:${otherPort}`));
    assert.equal(await wrong.done, 0);
    assert(states(wrong).includes('not_family_service'));
    for (const bad of ['http://192.168.1.20:8765', 'http://127.0.0.1.evil.example:8765']) {
      const badDir = supportDir('bad' + bad.length, bad);
      const refused = runApp(exe, 'bad-saved-' + bad.length, badDir);
      assert.equal(await refused.done, 0);
      const shown = refused.lines.find(l => l.state === 'setup_shown');
      assert(shown && shown.typed === bad && /已保存的地址不能使用/.test(shown.message), bad);
      plainMessages(refused, badDir);
    }

    // 4. Wrong entries in the form are explained and never saved.
    const failDir = supportDir('first-use-failures');
    const failing = runApp(exe, 'first-use-failures', failDir, {FAMILY_DESKTOP_TEST_SETUP_INPUTS: JSON.stringify(['http://192.168.1.20:8765', `http://127.0.0.1:${otherPort}`, `http://127.0.0.1:${closed}`])});
    assert.equal(await failing.done, 0);
    assert.deepEqual(failing.lines.filter(l => l.state.startsWith('setup_') && l.state !== 'setup_shown').map(l => l.reason || l.state),
      ['setup_rejected', 'not_family_service', 'unreachable']);
    assert.equal(configured(failDir), null, 'failed attempts write nothing');
    assert.equal(await get(`http://127.0.0.1:${closed}/`), null);
    plainMessages(failing, failDir);

    // 5. First use: wrong entry, then the right one → saved → original list. Then, in WebKit at 360 and 1440, the original
    //    homework entry with a file → feedback on the same homework → hand-written wrong item → correction → reopen.
    //    At 360 a denied microphone keeps the visible feedback form usable, and change address/close/Esc/Cmd+Q keep the draft.
    const upload = path.join(tmp, FILE_NAME);
    // A 1×1 fictional photo: the original homework save takes photos, recordings or PDF and refuses plain text with its own message.
    fs.writeFileSync(upload, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=', 'base64'));
    const stepsFile = path.join(tmp, 'steps.json');
    fs.writeFileSync(stepsFile, JSON.stringify([...flowSteps(360, true), ...flowSteps(1440, false)]));
    const setupDir = supportDir('first-use');
    const setup = runApp(exe, 'first-use-then-flow', setupDir, {FAMILY_DESKTOP_TEST_SETUP_INPUTS: JSON.stringify([`http://127.0.0.1:${otherPort}`, origin]),
      FAMILY_DESKTOP_TEST_STEPS: stepsFile, FAMILY_DESKTOP_TEST_OPEN_FILE: upload}, undefined, {limit: 360000});
    const setupEnd = await setup.done;
    check(setupEnd === 0, 'first-use flow run ended with ' + setupEnd + ': ' + JSON.stringify(setup.lines.slice(-3)));
    const flow = setup.lines.find(l => l.state === 'loaded');
    if (flow) {
      check(same(states(setup).filter(s => !s.startsWith('step')).slice(0, 5), ['unconfigured', 'setup_shown', 'setup_probe_failed', 'setup_saved', 'loaded']), 'first-use states ' + JSON.stringify(states(setup).filter(s => !s.startsWith('step'))));
      check(same(configured(setupDir), {service_origin: origin}), 'saved setting ' + JSON.stringify(configured(setupDir)));
      check(same(privateModes(setupDir), [0o700, 0o600]), 'new Support directory/settings are 0700/0600: ' + privateModes(setupDir).map(m => m?.toString(8)));
      try { plainMessages(setup, setupDir); } catch (e) { problems.push(e.message); }
      check(flow.isolation.marker_seen_at_start === false, 'cookie/localStorage of the earlier run on the same 127.0.0.1 origin is not visible');
      const stopped = setup.lines.find(l => l.state === 'steps_stopped');
      const step = name => flow.steps.find(s => s.name === name)?.result;
      check(!stopped, 'steps stopped after ' + stopped?.after + ': ' + JSON.stringify(step(stopped?.after)));
      for (const w of [360, 1440]) {
        for (const name of ['homework_open', 'homework_fill', 'homework_save', 'homework_close', 'task_open', 'feedback_save', 'wrong_save', 'wrong_card', 'correction_open', 'correction_save', 'reopen', 'reopen_close'])
          check(step(name + '_' + w)?.ok === true, name + '_' + w + ' ' + JSON.stringify(step(name + '_' + w)));
        const entry = step('homework_open_' + w)?.state;
        check(entry?.width === w && entry?.overflow === false && entry?.is_record_dialog === false && entry?.item === '0', 'homework entry ' + w + ' ' + JSON.stringify(entry));
        check(step('homework_file_' + w)?.ok === true, 'homework file ' + w + ' ' + JSON.stringify(step('homework_file_' + w)));
        const mic = step('mic_denied_' + w);
        if (mic?.skipped) unverified.push('microphone denial ' + w + ': ' + mic.skipped);
        else check(mic?.ok === true && mic.state.record_enabled && mic.state.save_enabled && mic.state.note_enabled && mic.state.dialog_open, 'denied microphone keeps the visible feedback form usable ' + w + ' ' + JSON.stringify(mic));
        const fix = step('correction_open_' + w)?.state;
        check(fix?.followup_kind === '订正' && fix?.task === TITLE(w) && fix?.width === w && fix?.overflow === false, 'correction form ' + w + ' ' + JSON.stringify(fix));
        const back = step('reopen_' + w)?.state;
        check(back && back.history_has_note && back.history_has_correction && back.wrong_related_to_answer && back.correction_kind === '订正' && back.correction_note === CORRECTION(w) && back.task_update === null && back.width === w && back.overflow === false, 'reopen ' + w + ' ' + JSON.stringify(back));
      }
      check(flow.events.some(e => e.open_panel === 'test_file'), 'WebKit requested the open panel for [data-homework-files]: ' + JSON.stringify(flow.events.filter(e => e.open_panel)));
      const keep = step('change_address_keep');
      check(keep && same(keep.prompt, [{discard_prompt: '更改地址', choice: '继续编辑'}]) && keep.setup_shown === false && keep.web_visible === true && keep.saved_origin === origin && keep.main_frame_loads === 1, 'change address keeps the page, draft and address ' + JSON.stringify(keep));
      check(step('draft_kept_360')?.ok === true, 'draft kept ' + JSON.stringify(step('draft_kept_360')));
      const guard = step('close_esc_quit');
      check(same({...guard}, {dirty: true, window_open_after_close: true, window_open_after_esc: true, quit_reply: 'cancelled', main_frame_loads: 1}), 'close/Esc/Cmd+Q ' + JSON.stringify(guard));
      check(flow.unsaved_after_steps === false, 'after everything is saved nothing is left to protect');
    } else check(false, 'first-use flow never reached loaded: ' + JSON.stringify(setup.lines.slice(-4)));

    // 6. Reopen: the saved address opens directly with the saved homework history; no data carried over from the previous
    //    test process. With a draft, changing the address shows the form only after an explicit discard, then reloads.
    const reopenFile = path.join(tmp, 'reopen.json');
    fs.writeFileSync(reopenFile, JSON.stringify([
      {name: 'reopen_saved_1440', width: 1440, js: openTask(TITLE(1440)), until: reopenCheck(1440)},
      {name: 'reopen-saved-1440', native: 'snapshot'},
      {name: 'draft_before_discard', js: `${SET}set(document.querySelector('#taskForm textarea[name=note]'),${q(DRAFT)});return {ok:true};`},
      {name: 'change_address_discard', native: 'change_address', discard: true},
      {name: 'after_discard', js: "return {ok:true,dialog_open:document.querySelector('#taskDialog').open,note:document.querySelector('#taskForm textarea[name=note]').value,href:location.href};"},
    ]));
    const reopen = runApp(exe, 'reopen-saved', setupDir, {FAMILY_DESKTOP_TEST_STEPS: reopenFile, FAMILY_DESKTOP_TEST_SETUP_INPUTS: JSON.stringify([origin])}, undefined, {limit: 120000});
    const reopenEnd = await reopen.done;
    check(reopenEnd === 0, 'reopen run ended with ' + reopenEnd + ': ' + JSON.stringify(reopen.lines.slice(-3)));
    const again = reopen.lines.find(l => l.state === 'loaded');
    const beforeSteps = states(reopen).slice(0, Math.max(0, states(reopen).indexOf('step')));
    check(!beforeSteps.includes('setup_shown') && again?.isolation.marker_seen_at_start === false, 'saved address reopens directly ' + JSON.stringify(beforeSteps));
    const r = name => again?.steps.find(s => s.name === name)?.result;
    check(r('reopen_saved_1440')?.ok === true, 'saved homework history after reopening the app ' + JSON.stringify(r('reopen_saved_1440')));
    const discard = r('change_address_discard');
    check(discard && same(discard.prompt, [{discard_prompt: '更改地址', choice: '放弃'}]) && discard.setup_shown === true && discard.typed === origin && discard.main_frame_loads === 2 && discard.saved_origin === origin,
      'explicit discard opens the form, then the confirmed address reloads ' + JSON.stringify(discard));
    check(r('after_discard')?.dialog_open === false && r('after_discard')?.note === '' && again?.unsaved_after_steps === false, 'discarded draft is gone only after the explicit choice ' + JSON.stringify(r('after_discard')));
    try { plainMessages(reopen, setupDir); } catch (e) { problems.push(e.message); }

    // 7. A saved address that stops working can be corrected from the failure state; the external-link setting is kept.
    const fixDir = supportDir('correct', `http://127.0.0.1:${closed}`, {external_hosts: ['example.org']});
    const fix = runApp(exe, 'correct-after-failure', fixDir, {FAMILY_DESKTOP_RETRY_SECONDS: '0.2', FAMILY_DESKTOP_MAX_RETRIES: '2', FAMILY_DESKTOP_TEST_SETUP_INPUTS: JSON.stringify([origin])});
    check((await fix.done) === 0, 'correction run ' + JSON.stringify(fix.lines.slice(-3)));
    check(same(states(fix).filter(s => ['unavailable', 'setup_shown', 'setup_saved', 'loaded'].includes(s)), ['unavailable', 'setup_shown', 'setup_saved', 'loaded']), 'correction states ' + JSON.stringify(states(fix)));
    check(fix.lines.find(l => l.state === 'setup_shown')?.typed === `http://127.0.0.1:${closed}`, 'failure form shows the saved address');
    check(same(configured(fixDir), {service_origin: origin, external_hosts: ['example.org']}), 'corrected setting keeps external hosts ' + JSON.stringify(configured(fixDir)));
    check(same(privateModes(fixDir), [0o700, 0o600]), 'corrected settings stay 0700/0600: ' + privateModes(fixDir).map(m => m?.toString(8)));
    check((await get(origin + '/'))?.status === 200, 'the demo service keeps running');

    console.log(JSON.stringify({native_problems: problems, unverified}));
    assert.deepEqual(problems, [], 'native acceptance problems');

    // 8. Chrome baseline of the same original UI (optional; Root's existing Playwright environment).
    let playwright = null;
    try { playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright'); } catch {}
    if (playwright) {
      const browser = await playwright.chromium.launch({channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true});
      for (const width of [360, 1440]) {
        const page = await browser.newPage({viewport: {width, height: 860}});
        await page.goto(origin + '/');
        await page.locator('[data-child-filter]').first().waitFor();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.close();
      }
      await browser.close();
      console.log('chrome baseline: pass');
    } else console.log('chrome baseline: skipped (playwright not available here)');
    console.log(JSON.stringify({pass: true, origin}));
  } finally {
    if (evidence) fs.writeFileSync(path.join(evidence, 'native-lines.json'), JSON.stringify(log, null, 1));
    other?.closeAllConnections?.(); other?.close();
    if (demo && demo.exitCode === null) { demo.kill('SIGINT'); if (await exitWithin(demo, 1500) === 'late') demo.kill('SIGKILL'); }
    fs.rmSync(tmp, {recursive: true, force: true});
  }
})().catch(e => { console.error(e); process.exitCode = 1; });

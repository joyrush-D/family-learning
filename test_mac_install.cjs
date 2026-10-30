// 一起成长.app 完整安装候选（packaging/macos）的虚构验收：真实 .app、真实 WKWebView 原入口、真实 launchd 登录服务。
// 只用本测试新建的虚构家庭、带 test. 前缀的服务名、临时目录和端口；不读取或控制真实家庭、其他服务、QQ/微信或 TCC。
// 需要已构建的两个完整包（packaging/macos/build.sh 构建号 1 与 2）：
//   FAMILY_MAC_APP_V1=…/一起成长.app FAMILY_MAC_APP_V2=…/一起成长.app node test_mac_install.cjs
// 可选 FAMILY_MAC_INSTALL_EVIDENCE_DIR 保存行日志、截图与结果。结束时 bootout 本测试的服务；服务设置在测试目录里，launchd 登录时不会加载。
// “重启恢复”用与退出登录/登录相同的 bootout 与按服务设置 bootstrap 模拟，不重启这台 Mac。
const {spawn, spawnSync, execFileSync} = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const {once} = require('node:events');
const {setTimeout: delay} = require('node:timers/promises');

const V1 = process.env.FAMILY_MAC_APP_V1, V2 = process.env.FAMILY_MAC_APP_V2;
if (!V1 || !V2) { console.error('需要 FAMILY_MAC_APP_V1 与 FAMILY_MAC_APP_V2（构建号 1、2 的完整包）；未运行，不算通过'); process.exit(2); }
const root = __dirname;
const exe = app => path.join(app, 'Contents/MacOS/YiqiChengzhang');
const evidence = process.env.FAMILY_MAC_INSTALL_EVIDENCE_DIR || fs.mkdtempSync(path.join(os.tmpdir(), 'synthetic-mac-install-evidence-'));
fs.mkdirSync(evidence, {recursive: true});
const tmp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'synthetic-mac-install-')));
const uid = process.getuid();
const log = {}, results = [], problems = [];
const check = (ok, message, detail) => { results.push({ok: !!ok, message, ...(detail === undefined ? {} : {detail})}); if (!ok) problems.push(message); console.log((ok ? 'ok   ' : 'FAIL ') + message); };

async function freePort() {
  const s = net.createServer(); s.listen(0, '127.0.0.1'); await once(s, 'listening');
  const port = s.address().port; await new Promise(r => s.close(r)); return port;
}
function get(url) {
  return new Promise(resolve => http.get(url, {agent: false}, res => { let b = ''; res.on('data', d => b += d); res.on('end', () => resolve({status: res.statusCode, body: b})); })
    .on('error', () => resolve(null)));
}
async function apiState(origin) { const r = await get(origin + '/api/state'); try { return JSON.parse(r.body); } catch { return null; } }
function profile(name) {
  const dir = path.join(tmp, name); fs.mkdirSync(path.join(dir, 'support'), {recursive: true});
  return {dir, support: path.join(dir, 'support'), base: path.join(dir, 'backend'), agents: path.join(dir, 'LaunchAgents'),
          label: 'test.yiqichengzhang.' + crypto.createHash('sha256').update(dir).digest('hex').slice(0, 12)};
}
const kinds = ['web', 'agent', 'collector', 'backup'];
function service(p, kind) {  // 只查询本测试自己的服务名
  const r = spawnSync('/bin/launchctl', ['print', `gui/${uid}/${p.label}.${kind}`], {encoding: 'utf8'});
  if (r.status !== 0) return null;
  const m = r.stdout.match(/^\s*pid = (\d+)/m); return {pid: m ? Number(m[1]) : 0};
}
const loaded = p => kinds.filter(k => service(p, k));
const bootout = p => { for (const k of kinds) spawnSync('/bin/launchctl', ['bootout', `gui/${uid}/${p.label}.${k}`]); };
// 网页写入进程：只按本测试安装目录匹配，返回进程号个数，不读取其他进程的命令行。
const writers = p => (spawnSync('/usr/bin/pgrep', ['-f', '--', path.join(p.base, 'app', 'app.py')], {encoding: 'utf8'}).stdout || '').split('\n').filter(Boolean).length;
const plists = p => fs.existsSync(p.agents) ? fs.readdirSync(p.agents).filter(n => n.endsWith('.plist')).sort() : [];
const record = p => { try { return JSON.parse(fs.readFileSync(path.join(p.base, 'install.json'), 'utf8')); } catch { return null; } };
const mode = f => { try { return fs.statSync(f).mode & 0o777; } catch { return null; } };

function backendCli(app, command, p, port, support = p.support) {
  const res = path.join(app, 'Contents/Resources');
  const r = spawnSync(path.join(res, 'runtime/bin/python3.11'), ['-I', '-B', path.join(res, 'app/packaging/macos/backend.py'), command, '--resources', res,
    '--support', support, '--test-profile', p.dir, '--port', String(port)], {encoding: 'utf8', env: {PATH: '/usr/bin:/bin:/usr/sbin:/sbin', HOME: os.homedir(), LANG: 'en_US.UTF-8'}});
  let reply = null; try { reply = JSON.parse(r.stdout.trim().split('\n').pop()); } catch {}
  return {status: r.status, reply};
}

// 运行真实 .app（测试模式），收集它输出的每行 JSON；只会结束它自己。
function runApp(app, name, support, env, {limit = 300000, idle = 240000} = {}, onLine = () => {}) {
  const shots = path.join(evidence, 'snapshots', name); fs.mkdirSync(shots, {recursive: true});
  const proc = spawn(exe(app), ['--smoke-test'], {env: {...process.env, FAMILY_DESKTOP_SUPPORT_DIR: support, FAMILY_DESKTOP_TEST_SNAPSHOT_DIR: shots, ...env}, stdio: ['ignore', 'pipe', 'pipe']});
  const lines = []; let buffer = '', total, quiet;
  const done = new Promise(resolve => {
    const end = value => { clearTimeout(total); clearTimeout(quiet); resolve(value); };
    const kill = reason => { proc.kill('SIGKILL'); end(reason); };
    const watch = () => { clearTimeout(quiet); quiet = setTimeout(() => kill('stalled after ' + ((lines.at(-1) || {}).state || 'start')), idle); };
    total = setTimeout(() => kill('timeout'), limit); watch();
    proc.stdout.on('data', d => { watch(); buffer += d; let i; while ((i = buffer.indexOf('\n')) >= 0) { const line = buffer.slice(0, i); buffer = buffer.slice(i + 1);
      try { const value = JSON.parse(line); lines.push(value); onLine(value); } catch {} } });
    proc.once('close', code => end(code));
  });
  log[name] = lines;
  return {proc, lines, done};
}
const line = (run, state) => run.lines.find(l => l.state === state);
const stepResult = (run, name) => run.lines.find(l => l.state === 'step_done' && l.name === name)?.result;
function stepsPassed(run, label) {
  const stopped = line(run, 'steps_stopped'), loadedLine = line(run, 'loaded');
  check(loadedLine && !stopped, label + ': every original-page step passed', stopped ? {after: stopped.after, result: stepResult(run, stopped.after)} : undefined);
  for (const w of loadedLine?.widths || []) check(!w.overflow && !w.all_children, label + `: ${w.width}px without horizontal overflow or “全部孩子”`, w);
}
// 家长看到的原生文字不含路径、命令、进程号或文件格式。
function plain(run) {
  for (const l of run.lines) for (const text of [l.message || ''])
    if (/\/Users|\/var|\/private|Application Support|python|launchctl|sqlite|\.json|\bpid\b|[{}]/i.test(text) || text.includes(tmp)) check(false, 'internal detail shown: ' + text);
}

const q = JSON.stringify;
const LAYOUT = 'width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth';
const SET = "const set=(el,v)=>{el.focus();el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}))};";
const TEXT = "const text=x=>x.innerText.replace(/\\s+/g,' ').trim();";
const ITEM = "const d=document.querySelector('#homeworkInputDialog');const item=d&&(d.querySelector('form[data-homework-item=\"0\"]')||d.querySelector('form[data-homework-item]'));";
const CHILD = '虚构小林', GOAL = '朗读第三课两遍，家长听后签字', FILE_NAME = '虚构-口头作业照片.png';
const T = w => '虚构安装后作业 ' + w, T_NEW = '虚构更新前新增作业';
const STATE = title => `const st=await (await fetch('/api/state',{cache:'no-store'})).json();const task=st.tasks.find(t=>t.title===${q(title)});if(!task)return {ok:false,reason:'homework not in api/state',titles:st.tasks.map(t=>t.title)};`;
// Select the actual list row first; the feedback entry now belongs to its own detail (phone: list -> detail).
const openTask = title => `${STATE(title)}const back=document.querySelector('[data-grove-back]');if(back?.offsetParent){back.click();await new Promise(r=>setTimeout(r,100));}const row=[...document.querySelectorAll('[data-grove-open="'+task.id+'"]')].find(x=>x.offsetParent);if(row){row.click();await new Promise(r=>setTimeout(r,100));}const b=[...document.querySelectorAll('#groveDetail [data-task="'+task.id+'"], [data-task="'+task.id+'"]')].find(x=>x.offsetParent);if(!b)return {ok:false,reason:'no visible own detail feedback entry',id:task.id};b.click();return {ok:true,id:task.id};`;
const childSteps = () => [
  {name: 'child_setup', width: 1440, timeout: 25,
   js: `${SET}let f=document.querySelector('form[data-settings-form="child"]');if(!f||!f.offsetParent){const b=[...document.querySelectorAll('[data-page="settings"]')].find(x=>x.offsetParent);if(b)b.click();await new Promise(r=>setTimeout(r,800));f=document.querySelector('form[data-settings-form="child"]');}
if(!f)return {ok:false,reason:'no child form',text:document.body.innerText.slice(0,300)};const det=f.closest('details');if(det)det.open=true;set(f.querySelector('[name=name]'),${q(CHILD)});set(f.querySelector('[name=grade]'),'四年级');f.querySelector('[type=submit]').click();return {ok:true};`,
   until: `const st=await (await fetch('/api/state',{cache:'no-store'})).json();return {ok:st.children.length===1&&st.children[0].name===${q(CHILD)},children:st.children.map(c=>c.name)};`},
  {name: 'child-saved', native: 'snapshot'},
  {name: 'go_home', timeout: 20,
   js: "const b=[...document.querySelectorAll('[data-page=\"home\"]')].find(x=>x.offsetParent);if(b)b.click();return {ok:true,clicked:!!b};",
   until: "return {ok:[...document.querySelectorAll('button[data-homework-new]')].some(x=>x.offsetParent&&!x.disabled),text:document.body.innerText.slice(0,200)};"},
];
const homeworkSteps = (w, title) => [
  {name: 'homework_open_' + w + title.length, width: w,
   js: "const b=[...document.querySelectorAll('button[data-homework-new]')].find(x=>x.offsetParent&&!x.disabled);if(!b)return {ok:false,reason:'no visible [data-homework-new]'};b.click();return {ok:true};",
   until: `${ITEM}return {ok:!!(d&&d.open&&item&&item.querySelector('[name=title]').offsetParent),${LAYOUT}};`},
  {name: 'homework_fill_' + w + title.length,
   js: `${SET}${ITEM}if(!item)return {ok:false,reason:'no [data-homework-item] form'};set(item.querySelector('[name=title]'),${q(title)});set(item.querySelector('[name=goal]'),${q(GOAL)});return {ok:item.querySelector('[name=title]').value===${q(title)}};`},
  {name: 'homework_file_' + w + title.length, required: false,
   js: "const f=document.querySelector('#homeworkInputDialog input[type=file][data-homework-files]');if(!f)return {ok:false,reason:'no [data-homework-files]'};f.click();return {ok:true};",
   until: `${TEXT}const rows=[...document.querySelectorAll('#homeworkInputDialog .homework-files > div')].map(text);return {ok:rows.some(t=>t.includes(${q(FILE_NAME)})&&/原件已保存/.test(t)),rows};`},
  {name: 'homework_save_' + w + title.length,
   js: `const d=document.querySelector('#homeworkInputDialog'),item=[...d.querySelectorAll('form[data-homework-item]')].find(f=>f.querySelector('[name=title]').value===${q(title)});if(!item)return {ok:false,reason:'filled form is gone'};item.querySelector('[type=submit]').click();return {ok:true};`,
   until: `${TEXT}const d=document.querySelector('#homeworkInputDialog'),s=[...d.querySelectorAll('.homework-saved')].find(x=>x.innerText.includes(${q(title)}));return {ok:!!s,saved:s?text(s):'',dialog:text(d).slice(0,400),${LAYOUT}};`},
  {name: w + '-' + title.length + '-homework-saved', native: 'snapshot'},
  {name: 'homework_close_' + w + title.length, js: "document.querySelector('#homeworkInputDialog [data-homework-close]').click();return {ok:true};",
   until: "return {ok:!document.querySelector('#homeworkInputDialog').open};"},
  ...reopenSteps([title], w, 'saved_' + w + title.length),
];
function reopenSteps(titles, w, tag) {
  return titles.flatMap((title, i) => [
    {name: `reopen_${tag}_${i}`, width: w, timeout: 20, js: openTask(title),
     until: `const d=document.querySelector('#taskDialog');return {ok:d.open&&d.innerText.includes(${q(title)}),${LAYOUT}};`},
    {name: `${tag}-${i}-reopened`, native: 'snapshot'},
    {name: `reopen_close_${tag}_${i}`, js: "document.querySelector('#taskDialog [data-close=\"taskDialog\"]').click();return {ok:true};",
     until: "return {ok:!document.querySelector('#taskDialog').open};"},
  ]);
}

(async () => {
  const A = profile('family-a'), B = profile('family-b'), C = profile('family-c');
  const port = await freePort(), origin = `http://127.0.0.1:${port}`;
  const upload = path.join(tmp, FILE_NAME);
  fs.writeFileSync(upload, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWF8AAAAASUVORK5CYII=', 'base64'));
  const stepsFile = (name, list) => { const f = path.join(tmp, name + '.json'); fs.writeFileSync(f, JSON.stringify(list)); return f; };
  const env = (p, extra = {}, o = origin) => ({FAMILY_DESKTOP_TEST_ORIGIN: o, FAMILY_DESKTOP_TEST_PROFILE: p.dir, FAMILY_DESKTOP_TEST_OPEN_FILE: upload, ...extra});
  const titles = () => [T(360), T(1440)];
  const db = path.join(A.base, 'app/private/family.sqlite3');
  try {
    for (const app of [V1, V2]) check(JSON.parse(execFileSync(exe(app), ['--self-test'], {encoding: 'utf8'})).self_test === 'pass', 'policy self-test ' + path.basename(path.dirname(app)));
    const build = app => JSON.parse(fs.readFileSync(path.join(app, 'Contents/Resources/BUILD.json'), 'utf8'));
    check(build(V1).build === 1 && build(V2).build === 2 && build(V1).commit === build(V2).commit, 'bundles carry build 1 and 2 of one commit', {commit: build(V1).commit});
    check(spawnSync('/usr/bin/codesign', ['--verify', '--deep', '--strict', V1]).status === 0, 'bundle seal intact before use');

    // 1. 全新虚构 Mac：原生首用表单只读检查后提供“安装后台”，家长点击安装 → 原清单；360/1440 建孩子、存作业、重开同一作业。
    const first = runApp(V1, 'first-install', A.support, env(A, {FAMILY_DESKTOP_TEST_INSTALL: '1',
      FAMILY_DESKTOP_TEST_STEPS: stepsFile('first', [...childSteps(), ...homeworkSteps(360, T(360)), ...homeworkSteps(1440, T(1440))])}), {limit: 900000, idle: 300000});
    const firstEnd = await first.done;
    check(firstEnd === 0, 'first install run ended normally: ' + firstEnd);
    check(line(first, 'backend_check')?.result === 'fresh', 'fresh Mac: install offered only after the read-only check', line(first, 'backend_check'));
    check(line(first, 'backend_install')?.ok === true && line(first, 'backend_install')?.result === 'installed', 'parent click installs the backend', line(first, 'backend_install'));
    check(line(first, 'setup_saved')?.origin === origin, 'installed origin saved through the same confirmation');
    stepsPassed(first, 'first install');
    plain(first);
    const rec1 = record(A);
    check(rec1?.state === 'installed' && rec1?.build === 1 && mode(path.join(A.base, 'install.json')) === 0o600, 'install record owned and private', rec1 && {state: rec1.state, build: rec1.build});
    check(mode(path.join(A.support, 'desktop.json')) === 0o600 && mode(A.base) === 0o700, 'desktop setting and install directory private to this user');
    const web1 = service(A, 'web');
    check(web1?.pid > 0 && JSON.stringify(loaded(A)) === JSON.stringify(['web', 'agent', 'backup']), 'web/agent/backup loaded, collector waits for a source', loaded(A));
    check(JSON.stringify(plists(A)) === JSON.stringify(kinds.map(k => `${A.label}.${k}.plist`).sort()), 'the four original service settings', plists(A));
    const webPlist = fs.readFileSync(path.join(A.agents, `${A.label}.web.plist`), 'utf8');
    const stablePython = path.join(A.base, 'runtime', build(V1).runtime_id, 'bin/python3.11');
    check(webPlist.includes(`<string>${stablePython}</string>`) && webPlist.includes('<key>FAMILY_DEEPTUTOR_PYTHON</key>') && !webPlist.includes(V1),
      'services use the stable copied runtime (not the .app) and name it for DeepTutor');
    const s1 = await apiState(origin);
    check(s1 && titles().every(t => s1.tasks.some(x => x.title === t)), 'second client (HTTP) reads the same homework after the GUI quit');
    check(writers(A) === 1 && fs.existsSync(db), 'one web writer, one main DB at the stable location');
    const inode = fs.statSync(db).ino;
    const dt = spawnSync(stablePython, ['-B', '-m', 'unittest', '-v', 'test_deeptutor_bridge'], {cwd: root, encoding: 'utf8', env: {PATH: '/usr/bin:/bin', HOME: os.homedir(), LANG: 'en_US.UTF-8', FAMILY_DEEPTUTOR_PYTHON: stablePython}});
    fs.writeFileSync(path.join(evidence, 'deeptutor-stable-runtime.log'), dt.stderr);
    check(dt.status === 0 && !/skipped/.test(dt.stderr) && /Ran 18 tests/.test(dt.stderr), 'DeepTutor bridge runs (not skipped) on the installed runtime', dt.stderr.split('\n').slice(-4).join(' '));

    // 2. 再次打开（同一作业重开）后强杀 GUI：后台进程不变。
    const reopen = runApp(V1, 'reopen-then-kill', A.support, env(A, {FAMILY_DESKTOP_SMOKE_HOLD: '60', FAMILY_DESKTOP_TEST_STEPS: stepsFile('reopen', reopenSteps(titles(), 1440, 'gui2'))}),
      {limit: 240000}, l => { if (l.state === 'loaded') setTimeout(() => reopen.proc.kill('SIGKILL'), 300); });
    const killed = await reopen.done;
    check(killed === null || killed === 137, 'GUI force-killed after reopening the same homework: ' + killed);
    stepsPassed(reopen, 'reopen');
    await delay(1500);
    check(service(A, 'web')?.pid === web1.pid && (await get(origin + '/'))?.status === 200 && writers(A) === 1, 'backend unchanged after GUI quit and force kill');

    // 3. 重复安装与冲突：零新写入者。
    const support2 = path.join(A.dir, 'support-2'); fs.mkdirSync(support2);
    const repeat = runApp(V1, 'repeat-install', support2, env(A, {FAMILY_DESKTOP_TEST_INSTALL: '1'}));
    await repeat.done;
    check(line(repeat, 'backend_check')?.result === 'existing' && !line(repeat, 'backend_install_started'), 'repeat install not offered over the existing backend', line(repeat, 'backend_check'));
    const cliRepeat = backendCli(V1, 'install', A, port, support2);
    check(cliRepeat.status === 1 && cliRepeat.reply?.state === 'existing', 'backend refuses a second install', cliRepeat.reply);
    const conflict = runApp(V1, 'port-conflict', B.support, env(B, {FAMILY_DESKTOP_TEST_INSTALL: '1'}));
    await conflict.done;
    check(line(conflict, 'backend_check')?.result === 'port_busy', 'occupied port: install not offered, no other port', line(conflict, 'backend_check'));
    check(backendCli(V1, 'install', B, port).reply?.state === 'port_busy' && !fs.existsSync(B.base) && plists(B).length === 0 && loaded(B).length === 0, 'port conflict creates nothing');
    const portC = await freePort();
    fs.mkdirSync(C.agents, {recursive: true});
    fs.writeFileSync(path.join(C.agents, 'com.example.fictional-family.web.plist'), `<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>Label</key><string>com.example.fictional-family.web</string><key>ProgramArguments</key><array><string>/fictional/python3</string><string>/fictional/family/app.py</string></array></dict></plist>`);
    const offline = runApp(V1, 'known-service-offline', C.support, env(C, {FAMILY_DESKTOP_TEST_INSTALL: '1'}, `http://127.0.0.1:${portC}`));
    await offline.done;
    check(line(offline, 'backend_check')?.result === 'existing' && !fs.existsSync(C.base) && loaded(C).length === 0, 'offline known family service: no second backend', line(offline, 'backend_check'));
    check(service(A, 'web')?.pid === web1.pid && writers(A) === 1, 'still the same single writer');
    for (const r of [repeat, conflict, offline]) plain(r);

    // 4. 有新资料的更新失败：只退回已核对的旧代码，主库与新资料保留。
    const fail = runApp(V2, 'update-fails', A.support, env(A, {FAMILY_DESKTOP_TEST_UPDATE_FAULT: 'after_start',
      FAMILY_DESKTOP_TEST_STEPS: stepsFile('update-fail', [...homeworkSteps(1440, T_NEW), {name: 'update_fail', native: 'update_backend'}, ...reopenSteps([T_NEW], 1440, 'after_fail')])}), {limit: 600000, idle: 300000});
    await fail.done;
    const uf = stepResult(fail, 'update_fail');
    check(line(fail, 'backend_status')?.result === 'update_available', 'newer bundle offers an update in the menu only');
    check(uf?.reply?.ok === false && uf?.reply?.state === 'rolled_back' && uf?.reloaded, 'failed update restores the old version and reopens the list', uf?.reply);
    stepsPassed(fail, 'update failure');
    plain(fail);
    const status1 = backendCli(V2, 'status', A, port);
    check(record(A)?.build === 1 && status1.reply?.state === 'update_available', 'old code and settings verify file by file after rollback', status1.reply);
    const sF = await apiState(origin);
    check(fs.statSync(db).ino === inode && sF && [...titles(), T_NEW].every(t => sF.tasks.some(x => x.title === t)), 'main DB kept in place with the new homework (no backup restored over it)');
    check(writers(A) === 1, 'one writer after rollback');

    // 5. 正常更新：备份、隔离恢复核对、换代码，原资料保留。
    const ok = runApp(V2, 'update-succeeds', A.support, env(A, {FAMILY_DESKTOP_TEST_STEPS: stepsFile('update-ok', [{name: 'update_ok', native: 'update_backend'},
      ...reopenSteps([...titles(), T_NEW], 360, 'after_update_360'), ...reopenSteps([T_NEW], 1440, 'after_update_1440')])}), {limit: 600000, idle: 300000});
    await ok.done;
    const uo = stepResult(ok, 'update_ok');
    check(uo?.reply?.ok === true && uo?.reply?.state === 'updated' && uo?.reply?.checked_tables > 0 && uo?.reloaded, 'update completes after backup and isolated restore check of every live table', uo?.reply);
    stepsPassed(ok, 'update');
    plain(ok);
    const rec2 = record(A);
    check(rec2?.build === 2 && rec2?.previous_build === 1 && fs.statSync(db).ino === inode, 'record shows build 2; same main DB', rec2 && {build: rec2.build, tables: rec2.checked_tables, backup: rec2.backup});
    const backups = fs.readdirSync(path.join(A.base, 'app/private/backups')).filter(n => n.startsWith('更新前-1-'));
    check(backups.length === 2, 'a fresh pre-update backup for each attempt', backups);
    check(writers(A) === 1, 'one writer after update');

    // 6. 重启恢复（模拟退出登录与再次登录）：服务全部停下，再按服务设置重新加载。
    bootout(A);
    for (let n = 0; n < 100 && (loaded(A).length || writers(A)); n++) await delay(100);
    check(loaded(A).length === 0 && writers(A) === 0 && !(await get(origin + '/')), 'all own services stopped as at logout');
    for (const name of plists(A)) {
      if (/<key>Disabled<\/key>\s*<true\/>/.test(fs.readFileSync(path.join(A.agents, name), 'utf8'))) continue;
      spawnSync('/bin/launchctl', ['bootstrap', `gui/${uid}`, path.join(A.agents, name)]);
    }
    for (let n = 0; n < 200 && (await get(origin + '/'))?.status !== 200; n++) await delay(100);
    const sR = await apiState(origin);
    check(sR && [...titles(), T_NEW].every(t => sR.tasks.some(x => x.title === t)) && writers(A) === 1 && fs.statSync(db).ino === inode, 'after reload the same data, one writer');
    const after = runApp(V2, 'after-restart', A.support, env(A, {FAMILY_DESKTOP_TEST_STEPS: stepsFile('after-restart', reopenSteps([T(1440)], 1440, 'restart'))}));
    await after.done;
    stepsPassed(after, 'after restart');

    // 7. 卸载：停服务、删程序与运行时，家庭资料与备份保留；之后也不会在原资料旁另装一套。
    const un = runApp(V2, 'uninstall', A.support, env(A, {FAMILY_DESKTOP_TEST_STEPS: stepsFile('uninstall', [{name: 'uninstall', native: 'uninstall_backend'}, {name: 'uninstalled', native: 'snapshot'}])}));
    await un.done;
    const ur = stepResult(un, 'uninstall');
    check(ur?.reply?.ok === true && ur?.reply?.state === 'uninstalled', 'uninstall from the menu', ur?.reply);
    plain(un);
    // 只读核对：原主库里仍能找到全部虚构作业标题（不写库）。
    const count = fs.existsSync(db) ? execFileSync(path.join(V2, 'Contents/Resources/runtime/bin/python3.11'), ['-I', '-B', '-c',
      'import sqlite3,sys,pathlib\nc=sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri()+"?mode=ro",uri=True)\nfound=set()\nfor (n,) in c.execute("select name from sqlite_master where type=\'table\'").fetchall():\n for row in c.execute(\'select * from "%s"\' % n.replace(\'"\',\'""\')):\n  found.update(t for t in sys.argv[2:] for v in row if isinstance(v,str) and t in v)\nprint(len(found))',
      db, ...titles(), T_NEW], {encoding: 'utf8'}).trim() : '0';
    check(loaded(A).length === 0 && writers(A) === 0 && plists(A).length === 0 && !fs.existsSync(path.join(A.base, 'runtime')) && !fs.existsSync(path.join(A.base, 'app/app.py')),
      'services, settings, program files and runtime removed');
    check(fs.statSync(db).ino === inode && Number(count) === 3 && fs.readdirSync(path.join(A.base, 'app/private/backups')).length >= 2 && record(A)?.state === 'uninstalled',
      'family data, backups and record kept after uninstall', {tasks: count});
    check(backendCli(V2, 'check', A, port, path.join(A.dir, 'support-3')).reply?.state === 'existing', 'kept data blocks a silent second install');
  } catch (error) {
    check(false, 'harness error: ' + (error && error.stack || error));
  } finally {
    for (const p of [A, B, C]) bootout(p);
    fs.writeFileSync(path.join(evidence, 'lines.json'), JSON.stringify(log, null, 1));
    fs.writeFileSync(path.join(evidence, 'results.json'), JSON.stringify({problems, results, labels: [A.label, B.label, C.label], tmp}, null, 1));
    console.log(problems.length ? `FAILED ${problems.length}/${results.length}` : `PASS ${results.length} checks`);
    process.exit(problems.length ? 1 : 0);
  }
})();

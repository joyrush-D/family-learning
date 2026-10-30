/* 一起成长 · Family Grove 交互原型（设计交付，不是产品发布）
   方法与脚手架：baoyu-design https://github.com/jimliu/baoyu-design （MIT，c15e76ef5134228d2bb5da35652d30d7d6b8a34d）。
   下面第一段为该技能 starter-components/macos-window.jsx 原文，只用于原型里的 Mac 窗口示意（实际 App 用系统窗口）；
   之后是本原型自己的代码。 */

/* BEGIN USAGE */
// MacOS.jsx — Simplified macOS Tahoe (Liquid Glass) window
// Based on the macOS Tahoe UI Kit. No image assets, no dependencies.
// Exports (to window): MacWindow, MacSidebar, MacSidebarItem, MacSidebarHeader, MacToolbar, MacGlass, MacTrafficLights
//
// Usage — wrap your app content in <MacWindow> to get the window chrome
// (traffic lights + titlebar). Props: width, height, title, sidebar (pass a
// <MacSidebar> element); compose MacToolbar/MacGlass inside as needed:
//
//   <MacWindow width={980} height={620} title="Documents"
//              sidebar={<MacSidebar>…</MacSidebar>}>
//     ...your app content...
//   </MacWindow>
/* END USAGE */

const MAC_FONT = '-apple-system, BlinkMacSystemFont, "SF Pro", "Helvetica Neue", sans-serif';

// ─────────────────────────────────────────────────────────────
// Liquid glass primitive — blur + white tint + inset highlight
// ─────────────────────────────────────────────────────────────
function MacGlass({ children, radius = 296, dark = false, style = {} }) {
  return (
    <div style={{ position: 'relative', borderRadius: radius, ...style }}>
      <div style={{
        position: 'absolute', inset: 0, borderRadius: radius,
        background: dark ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.35)',
        backdropFilter: 'blur(40px) saturate(180%)',
        WebkitBackdropFilter: 'blur(40px) saturate(180%)',
        border: dark ? '0.5px solid rgba(255,255,255,0.12)' : '0.5px solid rgba(255,255,255,0.6)',
        boxShadow: dark
          ? '0 8px 40px rgba(0,0,0,0.2)'
          : '0 8px 40px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.4)',
      }} />
      <div style={{ position: 'relative', zIndex: 1 }}>{children}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Traffic lights (14px, Tahoe colors)
// ─────────────────────────────────────────────────────────────
function MacTrafficLights({ style = {} }) {
  const dot = (bg) => (
    <div style={{
      width: 14, height: 14, borderRadius: '50%', background: bg,
      border: '0.5px solid rgba(0,0,0,0.1)',
    }} />
  );
  return (
    <div style={{ display: 'flex', gap: 9, alignItems: 'center', padding: 1, ...style }}>
      {dot('#ff736a')}{dot('#febc2e')}{dot('#19c332')}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Toolbar — title + single glass pill icon
// ─────────────────────────────────────────────────────────────
function MacToolbar({ title = 'Folder' }) {
  return (
    <div style={{
      display: 'flex', gap: 8, alignItems: 'center', padding: 8, flexShrink: 0,
    }}>
      {/* title */}
      <div style={{
        fontFamily: MAC_FONT, fontSize: 15, fontWeight: 700,
        color: 'rgba(0,0,0,0.85)', whiteSpace: 'nowrap', paddingLeft: 8,
      }}>{title}</div>
      <div style={{ flex: 1 }} />
      {/* single action */}
      <MacGlass>
        <div style={{
          width: 36, height: 36, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#4c4c4c', opacity: 0.4 }} />
        </div>
      </MacGlass>
      {/* search */}
      <MacGlass>
        <div style={{
          width: 140, height: 36, display: 'flex', alignItems: 'center',
          gap: 6, padding: '0 12px',
        }}>
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <circle cx="5.5" cy="5.5" r="4" stroke="#727272" strokeWidth="1.5"/>
            <path d="M8.5 8.5l3 3" stroke="#727272" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <span style={{
            fontFamily: MAC_FONT, fontSize: 13, fontWeight: 500, color: '#727272',
          }}>Search</span>
        </div>
      </MacGlass>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Sidebar — frosted glass panel floating inside the window
// ─────────────────────────────────────────────────────────────
function MacSidebarItem({ label, selected = false }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      height: 24, padding: '4px 10px 4px 6px', margin: '0 10px',
      borderRadius: 8, position: 'relative',
      fontFamily: MAC_FONT, fontSize: 11, fontWeight: 500,
    }}>
      {selected && (
        <div style={{
          position: 'absolute', inset: 0, borderRadius: 8,
          background: 'rgba(0,0,0,0.11)', mixBlendMode: 'multiply',
        }} />
      )}
      <div style={{
        width: 14, height: 14, borderRadius: '50%',
        background: selected ? '#007aff' : 'rgba(0,0,0,0.4)',
        opacity: selected ? 1 : 0.5, flexShrink: 0, position: 'relative',
      }} />
      <span style={{ color: 'rgba(0,0,0,0.85)', position: 'relative' }}>{label}</span>
    </div>
  );
}

function MacSidebar({ children }) {
  return (
    <div style={{
      width: 220, height: '100%', padding: 8, flexShrink: 0,
      position: 'relative', display: 'flex', flexDirection: 'column',
    }}>
      {/* glass panel */}
      <div style={{
        position: 'absolute', inset: 8, borderRadius: 18,
        background: 'rgba(210,225,245,0.45)',
        backdropFilter: 'blur(50px) saturate(200%)',
        WebkitBackdropFilter: 'blur(50px) saturate(200%)',
        border: '0.5px solid rgba(255,255,255,0.5)',
        boxShadow: '0 8px 40px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.35)',
      }} />
      {/* content */}
      <div style={{
        position: 'relative', zIndex: 1, padding: '10px 0',
        display: 'flex', flexDirection: 'column', gap: 2,
      }}>
        {/* window controls + sidebar toggle */}
        <div style={{
          height: 32, display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', padding: '0 10px', marginBottom: 4,
        }}>
          <MacTrafficLights />
        </div>
        {children}
      </div>
    </div>
  );
}

function MacSidebarHeader({ title }) {
  return (
    <div style={{
      padding: '14px 18px 5px',
      fontFamily: MAC_FONT, fontSize: 11, fontWeight: 700,
      color: 'rgba(0,0,0,0.5)',
    }}>{title}</div>
  );
}

// ─────────────────────────────────────────────────────────────
// Window — r:26, big shadow, sidebar + toolbar + content
// ─────────────────────────────────────────────────────────────
function MacWindow({
  width = 900, height = 600, title = 'Folder',
  sidebar, children,
}) {
  return (
    // data-om-starter: inert presence marker — Claude Design's starter-usage
    // probe reads it; it renders nothing. Keep it on this root element.
    <div data-om-starter="macos-window" style={{
      width, height, borderRadius: 26, overflow: 'hidden',
      background: '#fff',
      boxShadow: '0 0 0 1px rgba(0,0,0,0.23), 0 16px 48px rgba(0,0,0,0.35)',
      display: 'flex', position: 'relative',
      fontFamily: MAC_FONT,
    }}>
      <MacSidebar>{sidebar}</MacSidebar>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <MacToolbar title={title} />
        <div style={{ flex: 1, overflow: 'auto', padding: '4px 8px' }}>
          {children}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  MacWindow, MacSidebar, MacSidebarItem, MacSidebarHeader,
  MacToolbar, MacGlass, MacTrafficLights,
});


/* =====================================================================
   一起成长 · Family Grove 交互原型
   - 演示数据都是虚构的（星星 / 小宇，演示日 2026-11-04）
   - 不连接家庭后台、不真的上传或打印、不调用任何模型；“AI 已整理 / 检查结果”均为写死的演示内容
   - 状态只有 App 一个归属；保存到本机 localStorage，刷新即“保存后重开”
   ===================================================================== */
const { useState, useEffect, useRef } = React;

const DEMO_TODAY = '2026-11-04';
const STORE_KEY = 'family-grove-demo-v1';
const SUBJECTS = ['语文', '数学', '英语', '综合'];
const CHILDREN = [
  { id: 'xingxing', name: '星星', grade: '三年级' },
  { id: 'xiaoyu', name: '小宇', grade: '一年级' },
];

/* ---------- 日期：只做显示，不做归类推断 ---------- */
const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
const parseDay = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)); };
const fmtDay = (s) => { const t = parseDay(s); return `${t.getUTCMonth() + 1}月${t.getUTCDate()}日`; };
const weekDay = (s) => WEEK[parseDay(s).getUTCDay()];
const addDays = (s, n) => { const t = parseDay(s); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
const relDay = (s) => ({ 0: '今天', 1: '明天', 2: '后天', '-1': '昨天' })[Math.round((parseDay(s) - parseDay(DEMO_TODAY)) / 86400000)] || '';
const hm = (iso) => iso.slice(11, 16);
const nowHM = () => { const d = new Date(); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
const dayWord = (d) => (relDay(d) ? `${relDay(d)} ${fmtDay(d)}` : fmtDay(d));
const dayText = (d) => (d ? fmtDay(d) : '日期未写明');
const srcWhen = (iso, day) => (iso.slice(0, 10) === day ? hm(iso) : `${fmtDay(iso.slice(0, 10))} ${hm(iso)}`);

/* ---------- 演示资料：角色（原卷/教师答案/家长参考/原件）与读取状态分开 ---------- */
const MATERIALS = {
  'm-ce-paper': { role: '原卷', name: '第3单元测验卷.pdf', pages: 2, state: 'organized', print: 'original',
    sum: [['第 1 页', '计算 1–6 题，要求写竖式'], ['第 2 页', '应用题 7–12 题，第 10 题要画线段图']],
    next: '可以直接打印原卷（2 页）',
    mock: { title: '三年级数学 · 第3单元测验卷', lines: ['一、用竖式计算（1–6 题）', '1. 26 + 35 =　　2. 63 − 28 =　　3. 54 + 19 =', '4. 38 + 47 =　　5. 90 − 46 =　　6. 72 − 37 =', '二、解决问题（7–12 题）', '10. 画线段图表示“3 个 12”，再列式计算。'] } },
  'm-ce-key': { role: '教师答案', name: '测验卷答案.jpg', pages: 1, state: 'organized', parentOnly: true,
    sum: [['1 页', '12 题答案齐全，第 10 题附线段图示例']],
    next: '已据此整理家长参考；检查作答时优先按它核对',
    mock: { title: '答案（李老师）', lines: ['1. 61　2. 35　3. 73　4. 85　5. 44　6. 35', '7. 32 支　8. 9 个　9. 18 人', '10. 线段图 3 段，每段 12；12 × 3 = 36', '11. 48 本　12. 42 棵'] } },
  'm-ce-ref': { role: '家长参考', name: '家长参考（由教师答案整理）', pages: 1, state: 'organized', parentOnly: true, derived: true, print: 'parent',
    sum: [['1 页', '逐题答案，第 4、10 题标出要留意的步骤']],
    next: '打印给家长检查用，不给孩子看' },
  'm-ce-fix': { role: '原件', name: '订正格式示例.jpg', pages: 1, state: 'unread', from: '李老师 18:02 补充',
    why: '照片偏暗，没能读出内容。', next: '订正格式尚未读清，请看原件。' },
  'm-en-sheet': { role: '原卷', name: 'Unit 3 练习纸.pdf', pages: 2, state: 'organized', print: 'original',
    sum: [['第 1 面', '看图连线 1–3 题'], ['第 2 面', '选词填空 4–6 题（第 5 题不用做）']],
    next: '打印前先核对 19:20 的补充',
    mock: { title: 'Unit 3 Exercise', lines: ['Part 1  Look and match (1–3)', 'Part 2  Choose and fill (4–6)', '5. ________ （19:20 补充：不用做）'] } },
  'm-sign': { role: '原卷', name: '秋游安全告知书.pdf', pages: 1, state: 'organized', print: 'original',
    sum: [['1 页', '11月6日 周五秋游；回执在页面下方，需要剪下']],
    next: '打印 1 页，签好回执',
    mock: { title: '秋游安全告知书', lines: ['时间：11月6日（周五）', '请穿运动鞋，注意安全……', '— — — — 回执（请剪下）— — — —', '□ 参加　□ 不参加　　家长签字：________'] } },
  'm-xy-shu': { role: '原卷', name: '数一数练习纸.jpg', pages: 2, state: 'organized', print: 'original',
    sum: [['正面', '4 组，数一数写数字'], ['反面', '4 组，圈出数量对应的数']],
    next: '可以直接打印原卷（正反 2 页）' },
};

/* 演示“检查”结果：写死在这里，不调用 AI */
const DEMO_CHECKS = {
  'xx-sx-ce': { basis: '按教师答案核对', total: 12,
    wrong: [
      { q: '第 4 题', what: '38 + 47', answer: '75', key: '85', note: '个位满十没有向十位进 1', page: 1 },
      { q: '第 10 题', what: '画线段图表示“3 个 12”', answer: '画了 2 段', key: '3 段，每段 12', note: '少画了 1 段', page: 2 },
    ],
    doubt: [{ q: '第 11 题', what: '一共有多少本书？', answer: '字迹不清（像 48 也像 46）', key: '48 本', note: '字迹看不清，没有判定', page: 2 }] },
  'xx-en-sheet': { basis: '没有教师答案，按题目核对', total: 5, wrong: [], doubt: [] },
  'xx-yw-chao': { basis: '按书写要求核对', total: 12, unit: '字', wrong: [], doubt: [] },
  'xy-sx-shu': { basis: '没有教师答案，按题目核对', total: 8, wrong: [], doubt: [] },
};
const DEMO_ANSWERS = {
  'xx-sx-ce': { 1: ['1. 26 + 35 = 61', '2. 63 − 28 = 35', '3. 54 + 19 = 73', '4. 38 + 47 = 75', '5. 90 − 46 = 44', '6. 72 − 37 = 35'],
    2: ['7. 4 × 8 = 32（支）', '8. 45 ÷ 5 = 9（个）', '9. 36 − 18 = 18（人）', '10. 线段图：画了 2 段', '11. 字迹不清（像 48 也像 46）', '12. 6 × 7 = 42（棵）'] },
  'xx-sx-kousuan': { 1: ['……', '7. 28 ÷ 4 = 7', '8. 36 ÷ 4 = 8', '9. 45 ÷ 9 = 5', '……'] },
};

function seedTasks() {
  return [
    // —— 星星 · 11月4日：语文 2、数学 1、英语 2、综合 1 ——
    { id: 'xx-yw-chao', child: 'xingxing', subject: '语文', day: '2026-11-04', kind: 'home',
      title: '抄写第7课生字', scope: '《秋天的雨》生字表 12 个字',
      standard: ['每字写 3 遍，写在田字格本上', '写完自己圈出写得最好的 1 个字'],
      fix: { index: 0, at: '18:10', label: '更正', note: '原为每字 2 遍' },
      handIn: { label: '明早交', sub: '11月5日 交语文作业本', urgent: true }, need: '课本 p.32 · 田字格本', checkable: true,
      src: { who: '王老师', at: '2026-11-04T16:42' },
      msgs: [
        { who: '王老师', at: '2026-11-04T16:42', kind: '原消息', text: '今天语文：1. 抄写第7课生字，每字2遍；2. 预习第8课，标自然段；3. 第7课第2自然段要会背。' },
        { who: '王老师', at: '2026-11-04T18:10', kind: '更正', text: '更正一下：生字每字写3遍，不是2遍。' },
      ], mats: [] },
    { id: 'xx-yw-yuxi', child: 'xingxing', subject: '语文', day: '2026-11-04', kind: 'home',
      title: '预习第8课', scope: '《听听，秋的声音》全文',
      standard: ['读 2 遍课文', '标出自然段序号', '圈出不认识的字'],
      handIn: { label: '不用交', sub: '明天课上检查' }, need: '课本 p.34–35',
      src: { who: '王老师', at: '2026-11-04T16:42' }, msgs: 'xx-yw-chao', done: true, mats: [] },
    { id: 'xx-sx-ce', child: 'xingxing', subject: '数学', day: '2026-11-04', kind: 'home',
      title: '完成第3单元测验卷', scope: '测验卷 2 页，共 12 题',
      standard: ['12 题都做完，计算题写竖式', '做完自己检查一遍，没把握的题用铅笔圈出', '家长检查后在卷首签字'],
      handIn: { label: '明早交', sub: '11月5日 到校交给李老师', urgent: true }, need: '测验卷（需打印）· 铅笔 · 直尺', checkable: true,
      src: { who: '李老师', at: '2026-11-04T15:58' },
      msgs: [
        { who: '李老师', at: '2026-11-04T15:58', kind: '原消息', text: '第3单元测验卷今晚完成，家长检查并签字，明早交。卷子和答案见附件。' },
        { who: '李老师', at: '2026-11-04T18:02', kind: '补充', text: '附上订正格式示例，错题请按这个格式订正。' },
      ], mats: ['m-ce-paper', 'm-ce-key', 'm-ce-ref', 'm-ce-fix'] },
    { id: 'xx-en-sheet', child: 'xingxing', subject: '英语', day: '2026-11-04', kind: 'home',
      title: '完成 Unit 3 练习纸', scope: '练习纸 1 张，正反 2 面',
      standard: ['正反两面做完', '第 2 面第 5 题不用做'],
      fix: { index: 1, at: '19:20', label: '补充', note: '陈老师后来补充' },
      handIn: { label: '明天交', sub: '11月5日 英语课前交' }, need: '练习纸（需打印）', checkable: true,
      printChange: { at: '19:20', who: '陈老师', text: '第 2 面第 5 题不用做' },
      src: { who: '陈老师', at: '2026-11-04T16:20' },
      msgs: [
        { who: '陈老师', at: '2026-11-04T16:20', kind: '原消息', text: '今天英语：1. Unit 3 练习纸；2. 跟读 Part A 课文 3 遍。明天课上听写 Unit 3 单词。' },
        { who: '陈老师', at: '2026-11-04T19:20', kind: '补充', text: '练习纸第2面第5题不用做。' },
      ], mats: ['m-en-sheet'] },
    { id: 'xx-en-read', child: 'xingxing', subject: '英语', day: '2026-11-04', kind: 'home',
      title: '跟读 Unit 3 Part A 课文', scope: '课本 p.24–25',
      standard: ['跟着点读音频读 3 遍', '第 3 遍试着不看书'],
      handIn: { label: '不用交' }, need: '课本 · 点读音频',
      src: { who: '陈老师', at: '2026-11-04T16:20' }, msgs: 'xx-en-sheet', done: true, mats: [] },
    { id: 'xx-zh-sign', child: 'xingxing', subject: '综合', day: '2026-11-04', kind: 'home',
      title: '秋游告知书：家长签字', scope: '告知书 1 页，回执在页面下方',
      standard: ['家长读完告知书', '在回执上签字，勾选是否参加', '剪下回执放进书包'],
      handIn: { label: '明早交', sub: '11月5日 交给周老师', urgent: true }, need: '告知书（需打印回执）',
      src: { who: '周老师', at: '2026-11-04T17:05' },
      msgs: [{ who: '周老师', at: '2026-11-04T17:05', kind: '原消息', text: '请家长阅读秋游安全告知书，在回执签字，明早交给我。' }],
      others: [{ who: '吴老师', at: '2026-11-04T17:30', text: '周五秋游请穿运动鞋，带水壶。', day: '2026-11-06', id: 'xx-zh-trip' }],
      mats: ['m-sign'] },
    // —— 星星 · 课内安排 / 日期未写明（不计入当天）——
    { id: 'xx-en-dict', child: 'xingxing', subject: '英语', day: '2026-11-05', kind: 'class',
      title: 'Unit 3 单词课堂听写', scope: 'Unit 3 单词表', standard: ['英语课上听写，不是今晚的家庭作业'],
      handIn: { label: '课上进行' }, need: '无',
      src: { who: '陈老师', at: '2026-11-04T16:20' }, msgs: 'xx-en-sheet', mats: [] },
    { id: 'xx-yw-bei', child: 'xingxing', subject: '语文', day: null, kind: 'home',
      title: '背诵第7课第2自然段', scope: '《秋天的雨》第 2 自然段', standard: ['能不看书完整背出来'],
      handIn: { label: '检查日未写明' }, need: '课本 p.31',
      src: { who: '王老师', at: '2026-11-04T16:42' }, msgs: 'xx-yw-chao', mats: [] },
    // —— 星星 · 其他日期 ——
    { id: 'xx-sx-kousuan', child: 'xingxing', subject: '数学', day: '2026-11-03', kind: 'home',
      title: '口算练习第 15 页', scope: '口算本 p.15，共 20 题', standard: ['20 题都做完', '做完自己检查一遍'],
      handIn: { label: '已交', sub: '11月4日 早上已交' }, need: '口算本', checkable: true,
      src: { who: '李老师', at: '2026-11-03T16:10' },
      msgs: [{ who: '李老师', at: '2026-11-03T16:10', kind: '原消息', text: '今天口算本第15页。' }],
      done: true, mats: [],
      fb: { stage: 'checked', photos: 1, at: '11月3日 20:31', result: { basis: '没有教师答案，按题目核对', total: 20, right: 19, doubt: [] } } },
    { id: 'xx-yw-du', child: 'xingxing', subject: '语文', day: '2026-11-03', kind: 'home',
      title: '朗读第7课 2 遍', scope: '《秋天的雨》全文', standard: ['读 2 遍，读准“凉爽、频频点头”'],
      handIn: { label: '不用交' }, need: '课本 p.30–31',
      src: { who: '王老师', at: '2026-11-03T16:30' },
      msgs: [{ who: '王老师', at: '2026-11-03T16:30', kind: '原消息', text: '今天读第7课两遍。' }], done: true, mats: [] },
    { id: 'xx-zh-trip', child: 'xingxing', subject: '综合', day: '2026-11-06', kind: 'home',
      title: '秋游：穿运动鞋、带水壶', scope: '11月6日 周五秋游', standard: ['穿运动鞋', '带装好水的水壶'],
      handIn: { label: '当天早上' }, need: '运动鞋 · 水壶',
      src: { who: '吴老师', at: '2026-11-04T17:30' },
      msgs: [{ who: '吴老师', at: '2026-11-04T17:30', kind: '原消息', text: '周五秋游请穿运动鞋，带水壶。' }], mats: [] },
    // —— 小宇 · 11月4日 ——
    { id: 'xy-yw-er', child: 'xiaoyu', subject: '语文', day: '2026-11-04', kind: 'home',
      title: '读拼音儿歌《小青蛙》', scope: '课本 p.18', standard: ['读 3 遍，声音响亮', '最后一遍读给家长听'],
      handIn: { label: '不用交' }, need: '课本 p.18',
      src: { who: '刘老师', at: '2026-11-04T16:05' },
      msgs: [{ who: '刘老师', at: '2026-11-04T16:05', kind: '原消息', text: '今天读拼音儿歌《小青蛙》3遍，最后一遍读给家长听。' }], mats: [] },
    { id: 'xy-sx-shu', child: 'xiaoyu', subject: '数学', day: '2026-11-04', kind: 'home',
      title: '“数一数”练习纸', scope: '练习纸 1 张，正反面 8 组',
      standard: ['数对每组的个数，写在方框里', '写数字时注意 6 和 9 的方向'],
      handIn: { label: '明早交', sub: '11月5日 交给赵老师', urgent: true }, need: '练习纸（需打印）', checkable: true,
      src: { who: '赵老师', at: '2026-11-04T15:40' },
      msgs: [{ who: '赵老师', at: '2026-11-04T15:40', kind: '原消息', text: '附件练习纸今晚完成，明早交。' }], mats: ['m-xy-shu'] },
    { id: 'xy-zh-leaf', child: 'xiaoyu', subject: '综合', day: '2026-11-04', kind: 'home',
      title: '带一片落叶到学校', scope: '科学课用', standard: ['干净完整的落叶 1 片', '夹在书里带去，别折坏'],
      handIn: { label: '明早带', sub: '11月5日 科学课', urgent: true }, need: '落叶 1 片',
      src: { who: '孙老师', at: '2026-11-04T17:30' },
      msgs: [{ who: '孙老师', at: '2026-11-04T17:30', kind: '原消息', text: '明天科学课，请每位同学带一片干净完整的落叶。' }], mats: [] },
    { id: 'xy-zh-pen', child: 'xiaoyu', subject: '综合', day: '2026-11-04', kind: 'home',
      title: '明天带彩笔', scope: '美术课用', standard: ['12 色彩笔放进书包'],
      handIn: { label: '明早带', sub: '11月5日 美术课' }, need: '彩笔',
      src: { who: '孩子口头转述', at: '2026-11-04T20:40', oral: true },
      msgs: [{ who: '家长补录', at: '2026-11-04T20:40', kind: '口头补录', text: '小宇说：美术老师课上讲明天带彩笔。（群里没有这条）' }], mats: [] },
    { id: 'xy-ty-rope', child: 'xiaoyu', subject: '综合', day: '2026-11-06', kind: 'class',
      title: '体育课跳绳测试', scope: '1 分钟跳绳', standard: ['体育课上测试，不是家庭作业'],
      handIn: { label: '课上进行' }, need: '无',
      src: { who: '钱老师', at: '2026-11-04T16:50' },
      msgs: [{ who: '钱老师', at: '2026-11-04T16:50', kind: '原消息', text: '周五体育课测1分钟跳绳。' }], mats: [] },
  ];
}
const seedDb = () => ({ v: 1, child: 'xingxing', day: DEMO_TODAY, tasks: seedTasks(), prints: [], printChecked: {},
  wrongs: [{ id: 'w-ks-8', child: 'xingxing', task: 'xx-sx-kousuan', q: '第 8 题', what: '36 ÷ 4', answer: '8', key: '9', note: '商写错了', page: 1, status: 'todo' }] });

function loadDb() {
  try {
    const d = JSON.parse(window.localStorage.getItem(STORE_KEY) || 'null');
    if (d && d.v === 1 && Array.isArray(d.tasks)) {
      // 重开时，没跑完的“检查中”回到“照片已交”，不假装检查完成
      d.tasks = d.tasks.map((t) => (t.fb && t.fb.stage === 'checking' ? { ...t, fb: { ...t.fb, stage: 'uploaded' } } : t));
      return d;
    }
  } catch (e) { /* 读不到就用演示初始数据 */ }
  return seedDb();
}

/* ---------- 小图标：统一 24 网格线性图标（原生版对应 SF Symbols，见 design-notes） ---------- */
const ICONS = {
  check: 'M5 12.5l4.2 4.2L19 7', chevL: 'M15 5l-7 7 7 7', chevR: 'M9 5l7 7-7 7', plus: 'M12 5v14M5 12h14', x: 'M6 6l12 12M18 6L6 18',
  printer: 'M7 9V4h10v5M6 18H4.5A1.5 1.5 0 0 1 3 16.5v-6A1.5 1.5 0 0 1 4.5 9h15a1.5 1.5 0 0 1 1.5 1.5v6a1.5 1.5 0 0 1-1.5 1.5H18M7 14h10v6H7z',
  camera: 'M4 8.5A1.5 1.5 0 0 1 5.5 7h2.2l1.6-2h5.4l1.6 2h2.2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5zM12 16a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4z',
  doc: 'M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10A.5.5 0 0 1 6 20V4a.5.5 0 0 1 .5-.5zM14 3.5V8h4M9 12h6M9 15.5h6',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7.5V12l3 2',
  calendar: 'M5 6.5h14a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7.5a1 1 0 0 1 1-1zM4 10.5h16M8.5 4v4M15.5 4v4',
  ask: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.6M12 17v.2',
  lock: 'M7 11V8a5 5 0 0 1 10 0v3M5.5 11h13a.5.5 0 0 1 .5.5v8a.5.5 0 0 1-.5.5h-13a.5.5 0 0 1-.5-.5v-8a.5.5 0 0 1 .5-.5z',
  message: 'M4 5.5h16a1 1 0 0 1 1 1v9.5a1 1 0 0 1-1 1H10l-4.5 3.5V17H4a1 1 0 0 1-1-1V6.5a1 1 0 0 1 1-1z',
  book: 'M4 5.5c2.5-1 5.5-1 8 .5 2.5-1.5 5.5-1.5 8-.5V19c-2.5-1-5.5-1-8 .5-2.5-1.5-5.5-1.5-8-.5zM12 6v13.5',
  undo: 'M4 9h10a6 6 0 0 1 0 12H8M8 5L4 9l4 4', more: 'M5.5 12h.01M12 12h.01M18.5 12h.01',
  list: 'M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01',
  pencil: 'M15.5 4.5l4 4L9 19H5v-4zM13.5 6.5l4 4', eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  sprout: 'M12 21v-8M12 13c0-4-3-6.5-7.5-6.5 0 4 3 6.5 7.5 6.5zM12 11c0-3.6 2.7-6 7-6 0 3.8-2.8 6-7 6z',
};
function Icon({ name, size = 20 }) {
  return (
    <svg className="ico" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={name === 'more' ? 3.2 : 1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={ICONS[name]}></path>
    </svg>
  );
}

function useMedia(query) {
  const read = () => (window.matchMedia ? window.matchMedia(query).matches : false);
  const [on, setOn] = useState(read);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const sync = () => setOn(mq.matches);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, [query]);
  return on;
}

/* ---------- 通用弹出层：焦点进入、Tab 循环、Esc 关闭、关闭后焦点回到原处 ---------- */
function Sheet({ id, label, title, sub, onClose, footer, children }) {
  const box = useRef(null);
  useEffect(() => {
    const prev = document.activeElement;
    const el = box.current;
    const first = el && (el.querySelector('[data-autofocus]') || el);
    if (first) first.focus();
    return () => { if (prev && prev.focus && document.contains(prev)) prev.focus(); };
  }, []);
  const onKeyDown = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
    if (e.key !== 'Tab') return;
    const items = [...box.current.querySelectorAll('button:not([disabled]), input, textarea, [href]')];
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  return (
    <div className="scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby={`${id}-t`} ref={box} tabIndex={-1} onKeyDown={onKeyDown} data-screen-label={label}>
        <div className="sheet-h">
          <div className="sheet-t"><h2 id={`${id}-t`}>{title}</h2>{sub && <p>{sub}</p>}</div>
          <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}><Icon name="x"></Icon></button>
        </div>
        <div className="sheet-b">{children}</div>
        {footer && <div className="sheet-f">{footer}</div>}
      </div>
    </div>
  );
}

function ChoiceGroup({ value, options, onPick, label }) {
  return (
    <div className="choice" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button type="button" key={v} role="radio" aria-checked={value === v} className="choice-btn" onClick={() => onPick(v)}>{text}</button>
      ))}
    </div>
  );
}

function LeaveConfirm({ text, onStay, onLeave }) {
  const stay = useRef(null);
  useEffect(() => { if (stay.current) stay.current.focus(); }, []);
  return (
    <div className="confirm" role="alertdialog" aria-label={text}>
      <p>{text}</p>
      <div className="choice">
        <button type="button" className="btn btn-primary" ref={stay} onClick={onStay}>继续编辑</button>
        <button type="button" className="btn" onClick={onLeave}>放弃</button>
      </div>
    </div>
  );
}

/* ---------- 补录口头作业 ---------- */
function AddSheet({ childName, day, save, onClose }) {
  const [f, setF] = useState({ subject: '语文', what: '', std: '', when: 'today', inClass: false, handIn: 'unknown', teacher: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [invalid, setInvalid] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const whatRef = useRef(null);
  const dirty = !!(f.what.trim() || f.std.trim() || f.teacher.trim());
  const set = (k, v) => setF((o) => ({ ...o, [k]: v }));
  const close = () => { if (busy) return; if (dirty) setLeaving(true); else onClose(); };
  const submit = async () => {
    if (busy) return;
    if (!f.what.trim()) { setInvalid(true); setErr(''); if (whatRef.current) whatRef.current.focus(); return; }
    setBusy(true); setErr('');
    try { await save(f); }
    catch (e) { setErr('没保存上（演示：模拟网络中断）。填写的内容都还在，可以再试一次。'); setBusy(false); }
  };
  return (
    <Sheet id="add" label="补录口头作业" title="补录口头作业" sub={`给${childName} · 来源记为“孩子口头转述”，不和老师消息合并`} onClose={close}
      footer={leaving ? null : (<>
        <button type="button" className="btn" onClick={close} disabled={busy}>取消</button>
        <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>{busy ? '保存中…' : err ? '重试保存' : '保存到清单'}</button>
      </>)}>
      {leaving ? (
        <LeaveConfirm text="这条补录还没保存，要放弃吗？" onStay={() => setLeaving(false)} onLeave={onClose}></LeaveConfirm>
      ) : (<>
        <div className="field"><span className="field-l" id="add-subj">科目</span>
          <ChoiceGroup label="科目" value={f.subject} onPick={(v) => set('subject', v)} options={SUBJECTS.map((s) => [s, s])}></ChoiceGroup></div>
        <label className="field"><span className="field-l">要做什么</span>
          <input id="add-what" ref={whatRef} data-autofocus className="input" value={f.what} aria-invalid={invalid && !f.what.trim()} aria-describedby="add-what-err"
            placeholder="例如：口算本第 16 页" onChange={(e) => { set('what', e.target.value); setInvalid(false); }}></input>
          {invalid && !f.what.trim() && <span className="err" id="add-what-err">写一下要做什么</span>}
        </label>
        <label className="field"><span className="field-l">完成标准<small>可不填；不填就标为“完成标准未提供”</small></span>
          <textarea className="textarea" value={f.std} placeholder="例如：做完自己检查一遍；家长签字" onChange={(e) => set('std', e.target.value)}></textarea></label>
        <div className="field"><span className="field-l">什么时候做<small>默认是正在看的这一天，可改</small></span>
          <ChoiceGroup label="什么时候做" value={f.when} onPick={(v) => set('when', v)} options={[['today', dayWord(day)], ['tomorrow', dayWord(addDays(day, 1))], ['unknown', '还不知道']]}></ChoiceGroup>
          <div className="choice"><button type="button" role="switch" aria-checked={f.inClass} className="choice-btn" onClick={() => set('inClass', !f.inClass)}>{f.inClass ? '✓ ' : ''}课堂上做，不算家庭作业</button></div>
        </div>
        <div className="field"><span className="field-l">交回<small>默认“还不知道”，不推断</small></span>
          <ChoiceGroup label="交回" value={f.handIn} onPick={(v) => set('handIn', v)} options={[['morning', '明早交'], ['none', '不用交'], ['unknown', '还不知道']]}></ChoiceGroup></div>
        <label className="field"><span className="field-l">哪位老师说的<small>可不填</small></span>
          <input className="input" value={f.teacher} placeholder="例如：美术老师" onChange={(e) => set('teacher', e.target.value)}></input></label>
        {err && <p className="err" role="alert">{err}</p>}
      </>)}
    </Sheet>
  );
}

/* ---------- 交作答照片（演示：不上传，不读真实照片） ---------- */
function UploadSheet({ task, pages, upload, onClose }) {
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [leaving, setLeaving] = useState(false);
  const close = () => { if (busy) return; if (photos.length) setLeaving(true); else onClose(); };
  const add = () => setPhotos((p) => [...p, `示例照片 ${p.length + 1}（第 ${p.length + 1} 页）`]);
  const submit = async () => {
    if (busy || !photos.length) return;
    setBusy(true); setErr('');
    try { await upload(photos.length); }
    catch (e) { setErr('没上传成功（演示：模拟网络中断）。照片还在，可以重试。'); setBusy(false); }
  };
  return (
    <Sheet id="up" label="交作答照片" title="交作答照片" sub={`${task.title} · 演示：不会真的上传，也不读取真实照片`} onClose={close}
      footer={leaving ? null : (<>
        <button type="button" className="btn" onClick={close} disabled={busy}>取消</button>
        <button type="button" className="btn btn-primary" onClick={submit} disabled={busy || !photos.length}>{busy ? '上传中…' : err ? '重试上传' : `上传 ${photos.length} 张`}</button>
      </>)}>
      {leaving ? (
        <LeaveConfirm text={`这 ${photos.length} 张照片还没上传，要放弃吗？`} onStay={() => setLeaving(false)} onLeave={onClose}></LeaveConfirm>
      ) : (<>
        <p className="hint">按页拍，一页一张。上传后只表示“照片已保存”，检查要另外开始。</p>
        <div className="photo-list">
          {photos.map((p, i) => (
            <div className="photo-item" key={p}><Icon name="camera"></Icon><span>{p}</span>
              <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => setPhotos((all) => all.filter((_, j) => j !== i))}>移除</button></div>
          ))}
          {photos.length < pages && (
            <button type="button" className="photo-slot" data-autofocus onClick={add} disabled={busy}><Icon name="plus"></Icon>添加示例照片（第 {photos.length + 1} 页，共 {pages} 页）</button>
          )}
        </div>
        {err && <p className="err" role="alert">{err}</p>}
      </>)}
    </Sheet>
  );
}

/* ---------- 文字反馈与手动错题：照片可选，不调用 AI，不自动标已办或判错 ---------- */
function DemoPhotos({ photos, setPhotos, busy }) {
  const add = () => setPhotos((all) => [...all, `示例照片 ${all.reduce((m, x) => Math.max(m, Number(x.split(' ')[1]) || 0), 0) + 1}`]);
  return (
    <div className="photo-list">
      {photos.map((x, i) => (
        <div className="photo-item" key={x}><Icon name="camera"></Icon><span>{x}（演示，不上传）</span>
          <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => setPhotos((all) => all.filter((_, j) => j !== i))}>移除</button></div>
      ))}
      <button type="button" className="photo-slot" onClick={add} disabled={busy}><Icon name="plus"></Icon>添加示例照片（可不加）</button>
    </div>
  );
}

function NoteSheet({ task, save, onClose }) {
  const [text, setText] = useState('');
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [invalid, setInvalid] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const area = useRef(null);
  const dirty = !!(text.trim() || photos.length);
  const close = () => { if (busy) return; if (dirty) setLeaving(true); else onClose(); };
  const submit = async () => {
    if (busy) return;
    if (!text.trim()) { setInvalid(true); setErr(''); if (area.current) area.current.focus(); return; }
    setBusy(true); setErr('');
    try { await save({ text, photos: photos.length }); }
    catch (e) { setErr('没保存上（演示：模拟网络中断）。写的内容和照片都还在，可以再试一次。'); setBusy(false); }
  };
  return (
    <Sheet id="nt" label="写反馈" title="写反馈" sub={`${task.subject} · ${task.title} · 不调用 AI；保存后不会自动标已办，也不会自动判错`} onClose={close}
      footer={leaving ? null : (<>
        <button type="button" className="btn" onClick={close} disabled={busy}>取消</button>
        <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>{busy ? '保存中…' : err ? '重试保存' : '保存反馈'}</button>
      </>)}>
      {leaving ? (
        <LeaveConfirm text="这条反馈还没保存，要放弃吗？" onStay={() => setLeaving(false)} onLeave={onClose}></LeaveConfirm>
      ) : (<>
        <label className="field"><span className="field-l">反馈</span>
          <textarea id="nt-text" ref={area} data-autofocus className="textarea" value={text} aria-invalid={invalid && !text.trim()} aria-describedby="nt-text-err"
            placeholder="例如：读了 2 遍，第 3 自然段还不太顺" onChange={(e) => { setText(e.target.value); setInvalid(false); }}></textarea>
          {invalid && !text.trim() && <span className="err" id="nt-text-err">写几句反馈再保存</span>}
        </label>
        <div className="field"><span className="field-l">照片<small>可不加</small></span>
          <DemoPhotos photos={photos} setPhotos={setPhotos} busy={busy}></DemoPhotos></div>
        <p className="hint">保存后记在这一项下面，重开还在；需要的话，保存后可以在这条反馈下记错题。</p>
        {err && <p className="err" role="alert">{err}</p>}
      </>)}
    </Sheet>
  );
}

function WrongNoteSheet({ task, note, save, onClose }) {
  const [f, setF] = useState({ q: '', note: '' });
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [invalid, setInvalid] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const qRef = useRef(null);
  const dirty = !!(f.q.trim() || f.note.trim() || photos.length);
  const set = (k, v) => setF((o) => ({ ...o, [k]: v }));
  const close = () => { if (busy) return; if (dirty) setLeaving(true); else onClose(); };
  const submit = async () => {
    if (busy) return;
    if (!f.q.trim()) { setInvalid(true); setErr(''); if (qRef.current) qRef.current.focus(); return; }
    setBusy(true); setErr('');
    try { await save({ q: f.q, note: f.note, photos: photos.length }); }
    catch (e) { setErr('没保存上（演示：模拟网络中断）。填写的内容都还在，可以再试一次。'); setBusy(false); }
  };
  return (
    <Sheet id="wn" label="记错题" title="记一道错题" sub={`${task.title}${note ? ` · 记在 ${note.at} 的反馈下` : ''} · 手动记录，不调用 AI`} onClose={close}
      footer={leaving ? null : (<>
        <button type="button" className="btn" onClick={close} disabled={busy}>取消</button>
        <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>{busy ? '保存中…' : err ? '重试保存' : '保存错题'}</button>
      </>)}>
      {leaving ? (
        <LeaveConfirm text="这道错题还没保存，要放弃吗？" onStay={() => setLeaving(false)} onLeave={onClose}></LeaveConfirm>
      ) : (<>
        <label className="field"><span className="field-l">哪一题</span>
          <input id="wn-q" ref={qRef} data-autofocus className="input" value={f.q} aria-invalid={invalid && !f.q.trim()} aria-describedby="wn-q-err"
            placeholder="例如：第 12 题" onChange={(e) => { set('q', e.target.value); setInvalid(false); }}></input>
          {invalid && !f.q.trim() && <span className="err" id="wn-q-err">写一下是哪一题</span>}
        </label>
        <label className="field"><span className="field-l">错在哪<small>可不填</small></span>
          <textarea id="wn-note" className="textarea" value={f.note} placeholder="例如：进位漏了" onChange={(e) => set('note', e.target.value)}></textarea></label>
        <div className="field"><span className="field-l">照片<small>可不加</small></span>
          <DemoPhotos photos={photos} setPhotos={setPhotos} busy={busy}></DemoPhotos></div>
        <p className="hint">和检查出的错题一样进入“错题订正”，可以标订正好了，也可以重开。</p>
        {err && <p className="err" role="alert">{err}</p>}
      </>)}
    </Sheet>
  );
}

/* ---------- 打印（演示）：原卷与家长参考分开；依据变了先核对，不绕过守卫 ---------- */
function PrintSheet({ task, mat, kind, childName, checkedAt, markChecked, doPrint, openMsgs, onClose }) {
  const [busy, setBusy] = useState(false);
  const needsCheck = !!(task.printChange && !checkedAt);
  const go = async () => { if (busy || needsCheck) return; setBusy(true); try { await doPrint(); } catch (e) { setBusy(false); } };
  return (
    <Sheet id="pr" label="打印" title={kind === 'parent' ? '打印家长参考' : '打印原卷'} sub="演示：送到演示打印机，不会真的出纸" onClose={onClose}
      footer={<>
        <button type="button" className="btn" onClick={onClose}>取消</button>
        <button type="button" id="pr-print" className="btn btn-primary" data-autofocus={needsCheck ? undefined : true} onClick={go} disabled={busy || needsCheck}><Icon name="printer"></Icon>{busy ? '发送中…' : '打印（演示）'}</button>
      </>}>
      <dl className="kv">
        <dt>内容</dt><dd>{mat.name} · {mat.pages} 页</dd>
        <dt>给谁用</dt><dd>{kind === 'parent' ? '家长检查用，不给孩子看' : `${childName}做作业用`}</dd>
        <dt>依据</dt><dd>{task.src.who} {srcWhen(task.src.at, DEMO_TODAY)} 原消息{task.printChange ? ` + ${task.printChange.who} ${task.printChange.at} 补充` : ''}</dd>
      </dl>
      {task.printChange && (needsCheck ? (
        <div className="notice" role="alert">
          <span><b>打印依据变了。</b>{task.printChange.at} {task.printChange.who}补充：“{task.printChange.text}”。之前核对过的打印依据不再适用，请先看一眼再打印。</span>
          <div className="choice">
            <button type="button" className="btn" onClick={openMsgs}><Icon name="message"></Icon>看原消息</button>
            <button type="button" className="btn btn-warn" data-autofocus onClick={() => { markChecked(); requestAnimationFrame(() => { const b = document.getElementById('pr-print'); if (b) b.focus(); }); }}>我已核对新依据</button>
          </div>
        </div>
      ) : (
        <div className="notice notice-ok">已按 {task.printChange.at} 的补充核对（{checkedAt}），可以打印。</div>
      ))}
    </Sheet>
  );
}

/* ---------- 资料 / 原件查看 ---------- */
function MatStates({ m }) {
  return (
    <span className="mat-states">
      {m.derived ? <span className="chip chip-plain">由教师答案整理</span> : <span className="chip chip-saved"><Icon name="doc" size={14}></Icon>原件已保存</span>}
      {m.state === 'organized' ? <span className="chip chip-ai">AI 已整理 · 演示</span> : <span className="chip chip-unread">尚未读清</span>}
      {m.parentOnly && <span className="chip chip-plain"><Icon name="lock" size={14}></Icon>仅家长看</span>}
    </span>
  );
}

function PageMock({ title, lines, mark, caption }) {
  return (
    <figure className="page-mock" aria-label={title}>
      <h3>{title}</h3>
      {lines.map((l, i) => <p key={i}>{mark && l.startsWith(mark) ? <mark>{l}</mark> : l}</p>)}
      <figcaption className="page-cap">{caption}</figcaption>
    </figure>
  );
}

function MaterialSheet({ mat, task, onPrint, onClose }) {
  const organized = mat.state === 'organized';
  return (
    <Sheet id="mt" label="资料" title={`${mat.role} · ${mat.name}`} sub={`${task.subject} · ${task.title}`} onClose={onClose}
      footer={<>
        {mat.print && <button type="button" className="btn btn-primary" onClick={() => onPrint(mat)}><Icon name="printer"></Icon>{mat.print === 'parent' ? '打印家长参考' : '打印原卷'}</button>}
        <button type="button" className="btn" data-autofocus onClick={onClose}>关闭</button>
      </>}>
      <MatStates m={mat}></MatStates>
      {organized ? (<>
        <dl className="kv">
          {mat.sum.map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>)}
          <dt>下一步</dt><dd>{mat.next}</dd>
        </dl>
        {mat.mock && <PageMock title={mat.mock.title} lines={mat.mock.lines} caption="演示：用文字排出原件内容；正式版在这里显示原件页面"></PageMock>}
      </>) : (<>
        <p className="mat-unread">原件已保存，但{mat.why}这里不显示任何猜测出来的内容。</p>
        <dl className="kv"><dt>来源</dt><dd>{mat.from}</dd><dt>下一步</dt><dd>{mat.next}</dd></dl>
        <div className="photo-slot"><Icon name="doc"></Icon>原件位置：正式版直接打开原图。演示里不放真实照片。</div>
      </>)}
    </Sheet>
  );
}

function AnswerSheet({ task, page, mark, onClose }) {
  const pages = DEMO_ANSWERS[task.id] || {};
  const [p, setP] = useState(page || 1);
  const lines = pages[p] || ['（演示）这一页的作答内容'];
  const count = Math.max(1, Object.keys(pages).length);
  return (
    <Sheet id="an" label="作答照片" title={`作答照片 · 第 ${p} 页`} sub={`${task.title} · 孩子原答，不改动`} onClose={onClose}
      footer={<>
        {count > 1 && <button type="button" className="btn" onClick={() => setP(p === 1 ? 2 : 1)}>看第 {p === 1 ? 2 : 1} 页</button>}
        <button type="button" className="btn" data-autofocus onClick={onClose}>关闭</button>
      </>}>
      <PageMock title={`第 ${p} 页 · 原答`} lines={lines} mark={mark ? mark.replace('第 ', '').replace(' 题', '.') : null}
        caption="演示：用文字代替照片；正式版显示原照片并框出对应题目"></PageMock>
    </Sheet>
  );
}

function MessageSheet({ task, msgs, gotoOther, onClose }) {
  return (
    <Sheet id="ms" label="原消息" title="原消息" sub={`只列出和“${task.title}”有关的原话；补充和更正按时间排在后面`} onClose={onClose}
      footer={<button type="button" className="btn" data-autofocus onClick={onClose}>关闭</button>}>
      <div className="bubbles">
        {msgs.map((m) => (
          <div className="bubble" key={m.at + m.kind}>
            <div className="bubble-meta"><b>{m.who}</b><span>{srcWhen(m.at, DEMO_TODAY)}</span>
              <span className={`chip ${m.kind === '原消息' ? 'chip-plain' : m.kind === '口头补录' ? 'chip-saved' : 'chip-coral'}`}>{m.kind}</span></div>
            <p>{m.text}</p>
          </div>
        ))}
      </div>
      {task.others && task.others.map((o) => (
        <div className="d-sec" key={o.at}>
          <p className="hint">另一位老师的相关消息，没有合并进这一项：</p>
          <div className="bubble bubble-other">
            <div className="bubble-meta"><b>{o.who}</b><span>{srcWhen(o.at, DEMO_TODAY)}</span></div>
            <p>{o.text}</p>
          </div>
          <div><button type="button" className="btn btn-quiet" onClick={() => gotoOther(o)}>已单独列在 {fmtDay(o.day)}，去看看<Icon name="chevR" size={18}></Icon></button></div>
        </div>
      ))}
    </Sheet>
  );
}

/* ---------- 清单行与分组 ---------- */
function doneLabel(t) {
  if (t.kind === 'class') return t.day ? `${fmtDay(t.day)} 课上` : '课上做 · 日期未写明';
  if (!t.day) return '日期未写明';
  const r = relDay(t.day);
  return r === '今天' ? '今晚完成' : r ? `${r}完成` : `${fmtDay(t.day)}完成`;
}
function progressText(t, wrongs) {
  const fb = t.fb;
  if (!fb) return null;
  if (fb.stage === 'uploaded') return { tone: 'plain', text: `照片已交 ${fb.photos} 张，还没检查` };
  if (fb.stage === 'checking') return { tone: 'plain', text: '检查中（演示）' };
  const todo = wrongs.filter((w) => w.task === t.id && w.status === 'todo').length;
  const doubt = (fb.result.doubt || []).length;
  const parts = ['已检查', todo ? `${todo} 题待订正` : '没有待订正', doubt ? `${doubt} 题待你看` : ''].filter(Boolean);
  return { tone: todo || doubt ? 'coral' : 'leaf', text: parts.join(' · ') };
}

function TaskRow({ t, selected, onOpen, onToggle, wrongs }) {
  const mats = t.mats.map((id) => MATERIALS[id]);
  const unread = mats.filter((m) => m.state === 'unread').length;
  const prog = progressText(t, wrongs);
  return (
    <div className="row" data-row={t.id} data-sel={selected ? 'true' : 'false'} data-done={t.done ? 'true' : 'false'}>
      {t.kind === 'class' ? (
        <span className="leaf" aria-hidden="true"><i><Icon name="book" size={15}></Icon></i></span>
      ) : (
        <button type="button" className="leaf" aria-pressed={!!t.done} aria-label={`${t.done ? '改回待办' : '标记已办'}：${t.title}`} onClick={() => onToggle(t.id)}>
          <i><Icon name="check" size={16}></Icon></i>
        </button>
      )}
      <button type="button" className="row-main" aria-current={selected ? 'true' : undefined} onClick={() => onOpen(t.id)}>
        <span className="row-title">{t.title}</span>
        <span className="row-std">{t.scope}。{t.standard.length ? t.standard.join('；') : '完成标准未提供'}</span>
        <span className="row-meta">
          <span>{doneLabel(t)}</span>
          {t.handIn.urgent ? <span className="chip chip-coral">{t.handIn.label}</span> : <span>· {t.handIn.label}</span>}
          {t.fix && <span className="chip chip-plain">{t.fix.at} {t.fix.label}</span>}
          {mats.length > 0 && <span>· {mats.length} 份资料{unread ? `（${unread} 份尚未读清）` : ''}</span>}
          {(t.notes || []).length > 0 && <span>· 反馈 {t.notes.length} 条</span>}
          <span className="row-src">· {t.src.oral ? '孩子口头' : t.src.who} {hm(t.src.at)}</span>
        </span>
        {prog && <span className={`chip chip-${prog.tone}`}>{prog.text}</span>}
      </button>
    </div>
  );
}

function SubjectGroups({ tasks, selId, onOpen, onToggle, wrongs }) {
  return SUBJECTS.map((s) => {
    const items = tasks.filter((t) => t.subject === s);
    if (!items.length) return null;
    return (
      <section className="group" key={s} aria-label={s}>
        <div className="group-h"><span className="sign">{s}<b>{items.length} 项</b></span></div>
        {items.map((t) => <TaskRow key={t.id} t={t} selected={t.id === selId} onOpen={onOpen} onToggle={onToggle} wrongs={wrongs}></TaskRow>)}
      </section>
    );
  });
}

/* ---------- 事项详情 ---------- */
function MaterialRow({ m, id, prints, onView, onPrint }) {
  const log = prints.filter((p) => p.mat === id);
  return (
    <div className="mat" data-state={m.state}>
      <div className="mat-top">
        <span className="mat-role" data-role={m.role}>{m.role}</span>
        <span className="mat-name">{m.name}</span>
        <MatStates m={m}></MatStates>
      </div>
      {m.state === 'organized' ? (<>
        <p className="mat-sum">{m.sum.map(([k, v], i) => <React.Fragment key={k}>{i > 0 && '；'}<b>{k}</b> {v}</React.Fragment>)}</p>
        <span className="mat-next">下一步：{m.next}</span>
      </>) : (
        <p className="mat-unread">{m.why}{m.next}</p>
      )}
      <div className="mat-actions">
        <button type="button" className="btn" onClick={() => onView(id)}><Icon name="eye"></Icon>{m.state === 'organized' ? '查看' : '打开原件'}</button>
        {m.print && <button type="button" className="btn btn-primary" onClick={() => onPrint(id)}><Icon name="printer"></Icon>{m.print === 'parent' ? '打印家长参考' : '打印原卷'}</button>}
        {log.length > 0 && <span className="mat-print-log">已送演示打印 {log.length} 次 · 最近 {log[log.length - 1].at}</span>}
      </div>
    </div>
  );
}

function Feedback({ t, wrongs, busyIds, ctx }) {
  const fb = t.fb;
  const notes = t.notes || [];
  const key = t.mats.map((id) => MATERIALS[id]).find((m) => m.role === '教师答案' && m.state === 'organized');
  const mine = wrongs.filter((w) => w.task === t.id);
  const checked = mine.filter((w) => !w.manual);
  const item = (w) => <WrongItem key={w.id} w={w} busy={busyIds.includes(w.id)} ctx={ctx} task={t}></WrongItem>;
  return (
    <section className="d-sec" aria-labelledby={`fb-${t.id}`}>
      <h3 className="d-sec-h" id={`fb-${t.id}`}>反馈与订正</h3>
      <div className="fb">
        {t.checkable && !fb && (
          <div className="fb-line">
            <p>还没交作答照片。{key ? '检查时优先按教师答案核对。' : '这项没有教师答案。'}</p>
            <button type="button" className="btn btn-primary" onClick={() => ctx.openUpload(t.id)}><Icon name="camera"></Icon>交作答照片</button>
          </div>
        )}
        {fb && fb.stage === 'uploaded' && (
          <div className="fb-line">
            <p><b>照片已保存 {fb.photos} 张</b>（{fb.at}）。还没检查，保存不等于看懂。</p>
            <button type="button" className="btn btn-primary" onClick={() => ctx.startCheck(t.id)}>开始检查（演示）</button>
          </div>
        )}
        {fb && fb.stage === 'checking' && (
          <div className="fb-line" role="status"><span className="spinner" aria-hidden="true"></span><p>正在检查（演示，不调用 AI）…</p></div>
        )}
        {fb && fb.stage === 'checked' && (<>
          <div className="fb-line">
            <p className="fb-sum">{fb.result.total} {fb.result.unit || '题'}：{fb.result.right} 对 · {checked.length} 错{(fb.result.doubt || []).length ? ` · ${fb.result.doubt.length} 待你看` : ''}
              <span>　{fb.result.basis} · {fb.at} · 演示结果</span></p>
            <button type="button" className="btn" onClick={() => ctx.openAnswer(t.id, 1, null)}><Icon name="eye"></Icon>作答照片</button>
          </div>
          {(fb.result.doubt || []).map((d) => (
            <div className="doubt" key={d.q}>
              <div className="wq-top"><Icon name="ask"></Icon><span className="wq-q">{d.q} · AI 疑点</span><span className="chip chip-demo">演示</span></div>
              <div className="wq-body"><span>{d.what}</span>原答：{d.answer}　教师答案：{d.key}<span>{d.note}。只需要看这一题，其他不用再确认。</span></div>
              <div className="wq-actions">
                <button type="button" className="btn" onClick={() => ctx.openAnswer(t.id, d.page, d.q)}>看原答</button>
                <button type="button" className="btn" onClick={() => ctx.resolveDoubt(t.id, d, true)}>我看了：对</button>
                <button type="button" className="btn" onClick={() => ctx.resolveDoubt(t.id, d, false)}>我看了：错</button>
              </div>
            </div>
          ))}
          {checked.length > 0 && <div className="wq-list">{checked.map(item)}</div>}
          {!checked.length && !(fb.result.doubt || []).length && <p className="hint">演示结果：没有需要订正的地方。</p>}
        </>)}
        {notes.map((n) => (
          <div className="note" key={n.id}>
            <div className="wq-top"><span className="wq-q">家长反馈 · {n.at}</span>
              <span className="chip chip-plain">{n.photos ? `照片 ${n.photos} 张 · 演示` : '只有文字'}</span></div>
            <p className="note-text">{n.text}</p>
            {mine.some((w) => w.noteId === n.id) && <div className="wq-list">{mine.filter((w) => w.noteId === n.id).map(item)}</div>}
            <div className="wq-actions"><button type="button" className="btn" onClick={() => ctx.openWrongNote(t.id, n.id)}><Icon name="pencil"></Icon>记一道错题</button></div>
          </div>
        ))}
        <div className="fb-line">
          {!notes.length && <p>{t.checkable ? (fb ? '还可以写几句文字反馈，照片可加可不加。' : '也可以只写文字，照片可加可不加。') : '还没有反馈。可以只写文字，照片可加可不加。'}</p>}
          <button type="button" className={notes.length ? 'btn btn-quiet' : 'btn'} onClick={() => ctx.openNote(t.id)}>
            <Icon name={notes.length ? 'plus' : 'pencil'}></Icon>{notes.length ? '再写一条反馈' : '写文字反馈'}</button>
        </div>
      </div>
    </section>
  );
}

function WrongItem({ w, busy, ctx, task }) {
  return (
    <div className="wq" data-status={w.status}>
      <div className="wq-top">
        <span className="wq-q">{w.q} · 错题</span>
        {w.manual && <span className="chip chip-plain">家长记录</span>}
        {w.status === 'done' ? <span className="chip chip-leaf">已订正 {w.doneAt}</span> : <span className="chip chip-coral">待订正</span>}
      </div>
      {w.manual
        ? <div className="wq-body">{w.note || '原因没写'}<span>{w.photos ? `照片 ${w.photos} 张（演示）` : '没有照片'} · 手动记录，没有调用 AI</span></div>
        : <div className="wq-body"><span>{w.what}</span>原答：{w.answer}　教师答案：{w.key}<span>{w.note}（演示）</span></div>}
      <div className="wq-actions">
        {!w.manual && <button type="button" className="btn" onClick={() => ctx.openAnswer(task.id, w.page, w.q)}>看原答</button>}
        {w.status === 'done'
          ? <button type="button" className="btn" disabled={busy} onClick={() => ctx.setWrong(w, 'todo')}><Icon name="undo"></Icon>{busy ? '保存中…' : '重开订正'}</button>
          : <button type="button" className="btn btn-primary" disabled={busy} onClick={() => ctx.setWrong(w, 'done')}><Icon name="pencil"></Icon>{busy ? '保存中…' : '订正好了'}</button>}
      </div>
    </div>
  );
}

function TaskDetail({ t, db, busyIds, ctx, hideDoneButton }) {
  const mats = t.mats;
  const wrongs = db.wrongs.filter((w) => w.child === t.child);
  const msgCount = ctx.msgsOf(t).length + (t.others ? t.others.length : 0);
  return (<>
    <header className="d-head">
      <div className="d-top">
        <span className="sign">{t.subject}</span>
        <span className="d-source"><Icon name="message" size={16}></Icon>{t.src.oral ? `孩子口头转述 · 家长补录 ${hm(t.src.at)}` : `${t.src.who} · ${srcWhen(t.src.at, DEMO_TODAY)} 发布`}</span>
        <button type="button" className="btn btn-quiet" onClick={() => ctx.openMsgs(t.id)}>看原消息（{msgCount}）</button>
      </div>
      <h1 className="d-title">{t.title}</h1>
      <p className="d-scope">{t.scope}</p>
      {!hideDoneButton && (
        <div className="d-actions">
          {t.kind === 'class'
            ? <span className="chip chip-plain">课堂上进行 · 不算家庭作业</span>
            : <button type="button" className={`btn ${t.done ? '' : 'btn-primary'}`} onClick={() => ctx.toggleDone(t.id)}>
                <Icon name={t.done ? 'undo' : 'check'}></Icon>{t.done ? '已办 · 改回待办' : '标记已办'}</button>}
        </div>
      )}
    </header>

    <div className="d-facts">
      <div className="fact"><span className="fact-k"><Icon name="clock" size={16}></Icon>完成</span>
        <span className="fact-v">{doneLabel(t)}<small>{t.day ? `${fmtDay(t.day)} ${weekDay(t.day)}${t.dateBy ? ' · 日期由家长补上' : ''}` : '日期未知，不猜；可以由家长补上'}</small></span>
        {!t.day && (
          <div className="choice">
            <button type="button" className="btn" onClick={() => ctx.setTaskDay(t.id, addDays(DEMO_TODAY, 1))}>定在明天</button>
            <button type="button" className="btn" onClick={() => ctx.setTaskDay(t.id, addDays(DEMO_TODAY, 2))}>定在后天</button>
          </div>
        )}
      </div>
      <div className="fact" data-tone={t.handIn.urgent ? 'coral' : undefined}><span className="fact-k"><Icon name="calendar" size={16}></Icon>交回</span>
        <span className="fact-v">{t.handIn.label}{t.handIn.sub && <small>{t.handIn.sub}</small>}</span></div>
      <div className="fact"><span className="fact-k"><Icon name="book" size={16}></Icon>所需</span>
        <span className="fact-v">{t.need}{mats.length > 0 && <small>{mats.length} 份资料见下方</small>}</span></div>
    </div>

    <section className="d-sec" aria-labelledby={`std-${t.id}`}>
      <h3 className="d-sec-h" id={`std-${t.id}`}>完成标准</h3>
      {t.standard.length ? (
        <ul className="std-list">
          {t.standard.map((s, i) => (
            <li key={s}><span>{s}{t.fix && t.fix.index === i && <span className="std-fix"><span className="chip chip-coral">{t.fix.at} {t.fix.label} · {t.fix.note}</span></span>}</span></li>
          ))}
        </ul>
      ) : <p className="hint">完成标准未提供，待补充；这里不猜。</p>}
    </section>

    {mats.length > 0 && (
      <section className="d-sec" aria-labelledby={`mat-${t.id}`}>
        <h3 className="d-sec-h" id={`mat-${t.id}`}>资料</h3>
        <div className="mats">
          {mats.map((id) => <MaterialRow key={id} id={id} m={MATERIALS[id]} prints={db.prints} onView={(mid) => ctx.openMat(t.id, mid)} onPrint={(mid) => ctx.openPrint(t.id, mid)}></MaterialRow>)}
        </div>
      </section>
    )}

    <Feedback t={t} wrongs={wrongs} busyIds={busyIds} ctx={ctx}></Feedback>
  </>);
}

function WrongDetail({ w, t, busy, ctx }) {
  return (<>
    <header className="d-head">
      <div className="d-top">
        <span className="sign">{t.subject}</span>
        <span className="d-source">来自 {t.title} · {dayText(t.day)}</span>
        <button type="button" className="btn btn-quiet" onClick={() => ctx.gotoTask(t)}>回到这份作业<Icon name="chevR" size={18}></Icon></button>
      </div>
      <h1 className="d-title">{w.q}{w.what ? `：${w.what}` : ''}</h1>
    </header>
    <div className="d-facts">
      {w.manual ? (<>
        <div className="fact"><span className="fact-k">家长记录</span><span className="fact-v">{w.note || '原因没写'}<small>来自 {w.noteAt} 的反馈</small></span></div>
        <div className="fact"><span className="fact-k">原答</span><span className="fact-v">没有记录<small>{w.photos ? `照片 ${w.photos} 张（演示）` : '没有照片'} · 没有调用 AI</small></span></div>
      </>) : (<>
        <div className="fact"><span className="fact-k">孩子原答</span><span className="fact-v">{w.answer}</span></div>
        <div className="fact"><span className="fact-k">教师答案</span><span className="fact-v">{w.key}</span></div>
      </>)}
      <div className="fact" data-tone={w.status === 'todo' ? 'coral' : undefined}><span className="fact-k">订正</span>
        <span className="fact-v">{w.status === 'done' ? `已订正 ${w.doneAt}` : '待订正'}<small>只记已办 / 待办</small></span></div>
    </div>
    <div className="wq-list"><WrongItem w={w} busy={busy} ctx={ctx} task={t}></WrongItem></div>
  </>);
}

/* ---------- App：唯一状态归属 ---------- */
function App() {
  const [db, setDb] = useState(loadDb);
  const [view, setView] = useState('today');
  const [sel, setSel] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [menu, setMenu] = useState(null);
  const [toast, setToast] = useState(null);
  const [failNext, setFailNext] = useState(false);
  const [busyIds, setBusyIds] = useState([]);
  const [mDetail, setMDetail] = useState(false);
  const isMobile = useMedia('(max-width: 899px)');
  const failRef = useRef(false);
  const toastTimer = useRef(null);
  failRef.current = failNext;

  useEffect(() => { try { window.localStorage.setItem(STORE_KEY, JSON.stringify(db)); } catch (e) { /* 演示：写不进也不影响操作 */ } }, [db]);
  useEffect(() => {
    const onPop = () => setMDetail(false);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  useEffect(() => { if (isMobile) window.scrollTo(0, 0); }, [mDetail, isMobile]);

  const child = db.child, day = db.day;
  const childName = CHILDREN.find((c) => c.id === child).name;
  const mine = db.tasks.filter((t) => t.child === child);
  const order = (list) => SUBJECTS.flatMap((s) => list.filter((t) => t.subject === s));
  const dayHome = order(mine.filter((t) => t.day === day && t.kind === 'home'));
  const dayClass = order(mine.filter((t) => t.day === day && t.kind === 'class'));
  // 有日期的课内安排与日期未写明分开；课堂上做但日期未知的仍是课内，只在“日期未写明”里出现一次
  const later = mine.filter((t) => !t.day || (t.kind === 'class' && t.day >= day));
  const laterOther = later.filter((t) => t.day !== day);
  const laterClass = later.filter((t) => t.kind === 'class' && t.day).sort((a, b) => a.day.localeCompare(b.day));
  const laterUndated = order(later.filter((t) => !t.day));
  const wrongs = db.wrongs.filter((w) => w.child === child);
  const wrongTodo = wrongs.filter((w) => w.status === 'todo');
  const wrongDone = wrongs.filter((w) => w.status === 'done');
  const doneCount = dayHome.filter((t) => t.done).length;
  const rel = relDay(day);

  const listForView = view === 'today' ? [...dayHome, ...dayClass] : view === 'later' ? [...laterClass, ...laterUndated] : [...wrongTodo, ...wrongDone];
  const selItem = listForView.find((x) => x.id === sel) || (isMobile ? null : listForView[0]) || null;

  /* ----- 写入（演示）----- */
  const update = (fn) => setDb((d) => { const n = { ...d, tasks: d.tasks.slice(), wrongs: d.wrongs.slice(), prints: d.prints.slice(), printChecked: { ...d.printChecked } }; fn(n); return n; });
  const patchTask = (id, fn) => update((n) => { n.tasks = n.tasks.map((t) => (t.id === id ? { ...t, ...fn(t) } : t)); });
  const demoSave = (ms) => new Promise((resolve, reject) => setTimeout(() => {
    if (failRef.current) { setFailNext(false); reject(new Error('demo-fail')); } else resolve();
  }, ms));
  const say = (text, action) => {
    clearTimeout(toastTimer.current);
    setToast({ text, action, key: Date.now() });
    toastTimer.current = setTimeout(() => setToast(null), 5000);
  };

  const ctx = {
    msgsOf: (t) => (typeof t.msgs === 'string' ? [db.tasks.find((x) => x.id === t.msgs).msgs[0]] : t.msgs),
    toggleDone: (id) => {
      const t = db.tasks.find((x) => x.id === id);
      const next = !t.done;
      patchTask(id, () => ({ done: next }));
      say(next ? `已办：${t.title}` : `改回待办：${t.title}`, { label: '撤销', fn: () => patchTask(id, () => ({ done: !next })) });
    },
    openUpload: (id) => setSheet({ type: 'upload', task: id }),
    openMsgs: (id) => setSheet({ type: 'msgs', task: id }),
    openMat: (taskId, mat) => setSheet({ type: 'mat', task: taskId, mat }),
    openPrint: (taskId, mat) => setSheet({ type: 'print', task: taskId, mat }),
    openAnswer: (taskId, page, mark) => setSheet({ type: 'answer', task: taskId, page, mark }),
    openNote: (id) => setSheet({ type: 'note', task: id }),
    openWrongNote: (taskId, noteId) => setSheet({ type: 'wrongnote', task: taskId, note: noteId }),
    startCheck: (id) => {
      patchTask(id, (t) => ({ fb: { ...t.fb, stage: 'checking' } }));
      setTimeout(() => {
        const r = DEMO_CHECKS[id] || { basis: '按题目核对', total: 1, wrong: [], doubt: [] };
        update((n) => {
          const t = n.tasks.find((x) => x.id === id);
          if (!t || !t.fb || t.fb.stage !== 'checking') return;
          n.tasks = n.tasks.map((x) => (x.id === id ? { ...x, fb: { ...x.fb, stage: 'checked', at: nowHM(),
            result: { basis: r.basis, unit: r.unit, total: r.total, right: r.total - r.wrong.length - r.doubt.length, doubt: r.doubt.slice() } } } : x));
          // 再次提交不覆盖：已有错题（含手动记录和订正状态）都保留，只补上还没有的
          const have = new Set(n.wrongs.map((w) => w.id));
          n.wrongs = n.wrongs.concat(r.wrong.map((w, i) => ({ ...w, id: `w-${id}-${i}`, child: t.child, task: id, status: 'todo' })).filter((w) => !have.has(w.id)));
        });
        say('检查完成（演示结果，没有调用 AI）');
      }, 1200);
    },
    resolveDoubt: (id, d, right) => {
      update((n) => {
        const t = n.tasks.find((x) => x.id === id);
        n.tasks = n.tasks.map((x) => (x.id === id ? { ...x, fb: { ...x.fb, result: { ...x.fb.result,
          right: x.fb.result.right + (right ? 1 : 0), doubt: x.fb.result.doubt.filter((y) => y.q !== d.q) } } } : x));
        if (!right) n.wrongs = n.wrongs.concat({ ...d, note: '家长看过，判为错', id: `w-${id}-d-${d.q}`, child: t.child, task: id, status: 'todo' });
      });
      say(right ? `${d.q} 记为对` : `${d.q} 记为错，已放进错题`);
    },
    setWrong: async (w, status) => {
      if (busyIds.includes(w.id)) return;
      setBusyIds((b) => b.concat(w.id));
      try {
        await demoSave(450);
        const at = nowHM();
        update((n) => { n.wrongs = n.wrongs.map((x) => (x.id === w.id ? { ...x, status, doneAt: status === 'done' ? at : undefined } : x)); });
        say(status === 'done' ? `${w.q} 订正好了` : `${w.q} 已重开，回到待订正`);
      } catch (e) {
        say(`${w.q} 的订正状态没保存上（演示失败）`, { label: '重试', fn: () => ctx.setWrong(w, status) });
      } finally {
        setBusyIds((b) => b.filter((x) => x !== w.id));
      }
    },
    setTaskDay: (id, d) => {
      patchTask(id, () => ({ day: d, dateBy: 'parent' }));
      say(`已放到 ${fmtDay(d)}（日期由家长补上）`, { label: '去看看', fn: () => { setDay(d); setView('today'); setSel(id); } });
    },
    gotoTask: (t) => { if (t.day) { setDay(t.day); setView('today'); } else setView('later'); setSel(t.id); if (isMobile) setMDetail(true); },
  };

  // 换孩子时收起上一个孩子的提示：它的“撤销 / 去看看”只对那个孩子的事项有效
  function setChild(id) { clearTimeout(toastTimer.current); setToast(null); update((n) => { n.child = id; }); setSel(null); setMDetail(false); }
  function setDay(d) { update((n) => { n.day = d; }); setSel(null); }
  function switchView(v) { setView(v); setSel(null); }
  function openItem(id) {
    setSel(id);
    if (isMobile) { setMDetail(true); try { window.history.pushState({ fg: 'detail' }, ''); } catch (e) { /* 忽略 */ } }
  }
  function closeMobile() {
    if (window.history.state && window.history.state.fg === 'detail') window.history.back(); else setMDetail(false);
  }
  function resetDemo() { setDb(seedDb()); setView('today'); setSel(null); setMenu(null); setMDetail(false); say('演示数据已重置'); }

  async function saveAdd(f) {
    await demoSave(700);
    const at = nowHM();
    const d = f.when === 'today' ? day : f.when === 'tomorrow' ? addDays(day, 1) : null;
    const id = `oral-${Date.now()}`;
    const task = { id, child, subject: f.subject, day: d, kind: f.inClass ? 'class' : 'home', title: f.what.trim(), scope: '口头布置',
      standard: f.std.split(/[；;\n]/).map((s) => s.trim()).filter(Boolean),
      handIn: f.handIn === 'morning' ? { label: '明早交', sub: `${fmtDay(addDays(day, 1))} 早上`, urgent: true } : f.handIn === 'none' ? { label: '不用交' } : { label: '交回日未知', sub: '补录时还不知道，不推断' },
      need: '未提供', src: { who: f.teacher.trim() ? `${f.teacher.trim()}（口头）` : '孩子口头转述', at: `${day}T${at}`, oral: true },
      msgs: [{ who: '家长补录', at: `${day}T${at}`, kind: '口头补录', text: `${childName}说：${f.what.trim()}${f.teacher.trim() ? `（${f.teacher.trim()}说的）` : ''}${f.std.trim() ? `；${f.std.trim()}` : ''}` }], mats: [] };
    // 课堂上做且日期未知：仍按课内安排保存，不改成家庭作业
    update((n) => { n.tasks = n.tasks.concat(task); });
    setSheet(null);
    if (d === day && task.kind === 'home') { setView('today'); setSel(id); say(`已补录到${f.subject} · 来源：孩子口头`); }
    else if (!d || task.kind === 'class') { setView('later'); setSel(id); say(task.kind === 'class' ? (d ? '已补录为课内安排，不计入当天' : '已补录为课内安排，日期未写明，不猜日期') : '已补录到“日期未写明”，不猜日期'); }
    else say(`已补录到 ${fmtDay(d)}`, { label: '去看看', fn: () => { setDay(d); setView('today'); setSel(id); } });
  }
  async function saveUpload(taskId, count) {
    await demoSave(900);
    patchTask(taskId, () => ({ fb: { stage: 'uploaded', photos: count, at: nowHM() } }));
    setSheet(null);
    say(`照片已保存 ${count} 张，还没检查`);
  }
  async function saveNote(taskId, f) {
    await demoSave(600);
    const note = { id: `n-${Date.now()}`, text: f.text.trim(), photos: f.photos, at: `${fmtDay(DEMO_TODAY)} ${nowHM()}` };
    // 追加在同一项下，不覆盖已有反馈；不改已办、不生成错题、不调用 AI
    patchTask(taskId, (t) => ({ notes: (t.notes || []).concat(note) }));
    setSheet(null);
    say('反馈已保存在这一项下（没有调用 AI，没有标已办）');
  }
  async function saveWrongNote(taskId, noteId, f) {
    await demoSave(500);
    const id = `w-m-${Date.now()}`;
    update((n) => {
      const t = n.tasks.find((x) => x.id === taskId);
      const note = (t.notes || []).find((x) => x.id === noteId);
      n.wrongs = n.wrongs.concat({ id, child: t.child, task: taskId, noteId, noteAt: note ? note.at : '', manual: true,
        q: f.q.trim(), what: '', note: f.note.trim(), photos: f.photos, status: 'todo' });
    });
    setSheet(null);
    say(`${f.q.trim()} 已记为错题，待订正`);
  }
  async function doPrint(taskId, matId) {
    await new Promise((r) => setTimeout(r, 600));
    update((n) => { n.prints = n.prints.concat({ task: taskId, mat: matId, at: nowHM() }); });
    setSheet(null);
    say('已送到演示打印机，没有真的打印');
  }

  /* ----- 键盘：原生版对应菜单快捷键（⌘），原型用单键避免和浏览器冲突 ----- */
  useEffect(() => {
    function onKey(e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tag = (e.target && e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || sheet || menu) return;
      if (e.key === 'Escape' && isMobile && mDetail) { closeMobile(); return; }
      if (e.key === '[') setDay(addDays(day, -1));
      else if (e.key === ']') setDay(addDays(day, 1));
      else if (e.key === 't' || e.key === 'T') setDay(DEMO_TODAY);
      else if (e.key === 'n' || e.key === 'N') setSheet({ type: 'add' });
      else if (e.key === '1') setChild('xingxing');
      else if (e.key === '2') setChild('xiaoyu');
      else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !isMobile && listForView.length) {
        e.preventDefault();
        const i = Math.max(0, listForView.findIndex((x) => selItem && x.id === selItem.id));
        const next = listForView[Math.min(listForView.length - 1, Math.max(0, i + (e.key === 'ArrowDown' ? 1 : -1)))];
        setSel(next.id);
        requestAnimationFrame(() => { const b = document.querySelector(`[data-row="${next.id}"] .row-main`); if (b) b.focus(); });
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  /* ----- 共用片段 ----- */
  const childSeg = (
    <div className="seg" role="group" aria-label="选择孩子（一次只看一个）">
      {CHILDREN.map((c) => (
        <button type="button" key={c.id} className="seg-btn" aria-pressed={c.id === child} onClick={() => setChild(c.id)}>{c.name}<small>{c.grade}</small></button>
      ))}
    </div>
  );
  const dateBar = (
    <div className="datebar" role="group" aria-label="日期">
      <button type="button" className="icon-btn" aria-label="前一天" onClick={() => setDay(addDays(day, -1))}><Icon name="chevL"></Icon></button>
      <span className="date-label" aria-live="polite">{fmtDay(day)} {weekDay(day)}<small>{rel ? (rel === '今天' ? '今天（演示日）' : rel) : ' '}</small></span>
      <button type="button" className="icon-btn" aria-label="后一天" onClick={() => setDay(addDays(day, 1))}><Icon name="chevR"></Icon></button>
      {day !== DEMO_TODAY && <button type="button" className="btn btn-quiet" onClick={() => setDay(DEMO_TODAY)}>回到今天</button>}
    </div>
  );
  const navItems = (
    <>
      <button type="button" className="nav-btn" aria-current={view === 'today' ? 'page' : undefined} onClick={() => switchView('today')}>
        <Icon name="list"></Icon><span className="nav-label">{rel === '今天' ? '今天' : fmtDay(day)}</span><span className="nav-count">{dayHome.length}</span></button>
      <button type="button" className="nav-btn" aria-current={view === 'later' ? 'page' : undefined} onClick={() => switchView('later')}>
        <Icon name="book"></Icon><span className="nav-label">课内 · 未定</span><span className="nav-count">{later.length}</span></button>
      {!isMobile && <p className="nav-hint">不计入当天清单</p>}
      <button type="button" className="nav-btn" aria-current={view === 'wrong' ? 'page' : undefined} onClick={() => switchView('wrong')}>
        <Icon name="pencil"></Icon><span className="nav-label">错题订正</span><span className="nav-count">{wrongTodo.length}</span></button>
    </>
  );

  const toggle = (id) => ctx.toggleDone(id);
  let listBody;
  if (view === 'today') {
    listBody = (<>
      <header className="list-head">
        <h2>{rel === '今天' ? '今天要做' : `${fmtDay(day)} 要做`}</h2>
        <p>{dayHome.length ? `${dayHome.length} 项 · 已办 ${doneCount} · 待办 ${dayHome.length - doneCount}` : '没有家庭作业'}</p>
      </header>
      {dayHome.length === 0 && (
        <div className="list-empty"><Icon name="sprout" size={28}></Icon><span>这一天没有学校布置的家庭作业。</span>
          <button type="button" className="btn" onClick={() => setSheet({ type: 'add' })}><Icon name="plus"></Icon>补录口头作业</button></div>
      )}
      <SubjectGroups tasks={dayHome} selId={selItem && selItem.id} onOpen={openItem} onToggle={toggle} wrongs={wrongs}></SubjectGroups>
      {dayClass.length > 0 && (
        <section className="group" aria-label="课内安排">
          <div className="group-h"><span className="sign">课内安排<b>不算家庭作业</b></span></div>
          {dayClass.map((t) => <TaskRow key={t.id} t={t} selected={selItem && t.id === selItem.id} onOpen={openItem} onToggle={toggle} wrongs={wrongs}></TaskRow>)}
        </section>
      )}
      {laterOther.length > 0 && (
        <button type="button" className="list-foot" onClick={() => switchView('later')}><Icon name="book"></Icon>
          另有 {laterOther.length} 项课内安排或日期未写明，不计入{rel === '今天' ? '今天' : '这一天'}<Icon name="chevR" size={16}></Icon></button>
      )}
    </>);
  } else if (view === 'later') {
    listBody = (<>
      <header className="list-head"><h2>课内 · 未定日期</h2><p>都不计入当天清单；没写日期的不猜。</p></header>
      {laterClass.length > 0 && (
        <section className="group" aria-label="课内安排">
          <div className="group-h"><span className="sign">课内安排<b>在学校完成</b></span></div>
          {laterClass.map((t) => <TaskRow key={t.id} t={t} selected={selItem && t.id === selItem.id} onOpen={openItem} onToggle={toggle} wrongs={wrongs}></TaskRow>)}
        </section>
      )}
      {laterUndated.length > 0 && (
        <section className="group" aria-label="日期未写明">
          <div className="group-h"><span className="sign">日期未写明<b>{laterUndated.length} 项</b></span></div>
          {laterUndated.map((t) => <TaskRow key={t.id} t={t} selected={selItem && t.id === selItem.id} onOpen={openItem} onToggle={toggle} wrongs={wrongs}></TaskRow>)}
        </section>
      )}
      {!later.length && <div className="list-empty"><Icon name="sprout" size={28}></Icon><span>没有课内安排或日期未定的事项。</span></div>}
    </>);
  } else {
    const wrongRow = (w) => {
      const t = db.tasks.find((x) => x.id === w.task);
      const on = selItem && selItem.id === w.id;
      return (
        <div className="row" key={w.id} data-row={w.id} data-sel={on ? 'true' : 'false'} data-done={w.status === 'done' ? 'true' : 'false'}>
          <span className="leaf" aria-hidden="true"><i>{w.status === 'done' ? <Icon name="check" size={16}></Icon> : <Icon name="pencil" size={15}></Icon>}</i></span>
          <button type="button" className="row-main" aria-current={on ? 'true' : undefined} onClick={() => openItem(w.id)}>
            <span className="row-title">{t.subject} {w.q}{w.what ? `：${w.what}` : ''}</span>
            <span className="row-std">{w.manual ? `家长记录：${w.note || '原因没写'}` : `原答 ${w.answer} · 教师答案 ${w.key}`}</span>
            <span className="row-meta">来自 {t.title} · {dayText(t.day)}{w.status === 'done' && ` · 已订正 ${w.doneAt}`}</span>
          </button>
        </div>
      );
    };
    listBody = (<>
      <header className="list-head"><h2>错题订正</h2><p>待订正 {wrongTodo.length} · 已订正 {wrongDone.length}</p></header>
      {wrongTodo.length > 0 && <section className="group" aria-label="待订正"><div className="group-h"><span className="sign">待订正<b>{wrongTodo.length}</b></span></div>{wrongTodo.map(wrongRow)}</section>}
      {wrongDone.length > 0 && <section className="group" aria-label="已订正"><div className="group-h"><span className="sign">已订正<b>{wrongDone.length}</b></span></div>{wrongDone.map(wrongRow)}</section>}
      {!wrongs.length && <div className="list-empty"><Icon name="sprout" size={28}></Icon><span>{childName}现在没有错题。</span></div>}
    </>);
  }

  let detailBody = null;
  if (selItem && view === 'wrong') {
    const t = db.tasks.find((x) => x.id === selItem.task);
    detailBody = <WrongDetail w={selItem} t={t} busy={busyIds.includes(selItem.id)} ctx={ctx}></WrongDetail>;
  } else if (selItem) {
    detailBody = <TaskDetail t={selItem} db={db} busyIds={busyIds} ctx={ctx} hideDoneButton={isMobile}></TaskDetail>;
  } else {
    detailBody = <div className="d-empty"><Icon name="sprout" size={28}></Icon><span>在左边选一项，就能看到要做什么、标准、资料和反馈。</span></div>;
  }

  /* ----- 弹出层 ----- */
  let sheetEl = null;
  if (sheet) {
    const st = sheet.task && db.tasks.find((x) => x.id === sheet.task);
    const close = () => setSheet(null);
    if (sheet.type === 'add') sheetEl = <AddSheet childName={childName} day={day} save={saveAdd} onClose={close}></AddSheet>;
    else if (sheet.type === 'upload') sheetEl = <UploadSheet task={st} pages={(MATERIALS[st.mats[0]] || {}).pages || 2} upload={(n) => saveUpload(st.id, n)} onClose={close}></UploadSheet>;
    else if (sheet.type === 'msgs') sheetEl = <MessageSheet task={st} msgs={ctx.msgsOf(st)} onClose={close}
      gotoOther={(o) => { setSheet(null); setDay(o.day); setView('today'); setSel(o.id); if (isMobile) setMDetail(true); }}></MessageSheet>;
    else if (sheet.type === 'mat') sheetEl = <MaterialSheet mat={MATERIALS[sheet.mat]} task={st} onClose={close}
      onPrint={() => setSheet({ type: 'print', task: st.id, mat: sheet.mat })}></MaterialSheet>;
    else if (sheet.type === 'answer') sheetEl = <AnswerSheet task={st} page={sheet.page} mark={sheet.mark} onClose={close}></AnswerSheet>;
    else if (sheet.type === 'note') sheetEl = <NoteSheet task={st} save={(f) => saveNote(st.id, f)} onClose={close}></NoteSheet>;
    else if (sheet.type === 'wrongnote') sheetEl = <WrongNoteSheet task={st} note={(st.notes || []).find((x) => x.id === sheet.note)}
      save={(f) => saveWrongNote(st.id, sheet.note, f)} onClose={close}></WrongNoteSheet>;
    else if (sheet.type === 'print') sheetEl = <PrintSheet task={st} mat={MATERIALS[sheet.mat]} kind={MATERIALS[sheet.mat].print} childName={childName}
      checkedAt={db.printChecked[st.id]} markChecked={() => update((n) => { n.printChecked[st.id] = nowHM(); })}
      doPrint={() => doPrint(st.id, sheet.mat)} openMsgs={() => setSheet({ type: 'msgs', task: st.id })} onClose={close}></PrintSheet>;
  }

  const selTask = selItem && view !== 'wrong' ? selItem : null;
  const printable = (kind) => selTask && selTask.mats.find((id) => MATERIALS[id].print === kind);
  const menuEl = menu && (
    <MenuPop pos={menu} onClose={() => setMenu(null)} items={[
      { label: '补录口头作业', key: 'N', native: '⌘N', fn: () => setSheet({ type: 'add' }) },
      { sep: true },
      { label: '前一天', key: '[', native: '⌘[', fn: () => setDay(addDays(day, -1)) },
      { label: '后一天', key: ']', native: '⌘]', fn: () => setDay(addDays(day, 1)) },
      { label: '回到今天', key: 'T', native: '⌘T', fn: () => setDay(DEMO_TODAY) },
      { label: '看星星', key: '1', native: '⌘1', fn: () => setChild('xingxing') },
      { label: '看小宇', key: '2', native: '⌘2', fn: () => setChild('xiaoyu') },
      { sep: true },
      { label: '打印原卷', native: '⌘P', disabled: !printable('original'), fn: () => setSheet({ type: 'print', task: selTask.id, mat: printable('original') }) },
      { label: '打印家长参考', native: '⇧⌘P', disabled: !printable('parent'), fn: () => setSheet({ type: 'print', task: selTask.id, mat: printable('parent') }) },
      { sep: true },
      { label: failNext ? '演示：下一次保存会失败 ✓' : '演示：让下一次保存失败', fn: () => { setFailNext(!failNext); say(failNext ? '已取消模拟失败' : '下一次保存会模拟失败（演示）'); } },
      { label: '演示：重置演示数据', fn: resetDemo },
    ]}></MenuPop>
  );
  const toastEl = (<>
    <div className="vh" aria-live="polite">{toast ? toast.text : ''}</div>
    {toast && (
      <div className="toast" key={toast.key}><span>{toast.text}</span>
        {toast.action && <button type="button" className="btn btn-quiet" onClick={() => { setToast(null); toast.action.fn(); }}>{toast.action.label}</button>}</div>
    )}
  </>);
  const openMenu = (e) => { const r = e.currentTarget.getBoundingClientRect(); setMenu({ top: r.bottom + 6, left: Math.max(12, r.right - 300) }); };

  /* ----- 手机：单列 + 自然返回 ----- */
  if (isMobile) {
    const backLabel = view === 'today' ? (rel === '今天' ? '今天' : fmtDay(day)) : view === 'later' ? '课内 · 未定' : '错题订正';
    return (
      <div className="m-app">
        {mDetail && selItem ? (<>
          <div className="m-back" data-screen-label="手机 · 详情">
            <button type="button" className="btn btn-quiet" onClick={closeMobile}><Icon name="chevL"></Icon>{backLabel}</button>
            <span className="chip chip-plain">{childName}</span>
          </div>
          <main className="detail">{detailBody}</main>
          {view !== 'wrong' && selItem.kind === 'home' && (
            <div className="m-bottom">
              <button type="button" className={`btn ${selItem.done ? '' : 'btn-primary'}`} onClick={() => ctx.toggleDone(selItem.id)}>
                <Icon name={selItem.done ? 'undo' : 'check'}></Icon>{selItem.done ? '已办 · 改回待办' : '标记已办'}</button>
            </div>
          )}
        </>) : (<>
          <header className="m-top" data-screen-label="手机 · 清单">
            <div className="m-row">{childSeg}
              <button type="button" className="icon-btn" aria-label="更多操作" aria-haspopup="menu" aria-expanded={!!menu} onClick={openMenu}><Icon name="more"></Icon></button></div>
            <div className="m-row">{dateBar}</div>
            <nav className="m-views" aria-label="视图">{navItems}</nav>
          </header>
          <main className="m-content">{listBody}</main>
          <div className="m-bottom"><button type="button" className="btn btn-primary" onClick={() => setSheet({ type: 'add' })}><Icon name="plus"></Icon>补录口头作业</button></div>
        </>)}
        {sheetEl}{menuEl}{toastEl}
      </div>
    );
  }

  /* ----- Mac：工具栏 / 窄导航 / 科目清单 / 所选事项详情 ----- */
  return (
    <div className="fg-stage">
      <div className="win" data-om-starter="macos-window" data-screen-label="Mac 每日工作台">
        <div className="win-bar">
          <span aria-hidden="true"><MacTrafficLights></MacTrafficLights></span>
          <span className="win-title"><Icon name="sprout"></Icon>一起成长</span>
          {childSeg}
          {dateBar}
          <span className="win-spacer"></span>
          <span className="chip chip-demo">演示数据</span>
          <button type="button" className="btn btn-primary" onClick={() => setSheet({ type: 'add' })}><Icon name="plus"></Icon>补录</button>
          <button type="button" className="icon-btn" aria-label="更多操作" aria-haspopup="menu" aria-expanded={!!menu} onClick={openMenu}><Icon name="more"></Icon></button>
        </div>
        <div className="win-body">
          <nav className="nav" aria-label="视图">
            {navItems}
            <div className="nav-foot"><span className="chip chip-demo">演示</span><span>都是虚构数据。上传、检查、打印都只在本页模拟。</span></div>
          </nav>
          <section className="list" aria-label="科目清单">{listBody}</section>
          <section className="detail" aria-label="所选事项">{detailBody}</section>
        </div>
      </div>
      <p className="fg-caption"><span>设计原型 · 星星、小宇为虚构孩子 · 不连接家庭后台</span><span>键盘：↑↓ 选择　[ ] 换日　T 今天　N 补录　1 / 2 换孩子</span></p>
      {sheetEl}{menuEl}{toastEl}
    </div>
  );
}

function MenuPop({ pos, items, onClose }) {
  const box = useRef(null);
  useEffect(() => {
    const first = box.current && box.current.querySelector('button:not([disabled])');
    if (first) first.focus();
    const away = (e) => { if (box.current && !box.current.contains(e.target)) onClose(); };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, []);
  const onKeyDown = (e) => {
    const list = [...box.current.querySelectorAll('button:not([disabled])')];
    const i = list.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); list[(i + 1) % list.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); list[(i - 1 + list.length) % list.length].focus(); }
    else if (e.key === 'Tab') { e.preventDefault(); onClose(); }
  };
  return (
    <div className="menu" role="menu" aria-label="更多操作" ref={box} style={{ top: pos.top, left: pos.left }} onKeyDown={onKeyDown}>
      {items.map((it, i) => (it.sep ? <div className="menu-sep" key={i} role="separator"></div> : (
        <button type="button" role="menuitem" className="menu-item" key={i} disabled={it.disabled} onClick={() => { onClose(); it.fn(); }}>
          <span>{it.label}</span>{it.key && <span className="kbd">{it.key}</span>}{it.native && <span className="kbd">{it.native}</span>}
        </button>
      )))}
      <p className="menu-note">原生 App 里这些是菜单栏命令，用右侧 ⌘ 快捷键；原型里用左侧单键，避免和浏览器冲突。</p>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App></App>);

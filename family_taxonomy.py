"""cn-math-taxonomy固定知识包的薄适配：载包校验、数学知识点搜索、同孩原错题的知识点链接与诊断记录。

上游：xiaoyang111222/cn-math-taxonomy@e0f931badaed994fa8e10cfc7a30cdbdffc2dfd5，CC BY-NC 4.0，
AI初稿、未经教师审核。公开仓库只放本清单与适配代码；知识包由家庭本机放入Git忽略目录，
加载时逐文件校验sha256，不在则报“知识包未安装”，原错题/引导/每日待办照常可用。
诊断算法（diagnose/engine.js）在浏览器里原样运行（createSession/nextItem/judgeQuestion/applyAnswer/
summarize/replay），本模块不选题、不判题、不推断掌握：只核对题号属于本次知识点子图、按逐题幂等保存
原答与上游输出，并在“新题再试”时交DeepTutor原LearningService登记/判定（family_deeptutor）。
每道题显示前先登记“已出示”；同孩历次诊断的出示/作答/说明/再试痕迹跨诊断、跨更正保留，独立新题只认从没见过的题。
原错题更正后，旧诊断里DeepTutor已判定的作答经原repair_question(void)作废（组件不可用时记“待作废”）。
家庭SQLite是唯一主数据；上游“掌握/推断掌握”只作本轮线索原样留存，不写成孩子掌握事实。"""
import hashlib, json, os, re, sqlite3, time
from pathlib import Path

import family_deeptutor

TAXONOMY_SHA = 'e0f931badaed994fa8e10cfc7a30cdbdffc2dfd5'
RAW = f'https://raw.githubusercontent.com/xiaoyang111222/cn-math-taxonomy/{TAXONOMY_SHA}/'
# sha256与字节数已按上游e0f931b的Git tree blob逐字节核对（engine.js blob a35cedd9，47863 B）。
MANIFEST = {
    'diagnose/engine.js': ('b4a48814213a5b50a49c86e39afcc6a6c81142cf4a8243cdfdc55dea397a017e', 47863),
    'data/topics.json': ('003a94a2dc6f5161f46b32f9e61d95c3ece73ec238ced58f6802b3bfe4e95909', 2010398),
    'data/dependencies.json': ('e4c459ea539b2c85ef4a588c6814bbba7d24a7d53252b57c9061d01cf2419bb2', 710228),
    'data/questions.json': ('74f669033e5d47685da4d8e66331188806ff99f415550d6a2e09cc2ade9f1a5c', 6083743),
    'data/id-aliases.json': ('791334fe08835c539ce7dd6afa686dffebba5f810d11ec616b5c5d70a87864fb', 3177),
}
GIT_BLOBS = {'diagnose/engine.js': 'a35cedd9c638762013320b1666fc8160ae1b7bde', 'data/topics.json': 'e13349ef46e60a65decfdf8321c13f1f7d6d5fd8',
             'data/dependencies.json': 'b92df17438d9a2a56697bbfda907ea76977ce365', 'data/questions.json': '2363b2a58c90879cc756e8bfdaffed7397f5af1b',
             'data/id-aliases.json': 'ede2ca50fb5600d2c6dec63e71d27a977e462ce0'}
ENGINE_SHA256 = MANIFEST['diagnose/engine.js'][0]
REVIEW_STATUS = 'AI初稿，未经教师审核'
LINK_STATES = ('confirmed', 'candidate', 'unclear', 'no_match')
WRONG_SOURCE = '错题照片核对'
RETRY_SOURCE = '知识点诊断·新题再试'
DIAG_LIMIT = 8  # createSession的limit；confirm用上游DEFAULT_CONFIRM=3（连续答对3题）
ANSWER_MAX = 500  # 原答字数上限：超长整笔400拒收，不截断后再保存、比对或交判定
KINDS = ('answer', 'skip', 'unknown')
REQUEST = re.compile(r'^[A-Za-z0-9_-]{16,128}$')


class TaxonomyError(Exception):
    def __init__(self, message, code, status=400):
        super().__init__(message); self.code = code; self.status = status


def pack_dir():
    return Path(os.environ.get('FAMILY_TAXONOMY_DIR') or Path(__file__).resolve().parent / 'knowledge' / f'cn-math-taxonomy-{TAXONOMY_SHA[:7]}')


_VERIFIED, _PACKS = {}, {}


def pack_status(root=None, manifest=None):
    root = Path(root or pack_dir()); problems = []; manifest = manifest or MANIFEST
    for rel, (digest, size) in manifest.items():
        path = root / rel
        if not path.is_file(): problems.append({'file': rel, 'problem': 'missing'}); continue
        st = path.stat(); key = (str(path), st.st_size, st.st_mtime_ns, digest)
        if key not in _VERIFIED:
            _VERIFIED[key] = st.st_size == size and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        if not _VERIFIED[key]: problems.append({'file': rel, 'problem': 'sha256_mismatch'})
    return {'installed': not problems, 'sha': TAXONOMY_SHA, 'review_status': REVIEW_STATUS, 'problems': problems,
            'message': '' if not problems else '知识包未安装或与固定版本不一致；原错题与引导照常可用'}


def load_pack(root=None):
    root = Path(root or pack_dir()); status = pack_status(root)
    if not status['installed']: raise TaxonomyError(status['message'], 'pack_unavailable', 503)
    if str(root) not in _PACKS:
        data = {n: json.loads((root / 'data' / f'{n}.json').read_text(encoding='utf-8')) for n in ('topics', 'dependencies', 'questions')}
        data['by_id'] = {t['id']: t for t in data['topics']}
        data['prereqs'] = {}
        for d in data['dependencies']: data['prereqs'].setdefault(d['topicId'], []).append(d['prerequisiteId'])
        data['qid'] = {q['id']: q for q in data['questions'] if q.get('topicId') in data['by_id']}
        _PACKS[str(root)] = data
    return _PACKS[str(root)]


def engine_bytes(root=None):
    root = Path(root or pack_dir())
    if not pack_status(root)['installed']: raise TaxonomyError('知识包未安装或与固定版本不一致', 'pack_unavailable', 503)
    return (root / 'diagnose' / 'engine.js').read_bytes()


def math_topics(topics):
    return [t for t in topics if str(t.get('id', '')).startswith('cnm_') and t.get('subject') in (None, '', 'math')]


def search(topics, query, limit=8):
    """按名称、册章核对；唯一才给confirmable候选，歧义列候选，无匹配回原材料，不猜。"""
    words = [w for w in str(query or '').split() if w]
    if not words: return {'status': 'unclear', 'candidates': []}
    hits = [t for t in math_topics(topics) if all(w in f"{t.get('name','')} {t.get('chapter','')}" for w in words)]
    exact = [t for t in hits if t.get('name') == ' '.join(words)]
    chosen = exact if len(exact) == 1 else hits
    status = 'none' if not chosen else 'unique' if len(chosen) == 1 else 'ambiguous'
    keep = ('id', 'name', 'grade', 'semester', 'chapter', 'mastery_criteria')
    return {'status': status, 'candidates': [{k: t.get(k) for k in keep} for t in chosen[:limit]], 'total': len(chosen),
            'review_status': REVIEW_STATUS}


def closure(pack, topic_id):
    """目标点及其全部先修（上游engine的subgraph范围）。"""
    seen, stack = set(), [topic_id]
    while stack:
        t = stack.pop()
        if t in seen or t not in pack['by_id']: continue
        seen.add(t); stack.extend(pack['prereqs'].get(t, []))
    return seen


def graph_payload(pack, topic_id):
    """只下发目标点祖先闭包内的原条目（保持上游文件顺序，buildGraph的确定次序不变）。"""
    ids = closure(pack, topic_id)
    return {'topics': [t for t in pack['topics'] if t['id'] in ids],
            'dependencies': [d for d in pack['dependencies'] if d['topicId'] in ids and d['prerequisiteId'] in ids],
            'questions': [q for q in pack['questions'] if q.get('topicId') in ids]}


def question(pack, qid):
    q = pack['qid'].get(qid)
    if q: return q
    m = re.fullmatch(r'(.+)_q1', str(qid or ''))  # 上游buildGraph对无题库点回退的diagnostic_question
    t = pack['by_id'].get(m.group(1)) if m else None
    dq = (t or {}).get('diagnostic_question') or {}
    if t and not t.get('external') and dq.get('question') and not any(x.get('topicId') == t['id'] for x in pack['questions']):
        return {'id': qid, 'topicId': t['id'], 'type': 'legacy', 'prompt': dq['question'], 'answer': dq.get('answer', ''), 'explanation': ''}
    return None


def ensure_schema(conn):
    # 只新增表，不改旧表/旧行。topic_exposures、topic_basis_voids是v3新增：CREATE IF NOT EXISTS，
    # 已建过前4张表的候选库下次打开时原地补建，旧行不需迁移（见_evidence与settle_basis）。
    conn.execute('''CREATE TABLE IF NOT EXISTS topic_links(
        id INTEGER PRIMARY KEY, child_id TEXT NOT NULL, record_id TEXT NOT NULL, record_hash TEXT NOT NULL,
        topic_id TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, pack_sha TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
        request_id TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(child_id, request_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS topic_diagnoses(
        id INTEGER PRIMARY KEY, child_id TEXT NOT NULL, record_id TEXT NOT NULL, record_hash TEXT NOT NULL, topic_id TEXT NOT NULL,
        pack_sha TEXT NOT NULL, engine_sha256 TEXT NOT NULL, opts TEXT NOT NULL, session TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 0,
        deeptutor_snapshot TEXT NOT NULL DEFAULT '', request_id TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        UNIQUE(child_id, request_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS topic_diagnosis_items(
        id INTEGER PRIMARY KEY, diagnosis_id INTEGER NOT NULL, seq INTEGER NOT NULL, topic_id TEXT NOT NULL, qid TEXT NOT NULL,
        kind TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '', verdict TEXT NOT NULL, engine_result TEXT NOT NULL,
        help TEXT NOT NULL DEFAULT '', payload_hash TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(diagnosis_id, seq))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS topic_retries(
        id INTEGER PRIMARY KEY, diagnosis_id INTEGER NOT NULL, child_id TEXT NOT NULL, record_id TEXT NOT NULL, record_hash TEXT NOT NULL,
        topic_id TEXT NOT NULL, qid TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '', taxonomy_verdict TEXT NOT NULL,
        deeptutor TEXT NOT NULL DEFAULT '{}', outcome TEXT NOT NULL, followup_record_id INTEGER, request_id TEXT NOT NULL,
        created_at REAL NOT NULL, UNIQUE(child_id, request_id))''')
    # 每道题先登记“已出示”再显示（诊断题mode=diagnosis；新题再试mode=retry），没提交的题也算见过。
    conn.execute('''CREATE TABLE IF NOT EXISTS topic_exposures(
        id INTEGER PRIMARY KEY, child_id TEXT NOT NULL, record_id TEXT NOT NULL, diagnosis_id INTEGER NOT NULL, pack_sha TEXT NOT NULL,
        qid TEXT NOT NULL, mode TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(child_id, diagnosis_id, qid, mode))''')
    # 原错题更正后对旧诊断DeepTutor快照的作废：pending=待作废（组件不可用，旧结果不当当前，可重试）/voided/nothing。
    conn.execute('''CREATE TABLE IF NOT EXISTS topic_basis_voids(
        id INTEGER PRIMARY KEY, diagnosis_id INTEGER NOT NULL UNIQUE, child_id TEXT NOT NULL, record_id TEXT NOT NULL,
        old_record_hash TEXT NOT NULL, state TEXT NOT NULL, question_ids TEXT NOT NULL DEFAULT '[]', detail TEXT NOT NULL DEFAULT '',
        snapshot_before_sha256 TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL)''')


def record_hash(record):
    keep = {k: record.get(k) for k in ('id', 'child_id', 'child', 'subject', 'title', 'note', 'attachments', 'created',
                                       'question', 'answer', 'correction', 'updated_at')}
    return hashlib.sha256(json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


BASIS_CHANGED = '原错题已更正，这次诊断的依据已失效；之前的作答作为历史保留，请按更正后的错题重新开始'


def _own(child_id, record):
    if not record or str(record.get('child_id')) != str(child_id):
        raise TaxonomyError('这条错题不属于当前孩子', 'cross_child', 403)


def _link_write(conn, child_id, record, topic_id, state, request_id, topics=None, note=''):
    """同一提交编号只认同一条确认：原样重发读回（返回True），换记录/知识点/状态/备注409零写。"""
    _own(child_id, record)
    if state not in LINK_STATES: raise TaxonomyError('知识点状态不正确', 'bad_state')
    if state in ('confirmed', 'candidate'):
        if not topic_id or (topics is not None and topic_id not in {t['id'] for t in math_topics(topics)}):
            raise TaxonomyError('知识点不在固定数学知识包中', 'unknown_topic')
    elif topic_id: raise TaxonomyError('不明或无匹配时不绑定知识点', 'bad_state')
    if not request_id: raise TaxonomyError('缺少请求编号', 'missing_request')
    ensure_schema(conn)
    fact = (str(record['id']), topic_id or '', state, str(note)[:300])
    with conn:
        prev = conn.execute('SELECT record_id,topic_id,state,note,record_hash FROM topic_links WHERE child_id=? AND request_id=?',
                            (str(child_id), str(request_id))).fetchone()
        if prev is not None:
            if (prev[0], prev[1], prev[2], prev[3]) != fact:
                raise TaxonomyError('这个提交编号已用于另一条知识点确认；请刷新后重新选择', 'request_conflict', 409)
            if prev[4] != record_hash(record): raise TaxonomyError(BASIS_CHANGED, 'basis_changed', 409)
            return True
        conn.execute('INSERT INTO topic_links(child_id,record_id,record_hash,topic_id,state,pack_sha,note,request_id,created_at) '
                     'VALUES(?,?,?,?,?,?,?,?,?)', (str(child_id), str(record['id']), record_hash(record), topic_id or '', state,
                                                   TAXONOMY_SHA, str(note)[:300], str(request_id), time.time()))
    return False


def link(conn, child_id, record, topic_id, state, request_id, topics=None, note=''):
    _link_write(conn, child_id, record, topic_id, state, request_id, topics, note)
    return links(conn, child_id, record)


def links(conn, child_id, record):
    _own(child_id, record)
    ensure_schema(conn); now = record_hash(record)
    rows = conn.execute('SELECT topic_id,state,record_hash,pack_sha,note,created_at FROM topic_links WHERE child_id=? AND record_id=? ORDER BY id',
                        (str(child_id), str(record['id']))).fetchall()
    return [{'topic_id': r[0], 'state': r[1], 'pack_sha': r[3], 'note': r[4], 'created_at': r[5],
             'basis': 'current' if r[2] == now else 'basis_changed'} for r in rows]


# ---------------------------------------------------------------- 原错题入口的诊断流程（HTTP适配）

def wrong_record(app, conn, child_id, record_id):
    """只读原错题；不属于当前孩子时403，此时一张新表都不建。"""
    if not isinstance(child_id, str) or not child_id: raise TaxonomyError('请选择孩子', 'child')
    if type(record_id) is not int or record_id <= 0: raise TaxonomyError('错题记录编号不正确', 'record')
    prof = next((p for p in app.profiles(conn) if p['id'] == child_id), None)
    if prof is None: raise TaxonomyError('请选择孩子', 'child')
    row = conn.execute('SELECT id,child,day,subject,title,note,source,attachments,created FROM records WHERE id=?', (record_id,)).fetchone()
    if row is None: raise TaxonomyError('错题记录不存在', 'not_found', 404)
    if row['child'] != prof['name']: raise TaxonomyError('这条错题不属于当前孩子', 'cross_child', 403)
    if WRONG_SOURCE not in (row['source'] or ''): raise TaxonomyError('只能从原错题进入知识点诊断', 'not_wrong_record')
    return dict(dict(row), child_id=child_id)


def _fields(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or any(k not in obj for k in required):
        raise TaxonomyError('请求字段不正确', 'bad_request')
    rid = obj.get('request_id')
    if 'request_id' in required and (not isinstance(rid, str) or not REQUEST.fullmatch(rid)):
        raise TaxonomyError('提交标识不正确', 'bad_request')


def _answer(obj):
    """原答=保存=幂等比对=判定依据，一字不改；非文字或超长整笔拒收，此时还没读写任何表、没调判定组件。"""
    text = obj['answer']
    if not isinstance(text, str): raise TaxonomyError('原答格式不正确，这一步没有保存', 'bad_answer')
    if len(text) > ANSWER_MAX:
        raise TaxonomyError(f'原答超过{ANSWER_MAX}个字，这一步没有保存；请缩短后再提交，输入框里的原答还在', 'answer_too_long')
    return text


def _diagnosis(conn, child_id, record, diagnosis_id):
    row = conn.execute('SELECT * FROM topic_diagnoses WHERE id=? AND child_id=? AND record_id=?',
                       (diagnosis_id, child_id, str(record['id']))).fetchone() if type(diagnosis_id) is int else None
    if row is None: raise TaxonomyError('这次诊断不属于这道错题', 'not_found', 404)
    return row


def _current(row, record):
    if row['record_hash'] != record_hash(record): raise TaxonomyError(BASIS_CHANGED, 'basis_changed', 409)


def _payload_hash(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _evidence(c, child_id):
    """同孩历次诊断与再试的全部痕迹：题号→{(已出示/已答/看过说明/已再试/出示为新题, 诊断号)}。
    不按原错题版本或单次诊断过滤：重新诊断、更正原错题都洗不掉已见历史；不同孩子互不相干。"""
    ev = {}
    for qid, did, helps in c.execute('SELECT i.qid,i.diagnosis_id,i.help FROM topic_diagnosis_items i JOIN topic_diagnoses d ON d.id=i.diagnosis_id '
                                     'WHERE d.child_id=?', (child_id,)):
        ev.setdefault(qid, set()).add(('answered', did))
        if helps: ev[qid].add(('helped', did))
    for qid, did in c.execute('SELECT qid,diagnosis_id FROM topic_retries WHERE child_id=?', (child_id,)):
        ev.setdefault(qid, set()).add(('retried', did))
    for qid, did, mode in c.execute('SELECT qid,diagnosis_id,mode FROM topic_exposures WHERE child_id=?', (child_id,)):
        ev.setdefault(qid, set()).add(('offered' if mode == 'retry' else 'shown', did))
    return ev


def _fresh(ev, qid, diagnosis_id):
    """独立新题：这个孩子此前对这题唯一的痕迹，只能是本次诊断把它出示为“新题再试”。"""
    return ev.get(qid) == {('offered', diagnosis_id)}


def settle_basis(app, record):
    """原错题更正后：旧诊断里DeepTutor已判定的新题作答，逐题交原LearningService.repair_question(action='void')作废，
    版本核对一致才保存新快照（原attempt保留并标voided）；旧再试行与复测原话不动，只标依据已变。
    组件不可用记pending“待作废”：旧结果同样不当当前结果，下次打开安全重试（同一旧快照、同一turn编号）。"""
    now = record_hash(record)
    with app.connect() as c:
        ensure_schema(c)
        todo = c.execute("SELECT d.id,d.record_hash,d.topic_id,d.version,d.deeptutor_snapshot FROM topic_diagnoses d "
                         "LEFT JOIN topic_basis_voids v ON v.diagnosis_id=d.id WHERE d.child_id=? AND d.record_id=? AND d.record_hash<>? "
                         "AND (v.state IS NULL OR v.state='pending') ORDER BY d.id", (record['child_id'], str(record['id']), now)).fetchall()
        graded = {d[0]: list(dict.fromkeys(r[0] for r in c.execute("SELECT qid FROM topic_retries WHERE diagnosis_id=? AND deeptutor<>'{}' ORDER BY id", (d[0],))))
                  for d in todo}
    for did, old_hash, topic_id, version, before in todo:
        qids, snap, detail, outcome = graded[did], before, [], 'nothing'
        if qids and before:
            try:
                for qid in qids:
                    out = family_deeptutor.call('void', snap, topic={'id': topic_id, 'name': topic_id}, question_id=qid,
                                                reason='原错题已更正，旧依据作废', session_id=f'diag-{did}', turn_id=f'void-{did}-{qid}')
                    snap = out['snapshot']
                    detail.append({'question_id': qid, 'attempts': [a for a in out.get('attempts') or [] if a.get('question_id') == qid]})
                outcome = 'voided'
            except family_deeptutor.DeepTutorUnavailable as exc:
                snap, detail, outcome = before, [{'error': str(exc)}], 'pending'
        with app.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT version FROM topic_diagnoses WHERE id=?', (did,)).fetchone()
            if row is None or row[0] != version: c.rollback(); continue  # 期间有新保存：下次打开再作废，不覆盖
            t = time.time()
            if outcome == 'voided': c.execute('UPDATE topic_diagnoses SET deeptutor_snapshot=?,version=version+1,updated_at=? WHERE id=?', (snap, t, did))
            c.execute('INSERT INTO topic_basis_voids(diagnosis_id,child_id,record_id,old_record_hash,state,question_ids,detail,snapshot_before_sha256,created_at,updated_at) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(diagnosis_id) DO UPDATE SET state=excluded.state,question_ids=excluded.question_ids,'
                      'detail=excluded.detail,updated_at=excluded.updated_at',
                      (did, record['child_id'], str(record['id']), old_hash, outcome, json.dumps(qids), json.dumps(detail, ensure_ascii=False)[:20000],
                       hashlib.sha256((before or '').encode()).hexdigest(), t, t))


def state(app, obj, root=None):
    """统一完整状态：每个写操作都返回它（知识包、链接、诊断、已见题号、图谱），面板不用拼半截状态。"""
    _fields(obj, ('child_id', 'record_id'), ('child_id', 'record_id'))
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
    settle_basis(app, record)
    with app.connect() as c:
        now = record_hash(record); ev = _evidence(c, record['child_id'])
        voids = {r[0]: {'state': r[1], 'question_ids': json.loads(r[2])} for r in c.execute(
            'SELECT diagnosis_id,state,question_ids FROM topic_basis_voids WHERE child_id=? AND record_id=?', (record['child_id'], str(record['id'])))}
        diags = []
        for d in c.execute('SELECT * FROM topic_diagnoses WHERE child_id=? AND record_id=? ORDER BY id DESC LIMIT 5', (record['child_id'], str(record['id']))).fetchall():
            items = [dict(r) for r in c.execute('SELECT seq,topic_id,qid,kind,answer,verdict,engine_result,help FROM topic_diagnosis_items WHERE diagnosis_id=? ORDER BY seq', (d['id'],))]
            retries = [dict(r, deeptutor=json.loads(r['deeptutor'])) for r in c.execute(
                'SELECT id,topic_id,qid,answer,taxonomy_verdict,deeptutor,outcome,followup_record_id,created_at FROM topic_retries WHERE diagnosis_id=? ORDER BY id', (d['id'],))]
            shown, offers = [], []
            for qid, mode in c.execute('SELECT qid,mode FROM topic_exposures WHERE diagnosis_id=? ORDER BY id', (d['id'],)):
                (offers if mode == 'retry' else shown).append(qid)
            done = {r['qid'] for r in retries}; offer = next((q for q in reversed(offers) if q not in done), '')
            diags.append({'id': d['id'], 'topic_id': d['topic_id'], 'opts': json.loads(d['opts']), 'state': d['state'], 'version': d['version'],
                          'summary': json.loads(d['summary'] or 'null'), 'items': items, 'retries': retries, 'shown': shown,
                          'retry_offer': {'qid': offer, 'fresh': _fresh(ev, offer, d['id'])} if offer else None,
                          'pack_sha': d['pack_sha'], 'engine_sha256': d['engine_sha256'], 'void': voids.get(d['id']),
                          'basis': 'current' if d['record_hash'] == now else 'basis_changed'})
        out = {'ok': True, 'record': {k: record[k] for k in ('id', 'day', 'subject', 'title', 'note')}, 'links': links(c, record['child_id'], record),
               'diagnoses': diags, 'seen_qids': sorted(ev)}
    status = pack_status(root)
    out.update(pack=status, deeptutor=family_deeptutor.status())
    if status['installed']:
        pack = load_pack(root)
        topic_ids = {d['topic_id'] for d in diags} | {l['topic_id'] for l in out['links'] if l['topic_id']}
        out['topics'] = {t: {k: pack['by_id'][t].get(k) for k in ('id', 'name', 'grade', 'semester', 'chapter')} for t in topic_ids if t in pack['by_id']}
        current = [d for d in diags if d['basis'] == 'current']
        target = current[0]['topic_id'] if current else next((l['topic_id'] for l in reversed(out['links']) if l['state'] == 'confirmed' and l['basis'] == 'current'), '')
        if target in pack['by_id']: out['graph'] = dict(graph_payload(pack, target), target=target)
    return out


def _base(obj):
    return {'child_id': obj['child_id'], 'record_id': obj['record_id']}


def search_record(app, obj, root=None):
    _fields(obj, ('child_id', 'record_id', 'query'), ('child_id', 'record_id', 'query'))
    with app.connect() as c: record = wrong_record(app, c, obj['child_id'], obj['record_id'])
    if record['subject'] and '数学' not in record['subject']:
        return {'status': 'none', 'candidates': [], 'total': 0, 'message': '固定知识包只覆盖数学；这道错题请回原题和原材料核对'}
    return search(load_pack(root)['topics'], str(obj['query'])[:60])


def link_record(app, obj, root=None):
    _fields(obj, ('child_id', 'record_id', 'topic_id', 'state', 'request_id', 'note'), ('child_id', 'record_id', 'state', 'request_id'))
    topics = load_pack(root)['topics'] if obj['state'] in ('confirmed', 'candidate') else None
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        replayed = _link_write(c, obj['child_id'], record, obj.get('topic_id') or '', obj['state'], obj['request_id'], topics, obj.get('note') or '')
    return dict(state(app, _base(obj), root), replayed=replayed)


def start(app, obj, root=None):
    _fields(obj, ('child_id', 'record_id', 'topic_id', 'request_id'), ('child_id', 'record_id', 'topic_id', 'request_id'))
    pack = load_pack(root)
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c); c.execute('BEGIN IMMEDIATE')
        prev = c.execute('SELECT record_id,topic_id FROM topic_diagnoses WHERE child_id=? AND request_id=?', (record['child_id'], obj['request_id'])).fetchone()
        if prev is not None:
            if (prev[0], prev[1]) != (str(record['id']), obj['topic_id']):
                raise TaxonomyError('这个提交编号已用于另一次诊断；请刷新后重新开始', 'request_conflict', 409)
        else:
            current = [l for l in links(c, record['child_id'], record) if l['basis'] == 'current']
            if not current or current[-1]['state'] != 'confirmed' or current[-1]['topic_id'] != obj['topic_id'] or obj['topic_id'] not in pack['by_id']:
                raise TaxonomyError('请先在这道错题上确认一个数学知识点', 'topic_not_confirmed', 409)
            now = time.time(); opts = {'limit': DIAG_LIMIT, 'seed': obj['request_id']}
            c.execute('INSERT INTO topic_diagnoses(child_id,record_id,record_hash,topic_id,pack_sha,engine_sha256,opts,request_id,created_at,updated_at) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?)', (record['child_id'], str(record['id']), record_hash(record), obj['topic_id'], TAXONOMY_SHA,
                                                      ENGINE_SHA256, json.dumps(opts), obj['request_id'], now, now))
    return dict(state(app, _base(obj), root), replayed=prev is not None)


def answer(app, obj, root=None):
    """逐题保存：同一序号同一内容重放不重复写；同序号不同内容409。题号须属于本次知识点子图。"""
    keys = ('child_id', 'record_id', 'diagnosis_id', 'seq', 'topic_id', 'qid', 'kind', 'answer', 'verdict', 'engine_result', 'session', 'summary')
    _fields(obj, keys, keys)
    text = _answer(obj)  # 先于任何读写和比对
    kind, verdict, result = obj['kind'], obj['verdict'], obj['engine_result']
    expected = verdict if verdict in ('correct', 'wrong') else 'skip'
    if kind not in KINDS or (kind == 'answer') != (verdict in ('correct', 'wrong', 'manual')) or (kind != 'answer' and verdict != 'skip') or result != expected:
        raise TaxonomyError('作答结果不一致：只有判对/判错进入上游计分，待核/跳过/不会都按上游skip保存', 'bad_result')
    session, summary = obj['session'], obj['summary']
    last = (session.get('answers') or [None])[-1] if isinstance(session, dict) else None
    if (type(obj['seq']) is not int or not isinstance(last, dict) or len(session['answers']) != obj['seq'] or last.get('qid') != obj['qid']
            or last.get('id') != obj['topic_id'] or last.get('result') != result or not isinstance(summary, dict)):
        raise TaxonomyError('上游会话与本题不一致，请刷新后从已保存的作答继续', 'bad_session', 409)
    blob = json.dumps(session, ensure_ascii=False); sblob = json.dumps(summary, ensure_ascii=False)
    if len(blob) > 60000 or len(sblob) > 30000: raise TaxonomyError('会话过大', 'bad_session')
    pack = load_pack(root)
    q = question(pack, obj['qid'])
    fact = {k: obj[k] for k in ('seq', 'topic_id', 'qid', 'kind', 'answer', 'verdict', 'engine_result')}
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c); c.execute('BEGIN IMMEDIATE')
        d = _diagnosis(c, record['child_id'], record, obj['diagnosis_id'])
        old = c.execute('SELECT payload_hash FROM topic_diagnosis_items WHERE diagnosis_id=? AND seq=?', (d['id'], obj['seq'])).fetchone()
        if old:
            if old[0] != _payload_hash(fact): raise TaxonomyError('这一题已保存为不同的作答；请刷新查看已保存内容', 'item_conflict', 409)
            _current(d, record)  # 依据已变时，原样重发也不冒充当前作答
            c.rollback()
            return dict(state(app, _base(obj), root), replayed=True)
        _current(d, record)
        count = c.execute('SELECT count(*) FROM topic_diagnosis_items WHERE diagnosis_id=?', (d['id'],)).fetchone()[0]
        if obj['seq'] != count + 1: raise TaxonomyError('请按顺序保存作答；刷新后从已保存的作答继续', 'out_of_order', 409)
        if count >= json.loads(d['opts'])['limit']: raise TaxonomyError('本次诊断已到题量上限', 'limit_reached', 409)
        if q is None or q['topicId'] != obj['topic_id'] or obj['topic_id'] not in closure(pack, d['topic_id']):
            raise TaxonomyError('题号不属于这次知识点范围', 'qid_outside_scope')
        c.execute('INSERT INTO topic_diagnosis_items(diagnosis_id,seq,topic_id,qid,kind,answer,verdict,engine_result,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (d['id'], obj['seq'], obj['topic_id'], obj['qid'], kind, text, verdict, result, _payload_hash(fact), time.time()))
        c.execute('UPDATE topic_diagnoses SET session=?,summary=?,state=?,version=version+1,updated_at=? WHERE id=?',
                  (blob, sblob, 'finished' if summary.get('finished') else 'active', time.time(), d['id']))
    return state(app, _base(obj), root)


def mark(app, obj, root=None):
    """暂停；记“这题看过说明/引导”（帮助只挂在这一题上）；或在显示前登记“已出示”（诊断题/新题再试）。重复点击幂等。"""
    _fields(obj, ('child_id', 'record_id', 'diagnosis_id', 'action', 'seq', 'qid', 'mode'), ('child_id', 'record_id', 'diagnosis_id', 'action'))
    action = obj['action']
    if action not in ('pause', 'help_explanation', 'help_guided', 'shown'): raise TaxonomyError('操作不正确', 'bad_request')
    if action == 'shown' and (obj.get('mode') not in ('diagnosis', 'retry') or not isinstance(obj.get('qid'), str)): raise TaxonomyError('操作不正确', 'bad_request')
    pack = load_pack(root) if action == 'shown' else None
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c); c.execute('BEGIN IMMEDIATE')
        d = _diagnosis(c, record['child_id'], record, obj['diagnosis_id'])
        if action == 'pause':
            c.execute("UPDATE topic_diagnoses SET state='paused',updated_at=? WHERE id=? AND state='active'", (time.time(), d['id']))
        elif action == 'shown':
            _current(d, record)
            q = question(pack, obj['qid'])
            if q is None or q['topicId'] not in closure(pack, d['topic_id']): raise TaxonomyError('题号不属于这次知识点范围', 'qid_outside_scope')
            known = c.execute('SELECT 1 FROM topic_exposures WHERE diagnosis_id=? AND qid=? AND mode=?', (d['id'], q['id'], obj['mode'])).fetchone()
            if obj['mode'] == 'retry' and known is None:
                if not c.execute('SELECT 1 FROM topic_diagnosis_items WHERE diagnosis_id=?', (d['id'],)).fetchone():
                    raise TaxonomyError('先做至少一题诊断，再独立再试新题', 'no_items', 409)
                if q['id'] in _evidence(c, record['child_id']):
                    raise TaxonomyError('这题此前出现过、答过或看过说明，不能当新题；请换一道没见过的', 'not_new', 409)
            if known is None:
                c.execute('INSERT INTO topic_exposures(child_id,record_id,diagnosis_id,pack_sha,qid,mode,created_at) VALUES(?,?,?,?,?,?,?)',
                          (record['child_id'], str(record['id']), d['id'], d['pack_sha'], q['id'], obj['mode'], time.time()))
        else:
            item = c.execute('SELECT id,help FROM topic_diagnosis_items WHERE diagnosis_id=? AND seq=?', (d['id'], obj.get('seq'))).fetchone()
            if item is None: raise TaxonomyError('请先保存这一题的作答，再看说明', 'not_found', 404)
            helps = sorted(set(filter(None, item['help'].split(','))) | {action[5:]})
            c.execute('UPDATE topic_diagnosis_items SET help=? WHERE id=?', (','.join(helps), item['id']))
    return state(app, _base(obj), root)


def _dt_question(q):
    kind = {'choice': 'choice', 'numeric': 'short', 'short': 'short', 'legacy': 'short'}.get(q.get('type'))
    return None if kind is None or not str(q.get('answer') or '') else {
        'question_id': q['id'], 'prompt': q.get('prompt', ''), 'question_type': kind, 'expected_answer': str(q['answer'])}


def _same_retry(prev, mine, record):
    """提交编号绑定 原错题/诊断/题号/原答/上游判定 与当时的原错题版本。"""
    if (prev['record_id'], prev['diagnosis_id'], prev['qid'], prev['answer'], prev['taxonomy_verdict']) != mine:
        raise TaxonomyError('这个提交编号已用于不同的作答；已保存的原答不变，请刷新查看', 'request_conflict', 409)
    if prev['record_hash'] != record_hash(record): raise TaxonomyError(BASIS_CHANGED, 'basis_changed', 409)


def retry(app, obj, root=None):
    """帮助之后的新题再试：这题须先由面板登记为本次诊断的“新题再试”出示，且同孩历次诊断从没出示、作答、
    看过说明或再试过；DeepTutor原register_question/grade_interaction登记并判定。题库核对（上游judgeQuestion）
    与DeepTutor复核一致且判为独立才写“复测”原记录；见过的题记not_new，不调判定组件。"""
    keys = ('child_id', 'record_id', 'diagnosis_id', 'qid', 'answer', 'verdict', 'request_id')
    _fields(obj, keys, keys)
    text = _answer(obj)  # 先于任何读写、比对和判定
    if obj['verdict'] not in ('correct', 'wrong', 'manual'): raise TaxonomyError('题库核对结果不正确', 'bad_result')
    pack = load_pack(root)
    mine = (str(obj['record_id']), obj['diagnosis_id'], obj['qid'], text, obj['verdict'])
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c)
        prev = c.execute('SELECT * FROM topic_retries WHERE child_id=? AND request_id=?', (record['child_id'], obj['request_id'])).fetchone()
        if prev is None:
            d = _diagnosis(c, record['child_id'], record, obj['diagnosis_id']); _current(d, record)
            ev = _evidence(c, record['child_id']); version, snapshot = d['version'], d['deeptutor_snapshot']
    if prev is not None:
        _same_retry(prev, mine, record)
        return dict(state(app, _base(obj), root), replayed=True)
    q = question(pack, obj['qid'])
    if q is None or q['topicId'] not in closure(pack, d['topic_id']): raise TaxonomyError('题号不属于这次知识点范围', 'qid_outside_scope')
    if q['id'] not in ev: raise TaxonomyError('这道题还没有在面板上出示为新题；请刷新后点“独立再试一道新题”', 'retry_not_offered', 409)
    fresh = _fresh(ev, q['id'], d['id'])
    dt = {}; outcome = 'parent_check'
    if not fresh:
        outcome = 'not_new'  # 此前出示/答过/看过说明/再试过：不算独立，不调判定器
    elif obj['verdict'] != 'manual' and _dt_question(q):
        topic = {'id': d['topic_id'], 'name': pack['by_id'][d['topic_id']].get('name', '')}
        session = f"diag-{d['id']}"
        reg = family_deeptutor.call('register', snapshot, topic=topic, question=_dt_question(q), session_id=session, turn_id=obj['request_id'] + '-q')
        graded = family_deeptutor.call('grade', reg['snapshot'], topic=topic, question_id=q['id'], answer=text,
                                       session_id=session, turn_id=obj['request_id'] + '-a')
        result = (graded.get('interaction') or {}).get('result') or {}
        dt = {'is_correct': result.get('is_correct'), 'independent': result.get('independent'), 'replayed': graded.get('replayed'),
              'deeptutor_sha': graded.get('deeptutor_sha'), 'snapshot': graded['snapshot']}
        agreed = isinstance(dt['is_correct'], bool) and (obj['verdict'] == 'correct') == dt['is_correct']
        outcome = ('not_independent' if dt['independent'] is not True else
                   'parent_check' if not agreed else 'independent_correct' if dt['is_correct'] else 'independent_wrong')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        prev = c.execute('SELECT * FROM topic_retries WHERE child_id=? AND request_id=?', (record['child_id'], obj['request_id'])).fetchone()
        if prev is not None:
            c.rollback(); _same_retry(prev, mine, record)
            return dict(state(app, _base(obj), root), replayed=True)
        d = _diagnosis(c, record['child_id'], record, obj['diagnosis_id']); _current(d, record)
        if d['version'] != version or _fresh(_evidence(c, record['child_id']), q['id'], d['id']) != fresh:
            raise TaxonomyError('这次诊断刚有新的保存，请刷新后再提交；原答还在输入框里', 'diagnosis_changed', 409)
        followup = None
        if outcome.startswith('independent_'):
            topic = pack['by_id'][q['topicId']]
            note = '\n'.join([f"新题（{REVIEW_STATUS}）：{q.get('prompt', '')}", f"孩子作答：{text}",
                              f"题库核对：{ {'correct': '对', 'wrong': '错'}[obj['verdict']] }；复核结果：{'对' if dt['is_correct'] else '错'}（独立作答，两项检查一致）",
                              f"知识点：{topic.get('name', '')}（{q['topicId']}，知识包{TAXONOMY_SHA[:7]}）",
                              '这题此前各次诊断都没出示、没答过、没看过说明；一次结果不等于掌握。'])
            saved = app.save_record(dict(child=record['child'], day=time.strftime('%Y-%m-%d'), category='学习进展', subject=record['subject'] or '数学',
                                         title=('新题再试 · ' + (record['title'] or '错题'))[:200], note=note, source=RETRY_SOURCE,
                                         related_record_id=record['id'], followup_kind='复测', assistance='独立尝试',
                                         practice_relation='相近的新题或新片段', request_key=('tdr-' + obj['request_id'])[:128]), connection=c)
            followup = saved.get('record_id')
        snap = dt.pop('snapshot', None)
        c.execute('INSERT INTO topic_retries(diagnosis_id,child_id,record_id,record_hash,topic_id,qid,answer,taxonomy_verdict,deeptutor,outcome,followup_record_id,request_id,created_at) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (d['id'], record['child_id'], str(record['id']), record_hash(record), q['topicId'], q['id'],
                                                        text, obj['verdict'], json.dumps(dt), outcome, followup, obj['request_id'], time.time()))
        c.execute('UPDATE topic_diagnoses SET deeptutor_snapshot=?,version=version+1,updated_at=? WHERE id=?', (snap or snapshot, time.time(), d['id']))
    return state(app, _base(obj), root)


ROUTES = {'/api/topic/state': state, '/api/topic/search': search_record, '/api/topic/link': link_record,
          '/api/topic/diagnosis/start': start, '/api/topic/diagnosis/answer': answer, '/api/topic/diagnosis/mark': mark,
          '/api/topic/diagnosis/retry': retry}

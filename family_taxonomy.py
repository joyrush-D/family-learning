"""cn-math-taxonomy固定知识包的薄适配：载包校验、数学知识点搜索、同孩原错题的知识点链接与诊断记录。

上游：xiaoyang111222/cn-math-taxonomy@e0f931badaed994fa8e10cfc7a30cdbdffc2dfd5，CC BY-NC 4.0，
AI初稿、未经教师审核。公开仓库只放本清单与适配代码；知识包由家庭本机放入Git忽略目录，
加载时逐文件校验sha256，不在则报“知识包未安装”，原错题/引导/每日待办照常可用。
诊断算法（diagnose/engine.js）在浏览器里原样运行（createSession/nextItem/judgeQuestion/applyAnswer/
summarize/replay），本模块不选题、不判题、不推断掌握：只核对题号属于本次知识点子图、按逐题幂等保存
原答与上游输出，并在“新题再试”时交DeepTutor原LearningService登记/判定（family_deeptutor）。
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
    # 只新增表，不改旧表/旧行。
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


def record_hash(record):
    keep = {k: record.get(k) for k in ('id', 'child_id', 'child', 'subject', 'title', 'note', 'attachments', 'created',
                                       'question', 'answer', 'correction', 'updated_at')}
    return hashlib.sha256(json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _own(child_id, record):
    if not record or str(record.get('child_id')) != str(child_id):
        raise TaxonomyError('这条错题不属于当前孩子', 'cross_child', 403)


def link(conn, child_id, record, topic_id, state, request_id, topics=None, note=''):
    _own(child_id, record)
    if state not in LINK_STATES: raise TaxonomyError('知识点状态不正确', 'bad_state')
    if state in ('confirmed', 'candidate'):
        if not topic_id or (topics is not None and topic_id not in {t['id'] for t in math_topics(topics)}):
            raise TaxonomyError('知识点不在固定数学知识包中', 'unknown_topic')
    elif topic_id: raise TaxonomyError('不明或无匹配时不绑定知识点', 'bad_state')
    if not request_id: raise TaxonomyError('缺少请求编号', 'missing_request')
    ensure_schema(conn)
    with conn:
        conn.execute('INSERT OR IGNORE INTO topic_links(child_id,record_id,record_hash,topic_id,state,pack_sha,note,request_id,created_at) '
                     'VALUES(?,?,?,?,?,?,?,?,?)', (str(child_id), str(record['id']), record_hash(record), topic_id or '', state,
                                                   TAXONOMY_SHA, str(note)[:300], str(request_id), time.time()))
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


def _diagnosis(conn, child_id, record, diagnosis_id):
    row = conn.execute('SELECT * FROM topic_diagnoses WHERE id=? AND child_id=? AND record_id=?',
                       (diagnosis_id, child_id, str(record['id']))).fetchone() if type(diagnosis_id) is int else None
    if row is None: raise TaxonomyError('这次诊断不属于这道错题', 'not_found', 404)
    return row


def _current(row, record):
    if row['record_hash'] != record_hash(record):
        raise TaxonomyError('原错题已更正，这次诊断的依据已失效；请按更正后的错题重新开始', 'basis_changed', 409)


def _payload_hash(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def state(app, obj, root=None):
    _fields(obj, ('child_id', 'record_id'), ('child_id', 'record_id'))
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c)
        now = record_hash(record)
        diags = []
        for d in c.execute('SELECT * FROM topic_diagnoses WHERE child_id=? AND record_id=? ORDER BY id DESC LIMIT 5', (record['child_id'], str(record['id']))):
            items = [dict(r) for r in c.execute('SELECT seq,topic_id,qid,kind,answer,verdict,engine_result,help FROM topic_diagnosis_items WHERE diagnosis_id=? ORDER BY seq', (d['id'],))]
            retries = [dict(r, deeptutor=json.loads(r['deeptutor'])) for r in c.execute(
                'SELECT id,topic_id,qid,answer,taxonomy_verdict,deeptutor,outcome,followup_record_id,created_at FROM topic_retries WHERE diagnosis_id=? ORDER BY id', (d['id'],))]
            diags.append({'id': d['id'], 'topic_id': d['topic_id'], 'opts': json.loads(d['opts']), 'state': d['state'], 'version': d['version'],
                          'summary': json.loads(d['summary'] or 'null'), 'items': items, 'retries': retries,
                          'pack_sha': d['pack_sha'], 'engine_sha256': d['engine_sha256'],
                          'basis': 'current' if d['record_hash'] == now else 'basis_changed'})
        out = {'ok': True, 'record': {k: record[k] for k in ('id', 'day', 'subject', 'title', 'note')}, 'links': links(c, record['child_id'], record),
               'diagnoses': diags}
    status = pack_status(root)
    out.update(pack=status, deeptutor=family_deeptutor.status())
    if status['installed']:
        pack = load_pack(root)
        topic_ids = {d['topic_id'] for d in diags} | {l['topic_id'] for l in out['links'] if l['topic_id']}
        out['topics'] = {t: {k: pack['by_id'][t].get(k) for k in ('id', 'name', 'grade', 'semester', 'chapter')} for t in topic_ids if t in pack['by_id']}
        target = diags[0]['topic_id'] if diags else next((l['topic_id'] for l in reversed(out['links']) if l['state'] == 'confirmed' and l['basis'] == 'current'), '')
        if target in pack['by_id']: out['graph'] = dict(graph_payload(pack, target), target=target)
    return out


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
        return {'ok': True, 'links': link(c, obj['child_id'], record, obj.get('topic_id') or '', obj['state'], obj['request_id'], topics, obj.get('note') or '')}


def start(app, obj, root=None):
    _fields(obj, ('child_id', 'record_id', 'topic_id', 'request_id'), ('child_id', 'record_id', 'topic_id', 'request_id'))
    pack = load_pack(root)
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c); c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM topic_diagnoses WHERE child_id=? AND request_id=?', (record['child_id'], obj['request_id'])).fetchone() is None:
            current = [l for l in links(c, record['child_id'], record) if l['basis'] == 'current']
            if not current or current[-1]['state'] != 'confirmed' or current[-1]['topic_id'] != obj['topic_id'] or obj['topic_id'] not in pack['by_id']:
                raise TaxonomyError('请先在这道错题上确认一个数学知识点', 'topic_not_confirmed', 409)
            now = time.time(); opts = {'limit': DIAG_LIMIT, 'seed': obj['request_id']}
            c.execute('INSERT INTO topic_diagnoses(child_id,record_id,record_hash,topic_id,pack_sha,engine_sha256,opts,request_id,created_at,updated_at) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?)', (record['child_id'], str(record['id']), record_hash(record), obj['topic_id'], TAXONOMY_SHA,
                                                      ENGINE_SHA256, json.dumps(opts), obj['request_id'], now, now))
    return state(app, {'child_id': obj['child_id'], 'record_id': obj['record_id']}, root)


def answer(app, obj, root=None):
    """逐题保存：同一序号同一内容重放不重复写；同序号不同内容409。题号须属于本次知识点子图。"""
    keys = ('child_id', 'record_id', 'diagnosis_id', 'seq', 'topic_id', 'qid', 'kind', 'answer', 'verdict', 'engine_result', 'session', 'summary')
    _fields(obj, keys, keys)
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
            c.rollback()
            return dict(state(app, {'child_id': obj['child_id'], 'record_id': obj['record_id']}, root), replayed=True)
        _current(d, record)
        count = c.execute('SELECT count(*) FROM topic_diagnosis_items WHERE diagnosis_id=?', (d['id'],)).fetchone()[0]
        if obj['seq'] != count + 1: raise TaxonomyError('请按顺序保存作答；刷新后从已保存的作答继续', 'out_of_order', 409)
        if count >= json.loads(d['opts'])['limit']: raise TaxonomyError('本次诊断已到题量上限', 'limit_reached', 409)
        if q is None or q['topicId'] != obj['topic_id'] or obj['topic_id'] not in closure(pack, d['topic_id']):
            raise TaxonomyError('题号不属于这次知识点范围', 'qid_outside_scope')
        c.execute('INSERT INTO topic_diagnosis_items(diagnosis_id,seq,topic_id,qid,kind,answer,verdict,engine_result,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (d['id'], obj['seq'], obj['topic_id'], obj['qid'], kind, str(obj['answer'])[:500], verdict, result, _payload_hash(fact), time.time()))
        c.execute('UPDATE topic_diagnoses SET session=?,summary=?,state=?,version=version+1,updated_at=? WHERE id=?',
                  (blob, sblob, 'finished' if summary.get('finished') else 'active', time.time(), d['id']))
    return state(app, {'child_id': obj['child_id'], 'record_id': obj['record_id']}, root)


def mark(app, obj, root=None):
    """暂停，或记“这题看过说明/引导”（帮助只挂在这一题上）。重复点击幂等。"""
    _fields(obj, ('child_id', 'record_id', 'diagnosis_id', 'action', 'seq'), ('child_id', 'record_id', 'diagnosis_id', 'action'))
    if obj['action'] not in ('pause', 'help_explanation', 'help_guided'): raise TaxonomyError('操作不正确', 'bad_request')
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c); c.execute('BEGIN IMMEDIATE')
        d = _diagnosis(c, record['child_id'], record, obj['diagnosis_id'])
        if obj['action'] == 'pause':
            c.execute("UPDATE topic_diagnoses SET state='paused',updated_at=? WHERE id=? AND state='active'", (time.time(), d['id']))
        else:
            item = c.execute('SELECT id,help FROM topic_diagnosis_items WHERE diagnosis_id=? AND seq=?', (d['id'], obj.get('seq'))).fetchone()
            if item is None: raise TaxonomyError('请先保存这一题的作答，再看说明', 'not_found', 404)
            helps = sorted(set(filter(None, item['help'].split(','))) | {obj['action'][5:]})
            c.execute('UPDATE topic_diagnosis_items SET help=? WHERE id=?', (','.join(helps), item['id']))
    return state(app, {'child_id': obj['child_id'], 'record_id': obj['record_id']}, root)


def _dt_question(q):
    kind = {'choice': 'choice', 'numeric': 'short', 'short': 'short', 'legacy': 'short'}.get(q.get('type'))
    return None if kind is None or not str(q.get('answer') or '') else {
        'question_id': q['id'], 'prompt': q.get('prompt', ''), 'question_type': kind, 'expected_answer': str(q['answer'])}


def retry(app, obj, root=None):
    """帮助之后的新题再试：题号必须本次诊断（含此前再试）从未出现过，且这题没有帮助；DeepTutor原
    register_question/grade_interaction登记并判定。两个判题器一致且DeepTutor判为独立才写“复测”原记录。"""
    keys = ('child_id', 'record_id', 'diagnosis_id', 'qid', 'answer', 'verdict', 'request_id')
    _fields(obj, keys, keys)
    if obj['verdict'] not in ('correct', 'wrong', 'manual'): raise TaxonomyError('上游判题结果不正确', 'bad_result')
    pack = load_pack(root)
    replay = lambda: dict(state(app, {'child_id': obj['child_id'], 'record_id': obj['record_id']}, root), replayed=True)
    with app.connect() as c:
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        ensure_schema(c)
        if c.execute('SELECT 1 FROM topic_retries WHERE child_id=? AND request_id=?', (record['child_id'], obj['request_id'])).fetchone(): return replay()
        d = _diagnosis(c, record['child_id'], record, obj['diagnosis_id']); _current(d, record)
        seen = {r[0] for r in c.execute('SELECT qid FROM topic_diagnosis_items WHERE diagnosis_id=? UNION SELECT qid FROM topic_retries WHERE diagnosis_id=?', (d['id'], d['id']))}
        version, snapshot = d['version'], d['deeptutor_snapshot']
    q = question(pack, obj['qid'])
    if q is None or q['topicId'] not in closure(pack, d['topic_id']): raise TaxonomyError('题号不属于这次知识点范围', 'qid_outside_scope')
    dt = {}; outcome = 'parent_check'
    if obj['qid'] in seen:
        outcome = 'not_new'  # 上游avoid用尽会退回已见过的题：不算独立，不调判定器
    elif obj['verdict'] != 'manual' and _dt_question(q):
        topic = {'id': d['topic_id'], 'name': pack['by_id'][d['topic_id']].get('name', '')}
        session = f"diag-{d['id']}"
        reg = family_deeptutor.call('register', snapshot, topic=topic, question=_dt_question(q), session_id=session, turn_id=obj['request_id'] + '-q')
        graded = family_deeptutor.call('grade', reg['snapshot'], topic=topic, question_id=q['id'], answer=str(obj['answer'])[:500],
                                       session_id=session, turn_id=obj['request_id'] + '-a')
        result = (graded.get('interaction') or {}).get('result') or {}
        dt = {'is_correct': result.get('is_correct'), 'independent': result.get('independent'), 'replayed': graded.get('replayed'),
              'deeptutor_sha': graded.get('deeptutor_sha'), 'snapshot': graded['snapshot']}
        agreed = isinstance(dt['is_correct'], bool) and (obj['verdict'] == 'correct') == dt['is_correct']
        outcome = ('not_independent' if dt['independent'] is not True else
                   'parent_check' if not agreed else 'independent_correct' if dt['is_correct'] else 'independent_wrong')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM topic_retries WHERE child_id=? AND request_id=?', (record['child_id'], obj['request_id'])).fetchone():
            c.rollback(); return replay()
        record = wrong_record(app, c, obj['child_id'], obj['record_id'])
        d = _diagnosis(c, record['child_id'], record, obj['diagnosis_id']); _current(d, record)
        if d['version'] != version: raise TaxonomyError('这次诊断刚有新的保存，请刷新后再提交', 'diagnosis_changed', 409)
        followup = None
        if outcome.startswith('independent_'):
            topic = pack['by_id'][q['topicId']]
            note = '\n'.join([f"新题（{REVIEW_STATUS}）：{q.get('prompt', '')}", f"孩子作答：{obj['answer']}",
                              f"上游判题：{ {'correct': '对', 'wrong': '错'}[obj['verdict']] }；DeepTutor判定：{'对' if dt['is_correct'] else '错'}（独立作答）",
                              f"知识点：{topic.get('name', '')}（{q['topicId']}，知识包{TAXONOMY_SHA[:7]}）",
                              '这题本次诊断没出现过，作答前没看说明；一次结果不等于掌握。'])
            saved = app.save_record(dict(child=record['child'], day=time.strftime('%Y-%m-%d'), category='学习进展', subject=record['subject'] or '数学',
                                         title=('新题再试 · ' + (record['title'] or '错题'))[:200], note=note, source=RETRY_SOURCE,
                                         related_record_id=record['id'], followup_kind='复测', assistance='独立尝试',
                                         practice_relation='相近的新题或新片段', request_key=('tdr-' + obj['request_id'])[:128]), connection=c)
            followup = saved.get('record_id')
        snap = dt.pop('snapshot', None)
        c.execute('INSERT INTO topic_retries(diagnosis_id,child_id,record_id,record_hash,topic_id,qid,answer,taxonomy_verdict,deeptutor,outcome,followup_record_id,request_id,created_at) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (d['id'], record['child_id'], str(record['id']), record_hash(record), q['topicId'], q['id'],
                                                        str(obj['answer'])[:500], obj['verdict'], json.dumps(dt), outcome, followup, obj['request_id'], time.time()))
        c.execute('UPDATE topic_diagnoses SET deeptutor_snapshot=?,version=version+1,updated_at=? WHERE id=?', (snap or snapshot, time.time(), d['id']))
    return state(app, {'child_id': obj['child_id'], 'record_id': obj['record_id']}, root)


ROUTES = {'/api/topic/state': state, '/api/topic/search': search_record, '/api/topic/link': link_record,
          '/api/topic/diagnosis/start': start, '/api/topic/diagnosis/answer': answer, '/api/topic/diagnosis/mark': mark,
          '/api/topic/diagnosis/retry': retry}

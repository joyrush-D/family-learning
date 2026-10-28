"""cn-math-taxonomy固定知识包的薄适配：载包校验、数学知识点搜索、同孩原记录的知识点链接。

上游：xiaoyang111222/cn-math-taxonomy@e0f931badaed994fa8e10cfc7a30cdbdffc2dfd5，CC BY-NC 4.0，
AI初稿、未经教师审核。公开仓库只放本清单与适配代码；知识包由家庭本机放入Git忽略目录，
加载时逐文件校验sha256，不在则报“知识包未安装”，原错题/引导/每日待办照常可用。
诊断算法（diagnose/engine.js）不在此重写；本模块不选题、不判题、不推断掌握。"""
import hashlib, json, os, sqlite3, time
from pathlib import Path

TAXONOMY_SHA = 'e0f931badaed994fa8e10cfc7a30cdbdffc2dfd5'
RAW = f'https://raw.githubusercontent.com/xiaoyang111222/cn-math-taxonomy/{TAXONOMY_SHA}/'
# sha256取自本次run只读证据包；Root安装时须再与上游同SHA的Git blob核对。
MANIFEST = {
    'diagnose/engine.js': ('b4a48814213a5b50a49c86e39afcc6a6c81142cf4a8243cdfdc55dea397a017e', 47863),
    'data/topics.json': ('003a94a2dc6f5161f46b32f9e61d95c3ece73ec238ced58f6802b3bfe4e95909', 2010398),
    'data/dependencies.json': ('e4c459ea539b2c85ef4a588c6814bbba7d24a7d53252b57c9061d01cf2419bb2', 710228),
    'data/questions.json': ('74f669033e5d47685da4d8e66331188806ff99f415550d6a2e09cc2ade9f1a5c', 6083743),
    'data/id-aliases.json': ('791334fe08835c539ce7dd6afa686dffebba5f810d11ec616b5c5d70a87864fb', 3177),
}
REVIEW_STATUS = 'AI初稿，未经教师审核'
LINK_STATES = ('confirmed', 'candidate', 'unclear', 'no_match')


class TaxonomyError(Exception):
    def __init__(self, message, code, status=400):
        super().__init__(message); self.code = code; self.status = status


def pack_dir():
    return Path(os.environ.get('FAMILY_TAXONOMY_DIR') or Path(__file__).resolve().parent / 'knowledge' / f'cn-math-taxonomy-{TAXONOMY_SHA[:7]}')


def pack_status(root=None, manifest=MANIFEST):
    root = Path(root or pack_dir()); problems = []
    for rel, (digest, size) in manifest.items():
        path = root / rel
        if not path.is_file(): problems.append({'file': rel, 'problem': 'missing'}); continue
        if path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append({'file': rel, 'problem': 'sha256_mismatch'})
    return {'installed': not problems, 'sha': TAXONOMY_SHA, 'review_status': REVIEW_STATUS, 'problems': problems,
            'message': '' if not problems else '知识包未安装或与固定版本不一致；原错题与引导照常可用'}


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


def ensure_schema(conn):
    # 只新增表，不改旧表/旧行。
    conn.execute('''CREATE TABLE IF NOT EXISTS topic_links(
        id INTEGER PRIMARY KEY, child_id TEXT NOT NULL, record_id TEXT NOT NULL, record_hash TEXT NOT NULL,
        topic_id TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, pack_sha TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
        request_id TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(child_id, request_id))''')


def record_hash(record):
    keep = {k: record.get(k) for k in ('id', 'child_id', 'question', 'answer', 'correction', 'updated_at')}
    return hashlib.sha256(json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def link(conn, child_id, record, topic_id, state, request_id, topics=None, note=''):
    if not record or str(record.get('child_id')) != str(child_id):
        raise TaxonomyError('这条错题不属于当前孩子', 'cross_child', 403)
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
    if not record or str(record.get('child_id')) != str(child_id):
        raise TaxonomyError('这条错题不属于当前孩子', 'cross_child', 403)
    ensure_schema(conn); now = record_hash(record)
    rows = conn.execute('SELECT topic_id,state,record_hash,pack_sha,note,created_at FROM topic_links WHERE child_id=? AND record_id=? ORDER BY id',
                        (str(child_id), str(record['id']))).fetchall()
    return [{'topic_id': r[0], 'state': r[1], 'pack_sha': r[3], 'note': r[4], 'created_at': r[5],
             'basis': 'current' if r[2] == now else 'basis_changed'} for r in rows]

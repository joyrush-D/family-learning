"""一次性stdio适配：在独立py>=3.11进程里运行固定版本DeepTutor的原LearningService。

上游：HKUDS/DeepTutor@a31d82624c27d75f4e771d4fcb78dce16470b383（Apache-2.0），文件见third_party/deeptutor/；
除lesson_evidence.py把RAG导入移入实际使用的函数（NOTICE与patches/）外均为原字节。只走确定性的register_question、grade_interaction、
abandon_active_question、repair_question；不导入semantic/Agent/LLM/RAG模块，禁止联网。
家庭SQLite是唯一权威：每次请求把上一份快照写入父进程给定的一次性work_dir（环境不含HOME），原Service运算后序列化返回，
临时目录随即丢弃。由family_deeptutor.py用`python -I`启动，输入输出各一行JSON。"""
import base64, json, socket, sqlite3, sys, tempfile
from pathlib import Path

DEEPTUTOR_SHA = 'a31d82624c27d75f4e771d4fcb78dce16470b383'
SRC = Path(__file__).resolve().parent / 'third_party' / 'deeptutor' / 'src'
BOOK = 'family-retry'
MODULE = 'family-topic'


def _offline(*_args, **_kwargs):
    raise OSError('DeepTutor sidecar has no network access')


def _block_network():
    socket.socket.connect = _offline
    socket.socket.connect_ex = _offline
    socket.create_connection = _offline
    socket.getaddrinfo = _offline


def _restore(root, snapshot):
    if snapshot:
        # serialize()得到的是完整数据库文件映像（含已提交WAL页），原样写回即可由原LearningStore打开。
        (root / 'mastery.sqlite3').write_bytes(base64.b64decode(snapshot))


def _snapshot(root):
    db = sqlite3.connect(root / 'mastery.sqlite3')
    try: return base64.b64encode(db.serialize()).decode('ascii')
    finally: db.close()


def _interaction(item):
    if item is None: return None
    data = item.model_dump(mode='json')
    question = data.get('question') or {}
    return {'interaction_id': data.get('interaction_id'), 'status': data.get('status'),
            'question_id': question.get('question_id'), 'knowledge_point_id': question.get('knowledge_point_id'),
            'assistance_used': bool(question.get('assistance_used')), 'user_answer': data.get('user_answer', ''),
            'result': data.get('result') or {}}


def _attempts(progress):
    return [{'question_id': a.question_id, 'is_correct': a.is_correct, 'independent': a.independent,
             'voided': a.voided, 'void_reason': a.void_reason} for a in progress.quiz_attempts]


def run(request):
    from deeptutor.learning.models import KnowledgePoint, KnowledgeType, LearningModule, PendingQuestion
    from deeptutor.learning.service import LearningService
    from deeptutor.learning.storage import LearningStore
    op = request.get('op')
    with tempfile.TemporaryDirectory(prefix='family-deeptutor-', dir=request.get('work_dir') or None) as tmp:
        root = Path(tmp)
        _restore(root, request.get('snapshot'))
        service = LearningService(store=LearningStore(root=root))
        progress = service.get_or_create(BOOK)
        topic = request.get('topic') or {}
        if not progress.modules:
            point = KnowledgePoint(id=str(topic['id']), name=str(topic.get('name') or topic['id']),
                                   type=KnowledgeType.CONCEPT, module_id=MODULE)
            service.init_modules(progress, [LearningModule(id=MODULE, name=point.name, order=0, knowledge_points=[point])])
            service.store.save(progress)
        session, turn = str(request.get('session_id') or ''), str(request.get('turn_id') or '')
        out = {'op': op}
        if op == 'register':
            q = request['question']
            pending = PendingQuestion(
                question_id=str(q['question_id']), knowledge_point_id=str(topic['id']), module_id=MODULE,
                prompt=str(q.get('prompt') or ''), question_type=str(q.get('question_type') or 'short'),
                expected_answer=str(q.get('expected_answer') or ''),
                accepted_answers=[str(x) for x in q.get('accepted_answers') or []],
                explanation=str(q.get('explanation') or ''), difficulty=str(q.get('difficulty') or ''),
                source_evidence=dict(q.get('source_evidence') or {}),
                assistance_used=bool(request.get('assistance_used')),
                assistance_context={'session_id': session, 'turn_id': turn} if request.get('assistance_used') else {})
            action = request.get('pending_action') or 'retain'
            progress, item, created = service.register_question(
                BOOK, pending, pending_action=action, replace_question_id=str(request.get('replace_question_id') or ''),
                session_id=session, turn_id=turn)
            out.update(created=created, interaction=_interaction(item))
        elif op == 'grade':
            progress, item, replayed = service.grade_interaction(
                BOOK, answer=str(request.get('answer') or ''), question_id=str(request['question_id']),
                session_id=session, turn_id=turn)
            out.update(replayed=replayed, interaction=_interaction(item))
        elif op == 'abandon':
            progress, changed = service.abandon_active_question(BOOK)
            out.update(changed=changed)
        elif op == 'void':
            progress, receipt = service.repair_question(
                BOOK, str(request['question_id']), action='void', reason=str(request.get('reason') or 'source changed'),
                session_id=session, turn_id=turn)
            out.update(receipt=json.loads(json.dumps(receipt, default=str)))
        elif op != 'status':
            raise ValueError('unknown op')
        progress = service.get_or_create(BOOK)
        pending = progress.pending_question
        out.update(attempts=_attempts(progress), pending_question_id=pending.question_id if pending else '',
                   snapshot=_snapshot(root))
    return out


def main():
    _block_network()
    sys.path.insert(0, str(SRC))
    before = set(sys.modules)
    try:
        request = json.loads(sys.stdin.readline() or '{}')
        out = {'ok': True, **run(request)}
    except Exception as exc:  # 返回分类错误，父进程只降级当前步骤
        out = {'ok': False, 'error': type(exc).__name__, 'detail': str(exc)[:300]}
    loaded = sorted(m for m in set(sys.modules) - before if m.split('.')[0] in ('deeptutor', 'pydantic'))
    out.update(deeptutor_sha=DEEPTUTOR_SHA, python=sys.version.split()[0],
               modules=[m for m in loaded if m.startswith('deeptutor')],
               pydantic=getattr(sys.modules.get('pydantic.version'), 'VERSION', ''))
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()

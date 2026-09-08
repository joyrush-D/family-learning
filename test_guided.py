"""Fictional short-guidance HTTP, ownership, receipt and model-race checks."""
from concurrent.futures import ThreadPoolExecutor
import copy
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import family_backup
import family_child
import family_guided
import family_llm


class GuidedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-guided-')
        self.root = Path(self.temp.name).resolve()
        self.data = self.root / 'private'
        (self.data / 'uploads').mkdir(parents=True)
        self.config = patch.multiple(app, ROOT=self.root, DATA=self.data, DB=self.data / 'family.sqlite3')
        self.config.start()
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        (self.root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        (self.root / '跟踪台账.md').write_text('| T01 | 示例甲 | 学校原任务 | 2026-09-20 | 待跟进 | GROUP_PRIVATE_CANARY | 学校原要求 |\n')
        self.store = family_guided.Store(app)
        self.counter = 0
        self.calls = []
        def model(material, attempts, hints, images=(), **kwargs):
            self.calls.append(copy.deepcopy((material, attempts, hints, images)))
            return dict(hint='先把已知的数量分别写下来。', question='这两个数量表示什么？', uncertainties=[])
        self.model = patch.object(family_llm, 'guided_hint', side_effect=model)
        self.model.start()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.first = self.login('child-1')
        self.second = self.login('child-2')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.model.stop()
        self.environment.stop()
        self.config.stop()
        self.temp.cleanup()

    def request(self, **fields):
        self.counter += 1
        return dict(request_key='fictional-guided-request-' + str(self.counter), **fields)

    def http(self, path, obj=None, session=None, parent=False, csrf=True, headers=None):
        values = {'Host': 'localhost', 'Content-Type': 'application/json'} | dict(headers or {})
        if parent:
            values['X-Family-Token'] = app.TOKEN
        if session:
            values['Cookie'] = session['cookie']
            if csrf:
                values['X-Child-CSRF'] = session['csrf']
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        connection.request('GET' if obj is None else 'POST', path, None if obj is None else json.dumps(obj), values)
        reply = connection.getresponse()
        body, code, response_headers = reply.read(), reply.status, dict(reply.getheaders())
        connection.close()
        if response_headers.get('Content-Type', '').startswith('application/json'):
            body = json.loads(body)
        return code, body, response_headers

    def login(self, ident):
        invite = family_child.parent_action(app, 'invite', dict(child_id=ident))
        code, body, headers = self.http('/child/api/login', dict(invite=invite['invite']))
        self.assertEqual(code, 200)
        return dict(cookie=headers['Set-Cookie'].split(';', 1)[0], csrf=body['csrf'])

    def call(self, operation, obj, session=None, **kwargs):
        return self.http('/child/api/guided/' + operation, obj, self.first if session is None else session, **kwargs)

    def material(self, **fields):
        payload = self.request(child_id='child-1', version=0, title='虚构的加法问题', subject='数学',
            question_text='有两枚蓝色棋子和三枚红色棋子，一共有几枚？', question_attachments=[],
            reference_text='PRIVATE_REFERENCE_CANARY：2+3=5。', reference_checked=True, shared=True)
        payload.update(fields)
        result = self.store.save_material(payload)
        return next(row for row in result['sessions'] if row['title'] == payload['title'])

    def row(self, ident):
        return next(row for row in self.store.snapshot()['sessions'] if row['id'] == ident)

    def child_action(self, ident, action, **fields):
        payload = self.request(id=ident, version=self.row(ident)['version'], action=action, **fields)
        result = self.call('action', payload)
        return result, payload

    def parent_action(self, ident, action, **fields):
        row = self.row(ident)
        return self.store.action(self.request(id=ident, version=row['version'], child_id=row['child_id'], action=action, **fields))

    def plan(self, **fields):
        return dict(goal='解释合并两组数量为什么用加法', success_criteria='先说思路，再写出算式；记录实际用了什么帮助。',
                    start='PARENT_GUIDE_PRIVATE_CANARY：先让孩子独立说思路。', ask='你想怎样表示这两组数量？',
                    help='卡住时先指认已知数量；必要时示范相似一步，再让孩子继续。',
                    stop='孩子能解释本次思路或想休息时停下，保留实际表现。', retry='商量之后另选一次机会，不看讲解试相近的新问题。') | fields

    def upload(self, mime='image/png', child=None):
        ident = secrets.token_hex(16)
        raw = b'fictional original bytes'
        (self.data / 'uploads' / ident).write_bytes(raw)
        with app.connect() as c:
            c.execute('INSERT INTO uploads VALUES (?,?,?,?,?)', (ident, 'fictional-original', len(raw), mime, '2026-09-09'))
            if child:
                c.execute('INSERT INTO child_uploads VALUES (?,?)', (ident, child))
                c.execute('INSERT INTO reading_uploads VALUES (?,?)', (ident, child))
        return ident

    def test_first_attempt_hint_again_finish_and_immutable_provenance(self):
        original = app.save_record(dict(child='示例甲', day='2026-09-09', category='学习进展', title='虚构原练习', note='PARENT_NOTE_PRIVATE_CANARY'))['record']['id']
        row = self.material(related_record_id=original, practice_relation='相近的新题或新片段')
        initial, payload = self.child_action(row['id'], 'attempt', kind='first', text='我想到把两种颜色放在一起。', assistance='')
        self.assertEqual(initial[0], 200, initial)
        self.assertEqual(self.call('action', payload)[0], 200)
        self.assertEqual(self.call('action', payload | dict(text='换一个说法'))[0], 409)
        self.assertEqual(self.call('action', payload | dict(action='hint'))[0], 400)
        self.assertEqual(self.child_action(row['id'], 'hint')[0][0], 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1][0]['text'], payload['text'])
        self.assertNotIn('PARENT_NOTE_PRIVATE_CANARY', str(self.calls))
        self.assertNotIn('GROUP_PRIVATE_CANARY', str(self.calls))
        self.assertEqual(self.child_action(row['id'], 'attempt', kind='explain_again', text='我把两组放在一起数。', assistance='少量提示')[0][0], 200)
        self.assertEqual(self.child_action(row['id'], 'finish', note='今天先到这里')[0][0], 200)
        finished = self.row(row['id'])
        self.assertEqual(finished['state'], 'closed')
        child_row = self.call('state', {})[1]['sessions'][0]
        self.assertEqual(child_row['allowed_actions'], [])
        self.assertNotIn('PRIVATE_CANARY', json.dumps(child_row))
        for key in ('reference_text', 'reference_checked', 'related_record_id', 'record_id', 'child_id'):
            self.assertNotIn(key, json.dumps(child_row))
        with app.connect() as c:
            records = [dict(r) for r in c.execute('SELECT * FROM records WHERE source LIKE ? ORDER BY id', (family_guided.SOURCE + '%',))]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]['note'], payload['text'])
            self.assertEqual(records[0]['assistance'], '')
            self.assertEqual(records[0]['related_record_id'], original)
            self.assertEqual(records[0]['practice_relation'], '相近的新题或新片段')
            self.assertEqual(records[1]['related_record_id'], records[0]['id'])
            self.assertEqual(records[1]['practice_relation'], '同一道题或同一片段')
            self.assertIn('已提供 1 条系统提示', records[1]['comparison_note'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reading_awards').fetchone()[0], 0)
        code = self.http('/api/record', dict(id=records[0]['id'], child='示例甲', day=records[0]['day'], category='学习进展',
            title=records[0]['title'], note='不得替换孩子原话', source=records[0]['source']), parent=True)[0]
        self.assertEqual(code, 409)
        self.assertEqual(self.http('/api/record', dict(child='示例甲', day='2026-09-09', category='学习进展',
            title='伪造专属来源', note='虚构', source=family_guided.SOURCE + row['id']), parent=True)[0], 409)

    def test_http_permissions_parent_material_validation_and_upload_revocation(self):
        image = self.upload()
        row = self.material(question_attachments=[image])
        other = self.material(child_id='child-2', title='另一孩子问题')
        self.assertEqual(self.http('/child/api/guided/state', {})[0], 401)
        self.assertEqual(self.call('state', {}, csrf=False)[0], 403)
        self.assertEqual(self.call('state', {}, headers={'Host': 'invalid.example'})[0], 403)
        self.assertEqual(self.call('state', dict(child_id='child-2'))[0], 400)
        self.assertEqual(self.call('action', self.request(id=other['id'], version=1, action='pause'))[0], 404)
        self.assertEqual(self.http('/api/guided/state', {}, self.first)[0], 403)
        self.assertEqual(self.http('/api/guided/state', {}, parent=True)[0], 200)
        self.assertEqual(self.http('/api/guided/action', self.request(child_id='child-1', id=row['id'], version=1, action='attempt'), parent=True)[0], 403)
        self.assertEqual(self.call('action', self.request(id=row['id'], version=1, action='share'))[0], 403)
        self.assertEqual(self.call('action', self.request(id=row['id'], version=1, action='hint', reference_text='forged'))[0], 400)
        self.assertEqual(self.http('/child/upload/' + image, session=self.first)[0], 200)
        self.assertEqual(self.http('/child/upload/' + image, session=self.second)[0], 403)
        self.assertEqual(self.child_action(row['id'], 'attempt', kind='first', text='', attachments=[image])[0][0], 403)
        self.assertEqual(self.http('/api/record', dict(child='示例乙', day='2026-09-09', category='学习进展', title='跨孩原件', attachments=[image]), parent=True)[0], 400)
        self.parent_action(row['id'], 'unshare', note='PARENT_UNSHARE_PRIVATE_CANARY')
        self.assertEqual(self.http('/child/upload/' + image, session=self.first)[0], 403)
        self.assertEqual(self.child_action(row['id'], 'pause')[0][0], 403)
        self.assertEqual(self.call('state', {})[1]['sessions'], [])
        self.parent_action(row['id'], 'share')
        self.assertNotIn('PARENT_UNSHARE_PRIVATE_CANARY', json.dumps(self.call('state', {})[1]))
        edit = self.request(id=row['id'], version=self.row(row['id'])['version'], child_id='child-1', title='换一道题', question_text='新题')
        self.assertEqual(self.http('/api/guided/material', edit, parent=True)[0], 409)
        draft = self.material(title='未分享草稿', shared=False)
        update = self.request(id=draft['id'], version=draft['version'], child_id='child-1', title='核对后的草稿', shared=False)
        self.assertEqual(self.http('/api/guided/material', update, parent=True)[0], 200)
        self.assertEqual(self.http('/api/guided/material', update, parent=True)[0], 200)
        self.assertEqual(self.http('/api/guided/material', update | dict(title='改了内容'), parent=True)[0], 409)
        for changed in (dict(reference_checked='yes'), dict(shared=1), dict(question_text='x' * 4001), dict(related_record_id=True), dict(child_id='missing'), dict(reference_attachments=[])):
            payload = self.request(child_id='child-1', title='虚构坏输入') | changed
            self.assertIn(self.http('/api/guided/material', payload, parent=True)[0], (400, 404))

    def test_missing_material_offline_and_nonimage_originals_keep_attempts(self):
        pdf = self.upload('application/pdf')
        missing = self.material(title='缺参考和题目', question_text='', reference_text='', reference_checked=False)
        self.assertEqual(self.child_action(missing['id'], 'attempt', kind='first', text='我还没拿到题目。')[0][0], 200)
        self.assertEqual(self.child_action(missing['id'], 'hint')[0][0], 409)
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(self.child_action(missing['id'], 'skip', note='先等家长补充')[0][0], 200)
        pdf_question = self.material(title='PDF原题暂不可读', question_text='', question_attachments=[pdf])
        self.assertTrue(self.row(pdf_question['id'])['material_gaps'])
        self.child_action(pdf_question['id'], 'attempt', kind='first', text='我不知道从哪里开始。')
        self.assertEqual(self.child_action(pdf_question['id'], 'hint')[0][0], 409)
        textual = self.material(title='文字为已核对摘录', question_attachments=[pdf])
        self.child_action(textual['id'], 'attempt', kind='first', text='先读已知条件。')
        self.assertEqual(self.child_action(textual['id'], 'hint')[0][0], 200)
        self.assertIn('1 份原件未读取', self.calls[-1][0]['question_text'])
        with patch.object(family_llm, 'guided_hint', side_effect=family_llm.LLMDraftError('PRIVATE_MODEL_ERROR')):
            failed, payload = self.child_action(textual['id'], 'hint')
            self.assertEqual(failed[0], 200)
            self.assertEqual(failed[1]['sessions'][0]['events'][-1]['status'], 'failed')
            self.assertNotIn('PRIVATE_MODEL_ERROR', json.dumps(failed))
            self.assertEqual(self.call('action', payload)[0], 200)
        self.assertEqual(self.child_action(textual['id'], 'attempt', kind='explain_again', text='模型离线也继续保留自己的思路。')[0][0], 200)
        with patch.object(family_llm, 'guided_hint', return_value=dict(hint='x', question='', uncertainties=[], mastery=True)):
            self.assertEqual(self.child_action(textual['id'], 'hint')[0][1]['sessions'][0]['events'][-1]['status'], 'failed')
        own = self.upload(child='child-1')
        photo = self.material(title='图片与自述用途区分', question_attachments=[self.upload()])
        self.child_action(photo['id'], 'attempt', kind='first', text='', attachments=[own])
        self.assertEqual(self.child_action(photo['id'], 'hint')[0][0], 200)
        self.assertEqual([p['label'] for p in self.calls[-1][3]], ['题目原件', '首次尝试原件'])

    def test_pending_does_not_lock_pause_and_old_response_cannot_advance(self):
        row = self.material()
        self.child_action(row['id'], 'attempt', kind='first', text='先看看题目。')
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return dict(hint='STALE_HINT_PRIVATE_CANARY', question='', uncertainties=[])
        with patch.object(family_llm, 'guided_hint', side_effect=slow), ThreadPoolExecutor(max_workers=1) as pool:
            payload = self.request(id=row['id'], version=self.row(row['id'])['version'], action='hint')
            future = pool.submit(self.call, 'action', payload)
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.call('action', payload)[0], 200)
            pending = self.row(row['id'])
            self.assertEqual(pending['version'], payload['version'])
            self.assertEqual(pending['events'][-1]['status'], 'pending')
            pause = self.request(id=row['id'], version=payload['version'], action='pause', note='需要家长帮助')
            self.assertEqual(self.call('action', pause)[0], 200)
            release.set()
            result = future.result()
            self.assertEqual(result[0], 200)
            self.assertNotIn('STALE_HINT_PRIVATE_CANARY', json.dumps(result))
            self.assertEqual(self.row(row['id'])['state'], 'paused')
            self.assertEqual(self.row(row['id'])['version'], payload['version'] + 1)
        self.assertEqual(self.child_action(row['id'], 'resume')[0][0], 200)
        self.assertEqual(self.child_action(row['id'], 'hint')[0][0], 200)

    def test_revoke_during_model_and_stale_receipt_preserves_new_pending(self):
        row = self.material()
        self.child_action(row['id'], 'attempt', kind='first', text='先比较两种棋子。')
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        count = [0]
        def slow(*args, **kwargs):
            index = count[0]
            count[0] += 1
            entered[index].set()
            self.assertTrue(release[index].wait(5))
            return dict(hint='虚构有效提示' if index else 'OLD_SESSION_PRIVATE_CANARY', question='', uncertainties=[])
        with patch.object(family_llm, 'guided_hint', side_effect=slow), ThreadPoolExecutor(max_workers=2) as pool:
            payload = self.request(id=row['id'], version=self.row(row['id'])['version'], action='hint')
            first = pool.submit(self.call, 'action', payload)
            self.assertTrue(entered[0].wait(5))
            family_child.parent_action(app, 'revoke', dict(child_id='child-1'))
            self.parent_action(row['id'], 'pause')
            self.parent_action(row['id'], 'resume')
            self.first = self.login('child-1')
            second_payload = self.request(id=row['id'], version=self.row(row['id'])['version'], action='hint')
            second = pool.submit(self.call, 'action', second_payload)
            self.assertTrue(entered[1].wait(5))
            release[0].set()
            self.assertEqual(first.result()[0], 401)
            self.assertEqual(self.row(row['id'])['events'][-1]['status'], 'pending')
            release[1].set()
            self.assertEqual(second.result()[0], 200)
        self.assertNotIn('OLD_SESSION_PRIVATE_CANARY', json.dumps(self.row(row['id'])))
        self.assertEqual(self.row(row['id'])['events'][-1]['hint'], '虚构有效提示')

    def test_expired_request_can_retry_without_old_reply_cancelling_new_hint(self):
        row = self.material()
        self.child_action(row['id'], 'attempt', kind='first', text='  我的原话保留空白。\n')
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT note FROM records').fetchone()[0], '  我的原话保留空白。\n')
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        count = [0]
        def slow(*args, **kwargs):
            index = count[0]
            count[0] += 1
            entered[index].set()
            self.assertTrue(release[index].wait(5))
            return dict(hint='新的提示' if index else 'OLD_EXPIRED_PRIVATE_CANARY', question='', uncertainties=[])
        with patch.object(family_llm, 'guided_hint', side_effect=slow), ThreadPoolExecutor(max_workers=2) as pool:
            payload = self.request(id=row['id'], version=self.row(row['id'])['version'], action='hint')
            first = pool.submit(self.call, 'action', payload)
            self.assertTrue(entered[0].wait(5))
            with app.connect() as c:
                c.execute("UPDATE guided_events SET expires=0 WHERE session_id=? AND kind='hint'", (row['id'],))
            receipt = self.call('action', payload)
            self.assertEqual(receipt[0], 200)
            self.assertEqual(receipt[1]['sessions'][0]['events'][-1]['status'], 'stale')
            second = pool.submit(self.call, 'action', payload | dict(request_key='fictional-guided-new-after-expiry'))
            self.assertTrue(entered[1].wait(5))
            release[0].set()
            self.assertEqual(first.result()[0], 200)
            self.assertEqual(self.row(row['id'])['events'][-1]['status'], 'pending')
            release[1].set()
            self.assertEqual(second.result()[0], 200)
        self.assertNotIn('OLD_EXPIRED_PRIVATE_CANARY', json.dumps(self.row(row['id'])))
        self.assertEqual(self.row(row['id'])['events'][-1]['hint'], '新的提示')

    def test_revocation_between_http_lookup_and_write_and_record_hash(self):
        row = self.material()
        entered, release = threading.Event(), threading.Event()
        original = family_guided.Store.action
        def delayed(store, payload):
            if store.authorize:
                entered.set()
                self.assertTrue(release.wait(5))
            return original(store, payload)
        with patch.object(family_guided.Store, 'action', delayed), ThreadPoolExecutor(max_workers=1) as pool:
            payload = self.request(id=row['id'], version=row['version'], action='attempt', kind='first', text='不应写入的撤销后表达')
            future = pool.submit(self.call, 'action', payload)
            self.assertTrue(entered.wait(5))
            self.parent_action(row['id'], 'unshare')
            release.set()
            self.assertEqual(future.result()[0], 403)
        self.assertFalse(any(e['kind'] == 'attempt' for e in self.row(row['id'])['events']))
        self.parent_action(row['id'], 'share')
        self.child_action(row['id'], 'attempt', kind='first', text='原始表达')
        record = next(e['record_id'] for e in self.row(row['id'])['events'] if e['kind'] == 'attempt')
        with app.connect() as c:
            c.execute('UPDATE records SET note=? WHERE id=?', ('OUTSIDE_PARENT_NOTE_PRIVATE_CANARY', record))
        self.assertEqual(self.child_action(row['id'], 'hint')[0][0], 409)
        self.assertEqual(self.child_action(row['id'], 'attempt', kind='explain_again', text='不得覆盖')[0][0], 409)
        self.assertNotIn('OUTSIDE_PARENT_NOTE_PRIVATE_CANARY', json.dumps(self.call('state', {})[1]))

    def test_profile_rename_and_whole_database_restore(self):
        row = self.material()
        self.child_action(row['id'], 'attempt', kind='first', text='保留真实表达，帮助情况未知。')
        app.save_profile(dict(child_id='child-1', version=0, name='示例新称呼', grade='四年级', classroom='', reason='虚构称呼更正'))
        self.assertEqual(self.child_action(row['id'], 'attempt', kind='explain_again', text='同一个孩子再次解释。')[0][0], 200)
        with app.connect() as c:
            expected = [tuple(r) for r in c.execute('SELECT * FROM guided_events ORDER BY id')]
        archive = family_backup.create(self.root, 'private/backups/guided.zip')
        restored = family_backup.restore(archive, self.root / 'restored')
        with patch.multiple(app, ROOT=restored, DATA=restored / 'private', DB=restored / 'private/family.sqlite3'):
            snapshot = family_guided.Store(app).snapshot()
            self.assertEqual(snapshot['sessions'][0]['id'], row['id'])
            with app.connect() as c:
                self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM guided_events ORDER BY id')], expected)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM child_sessions').fetchone()[0], 0)

    def test_manual_plan_privacy_attempt_anchor_and_no_invented_help(self):
        row = self.material(reference_text='', reference_checked=False)
        self.assertIsNone(row['plan']); self.assertIsNone(row['plan_draft'])
        self.parent_action(row['id'], 'guide_save', plan=self.plan(), share_goal=False)
        plan = self.row(row['id'])['plan']
        self.assertEqual(plan['source'], 'parent')
        child = self.call('state', {})[1]['sessions'][0]
        self.assertIsNone(child['learning_goal'])
        self.assertFalse(any(e['kind'] in ('guide_draft', 'guide_plan') for e in child['events']))
        with app.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
        self.parent_action(row['id'], 'guide_save', plan=self.plan(), share_goal=True)
        first_plan = self.row(row['id'])['plan']
        child = self.call('state', {})[1]['sessions'][0]
        self.assertEqual(child['learning_goal'], {k: first_plan[k] for k in ('goal', 'success_criteria')} | dict(plan_event_id=first_plan['id']))
        self.assertNotIn('PRIVATE_CANARY', json.dumps(child))
        self.child_action(row['id'], 'attempt', kind='first', text='我先表示两种颜色。')
        self.parent_action(row['id'], 'guide_save', plan=self.plan(goal='另一个明确核对的目标'), share_goal=False)
        second_plan = self.row(row['id'])['plan']
        self.child_action(row['id'], 'attempt', kind='explain_again', text='再次说清我的理由。')
        attempts = [e for e in self.row(row['id'])['events'] if e['kind'] == 'attempt']
        self.assertEqual([e['plan_event_id'] for e in attempts], [first_plan['id'], second_plan['id']])
        self.assertIsNone(self.call('state', {})[1]['sessions'][0]['learning_goal'])
        with app.connect() as c:
            self.assertTrue(all('已提供 0 条系统提示' in r[0] for r in c.execute('SELECT comparison_note FROM records')))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reading_awards').fetchone()[0], 0)

    def test_proposal_zero_attempt_confirmation_and_lost_receipts(self):
        row = self.material()
        payload = self.request(child_id='child-1', id=row['id'], version=row['version'], action='guide_draft',
                               goal='家长明确的加法目标', success_criteria='')
        with patch.object(family_llm, 'guided_plan', return_value=dict(plan=self.plan(), uncertainties=[])) as model:
            self.assertEqual(self.http('/api/guided/action', payload, parent=True)[0], 200)
            model.assert_called_once()
            self.assertEqual(model.call_args.args[1], [])
            self.assertNotIn('GROUP_PRIVATE_CANARY', str(model.call_args))
            draft = self.row(row['id'])['plan_draft']
            self.assertEqual(draft['status'], 'ready')
            self.assertEqual(draft['goal_source'], 'parent')
            self.assertEqual(draft['success_criteria_source'], 'proposal')
            self.assertEqual(draft['plan']['goal'], payload['goal'])
            self.assertIsNone(self.row(row['id'])['plan'])
            child = self.call('state', {})[1]['sessions'][0]
            self.assertIsNone(child['learning_goal'])
            self.assertNotIn('guide_draft', json.dumps(child))
            self.assertEqual(self.http('/api/guided/action', payload, parent=True)[0], 200)
            model.assert_called_once()
            self.assertEqual(self.http('/api/guided/action', payload | dict(goal='不同请求'), parent=True)[0], 409)
        save = self.request(child_id='child-1', id=row['id'], version=self.row(row['id'])['version'], action='guide_save',
                            based_on_draft_id=draft['id'], share_goal=True, plan=draft['plan'] | dict(goal='家长修改后确认的目标'))
        self.assertEqual(self.http('/api/guided/action', save, parent=True)[0], 200)
        self.assertEqual(self.http('/api/guided/action', save, parent=True)[0], 200)
        current = self.row(row['id'])
        self.assertEqual(current['plan']['source'], 'model_reviewed')
        self.assertIsNone(current['plan_draft'])
        self.assertEqual(len([e for e in current['events'] if e['kind'] == 'guide_plan']), 1)
        self.child_action(row['id'], 'attempt', kind='first', text='我先说自己的思路。')
        with patch.object(family_llm, 'guided_hint', return_value=dict(hint='虚构小提示', question='', uncertainties=[])) as model:
            self.assertEqual(self.child_action(row['id'], 'hint')[0][0], 200)
            self.assertEqual(model.call_args.kwargs['learning_goal']['goal'], '家长修改后确认的目标')
            self.assertNotIn('PARENT_GUIDE_PRIVATE_CANARY', str(model.call_args))

    def test_guide_http_permissions_shapes_cross_session_and_stale_context(self):
        row = self.material()
        payload = self.request(id=row['id'], version=row['version'], child_id='child-1', action='guide_save', plan=self.plan(), share_goal=True)
        self.assertEqual(self.http('/api/guided/action', payload)[0], 403)
        self.assertEqual(self.http('/api/guided/action', payload, parent=True, headers={'Host':'untrusted.invalid'})[0], 403)
        self.assertEqual(self.call('action', {k:v for k,v in payload.items() if k != 'child_id'})[0], 400)
        self.assertEqual(self.http('/api/guided/action', payload | dict(child_id='child-2'), parent=True)[0], 404)
        for change in [dict(share_goal=1),dict(plan=self.plan(goal='')),dict(plan=self.plan(success_criteria='')),
                       dict(plan=self.plan(goal='x'*301)),dict(plan=self.plan(extra='forged')),
                       dict(based_on_draft_id=True),dict(based_on_draft_id=999999),dict(source='parent')]:
            self.assertIn(self.http('/api/guided/action', payload | change, parent=True)[0], (400,409))
        with patch.object(family_llm, 'guided_plan', return_value=dict(plan=self.plan(), uncertainties=[])):
            self.parent_action(row['id'], 'guide_draft', goal='', success_criteria='')
            draft = self.row(row['id'])['plan_draft']
            other = self.material(child_id='child-2', title='另一孩子的题目')
            with self.assertRaises(family_guided.GuidedError):
                self.parent_action(other['id'], 'guide_save', based_on_draft_id=draft['id'], share_goal=True, plan=self.plan())
            self.child_action(row['id'], 'attempt', kind='first', text='孩子新增的事实优先保留。')
            self.assertEqual(self.row(row['id'])['plan_draft']['status'], 'stale')
            with self.assertRaises(family_guided.GuidedError):
                self.parent_action(row['id'], 'guide_save', based_on_draft_id=draft['id'], share_goal=True, plan=self.plan())
        self.assertIsNone(self.row(row['id'])['plan'])
        self.parent_action(row['id'], 'close')
        with self.assertRaises(family_guided.GuidedError): self.parent_action(row['id'], 'guide_save', plan=self.plan(), share_goal=False)

    def test_pending_guide_allows_child_attempt_and_unshare_discards_late_reply(self):
        row = self.material()
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            entered.set(); self.assertTrue(release.wait(5))
            return dict(plan=self.plan(start='LATE_GUIDE_PRIVATE_CANARY'), uncertainties=[])
        with patch.object(family_llm, 'guided_plan', side_effect=slow), ThreadPoolExecutor(max_workers=1) as pool:
            payload = self.request(child_id='child-1', id=row['id'], version=row['version'], action='guide_draft', goal='', success_criteria='')
            pending = pool.submit(self.http, '/api/guided/action', payload, parent=True)
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.row(row['id'])['version'], row['version'])
            self.assertEqual(self.row(row['id'])['plan_draft']['status'], 'pending')
            self.assertEqual(self.http('/api/guided/action', payload, parent=True)[0], 200)
            self.assertEqual(self.child_action(row['id'], 'attempt', kind='first', text='生成指南时也能保存自己的表达。')[0][0], 200)
            self.parent_action(row['id'], 'unshare')
            release.set()
            self.assertEqual(pending.result()[0], 200)
        self.assertEqual(self.row(row['id'])['plan_draft']['status'], 'stale')
        self.assertNotIn('LATE_GUIDE_PRIVATE_CANARY', json.dumps(self.store.snapshot()))
        self.assertEqual(self.call('state', {})[1]['sessions'], [])

    def test_confirming_plan_invalidates_pending_hint_without_counting_as_help(self):
        row = self.material()
        self.child_action(row['id'], 'attempt', kind='first', text='先自己想一想。')
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            entered.set(); self.assertTrue(release.wait(5))
            return dict(hint='OLD_PLAN_HINT_PRIVATE_CANARY', question='', uncertainties=[])
        with patch.object(family_llm, 'guided_hint', side_effect=slow), ThreadPoolExecutor(max_workers=1) as pool:
            payload = self.request(id=row['id'], version=self.row(row['id'])['version'], action='hint')
            pending = pool.submit(self.call, 'action', payload)
            self.assertTrue(entered.wait(5))
            self.parent_action(row['id'], 'guide_save', plan=self.plan(), share_goal=True)
            release.set(); self.assertEqual(pending.result()[0], 200)
        self.assertNotIn('OLD_PLAN_HINT_PRIVATE_CANARY', json.dumps(self.store.snapshot()))
        self.assertEqual([e['status'] for e in self.row(row['id'])['events'] if e['kind']=='hint'], ['stale'])
        self.child_action(row['id'], 'attempt', kind='explain_again', text='继续自己表达。')
        with app.connect() as c:
            self.assertIn('已提供 0 条系统提示', c.execute('SELECT comparison_note FROM records ORDER BY id DESC LIMIT 1').fetchone()[0])

    def test_expired_guide_receipt_cannot_invalidate_new_pending_request(self):
        row = self.material()
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        count = [0]
        def slow(*args, **kwargs):
            index = count[0]; count[0] += 1
            entered[index].set(); self.assertTrue(release[index].wait(5))
            return dict(plan=self.plan(start='旧草稿不得采用' if index == 0 else '新的可核对草稿'), uncertainties=[])
        with patch.object(family_llm, 'guided_plan', side_effect=slow), ThreadPoolExecutor(max_workers=2) as pool:
            payload = self.request(child_id='child-1', id=row['id'], version=row['version'], action='guide_draft', goal='', success_criteria='')
            first = pool.submit(self.http, '/api/guided/action', payload, parent=True)
            self.assertTrue(entered[0].wait(5))
            with app.connect() as c:
                c.execute("UPDATE guided_events SET expires=0 WHERE session_id=? AND kind='guide_draft'", (row['id'],))
            self.assertEqual(self.http('/api/guided/action', payload, parent=True)[0], 200)
            self.assertEqual(self.row(row['id'])['plan_draft']['status'], 'stale')
            second = pool.submit(self.http, '/api/guided/action', payload | dict(request_key='fictional-new-guide-after-expiry'), parent=True)
            self.assertTrue(entered[1].wait(5))
            release[0].set(); self.assertEqual(first.result()[0], 200)
            self.assertEqual(self.row(row['id'])['plan_draft']['status'], 'pending')
            release[1].set(); self.assertEqual(second.result()[0], 200)
        self.assertEqual(self.row(row['id'])['plan_draft']['plan']['start'], '新的可核对草稿')
        self.assertNotIn('旧草稿不得采用', json.dumps(self.store.snapshot()))

    def test_material_edit_immediately_releases_old_guide_pending_gate(self):
        row = self.material(shared=False)
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        count = [0]
        def slow(*args, **kwargs):
            index = count[0]; count[0] += 1
            entered[index].set(); self.assertTrue(release[index].wait(5))
            return dict(plan=self.plan(start='旧题草稿不得采用' if index == 0 else '新题的教学草稿'), uncertainties=[])
        with patch.object(family_llm, 'guided_plan', side_effect=slow), ThreadPoolExecutor(max_workers=2) as pool:
            payload = self.request(child_id='child-1', id=row['id'], version=row['version'], action='guide_draft', goal='', success_criteria='')
            first = pool.submit(self.http, '/api/guided/action', payload, parent=True)
            self.assertTrue(entered[0].wait(5))
            edit = self.request(child_id='child-1', id=row['id'], version=row['version'], title='修改后的虚构原题',
                                question_text='3+4=?', reference_text='7', reference_checked=True, shared=False)
            self.assertEqual(self.http('/api/guided/material', edit, parent=True)[0], 200)
            self.assertEqual(self.row(row['id'])['plan_draft']['status'], 'stale')
            fresh = payload | dict(request_key='fictional-guide-after-material-edit', version=self.row(row['id'])['version'])
            second = pool.submit(self.http, '/api/guided/action', fresh, parent=True)
            self.assertTrue(entered[1].wait(5), 'new draft must start immediately, without waiting for old model or expiry')
            release[0].set(); self.assertEqual(first.result()[0], 200)
            self.assertEqual(self.row(row['id'])['plan_draft']['status'], 'pending')
            release[1].set(); self.assertEqual(second.result()[0], 200)
        self.assertEqual(self.row(row['id'])['plan_draft']['plan']['start'], '新题的教学草稿')
        self.assertNotIn('旧题草稿不得采用', json.dumps(self.store.snapshot()))

    def test_offline_manual_fallback_material_receipt_and_unshared_material_change(self):
        payload = self.request(child_id='child-1', version=0, title='相同虚构名称', question_text='2+3=?', reference_text='5', reference_checked=True, shared=False)
        first = self.store.save_material(payload)
        second = self.store.save_material(payload | dict(request_key='fictional-distinct-material-key'))
        self.assertNotEqual(first['session_id'], second['session_id'])
        self.assertEqual(self.store.save_material(payload)['session_id'], first['session_id'])
        ident = first['session_id']
        with patch.object(family_llm, 'guided_plan', side_effect=family_llm.LLMDraftError('PRIVATE_FAILURE_CANARY')):
            self.parent_action(ident, 'guide_draft', goal='', success_criteria='')
        self.assertEqual(self.row(ident)['plan_draft']['status'], 'failed')
        self.assertNotIn('PRIVATE_FAILURE_CANARY', json.dumps(self.store.snapshot()))
        self.parent_action(ident, 'guide_save', plan=self.plan(start='',ask='',help='',stop='',retry=''), share_goal=False)
        self.assertIsNotNone(self.row(ident)['plan'])
        change = payload | dict(id=ident,version=self.row(ident)['version'],request_key='fictional-material-edit-key',question_text='3+4=?',reference_text='7')
        self.store.save_material(change)
        self.assertIsNone(self.row(ident)['plan'])
        # Existing SQLite backup includes plans and receipts without schema changes.
        self.parent_action(ident, 'guide_save', plan=self.plan(), share_goal=True)
        expected = self.row(ident)['plan']
        archive = family_backup.create(self.root, 'private/backups/guide-plan.zip')
        restored = family_backup.restore(archive, self.root/'restored-plan')
        with patch.multiple(app,ROOT=restored,DATA=restored/'private',DB=restored/'private/family.sqlite3'):
            rows = family_guided.Store(app).snapshot()['sessions']
            self.assertEqual(next(r for r in rows if r['id']==ident)['plan'],expected)


if __name__ == '__main__':
    unittest.main()

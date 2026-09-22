"""Synthetic check: parent-saved page fragments feed the existing pending school candidate's purpose review.
No family data, network or real model; every model reply is a fixture and the page fetch is always fake."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import family_agent as agent
import family_llm
import family_review

LINK = 'https://school.example.invalid/notice/2026-02'
OTHER = 'https://school.example.invalid/other'
TEXT = '请查看 ' + LINK
PAGE = '英语：本周朗读第3课课文三遍，家长录音后上传到班级群打卡。'
PLAIN = '语文：完成虚构习作一篇。'
FETCHED = '2026-02-10T08:10:00+08:00'


def page(url=LINK, text=PAGE, truncated=False):
    return dict(url=url, text=text, text_truncated=truncated, content_type='text/html', fetched_at=FETCHED)


def draft(**changes):
    return dict(dict(title='英语：朗读第3课课文三遍', goal='朗读第3课课文三遍。', advice='', state='ready', reason='页面写明朗读要求。',
                     purpose='learning', submission='录音上传到班级群打卡', change='new', target_id=''), **changes)


class SchoolPageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-page-evidence-'); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve(); self.data = root / 'private'; self.data.mkdir()
        (root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 11岁 | 五年级 |\n')
        self.app = family_review.load_app(root, self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data)
        self.now = dt.datetime(2026, 2, 10, 8, tzinfo=agent.TZ)
        self.source = dict(id='wechat:12345@chatroom', platform='wechat', child_id='child-1', name='虚构班级', cursor='10', enabled=True)
        self.config(); self.cursor = 10

    def config(self, enabled=True, source_enabled=True):
        (self.data / 'agent.json').write_text(json.dumps({'enabled': enabled, 'sources': [dict(self.source, enabled=source_enabled)]}))

    def ingest(self, ident, text=TEXT):
        message = dict(id=ident, time=self.now.isoformat(), kind='text', sender='虚构老师', text=text, unread=False)
        self.store.ingest(dict(source_id=self.source['id'], expected_cursor=str(self.cursor), cursor=str(self.cursor + 1),
                               checked_at=message['time'], last_message_time=message['time'], error='', messages=[message]))
        self.cursor += 1
        return message

    def candidate(self, ident, text=TEXT, brief=None):
        """A pending school candidate as the batch selection saved it: current policy, link-only, unread page."""
        self.ingest(ident, text)
        if brief is None:
            brief = dict(title='', goal='', advice='', state='review', reason='只有链接或短链，页面未读取，用途和内容待核对；请打开原链接核对后再填写具体要求。',
                         policy=agent.SCHOOL_TASK_POLICY, change='new', target_id='', purpose='unknown', links=[LINK], link_read=False)
        item = dict(child_id='child-1', kind='school', title='待核对：' + text[:20], body='学校', due='',
                    evidence=[dict(ref='message:%s:%s' % (self.source['id'], ident), text=text)],
                    plan=dict(school_task=brief, school_messages=[dict(source_id=self.source['id'], message_id=ident)]))
        key = 'synthetic-page:' + ident; self.store._save(key, self.store._job(key, ident, self.now), [item], self.now)
        with self.app.connect() as c:
            return c.execute('SELECT id FROM agent_items WHERE job_id=?', (key,)).fetchone()[0]

    def save_page(self, ident='1', **changes):
        keys = dict(child_id='child-1', source_id=self.source['id'], message_id=ident, url=LINK)
        return self.store.message_page(keys, lambda row: dict(row), fetch=lambda url: page(url=url, **changes))['page']

    def item(self, ident):
        with self.app.connect() as c:
            return dict(c.execute('SELECT * FROM agent_items WHERE id=?', (ident,)).fetchone())

    def brief(self, ident):
        return json.loads(self.item(ident)['plan']).get('school_task', {})

    def count(self, table):
        with self.app.connect() as c:
            return c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]

    def refresh(self, reply, budget=1, minutes=0):
        calls = []
        def model(messages, *args, **kwargs):
            calls.append(messages)
            if isinstance(reply, Exception): raise reply
            return reply(messages) if callable(reply) else reply
        with patch.object(family_llm, '_chat_json', side_effect=model):
            result = agent._refresh_school(self.app, self.store, self.now + dt.timedelta(minutes=minutes), budget)
        return result, calls

    def test_saved_fragment_reprepares_once_and_stays_for_the_parent(self):
        ident = self.candidate('1'); before = self.brief(ident)
        result, calls = self.refresh(draft())
        self.assertEqual((result['used'], calls, self.brief(ident)), (0, [], before))  # no fragment: the unread draft is untouched
        self.save_page()
        result, calls = self.refresh(draft())
        self.assertEqual((result['used'], result['created'], result['failed'], len(calls)), (1, 0, 0, 1))  # the full reply contract is accepted, nothing failed
        system, user = calls[0][0]['content'], json.loads(calls[0][1]['content'])
        self.assertNotIn('链接页面从未读取', system); self.assertIn(agent.SCHOOL_PAGE_PROMPT, system); self.assertNotIn(PAGE, system)
        self.assertEqual([(p['url'], p['text'], p['text_truncated'], p['fetched_at']) for p in user['pages']], [(LINK, PAGE, False, FETCHED)])
        self.assertEqual((user['evidence'][0]['text'], user['unread_links']), (TEXT, []))  # message text and page text stay separate
        brief = self.brief(ident); row = self.item(ident)
        self.assertEqual((row['state'], row['task_id'] or '', self.count('manual_tasks'), row['title']), ('pending', '', 0, '英语：朗读第3课课文三遍'))
        self.assertEqual((brief['state'], brief['purpose'], brief['link_read']), ('ready', 'learning', True))
        self.assertEqual([(r['url'], r['fetched_at'], r['text_truncated']) for r in brief['page_evidence']['read']], [(LINK, FETCHED, False)])
        self.assertIn(LINK, brief['reason']); self.assertIn('静态文字完整', brief['reason']); self.assertIn('未知', brief['reason'])
        self.assertNotIn('页面未读取', brief['reason']); self.assertIn('提交要求：录音上传到班级群打卡', brief['goal'])
        self.assertTrue(agent._keeps_learning(brief))
        self.save_page()  # cached re-read: same fragment, nothing changes
        result, calls = self.refresh(draft(), minutes=1)
        self.assertEqual((result['used'], calls, self.count('agent_items'), self.count('manual_tasks'), self.item(ident)['state']), (0, [], 1, 0, 'pending'))
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=ident, action='accept', expected_updated=self.item(ident)['updated']), school_auto=True)
        accepted = self.store.act(dict(id=ident, action='accept'))  # the parent accepts once through the ordinary path
        self.assertEqual((accepted['state'], self.count('manual_tasks')), ('accepted', 1))
        accepted_row = self.item(ident); result, calls = self.refresh(draft(), minutes=2)
        self.assertEqual((result['used'], calls, self.count('manual_tasks'), self.item(ident)['state']), (0, [], 1, 'accepted'))
        self.assertEqual(self.item(ident), accepted_row)  # the accepted row is never rewritten by a later round

    def test_one_page_candidate_per_round_budget_and_backoff(self):
        first = self.candidate('1'); second = self.candidate('2'); self.save_page('1'); self.save_page('2')
        before = self.brief(first); result, calls = self.refresh(draft(), budget=0)
        self.assertEqual((result['used'], calls, self.brief(first)), (0, [], before))  # no budget: the whole unread draft is untouched
        result, calls = self.refresh(draft(), budget=3); self.assertEqual((result['used'], len(calls)), (1, 1))
        result, calls = self.refresh(draft(), budget=3, minutes=1); self.assertEqual((result['used'], len(calls)), (1, 1))
        self.assertTrue(self.brief(first).get('page_evidence') and self.brief(second).get('page_evidence'))
        result, calls = self.refresh(draft(), budget=3, minutes=2); self.assertEqual((result['used'], calls), (0, []))
        third = self.candidate('3'); self.save_page('3'); before = self.brief(third)
        result, calls = self.refresh(agent.AgentError('synthetic failure'), minutes=3)
        self.assertEqual((result['used'], result['failed'], len(calls), self.brief(third)), (1, 1, 1, before))  # the old draft stays
        result, calls = self.refresh(draft(), minutes=4); self.assertEqual((result['used'], calls), (0, []))  # inside the backoff window
        result, calls = self.refresh(draft(), minutes=10); self.assertEqual((result['used'], len(calls)), (1, 1))
        self.assertTrue(self.brief(third).get('page_evidence'))
        self.assertEqual((self.count('manual_tasks'), self.count('agent_items')), (0, 3))

    def test_truncated_fragment_and_unread_addresses_keep_review(self):
        ident = self.candidate('1', text=TEXT + ' 另见 ' + OTHER); self.save_page(truncated=True)
        result, calls = self.refresh(draft())
        user = json.loads(calls[0][1]['content'])
        self.assertEqual((user['pages'][0]['text_truncated'], user['unread_links']), (True, [OTHER]))
        brief = self.brief(ident)
        self.assertEqual((brief['state'], brief['link_read'], brief['page_evidence']['unread'], brief['page_evidence']['read'][0]['text_truncated']), ('review', False, [OTHER], True))
        self.assertIn('文字已截断', brief['reason']); self.assertIn('未读取：' + OTHER, brief['reason']); self.assertIn('证据不足', brief['reason'])
        self.assertEqual((self.item(ident)['state'], self.count('manual_tasks')), ('pending', 0))

    def test_model_input_is_bounded_and_omissions_are_declared(self):
        evidence = [dict(ref='message:x:1', text=TEXT, unread=False)]
        fragments = [dict(ref='message:x:1', **page(url=LINK + '/%d' % i, text=chr(0x4e00 + i) * 2500)) for i in range(4)]
        bounded = agent._page_evidence(evidence, fragments)
        self.assertEqual([len(p['text']) for p in bounded['model_pages']], [2500, 2500, 1000])
        self.assertEqual([p['text_truncated'] for p in bounded['model_pages']], [False, False, True])
        self.assertEqual((bounded['omitted'], bounded['unread']), ([LINK + '/3'], [LINK]))
        self.assertNotEqual(bounded['fingerprint'], agent._page_evidence(evidence, fragments[:3])['fingerprint'])  # an unseen fragment still changes the fingerprint
        brief = agent._school_brief(draft(), evidence=evidence, pages=bounded)
        self.assertEqual((brief['state'], brief['page_evidence']['omitted']), ('review', [LINK + '/3']))

    def test_static_text_purposes_are_kept_apart_and_never_claim_unread(self):
        evidence = [dict(ref='message:x:1', text=TEXT, unread=False)]
        pages = agent._page_evidence(evidence, [dict(ref='message:x:1', **page())])
        form = agent._page_evidence(evidence, [dict(ref='message:x:1', **page(text='请各位家长在本页填写虚构信息表。'))])
        learning = agent._school_brief(draft(), evidence=evidence, pages=pages)
        self.assertEqual((learning['state'], learning['purpose'], agent._keeps_learning(learning)), ('ready', 'learning', True))
        admin = agent._school_brief(draft(title='填写虚构信息表', goal='在页面填写信息表。', purpose='admin', submission=''), evidence=evidence, pages=form)
        self.assertEqual((admin['state'], admin['purpose'], agent._keeps_learning(admin)), ('ready', 'admin', False))
        mixed = agent._school_brief(draft(title='打卡', goal='完成打卡。', purpose='admin', submission=''), evidence=evidence, pages=pages)
        self.assertEqual(mixed['state'], 'review'); self.assertIn('学习活动', mixed['reason'])  # page text mentions reading aloud
        optional = agent._school_brief(draft(purpose='optional', submission=''), evidence=evidence, pages=pages)
        self.assertEqual((optional['state'], agent._keeps_learning(optional)), ('review', False))
        unknown = agent._school_brief(draft(title='', goal='', purpose='unknown', submission='', state='review'), evidence=evidence, pages=pages)
        self.assertEqual((unknown['state'], unknown['title'], agent._keeps_learning(unknown)), ('review', '', False))
        for brief in (learning, admin, mixed, optional, unknown):
            self.assertEqual(brief['page_evidence']['read'][0]['url'], LINK); self.assertIn(LINK, brief['reason']); self.assertNotIn('页面未读取', brief['reason'])
        bare = agent._school_brief(draft(), evidence=evidence)  # no fragment: the existing unread behaviour is unchanged
        self.assertEqual((bare['state'], bare['purpose'], bare['title'], bare['link_read']), ('review', 'unknown', '', False))
        self.assertIn('页面未读取', bare['reason']); self.assertNotIn('page_evidence', bare)
        self.assertIn(agent._PAGE_UNREAD, agent._task_prompt(None)); self.assertNotIn(agent._PAGE_UNREAD, agent._task_prompt(pages))

    def test_corrected_or_revoked_material_never_goes_out_and_inflight_change_discards(self):
        ident = self.candidate('1'); self.save_page(); before = self.brief(ident)
        def correct(messages):
            payload = json.dumps(dict(id='1', time=self.now.isoformat(), kind='text', sender='虚构老师', text=TEXT + '（更正）', unread=False), ensure_ascii=False)
            with self.store._db() as c:
                c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?', (payload, self.source['id'], '1'))
            return draft()
        result, calls = self.refresh(correct)
        self.assertEqual((result['used'], len(calls), self.brief(ident), self.item(ident)['state']), (1, 1, before, 'pending'))  # in-flight correction: dropped
        with self.store._db() as c:
            corrected = json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?', (self.source['id'], '1')).fetchone()['payload'])['text']
        self.assertEqual((result['failed'], corrected), (0, TEXT + '（更正）'))  # the correction really landed; the round was dropped, not failed
        result, calls = self.refresh(draft(), minutes=1)
        self.assertEqual((result['used'], calls), (0, []))  # the corrected message hides the fragment; nothing goes out again
        second = self.candidate('2'); self.save_page('2')
        result, calls = self.refresh(draft(), minutes=2); self.assertTrue(self.brief(second).get('page_evidence'))
        self.config(source_enabled=False)
        result, calls = self.refresh(draft(), minutes=3)
        for messages in calls:
            self.assertNotIn('pages', json.loads(messages[1]['content']))
            for message in messages: self.assertNotIn(PAGE, message['content'])
        self.assertEqual((self.item(second)['state'], self.count('manual_tasks'), self.count('agent_items')), ('pending', 0, 2))

    def test_plain_notice_without_fragment_keeps_automatic_collection(self):
        ident = self.candidate('1', text=PLAIN, brief=dict(title='旧', goal='旧', advice='', state='review', reason='旧策略', policy=1))
        result, calls = self.refresh(dict(title='语文：完成虚构习作', goal='完成虚构习作一篇。', advice='', state='ready', reason='明确要求。', purpose='learning', submission='', change='new', target_id=''))
        self.assertIn(agent._PAGE_UNREAD, calls[0][0]['content']); self.assertNotIn('pages', json.loads(calls[0][1]['content']))
        self.assertEqual((result['used'], result['created'], self.item(ident)['state'], self.count('manual_tasks')), (1, 1, 'accepted', 1))
        self.assertNotIn('page_evidence', self.brief(ident))

    def test_reference_fragment_is_recorded_once_without_model(self):
        text = '请问有哪位家长有语文课本第3页的照片，发我一下 ' + LINK
        ident = self.candidate('1', text=text, brief=dict(title='旧', goal='旧', advice='', state='review', reason='旧策略', policy=1)); self.save_page()
        result, calls = self.refresh(draft()); brief = self.brief(ident)
        self.assertEqual((result['used'], result['failed'], calls, brief['state'], bool(brief['page_evidence']['fingerprint'])), (0, 0, [], 'reference', True))
        row = self.item(ident)
        for minutes in (1, 2):  # the same reference page is never prepared or written again
            result, calls = self.refresh(draft(), minutes=minutes)
            self.assertEqual((result['used'], calls, self.item(ident), self.count('manual_tasks')), (0, [], row, 0))

    def test_inflight_revocation_or_dismissal_discards_the_model_result(self):
        ident = self.candidate('1'); self.save_page(); before = self.brief(ident)
        def revoke(messages): self.config(source_enabled=False); return draft()
        result, calls = self.refresh(revoke)
        self.assertFalse(json.loads((self.data / 'agent.json').read_text())['sources'][0]['enabled'])  # the revocation really happened
        self.assertEqual((result['used'], result['failed'], len(calls), self.brief(ident), self.item(ident)['state']), (1, 0, 1, before, 'pending'))
        self.store.act(dict(id=ident, action='dismiss')); self.config(); second = self.candidate('2'); self.save_page('2')
        def dismiss(messages): self.store.act(dict(id=second, action='dismiss')); return draft()
        result, calls = self.refresh(dismiss, minutes=1)
        self.assertEqual((result['used'], result['failed'], len(calls), self.item(second)['state'], self.count('manual_tasks')), (1, 0, 1, 'dismissed', 0))
        self.assertNotIn('page_evidence', self.brief(second))  # the dismissed row keeps its pre-model draft
        rows = (self.item(ident), self.item(second)); result, calls = self.refresh(draft(), minutes=2)
        self.assertEqual((result['used'], calls, (self.item(ident), self.item(second))), (0, [], rows))  # dismissed rows stay exactly as they were

    def test_page_draft_after_correction_or_revocation_is_stale_and_refused(self):
        ident = self.candidate('1'); self.save_page(); original = self.item(ident)['title']
        self.refresh(draft()); self.assertEqual(self.brief(ident)['state'], 'ready')
        self.config(source_enabled=False)  # revoked after the draft was made
        result, calls = self.refresh(draft(), minutes=1); brief = self.brief(ident)
        self.assertEqual((result['used'], calls, brief['state'], brief['page_evidence']['fingerprint'], brief['reason']), (0, [], 'review', '', agent._PAGE_STALE))
        with self.assertRaises(agent.AgentError) as refused: self.store.act(dict(id=ident, action='accept'))
        self.assertEqual((refused.exception.status, self.item(ident)['state'], self.count('manual_tasks')), (409, 'pending', 0))
        row = self.item(ident); result, calls = self.refresh(draft(), minutes=2)
        self.assertEqual((result['used'], calls, self.item(ident)), (0, [], row))  # marked stale once, never rewritten
        self.config()  # re-authorized: the same fragment is prepared again from the original notice, not from the old draft
        result, calls = self.refresh(draft(), minutes=3); user = json.loads(calls[0][1]['content'])
        self.assertEqual((result['used'], result['failed'], len(calls), user['candidate'], self.brief(ident)['state']), (1, 0, 1, original, 'ready'))
        self.assertNotIn(draft()['title'], json.dumps(user, ensure_ascii=False))
        payload = json.dumps(dict(id='1', time=self.now.isoformat(), kind='text', sender='虚构老师', text='（更正）' + TEXT, unread=False), ensure_ascii=False)
        with self.store._db() as c:
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?', (payload, self.source['id'], '1'))
        result, calls = self.refresh(draft(), minutes=4)  # corrected after the draft: the fragment is hidden the same way
        self.assertEqual((result['used'], calls, self.brief(ident)['state']), (0, [], 'review'))
        with self.assertRaises(agent.AgentError) as refused: self.store.act(dict(id=ident, action='accept', title='手填', body='手填'))
        self.assertEqual((refused.exception.status, self.count('manual_tasks')), (409, 0))
        self.save_page()  # the parent re-reads the corrected message's page: a fresh fragment, the original notice as candidate
        result, calls = self.refresh(draft(), minutes=5)
        self.assertEqual((result['used'], len(calls), json.loads(calls[0][1]['content'])['candidate']), (1, 1, original))
        self.assertEqual((self.item(ident)['state'], self.count('manual_tasks'), self.count('agent_items')), ('pending', 0, 1))


if __name__ == '__main__':
    unittest.main()

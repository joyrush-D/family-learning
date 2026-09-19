"""QQ screenshot import: synthetic only, no desktop or external model access."""
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import family_qq_inbox as inbox
import family_agent as agent
from family_settings import atomic_json
from test_agent_http import AgentHTTPTests
from test_media import png

SOURCE = dict(id='qq:123456', platform='qq', child_id='child-1', name='虚构班级群', cursor='100', enabled=True)


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.case = AgentHTTPTests(); self.case.setUp()
        self.case.source = SOURCE.copy()
        self.case.config = dict(enabled=True, sources=[self.case.source]); self.case.write_config(self.case.config)
        import app
        self.app = app; self.store = app.agent_store(); self.now = agent._now()
        atomic_json(self.store.data/'qq-inbox.json', dict(enabled=True, source_id=SOURCE['id']))
        self.folder = inbox.directory(self.store.data)

    def tearDown(self): self.case.tearDown()

    def run_capture(self, text='虚构班级群\n请打印词汇学案，不需要写。', now=None):
        with patch.object(inbox, 'recognize', return_value=text):
            return inbox.run_one(self.app, self.store, now or self.now)

    def test_import_retry_archive_and_preserve_native_cursor(self):
        path=self.folder/'a.png'; path.write_bytes(png())
        self.assertEqual(self.store.collector_plan()['sources'], [])
        self.assertEqual(len(self.store.collector_plan(fragment=True)['sources']), 1)
        first=self.run_capture(); self.assertEqual(first['inserted'], 1)
        self.assertFalse(path.exists()); self.assertEqual(len(list((self.folder/'已处理').glob('*.png'))), 1)
        path.write_bytes(png()); replay=self.run_capture(); self.assertEqual(replay['inserted'], 0)
        with self.store._db() as c:
            self.assertEqual(c.execute('select cursor from agent_sources').fetchone()[0], '100')
            self.assertEqual(c.execute('select count(*) from agent_messages').fetchone()[0], 1)
            self.assertEqual(c.execute('select count(*) from manual_tasks').fetchone()[0], 0)
            m=json.loads(c.execute('select payload from agent_messages').fetchone()[0])
            self.assertEqual(m['time'], ''); self.assertTrue(m['unread'])
        self.assertEqual(self.run_capture()['state'], 'waiting')

    def test_wrong_group_retained_backoff_does_not_starve_other_files(self):
        bad=self.folder/'a.png'; bad.write_bytes(png())
        self.assertEqual(self.run_capture('另一个群')['state'], 'error'); self.assertTrue(bad.exists())
        (self.folder/'b.png').write_bytes(png())
        self.assertEqual(self.run_capture()['inserted'], 1); self.assertTrue(bad.exists())
        with patch.object(inbox, 'recognize') as ocr:
            self.assertEqual(inbox.run_one(self.app,self.store,self.now)['state'], 'waiting'); ocr.assert_not_called()

    def test_disabled_symlink_and_partial_do_not_import(self):
        (self.folder/'a.partial.png').write_bytes(png())
        self.assertEqual(self.run_capture()['state'], 'waiting')
        (self.folder/'link.png').symlink_to(self.folder/'a.partial.png')
        self.assertEqual(self.run_capture()['state'], 'error')
        atomic_json(self.store.data/'qq-inbox.json',dict(enabled=False,source_id=SOURCE['id']))
        self.assertEqual(self.run_capture()['state'], 'disabled')

    def test_fragment_brief_stays_reviewable_but_other_gaps_stay_empty(self):
        brief=dict(title='打印词汇学案',goal='打印后带校，不用作答',advice='核对页数',state='ready',reason='')
        e=dict(kind='qq_window_fragment',text='请打印词汇学案，不需要写。')
        result=agent._school_brief(brief,incomplete=True,evidence=[e])
        self.assertEqual(result['title'],brief['title']); self.assertEqual(result['state'],'review')
        self.assertEqual(agent._school_brief(brief,incomplete=True,evidence=[dict(kind='image',text='[图片]')])['title'],'')

    def test_agent_tick_uses_screenshot_text_and_only_creates_review(self):
        (self.folder/'a.png').write_bytes(png())
        imported=self.run_capture()
        ref='message:'+SOURCE['id']+':'+imported['message_id']
        proposal=dict(title_quote='请打印词汇学案',focus='school',due='',evidence=[dict(ref=ref)],
            learning_subject='',learning_goal_id='',task_title='打印词汇学案',task_goal='打印后带校，不需要写',
            task_advice='核对原文件',task_state='ready',task_reason='文字可见')
        import family_llm
        with patch.object(family_llm,'_chat_json',return_value={'proposals':[proposal]}) as model:
            result=agent.run_once(self.app)
        self.assertEqual(result['failed'],0)
        self.assertEqual(model.call_count,1)
        self.assertIn('截图本机文字识别',str(model.call_args))
        with self.store._db() as c:
            item=c.execute('select * from agent_items where kind="school"').fetchone()
            self.assertIsNotNone(item); self.assertEqual(item['state'],'pending')
            brief=json.loads(item['plan'])['school_task']
            self.assertEqual(brief['state'],'review');self.assertEqual(brief['title'],'打印词汇学案')
            self.assertEqual(c.execute('select count(*) from manual_tasks').fetchone()[0],0)


if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""The one-off pending cleanup counts first, writes only by run id, and never touches another table.

Every store here is a throwaway copy under a temporary directory; the product's real family database is never opened.
"""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NOW = '2026-11-14T12:00:00+08:00'
ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / 'family_cleanup_pending.py'

SCHEMA = '''
CREATE TABLE agent_items (
  id TEXT PRIMARY KEY, job_id TEXT NOT NULL, child_id TEXT NOT NULL, kind TEXT NOT NULL,
  title TEXT NOT NULL, body TEXT NOT NULL, evidence TEXT NOT NULL, due TEXT NOT NULL,
  care_id TEXT NOT NULL DEFAULT '', record_id INTEGER, state TEXT NOT NULL DEFAULT 'pending',
  created TEXT NOT NULL, updated TEXT NOT NULL, task_id TEXT NOT NULL DEFAULT '',
  plan TEXT NOT NULL DEFAULT '{}');
CREATE TABLE agent_messages (source_id TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
  processed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(source_id,id));
CREATE TABLE agent_message_attachments (source_id TEXT NOT NULL, message_id TEXT NOT NULL,
  upload_id TEXT NOT NULL, PRIMARY KEY(source_id,message_id,upload_id));
CREATE TABLE manual_tasks (id TEXT PRIMARY KEY);
'''


def _brief(title, goal='', **extra):
    value = {'title': title, 'goal': goal, 'state': 'review', 'change': 'new', 'purpose': 'admin'}
    value.update(extra)
    return {'school_task': value}


class CleanupPendingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.db = self.data / 'family.sqlite3'
        c = sqlite3.connect(self.db)
        c.executescript(SCHEMA)
        self.rows = [
            # id, title, created, due, plan, task_id, evidence ref
            ('confirm-fresh', '带水彩笔', '2026-11-14T10:00:00+08:00', '', _brief('带水彩笔', '明天带水彩笔'), '', 'normal'),
            ('hold-old', '待核对：[图片]', '2026-11-12T10:00:00+08:00', '', _brief('待核对：[图片]', ''), '', 'normal'),
            ('ref-row', '成绩说明', '2026-11-14T10:00:00+08:00', '', _brief('成绩说明', '看成绩', state='reference'), '', 'normal'),
            ('noise-row', '群里闲聊', '2026-11-14T10:00:00+08:00', '', _brief('群里闲聊', '收到'), '', 'noise'),
            ('stale-row', '旧提醒', '2026-11-12T10:00:00+08:00', '2026-11-13',
             _brief('旧提醒', '交作业'), '', 'normal'),
            ('future-due', '明天带彩笔', '2026-11-12T10:00:00+08:00', '2026-11-15',
             _brief('明天带彩笔', '明天带彩笔'), '', 'normal'),
            ('protected', '受保护事项', '2026-11-01T10:00:00+08:00', '', _brief('受保护事项', ''), 'task-1', 'normal'),
            ('duplicate-a', '重复事项', '2026-11-14T10:00:00+08:00', '', _brief('重复事项', '做同一件事'), '', 'normal'),
            ('duplicate-b', '重复事项', '2026-11-14T10:00:00+08:00', '', _brief('重复事项', '做同一件事'), '', 'normal'),
        ]
        for ident, title, created, due, plan, task_id, message in self.rows:
            ref = 'message:src-1:' + ident
            evidence = json.dumps([{'ref': ref, 'text': '来源 · 时间\n' + title}])
            c.execute('INSERT INTO agent_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ident, 'job-1', 'child-1', 'school', title, 'body', evidence, due, '', None, 'pending',
                       created, created, task_id, json.dumps(plan)))
            text = '[强][强][强]' if message == 'noise' else ('收到' if message == 'ack' else title)
            sender = '家长小明' if message in ('noise', 'ack') else '林老师'
            payload = json.dumps(dict(id=ident, kind='text', text=text, sender=sender,
                                      time='2026-11-13T10:00:00+08:00', unread=False))
            c.execute('INSERT INTO agent_messages(source_id,id,payload) VALUES (?,?,?)', ('src-1', ident, payload))
        c.execute("INSERT INTO agent_items VALUES ('accepted-1','job-1','child-1','school','已完成','b','[]','','',NULL,'accepted','2026-11-01','2026-11-01','','{}')")
        c.execute("INSERT INTO agent_items VALUES ('dismissed-1','job-1','child-1','school','已忽略','b','[]','','',NULL,'dismissed','2026-11-01','2026-11-01','','{}')")
        c.executemany('INSERT INTO manual_tasks(id) VALUES (?)', [('manual-1',), ('manual-2',)])
        c.commit()
        c.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), '--data', str(self.data), '--now', NOW, *args],
                              cwd=str(ROOT), capture_output=True, text=True)

    def _dump(self, without_events=False):
        c = sqlite3.connect(self.db)
        lines = list(c.iterdump())
        c.close()
        if without_events:
            lines = [line for line in lines if 'agent_item_events' not in line]
        return lines

    def _states(self):
        c = sqlite3.connect(self.db)
        states = dict(c.execute('SELECT id,state FROM agent_items'))
        c.close()
        return states

    def test_stats_mode_changes_nothing_and_hides_titles_by_default(self):
        before = self._dump()
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._dump(), before)
        self.assertIn('R1 noise', result.stdout)
        self.assertIn('R2 reference', result.stdout)
        self.assertIn('R3 placeholder', result.stdout)
        self.assertIn('R4 stale', result.stdout)
        self.assertIn('R5 duplicate', result.stdout)
        self.assertNotIn('带水彩笔', result.stdout)

    def test_show_titles_prints_the_readable_title(self):
        result = self._run('--show-titles')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('带水彩笔', result.stdout)

    def test_apply_writes_only_expired_rows_and_one_event_each(self):
        before = self._dump()
        result = self._run('--apply', '--run-id', 'run-1')
        self.assertEqual(result.returncode, 0, result.stderr)
        states = self._states()
        for ident in ('hold-old', 'ref-row', 'noise-row', 'stale-row'):
            self.assertEqual(states[ident], 'expired', ident)
        for ident in ('confirm-fresh', 'future-due', 'protected', 'duplicate-a'):
            self.assertEqual(states[ident], 'pending', ident)
        self.assertEqual(states['duplicate-b'], 'pending')
        self.assertEqual(states['accepted-1'], 'accepted')
        self.assertEqual(states['dismissed-1'], 'dismissed')
        c = sqlite3.connect(self.db)
        events = c.execute('SELECT item_id,actor,before,after,note FROM agent_item_events ORDER BY item_id').fetchall()
        self.assertEqual(len(events), 4, events)
        self.assertEqual({row[0] for row in events}, {'hold-old', 'ref-row', 'noise-row', 'stale-row'})
        self.assertTrue(all(row[1] == 'script:run-1' and row[2] == 'pending' and row[3] == 'expired' for row in events))
        self.assertEqual({row[4] for row in events}, {'noise', 'reference', 'placeholder', 'stale'})
        self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 2)
        c.close()
        # The write changed no other table: the only new statements are the expired state and the event rows.
        after = self._dump()
        changed = [line for line in after if line not in before]
        self.assertTrue(changed)
        self.assertTrue(all('agent_item_events' in line or 'expired' in line for line in changed), changed)

    def test_undo_restores_only_this_run_and_keeps_the_events(self):
        before = self._dump(without_events=True)
        result = self._run('--apply', '--run-id', 'run-2')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self._run('--undo', 'run-2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('restored=4', result.stdout)
        self.assertEqual(self._dump(without_events=True), before)
        states = self._states()
        for ident in ('hold-old', 'ref-row', 'noise-row', 'stale-row'):
            self.assertEqual(states[ident], 'pending', ident)
        c = sqlite3.connect(self.db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_item_events WHERE actor='script:run-2'").fetchone()[0], 4)
        c.close()

    def test_a_run_id_can_not_be_reused(self):
        self.assertEqual(self._run('--apply', '--run-id', 'run-3').returncode, 0)
        result = self._run('--apply', '--run-id', 'run-3')
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()

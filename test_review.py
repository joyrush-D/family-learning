"""Synthetic local review inspections; no production database or notifications."""
from contextlib import redirect_stdout
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import family_review as review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-review-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'private'
        self.data.mkdir()
        self.db = self.data / 'family.sqlite3'
        self.now = dt.datetime(2026, 2, 10, 8, tzinfo=review.TIMEZONE)
        (self.root / '家庭运行规则.md').write_text(
            '| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        with sqlite3.connect(self.db) as connection:
            connection.executescript('''
                CREATE TABLE profile_aliases (alias TEXT PRIMARY KEY,child_id TEXT);
                CREATE TABLE profile_overrides (child_id TEXT PRIMARY KEY,name TEXT,grade TEXT,classroom TEXT,version INTEGER);
                CREATE TABLE profile_history (child_id TEXT,version INTEGER,previous TEXT,current TEXT,reason TEXT,changed TEXT);
                CREATE TABLE records (id INTEGER PRIMARY KEY,child TEXT,day TEXT,category TEXT,subject TEXT,title TEXT,note TEXT,source TEXT,score REAL,total REAL,created TEXT,attachments TEXT DEFAULT '[]');
            ''')
        self.item = dict(id='synthetic-care-a', child='示例甲', topic='阅读', title='虚构阅读交流',
                         evidence='虚构作品来源；实际理解情况未知。', action='一起谈一个发现。',
                         review_on='2026-02-11', expires_on='2026-02-20')
        self.write_items([self.item])
        self.write_state({})

    def write_items(self, value):
        (self.data / '陪伴建议.json').write_text(json.dumps(value, ensure_ascii=False))

    def write_state(self, value):
        (self.data / '陪伴提醒状态.json').write_text(json.dumps(value, ensure_ascii=False))

    def record(self, ident=1, child='示例甲', note='虚构反馈：暂不考虑可能是另一个人的想法，决定待核对。'):
        with sqlite3.connect(self.db) as connection:
            connection.execute('INSERT INTO records (id,child,day,title,note,source,created) VALUES (?,?,?,?,?,?,?)',
                (ident, child, '2026-02-10', '虚构反馈', note, '陪伴建议:synthetic-care-a', '2026-02-10T08:00:00+08:00'))

    def source_hashes(self):
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in [self.db, self.data / '陪伴建议.json', self.data / '陪伴提醒状态.json'] if path.exists()}

    def run_check(self, now=None):
        before = self.source_hashes()
        load = review.load_app
        original_connect = sqlite3.connect
        def readonly_connection(*args, **kwargs):
            self.assertIs(kwargs.get('uri'), True)
            self.assertTrue(args[0].endswith('?mode=ro'))
            connection = original_connect(*args, **kwargs)
            # Verify the URI itself rejects writes before PRAGMA query_only.
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute('CREATE TABLE forbidden_review_write (id INTEGER)')
            return connection
        def guarded(*args):
            app = load(*args)
            def forbidden(*_args, **_kwargs):
                raise AssertionError('review may not use app.connect/snapshot or external services')
            app.connect = app.snapshot = app.ask_family = app.print_store = forbidden
            return app
        with patch.object(review, 'load_app', guarded), patch.object(review.sqlite3, 'connect', readonly_connection):
            result = review.check(self.root, self.data, now or self.now)
        self.assertEqual(before, self.source_hashes())
        self.assertEqual((self.data / review.REPORT_NAME).stat().st_mode & 0o777, 0o600)
        return result

    def test_due_catchup_repeated_checks_and_full_report(self):
        report, changed = self.run_check()
        self.assertFalse(changed)
        self.assertEqual(report['status'], 'clear')
        report, changed = self.run_check(self.now + dt.timedelta(days=3))
        self.assertTrue(changed)
        self.assertEqual(report['candidates'][0]['reason'], 'due_review')
        self.assertEqual(report['candidates'][0]['execution_status'], 'unknown')
        again, changed = self.run_check(self.now + dt.timedelta(days=4))
        self.assertFalse(changed)
        self.assertEqual(again['fingerprint'], report['fingerprint'])
        self.assertNotEqual(again['checked_at'], report['checked_at'])
        self.assertEqual(again['candidates'], report['candidates'])
        self.assertNotIn('last_notified', again)

    def test_decisions_and_expiry_do_not_infer_or_renew(self):
        self.record()
        report, _ = self.run_check()
        self.assertEqual(report['candidates'][0]['reason'], 'feedback_needs_review')
        self.assertEqual(report['candidates'][0]['review_status'], '')
        self.write_state({'synthetic-care-a': dict(status='declined', last_notified=None)})
        report, changed = self.run_check(self.now + dt.timedelta(days=30))
        self.assertTrue(changed)
        self.assertEqual(report['candidates'][0]['review_status'], 'declined')
        self.assertEqual(report['candidates'][0]['reason'], 'feedback_needs_review')
        self.assertTrue(report['candidates'][0]['action_is_reference_only'])
        self.write_state({'synthetic-care-a': dict(status='deferred', next_review_on='2026-02-15')})
        deferred, _ = self.run_check()
        self.assertEqual(deferred['candidates'][0]['reason'], 'feedback_needs_review')
        self.assertEqual(deferred['candidates'][0]['review_on'], '2026-02-15')
        due, _ = self.run_check(self.now + dt.timedelta(days=5))
        self.assertEqual(due['candidates'][0]['review_on'], '2026-02-15')
        self.assertEqual(due['candidates'][0]['reason'], 'due_review')
        self.write_state({'synthetic-care-a': dict(status='deferred', next_review_on='2026-03-01')})
        expired, _ = self.run_check(self.now + dt.timedelta(days=11))
        candidate = expired['candidates'][0]
        self.assertEqual(candidate['reason'], 'feedback_needs_review')
        self.assertTrue(candidate['expired'])
        self.assertEqual(candidate['review_on'], '2026-03-01')
        self.assertEqual(candidate['expires_on'], '2026-02-20')
        self.write_state({'synthetic-care-a': dict(status='awaiting_parent_feedback', next_review_on='2026-03-01')})
        original, _ = self.run_check(self.now + dt.timedelta(days=1))
        self.assertEqual(original['candidates'][0]['review_on'], self.item['review_on'])
        expired, _ = self.run_check(self.now + dt.timedelta(days=11))
        self.assertEqual(expired['candidates'][0]['reason'], 'expired_needs_revalidation')
        with sqlite3.connect(self.db) as connection:
            connection.execute('DELETE FROM records')
        for state in [dict(status='declined'), dict(status='deferred', next_review_on='2026-03-01')]:
            self.write_state({'synthetic-care-a': state})
            self.assertEqual(self.run_check()[0]['candidates'], [])

    def test_same_child_feedback_edits_and_identity_aliases(self):
        self.record(child='示例乙', note='FICTIONAL_OTHER_CHILD_NOT_FOR_REPORT')
        self.assertEqual(self.run_check()[0]['candidates'], [])
        with sqlite3.connect(self.db) as connection:
            connection.execute('INSERT INTO profile_aliases VALUES (?,?)', ('示例甲旧称', 'child-1'))
        self.record(ident=2, child='示例甲旧称', note='虚构同孩反馈')
        report, _ = self.run_check()
        self.assertEqual(report['candidates'][0]['child_id'], 'child-1')
        self.assertEqual([row['id'] for row in report['candidates'][0]['feedback']], [2])
        self.assertNotIn('FICTIONAL_OTHER_CHILD', json.dumps(report))
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE records SET note='更正后的虚构反馈',attachments='[\"synthetic-photo\"]' WHERE id=2")
        edited, changed = self.run_check()
        self.assertTrue(changed)
        self.assertNotEqual(edited['fingerprint'], report['fingerprint'])
        self.assertEqual(edited['candidates'][0]['feedback'][0]['attachment_ids'], ['synthetic-photo'])
        self.assertFalse(edited['candidates'][0]['feedback'][0]['attachment_content_read'])

    def test_bad_state_fails_closed_retains_pending_and_recovers(self):
        self.record()
        valid, _ = self.run_check()
        for broken in ['{broken', '[]', '{"synthetic-care-a":{"status":"deferred","next_review_on":"not-a-date"}}']:
            (self.data / '陪伴提醒状态.json').write_text(broken)
            invalid, _ = self.run_check()
            self.assertEqual(invalid['status'], 'needs_review')
            self.assertEqual(invalid['candidate_coverage'], 'current_inputs_unavailable')
            self.assertEqual(invalid['candidates'], valid['candidates'])
            self.assertTrue(invalid['errors'])
            self.assertFalse(self.run_check()[1])
        self.write_state({})
        restored, changed = self.run_check()
        self.assertTrue(changed)
        self.assertEqual(restored['errors'], [])
        self.assertEqual(restored['candidate_coverage'], 'current_inputs_verified')

    def test_database_failure_and_checkpoint_corruption_are_not_clear(self):
        self.record()
        good, _ = self.run_check()
        with patch.object(review, 'read_candidates', side_effect=sqlite3.OperationalError('synthetic failure')):
            failed, changed = self.run_check()
        self.assertTrue(changed)
        self.assertEqual(failed['candidates'], good['candidates'])
        self.assertEqual(failed['errors'][0]['code'], 'family_inputs_unavailable')
        (self.data / review.REPORT_NAME).write_text('{broken')
        rebuilt, changed = self.run_check()
        self.assertTrue(changed)
        self.assertEqual(rebuilt['errors'][0]['code'], 'previous_report_unverified')
        self.assertEqual(rebuilt['candidates'], good['candidates'])
        previous = (self.data / review.REPORT_NAME).read_bytes()
        with patch.object(review.os, 'replace', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                review.check(self.root, self.data, self.now)
        self.assertEqual((self.data / review.REPORT_NAME).read_bytes(), previous)
        self.assertEqual(list(self.data.glob('.review-*.tmp')), [])

    def test_missing_config_stays_unverified_instead_of_clearing_or_reopening(self):
        self.record()
        pending, _ = self.run_check()
        (self.data / '陪伴建议.json').unlink()
        unavailable, changed = self.run_check()
        self.assertTrue(changed)
        self.assertEqual(unavailable['candidate_coverage'], 'current_inputs_unavailable')
        self.assertEqual(unavailable['candidates'], pending['candidates'])
        repeated, changed = self.run_check()
        self.assertFalse(changed)
        self.assertEqual(repeated['status'], 'needs_review')
        self.write_items([self.item])
        self.write_state({'synthetic-care-a': dict(status='declined')})
        self.run_check()
        (self.data / '陪伴提醒状态.json').unlink()
        unavailable, _ = self.run_check()
        self.assertEqual(unavailable['status'], 'needs_review')
        self.assertEqual(unavailable['candidates'][0]['review_status'], 'declined')
        self.assertFalse(self.run_check()[1])
        (self.data / review.REPORT_NAME).unlink()  # Simulate a new install without a prior report.
        missing_state, _ = self.run_check()
        self.assertEqual(missing_state['errors'][0]['code'], 'reminder_state_missing')
        (self.data / '陪伴建议.json').unlink()
        (self.data / review.REPORT_NAME).unlink()
        unconfigured, changed = self.run_check()
        self.assertEqual(unconfigured['status'], 'clear')
        self.assertFalse(changed)

    def test_cli_quiet_and_error_changes_without_fake_delivery(self):
        self.item.update(review_on='2999-01-01', expires_on='2999-02-01')
        self.write_items([self.item])
        args = ['--root', str(self.root), '--data', str(self.data)]
        def run():
            output = io.StringIO()
            with redirect_stdout(output):
                code = review.main(args)
            return code, output.getvalue()
        self.assertEqual(run(), (0, ''))
        (self.data / '陪伴提醒状态.json').write_text('{broken')
        code, output = run()
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['status'], 'needs_review')
        self.assertEqual(run(), (1, ''))
        self.write_state({})
        code, output = run()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['status'], 'clear')
        self.assertEqual(run(), (0, ''))
        report = json.loads((self.data / review.REPORT_NAME).read_text())
        self.assertLess(abs((dt.datetime.fromisoformat(report['checked_at']) - dt.datetime.now(review.TIMEZONE)).total_seconds()), 10)

    def test_structured_choices_are_arrangements_and_text_remains_unreviewed(self):
        self.now=dt.datetime.now(review.TIMEZONE)
        today=self.now.date()
        self.item.update(review_on=(today+dt.timedelta(days=1)).isoformat(),expires_on=(today+dt.timedelta(days=8)).isoformat())
        self.write_items([self.item])
        app=review.load_app(self.root,self.data)
        app.connect().close()  # Synthetic application migration precedes the read-only checker.
        def feedback(key,choice='',note='',date=''):
            return app.save_record(dict(child='示例甲',day=today.isoformat(),category='家长观察',subject='阅读',
                title='虚构选择反馈',note=note,source='陪伴建议:synthetic-care-a',attachments=[],
                care_choice=choice,care_review_on=date,request_key='synthetic_review_choice_'+key),care_only=True)
        stopped=feedback('1','暂不考虑')
        self.assertEqual(self.run_check()[0]['candidates'],[])
        plain=feedback('2',note='虚构实际反馈，内容尚未解读。')
        pending,_=self.run_check()
        self.assertEqual(pending['candidates'][0]['review_status'],'declined')
        self.assertEqual(pending['candidates'][0]['unchecked_feedback_ids'],[plain['record_id']])
        deferred=feedback('3','改天回看',date=(today+dt.timedelta(days=3)).isoformat())
        pending,_=self.run_check()
        self.assertEqual(pending['candidates'][0]['reason'],'feedback_needs_review')
        self.assertEqual(pending['candidates'][0]['review_status'],'deferred')
        self.assertEqual(pending['candidates'][0]['choice_record_id'],deferred['record_id'])
        # A correction to an earlier record remains evidence, without changing the newer choice.
        app.save_record(dict(id=plain['record_id'],child='示例甲',day=today.isoformat(),category='家长观察',
            title='虚构更正',note='更正后的实际反馈。',source='陪伴建议:synthetic-care-a'))
        corrected,changed=self.run_check()
        self.assertTrue(changed)
        self.assertEqual(corrected['candidates'][0]['choice_record_id'],deferred['record_id'])
        paired=feedback('4','愿意试试',note='同条附有虚构观察，仍需核对。')
        paired_report,_=self.run_check()
        self.assertEqual(paired_report['candidates'][0]['review_status'],'accepted')
        self.assertIn(paired['record_id'],paired_report['candidates'][0]['unchecked_feedback_ids'])
        self.assertNotIn(stopped['record_id'],paired_report['candidates'][0]['unchecked_feedback_ids'])
        self.assertEqual(paired_report['candidates'][0]['review_on'],self.item['review_on'])
        due,_=self.run_check(self.now+dt.timedelta(days=1))
        self.assertEqual(due['candidates'][0]['reason'],'due_review')
        self.assertEqual(due['candidates'][0]['execution_status'],'unknown')


if __name__ == '__main__':
    unittest.main()

"""Root's fictional English teacher image (503) through the original entry: its three actual product replies replayed as
fixed inputs, not an accuracy proof. 503 is ingested as Root's input had it, an unread image message whose caption only points
to the image; the other five stay text. save_upload -> message_attachment -> the real original reader -> run_once rounds ->
the single-child list, as newly saved and as the earlier release saved it (its follow-reading held for review with no day),
reopened. The served whole day (--serve-image, --serve-image-saved) adds the child's own oral math correction through study
as the whole-day fixture saves it, its one request twice: seven tasks, the six school items and that one. No model is
configured or called; only the upload id this fixture's own save gives (and Root's program-assigned candidate id, not model
content) replaces the replies' one; order and every other value are kept. No household path, collector, printer or device
is used."""
import contextlib
import copy
import datetime as dt
import base64
import io
import json
import re
import unittest
from pathlib import Path
from unittest import mock

import family_agenda
import family_agent as agent
import family_llm
import family_media
import family_study
import test_daily_list_frozen as frozen
import test_daily_list_whole_day as whole

FIX = json.loads(Path(__file__).with_name('test_image_original_date_scope.json').read_text(encoding='utf-8'))
PNG = base64.b64decode(FIX['image_png_base64'])
OLD_ID, CAPTION = FIX['image_source']['upload_id'], FIX['image_source']['caption']
DAY = whole.DAY
ROOT_CANDIDATE = FIX['call_3']['actions'][0]['existing_item_id']
HELD = '本项日期与对应原件行动不一致，日期待补充；已读要求保留。'


def swap(value, new):
    if isinstance(value, str): return value.replace(OLD_ID, new)
    if isinstance(value, list): return [swap(v, new) for v in value]
    if isinstance(value, dict): return {swap(k, new): swap(v, new) for k, v in value.items()}
    return value


def earlier_reading(real):
    """a1b8873's completion reading: only 今天/今日/今晚 opened a work day, so a read original's restated written evening day
    (2026年11月4日晚…) gave none and the save check cleared the model day into review. Used only to make that saved state."""
    def read(quote, header, time, due_on):
        if re.match(r'\s*(?:\d{4}\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}\s*[日号]\s*(?:晚上|晚)', quote or ''): return ''
        return real(quote, header, time, due_on)
    return read


class ImageOriginalChainTests(unittest.TestCase):
    setUp = frozen.DailyListFrozenTests.setUp

    def _chain(self, earlier=False):
        payload = self.fixture.payload(cursor='506')
        # As Root's actual input: 503 the teacher's image message, collected unread with its caption only; the others text.
        payload['messages'] = [dict(id=i, message_order=i, time=DAY + 'T' + hm + ':00+08:00', kind='image' if i == '503' else 'text',
                                    sender=sender, sender_id=publisher, text=CAPTION if i == '503' else text, unread=i == '503')
                               for i, publisher, sender, text, hm in whole.MESSAGES]
        self.store.ingest(payload)
        self.upload = self.app.save_upload(io.BytesIO(PNG), len(PNG), 'fictional-teacher-message.png')['id']
        self.keys = dict(child_id='child-1', source_id=self.source['id'], message_id='503')
        self.store.message_attachment(dict(self.keys, attachment_id=self.upload, action='attach'), self.app.upload_info)
        replies = {n: swap(FIX['call_%d' % n], self.upload) for n in (1, 2, 3)}
        self.calls = []

        def model(messages, schema, name, timeout=60, *, data_path=None):
            context = json.loads(messages[-1]['content']); self.calls.append(name)
            if name == 'family_agent_selection': return copy.deepcopy(replies[2])
            if 'original_parts' in context:
                # Root's candidate id was assigned by its own run's program, not the model: the same candidate is this run's one.
                out = copy.deepcopy(replies[3])
                for action in out['actions']:
                    if action.get('existing_item_id') == ROOT_CANDIDATE: action['existing_item_id'] = context['candidate_id']
                return out
            raise AssertionError('no other model call in this chain: ' + name)
        self.model.side_effect = model
        self.ref = 'message:' + self.source['id'] + ':503'
        stack = contextlib.ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(family_media, 'prepare_draft', frozen.READ_ORIGINALS))
        self.reads = stack.enter_context(mock.patch.object(family_llm, 'extract_draft', side_effect=[copy.deepcopy(replies[1])]))
        with contextlib.ExitStack() as old:
            if earlier: old.enter_context(mock.patch.object(family_agenda, 'completion_day', earlier_reading(family_agenda.completion_day)))
            for minutes in (0, 1): agent.run_once(self.app, self.now + dt.timedelta(minutes=minutes))
        self.assertEqual((self.calls, self.reads.call_count), (['family_agent_selection', 'family_school_task'], 1))

    def _db(self):
        with self.store._db() as c:
            return ({r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")},
                    {r['id']: dict(r) for r in c.execute('SELECT * FROM agent_jobs')},
                    [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')],
                    [dict(r) for r in c.execute('SELECT id,cursor FROM agent_sources ORDER BY id')])

    def _follow(self, rows):
        found = [r for r in rows.values() if '跟读' in r['title'] + r['body'] and json.loads(r['plan']).get('school_original_action')]
        self.assertEqual(len(found), 1, [r['title'] for r in rows.values()]); return found[0]

    def _check_list(self, held=False):
        before = self._db()
        mine, _ = whole.WholeDayTests._list(self)
        self.assertEqual(self._db(), before)  # opening the list writes nothing and calls no model
        school = [i for i in mine if i['agenda'].get('publications')]
        self.assertEqual(len(school), 6, [i['title'] for i in school])
        english = [i for i in school if [p['ref'] for p in i['agenda']['publications']] == [self.ref]]
        self.assertEqual(len(english), 2, [i['title'] for i in english])
        follow, = [i for i in english if '跟读' in i['title'] + i['body']]
        dictation, = [i for i in english if i is not follow]
        for word in ('Unit 7', '3', '10', '3遍', '不用抄写'): self.assertIn(word, follow['title'] + follow['body'])
        for word in ('跟读', 'Unit', '今晚'): self.assertNotIn(word, dictation['title'])
        self.assertEqual((dictation['agenda']['due_on'], dictation['agenda'].get('due_kind')), ('2026-11-05', 'inspection'))
        m = follow['agenda']
        self.assertNotIn(m.get('due_kind', ''), ('handback', 'inspection', 'arranged'))
        self.assertIn(DAY, (m.get('complete_on', ''), m['due_on'] if m.get('due_kind', '') in ('', 'deadline') else ''), m)
        self.assertEqual(follow['kind'], 'task')  # accepted into the list, no blanket confirmation
        snapshot = self.app.calendar_snapshot(DAY, DAY)
        ids = {i['id'] for i in school}
        self.assertFalse([i for i in snapshot['inbox'] if i['child_ids'] != ['child-1'] and i['id'] in ids])
        return follow, dictation

    def test_new_save_lists_both_image_actions_on_their_own_days(self):
        self._chain()
        rows = self._db()[0]; follow = self._follow(rows)
        self.assertEqual((follow['state'], follow['due'], json.loads(follow['plan'])['school_task']['state']), ('accepted', DAY, 'ready'))
        self._check_list()
        made = self._db(); agent.run_once(self.app, self.now + dt.timedelta(minutes=2))  # reopen: no call, write or duplicate
        self.assertEqual((self._db(), self.calls, self.reads.call_count), (made, ['family_agent_selection', 'family_school_task'], 1))
        self._check_list()

    def test_earlier_saved_review_is_restored_once_without_a_model_call(self):
        self._chain(earlier=True)
        rows, jobs, tasks, sources = self._db(); follow = self._follow(rows)
        brief = json.loads(follow['plan'])['school_task']
        # The state Root's receipt shows the earlier release saved: pending, held for review, no day.
        self.assertEqual((follow['state'], follow['due'], brief['state'], brief['reason']), ('pending', '', 'review', HELD))
        agent.run_once(self.app, self.now + dt.timedelta(minutes=2))
        after, jobs2, tasks2, sources2 = self._db(); restored = after[follow['id']]
        self.assertEqual((self.calls, self.reads.call_count), (['family_agent_selection', 'family_school_task'], 1))
        self.assertEqual(set(after), set(rows))  # same rows and ids, no duplicate
        self.assertEqual((restored['state'], restored['due'], restored['title'], restored['body']), ('accepted', DAY, follow['title'], follow['body']))
        plan = json.loads(restored['plan'])
        self.assertEqual(plan['school_role_reselect']['previous_row'], follow)
        self.assertEqual(plan['school_original_action']['requirements'], json.loads(follow['plan'])['school_original_action']['requirements'])
        self.assertEqual(sources2, sources)  # cursor unchanged
        for key, job in jobs.items(): self.assertEqual((jobs2[key]['attempts'], jobs2[key]['done']), (job['attempts'], job['done']), key)
        self.assertEqual(len(tasks2), len(tasks) + 1)
        self._check_list()
        made = self._db(); agent.run_once(self.app, self.now + dt.timedelta(minutes=3))  # once only; reopen writes nothing
        self.assertEqual(self._db(), made)
        self._check_list()

    def _held(self, change):
        self._chain(earlier=True)
        follow = self._follow(self._db()[0]); change(follow)
        held = self._db(); agent.run_once(self.app, self.now + dt.timedelta(minutes=2))
        now = self._db()[0][follow['id']]
        self.assertEqual((now['state'], now['due']), ('pending', ''))
        self.assertNotIn('school_role_reselect', json.loads(now['plan']))
        self.assertEqual(self.calls, ['family_agent_selection', 'family_school_task'])
        return held, now

    def test_a_parent_edit_keeps_the_saved_review(self):
        def edit(row):
            with self.store._db() as c: c.execute('UPDATE agent_items SET title=? WHERE id=?', ('英语：家长改过的标题', row['id']))
        _, now = self._held(edit)
        self.assertEqual(now['title'], '英语：家长改过的标题')

    def test_a_detached_original_keeps_its_day_unknown(self):
        def detach(row):
            self.store.message_attachment(dict(self.keys, attachment_id=self.upload, action='detach'), self.app.upload_info)
        _, now = self._held(detach)
        with self.store._db() as c:
            self.assertEqual(agent.school_original_requirements(self.store, c, now), ())

    def _whole_day(self, earlier=False):
        """The served whole day: the chain (saved earlier: then its one bounded restore, no model call) and the child's own oral
        math correction through study as the whole-day fixture saves it, its same request twice as a lost reply resent."""
        self._chain(earlier=earlier)
        if earlier: agent.run_once(self.app, self.now + dt.timedelta(minutes=2))
        for _ in range(2): whole.WholeDayTests._oral(self)

    def _check_whole_day(self, earlier):
        self._whole_day(earlier)
        self._check_list()  # the six school items stay as above
        mine, visible = whole.WholeDayTests._list(self)
        self.assertEqual(len(mine), 7, [i['title'] for i in mine])
        oral, = [i for i in mine if not i['agenda'].get('publications')]  # one oral task, citing no teacher original
        self.assertIn('订正课堂练习第5、6题', oral['title'])
        self.assertIn('错因', oral['title'] + oral['body'])
        self.assertIn(DAY, (oral['agenda']['due_on'], oral['agenda']['scheduled_on'], oral['agenda'].get('complete_on', '')), oral['agenda'])
        self.assertIn(oral['title'], visible)
        saved, = [t for t in self.app.tasks() if '第5、6题' in t['title']]
        self.assertEqual(saved['source'], family_study.CHILD_REPORT_PENDING, "the child's own report")
        self.assertEqual((self.calls, self.reads.call_count), (['family_agent_selection', 'family_school_task'], 1))

    def test_the_served_new_whole_day_adds_the_childs_own_oral_correction_once(self):
        self._check_whole_day(False)

    def test_the_served_earlier_saved_whole_day_adds_the_childs_own_oral_correction_once(self):
        self._check_whole_day(True)


def serve(port, earlier):
    case = ImageOriginalChainTests('test_new_save_lists_both_image_actions_on_their_own_days'); case.setUp()
    try:
        case._whole_day(earlier)
        frozen.serve_store(case, port, 'Image original whole day served')
    finally:
        case.doCleanups()


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] in (['--serve-image'], ['--serve-image-saved']): serve(int(sys.argv[2]), sys.argv[1] == '--serve-image-saved')
    else: unittest.main()

"""独立 PDF 页组整理：合成 11 页 PDF 与虚构 QQ 截图通知，模型全部替身；缺 poppler 时按 test_pdf 同法只替换子进程。"""
import contextlib
import datetime as dt
import inspect
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import family_llm
import family_pdf
import family_pdf_material as pdfm
import test_media
import test_pdf

PDF = test_pdf.build_pdf(11)
DRAFT = dict(title='虚构练习卷页组', note='题目与参考答案为老师材料，未见孩子作答。', uncertainties=['发送日期未知'])
BATCHES = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11]]
TABLES = ('sqlite_master', 'agent_pdf_material', 'agent_jobs', 'agent_message_drafts', 'agent_message_attachments',
          'agent_items', 'records', 'manual_tasks', 'uploads')


def renderer():
    """Real poppler when present; otherwise test_pdf's subprocess stand-in, so render_pages/page_count still run."""
    if test_pdf.TOOLS_AVAILABLE:
        return contextlib.nullcontext()
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(family_pdf.shutil, 'which', lambda name: '/synthetic/' + name))
    stack.enter_context(patch.object(family_pdf, '_run', test_pdf.fake_run_factory(page_count=11)))
    return stack


def no_render():
    return patch.object(family_pdf.subprocess, 'run', side_effect=AssertionError('pdfinfo/pdftoppm must not run here'))


class Base(test_media.MediaTests):
    """Reuses the fictional family, QQ source and helpers; the inherited media tests are hidden below."""


for _name in [n for n in dir(test_media.MediaTests) if n.startswith('test_')]:
    setattr(Base, _name, None)


class PdfMaterialTests(Base):
    def seed_pdf(self, ident, body=PDF, name='虚构练习卷.pdf'):
        (self.data / 'uploads').mkdir(exist_ok=True)
        (self.data / 'uploads' / ident).write_bytes(body)
        with self.store._db() as c:
            c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',
                      (ident, name, len(body), 'application/pdf', self.now.isoformat()))
        return ident

    def view(self, keys):
        return self.store.message(keys, dict)['pdf_material']

    def rows(self, sql, *params):
        with self.store._db() as c:
            return [tuple(r) for r in c.execute(sql, params).fetchall()]

    def snapshot(self):
        return [self.rows('SELECT * FROM ' + t) for t in TABLES]

    def consumers(self):
        return [self.rows('SELECT * FROM records'), self.rows('SELECT * FROM agent_items'), self.rows('SELECT * FROM manual_tasks'),
                self.rows('SELECT id,processed FROM agent_messages'), self.rows('SELECT * FROM agent_message_drafts')]

    def set_sources(self, enabled):
        path = self.data / 'agent.json'; obj = json.loads(path.read_text())
        for s in obj['sources']:
            s['enabled'] = enabled
        path.write_text(json.dumps(obj, ensure_ascii=False))

    def test_eleven_pages_take_four_ordered_batches_then_zero_calls(self):
        keys = self.school_fragment('数学：完成所附练习卷第1至11页。')
        self.assertIsNone(self.view(keys))
        pdf = self.seed_pdf('a' * 32); self.link(keys, pdf)
        first = self.view(keys)
        self.assertEqual((first['state'], first['kind'], first['page_count'], first['batches'], first['complete'], first['upload_id']),
                         ('pending', 'school_material', None, [], False, pdf))
        facts = self.facts(); consumers = self.consumers(); calls = []

        def model(text, images, **kw):
            context = json.loads(text)
            self.assertEqual(context['source_message']['id'], keys['message_id']); self.assertEqual(context['original_pdf']['page_count'], 11)
            calls.append((context['original_pdf']['pages'], context['original_pdf']['unprocessed_pages'], [i['mime'] for i in images], kw))
            return dict(DRAFT, title='第%s页' % context['original_pdf']['pages'])
        with renderer(), patch.object(family_llm, 'extract_draft', side_effect=model) as m:
            for index, expected in enumerate(BATCHES):
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=index)), dict(used=1, failed=0))
                pages, left, mimes, kw = calls[-1]
                self.assertEqual((pages, left, mimes), (expected, list(range(expected[-1] + 1, 12)), ['image/png'] * len(expected)))
                self.assertIs(kw['school_material'], True); self.assertEqual(kw['target_child'], '示例甲'); self.assertNotIn('documents', kw)
                shown = self.view(keys)
                self.assertEqual(shown['page_count'], 11); self.assertEqual([b['pages'] for b in shown['batches']], BATCHES[:index + 1])
                self.assertEqual((shown['processed_pages'], shown['pending_pages']), (list(range(1, expected[-1] + 1)), list(range(expected[-1] + 1, 12))))
                self.assertEqual((shown['complete'], shown['state']), (index == 3, 'ready' if index == 3 else 'pending'))
            self.assertEqual(m.call_count, 4)
            with no_render():  # Complete: no pdfinfo, no render, no model, no job attempt.
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=9)), dict(used=0, failed=0))
            self.assertEqual(m.call_count, 4)
        shown = self.view(keys)
        self.assertEqual([b['draft']['title'] for b in shown['batches']], ['第%s页' % b for b in BATCHES])
        self.assertEqual(shown['explanation'], '')
        self.assertEqual((self.facts(), self.consumers()), (facts, consumers))

    def test_failed_group_keeps_saved_groups_and_retries_only_pending_pages(self):
        keys = self.school_fragment('英语：阅读所附材料。'); self.link(keys, self.seed_pdf('b' * 32))
        outcomes = [DRAFT, family_llm.LLMDraftError('虚构失败'), DRAFT]; seen = []

        def model(text, images, **kw):
            seen.append(json.loads(text)['original_pdf']['pages']); result = outcomes.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        with renderer(), patch.object(family_llm, 'extract_draft', side_effect=model):
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=1)), dict(used=1, failed=1))
            shown = self.view(keys)
            self.assertEqual((shown['state'], shown['processed_pages'], shown['pending_pages'], shown['explanation']),
                             ('error', [1, 2, 3], list(range(4, 12)), pdfm.FAILED))
            with no_render():  # Back-off of the same job: nothing rendered or called.
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=2)), dict(used=0, failed=0))
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=7)), dict(used=1, failed=0))
        self.assertEqual(seen, [[1, 2, 3], [4, 5, 6], [4, 5, 6]])
        self.assertEqual([b['pages'] for b in self.view(keys)['batches']], [[1, 2, 3], [4, 5, 6]])

    def test_zero_budget_neither_renders_nor_calls(self):
        keys = self.school_fragment('科学：见附件。'); self.link(keys, self.seed_pdf('c' * 32))
        jobs = self.rows('SELECT * FROM agent_jobs')
        with no_render(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            self.assertEqual(pdfm.prepare(self.store, self.now, 0), dict(used=0, failed=0))
        self.assertEqual(self.rows('SELECT * FROM agent_jobs'), jobs)
        self.assertEqual(self.view(keys)['state'], 'pending')

    def test_revocation_and_other_child_hide_progress_and_stop_calls(self):
        keys = self.school_fragment('语文：见附件。'); pdf = self.seed_pdf('d' * 32); self.link(keys, pdf)
        with renderer(), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
            for change, restore in [(lambda: self.write_config(enabled=False), self.write_config),
                                    (lambda: self.set_sources(False), lambda: self.set_sources(True))]:
                change()
                self.assertEqual(self.view(keys)['state'], 'unavailable')
                with no_render():
                    self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=1)), dict(used=0, failed=0))
                restore()
                self.assertEqual(self.view(keys)['processed_pages'], [1, 2, 3])  # Saved groups survive re-authorization.
            self.assertEqual(m.call_count, 1)
            other = self.seed_pdf('e' * 32, name='别人的.pdf')
            with self.store._db() as c:
                self.store._message_upload(c, 'child-2', other)  # Claimed by the other child first.
            self.link(keys, pdf, 'detach'); self.link(keys, other)
            self.assertEqual(self.view(keys)['state'], 'unavailable')
            with no_render():
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=2)), dict(used=0, failed=0))
            with self.assertRaises(agent.AgentError):
                self.store.message(keys | dict(child_id='child-2'), dict)
        self.assertEqual(m.call_count, 1)

    def test_inflight_unlink_or_correction_discards_result_without_holding_lock(self):
        keys = self.school_fragment('数学：见附件。'); pdf = self.seed_pdf('f' * 32); self.link(keys, pdf)

        def unlink_during_model(text, images, **kw):
            self.link(keys, pdf, 'detach')  # Parent acts while the model runs: no database lock may be held.
            self.assertEqual(self.rows('SELECT * FROM agent_message_attachments WHERE upload_id=?', pdf), [])
            return DRAFT
        with renderer(), patch.object(family_llm, 'extract_draft', side_effect=unlink_during_model) as m:
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
        self.assertEqual(m.call_count, 1)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_pdf_material'), [(0,)])
        self.assertEqual(self.rows("SELECT done,error FROM agent_jobs WHERE id LIKE 'pdf-material:%'"), [(1, '')])
        self.assertIsNone(self.view(keys))
        self.link(keys, pdf)

        def correct_during_model(text, images, **kw):
            with self.store._db() as c:
                c.execute('BEGIN IMMEDIATE')
                payload = json.loads(c.execute('SELECT payload FROM agent_messages WHERE id=?', (keys['message_id'],)).fetchone()['payload'])
                payload['text'] += '（家长更正：第3页不用做）'
                c.execute('UPDATE agent_messages SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), keys['message_id']))
            return DRAFT
        with renderer(), patch.object(family_llm, 'extract_draft', side_effect=correct_during_model):
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=1)), dict(used=1, failed=0))
        self.assertIn('家长更正', self.store.message(keys, dict)['message']['text'])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_pdf_material'), [(0,)])
        shown = self.view(keys)
        self.assertEqual((shown['state'], shown['batches'], shown['processed_pages']), ('pending', [], []))

    def test_changed_original_hides_old_groups_and_restarts_from_page_one(self):
        keys = self.school_fragment('数学：见附件。'); pdf = self.seed_pdf('1' * 32); self.link(keys, pdf); seen = []

        def model(text, images, **kw):
            seen.append(json.loads(text)['original_pdf']['pages']); return DRAFT
        with renderer(), patch.object(family_llm, 'extract_draft', side_effect=model):
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
            self.assertEqual(self.view(keys)['processed_pages'], [1, 2, 3])
            other = test_pdf.build_pdf(11, width=2001); self.assertEqual(len(other), len(PDF))
            (self.data / 'uploads' / pdf).write_bytes(other)  # Same size and name, different bytes.
            shown = self.view(keys)
            self.assertEqual((shown['state'], shown['processed_pages'], shown['batches']), ('pending', [], []))
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=1)), dict(used=1, failed=0))
        self.assertEqual(seen, [[1, 2, 3], [1, 2, 3]])
        self.assertEqual(self.rows('SELECT COUNT(DISTINCT fingerprint) FROM agent_pdf_material'), [(2,)])
        self.assertEqual([b['pages'] for b in self.view(keys)['batches']], [[1, 2, 3]])

    def test_view_is_read_only_without_render_model_or_new_tables(self):
        keys = self.school_fragment('数学：见附件。'); self.link(keys, self.seed_pdf('2' * 32))
        self.view(keys); before = self.snapshot()
        with no_render(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model in GET')):
            shown = self.view(keys)
        self.assertEqual((shown['state'], shown['page_count'], shown['pending_pages'], shown['complete']), ('pending', None, [], False))
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn('pdf_material', inspect.getsource(__import__('family_child')))

    def test_multiple_or_mixed_originals_are_refused_explicitly(self):
        keys = self.school_fragment('数学：见附件。'); a = self.seed_pdf('3' * 32); b = self.seed_pdf('4' * 32, name='第二份.pdf')
        self.link(keys, a); self.link(keys, b)
        with no_render(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            shown = self.view(keys); self.assertEqual(shown['state'], 'unavailable'); self.assertIn('多个PDF', shown['explanation'])
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=0, failed=0))
            self.link(keys, b, 'detach'); image = self.seed_upload('5' * 32, test_media.png()); self.link(keys, image)
            shown = self.view(keys); self.assertEqual(shown['state'], 'unavailable'); self.assertIn('单独关联', shown['explanation'])
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=0, failed=0))
            self.link(keys, image, 'detach'); self.assertEqual(self.view(keys)['state'], 'pending')
            self.link(keys, a, 'detach'); self.link(keys, image); self.assertIsNone(self.view(keys))  # Pictures: existing path.
        self.assertEqual(self.store.message(keys, dict)['material_draft']['state'], 'pending')
        self.assertEqual(self.rows("SELECT * FROM agent_jobs WHERE id LIKE 'pdf-material:%'"), [])

    def test_school_material_stays_isolated_from_facts(self):
        keys = self.school_fragment('数学：见附件成绩表。'); self.link(keys, self.seed_pdf('6' * 32))
        with self.store._db() as c:
            c.execute("INSERT INTO manual_tasks(id,child,title,due,original_status,source,action) VALUES('task-1','child-1','虚构学校任务','2026-02-11','待完成','Agent建议:agent-x','家长已确认完成')")
        facts = self.facts(); consumers = self.consumers(); leaked = dict(DRAFT, score=95, total=100)
        with renderer(), patch.object(family_llm, 'extract_draft', side_effect=[leaked, DRAFT]):
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=1))
            self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_pdf_material'), [(0,)])
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=6)), dict(used=1, failed=0))
        saved = json.loads(self.rows('SELECT payload FROM agent_pdf_material')[0][0])
        self.assertEqual(set(saved), {'kind', 'title', 'note', 'uncertainties'})
        self.assertEqual((self.facts(), self.consumers()), (facts, consumers))

    def test_tick_hook_uses_leftover_budget_with_one_call_cap(self):
        source = inspect.getsource(agent.run_once)
        self.assertIn('family_pdf_material.prepare(store, now, min(budget, family_pdf_material.ROUND_CALLS))', source)
        self.assertEqual(pdfm.ROUND_CALLS, 1); self.assertEqual(pdfm.BATCH_PAGES, 3)
        self.assertEqual(pdfm.prepare(self.store, self.now, 0), dict(used=0, failed=0))


if __name__ == '__main__':
    unittest.main()

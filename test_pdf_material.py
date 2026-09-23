"""独立 PDF/DOCX 页组整理：合成 11 页 PDF、含图片的合成 DOCX（docx_pdf 替身返回真实合成 PDF）与虚构 QQ 截图通知，模型全部替身；缺 poppler 时按 test_pdf 同法只替换子进程。"""
import contextlib
import datetime as dt
import inspect
import json
import unittest
import zipfile
from unittest.mock import patch

import family_agent as agent
import family_llm
import family_media
import family_pdf
import family_pdf_material as pdfm
import test_media
import test_pdf

PDF = test_pdf.build_pdf(11)
DRAFT = dict(title='虚构练习卷页组', note='题目与参考答案为老师材料，未见孩子作答。', uncertainties=['发送日期未知'])
BATCHES = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11]]
TABLES = ('sqlite_master', 'agent_pdf_material', 'agent_jobs', 'agent_message_drafts', 'agent_message_attachments',
          'agent_items', 'records', 'manual_tasks', 'uploads')


def renderer(page_count=11):
    """Real poppler when present; otherwise test_pdf's subprocess stand-in, so render_pages/page_count still run."""
    if test_pdf.TOOLS_AVAILABLE:
        return contextlib.nullcontext()
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(family_pdf.shutil, 'which', lambda name: '/synthetic/' + name))
    stack.enter_context(patch.object(family_pdf, '_run', test_pdf.fake_run_factory(page_count=page_count)))
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

    def facts(self):
        facts = super().facts(); del facts['agent_pdf_material']  # The one table this line may write; everything else must not move.
        return facts

    def progress(self):
        return self.rows('SELECT first_page,pages,page_count FROM agent_pdf_material ORDER BY fingerprint,first_page')

    def claim_for_other_child(self, ident):
        """child-2's reading work already owns the upload: the same binding `_message_upload` enforces for child-1."""
        import family_reading
        family_reading.Store(self.app.connect, self.app.profiles, lambda c: [])
        with self.store._db() as c:
            c.execute('INSERT INTO reading_uploads(upload_id,child_id) VALUES(?,?)', (ident, 'child-2'))
        with self.store._db() as c:
            self.assertEqual(self.store._message_upload(c, 'child-2', ident)['id'], ident)
            with self.assertRaises(agent.AgentError) as raised:
                self.store._message_upload(c, 'child-1', ident)
            self.assertIn('另一位孩子', str(raised.exception))

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
        self.assertEqual([(r[0], r[2]) for r in self.progress()], [(1, 11), (4, 11), (7, 11), (10, 11)])

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
            self.claim_for_other_child(other)
            self.link(keys, pdf, 'detach')
            with self.assertRaises(agent.AgentError):
                self.link(keys, other)  # The real API must reject first; then simulate a stale legacy association.
            with self.store._db() as c:
                c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', (keys['source_id'], keys['message_id'], other))
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
        self.assertEqual(self.rows("SELECT * FROM agent_jobs WHERE id LIKE 'pdf-material:%'"), [])  # Withdrawn, not completed.
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
        with renderer(), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:  # Recovery: the corrected notice continues.
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=2)), dict(used=1, failed=0))
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=3)), dict(used=1, failed=0))
        self.assertEqual((m.call_count, self.view(keys)['processed_pages'], [r[0] for r in self.progress()]), (2, [1, 2, 3, 4, 5, 6], [1, 4]))
        self.assertEqual([json.loads(c.args[0])['original_pdf']['pages'] for c in m.call_args_list], [[1, 2, 3], [4, 5, 6]])

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

    def test_render_count_and_pages_share_one_twenty_second_deadline(self):
        from types import SimpleNamespace
        keys = self.school_fragment('数学：见附件。'); self.link(keys, self.seed_pdf('0' * 32))
        clock = iter([0, 1, 21])
        with patch.object(pdfm, 'time', SimpleNamespace(monotonic=lambda: next(clock))), \
                patch.object(family_pdf, 'page_count', return_value=11) as count, \
                patch.object(family_pdf, 'render_pages') as render, patch.object(family_llm, 'extract_draft') as model:
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=1))
        self.assertEqual(count.call_args.args[1], 19)
        self.assertEqual((render.call_count, model.call_count), (0, 0))
        self.assertEqual(self.view(keys)['processed_pages'], [])

    def test_view_is_read_only_without_render_model_or_new_tables(self):
        keys = self.school_fragment('数学：见附件。'); self.link(keys, self.seed_pdf('2' * 32))
        self.view(keys); before = self.snapshot()
        sql = []; original = self.store._db
        @contextlib.contextmanager
        def traced():
            with original() as c:
                c.set_trace_callback(sql.append); yield c
        with patch.object(self.store, '_db', traced), no_render(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model in GET')):
            shown = self.view(keys)
        self.assertFalse(any(q.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'REPLACE')) for q in sql), sql)
        self.assertEqual((shown['state'], shown['page_count'], shown['pending_pages'], shown['complete']), ('pending', None, [], False))
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn('pdf_material', inspect.getsource(__import__('family_child')))

    def test_multiple_or_mixed_originals_are_refused_explicitly(self):
        keys = self.school_fragment('数学：见附件。'); a = self.seed_pdf('3' * 32); b = self.seed_pdf('4' * 32, name='第二份.pdf')
        self.link(keys, a); self.link(keys, b)
        with no_render(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            shown = self.view(keys); self.assertEqual(shown['state'], 'unavailable'); self.assertIn('多个PDF', shown['explanation'])
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=0, failed=0))
            self.link(keys, b, 'detach'); image = self.seed_upload('5' * 32, test_media.png(width=97)); self.link(keys, image)
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
        self.assertEqual([r[0] for r in self.progress()], [1])

    def test_change_after_render_sends_nothing_and_progress_resumes_after_restore(self):
        keys = self.school_fragment('数学：见附件。'); pdf = self.seed_pdf('7' * 32); self.link(keys, pdf)

        def correct():
            with self.store._db() as c:
                c.execute('BEGIN IMMEDIATE')
                payload = json.loads(c.execute('SELECT payload FROM agent_messages WHERE id=?', (keys['message_id'],)).fetchone()['payload'])
                payload['text'] += '（家长更正）'
                c.execute('UPDATE agent_messages SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), keys['message_id']))
        cases = [(lambda: self.write_config(enabled=False), lambda: self.assertFalse(self.store._config()['enabled']), self.write_config),
                 (lambda: self.link(keys, pdf, 'detach'),
                  lambda: self.assertEqual(self.rows('SELECT * FROM agent_message_attachments WHERE upload_id=?', pdf), []),
                  lambda: self.link(keys, pdf)),
                 (correct, lambda: self.assertIn('家长更正', self.store.message(keys, dict)['message']['text']), lambda: None)]
        real = family_pdf.render_pages
        for index, (change, applied, restore) in enumerate(cases):
            def rendered_then_changed(body, pages, deadline=family_pdf.DEADLINE_SECONDS, change=change):
                result = real(body, pages, deadline); change(); return result
            with renderer(), patch.object(family_pdf, 'render_pages', side_effect=rendered_then_changed) as r, \
                    patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model after a change')) as m:
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=index)), dict(used=0, failed=0))
            self.assertEqual((r.call_count, m.call_count), (1, 0)); applied()  # The change really took effect; nothing went out.
            self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_pdf_material'), [(0,)])
            self.assertEqual(self.rows("SELECT * FROM agent_jobs WHERE id LIKE 'pdf-material:%'"), [])
            restore()
        with renderer(), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:  # Restored: continues with one call.
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=5)), dict(used=1, failed=0))
        self.assertEqual((m.call_count, self.view(keys)['processed_pages']), (1, [1, 2, 3]))

    def test_corrupted_progress_rows_never_fake_coverage_or_block_real_groups(self):
        keys = self.school_fragment('数学：见附件。'); pdf = self.seed_pdf('8' * 32); self.link(keys, pdf); seen = []
        with self.store._db() as c:
            source, message = self.store._message_context(c, keys)
            fp = pdfm.pdf_input(self.store, c, source, message)['fingerprint']
            payload = json.dumps(dict(kind='school_material', **DRAFT), ensure_ascii=False)
            for first, pages, count in [(1, list(range(1, 12)), 11), (2, [2, 2, 3], 11), (3, [3, 4, 5], 500), (5, [4, 5, 6], 11),
                                        (6, [6, 30], 11), (7, [7, 8, 9], 11)]:  # Only the last row is a real page group.
                c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',
                          (source['id'], message['id'], fp, first, json.dumps(pages), count, payload, self.now.isoformat()))
        shown = self.view(keys)
        self.assertEqual((shown['page_count'], shown['processed_pages'], shown['complete'], shown['state']), (11, [7, 8, 9], False, 'pending'))
        with renderer(), patch.object(family_llm, 'extract_draft',
                                      side_effect=lambda text, images, **kw: seen.append(json.loads(text)['original_pdf']['pages']) or DRAFT):
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
        self.assertEqual((seen, self.view(keys)['processed_pages']), ([[1, 2, 3]], [1, 2, 3, 7, 8, 9]))

    def test_run_once_hands_the_pdf_one_call_of_the_tick_budget(self):
        keys = self.school_fragment('数学：见附件。'); self.link(keys, self.seed_pdf('9' * 32)); budgets = []; real = pdfm.prepare

        def spy(store, now, budget=pdfm.ROUND_CALLS):
            budgets.append(budget); return real(store, now, budget)
        with renderer(), patch.object(pdfm, 'prepare', side_effect=spy), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:
            agent.run_once(self.app, self.now)
        self.assertEqual(budgets, [1])
        self.assertEqual([c.kwargs.get('school_material') for c in m.call_args_list if 'original_pdf' in c.args[0]], [True])
        self.assertEqual(self.view(keys)['processed_pages'], [1, 2, 3])

    def test_tick_hook_uses_leftover_budget_with_one_call_cap(self):
        source = inspect.getsource(agent.run_once)
        self.assertIn('family_pdf_material.prepare(store, now, min(budget, family_pdf_material.ROUND_CALLS))', source)
        self.assertEqual(pdfm.ROUND_CALLS, 1); self.assertEqual(pdfm.BATCH_PAGES, 3)
        self.assertEqual(pdfm.prepare(self.store, self.now, 0), dict(used=0, failed=0))



DOCX_MIME = family_media.DOCX_MIME
DOCX_RELS = test_media._RELS % ('<Relationship Id="rId5" Type="%simage" Target="media/image1.png"/>' % test_media._REL_TYPE)


def layout_docx(caption='题目见下图'):
    """A synthetic DOCX with an embedded picture: docx_text refuses it as layout, docx_pdf would accept it. Stored, so
    two captions of equal byte length give same-size files with different bytes."""
    return test_media.docx(test_media.para('虚构练习卷，' + caption) + '<w:p><w:r><w:drawing/></w:r></w:p>',
                           [('word/media/image1.png', test_media.png()), ('word/_rels/document.xml.rels', DOCX_RELS)], method=zipfile.ZIP_STORED)


DOCX_LAYOUT = layout_docx()
DOCX_PLAIN = test_media.docx(test_media.para('虚构纯文字通知：完成练习卷。'))
DOCX_MACRO = test_media.docx(test_media.para('虚构正文'), [('word/vbaProject.bin', 'x')])


def no_convert():
    return patch.object(family_media, 'docx_pdf', side_effect=AssertionError('LibreOffice conversion must not run here'))


def no_pages():
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(family_pdf, 'page_count', side_effect=AssertionError('pdfinfo must not run here')))
    stack.enter_context(patch.object(family_pdf, 'render_pages', side_effect=AssertionError('render must not run here')))
    return stack


class DocxMaterialTests(PdfMaterialTests):
    """One layout DOCX enters the same page-group path; docx_pdf is a stand-in that receives the original DOCX bytes and
    returns a real synthetic PDF (a real LibreOffice run is Codex's on-site check). The inherited PDF tests are hidden below."""

    def setUp(self):
        super().setUp(); self.converted = []

    def seed_docx(self, ident, body=DOCX_LAYOUT, name='虚构练习卷.docx'):
        (self.data / 'uploads').mkdir(exist_ok=True)
        (self.data / 'uploads' / ident).write_bytes(body)
        with self.store._db() as c:
            c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)', (ident, name, len(body), DOCX_MIME, self.now.isoformat()))
        return ident

    def converter(self, result=PDF, during=None):
        def convert(body, *, soffice=None):
            self.assertTrue(body.startswith(b'PK\x03\x04'), 'the original DOCX bytes are converted, never a kept PDF')
            self.converted.append(len(body))
            if during:
                during()  # The parent acts while LibreOffice runs: no database lock may be held.
            return result
        return patch.object(family_media, 'docx_pdf', side_effect=convert)

    def draft_state(self, keys):
        return self.store.message(keys, dict)['material_draft']

    def test_layout_docx_is_reconverted_each_round_and_covered_in_four_batches(self):
        keys = self.school_fragment('数学：完成所附练习卷。'); self.assertIsNone(self.view(keys))
        docx = self.seed_docx('a' * 32); self.link(keys, docx); tables = self.rows('SELECT name FROM sqlite_master')
        first = self.view(keys)
        self.assertEqual((first['state'], first['kind'], first['page_count'], first['batches'], first['complete'], first['upload_id']),
                         ('pending', 'school_material', None, [], False, docx))
        self.assertEqual((first['mime'], first['original'], first['name'], first['explanation'], first['conversion']),
                         (DOCX_MIME, 'docx', '虚构练习卷.docx', pdfm.WAITING_DOCX, pdfm.CONVERSION))
        self.assertEqual(self.draft_state(keys)['state'], 'unavailable')  # The text draft path still refuses pictures, unchanged.
        with no_convert(), no_pages(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            self.assertEqual(pdfm.prepare(self.store, self.now, 0), dict(used=0, failed=0))
        facts = self.facts(); consumers = self.consumers(); calls = []

        def model(text, images, **kw):
            context = json.loads(text)
            self.assertEqual(context['source_message']['id'], keys['message_id'])
            original = context['original_pdf']
            self.assertEqual((original['mime'], original['name'], original['page_count'], original['conversion']),
                             (DOCX_MIME, '虚构练习卷.docx', 11, pdfm.CONVERSION))
            calls.append((original['pages'], original['unprocessed_pages'], [i['mime'] for i in images], kw))
            return dict(DRAFT, title='第%s页' % original['pages'])
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', side_effect=model) as m:
            for index, expected in enumerate(BATCHES):
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=index)), dict(used=1, failed=0))
                pages, left, mimes, kw = calls[-1]
                self.assertEqual((pages, left, mimes), (expected, list(range(expected[-1] + 1, 12)), ['image/png'] * len(expected)))
                self.assertIs(kw['school_material'], True); self.assertEqual(kw['target_child'], '示例甲'); self.assertNotIn('documents', kw)
                self.assertEqual(len(self.converted), index + 1)  # One conversion per round; no converted copy is kept anywhere.
                shown = self.view(keys)
                self.assertEqual((shown['page_count'], [b['pages'] for b in shown['batches']]), (11, BATCHES[:index + 1]))
                self.assertEqual((shown['processed_pages'], shown['pending_pages']), (list(range(1, expected[-1] + 1)), list(range(expected[-1] + 1, 12))))
                self.assertEqual((shown['complete'], shown['state'], shown['original']), (index == 3, 'ready' if index == 3 else 'pending', 'docx'))
            with no_convert(), no_pages():  # Complete: no conversion, no pdfinfo, no render, no model, no job attempt.
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=9)), dict(used=0, failed=0))
            self.assertEqual(m.call_count, 4)
        shown = self.view(keys)
        self.assertEqual(([b['draft']['title'] for b in shown['batches']], shown['explanation']), (['第%s页' % b for b in BATCHES], ''))
        self.assertEqual((self.facts(), self.consumers(), self.rows('SELECT name FROM sqlite_master')), (facts, consumers, tables))
        self.assertEqual([(r[0], r[2]) for r in self.progress()], [(1, 11), (4, 11), (7, 11), (10, 11)])
        with self.store._db() as c, no_convert(), no_pages():
            evidence = pdfm.complete_evidence(self.store, c, *self.store._message_context(c, keys))
        self.assertEqual((evidence['mime'], evidence['original'], evidence['conversion'], evidence['name'], evidence['page_count'],
                          [b['pages'] for b in evidence['batches']]), (DOCX_MIME, 'docx', pdfm.CONVERSION, '虚构练习卷.docx', 11, BATCHES))

    def test_conversion_failure_and_missing_soffice_save_retryable_failures_keeping_groups(self):
        keys = self.school_fragment('英语：阅读所附材料。'); self.link(keys, self.seed_docx('b' * 32)); seen = []
        model = lambda text, images, **kw: seen.append(json.loads(text)['original_pdf']['pages']) or DRAFT
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', side_effect=model):
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
        with patch.object(family_media, 'docx_pdf', side_effect=family_media.MediaError('process_failed')), no_pages(), \
                patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=1)), dict(used=1, failed=1))
        shown = self.view(keys)
        self.assertEqual((shown['state'], shown['processed_pages'], shown['pending_pages'], shown['explanation']),
                         ('error', [1, 2, 3], list(range(4, 12)), pdfm.FAILED_DOCX))
        self.assertIn('process_failed', self.rows("SELECT error FROM agent_jobs WHERE id LIKE 'pdf-material:%'")[0][0])
        with no_convert(), no_pages():  # Back-off of the same job: nothing converted, rendered or called.
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=2)), dict(used=0, failed=0))
        with patch.object(family_media.shutil, 'which', return_value=None), no_pages(), \
                patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):  # The real docx_pdf without soffice.
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=7)), dict(used=1, failed=1))
        self.assertIn('process_unavailable', self.rows("SELECT error FROM agent_jobs WHERE id LIKE 'pdf-material:%'")[0][0])
        self.assertEqual((self.view(keys)['state'], self.view(keys)['processed_pages']), ('error', [1, 2, 3]))
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', side_effect=model):
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=20)), dict(used=1, failed=0))
        self.assertEqual((seen, [b['pages'] for b in self.view(keys)['batches']]), ([[1, 2, 3], [4, 5, 6]], [[1, 2, 3], [4, 5, 6]]))

    def test_page_count_change_between_conversions_is_refused_before_any_model_call(self):
        keys = self.school_fragment('数学：见附件。'); self.link(keys, self.seed_docx('c' * 32))
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', return_value=DRAFT):
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
        with renderer(12), self.converter(test_pdf.build_pdf(12)), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=1)), dict(used=1, failed=1))
        shown = self.view(keys)
        self.assertEqual((shown['state'], shown['processed_pages'], shown['page_count'], shown['complete']), ('error', [1, 2, 3], 11, False))
        self.assertIn('pdf_page_count_changed', self.rows("SELECT error FROM agent_jobs WHERE id LIKE 'pdf-material:%'")[0][0])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_pdf_material'), [(1,)])

    def test_change_during_conversion_or_after_render_sends_nothing_and_progress_resumes(self):
        keys = self.school_fragment('数学：见附件。'); docx = self.seed_docx('d' * 32); self.link(keys, docx)
        other_bytes = layout_docx('题目见上图'); self.assertEqual(len(other_bytes), len(DOCX_LAYOUT)); self.assertNotEqual(other_bytes, DOCX_LAYOUT)

        def correct():
            with self.store._db() as c:
                c.execute('BEGIN IMMEDIATE')
                payload = json.loads(c.execute('SELECT payload FROM agent_messages WHERE id=?', (keys['message_id'],)).fetchone()['payload'])
                payload['text'] += '（家长更正）'
                c.execute('UPDATE agent_messages SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), keys['message_id']))
        cases = [(lambda: self.write_config(enabled=False), lambda: self.assertFalse(self.store._config()['enabled']), self.write_config),
                 (lambda: self.link(keys, docx, 'detach'),
                  lambda: self.assertEqual(self.rows('SELECT * FROM agent_message_attachments WHERE upload_id=?', docx), []),
                  lambda: self.link(keys, docx)),
                 (correct, lambda: self.assertIn('家长更正', self.store.message(keys, dict)['message']['text']), lambda: None),
                 (lambda: (self.data / 'uploads' / docx).write_bytes(other_bytes),  # Same size and name, different bytes.
                  lambda: self.assertEqual((self.data / 'uploads' / docx).read_bytes(), other_bytes),
                  lambda: (self.data / 'uploads' / docx).write_bytes(DOCX_LAYOUT))]
        for index, (change, applied, restore) in enumerate(cases):  # Changed while LibreOffice runs: nothing is probed, rendered or sent.
            with self.converter(during=change), no_pages(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=index)), dict(used=0, failed=0))
            applied(); self.assertEqual(len(self.converted), index + 1)
            self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_pdf_material'), [(0,)])
            self.assertEqual(self.rows("SELECT * FROM agent_jobs WHERE id LIKE 'pdf-material:%'"), [])
            restore()
        real = family_pdf.render_pages

        def rendered_then_detached(body, pages, deadline=family_pdf.DEADLINE_SECONDS):
            result = real(body, pages, deadline); self.link(keys, docx, 'detach'); return result
        with renderer(), self.converter(), patch.object(family_pdf, 'render_pages', side_effect=rendered_then_detached) as r, \
                patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model after a change')) as m:
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=4)), dict(used=0, failed=0))
        self.assertEqual((r.call_count, m.call_count, len(self.converted)), (1, 0, 5))
        self.assertEqual(self.rows('SELECT * FROM agent_message_attachments WHERE upload_id=?', docx), [])
        self.assertIsNone(self.view(keys)); self.link(keys, docx)
        other = self.seed_docx('e' * 32, name='别人的.docx'); self.claim_for_other_child(other)
        with self.assertRaises(agent.AgentError):
            self.link(keys, other)  # The real API rejects another child's DOCX first; then simulate a stale legacy association.
        with self.store._db() as c:
            c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', (keys['source_id'], keys['message_id'], other))
        self.assertEqual(self.view(keys)['state'], 'unavailable')
        with no_convert(), no_pages(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=5)), dict(used=0, failed=0))
        with self.store._db() as c:
            c.execute('DELETE FROM agent_message_attachments WHERE upload_id=?', (other,))
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:  # Restored: continues with one call.
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=6)), dict(used=1, failed=0))
        self.assertEqual((m.call_count, self.view(keys)['processed_pages']), (1, [1, 2, 3]))

    def test_get_is_read_only_and_plain_rejected_multiple_or_mixed_docx_never_convert(self):
        keys = self.school_fragment('数学：见附件。'); docx = self.seed_docx('f' * 32); self.link(keys, docx)
        self.view(keys); before = self.snapshot(); sql = []; original = self.store._db

        @contextlib.contextmanager
        def traced():
            with original() as c:
                c.set_trace_callback(sql.append); yield c
        with patch.object(self.store, '_db', traced), no_convert(), no_render(), no_pages(), \
                patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model in GET')):
            shown = self.view(keys)
            with original() as c:
                self.assertIsNone(pdfm.complete_evidence(self.store, c, *self.store._message_context(c, keys)))
        self.assertFalse(any(q.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'REPLACE')) for q in sql), sql)
        self.assertEqual((shown['state'], shown['original'], shown['page_count'], shown['complete']), ('pending', 'docx', None, False))
        self.assertEqual(self.snapshot(), before)
        with no_convert(), no_pages(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
            plain = self.school_fragment('语文：见附件文字通知。'); self.link(plain, self.seed_docx('1' * 32, DOCX_PLAIN, '文字通知.docx'))
            self.assertIsNone(self.view(plain)); self.assertEqual(self.draft_state(plain)['state'], 'pending')  # Plain text: the existing path, untouched.
            macro = self.school_fragment('英语：见附件。'); self.link(macro, self.seed_docx('2' * 32, DOCX_MACRO, '含宏.docx'))
            self.assertIsNone(self.view(macro)); self.assertIn('含宏', self.draft_state(macro)['explanation'])  # Refused there; never converted here.
            self.link(keys, docx, 'detach')
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=0, failed=0))
            self.link(keys, docx); second = self.seed_docx('3' * 32, DOCX_PLAIN, '第二份.docx'); self.link(keys, second)
            shown = self.view(keys); self.assertEqual(shown['state'], 'unavailable'); self.assertIn('多个DOCX', shown['explanation'])
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=0, failed=0))
            self.link(keys, second, 'detach'); image = self.seed_upload('4' * 32, test_media.png(width=97)); self.link(keys, image)
            shown = self.view(keys); self.assertEqual(shown['state'], 'unavailable'); self.assertIn('单独关联', shown['explanation'])
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=0, failed=0))
            self.link(keys, image, 'detach'); pdf = self.seed_pdf('5' * 32); self.link(keys, pdf)
            shown = self.view(keys); self.assertEqual(shown['state'], 'unavailable'); self.assertIn('混在', shown['explanation'])
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=0, failed=0))
            self.link(keys, pdf, 'detach'); self.assertEqual(self.view(keys)['state'], 'pending')
        self.assertEqual(self.rows("SELECT * FROM agent_jobs WHERE id LIKE 'pdf-material:%'"), [])


    def correct_message(self, keys):
        with self.store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            payload = json.loads(c.execute('SELECT payload FROM agent_messages WHERE id=?', (keys['message_id'],)).fetchone()['payload'])
            payload['text'] += '（家长更正）'
            c.execute('UPDATE agent_messages SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), keys['message_id']))

    def test_change_between_claim_and_conversion_converts_probes_and_sends_nothing(self):
        keys = self.school_fragment('数学：见附件。'); docx = self.seed_docx('g' * 32); self.link(keys, docx)
        other_bytes = layout_docx('题目见上图'); real_job = self.store._job; claimed = []

        def lose_claim():
            with self.store._db() as c:
                c.execute("DELETE FROM agent_jobs WHERE id LIKE 'pdf-material:%'")
        cases = [(lambda: self.write_config(enabled=False), self.write_config),
                 (lambda: self.link(keys, docx, 'detach'), lambda: self.link(keys, docx)),
                 (lambda: (self.data / 'uploads' / docx).write_bytes(other_bytes), lambda: (self.data / 'uploads' / docx).write_bytes(DOCX_LAYOUT)),
                 (lose_claim, lambda: None),
                 (lambda: self.correct_message(keys), lambda: None)]
        for index, (change, restore) in enumerate(cases):
            def claim_then_change(key, value, now, **kw):  # The real claim is taken; the parent acts before LibreOffice would start.
                fp = real_job(key, value, now, **kw)
                self.assertTrue(fp); claimed.append(fp); change()
                return fp
            with patch.object(self.store, '_job', side_effect=claim_then_change), no_convert(), no_render(), no_pages(), \
                    patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model')):
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=index)), dict(used=0, failed=0))
            self.assertEqual(len(claimed), index + 1)  # The change callback really ran after a real claim: 0 conversion, 0 probe, 0 model.
            self.assertEqual((self.converted, self.rows('SELECT COUNT(*) FROM agent_pdf_material'),
                              self.rows("SELECT * FROM agent_jobs WHERE id LIKE 'pdf-material:%'")), ([], [(0,)], []))
            restore()
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:  # Restored: one conversion, one call.
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=9)), dict(used=1, failed=0))
        self.assertEqual((m.call_count, len(self.converted), self.view(keys)['processed_pages']), (1, 1, [1, 2, 3]))

    def test_change_while_docx_model_runs_discards_result_and_reattachment_resumes(self):
        keys = self.school_fragment('数学：见附件。'); docx = self.seed_docx('h' * 32); self.link(keys, docx)
        replacement = self.seed_docx('i' * 32, layout_docx('题目见上图'), '替换件.docx'); entered = []
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', return_value=DRAFT):
            self.assertEqual(pdfm.prepare(self.store, self.now), dict(used=1, failed=0))
        before = self.rows('SELECT * FROM agent_pdf_material'); self.assertEqual(len(before), 1)

        def relink():
            self.link(keys, docx, 'detach'); self.link(keys, replacement)

        def relink_back():
            self.link(keys, replacement, 'detach'); self.link(keys, docx)
        cases = [(lambda: self.write_config(enabled=False), self.write_config), (relink, relink_back),
                 (lambda: self.correct_message(keys), lambda: None)]
        for index, (change, restore) in enumerate(cases):
            def model(text, images, **kw):  # The model really runs and returns a draft while the parent acts.
                entered.append(json.loads(text)['original_pdf']['pages']); change(); return DRAFT
            with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', side_effect=model) as m:
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=index + 1)), dict(used=1, failed=0))
            self.assertEqual((m.call_count, entered[-1], len(self.converted)), (1, [4, 5, 6], index + 2))
            self.assertEqual(self.rows('SELECT * FROM agent_pdf_material'), before)  # The returned draft is discarded; nothing else moves.
            self.assertEqual(self.rows("SELECT * FROM agent_jobs WHERE id LIKE 'pdf-material:%'"), [])
            if index == 1:  # Re-linked to another original: no group of the old one is shown for it.
                self.assertEqual((self.view(keys)['upload_id'], self.view(keys)['processed_pages']), (replacement, []))
            restore()
            if index < 2:
                self.assertEqual((self.view(keys)['upload_id'], self.view(keys)['processed_pages']), (docx, [1, 2, 3]))  # Restored: saved group is back.
        self.assertEqual(self.view(keys)['processed_pages'], [])  # Corrected message: old groups hidden; restart from page one.
        with renderer(), self.converter(), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:
            self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=9)), dict(used=1, failed=0))
        self.assertEqual((m.call_count, self.view(keys)['processed_pages'], len(self.converted)), (1, [1, 2, 3], 5))

    def test_full_coverage_get_is_sql_read_only_and_converted_metadata_never_enters_fingerprint(self):
        keys = self.school_fragment('数学：见附件。'); docx = self.seed_docx('j' * 32); self.link(keys, docx); outputs = []
        head, tail = PDF.rsplit(b'%%EOF', 1)

        def convert(body, *, soffice=None):  # Every LibreOffice run yields different bytes (CreationDate/ID); the DOCX stays the original.
            self.assertTrue(body.startswith(b'PK\x03\x04'))
            outputs.append(head + b'%% CreationDate D:2026092300000%d\n%%EOF' % len(outputs) + tail)
            return outputs[-1]
        with renderer(), patch.object(family_media, 'docx_pdf', side_effect=convert), patch.object(family_llm, 'extract_draft', return_value=DRAFT) as m:
            for index in range(4):
                self.assertEqual(pdfm.prepare(self.store, self.now + dt.timedelta(minutes=index)), dict(used=1, failed=0))
        fingerprints = self.rows('SELECT DISTINCT fingerprint FROM agent_pdf_material')
        self.assertEqual((m.call_count, len(set(outputs)), len(fingerprints)), (4, 4, 1))  # Four different PDFs, one original fingerprint.
        self.assertEqual([(r[0], r[2]) for r in self.progress()], [(1, 11), (4, 11), (7, 11), (10, 11)])
        before = self.snapshot(); sql = []; original = self.store._db

        @contextlib.contextmanager
        def traced():
            with original() as c:
                c.set_trace_callback(sql.append); yield c
        with patch.object(self.store, '_db', traced), no_convert(), no_render(), no_pages(), \
                patch.object(family_llm, 'extract_draft', side_effect=AssertionError('model in GET')):
            shown = self.view(keys)
            with traced() as c:
                evidence = pdfm.complete_evidence(self.store, c, *self.store._message_context(c, keys))
        self.assertTrue(sql)
        self.assertFalse(any(q.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'REPLACE')) for q in sql), sql)
        self.assertEqual((shown['complete'], shown['state'], shown['processed_pages'], shown['original'], shown['mime'], shown['explanation']),
                         (True, 'ready', list(range(1, 12)), 'docx', DOCX_MIME, ''))
        self.assertEqual((evidence['fingerprint'], evidence['page_count'], [b['pages'] for b in evidence['batches']], evidence['original'],
                          evidence['mime'], evidence['conversion'], evidence['upload_id']),
                         (fingerprints[0][0], 11, BATCHES, 'docx', DOCX_MIME, pdfm.CONVERSION, docx))
        self.assertEqual((self.snapshot(), len(outputs)), (before, 4))  # GET: no write, no conversion, no probe, no render, no model.


for _name in [n for n in dir(PdfMaterialTests) if n.startswith('test_')]:
    setattr(DocxMaterialTests, _name, None)

if __name__ == '__main__':
    unittest.main()

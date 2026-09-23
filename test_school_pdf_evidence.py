"""Synthetic check: a completely整理 PDF original feeds this pending school candidate's parent-reviewable draft.
Fictional family, QQ fragment notice and 11-page synthetic PDF; every model reply is a fixture; no render, network or real material."""
import datetime as dt
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import family_llm
import family_pdf_material as pdfm
import test_pdf
import test_pdf_material
from test_pdf_material import BATCHES, DOCX_LAYOUT, DOCX_MIME, DRAFT, layout_docx, no_convert, no_pages, no_render

TEXT = '数学：完成所附练习卷第1至11页。'
DETACH = 'detach'


def draft(**changes):
    return dict(dict(title='数学：完成练习卷第1至11页', goal='完成练习卷第1至11页。', advice='', state='ready', reason='原件写明练习范围。',
                     purpose='learning', submission='', change='new', target_id=''), **changes)


class SchoolPdfEvidenceTests(test_pdf_material.Base):
    seed_pdf = test_pdf_material.PdfMaterialTests.seed_pdf
    rows = test_pdf_material.PdfMaterialTests.rows
    set_sources = test_pdf_material.PdfMaterialTests.set_sources
    seed_docx = test_pdf_material.DocxMaterialTests.seed_docx

    def setUp(self):
        super().setUp()
        self.keys = self.school_fragment(TEXT); self.pdf = self.seed_pdf('a' * 32); self.link(self.keys, self.pdf)

    def seed_groups(self, batches=BATCHES, note=DRAFT['note'], keys=None):
        with self.store._db() as c:
            source, message = self.store._message_context(c, keys or self.keys)
            fp = pdfm.pdf_input(self.store, c, source, message)['fingerprint']
            for pages in batches:
                payload = json.dumps(dict(DRAFT, note=note, title='第%s-%s页组' % (pages[0], pages[-1]), kind='school_material'), ensure_ascii=False)
                c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',
                          (source['id'], message['id'], fp, pages[0], json.dumps(pages), 11, payload, self.now.isoformat()))
        return fp

    def candidate(self, keys=None, ident='pdf-1', brief=None, title=None):
        keys = keys or self.keys
        with self.store._db() as c:  # quotes its own fragment's recognized text (still a screenshot), never another notice's
            text = json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?', (keys['source_id'], keys['message_id'])).fetchone()[0])['text']
        title = title or '待核对：' + text.splitlines()[-1]
        if brief is None:
            brief = dict(title='', goal='', advice='', state='review', reason='仅截图可见内容，请核对原图和附件。',
                         policy=agent.SCHOOL_TASK_POLICY, change='new', target_id='')
        item = dict(child_id='child-1', kind='school', title=title, body='学校', due='',
                    evidence=[dict(ref='message:%s:%s' % (keys['source_id'], keys['message_id']), text=text)],
                    plan=dict(school_task=brief, school_messages=[dict(source_id=keys['source_id'], message_id=keys['message_id'])]))
        key = 'synthetic-pdf:' + ident; self.store._save(key, self.store._job(key, ident, self.now), [item], self.now)
        with self.store._db() as c:
            return c.execute('SELECT id FROM agent_items WHERE job_id=?', (key,)).fetchone()[0]

    def item(self, ident):
        with self.store._db() as c:
            return dict(c.execute('SELECT * FROM agent_items WHERE id=?', (ident,)).fetchone())

    def brief(self, ident):
        return json.loads(self.item(ident)['plan']).get('school_task', {})

    def count(self, table):
        return self.rows('SELECT COUNT(*) FROM ' + table)[0][0]

    def material(self, keys=None):
        try:
            with self.store._db() as c:
                source, message = self.store._message_context(c, keys or self.keys)
                return pdfm.complete_evidence(self.store, c, source, message)
        except agent.AgentError: return None

    def refresh(self, reply, budget=1, minutes=0):
        calls = []

        def model(messages, *args, **kwargs):
            calls.append(messages)
            if isinstance(reply, Exception): raise reply
            return reply(messages) if callable(reply) else reply
        with no_render(), patch.object(family_llm, 'extract_draft', side_effect=AssertionError('no page-group model call here')), \
                patch.object(family_llm, '_chat_json', side_effect=model):
            result = agent._refresh_school(self.app, self.store, self.now + dt.timedelta(minutes=minutes), budget)
        return result, calls

    def test_complete_pdf_feeds_one_call_and_waits_for_the_parent(self):
        ident = self.candidate(); before = self.item(ident)
        self.assertEqual(self.refresh(draft()), (dict(used=0, failed=0, created=0), []))  # no saved group: nothing goes out
        self.seed_groups(BATCHES[:3])
        result, calls = self.refresh(draft())
        self.assertEqual((result['used'], calls, self.item(ident)), (0, [], before))  # 9 of 11 pages is not whole-document evidence
        with self.store._db() as c:
            c.execute('DELETE FROM agent_pdf_material')
        self.seed_groups()
        self.assertEqual((self.refresh(draft(), budget=0), self.item(ident)), ((dict(used=0, failed=0, created=0), []), before))
        result, calls = self.refresh(draft())
        self.assertEqual((result['used'], result['failed'], result['created'], len(calls)), (1, 0, 0, 1))
        system, user = calls[0][0]['content'], json.loads(calls[0][1]['content'])
        self.assertIn(agent.SCHOOL_PDF_PROMPT, system); self.assertNotIn(agent.SCHOOL_PAGE_PROMPT, system); self.assertNotIn('pages', user)
        doc = user['pdf_material'][0]
        self.assertEqual((doc['page_count'], doc['processed_pages'], doc['complete'], [g['pages'] for g in doc['groups']], doc['omitted_groups'], doc['truncated_groups']),
                         (11, list(range(1, 12)), True, BATCHES, [], []))
        self.assertTrue(all(DRAFT['note'] in g['text'] and not g['text_truncated'] for g in doc['groups']))
        brief = self.brief(ident); row = self.item(ident)
        self.assertEqual((row['state'], row['task_id'] or '', self.count('manual_tasks'), row['title']), ('pending', '', 0, draft()['title']))
        self.assertTrue(brief['pdf_evidence']['fingerprint']); self.assertEqual(brief['pdf_evidence']['documents'][0]['sent'], 4)
        self.assertIn('已参考PDF原件整理', brief['reason']); self.assertIn('不是老师原文', brief['reason'])
        with self.assertRaises(agent.AgentError) as auto:
            self.store.act(dict(id=ident, action='accept', expected_updated=row['updated']), school_auto=True)
        self.assertEqual(auto.exception.status, 409)
        saved = self.item(ident); result, calls = self.refresh(draft(), minutes=1)
        self.assertEqual((result['used'], calls, self.item(ident), self.count('agent_items')), (0, [], saved, 1))  # same evidence: no call, no write
        accepted = self.store.act(dict(id=ident, action='accept'))  # the parent accepts once through the ordinary path
        self.assertEqual((accepted['state'], self.count('manual_tasks')), ('accepted', 1))
        again = self.store.act(dict(id=ident, action='accept'))
        self.assertEqual((again['state'], again['task_id'], self.count('manual_tasks')), ('accepted', accepted['task_id'], 1))
        accepted_row = self.item(ident); result, calls = self.refresh(draft(), minutes=2)
        self.assertEqual((result['used'], calls, self.item(ident)), (0, [], accepted_row))

    def test_revoked_detached_or_changed_original_hides_draft_and_refuses_acceptance(self):
        self.seed_groups(); ident = self.candidate()
        self.assertEqual(self.refresh(draft())[0]['used'], 1); fingerprint = self.brief(ident)['pdf_evidence']['fingerprint']
        self.set_sources(False)
        result, calls = self.refresh(draft(), minutes=1); brief = self.brief(ident)
        self.assertEqual((result['used'], calls, brief['state'], brief['reason'], brief['pdf_evidence']['fingerprint']), (0, [], 'review', agent._PDF_STALE, ''))
        with self.assertRaises(agent.AgentError) as refused: self.store.act(dict(id=ident, action='accept'))
        self.assertEqual((refused.exception.status, refused.exception.code, self.count('manual_tasks')), (409, 'pdf_evidence_stale', 0))
        self.set_sources(True)
        result, calls = self.refresh(draft(), minutes=2)
        self.assertEqual((result['used'], len(calls), self.brief(ident)['pdf_evidence']['fingerprint']), (1, 1, fingerprint))  # restored: one new round, same evidence
        self.link(self.keys, self.pdf, action=DETACH)
        result, calls = self.refresh(draft(), minutes=3)
        self.assertEqual((result['used'], calls, self.brief(ident)['state'], self.brief(ident)['pdf_evidence']['fingerprint']), (0, [], 'review', ''))
        self.link(self.keys, self.pdf)
        self.assertEqual(self.refresh(draft(), minutes=4)[0]['used'], 1)
        (self.data / 'uploads' / self.pdf).write_bytes(test_pdf.build_pdf(11, width=2001))  # same size, other bytes: another original
        with self.assertRaises(agent.AgentError) as refused: self.store.act(dict(id=ident, action='accept'))  # rechecked inside the acceptance transaction
        self.assertEqual((refused.exception.status, refused.exception.code, self.item(ident)['state'], self.count('manual_tasks')), (409, 'pdf_evidence_stale', 'pending', 0))
        result, calls = self.refresh(draft(), minutes=5)
        self.assertEqual((result['used'], calls, self.brief(ident)['pdf_evidence']['fingerprint']), (0, [], ''))

    def test_inflight_detach_or_dismissal_discards_the_result(self):
        self.seed_groups(); ident = self.candidate(); before = self.item(ident); mutated = []

        def detach(messages):
            self.link(self.keys, self.pdf, action=DETACH)
            mutated.append(self.rows('SELECT COUNT(*) FROM agent_message_attachments WHERE upload_id=?', self.pdf)); return draft()
        result, calls = self.refresh(detach)
        self.assertEqual((result['used'], result['failed'], len(calls), mutated, self.item(ident)), (1, 0, 1, [[(0,)]], before))
        self.assertEqual(self.rows('SELECT done,error FROM agent_jobs WHERE id=?', 'school-task:' + ident), [(1, '')])
        self.link(self.keys, self.pdf)
        self.assertEqual(self.refresh(draft(), minutes=1)[0]['used'], 1); self.assertTrue(self.brief(ident)['pdf_evidence']['fingerprint'])
        other = self.candidate(ident='pdf-2')  # a second candidate on the same notice, dismissed while its model round runs

        def dismiss(messages):
            self.store.act(dict(id=other, action='dismiss')); mutated.append(self.item(other)['state']); return draft()
        result, calls = self.refresh(dismiss, minutes=2)
        self.assertEqual((result['used'], len(calls), mutated[-1], self.item(other)['state'], self.brief(other).get('pdf_evidence')),
                         (1, 1, 'dismissed', 'dismissed', None))

    def test_failure_keeps_retry_backoff_and_same_evidence_causes_no_repeat(self):
        self.seed_groups(); ident = self.candidate()
        result, calls = self.refresh(family_llm.LLMDraftError('合成失败'))
        self.assertEqual((result['used'], result['failed'], len(calls), self.brief(ident).get('pdf_evidence')), (1, 1, 1, None))
        job = self.rows('SELECT attempts,done,next_try FROM agent_jobs WHERE id=?', 'school-task:' + ident)[0]
        self.assertEqual((job[0], job[1]), (1, 0)); self.assertTrue(job[2])
        self.assertEqual(self.refresh(draft(), minutes=1)[1], [])  # inside the backoff window nothing is retried
        result, calls = self.refresh(draft(), minutes=6)
        self.assertEqual((result['used'], len(calls), self.brief(ident)['pdf_evidence']['documents'][0]['page_count']), (1, 1, 11))

    def test_long_group_notes_are_clipped_and_omissions_declared_apart_from_coverage(self):
        self.seed_groups(note='摘' * 3000); ident = self.candidate()
        result, calls = self.refresh(draft())
        doc = json.loads(calls[0][1]['content'])['pdf_material'][0]
        self.assertEqual((doc['complete'], doc['processed_pages'], [g['pages'] for g in doc['groups']], doc['truncated_groups'], doc['omitted_groups']),
                         (True, list(range(1, 12)), BATCHES[:2], ['第4–6页'], ['第7–9页', '第10–11页']))
        self.assertEqual(sum(len(g['text']) for g in doc['groups']), agent.PDF_TEXT_LIMIT)
        brief = self.brief(ident); record = brief['pdf_evidence']['documents'][0]
        self.assertEqual((brief['state'], record['groups'], record['sent'], record['omitted'], record['truncated']), ('review', 4, 2, ['第7–9页', '第10–11页'], ['第4–6页']))
        self.assertIn('共11页已逐组整理，送核2/4组', brief['reason']); self.assertIn('第7–9页', brief['reason']); self.assertIn('未全部送核', brief['reason'])

    def test_change_confirmation_rechecks_pdf_evidence_and_plain_notice_keeps_old_flow(self):
        other = self.school_fragment('语文：完成虚构习作一篇。')
        target_item = self.candidate(keys=other, ident='target', brief=dict(draft(), policy=agent.SCHOOL_TASK_POLICY), title='语文：完成虚构习作一篇')
        accepted = self.store.act(dict(id=target_item, action='accept'))  # a notice without PDF keeps the ordinary path
        with self.app.connect() as c:
            target = next(t for t in self.app.tasks(c) if t['id'] == accepted['task_id'])
            original = dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (target['id'],)).fetchone())
        self.seed_groups(); ident = self.candidate()
        result, calls = self.refresh(draft(change='update', target_id=target['id'], state='review', reason='原件更正范围。'))
        self.assertEqual((result['used'], len(calls), self.brief(ident)['change'], self.brief(ident)['target_id'], self.count('manual_tasks')), (1, 1, 'update', target['id'], 1))
        obj = dict(action='school_change', id=ident, target_id=target['id'], change='update', title='更正要求', body='新要求', due='',
                   expected_updated=self.item(ident)['updated'], target_version=target['focus']['version'], target_updated='')
        self.link(self.keys, self.pdf, action=DETACH)
        with self.assertRaises(agent.AgentError) as stale: agent.apply_school_change(self.app, self.store, obj)
        self.assertEqual((stale.exception.status, stale.exception.code, self.item(ident)['state']), (409, 'pdf_evidence_stale', 'pending'))
        with self.assertRaises(agent.AgentError) as stale: self.store.act(dict(id=ident, action='accept', school_new=True))
        self.assertEqual((stale.exception.status, stale.exception.code, self.count('manual_tasks')), (409, 'pdf_evidence_stale', 1))
        with self.app.connect() as c:
            self.assertEqual(dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (target['id'],)).fetchone()), original)
        self.link(self.keys, self.pdf)
        outcome = agent.apply_school_change(self.app, self.store, dict(obj, expected_updated=self.item(ident)['updated']))
        self.assertEqual((outcome['school_changed'], outcome['task_id'], self.item(ident)['state'], self.count('manual_tasks')), (True, target['id'], 'accepted', 1))
        with self.app.connect() as c:
            changed = dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (target['id'],)).fetchone())
        self.assertNotEqual(changed, original); self.assertIn(TEXT, changed['source'])

    def test_change_during_job_claim_causes_no_model_call_and_same_evidence_recovers_once(self):
        self.seed_groups(); ident = self.candidate(); before = self.item(ident); real = self.store._job; job = 'school-task:' + ident

        def claim(mutate):
            def claimed(*args, **kwargs):
                fp = real(*args, **kwargs); mutate(); return fp
            return claimed
        with patch.object(self.store, '_job', side_effect=claim(lambda: self.set_sources(False))):  # authorization revoked after the claim
            result, calls = self.refresh(draft())
        self.assertIsNone(self.material())
        self.assertEqual((result['used'], result['failed'], calls, self.item(ident), self.rows('SELECT done,error FROM agent_jobs WHERE id=?', job)), (0, 0, [], before, [(1, '')]))
        self.assertEqual((self.refresh(draft(), minutes=1)[1], self.item(ident)), ([], before))  # still revoked: nothing repeats
        self.set_sources(True)
        with patch.object(self.store, '_job', side_effect=claim(lambda: self.link(self.keys, self.pdf, action=DETACH))):  # original detached after the claim
            result, calls = self.refresh(draft(), minutes=2)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_message_attachments WHERE upload_id=?', self.pdf), [(0,)])
        self.assertEqual((result['used'], calls, self.item(ident)), (0, [], before))
        self.link(self.keys, self.pdf)
        with patch.object(self.store, '_job', side_effect=claim(lambda: self.store.act(dict(id=ident, action='dismiss')))):  # candidate dismissed after the claim
            result, calls = self.refresh(draft(), minutes=3)
        self.assertEqual((result['used'], calls, self.item(ident)['state'], self.brief(ident).get('pdf_evidence')), (0, [], 'dismissed', None))
        other = self.candidate(ident='pdf-2')
        result, calls = self.refresh(draft(), minutes=4)  # the same evidence, unchanged this time: exactly one round
        self.assertEqual((result['used'], len(calls), self.count('manual_tasks')), (1, 1, 0)); self.assertTrue(self.brief(other)['pdf_evidence']['fingerprint'])
        saved = self.item(other)
        self.assertEqual((self.refresh(draft(), minutes=5)[1], self.item(other)), ([], saved))

    def test_group_label_never_implies_pages_between_noncontiguous_pages(self):
        self.assertEqual([agent._span(p) for p in ([3], [1, 2, 3], [1, 2, 5, 7, 8], [4, 2])], ['第3页', '第1–3页', '第1–2、5、7–8页', '第2、4页'])

    def test_source_message_and_authorization_changes_before_and_after_model(self):
        self.seed_groups(); ident = self.candidate(); before = self.item(ident)
        config = self.data / 'agent.json'; original_config = config.read_text()
        sql = 'SELECT payload FROM agent_messages WHERE source_id=? AND id=?'
        args = (self.keys['source_id'], self.keys['message_id'])
        with self.store._db() as c: original_message = c.execute(sql, args).fetchone()[0]
        real = self.store._job
        for phase in ('claim', 'model'):
            for what in ('message', 'source', 'authorization'):
                with self.subTest(phase=phase, what=what):
                    changed = []
                    def mutate():
                        if what == 'message':
                            payload = dict(json.loads(original_message), text=json.loads(original_message)['text'] + '（实际更正）')
                            with self.store._db() as c:
                                c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?', (json.dumps(payload, ensure_ascii=False),) + args)
                                changed.append(c.execute(sql, args).fetchone()[0] != original_message)
                        else:
                            value = json.loads(original_config)
                            source = next(s for s in value['sources'] if s['id'] == self.keys['source_id'])
                            source['name' if what == 'source' else 'enabled'] = '实际更名' if what == 'source' else False
                            config.write_text(json.dumps(value, ensure_ascii=False))
                            changed.append(config.read_text() != original_config)
                    def claimed(*a, **kw):
                        fp = real(*a, **kw); mutate(); return fp
                    def model(messages):
                        mutate(); return draft()
                    if phase == 'claim':
                        with patch.object(self.store, '_job', side_effect=claimed): result, calls = self.refresh(draft())
                    else: result, calls = self.refresh(model)
                    self.assertEqual((changed, result['used'], result['failed'], len(calls), self.item(ident)),
                                     ([True], int(phase == 'model'), 0, int(phase == 'model'), before))
                    config.write_text(original_config)
                    with self.store._db() as c:
                        c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?', (original_message,) + args)

    def test_complete_word_original_is_named_as_word_with_converted_pages_and_parent_confirms(self):
        """A layout Word original: same page-group path, but the model and the parent are told it is Word, by its original name,
        with converted-PDF page numbers; the 6000-char summary limit still stays a separate claim from whole-original coverage."""
        keys = self.school_fragment('英语：完成所附Word练习。'); docx = self.seed_docx('d' * 32); self.link(keys, docx)
        ident = self.candidate(keys=keys, ident='docx-1'); before = self.item(ident)
        with no_convert(), no_pages():  # zero LibreOffice, pdfinfo or render anywhere in the candidate path
            self.assertEqual(self.refresh(draft()), (dict(used=0, failed=0, created=0), []))  # no saved group: nothing goes out
            self.seed_groups(BATCHES[:3], keys=keys)
            self.assertEqual((self.refresh(draft())[0]['used'], self.item(ident)), (0, before))  # partial coverage: no derived call
            with self.store._db() as c:
                c.execute('DELETE FROM agent_pdf_material')
            self.seed_groups(keys=keys); evidence = self.material(keys)
            self.assertEqual((evidence['original'], evidence['mime'], evidence['conversion']), ('docx', DOCX_MIME, pdfm.CONVERSION))
            self.assertEqual(self.refresh(draft(), budget=0), (dict(used=0, failed=0, created=0), []))
            result, calls = self.refresh(draft())
            self.assertEqual((result['used'], result['failed'], result['created'], len(calls)), (1, 0, 0, 1))
            system, user = calls[0][0]['content'], json.loads(calls[0][1]['content'])
            self.assertIn(agent.SCHOOL_PDF_PROMPT, system); self.assertIn('可能与Word中显示的分页不同', system); self.assertIn('不是老师原文', system)
            doc = user['pdf_material'][0]
            self.assertEqual((doc['original'], doc['mime'], doc['conversion'], doc['name'], doc['page_count'], doc['processed_pages'], doc['complete'],
                              [g['pages'] for g in doc['groups']], doc['omitted_groups'], doc['truncated_groups']),
                             ('docx', DOCX_MIME, pdfm.CONVERSION, '虚构练习卷.docx', 11, list(range(1, 12)), True, BATCHES, [], []))
            brief = self.brief(ident); record = brief['pdf_evidence']['documents'][0]; row = self.item(ident)
            self.assertEqual((row['state'], row['task_id'] or '', self.count('manual_tasks'), brief['state']), ('pending', '', 0, 'review'))  # the source is an OCR screenshot, not a verified teacher message
            self.assertIn('仅截图可见内容', brief['reason'])
            self.assertEqual((record['original'], record['mime'], record['conversion'], record['name'], record['sent'], record['groups'], record['page_count']),
                             ('docx', DOCX_MIME, pdfm.CONVERSION, '虚构练习卷.docx', 4, 4, 11))
            for text in ('已参考Word原件整理', '可能与Word中显示的分页不同', '虚构练习卷.docx（转换后共11页已逐组整理，送核4/4组）', '不是老师原文', '不说明孩子完成情况'):
                self.assertIn(text, brief['reason'])
            self.assertNotIn('PDF原件', brief['reason'])
            with self.assertRaises(agent.AgentError) as auto:
                self.store.act(dict(id=ident, action='accept', expected_updated=row['updated']), school_auto=True)
            self.assertEqual(auto.exception.status, 409); self.assertEqual(self.count('manual_tasks'), 0)
            saved = self.item(ident)
            self.assertEqual((self.refresh(draft(), minutes=1), self.item(ident)), ((dict(used=0, failed=0, created=0), []), saved))  # same evidence: no call

            # Change a saved group so this is an actual new model round, not a deduplicated no-op.
            with self.store._db() as c:
                c.execute('UPDATE agent_pdf_material SET payload=? WHERE fingerprint=? AND first_page=1', (json.dumps(dict(DRAFT, note='新核对摘要', kind='school_material')), evidence['fingerprint']))
            def detach(messages):
                self.link(keys, docx, action=DETACH); return draft()
            self.assertEqual((self.refresh(detach, minutes=2)[0]['used'], self.item(ident)), (1, saved))  # detached in flight: result discarded
            self.link(keys, docx)
            self.assertEqual(self.refresh(draft(), minutes=3)[0]['used'], 1); self.assertTrue(self.brief(ident)['pdf_evidence']['fingerprint'])
            accepted = self.store.act(dict(id=ident, action='accept'))  # the parent explicitly adds it through the ordinary path
            self.assertEqual((accepted['state'], self.count('manual_tasks')), ('accepted', 1))
            with self.app.connect() as c:
                task = dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (accepted['task_id'],)).fetchone())
            self.assertEqual((task['child'], task['title'], self.item(ident)['state'], self.item(ident)['task_id']), ('示例甲', draft()['title'], 'accepted', accepted['task_id']))
            self.assertEqual(self.item(ident)['child_id'], 'child-1')
            again = self.store.act(dict(id=ident, action='accept'))
            self.assertEqual((again['state'], again['task_id'], self.count('manual_tasks')), ('accepted', accepted['task_id'], 1))
            self.assertEqual(self.refresh(draft(), minutes=4)[1], [])

    def test_word_original_change_confirmation_rechecks_and_names_word_when_stale(self):
        other = self.school_fragment('语文：完成虚构习作一篇。')
        target_item = self.candidate(keys=other, ident='target', brief=dict(draft(), policy=agent.SCHOOL_TASK_POLICY), title='语文：完成虚构习作一篇')
        accepted = self.store.act(dict(id=target_item, action='accept'))
        with self.app.connect() as c:
            target = next(t for t in self.app.tasks(c) if t['id'] == accepted['task_id'])
            original = dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (target['id'],)).fetchone())
        keys = self.school_fragment('语文：习作要求见所附Word。'); docx = self.seed_docx('e' * 32); self.link(keys, docx)
        self.seed_groups(keys=keys); ident = self.candidate(keys=keys, ident='docx-2')
        update = draft(change='update', target_id=target['id'], state='review', reason='原件更正范围。')
        with no_convert(), no_pages():
            result, calls = self.refresh(update); brief = self.brief(ident)
            self.assertEqual((result['used'], len(calls), brief['change'], brief['target_id'], brief['pdf_evidence']['documents'][0]['original'], self.count('manual_tasks')),
                             (1, 1, 'update', target['id'], 'docx', 1))
            self.assertIn('已参考Word原件整理', brief['reason'])
            obj = dict(action='school_change', id=ident, target_id=target['id'], change='update', title='更正要求', body='新要求', due='',
                       expected_updated=self.item(ident)['updated'], target_version=target['focus']['version'], target_updated='')
            (self.data / 'uploads' / docx).write_bytes(layout_docx('题目见上图'))  # same size, other bytes: another Word original
            with self.assertRaises(agent.AgentError) as stale: agent.apply_school_change(self.app, self.store, obj)
            self.assertEqual((stale.exception.status, stale.exception.code, self.item(ident)['state']), (409, 'pdf_evidence_stale', 'pending'))
            self.assertIn('Word原件整理已失效', str(stale.exception))
            with self.assertRaises(agent.AgentError) as stale: self.store.act(dict(id=ident, action='accept', school_new=True))
            self.assertEqual((stale.exception.status, stale.exception.code, self.count('manual_tasks')), (409, 'pdf_evidence_stale', 1))
            result, calls = self.refresh(update, minutes=1); brief = self.brief(ident)
            self.assertEqual((result['used'], calls, brief['state'], brief['reason'], brief['pdf_evidence']['fingerprint']),
                             (0, [], 'review', agent._ORIGINAL_STALE.format('Word'), ''))
            self.assertNotEqual(brief['reason'], agent._PDF_STALE)
            with self.app.connect() as c:
                self.assertEqual(dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (target['id'],)).fetchone()), original)
            (self.data / 'uploads' / docx).write_bytes(DOCX_LAYOUT)  # the original back: one round from the saved groups, no conversion
            self.assertEqual(self.refresh(update, minutes=2)[0]['used'], 1)
            outcome = agent.apply_school_change(self.app, self.store, dict(obj, expected_updated=self.item(ident)['updated']))
            self.assertEqual((outcome['school_changed'], outcome['task_id'], self.item(ident)['state'], self.count('manual_tasks')), (True, target['id'], 'accepted', 1))
            with self.app.connect() as c:
                changed = dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (target['id'],)).fetchone())
            self.assertNotEqual(changed, original); self.assertIn('语文：习作要求见所附Word。', changed['source'])


    def test_word_changes_before_and_during_model_use_the_shared_guard(self):
        self.link(self.keys, self.pdf, action=DETACH)
        self.pdf = self.seed_docx('f' * 32); self.link(self.keys, self.pdf)
        with no_convert(), no_pages():
            self.test_source_message_and_authorization_changes_before_and_after_model()

    def test_word_claim_detach_and_recovery_do_not_convert_or_call_early(self):
        self.link(self.keys, self.pdf, action=DETACH)
        self.pdf = self.seed_docx('f' * 32); self.link(self.keys, self.pdf)
        with no_convert(), no_pages():
            self.test_change_during_job_claim_causes_no_model_call_and_same_evidence_recovers_once()

    def test_word_full_coverage_does_not_hide_summary_omissions(self):
        self.link(self.keys, self.pdf, action=DETACH)
        self.pdf = self.seed_docx('f' * 32); self.link(self.keys, self.pdf)
        batches = [[1, 4, 7], [2, 5, 8], [3, 6, 9], [10, 11]]
        self.seed_groups(batches, note='摘' * 3000); ident = self.candidate()
        with no_convert(), no_pages():
            result, calls = self.refresh(draft())
        doc = json.loads(calls[0][1]['content'])['pdf_material'][0]
        self.assertEqual((result['used'], doc['original'], doc['complete'], doc['processed_pages']), (1, 'docx', True, list(range(1,12))))
        self.assertEqual((doc['truncated_groups'], doc['omitted_groups']), (['第2、5、8页'], ['第3、6、9页', '第10–11页']))
        self.assertEqual(sum(len(g['text']) for g in doc['groups']), 6000)
        brief = self.brief(ident)
        self.assertEqual(brief['state'], 'review')
        self.assertIn('Word整理摘要未全部送核', brief['reason'])
        self.assertIn('转换后共11页', brief['reason'])
        self.assertIn('第3、6、9页', brief['reason'])


if __name__ == '__main__':
    unittest.main()

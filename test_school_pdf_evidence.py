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
                     purpose='learning', submission='', change='new', target_id='',
                     learning_subject='数学' if changes.get('purpose','learning')=='learning' else '',learning_goal_id=''), **changes)


class SchoolPdfEvidenceTests(test_pdf_material.Base):
    seed_pdf = test_pdf_material.PdfMaterialTests.seed_pdf
    rows = test_pdf_material.PdfMaterialTests.rows
    set_sources = test_pdf_material.PdfMaterialTests.set_sources
    seed_docx = test_pdf_material.DocxMaterialTests.seed_docx

    def setUp(self):
        super().setUp()
        self.keys = self.school_fragment(TEXT); self.pdf = self.seed_pdf('a' * 32); self.link(self.keys, self.pdf)

    def seed_groups(self, batches=BATCHES, note=DRAFT['note'], keys=None, uncertainties=None, upload_id=None):
        with self.store._db() as c:
            source, message = self.store._message_context(c, keys or self.keys)
            fp = pdfm.pdf_input(self.store, c, source, message, upload_id=upload_id)['fingerprint']
            for pages in batches:
                payload = json.dumps(dict(DRAFT, note=note, uncertainties=DRAFT['uncertainties'] if uncertainties is None else uncertainties,
                                          title='第%s-%s页组' % (pages[0], pages[-1]), kind='school_material'), ensure_ascii=False)
                c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',
                          (source['id'], message['id'], fp, pages[0], json.dumps(pages), 11, payload, self.now.isoformat()))
        return fp

    def multi_originals(self):
        keys=self.native_notice('multi')
        reference=self.seed_pdf('b'*32,name='虚构家长参考.pdf')
        self.link(keys,reference)
        return keys,reference

    def test_complete_original_keeps_independent_homework_and_receipt(self):
        keys=self.native_notice('independent-original')
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                    (keys['source_id'],keys['message_id'])).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(raw,text='要求见附件。')),keys['source_id'],keys['message_id']))
        ident=self.candidate(keys=keys,ident='independent-original')
        homework='数学：2026-02-12前完成练习卷第1–3题必做，第4题选做，做完检查。'
        receipt='家长事务：2026-02-13前打印独立活动回执，家长签字后由孩子交回，无需盖章。'
        self.seed_groups(keys=keys,note=homework+'\n'+receipt,uncertainties=[])
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[
            dict(draft(title='数学：完成练习卷',goal=homework),due='2026-02-12',existing_item_id=ident,
                 basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=homework)]),
            dict(draft(title='事务：签字交回活动回执',goal=receipt,purpose='admin'),due='2026-02-13',existing_item_id='',
                 basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=receipt)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['used'],result['failed'],result['created'],len(calls)),(1,0,2,1))
        tasks=self.rows('SELECT title,due,action,original_status,source FROM manual_tasks ORDER BY due')
        self.assertEqual([(r[0],r[1],r[3]) for r in tasks],
                         [('数学：完成练习卷','2026-02-12','待跟进'),('事务：签字交回活动回执','2026-02-13','待跟进')])
        self.assertIn('第4题选做',tasks[0][2]);self.assertIn('无需盖章',tasks[1][2])
        self.assertTrue(all(ref in r[4] for r in tasks))
        self.assertEqual((self.item(ident)['state'],self.count('records')),('accepted',0))
        saved=self.rows('SELECT id,state,task_id,plan FROM agent_items ORDER BY id')
        self.assertEqual(self.refresh(reply,minutes=1),(dict(used=0,failed=0,created=0),[]))
        self.assertEqual(self.rows('SELECT id,state,task_id,plan FROM agent_items ORDER BY id'),saved)

    def test_original_action_cannot_borrow_other_action_deadline(self):
        keys=self.native_notice('separate-date')
        ident=self.candidate(keys=keys,ident='separate-date')
        math='数学：2026-02-12前完成练习卷第1至11页。'
        receipt='家长事务：2026-02-13前打印并签字交回活动回执。'
        self.seed_groups(keys=keys,note=math+'\n'+receipt,uncertainties=[])
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[dict(draft(goal=math),due='2026-02-13',existing_item_id=ident,basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=math)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['used'],len(calls),self.item(ident)['state'],self.count('manual_tasks')),(1,1,'pending',0))
        self.assertEqual(self.brief(ident)['state'],'review')
        self.assertIn('日期',self.brief(ident)['reason'])

    def test_two_originals_require_both_complete_before_one_school_round(self):
        keys,reference=self.multi_originals()
        ident=self.candidate(keys=keys,ident='multi')
        before=self.item(ident)
        note='数学：2026-02-12前完成练习卷第1至11页，做完检查。'
        self.seed_groups(keys=keys,note=note,uncertainties=[],upload_id=self.pdf)
        self.assertIsNone(self.material(keys))
        self.assertEqual(self.refresh(draft()),(dict(used=0,failed=0,created=0),[]))
        self.assertEqual(self.item(ident),before)
        self.seed_groups(keys=keys,note='本附件为上述练习卷的家长核对参考，不是孩子作答。',uncertainties=[],upload_id=reference)
        material=self.material(keys)
        self.assertEqual([d['upload_id'] for d in material['documents']],[self.pdf,reference])
        result,calls=self.refresh(draft(goal=note))
        self.assertEqual((result['used'],len(calls),result['created']),(1,1,1))
        documents=json.loads(calls[0][1]['content'])['pdf_material']
        self.assertEqual([d['upload_id'] for d in documents],[self.pdf,reference])
        self.assertEqual([d['name'] for d in documents],['虚构练习卷.pdf','虚构家长参考.pdf'])
        self.assertTrue(all(d['complete'] and d['processed_pages']==list(range(1,12)) for d in documents))
        self.assertEqual([d['processed_pages'] for d in documents],[list(range(1,12))]*2)
        row=self.item(ident)
        self.assertEqual((row['state'],row['due'],self.count('manual_tasks'),self.count('records')),('accepted','2026-02-12',1,0))
        self.assertEqual(len(self.brief(ident)['pdf_evidence']['documents']),2)
        self.assertEqual(self.refresh(draft(),minutes=1),(dict(used=0,failed=0,created=0),[]))
        self.assertEqual(self.item(ident),row)

    def test_reference_reading_gap_does_not_become_a_complete_school_requirement(self):
        keys,reference=self.multi_originals()
        self.seed_groups(keys=keys,note=TEXT,uncertainties=[],upload_id=self.pdf)
        self.seed_groups(keys=keys,note='家长参考。',uncertainties=['参考最后一页看不清'],upload_id=reference)
        ident=self.candidate(keys=keys,ident='uncertain-multi')
        result,calls=self.refresh(draft())
        self.assertEqual((result['used'],len(calls),self.item(ident)['state'],self.count('manual_tasks')),(1,1,'pending',0))
        self.assertEqual(self.brief(ident)['state'],'review')
        self.assertIn('参考最后一页看不清',self.brief(ident)['reason'])
        self.assertEqual(len(self.brief(ident)['pdf_evidence']['documents']),2)
        self.assertTrue(json.loads(calls[0][1]['content'])['evidence'][0]['content_incomplete'])

    def test_complete_original_reading_scope_does_not_become_parent_read_approval(self):
        keys=self.native_notice('receipt-scope')
        text='家长事务：2月12日前打印阅读活动回执一份，家长签字后由孩子交回，无需盖章。'
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                   (keys['source_id'],keys['message_id'])).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(raw,text=text,unread=True)),keys['source_id'],keys['message_id']))
            before=c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                             (keys['source_id'],keys['message_id'])).fetchone()[0]
        self.seed_groups(keys=keys,note=text,uncertainties=[])
        ident=self.candidate(keys=keys,ident='receipt-scope')
        def read_scope(messages):
            context=json.loads(messages[-1]['content']);e=context['evidence'][0]
            self.assertNotIn('unread',e)
            self.assertEqual((e['collection_content_incomplete'],e['content_incomplete']),(True,False))
            self.assertTrue(context['pdf_material'][0]['complete'])
            return draft(title='家长事务：打印签字交回阅读活动回执',goal=text,purpose='admin')
        result,calls=self.refresh(read_scope)
        self.assertEqual((result['created'],len(calls),self.item(ident)['state']),(1,1,'accepted'))
        self.assertEqual(self.count('manual_tasks'),1);self.assertEqual(self.count('records'),0)
        with self.store._db() as c:
            self.assertEqual(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                      (keys['source_id'],keys['message_id'])).fetchone()[0],before)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE kind='goal'").fetchone()[0],0)
        self.assertNotIn('school_learning',json.loads(self.item(ident)['plan']))

    def test_original_refinement_new_learning_restores_exact_goal_and_message_association(self):
        import family_goals
        keys=self.native_notice('restored-learning')
        self.seed_groups(keys=keys,note='数学：2月12日前完成练习卷第1至11页。',uncertainties=[])
        preliminary=dict(title='',goal='',advice='',state='review',reason='原件尚未整理。',
                         policy=agent.SCHOOL_TASK_POLICY,purpose='learning',change='append',target_id='')
        ident=self.candidate(keys=keys,ident='restored-learning',brief=preliminary)
        with self.store._db() as c:
            plan=json.loads(self.item(ident)['plan']);plan.pop('school_messages')
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),ident))
        result,calls=self.refresh(draft(goal='2月12日前完成练习卷第1至11页。'))
        self.assertEqual((result['created'],len(calls),self.item(ident)['state']),(1,1,'accepted'))
        plan=json.loads(self.item(ident)['plan'])
        self.assertEqual(plan['school_learning'],dict(subject='数学',goal_id=''))
        self.assertEqual(plan['school_messages'],[dict(source_id=keys['source_id'],message_id=keys['message_id'])])
        goals=family_goals.Store(self.app,self.store)
        self.assertEqual((goals.route_school(),goals.route_school()),(1,0))
        plan=json.loads(self.item(ident)['plan'])
        with self.store._db() as c:
            root=c.execute('SELECT * FROM agent_items WHERE id=?',(plan['school_goal_id'],)).fetchone()
            messages,missing,tasks=goals._school_context(c,root)
            self.assertEqual((missing,len(messages),len(tasks)),(0,1,1))
            self.assertEqual(tasks[0]['id'],self.item(ident)['task_id'])
            self.assertEqual(tasks[0]['source_refs'],['school:message:'+keys['source_id']+':'+keys['message_id']])
        self.assertEqual(self.refresh(draft(),minutes=1),(dict(used=0,failed=0,created=0),[]))
        self.assertEqual((self.count('manual_tasks'),self.count('records')),(1,0))

    def test_original_refinement_rejects_goal_from_another_child_without_writes(self):
        import family_goals
        goals=family_goals.Store(self.app,self.store)
        other=goals.action(dict(action='create',request_key='synthetic-other-child-goal',
                               child_id='child-2',title='虚构另一孩子数学',subject='数学'))['id']
        keys=self.native_notice('foreign-learning')
        self.seed_groups(keys=keys,note=TEXT,uncertainties=[])
        ident=self.candidate(keys=keys,ident='foreign-learning');before=self.item(ident)
        result,calls=self.refresh(draft(learning_goal_id=other))
        self.assertEqual((result['failed'],result['created'],len(calls)),(1,0,1))
        self.assertEqual(self.item(ident),before)
        self.assertNotIn(other,[g['id'] for g in json.loads(calls[0][1]['content'])['learning_goals']])
        self.assertEqual((self.count('manual_tasks'),self.count('records')),(0,0))

    def test_unread_original_without_requirements_cannot_create_a_learning_goal(self):
        from family_goals import Store as Goals
        keys=self.native_notice('unread-learning')
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                    (keys['source_id'],keys['message_id'])).fetchone()[0])
            raw.update(text='[文件] 虚构资料.pdf',unread=True)
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(raw),keys['source_id'],keys['message_id']))
        ident=self.candidate(keys=keys,ident='unread-learning',brief=dict(policy=7,state='review',title='',goal=''))
        result,calls=self.refresh(draft())
        self.assertEqual((result['used'],result['created'],self.brief(ident)['goal'],self.item(ident)['state']),(1,0,'','pending'))
        self.assertNotIn('school_learning',json.loads(self.item(ident)['plan']))
        goals=Goals(self.app,self.store)
        self.assertEqual((goals.route_school(),goals.snapshot()['goals'],self.count('manual_tasks'),self.count('records')),(0,[],0,0))

    def test_original_refinement_links_a_paused_goal_without_resuming_or_creating_another(self):
        import family_goals
        goals=family_goals.Store(self.app,self.store)
        ident=goals.action(dict(action='create',request_key='synthetic-paused-school-goal',
                               child_id='child-1',title='虚构数学要求',subject='数学'))['id']
        version=next(g['version'] for g in goals.snapshot()['goals'] if g['id']==ident)
        goals.action(dict(action='pause',request_key='synthetic-pause-school-goal',id=ident,expected_version=version))
        keys=self.native_notice('paused-learning')
        self.seed_groups(keys=keys,note=TEXT,uncertainties=[])
        item=self.candidate(keys=keys,ident='paused-learning')
        result,calls=self.refresh(draft(learning_goal_id=ident))
        self.assertEqual((result['created'],len(calls),self.item(item)['state']),(1,1,'accepted'))
        self.assertEqual(goals.route_school(),0)
        self.assertEqual(json.loads(self.item(item)['plan'])['school_goal_id'],ident)
        roots=goals.snapshot()['goals']
        self.assertEqual((len(roots),roots[0]['lifecycle']),(1,'paused'))
        self.assertEqual(self.count('records'),0)

    def test_same_named_originals_keep_distinct_ids_and_group_content_in_school_context(self):
        keys,reference=self.multi_originals()
        with self.store._db() as c:
            c.execute('UPDATE uploads SET name=? WHERE id IN (?,?)',('虚构资料.pdf',self.pdf,reference))
        self.seed_groups(keys=keys,note='题目原件：完成练习卷第1至11页。',uncertainties=[],upload_id=self.pdf)
        self.seed_groups(keys=keys,note='家长参考：第1题答案为3，不是孩子作答。',uncertainties=[],upload_id=reference)
        ident=self.candidate(keys=keys,ident='same-name-multi')
        result,calls=self.refresh(draft(state='review',reason='请对照两份原件。'))
        documents=json.loads(calls[0][1]['content'])['pdf_material']
        self.assertEqual((result['used'],len(calls),self.item(ident)['state']),(1,1,'pending'))
        self.assertEqual([d['name'] for d in documents],['虚构资料.pdf']*2)
        self.assertEqual([d['upload_id'] for d in documents],[self.pdf,reference])
        self.assertIn('题目原件',documents[0]['groups'][0]['text'])
        self.assertNotIn('家长参考',documents[0]['groups'][0]['text'])
        self.assertIn('家长参考',documents[1]['groups'][0]['text'])
        self.assertEqual(self.count('manual_tasks'),0)

    def test_multi_original_association_changes_discard_inflight_school_result(self):
        keys,reference=self.multi_originals()
        for upload in (self.pdf,reference):
            self.seed_groups(keys=keys,note=TEXT,uncertainties=[],upload_id=upload)
        ident=self.candidate(keys=keys,ident='detach-multi');before=self.item(ident)
        def detach(messages):
            self.link(keys,reference,action=DETACH)
            return draft()
        result,calls=self.refresh(detach)
        self.assertEqual((result['used'],len(calls),self.item(ident),self.count('manual_tasks')),(1,1,before,0))
        self.assertEqual(self.rows('SELECT COUNT(*) FROM agent_pdf_material'),[(8,)])

    def test_multi_original_bytes_change_refuses_parent_acceptance_without_overwriting_draft(self):
        keys,reference=self.multi_originals()
        for upload in (self.pdf,reference):
            self.seed_groups(keys=keys,note=TEXT,uncertainties=[],upload_id=upload)
        ident=self.candidate(keys=keys,ident='changed-multi')
        self.refresh(draft(state='review',reason='家长核对原件。'))
        before=self.item(ident)
        original=(self.data/'uploads'/reference).read_bytes()
        changed=test_pdf.build_pdf(11,width=2001)
        self.assertEqual(len(original),len(changed))
        (self.data/'uploads'/reference).write_bytes(changed)
        with self.assertRaises(agent.AgentError) as refused:
            self.store.act(dict(id=ident,action='accept',expected_updated=before['updated']))
        self.assertEqual((refused.exception.status,refused.exception.code,self.item(ident),self.count('manual_tasks')),(409,'pdf_evidence_stale',before,0))

    def native_notice(self, ident='native', upload=None, published=None):
        message=dict(self.message(ident,kind='text'),text=TEXT)
        self.ingest(message)
        keys=dict(child_id='child-1',source_id=self.source['id'],message_id=ident)
        if published is not None:
            with self.store._db() as c:
                c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                          (json.dumps(dict(message,time=published)),self.source['id'],ident))
        self.link(keys,upload or self.pdf)
        return keys

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
            result=reply(messages) if callable(reply) else reply
            context=json.loads(messages[-1]['content'])
            if 'original_parts' in context and isinstance(result,dict) and set(result)==set(agent.TASK_BRIEF_SCHEMA['required']):
                # The existing one-action fixtures keep their business assertions under the new array interface.
                parts=context['original_parts'];part=next((p for p in parts if p['upload_ids']),parts[0])
                return {'actions':[dict(result,due='',existing_item_id=context['candidate_id'],basis=[dict(part=part['id'],text=part['text'][:2000])])]}
            return result
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
        self.assertNotIn('school_learning',json.loads(row['plan']))  # a complete attached PDF does not validate a screenshot's scope
        self.assertTrue(brief['pdf_evidence']['fingerprint']); self.assertEqual(brief['pdf_evidence']['documents'][0]['sent'], 4)
        self.assertEqual(brief['state'],'review');self.assertIn('截图',brief['reason'])
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

    def test_complete_native_pdf_and_word_collect_once_under_the_original_source(self):
        for original,upload in [('pdf',self.pdf),('docx',self.seed_docx('b'*32))]:
            with self.subTest(original=original),no_convert(),no_pages():
                keys=self.native_notice(original,upload)
                self.seed_groups(keys=keys,note=TEXT,uncertainties=[])
                material=self.material(keys)
                evidence=agent._pdf_evidence([dict(material,ref='message:'+keys['source_id']+':'+keys['message_id'])])
                # The complete original and its summary have not changed since policy 7 marked the file unread.
                old=dict(draft(state='review',reason='原件或具体要求尚未读全。'),policy=7,
                         pdf_evidence=dict(fingerprint=evidence['fingerprint'],documents=evidence['documents']))
                ident=self.candidate(keys=keys,ident=original,brief=old);before=self.item(ident)
                self.assertEqual(self.refresh(draft(),budget=0),(dict(used=0,failed=0,created=0),[]))
                self.assertEqual(self.item(ident),before)
                result,calls=self.refresh(draft())
                row=self.item(ident);brief=self.brief(ident)
                self.assertEqual((result['used'],result['created'],len(calls),row['state'],brief['state']),(1,1,1,'accepted','ready'))
                self.assertEqual((brief['policy'],brief['pdf_evidence']['fingerprint'],brief['pdf_evidence']['documents'][0]['original']),
                                 (agent.SCHOOL_TASK_POLICY,evidence['fingerprint'],original))
                self.assertTrue(brief['auto_added'])
                doc=json.loads(calls[0][1]['content'])['pdf_material'][0]
                self.assertEqual((doc['complete'],doc['processed_pages'],doc['omitted_groups'],doc['truncated_groups']),(True,list(range(1,12)),[],[]))
                with self.app.connect() as c:
                    task=c.execute('SELECT * FROM manual_tasks WHERE id=?',(row['task_id'],)).fetchone()
                    self.assertEqual((task['child'],task['original_status']),('示例甲','待跟进'))
                    self.assertIn('message:'+keys['source_id']+':'+keys['message_id'],task['source'])
                again=self.store.act(dict(id=ident,action='accept',expected_updated=row['updated']),school_auto=True)
                self.assertEqual((again['state'],again['task_id']),('accepted',row['task_id']))
                self.assertEqual((self.refresh(draft())[1],self.item(ident)),([],row))
        self.assertEqual((self.count('manual_tasks'),self.count('agent_items'),self.count('records')),(2,2,0))

    def test_native_pdf_deadline_and_history_use_actual_sent_group_text(self):
        cases=[
            ('relative','2026-02-09T08:00:00+08:00','数学：明天提交练习卷。','accepted','2026-02-10',''),
            ('old','2026-02-09T08:00:00+08:00',TEXT,'pending','','早于今天'),
            ('unknown','',TEXT,'pending','','发布日期不明'),
            ('expired',self.now.isoformat(),'数学：2026-02-09前提交练习卷。','pending','2026-02-09','已过'),
            ('multiple',self.now.isoformat(),'数学：明天提交练习卷；后天上交订正。','pending','','不同完成日期'),
        ]
        for key,published,note,state,due,reason in cases:
            with self.subTest(case=key):
                keys=self.native_notice(key,published=published);self.seed_groups(keys=keys,note=note,uncertainties=[])
                ident=self.candidate(keys=keys,ident=key)
                result,calls=self.refresh(draft(goal=note))
                row=self.item(ident)
                self.assertEqual((result['used'],len(calls),row['state'],row['due']),(1,1,state,due))
                if reason:self.assertIn(reason,self.brief(ident)['reason'])
                self.assertEqual(self.brief(ident)['state'],'ready' if state=='accepted' else 'review')

    def test_native_pdf_partial_summary_and_uncovered_message_remain_review(self):
        keys=self.native_notice();ident=self.candidate(keys=keys)
        self.seed_groups(BATCHES[:3],keys=keys,note=TEXT+'摘'*2000,uncertainties=[])
        self.assertEqual(self.refresh(draft()),(dict(used=0,failed=0,created=0),[]))
        self.seed_groups(BATCHES[3:],keys=keys,note='2026-02-12前提交。'+'摘'*2000,uncertainties=[])
        result,calls=self.refresh(draft())
        self.assertEqual((result['used'],result['created'],self.brief(ident)['state'],self.count('manual_tasks')),(1,0,'review',0))
        self.assertIn('未全部送核',self.brief(ident)['reason'])
        self.assertEqual(self.item(ident)['due'],'')  # a date in an incompletely sent group does not become a deadline
        with self.store._db() as c:
            source,message=self.store._message_context(c,keys)
            pdf=agent._pdf_evidence([dict(self.material(keys),ref='message:'+source['id']+':'+message['id'])])
        evidence=[dict(ref='message:'+source['id']+':'+message['id'],**message),dict(ref='message:qq:other:missing',text='[文件]',kind='text',unread=True)]
        brief=agent._school_brief(draft(),incomplete=True,evidence=evidence,pdf=pdf)
        self.assertEqual(brief['state'],'review')

    def test_complete_native_pdf_known_reading_gap_is_not_erased_by_ready_model(self):
        keys=self.native_notice();self.seed_groups(keys=keys,note=TEXT,uncertainties=['最后一页要求看不清'])
        ident=self.candidate(keys=keys)
        self.assertIsNotNone(self.material(keys))  # All pages have a group; this is not proof of readable requirements.
        result,calls=self.refresh(draft())
        self.assertEqual((result['used'],len(calls),self.brief(ident)['state'],self.item(ident)['state'],self.count('manual_tasks')),(1,1,'review','pending',0))
        self.assertIn('最后一页要求看不清',self.brief(ident)['reason'])
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=ident,action='accept',expected_updated=self.item(ident)['updated']),school_auto=True)

    def test_other_pdf_notice_date_cannot_become_this_homework_deadline(self):
        keys=self.native_notice();self.seed_groups(keys=keys,note=TEXT+'示例通知：2026-02-12前提交报名表。',uncertainties=[])
        ident=self.candidate(keys=keys)
        result,calls=self.refresh(draft())
        self.assertEqual((result['used'],len(calls),self.item(ident)['due'],self.item(ident)['state'],self.count('manual_tasks')),(1,1,'','pending',0))
        self.assertIn('日期未能对应本项',self.brief(ident)['reason'])

    def test_auto_acceptance_rechecks_pdf_link_and_rejects_forged_ready_screenshot(self):
        keys=self.native_notice();self.seed_groups(keys=keys,note=TEXT,uncertainties=[]);ident=self.candidate(keys=keys)
        real=self.store.act
        def detach(obj,**kwargs):
            self.link(keys,self.pdf,action=DETACH)
            return real(obj,**kwargs)
        with patch.object(self.store,'act',side_effect=detach):result,calls=self.refresh(draft())
        self.assertEqual((result['used'],len(calls),self.item(ident)['state'],self.count('manual_tasks')),(1,1,'pending',0))
        self.refresh(draft());self.assertEqual(self.brief(ident)['state'],'review')
        self.seed_groups();screenshot=self.candidate(ident='screenshot');self.refresh(draft())
        row=self.item(screenshot);plan=json.loads(row['plan']);plan['school_task']['state']='ready'
        with self.store._db() as c:c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),screenshot))
        with self.assertRaises(agent.AgentError) as refused:
            real(dict(id=screenshot,action='accept',expected_updated=row['updated']),school_auto=True)
        self.assertIn('截图',str(refused.exception));self.assertEqual(self.count('manual_tasks'),0)

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

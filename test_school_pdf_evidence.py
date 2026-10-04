"""Synthetic check: a completely整理 PDF original feeds this pending school candidate's parent-reviewable draft.
Fictional family, QQ fragment notice and 11-page synthetic PDF; every model reply is a fixture; no render, network or real material."""
import datetime as dt
import copy
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import family_llm
import family_media as media
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
    def test_model_progress_is_not_a_complete_teacher_requirement(self):
        good='数学：2026-02-12前完成第1至3题，选做条件见第4页；等老师发资料再做另一份练习。'
        for requirement in (good+'须待第4页送入后按原文核对。',good+'本轮未重送第1至3页。',good+'processed_pages=[1,2,3]'):
            original=dict(upload_id='a'*32,title='虚构页组',note='本轮第1至3页。',requirements=[requirement],
                uncertainties=['第2页单位模糊'],deferred_contexts=[dict(pages=[4],note='续页标准待本轮后的处理。')])
            value=dict(originals=[original]);before=copy.deepcopy(value)
            with self.assertRaises(family_llm.LLMDraftError):
                family_llm.validate_school_material(value,original_ids=['a'*32],require_requirements=True,
                    allow_page_scope=True,deferred_pages=[4])
            self.assertEqual(value,before)
            legacy=family_llm.validate_school_material(value,original_ids=['a'*32],require_requirements=True,
                allow_page_scope=True,allow_legacy_reading_progress=True)
            self.assertEqual(legacy['originals'][0],original)
        original['requirements']=[good]
        self.assertEqual(family_llm.validate_school_material(dict(originals=[original]),original_ids=['a'*32],
            require_requirements=True,allow_page_scope=True,deferred_pages=[4])['originals'][0]['requirements'],[good])

    def progress_group(self):
        self.link(self.keys,self.pdf,action=DETACH)
        keys=self.native_notice('progress-requirements');ident=self.candidate(keys=keys,ident='progress-requirements')
        self.seed_groups(keys=keys,uncertainties=[])
        with self.store._db() as c:
            old=c.execute('SELECT payload FROM agent_pdf_material WHERE message_id=? AND first_page=1',(keys['message_id'],)).fetchone()
            value=json.loads(old[0]);original=value['originals'][0]
            original['requirements']=[TEXT+'须待第4页送入后按该页原文核对。']
            original['deferred_contexts']=[dict(pages=[4],note='后续页处理范围')]
            c.execute('UPDATE agent_pdf_material SET payload=? WHERE message_id=? AND first_page=1',(json.dumps(value),keys['message_id']))
        return keys,ident

    def progress_view(self,keys):
        with self.store._db() as c:
            source,message=self.store._message_context(c,keys)
            return pdfm.view(self.store,c,source,message)

    def test_old_progress_remains_readable_and_is_rechecked_without_losing_history(self):
        keys,ident=self.progress_group()
        before=self.rows('SELECT first_page,payload,updated,pages,page_count FROM agent_pdf_material ORDER BY first_page')
        view=self.progress_view(keys)
        self.assertEqual((view['complete'],view['requirements_complete'],view['processed_pages']),(True,False,list(range(1,12))))
        with self.store._db() as c:pdf=agent._pdf_evidence(agent._school_pdf(self.store,c,self.item(ident)))
        self.assertFalse(pdf['requirements_complete']);self.assertTrue(pdf['reading_progress_in_requirements'])
        with patch.object(family_llm,'_chat_json',side_effect=AssertionError('polluted requirements cannot map actions')):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=0,failed=0,created=0))
        bad=dict(originals=[dict(upload_id=self.pdf,title='不正确返回',note='背景',requirements=[TEXT+'须待第4页送入后核对。'],
            uncertainties=[],deferred_contexts=[])])
        with test_pdf_material.renderer(),patch.object(family_llm,'extract_draft',return_value=bad):
            self.assertEqual(pdfm.prepare(self.store,self.now,budget=1),dict(used=1,failed=1))
        self.assertEqual(self.rows('SELECT first_page,payload,updated,pages,page_count FROM agent_pdf_material ORDER BY first_page'),before)
        self.assertEqual(self.progress_view(keys)['state'],'error')
        with no_render(),patch.object(family_llm,'extract_draft',side_effect=AssertionError('backoff or zero budget')):
            self.assertEqual(pdfm.prepare(self.store,self.now,budget=0),dict(used=0,failed=0))
            self.assertEqual(pdfm.prepare(self.store,self.now+dt.timedelta(seconds=1),budget=1),dict(used=0,failed=0))
        def good(text,images,**kw):
            self.assertEqual(kw['original_pages'],[1,2,3]);self.assertEqual(kw['deferred_pages'],[])
            return dict(originals=[dict(upload_id=self.pdf,title='重新读取',note='老师要求',requirements=[TEXT],
                uncertainties=[],deferred_contexts=[])])
        with test_pdf_material.renderer(),patch.object(family_llm,'extract_draft',side_effect=good) as model:
            self.assertEqual(pdfm.prepare(self.store,self.now+dt.timedelta(minutes=30),budget=1),dict(used=1,failed=0))
            self.assertEqual(pdfm.prepare(self.store,self.now+dt.timedelta(minutes=31),budget=1),dict(used=0,failed=0))
            model.assert_called_once()
        after=self.rows('SELECT first_page,payload,updated,pages,page_count FROM agent_pdf_material ORDER BY first_page')
        self.assertEqual(after[1:],before[1:])
        self.assertEqual(json.loads(after[0][1])['previous_group'],dict(payload=json.loads(before[0][1]),updated=before[0][2],
            pages=json.loads(before[0][3]),page_count=before[0][4]))
        self.assertTrue(self.progress_view(keys)['requirements_complete'])
        self.assertEqual((self.count('manual_tasks'),self.count('records')),(0,0))

    def test_progress_recheck_never_replaces_a_parent_decision_or_edited_candidate(self):
        keys,ident=self.progress_group()
        before=self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page')
        for state,body in [('accepted',agent.FOCUS['school']),('dismissed',agent.FOCUS['school']),('pending','家长修改的实际要求')]:
            with self.subTest(state=state,body=body):
                with self.store._db() as c:c.execute('UPDATE agent_items SET state=?,body=? WHERE id=?',(state,body,ident))
                with no_render(),patch.object(family_llm,'extract_draft',side_effect=AssertionError('decision or edited body')):
                    self.assertEqual(pdfm.prepare(self.store,self.now),dict(used=0,failed=0))
                self.assertEqual(self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page'),before)

    def test_progress_recheck_voids_its_result_when_a_decision_changes_mid_call(self):
        keys,ident=self.progress_group();before=self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page')
        def model(*a,**kw):
            with self.store._db() as c:c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(ident,))
            return dict(originals=[dict(upload_id=self.pdf,title='重读',note='原件',requirements=[TEXT],uncertainties=[],deferred_contexts=[])])
        with test_pdf_material.renderer(),patch.object(family_llm,'extract_draft',side_effect=model):
            self.assertEqual(pdfm.prepare(self.store,self.now),dict(used=1,failed=0))
        self.assertEqual(self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page'),before)
        self.assertEqual(self.item(ident)['state'],'dismissed')

    def test_cached_ready_progress_cannot_be_accepted_or_silently_remapped(self):
        keys,ident=self.progress_group()
        with self.store._db() as c:
            row=self.item(ident);pdf=agent._pdf_evidence(agent._school_pdf(self.store,c,row));evidence,_=agent._school_material(self.store,c,row)
            full=TEXT+'须待第4页送入后按该页原文核对。'
            brief=dict(draft(goal=full),policy=agent.SCHOOL_TASK_POLICY,pdf_evidence=dict(fingerprint=pdf['fingerprint'],documents=pdf['documents']),
                origin_basis=agent._school_message_basis(evidence))
            plan=json.loads(row['plan']);plan['school_task']=brief
            plan['school_original_action']=dict(identity='synthetic-progress',anchors=[dict(ref=evidence[0]['ref'],upload_ids=[self.pdf],pages=[1,2,3],quote=full)],
                requirements=[dict(id='synthetic-requirement',ref=evidence[0]['ref'],upload_ids=[self.pdf],text=full)])
            c.execute('UPDATE agent_items SET title=?,body=?,due=?,plan=? WHERE id=?',
                (brief['title'],brief['goal'],'2026-02-12',json.dumps(plan),ident))
        before=self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page');row=self.item(ident)
        for automatic in (False,True):
            with self.subTest(automatic=automatic):
                with self.assertRaises(agent.AgentError) as caught:
                    self.store.act(dict(id=ident,action='accept',expected_updated=row['updated']),school_auto=automatic)
                self.assertEqual((caught.exception.status,caught.exception.code),(409,'pdf_requirements_incomplete'))
        with no_render(),patch.object(family_llm,'extract_draft',side_effect=AssertionError('complete action identity requires explicit recheck')):
            self.assertEqual(pdfm.prepare(self.store,self.now),dict(used=0,failed=0))
        self.assertEqual(self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page'),before)
        self.assertEqual((self.count('manual_tasks'),self.count('records'),self.item(ident)['body']),(0,0,full))

    def test_page_scope_boundary_has_a_checked_channel_without_clearing_real_doubts(self):
        original=dict(upload_id='a'*32,title='虚构页组',note='仅本轮第1至3页。',requirements=['数学：完成第1题。'],
            uncertainties=['第2页单位模糊'],deferred_contexts=[dict(pages=[4],note='通知中的独立回执在后续页另轮整理。')])
        checked=family_llm.validate_school_material(dict(originals=[original]),original_ids=['a'*32],
            require_requirements=True,allow_page_scope=True,deferred_pages=[4])
        self.assertEqual(checked['uncertainties'],['第2页单位模糊'])
        self.assertEqual(checked['originals'][0]['deferred_contexts'],original['deferred_contexts'])
        for bad in [dict(original,deferred_contexts=[dict(pages=[5],note='不在当前待处理范围')]),
                    dict(original,deferred_contexts=[dict(pages=[True],note='布尔值不是页码')]),
                    dict(original,deferred_contexts=[dict(pages=[4,4],note='重复页码')]),
                    {k:v for k,v in original.items() if k!='deferred_contexts'}]:
            with self.assertRaises(family_llm.LLMDraftError):
                family_llm.validate_school_material(dict(originals=[bad]),original_ids=['a'*32],
                    require_requirements=True,allow_page_scope=True,deferred_pages=[4])
        with self.assertRaises(family_llm.LLMDraftError):
            family_llm.validate_school_material(dict(originals=[original]),original_ids=['a'*32],require_requirements=True)

    def test_old_untyped_scope_doubt_recheck_preserves_payload_and_does_not_repeat(self):
        self.link(self.keys,self.pdf,action=DETACH)
        keys=self.native_notice('untyped-scope');ident=self.candidate(keys=keys,ident='untyped-scope')
        self.seed_groups(keys=keys,uncertainties=[])
        with self.store._db() as c:
            first=c.execute('SELECT * FROM agent_pdf_material WHERE message_id=? AND first_page=1',(keys['message_id'],)).fetchone()
            old=json.loads(first['payload']);old['originals'][0]['uncertainties']=['第4页尚未送入，独立回执尚未知。']
            c.execute('UPDATE agent_pdf_material SET payload=? WHERE message_id=? AND first_page=1',
                (json.dumps(old,ensure_ascii=False),keys['message_id']))
        before=self.rows('SELECT first_page,payload,updated,pages,page_count FROM agent_pdf_material WHERE message_id=? ORDER BY first_page',keys['message_id'])
        def model(text,images,**kw):
            self.assertEqual(kw['original_pages'],[1,2,3]);self.assertEqual(kw['deferred_pages'],[])
            return dict(originals=[dict(upload_id=self.pdf,title='重核第1至3页',note='背景',uncertainties=[],
                requirements=[TEXT],deferred_contexts=[])])
        with test_pdf_material.renderer(),patch.object(family_llm,'extract_draft',side_effect=model) as called:
            self.assertEqual(pdfm.prepare(self.store,self.now),dict(used=1,failed=0))
            self.assertEqual(pdfm.prepare(self.store,self.now+dt.timedelta(minutes=1)),dict(used=0,failed=0))
            self.assertEqual(called.call_count,1)
        after=self.rows('SELECT first_page,payload,updated,pages,page_count FROM agent_pdf_material WHERE message_id=? ORDER BY first_page',keys['message_id'])
        self.assertEqual(after[1:],before[1:])
        self.assertEqual(json.loads(after[0][1])['previous_group'],dict(payload=old,updated=before[0][2],pages=json.loads(before[0][3]),page_count=before[0][4]))
        with self.store._db() as c:
            row=self.item(ident);pdf=agent._pdf_evidence(agent._school_pdf(self.store,c,row))
        self.assertEqual(pdf['uncertainties'],[])

    def test_covered_deferred_pages_never_clear_a_real_content_doubt(self):
        for doubt in ['', '第2页单位模糊，无法确定写厘米还是米。']:
            with self.subTest(doubt=doubt):
                with self.store._db() as c:c.execute('DELETE FROM agent_pdf_material')
                self.seed_groups(uncertainties=[])
                ident=self.candidate(ident='covered-'+str(bool(doubt)))
                with self.store._db() as c:
                    rows=list(c.execute('SELECT first_page,payload FROM agent_pdf_material ORDER BY first_page'))
                    for first,payload in rows:
                        value=json.loads(payload);original=value['originals'][0]
                        original['deferred_contexts']=[dict(pages=[4],note='独立回执在后续页整理。')] if first==1 else []
                        original['uncertainties']=[doubt] if first==1 and doubt else []
                        c.execute('UPDATE agent_pdf_material SET payload=? WHERE first_page=?',(json.dumps(value),first))
                    row=self.item(ident);pdf=agent._pdf_evidence(agent._school_pdf(self.store,c,row))
                self.assertEqual(pdf['uncertainties'],[doubt] if doubt else [])

    def test_untyped_doubt_is_not_reread_after_any_parent_decision(self):
        self.link(self.keys,self.pdf,action=DETACH)
        keys=self.native_notice('scope-decided');ident=self.candidate(keys=keys,ident='scope-decided')
        self.seed_groups(keys=keys,uncertainties=['第4页尚未送入，回执未知。'])
        for state in ('accepted','dismissed'):
            with self.subTest(state=state):
                with self.store._db() as c:c.execute('UPDATE agent_items SET state=? WHERE id=?',(state,ident))
                before=self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page')
                with no_render(),patch.object(family_llm,'extract_draft',side_effect=AssertionError('decision must not be re-read')):
                    self.assertEqual(pdfm.prepare(self.store,self.now),dict(used=0,failed=0))
                self.assertEqual(self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page'),before)

    seed_pdf = test_pdf_material.PdfMaterialTests.seed_pdf
    rows = test_pdf_material.PdfMaterialTests.rows
    set_sources = test_pdf_material.PdfMaterialTests.set_sources
    seed_docx = test_pdf_material.DocxMaterialTests.seed_docx

    def setUp(self):
        super().setUp()
        self.keys = self.school_fragment(TEXT); self.pdf = self.seed_pdf('a' * 32); self.link(self.keys, self.pdf)

    def seed_groups(self, batches=BATCHES, note=DRAFT['note'], keys=None, uncertainties=None, upload_id=None,
                    requirements=(TEXT,), legacy=False):
        with self.store._db() as c:
            source, message = self.store._message_context(c, keys or self.keys)
            original = pdfm.pdf_input(self.store, c, source, message, upload_id=upload_id)
            fp = original['fingerprint']
            for pages in batches:
                group = dict(title='第%s-%s页组' % (pages[0], pages[-1]), note=note,
                             uncertainties=DRAFT['uncertainties'] if uncertainties is None else uncertainties)
                if legacy:
                    payload = dict(group, kind='school_material')
                else:
                    payload = dict(kind='school_material', originals=[dict(group, upload_id=original['upload_id'],
                                                                         requirements=list(requirements))])
                payload = json.dumps(payload, ensure_ascii=False)
                c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',
                          (source['id'], message['id'], fp, pages[0], json.dumps(pages), 11, payload, self.now.isoformat()))
        return fp

    def multi_originals(self):
        keys=self.native_notice('multi')
        reference=self.seed_pdf('b'*32,name='虚构家长参考.pdf')
        self.link(keys,reference)
        return keys,reference

    def test_legacy_pdf_summary_cannot_auto_add_a_shortened_action(self):
        keys=self.native_notice('legacy-pdf-standards')
        ident=self.candidate(keys=keys,ident='legacy-pdf-standards')
        short='数学：2026-02-12前完成练习第1至3题。'
        note=short+'写明单位；第4题选做，若选做须用两种方法，做完检查，无需家长签字。\n家长事务：2026-02-13前打印独立活动回执，家长签字后交回。'
        self.seed_groups(keys=keys,note=note,uncertainties=[],legacy=True)
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[dict(draft(title='数学：完成练习',goal=short),due='2026-02-12',existing_item_id=ident,
            basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=short)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['failed'],result['created'],self.count('manual_tasks'),len(calls)),(0,0,0,0))
        self.assertEqual(self.item(ident)['state'],'pending')

    def test_pdf_complete_requirements_preserve_cross_group_standards_and_receipt(self):
        keys=self.native_notice('page-requirements')
        ident=self.candidate(keys=keys,ident='page-requirements')
        requirements=['数学：2026-02-12前完成练习第1至3题必做，写明单位。',
                      '同一数学练习第4题选做，若选做须用两种方法，做完检查，无需家长签字。',
                      '家长事务：2026-02-13前打印独立活动回执，家长签字后交回。']
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        with self.store._db() as c:
            source,message=self.store._message_context(c,keys)
            fp=pdfm.pdf_input(self.store,c,source,message)['fingerprint']
            for pages,rs in zip(BATCHES,[[requirements[0]],[requirements[1]],[],[requirements[2]]]):
                original=dict(upload_id=self.pdf,title='虚构页组',note='题面和空白栏是背景。',uncertainties=[],requirements=rs)
                payload=json.dumps(dict(kind='school_material',originals=[original]),ensure_ascii=False)
                c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',
                    (source['id'],message['id'],fp,pages[0],json.dumps(pages),11,payload,self.now.isoformat()))
        with self.store._db() as c:
            row=self.item(ident);evidence,_=agent._school_material(self.store,c,row)
            pdf=agent._pdf_evidence(agent._school_pdf(self.store,c,row))
        parts=agent._school_original_parts(evidence,pdf,None)
        required=[p for p in parts if p.get('requirement')]
        self.assertEqual([(p['text'],p['pages'],p['upload_ids']) for p in required],
                         [(t,p,[self.pdf]) for t,p in zip(requirements,[BATCHES[0],BATCHES[1],BATCHES[3]])])
        reply={'actions':[
            dict(draft(title='数学：完成练习',goal='完成练习。'),due='2026-02-12',existing_item_id=ident,
                 basis=[dict(part=p['id'],text=p['text']) for p in required[:2]]),
            dict(draft(title='事务：签字交回回执',goal='签字交回。',purpose='admin'),due='2026-02-13',existing_item_id='',
                 basis=[dict(part=required[2]['id'],text=required[2]['text'])])]}
        result,_=self.refresh(reply)
        self.assertEqual((result['failed'],result['created']),(0,2))
        tasks=self.rows('SELECT action,due FROM manual_tasks ORDER BY due')
        self.assertEqual(tasks,[(requirements[0]+'\n'+requirements[1],'2026-02-12'),(requirements[2],'2026-02-13')])
        self.assertEqual(self.count('records'),0)
        self.assertEqual(self.refresh(reply,minutes=1),(dict(used=0,failed=0,created=0),[]))

    def test_pdf_legacy_upgrade_is_bounded_preserves_each_old_group_and_all_decisions(self):
        self.link(self.keys,self.pdf,action=DETACH)
        keys=self.native_notice('upgrade-groups')
        self.candidate(keys=keys,ident='upgrade-groups')
        self.seed_groups(keys=keys,note='旧页组摘要：数学练习，完整标准尚未结构化。',uncertainties=[],legacy=True)
        before=self.rows('SELECT first_page,pages,page_count,payload,updated FROM agent_pdf_material ORDER BY first_page')
        seen=[]
        def model(text,images,**kw):
            pages=json.loads(text)['original_pdf']['pages'];seen.append(pages)
            self.assertEqual((kw['original_ids'],kw['original_pages']),([self.pdf],pages))
            return dict(originals=[dict(upload_id=self.pdf,title='新页组',note='背景',uncertainties=[],requirements=[],deferred_contexts=[])])
        with test_pdf_material.renderer(),patch.object(family_llm,'extract_draft',side_effect=model) as called:
            self.assertEqual(pdfm.prepare(self.store,self.now,budget=0),dict(used=0,failed=0));called.assert_not_called()
            for step in range(4):
                self.assertEqual(pdfm.prepare(self.store,self.now+dt.timedelta(minutes=step)),dict(used=1,failed=0))
            self.assertEqual(pdfm.prepare(self.store,self.now+dt.timedelta(minutes=4)),dict(used=0,failed=0))
        self.assertEqual(seen,BATCHES)
        after=self.rows('SELECT first_page,payload FROM agent_pdf_material ORDER BY first_page')
        for old,new in zip(before,after):
            self.assertEqual(json.loads(new[1])['previous_group'],dict(payload=json.loads(old[3]),updated=old[4],pages=json.loads(old[1]),page_count=old[2]))
        with self.store._db() as c:
            source,message=self.store._message_context(c,keys)
            self.assertTrue(pdfm.view(self.store,c,source,message)['requirements_complete'])
        self.assertEqual((self.count('manual_tasks'),self.count('records')),(0,0))

    def test_pdf_legacy_upgrade_mixed_decision_and_model_race_never_replace_groups(self):
        self.link(self.keys,self.pdf,action=DETACH)
        keys=self.native_notice('upgrade-decisions')
        first=self.candidate(keys=keys,ident='upgrade-decisions-first')
        second=self.candidate(keys=keys,ident='upgrade-decisions-second')
        self.seed_groups(keys=keys,note='旧页组，留待完整核对。',uncertainties=[],legacy=True)
        before=self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page')
        with self.store._db() as c:c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(second,))
        with no_render(),patch.object(family_llm,'extract_draft',side_effect=AssertionError('mixed decision must not reread')):
            self.assertEqual(pdfm.prepare(self.store,self.now),dict(used=0,failed=0))
        with self.store._db() as c:c.execute("UPDATE agent_items SET state='pending' WHERE id=?",(second,))
        def changed(text,images,**kw):
            with self.store._db() as c:c.execute("UPDATE agent_items SET plan=? WHERE id=?",(json.dumps(dict(school_task=dict(goal='家长并发修改'))),first))
            return dict(originals=[dict(upload_id=self.pdf,title='新页组',note='背景',uncertainties=[],requirements=[],deferred_contexts=[])])
        with test_pdf_material.renderer(),patch.object(family_llm,'extract_draft',side_effect=changed):
            self.assertEqual(pdfm.prepare(self.store,self.now),dict(used=1,failed=0))
        self.assertEqual(self.rows('SELECT * FROM agent_pdf_material ORDER BY first_page'),before)
        self.assertEqual((self.count('manual_tasks'),self.count('records')),(0,0))

    def test_repeated_page_requirements_are_sent_once_with_their_full_page_scope(self):
        keys=self.native_notice('repeated-budget')
        requirement='数学：2026-02-12前完成练习第1至3题，写明单位并检查。'+'标准'*750
        self.seed_groups(keys=keys,note='背景',uncertainties=[],requirements=[requirement])
        ident=self.candidate(keys=keys,ident='repeated-budget')
        def mapping(messages):
            context=json.loads(messages[-1]['content'])
            requirements=[p for p in context['original_parts'] if p.get('requirement')]
            self.assertEqual([(p['text'],p['pages'],p['upload_ids']) for p in requirements],
                             [(requirement,list(range(1,12)),[self.pdf])])
            sent=sum(len(g['text'])+sum(map(len,g.get('requirements',[])))
                     for doc in context['pdf_material'] for g in doc['groups'])
            sent+=sum(len(p['text']) for p in requirements)
            self.assertLessEqual(sent,agent.PDF_TEXT_LIMIT,'repeated groups must not expand the actual complete-requirement input budget')
            return {'actions':[dict(draft(goal='短摘要'),due='2026-02-12',existing_item_id=ident,
                basis=[dict(part=requirements[0]['id'],text=requirement)])]}
        result,_=self.refresh(mapping)
        self.assertEqual((result['created'],self.item(ident)['body']),(1,requirement))

    def legacy_action_candidates(self):
        keys=self.native_notice('legacy-actions')
        requirements=['数学：2026-02-12前完成练习第1题，写明单位。',
                      '语文：2026-02-13前完成习作第2题，写出完整过程。']
        shorts=['数学：2026-02-12前完成练习第1题','语文：2026-02-13前完成习作第2题']
        self.seed_groups(keys=keys,note='题面背景',uncertainties=[],requirements=requirements)
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        ids=[]
        for index,(text,short) in enumerate(zip(requirements,shorts)):
            ident=self.candidate(keys=keys,ident='legacy-action-'+str(index));ids.append(ident)
            with self.store._db() as c:
                row=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone())
                evidence,_=agent._school_material(self.store,c,row)
                brief=dict(draft(title=short,goal=short,state='review'),origin_basis=agent._school_message_basis(evidence))
                plan=dict(school_task=brief,school_original_action=dict(identity='legacy-'+str(index),scope='legacy',root_id=ids[0],
                    anchors=[dict(ref=ref,upload_ids=[self.pdf],pages=[1,2,3],quote=short)]))
                c.execute('UPDATE agent_items SET title=?,body=?,due=?,plan=? WHERE id=?',
                          (short,short,'2026-02-'+str(12+index),json.dumps(plan,ensure_ascii=False),ident))
        return ids,requirements

    def test_legacy_reflow_retains_each_old_action_and_rejects_merging_two_ids(self):
        ids,requirements=self.legacy_action_candidates()
        before=self.rows('SELECT * FROM agent_items ORDER BY id')
        def merged(messages):
            context=json.loads(messages[-1]['content']);parts=[p for p in context['original_parts'] if p.get('requirement')]
            return {'actions':[dict(draft(goal='把两项混合'),due='',existing_item_id=context['candidate_id'],
                basis=[dict(part=p['id'],text=p['text']) for p in parts])]}
        result,_=self.refresh(merged)
        self.assertEqual((result['failed'],result['created'],self.count('manual_tasks')),(1,0,0))
        self.assertEqual(self.rows('SELECT * FROM agent_items ORDER BY id'),before)
        def separated(messages):
            context=json.loads(messages[-1]['content']);parts=[p for p in context['original_parts'] if p.get('requirement')]
            return {'actions':[dict(draft(title=text.split('：')[0]+'：完成练习',goal='短摘要',learning_subject=text.split('：')[0]),
                due='2026-02-'+str(12+i),existing_item_id=ids[i],basis=[dict(part=parts[i]['id'],text=text)])
                for i,text in enumerate(requirements)]}
        result,_=self.refresh(separated,minutes=6)
        self.assertEqual((result['failed'],result['created']),(0,2))
        self.assertEqual(self.rows('SELECT id,body,state FROM agent_items ORDER BY id'),
                         sorted((ident,text,'accepted') for ident,text in zip(ids,requirements)))
        self.assertTrue(all(json.loads(self.item(ident)['plan'])['previous_pdf_action']['body'] in text
                            for ident,text in zip(ids,requirements)))
        self.assertEqual(self.refresh(separated,minutes=7),(dict(used=0,failed=0,created=0),[]))

    def test_legacy_pdf_refinement_never_falls_back_to_a_free_summary_after_other_decision(self):
        ids,_=self.legacy_action_candidates()
        with self.store._db() as c:c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(ids[1],))
        before=self.rows('SELECT id,title,body,due,state,task_id FROM agent_items ORDER BY id')
        result,calls=self.refresh(draft(goal='省略标准的新摘要'))
        self.assertEqual((result,len(calls)),(dict(used=0,failed=0,created=0),0))
        self.assertEqual(self.rows('SELECT id,title,body,due,state,task_id FROM agent_items ORDER BY id'),before)

    def test_docx_only_actions_keep_each_original_standard_and_unrelated_text_separate(self):
        from test_media import MediaTests,docx,para
        uploads=['b'*32,'c'*32]
        math='数学：2026-02-12前完成练习第1至3题，写明单位；第4题选做，若选做须用两种方法，做完检查，不需要家长签字。'
        receipt='家长事务：2026-02-13前打印独立活动回执，家长签字后交回；不需要填写日期空白栏。'
        notice='英语：2026-02-14前背诵Unit3第2页，不需要打印。'
        keys=self.native_notice('docx-only')
        self.link(keys,self.pdf,action=DETACH)  # This fixture must exercise only the two DOCX, not the PDF page route.
        for upload,text in zip(uploads,[math,receipt]):
            self.link(keys,MediaTests.seed_docx(self,upload,docx(para(text)),name='相同名称.docx'))
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                    (keys['source_id'],keys['message_id'])).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(raw,text=notice,unread=False)),keys['source_id'],keys['message_id']))  # No additional unknown collection gap in this full-action fixture.
        item_id=self.candidate(keys=keys,ident='docx-only')
        notes=[dict(upload_id=i,title=t,note='正文另存完整要求；空白栏不新增行动。',uncertainties=[],requirements=[r])
               for i,t,r in zip(uploads,['数学练习','独立回执'],[math,receipt])]
        with patch.object(family_llm,'extract_draft',return_value=dict(originals=notes)) as model:
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=1,failed=0))
        self.assertEqual(model.call_args.args[1],[])
        self.assertEqual(model.call_args.kwargs['original_ids'],uploads)
        self.assertEqual([d['text'] for d in model.call_args.kwargs['documents']],[math,receipt])
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        part_ids=['material:'+i+'@'+ref+':requirement:'+agent._hash(r)[:16] for i,r in zip(uploads,[math,receipt])]
        with self.store._db() as c:
            row=self.item(item_id);evidence,_=agent._school_material(self.store,c,row)
            material=agent._school_drafts(self.store,c,row)
        parts=agent._school_original_parts(evidence,None,material)
        self.assertEqual([(p['upload_ids'],p['text']) for p in parts],[([],notice),([uploads[0]],math),([uploads[1]],receipt)])
        actions={'actions':[
            dict(draft(title='数学：完成练习',goal='完成练习。'),due='2026-02-12',existing_item_id=item_id,basis=[dict(part=part_ids[0],text=math)]),
            dict(draft(title='事务：签字交回回执',goal='签字交回。',purpose='admin'),due='2026-02-13',existing_item_id='',basis=[dict(part=part_ids[1],text=receipt)]),
            dict(draft(title='英语：背诵Unit3第2页',goal=notice,learning_subject='英语'),due='2026-02-14',existing_item_id='',basis=[dict(part=ref,text=notice)])]}
        self.assertEqual(self.refresh(actions)[0],dict(used=1,failed=0,created=3))
        saved=self.rows('SELECT body,plan FROM agent_items ORDER BY due')
        self.assertEqual([r[0] for r in saved],[math,receipt,notice])
        self.assertEqual([[a['upload_ids'] for a in json.loads(r[1])['school_original_action']['anchors']] for r in saved],
                         [[[uploads[0]]],[[uploads[1]]],[[]]])
        self.assertEqual(self.count('manual_tasks'),3)
        before=self.rows('SELECT * FROM agent_items ORDER BY id')
        self.assertEqual(self.refresh(actions,minutes=1),(dict(used=0,failed=0,created=0),[]))
        self.assertEqual(self.rows('SELECT * FROM agent_items ORDER BY id'),before)
        self.assertEqual(self.count('records'),0)

    def test_two_same_named_images_build_separate_actions_and_keep_shared_reference_possible(self):
        from test_media import png
        images=['b'*32,'c'*32]
        for index,ident in enumerate(images):
            body=png(64+index,96)
            (self.data/'uploads'/ident).write_bytes(body)
            with self.store._db() as c:
                c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',
                          (ident,'相同名称.png',len(body),'image/png',self.now.isoformat()))
        keys=self.native_notice('two-images',upload=images[0]);self.link(keys,images[1])
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                    (keys['source_id'],keys['message_id'])).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(raw,text='学校要求见两张图片。\n[图片原件：2份，内容未读]',unread=True)),keys['source_id'],keys['message_id']))
        ident=self.candidate(keys=keys,ident='two-images')
        math='数学：2026-02-12前完成练习卷第1–3题。'
        receipt='家长事务：2026-02-13前家长签字交回独立活动回执。该回执与数学练习分开，不是作业答题页。'
        reply=dict(originals=[dict(upload_id=i,title=t,note=n,uncertainties=[],requirements=[n]) for i,t,n in
                             zip(images,['数学练习卷','活动回执'],[math,receipt])])
        with patch.object(family_llm,'extract_draft',return_value=reply) as model:
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=1,failed=0))
        self.assertEqual(model.call_args.kwargs['original_ids'],images)
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        part_ids=['material:'+i+'@'+ref+':requirement:'+agent._hash(n)[:16] for i,n in zip(images,[math,receipt])]
        with self.store._db() as c:
            row=self.item(ident);evidence,_=agent._school_material(self.store,c,row)
            material=agent._school_drafts(self.store,c,row)
        parts=agent._school_original_parts(evidence,None,material)
        self.assertEqual([(p['id'],p['upload_ids'],p['text']) for p in parts if p['upload_ids']],
                         [(part_ids[0],[images[0]],math),(part_ids[1],[images[1]],receipt)])
        schema=agent._school_original_schema(parts,[row],[],[])
        self.assertEqual(schema['properties']['actions']['items']['properties']['basis']['items']['properties']['part']['enum'],[p['id'] for p in parts])
        actions={'actions':[
            dict(draft(title='数学：完成练习卷',goal=math),due='2026-02-12',existing_item_id=ident,basis=[dict(part=part_ids[0],text=math)]),
            dict(draft(title='事务：签字交回回执',goal=receipt,purpose='admin'),due='2026-02-13',existing_item_id='',basis=[dict(part=part_ids[1],text=receipt)])]}
        result,calls=self.refresh(actions)
        self.assertEqual((result,len(calls)),(dict(used=1,failed=0,created=2),1))
        self.assertEqual(self.count('manual_tasks'),2)
        rows=self.rows('SELECT state,plan FROM agent_items ORDER BY due')
        self.assertEqual([r[0] for r in rows],['accepted','accepted'])
        plans=[json.loads(r[1]) for r in rows]
        self.assertEqual([[a['upload_ids'] for a in p['school_original_action']['anchors']] for p in plans],[[[images[0]]],[[images[1]]]])
        self.assertEqual(self.count('records'),0)
        before=self.rows('SELECT * FROM agent_items ORDER BY id')
        self.assertEqual(self.refresh(actions,minutes=1),(dict(used=0,failed=0,created=0),[]))
        self.assertEqual(self.rows('SELECT * FROM agent_items ORDER BY id'),before)
        # Selecting more than one proven part remains supported; no model-created upload selector is added.
        self.assertEqual(schema['properties']['actions']['items']['properties']['basis']['maxItems'],6)
        scoped=dict(row,plan=json.dumps(dict(school_original_action=dict(anchors=[dict(ref=ref,upload_ids=images,pages=[],quote=math)]))))
        with self.store._db() as c: shared=agent._school_drafts(self.store,c,scoped)
        self.assertEqual([e['upload_ids'] for e in shared['model']],[[images[0]],[images[1]]])
        scoped['plan']=json.dumps(dict(school_original_action=dict(anchors=[dict(ref=ref,upload_ids=[images[0]],pages=[],quote=math)])))
        with self.store._db() as c: selected=agent._school_drafts(self.store,c,scoped)
        self.assertEqual([e['upload_ids'] for e in selected['model']],[[images[0]]])
        self.assertEqual(selected['model'][0]['draft']['note'],math)
        # An unreadable sibling is not silently dropped, and is not attached to this independently scoped action.
        reply['originals'][1]['uncertainties']=['回执下方小字模糊']
        checked=family_llm.validate_school_material(reply,original_ids=images)
        with self.store._db() as c:
            c.execute('UPDATE agent_message_drafts SET payload=? WHERE source_id=? AND message_id=?',
                      (json.dumps(dict(kind='school_material',**checked)),keys['source_id'],keys['message_id']))
            selected=agent._school_drafts(self.store,c,scoped)
            whole=agent._school_drafts(self.store,c,row)
        self.assertEqual(selected['uncertainties'],[])
        self.assertEqual(whole['uncertainties'],['回执下方小字模糊'])

    def required_image(self, requirements, ident='required-image'):
        from test_media import png
        upload='b'*32;body=png(64,96)
        (self.data/'uploads'/upload).write_bytes(body)
        with self.store._db() as c:
            c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',
                      (upload,'虚构完整要求.png',len(body),'image/png',self.now.isoformat()))
        keys=self.native_notice(ident,upload=upload)
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                    (keys['source_id'],keys['message_id'])).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(raw,text='学校要求见图片。\n[图片原件：1份，内容未读]',unread=True)),keys['source_id'],keys['message_id']))
        reply=dict(originals=[dict(upload_id=upload,title='数学练习要求',note='题面和空白栏只是背景。',
                                   uncertainties=[],requirements=requirements)])
        with patch.object(family_llm,'extract_draft',return_value=reply):
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=1,failed=0))
        item_id=self.candidate(keys=keys,ident=ident)
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        parts=['material:'+upload+'@'+ref+':requirement:'+agent._hash(n)[:16] for n in requirements]
        return item_id,parts,keys

    def test_complete_requirements_replace_a_later_lossy_or_added_action_summary(self):
        requirement='数学：2026-02-12前完成练习；第1至3题必做，第3题写明单位；第4题选做，若选做须用两种方法；做完检查，不需要家长签字。'
        ident,parts,keys=self.required_image([requirement])
        reply={'actions':[dict(draft(title='数学：完成练习',goal='完成第1至3题，并填写日期。',submission='填写日期。'),
            due='2026-02-12',existing_item_id=ident,basis=[dict(part=parts[0],text=requirement)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result,len(calls)),(dict(used=1,failed=0,created=1),1))
        saved=self.item(ident);brief=self.brief(ident)
        self.assertEqual((saved['body'],brief['goal'],brief.get('submission','')),(requirement,requirement,''))
        task=self.rows('SELECT action FROM manual_tasks')[0][0]
        self.assertEqual(task,requirement)
        self.assertEqual(json.loads(saved['plan'])['school_original_action']['requirements'][0]['text'],requirement)
        self.assertEqual(self.count('records'),0)
        self.assertEqual(self.refresh(reply,minutes=1),(dict(used=0,failed=0,created=0),[]))

    def test_partial_requirement_quote_fails_before_any_task_or_item_write(self):
        requirement='数学：2026-02-12前完成第1至3题，第3题写明单位，第4题选做并用两种方法。'
        ident,parts,keys=self.required_image([requirement]);before=self.item(ident)
        reply={'actions':[dict(draft(goal='完成第1至3题'),due='2026-02-12',existing_item_id=ident,
            basis=[dict(part=parts[0],text='完成第1至3题')])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result,len(calls),self.count('manual_tasks'),self.item(ident)),
                         (dict(used=1,failed=1,created=0),1,0,before))
        self.assertIn('截取或重复分配',self.rows("SELECT error FROM agent_jobs WHERE id LIKE 'school-task:%'")[0][0])

    def test_requirement_outer_whitespace_is_frozen_without_losing_internal_standards(self):
        requirement='数学：2026-02-12前完成第1至3题。\n第3题写明单位；第4题选做，须用两种方法。'
        ident,_,keys=self.required_image(['  '+requirement+'\n'])
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        part='material:'+'b'*32+'@'+ref+':requirement:'+agent._hash(requirement)[:16]
        reply={'actions':[dict(draft(goal='简短摘要'),due='2026-02-12',existing_item_id=ident,
            basis=[dict(part=part,text=requirement+'\n')])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['created'],len(calls),self.item(ident)['body']),(1,1,requirement))

    def test_original_optional_question_range_is_clear_in_the_saved_title(self):
        requirement='数学：2026-02-12前完成数学练习：第1至3题必做，第4题选做；第3题写明单位，选做的第4题用两种方法。'
        ident,parts,keys=self.required_image([requirement])
        reply={'actions':[dict(draft(title='数学：完成数学练习第1至4题',goal='短摘要'),due='2026-02-12',existing_item_id=ident,
            basis=[dict(part=parts[0],text=requirement)])]}
        self.assertEqual(self.refresh(reply)[0]['created'],1)
        title='数学：完成数学练习（第1至3题必做；第4题选做）'
        self.assertEqual(self.item(ident)['title'],title)
        self.assertEqual(self.rows('SELECT title,action FROM manual_tasks')[0],(title,requirement))
        for text in ('第4题选做','选做的第4题'):
            result=agent._school_requirement_goal(draft(title='数学：完成第1至4题'),[text+'，写出两种方法。'])
            self.assertEqual(result['title'],'数学：完成（第4题选做）')
        result=agent._school_requirement_goal(draft(title='数学：阅读任选章节'),['任选章节为选做，不改变必读第2章。'])
        self.assertEqual(result['title'],'数学：阅读任选章节')
        for requirement in ('第1至4题必须完成，不是选做','第4题不能当选做，必须完成','不是选做的第4题，必须完成',
                            '取消选做的第4题，改为必做','第4题不能当成选做，必须完成','第4题不再选做，改为必做',
                            '第4题不可选做，必须完成','不能当成选做的第4题，必须完成'):
            result=agent._school_requirement_goal(draft(title='数学：完成第1至4题'),[requirement])
            self.assertEqual(result['title'],'数学：完成第1至4题')
        result=agent._school_requirement_goal(draft(title='数学：第1至4题错题订正'),['第1至3题必做，第4题选做'])
        self.assertEqual(result['title'],'数学：错题订正（第1至3题必做；第4题选做）')
        result=agent._school_requirement_goal(draft(title='数学：完成第1至第4题'),['第1至第3题必做，第4题选做'])
        self.assertEqual(result['title'],'数学：完成（第1至第3题必做；第4题选做）')

    def test_missing_independent_requirement_fails_the_whole_round(self):
        requirements=['数学：2026-02-12前完成第1至3题并写明单位。','数学：2026-02-13前复习错题本第1至2题，并写出订正过程。']
        ident,parts,keys=self.required_image(requirements);before=self.item(ident)
        reply={'actions':[dict(draft(goal=requirements[0]),due='2026-02-12',existing_item_id=ident,
            basis=[dict(part=parts[0],text=requirements[0])])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['failed'],self.count('manual_tasks'),self.item(ident)),(1,0,before))
        self.assertIn('未全部分配',self.rows("SELECT error FROM agent_jobs WHERE id LIKE 'school-task:%'")[0][0])

    def test_duplicate_requirement_assignment_fails_the_whole_round(self):
        requirement='数学：2026-02-12前完成第1至3题并写明单位。'
        ident,parts,keys=self.required_image([requirement]);before=self.item(ident)
        entry=dict(draft(goal=requirement),due='2026-02-12',existing_item_id=ident,basis=[dict(part=parts[0],text=requirement)])
        reply={'actions':[entry,dict(entry,existing_item_id='',title='数学：再次练习')]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['failed'],self.count('manual_tasks'),self.item(ident)),(1,0,before))

    def test_one_original_can_have_two_complete_independent_actions(self):
        requirements=['数学：2026-02-12前完成第1至3题；第3题写明单位，第4题选做用两种方法。',
                      '数学：2026-02-13前复习错题本第1至2题，并写出订正过程，不必打印。']
        ident,parts,keys=self.required_image(requirements)
        reply={'actions':[dict(draft(title=t,goal='过度简化的摘要'),due=d,existing_item_id=i,basis=[dict(part=p,text=r)])
                          for t,d,i,p,r in zip(['数学：完成练习','数学：复习错题'],['2026-02-12','2026-02-13'],[ident,''],parts,requirements)]}
        result,calls=self.refresh(reply)
        self.assertEqual((result,len(calls)),(dict(used=1,failed=0,created=2),1))
        self.assertEqual([r[0] for r in self.rows('SELECT body FROM agent_items ORDER BY due')],requirements)
        self.assertEqual([r[0] for r in self.rows('SELECT action FROM manual_tasks ORDER BY due')],requirements)

    def test_background_only_material_cannot_be_promoted_by_a_ready_summary(self):
        ident,parts,keys=self.required_image([]);before=self.item(ident)
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[dict(draft(goal='完成新练习'),due='',existing_item_id=ident,
            basis=[dict(part='material:'+'b'*32+'@'+ref+':background',text='题面和空白栏只是背景。')])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['failed'],self.count('manual_tasks'),self.item(ident)),(1,0,before))

    def test_pending_refinement_keeps_saved_complete_requirements_and_rejects_changed_ones(self):
        requirement='数学：2026-02-12前完成第1至3题；第3题写明单位，第4题选做用两种方法。'
        ident,parts,keys=self.required_image([requirement])
        reply={'actions':[dict(draft(goal='简短摘要',state='review',reason='是否仍适用不明'),due='2026-02-12',existing_item_id=ident,
            basis=[dict(part=parts[0],text=requirement)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['created'],self.item(ident)['state']),(0,'pending'))
        with self.store._db() as c:
            plan=json.loads(self.item(ident)['plan']);plan['school_task']['policy']=0
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),ident))
        result,calls=self.refresh(draft(title='数学：完成练习',goal='再一次丢单位和方法数量'),minutes=1)
        self.assertEqual((result['created'],self.item(ident)['body']),(1,requirement))
        # The source map is checked independently of free summary wording.
        row=self.item(ident)
        with self.store._db() as c:
            ev,_=agent._school_material(self.store,c,row);material=agent._school_drafts(self.store,c,row)
        current_parts=agent._school_original_parts(ev,None,material)
        self.assertEqual(agent._school_saved_requirements(row,current_parts),[requirement])
        changed=[dict(p,text=p['text']+'新增一步') if p.get('requirement') else p for p in current_parts]
        with self.assertRaisesRegex(agent.AgentError,'要求已变化'):
            agent._school_saved_requirements(row,changed)

    def test_explicit_admin_material_contrast_does_not_hide_a_positive_learning_requirement(self):
        cases=[('negative','家长：2026-02-13前签字交回活动回执。该回执与数学练习分开，不是作业答题页。','accepted'),
               ('positive','家长：2026-02-13前完成数学练习第1–3题，再签字交回活动回执。该回执不是作业答题页。','pending'),
               ('submit-both','家长：2026-02-13前回执与数学作业分开提交，家长签字。','pending'),
               ('question-first','2026-02-13前打印回执，家长签字后交回。回执与数学练习分开。第1至3题必做，第4题选做。','pending'),
               ('required-after-question','2026-02-13前签字交回。这份回执不是练习卷。第1至3题必须完成并检查。','pending')]
        for label,note,state in cases:
            with self.subTest(label=label):
                keys=self.native_notice('admin-'+label)
                ident=self.candidate(keys=keys,ident='admin-'+label)
                self.seed_groups(keys=keys,note=note,uncertainties=[],requirements=[note])
                result,calls=self.refresh(draft(title='事务：签字交回回执',goal=note,purpose='admin'))
                self.assertEqual((result['used'],result['failed'],len(calls),self.item(ident)['state']),(1,0,1,state))
                if state=='pending':self.assertIn('同时提到学习活动',self.brief(ident)['reason'])
        self.assertEqual(self.count('manual_tasks'),1)
        for separate in (False,True):
            brief=agent._school_brief(draft(title='事务：签字交回回执',goal=cases[0][1],purpose='admin'),
                evidence=[dict(ref='message:qq:synthetic:1',text=cases[0][1],kind='text',unread=False)],separate_learning=separate)
            self.assertEqual(brief['state'],'ready')
            for label,note,state in cases[1:]:
                with self.subTest(label=label,separate=separate):
                    mixed=agent._school_brief(draft(title='事务：签字交回回执',goal=note,purpose='admin'),
                        evidence=[dict(ref='message:qq:synthetic:1',text=note,kind='text',unread=False)],separate_learning=separate)
                    self.assertEqual(mixed['state'],'review')
                    self.assertIn('同时提到学习活动',mixed['reason'])

    def test_question_first_actions_keep_positive_and_negated_requirements_distinct(self):
        for action in ('第1至3题必做，第4题选做。','第1至3题必须完成并检查。','第4题需完成。','第三至五题订正。'):
            with self.subTest(action=action):
                self.assertIsNotNone(agent._LEARNING_ACTION.search(action))
                text='这份回执不是练习卷。签字交回。'+action
                brief=agent._school_brief(draft(title='事务：签字交回回执',goal=text,purpose='admin'),
                    evidence=[dict(ref='message:s:1',text=text,kind='text',unread=False)],separate_learning=True)
                self.assertEqual(brief['state'],'review')
        for action in ('第1至3题不必做。','第4题无需完成。','第1至3题不是必做。','题号：第1至3题。'):
            with self.subTest(action=action):
                self.assertIsNone(agent._LEARNING_ACTION.search(action))
                text='这份回执不是练习卷。签字交回。'+action
                brief=agent._school_brief(draft(title='事务：签字交回回执',goal=text,purpose='admin'),
                    evidence=[dict(ref='message:s:1',text=text,kind='text',unread=False)],separate_learning=True)
                self.assertEqual(brief['state'],'ready')

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
        self.seed_groups(keys=keys,note=homework+'\n'+receipt,uncertainties=[],requirements=[homework,receipt])
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
                         [('数学：完成练习卷（第1–3题必做；第4题选做）','2026-02-12','待跟进'),('事务：签字交回活动回执','2026-02-13','待跟进')])
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
        self.seed_groups(keys=keys,note=math+'\n'+receipt,uncertainties=[],requirements=[math,receipt])
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[
            dict(draft(goal=math),due='2026-02-13',existing_item_id=ident,basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=math)]),
            dict(draft(title='事务：打印签字交回活动回执',goal=receipt,purpose='admin',state='review',reason='独立回执留待核对。'),
                 due='2026-02-13',existing_item_id='',basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=receipt)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['used'],len(calls),self.item(ident)['state'],self.count('manual_tasks')),(1,1,'pending',0))
        self.assertEqual(self.brief(ident)['state'],'review')
        self.assertIn('日期',self.brief(ident)['reason'])

    def test_four_literal_model_actions_include_revision_and_print_dates(self):
        keys=self.native_notice('four-model-actions')
        native='英语：2026-02-11完成Unit5朗读两遍，不用录音。'
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                    (keys['source_id'],keys['message_id'])).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(raw,text=native)),keys['source_id'],keys['message_id']))
        receipt_file=self.seed_pdf('b'*32,name='虚构独立活动回执.pdf');self.link(keys,receipt_file)
        maths=['数学：2026-02-12完成练习卷第1至3题，第4题选做，做完检查。',
               '数学：2026-02-13复习错题第1至2题，写出订正过程，不必打印。']
        receipt='家长事务：2026-02-14打印独立活动回执，家长签字后由孩子交回，无需盖章。'
        self.seed_groups(keys=keys,note='\n'.join(maths),uncertainties=[],upload_id=self.pdf,requirements=maths)
        self.seed_groups(keys=keys,note=receipt,uncertainties=[],upload_id=receipt_file,requirements=[receipt])
        ident=self.candidate(keys=keys,ident='four-model-actions');ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[
            dict(draft(title='英语：朗读Unit5两遍',goal=native,learning_subject='英语'),due='2026-02-11',existing_item_id=ident,basis=[dict(part=ref,text=native)]),
            dict(draft(title='数学：完成练习卷题目',goal=maths[0]),due='2026-02-12',existing_item_id='',basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=maths[0])]),
            dict(draft(title='数学：复习错题并写订正过程',goal=maths[1]),due='2026-02-13',existing_item_id='',basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=maths[1])]),
            dict(draft(title='事务：打印并交回独立活动回执',goal=receipt,purpose='admin'),due='2026-02-14',existing_item_id='',basis=[dict(part='pdf:'+receipt_file+':1@'+ref,text=receipt)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result,len(calls)),(dict(used=1,failed=0,created=4),1))
        rows=self.rows('SELECT due,plan,state FROM agent_items ORDER BY due')
        self.assertEqual([r[0] for r in rows],['2026-02-11','2026-02-12','2026-02-13','2026-02-14'])
        self.assertEqual([sorted({u for a in json.loads(r[1])['school_original_action']['anchors'] for u in a['upload_ids']}) for r in rows],[[],[self.pdf],[self.pdf],[receipt_file]])
        self.assertTrue(all(r[2]=='accepted' for r in rows));self.assertEqual(self.count('records'),0)
        self.assertEqual(self.refresh(reply,minutes=1),(dict(used=0,failed=0,created=0),[]))

    def original_action_fixture(self,note,**changes):
        keys=self.native_notice('action-guard')
        ident=self.candidate(keys=keys,ident='action-guard')
        self.seed_groups(keys=keys,note=note,uncertainties=[],requirements=note.splitlines())
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        value=dict(draft(title='事务：交回活动回执',goal=note,purpose='admin'),due='',existing_item_id=ident,
                   basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=note)])
        value.update(changes)
        return ident,{'actions':[value]}

    def test_complete_original_date_cannot_be_replaced_by_the_second_summary(self):
        ident,reply=self.original_action_fixture('2026-02-13前交回活动回执。',goal='2026-02-12前交回活动回执。')
        result,_=self.refresh(reply)
        row=self.item(ident)
        self.assertEqual((result['created'],row['state'],self.count('manual_tasks')),(1,'accepted',1))
        self.assertEqual((row['body'],row['due']),('2026-02-13前交回活动回执。','2026-02-13'))
        self.assertEqual(self.rows('SELECT action,due,original_status FROM manual_tasks'),
                         [('2026-02-13前交回活动回执。','2026-02-13','待跟进')])

    def test_original_admin_upload_cannot_swallow_required_learning(self):
        ident,reply=self.original_action_fixture('英语第5课朗读两遍后上传录音。',title='提交录音',goal='录音上传班级区')
        result,_=self.refresh(reply)
        self.assertEqual((result['created'],self.item(ident)['state'],self.count('manual_tasks')),(0,'pending',0))
        self.assertIn('学习',self.brief(ident)['reason'])

    def test_original_new_action_cannot_bind_an_unproven_old_decision(self):
        ident,reply=self.original_action_fixture('2026-02-13前交回活动回执。\n领取用品。')
        reply['actions'][0]['basis'][0]['text']='2026-02-13前交回活动回执。'
        other=self.candidate(keys=self.native_notice('other-initial'),ident='old-decision',title='旧决定')
        with self.store._db() as c:
            c.execute('UPDATE agent_items SET evidence=?,state=? WHERE id=?',
                      (self.item(ident)['evidence'],'dismissed',other))
        before=self.item(other)
        extra=dict(reply['actions'][0],existing_item_id=other,title='事务：领取用品',goal='领取用品。')
        extra['basis']=[dict(reply['actions'][0]['basis'][0],text='领取用品。')]
        reply['actions'].append(extra)
        result,_=self.refresh(reply)
        self.assertEqual((result['failed'],self.count('manual_tasks'),self.item(other)),(1,0,before))
        self.assertEqual(self.item(ident)['state'],'pending')

    def test_original_basis_must_name_an_action_not_only_a_date(self):
        ident,reply=self.original_action_fixture('2026-02-13前交回活动回执。')
        reply['actions'][0]['basis'][0]['text']='2026-02-13'
        result,_=self.refresh(reply)
        self.assertEqual((result['failed'],self.count('manual_tasks'),self.item(ident)['state']),(1,0,'pending'))

    def test_original_subset_sibling_change_discards_the_entire_round(self):
        ident,reply=self.original_action_fixture('2026-02-13前交回活动回执。')
        second=self.native_notice('second-original')
        other=self.candidate(keys=second,ident='subset')
        self.seed_groups(keys=second,note='2026-02-13前交回活动回执。',uncertainties=[],requirements=['2026-02-13前交回活动回执。'])
        with self.store._db() as c:
            both=json.loads(self.item(ident)['evidence'])+json.loads(self.item(other)['evidence'])
            c.execute('UPDATE agent_items SET evidence=? WHERE id=?',(json.dumps(both),ident))
        before=self.item(ident)
        def model(messages):
            with self.store._db() as c:c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(other,))
            return reply
        result,_=self.refresh(model)
        self.assertEqual((result['created'],self.item(ident),self.item(other)['state'],self.count('manual_tasks')),(0,before,'dismissed',0))

    def test_original_known_action_overflow_is_a_bounded_job_failure(self):
        keys=self.native_notice('too-many-known-actions')
        ident=self.candidate(keys=keys,ident='overflow-root')
        self.seed_groups(keys=keys,uncertainties=[])
        for index in range(agent.SCHOOL_PROPOSAL_LIMIT):
            previous=self.candidate(keys=keys,ident='overflow-old-'+str(index))
            with self.store._db() as c:c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(previous,))
        before=self.rows('SELECT id,state,plan,evidence FROM agent_items ORDER BY id')
        result,calls=self.refresh(draft())
        self.assertEqual((result,calls),(dict(used=0,failed=1,created=0),[]))
        self.assertEqual(self.rows('SELECT id,state,plan,evidence FROM agent_items ORDER BY id'),before)
        self.assertEqual(self.count('manual_tasks'),0)
        error,next_try=self.rows('SELECT error,next_try FROM agent_jobs WHERE id=?','school-task:'+ident)[0]
        self.assertIn('超过本轮',error);self.assertGreater(next_try,self.now.isoformat())
        self.assertEqual(self.refresh(draft(),minutes=1),(dict(used=0,failed=0,created=0),[]))

    def test_original_actions_keep_their_own_messages_dates_and_files(self):
        first=self.native_notice('dated-a',published='2026-02-10T08:00:00+08:00')
        paper_b=self.seed_pdf('b'*32,name='虚构独立回执.pdf')
        second=self.native_notice('dated-b',upload=paper_b,published='2026-02-11T08:00:00+08:00')
        ident=self.candidate(keys=first,ident='dated-pair')
        ref_a='message:%s:%s'%(first['source_id'],first['message_id']);ref_b='message:%s:%s'%(second['source_id'],second['message_id'])
        with self.store._db() as c:
            c.execute('UPDATE agent_items SET evidence=? WHERE id=?',
                      (json.dumps([dict(ref=ref_a,text=TEXT),dict(ref=ref_b,text=TEXT)]),ident))
        math='数学：明天完成练习卷第1至11页。';receipt='明天打印、签字并交回独立活动回执。'
        self.seed_groups(keys=first,note=math,uncertainties=[],upload_id=self.pdf,requirements=[math])
        self.seed_groups(keys=second,note=receipt,uncertainties=[],upload_id=paper_b,requirements=[receipt])
        reply={'actions':[
            dict(draft(goal=math),due='2026-02-11',existing_item_id=ident,basis=[dict(part='pdf:'+self.pdf+':1@'+ref_a,text=math)]),
            dict(draft(title='事务：签字交回活动回执',goal=receipt,purpose='admin'),due='2026-02-12',existing_item_id='',basis=[dict(part='pdf:'+paper_b+':1@'+ref_b,text=receipt)])]}
        result,_=self.refresh(reply)
        self.assertEqual((result['failed'],result['created']),(0,2))
        rows=self.rows('SELECT evidence,plan,due FROM agent_items ORDER BY due')
        self.assertEqual([[e['ref'] for e in json.loads(r[0])] for r in rows],[[ref_a],[ref_b]])
        self.assertEqual([[d['upload_id'] for d in json.loads(r[1])['school_task']['pdf_evidence']['documents']] for r in rows],[[self.pdf],[paper_b]])

    def scoped_original_tasks(self):
        self.store.app=self.app
        keys=self.native_notice('scoped-original')
        with self.store._db() as c:
            raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                    (keys['source_id'],keys['message_id'])).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(raw,text='要求见附件。')),keys['source_id'],keys['message_id']))
        receipt_file=self.seed_pdf('b'*32,name='虚构独立回执.pdf');self.link(keys,receipt_file)
        math='数学：2026-02-12前完成练习卷第1至11页，做完检查。'
        receipt='2026-02-13前签字交回独立活动回执。'
        self.seed_groups(keys=keys,note=math,uncertainties=[],upload_id=self.pdf,requirements=[math])
        self.seed_groups(keys=keys,note=receipt,uncertainties=[],upload_id=receipt_file,requirements=[receipt])
        ident=self.candidate(keys=keys,ident='scoped-original')
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[
            dict(draft(goal=math),due='2026-02-12',existing_item_id=ident,basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=math)]),
            dict(draft(title='事务：签字交回活动回执',goal=receipt,purpose='admin'),due='2026-02-13',existing_item_id='',basis=[dict(part='pdf:'+receipt_file+':1@'+ref,text=receipt)])]}
        result,_=self.refresh(reply);self.assertEqual(result,dict(used=1,failed=0,created=2))
        return keys,ident,receipt_file

    def test_same_message_originals_are_scoped_for_task_reading_print_and_check(self):
        app=self.app
        keys,ident,receipt_file=self.scoped_original_tasks();homework=self.item(ident)['task_id']
        before=self.rows('SELECT * FROM records')
        view=self.store.message(dict(keys,task_id=homework),app.upload_info)
        self.assertEqual((view['task_id'],[u['id'] for u in view['attachments']]),(homework,[self.pdf]))
        self.assertEqual([d['upload_id'] for d in view['pdf_material']['documents']],[self.pdf])
        self.assertTrue(all('回执' not in q['text'] for q in view['action_material']['quotes']))
        with patch.object(agent.Store,'_config',return_value=self.store._config()):
            with self.app.connect() as c:
                context=app.homework_material_context(c,homework)
            self.assertEqual(set(context['allowed']),{self.pdf})
            with self.assertRaises(app.family_print.PrintError):
                app.homework_print_sources(dict(task_id=homework,question_sources=[dict(type='upload',id=receipt_file)]))
        full=self.store.message(keys,app.upload_info)
        self.assertEqual({u['id'] for u in full['attachments']},{self.pdf,receipt_file})
        self.assertEqual(self.rows('SELECT * FROM records'),before)
        other=next(r[0] for r in self.rows('SELECT task_id FROM agent_items WHERE task_id!=?',homework))
        receipt=self.store.message(dict(keys,task_id=other),app.upload_info)
        self.assertEqual([u['id'] for u in receipt['attachments']],[receipt_file])

    def test_scoped_original_refuses_foreign_task_and_detached_anchor(self):
        app=self.app
        keys,ident,receipt_file=self.scoped_original_tasks();task_id=self.item(ident)['task_id']
        foreign=app.new_task(dict(child='示例乙',title='虚构其他孩子作业',category='homework'))
        with self.assertRaises(agent.AgentError):self.store.message(dict(keys,task_id=foreign['id']),app.upload_info)
        other=self.native_notice('unrelated-message')
        with self.assertRaises(agent.AgentError):self.store.message(dict(other,task_id=task_id),app.upload_info)
        self.link(keys,self.pdf,action=DETACH)
        with self.assertRaises(agent.AgentError):self.store.message(dict(keys,task_id=task_id),app.upload_info)
        with patch.object(agent.Store,'_config',return_value=self.store._config()):
            with self.app.connect() as c:context=app.homework_material_context(c,task_id)
        self.assertTrue(context['school_error']);self.assertEqual(context['allowed'],{})
        self.assertEqual(self.count('records'),0)

    def text_action_original(self,fragment=False):
        self.store.app=self.app
        text='数学：2026-02-12前完成口算10题，做完检查。'
        keys=self.school_fragment(text) if fragment else self.native_notice('text-with-receipt')
        if fragment:self.link(keys,self.pdf)
        else:
            with self.store._db() as c:
                raw=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                        (keys['source_id'],keys['message_id'])).fetchone()[0])
                c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                          (json.dumps(dict(raw,text=text,unread=True)),keys['source_id'],keys['message_id']))
        self.seed_groups(keys=keys,note='2026-02-13前签字交回独立活动回执。',uncertainties=[],requirements=['2026-02-13前签字交回独立活动回执。'])
        ident=self.candidate(keys=keys,ident='text-action')
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        receipt='2026-02-13前签字交回独立活动回执。'
        reply={'actions':[
            dict(draft(title='数学：口算10题',goal=text),due='2026-02-12',existing_item_id=ident,basis=[dict(part=ref,text=text)]),
            dict(draft(title='事务：签字交回独立活动回执',goal=receipt,purpose='admin',state='review',reason='独立回执留待核对。'),
                 due='2026-02-13',existing_item_id='',basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=receipt)])]}
        return keys,ident,reply

    def test_read_native_text_action_does_not_inherit_other_attachment_gap(self):
        keys,ident,reply=self.text_action_original()
        result,_=self.refresh(reply)
        self.assertEqual(result,dict(used=1,failed=0,created=1))
        row=self.item(ident);self.assertEqual(row['state'],'accepted')
        self.assertIn('口算10题',row['body'])
        brief=self.brief(ident)
        with self.store._db() as c:
            evidence,_=agent._school_material(self.store,c,row)
        self.assertEqual(brief['origin_basis'],agent._school_message_basis(evidence))
        view=self.store.message(dict(keys,task_id=row['task_id']),self.app.upload_info)
        self.assertEqual(view['attachments'],[])
        self.assertEqual(view['action_material']['quotes'][0]['upload_ids'],[])
        with patch.object(agent.Store,'_config',return_value=self.store._config()):
            with self.app.connect() as c:context=self.app.homework_material_context(c,row['task_id'])
        self.assertEqual(context['allowed'],{});self.assertFalse(context['school_error'])
        self.assertEqual(len(self.store.message(keys,self.app.upload_info)['attachments']),1)

    def test_text_scope_does_not_promote_a_screenshot_fragment(self):
        _,ident,reply=self.text_action_original(fragment=True)
        result,_=self.refresh(reply)
        self.assertEqual((result['created'],self.count('manual_tasks'),self.item(ident)['state']),(0,0,'pending'))
        self.assertEqual(self.brief(ident)['state'],'review')

    def test_two_originals_require_both_complete_before_one_school_round(self):
        keys,reference=self.multi_originals()
        ident=self.candidate(keys=keys,ident='multi')
        before=self.item(ident)
        note='数学：2026-02-12前完成练习卷第1至11页，做完检查。'
        self.seed_groups(keys=keys,note=note,uncertainties=[],upload_id=self.pdf,requirements=[note])
        self.assertIsNone(self.material(keys))
        self.assertEqual(self.refresh(draft()),(dict(used=0,failed=0,created=0),[]))
        self.assertEqual(self.item(ident),before)
        self.seed_groups(keys=keys,note='本附件为上述练习卷的家长核对参考，不是孩子作答。',uncertainties=[],upload_id=reference,requirements=[])
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

    def test_reference_background_stays_accessible_without_becoming_goal_or_deadline(self):
        self.store.app=self.app
        keys,reference=self.multi_originals()
        requirement='数学：2026-02-12前完成练习卷第1至3题，写明单位，做完检查，无需家长签字。'
        background='家长核对参考，印刷日期2026-02-13；本页不是孩子作答，也不是签字要求。'
        self.seed_groups(keys=keys,uncertainties=[],upload_id=self.pdf,requirements=[requirement])
        self.seed_groups(keys=keys,note=background,uncertainties=[],upload_id=reference,requirements=[])
        ident=self.candidate(keys=keys,ident='reference-context')
        result,_=self.refresh(draft(goal='短摘要'))
        row=self.item(ident)
        self.assertEqual((result['created'],row['body'],row['due']),(1,requirement,'2026-02-12'))
        view=self.store.message(dict(keys,task_id=row['task_id']),self.app.upload_info)
        self.assertEqual({a['id'] for a in view['attachments']},{self.pdf,reference})
        self.assertEqual(self.count('records'),0)
        with self.store._db() as c:
            evidence,_=agent._school_material(self.store,c,row)
            pdf=agent._pdf_evidence(agent._school_pdf(self.store,c,row))
        self.assertEqual(agent._school_saved_requirements(row,agent._school_original_parts(evidence,pdf,None)),[requirement])

    def test_reference_reading_gap_does_not_become_a_complete_school_requirement(self):
        keys,reference=self.multi_originals()
        self.seed_groups(keys=keys,note=TEXT,uncertainties=[],upload_id=self.pdf)
        self.seed_groups(keys=keys,note='家长参考。',uncertainties=['参考最后一页看不清'],upload_id=reference,requirements=[])
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
        self.seed_groups(keys=keys,note=text,uncertainties=[],requirements=[text])
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
        self.seed_groups(keys=keys,note='数学：2月12日前完成练习卷第1至11页。',uncertainties=[],requirements=['数学：2月12日前完成练习卷第1至11页。'])
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
        self.seed_groups(keys=keys,note='题目原件：完成练习卷第1至11页。',uncertainties=[],upload_id=self.pdf,requirements=['题目原件：完成练习卷第1至11页。'])
        self.seed_groups(keys=keys,note='家长参考：第1题答案为3，不是孩子作答。',uncertainties=[],upload_id=reference,requirements=[])
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
        item = dict(child_id='child-1', kind='school', title=title, body=brief.get('goal') or agent.FOCUS['school'], due='',
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
            if 'original_parts' in context and isinstance(result,dict) and set(result)=={'actions'}:
                result=copy.deepcopy(result)
                # Old fixtures identify the page group. Map only the identical whole
                # requirement, never turn a partial quote into the full requirement.
                for action in result['actions']:
                    for quote in action['basis']:
                        matches=[part for part in context['original_parts'] if part.get('requirement')
                                 and part['id'].split(':requirement:',1)[0]==quote['part']
                                 and part['text']==quote['text']]
                        if len(matches)==1:
                            quote['part']=matches[0]['id']
            if 'original_parts' in context and isinstance(result,dict) and set(result)==set(agent.TASK_BRIEF_SCHEMA['required']):
                # A single-draft fixture still assigns every complete requirement.
                # Identical requirements shared by originals may support one action;
                # distinct requirements retain separate actions and file ownership.
                parts=context['original_parts'];groups=[]
                for part in parts:
                    if not part.get('requirement'):continue
                    selected=next((group for group in groups if group[0]['text']==part['text']),None)
                    if selected is None:groups.append([part])
                    else:selected.append(part)
                # A reference attachment remains explicitly attached to the action
                # from the same message. It never becomes an invented requirement.
                for selected in groups:
                    refs={part['ref'] for part in selected};seen={u for part in selected for u in part['upload_ids']}
                    for part in parts:
                        if part.get('background_only') and part['ref'] in refs and part['text'].strip() and not set(part['upload_ids'])<=seen:
                            selected.append(part);seen.update(part['upload_ids'])
                if not groups:
                    selected=[];seen=set()
                    for part in parts:
                        if part['upload_ids'] and part['text'].strip() and not set(part['upload_ids'])<=seen:
                            selected.append(part);seen.update(part['upload_ids'])
                    groups=[selected or [parts[0]]]
                actions=[]
                for index,selected in enumerate(groups):
                    basis=[dict(part=part['id'],text=part['text'] if part.get('requirement') else part['text'][:2000])
                           for part in selected]
                    actions.append(dict(result,due='',existing_item_id=context['candidate_id'] if index==0 else '',basis=basis))
                return {'actions':actions}
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
                old=dict(draft(goal=TEXT,state='review',reason='原件或具体要求尚未读全。'),policy=7,
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
                keys=self.native_notice(key,published=published);self.seed_groups(keys=keys,note=note,uncertainties=[],requirements=[note])
                ident=self.candidate(keys=keys,ident=key)
                result,calls=self.refresh(draft(goal=note))
                row=self.item(ident)
                self.assertEqual((result['used'],len(calls),row['state'],row['due']),(1,1,state,due))
                if reason:self.assertIn(reason,self.brief(ident)['reason'])
                self.assertEqual(self.brief(ident)['state'],'ready' if state=='accepted' else 'review')

    def test_complete_requirements_survive_clipped_background_but_uncovered_messages_do_not(self):
        keys=self.native_notice();ident=self.candidate(keys=keys)
        self.seed_groups(BATCHES[:3],keys=keys,note=TEXT+'摘'*2000,uncertainties=[],requirements=[TEXT])
        self.assertEqual(self.refresh(draft()),(dict(used=0,failed=0,created=0),[]))
        last='本练习2026-02-12前提交，做完检查。'
        self.seed_groups(BATCHES[3:],keys=keys,note=last+'摘'*2000,uncertainties=[],requirements=[last])
        ref='message:%s:%s'%(keys['source_id'],keys['message_id'])
        reply={'actions':[dict(draft(goal='短摘要'),due='2026-02-12',existing_item_id=ident,
            basis=[dict(part='pdf:'+self.pdf+':1@'+ref,text=TEXT),dict(part='pdf:'+self.pdf+':10@'+ref,text=last)])]}
        result,calls=self.refresh(reply)
        self.assertEqual((result['used'],result['created'],self.brief(ident)['state'],self.count('manual_tasks')),(1,1,'ready',1))
        self.assertEqual((self.item(ident)['body'],self.item(ident)['due']),(TEXT+'\n'+last,'2026-02-12'))
        doc=json.loads(calls[0][1]['content'])['pdf_material'][0]
        context=json.loads(calls[0][1]['content'])
        self.assertEqual(doc['requirements_in'],'original_parts')
        self.assertTrue(all('requirements' not in g for g in doc['groups']))
        self.assertEqual([p['text'] for p in context['original_parts'] if p.get('requirement')],[TEXT,last])
        self.assertTrue(any(g['text_truncated'] for g in doc['groups']))
        self.assertEqual(self.rows('SELECT original_status FROM manual_tasks'),[('待跟进',)])
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
        keys=self.native_notice();self.seed_groups(keys=keys,note=TEXT+'示例日期（并非本次要求）：2026-02-12报名表样例。',uncertainties=[],requirements=[TEXT])
        ident=self.candidate(keys=keys)
        result,calls=self.refresh(draft())
        self.assertEqual((result['used'],len(calls),self.item(ident)['due'],self.item(ident)['state'],self.count('manual_tasks')),(1,1,'','accepted',1))
        self.assertEqual((self.item(ident)['body'],self.rows('SELECT due,original_status FROM manual_tasks')),
                         (TEXT,[('无明确截止','待跟进')]))

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

    def test_clipped_background_keeps_page_groups_but_cannot_invent_an_action(self):
        self.seed_groups(note='摘' * 3000,requirements=[]); ident = self.candidate()
        before=self.item(ident)
        result, calls = self.refresh(draft())
        doc = json.loads(calls[0][1]['content'])['pdf_material'][0]
        self.assertEqual((doc['complete'], doc['processed_pages'], [g['pages'] for g in doc['groups']], doc['truncated_groups'], doc['omitted_groups']),
                         (True, list(range(1, 12)), BATCHES, [], []))
        self.assertEqual(sum(len(g['text']) for g in doc['groups']), agent.PDF_TEXT_LIMIT)
        self.assertEqual([g['text_truncated'] for g in doc['groups']],[False,True,True,True])
        self.assertTrue(all('requirements' not in g for g in doc['groups']))
        self.assertFalse(any(p.get('requirement') for p in json.loads(calls[0][1]['content'])['original_parts']))
        self.assertEqual((result['failed'],result['created'],self.count('manual_tasks'),self.item(ident)),(1,0,0,before))
        self.assertEqual(sorted(p for group in self.material()['batches'] for p in group['pages']),list(range(1,12)))

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
                group=json.loads(c.execute('SELECT payload FROM agent_pdf_material WHERE fingerprint=? AND first_page=1',
                                           (evidence['fingerprint'],)).fetchone()[0])
                group['originals'][0]['note']='新核对摘要'
                c.execute('UPDATE agent_pdf_material SET payload=? WHERE fingerprint=? AND first_page=1',
                          (json.dumps(group),evidence['fingerprint']))
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

    def test_word_full_coverage_keeps_clipping_explicit_without_inventing_an_action(self):
        self.link(self.keys, self.pdf, action=DETACH)
        self.pdf = self.seed_docx('f' * 32); self.link(self.keys, self.pdf)
        batches = [[1, 4, 7], [2, 5, 8], [3, 6, 9], [10, 11]]
        self.seed_groups(batches, note='摘' * 3000,requirements=[]); ident = self.candidate()
        before=self.item(ident)
        with no_convert(), no_pages():
            result, calls = self.refresh(draft())
        doc = json.loads(calls[0][1]['content'])['pdf_material'][0]
        self.assertEqual((result['used'], doc['original'], doc['complete'], doc['processed_pages']), (1, 'docx', True, list(range(1,12))))
        self.assertEqual((doc['truncated_groups'], doc['omitted_groups']), ([], []))
        self.assertEqual(sum(len(g['text']) for g in doc['groups']), 6000)
        self.assertEqual([g['pages'] for g in doc['groups']],batches)
        self.assertEqual([g['text_truncated'] for g in doc['groups']],[False,True,True,True])
        self.assertTrue(all('requirements' not in g for g in doc['groups']))
        self.assertFalse(any(p.get('requirement') for p in json.loads(calls[0][1]['content'])['original_parts']))
        self.assertEqual((result['failed'],result['created'],self.count('manual_tasks'),self.item(ident)),(1,0,0,before))


if __name__ == '__main__':
    unittest.main()

"""Run python3 test_homework_review.py. Synthetic temporary files; no model, printer or household service."""
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import family_llm
import family_pdf
import family_print
from test_print import png


def item(**changes):
    return dict(label='第1题',question='',student_answer='B',answer='教师参考：B',judgment='correct',
                error_reason='',possible_cause='',steps='',uncertainty='')|changes


def refused(fn,code=None,status=None):
    try: fn()
    except ValueError as error:
        if code is not None: assert error.code==code,(error.code,code)
        if status is not None: assert error.status==status,(error.status,status)
    else: raise AssertionError('expected refusal')


def run():
    with tempfile.TemporaryDirectory(prefix='synthetic-homework-review-') as temporary:
        root=Path(temporary);data=root/'private';data.mkdir()
        with patch.dict(os.environ,{'FAMILY_DATA':str(data)}):
            import app
        with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
            (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 8岁 | 二年级 |\n')
            (root/'跟踪台账.md').write_text('')
            def upload(name,body): return app.save_upload(io.BytesIO(body),len(body),name)['id']
            answer=upload('synthetic-answer.png',png())
            reference=upload('synthetic-reference.txt',b'1. B\n')
            paper=upload('synthetic-paper.pdf',b'%PDF-synthetic-paper')
            teacher_pdf=upload('synthetic-teacher.pdf',b'%PDF-synthetic-teacher')
            other=upload('synthetic-other.png',png(3))
            task=app.new_task(dict(child='示例甲',title='虚构试卷核对',category='homework',action='按题号核对',request_key='synthetic-homework-task-1'))
            another=app.new_task(dict(child='示例乙',title='虚构另一孩子作业',category='homework',request_key='synthetic-homework-task-2'))
            app.save_task_feedback(dict(task_id=another['id'],child='示例乙',day='2026-10-01',request_key='synthetic-other-feedback',attachments=[other]))
            saved=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-01',request_key='synthetic-answer-feedback',attachments=[answer,reference,teacher_pdf]))
            rid=saved['record_id'];created=saved['feedback']['created']
            source=lambda ident,**extra:dict(type='upload',id=ident,**extra)
            request=dict(purpose='review',task_id=task['id'],record_id=rid,expected_created=created,
                         question_sources=[source(answer)],reference_sources=[source(reference)])
            def fake_model(messages,schema,name,timeout,**kwargs):
                serialized=json.dumps(messages,ensure_ascii=False)
                assert '教师参考原文' in serialized and '1. B' in serialized
                assert '不执行' in serialized and '不擅自改写老师答案' in serialized
                return dict(items=[item()],coverage='仅按明确题号比较教师参考；原题未提供')
            with patch.object(family_llm,'_chat_json',side_effect=fake_model) as model:
                result=app.homework_review_draft(request)
                assert model.call_count==1
            assert result['draft']['questions'][0]['question']==''
            assert result['draft']['questions'][0]['judgment']=='correct'
            assert '教师参考：B' in result['draft']['text'] and result['draft']['items']==1
            basis=result['review_basis'];assert basis['photo_ids']==[answer,reference]
            with app.connect() as c:
                before='\n'.join(c.iterdump());context=app.homework_review_context(c,task['id'],rid)
                assert set(context['allowed'])=={answer,reference,teacher_pdf}
                assert '\n'.join(c.iterdump())==before,'source listing must not write'
            # Neither arbitrary uploads, archive paths nor other-child records may enter a model request.
            with patch.object(family_llm,'_chat_json') as model:
                refused(lambda:app.homework_review_draft(request|dict(reference_sources=[source(other)])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(request|dict(question_sources=[dict(type='attachment',name='elsewhere.pdf')])))
                refused(lambda:app.homework_review_draft(request|dict(task_id=another['id'])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(request|dict(expected_created='stale')),'review_source_changed')
                assert model.call_count==0
            # Program-written partial-page coverage; 3/3/1 groups share one decreasing deadline.
            calls=[]
            def render(body,pages,deadline):
                calls.append((list(pages),deadline))
                return dict(page_count=11,pages=[dict(page=p,mime_type='image/png',data=png()) for p in pages],
                            omitted_pages=[p for p in range(1,12) if p not in pages],complete=False)
            with patch.object(family_pdf,'page_count',return_value=11),patch.object(family_pdf,'render_pages',side_effect=render),patch.object(family_llm,'_chat_json',return_value=dict(items=[item(question='选择正确答案\n保留条件')],coverage='第1题')):
                selected=app.homework_review_draft(request|dict(reference_sources=[source(teacher_pdf,pages=list(range(1,8)))]))
            assert [pages for pages,_ in calls]==[[1,2,3],[4,5,6],[7]]
            assert all(0<deadline<=20 for _,deadline in calls) and calls[-1][1]<=calls[0][1]
            assert '未读取页：8-11' in selected['draft']['text'] and '未读取页：8-11' in selected['draft']['coverage']
            with patch.object(family_pdf,'page_count',return_value=11),patch.object(family_pdf,'render_pages') as renderer,patch.object(family_llm,'_chat_json') as model:
                refused(lambda:app.homework_review_draft(request|dict(reference_sources=[source(teacher_pdf)])))
                refused(lambda:app.homework_review_draft(request|dict(reference_sources=[source(teacher_pdf,pages=[True])])))
                assert renderer.call_count==model.call_count==0,'oversize/invalid PDF request must not render or call the model'
            # Missing mappings remain unknown; a conflicting teacher answer is retained rather than overwritten.
            conflict=item(judgment='unknown',answer='教师参考：B',uncertainty='教师参考与可见题面冲突，待老师核对')
            unknown=item(label='题号不明',judgment='unknown',answer='',student_answer='',uncertainty='题号无法对应')
            with patch.object(family_llm,'_chat_json',return_value=dict(items=[conflict,unknown],coverage='仅这些题')):
                draft=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                    reference_documents=[dict(name='synthetic-reference.txt',text='1. B')])
            assert draft['questions'][0]['answer']=='教师参考：B'
            assert draft['unknown_items']==2 and draft['wrong_items']==0
            # Every material participates in the save guard, not just the answer photo.
            feedback=dict(task_id=task['id'],child='示例甲',day='2026-10-01',request_key='synthetic-reviewed-feedback',
                          note='虚构已核对参考比较，原题要求待补',attachments=[answer,reference],review_basis=basis)
            with app.connect() as c: before='\n'.join(c.iterdump())
            (data/'uploads'/reference).write_bytes(b'1. C\n')
            refused(lambda:app.save_task_feedback(feedback),'review_basis_changed')
            with app.connect() as c: assert '\n'.join(c.iterdump())==before,'stale guard must roll back the entire feedback'
            (data/'uploads'/reference).write_bytes(b'1. B\n')
            refused(lambda:app.save_task_feedback(feedback|dict(attachments=[answer])),'review_basis_changed')
            refused(lambda:app.save_task_feedback(feedback|dict(review_basis=basis|dict(reference_sources=[source(answer)]))),'review_basis_invalid')
            reviewed=app.save_task_feedback(feedback);assert not reviewed['completion_changed']
            (data/'uploads'/reference).write_bytes(b'1. C\n')
            assert app.save_task_feedback(feedback)['replayed'],'known same-key retry keeps its original saved receipt'
            # Recreate r155's ordinary-feedback payload/hash, then replay it through the upgraded endpoint.
            legacy_text='虚构r155初检：第1题尚缺老师依据。'
            legacy_opinion=upload('作业批改参考-'+str(rid)+'.txt',legacy_text.encode())
            r155_feedback=feedback|dict(request_key='synthetic-r155-review-retry',
                note='家长核对的作业批改参考；完整逐题意见见文字附件。原作答反馈 #'+str(rid)+'。',
                attachments=feedback['attachments']+[legacy_opinion],
                review_basis={k:v for k,v in basis.items() if k!='previous_sources'})
            r155_record=dict(child='示例甲',source='事项:'+task['id'],title=('反馈：'+task['title'])[:200],
                day=r155_feedback['day'],category='学习进展',subject='',note=r155_feedback['note'],transcript='',transcript_state='',assistance='',
                attachments=r155_feedback['attachments'],review_basis=r155_feedback['review_basis'],request_key=r155_feedback['request_key'],
                completion=dict(complete=False,note=''))
            (data/'uploads'/reference).write_bytes(b'1. B\n')
            r155_saved=app._save_record(r155_record,False,{})
            (data/'uploads'/reference).write_bytes(b'1. C\n')
            with app.connect() as c: before='\n'.join(c.iterdump())
            replayed=app.save_task_feedback(r155_feedback)
            assert replayed['replayed'] and replayed['record_id']==r155_saved['record_id']
            with app.connect() as c:
                assert '\n'.join(c.iterdump())==before,'r155 retry preserves the old hash and writes nothing'
                row=c.execute('SELECT followup_kind,related_record_id FROM records WHERE id=?',(r155_saved['record_id'],)).fetchone()
                assert row['followup_kind']=='' and row['related_record_id'] is None,'r155 ordinary feedback is not relabelled on replay'
                context=app.homework_review_context(c,task['id'],rid)
                assert context['allowed'][legacy_opinion]['origin']=='review_result','known r155 output is previous opinion without migrating its record'
                assert context['allowed'][reference]['origin']!='review_result','the actual teacher input keeps its original identity'
                assert '\n'.join(c.iterdump())==before,'legacy role listing writes no rows or request hashes'
            with patch.object(family_llm,'_chat_json') as model:
                refused(lambda:app.homework_review_draft(request|dict(reference_sources=[source(legacy_opinion)])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(request|dict(question_sources=[source(legacy_opinion)])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(request|dict(record_id=r155_saved['record_id'],expected_created=replayed['feedback']['created'])),'review_source_not_allowed')
                assert model.call_count==0,'old AI text cannot enter teacher or answer roles'
            (data/'uploads'/reference).write_bytes(b'1. B\n')
            with patch.object(family_llm,'homework_reference_draft',wraps=family_llm.homework_reference_draft) as generate,patch.object(family_llm,'_chat_json',return_value=dict(items=[item()],coverage='虚构旧意见复核')):
                app.homework_review_draft(request|dict(previous_sources=[source(legacy_opinion)]))
                assert generate.call_args.kwargs['previous_documents']==[dict(name='作业批改参考-'+str(rid)+'.txt',text=legacy_text)]
            # A same-child original report can provide the electronic worksheet without re-uploading it.
            store=app.study_store()
            with store._db() as c:
                columns={r[1] for r in c.execute('PRAGMA table_info(study_items)')}
                assert 'report' in columns
            reported=store.save_item(dict(child_id='child-1',day='2026-10-01',request_key='synthetic-reported-paper',version=0,
                title='虚构电子试卷',subject='语文',planned_minutes=None,report=dict(text='',explanation='',goal='完成这份试卷',attachments=[paper])))
            report_task=reported['saved_item_id']
            record=app.save_task_feedback(dict(task_id=report_task,child='示例甲',day='2026-10-01',request_key='synthetic-report-answer',attachments=[answer]))
            with app.connect() as c: ctx=app.homework_review_context(c,report_task,record['record_id'])
            assert ctx['allowed'][paper]['origin']=='reported_homework'
            # A later reference-only feedback belongs to the same task and remains available for the original answer.
            later=upload('synthetic-later-reference.txt',b'1. B\n')
            app.save_task_feedback(dict(task_id=report_task,child='示例甲',day='2026-10-01',request_key='synthetic-later-reference',attachments=[later]))
            with app.connect() as c: ctx=app.homework_review_context(c,report_task,record['record_id'])
            assert ctx['allowed'][later]['origin']=='same_task'
            # Byte-preserving guard rechecks role/order/page fingerprints without probing PDF tools.
            with patch.object(family_pdf,'page_count') as probe,patch.object(family_pdf,'render_pages') as renderer:
                with app.connect() as c: app.guard_homework_review(c,task['id'],selected['review_basis'],[answer,teacher_pdf])
                assert probe.call_count==renderer.call_count==0
            # Reuse only a source explicitly bound to this same task/child; revocation invalidates its old result.
            school_file=upload('synthetic-school-reference.txt',b'1. B\n')
            app.agent_store()  # Initialize only the temporary synthetic database's existing Agent tables.
            school=dict(id='synthetic-school',platform='qq',child_id='child-1',name='虚构学校来源',enabled=True)
            message=dict(id='synthetic-message',time='2026-10-01T12:00:00+08:00',kind='text',sender='虚构老师',text='虚构作业参考',unread=False)
            with app.connect() as c:
                c.execute('INSERT INTO agent_sources (id,binding,cursor) VALUES (?,?,?)',(school['id'],json.dumps(['qq','child-1'],separators=(',',':')),''))
                c.execute('INSERT INTO agent_messages (source_id,id,payload) VALUES (?,?,?)',(school['id'],message['id'],json.dumps(message)))
                c.execute('INSERT INTO agent_message_attachments VALUES (?,?,?)',(school['id'],message['id'],school_file))
            with patch.object(app.family_agent.Store,'_config',return_value=dict(enabled=True,sources=[school])):
                school_task=app.new_task(dict(child='示例甲',title='虚构学校原件复用',category='homework',source='message:synthetic-school:synthetic-message',request_key='synthetic-school-task'))
                school_saved=app.save_task_feedback(dict(task_id=school_task['id'],child='示例甲',day='2026-10-01',request_key='synthetic-school-answer',attachments=[answer]))
                with app.connect() as c: ctx=app.homework_review_context(c,school_task['id'],school_saved['record_id'])
                assert ctx['allowed'][school_file]['origin']=='school' and not ctx['school_error']
                school_request=dict(purpose='review',task_id=school_task['id'],record_id=school_saved['record_id'],expected_created=school_saved['feedback']['created'],
                                    question_sources=[source(answer)],reference_sources=[source(school_file)])
                with patch.object(family_llm,'_chat_json',return_value=dict(items=[item()],coverage='仅教师参考比较')):
                    school_result=app.homework_review_draft(school_request)
                assert school_result['review_basis']['photo_ids']==[answer]
                school['enabled']=False
                with app.connect() as c:
                    refused(lambda:app.guard_homework_review(c,school_task['id'],school_result['review_basis'],[answer,school_file]),'review_basis_changed')
                school['enabled']=True;school['child_id']='child-2'
                with app.connect() as c:
                    refused(lambda:app.guard_homework_review(c,school_task['id'],school_result['review_basis'],[answer,school_file]),'review_basis_changed')
            # One recheck flow: parent clarification, previous opinion, later teacher reference and append-only results.
            def dump():
                with app.connect() as c: return '\n'.join(c.iterdump())
            def version(ident,value):
                with app.connect() as c: c.execute('UPDATE records SET created=? WHERE id=?',(value,ident))
            def rejected_unchanged(fn,code=None,status=409):
                before=dump()
                refused(fn,code,status)
                assert dump()==before,'rejected review must leave all records and revisions unchanged'
            action='虚构作业要求：每题写出判断理由，不省略第2题'
            recheck_task=app.new_task(dict(child='示例甲',title='虚构初检后补参考',category='homework',action=action,request_key='synthetic-recheck-task'))
            recheck_answer=upload('synthetic-recheck-answer.png',png(4))
            old_teacher=upload('synthetic-recheck-old-teacher.txt',b'1. B\n')
            original=app.save_task_feedback(dict(task_id=recheck_task['id'],child='示例甲',day='2026-10-02',
                request_key='synthetic-recheck-original',attachments=[recheck_answer,old_teacher]))
            original_id=original['record_id']
            initial_request=dict(purpose='review',task_id=recheck_task['id'],record_id=original_id,expected_created=original['feedback']['created'],
                question_sources=[source(recheck_answer)],reference_sources=[source(old_teacher)])
            model_result=dict(items=[item()],coverage='虚构仅核第1题')
            with patch.object(family_llm,'_chat_json',return_value=model_result): initial=app.homework_review_draft(initial_request)
            assert not initial['draft'].get('comparison'),'old model output without comparison remains readable'
            legacy_basis={k:v for k,v in initial['review_basis'].items() if k!='previous_sources'}
            assert app.homework_review_basis(legacy_basis)==legacy_basis
            prior_text='虚构初检：第1题一致，第2题尚未检查。'
            review_name='作业批改参考-'+str(original_id)+'.txt'
            review_note='家长核对的作业批改参考；完整逐题意见见文字附件。原作答反馈 #'+str(original_id)+'。'
            prior=upload(review_name,prior_text.encode())
            first_feedback=dict(task_id=recheck_task['id'],child='示例甲',day='2026-10-02',request_key='synthetic-recheck-first',
                note=review_note,attachments=[recheck_answer,old_teacher,prior],review_basis=legacy_basis)
            first=app.save_task_feedback(first_feedback)
            later_teacher=upload('synthetic-recheck-later-teacher.txt','虚构教师参考：第1题B，第2题必须写理由。'.encode())
            app.save_task_feedback(dict(task_id=recheck_task['id'],child='示例甲',day='2026-10-02',request_key='synthetic-recheck-later-teacher',attachments=[later_teacher]))
            with app.connect() as c:
                ctx=app.homework_review_context(c,recheck_task['id'],original_id)
                assert ctx['allowed'][prior]['origin']=='review_result'
                assert ctx['allowed'][old_teacher]['origin']!='review_result','a reused teacher original keeps its identity'
            instruction='虚构补充：第2题被漏查，请按新教师参考复核。'
            previous_text='虚构未保存初检补充：第2题曾被跳过。'
            recheck_request=initial_request|dict(reference_sources=[source(later_teacher)],previous_sources=[source(prior)],
                review_instruction=instruction,previous_text=previous_text)
            comparison='虚构复核差异：第1题不变，新增第2题理由缺漏；只核对所选范围。'
            recheck_model_result=model_result|dict(comparison=comparison)
            def recheck_model(messages,schema,name,timeout,**kwargs):
                serialized=json.dumps(messages,ensure_ascii=False)
                assert all(text in serialized for text in (action,instruction,prior_text,previous_text,'第2题必须写理由'))
                return recheck_model_result
            with patch.object(family_llm,'homework_reference_draft',wraps=family_llm.homework_reference_draft) as generate,patch.object(family_llm,'_chat_json',side_effect=recheck_model):
                rechecked=app.homework_review_draft(recheck_request)
                args=generate.call_args.kwargs
                assert args['task_action']==action and args['review_instruction']==instruction and args['previous_text']==previous_text
                assert args['previous_documents']==[dict(name=review_name,text=prior_text)]
                assert args['reference_documents']==[dict(name='synthetic-recheck-later-teacher.txt',text='虚构教师参考：第1题B，第2题必须写理由。')]
            assert rechecked['draft']['comparison']==comparison
            assert comparison in rechecked['draft']['text'],'comparison must be included in the persisted review text'
            foreign_previous=upload('synthetic-recheck-other-child.txt',b'Synthetic other-child opinion')
            app.save_task_feedback(dict(task_id=another['id'],child='示例乙',day='2026-10-02',request_key='synthetic-recheck-other-child',attachments=[foreign_previous]))
            unrelated_previous=upload('synthetic-recheck-other-task.txt',b'Synthetic unrelated-task opinion')
            app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-02',request_key='synthetic-recheck-other-task',attachments=[unrelated_previous]))
            with patch.object(family_llm,'_chat_json') as model:
                for ident in (foreign_previous,unrelated_previous):
                    refused(lambda:app.homework_review_draft(recheck_request|dict(previous_sources=[source(ident)])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(recheck_request|dict(reference_sources=[source(prior)])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(recheck_request|dict(question_sources=[source(prior)])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(recheck_request|dict(record_id=first['record_id'],expected_created=first['feedback']['created'])),'review_source_not_allowed')
                refused(lambda:app.homework_review_draft(recheck_request|dict(review_instruction='字'*1001)))
                refused(lambda:app.homework_review_draft(recheck_request|dict(previous_text='字'*12001)))
                refused(lambda:app.homework_review_draft(recheck_request|dict(previous_sources=[source(prior)]*3)))
                assert model.call_count==0
            changed={};prior_created=first['feedback']['created']
            def changed_during_generation(*args,**kwargs):
                version(first['record_id'],'2026-10-02T01:02:03.000001');changed['dump']=dump()
                return recheck_model_result
            with patch.object(family_llm,'_chat_json',side_effect=changed_during_generation):
                refused(lambda:app.homework_review_draft(recheck_request),'review_basis_changed',409)
            assert dump()==changed['dump'],'generation with a changed previous record writes no result'
            version(first['record_id'],prior_created)
            final_text=upload(review_name,rechecked['draft']['text'].encode())
            final_feedback=dict(task_id=recheck_task['id'],child='示例甲',day='2026-10-02',request_key='synthetic-recheck-final',
                note=review_note,attachments=[recheck_answer,later_teacher,prior,final_text],review_basis=rechecked['review_basis'],
                comparison_note=comparison,related_record_id=first['record_id'],followup_kind='订正')
            version(first['record_id'],'2026-10-02T01:02:03.000002')
            rejected_unchanged(lambda:app.save_task_feedback(final_feedback),'review_basis_changed')
            version(first['record_id'],prior_created)
            final=app.save_task_feedback(final_feedback);assert not final['completion_changed']
            with app.connect() as c:
                rows={r['id']:dict(r) for r in c.execute('SELECT * FROM records WHERE source=?',('事项:'+recheck_task['id'],))}
                assert len(rows)==4 and first['record_id']!=final['record_id']
                for ident in (first['record_id'],final['record_id']):
                    assert rows[ident]['related_record_id']==original_id and rows[ident]['followup_kind']=='作业检查'
                assert rows[first['record_id']]['note']==review_note and rows[final['record_id']]['comparison_note']==comparison
                assert prior in json.loads(rows[first['record_id']]['attachments']) and final_text in json.loads(rows[final['record_id']]['attachments'])
                assert (data/'uploads'/final_text).read_text()==rechecked['draft']['text']
                ctx=app.homework_review_context(c,recheck_task['id'],original_id)
                assert ctx['allowed'][prior]['review_binding']==[first['record_id'],prior_created],'appending a result preserves the prior opinion binding checked by the save transaction'
            rejected_unchanged(lambda:app.save_task_feedback(dict(task_id=recheck_task['id'],child='示例甲',day='2026-10-02',
                record_id=first['record_id'],expected_created=prior_created,note='虚构试图覆盖初检')),status=None)
            (data/'uploads'/old_teacher).write_bytes(b'1. C\n')
            assert app.save_task_feedback(first_feedback)['replayed'],'old-basis retry returns the saved initial check after its original material changes'
            (data/'uploads'/old_teacher).write_bytes(b'1. B\n')
            # Correcting the ordinary answer itself never relabels it as a generated check.
            with patch.object(family_llm,'_chat_json',return_value=model_result): correction_basis=app.homework_review_draft(initial_request)['review_basis']
            app.save_task_feedback(dict(task_id=recheck_task['id'],child='示例甲',record_id=original_id,expected_created=original['feedback']['created'],
                note='虚构更正原作答说明',review_basis=correction_basis))
            with app.connect() as c:
                row=c.execute('SELECT related_record_id,followup_kind FROM records WHERE id=?',(original_id,)).fetchone()
                assert row['related_record_id'] is None and row['followup_kind']=='','ordinary answer type and relationship survive a basis-bearing correction'
                current_created=c.execute('SELECT created FROM records WHERE id=?',(original_id,)).fetchone()['created']
            # A saved history may be larger than the bounded latest opinion sent for the next recheck.
            latest='最新核查'*2000;archive='历史不入模'*3200
            assert len(latest)==8000 and len(archive)==16000
            def saved_opinion(name,text,key):
                ident=upload(name,text.encode())
                app._save_record(dict(child='示例甲',day='2026-10-02',category='学习进展',title='虚构已保存检查',
                    source='事项:'+recheck_task['id'],note='虚构检查格式原件',attachments=[ident],
                    related_record_id=original_id,followup_kind='作业检查',request_key=key),False,{})
                return ident
            framed='作业检查保存格式 v1\n最新检查字数：8000\n'+latest+'\n此前检查草稿（仅供对照，不是教师参考）：\n'+archive
            framed_id=saved_opinion('synthetic-framed-opinion.txt',framed,'synthetic-framed-opinion')
            framed_request=initial_request|dict(expected_created=current_created,previous_sources=[source(framed_id)])
            def framed_model(messages,schema,name,timeout,**kwargs):
                serialized=json.dumps(messages,ensure_ascii=False)
                assert latest in serialized and '历史不入模' not in serialized,'archive stays saved but never enters the current model input'
                return recheck_model_result
            before=dump()
            with patch.object(family_llm,'homework_reference_draft',wraps=family_llm.homework_reference_draft) as generate,patch.object(family_llm,'_chat_json',side_effect=framed_model) as model:
                app.homework_review_draft(framed_request)
                assert model.call_count==1
                assert generate.call_args.kwargs['previous_documents']==[dict(name='synthetic-framed-opinion.txt',text=latest)]
            assert dump()==before,'reading a framed history writes no records'
            invalid_frames=[
                '作业检查保存格式 v1\n最新检查字数：错误\n甲',
                '作业检查保存格式 v1\n最新检查字数：0\n甲',
                '作业检查保存格式 v1\n最新检查字数：12001\n'+'甲'*12001,
                '作业检查保存格式 v1\n最新检查字数：20\n短',
                '作业检查保存格式 v1\n最新检查字数：2\nabc',
            ]
            with patch.object(family_llm,'_chat_json') as model:
                for n,text in enumerate(invalid_frames):
                    ident=saved_opinion('synthetic-invalid-framed-'+str(n)+'.txt',text,'synthetic-invalid-framed-'+str(n))
                    before=dump()
                    refused(lambda:app.homework_review_draft(framed_request|dict(previous_sources=[source(ident)])))
                    assert dump()==before,'invalid framed history must not write a result'
                assert model.call_count==0,'invalid lengths are rejected before any model call'
    print('homework review synthetic checks passed')


if __name__=='__main__': run()

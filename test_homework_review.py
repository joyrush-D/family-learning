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


def refused(fn,code=None):
    try: fn()
    except ValueError as error:
        if code is not None: assert error.code==code,(error.code,code)
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
            with patch.object(family_pdf,'page_count',return_value=11),patch.object(family_pdf,'render_pages',side_effect=render),patch.object(family_llm,'_chat_json',return_value=dict(items=[item(question='选择正确答案')],coverage='第1题')):
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
    print('homework review synthetic checks passed')


if __name__=='__main__': run()

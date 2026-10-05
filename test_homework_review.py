"""Run python3 test_homework_review.py. Synthetic temporary files; no model, printer or household service."""
import io
import json
import os
from pathlib import Path
import tempfile
from email.message import Message
from unittest.mock import patch

import family_llm
import family_pdf
import family_print
from test_print import png


def item(**changes):
    return dict(label='第1题',question='',student_answer='B',answer='教师参考：B',judgment='correct',question_kind='objective',
                error_reason='',possible_cause='',steps='',uncertainty='')|changes


def refused(fn,code=None,status=None):
    try: fn()
    except ValueError as error:
        if code is not None: assert error.code==code,(error.code,code)
        if status is not None: assert error.status==status,(error.status,status)
    else: raise AssertionError('expected refusal')


def output_contract_checks():
    """Only supplied synthetic transport replies; no configuration or model access."""
    calls=0
    def draft_for(question,coverage='仅按甲卷第1题的教师参考比较；原题要求未核。',*,teacher=True):
        nonlocal calls
        raw=dict(items=[question],coverage=coverage)
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            try:
                return family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                    reference_documents=[dict(name='synthetic-paper-a-teacher.txt',text='甲卷 第1题 B')] if teacher else [])
            finally:
                assert model.call_count==1
                assert raw==original,'normalizing a draft must preserve its supplied transport reply'
                calls+=1
    def rejected(question,coverage,*,teacher=True):
        try: draft_for(question,coverage,teacher=teacher)
        except family_llm.LLMDraftError: pass
        else: raise AssertionError('an unsupported draft or coverage must still be rejected')

    correct=item(label='甲卷第1题')
    known_wrong=item(label='甲卷第1题',student_answer='C',judgment='incorrect',
        error_reason='本卷第1题作答C与教师参考B不同。')
    d=draft_for(correct)
    assert d['questions'][0]['judgment']=='correct' and d['wrong_items']==d['unknown_items']==0
    for steps in ('','先独立尝试；补齐原题后再核对解题过程。'):
        d=draft_for(known_wrong|dict(steps=steps))
        q=d['questions'][0]
        assert q['judgment']=='incorrect' and d['wrong_items']==1 and d['unknown_items']==0
        assert q['error_reason']==known_wrong['error_reason'] and q['steps']==steps
        assert q['question']==q['possible_cause']==q['uncertainty']=='','do not invent a question, cause or prompt'
        assert '需订正1题' in d['text'] and known_wrong['error_reason'] in d['text']
    for changes in (dict(uncertainty='教师参考与可见题面冲突，待核对'),dict(error_reason=''),
                    dict(student_answer=''),dict(answer='',question='虚构甲卷第1题：选择正确选项。'),dict(question_kind='subjective'),
                    dict(question_kind='unknown'),dict(judgment='unknown',error_reason='',steps='无依据的提示')):
        d=draft_for(known_wrong|changes)
        assert d['questions'][0]['judgment']=='unknown' and d['wrong_items']==0 and d['unknown_items']==1
        assert not d['questions'][0]['error_reason'] and not d['questions'][0]['steps']
    rejected(known_wrong,'原题未提供；也没有本题教师参考。',teacher=False)
    rejected(known_wrong|dict(answer=''),'原题及本题可核对参考均缺失。')

    for coverage,expected in (('甲卷第1题；第2页未读','甲卷第1题；第2页未读'),
                              ('甲卷第1题\n第2页未读','甲卷第1题\n第2页未读'),
                              ('甲卷第1题\r\n第2页未读','甲卷第1题\n第2页未读'),
                              ('甲卷第1题\r第2页未读','甲卷第1题\n第2页未读'),
                              ('甲卷第1题\t第2页未读','甲卷第1题 第2页未读'),
                              ('甲卷第1题\r\n\t第2页未读','甲卷第1题\n 第2页未读')):
        d=draft_for(correct,coverage)
        assert d['coverage']==expected and expected in d['text']
        assert d['questions'][0]['judgment']=='correct' and d['unknown_items']==0
    assert len(draft_for(correct,'范'*599+'\t')['coverage'])==600
    # A 601-character raw reply cannot evade the schema's 600 limit by CRLF normalization.
    for coverage in (None,7,[],dict(text='不能替代字符串'),'范'*601,'范'*599+'\r\n'):
        rejected(correct,coverage)
    for code in (*[n for n in range(32) if n not in (9,10,13)],127):
        rejected(correct,'甲卷第1题'+chr(code)+'第2页未读')
    return calls


def duplicate_question_checks():
    """One visible question identity cannot carry two counts or opposite grades."""
    calls=0
    question=item(label='虚构甲卷第1题',question='虚构第1题：2+3=?',student_answer='5',answer='教师参考：5')
    def generate(questions):
        nonlocal calls
        raw=dict(items=questions,coverage='仅核本次明确的卷别与题号。')
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            try:
                return family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                    reference_documents=[dict(name='synthetic-two-papers.txt',text='虚构甲卷与乙卷第1题均为5。')])
            finally:
                assert model.call_count==1 and raw==original,'rejected replies must keep the original transport intact'
                calls+=1
    duplicates=[
        [question,question.copy()],
        [question,question|dict(judgment='incorrect',error_reason='本题需要订正。')],
        [question,question|dict(label='  虚构甲卷第1题\n\t  ')],
        [question,question|dict(label='虚构甲卷 第1题',judgment='incorrect',error_reason='本题需要订正。')],
        [question|dict(label=''),question|dict(label='',judgment='incorrect',error_reason='本题需要订正。')],
        [question,question|dict(question='另一道题却用了相同卷别题号。',student_answer='6',answer='教师参考：6')],
    ]
    for questions in duplicates:
        try: generate(questions)
        except family_llm.LLMDraftError as error:
            assert '重复' in str(error) and '题' in str(error)
        else: raise AssertionError('a repeated question identity must not become two visible judgments')
    for labels in (('虚构甲卷第1题','虚构乙卷第1题'),('虚构甲卷第1题（1）','虚构甲卷第1题（2）')):
        questions=[question|dict(label=labels[0]),question|dict(label=labels[1],student_answer='4',judgment='incorrect',error_reason='作答4与教师参考5不同。')]
        draft=generate(questions)
        assert draft['items']==2 and draft['wrong_items']==1 and draft['unknown_items']==0
        assert [q['label'] for q in draft['questions']]==list(labels)
        assert [q['judgment'] for q in draft['questions']]==['correct','incorrect']
    unknown=question|dict(label='题号未明 · 虚构照片第1页',question='',student_answer='',answer='',
        judgment='unknown',uncertainty='卷别或题号未能辨认，请补原题。')
    draft=generate([unknown]);assert draft['items']==1 and draft['unknown_items']==1 and draft['wrong_items']==0
    assert draft['questions'][0]['label']==unknown['label'],'an explicit unread scope does not invent a question number'
    return calls


def summary_consistency_checks():
    """A program downgrade must reach both summaries without rewriting transport evidence."""
    calls=0
    scope='教师参考《虚构甲卷.pdf》：共11页，本次第1、3页；未读取页：2、4-11。'
    stale_coverage='甲卷第3题已核实需订正；整卷已经检查完成。'
    stale_comparison='后补教师参考后，第3题从正确改为确定错误，须订正。'
    definite=item(label='甲卷第3题',question='虚构第3题：选择正确选项。',student_answer='C',
        judgment='incorrect',error_reason='作答C与教师参考B不同。')
    changes=[
        dict(uncertainty='教师参考与可见题面冲突，待老师核对。'),
        dict(judgment='correct',error_reason='',uncertainty='所选参考的题号对应不明。'),
        dict(student_answer=''),dict(answer=''),dict(error_reason=''),
        dict(judgment='correct',error_reason='没有依据的错误结论。'),
        dict(judgment='correct',error_reason='',possible_cause='没有依据的原因。'),
        dict(question='',question_kind='subjective'),
    ]
    def generate(questions,coverage,comparison=None,*,review=True,program_scope=()):
        nonlocal calls
        raw=dict(items=questions,coverage=coverage)
        if comparison is not None: raw['comparison']=comparison
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            draft=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=review,
                reference_documents=[dict(name='synthetic-teacher.txt',text='虚构甲卷 第1题B，第2题B，第3题B。')] if review else [],
                program_coverage=program_scope)
            assert model.call_count==1 and raw==original,'the original transport evidence must remain unchanged'
            calls+=1
        return draft
    for change in changes:
        d=generate([definite|change],stale_coverage,stale_comparison,program_scope=[scope])
        q=d['questions'][0]
        assert q['judgment']=='unknown' and d['wrong_items']==0 and d['unknown_items']==1
        assert not q['error_reason'] and not q['steps'] and q['uncertainty']
        assert stale_coverage not in d['coverage']+d['text'],'coverage must not retain a grade the program refused'
        assert stale_comparison not in d['comparison']+d['text'],'comparison must not retain a grade the program refused'
        assert '甲卷第3题' in d['coverage'] and '未判定' in d['coverage'] and '不能沿用' in d['comparison']
        assert scope in d['coverage'] and scope in d['text'],'actual selected and unread pages must remain visible'
        assert q['uncertainty'] in d['text'] and q['student_answer'] in d['text']
        if change.get('answer')!='': assert q['answer']=='教师参考：B'
    # A changed summary must not erase sound grades, or require invented hints or causes.
    sound_correct=item(label='甲卷第1题')
    sound_wrong=item(label='甲卷第2题',student_answer='C',judgment='incorrect',error_reason='第2题C与参考B不同。')
    conflict=definite|dict(uncertainty='第3题教师参考冲突。')
    d=generate([sound_correct,sound_wrong,conflict],stale_coverage,stale_comparison,program_scope=[scope])
    assert [q['judgment'] for q in d['questions']]==['correct','incorrect','unknown']
    assert d['wrong_items']==d['unknown_items']==1
    assert d['questions'][1]['error_reason']==sound_wrong['error_reason']
    assert not d['questions'][1]['steps'] and not d['questions'][1]['possible_cause']
    assert '需订正1题，与参考一致1题，未判定1题' in d['text']
    assert stale_coverage not in d['text'] and stale_comparison not in d['text']
    assert scope in d['text'] and conflict['uncertainty'] in d['text']
    # A missing optional comparison still needs the replacement when a grade was changed.
    d=generate([conflict],stale_coverage)
    assert d['comparison'] and '未判定' in d['comparison']
    # Sound existing comparisons and reference-printing output retain their original contract.
    normal_coverage='虚构甲卷仅核第1、2题；第3题尚未检查。'
    normal_comparison='虚构复核：第1题一致，第2题仍需订正，第3题未检查。'
    d=generate([sound_correct,sound_wrong],normal_coverage,normal_comparison)
    assert d['coverage']==normal_coverage and d['comparison']==normal_comparison
    assert normal_comparison in d['text'] and normal_coverage in d['text']
    printed=definite|dict(uncertainty='虚构参考冲突。');printed.pop('question_kind')
    d=generate([printed],normal_coverage,review=False)
    assert d['questions'][0]['judgment']=='unknown' and d['coverage']==normal_coverage
    assert 'comparison' not in d,'reference printing must not gain review comparison fields'
    return calls


def summary_http_checks(app,upload):
    """Real temporary HTTP dispatch, final-source guards, save/retry and original-answer reopen."""
    from http.client import HTTPConnection
    import threading
    task=app.new_task(dict(child='示例甲',title='虚构后补参考一致性',category='homework'))
    answer=upload('synthetic-summary-answer.png',png(7))
    teacher=upload('synthetic-summary-teacher.pdf',b'%PDF-synthetic-summary-reference')
    original=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-05',
        request_key='synthetic-summary-original',note='虚构甲卷，检查第1至3题。',attachments=[answer,teacher]))
    source=lambda ident,**extra:dict(type='upload',id=ident,**extra)
    request=dict(purpose='review',task_id=task['id'],record_id=original['record_id'],expected_created=original['feedback']['created'],
        question_sources=[source(answer)],reference_sources=[source(teacher,pages=[1,3])],
        review_instruction='虚构后补教师参考，请复核第3题。',previous_text='虚构上一轮第3题与参考一致。')
    stale_coverage='虚构第3题已核实需订正。'
    stale_comparison='虚构后补参考将第3题改判为确定错误。'
    raw=dict(items=[item(label='第1题'),item(label='第2题',student_answer='C',judgment='incorrect',error_reason='第2题C与参考B不同。'),
        item(label='第3题',question='虚构第3题：选择正确选项。',student_answer='C',judgment='incorrect',
             error_reason='第3题C与参考B不同。',uncertainty='第3题教师参考与可见题面冲突。')],
        coverage=stale_coverage,comparison=stale_comparison)
    transport_original=json.loads(json.dumps(raw))
    def render(body,pages,deadline):
        return dict(page_count=11,pages=[dict(page=p,mime_type='image/png',data=png()) for p in pages],
            omitted_pages=[p for p in range(1,12) if p not in pages],complete=False)
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        def http(method,path,payload=None,token=app.TOKEN):
            client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                client.request(method,path,json.dumps(payload) if payload is not None else None,
                    {'Content-Type':'application/json','X-Family-Token':token})
                response=client.getresponse();return response.status,json.loads(response.read())
            finally: client.close()
        with patch.object(family_pdf,'page_count',return_value=11),patch.object(family_pdf,'render_pages',side_effect=render),patch.object(family_llm,'_chat_json',return_value=raw) as model:
            assert http('POST','/api/print/homework/draft',request,token='invalid-synthetic-token')[0]==403
            assert model.call_count==0
            status,result=http('POST','/api/print/homework/draft',request)
            assert status==200 and model.call_count==1 and raw==transport_original
        d=result['draft'];assert [q['judgment'] for q in d['questions']]==['correct','incorrect','unknown']
        assert stale_coverage not in d['text'] and stale_comparison not in d['text']
        assert '未读取页：2,4-11' in d['text'] and '本次第1,3页' in d['text']
        ident=upload('作业批改参考-'+str(original['record_id'])+'.txt',d['text'].encode())
        feedback=dict(task_id=task['id'],child='示例甲',day='2026-10-05',request_key='synthetic-summary-saved',
            note='虚构家长核对的复核草稿，冲突题仍需补依据。',attachments=[answer,teacher,ident],
            review_basis=result['review_basis'],comparison_note=d['comparison'])
        with patch.object(family_llm,'_chat_json') as model:
            status,saved=http('POST','/api/task/feedback',feedback)
            assert status==200 and not saved['completion_changed']
            status,retry=http('POST','/api/task/feedback',feedback)
            assert status==200 and retry['replayed'] and retry['record_id']==saved['record_id']
            status,view=http('GET','/api/print/homework/saved-review?task_id='+task['id']+'&record_id='+str(saved['record_id']))
            assert status==200 and view['original_record_id']==original['record_id'] and view['text']==d['text']
            assert stale_coverage not in view['text'] and stale_comparison not in view['text']
            assert '未读取页：2,4-11' in view['text'] and '第3题教师参考与可见题面冲突。' in view['text']
            assert model.call_count==0,'save, lost-receipt retry and reopen must not call a model'
        with app.connect() as c:
            answer_row=c.execute('SELECT * FROM records WHERE id=?',(original['record_id'],)).fetchone()
            check_row=c.execute('SELECT * FROM records WHERE id=?',(saved['record_id'],)).fetchone()
            assert answer_row['created']==original['feedback']['created'] and answer_row['note']=='虚构甲卷，检查第1至3题。'
            assert json.loads(answer_row['attachments'])==[answer,teacher]
            assert check_row['related_record_id']==original['record_id'] and check_row['followup_kind']=='作业检查'
            assert check_row['comparison_note']==d['comparison']
    finally:
        server.shutdown();server.server_close();worker.join(timeout=3)


def review_origin_http_checks(app,upload):
    """A saved AI result cannot regain an original role by attachment re-use."""
    from http.client import HTTPConnection
    import threading
    source=lambda ident:dict(type='upload',id=ident)
    answer=upload('synthetic-origin-answer.png',png(9))
    answer_text=upload('synthetic-origin-original-answer.txt','虚构甲卷原作答：第1题B。'.encode())
    ordinary_teacher=upload('synthetic-origin-ordinary-teacher.txt','虚构甲卷教师参考：第1题B。'.encode())
    app.agent_store()
    school=dict(id='synthetic-origin-school',platform='qq',child_id='child-1',name='虚构身份学校来源',enabled=True)
    message=dict(id='synthetic-origin-message',time='2026-10-05T12:00:00+08:00',kind='text',sender='虚构老师',
        text='虚构甲卷教师参考',unread=False)
    with app.connect() as c:
        c.execute('INSERT INTO agent_sources (id,binding,cursor) VALUES (?,?,?)',
            (school['id'],json.dumps(['qq','child-1'],separators=(',',':')),''))
        c.execute('INSERT INTO agent_messages (source_id,id,payload) VALUES (?,?,?)',
            (school['id'],message['id'],json.dumps(message)))
    def dump():
        with app.connect() as c: return '\n'.join(c.iterdump())
    raw=dict(items=[item(label='虚构甲卷第1题')],coverage='仅虚构甲卷第1题的明确答案比较，原题要求未核。')
    transport_original=json.loads(json.dumps(raw))
    with patch.object(app.family_agent.Store,'_config',return_value=dict(enabled=True,sources=[school])):
        task=app.new_task(dict(child='示例甲',title='虚构结果身份重挂',category='homework',
            source='message:'+school['id']+':'+message['id'],request_key='synthetic-origin-task'))
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            def http(method,path,payload=None):
                client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    client.request(method,path,json.dumps(payload) if payload is not None else None,
                        {'Content-Type':'application/json','X-Family-Token':app.TOKEN})
                    response=client.getresponse();return response.status,json.loads(response.read())
                finally: client.close()
            def feedback(key,attachments,note,**extra):
                status,result=http('POST','/api/task/feedback',dict(task_id=task['id'],child='示例甲',day='2026-10-05',
                    request_key=key,attachments=attachments,note=note)|extra)
                assert status==200 and not result['completion_changed'],result
                return result
            def sources(record,task_id=task['id']):
                before=dump()
                status,result=http('GET','/api/print/homework/sources?task_id='+task_id+'&record_id='+str(record['record_id']))
                assert status==200 and result['created']==record['feedback']['created'],result
                assert dump()==before,'source classification must not migrate original records'
                return {entry['id']:entry for entry in result['sources']}
            original=feedback('synthetic-origin-original',[answer,answer_text],'虚构甲卷原作答，第1题B。')
            school_teacher_name='作业批改参考-'+str(original['record_id'])+'.txt'
            school_teacher=upload(school_teacher_name,'虚构学校教师参考：甲卷第1题B。'.encode())
            with app.connect() as c:
                c.execute('INSERT INTO agent_message_attachments VALUES (?,?,?)',(school['id'],message['id'],school_teacher))
            feedback('synthetic-origin-teacher',[ordinary_teacher],'虚构家长后补教师原参考。')
            request=dict(purpose='review',task_id=task['id'],record_id=original['record_id'],
                expected_created=original['feedback']['created'],question_sources=[source(answer)],
                reference_sources=[source(ordinary_teacher),source(school_teacher)])
            with patch.object(family_llm,'_chat_json',return_value=raw) as model:
                status,generated=http('POST','/api/print/homework/draft',request)
                assert status==200 and model.call_count==1 and raw==transport_original,generated
            opinion_text=generated['draft']['text']
            opinion_name='作业批改参考-'+str(original['record_id'])+'.txt'
            opinion=upload(opinion_name,opinion_text.encode())
            with patch.object(family_llm,'_chat_json') as model:
                formal=feedback('synthetic-origin-formal',[answer,answer_text,ordinary_teacher,school_teacher,opinion],
                    '家长核对的作业批改参考；完整逐题意见见文字附件。原作答反馈 #'+str(original['record_id'])+'。',
                    review_basis=generated['review_basis'])
                assert model.call_count==0,'saving the generated check must not call the model again'
            with app.connect() as c:
                formal_row=c.execute('SELECT * FROM records WHERE id=?',(formal['record_id'],)).fetchone()
                assert formal_row['followup_kind']=='作业检查' and formal_row['related_record_id']==original['record_id']
                assert set(json.loads(formal_row['attachments']))=={answer,answer_text,ordinary_teacher,school_teacher,opinion}
                assert json.loads(formal_row['review_output_ids'])==[opinion], 'only the newly written result is marked, never retained teacher or answer inputs'
            before=dump()
            with patch.object(family_llm,'_chat_json') as model:
                repeated=feedback('synthetic-origin-formal',[answer,answer_text,ordinary_teacher,school_teacher,opinion],
                    '家长核对的作业批改参考；完整逐题意见见文字附件。原作答反馈 #'+str(original['record_id'])+'。',
                    review_basis=generated['review_basis'])
                assert repeated['replayed'] and repeated['record_id']==formal['record_id'] and model.call_count==0
            assert dump()==before, 'same numbered retry must not change output metadata or any old row'
            # The parent reuses the exact upload, not a new file with a similar name.
            reattached=feedback('synthetic-origin-reattached',[answer,opinion],'虚构普通反馈重挂原照片及旧AI意见。',review_output_ids='[]')
            with app.connect() as c:
                assert c.execute('SELECT review_output_ids FROM records WHERE id=?',(reattached['record_id'],)).fetchone()[0] is None, 'an ordinary client cannot alter the server-only result binding'
            with patch.object(family_llm,'_chat_json') as model:
                listed=sources(reattached)
                assert listed[opinion]['origin']=='review_result','re-attaching a formal result cannot make it a saved answer'
                assert listed[ordinary_teacher]['origin']!='review_result','an earlier ordinary teacher original stays usable'
                assert listed[school_teacher]['origin']=='school','a school-bound teacher original stays usable'
                assert sources(original)[answer_text]['origin']=='saved_answer','a reused original answer TXT keeps its identity'
                assert model.call_count==0,'source listing must not request another judgment'
            recheck=request|dict(record_id=reattached['record_id'],expected_created=reattached['feedback']['created'])
            for role,changes in (('question',dict(question_sources=[source(answer),source(opinion)])),
                                 ('reference',dict(reference_sources=[source(opinion)]))):
                before=dump()
                with patch.object(family_llm,'_chat_json') as model:
                    status,result=http('POST','/api/print/homework/draft',recheck|changes)
                    assert status==403 and result.get('code')=='review_source_not_allowed',(role,status,result)
                    assert model.call_count==0,'the AI-result role must be refused before a model call'
                assert dump()==before,'refused AI-result inputs must not change any saved data'
            for ident,name,text in ((ordinary_teacher,'synthetic-origin-ordinary-teacher.txt','虚构甲卷教师参考：第1题B。'),
                                    (school_teacher,school_teacher_name,'虚构学校教师参考：甲卷第1题B。')):
                before=dump()
                with patch.object(family_llm,'homework_reference_draft',wraps=family_llm.homework_reference_draft) as generate,\
                     patch.object(family_llm,'_chat_json',return_value=raw) as model:
                    status,result=http('POST','/api/print/homework/draft',recheck|dict(reference_sources=[source(ident)]))
                    assert status==200 and model.call_count==1,result
                    assert generate.call_args.kwargs['reference_documents']==[dict(name=name,text=text)]
                assert dump()==before,'reusing a teacher input must not write a check automatically'
            # An explicitly selected previous-text input keeps its role separate from teacher references.
            for ident,name,text in ((answer_text,'synthetic-origin-original-answer.txt','虚构甲卷原作答：第1题B。'),
                                    (opinion,opinion_name,opinion_text)):
                before=dump()
                with patch.object(family_llm,'homework_reference_draft',wraps=family_llm.homework_reference_draft) as generate,\
                     patch.object(family_llm,'_chat_json',return_value=raw) as model:
                    status,rechecked=http('POST','/api/print/homework/draft',recheck|dict(previous_sources=[source(ident)]))
                    assert status==200 and model.call_count==1 and raw==transport_original,rechecked
                    assert generate.call_args.kwargs['previous_documents']==[dict(name=name,text=text)]
                    assert [d['name'] for d in generate.call_args.kwargs['reference_documents']]==[
                        'synthetic-origin-ordinary-teacher.txt',school_teacher_name]
                    assert dict(name=name,text=text) not in generate.call_args.kwargs['reference_documents'], 'same filenames do not make AI text a teacher input'
                assert dump()==before,'an allowed text input stays a draft until explicitly saved'
            next_opinion=upload('作业批改参考-'+str(reattached['record_id'])+'.txt',rechecked['draft']['text'].encode())
            with patch.object(family_llm,'_chat_json') as model:
                next_formal=feedback('synthetic-origin-recheck-saved',
                    [answer,ordinary_teacher,school_teacher,opinion,next_opinion],
                    '虚构家长核对旧AI意见后追加复核，原意见保留。',review_basis=rechecked['review_basis'])
                assert model.call_count==0
            with app.connect() as c:
                next_row=c.execute('SELECT * FROM records WHERE id=?',(next_formal['record_id'],)).fetchone()
                assert next_row['followup_kind']=='作业检查' and next_row['related_record_id']==reattached['record_id']
            # A later correction can attach P to an ordinary record whose ID precedes F.
            # First-seen record order must not turn the generated result into original evidence.
            with patch.object(family_llm,'_chat_json') as model:
                corrected=feedback('',[answer,answer_text,opinion],'虚构更正：追加旧AI意见，原作答仍为第1题B。',
                    record_id=original['record_id'],expected_created=original['feedback']['created'])
                assert corrected['record_id']==original['record_id']<formal['record_id']
                assert sources(corrected)[opinion]['origin']=='review_result','an earlier ordinary record cannot reclassify a later AI result'
                assert model.call_count==0
            corrected_request=request|dict(expected_created=corrected['feedback']['created'],reference_sources=[source(opinion)])
            before=dump()
            with patch.object(family_llm,'_chat_json') as model:
                status,result=http('POST','/api/print/homework/draft',corrected_request)
                assert status==403 and result.get('code')=='review_source_not_allowed',result
                assert model.call_count==0,'an appended old result is still refused before the model'
            assert dump()==before,'refusing a result appended by correction must leave all data unchanged'

            # Reattaching the same generated upload under another same-child task does
            # not grant teacher or question roles. No cross-task previous-text behavior is asserted.
            other_task=app.new_task(dict(child='示例甲',title='虚构另一份作业重挂结果',category='homework',
                request_key='synthetic-origin-other-task'))
            other_answer=upload('synthetic-origin-other-answer.png',png(11))
            with patch.object(family_llm,'_chat_json') as model:
                other_record=feedback('synthetic-origin-other-reattached',[other_answer,opinion],
                    '虚构另一作业的原作答及重挂旧AI意见。',task_id=other_task['id'])
                assert sources(other_record,task_id=other_task['id'])[opinion]['origin']=='review_result'
                assert model.call_count==0
            other_request=dict(purpose='review',task_id=other_task['id'],record_id=other_record['record_id'],
                expected_created=other_record['feedback']['created'],question_sources=[source(other_answer)],reference_sources=[])
            for role,changes in (('question',dict(question_sources=[source(other_answer),source(opinion)])),
                                 ('reference',dict(reference_sources=[source(opinion)]))):
                before=dump()
                with patch.object(family_llm,'_chat_json') as model:
                    status,result=http('POST','/api/print/homework/draft',other_request|changes)
                    assert status==403 and result.get('code')=='review_source_not_allowed',(role,status,result)
                    assert model.call_count==0,'changing tasks does not authorize an AI result as original evidence'
                assert dump()==before,'cross-task rejected result inputs must not write any data'

            # Two distinct TXT uploads may have the same product-looking filename.
            # The teacher file was bound before the formal typed check and remains an input.
            same_task=app.new_task(dict(child='示例甲',title='虚构同名教师资料身份',category='homework',
                request_key='synthetic-origin-same-name-task'))
            same_answer=upload('synthetic-origin-same-name-answer.png',png(13))
            same_original=feedback('synthetic-origin-same-name-original',[same_answer],
                '虚构甲卷原作答，第1题B。',task_id=same_task['id'])
            same_name='作业批改参考-'+str(same_original['record_id'])+'.txt'
            same_teacher_text='虚构同名教师原参考：第1题B。'
            same_teacher=upload(same_name,same_teacher_text.encode())
            teacher_record=feedback('synthetic-origin-same-name-teacher',[same_teacher],
                '虚构普通反馈绑定的教师原参考。',task_id=same_task['id'])
            same_request=dict(purpose='review',task_id=same_task['id'],record_id=same_original['record_id'],
                expected_created=same_original['feedback']['created'],question_sources=[source(same_answer)],
                reference_sources=[source(same_teacher)])
            with patch.object(family_llm,'_chat_json',return_value=raw) as model:
                status,same_generated=http('POST','/api/print/homework/draft',same_request)
                assert status==200 and model.call_count==1 and raw==transport_original,same_generated
            same_opinion=upload(same_name,same_generated['draft']['text'].encode())
            assert same_opinion!=same_teacher,'the same filename is not the same upload identity'
            with patch.object(family_llm,'_chat_json') as model:
                same_formal=feedback('synthetic-origin-same-name-formal',[same_answer,same_teacher,same_opinion],
                    '家长核对的作业批改参考；完整逐题意见见文字附件。原作答反馈 #'+str(same_original['record_id'])+'。',
                    task_id=same_task['id'],review_basis=same_generated['review_basis'])
                assert model.call_count==0
            with app.connect() as c:
                row=c.execute('SELECT * FROM records WHERE id=?',(same_formal['record_id'],)).fetchone()
                assert row['followup_kind']=='作业检查' and row['related_record_id']==same_original['record_id']
                assert set(json.loads(row['attachments']))=={same_answer,same_teacher,same_opinion}
            for stage in ('original_teacher_note','corrected_teacher_note'):
                if stage=='corrected_teacher_note':
                    with patch.object(family_llm,'_chat_json') as model:
                        teacher_corrected=feedback('',[same_teacher],'虚构只更正教师资料的备注，原附件不变。',
                            task_id=same_task['id'],record_id=teacher_record['record_id'],
                            expected_created=teacher_record['feedback']['created'])
                        assert teacher_corrected['record_id']==teacher_record['record_id'] and model.call_count==0
                    with app.connect() as c:
                        row=c.execute('SELECT * FROM records WHERE id=?',(teacher_record['record_id'],)).fetchone()
                        assert json.loads(row['attachments'])==[same_teacher] and not row['followup_kind']
                before=dump()
                with patch.object(family_llm,'homework_reference_draft',wraps=family_llm.homework_reference_draft) as generate,\
                     patch.object(family_llm,'_chat_json',return_value=raw) as model:
                    listed=sources(same_original,task_id=same_task['id'])
                    assert listed[same_teacher]['name']==listed[same_opinion]['name']==same_name
                    assert listed[same_teacher]['origin']!='review_result',(stage,'teacher input was incorrectly classified')
                    assert listed[same_opinion]['origin']=='review_result',(stage,'generated opinion lost its result identity')
                    assert model.call_count==0
                    status,result=http('POST','/api/print/homework/draft',same_request)
                    assert status==200 and model.call_count==1 and raw==transport_original,(stage,result)
                    assert generate.call_args.kwargs['reference_documents']==[dict(name=same_name,text=same_teacher_text)]
                assert dump()==before,'reading an unchanged teacher file must not migrate its record or save a check'
        finally:
            server.shutdown();server.server_close();worker.join(timeout=3)


def run():
    contract_cases=output_contract_checks()+duplicate_question_checks()+summary_consistency_checks()
    with tempfile.TemporaryDirectory(prefix='synthetic-homework-review-') as temporary:
        root=Path(temporary);data=root/'private';data.mkdir()
        with patch.dict(os.environ,{'FAMILY_DATA':str(data)}):
            import app
        with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
            (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 8岁 | 二年级 |\n')
            (root/'跟踪台账.md').write_text('')
            def upload(name,body): return app.save_upload(io.BytesIO(body),len(body),name)['id']
            # Upgrade a real old-column layout in this disposable database; preserve every old field.
            import sqlite3
            migration_file=upload('synthetic-origin-migration.txt',b'Synthetic original teacher text')
            migration=app._save_record(dict(child='示例甲',day='2026-10-05',category='学习进展',title='虚构旧原件记录',
                source='家长网页记录',note='虚构迁移保留原话',attachments=[migration_file]),False,{})
            with sqlite3.connect(app.DB) as c:
                c.execute('ALTER TABLE records DROP COLUMN review_output_ids')
                old_columns=[r[1] for r in c.execute('PRAGMA table_info(records)')]
                old_rows=c.execute('SELECT * FROM records').fetchall()
            with app.connect() as c:
                assert [tuple(r) for r in c.execute('SELECT '+','.join(old_columns)+' FROM records')]==old_rows
                assert c.execute('SELECT review_output_ids FROM records WHERE id=?',(migration['record_id'],)).fetchone()[0] is None
            answer=upload('synthetic-answer.png',png())
            reference=upload('synthetic-reference.txt',b'1. B\n')
            paper=upload('synthetic-paper.pdf',b'%PDF-synthetic-paper')
            teacher_pdf=upload('synthetic-teacher.pdf',b'%PDF-synthetic-teacher')
            other=upload('synthetic-other.png',png(3))
            task=app.new_task(dict(child='示例甲',title='虚构试卷核对',category='homework',action='按题号核对',request_key='synthetic-homework-task-1'))
            another=app.new_task(dict(child='示例乙',title='虚构另一孩子作业',category='homework',request_key='synthetic-homework-task-2'))
            app.save_task_feedback(dict(task_id=another['id'],child='示例乙',day='2026-10-01',request_key='synthetic-other-feedback',attachments=[other]))
            answer_note='虚构甲卷；本次第1题，余题未检查'
            saved=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-01',request_key='synthetic-answer-feedback',note=answer_note,attachments=[answer,reference,teacher_pdf]))
            rid=saved['record_id'];created=saved['feedback']['created']
            source=lambda ident,**extra:dict(type='upload',id=ident,**extra)
            request=dict(purpose='review',task_id=task['id'],record_id=rid,expected_created=created,
                         question_sources=[source(answer)],reference_sources=[source(reference)])
            def fake_model(messages,schema,name,timeout,**kwargs):
                serialized=json.dumps(messages,ensure_ascii=False)
                assert '教师参考原文' in serialized and '1. B' in serialized
                assert '不执行' in serialized and '不擅自改写老师答案' in serialized
                assert answer_note in serialized and '原作答家长说明' in serialized
                assert '不同卷即使题号相同也不能合并或猜配' in serialized
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
            # Two original answers under one task keep their own paper/range; another paper cannot replace this answer.
            second_answer=upload('synthetic-second-paper.png',png(5))
            second_note='虚构乙卷；同名第1题，本次只查乙卷'
            second=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-01',
                request_key='synthetic-second-paper-answer',note=second_note,attachments=[second_answer]))
            second_request=request|dict(record_id=second['record_id'],expected_created=second['feedback']['created'],
                question_sources=[source(second_answer)])
            def second_model(messages,*args,**kwargs):
                serialized=json.dumps(messages,ensure_ascii=False)
                assert second_note in serialized and answer_note not in serialized
                return dict(items=[item()],coverage='虚构只核乙卷第1题')
            with patch.object(family_llm,'_chat_json',side_effect=second_model):
                second_result=app.homework_review_draft(second_request)
            assert second_result['review_basis']['record_id']==second['record_id']
            assert second_result['review_basis']['photo_ids']==[second_answer]
            with patch.object(family_llm,'_chat_json') as model:
                refused(lambda:app.homework_review_draft(request|dict(question_sources=[source(second_answer)])),'review_basis_changed',409)
                refused(lambda:family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,answer_note='字'*4001))
                assert model.call_count==0
            # The description itself is guarded even if an external writer forgot to change its version timestamp.
            with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',('虚构说明更正为乙卷',rid))
            try:
                with app.connect() as c: refused(lambda:app.guard_homework_review(c,task['id'],basis,[answer,reference]),'review_basis_changed',409)
            finally:
                with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',(answer_note,rid))
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
            # A reference-word match does not establish an unseen subjective requirement.
            answer_only=[item(),item(label='Q2',question_kind='subjective',student_answer='Plants get energy from sunlight.',
                answer='教师参考：Plants get energy from sunlight.'),
                item(label='Q3',judgment='unknown',student_answer='2',answer='教师参考：2 m',
                     steps='如果要单位，就补写2 m。',uncertainty='原题单位格式未提供')]
            answer_only_raw=dict(items=answer_only,coverage='Q1—Q3均正确，整卷已检查完',comparison='上一轮三题均正确')
            with patch.object(family_llm,'_chat_json',return_value=answer_only_raw):
                limited=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                    reference_documents=[dict(name='synthetic-answer-only.txt',text='Q1 B; Q2 Plants get energy from sunlight.; Q3 2 m')])
            assert [q['judgment'] for q in limited['questions']]==['correct','unknown','unknown']
            assert limited['unknown_items']==2 and limited['wrong_items']==0
            assert limited['questions'][1]['student_answer']=='Plants get energy from sunlight.'
            assert limited['questions'][1]['answer']=='教师参考：Plants get energy from sunlight.'
            assert all(not q['steps'] and not q['error_reason'] and not q['possible_cause'] for q in limited['questions'][1:])
            assert 'Q2' in limited['comparison'] and 'Q3' in limited['comparison'] and '不能沿用' in limited['comparison']
            assert '上一轮三题均正确' not in limited['comparison']
            assert 'Q1—Q3均正确，整卷已检查完' not in limited['text']+limited['coverage']
            assert all(label in limited['coverage'] for label in ('Q2','Q3')) and '仍未判定' in limited['coverage']
            assert answer_only_raw['coverage']=='Q1—Q3均正确，整卷已检查完'
            assert answer_only_raw['items'][1]['question_kind']=='subjective' and answer_only_raw['items'][1]['judgment']=='correct'
            for kind in ('unknown','subjective'):
                with patch.object(family_llm,'_chat_json',return_value=dict(items=[item(question_kind=kind)],coverage='仅答题纸')):
                    uncertain=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                        reference_documents=[dict(name='synthetic-unknown-kind.txt',text='Q1 B')])
                assert uncertain['unknown_items']==1 and uncertain['questions'][0]['answer']=='教师参考：B'
            with patch.object(family_llm,'_chat_json',return_value=dict(items=[item(question_kind='subjective',question='明确题干：说明能量来源')],coverage='有题干')):
                complete=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                    reference_documents=[dict(name='synthetic-complete-question.txt',text='Q1 B')])
            assert complete['questions'][0]['judgment']=='correct','readable subjective requirements keep the existing full-question path'
            missing_kind=item();missing_kind.pop('question_kind')
            with patch.object(family_llm,'_chat_json',return_value=dict(items=[missing_kind],coverage='无题型')):
                try:family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                    reference_documents=[dict(name='synthetic-missing-kind.txt',text='Q1 B')])
                except family_llm.LLMDraftError:pass
                else:raise AssertionError('missing question-kind basis must not keep a definite grade')
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
            later_record=app.save_task_feedback(dict(task_id=report_task,child='示例甲',day='2026-10-01',request_key='synthetic-later-reference',attachments=[later]))
            with app.connect() as c: ctx=app.homework_review_context(c,report_task,record['record_id'])
            assert ctx['allowed'][later]['origin']=='same_task'
            with patch.object(family_llm,'_chat_json') as model:
                refused(lambda:app.homework_review_draft(dict(purpose='review',task_id=report_task,
                    record_id=later_record['record_id'],expected_created=later_record['feedback']['created'],
                    question_sources=[source(answer)],reference_sources=[source(later)])),'review_basis_changed',409)
                assert model.call_count==0,'a reference-only feedback is not the original child answer'
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
            # Reopening is a bounded read of the parent's saved text, never a reconstruction of AI judgments.
            def preview_record(text,key,extra=(),**changes):
                ident=upload(review_name,text.encode('utf-8'))
                saved=app._save_record(dict(child='示例甲',day='2026-10-02',category='学习进展',title='虚构保存检查回看',
                    source='事项:'+recheck_task['id'],note='虚构家长核对后的文字',attachments=[ident,*extra],
                    related_record_id=original_id,followup_kind='作业检查',request_key=key)|changes,False,{})
                return saved['record_id'],ident
            def preview(ident,task_id=recheck_task['id']):
                with patch.object(app,'connect',side_effect=AssertionError('preview must use the read-only connection')):
                    return app.homework_saved_review(task_id,ident)
            def preview_get(query,child=False):
                handler=object.__new__(app.Handler);handler.command='GET';handler.path='/api/print/homework/saved-review?'+query
                handler.client_address=('127.0.0.1',0);handler.headers=Message();handler.headers['Host']='127.0.0.1'
                if child: handler.headers['X-Child-CSRF']='synthetic-child-token'
                replies=[];handler.reply=lambda status,body,*args,**kwargs:replies.append((status,body))
                with patch.object(app,'connect',side_effect=AssertionError('preview route must remain read-only')):
                    handler.do_GET()
                assert len(replies)==1
                return replies[0]
            edited='家长更正：第1题仍未判定，不能按旧AI卡片判对。🙂 e\u0301\n此前检查草稿（仅供对照，不是教师参考）：\n这句也是家长本轮原文。'
            archived='旧AI意见：第1题与答案一致。'
            framed_edited='作业检查保存格式 v1\n最新检查字数：'+str(len(edited))+'\n'+edited+'\n\n此前检查草稿（仅供对照，不是教师参考）：\n'+archived+'\n'
            preview_id,preview_txt=preview_record(framed_edited,'synthetic-saved-preview')
            with patch.object(family_llm,'_chat_json') as model:
                before=dump();view=preview(preview_id)
                assert view==dict(task_id=recheck_task['id'],record_id=preview_id,created=view['created'],original_record_id=original_id,text=edited,has_archived=True)
                assert archived not in view['text'] and 'judgment' not in view and dump()==before
                query='task_id='+recheck_task['id']+'&record_id='+str(preview_id)
                before=dump();assert preview_get(query)==(200,view);assert preview_get(query,child=True)[0]==403;assert dump()==before
                for invalid_query in ('record_id='+str(preview_id),query+'&record_id='+str(preview_id),query+'&extra=1','task_id='+recheck_task['id']+'&record_id=-1'):
                    before=dump();assert preview_get(invalid_query)[0]==400;assert dump()==before
                plain_id,_=preview_record(edited,'synthetic-saved-plain-preview')
                before=dump();assert preview(plain_id)['text']==edited and not preview(plain_id)['has_archived'];assert dump()==before
                empty_archive='作业检查保存格式 v1\n最新检查字数：'+str(len(edited))+'\n'+edited+'\n'
                empty_id,_=preview_record(empty_archive,'synthetic-saved-empty-archive')
                before=dump();assert preview(empty_id)['text']==edited and not preview(empty_id)['has_archived'];assert dump()==before
                before=dump();legacy_view=preview(r155_saved['record_id'],task['id'])
                assert legacy_view['text']==legacy_text and legacy_view['original_record_id']==rid and not legacy_view['has_archived'];assert dump()==before
                for ident,task_id in ((preview_id,task['id']),(preview_id,another['id']),(original_id,recheck_task['id'])):
                    rejected_unchanged(lambda ident=ident,task_id=task_id:preview(ident,task_id),'review_source_not_allowed',403)
                rejected_unchanged(lambda:preview(9223372036854775807),'not_found',404)
                name_only,_=preview_record('虚构只有文件名不能认作检查','synthetic-preview-name-only',followup_kind='',related_record_id=None)
                rejected_unchanged(lambda:preview(name_only),'review_source_not_allowed',403)
                note_only=app._save_record(dict(child='示例甲',day='2026-10-02',category='学习进展',title='虚构只有旧模板',
                    source='事项:'+recheck_task['id'],note=review_note,attachments=[],request_key='synthetic-preview-note-only'),False,{})['record_id']
                rejected_unchanged(lambda:preview(note_only),'review_source_not_allowed',403)
                reused=app._save_record(dict(child='示例甲',day='2026-10-02',category='学习进展',title='虚构仅携带上一轮',
                    source='事项:'+recheck_task['id'],note='虚构检查记录',attachments=[preview_txt],related_record_id=original_id,
                    followup_kind='作业检查',request_key='synthetic-preview-reused-txt'),False,{})['record_id']
                rejected_unchanged(lambda:preview(reused),status=None)
                duplicate=upload(review_name,b'Synthetic second result')
                ambiguous,_=preview_record('虚构两份本轮文字','synthetic-preview-ambiguous',[duplicate])
                rejected_unchanged(lambda:preview(ambiguous),status=None)
                for n,text in enumerate(invalid_frames+['字'*12001]):
                    invalid,_=preview_record(text,'synthetic-preview-invalid-'+str(n))
                    rejected_unchanged(lambda invalid=invalid:preview(invalid),status=None)
                path=data/'uploads'/preview_txt;body=path.read_bytes()
                for changed in (b'\xff'+body[1:],b'\x00'+body[1:],body+b'changed'):
                    path.write_bytes(changed);rejected_unchanged(lambda:preview(preview_id),status=None)
                path.write_bytes(body)
                backup=path.with_suffix('.saved');path.rename(backup)
                rejected_unchanged(lambda:preview(preview_id),'file_unavailable',404)
                path.symlink_to(backup);rejected_unchanged(lambda:preview(preview_id),status=None);path.unlink();backup.rename(path)
                uploads=data/'uploads';moved=data/'moved-uploads';uploads.rename(moved);uploads.symlink_to(moved,target_is_directory=True)
                rejected_unchanged(lambda:preview(preview_id),status=None);uploads.unlink();moved.rename(uploads)
                with app.connect() as c: c.execute('UPDATE records SET child=? WHERE id=?',('示例乙',preview_id))
                rejected_unchanged(lambda:preview(preview_id),'review_source_not_allowed',403)
                with app.connect() as c: c.execute('UPDATE records SET child=? WHERE id=?',('示例甲',preview_id))
                missing_db=data/'missing-preview.sqlite3'
                with patch.object(app,'DB',missing_db):
                    try: preview(preview_id)
                    except app.sqlite3.OperationalError: pass
                    else: raise AssertionError('an absent database must not be initialized by a preview')
                assert not missing_db.exists()
                assert model.call_count==0,'saved text preview must never call a model'
            # Explicitly linked ordinary answers retain provenance; a link decision is
            # part of the review basis even after moving away and back to the same task.
            linked_task=app.new_task(dict(child='示例甲',title='虚构关联原作答',category='homework'))
            moved_task=app.new_task(dict(child='示例甲',title='虚构临时关联',category='homework'))
            ordinary=app.save_record(dict(child='示例甲',day='2026-10-01',category='学习进展',subject='英语',
                title='虚构独立甲卷',source='试卷 / 作业核对',note='虚构原答：第1题B',attachments=[answer,reference]))
            ordinary_id=ordinary['record_id']
            app.link_record_task(dict(record_id=ordinary_id,child='示例甲',task_id=linked_task['id'],expected_linked_at=''))
            with app.connect() as c:
                linked_row=dict(c.execute('SELECT * FROM records WHERE id=?',(ordinary_id,)).fetchone())
            linked_request=dict(purpose='review',task_id=linked_task['id'],record_id=ordinary_id,
                expected_created=linked_row['created'],question_sources=[source(answer)],reference_sources=[source(reference)])
            for invalid_task in (None,1,'','x'*31):
                with patch.object(family_llm,'_chat_json') as model:
                    refused(lambda:app.homework_review_draft(linked_request|dict(task_id=invalid_task)),status=400)
                    assert model.call_count==0
            with patch.object(family_llm,'_chat_json',return_value=dict(items=[item()],coverage='虚构仅第1题')) as model:
                linked_basis=app.homework_review_draft(linked_request)['review_basis']
                assert model.call_count==1
            moved=app.link_record_task(dict(record_id=ordinary_id,child='示例甲',task_id=moved_task['id'],
                expected_linked_at=linked_row['linked_task_at']))
            app.link_record_task(dict(record_id=ordinary_id,child='示例甲',task_id=linked_task['id'],
                expected_linked_at=moved['link']['linked_at']))
            with app.connect() as c:
                current=dict(c.execute('SELECT * FROM records WHERE id=?',(ordinary_id,)).fetchone())
                assert current['created']==linked_row['created'] and current['source']==linked_row['source']
                assert current['linked_task_at']!=linked_row['linked_task_at']
                refused(lambda:app.guard_homework_review(c,linked_task['id'],linked_basis,[answer,reference]),'review_basis_changed',409)
            for kind in ('订正','作业检查'):
                derived=app.save_record(dict(child='示例甲',day='2026-10-01',category='学习进展',subject='英语',
                    title='虚构'+kind,source='家长观察',note='虚构后续记录',attachments=[answer],
                    related_record_id=ordinary_id,followup_kind=kind))
                with patch.object(family_llm,'_chat_json') as model:
                    refused(lambda:app.homework_review_draft(linked_request|dict(record_id=derived['record_id'],expected_created=None)),
                        'review_source_not_allowed',403)
                    assert model.call_count==0
            summary_http_checks(app,upload)
            review_origin_http_checks(app,upload)
    print('homework review synthetic checks passed (%d output contract cases)'%contract_cases)


if __name__=='__main__': run()

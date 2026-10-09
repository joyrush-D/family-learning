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
        assert d['unverified_model_summary']['coverage']==expected
        assert '未列入' in d['coverage'] and '完整覆盖尚未核明' in d['text']
        assert d['questions'][0]['judgment']=='correct' and d['unknown_items']==0
    assert len(draft_for(correct,'范'*599+'\t')['unverified_model_summary']['coverage'])==600
    # A 601-character raw reply cannot evade the schema's 600 limit by CRLF normalization.
    for coverage in (None,7,[],dict(text='不能替代字符串'),'范'*601,'范'*599+'\r\n'):
        rejected(correct,coverage)
    for code in (*[n for n in range(32) if n not in (9,10,13)],127):
        rejected(correct,'甲卷第1题'+chr(code)+'第2页未读')
    return calls


def choice_judgment_checks():
    """Explicit single-choice letters must not contradict their own comparison."""
    calls=0
    def generate(question,*,previous=False,teacher='虚构甲卷第1题教师参考B。'):
        nonlocal calls
        raw=dict(question_labels=[question['label']],items=[question],coverage='本题已与教师参考核对。')
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            draft=family_llm.homework_reference_draft([],review=True,
                question_documents=[dict(name='synthetic-choice-child.txt',text='虚构甲卷第1题最终作答C。')],
                reference_documents=[dict(name='synthetic-choice-teacher.txt',text=teacher)],
                previous_text='虚构旧意见：第1题正确。' if previous else '')
            assert model.call_count==1 and raw==original
            calls+=1
        return draft
    for previous in (False,True):
        for student,answer,judgment in (('C','B','correct'),('B','B','incorrect'),
                                        (' C ',' B ','correct'),(' B ','B','incorrect')):
            question=item(label='虚构甲卷第1题',student_answer=student,answer='教师参考：'+answer,
                judgment=judgment,error_reason='虚构模型判为不同。' if judgment=='incorrect' else '')
            draft=generate(question,previous=previous);q=draft['questions'][0]
            assert q['judgment']=='unknown' and draft['unknown_items']==1 and draft['wrong_items']==0
            assert q['student_answer']==student and q['answer']==question['answer']
            assert '判定矛盾' in q['uncertainty'] and not q['error_reason'] and not q['possible_cause'] and not q['steps']
            assert draft['text'].startswith('本次核对1题：需订正0题，与参考一致0题，未判定1题。')
    for question in (item(),item(student_answer='C',judgment='incorrect',error_reason='C与教师参考B不同。'),
                     item(student_answer='C',judgment='unknown',uncertainty='原题号未核明。'),
                     item(question='虚构填空：请写出小写字母b。',student_answer='B',answer='教师参考：b',
                          judgment='incorrect',error_reason='题目要求小写b，孩子写大写B。'),
                     item(question='虚构解释题：说明原因。',question_kind='subjective',student_answer='因为阳光',answer='教师参考：有阳光'),
                     item(student_answer='1/2',answer='教师参考：0.5'),
                     item(student_answer='AB',answer='教师参考：BA')):
        # A bare 第1题 cannot be paired with a 虚构甲卷 teacher line, so give the same unnamed number its own teacher value.
        draft=generate(question,teacher='第1题教师参考'+question['answer'].removeprefix('教师参考：'))
        assert draft['questions'][0]['judgment']==question['judgment'], 'do not infer case, semantic, numeric or multiple-choice equivalence'
        assert draft['questions'][0]['error_reason']==question['error_reason']
    return calls


def duplicate_question_checks():
    """One visible question identity cannot carry two counts or opposite grades."""
    calls=0
    question=item(label='虚构甲卷第1题',question='虚构第1题：2+3=?',student_answer='5',answer='教师参考：5')
    def generate(questions,teacher='虚构甲卷与虚构乙卷第1题均为5。'):
        nonlocal calls
        raw=dict(items=questions,coverage='仅核本次明确的卷别与题号。')
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            try:
                return family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                    reference_documents=[dict(name='synthetic-two-papers.txt',text=teacher)])
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
    # A whole-question teacher line no longer vouches for each sub-question, so the sub-question pair gets its own lines.
    for labels,teacher in ((('虚构甲卷第1题','虚构乙卷第1题'),'虚构甲卷与虚构乙卷第1题均为5。'),
                           (('虚构甲卷第1题（1）','虚构甲卷第1题（2）'),'虚构甲卷第1题（1）5；第1题（2）5。')):
        questions=[question|dict(label=labels[0]),question|dict(label=labels[1],student_answer='4',judgment='incorrect',error_reason='作答4与教师参考5不同。')]
        draft=generate(questions,teacher)
        assert draft['items']==2 and draft['wrong_items']==1 and draft['unknown_items']==0
        assert [q['label'] for q in draft['questions']]==list(labels)
        assert [q['judgment'] for q in draft['questions']]==['correct','incorrect']
    unknown=question|dict(label='题号未明 · 虚构照片第1页',question='',student_answer='',answer='',
        judgment='unknown',uncertainty='卷别或题号未能辨认，请补原题。')
    draft=generate([unknown]);assert draft['items']==1 and draft['unknown_items']==1 and draft['wrong_items']==0
    assert draft['questions'][0]['label']==unknown['label'],'an explicit unread scope does not invent a question number'
    return calls


def summary_consistency_checks():
    """Both original unknowns and program downgrades must reach the summaries."""
    calls=0
    scope='教师参考《虚构甲卷.pdf》：共11页，本次第1、3页；未读取页：2、4-11。'
    stale_coverage='甲卷第3题已核实需订正；整卷已经检查完成。'
    stale_comparison='后补教师参考后，第3题从正确改为确定错误，须订正。'
    definite=item(label='甲卷第3题',question='虚构第3题：选择正确选项。',student_answer='C',
        judgment='incorrect',error_reason='作答C与教师参考B不同。')
    changes=[
        dict(judgment='unknown',student_answer='',error_reason='',uncertainty='答题格空白，未能确认作答。'),
        dict(judgment='unknown',student_answer='',error_reason=''),
        dict(uncertainty='教师参考与可见题面冲突，待老师核对。'),
        dict(judgment='correct',error_reason='',uncertainty='所选参考的题号对应不明。'),
        dict(student_answer=''),dict(answer=''),dict(error_reason=''),
        dict(judgment='correct',error_reason='没有依据的错误结论。'),
        dict(judgment='correct',error_reason='',possible_cause='没有依据的原因。'),
        dict(question='',question_kind='subjective'),
    ]
    def generate(questions,coverage,comparison=None,*,review=True,program_scope=(),teacher='甲卷 第1题B，第2题B，第3题B。'):
        nonlocal calls
        raw=dict(items=questions,coverage=coverage)
        if comparison is not None: raw['comparison']=comparison
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            draft=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=review,
                reference_documents=[dict(name='synthetic-teacher.txt',text=teacher)] if review else [],
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
        assert d['text'].count('甲卷第3题')==1 and '1题仍未判定' in d['coverage'] and '不能沿用' in d['comparison']
        assert d['unverified_model_summary']==dict(coverage=stale_coverage,comparison=stale_comparison)
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
    original_unknown=definite|dict(judgment='unknown',student_answer='',error_reason='',uncertainty='答题格空白。')
    mixed_scope='第3题正确；作文未提供，超出本批材料。'
    # A 乙卷 item cannot vouch for itself against a 甲卷-only teacher line, so this teacher text names 乙卷第3题 too.
    d=generate([original_unknown,item(label='乙卷第3题')],mixed_scope,stale_comparison,program_scope=[scope],
               teacher='甲卷 第1题B，第2题B，第3题B。乙卷 第3题B。')
    assert [q['judgment'] for q in d['questions']]==['unknown','correct']
    assert '第3题正确' not in d['text']+d['coverage']+d['comparison']
    assert d['unverified_model_summary']==dict(coverage=mixed_scope,comparison=stale_comparison)
    assert '未列入本次逐题结果的题目和资料范围仍未检查' in d['coverage'] and scope in d['text']
    assert d['questions'][0]['uncertainty']=='答题格空白。' and d['questions'][0]['answer']=='教师参考：B'
    # Sound grades survive; free summaries are observations, not coverage proof.
    normal_coverage='虚构甲卷仅核第1、2题；第3题尚未检查。'
    normal_comparison='虚构复核：第1题一致，第2题仍需订正，第3题未检查。'
    d=generate([sound_correct,sound_wrong],normal_coverage,normal_comparison)
    assert d['unverified_model_summary']==dict(coverage=normal_coverage,comparison=normal_comparison)
    assert [q['judgment'] for q in d['questions']]==['correct','incorrect']
    assert normal_comparison not in d['text'] and normal_coverage not in d['text']
    printed=definite|dict(uncertainty='虚构参考冲突。');printed.pop('question_kind')
    d=generate([printed],normal_coverage,review=False)
    assert d['questions'][0]['judgment']=='unknown' and d['coverage']==normal_coverage
    assert 'comparison' not in d,'reference printing must not gain review comparison fields'
    assert 'unverified_model_summary' not in d
    return calls


def question_coverage_checks():
    """A sound returned item is not proof that every supplied question was checked."""
    calls=0
    question=item(label='虚构甲卷第1题',question='虚构甲卷第1题：2+3=?',student_answer='5',answer='教师参考：5')
    def generate(raw):
        nonlocal calls
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            try:
                return family_llm.homework_reference_draft([],review=True,
                    question_documents=[dict(name='synthetic-paper-a-answer.txt',text='虚构甲卷\n第1题 2+3，孩子作答5。\n第2题 6-2，孩子作答3。')],
                    reference_documents=[dict(name='synthetic-paper-a-teacher.txt',text='虚构甲卷\n第1题5。\n第2题4。')],
                    program_coverage=['题目/孩子作答《synthetic-paper-a-answer.txt》：本次读取完整文字。'])
            finally:
                assert model.call_count==1 and raw==original
                calls+=1
    claim='第1、2题均正确，全卷已经核对完成。'
    raw=dict(items=[question],coverage=claim,comparison=claim)
    draft=generate(raw)
    assert claim not in draft['text']+draft['coverage']+draft.get('comparison',''), 'a missing item must not be marked checked by a free summary'
    assert '未列入' in draft['coverage'], 'missing inventory must leave unlisted questions explicitly unchecked'
    scoped=raw|dict(question_labels=['虚构甲卷第1题','虚构甲卷第2题'])
    draft=generate(scoped)
    assert [q['label'] for q in draft['questions']]==scoped['question_labels']
    assert [q['judgment'] for q in draft['questions']]==['correct','unknown']
    assert draft['items']==2 and draft['unknown_items']==1 and draft['wrong_items']==0
    missing=draft['questions'][1]
    assert all(not missing[key] for key in ('question','student_answer','answer','error_reason','possible_cause','steps'))
    assert '未返回逐题检查结果' in missing['uncertainty'] and missing['uncertainty'] in draft['text']
    assert draft['text'].count('虚构甲卷第2题')==1
    assert claim not in draft['text'] and draft['unverified_model_summary']==dict(coverage=claim,comparison=claim)
    second=item(label='虚构甲卷第2题',question='虚构甲卷第2题：6-2=?',student_answer='3',answer='教师参考：4',
                judgment='incorrect',error_reason='孩子作答3与教师参考4不同。')
    completed=generate(scoped|dict(items=[question,second]))
    assert [q['judgment'] for q in completed['questions']]==['correct','incorrect']
    assert completed['unknown_items']==0 and completed['wrong_items']==1 and '3与教师参考4' in completed['text']
    for labels in ([],['虚构甲卷第1题']*2,['虚构甲卷第1题','虚构甲卷 第1题'],['虚构甲卷第2题'],
                   ['虚构甲卷第1题',3],['虚构甲卷第1题',''],['虚构甲卷第1题','坏\x00题号'],
                   ['虚构甲卷第1题','题'*81],['虚构甲卷第1题']+[f'虚构甲卷第{n}题' for n in range(2,27)]):
        try: generate(raw|dict(question_labels=labels))
        except family_llm.LLMDraftError: pass
        else: raise AssertionError('invalid or conflicting inventory must not silently truncate or guess')
    reordered=generate(scoped|dict(question_labels=['虚构甲卷第2题','虚构甲卷 第1题']))
    assert [q['judgment'] for q in reordered['questions']]==['unknown','correct']
    assert reordered['questions'][1]['label']==question['label']
    return calls


def recheck_pending_http_checks(app,upload):
    """Known unresolved questions survive same-material continuation; no old answer is evidence."""
    from http.client import HTTPConnection
    import threading
    task=app.new_task(dict(child='示例甲',title='虚构同批补查未判定',category='homework'))
    answer=upload('synthetic-pending-answer.txt','虚构甲卷第1题B。虚构乙卷第1题作答不清。'.encode())
    teacher=upload('synthetic-pending-teacher.txt','虚构甲卷第1题B。虚构乙卷第1题C。'.encode())
    original=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-05',
        request_key='synthetic-pending-original',attachments=[answer,teacher],note='虚构甲乙两卷原作答。'))
    request=dict(purpose='review',task_id=task['id'],record_id=original['record_id'],
        expected_created=original['feedback']['created'],question_sources=[dict(type='upload',id=answer)],
        reference_sources=[dict(type='upload',id=teacher)])
    first=item(label='虚构甲卷第1题')
    unknown=item(label='虚构乙卷第1题',student_answer='',answer='',judgment='unknown',uncertainty='作答不清。')
    raw=dict(question_labels=[first['label'],unknown['label']],items=[first,unknown],coverage='仅甲乙两卷第1题。')
    omitted=dict(question_labels=[first['label']],items=[first],coverage='全部正确。')
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        def http(path,payload):
            client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                client.request('POST',path,json.dumps(payload),{'Content-Type':'application/json','X-Family-Token':app.TOKEN})
                response=client.getresponse();return response.status,json.loads(response.read())
            finally: client.close()
        with patch.object(family_llm,'_chat_json',return_value=raw):
            status,initial=http('/api/print/homework/draft',request)
            assert status==200,initial
        continued=request|dict(previous_text=initial['draft']['text'],review_instruction='虚构补查乙卷第1题。')
        if 'continuation' in initial['draft']: continued['previous_continuation']=initial['draft']['continuation']
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,rechecked=http('/api/print/homework/draft',continued)
            assert status==200,rechecked
        d=rechecked['draft']
        assert [q['label'] for q in d['questions']]==[first['label'],unknown['label']], 'known pending question vanished on same-material recheck'
        assert d['unknown_items']==1 and d['items']==2 and '未判定1题' in d['text']
        q=d['questions'][1]
        assert q['judgment']=='unknown' and all(not q[k] for k in ('question','student_answer','answer','error_reason','possible_cause','steps'))
        assert '上一轮' in q['uncertainty'] and '补查' in q['uncertainty']
        pending=d['continuation'];assert pending['pending_labels']==[unknown['label']]
        def saved(result,key,continuation=None):
            text=result['draft']['text'];state=continuation or result['draft']['continuation']
            frame='作业检查保存格式 v2\n复核待补清单：'+json.dumps(state,ensure_ascii=False)+'\n最新检查字数：'+str(len(text))+'\n'+text+'\n此前检查草稿：虚构旧判定不作答案证据。'
            ident=upload('作业批改参考-'+str(original['record_id'])+'.txt',frame.encode())
            inputs=[s['id'] for s in result['review_basis']['question_sources']+result['review_basis']['reference_sources']+result['review_basis'].get('previous_sources',[])]
            feedback=dict(task_id=task['id'],child='示例甲',day='2026-10-05',request_key=key,
                note='虚构核对的检查意见。',attachments=inputs+[ident],review_basis=result['review_basis'])
            status,value=http('/api/task/feedback',feedback)
            return status,value,feedback,ident
        with patch.object(family_llm,'_chat_json') as model:
            status,formal,payload,prior=saved(rechecked,'synthetic-pending-saved')
            assert status==200 and not formal['completion_changed'],formal
            status,retry=http('/api/task/feedback',payload)
            assert status==200 and retry['replayed'] and retry['record_id']==formal['record_id']
            reopened=app.homework_saved_review(task['id'],formal['record_id'])
            assert reopened['text']==d['text'] and reopened['continuation']==pending and reopened['has_archived']
            assert model.call_count==0
        # Default reopen: only the same answer and teacher reference, no saved AI text selected; the saved same-scope gap continues.
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,out=http('/api/print/homework/draft',request)
            assert status==200 and out['draft']['items']==2 and out['draft']['unknown_items']==1,'saved same-scope pending label lost on default reopen'
            q=out['draft']['questions'][1];assert out['draft']['continuation']==pending and q['label']==unknown['label'] and '上一轮' in q['uncertainty']
            assert all(not q[k] for k in ('student_answer','answer','error_reason')),'only the label continues, never an old answer or judgment'
        # A newer valid check saved without structured output has nothing to continue: it neither blocks nor clears the known gap.
        bare=dict(task_id=task['id'],child='示例甲',day='2026-10-05',request_key='synthetic-pending-no-output',
            note='虚构核对的检查意见，未附检查文字。',attachments=[answer,teacher],review_basis=out['review_basis'])
        with patch.object(family_llm,'_chat_json') as model:
            status,plain=http('/api/task/feedback',bare)
            assert status==200 and not plain['completion_changed'] and model.call_count==0,plain
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,out=http('/api/print/homework/draft',request)
            assert status==200 and out['draft']['unknown_items']==1 and out['draft']['continuation']==pending,'a saved check without structured output must neither block nor clear the known gap'
        third=request|dict(previous_sources=[dict(type='upload',id=prior)])
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,rechecked=http('/api/print/homework/draft',third)
            assert status==200 and rechecked['draft']['unknown_items']==1,rechecked
        # Current sound evidence clears the pending label, not an old opinion's answer.
        resolved=raw|dict(items=[first,item(label=unknown['label'],student_answer='C',answer='教师参考：C')])
        with patch.object(family_llm,'_chat_json',return_value=resolved):
            status,finished=http('/api/print/homework/draft',third)
            assert status==200 and finished['draft']['continuation']['pending_labels']==[],finished
        status,formal,_,newer=saved(finished,'synthetic-pending-resolved')
        assert status==200,formal
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,out=http('/api/print/homework/draft',request)
            assert status==200 and out['draft']['unknown_items']==0,'a newer same-scope saved check must not revive the older gap on default reopen'
        path=Path(app.DATA)/'uploads'/newer;kept=path.read_bytes()
        try:
            path.write_bytes(kept+b'x')
            with app.connect() as c: rows='\n'.join(c.iterdump())
            with patch.object(family_llm,'_chat_json',return_value=omitted) as model:
                status,out=http('/api/print/homework/draft',request)
                assert status==409 and model.call_count==0,'an unverifiable newest saved check must not become a gap-free draft'
            with app.connect() as c: assert '\n'.join(c.iterdump())==rows and path.read_bytes()==kept+b'x','a refused reopen writes nothing and keeps the saved original'
            # A declared output that is missing is not a check saved without output: it also stops before the model.
            path.unlink()
            with patch.object(family_llm,'_chat_json',return_value=omitted) as model:
                status,out=http('/api/print/homework/draft',request)
                assert status==409 and model.call_count==0,'a missing declared saved output must not be skipped as if none was saved'
        finally: path.write_bytes(kept)
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            for previous in ([prior,newer],[newer,prior]):
                status,out=http('/api/print/homework/draft',request|dict(previous_sources=[dict(type='upload',id=i) for i in previous]))
                assert status==200 and out['draft']['unknown_items']==0,'older pending label must not revive after a newer same-scope check'
            changed=upload('synthetic-pending-new-teacher.txt','虚构新范围：虚构甲卷第1题B。'.encode())
            app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-05',request_key='synthetic-pending-new-reference',attachments=[changed]))
            status,out=http('/api/print/homework/draft',continued|dict(reference_sources=[dict(type='upload',id=changed)]))
            assert status==200 and out['draft']['unknown_items']==0,'a changed original scope must not inherit old labels'
            status,out=http('/api/print/homework/draft',continued|dict(previous_continuation=pending|dict(scope_sha256='0'*64)))
            assert status==200 and out['draft']['unknown_items']==0
            status,out=http('/api/print/homework/draft',continued|dict(previous_continuation=pending|dict(pending_labels=['bad\x00label'])))
            assert status==400,out
        # A forged saved scope cannot enter a formal result; originals and records stay intact.
        with app.connect() as c: before=c.execute('SELECT COUNT(*) FROM records').fetchone()[0]
        status,out,_,_=saved(initial,'synthetic-pending-foreign-scope',pending|dict(scope_sha256='0'*64))
        assert status==409 and out['code']=='review_basis_changed',out
        with app.connect() as c: assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==before
        # Legacy output without a model inventory still keeps the same pending checklist.
        with patch.object(family_llm,'_chat_json',return_value={k:v for k,v in omitted.items() if k!='question_labels'}):
            status,out=http('/api/print/homework/draft',continued)
            assert status==200 and out['draft']['unknown_items']==1,out
        over=dict(question_labels=[f'虚构甲卷第{n}题' for n in range(1,26)],
            items=[item(label=f'虚构甲卷第{n}题') for n in range(1,26)],coverage='虚构本次25项。')
        with patch.object(family_llm,'_chat_json',return_value=over):
            status,out=http('/api/print/homework/draft',continued)
            assert status!=200 and '超过25项' in out['error'],out
        for invalid in ('作业检查保存格式 v2\n无结构\n',
                '作业检查保存格式 v2\n复核待补清单：{}\n最新检查字数：1\n甲\n',
                '作业检查保存格式 v2\n复核待补清单：'+'['*1100+'0'+']'*1100+'\n最新检查字数：1\n甲\n'):
            refused(lambda:family_print.review_text(invalid,saved=True))
        for labels in ([str(n)+'"\\'*39 for n in range(10)], [str(n)+'\U0001f600'*78 for n in range(25)]):
            state=pending|dict(pending_labels=labels)
            frame='作业检查保存格式 v2\n复核待补清单：'+json.dumps(state)+'\n最新检查字数：1\n甲\n'
            assert family_print.review_text(frame,saved=True)['continuation']==state,'valid bounded labels must survive JSON escaping'
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,out=http('/api/print/homework/draft',continued|dict(question_sources=request['reference_sources'],reference_sources=request['question_sources']))
            assert status==200 and out['draft']['unknown_items']==0,'role changes must not inherit old pending labels'
            path=Path(app.DATA)/'uploads'/teacher;old=path.read_bytes()
            try:
                path.write_bytes(old.replace(b'C',b'D'))
                status,out=http('/api/print/homework/draft',continued)
                assert status==200 and out['draft']['unknown_items']==0,'same ID with changed bytes is a new review scope'
            finally: path.write_bytes(old)
        pdf=upload('synthetic-pending-reference.pdf',b'%PDF-synthetic-pending')
        app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-05',request_key='synthetic-pending-pdf',attachments=[pdf]))
        pdf_request=request|dict(reference_sources=[dict(type='upload',id=pdf,pages=[1])])
        def render(body,pages,deadline):
            return dict(page_count=2,pages=[dict(page=p,mime_type='image/png',data=png(p)) for p in pages],omitted_pages=[],complete=False)
        with patch.object(family_pdf,'page_count',return_value=2),patch.object(family_pdf,'render_pages',side_effect=render):
            with patch.object(family_llm,'_chat_json',return_value=raw):
                status,partial=http('/api/print/homework/draft',pdf_request);assert status==200,partial
            with patch.object(family_llm,'_chat_json',return_value=omitted):
                status,out=http('/api/print/homework/draft',pdf_request|dict(reference_sources=[dict(type='upload',id=pdf,pages=[2])],previous_continuation=partial['draft']['continuation']))
                assert status==200 and out['draft']['unknown_items']==0,'changing PDF selection must not inherit old scope'
        # Plain imported opinions never become deterministic scope checklists, even with a v2-shaped header.
        state=pending;frame='作业检查保存格式 v2\n复核待补清单：'+json.dumps(state)+'\n最新检查字数：1\n甲\n'
        plain=upload('synthetic-pending-imported-opinion.txt',frame.encode())
        app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-05',request_key='synthetic-pending-imported',attachments=[plain]))
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,out=http('/api/print/homework/draft',request|dict(previous_sources=[dict(type='upload',id=plain)]))
            assert status==200 and out['draft']['unknown_items']==0,'imported text is not a product checklist'
        corrected=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-05',record_id=original['record_id'],
            expected_created=original['feedback']['created'],note='虚构原作答说明更正。',attachments=[answer,teacher]))
        with patch.object(family_llm,'_chat_json',return_value=omitted):
            status,out=http('/api/print/homework/draft',continued|dict(expected_created=corrected['feedback']['created']))
            assert status==200 and out['draft']['unknown_items']==0,'a new answer version must not inherit the old checklist'
    finally:
        server.shutdown();server.server_close();worker.join(timeout=3)


def scope_handler_checks(app,upload):
    """Disclosed G03-G10 and R13-1..3 through real HTTP draft, save, same-key retry and reopen: an unread level 「第几小问」「第？小问」 stays
    pending, never the parent's answer, while plain words after the path, 「是这道选择小题」, still compare as the path, as does a teacher's
    answer naming 「第2问」 (G10) or, with no source word, a later 「参考」 and 「第θ小问」 (R13-3), kept whole."""
    from http.client import HTTPConnection
    import threading
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    def http(method,path,payload=None):
        client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        try:
            client.request(method,path,json.dumps(payload) if payload is not None else None,{'Content-Type':'application/json','X-Family-Token':app.TOKEN})
            response=client.getresponse();return response.status,json.loads(response.read())
        finally: client.close()
    try:
        for case,label in (('G03','虚构榆溪卷第9题(4)第甲小问'),('G04','虚构榆溪卷第9题(4)第1、 2小问'),
                           ('G05','虚构榆溪卷第9题(4)第甲小问的答案'),('G06','虚构榆溪卷第9题(4)第甲问'),
                           ('G08','虚构榆溪卷第9题(4)第θ小问'),('G09','虚构榆溪卷第9题(4)第1 / 2小问'),
                           ('R13-1','虚构榆溪卷第9题(4)第几小问'),('R13-2','虚构榆溪卷第9题(4)第？小问')):
            task=app.new_task(dict(child='示例甲',title='虚构榆溪卷'+case,category='homework'))
            answer=upload('synthetic-%s-answer.txt'%case,('虚构榆溪卷\n%s 全虚构选择题。孩子作答C。'%label).encode())
            teacher=upload('synthetic-%s-teacher.txt'%case,'试卷名称：虚构榆溪卷\n第9题(4)：C。'.encode())
            original=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-09',
                request_key='synthetic-%s-original'%case,note='虚构榆溪卷第9题。',attachments=[answer,teacher]))
            source=lambda ident:dict(type='upload',id=ident)
            request=dict(purpose='review',task_id=task['id'],record_id=original['record_id'],expected_created=original['feedback']['created'],
                question_sources=[source(answer)],reference_sources=[source(teacher)])
            raw=dict(items=[item(label=label,question='全虚构选择题。',student_answer='C',answer='教师参考：C')],
                coverage='仅核这一虚构题，其余未核。',question_labels=[label])
            with patch.object(family_llm,'_chat_json',return_value=raw) as model:
                status,result=http('POST','/api/print/homework/draft',request)
                assert status==200 and model.call_count==1,(case,status,result)
            d=result['draft'];q,=d['questions']
            assert (q['label'],q['student_answer'],q['answer'],q['judgment'],d['unknown_items'],d['wrong_items'])==(label,'C','','unknown',1,0),(case,q)
            assert label in d['text'] and '教师参考：C' not in d['text'],(case,d['text'])
            ident=upload('作业批改参考-%s.txt'%original['record_id'],d['text'].encode())
            feedback=dict(task_id=task['id'],child='示例甲',day='2026-10-09',request_key='synthetic-%s-saved'%case,
                note='虚构家长核对：本题待补依据。',attachments=[answer,teacher,ident],review_basis=result['review_basis'],
                **({'comparison_note':d['comparison']} if d.get('comparison') else {}))
            with patch.object(family_llm,'_chat_json') as model:
                status,saved=http('POST','/api/task/feedback',feedback);assert status==200,(case,saved)
                status,retry=http('POST','/api/task/feedback',feedback)
                assert status==200 and retry['replayed'] and retry['record_id']==saved['record_id'],(case,retry)
                status,view=http('GET','/api/print/homework/saved-review?task_id='+task['id']+'&record_id='+str(saved['record_id']))
                assert status==200 and view['original_record_id']==original['record_id'] and view['text']==d['text'],(case,view)
                assert label in view['text'] and model.call_count==0,'save, same-key retry and reopen keep the pending label without a model'
        # G07: a level word with no number before it is plain words, so the same path compares through save, retry and reopen.
        case,label='G07','虚构榆溪卷第9题(4) 是这道选择小题'
        task=app.new_task(dict(child='示例甲',title='虚构榆溪卷'+case,category='homework'))
        answer=upload('synthetic-%s-answer.txt'%case,('虚构榆溪卷\n%s 全虚构选择题。孩子作答C。'%label).encode())
        teacher=upload('synthetic-%s-teacher.txt'%case,'试卷名称：虚构榆溪卷\n第9题(4)：C。'.encode())
        original=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-09',
            request_key='synthetic-%s-original'%case,note='虚构榆溪卷第9题。',attachments=[answer,teacher]))
        request=dict(purpose='review',task_id=task['id'],record_id=original['record_id'],expected_created=original['feedback']['created'],
            question_sources=[source(answer)],reference_sources=[source(teacher)])
        raw=dict(items=[item(label=label,question='全虚构选择题。',student_answer='C',answer='教师参考：C')],
            coverage='仅核这一虚构题，其余未核。',question_labels=[label])
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            status,result=http('POST','/api/print/homework/draft',request)
            assert status==200 and model.call_count==1,(case,status,result)
        d=result['draft'];q,=d['questions']
        assert (q['label'],q['student_answer'],q['answer'],q['judgment'],d['unknown_items'],d['wrong_items'])==(label,'C','教师参考：C','correct',0,0),(case,q)
        assert label in d['text'] and '教师参考：C' in d['text'],(case,d['text'])
        ident=upload('作业批改参考-%s.txt'%original['record_id'],d['text'].encode())
        feedback=dict(task_id=task['id'],child='示例甲',day='2026-10-09',request_key='synthetic-%s-saved'%case,
            note='虚构家长核对：本题与教师参考一致。',attachments=[answer,teacher,ident],review_basis=result['review_basis'],
            **({'comparison_note':d['comparison']} if d.get('comparison') else {}))
        with patch.object(family_llm,'_chat_json') as model:
            status,saved=http('POST','/api/task/feedback',feedback);assert status==200,(case,saved)
            status,retry=http('POST','/api/task/feedback',feedback)
            assert status==200 and retry['replayed'] and retry['record_id']==saved['record_id'],(case,retry)
            status,view=http('GET','/api/print/homework/saved-review?task_id='+task['id']+'&record_id='+str(saved['record_id']))
            assert status==200 and view['original_record_id']==original['record_id'] and view['text']==d['text'],(case,view)
            assert label in view['text'] and model.call_count==0,(case,'save, same-key retry and reopen keep the compared label without a model')
        # G10: a teacher's answer starts at 「教师参考答案为」, so 「第2问」 inside it names no level and the whole answer compares; R13-3:
        # with no source word the first answer content 「5」 starts it, so a later 「参考」 and 「第θ小问」 are that answer, kept whole.
        for case,line,stem,said in (('G10','第9题(4) 教师参考答案为先解第2问，再检查。','客观填空：按老师给出的步骤填写处理顺序。','先解第2问，再检查。'),
                                    ('R13-3','第9题(4)5，这是第θ小问的参考思路','客观填空：照老师给出的原话填写。','5，这是第θ小问的参考思路')):
            label='虚构榆溪卷第9题(4)'
            task=app.new_task(dict(child='示例甲',title='虚构榆溪卷'+case,category='homework'))
            answer=upload('synthetic-%s-answer.txt'%case,('虚构榆溪卷\n%s %s孩子作答：%s'%(label,stem,said)).encode())
            teacher=upload('synthetic-%s-teacher.txt'%case,('试卷名称：虚构榆溪卷\n'+line).encode())
            original=app.save_task_feedback(dict(task_id=task['id'],child='示例甲',day='2026-10-09',
                request_key='synthetic-%s-original'%case,note='虚构榆溪卷第9题。',attachments=[answer,teacher]))
            request=dict(purpose='review',task_id=task['id'],record_id=original['record_id'],expected_created=original['feedback']['created'],
                question_sources=[source(answer)],reference_sources=[source(teacher)])
            raw=dict(items=[item(label=label,question=stem,student_answer=said,answer='教师参考：'+said)],
                coverage='仅核这一虚构题，其余未核。',question_labels=[label])
            with patch.object(family_llm,'_chat_json',return_value=raw) as model:
                status,result=http('POST','/api/print/homework/draft',request)
                assert status==200 and model.call_count==1,(case,status,result)
            d=result['draft'];q,=d['questions']
            assert (q['label'],q['student_answer'],q['answer'],q['judgment'],d['unknown_items'],d['wrong_items'])==(label,said,'教师参考：'+said,'correct',0,0),(case,q)
            assert label in d['text'] and '教师参考：'+said in d['text'] and not q['uncertainty'],(case,d['text'])
            ident=upload('作业批改参考-%s.txt'%original['record_id'],d['text'].encode())
            feedback=dict(task_id=task['id'],child='示例甲',day='2026-10-09',request_key='synthetic-%s-saved'%case,
                note='虚构家长核对：本题与教师参考一致。',attachments=[answer,teacher,ident],review_basis=result['review_basis'],
                **({'comparison_note':d['comparison']} if d.get('comparison') else {}))
            with patch.object(family_llm,'_chat_json') as model:
                status,saved=http('POST','/api/task/feedback',feedback);assert status==200,(case,saved)
                status,retry=http('POST','/api/task/feedback',feedback)
                assert status==200 and retry['replayed'] and retry['record_id']==saved['record_id'],(case,retry)
                status,view=http('GET','/api/print/homework/saved-review?task_id='+task['id']+'&record_id='+str(saved['record_id']))
                assert status==200 and view['original_record_id']==original['record_id'] and view['text']==d['text'],(case,view)
                assert '教师参考：'+said in view['text'] and model.call_count==0,(case,'save, same-key retry and reopen keep the whole teacher answer without a model')
    finally:
        server.shutdown();server.server_close();worker.join(timeout=3)


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


def missing_condition_checks():
    """A6 replay and unseen variants: stated missing givens leave no definite grade; other guards stay."""
    def draft(items,teacher):
        with patch.object(family_llm,'_chat_json',return_value=dict(items=items,coverage='虚构合成检查。')) as model:
            result=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                reference_documents=[dict(name='synthetic-teacher.txt',text=teacher)] if teacher else [])
            assert model.call_count==1
        return result,{q['label']:q for q in result['questions']}
    def vetoed(q,student,answer,*words):
        assert q['judgment']=='unknown' and q['student_answer']==student and q['answer']==answer,q
        assert not q['error_reason'] and not q['possible_cause'] and not q['steps'],q
        assert all(word in q['uncertainty'] for word in words+('补全',)),q
    pine=('独立教师参考（全虚构）\n试卷名称：虚构松石卷\n第1题：74\n第2题：200。题目空格外已印“厘米”。\n'
          '第3题：22厘米。题目跨第1页和第2页，仍为同一题。\n第4题：375毫升。\n'
          '第5题：长方形有两条长边和两条宽边，所以周长是长宽之和的2倍。含义相同的说明可接受。\n'
          '第6题：所给图示没有短边长度，无法计算确定的周长。本题不提供数值参考。')
    gap='所给图示没有短边长度，无法计算确定的周长';a6='所给图示没有短边长度，无法计算确定的周长。本题不提供数值参考'
    a=lambda n,**c:item(label='虚构松石卷·第%d题'%n,question='虚构题面%d'%n)|c
    five='每种边长都有2条，所以长宽相加后再乘2。'
    result,got=draft([a(1,student_answer='74',answer='教师参考：74'),
        a(2,student_answer='20',answer='教师参考：200。题目空格外已印“厘米”。',judgment='incorrect',
          error_reason='1米等于100厘米，所以2米应等于200厘米；作答写成20，单位换算错误。',possible_cause='可能把进率误记为10。',steps='先写出1米＝100厘米。'),
        a(3,student_answer='22厘米',answer='教师参考：22厘米。题目跨第1页和第2页，仍为同一题。'),
        a(4,student_answer='',answer='教师参考：375毫升',judgment='unknown',uncertainty='作答区域为空白，未见孩子的最终作答，无法进行答案比较。'),
        a(5,student_answer=five,answer='教师参考：长方形有两条长边和两条宽边，所以周长是长宽之和的2倍。含义相同的说明可接受。',question_kind='subjective'),
        a(6,question='求下图长方形的周长。图中标出长边9厘米，短边标签缺失。',student_answer='24厘米',answer='教师参考：'+a6+'。',
          judgment='incorrect',error_reason='长方形周长必须知道长和宽；图中只有长边9厘米，缺少短边长度，不能得出确定的24厘米。',
          possible_cause='可能自行假设了短边长度。',steps='独立尝试：先列出周长公式。')],pine)
    vetoed(got['虚构松石卷·第6题'],'24厘米','教师参考：'+a6+'。','教师参考原文',gap)
    assert [got['虚构松石卷·第%d题'%n]['judgment'] for n in range(1,6)]==['correct','incorrect','correct','unknown','correct'],got
    assert got['虚构松石卷·第2题']['error_reason'] and got['虚构松石卷·第4题']['uncertainty'].startswith('作答区域为空白')
    assert '需订正1题，与参考一致3题，未判定2题' in result['text'] and (result['wrong_items'],result['unknown_items'])==(1,2),result
    assert '错误依据：长方形周长' not in result['text'] and '订正建议：独立尝试：先列出周长公式' not in result['text']
    result,got=draft([a(1,student_answer='74',answer='74'),
        a(2,student_answer='20',answer='200',judgment='incorrect',error_reason='2米等于200厘米，学生作答20错误'),
        a(3,student_answer='22厘米',answer='22厘米'),a(5,student_answer=five,answer='长方形有两条长边和两条宽边，所以周长是长宽之和的2倍。',question_kind='subjective'),
        a(6,student_answer='24厘米',answer=gap,judgment='incorrect',error_reason='题目未提供长方形短边的长度，无法计算确定的周长，学生作答24厘米错误')],pine)
    vetoed(got['虚构松石卷·第6题'],'24厘米','教师参考：'+a6,'教师参考原文',gap)
    assert got['虚构松石卷·第1题']['judgment']=='correct'
    for n in (2,3,5):
        q=got['虚构松石卷·第%d题'%n]
        assert q['judgment']=='unknown' and '尚未核明' in q['uncertainty'] and '未按教师参考' not in q['uncertainty'] and '附注' in q['uncertainty'],q
    fir=('试卷名称：虚构云杉卷\n第3题：图中圆没有标出半径，无法求出确定的面积。\n第4题：B\n'
         '第8题：只给出一个数量，缺少第二个数量，不能核定两数之差。\n第9题：5米。缺单位扣1分。')
    b=lambda n,**c:item(label='虚构云杉卷·第%d题'%n,question='虚构题面%d'%n)|c
    result,got=draft([b(3,student_answer='12.56平方厘米',answer='教师参考：图中圆没有标出半径，无法求出确定的面积。'),
        b(4,question='',student_answer='C',judgment='incorrect',error_reason='题干缺失，无法确定题意；作答C与教师参考B不同。'),
        b(8,student_answer='7',answer='AI自行推导：9',judgment='incorrect',error_reason='两数之差应为9，作答7错误。',steps='再算一次。'),
        b(9,student_answer='5',answer='教师参考：5米。缺单位扣1分。',judgment='incorrect',error_reason='缺少单位米。')],fir)
    vetoed(got['虚构云杉卷·第3题'],'12.56平方厘米','教师参考：图中圆没有标出半径，无法求出确定的面积。','没有标出半径')
    vetoed(got['虚构云杉卷·第8题'],'7','教师参考：只给出一个数量，缺少第二个数量，不能核定两数之差','缺少第二个数量')
    assert got['虚构云杉卷·第4题']['judgment']=='incorrect' and got['虚构云杉卷·第4题']['answer']=='教师参考：B',got
    assert got['虚构云杉卷·第9题']['judgment']=='incorrect' and got['虚构云杉卷·第9题']['error_reason']=='缺少单位米。',got
    result,got=draft([item(label='第1题',question='虚构题面',student_answer='36平方厘米',answer='AI自行推导：图中没有给出高，无法计算确定的面积。',
                           judgment='incorrect',error_reason='面积应另行计算。'),
        item(label='第2题',question='虚构题面',student_answer='36',answer='AI自行推导：40',judgment='incorrect',error_reason='题中缺少宽，不能得出确定的面积。'),
        item(label='第3题',question='虚构题面',student_answer='20',answer='AI自行推导：200',judgment='incorrect',error_reason='没有掌握进率，不能得出正确结果。')],'')
    vetoed(got['第1题'],'36平方厘米','AI自行推导：图中没有给出高，无法计算确定的面积。','所列参考','没有给出高')
    vetoed(got['第2题'],'36','AI自行推导：40','检查依据','缺少宽')
    assert got['第3题']['judgment']=='incorrect' and got['第3题']['error_reason'],got
    # Nine fictional boundary cases: only this question's actual missing given, with no settled value, vetoes a grade;
    # a hypothesis, the child's skill or work, another question, a negation or a missing stem does not.
    cases=[('槐树',7,'图中半径明确为4，求圆的面积。','16π','若没有半径则无法计算，本题半径明确为4，面积为16π','correct',''),
        ('银杏',2,'图中半径明确为4，求圆的面积。','8π','16π。孩子没有掌握公式，无法计算','incorrect','作答8π与老师明确16π不同。'),
        ('山茶',3,'本题2米换算成厘米。','20','200。上一题缺宽无法核定，本题教师参考200','incorrect','本题20与教师200不同。'),
        ('梧桐',4,'本题2米换算成厘米。','20','200','incorrect','孩子没有掌握进率，无法算出准确结果，最终20与参考200不同。'),
        ('石楠',5,'本题2+3的值，题目条件完整。','4','5。条件并不缺失，无法核定的只是孩子是否独立完成','incorrect','本题4与参考5不同。'),
        ('木兰',8,'本题2米换算成厘米。','20','200','incorrect','学生未提供计算过程，无法核定其解题步骤，但最终20与参考200不同。'),
        ('杜鹃',9,'图中仅给长9，短边长度未标注，求周长。','24','所给图示没有短边长度，无法计算确定的周长。本题不提供数值参考','incorrect','题中缺少短边长度，不能得出确定的周长。'),
        ('栀子',11,'','C','B','incorrect','题干缺失，无法确定题意；作答C与教师参考B不同。'),
        ('花梨',12,'已标长9，短边标签缺失，求长方形周长。','24厘米','题目没有给出短边长度。无法核定周长。','incorrect','作答24厘米未核定。')]
    label=lambda paper,n:'虚构%s卷·第%d题'%(paper,n)
    result,got=draft([item(label=label(p,n),question=q,student_answer=s,answer='教师参考：'+t,judgment=j,error_reason=e) for p,n,q,s,t,j,e in cases],
                     ''.join('试卷名称：虚构%s卷\n第%d题：%s\n'%(p,n,t) for p,n,_,_,t,_,_ in cases))
    vetoed(got[label('杜鹃',9)],'24','教师参考：'+cases[6][4],'教师参考原文','所给图示没有短边长度，无法计算确定的周长')
    vetoed(got[label('花梨',12)],'24厘米','教师参考：'+cases[8][4],'教师参考原文','题目没有给出短边长度。无法核定周长')
    for p,n,_,s,t,j,e in cases[:6]+cases[7:8]:
        q=got[label(p,n)]
        assert (q['judgment'],q['student_answer'],q['answer'],q['error_reason'],q['uncertainty'])==(j,s,'教师参考：'+t,e,''),q
    assert '需订正6题，与参考一致1题，未判定2题' in result['text'] and (result['wrong_items'],result['unknown_items'])==(6,2),result
    # Unseen variants: a linked 「所以无法」 sentence vetoes; 「如果」, the child's inability, another question,
    # 「并非缺少」 and a question mark do not.
    v=lambda n,**c:item(label='第%d题'%n,question='虚构题面',student_answer='25',judgment='incorrect',error_reason='作答25与27不同。')|c
    result,got=draft([v(1,student_answer='27',answer='AI自行推导：如果图中没有标出宽，就无法求出面积；本题宽为3，面积27',judgment='correct',error_reason=''),
        v(2,answer='AI自行推导：图中没有标出宽。所以无法求出确定的面积。'),v(3,answer='AI自行推导：27。图中没有标出宽。孩子无法求出面积。'),
        v(4,answer='AI自行推导：27。第6题图中缺宽，无法核定。',error_reason='并非缺少条件，无法核定的是孩子的书写；作答25与27不同。'),
        v(5,answer='AI自行推导：27',error_reason='题中缺少宽？无法核定。作答25与27不同。'),
        v(6,answer='AI自行推导：存在以下问题：缺少宽，无法计算确定的面积。')],'')
    vetoed(got['第2题'],'25','AI自行推导：图中没有标出宽。所以无法求出确定的面积。','所列参考','图中没有标出宽。所以无法求出确定的面积')
    vetoed(got['第6题'],'25','AI自行推导：存在以下问题：缺少宽，无法计算确定的面积。','所列参考','缺少宽')
    assert got['第1题']['judgment']=='correct' and all(got['第%d题'%n]['judgment']=='incorrect' and got['第%d题'%n]['error_reason'] for n in (3,4,5)),got
    # Root's frozen unit pair: the question's own lengths given without a unit leave no comparison, while the child
    # leaving the unit off a given 3米+2米 stays a definite mistake. Unseen variants follow on both sides.
    elm=lambda paper,n,question,student,teacher,reason:dict(label='虚构%s卷·第%d题'%(paper,n),question=question,question_kind='objective',
        student_answer=student,answer='教师参考：'+teacher,judgment='incorrect',error_reason=reason,possible_cause='确定错因示例。',
        steps='确定订正步骤示例。',uncertainty='')
    bare='题目只给出两段长度数值2和30，但没有提供长度单位，无法比较哪一段更长。本题不提供确定比较答案。'
    two='两段长度只分别标出数值2和30，没有标明长度单位，哪一段更长？';rope='一根绳子长3米，接上2米，共长多少米？'
    result,got=draft([elm('榆树',10,two,'数值2的那段更短',bare,'仅比较数值2小于30，因此认定长度2更短。')],'试卷名称：虚构榆树卷\n第10题：%s\n'%bare)
    vetoed(got['虚构榆树卷·第10题'],'数值2的那段更短','教师参考：'+bare,'教师参考原文','但没有提供长度单位，无法比较哪一段更长')
    assert (len(result['questions']),result['wrong_items'],result['unknown_items'])==(1,0,1),result
    result,got=draft([elm('榆树',11,rope,'5','5米。缺单位扣1分。','孩子漏写单位米，作答未按要求写完整长度。')],'试卷名称：虚构榆树卷\n第11题：5米。缺单位扣1分。\n')
    q=got['虚构榆树卷·第11题']
    assert (q['judgment'],q['answer'],q['error_reason'],q['steps'])==('incorrect','教师参考：5米。缺单位扣1分。','孩子漏写单位米，作答未按要求写完整长度。','确定订正步骤示例。'),q
    assert (len(result['questions']),result['wrong_items'],result['unknown_items'])==(1,1,0),result
    units=['题目没有给出单位，无法比较两段长短','图中两个数值未标明单位，无法判断哪段更长','两段长度的单位没有提供，无法比较长短',
           '题中数值缺少单位，无法确定哪个更大','5米。作答没有单位，无法判定为全对','5米。缺少单位，不能判定为全对',
           '5米。没标单位，无法判定为满分','5米。孩子没有标明单位，无法判定为满分']
    result,got=draft([elm('枫杨',n,two,'数值2的那段更短',t+'。','只比较了数值。') if n<5 else elm('枫杨',n,rope,'5',t+'。','漏写单位米。')
                      for n,t in enumerate(units,1)],'试卷名称：虚构枫杨卷\n'+''.join('第%d题：%s。\n'%(n,t) for n,t in enumerate(units,1)))
    for n,t in enumerate(units[:4],1): vetoed(got['虚构枫杨卷·第%d题'%n],'数值2的那段更短','教师参考：'+t+'。','教师参考原文',t)
    assert all((got['虚构枫杨卷·第%d题'%n]['judgment'],got['虚构枫杨卷·第%d题'%n]['error_reason'])==('incorrect','漏写单位米。') for n in range(5,9)),got
    assert (result['wrong_items'],result['unknown_items'])==(4,4),result
    return 9


def word_boundary_checks():
    """W01/W02: a space between fullwidth Latin letters parts the teacher's words, as in 「a lot」; a joined quote stays unknown."""
    cases=(('虚构云杉卷','ｉｃｅ ｃｒｅａｍ','ｉｃｅｃｒｅａｍ','填写表示冰淇淋的英文短语'),('虚构银桦卷','Ａ ＬＯＴ','ＡＬＯＴ','填写表示许多的英文短语'))
    for n,(paper,spaced,joined,question) in enumerate(cases,1):
        label=paper+'第1题'
        raw=dict(coverage='仅核虚构本卷第1题。',question_labels=[label],items=[dict(answer='教师参考：'+joined,error_reason='',judgment='correct',
            label=label,possible_cause='',question=question,question_kind='objective',steps='',student_answer=joined,uncertainty='')])
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                reference_documents=[dict(name='synthetic-word-W%02d-teacher.txt'%n,text='试卷名称：%s\n第1题：%s。'%(paper,spaced))])
            assert model.call_count==1
        q,=result['questions']
        assert q['label']==label and q['judgment']=='unknown' and q['student_answer']==joined and q['answer']=='教师参考：'+spaced,q
        assert '教师参考原文' in q['uncertainty'] and not q['error_reason'] and not q['possible_cause'] and not q['steps'],q
        assert (result['wrong_items'],result['unknown_items'])==(0,1),result
    agrees=family_llm._ref_agrees
    for spaced in ('a lot','café noir','cafe\u0301 noir','ｉｃｅ ｃｒｅａｍ','Ａ ＬＯＴ','ｃａｆｅ\u0301 ｎｏｉｒ','ｃａｆé ｎｏｉｒ'):
        joined=spaced.replace(' ','')
        assert not agrees(joined,spaced) and not agrees(spaced,joined),spaced
        assert agrees(spaced.replace(' ','  '),spaced),spaced  # more spacing between the same words is still layout
    for claimed,teacher in (('光合作用','光 合 作 用'),('ｱｲｽ','ｱ ｲ ｽ'),('光合作用ice','光合作用 ice'),('5','2+3=5'),('2 + 3 = 5','2+3=5')):
        assert agrees(claimed,teacher) and agrees(teacher,claimed),(claimed,teacher)


def nested_sub_checks():
    """D01/D02: a sub-question is read to its last level; the teacher's 「第4题（2）」 answers 「（2）」 only, never 「（2）②」."""
    def draft(case,sub,teacher,answer='教师参考：B'):
        label='虚构松丘卷第4题'+sub
        raw=dict(items=[dict(label=label,question='全虚构选择题',student_answer='B',answer=answer,judgment='correct',question_kind='objective',
            error_reason='',possible_cause='',steps='',uncertainty='')],coverage='只核本次全虚构小题。',question_labels=[label])
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,
                question_documents=[dict(name='synthetic-nested-%s-answer.txt'%case,text='虚构松丘卷\n%s选择正确选项，孩子作答B。'%label)],
                reference_documents=[dict(name='synthetic-nested-%s-teacher.txt'%case,text='试卷名称：虚构松丘卷\n'+teacher)])
            assert model.call_count==1
        q,=result['questions']
        assert q['label']==label and q['student_answer']=='B' and result['wrong_items']==0,(case,q,result)
        return q,result
    q,result=draft('D02','（2）','第4题（2） B。')  # the one level both name is still the teacher's reference
    assert q['judgment']=='correct' and q['answer']=='教师参考：B' and result['unknown_items']==0,('D02',q)
    # 「（2）②」 is not 「（2）」, nor 「（2）①」: a level read only in part stays unknown and the teacher's answer is not borrowed.
    for case,sub,teacher in (('D01','（2）②','第4题（2） B。'),('D01-teacher-deeper','（2）','第4题（2）② B。'),('D01-sibling','（2）②','第4题（2）① B。')):
        q,result=draft(case,sub,teacher)
        assert q['judgment']=='unknown' and q['answer']=='' and '小题' in q['uncertainty'] and result['unknown_items']==1,(case,q)
        assert not q['error_reason'] and not q['possible_cause'] and not q['steps'],(case,q)
    # Disclosed full synthetic D01/D02: both sides name the whole path 「(2)(1)」「(3)(2)」 of the same paper and question, so it is the teacher's.
    for case,label,student,judgment,reason in (('qualified-D01','虚构松林卷第8题(2)(1)','B','correct',''),
                                               ('qualified-D02','虚构枫桥卷第9题(3)(2)','C','incorrect','作答C与教师参考B不同。')):
        paper,own=label.split('第',1);own='第'+own
        raw=dict(items=[dict(label=label,question='全虚构选择题，选择正确选项。',student_answer=student,answer='教师参考：B',judgment=judgment,question_kind='objective',
            error_reason=reason,possible_cause='',steps='',uncertainty='')],coverage='仅核本次全虚构明确的小题；其他题未列入。',question_labels=[label])
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,
                question_documents=[dict(name='synthetic-%s-answer.txt'%case,text='%s\n%s请选择正确选项；孩子作答%s。'%(paper,own,student))],
                reference_documents=[dict(name='synthetic-%s-teacher.txt'%case,text='试卷名称：%s\n%s：B。'%(paper,own))])
            assert model.call_count==1
        q,=result['questions']
        assert (q['label'],q['student_answer'],q['answer'],q['judgment'],q['error_reason'])==(label,student,'教师参考：B',judgment,reason),(case,q)
        assert result['unknown_items']==0 and result['wrong_items']==(judgment=='incorrect'),(case,result)
    # The same whole path pairs in any read notation; a parent, a deeper path, an unread level 「②」「(a)」 or another branch never does,
    # whichever source the model claims: 「AI自行推导」 is not kept beside a teacher answer whose scope is only a prefix of this one.
    q,result=draft('full-notation','（2）第1小问','第4题(2)(1) B。','AI自行推导：B')
    assert q['judgment']=='correct' and q['answer']=='教师参考：B' and result['unknown_items']==0,('full-notation',q)
    for case,sub,teacher,answer in (('full-parent','(2)(1)','第4题(2) B。','AI自行推导：B'),('full-deeper','(2)','第4题（2）（1） B。','AI自行推导：B'),
                                    ('full-unread-level','(2)(1)','第4题(2)② B。','教师参考：B'),('letter-level','(2)(a)','第4题(2) B。','AI自行推导：B'),
                                    ('full-branch','(2)(1)','第4题(2)(2) B。','教师参考：B')):
        q,result=draft(case,sub,teacher,answer)
        assert q['judgment']=='unknown' and q['answer']=='' and result['unknown_items']==1,(case,q)

    # Disclosed full synthetic F01/F02 (repair1): an unread qualifier 「(A)」 after 「(3)」 is never its parent; a teacher line naming 「(4)(a)」 with no answer keeps the question pending, never the model's claimed teacher value.
    for case,paper,own,teacher in (('repair1-F01','虚构青岸卷','第7题(3)(A)','试卷名称：虚构青岸卷\n第7题(3)：B'),
                                   ('repair1-F02','虚构白沙卷','第9题(4)(a)','试卷名称：虚构白沙卷\n第9题(4)(a)')):
        label=paper+own
        raw=dict(items=[dict(label=label,question='全虚构选择题',student_answer='B',answer='教师参考：B',judgment='correct',question_kind='objective',
            error_reason='',possible_cause='',steps='',uncertainty='')],question_labels=[label],coverage='仅核这一虚构题，其余未核。')
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,
                question_documents=[dict(name='synthetic-%s-answer.txt'%case,text='%s\n%s请选择正确选项，孩子作答B。'%(paper,label))],
                reference_documents=[dict(name='synthetic-%s-teacher.txt'%case,text=teacher)])
            assert model.call_count==1
        q,=result['questions']
        assert (q['label'],q['student_answer'],q['answer'],q['judgment'])==(label,'B','','unknown'),(case,q)
        assert not q['error_reason'] and not q['possible_cause'] and not q['steps'] and q['uncertainty'],(case,q)
        assert result['unknown_items']==1 and result['wrong_items']==0,(case,result)
        assert [p['label'] for p in result['questions'] if p['judgment']=='unknown']==[label],(case,result)
    # A page note 「（第1页）」 after the path is no level: the whole path 「(3)」 still pairs with the teacher's 「(3)」.
    label='虚构青岸卷第7题(3)（第1页）'
    raw=dict(items=[dict(label=label,question='全虚构选择题',student_answer='B',answer='教师参考：B',judgment='correct',question_kind='objective',
        error_reason='',possible_cause='',steps='',uncertainty='')],question_labels=[label],coverage='仅核这一虚构题，其余未核。')
    with patch.object(family_llm,'_chat_json',return_value=raw):
        result=family_llm.homework_reference_draft([],review=True,question_documents=[dict(name='synthetic-page-answer.txt',text='虚构青岸卷\n%s请选择正确选项，孩子作答B。'%label)],
            reference_documents=[dict(name='synthetic-page-teacher.txt',text='试卷名称：虚构青岸卷\n第7题(3)：B')])
    q,=result['questions']
    assert (q['answer'],q['judgment'])==('教师参考：B','correct') and result['unknown_items']==0,q
    # Disclosed full synthetic F03-F08 (repair4): a long, empty or unclosed bracket after the path is a level not read, never its parent's;
    # a teacher image may answer the very scope its text names without an answer, but no image settles a parent, an unread level or an unnamed paper.
    def scoped(case,label,teacher,student,images,answer,question):
        paper=label.split('第',1)[0]
        raw=dict(items=[dict(label=label,question=question,student_answer=student,answer=answer,judgment='correct',question_kind='objective',
            error_reason='',possible_cause='',steps='',uncertainty='')],question_labels=[label],coverage='仅核这一虚构题，其余未核。')
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,
                question_documents=[dict(name='synthetic-%s-answer.txt'%case,text='%s\n%s %s 孩子作答%s。'%(paper,label,question,student))],
                reference_documents=[dict(name='synthetic-%s-teacher.txt'%case,text=teacher)],reference_images=[dict(mime='image/png',data=png())]*images)
            assert model.call_count==1
        q,=result['questions']
        return q['label'],q['student_answer'],q['answer'],q['judgment'],q['error_reason']+q['possible_cause']+q['steps'],result['unknown_items'],result['wrong_items']
    reed,stone,willow,sums='虚构芦溪卷 第7题(3)：C','虚构石径卷 第9题（2）：D','试卷名称：虚构柳沙卷\n第11题（1）','2+3=? A.2 B.3 C.4 D.5'
    bad=[]
    for case,label,teacher,student,images,answer,question,expected in (
            ('F03','虚构芦溪卷第7题(3)(uvwxyzabcdefghijklmnoq)',reed,'C',0,'教师参考：C','全虚构选择题。',''),
            ('F04','虚构石径卷第9题（2）（zyxwvutsrqponmlkjihgf）',stone,'D',0,'教师参考：D','全虚构选择题。',''),
            ('unclosed','虚构芦溪卷第7题(3)(uvw',reed,'C',0,'教师参考：C','全虚构选择题。',''),
            ('empty','虚构芦溪卷第7题(3)()',reed,'C',0,'教师参考：C','全虚构选择题。',''),
            ('empty-fullwidth','虚构石径卷第9题（2）（）',stone,'D',0,'教师参考：D','全虚构选择题。',''),
            ('F05','虚构芦溪卷第7题(3)(1)','虚构芦溪卷 第7题(3)(1)：C','C',0,'教师参考：C','全虚构选择题。','教师参考：C'),
            ('F06','虚构芦溪卷第7题(3)（第2页）',reed,'C',0,'教师参考：C','全虚构选择题。','教师参考：C'),
            ('F07','虚构柳沙卷第11题（1）',willow,'D',1,'教师参考：D',sums,'教师参考：D'),
            ('F08','虚构柳沙卷第11题（1）（A）',willow,'D',1,'教师参考：D','全虚构选择小题。',''),
            ('F07-no-image','虚构柳沙卷第11题（1）',willow,'D',0,'教师参考：D',sums,''),
            ('F07-image-own','虚构柳沙卷第11题（1）',willow,'D',1,'AI自行推导：D',sums,''),
            ('F07-image-parent','虚构柳沙卷第11题',willow,'D',1,'教师参考：D',sums,''),
            ('F07-image-paper','虚构柳沙卷第11题（1）','第11题（1）','D',1,'教师参考：D',sums,'')):
        got=scoped(case,label,teacher,student,images,answer,question)
        if got!=(label,student,expected,'correct' if expected else 'unknown','',int(not expected),0): bad.append((case,got))
    assert not bad,bad
    # Disclosed full synthetic repair6 Handler cases: whatever stops the path short, a stray 「)」 before 「(A)」, a level word 「第A小问」
    # or any other mark not read, leaves the scope unknown on a label and a teacher line alike; the parent's answer is never borrowed,
    # nor is it waived by an image. A whole same path, a page note, plain words after the path and an image of the same scope still compare.
    reed,elm,q6='试卷名称：虚构芦溪卷\n第7题(3)：C。','试卷名称：虚构榆溪卷\n第9题(4)：C。','全虚构选择题。'
    bad=[]
    for case,label,teacher,student,images,expected,judgment in (
            ('R6-01','虚构芦溪卷第7题(3))(A)',reed,'C',0,'','unknown'),('R6-02','虚构榆溪卷第9题(4)第A小问',elm,'C',0,'','unknown'),
            ('stray-close','虚构芦溪卷第7题(3)）',reed,'C',0,'','unknown'),
            ('stray-after-number','虚构芦溪卷第7题)(A)','试卷名称：虚构芦溪卷\n第7题：C。','C',0,'','unknown'),
            ('square','虚构芦溪卷第7题(3)[A]',reed,'C',0,'','unknown'),('lenticular','虚构芦溪卷第7题(3)【甲】',reed,'C',0,'','unknown'),
            ('letter-ask','虚构榆溪卷第9题(4)第a问',elm,'C',0,'','unknown'),('roman-sub','虚构榆溪卷第9题(4)第Ⅱ小题',elm,'C',0,'','unknown'),
            ('mark-word','虚构榆溪卷第9题(4)A小问',elm,'C',0,'','unknown'),('word-mark','虚构榆溪卷第9题(4)小问B',elm,'C',0,'','unknown'),
            ('enclosed','虚构榆溪卷第9题(4)⑴',elm,'C',0,'','unknown'),
            ('teacher-mark','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)第A小问：C。','C',0,'','unknown'),
            ('teacher-stray','虚构芦溪卷第7题(3)','试卷名称：虚构芦溪卷\n第7题(3))(A)：C。','C',0,'','unknown'),
            ('image-mark','虚构榆溪卷第9题(4)第A小问','试卷名称：虚构榆溪卷\n第9题(4)','C',1,'','unknown'),
            ('path-same','虚构芦溪卷第7题(3)(1)','试卷名称：虚构芦溪卷\n第7题(3)(1)：C。','C',0,'教师参考：C','correct'),
            ('page-lenticular','虚构芦溪卷第7题(3)【第2页】',reed,'C',0,'教师参考：C','correct'),
            ('plain-words','虚构芦溪卷第7题(3) 看图选择',reed,'C',0,'教师参考：C','correct'),
            ('image-same','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)','C',1,'教师参考：C','correct')):
        got=scoped(case,label,teacher,student,images,'教师参考：'+student,q6)
        if got!=(label,student,expected,judgment,'',int(judgment=='unknown'),0): bad.append((case,got))
    assert not bad,bad
    # Disclosed full synthetic repair7 Handler cases G01/G02: a level names one whole number before its level word, so 「第VIII小问」 is
    # never cut back to 「(4)」, while plain words after the path, 「第一次问路」, are no level and the same path still compares.
    bad=[]
    for case,label,teacher,expected,judgment in (
            ('G01','虚构榆溪卷第9题(4)第VIII小问',elm,'','unknown'),('G02','虚构榆溪卷第9题(4) 第一次问路',elm,'教师参考：C','correct'),
            ('long-word-mark','虚构榆溪卷第9题(4)VIII小问',elm,'','unknown'),('long-sub','虚构榆溪卷第9题(4)第XIII小题',elm,'','unknown'),
            ('long-bracketed','虚构榆溪卷第9题(4)第(VIII)小问',elm,'','unknown'),
            ('teacher-long','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)第VIII小问：C。','','unknown'),
            ('words-day','虚构榆溪卷第9题(4)第二天问老师',elm,'教师参考：C','correct'),
            ('words-person','虚构榆溪卷第9题(4) 第一个问路的人',elm,'教师参考：C','correct'),
            ('blank-word','虚构榆溪卷第9题(4)第一个空',elm,'','unknown'),('ask-word','虚构榆溪卷第9题(4)第二问',elm,'','unknown'),
            ('mark-long-after','虚构榆溪卷第9题(4)小问VIII',elm,'','unknown'),('joined','虚构榆溪卷第9题(4)第4-1小问',elm,'','unknown')):
        got=scoped(case,label,teacher,'C',0,'教师参考：C',q6)
        if got!=(label,'C',expected,judgment,'',int(judgment=='unknown'),0): bad.append((case,got))
    assert not bad,bad
    # A classifier 「道」 or a listed run 「1、2」 inside the frame still names a level; a dish 「第一道菜」 is plain words.
    bad=[]
    for case,label,expected,judgment in (('classifier','虚构榆溪卷第9题(4)第一道小题','','unknown'),('listed','虚构榆溪卷第9题(4)第1、2小问','','unknown'),
                                         ('words-dish','虚构榆溪卷第9题(4) 第一道菜很香','教师参考：C','correct')):
        got=scoped(case,label,elm,'C',0,'教师参考：C',q6)
        if got!=(label,'C',expected,judgment,'',int(judgment=='unknown'),0): bad.append((case,got))
    assert not bad,bad
    # Disclosed full synthetic repair8 Handler cases G03/G04: an explicit level word 「小问」「小题」 closing what follows the path names a
    # level however its number is written, 「第甲小问」「第1、 2小问」, and a list mark before another level names a list; neither is ever
    # the parent's answer. A level word inside plain words 「小问题」, a list mark before plain words or 「小题」 restating (4) is no level.
    bad=[]
    for case,label,teacher,expected,judgment in (
            ('G03','虚构榆溪卷第9题(4)第甲小问',elm,'','unknown'),('G04','虚构榆溪卷第9题(4)第1、 2小问',elm,'','unknown'),
            ('named-bare','虚构榆溪卷第9题(4)甲小问',elm,'','unknown'),('named-bracketed','虚构榆溪卷第9题(4)第(甲)小问',elm,'','unknown'),
            ('named-comma','虚构榆溪卷第9题(4)第1，2小问',elm,'','unknown'),
            ('list-mark','虚构榆溪卷第9题(4)、(5)',elm,'','unknown'),('list-word','虚构榆溪卷第9题(4)和(5)',elm,'','unknown'),
            ('teacher-named','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)第甲小问：C。','','unknown'),
            ('words-problem','虚构榆溪卷第9题(4) 有个小问题',elm,'教师参考：C','correct'),
            ('words-after-list','虚构榆溪卷第9题(4)、第一次问路',elm,'教师参考：C','correct'),
            ('word-restated','虚构榆溪卷第9题(4)小题',elm,'教师参考：C','correct')):
        got=scoped(case,label,teacher,'C',0,'教师参考：C',q6)
        if got!=(label,'C',expected,judgment,'',int(judgment=='unknown'),0): bad.append((case,got))
    assert not bad,bad
    # Disclosed full synthetic repair9 Handler cases G05-G07: a level number is read whole whatever follows it, 「第甲小问的答案」, and
    # 「第甲问」「第(丙)问」 name a level as 「第二问」 does, on a label and a teacher line alike; a level word with no number before it,
    # 「是这道选择小题」「这道选择小题」, is plain words after the path and the same path still compares.
    bad=[]
    for case,label,teacher,expected,judgment in (
            ('G05','虚构榆溪卷第9题(4)第甲小问的答案',elm,'','unknown'),('G06','虚构榆溪卷第9题(4)第甲问',elm,'','unknown'),
            ('G07','虚构榆溪卷第9题(4) 是这道选择小题',elm,'教师参考：C','correct'),
            ('bracketed-ask','虚构榆溪卷第9题(4)第(丙)问',elm,'','unknown'),
            ('teacher-ask','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)第甲问：C。','','unknown'),
            ('words-choice','虚构榆溪卷第9题(4)这道选择小题',elm,'教师参考：C','correct')):
        got=scoped(case,label,teacher,'C',0,'教师参考：C',q6)
        if got!=(label,'C',expected,judgment,'',int(judgment=='unknown'),0): bad.append((case,got))
    assert not bad,bad
    # Disclosed full synthetic repair10 Handler cases G08-G10: whatever an ordinal frame 「第…小问/小题/问/空」 encloses names a level, a
    # mark not read 「θ」「□」 or a list with spaces or any list mark 「1 / 2」「1和2」 too, never the parent's answer, while plain words
    # 「第2次问老师」 name none; on a teacher line the answer starts at 「教师参考答案为」 or 「：」, or right after the path when neither
    # comes, so 「第2问」 inside the answer names no level and its whole value compares.
    bad=[]
    for case,label,teacher,expected,judgment in (
            ('G08','虚构榆溪卷第9题(4)第θ小问',elm,'','unknown'),('G09','虚构榆溪卷第9题(4)第1 / 2小问',elm,'','unknown'),
            ('mark-greek-ask','虚构榆溪卷第9题(4)第α问',elm,'','unknown'),('mark-box','虚构榆溪卷第9题(4)第□小题',elm,'','unknown'),
            ('mark-bare','虚构榆溪卷第9题(4)θ小问',elm,'','unknown'),('list-wide','虚构榆溪卷第9题(4)第１／２小问',elm,'','unknown'),
            ('list-joined','虚构榆溪卷第9题(4)第1和2小问',elm,'','unknown'),
            ('teacher-mark','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)第θ小问：C。','','unknown'),
            ('teacher-heading','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)的第甲小问：C。','','unknown'),
            ('words-times','虚构榆溪卷第9题(4) 第2次问老师',elm,'教师参考：C','correct')):
        got=scoped(case,label,teacher,'C',0,'教师参考：C',q6)
        if got!=(label,'C',expected,judgment,'',int(judgment=='unknown'),0): bad.append((case,got))
    q10='客观填空：按老师给出的步骤填写处理顺序。'
    for case,teacher,said in (('G10','第9题(4) 教师参考答案为先解第2问，再检查。','先解第2问，再检查。'),
                              ('answer-is','第9题(4) 答案是先解第2小问，再检查。','先解第2小问，再检查。'),
                              ('answer-bare','第9题(4) 先解第2问，再检查。','先解第2问，再检查。'),
                              ('answer-person','第9题(4) 教师参考答案为第一个人问。','第一个人问。')):
        got=scoped(case,'虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n'+teacher,said,0,'教师参考：'+said,q10)
        if got!=('虚构榆溪卷第9题(4)',said,'教师参考：'+said,'correct','',0,0): bad.append((case,got))
    assert not bad,bad
    # Disclosed full synthetic repair13 cases R13-1..3: an ordinal frame is read whole before its number, so 「第几小问」「第？小问」 name a
    # level not read, never the parent's answer, and 「的」 joins a heading to its next level 「(4)的(1)」 on a label and a teacher line
    # alike; plain words 「第一次问路」「第2次问老师」「有个小问题」 name none. On a teacher line only the continuous path is heading: the
    # first answer content starts the body, so a later 「参考」「答案」 or ordinal inside it neither names a level nor cuts the value.
    bad=[]
    for case,label,teacher,expected,judgment in (
            ('R13-1','虚构榆溪卷第9题(4)第几小问',elm,'','unknown'),('R13-2','虚构榆溪卷第9题(4)第？小问',elm,'','unknown'),
            ('ask-ascii','虚构榆溪卷第9题(4)第?小问',elm,'','unknown'),('ask-how-many','虚构榆溪卷第9题(4)第几问',elm,'','unknown'),
            ('blank-how-many','虚构榆溪卷第9题(4)第几个空',elm,'','unknown'),('linked-frame','虚构榆溪卷第9题(4)的第几小问',elm,'','unknown'),
            ('linked-bracket','虚构榆溪卷第9题(4)的(1)',elm,'','unknown'),
            ('teacher-how-many','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)第几小问：C。','','unknown'),
            ('teacher-ask','虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n第9题(4)的第？小问：C。','','unknown'),
            ('teacher-linked','虚构榆溪卷第9题(4)(1)','试卷名称：虚构榆溪卷\n第9题(4)的(1)：C。','教师参考：C','correct'),
            ('words-way','虚构榆溪卷第9题(4)第一次问路',elm,'教师参考：C','correct'),
            ('words-teacher','虚构榆溪卷第9题(4)第2次问老师',elm,'教师参考：C','correct'),
            ('words-how-often','虚构榆溪卷第9题(4) 第几次问老师',elm,'教师参考：C','correct'),
            ('words-small','虚构榆溪卷第9题(4)有个小问题',elm,'教师参考：C','correct')):
        got=scoped(case,label,teacher,'C',0,'教师参考：C',q6)
        if got!=(label,'C',expected,judgment,'',int(judgment=='unknown'),0): bad.append((case,got))
    for case,teacher,said in (('R13-3','第9题(4)5，这是第θ小问的参考思路','5，这是第θ小问的参考思路'),
                              ('body-later-word','第9题(4) 先解第2问，再写答案。','先解第2问，再写答案。'),
                              ('body-source-first','第9题(4) 教师参考答案为先核第3问，然后订正。','先核第3问，然后订正。')):
        got=scoped(case,'虚构榆溪卷第9题(4)','试卷名称：虚构榆溪卷\n'+teacher,said,0,'教师参考：'+said,q10)
        if got!=('虚构榆溪卷第9题(4)',said,'教师参考：'+said,'correct','',0,0): bad.append((case,got))
    assert not bad,bad

def teacher_note_checks():
    """A paper or 大题 named inside a teacher note is part of that value; only a heading starts a new scope."""
    calls=0
    def draft(items,teacher):
        nonlocal calls
        with patch.object(family_llm,'_chat_json',return_value=dict(items=items,coverage='仅这些虚构题，其他未核。')) as model:
            result=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                reference_documents=[dict(name='synthetic-teacher-note.txt',text=teacher)])
            assert model.call_count==1
        calls+=1;got={q['label']:q for q in result['questions']}
        judged=[q['judgment'] for q in result['questions']]  # counts and text follow the guarded questions
        assert result['items']==len(judged) and result['wrong_items']==judged.count('incorrect') and result['unknown_items']==judged.count('unknown'),result
        return result,got
    def kept(q,judgment,answer):
        assert q['judgment']==judgment and q['answer']==answer,q
    def unknown(q,student,*words):
        assert q['judgment']=='unknown' and q['student_answer']==student and not q['error_reason'] and not q['steps'],q
        assert all(word in q['uncertainty'] for word in words),q
    # Disclosed regression replay: the whole same-paper teacher value, its note on 乙卷 included, is the reference.
    mint='虚构薄荷卷第16题 500。乙卷缺少宽度，无法核定周长；本卷本题参考500'
    note='500。乙卷缺少宽度，无法核定周长；本卷本题参考500'
    replay=dict(label='虚构薄荷卷第16题',question='将5米换成厘米。',student_answer='50',answer='教师参考：'+note,judgment='incorrect',
                question_kind='objective',error_reason='虚构已知作答与参考不同。',possible_cause='',steps='',uncertainty='')
    result,got=draft([replay],mint)
    kept(got['虚构薄荷卷第16题'],'incorrect','教师参考：'+note)
    assert got['虚构薄荷卷第16题']['student_answer']=='50' and result['wrong_items']==1 and result['unknown_items']==0
    # The whole note is the teacher's: quoting only its opening 500 is not yet matched, and the full original is shown.
    result,got=draft([replay|dict(answer='教师参考：500')],mint)
    unknown(got['虚构薄荷卷第16题'],'50','开头');assert got['虚构薄荷卷第16题']['answer']=='教师参考：'+note
    # A note naming another 大题 is not cut either, and the next line keeps this paper.
    a=lambda label,**c:item(label=label,question='虚构题面')|c
    pine='虚构松针卷\n第7题 12。第二大题缺少高度，无法核定面积；本题参考12\n第8题 6'
    note7='12。第二大题缺少高度，无法核定面积；本题参考12'
    result,got=draft([a('虚构松针卷第7题',student_answer='21',answer='教师参考：'+note7,judgment='incorrect',error_reason='作答21与教师参考12不同。'),
                      a('虚构松针卷第8题',student_answer='6',answer='教师参考：6')],pine)
    kept(got['虚构松针卷第7题'],'incorrect','教师参考：'+note7);kept(got['虚构松针卷第8题'],'correct','教师参考：6')
    # Real headings on one line still split papers, 大题 and questions; a bare heading ending a line applies below.
    multi='虚构甲卷第1题 5；虚构乙卷第1题 6\n虚构丙卷 第一大题 第2题 A 第二大题 第2题 C\n虚构丁卷第3题 8。虚构戊卷\n第3题 9'
    result,got=draft([a('虚构甲卷第1题',student_answer='5',answer='教师参考：5'),
                      a('虚构乙卷第1题',student_answer='5',answer='教师参考：6',judgment='incorrect',error_reason='作答5与教师参考6不同。'),
                      a('虚构丙卷第一大题第2题',student_answer='C',answer='教师参考：A',judgment='incorrect',error_reason='作答C与教师参考A不同。'),
                      a('虚构丙卷第二大题第2题',student_answer='C',answer='教师参考：C'),
                      a('虚构丁卷第3题',student_answer='8',answer='教师参考：8'),a('虚构戊卷第3题',student_answer='9',answer='教师参考：9')],multi)
    assert [q['judgment'] for q in result['questions']]==['correct','incorrect','incorrect','correct','correct','correct'],result['questions']
    # Same number on another paper stays isolated: 乙卷第3题's own value is its note, not 甲卷's 8.
    result,got=draft([a('虚构甲卷第3题',student_answer='8',answer='教师参考：8'),a('虚构乙卷第3题',student_answer='8',answer='教师参考：8')],
                     '虚构甲卷第3题 8。虚构乙卷第3题另有说明')
    kept(got['虚构甲卷第3题'],'correct','教师参考：8');unknown(got['虚构乙卷第3题'],'8','不一致')
    # Unclear structure stays unknown: a paper named with other words right before the next question owns neither reading.
    result,got=draft([a('虚构甲卷第2题',student_answer='6',answer='教师参考：6'),a('虚构乙卷第2题',student_answer='6',answer='教师参考：6')],
                     '虚构甲卷第1题 5，虚构乙卷另附说明第2题 6')
    unknown(got['虚构甲卷第2题'],'6');unknown(got['虚构乙卷第2题'],'6','无法核明')
    # A note on another paper never stands for this question's missing given; this question's own stays a veto.
    result,got=draft([a('虚构薄荷卷第18题',student_answer='20',answer='教师参考：乙卷另有长方形。本题缺少宽度，无法核定周长',judgment='incorrect',
                        error_reason='作答与参考不同。')],'虚构薄荷卷第18题 乙卷另有长方形。本题缺少宽度，无法核定周长')
    unknown(got['虚构薄荷卷第18题'],'20','缺少决定性条件','补全')
    # The child's own missing unit is not a missing condition, even beside another paper's note.
    unit='500厘米。乙卷同题作答缺单位不得分'
    result,got=draft([a('虚构薄荷卷第19题',student_answer='500',answer='教师参考：'+unit,judgment='incorrect',error_reason='作答缺少单位。')],
                     '虚构薄荷卷第19题 '+unit)
    kept(got['虚构薄荷卷第19题'],'incorrect','教师参考：'+unit)
    return calls


def teacher_note_owner_checks():
    """A paper named in a missing-given note is another paper's only when that whole name is known to differ from this question's."""
    calls=0
    def draft(items,teacher,coverage='只核对这些虚构题，其他未核。'):
        nonlocal calls
        with patch.object(family_llm,'_chat_json',return_value=dict(items=items,coverage=coverage)) as model:
            result=family_llm.homework_reference_draft([dict(mime='image/png',data=png())],review=True,
                reference_documents=[dict(name='synthetic-teacher-note.txt',text=teacher)])
            assert model.call_count==1
        calls+=1;got={q['label']:q for q in result['questions']}
        judged=[q['judgment'] for q in result['questions']]  # counts and text follow the guarded questions
        assert result['items']==len(judged) and result['wrong_items']==judged.count('incorrect') and result['unknown_items']==judged.count('unknown'),result
        return result,got
    def unknown(q,student,answer):  # the child's answer and the whole teacher original stay, no definite correction is left
        assert q['judgment']=='unknown' and q['student_answer']==student and q['answer']==answer,q
        assert not q['error_reason'] and not q['possible_cause'] and not q['steps'] and q['uncertainty'].strip(),q
    # Disclosed regression replay (fictional; a development regression, not held out): the note names this question's own whole paper.
    note='本题条件说明：虚构沐岑卷：缺少半径，无法核定面积；请补全本题半径后再核对'
    replay=dict(label='虚构沐岑卷第29题',question='本题的圆形题图未标半径或直径，求面积。',student_answer='16π平方厘米',answer='教师参考：'+note,
                judgment='incorrect',question_kind='objective',error_reason='虚构模型认定16π与参考不同。',possible_cause='虚构模型猜测发生运算错误。',
                steps='虚构模型要求重新计算本题面积。',uncertainty='')
    result,got=draft([replay],'虚构沐岑卷第29题 '+note,'只核对本虚构题，其他未核。')
    unknown(got['虚构沐岑卷第29题'],'16π平方厘米','教师参考：'+note)
    judged=[q['judgment'] for q in result['questions']]
    assert got['虚构沐岑卷第29题']['question']==replay['question'] and judged.count('correct')==result.get('correct_items',0)==0,result
    assert (result['items'],result['wrong_items'],result['unknown_items'])==(1,0,1),result
    # When this question's paper cannot be confirmed, the named note is not set aside either.
    result,got=draft([replay|dict(label='第29题')],'第29题 '+note)
    unknown(got['第29题'],'16π平方厘米','教师参考：'+note)
    # A pointing 「这张卷」 names no other paper: this question's missing given still vetoes, as on the earlier main.
    this='这张卷缺少半径，无法核定面积'
    result,got=draft([replay|dict(label='虚构沐岑卷第30题',answer='教师参考：'+this)],'虚构沐岑卷第30题 '+this)
    unknown(got['虚构沐岑卷第30题'],'16π平方厘米','教师参考：'+this)
    # Only a note under a whole paper name known to differ is set aside: this paper's own 12 still grades the child's 21.
    other='12。虚构青石卷：缺少半径，无法核定面积；本卷本题参考12'
    result,got=draft([item(label='虚构沐岑卷第31题',question='虚构题面')|dict(student_answer='21',answer='教师参考：'+other,judgment='incorrect',
                      error_reason='作答21与教师参考12不同。')],'虚构沐岑卷第31题 '+other)
    assert got['虚构沐岑卷第31题']['judgment']=='incorrect' and got['虚构沐岑卷第31题']['answer']=='教师参考：'+other and result['wrong_items']==1,result
    # Disclosed full-entry regression (fictional; a development regression, not held out): a note under this question's own heading
    # naming 「当前卷」 points at a paper and confirms no other, so through the real entry, with the question and teacher documents and
    # no image, the child's answer and the whole teacher original stay, unknown, with the definite correction cleared.
    current=dict(label='虚构沐岑卷第29题',question='本题的圆形题图未标半径或直径，求面积。',student_answer='16π平方厘米',
                 answer='教师参考：当前卷缺少半径，无法核定面积',judgment='incorrect',question_kind='objective',
                 error_reason='虚构模型认定16π与参考不同。',possible_cause='虚构模型猜测发生运算错误。',steps='虚构模型要求重新计算本题面积。',
                 uncertainty='')
    with patch.object(family_llm,'_chat_json',return_value=dict(items=[current],coverage='只核对本虚构题，其他未核。')) as model:
        result=family_llm.homework_reference_draft([],review=True,
            question_documents=[dict(name='fictional-question.txt',text='虚构沐岑卷第29题 本题的圆形题图未标半径或直径，求面积。\n实际作答：16π平方厘米')],
            reference_documents=[dict(name='fictional-teacher.txt',text='虚构沐岑卷第29题 当前卷缺少半径，无法核定面积')])
        assert model.call_count==1
    calls+=1;judged=[q['judgment'] for q in result['questions']];q=result['questions'][0]
    unknown(q,'16π平方厘米','教师参考：当前卷缺少半径，无法核定面积')
    assert q['label']==current['label'] and q['question']==current['question'] and '半径' in q['uncertainty'],q
    assert ((result['items'],result['wrong_items'],result['unknown_items'],result.get('correct_items',0))==(1,0,1,0)
            ==(len(judged),judged.count('incorrect'),judged.count('unknown'),judged.count('correct'))),result
    # Same cause, development checks: a pointing name no determiner list holds, or a whole name the source never separates from
    # this question, confirms no other paper; a request about this question is no reference of its own either.
    for n,said in enumerate(('上述卷缺少半径，无法核定面积','虚构青石卷缺少半径，无法核定面积','上述卷缺少半径，无法核定面积；请补全本题半径后再核对')):
        label='虚构沐岑卷第%d题'%(32+n)
        result,got=draft([replay|dict(label=label,answer='教师参考：'+said)],label+' '+said)
        unknown(got[label],'16π平方厘米','教师参考：'+said)
    # Only when the teacher states this question's own reference apart from the note is a different whole name another paper's.
    apart='8。虚构乙卷缺少宽度，无法核定周长；本题参考答案8'
    result,got=draft([item(label='虚构沐岑卷第35题',question='虚构题面')|dict(student_answer='9',answer='教师参考：'+apart,judgment='incorrect',
                      error_reason='作答9与教师参考8不同。')],'虚构沐岑卷第35题 '+apart)
    assert got['虚构沐岑卷第35题']['judgment']=='incorrect' and got['虚构沐岑卷第35题']['answer']=='教师参考：'+apart and result['wrong_items']==1,result
    # Disclosed full-entry regression (fictional; a development regression, not held out): this question's value opens with 12 and
    # restates it after a note naming 「当前卷」. A pointing name confirms no other paper however the value goes on, so through the
    # real entry the child's answer and the whole teacher original stay, unknown, with the definite correction cleared.
    leading='12。当前卷缺少半径，无法核定面积；本卷本题参考12'
    regression=current|dict(answer='教师参考：'+leading)
    with patch.object(family_llm,'_chat_json',return_value=dict(items=[regression],coverage='只核对本虚构题，其他未核。')) as model:
        result=family_llm.homework_reference_draft([],review=True,
            question_documents=[dict(name='fictional-question.txt',text='虚构沐岑卷第29题 本题的圆形题图未标半径或直径，求面积。\n实际作答：16π平方厘米')],
            reference_documents=[dict(name='fictional-teacher.txt',text='虚构沐岑卷第29题 '+leading)])
        assert model.call_count==1
    calls+=1;judged=[q['judgment'] for q in result['questions']];q=result['questions'][0]
    unknown(q,'16π平方厘米','教师参考：'+leading)
    assert q['label']==regression['label'] and q['question']==regression['question'] and '半径' in q['uncertainty'],q
    assert ((result['items'],result['wrong_items'],result['unknown_items'],result.get('correct_items',0))==(1,0,1,0)
            ==(len(judged),judged.count('incorrect'),judged.count('unknown'),judged.count('correct'))),result
    # Same cause, development checks: a determiner phrase the one-character generic form read as a name confirms no other paper even
    # beside this question's own 12, and as a heading it reads as 「本卷」 does, never as another paper's question.
    for n,pointing in enumerate(('上述卷','当前的卷','这份卷')):
        label,said='虚构沐岑卷第%d题'%(36+n),'12。%s缺少半径，无法核定面积；本题参考答案12'%pointing
        result,got=draft([replay|dict(label=label,answer='教师参考：'+said)],label+' '+said)
        unknown(got[label],'16π平方厘米','教师参考：'+said)
    read=[]
    for heading in ('本卷','当前卷'):
        result,got=draft([item(label='虚构沐岑卷第39题',question='虚构题面')|dict(student_answer='21',answer='教师参考：12',judgment='incorrect',
                          error_reason='作答21与教师参考12不同。')],heading+'第39题 12')
        read.append({k:got['虚构沐岑卷第39题'][k] for k in ('judgment','answer','uncertainty')})
    assert read[0]==read[1] and read[0]['judgment']=='unknown',read
    # A whole name the shared reading gives as another paper is set aside only when this question's own reference stands apart, in
    # whatever order: the 12 opening the value or given in a sentence of its own still grades the child's 21, while another paper's
    # note with only a request about this question has no reference of this question's and stays unknown.
    for n,said in enumerate(('12。虚构青石卷缺少半径，无法核定面积','虚构青石卷缺少半径，无法核定面积；本题参考答案12')):
        label='虚构沐岑卷第%d题'%(40+n)
        result,got=draft([item(label=label,question='虚构题面')|dict(student_answer='21',answer='教师参考：'+said,judgment='incorrect',
                          error_reason='作答21与教师参考12不同。')],label+' '+said)
        assert got[label]['judgment']=='incorrect' and got[label]['answer']=='教师参考：'+said and result['wrong_items']==1,result
    said='虚构青石卷缺少半径，无法核定面积；请补全本题半径后再核对'
    result,got=draft([replay|dict(label='虚构沐岑卷第42题',answer='教师参考：'+said)],'虚构沐岑卷第42题 '+said)
    unknown(got['虚构沐岑卷第42题'],'16π平方厘米','教师参考：'+said)
    return calls



def run():
    contract_cases=output_contract_checks()+choice_judgment_checks()+duplicate_question_checks()+summary_consistency_checks()+question_coverage_checks()+missing_condition_checks()+teacher_note_checks()+teacher_note_owner_checks()
    word_boundary_checks()
    nested_sub_checks()
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
            assert '2题' in limited['comparison'] and '不能沿用' in limited['comparison']
            assert all(limited['text'].count(label)==1 for label in ('Q2','Q3'))
            assert '上一轮三题均正确' not in limited['comparison']
            assert 'Q1—Q3均正确，整卷已检查完' not in limited['text']+limited['coverage']
            assert '2题仍未判定' in limited['coverage']
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
            later_teacher=upload('synthetic-recheck-later-teacher.txt','虚构教师参考：第1题B，第2题B，必须写理由。'.encode())
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
            recheck_model_result=model_result|dict(comparison=comparison,question_labels=['第1题','第2题'],items=[item(),
                item(label='第2题',question='虚构第2题：判断并写出理由。',student_answer='B，未写理由。',
                     answer='教师参考：B，必须写理由。',question_kind='subjective',judgment='incorrect',
                     error_reason='第2题作答缺少老师要求的判断理由。')])
            def recheck_model(messages,schema,name,timeout,**kwargs):
                serialized=json.dumps(messages,ensure_ascii=False)
                assert all(text in serialized for text in (action,instruction,prior_text,previous_text,'第2题B，必须写理由'))
                return recheck_model_result
            with patch.object(family_llm,'homework_reference_draft',wraps=family_llm.homework_reference_draft) as generate,patch.object(family_llm,'_chat_json',side_effect=recheck_model):
                rechecked=app.homework_review_draft(recheck_request)
                args=generate.call_args.kwargs
                assert args['task_action']==action and args['review_instruction']==instruction and args['previous_text']==previous_text
                assert args['previous_documents']==[dict(name=review_name,text=prior_text)]
                assert args['reference_documents']==[dict(name='synthetic-recheck-later-teacher.txt',text='虚构教师参考：第1题B，第2题B，必须写理由。')]
            assert rechecked['draft']['unverified_model_summary']['comparison']==comparison
            assert [q['label'] for q in rechecked['draft']['questions']]==['第1题','第2题']
            assert rechecked['draft']['questions'][1]['judgment']=='incorrect'
            assert '第2题作答缺少老师要求的判断理由' in rechecked['draft']['text'], 'the new question must actually reach the saved review'
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
            recheck_pending_http_checks(app,upload)
            summary_http_checks(app,upload)
            scope_handler_checks(app,upload)
            review_origin_http_checks(app,upload)
    print('homework review synthetic checks passed (%d output contract cases)'%contract_cases)


if __name__=='__main__': run()

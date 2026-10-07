"""Synthetic text-paper role, safety and real HTTP checks; no model or printer I/O."""
import io
import hashlib
import json
import unittest
import zipfile
from unittest.mock import patch
from xml.sax.saxutils import escape

import app
import family_llm
from test_homework_print_scope import HomeworkPrintScopeTests, PNG


def docx(text, extra=(), content=None):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>'+(content or '<w:p><w:r><w:t>'+escape(text)+'</w:t></w:r></w:p>')+'</w:body></w:document>')
        for name,body in extra:z.writestr(name,body)
    return data.getvalue()


QUESTION='虚构甲卷第1题：2+3=?\n实际作答：4'
REFERENCE='虚构甲卷第1题教师参考：5'
RAW=dict(items=[dict(label='虚构甲卷第1题',question='2+3=?',student_answer='4',answer='教师参考：5',judgment='incorrect',question_kind='objective',error_reason='作答4与教师参考5不同。',possible_cause='',steps='',uncertainty='')],coverage='仅本次虚构甲卷第1题。')


CHOICE='虚构甲卷第1题：2+3=? A.4 B.5 C.6\n实际作答：B'
TEACHER_B='虚构甲卷 第1题：教师参考B'


def choice(**changes):
    """Frozen synthetic reply that swaps the teacher-covered answer for its own derivation."""
    return dict(label='虚构甲卷第1题',question='2+3=? A.4 B.5 C.6',student_answer='B',answer='AI自行推导：C',judgment='incorrect',
                question_kind='objective',error_reason='作答B与推导C不同。',possible_cause='',steps='先重新计算。',uncertainty='')|changes


class TeacherReferencePriorityTests(unittest.TestCase):
    def draft(self,items,teacher=TEACHER_B,question=CHOICE,**extra):
        raw=dict(question_labels=[i['label'] for i in items],items=items,coverage='虚构冻结回执。')
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=[dict(name='synthetic-choice.txt',text=question)],
                reference_documents=[dict(name='synthetic-choice-teacher.txt',text=teacher)],**extra)
        self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        return result

    def test_same_paper_question_compares_by_teacher_not_model_source(self):
        result=self.draft([choice()]);q=result['questions'][0]
        self.assertEqual((q['answer'],q['judgment'],q['error_reason'],q['steps']),('教师参考：B','correct','',''))
        self.assertEqual((result['wrong_items'],result['unknown_items']),(0,0));self.assertIn('需订正0题',result['text'])
        self.assertNotIn('AI自行推导：C',result['text'])
        result=self.draft([choice(student_answer='C',judgment='correct',error_reason='',steps='')]);q=result['questions'][0]
        self.assertEqual((q['answer'],q['judgment']),('教师参考：B','incorrect'))
        self.assertIn('C',q['error_reason']);self.assertIn('教师参考B',q['error_reason'])
        self.assertEqual((result['wrong_items'],result['unknown_items']),(1,0));self.assertIn('需订正1题',result['text'])
        # A teacher label on a different letter is still the model's claim, not the supplied teacher text.
        result=self.draft([choice(answer='教师参考：C')]);q=result['questions'][0]
        self.assertEqual((q['answer'],q['judgment'],result['wrong_items']),('教师参考：B','correct',0))

    def test_other_question_or_paper_keeps_legal_ai_and_teacher_text_still_compares(self):
        question=CHOICE+'\n虚构甲卷第2题：3+3=? A.5 B.6 C.7\n实际作答：B\n虚构乙卷第1题：1+1=? A.2 B.3\n实际作答：B'
        items=[choice(),choice(label='虚构甲卷第2题',question='3+3=? A.5 B.6 C.7',answer='AI自行推导：B',judgment='correct',error_reason='',steps=''),
               choice(label='虚构乙卷第1题',question='1+1=? A.2 B.3',answer='AI自行推导：A',error_reason='作答B与推导A不同。')]
        result=self.draft(items,question=question)
        self.assertEqual([q['answer'] for q in result['questions']],['教师参考：B','AI自行推导：B','AI自行推导：A'])
        self.assertEqual([q['judgment'] for q in result['questions']],['correct','correct','incorrect'])
        self.assertEqual((result['wrong_items'],result['unknown_items']),(1,0))
        self.assertIn('有限写法',result['text'])

    def test_conflicting_or_unmatched_teacher_text_stays_pending_without_ai_answer(self):
        result=self.draft([choice()],teacher=TEACHER_B+'\n虚构甲卷 第1题：教师参考C');q=result['questions'][0]
        self.assertEqual(q['judgment'],'unknown');self.assertNotIn('AI自行推导',q['answer'])
        self.assertIn('B',q['uncertainty']);self.assertIn('C',q['uncertainty'])
        result=self.draft([choice(label='第1题')]);q=result['questions'][0]
        self.assertEqual((q['answer'],q['judgment']),('','unknown'));self.assertIn('卷别',q['uncertainty'])
        self.assertEqual((result['wrong_items'],result['unknown_items']),(0,1))

    def test_answer_only_teacher_text_is_not_widened_into_free_text_grading(self):
        question='虚构甲卷第2题：一根绳子长12米，剪去5米，还剩几米？\n实际作答：8米'
        item=choice(label='虚构甲卷第2题',question='一根绳子长12米，剪去5米，还剩几米？',student_answer='8米',answer='AI自行推导：8米',
                    judgment='correct',error_reason='',steps='')
        result=self.draft([item],teacher='虚构甲卷 第2题：教师参考7米',question=question);q=result['questions'][0]
        self.assertEqual((q['answer'],q['judgment'],result['wrong_items']),('教师参考：7米','unknown',0))
        result=self.draft([item|dict(student_answer='7米',answer='AI自行推导：7米')],teacher='虚构甲卷 第2题：教师参考7米',question=question)
        self.assertEqual((result['questions'][0]['answer'],result['questions'][0]['judgment']),('教师参考：7米','correct'))


class TextQuestionContractTests(unittest.TestCase):
    def test_text_teacher_claim_requires_teacher_original(self):
        previous=[{},dict(previous_text='虚构旧意见：教师参考为5。'),
                  dict(previous_documents=[dict(name='synthetic-previous.txt',text='虚构旧意见：教师参考为5。')])]
        for answer in ('教师参考：5',' \t教师参考:5'):
            for prior in previous:
                with self.subTest(answer=answer,previous=list(prior)):
                    raw=json.loads(json.dumps(RAW));raw['items'][0]['answer']=answer
                    original=json.loads(json.dumps(raw))
                    with patch.object(family_llm,'_chat_json',return_value=raw) as model:
                        with self.assertRaisesRegex(family_llm.LLMDraftError,'未提供.*教师参考'):
                            family_llm.homework_reference_draft([],review=True,
                                question_documents=[dict(name='synthetic-paper.txt',text=QUESTION)],**prior)
                    self.assertEqual(model.call_count,1);self.assertEqual(raw,original)

    def test_image_teacher_claim_keeps_existing_review_and_print_contract(self):
        for review in (False,True):
            with self.subTest(review=review):
                raw=json.loads(json.dumps(RAW))
                if not review:raw['items'][0].pop('question_kind')
                original=json.loads(json.dumps(raw))
                with patch.object(family_llm,'_chat_json',return_value=raw) as model:
                    result=family_llm.homework_reference_draft([dict(mime='image/png',data=PNG)],review=review)
                self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
                self.assertEqual(result['questions'][0]['answer'],'教师参考：5')
                self.assertEqual((result['wrong_items'],result['unknown_items']),(1,0))

    def test_blank_text_answer_keeps_teacher_reference_but_not_model_summary(self):
        raw=json.loads(json.dumps(RAW));q=raw['items'][0]
        q.update(student_answer='',judgment='unknown',error_reason='',uncertainty='答题格空白。')
        raw.update(coverage='第1题正确；作文未提供。',comparison='整卷检查完成。')
        original=json.loads(json.dumps(raw));scope=['题目原文：本次读取synthetic-paper.txt。']
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,
                question_documents=[dict(name='synthetic-paper.txt',text='虚构甲卷第1题：2+3=?\n实际作答：')],
                reference_documents=[dict(name='teacher.txt',text=REFERENCE)],program_coverage=scope)
        self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        self.assertEqual(result['questions'][0]['student_answer'],'');self.assertEqual(result['questions'][0]['answer'],'教师参考：5')
        self.assertEqual((result['wrong_items'],result['unknown_items']),(0,1))
        self.assertEqual(result['unverified_model_summary'],dict(coverage=raw['coverage'],comparison=raw['comparison']))
        for text in (raw['coverage'],raw['comparison']):self.assertNotIn(text,result['text'])
        for text in ('答题格空白。','1题仍未判定',scope[0]):self.assertIn(text,result['text'])

    def test_complete_text_choice_and_reading_use_text_evidence(self):
        documents=[dict(name='synthetic-choice.txt',text='虚构甲卷第1题：2+3=? A.4 B.5 C.6\n实际作答：B'),
                   dict(name='synthetic-reading.docx',text='虚构甲卷第2题：原文“周一小林去了图书馆。” 问：小林何时去图书馆？\n实际作答：周一')]
        raw=json.loads(json.dumps(RAW));raw['items'][0].update(question='2+3=? A.4 B.5 C.6',
            student_answer='B',answer='AI自行推导：B',judgment='correct',error_reason='')
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=documents)
        self.assertEqual(model.call_count,1);self.assertEqual(result['questions'][0]['student_answer'],'B')
        self.assertEqual(result['questions'][0]['answer'],'AI自行推导：B');self.assertEqual((result['wrong_items'],result['unknown_items']),(0,0))
        prompt=model.call_args.args[0][0]['content']
        self.assertNotIn('在这些图片中缺失时',prompt)
        self.assertIn('在本次明确提供的题目/作答原件（图片或文字）中缺失时',prompt)
        self.assertIn('不能从常识猜答案，judgment写unknown',prompt)
        self.assertFalse(any(p['type']=='image_url' for p in model.call_args.args[0][1]['content']))

    def test_only_text_question_is_separate_from_teacher_and_parent_note(self):
        q=dict(name='synthetic-paper.docx',text=QUESTION);r=dict(name='synthetic-teacher.txt',text=REFERENCE)
        raw=json.loads(json.dumps(RAW))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=[q],reference_documents=[r],answer_note='家长猜可能写了5；这不是实际作答。')
        self.assertEqual(model.call_count,1);self.assertEqual(result['questions'][0]['student_answer'],'4');self.assertEqual(result['wrong_items'],1)
        content=model.call_args.args[0][1]['content'];self.assertFalse(any(p['type']=='image_url' for p in content))
        qtext=[p['text'] for p in content if p.get('text','').startswith('题目/孩子作答原文')]
        teacher=[p['text'] for p in content if p.get('text','').startswith('教师参考原文')]
        self.assertEqual(len(qtext),1);self.assertIn(QUESTION.replace('\n','\\n'),qtext[0]);self.assertNotIn(REFERENCE,qtext[0])
        self.assertEqual(len(teacher),1);self.assertIn(REFERENCE,teacher[0]);self.assertNotIn(QUESTION.replace('\n','\\n'),teacher[0])
        self.assertEqual(raw,RAW)

    def test_missing_question_and_invalid_text_refuse_before_transport(self):
        invalid=[[],None,'text',[dict(name='synthetic.txt',text='')],[dict(name='synthetic.txt',text='bad\x00')],
                 [dict(name='synthetic.txt',text='x'*12001)],[dict(name='n'*201,text='Q1')],
                 [dict(name='synthetic.txt',text='Q1',extra='unexpected')]]
        for documents in invalid:
            with self.subTest(documents=documents),patch.object(family_llm,'_chat_json') as model:
                with self.assertRaises(ValueError):family_llm.homework_reference_draft([],review=True,question_documents=documents,reference_documents=[dict(name='teacher.txt',text=REFERENCE)])
                model.assert_not_called()
        with patch.object(family_llm,'_chat_json') as model:
            with self.assertRaises(ValueError):family_llm.homework_reference_draft([],review=False,question_documents=[dict(name='paper.txt',text=QUESTION)])
            with self.assertRaises(ValueError):family_llm.homework_reference_draft([],review=True,question_documents=[dict(name='paper.txt',text='q'*6001)],reference_documents=[dict(name='teacher.txt',text='a'*6000)])
            model.assert_not_called()


class TextQuestionHTTPTests(HomeworkPrintScopeTests):
    def review_request(self,questions,teachers):
        key='synthetic-text-original-'+hashlib.sha256(json.dumps([questions,teachers]).encode()).hexdigest()
        original=self.feedback(self.task,questions+teachers,key)
        return dict(purpose='review',task_id=self.task['id'],record_id=original['record_id'],expected_created=original['feedback']['created'],question_sources=[self.source(i) for i in questions],reference_sources=[self.source(i) for i in teachers])

    def test_txt_and_safe_word_are_question_originals_with_zero_images(self):
        teacher=self.upload('synthetic-teacher.txt',REFERENCE.encode())
        for name,body in [('synthetic-paper.txt',QUESTION.encode()),('synthetic-paper.docx',docx(QUESTION))]:
            with self.subTest(name=name):
                paper=self.upload(name,body);request=self.review_request([paper],[teacher]);before=self.dump()
                raw=json.loads(json.dumps(RAW))
                with patch.object(family_llm,'_chat_json',return_value=raw) as model:
                    status,out=self.request('POST','/api/print/homework/draft',request)
                self.assertEqual(status,200,out);self.assertEqual(model.call_count,1);self.assertEqual(raw,RAW)
                self.assertEqual(out['draft']['wrong_items'],1);self.assertIn('题目/孩子作答《'+name+'》',out['draft']['text']);self.assertIn('本次读取完整文字',out['draft']['text'])
                self.assertEqual(out['review_basis']['question_sources'],[self.source(paper)])
                self.assertEqual(out['review_basis']['reference_sources'],[self.source(teacher)])
                self.assertEqual(self.dump(),before)

    def test_teacher_choice_beats_frozen_ai_source_through_save_retry_and_reopen(self):
        paper=self.upload('synthetic-choice.txt',CHOICE.encode());teacher=self.upload('synthetic-choice-teacher.txt',TEACHER_B.encode())
        request=self.review_request([paper],[teacher])
        raw=dict(question_labels=['虚构甲卷第1题'],items=[choice()],coverage='虚构冻结回执。');original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            status,out=self.request('POST','/api/print/homework/draft',request)
        self.assertEqual(status,200,out);self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        d=out['draft'];self.assertEqual((d['wrong_items'],d['unknown_items']),(0,0))
        self.assertEqual(d['questions'][0]['answer'],'教师参考：B');self.assertEqual(d['continuation']['pending_labels'],[])
        result=self.upload('作业批改参考-%d.txt'%request['record_id'],d['text'].encode())
        feedback=dict(task_id=self.task['id'],child=self.task['child'],day='2026-10-01',request_key='synthetic-teacher-priority-save',
                      note='虚构家长核对的检查。',attachments=[paper,teacher,result],review_basis=out['review_basis'])
        with patch.object(family_llm,'_chat_json') as model:
            status,saved=self.request('POST','/api/task/feedback',feedback);self.assertEqual(status,200,saved)
            status,retry=self.request('POST','/api/task/feedback',feedback);self.assertEqual(status,200,retry)
            self.assertTrue(retry['replayed']);self.assertEqual(retry['record_id'],saved['record_id'])
            status,view=self.request('GET','/api/print/homework/saved-review?task_id=%s&record_id=%d'%(self.task['id'],saved['record_id']))
            self.assertEqual(status,200,view);model.assert_not_called()
        self.assertEqual(view['text'],d['text']);self.assertIn('需订正0题',view['text']);self.assertNotIn('AI自行推导：C',view['text'])

    def test_complex_word_and_missing_scope_still_refuse_before_model(self):
        teacher=self.upload('synthetic-teacher.txt',REFERENCE.encode())
        unsafe=[docx(QUESTION,extra=[('word/media/synthetic.png',b'not-read')]),
                docx(QUESTION,content='<w:p><m:oMath><m:r><m:t>2+3</m:t></m:r></m:oMath></w:p>'),
                docx(QUESTION,extra=[('word/_rels/document.xml.rels','<Relationships><Relationship TargetMode="External" Target="https://example.invalid/synthetic"/></Relationships>')])]
        for n,body in enumerate(unsafe):
            paper=self.upload('synthetic-unsafe-'+str(n)+'.docx',body);request=self.review_request([paper],[teacher]);before=self.dump()
            with patch.object(family_llm,'_chat_json') as model:
                status,out=self.request('POST','/api/print/homework/draft',request)
            self.assertGreaterEqual(status,400,out);model.assert_not_called();self.assertEqual(self.dump(),before)
        foreign=self.upload('synthetic-foreign.docx',docx(QUESTION));self.feedback(self.other_child,[foreign],'synthetic-foreign-word')
        request=self.review_request([self.question],[teacher]);request['question_sources']=[self.source(foreign)];before=self.dump()
        with patch.object(family_llm,'_chat_json') as model:
            status,out=self.request('POST','/api/print/homework/draft',request)
        self.assertEqual(status,403,out);model.assert_not_called();self.assertEqual(self.dump(),before)

    def test_word_automatic_question_numbers_refuse_instead_of_disappearing(self):
        teacher=self.upload('synthetic-teacher-number-guard.txt',REFERENCE.encode())
        ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        variants=[docx(QUESTION,content='<w:p><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>2+3=? 实际作答：4</w:t></w:r></w:p>'),
                  docx(QUESTION,extra=[('word/styles.xml','<w:styles xmlns:w="'+ns+'"><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style></w:styles>')]),
                  docx(QUESTION,content='<w:p><w:pPr><w:pStyle w:val="Question"/></w:pPr><w:r><w:t>2+3=? 实际作答：4</w:t></w:r></w:p>',extra=[('word/styles.xml','<w:styles xmlns:w="'+ns+'"><w:style w:styleId="Base"><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style><w:style w:styleId="Question"><w:basedOn w:val="Base"/></w:style></w:styles>')])]
        for n,body in enumerate(variants):
            paper=self.upload('synthetic-numbered-'+str(n)+'.docx',body);request=self.review_request([paper],[teacher]);before=self.dump()
            with patch.object(family_llm,'_chat_json',return_value=json.loads(json.dumps(RAW))) as model:
                status,out=self.request('POST','/api/print/homework/draft',request)
            self.assertEqual(status,400,out);model.assert_not_called();self.assertEqual(self.dump(),before)
            request=self.review_request([self.question],[paper]);before=self.dump()
            with patch.object(family_llm,'_chat_json',return_value=json.loads(json.dumps(RAW))) as model:
                status,out=self.request('POST','/api/print/homework/draft',request)
            self.assertEqual(status,400,out);model.assert_not_called();self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main(defaultTest=['TextQuestionContractTests','TeacherReferencePriorityTests','TextQuestionHTTPTests'])

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
from test_homework_print_scope import HomeworkPrintScopeTests


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


class TextQuestionContractTests(unittest.TestCase):
    def test_complete_text_choice_and_reading_use_text_evidence(self):
        documents=[dict(name='synthetic-choice.txt',text='虚构甲卷第1题：2+3=? A.4 B.5 C.6\n实际作答：B'),
                   dict(name='synthetic-reading.docx',text='虚构甲卷第2题：原文“周一小林去了图书馆。” 问：小林何时去图书馆？\n实际作答：周一')]
        with patch.object(family_llm,'_chat_json',return_value=json.loads(json.dumps(RAW))) as model:
            family_llm.homework_reference_draft([],review=True,question_documents=documents)
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


if __name__=='__main__':unittest.main(defaultTest=['TextQuestionContractTests','TextQuestionHTTPTests'])

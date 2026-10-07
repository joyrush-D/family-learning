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


def frozen(*items):
    return dict(question_labels=[i['label'] for i in items],items=list(items),coverage='只核本次虚构原件内明确的卷别与题号。')


def objective(label,question,student,answer,judgment='correct',**changes):
    return dict(label=label,question=question,student_answer=student,answer=answer,judgment=judgment,question_kind='objective',
                error_reason='',possible_cause='',steps='',uncertainty='')|changes


class TeacherReferenceIdentityTests(unittest.TestCase):
    """Independent review cases: a named paper's teacher answer is never lent to another paper or misquoted."""
    def run_case(self,questions,references,raw):
        original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=[dict(name=n,text=t) for n,t in questions],
                reference_documents=[dict(name=n,text=t) for n,t in references])
        self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        return result

    def test_named_papers_without_letter_names_keep_their_own_source(self):
        dipper=objective('虚构北斗卷第12题','5×5等于多少？A.20 B.21 C.24 D.26 E.25 F.30 G.35 H.15。','E','教师参考：E')
        south=objective('虚构南风卷第12题','3+3等于多少？A.3 B.4 C.5 D.6 E.7 F.8 G.9 H.10。','D','AI自行推导：D')
        result=self.run_case([('synthetic-heldout-dipper-q12-answer.txt','虚构北斗卷 第12题：5×5等于多少？A.20 B.21 C.24 D.26 E.25 F.30 G.35 H.15。学生原答：E。'),
                              ('synthetic-heldout-south-q12-answer.txt','虚构南风卷 第12题：3+3等于多少？A.3 B.4 C.5 D.6 E.7 F.8 G.9 H.10。学生原答：D。')],
                             [('synthetic-heldout-dipper-q12-teacher.txt','虚构北斗卷 第12题：教师参考E。')],frozen(dipper,south))
        self.assertEqual([(q['answer'],q['judgment']) for q in result['questions']],[('教师参考：E','correct'),('AI自行推导：D','correct')])
        self.assertEqual((result['wrong_items'],result['unknown_items']),(0,0))
        bridge=objective('虚构星桥卷第19题','9-5等于多少？A.1 B.2 C.3 D.5 E.6 F.7 G.4 H.8。','G','AI自行推导：G')
        result=self.run_case([('synthetic-heldout-bridge-q19-answer.txt','虚构星桥卷 第19题：9-5等于多少？A.1 B.2 C.3 D.5 E.6 F.7 G.4 H.8。学生原答：G。')],
                             [('synthetic-heldout-valley-q19-teacher.txt','虚构溪谷卷 第19题：教师参考H。')],frozen(bridge))
        self.assertEqual([(q['answer'],q['judgment']) for q in result['questions']],[('AI自行推导：G','correct')])
        self.assertEqual((result['wrong_items'],result['unknown_items']),(0,0))

    def test_unrecognized_paper_names_are_isolated_but_one_unnamed_paper_still_compares(self):
        south=objective('虚构南风练习第12题','3+3等于多少？A.5 B.6','B','AI自行推导：B')
        result=self.run_case([('synthetic-south-practice.txt','虚构南风练习第12题：3+3等于多少？A.5 B.6\n实际作答：B')],
                             [('synthetic-dipper-practice-teacher.txt','虚构北斗练习 第12题：教师参考A')],frozen(south))
        q=result['questions'][0];self.assertNotEqual(q['judgment'],'incorrect');self.assertNotIn('A',q['answer'])
        self.assertEqual(result['wrong_items'],0)
        single=objective('第1题','2+3=? A.4 B.5 C.6','B','AI自行推导：C','incorrect',error_reason='作答B与推导C不同。')
        result=self.run_case([('synthetic-single.txt','第1题：2+3=? A.4 B.5 C.6\n实际作答：B')],[('synthetic-single-teacher.txt','第1题：教师参考B')],frozen(single))
        self.assertEqual([(q['answer'],q['judgment']) for q in result['questions']],[('教师参考：B','correct')])

    def test_teacher_label_on_a_different_non_letter_value_is_not_confirmed(self):
        rope=objective('虚构甲卷第2题','一根绳子长12米，剪去5米，还剩几米？','8米','教师参考：8米')
        questions=[('synthetic-rope.txt','虚构甲卷第2题：一根绳子长12米，剪去5米，还剩几米？\n实际作答：8米')]
        teacher=[('synthetic-rope-teacher.txt','虚构甲卷 第2题：教师参考7米')]
        result=self.run_case(questions,teacher,frozen(rope));q=result['questions'][0]
        self.assertEqual((q['answer'],q['judgment'],result['wrong_items'],result['unknown_items']),('教师参考：7米','unknown',0,1))
        self.assertIn('8米',q['uncertainty']);self.assertIn('7米',q['uncertainty'])
        same=rope|dict(student_answer='7米',answer='教师参考：7米')
        result=self.run_case([('synthetic-rope.txt','虚构甲卷第2题：一根绳子长12米，剪去5米，还剩几米？\n实际作答：7米')],teacher,frozen(same))
        self.assertEqual([(q['answer'],q['judgment']) for q in result['questions']],[('教师参考：7米','correct')])


LONG_PREFIX='这是虚构教师参考长答案的共同前缀'*8


class TeacherReferenceScopeTests(unittest.TestCase):
    """Second independent review: sections, new titles, unsure pairing and whole teacher values."""
    def run_case(self,teacher,*items,images=0):
        raw=frozen(*items);original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=[dict(name='synthetic-paper.txt',text='虚构题目与孩子原答。')],
                reference_documents=[dict(name='synthetic-teacher.txt',text=teacher)],reference_images=[dict(mime='image/png',data=PNG)]*images)
        self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        return [(q['answer'],q['judgment']) for q in result['questions']],result

    def test_numbered_section_keeps_its_own_teacher_answer(self):
        got,_=self.run_case('虚构甲卷第1大题第1题B',objective('虚构甲卷第1大题第1题','2+3=? A.4 B.5 C.6','B','教师参考：B'),
                            objective('虚构甲卷第2大题第1题','3+4=? A.6 B.8 C.7','C','AI自行推导：C'))
        self.assertEqual(got,[('教师参考：B','correct'),('AI自行推导：C','correct')])

    def test_new_title_line_does_not_inherit_the_previous_paper(self):
        for title in ('南风卷','南风练习'):
            with self.subTest(title=title):
                got,_=self.run_case('虚构甲卷\n第1题教师B\n%s\n第1题教师C'%title,objective('虚构甲卷第1题','2+3=? A.4 B.5 C.6','B','教师参考：B'),
                                    objective(title+'第1题','1+2=? A.1 B.2 C.3','C','教师参考：C'))
                self.assertEqual(got,[('教师参考：B','correct'),('教师参考：C','correct')])

    def test_teacher_label_cannot_settle_an_unsure_pairing(self):
        got,result=self.run_case('虚构甲卷 第1题：教师参考B',objective('第1题','2+3=? A.4 B.5 C.6','B','教师参考：B'))
        self.assertEqual(got[0][1],'unknown');self.assertIn('卷别',result['questions'][0]['uncertainty'])
        self.assertEqual((result['wrong_items'],result['unknown_items']),(0,1))

    def test_claimed_teacher_value_must_be_the_whole_teacher_text(self):
        rope=objective('虚构甲卷第2题','一根绳子长12米，剪去5米，还剩几米？','8米','教师参考：8米')
        got,result=self.run_case('虚构甲卷 第2题：教师参考7米',rope,images=1)
        self.assertEqual(got,[('教师参考：7米','unknown')]);self.assertIn('8米',result['questions'][0]['uncertainty'])
        got,_=self.run_case('虚构甲卷 第1题：教师参考B',objective('虚构甲卷第1题','2+3=? A.4 B.5 C.6','C','教师参考：选C'))
        self.assertIn(got[0][1],('incorrect','unknown'));self.assertIn('B',got[0][0])
        cut=objective('虚构甲卷第3题','虚构长答案题。','虚构作答','教师参考：'+LONG_PREFIX[:100])
        for teacher in ('虚构甲卷 第3题：%s甲结论\n虚构甲卷 第3题：%s乙结论'%(LONG_PREFIX,LONG_PREFIX),'虚构甲卷 第3题：%s甲结论'%LONG_PREFIX):
            with self.subTest(entries=teacher.count('\n')+1):
                got,result=self.run_case(teacher,cut)
                self.assertEqual(got[0][1],'unknown');self.assertNotEqual(got[0][0],cut['answer'])
                self.assertEqual((result['wrong_items'],result['unknown_items']),(0,1))


class TeacherReferenceSourceTests(unittest.TestCase):
    """Third review: an unpaired or extended "教师参考：" label never proves its own source."""
    def run_case(self,teacher,item):
        raw=frozen(item);original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=[dict(name='synthetic-paper.txt',text='虚构题目与孩子原答。')],
                reference_documents=[dict(name='synthetic-teacher.txt',text=teacher)])
        self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        q=result['questions'][0]
        self.assertEqual((q['student_answer'],q['question']),(item['student_answer'],item['question']))
        return q

    def test_extended_teacher_letter_is_not_the_teacher_value(self):
        for claimed in ('B或C','B（因为2+3=5）'):
            with self.subTest(claimed=claimed):
                q=self.run_case('虚构甲卷 第4题：教师参考B',objective('虚构甲卷第4题','2+3=? A.4 B.5 C.6','C','教师参考：'+claimed))
                self.assertIn(q['judgment'],('incorrect','unknown'));self.assertEqual(q['answer'],'教师参考：B')
        q=self.run_case('虚构甲卷 第4题：教师参考B',objective('虚构甲卷第4题','2+3=? A.4 B.5 C.6','B','教师参考：B（因为2+3=5）'))
        self.assertEqual((q['answer'],q['judgment']),('教师参考：B','correct'))

    def test_title_or_sub_question_gap_cannot_make_a_teacher_source(self):
        for teacher in ('南风练习\n第1题：教师参考B','南风练习 第1题：教师参考B'):
            with self.subTest(teacher=teacher):
                q=self.run_case(teacher,objective('海风练习第1题','1+2=? A.2 B.4 C.3','C','教师参考：C'))
                self.assertEqual(q['judgment'],'unknown');self.assertNotEqual(q['answer'],'教师参考：C')
                q=self.run_case(teacher,objective('南风练习第1题','2+3=? A.4 B.5 C.6','B','教师参考：B'))
                self.assertEqual((q['answer'],q['judgment']),('教师参考：B','correct'))
                q=self.run_case(teacher,objective('南风练习第1题','2+3=? A.4 B.5 C.6','C','教师参考：C'))
                self.assertIn(q['judgment'],('incorrect','unknown'));self.assertNotEqual(q['answer'],'教师参考：C')
        q=self.run_case('虚构甲卷 第1题（1）：教师参考B',objective('虚构甲卷第1题','1+2=? A.2 B.4 C.3','C','教师参考：C'))
        self.assertEqual(q['judgment'],'unknown');self.assertNotEqual(q['answer'],'教师参考：C')
        q=self.run_case('虚构甲卷 第1题（1）：教师参考B',objective('虚构甲卷第1题（1）','2+3=? A.4 B.5 C.6','B','教师参考：B'))
        self.assertEqual((q['answer'],q['judgment']),('教师参考：B','correct'))

    def test_cover_heading_and_whole_values_keep_paired_results(self):
        q=self.run_case('虚构教师参考答案\n第1题：教师参考B',objective('第1题','2+3=? A.4 B.5 C.6','B','教师参考：B'))
        self.assertEqual((q['answer'],q['judgment']),('教师参考：B','correct'))
        q=self.run_case('虚构甲卷 第5题：教师参考2+3=5',objective('虚构甲卷第5题','写出2+3的算式和结果。','2+3=5','教师参考：2+3=5'))
        self.assertEqual((q['answer'],q['judgment']),('教师参考：2+3=5','correct'))
        whole=LONG_PREFIX+'甲结论'
        q=self.run_case('虚构甲卷 第6题：'+whole,objective('虚构甲卷第6题','虚构长答案题。',whole,'教师参考：'+whole))
        self.assertEqual((q['answer'],q['judgment']),('教师参考：'+whole,'correct'))


class TeacherReferenceEquationTests(TeacherReferenceSourceTests):
    """A teacher's bare equation and its one final value are the same teacher value; alternatives or added demands are not."""
    test_extended_teacher_letter_is_not_the_teacher_value=test_title_or_sub_question_gap_cannot_make_a_teacher_source=None
    test_cover_heading_and_whole_values_keep_paired_results=None

    def case(self,n,teacher,student,claimed,judgment,**changes):
        return self.run_case('虚构甲卷第%d题：%s'%(n,teacher),objective('虚构甲卷第%d题'%n,'2+3=?',student,'教师参考：'+claimed,judgment,**changes))

    def test_equation_final_value_and_same_value_expression_agree(self):
        q=self.case(1,'2+3=5。','4','5','incorrect',error_reason='作答4与教师参考5不同。')
        self.assertIn((q['answer'],q['judgment']),[('教师参考：5','incorrect'),('教师参考：2+3=5','incorrect')])
        q=self.case(2,'2+3=5','5','5','correct')
        self.assertIn((q['answer'],q['judgment']),[('教师参考：5','correct'),('教师参考：2+3=5','correct')])
        q=self.case(3,'5','5','2+3=5','correct')
        self.assertIn((q['answer'],q['judgment']),[('教师参考：5','correct'),('教师参考：2+3=5','correct')])

    def test_other_final_value_alternatives_or_added_demands_stay_the_teachers(self):
        q=self.case(4,'2+3=5','6','2+3=6','correct')
        self.assertIn((q['answer'],q['judgment']),[('教师参考：2+3=5','unknown'),('教师参考：5','unknown'),('教师参考：2+3=5','incorrect'),('教师参考：5','incorrect')])
        q=self.case(5,'5或6','5','5','correct')
        self.assertEqual((q['answer'],q['judgment']),('教师参考：5或6','unknown'))
        demand='5，并且必须说明把两组数量合并后得到总数的理由'
        q=self.case(6,demand,'5','5','correct')
        self.assertIn((q['answer'],q['judgment']),[('教师参考：'+demand,'unknown'),('教师参考：'+demand,'incorrect')])


LONG_TEACHER='TEACHER_ONLY_CANARY\n虚构甲卷\n第一大题\n第1题：6个零件。应写出2×3=6，并说明2表示每轮处理的零件数、3表示已经完成的轮数，乘法表示三轮相同工作量的合计；结果单位是“个零件”，不能只写一个数字而让读者猜测量的含义。还要解释只有每轮确实完成2个零件时才可以使用该式，若其中一轮只完成1个，实际总数为5个零件，应把2、2、1逐轮相加，不能继续把计划的三轮都当作已经完成。答题时须把总数、单位、列式、各量意义和条件说明五项分别交代清楚，让老师能从原作答核对计算与推理是否相符。单独写“6”只能核对到计划总数这一部分，不足以证明其余要求已经回答；是否满足完整作答须依据原题与学生完整文字，不得把参考说明补成学生已经写出的理由'
LONG_QUESTION='一台机器每轮处理2个零件，连续完成3轮，共处理多少？请给出总数、单位、列式，解释各数字表示的量，并说明若一轮只完成1个零件时为什么不能继续使用完整三轮的结果。五项要求都须回答。'


class TeacherReferenceGrammarTests(unittest.TestCase):
    """Fourth review: letters and chains are not equations, bare numbers and sections pair by text, original-reference
    headers are source words, and a long teacher answer survives whole."""
    def run_case(self,questions,teacher,item):
        raw=frozen(item);original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=[dict(name='synthetic-paper.txt',text=questions)],
                reference_documents=[dict(name='synthetic-teacher.txt',text=teacher)])
        self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        q=result['questions'][0];self.assertEqual(q['student_answer'],item['student_answer'])
        return (q['answer'],q['judgment']),result

    def test_letter_or_chained_claim_is_not_a_teacher_equation(self):
        got,_=self.run_case('虚构甲卷第21题：请选择正确选项（A/B/C/D）。 实际作答C。','虚构甲卷第21题：B。',
                            objective('虚构甲卷第21题','请选择正确选项（A/B/C/D）。','C','教师参考：C=B'))
        self.assertIn(got,[('教师参考：B','incorrect'),('教师参考：B','unknown')])
        got,_=self.run_case('虚构甲卷第22题：请填写教师已明确给出的本题结果。 实际作答6。','虚构甲卷第22题：6。',
                            objective('虚构甲卷第22题','请填写教师已明确给出的本题结果。','6','教师参考：2+3=5=6'))
        self.assertIn(got,[('教师参考：6','unknown'),('教师参考：6','correct')])
        got,_=self.run_case('虚构甲卷第1题：2+3=?\n实际作答：4','虚构甲卷第1题：2+3=5',objective('虚构甲卷第1题','2+3=?','4','教师参考：5','incorrect',error_reason='作答4与教师参考5不同。'))
        self.assertIn(got,[('教师参考：5','incorrect'),('教师参考：2+3=5','incorrect')])
        got,_=self.run_case('虚构甲卷第3题：2+3=?\n实际作答：5','虚构甲卷第3题：5',objective('虚构甲卷第3题','2+3=?','5','教师参考：2+3=5'))
        self.assertIn(got,[('教师参考：5','correct'),('教师参考：2+3=5','correct')])

    def test_bare_numbers_and_sections_pair_only_by_teacher_text(self):
        two='一、计算\n1. 36+47=? 作答83\n二、计算\n1. 30+17=? 作答47'
        cases=[('1. 36+47=? 作答83','1. 83',objective('1','36+47=?','83','教师参考：83'),[('教师参考：83','correct')]),
               ('1. 36+47=? 作答82','1. 83',objective('1','36+47=?','82','教师参考：83','incorrect',error_reason='作答82与教师参考83不同。'),[('教师参考：83','incorrect')]),
               ('一、计算\n1. 36+47=? 作答83','一、计算\n1. 83',objective('一、1','36+47=?','83','教师参考：83'),[('教师参考：83','correct')]),
               (two,'一、计算\n1. 83',objective('二、1','30+17=?','47','AI自行推导：47'),[('AI自行推导：47','correct')]),
               (two,'一、计算\n1. 83',objective('二、1','30+17=?','47','教师参考：47'),[('','unknown'),('AI自行推导：47','correct')]),
               ('虚构乙卷\n1. 30+17=? 作答47','虚构甲卷\n1. 83',objective('虚构乙卷1','30+17=?','47','教师参考：47'),[('','unknown'),('AI自行推导：47','correct')])]
        for n,(questions,teacher,item,allowed) in enumerate(cases,1):
            with self.subTest(case='B0%d'%n):
                got,_=self.run_case(questions,teacher,item);self.assertIn(got,allowed)

    def test_teacher_original_reference_header_is_a_source_word(self):
        item=objective('虚构身份甲卷第1题','虚构身份甲卷第1题：2+3=?','4','教师参考：5','incorrect',error_reason='卷面作答4与核对答案5不同。',
                       steps='先独立重算2+3，再对照核对答案。')
        got,result=self.run_case('虚构身份甲卷第1题：2+3=? 实际作答4','虚构身份甲卷第1题教师原参考：2+3=5。',item)
        self.assertEqual(got,('教师参考：5','incorrect'));self.assertEqual((result['wrong_items'],result['unknown_items']),(1,0))

    def test_long_teacher_answer_is_kept_whole_and_the_short_claim_stays_pending(self):
        teacher=LONG_TEACHER.split('第1题：',1)[1]
        item=objective('虚构甲卷第一大题第1题',LONG_QUESTION,'6','教师参考：6',question_kind='subjective')
        got,result=self.run_case('虚构甲卷\n第一大题\n第1题：'+LONG_QUESTION+'\n孩子最终作答：6',LONG_TEACHER,item)
        self.assertEqual(got,('教师参考：'+teacher,'unknown'));self.assertEqual(len(teacher),286)
        self.assertIn('参考答案：教师参考：'+teacher,result['text']);self.assertEqual(result['questions'][0]['student_answer'],'6')
        self.assertEqual((result['wrong_items'],result['unknown_items']),(0,1))


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


class TeacherPaperWholeNameTest(unittest.TestCase):
    """Fictional S01-S04 and L01: two explicit papers are one paper only when their whole names are equal."""

    def compare(self,label,teacher):
        from family_llm import _prefer_teacher_reference,_ref_relation,_teacher_reference_entries
        entries=_teacher_reference_entries([dict(name='synthetic-teacher.txt',text=teacher)])
        item=dict(label=label,question='1+2=? A.1 B.2 C.3',student_answer='C',answer='AI自行推导：C',judgment='correct',
                  question_kind='objective',error_reason='',possible_cause='',steps='',uncertainty='')
        relations=[_ref_relation(label,entry) for entry in entries]
        _prefer_teacher_reference(item,'objective',entries,False)
        return relations,item['answer'],item['judgment']

    def test_a_paper_name_ending_with_another_or_sharing_a_long_tail_is_another_paper(self):
        long='实验练习资料基础数学测验甲卷'
        for label,teacher in (('青树北窗卷 第1题','北窗卷 第1题：教师参考B'),('北窗卷 第1题','青树北窗卷 第1题：教师参考B'),
                              ('青树卷 第1题','北窗卷 第1题：教师参考B'),('青树%s 第1题'%long,'北窗%s 第1题：教师参考B'%long)):
            with self.subTest(label=label,teacher=teacher):
                self.assertEqual(self.compare(label,teacher),(['other'],'AI自行推导：C','correct'))

    def test_the_same_whole_paper_name_still_takes_the_teacher_answer(self):
        for paper in ('北窗卷','北窗实验练习资料基础数学测验甲卷'):
            with self.subTest(paper=paper):
                self.assertEqual(self.compare(paper+' 第1题',paper+' 第1题：教师参考B'),(['same'],'教师参考：B','incorrect'))

    def test_a_paper_name_too_long_to_read_whole_is_never_cut_to_a_shared_tail(self):
        long='实验练习资料基础数学测验'*3+'甲卷'
        relations,answer,judgment=self.compare('青树%s 第1题'%long,'北窗%s 第1题：教师参考B'%long)
        self.assertNotIn('same',relations);self.assertIn(judgment,('correct','unknown'));self.assertNotEqual(answer,'教师参考：B')


class TeacherPaperFormalNameTest(unittest.TestCase):
    """Fictional D01-D03 and S04: a formal paper name is read whole; a source word, 试/考/答 or connector in it is never cut off."""

    def review(self,question,teacher,label,ask='1+2=? A.1 B.2 C.3'):
        raw=frozen(objective(label,ask,'C','AI自行推导：C'));original=json.loads(json.dumps(raw))
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            result=family_llm.homework_reference_draft([],review=True,question_documents=[dict(name='synthetic-explicit-name-question.txt',text=question)],
                reference_documents=[dict(name='synthetic-explicit-name-teacher.txt',text=teacher)])
        self.assertEqual(model.call_count,1);self.assertEqual(raw,original)
        return [(q['answer'],q['judgment']) for q in result['questions']],result['wrong_items']

    def named(self,paper,teacher):
        return self.review('试卷名称：%s\n第1题：1+2=? A.1 B.2 C.3\n学生原答：C。'%paper,'试卷名称：%s\n第1题：教师参考B。'%teacher,paper+' 第1题')

    def test_a_source_word_or_connector_inside_a_formal_name_is_never_cut_off(self):
        for paper,teacher in (('老师青树卷','青树卷'),('青树卷','老师青树卷'),('参考北窗卷','北窗卷'),
                              ('教师青树卷','青树卷'),('青树卷','参考答案青树卷'),('青树卷','青树试卷'),('平卷','和平卷')):
            with self.subTest(paper=paper,teacher=teacher):
                self.assertEqual(self.named(paper,teacher),([('AI自行推导：C','correct')],0))

    def test_the_same_whole_formal_name_still_takes_the_teacher_answer(self):
        self.assertEqual(self.review('北窗卷 第1题：1+1=? A.1 B.2 C.3\n学生原答：C','北窗卷 第1题：教师参考B','北窗卷 第1题','1+1=? A.1 B.2 C.3'),
                         ([('教师参考：B','incorrect')],1))
        for paper in ('北窗卷','老师青树卷','参考北窗卷','和平卷','青树试卷'):
            with self.subTest(paper=paper):
                self.assertEqual(self.named(paper,paper),([('教师参考：B','incorrect')],1))

    def test_a_separated_source_word_cover_heading_or_paper_list_still_pairs(self):
        from family_llm import _ref_relation,_teacher_reference_entries
        for label,teacher,relations in (('青树卷 第1题','教师参考：青树卷\n第1题：B',['same']),('第1题','教师参考答卷\n第1题：教师参考B',['same']),
                                        ('乙卷 第1题','甲卷 与乙卷第1题均为B',['other','same']),('和平卷 第1题','甲卷和平卷第1题均为B',['other','other'])):
            with self.subTest(label=label,teacher=teacher):
                entries=_teacher_reference_entries([dict(name='synthetic-teacher.txt',text=teacher)])
                self.assertEqual(([_ref_relation(label,entry) for entry in entries],[entry['answer'] for entry in entries]),(relations,['B']*len(relations)))


    def test_a_title_declared_whole_stays_one_paper_even_with_a_join_inside(self):
        # Fictional E01-E03: each original declares one whole title after 「试卷名称：」; 甲卷和平卷 is not 甲卷 and 平卷.
        for paper,teacher,ask,expected in (('甲卷和平卷','平卷','1+2=? A.1 B.2 C.3',([('AI自行推导：C','correct')],0)),
                                           ('平卷','甲卷和平卷','1+2=? A.1 B.2 C.3',([('AI自行推导：C','correct')],0)),
                                           ('甲卷和平卷','甲卷和平卷','1+1=? A.1 B.2 C.3',([('教师参考：B','incorrect')],1))):
            with self.subTest(paper=paper,teacher=teacher):
                self.assertEqual(self.review('试卷名称：%s\n第1题：%s\n学生原答：C。'%(paper,ask),'试卷名称：%s\n第1题：教师参考B。'%teacher,
                                             paper+'第1题',ask),expected)

    def test_an_undeclared_unmarked_join_never_lends_its_teacher_answer(self):
        for teacher in ('甲卷和平卷\n第1题：教师参考B。','甲卷和平卷第1题：教师参考B。'):
            with self.subTest(teacher=teacher):
                got,wrong=self.review('试卷名称：平卷\n第1题：1+2=? A.1 B.2 C.3\n学生原答：C。',teacher,'平卷第1题')
                self.assertEqual(wrong,0);self.assertIn(got[0][1],('correct','unknown'));self.assertNotEqual(got[0][0],'教师参考：B')


if __name__=='__main__':unittest.main(defaultTest=['TextQuestionContractTests','TeacherReferencePriorityTests','TeacherReferenceIdentityTests','TeacherReferenceScopeTests','TeacherReferenceSourceTests','TeacherReferenceEquationTests','TeacherReferenceGrammarTests','TextQuestionHTTPTests','TeacherPaperWholeNameTest','TeacherPaperFormalNameTest'])

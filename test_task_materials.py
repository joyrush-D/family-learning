"""Synthetic read-only material listing for any same-child task and the PDF page-group card; no model, render or service."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app
from test_print_http import PRINTER
import test_homework_print_scope as scope  # module import: its own tests are not collected twice here

HomeworkPrintScopeTests=scope.HomeworkPrintScopeTests

PDF='application/pdf'


class TaskMaterialListingTests(unittest.TestCase):
    setUp=HomeworkPrintScopeTests.setUp
    tearDown=HomeworkPrintScopeTests.tearDown
    new_task=HomeworkPrintScopeTests.new_task
    upload=HomeworkPrintScopeTests.upload
    feedback=HomeworkPrintScopeTests.feedback
    request=HomeworkPrintScopeTests.request
    materials=HomeworkPrintScopeTests.materials
    dump=HomeworkPrintScopeTests.dump

    def todo(self,child,key):
        return app.new_task(dict(child=child,title='虚构签字通知 '+key,category='todo',request_key=key))

    def test_a_notice_lists_its_own_originals_read_only_and_keeps_the_homework_gates(self):
        notice=self.todo('示例甲','synthetic-notice');form=self.upload('synthetic-form.png')
        self.feedback(notice,[form],'synthetic-notice-photo')
        other=self.todo('示例乙','synthetic-other-notice');foreign=self.upload('synthetic-other-form.png')
        self.feedback(other,[foreign],'synthetic-other-notice-photo')
        before=self.dump()
        status,value=self.materials(notice)
        self.assertEqual(status,200,value)
        self.assertEqual((value['category'],value['print_basis'],value['task']['child']),('todo',None,'示例甲'))
        self.assertEqual([(f['source']['id'],f['origin'],f['state']) for f in value['files']],[(form,'same_task','saved')])
        status,value=self.materials(other)
        self.assertEqual((status,[f['source']['id'] for f in value['files']],value['task']['child']),(200,[foreign],'示例乙'))
        # Printing and the parent reference keep the homework-only gate: a notice is never made homework.
        status,value=self.request('POST','/api/print/homework',dict(task_id=notice['id'],request_key='synthetic-notice-print',
                                  question_sources=[self.source(form)],question_confirmed=True,printer=PRINTER['name'],confirmed_basis={}))
        self.assertEqual((status,value.get('code')),(403,'review_source_not_allowed'),value)
        with app.connect_read_only() as c:
            with self.assertRaises(app.family_print.PrintError) as refused: app.homework_material_context(c,notice['id'])
        self.assertEqual(refused.exception.status if hasattr(refused.exception,'status') else 403,403)
        self.assertEqual(self.dump(),before)  # listing writes nothing

    def test_an_oral_item_without_attachment_shows_no_invented_original(self):
        oral=self.todo('示例甲','synthetic-oral-item')
        status,value=self.materials(oral)
        self.assertEqual((status,value['files'],value['school_error']),(200,[],''))
        status,value=self.request('GET','/api/print/homework/materials?task_id=missing-task')
        self.assertEqual(status,404)

    source=staticmethod(HomeworkPrintScopeTests.source)


def document(**extra):
    note=dict(upload_id='u-pdf',title='虚构春游通知',note='周五带水壶，签回执。',uncertainties=['听力音频未随附','第2页表格模糊'],
              requirements=['签回执','听录音'],uncertainty_scopes=[dict(uncertainty='听力音频未随附',requirements=['听录音'],kind='resource')])
    return dict(dict(state='ready',upload_id='u-pdf',page_count=2,processed_pages=[1,2],pending_pages=[],complete=True,requirements_complete=True,
                     batches=[dict(pages=[1,2],draft=dict(originals=[note]),updated='2026-11-02T08:00:00+08:00')],explanation=''),**extra)


class PdfMaterialCardTests(unittest.TestCase):
    def test_a_fully_read_pdf_shows_its_pages_and_keeps_resources_apart_from_unclear_reading(self):
        state=app.pdf_material_state(document())
        self.assertEqual((state['state'],state['label'],state['scope']),('partial','已整理全部2页，有看不清的地方','共2页，已整理第1–2页'))
        self.assertEqual((state['unclear'],state['missing'],state['summary']),(['第2页表格模糊'],['听力音频未随附'],'周五带水壶，签回执。'))
        clear=document();clear['batches'][0]['draft']['originals'][0]['uncertainties']=['听力音频未随附']
        self.assertEqual((app.pdf_material_state(clear)['state'],app.pdf_material_state(clear)['label']),('ready','已整理全部2页'))

    def test_a_partial_pending_failed_or_unstructured_pdf_never_claims_the_whole_original(self):
        part=app.pdf_material_state(document(state='pending',page_count=5,processed_pages=[1,2,3],pending_pages=[4,5],complete=False,
                                             requirements_complete=False,explanation='逐批整理'))
        self.assertEqual((part['state'],part['label'],part['scope'],part['explanation']),('partial','已整理3/5页','共5页，已整理第1–3页，第4–5页未整理','逐批整理'))
        waiting=app.pdf_material_state(document(state='pending',page_count=None,processed_pages=[],pending_pages=[],complete=False,batches=[],requirements_complete=False))
        self.assertEqual((waiting['state'],waiting['label'],waiting['scope'],waiting['summary']),('pending','等待后台整理','尚未整理任何页',''))
        failed=app.pdf_material_state(document(state='error',page_count=4,processed_pages=[1,2],pending_pages=[3,4],complete=False,requirements_complete=False))
        self.assertEqual((failed['state'],failed['scope']),('error','共4页，已整理第1–2页，第3–4页未整理'))
        unstructured=app.pdf_material_state(document(requirements_complete=False))
        self.assertEqual((unstructured['state'],unstructured['label']),('partial','已读全部2页，行动要求待整理'))
        self.assertEqual(app.material_page_words([1,2,3,5,7,8]),'1–3、5、7–8')

    def test_states_prefer_the_page_groups_for_a_page_original_and_the_draft_for_an_image(self):
        context=dict(school=[(dict(id='s'),dict(id='m'),['u-pdf','u-img'])],allowed={'u-pdf':dict(mime=PDF),'u-img':dict(mime='image/png')})
        draft=dict(state='ready',draft=dict(originals=[dict(upload_id='u-img',title='虚构图片',note='图片提要',uncertainties=[])]),upload_ids=['u-img','u-pdf'])
        with patch.object(app,'agent_store',return_value=SimpleNamespace()), patch('family_media.draft_view',return_value=draft), \
             patch('family_pdf_material.view',return_value=document()):
            states=app.homework_material_states(None,context)
        self.assertEqual((states['u-pdf']['scope'],states['u-img']['label'],states['u-img']['summary']),('共2页，已整理第1–2页','已整理','图片提要'))
        refused=dict(state='unavailable',explanation='PDF原件与图片或其他格式原件混在同一条通知，本次未整理。')
        with patch.object(app,'agent_store',return_value=SimpleNamespace()), patch('family_media.draft_view',return_value=draft), \
             patch('family_pdf_material.view',return_value=refused):
            states=app.homework_material_states(None,context)
        self.assertEqual((states['u-pdf']['state'],states['u-pdf']['explanation']),('unread',refused['explanation']))
        self.assertEqual(states['u-img']['label'],'已整理')
        with patch.object(app,'agent_store',return_value=SimpleNamespace()), patch('family_media.draft_view',side_effect=RuntimeError), \
             patch('family_pdf_material.view',side_effect=RuntimeError):
            states=app.homework_material_states(None,context)
        self.assertEqual({k:v['label'] for k,v in states.items()},{'u-pdf':'原件已保存','u-img':'原件已保存'})


del HomeworkPrintScopeTests  # reused methods only; the scope suite runs in its own module


if __name__ == '__main__':
    unittest.main()

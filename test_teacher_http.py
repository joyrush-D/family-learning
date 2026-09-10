"""Parent teacher APIs and evidence lookup on the existing synthetic HTTP fixture."""
import datetime as dt
from unittest.mock import patch
import unittest

import app
import test_agent_http as http_checks


class TeacherHTTPTests(http_checks.AgentHTTPTests):
    def test_teacher_parent_api_and_query_scope(self):
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
        status, state, _ = self.request('GET', '/api/teachers')
        self.assertEqual(status, 200); self.assertEqual(state['teachers'], [])
        profile = dict(display_name='虚构老师', subject='语文', child_ids=['child-1'], source_ids=[],
                       public_url='https://school.example/teaching', archived=False, version=0, request_key='synthetic-profile-key')
        status, saved, _ = self.post('/api/teachers/profile', profile)
        self.assertEqual(status, 200, saved); teacher = saved['teacher']
        self.assertEqual(teacher['public_info']['status'], 'pending')
        observation = dict(teacher_id=teacher['id'], day=today, kind='praise', target='household', child_id='child-1',
                           behavior='能说明解题过程', teacher_reason='', parent_note='下次核对具体评价标准',
                           source_id='', message_id='', source_url='', status='active', version=0,
                           request_key='synthetic-observation-key')
        status, saved, _ = self.post('/api/teachers/observation', observation)
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.post('/api/teachers/observation', observation)[1], saved)
        child = self.child_headers('child-1')
        self.assertIn(self.request('GET', '/api/teachers', headers=child)[0], (401, 403))
        for path, value in [('/api/teachers/profile', profile), ('/api/teachers/observation', observation)]:
            self.assertIn(self.post(path, value, child | self.parent)[0], (401, 403))
            self.assertEqual(self.post(path, value, {})[0], 403)
        self.assertEqual(self.request('GET', '/child/api/teachers', headers=self.child_headers('child-1'))[0], 404)
        evidence, coverage = app.teacher_query_evidence('示例星星', '老师今天为什么表扬？')
        self.assertEqual(len(evidence), 1)
        self.assertIn('尚未记录老师明确说的理由', evidence[0]['detail'])
        self.assertIn('家长待核实理解', evidence[0]['detail'])
        self.assertIn('不能从一次表扬推断', coverage)
        self.assertEqual(app.teacher_query_evidence('示例月亮', '这位老师的表扬记录')[0], [])
        with patch.object(app.family_llm, 'answer_question', side_effect=lambda child, question, rows, coverage, **kw:
                          dict(answer='老师明确理由尚未记录。', citation_ids=[rows[0]['id']])):
            answer = app.ask_family(dict(child='示例星星', question='老师为什么表扬？'))
        self.assertEqual(answer['citations'][0]['kind'], 'teacher')
        self.assertEqual(answer['citations'][0]['target_id'], teacher['id'])
        shared = profile | dict(id=teacher['id'], version=1, request_key='synthetic-shared-teacher-key',
            child_ids=['child-1','child-2'], source_ids=[self.source['id']])
        self.assertEqual(self.post('/api/teachers/profile', shared)[0], 200)
        for key, changes in [('source-class', dict(target='class',child_id='',source_id=self.source['id'])),
                             ('ambiguous-class', dict(target='class',child_id='')),
                             ('old-record', dict(day='2020-01-01'))]:
            self.assertEqual(self.post('/api/teachers/observation', observation | changes |
                {'request_key':'synthetic-'+key+'-request'})[0], 200)
        self.assertEqual(app.teacher_query_evidence('示例月亮','老师表扬')[0], [])
        before = None
        with app.connect() as c: before='\n'.join(c.iterdump())
        current = app.teacher_query_evidence('示例星星','今天老师表扬',today,today)[0]
        self.assertEqual(len(current),2)
        self.assertTrue(all(r['day']==today for r in current))
        with app.connect() as c: self.assertEqual('\n'.join(c.iterdump()), before)
        self.model_mock.assert_not_called()


if __name__ == '__main__': unittest.main()

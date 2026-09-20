"""Run python3 test_record_task_link.py. Synthetic household in temporary files; no household services or paid models."""
import datetime as dt
import http.client
import io
import json
import threading
import unittest

import test_goals
from test_goals import goals




class RecordTaskLinkTests(unittest.TestCase):
    """#20: the parent attaches an already saved record to an existing task of the same child."""
    action=test_goals.GoalTests.action;goal=test_goals.GoalTests.goal;reply=test_goals.GoalTests.reply;evaluate=test_goals.GoalTests.evaluate;approve=test_goals.GoalTests.approve;on=test_goals.GoalTests.on
    TASK=test_goals.MediaFeedbackEvidenceTests.TASK;OTHER='M-synthetic-2';SIBLING='M-synthetic-3'
    setUp=test_goals.MediaFeedbackEvidenceTests.setUp;media=test_goals.MediaFeedbackEvidenceTests.media;ctx=test_goals.MediaFeedbackEvidenceTests.ctx

    def dump(self):
        with self.app.connect() as c:return '\n'.join(c.iterdump())

    def row(self,ident):
        with self.app.connect() as c:return dict(c.execute('SELECT * FROM records WHERE id=?',(ident,)).fetchone())

    def revisions(self,ident):
        with self.app.connect() as c:return c.execute('SELECT COUNT(*) FROM revisions WHERE record_id=?',(ident,)).fetchone()[0]

    def saved(self,**obj):
        content=b'synthetic worksheet original';upload=self.app.save_upload(io.BytesIO(content),len(content),'synthetic-sheet.txt')['id']
        body=dict(child='示例甲',day=self.now.date().isoformat(),category='学习进展',subject='英语',title='虚构试卷订正',
                  note='虚构：把 yesterday 写成 yestoday',source='试卷 / 作业核对',attachments=[upload],transcript='虚构转写：订正两处',transcript_state='已核对')
        body.update(obj);return self.app.save_record(body)['record_id'],upload

    def link(self,ident,task,expected=None,child='示例甲'):
        return self.app.link_record_task(dict(record_id=ident,child=child,task_id=task)|({} if expected is None else dict(expected_linked_at=expected)))

    def refused(self,code,status,call):
        before=self.dump()
        with self.assertRaises((self.app.RecordError,self.app.TaskError)) as caught:call()
        self.assertEqual((caught.exception.code,caught.exception.status),(code,status));self.assertEqual(self.dump(),before,'a refusal writes nothing')

    def test_link_keeps_the_record_and_the_task_as_they_were_and_a_repeat_writes_nothing(self):
        ident,upload=self.saved();self.app.save_task(dict(id=self.TASK,status='已完成',note=self.app.TASK_CHECK_NOTE))
        task=next(t for t in self.app.snapshot()['tasks'] if t['id']==self.TASK);before=self.row(ident)
        done=self.link(ident,self.TASK);after=self.row(ident)
        self.assertTrue(done['ok'] and done['changed'] and not done['replayed'])
        self.assertEqual({k for k in after if after[k]!=before[k]},{'linked_task_id','linked_task_at'})
        self.assertEqual((after['id'],after['source'],json.loads(after['attachments']),after['transcript'],after['transcript_state']),(ident,'试卷 / 作业核对',[upload],'虚构转写：订正两处','已核对'))
        self.assertEqual(done['link'],dict(record_id=ident,task_id=self.TASK,child='示例甲',linked_at=after['linked_task_at'],previous_task_id='',previous_linked_at=''))
        self.assertEqual((done['task']['linked_record_ids'],done['task']['feedback_ids'],done['task']['update'],done['task']['history']),([ident],[],task['update'],task['history']))
        self.assertEqual(done['task']['update']['status'],'已完成');self.assertEqual(self.revisions(ident),1)
        state=next(r for r in self.app.snapshot()['records'] if r['id']==ident);self.assertEqual((state['linked_task_id'],state['linked_task_at']),(self.TASK,after['linked_task_at']))
        dump=self.dump();again=self.link(ident,self.TASK)
        self.assertTrue(again['replayed'] and not again['changed']);self.assertEqual(again['link']['linked_at'],after['linked_task_at']);self.assertEqual(self.dump(),dump)
        # An ordinary content correction keeps the link.
        self.app.save_record(dict(id=ident,child='示例甲',day=before['day'],category='学习进展',subject='英语',title='虚构试卷订正',note='虚构：更正说明',source='试卷 / 作业核对'))
        self.assertEqual((self.row(ident)['linked_task_id'],self.row(ident)['linked_task_at']),(self.TASK,after['linked_task_at']))

    def test_every_change_of_an_existing_link_version_is_compared_and_removal_keeps_the_version(self):
        ident,_=self.saved();first=self.link(ident,self.TASK)['link']['linked_at']
        self.refused('record_task_link_conflict',409,lambda:self.link(ident,self.OTHER))
        self.refused('record_task_link_conflict',409,lambda:self.link(ident,self.OTHER,'2000-01-01T00:00:00'))
        self.refused('record_task_link_conflict',409,lambda:self.link(ident,''))
        gone=self.link(ident,'',first);row=self.row(ident)
        self.assertTrue(gone['changed'] and gone['task'] is None);self.assertEqual(gone['link']['previous_task_id'],self.TASK)
        self.assertEqual(row['linked_task_id'],'');self.assertTrue(row['linked_task_at'] and row['linked_task_at']!=first,'removal keeps a new version, not an empty one')
        self.assertEqual(self.revisions(ident),2)
        # The old first-link request, replayed after the removal, must not hang the record back.
        self.refused('record_task_link_conflict',409,lambda:self.link(ident,self.TASK))
        self.refused('record_task_link_conflict',409,lambda:self.link(ident,self.TASK,first))
        dump=self.dump();self.assertTrue(self.link(ident,'')['replayed']);self.assertEqual(self.dump(),dump)
        back=self.link(ident,self.TASK,row['linked_task_at']);self.assertTrue(back['changed']);self.assertEqual(self.revisions(ident),3)
        self.refused('record_task_link_conflict',409,lambda:self.link(ident,'',first))
        history=self.app.record_history(ident);self.assertEqual(history['current']['linked_task_id'],self.TASK)
        self.assertEqual([p['previous'].get('linked_task_id','') for p in history['history']].count(self.TASK),1)
        # Two corrections from the same version: exactly one wins, the other changes nothing.
        version=back['link']['linked_at'];results=[];gate=threading.Barrier(2)
        def attempt(task):
            gate.wait()
            try:results.append(self.link(ident,task,version)['link']['task_id'])
            except self.app.RecordError as error:results.append(error.code)
        workers=[threading.Thread(target=attempt,args=(task,)) for task in (self.OTHER,'')]
        [w.start() for w in workers];[w.join() for w in workers]
        self.assertEqual(results.count('record_task_link_conflict'),1,results)
        winner=next(r for r in results if r!='record_task_link_conflict');self.assertEqual(self.row(ident)['linked_task_id'],winner);self.assertEqual(self.revisions(ident),4)

    def test_missing_or_other_child_tasks_are_refused_and_a_correction_cannot_move_a_linked_record_to_another_child(self):
        ident,_=self.saved()
        self.refused('task_missing',404,lambda:self.link(ident,'M-synthetic-none'))
        self.refused('record_task_mismatch',409,lambda:self.link(ident,self.SIBLING))
        self.refused('record_task_mismatch',409,lambda:self.link(ident,self.SIBLING,child='示例乙'))
        self.refused('record_task_mismatch',409,lambda:self.link(ident,self.TASK,child='示例乙'))
        self.refused('record_missing',404,lambda:self.link(987654,self.TASK))
        for bad in (dict(record_id=ident,child='示例甲'),dict(record_id=str(ident),child='示例甲',task_id=self.TASK),dict(record_id=ident,child='示例甲',task_id=self.TASK,title='虚构')):
            self.refused('invalid_record',400,lambda bad=bad:self.app.link_record_task(bad))
        feedback=self.media(note='虚构：事项内反馈')['record_id']
        self.refused('record_task_link_source',409,lambda:self.link(feedback,self.OTHER))
        self.link(ident,self.TASK);row=self.row(ident)
        move=dict(id=ident,child='示例乙',day=row['day'],category='学习进展',subject='英语',title='虚构试卷订正',note=row['note'],source=row['source'])
        self.refused('record_task_mismatch',409,lambda:self.app.save_record(move))
        self.assertEqual(self.row(ident)['child'],row['child'])
        # After the parent removes the link, the same correction is an ordinary one again.
        self.link(ident,'',row['linked_task_at']);self.app.save_record(move);self.assertEqual(self.app.child_names()[self.row(ident)['child']],'示例乙')

    def test_link_joins_goal_evidence_and_a_changed_link_stales_the_confirmed_basis_of_that_record_only(self):
        kept=self.media(note='虚构：独立听写错两个');kept_ref='record:%d'%kept['record_id']
        ident,_=self.saved();ref='record:%d'%ident;empty=self.ctx()
        self.assertNotIn(ident,[r['id'] for r in empty['records']])
        version=self.link(ident,self.TASK)['link']['linked_at'];ctx=self.ctx();record=next(r for r in ctx['records'] if r['id']==ident)
        self.assertEqual((record['linked_task_id'],record['source']),(self.TASK,'试卷 / 作业核对'));self.assertNotEqual(empty['evidence_hash'],ctx['evidence_hash'])
        self.assertNotIn('linked_task_id',next(r for r in ctx['records'] if r['id']==kept['record_id']))
        self.approve(self.evaluate())
        goal=self.goal();self.assertFalse(goal['evidence_changed']);plan=goal['current_plan']
        def corrected():
            with self.app.connect() as c:
                return goals.family_learner_memory.corrected_refs(c,[ref,kept_ref],self.goal()['current_plan_confirmed_at'],self.store._owned(c,'child-1'))
        self.assertEqual(corrected(),[])
        moved=self.link(ident,self.OTHER,version)['link']['linked_at'];goal=self.goal()
        self.assertTrue(goal['evidence_changed']);self.assertEqual(goal['current_plan'],plan)
        self.assertNotIn(ident,[r['id'] for r in self.ctx()['records']])
        # The confirmed judgment that cited the moved record is flagged; the task's own feedback stays valid evidence.
        self.assertEqual(corrected(),[ref]);self.assertIn(kept['record_id'],[r['id'] for r in self.ctx()['records']])
        gone=self.link(ident,'',moved)['link']['linked_at'];self.assertEqual(corrected(),[ref]);self.assertTrue(self.goal()['evidence_changed'])
        # Attached again to the confirmed task, the record says what it said then.
        self.link(ident,self.TASK,gone);self.assertEqual(corrected(),[])

    def test_first_link_preserves_the_pre_link_basis_and_cannot_gain_a_second_task_source(self):
        ident,_=self.saved();before=self.row(ident);since=dt.datetime.now().isoformat()
        self.link(ident,self.TASK)
        with self.app.connect() as c:
            corrected=goals.family_learner_memory.corrected_refs(c,['record:%d'%ident],since,self.store._owned(c,'child-1'))
        self.assertEqual(corrected,['record:%d'%ident])
        history=self.app.record_history(ident)
        self.assertEqual(history['history'][0]['previous']['source'],before['source'])
        body={k:before[k] for k in ('child','day','category','subject','title','note')}
        self.refused('record_task_mismatch',409,lambda:self.app.save_record(dict(body,id=ident,source='事项:'+self.OTHER)))

    def test_http_route_needs_the_parent_token(self):
        ident,_=self.saved();server=self.app.ThreadingHTTPServer(('127.0.0.1',0),self.app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def post(token,body):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                client.request('POST','/api/record/task-link',json.dumps(body),{'Content-Type':'application/json','X-Family-Token':token})
                response=client.getresponse();return response.status,json.loads(response.read())
            finally:client.close()
        try:
            body=dict(record_id=ident,child='示例甲',task_id=self.TASK);before=self.dump()
            self.assertEqual(post('invalid-token',body)[0],403);self.assertEqual(self.dump(),before)
            status,result=post(self.app.snapshot()['token'],body)
            self.assertEqual((status,result['changed'],result['link']['task_id'],result['task']['linked_record_ids']),(200,True,self.TASK,[ident]))
            status,result=post(self.app.snapshot()['token'],body|dict(task_id=self.OTHER))
            self.assertEqual((status,result.get('code')),(409,'record_task_link_conflict'))
            child=self.app.family_child
            child.parent_action(self.app,'study',dict(child_id='child-1',enabled=True))
            invitation=child.parent_action(self.app,'invite',dict(child_id='child-1'))
            def child_request(path,body=None,headers=None):
                client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    client.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,
                                   {'Content-Type':'application/json',**(headers or {})})
                    response=client.getresponse();raw=response.read()
                    return response.status,json.loads(raw),dict(response.getheaders())
                finally:client.close()
            status,state,headers=child_request('/child/api/login',dict(invite=invitation['invite']))
            self.assertEqual(status,200);cookie=headers['Set-Cookie'].split(';',1)[0]
            headers={'Cookie':cookie,'X-Child-CSRF':state['csrf']}
            status,state,_=child_request('/child/api/state',headers=headers);self.assertEqual(status,200)
            serialized=json.dumps(state,ensure_ascii=False);record=self.row(ident)
            for hidden in (record['note'],record['transcript'],*json.loads(record['attachments'])):
                self.assertNotIn(hidden,serialized)
            before=self.dump()
            for token in ('',self.app.TOKEN):
                status,_,_=child_request('/api/record/task-link',body|dict(task_id=self.OTHER,expected_linked_at=record['linked_task_at']),
                                         headers|{'X-Family-Token':token})
                self.assertEqual(status,403);self.assertEqual(self.dump(),before)
            self.assertEqual(child_request('/child/upload/'+json.loads(record['attachments'])[0],headers=headers)[0],403)
        finally:server.shutdown();server.server_close();worker.join()


if __name__=='__main__':
    unittest.main()

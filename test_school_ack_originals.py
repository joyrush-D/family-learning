"""Synthetic acknowledgement/original intake; no collectors, model transport or devices."""
import base64
import copy
import datetime as dt
import io
import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import family_agent as agent
import family_media
import test_agent as fixtures


class SchoolAckOriginalTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.AgentTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app,self.store,self.now=self.fixture.app,self.fixture.store,self.fixture.now
        self.source=self.fixture.source
        # WAL lets a second session commit while the eligibility reader retains
        # its snapshot. A rollback-journal reader would block that writer instead.
        with self.store._db() as c:c.execute('PRAGMA journal_mode=WAL')
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('family_qq_capture.run_one',return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public,'run_one',return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media,'run_one',return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media,'prepare_draft',return_value=dict(used=0,failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run',return_value=dict(used=0,failed=0,created=0,children=set())))
        self.model=self.stack.enter_context(patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('not a real model call')))

    def _input(self,**changes):
        payload=self.fixture.payload()
        payload['messages'][0].update(text='收到，谢谢老师。',**changes)
        self.store.ingest(payload)
        return payload['messages']

    def _original(self,values,*,prepared=False):
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRZkAAAAASUVORK5CYII=')
        upload=self.app.save_upload(io.BytesIO(png),len(png),'synthetic-school.png')
        keys=dict(child_id='child-1',source_id=self.source['id'],message_id=values[0]['id'],attachment_id=upload['id'],action='attach')
        self.store.message_attachment(keys,dict)
        if prepared:
            with self.store._db() as c:
                source,message=self.store._message_context(c,keys)
                value=family_media.draft_input(self.store,c,source,message)
                note=dict(title='英语：朗读与练习',note='英语：朗读Unit 2课文两遍，完成练习册第8页。',
                    requirements=['英语：朗读Unit 2课文两遍，完成练习册第8页。'],uncertainties=[])
                draft=dict(kind='school_material',**agent.family_llm.validate_school_material(
                    dict(originals=[dict(upload_id=upload['id'],**note)]),original_ids=value['original_ids']))
                c.execute('INSERT INTO agent_message_drafts VALUES(?,?,?,?,?)',
                    (source['id'],message['id'],value['fingerprint'],json.dumps(draft,ensure_ascii=False),self.now.isoformat()))
        return keys

    def _legacy(self,values):
        key='messages:'+agent._hash([self.source['id'],[v['id'] for v in values]])[:40]
        fp=self.store._job(key,dict(school_learning_policy=8,messages=values),self.now,model=True)
        self.store._save(key,fp,[],self.now,[(self.source['id'],v['id']) for v in values])
        return key

    def _protected(self,key):
        with self.store._db() as c:
            return dict(sources=[dict(r) for r in c.execute('SELECT * FROM agent_sources')],
                messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages')],
                job=dict(c.execute('SELECT * FROM agent_jobs WHERE id=?',(key,)).fetchone()),
                attachments=[dict(r) for r in c.execute('SELECT * FROM agent_message_attachments')])

    def test_only_complete_text_acknowledgements_are_discarded(self):
        ref='message:synthetic-group:11';ack=dict(ref=ref,text='收到，谢谢老师。',time=self.now.isoformat(),kind='text',content_incomplete=False,attachments=[])
        self.assertEqual(agent._select('school',[ack],school_goals=[]),[])
        for extra in (dict(content_incomplete=True),dict(kind='image'),dict(kind='file'),
                      dict(kind='qq_window_fragment'),dict(attachments=[dict(name='synthetic.pdf',mime='application/pdf')])):
            with self.subTest(extra=extra):
                items=agent._select('school',[dict(ack,**extra)],school_goals=[])
                self.assertEqual(len(items),1,'unread originals need an ordinary pending reading entry')
                self.assertEqual(items[0]['evidence'],[dict(ref=ref,text=ack['text'])])
                self.assertEqual(items[0]['due'],'')
                self.assertEqual(items[0]['plan']['school_task']['state'],'review')
                self.assertNotIn('school_history_job',items[0]['plan'])
        self.model.assert_not_called()

    def test_initial_pending_original_then_prepared_requirements_reach_same_task(self):
        values=self._input(kind='image',unread=True)
        first=agent.run_once(self.app,self.now)
        self.assertEqual((first['failed'],first['created']),(0,1))
        with self.store._db() as c:
            row=dict(c.execute("SELECT * FROM agent_items WHERE kind='school'").fetchone())
            self.assertEqual(row['state'],'pending');self.assertEqual(row['due'],'')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
        self._original(values,prepared=True)
        ready=dict(title='英语：朗读与第8页练习',goal='朗读Unit 2课文两遍；完成练习册第8页。',advice='',
            state='ready',reason='原件要求明确。',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id='')
        self.model.side_effect=lambda *a,**kw:self.fixture._original_reply(row['id'],ready)
        result=agent.run_once(self.app,self.now+dt.timedelta(minutes=1))
        self.assertEqual(result['failed'],0)
        self.assertEqual(self.model.call_count,1)
        with self.store._db() as c:
            fresh=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone())
            self.assertEqual((fresh['state'],fresh['title']),('accepted',ready['title']))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
        agent.run_once(self.app,self.now+dt.timedelta(minutes=2))
        self.assertEqual(self.model.call_count,1)

    def test_exact_empty_policy8_material_recovers_without_changing_old_receipt(self):
        values=self._input(kind='image',unread=True);self._original(values)
        key=self._legacy(values);before=self._protected(key)
        self.assertEqual(agent._recover_school_ack_originals(self.store,self.store._config(),self.now)['created'],1)
        self.assertEqual(self._protected(key),before)
        self.assertEqual(agent._recover_school_ack_originals(self.store,self.store._config(),self.now)['created'],0)
        with self.store._db() as c:
            row=dict(c.execute("SELECT * FROM agent_items WHERE kind='school'").fetchone())
            self.assertEqual((row['state'],row['due']),('pending',''))
            self.assertNotIn('school_history_job',json.loads(row['plan']))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
        self.model.assert_not_called()

    def test_unknown_empty_policy8_and_pure_ack_remain_untouched(self):
        for text in ('收到，谢谢老师。','明天带练习本。'):
            with self.subTest(text=text):
                # independent fixture avoids reusing a finished intake receipt
                other=fixtures.AgentTests(methodName='runTest');other.setUp();self.addCleanup(other.doCleanups)
                payload=other.payload();payload['messages'][0]['text']=text;other.store.ingest(payload)
                values=payload['messages'];key='messages:'+agent._hash([other.source['id'],['11']])[:40]
                fp=other.store._job(key,dict(school_learning_policy=8,messages=values),other.now)
                other.store._save(key,fp,[],other.now,[(other.source['id'],'11')])
                self.assertEqual(agent._recover_school_ack_originals(other.store,other.store._config(),other.now)['created'],0)

    def test_legacy_receipt_changed_during_save_keeps_message_and_no_candidate(self):
        values=self._input(kind='image',unread=True);key=self._legacy(values)
        real=self.store._save
        def changed(*a,**kw):
            with self.store._db() as c:c.execute('UPDATE agent_jobs SET fingerprint=? WHERE id=?',('changed',key))
            return real(*a,**kw)
        with patch.object(self.store,'_save',side_effect=changed):
            result=agent._recover_school_ack_originals(self.store,self.store._config(),self.now)
        self.assertEqual((result['created'],result['failed']),(0,1))
        with self.store._db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],1)

    def test_old_text_caption_with_later_attachment_recovers_once_but_no_decision_is_inferred(self):
        values=self._input();key=self._legacy(values);self._original(values)
        before=self._protected(key)
        result=agent._recover_school_ack_originals(self.store,self.store._config(),self.now)
        self.assertEqual((result['created'],result['failed']),(1,0))
        self.assertEqual(self._protected(key),before)
        with self.store._db() as c:
            row=c.execute('SELECT id,plan FROM agent_items').fetchone()
            self.assertEqual(json.loads(row['plan'])['school_task']['goal'],'')
            c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(row['id'],))
        self.assertEqual(agent._recover_school_ack_originals(self.store,self.store._config(),self.now)['created'],0)
        self.model.assert_not_called()

    def test_existing_same_origin_candidate_blocks_legacy_recovery_even_if_superseded(self):
        values=self._input(kind='image',unread=True);key=self._legacy(values)
        ref='message:'+self.source['id']+':11'
        existing=dict(child_id='child-1',kind='school',title='已有决定',body=agent.FOCUS['school'],due='',
            evidence=[dict(ref=ref,text=values[0]['text'])],plan={})
        self.store._save('synthetic-existing','fixture',[existing],self.now)
        with self.store._db() as c:c.execute("UPDATE agent_items SET state='superseded'")
        before=self._protected(key)
        self.assertEqual(agent._recover_school_ack_originals(self.store,self.store._config(),self.now)['created'],0)
        self.assertEqual(self._protected(key),before)

    def test_same_origin_decision_inserted_during_recovery_rejects_new_pointer(self):
        values=self._input(kind='image',unread=True);self._legacy(values)
        real=self.store._save
        def changed(*a,**kw):
            real('synthetic-competing-decision','fixture',[dict(child_id='child-1',kind='school',title='已有记录',
                body=agent.FOCUS['school'],due='',evidence=[dict(ref='message:'+self.source['id']+':11',text=values[0]['text'])],plan={})],self.now)
            return real(*a,**kw)
        with patch.object(self.store,'_save',side_effect=changed):
            result=agent._recover_school_ack_originals(self.store,self.store._config(),self.now)
        self.assertEqual((result['created'],result['failed']),(0,1))
        with self.store._db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE job_id LIKE 'school-ack-originals:%'").fetchone()[0],0)

    def test_decision_between_eligibility_and_basis_does_not_become_approved_baseline(self):
        values=self._input(kind='image',unread=True);self._legacy(values)
        real=agent._history_context;changed=False
        def intervene(store,c,source,values,key,**kw):
            nonlocal changed
            if not changed:
                changed=True
                self.store._save('synthetic-between-checks','fixture',[dict(child_id='child-1',kind='school',
                    title='另一会话已忽略',body=agent.FOCUS['school'],due='',
                    evidence=[dict(ref='message:'+self.source['id']+':11',text=values[0]['text'])],plan={})],self.now)
                with self.store._db() as writer:writer.execute("UPDATE agent_items SET state='dismissed' WHERE job_id='synthetic-between-checks'")
            return real(store,c,source,values,key,**kw)
        with patch.object(agent,'_history_context',side_effect=intervene):
            result=agent._recover_school_ack_originals(self.store,self.store._config(),self.now)
        self.assertEqual((result['created'],result['failed']),(0,1))
        with self.store._db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE job_id LIKE 'school-ack-originals:%'").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT state FROM agent_items WHERE job_id='synthetic-between-checks'").fetchone()[0],'dismissed')

    def test_attachment_removed_between_eligibility_and_basis_cannot_seed_stale_pointer(self):
        values=self._input();keys=self._original(values);self._legacy(values)
        real=agent._history_context;changed=False
        def intervene(store,c,source,values,key,**kw):
            nonlocal changed
            if not changed:
                changed=True;self.store.message_attachment(dict(keys,action='detach'),dict)
            return real(store,c,source,values,key,**kw)
        with patch.object(agent,'_history_context',side_effect=intervene):
            result=agent._recover_school_ack_originals(self.store,self.store._config(),self.now)
        self.assertEqual((result['created'],result['failed']),(0,1))
        with self.store._db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_message_attachments').fetchone()[0],0)


if __name__=='__main__':unittest.main()

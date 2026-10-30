"""Run python3 test_retry_view.py. Temporary synthetic files/SQLite and a fictional pack stub; no household data, services or models.

A saved new-question attempt (the 复测 record written for one topic_retries row) gets one short read-only view, the same on the
web state and the day list the Mac app reads: question, the child's saved answer, result and help, topic and original wrong
record, then a next step that never calls one right answer mastery. It is found only through topic_retries.followup_record_id;
changed record text keeps that text shown, a corrected original makes it history (as the progress line counts it), a missing
pack keeps the record's own text, a record without that relation gets no view, and reading writes nothing.
"""
import os
from pathlib import Path
import tempfile
from unittest.mock import patch


def dump(app):
    with app.connect() as connection: return '\n'.join(connection.iterdump())


with tempfile.TemporaryDirectory(prefix='synthetic-retry-view-') as folder:
    root=Path(folder); data=root/'private'; data.mkdir()
    with patch.dict(os.environ, {'FAMILY_DATA':str(data)}):
        import app
        import family_taxonomy as tx
    with patch.multiple(app, ROOT=root, DATA=data, DB=data/'family.sqlite3'):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 8岁 | 二年级 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 数学：有理数加法 | 2026-10-28 | 待跟进 | 虚构学校通知 | 完成两道加法并检查 |\n')
        feedback=app.save_task_feedback(dict(task_id='T01',child='示例甲',day='2026-10-28',note='虚构：第一题符号算错',request_key='synthetic-retry-view-fb'))
        wid=app.save_record(dict(child='示例甲',day='2026-10-28',category='学习进展',subject='数学',title='虚构加法错题',note='题面：(-8)+5=?\n学生原答：-13',
                                 source=tx.WRONG_SOURCE,related_record_id=feedback['record_id'],followup_kind='补充观察'))['record_id']
        pack={'by_id':{'cnm_t1':{'id':'cnm_t1','name':'虚构的加法法则'}}}
        questions={'cnm_t1_q1':{'id':'cnm_t1_q1','topicId':'cnm_t1','prompt':'计算 (-1)+3。'}}
        note=tx._retry_note(questions['cnm_t1_q1'],pack['by_id']['cnm_t1'],'2','correct',True)
        fid=app.save_record(dict(child='示例甲',day='2026-10-31',category='学习进展',subject='数学',title='新题再试 · 虚构加法错题',note=note,source=tx.RETRY_SOURCE,
                                 related_record_id=wid,followup_kind='复测',assistance='独立尝试',practice_relation='相近的新题或新片段',request_key='tdr-synthetic-retry-0001'))['record_id']
        loose=app.save_record(dict(child='示例甲',day='2026-10-31',category='学习进展',subject='数学',title='新题再试 · 无关系',note='虚构：没有再试关系的文字',
                                   source=tx.RETRY_SOURCE,related_record_id=wid,followup_kind='复测',request_key='tdr-synthetic-loose-0001'))['record_id']
        with app.connect() as c:
            tx.ensure_schema(c); ids={p['name']:p['id'] for p in app.profiles(c)}
            w=dict(c.execute('SELECT id,child,day,subject,title,note,source,attachments,created FROM records WHERE id=?',(wid,)).fetchone())
            h=tx.record_hash(w|dict(child_id=ids['示例甲']))
            did=c.execute('INSERT INTO topic_diagnoses(child_id,record_id,record_hash,topic_id,pack_sha,engine_sha256,opts,request_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (ids['示例甲'],str(wid),h,'cnm_t1',tx.TAXONOMY_SHA,'synthetic','{}','synthetic-diag',0,0)).lastrowid
            c.execute('INSERT INTO topic_retries(diagnosis_id,child_id,record_id,record_hash,topic_id,qid,answer,taxonomy_verdict,deeptutor,outcome,followup_record_id,request_id,created_at) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(did,ids['示例甲'],str(wid),h,'cnm_t1','cnm_t1_q1','2','correct','{"is_correct": true, "independent": true, "deeptutor_sha": "a31d826synthetic"}',
                                                          'independent_correct',fid,'synthetic-retry',0))

        def view(rid):
            return next(r for r in app.snapshot()['records'] if r['id']==rid).get('retry')

        def listed(rid):
            out=app.day_view(ids['示例甲'],'2026-10-28');items=[i for g in out['groups'] for i in g['items']]+[i for i in out.get('closed') or [] if isinstance(i,dict) and 'records' in i]
            return [x for i in items for x in i['records'] if x['id']==rid]

        with patch.multiple(tx,load_pack=lambda root=None:pack,question=lambda p,qid:questions.get(qid)):
            app.snapshot();before=dump(app)
            v=view(fid);lines=dict(v['lines'])
            assert v['state']=='current' and v['show_note'] is False and not v['status'],v
            assert [k for k,_ in v['lines']]==['题目','孩子原答','本次结果','知识点','原错题'],v
            assert lines['题目'].startswith('计算 (-1)+3。') and tx.REVIEW_STATUS in lines['题目'] and lines['孩子原答']=='2'
            assert lines['本次结果'].startswith('对 · 独立尝试') and lines['知识点']=='虚构的加法法则' and lines['原错题']=='虚构加法错题'
            assert '不等于掌握' in v['next'] and '掌握。' not in v['next'].replace('不等于掌握','') and 'cnm_t1_q1' in v['trace'] and tx.TAXONOMY_SHA[:7] in v['trace'] and 'a31d826' in v['trace']
            row=listed(fid);assert row and row[0]['retry']==v and row[0]['note']==note,row
            assert view(loose) is None and all('retry' not in x for x in listed(loose))
            task=next(t for t in app.snapshot()['tasks'] if t['id']=='T01');assert task['progress']['retries']==1 and task['progress']['history']==0,task['progress']
            assert dump(app)==before,'reading the view wrote to the database'
            with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',(note+'\n家长补充：虚构',fid))
            v=view(fid);assert v['state']=='edited' and v['show_note'] and '改过文字' in v['status'] and '题目' in dict(v['lines']),v
            assert '本次结果' in dict(v['lines']),v
            assert listed(fid)[0]['note'].endswith('家长补充：虚构')
            with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',(note,fid))
            with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',('题面：(-8)+5=?\n学生原答：-3',wid))
            v=view(fid);assert v['state']=='history' and '只作历史' in v['status'] and '重新诊断' in v['next'] and not v['show_note'],v
            assert dict(v['lines'])['当时结果'].startswith('对') and '本次结果' not in dict(v['lines']),v
            task=next(t for t in app.snapshot()['tasks'] if t['id']=='T01');assert task['progress']['retries']==0 and task['progress']['history']==1,task['progress']
            with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',('题面：(-8)+5=?\n学生原答：-13',wid))

        def missing(root=None): raise tx.TaxonomyError('知识包未安装','pack_unavailable',503)
        with patch.object(tx,'load_pack',missing):
            v=view(fid);assert v['state']=='unclear' and v['show_note'] and '依据不明' in v['status'] and '题目' not in dict(v['lines']) and dict(v['lines'])['孩子原答']=='2',v
            assert '本次结果' in dict(v['lines']),v
        # An unreadable original proves no correction: say so, keep the saved text and result; only a recorded void makes it history.
        with patch.multiple(tx,load_pack=lambda root=None:pack,question=lambda p,qid:questions.get(qid)):
            with app.connect() as c: c.execute('DELETE FROM records WHERE id=?',(wid,))
            v=view(fid);lines=dict(v['lines'])
            assert v['state']=='unclear' and v['show_note'] and '原错题当前读不到' in v['status'] and '更正' not in v['status']+v['next'],v
            assert lines['孩子原答']=='2' and lines['当时结果'].startswith('对') and '本次结果' not in lines and '原错题' not in lines and '题目' not in lines,v
            assert next(r for r in app.snapshot()['records'] if r['id']==fid)['note']==note
            with app.connect() as c:
                c.execute('INSERT INTO topic_basis_voids(diagnosis_id,child_id,record_id,old_record_hash,state,question_ids,detail,snapshot_before_sha256,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (did,ids['示例甲'],str(wid),h,'voided','[]','synthetic','',0,0))
            v=view(fid);assert v['state']=='history' and '原错题当前读不到' in v['status'] and '只作历史' in v['status'],v
            assert '当时结果' in dict(v['lines']) and '本次结果' not in dict(v['lines']),v
print('retry view: current, list parity, unrelated, edited, history, missing pack, missing original and no writes passed')

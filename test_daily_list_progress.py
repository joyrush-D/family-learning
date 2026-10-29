"""Run python3 test_daily_list_progress.py. Temporary synthetic files/SQLite; no household services or models.

The list's progress line reads only what is already saved for the same task and child: no record gives none, feedback and
an explicitly linked wrong record count (the save/link replies carry the new line), a current-basis diagnosis is a clue
and only its independent new attempts count, a corrected
original moves the old diagnosis to history, missing topic tables give no clue, and opening the list writes nothing.
"""
import inspect
import io
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import family_agent as agent


def dump(app):
    with app.connect() as connection: return '\n'.join(connection.iterdump())


with tempfile.TemporaryDirectory(prefix='synthetic-list-progress-') as folder:
    root=Path(folder); data=root/'private'; data.mkdir()
    with patch.dict(os.environ, {'FAMILY_DATA':str(data)}):
        import app
        import family_taxonomy
    with patch.multiple(app, ROOT=root, DATA=data, DB=data/'family.sqlite3'):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 8岁 | 二年级 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 数学：完成P12第2至4题 | 本周 | 待跟进 | 虚构学校通知 | 完成练习册第12页第2至4题，写出计算过程 |\n'
                                   '| T02 | 示例甲 | 语文：朗读晚照 | 本周 | 待跟进 | 虚构学校通知 | 朗读《晚照》2遍 |\n')
        task=lambda ident:next(t for t in app.tasks() if t['id']==ident)
        # Nothing saved: the original task row only.
        assert 'progress' not in task('T01') and 'progress' not in task('T02')
        before=dump(app)
        app.tasks();assert dump(app)==before,'opening the list writes nothing'
        photo=app.save_upload(io.BytesIO(b'synthetic page'),14,'synthetic-page.txt')['id']
        saved=app.save_task_feedback(dict(task_id='T01',child='示例甲',day='2026-11-04',request_key='synthetic-progress-0001',
                                          note='第3题进位错了',attachments=[photo]))
        # The save itself returns the row's new line (the page applies this task without reloading the whole list).
        assert saved['task']['progress']==dict(feedback=1,wrong=0,wrong_ids=[],clues=0,retries=0,history=0),saved['task'].get('progress')
        assert task('T01')['progress']==dict(feedback=1,wrong=0,wrong_ids=[],clues=0,retries=0,history=0)
        assert 'progress' not in task('T02')
        with app.connect() as c:
            c.execute("INSERT INTO records (child,day,category,subject,title,note,source,score,total,created,attachments) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      ('示例甲','2026-11-04','学习进展','数学','错题：第3题','进位漏写',family_taxonomy.WRONG_SOURCE,None,None,'2026-11-04T20:00:00','[]'))
            wrong=c.execute('SELECT max(id) FROM records').fetchone()[0]
            c.execute("INSERT INTO records (child,day,category,subject,title,note,source,score,total,created,attachments) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      ('示例乙','2026-11-04','学习进展','数学','错题：别人的','进位漏写',family_taxonomy.WRONG_SOURCE,None,None,'2026-11-04T20:00:00','[]'))
            other=c.execute('SELECT max(id) FROM records').fetchone()[0]
        # An unlinked wrong record of the same subject is never inferred into the task.
        assert task('T01')['progress']['wrong']==0
        linked=app.link_record_task(dict(record_id=wrong,child='示例甲',task_id='T01'))
        assert linked['task']['progress']['wrong_ids']==[wrong] and 'previous_task' not in linked,linked['task']
        try: app.link_record_task(dict(record_id=other,child='示例乙',task_id='T01'))
        except app.RecordError: pass
        progress=task('T01')['progress']
        assert (progress['feedback'],progress['wrong'],progress['wrong_ids'],progress['clues'])==(1,1,[wrong],0),progress
        left=app.link_record_task(dict(record_id=wrong,child='示例甲',task_id='',expected_linked_at=linked['link']['linked_at']))
        assert left['task'] is None and left['previous_task']['progress']['wrong']==0,left
        app.link_record_task(dict(record_id=wrong,child='示例甲',task_id='T01',expected_linked_at=left['link']['linked_at']))
        # No topic tables yet: no clue, nothing created by reading.
        with app.connect() as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='topic_diagnoses'").fetchone()
        with app.connect() as c:
            family_taxonomy.ensure_schema(c)
            record=family_taxonomy.wrong_record(app,c,'child-1',wrong)
            now=family_taxonomy.record_hash(record)
            c.execute("INSERT INTO topic_diagnoses(child_id,record_id,record_hash,topic_id,pack_sha,engine_sha256,opts,request_id,created_at,updated_at) VALUES ('child-1',?,?,'g4-carry','p','e','{}','synthetic-d1',1,1)",(str(wrong),now))
            diag=c.execute('SELECT max(id) FROM topic_diagnoses').fetchone()[0]
            # The outcomes family_taxonomy.retry actually saves: only the two independent ones are new attempts.
            for n,(outcome,child_id) in enumerate([('independent_correct','child-1'),('independent_wrong','child-1'),('not_new','child-1'),
                                                   ('parent_check','child-1'),('not_independent','child-1'),('independent_correct','child-2')]):
                c.execute("INSERT INTO topic_retries(diagnosis_id,child_id,record_id,record_hash,topic_id,qid,taxonomy_verdict,outcome,request_id,created_at) VALUES (?,?,?,?,'g4-carry',?,'correct',?,?,2)",
                          (diag,child_id,str(wrong),now,'q%d'%n,outcome,'synthetic-r%d'%n))
        source=inspect.getsource(family_taxonomy.retry)
        for outcome in ('independent_correct','independent_wrong','not_new','parent_check','not_independent'): assert "'%s'"%outcome in source,outcome
        assert "outcome.startswith('independent_')" in source,'only independent outcomes write the 复测 record'
        before=dump(app)
        progress=task('T01')['progress']
        assert (progress['clues'],progress['retries'],progress['history'])==(1,2,0),progress
        assert dump(app)==before,'reading diagnosis progress writes nothing'
        # The original wrong record is corrected: the earlier diagnosis is history, not current progress, and nothing is voided by reading.
        with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',('进位漏写，已订正',wrong))
        before=dump(app)
        progress=task('T01')['progress']
        assert (progress['clues'],progress['retries'],progress['history'])==(0,0,1),progress
        assert dump(app)==before,'a changed basis is read, not settled'
        # The other child's task never sees this child's records.
        assert 'progress' not in task('T02')
        # The C06 carried name keeps its admin purpose; study outside the name still reads as learning.
        value=dict(title='英语：携带单词听写本',goal='明天英语课带《单词听写本》，不用在家练习。',advice='',state='ready',reason='',purpose='admin')
        brief=lambda goal:agent._school_brief(dict(value,goal=goal),evidence=[dict(ref='message:s:1',text=goal,kind='text',unread=False)],separate_learning=True)
        assert brief('明天英语课带《单词听写本》，不用在家练习。')['state']=='ready'
        for goal in ('明天英语课带《单词听写本》，今晚在家听写10个单词。','明天英语课带《单词听写本》，并非不用在家练习。'):
            assert brief(goal)['state']=='review',goal
print('ok')

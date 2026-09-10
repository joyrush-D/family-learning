"""Run python3 test_teachers.py: isolated synthetic teacher evidence, no network or family data."""
import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace

import family_agent
import family_teachers


def reject(call, code=None):
    try: call()
    except family_teachers.TeacherError as error:
        if code: assert error.code == code, (error.code, code)
    else: raise AssertionError('Invalid change accepted')


def main():
    with tempfile.TemporaryDirectory(prefix='synthetic-teachers-') as temporary:
        data = Path(temporary)
        def connect():
            c = sqlite3.connect(data / 'test.sqlite3'); c.row_factory = sqlite3.Row
            return c
        def profiles(c=None):
            return [dict(id='child-1', name='示例甲'), dict(id='child-2', name='示例乙')]
        agent = family_agent.Store(connect, profiles, data)
        config = dict(enabled=False, sources=[dict(id='qq:100001', platform='qq', child_id='child-1', name='虚构一班', cursor='', enabled=False),
                                              dict(id='qq:100002', platform='qq', child_id='child-2', name='虚构二班', cursor='', enabled=False)])
        (data / 'agent.json').write_text(json.dumps(config))
        app = SimpleNamespace(connect=connect, profiles=profiles, agent_store=lambda: agent)
        store = family_teachers.Store(app)
        assert store.snapshot()['teachers'] == store.snapshot()['observations'] == []
        counter = 0
        def request(**fields):
            nonlocal counter
            counter += 1
            return dict(request_key='synthetic-request-' + str(counter), version=0, **fields)
        create = request(display_name='示例老师甲', subject='语文', child_ids=['child-1'], source_ids=['qq:100001'], archived=False, public_url='')
        teacher = store.save_teacher(create)['teacher']; ident = teacher['id']
        assert teacher['version'] == 1 and teacher['display_name'] == '示例老师甲'
        assert store.save_teacher(create)['teacher']['id'] == ident
        reject(lambda: store.save_teacher(create | {'subject': '数学'}), 'teacher_request_conflict')
        reject(lambda: store.save_teacher(request(display_name='虚构', child_ids=['missing'])))
        reject(lambda: store.save_teacher(request(display_name='虚构', child_ids=['child-1'], source_ids=['qq:100002'])))
        reject(lambda: store.save_teacher(create | {'id': ident, 'request_key': 'other-request-key-1'}), 'teacher_conflict')
        for invalid in ('javascript:alert(1)', 'https://user:secret@example.com/profile', 'http://example.com/profile'):
            reject(lambda value=invalid: store.save_teacher(request(display_name='虚构', child_ids=['child-1'], public_url=value)))
        date = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
        observe = request(teacher_id=ident, day=date, kind='praise', target='household', child_id='child-1',
                          behavior='虚构：老师表扬主动说明解题思路', teacher_reason='虚构原话：步骤解释清楚',
                          parent_note='虚构家长待核实观察：下次再看是否同样重视口头表达', source_id='qq:100001',
                          message_id='', source_url='', status='active')
        observation = store.save_observation(observe)['observation']; observation_id = observation['id']
        assert observation['teacher_reason'] != observation['parent_note']
        assert store.save_observation(observe)['observation']['id'] == observation_id
        reject(lambda: store.save_observation(observe | {'behavior': '更改未换请求编号'}), 'teacher_request_conflict')
        reject(lambda: store.save_observation(observe | {'child_id': 'child-2'}))
        reject(lambda: store.save_observation(observe | {'source_id': 'qq:100002'}), 'teacher_source_conflict')
        reject(lambda: store.save_observation(observe | {'target': 'other_students'}))
        reject(lambda: store.save_observation(observe | {'other_student_name': '不应保存'}))
        reject(lambda: store.save_observation(observe | {'message_id': 'missing'}), 'teacher_message_unavailable')
        reject(lambda: store.save_observation(observe | {'day': '2026-02-30'}))
        reject(lambda: store.save_observation(observe | {'source_url': 'javascript:alert(1)'}))
        for field in ('status', 'kind', 'target', 'behavior', 'day'):
            reject(lambda key=field: store.save_observation(observe | {key: []}))
        linked = dict(id='message-1', time=date + 'T08:00:00+08:00', text='虚构教学通知', unread=[])
        with agent._db() as c:
            source = config['sources'][0]
            c.execute('INSERT INTO agent_sources(id,binding,cursor) VALUES (?,?,?)', (source['id'], agent._binding(source, None), ''))
            c.execute('INSERT INTO agent_messages(source_id,id,payload) VALUES (?,?,?)', (source['id'], linked['id'], json.dumps(linked)))
        other = store.save_observation(request(teacher_id=ident, day=date, kind='preference', target='other_students',
            child_id='', behavior='虚构：表扬一位同学先检查再提交', teacher_reason='', parent_note='原因未说明，待核实',
            source_id='qq:100001', message_id='message-1'))['observation']
        assert other['child_id'] == '' and other['teacher_reason'] == '' and other['status'] == 'active'
        reject(lambda: store.save_teacher(dict(create, id=ident, version=1, request_key='change-bindings-001', source_ids=[])),
               'teacher_binding_conflict')
        teacher2 = store.save_teacher(request(display_name='示例老师乙', child_ids=['child-1']))['teacher']
        reject(lambda: store.save_observation(dict(observe, id=observation_id, version=1,
            request_key='change-teacher-001', teacher_id=teacher2['id'], source_id='')), 'teacher_binding_conflict')
        corrected = dict(observe, id=observation_id, version=1, request_key='correct-observe-001',
                         behavior='虚构更正：实际表扬的是本次主动检查', teacher_reason='', parent_note='原原因误记，已更正')
        assert store.save_observation(corrected)['observation']['version'] == 2
        assert store.save_observation(corrected)['observation']['version'] == 2
        reject(lambda: store.save_observation(observe), 'teacher_conflict')
        withdraw = corrected | dict(version=2, request_key='withdraw-observe-001', status='withdrawn')
        assert store.save_observation(withdraw)['observation']['status'] == 'withdrawn'
        archive = create | dict(id=ident, version=1, request_key='archive-teacher-001', archived=True)
        assert store.save_teacher(archive)['teacher']['archived'] is True
        reject(lambda: store.save_observation(request(teacher_id=ident, day=date, kind='requirement', target='class',
                                                     behavior='虚构新增要求')))
        snapshot = family_teachers.Store(app).snapshot()
        assert len(snapshot['teachers']) == 2 and len(snapshot['observations']) == 2
        assert all('last_request_hash' not in row and 'last_request_key' not in row for row in snapshot['teachers'] + snapshot['observations'])
        with connect() as c: before = '\n'.join(c.iterdump())
        store.snapshot()
        with connect() as c: assert '\n'.join(c.iterdump()) == before
        (data / 'agent.json').write_text('{')
        assert store.snapshot()['source_error']
        assert store.save_teacher(request(display_name='虚构手动档案', child_ids=['child-2']))['teacher']['source_ids'] == []
        reject(lambda: store.save_teacher(create | dict(request_key='bad-config-test-001')), 'teacher_source_unavailable')
    print('Teacher evidence checks passed: synthetic persistence, corrections, scope, references, replay and manual fallback.')


if __name__ == '__main__': main()

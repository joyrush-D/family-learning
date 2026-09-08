"""Pure derived-reward regressions; every child and event below is fictitious."""
import copy
import datetime as dt

from family_growth import summarize


CHILDREN = [dict(id='child-example-a', name='示例甲'),
            dict(id='child-example-b', name='示例乙')]
TODAY = '2026-09-07'


def record(ident, **fields):
    return dict(id=ident, child='示例甲', day=TODAY, category='学习进展',
                title='虚构学习记录', note='', source='孩子自述',
                followup_kind='', related_record_id=None) | fields


def result(records=(), tasks=(), today=TODAY):
    return summarize(CHILDREN, records, tasks, today)


# Empty installation, deterministic child order, and no invented unlocked badges.
empty = result()
assert empty['rules_version'] == 'growth-v1'
assert [c['name'] for c in empty['children']] == ['示例甲', '示例乙']
for child in empty['children']:
    assert (child['energy'], child['level'], child['progress']) == (0, 0, 0)
    assert child['next_level_at'] == 10
    assert child['badges'] == child['events'] == []

# Each source ID once; each child/day/kind once. Other records remain explainable.
records = [record(1), record(2), record(3, category='兴趣'),
           record(4, followup_kind='独立复测', related_record_id=1),
           record(5, child='示例乙'), record(6, day='2026-09-06')]
saved = copy.deepcopy(records)
summary = result(records)
a, b = summary['children']
assert a['energy'] == 40 and b['energy'] == 10
assert [e['points'] for e in a['events'] if e['source_id'] in (1, 2)] == [10, 0]
assert all(e['reason'] and e['source_type'] == 'record' for e in a['events'])
assert {badge['id'] for badge in a['badges']} == {'learning', 'retest', 'interest'}
assert result(list(reversed(records)) + [records[0]]) == summary
assert records == saved

# Editing existing records is a recomputation, never an added reward event.
edited = copy.deepcopy(records)
edited[0].update(title='修正虚构标题', note='修改详情', score=100, total=100,
                 created='2030-01-01T00:00:00')
assert result(edited)['children'][0]['energy'] == a['energy']

# Tasks, repeated completion/reopening and printing logistics award nothing.
task = dict(id='MANUAL-example', child='示例甲', title='打印虚构讲义',
            update=dict(status='已完成', note='已打印'),
            history=[dict(status=s) for s in ['已完成', '待跟进', '已完成']])
assert result(tasks=[task])['children'][0]['energy'] == 0
assert result(records, [task]) == summary
task['update']['status'] = '待跟进'
assert result(records, [task]) == summary

# No NLP: only the specified structured source/category can receive record points.
# The reason deliberately rewards recording, and never claims this text was done.
ambiguous = record(1, title='仅记下一个计划', note='还没有做；可能下周试试')
assert result([ambiguous])['children'][0]['energy'] == 10
assert '不表示' in result([ambiguous])['children'][0]['events'][0]['reason']
excluded = [record(1, source='老师反馈'), record(2, source='学校群通知'),
            record(3, source='陪伴建议:EXAMPLE-1'), record(4, category='成绩', score=100),
            record(5, category='情绪'), record(6, category='家长观察'),
            record(7, source='未知来源'), record(8, source='家长网页记录'),
            record(9, day='2026-09-08'), record(10, day='bad-date'),
            record(11, child='示例未知'), record(True), record(0)]
assert result(excluded) == empty
assert result([record(1, source='家长观察')])['children'][0]['energy'] == 10
assert result([record(1, source='试卷 / 作业核对')])['children'][0]['energy'] == 10

# A retest must link to existing same-child facts; scores add no bonus.
base = record(1, category='成绩', source='试卷 / 作业核对', score=0, total=100)
retest = record(2, followup_kind='独立复测', related_record_id=1)
assert result([base, retest])['children'][0]['energy'] == 10
for parent in (None, 999, 2, '1', True):
    assert result([base, retest | {'related_record_id': parent}]) == empty
assert result([base | {'child': '示例乙'}, retest]) == empty
cycle = [base | {'related_record_id': 2}, retest]
assert result(cycle) == empty
assert result([base, retest | {'category': '成绩', 'score': 100}]) == empty

# New and legacy retests share the daily cap; help is not a penalty.
helped = retest | {'id': 3, 'followup_kind': '复测', 'assistance': '逐步帮助'}
assert result([base, helped])['children'][0]['energy'] == 10
both = result([base, retest, helped])['children'][0]
assert both['energy'] == 10
assert {e['kind'] for e in both['events']} == {'retest'}
assert '独立' not in both['badges'][0]['description']
assert result([base, helped | {'related_record_id': None}]) == empty

# Levels use only rule energy. Time passing never introduces streak penalties.
five_days = [record(i, day=f'2026-09-0{i}') for i in range(1, 6)]
leveled = result(five_days)['children'][0]
assert (leveled['energy'], leveled['level'], leveled['progress'],
        leveled['next_level_at']) == (50, 2, 0, 100)
assert result(five_days, today='2027-09-07') == result(five_days)
assert result(five_days, today=dt.date(2026, 9, 7)) == result(five_days)
assert '产品规则' in summary['note'] and '断签扣分' in summary['note']

print('growth reward checks passed (fictitious records only)')

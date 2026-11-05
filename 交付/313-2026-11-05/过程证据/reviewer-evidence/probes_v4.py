#!/usr/bin/env python3
"""Round-2 targeted probes for sha1 130d42f0: fold-char equivalence, title-trim permutation,
plan_lines extraction risk, empty/dead-zone. All strings invented (fictional)."""
import sys

sys.path.insert(0, '/Users/joyrush/.local/share/family-learning/public-integration-20260926')
import family_agenda as fa  # noqa: E402


def show(tag, title, action):
    out = fa.action_lines(title, action)
    print(f'{tag}: title={title!r}\n     action={action!r}\n     OUT={out!r}')


print('## 1 fold chars: does a real particle difference count as repetition?')
for i, (t, a) in enumerate([
        ('语文：A', '今天交练习册。\n今天还要交练习册。'),   # 还 = still/also
        ('语文：A', '明天带练习册。\n明天再带练习册。'),      # 再 = again
        ('语文：A', '语文要交。\n语文也要交。'),              # 也 = also
        ('语文：A', '数学都做。\n数学做。'),                  # 都 = all
        ('语文：A', '他自己做。\n他做。'),                    # 自己 = himself (not a fold char)
        ('语文：A', '家长陪着读。\n家长读。'),                # 陪着 = accompany
        ('语文：A', '明天不带练习册。\n明天不再带练习册。'),   # 不再 vs 不带
        ('语文：A', '读一遍。\n再读一遍。'),
        ('语文：A', '交或不交。\n交。'),
        ('语文：A', '和不和。\n和。')]):
    show(f'F{i}', t, a)

print('\n## 2 title trim / whole-line guard: same chars, different order or number')
for i, (t, a) in enumerate([
        ('数学：完成第3课第2题', '完成第2课第3题'),
        ('数学：完成第1—3题', '完成第13题'),
        ('数学：完成第1至3题', '完成第13题'),
        ('语文：朗读第1、2段', '朗读第12段'),
        ('数学：第20页第1题', '第1页第20题'),
        ('语文：完成练习册第2页第3题', '完成练习册第3页第2题'),
        ('数学：完成第1—3题', '完成第13题，其他不用做'),
        ('语文：读第2段', '读第2段和第3段'),
        ('语文：读第2段', '读第3段')]):
    show(f'P{i}', t, a)

print('\n## 3 empty / dead zone')
for i, (t, a) in enumerate([
        ('数学：完成《每日练习》', '完成《每日练习》。'),
        ('数学：完成《每日练习》', ''),
        ('英语：跟读', '英语：'),
        ('数学：A', '；。'),
        ('数学：A', '完成。')]):
    show(f'E{i}', t, a)

print('\n## 4 plan_lines matcher reach and the appended line')
print('  _PLAN_LINE.match(teacher text):',
      bool(fa._PLAN_LINE.match('家庭安排（计划 11月6日）：带水彩笔')), '->',
      fa._PLAN_LINE.match('家庭安排（计划 11月6日）：带水彩笔').groups() if fa._PLAN_LINE.match('家庭安排（计划 11月6日）：带水彩笔') else None)
print('  _PLAN_LINE.match(normal teacher line):', bool(fa._PLAN_LINE.match('明天带水彩笔。')))
import inspect
src = inspect.getsource(fa.day_view)
i = src.find('arranged')
print('  day_view arranged block:\n' + src[i-200:i+520])

print('\n## 5 expression hygiene over corpus outputs')
sys.path.insert(0, '.')
import property_test as pt
bad = []
for c in pt.extract_corpus():
    out = fa.action_lines(c['title'], c['action'], c.get('words'))
    for line in out:
        if line[:1] in '；;' or line[-1:] in '；;':
            bad.append((c['src'], c['action'], out))
        if any(line.startswith(w) for w in ('提交要求', '补充要求', '补充说明', '正文')):
            bad.append((c['src'], c['action'], out))
print('  dangling-；/label-start lines:', bad[:5], 'count=', len(bad))

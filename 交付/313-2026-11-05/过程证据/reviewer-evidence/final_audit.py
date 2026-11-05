#!/usr/bin/env python3
"""Final independent audit for family_agenda.py sha1 6c1574d7 (display-only change). Read-only."""
import sys

EV = '/Users/joyrush/Documents/deepseek-harness/default-workspace/work/reviewer-evidence'
REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
sys.path.insert(0, EV)
sys.path.insert(0, REPO)
import family_agenda as fa  # noqa: E402
import property_test as pt  # noqa: E402
import hashlib  # noqa: E402

print('REVIEWED sha1:', hashlib.sha1(open(REPO + '/family_agenda.py', 'rb').read()).hexdigest())

print('\n## 1 CORPUS (AST scan of repo *.py)')
cor = pt.extract_corpus()
print('CORPUS pairs:', len(cor))
flagged = []
for c in cor:
    L, E, R, O = pt.check(c['title'], c['action'], c.get('words'))
    if L or E or R:
        flagged.append((c.get('src'), c['title'], c['action'], L, E, R, O))
print('CORPUS findings:', len(flagged))
for f in flagged:
    print(' -', f)

print('\n## 2 ADVERSARIAL (pre-registered 18 hard-injury cases)')
print('cases:', len(pt.ADVERSARIAL))
red = []
for c in pt.ADVERSARIAL:
    L, E, R, O = pt.check(c['title'], c['action'])
    if L or E or R:
        red.append((c['id'], L, E, R, O))
print('ADVERSARIAL RED:', len(red))
for r in red:
    print(' -', r)

print('\n## 3 A5a (negation swap)')
print('A5a:', fa.action_lines('语文：不用抄写，要朗读两遍', '要抄写，不用朗读两遍'))

print('\n## 4 NEW risk probes: _FOLD_CHARS particles / _plain digit separators')
NEW = [
    ('F1 again', '语文：A', '读一遍。\n再读一遍。'),
    ('F2 also', '语文：A', '语文要交。\n语文也要交。'),
    ('F3 again-bring', '语文：A', '明天带练习册。\n明天再带练习册。'),
    ('F4 no-longer', '语文：A', '明天不带练习册。\n明天不再带练习册。'),
    ('N1 range-vs-13', '数学：完成第1—3题', '完成第13题'),
    ('N2 paras-vs-12', '语文：朗读第1、2段', '朗读第12段'),
]
for cid, t, a in NEW:
    L, E, R, O = pt.check(t, a)
    print(f' {cid}: T={t!r} A={a!r}\n     OUT={O!r} losses={L} errs={E} reorders={R}')

print('\n## 5 the 3 new negation guards: side effects (该省不省 / 该显不显)')
NEG = [
    ('NEG1 title-neg + body new neg', '数学：第4题不做', '第5题不做'),
    ('NEG2 body repeats title neg + new info', '数学：第4题不做', '第4题不做，改做第5题'),
    ('NEG3 restatement kept (dup)', '语文：不用背诵', '不用背诵《课文》，要朗读两遍'),
    ('NEG4 title-neg + new line', '语文：不用录音', '不用录音。明天带练习册'),
    ('NEG5 both neg, body trimmed?', '语文：不用抄写课文', '不用抄写课文，朗读两遍'),
]
for cid, t, a in NEG:
    print(f' {cid}: OUT={fa.action_lines(t, a)!r}')

print('\n## 6 no-loss join-back invariants used by the test suite')
c4 = fa.action_lines('英语：朗读课本第20页对话三遍', '朗读课本第20页对话三遍；家长签字。')
print('C4 join-back:', c4, '| join=', ''.join(c4))
print('L789 case:', fa.action_lines('英语：朗读', '今晚朗读课本第20页和第21页的对话；请家长听完后在这一页签字；明天早读检查。\n提交要求：家长听完后在第20页签字，明天早读检查。'))

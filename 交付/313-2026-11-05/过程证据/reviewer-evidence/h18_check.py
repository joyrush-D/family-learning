#!/usr/bin/env python3
"""Headless check: does the new display projection keep every h18 oracle unit readable?

Fictional acceptance material only. No model, no store, no network.
Feeds each matter's (title, action) to family_agenda.action_lines and checks that every
current_unit / negative_constraint stays readable in title+shown text (digits, 《objects》,
negation words, and character coverage). Two saved-action shapes are exercised because the
store saves a task's action as accumulated sentences.
"""
import json
import re
import sys

REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
ORACLE = ('/Users/joyrush/Documents/deepseek-harness/default-workspace/work/handoff-20261104/'
          'extract/DeepSeek-Harness-交接-20261104/附件/全虚构验收材料/ORACLE-EXECUTION.json')
sys.path.insert(0, REPO)
import family_agenda as fa  # noqa: E402


def combined(title, shown):
    return fa._plain(title) + fa._plain(''.join(shown))


def readable(text, title, shown):
    """No token loss: digits, 《objects》, negation words, and full character coverage."""
    whole = combined(title, shown)
    digits = re.findall(r'\d+', text)
    objs = re.findall(r'《([^》]+)》', text)
    negs = [c for c in '不没别勿禁未' if c in text]
    missing = ([d for d in digits if d not in whole]
               + [o for o in objs if o not in whole]
               + [n for n in negs if n not in whole])
    covered = fa._coverage(fa._plain(text), whole) if fa._plain(text) else 1.0
    return not missing and covered >= 0.999, missing, covered


def shapes(matter):
    units = [u['action'] for u in matter.get('current_units', [])]
    negs = [n['fact'] for n in matter.get('negative_constraints', [])]
    yield 'one-line-semicolon', ('；'.join(units) + '。' if units else '') + \
          (('\n' + '；'.join(negs) + '。') if negs else '')
    yield 'one-unit-per-line', '\n'.join(u + '。' for u in units) + \
          (('\n'.join(n + '。' for n in negs)) if negs else '')


def main():
    data = json.load(open(ORACLE))
    bad = 0
    for matter in data['matters']:
        subject = matter.get('subject') or ''
        title = (subject + '：' if subject else '') + matter['title_reference']
        print('=' * 88)
        print(matter['id'], '| title =', title)
        for name, action in shapes(matter):
            shown = fa.action_lines(title, action)
            print(f'  [{name}] action = {action!r}')
            print(f'  [{name}] shown  = {shown}')
            for unit in [u['action'] for u in matter.get('current_units', [])]:
                ok, missing, covered = readable(unit, title, shown)
                flag = 'OK ' if ok else 'LOSS'
                print(f'    {flag} unit={unit!r} coverage={covered:.2f} missing={missing}')
                bad += 0 if ok else 1
            for neg in [n['fact'] for n in matter.get('negative_constraints', [])]:
                ok, missing, covered = readable(neg, title, shown)
                flag = 'OK ' if ok else 'LOSS'
                print(f'    {flag} neg ={neg!r} coverage={covered:.2f} missing={missing}')
                bad += 0 if ok else 1
            if matter.get('dates'):
                print('    dates =', [(d['role'], d['date']) for d in matter['dates']])
    print('=' * 88)
    print('LOSSES:', bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

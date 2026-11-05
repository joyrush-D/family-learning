#!/usr/bin/env python3
"""Re-run the reviewer property suite against the CURRENT working tree (family_agenda.py v2).

Corpus = every action_lines/title+action fixture found in repo *.py (AST), plus the 8 h18
oracle matters, plus the invented adversarial strings from the first pass and the v2 probes.
Fictional data only; no product file is touched; no network, no GUI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import property_test as pt  # noqa: E402
import family_agenda as fa  # noqa: E402

V2_PROBES = [
    dict(id='P1 dash-range vs two digits (第1—3题 vs 第13题)',
         title='数学：完成第1—3题', action='完成第13题'),
    dict(id='P2 reverse: title 第13题 / line 第1—3题',
         title='数学：第13题', action='完成第1—3题'),
    dict(id='P3 朗读第1、2段 vs 朗读第12段',
         title='语文：朗读第1、2段', action='朗读第12段'),
    dict(id='P4 middle clause dropped: separator kept?',
         title='语文：A', action='读第3课，读第3课，读第3课两遍。'),
    dict(id='P5 fold-key particles (和/再) equality across two lines',
         title='语文：A', action='明天不再带练习册。\n明天不带练习册。'),
    dict(id='P6 positive clause inside a shown negation',
         title='语文：读课文', action='不用抄写课文。\n抄写课文'),
    dict(id='P7 label extension folds into last clause (intended C6)',
         title='语文：A', action='今晚完成，明天早上交。\n提交要求：明天早上交练习册。'),
    dict(id='P8 label extension when previous line has a trailing clause',
         title='语文：A', action='明天交练习册，然后读课文。\n提交要求：明天交练习册和卷子。'),
    dict(id='P9 title-only line with extra number (old A1e)',
         title='数学：完成练习册第20页第1题', action='完成练习册第20页第1、2题'),
    dict(id='P10 extension line (old B1)',
         title='数学：练习', action='明天交练习册。\n明天交练习册和卷子。'),
    dict(id='P11 quantity extension (old B2)',
         title='语文：读课文', action='读第3课。\n读第3课两遍。'),
    dict(id='P12 subject book (old A2g)',
         title='语文：带书', action='明天带数学练习册和语文书。\n明天带数学练习册和英语书。'),
    dict(id='P13 notebook number (old A2c/A2h)',
         title='数学：交本', action='把作业交到1号本。\n把作业交到2号本。'),
    dict(id='P14 correction negation hidden (old A3c)',
         title='语文：抄写', action='抄写课文。\n不用抄写课文。'),
    dict(id='P15 transposed page/question (old A1c)',
         title='语文：完成练习册第2页第3题', action='完成练习册第3页第2题'),
    dict(id='P16 order-blind multiset opposite claim (old A5a)',
         title='语文：不用抄写，要朗读两遍', action='要抄写，不用朗读两遍'),
]


def show(cases, label):
    print('=' * 90)
    print(label)
    flagged = 0
    for c in cases:
        losses, errs, reorders, out = pt.check(c['title'], c['action'], c.get('words'))
        if losses or errs or reorders:
            flagged += 1
            print(f'  [{c["id"]}] title={c["title"]!r} action={c["action"]!r}')
            print(f'      out={out!r}')
            for what, detail in losses:
                print(f'      LOSS {what!r} unreachable={detail!r}')
            for e in errs:
                print(f'      ERR  {e}')
            for r in reorders:
                print(f'      REORDER {r!r}')
    print(f'  -> flagged {flagged}/{len(cases)}')
    return flagged


def main():
    corpus = [dict(src=c['src'], id=f'corpus {c["src"]}', title=c['title'], action=c['action'], words=c.get('words'))
              for c in pt.extract_corpus()]
    h18 = pt.h18_cases()
    adv = pt.ADVERSARIAL + V2_PROBES
    total = show(corpus, 'CORPUS (repo fixtures)') + show(h18, 'H18 ORACLE (8 matters)') + \
        show(adv, 'ADVERSARIAL (invented fictional strings)')
    print('=' * 90)
    print('TOTAL FLAGGED CASES:', total, '| corpus', len(corpus), '| h18', len(h18), '| adversarial', len(adv))
    # exact outputs the review cites
    print('\nEXACT OUTPUTS FOR CITED CASES:')
    for c in [x for x in adv if x['id'].startswith(('P4', 'P5', 'P6', 'P9', 'P10', 'P11', 'P14', 'P15', 'P16'))]:
        print(f'  {c["id"]}\n    in : title={c["title"]!r} action={c["action"]!r}\n    out: {fa.action_lines(c["title"], c["action"])!r}')


if __name__ == '__main__':
    main()

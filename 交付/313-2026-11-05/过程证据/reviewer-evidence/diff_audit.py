#!/usr/bin/env python3
"""Round-2 differential audit: HEAD (58973a6) action_lines vs current working tree.

For every (title, action[, words]) pair the reviewer's AST scan found in repo *.py,
compute old and new output and list every plain-character fragment the OLD output showed
and the NEW one does not. Each fragment is classified:
  a-label / a-punct / a-title / a-dup  -> removable label, punctuation, or already shown
  B-LOSS                               -> not covered by title, not a repetition: information loss
Only fictional strings from the repo's own fixtures are used.
"""
import difflib
import importlib.util
import sys
from pathlib import Path

EV = Path(__file__).resolve().parent
REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
sys.path.insert(0, REPO)
sys.path.insert(0, str(EV))
import family_agenda as new  # noqa: E402
import property_test as pt  # noqa: E402

spec = importlib.util.spec_from_file_location('fa_head', '/tmp/rv_head/family_agenda.py')
head = importlib.util.module_from_spec(spec)
spec.loader.exec_module(head)

LABELS = set('提交要求补充说明正文：:')
LABEL_WORDS = ('提交要求', '补充要求', '补充说明', '正文')


def plain(t):
    return new._plain(t or '')


def classify(frag, title, new_text):
    if not frag:
        return 'a-empty'
    if set(frag) <= set('。；，,、！？!?;:：. '):
        return 'a-punct'
    if all(ch in LABELS for ch in frag) or frag.strip() in LABEL_WORDS:
        return 'a-label'
    tp = plain(title)
    if frag in tp:
        return 'a-title'
    if frag in new_text:
        return 'a-dup'
    if all(ch in tp for ch in frag):
        return 'a-title-multiset'
    return 'B-LOSS'


def fragments(old, new_t):
    """Fragments of old (in order) missing from new, as (fragment, context)."""
    o, n = plain(old), plain(new_t)
    sm = difflib.SequenceMatcher(None, o, n, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ('delete', 'replace') and i2 > i1:
            out.append((o[i1:i2], o[max(0, i1 - 8):i2 + 8]))
    return out


def main():
    pairs = pt.extract_corpus()
    print(f'PAIRS: {len(pairs)}  (HEAD=58973a6 vs working tree sha1 130d42f0)')
    stats = {'same': 0}
    cand = []
    for c in pairs:
        title, action = c['title'], c['action']
        words = c.get('words')
        try:
            old = head.action_lines(title, action, words)
        except Exception as e:  # noqa: BLE001
            old = [f'<HEAD raised {type(e).__name__}: {e}>']
        new_out = new.action_lines(title, action, words)
        old_t, new_t = ''.join(old), ''.join(new_out)
        if plain(old_t) == plain(new_t):
            stats['same'] += 1
            continue
        frags = fragments(old_t, new_t)
        judged = [(f, ctx, classify(f, title, plain(new_t))) for f, ctx in frags]
        kind = 'B' if any(j[2] == 'B-LOSS' for j in judged) else 'a'
        stats[kind] = stats.get(kind, 0) + 1
        cand.append((c, old, new_out, judged))
    for c, old, new_out, judged in cand:
        print('=' * 90)
        print(f'[{c["src"]}] title={c["title"]!r}')
        print(f'  action = {c["action"]!r}')
        print(f'  HEAD   = {old!r}')
        print(f'  NEW    = {new_out!r}')
        for f, ctx, k in judged:
            print(f'    {k:16s} {f!r}  ctx=...{ctx}...')
    print('=' * 90)
    print('SUMMARY:', stats)
    b = [c for c, _o, _n, j in cand if any(k == 'B-LOSS' for _f, _x, k in j)]
    print('B-LOSS pairs:', len(b))
    for c in b:
        print('  B-LOSS:', c['src'], repr(c['title']), repr(c['action']))


if __name__ == '__main__':
    main()

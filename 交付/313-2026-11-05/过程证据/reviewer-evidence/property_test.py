#!/usr/bin/env python3
"""Read-only property test of family_agenda.action_lines (display projection).

For every action_lines call literal / title+action fixture found in the repo (AST scan), for the
8 h18 oracle matters, and for invented fictional adversarial strings, check:

  (a) no fabrication: every output line is an in-order subsequence of the saved action text;
  (b) no silent loss: every saved line/sentence (label such as 提交要求 removed) that no longer
      reads verbatim in the card must have all of its characters reachable, in order, in the
      text the card shows (title + output); a saved line whose words are not reachable is a
      content loss. Protected tokens (digits, 第N页/第N题/第N段, negations 不没别勿禁, 《...》
      objects, time words 明天/明早/今晚/周X/18:30) get the same title-coverage test;
  (c) no output line starts with 提交要求/补充要求/补充说明/正文 and the card's last line is not
      left on a dangling ；/;.

A tracer mirrors the pipeline and names the guard that removed each lost line, so the reviewer
can point at the exact 0.90 / 0.80 path. No product file is touched.
"""
import ast
import difflib
import json
import re
import sys
from pathlib import Path

REPO = Path('/Users/joyrush/.local/share/family-learning/public-integration-20260926')
ORACLE = Path('/Users/joyrush/Documents/deepseek-harness/default-workspace/work/handoff-20261104/extract/'
              'DeepSeek-Harness-交接-20261104/附件/全虚构验收材料/ORACLE-EXECUTION.json')
sys.path.insert(0, str(REPO))
import family_agenda as fa  # noqa: E402

NEG = '不没别勿禁'
TIME = re.compile(r'明天|明早|今晚|今早|今天|后天|下周|周[一二三四五六日天]|上午|下午|晚上|[0-9]{1,2}[:：][0-9]{2}')
NUM = re.compile(r'[0-9]+')
PAGEQ = re.compile(r'第\s*[0-9一二三四五六七八九十]+\s*[页题段课节]')
OBJ = re.compile(r'《[^》]*》')


def plain(text):
    return fa._plain(text)


def norm_text(text):
    return re.sub(r'\s+', '', text or '')


def protected(text):
    found = []
    for rx, kind in ((PAGEQ, '页题'), (OBJ, '对象'), (TIME, '时间')):
        for m in rx.finditer(text):
            found.append((kind, m.group()))
    for m in NUM.finditer(text):
        found.append(('数字', m.group()))
    for ch in text:
        if ch in NEG:
            found.append(('否定', ch))
    out, seen = [], set()
    for kind, tok in found:
        if (kind, tok) in seen:
            continue
        seen.add((kind, tok))
        out.append((kind, tok))
    return out


def is_subsequence(part, source):
    i = 0
    for ch in part:
        j = source.find(ch, i)
        if j < 0:
            return False
        i = j + 1
    return True


def unreachable(part, displayed):
    """The tail of part whose characters cannot be read in order in displayed ('' = all reachable)."""
    i = 0
    for idx, ch in enumerate(part):
        j = displayed.find(ch, i)
        if j < 0:
            return part[idx:]
        i = j + 1
    return ''


def source_lines(title, action, words=None):
    saved = [x.strip() for x in str(action or '').splitlines()]
    if words:
        saved = [words['lead'] + x if x.startswith(words['work']) else x for x in saved]
    return [x for line in saved if line for x in fa._sentences(line)]


def check(title, action, words=None):
    """Returns (losses, errs, reorders, out)."""
    try:
        out = fa.action_lines(title, action, words)
    except Exception as exc:  # noqa: BLE001
        return [], [f'CRASH {type(exc).__name__}: {exc}'], [], []
    shown_plain = plain(str(title or '') + ''.join(out))
    losses, errs, reorders = [], [], []

    for line in out:
        if not is_subsequence(plain(line), plain(source_text(title, action, words))):
            errs.append(f'FABRICATE {line!r} is not made of contiguous source words in order')
    if not is_subsequence(plain(''.join(out)), plain(source_text(title, action, words))):
        reorders.append(plain(''.join(out)))

    # (b) saved lines whose words are no longer readable on the card
    for line in source_lines(title, action, words):
        body = fa._LABEL_LINE.sub('', line) if fa._LABEL_LINE.match(line) else line
        body_plain = plain(body)
        if not body_plain:
            continue
        if body_plain in shown_plain:
            continue
        tail = unreachable(body_plain, shown_plain)
        if tail:
            losses.append((line, tail))

    # protected tokens: only the title may cover a disappearance
    title_plain = plain(str(title or ''))
    for kind, tok in protected(source_text(title, action, words)):
        tn = plain(tok)
        if not tn or tn in shown_plain or tn in title_plain:
            continue
        if tok in ('不', '没', '别', '勿', '禁') and tok in title_plain:
            continue
        losses.append((f'{kind}:{tok}', tn))

    # (c) labels / dangling semicolon
    if out:
        last = out[-1].strip()
        if last.endswith(('；', ';')):
            errs.append(f'DANGLING semicolon on last line: {last!r}')
    for line in out:
        s = line.strip()
        if re.match(r'^(提交要求|补充要求|补充说明|正文)\s*[：:]', s):
            errs.append(f'LABEL prefix kept: {line!r}')
        if not plain(line):
            errs.append(f'EMPTY-only line: {line!r}')
    # no fabrication inside one line either (word order across the card)
    return losses, errs, reorders, out


def source_text(title, action, words=None):
    saved = [x.strip() for x in str(action or '').splitlines()]
    if words:
        saved = [words['lead'] + x if x.startswith(words['work']) else x for x in saved]
    return '\n'.join(saved)


def trace(title, action, words=None):
    """Mirror of the pipeline that names the guard which removed/rewrote each line."""
    notes = []
    saved = [x.strip() for x in str(action or '').splitlines()]
    if words:
        saved = [words['lead'] + x if x.startswith(words['work']) else x for x in saved]
    lines = [x for line in saved if line for x in fa._sentences(line)]
    heading = str(title or '').strip().rstrip(fa._LINE_END)
    lab = fa._TITLE_LABEL.match(heading)
    if lines and heading and lines[0].rstrip(fa._LINE_END) and \
            lines[0].rstrip(fa._LINE_END) in (heading, heading[lab.end():] if lab else heading):
        notes.append(f'first line = title: drop {lines[0]!r}')
        lines = lines[1:]
    elif lines and lab:
        own = heading[:lab.end()].rstrip()
        if lines[0].startswith(own) and lines[0][len(own):].strip():
            notes.append(f'strip heading label {own!r} from {lines[0]!r}')
            lines[0] = lines[0][len(own):].strip()
    shown = []
    for line in lines:
        orig = line
        line, taken = fa._title_prefix_removed(line, heading)
        if taken:
            notes.append(f'_title_prefix_removed: {orig!r} -> {line!r}')
        if taken and not plain(line):
            notes.append(f'drop (prefix removed everything): {orig!r}')
            continue
        labelled = fa._LABEL_LINE.match(line)
        if labelled:
            line = line[labelled.end():].strip()
            taken = True
            if not plain(line):
                notes.append(f'drop (label line empty): {orig!r}')
                continue
        cov = fa._coverage(plain(line), plain(heading))
        if plain(line) and cov >= fa._TITLE_REPEAT:
            notes.append(f'drop (_coverage vs title {cov:.3f} >= 0.90): {orig!r}')
            continue
        if labelled:
            content, touched = fa._label_line(line, shown)
            if not content:
                notes.append(f'drop (_label_line all clauses already shown): {orig!r}')
                continue
            notes.append(f'_label_line folds/keeps {orig!r} -> {content!r} touched={sorted(touched)}')
            shown.append(content)
            continue
        if fa._line_repeats(line, shown):
            notes.append(f'drop (_line_repeats >= 0.80 vs a shown line): {orig!r}')
            continue
        new, repeated = fa._without_repeats(line, shown)
        if repeated:
            notes.append(f'_without_repeats drops clauses: {orig!r} -> {new!r}')
        if not plain(new):
            notes.append(f'drop (_without_repeats removed every clause): {orig!r}')
            continue
        shown.append(new)
    return notes


# ---------------------------------------------------------------- corpus
def const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def kw(call, name):
    for k in call.keywords:
        if k.arg == name:
            return const(k.value)
    return None


def extract_corpus():
    cases = []
    for path in sorted(REPO.glob('*.py')):
        try:
            tree = ast.parse(path.read_text('utf-8'))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')
                if name == 'action_lines' and len(node.args) >= 2:
                    t, a = const(node.args[0]), const(node.args[1])
                    if t is not None and a is not None:
                        cases.append(dict(src=f'{path.name}:{node.lineno}', title=t, action=a, kind='call'))
                if node.keywords and any(k.arg == 'action' for k in node.keywords):
                    a, t = kw(node, 'action'), kw(node, 'title')
                    if a is not None and t is not None:
                        cases.append(dict(src=f'{path.name}:{node.lineno}', title=t, action=a, kind='kw'))
            elif isinstance(node, ast.Dict):
                keys = [const(k) for k in node.keys]
                if 'action' in keys and 'title' in keys:
                    t = const(node.values[keys.index('title')])
                    a = const(node.values[keys.index('action')])
                    if t is not None and a is not None:
                        cases.append(dict(src=f'{path.name}:{node.lineno}', title=t, action=a, kind='dict'))
    return cases


# ------------------------------------------------- invented adversarial cases (fictional strings only)
ADVERSARIAL = [
    dict(id='A1a 90% prefix, differing page/question digit mid-prefix',
         title='数学：完成第20页第1题', action='完成第20页第2题，家长签字'),
    dict(id='A1b 90% whole-line drop, extra question number',
         title='数学：完成第20页第1题', action='完成第20页第1、2题'),
    dict(id='A1c multiset coverage, page/question transposed',
         title='语文：完成练习册第2页第3题', action='完成练习册第3页第2题'),
    dict(id='A1d 90% prefix with a new practice-book name of its own',
         title='数学：完成《每日练习》第26页第1—3题', action='完成《口算卡》第26页第1—3题，家长签字'),
    dict(id='A2a 0.833 time word', title='语文：读课文', action='今天交练习册。\n明天交练习册。'),
    dict(id='A2b 0.857 object', title='语文：读课文', action='明天带上练习册。\n明天带上练习本。'),
    dict(id='A2c 0.857 number', title='数学：口算', action='交作业到1号本。\n交作业到2号本。'),
    dict(id='A2d 0.800 time word', title='语文：背书', action='不用明天交。\n不用后天交。'),
    dict(id='A2e 0.800 negation', title='数学：练习', action='明天交练习册。\n明天不交练习册。'),
    dict(id='A3a substring rule, negation inverted',
         title='语文：读课文', action='不用抄写课文。\n抄写课文'),
    dict(id='A3b substring rule inside a shown clause',
         title='语文：读课文', action='不用背诵课文。\n背诵课文'),
    dict(id='A4a label fold (fictional): intent of C6',
         title='语文：A', action='今晚完成，明天早上交。\n提交要求：明天早上交练习册。'),
    dict(id='A4b label fold with a middle clause',
         title='语文：A', action='明天交练习册，然后读课文。\n提交要求：明天交练习册和卷子。'),
    dict(id='A4c negation scope after fold',
         title='语文：A', action='今晚完成，不用明天交。\n提交要求：明天交练习册。'),
    dict(id='A5a order-blind multiset: line is the title with the negation moved',
         title='语文：不用抄写，要朗读两遍', action='要抄写，不用朗读两遍'),
    dict(id='A5b negation in title, different quantity in line',
         title='英语：不需要录音，跟读两遍', action='需要录音，跟读三遍'),
    dict(id='A6a clause deletion inside a sentence',
         title='语文：读第3课', action='今天读第3课，明天交练习册。'),
    dict(id='A6b clause deletion, sentence keeps its own mark',
         title='语文：A', action='读第3课。\n读第3课，家长签字。'),
]


def h18_cases():
    data = json.loads(ORACLE.read_text('utf-8'))
    cases = []
    for m in data['matters']:
        units = [u['action'] for u in m.get('current_units', [])]
        negs = [n['fact'] for n in m.get('negative_constraints', [])]
        title = (m.get('subject') + '：' if m.get('subject') else '') + m['title_reference']
        action = '\n'.join(units + negs)
        cases.append(dict(id=m['id'], title=title, action=action, units=units, negs=negs))
    return cases


def main():
    out_lines = []

    def say(s=''):
        out_lines.append(s)
        print(s)

    say('== property test of family_agenda.action_lines (display projection) ==')
    say(f'repo: {REPO}  (HEAD 58973a6, working tree with the uncommitted change)')
    corpus = extract_corpus()
    say(f'corpus: {len(corpus)} (title, action) pairs found by AST scan of repo *.py')
    corpus_findings = 0
    for c in corpus:
        losses, errs, reorders, out = check(c['title'], c['action'])
        if not (losses or errs or reorders):
            continue
        corpus_findings += 1
        say(f'  [{c["src"]}] title={c["title"]!r}')
        say(f'      action={c["action"]!r}')
        say(f'      out   ={out!r}')
        for what, detail in losses:
            say(f'      LOSS {what!r} unreachable={detail!r}')
        for e in errs:
            say(f'      {e}')
        for r in reorders:
            say(f'      REORDER {r!r}')
        for note in trace(c['title'], c['action']):
            say(f'      trace: {note}')
    say(f'corpus findings: {corpus_findings}')

    say('\n== invented adversarial cases (fictional strings only) ==')
    red = []
    for c in ADVERSARIAL:
        losses, errs, reorders, out = check(c['title'], c['action'])
        bad = bool(losses or errs or reorders)
        if bad:
            red.append(c['id'])
        say(f'  [{c["id"]}] {"RED" if bad else "ok"}')
        say(f'      title ={c["title"]!r}')
        say(f'      action={c["action"]!r}')
        say(f'      out   ={out!r}')
        for what, detail in losses:
            say(f'      LOSS {what!r} unreachable={detail!r}')
        for e in errs:
            say(f'      {e}')
        for r in reorders:
            say(f'      REORDER {r!r}')
        for note in trace(c['title'], c['action']):
            say(f'      trace: {note}')
        ids = [x for x in c['action'].splitlines() if x.strip()]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pa, pb = plain(a), plain(b)
                if pa and pb:
                    ratio = difflib.SequenceMatcher(None, pa, pb).ratio()
                    if ratio >= 0.8:
                        say(f'      similarity {pa!r} vs {pb!r} = {ratio:.3f} (>= 0.80)')

    say(f'\nadversarial RED cases: {len(red)} -> {red}')

    say('\n== h18 oracle matters: every unit / negative constraint still readable? ==')
    for c in h18_cases():
        losses, errs, reorders, out = check(c['title'], c['action'])
        shown_plain = plain(c['title'] + ''.join(out))
        say(f'  [{c["id"]}] title={c["title"]!r}')
        for u in c['units']:
            missing = [f'{k}:{t}' for k, t in protected(u) if plain(t) not in shown_plain]
            say(f'      unit {u!r} missing={missing}')
        for n in c['negs']:
            missing = [f'{k}:{t}' for k, t in protected(n) if plain(t) not in shown_plain]
            say(f'      neg  {n!r} missing={missing}')
        say(f'      out={out!r}')
        for what, detail in losses:
            say(f'      LOSS {what!r} unreachable={detail!r}')
        for e in errs:
            say(f'      {e}')

    Path(__file__).with_name('property-report.txt').write_text('\n'.join(out_lines) + '\n', 'utf-8')


if __name__ == '__main__':
    main()

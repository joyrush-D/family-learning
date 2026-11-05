#!/usr/bin/env python3
"""Round-2: run the reviewer's own property_test.py against sha1 130d42f0.

The diagnostic tracer inside property_test.py names comparison helpers/constants of the
first implementation; the current one no longer has them. Only those missing names are
shimmed so the tracer can still describe which guard dropped a line; action_lines itself
is the real working-tree code.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, '/Users/joyrush/.local/share/family-learning/public-integration-20260926')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import family_agenda as fa  # noqa: E402


def _coverage(part, whole):
    if not part:
        return 1.0
    c, w = Counter(part), Counter(whole)
    return sum(min(c[k], w[k]) for k in c) / len(part)


for name, value in (('_TITLE_REPEAT', 0.90), ('_TITLE_PREFIX', 0.90), ('_NEAR_REPEAT', 0.80)):
    if not hasattr(fa, name):
        setattr(fa, name, value)
        print(f'# shim (diagnostic only): {name}={value}')
if not hasattr(fa, '_coverage'):
    fa._coverage = _coverage
    print('# shim (diagnostic only): _coverage = char-multiset overlap')
if not hasattr(fa, '_line_repeats'):
    fa._line_repeats = lambda line, shown: any(fa._covered_by(fa._plain(w), fa._plain(line)) for w in shown)
    print('# shim (diagnostic only): _line_repeats = _covered_by on whole shown lines')

import property_test as pt  # noqa: E402

pt.main()

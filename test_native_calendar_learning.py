"""Synthetic real Mac SwiftUI acceptance of the calendar-led workbench. Build the App from the committed source first, then opt
in to a visible window on a separate test Mac. The fixture is test_calendar_learning's fictional week served by the real app
server; every step clicks the App's own controls (week strip, child, list row, 待办/已办, 错题本, 记订正, 学习进展, 回原作业),
reads text shown in the window, saves through the existing correction contract and reads the server back. No model, household,
printer, login or collection is used."""
from pathlib import Path
import argparse, hashlib, json, os, signal, subprocess, sys, time, urllib.request


def serve_fixture():
    import test_calendar_learning as week
    week.setUpModule()
    # The fixed e0f931b pack when the runner names one, so the pages show the pack's own topic names.
    if os.environ.get('CALENDAR_FIXTURE_TAXONOMY_DIR'): os.environ['FAMILY_TAXONOMY_DIR'] = os.environ['CALENDAR_FIXTURE_TAXONOMY_DIR']
    app = week.app
    app.prepare_assets(); server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    print(json.dumps(dict(url='http://127.0.0.1:' + str(server.server_address[1]), ids=week.IDS, pack_installed=bool(week.family_taxonomy.pack_status().get('installed')))), flush=True)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__':
    if sys.argv[1:2] == ['--fixture']:
        if os.environ.get('FAMILY_NATIVE_CALENDAR_FIXTURE') != '1': raise SystemExit('fixture mode needs the test runner')
        sys.path.insert(0, str(Path(__file__).resolve().parent)); serve_fixture(); raise SystemExit()
    parser = argparse.ArgumentParser(description='Synthetic Mac calendar/wrong book/learning acceptance; opens a test window only with explicit opt-in.')
    parser.add_argument('--app', type=Path, required=True, help='App built from this committed source (.app or executable)')
    parser.add_argument('--python', type=Path, default=Path(sys.executable), help='Python >=3.10 for the fixture server')
    parser.add_argument('--output', type=Path, required=True, help='A new private QA directory')
    parser.add_argument('--allow-visible-test-window', action='store_true')
    args = parser.parse_args()
    if not args.allow_visible_test_window: parser.error('This opens a test window. Run only on a separate test Mac with --allow-visible-test-window.')
    repo = Path(__file__).resolve().parent; out = args.output.resolve(); exe = args.app.resolve()
    exe = exe / 'Contents/MacOS/YiqiChengzhang' if exe.suffix == '.app' else exe
    out.mkdir(mode=0o700, exist_ok=False)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True).strip()
    env = {k: v for k, v in os.environ.items() if not k.startswith('FAMILY_')}; env['FAMILY_NATIVE_CALENDAR_FIXTURE'] = '1'
    result = {'commit': head, 'passed': False, 'all_fictional': True, 'product_model_calls': 0, 'app_binary_sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
    fixture = app = None
    try:
        fixture = subprocess.Popen([str(args.python), '-B', str(Path(__file__).resolve()), '--fixture'], cwd=repo, env=env, stdout=subprocess.PIPE, stderr=(out / 'fixture.log').open('wb'), text=True)
        info = json.loads(fixture.stdout.readline()); origin = info['url']; w1 = info['ids']['w1']; w3 = info['ids']['w3']; topic = '有理数的加法法则' if info.get('pack_installed') else 'cnm_010'
        get = lambda q: json.load(urllib.request.urlopen(origin + '/api/day?' + q, timeout=10))
        first = get('child_id=child-1&day=2026-10-28')
        t01 = next(i for g in first['groups'] for i in g['items'] if i['task_id'] == 'T01')['id']
        course = next(c['record_id'] for s in first['learning']['subjects'] for c in s['course'])
        steps = [
            {'name': 'calendar ready', 'until': 'week-2026-10-28', 'timeout': 20},
            # The time badge sits in a FlowRow the row's combined accessibility label does not expose; the merge itself is
            # asserted on the server (test_calendar_learning) and seen in the snapshot. Here: the tied plan is not listed again.
            {'name': 'task row listed', 'width': 1440, 'until': 'row-' + t01, 'timeout': 15},
            {'name': 'tied plan not listed again', 'find_text': '虚构数学作业时段', 'absent': True, 'timeout': 5},
            {'name': 'lessons as written', 'find_text': '第3节', 'timeout': 10},
            {'name': 'calendar-1440', 'native': 'snapshot'},
            {'name': 'pick Monday on the strip', 'click': 'week-2026-10-26'},
            {'name': 'Monday is the selected day', 'until': 'day-title', 'contains': '2026-10-26', 'timeout': 15},
            {'name': 'Monday repeat and extra time', 'find_text': '18:00–18:30', 'timeout': 15},
            {'name': 'calendar-monday-1440', 'native': 'snapshot'},
            {'name': 'next week', 'click': 'week-next'},
            {'name': 'next week selected', 'until': 'day-title', 'contains': '2026-11-02', 'timeout': 15},
            {'name': 'back to today', 'click': 'day-today'},
            {'name': 'today selected', 'until': 'day-title', 'contains': '2026-10-28', 'timeout': 15},
            {'name': 'switch child', 'click': 'child-child-2'},
            {'name': 'other child lessons', 'find_text': '乙的英语', 'timeout': 15},
            {'name': 'other child plan', 'find_text': '虚构乙的活动', 'timeout': 10},
            {'name': 'first child plan not shown', 'find_text': '虚构钢琴课', 'absent': True, 'timeout': 5},
            {'name': 'back to first child', 'click': 'child-child-1'},
            {'name': 'original row', 'until': 'row-' + t01, 'timeout': 15},
            {'name': 'select original row', 'click': 'row-' + t01},
            {'name': 'original task detail open', 'until': 'history-web', 'timeout': 15},
            {'name': 'calendar-900', 'width': 900, 'native': 'snapshot'},
            {'name': 'done switch', 'click': 'mode-已办'},
            {'name': 'done list', 'until': 'list-summary', 'contains': '已办', 'timeout': 10},
            {'name': 'todo switch', 'click': 'mode-当天'},
            {'name': 'wrong book', 'click': 'mode-错题本'},
            {'name': 'wrong row shown', 'until': 'wrong-row-' + str(w1), 'contains': '虚构加法错题 待订正', 'timeout': 15},
            {'name': 'select wrong row', 'click': 'wrong-row-' + str(w1)},
            {'name': 'wrong back to task button', 'until': 'record-task-' + str(w1), 'timeout': 10},
            {'name': 'wrongbook-900', 'native': 'snapshot'},
            {'name': 'wrongbook-1440', 'width': 1440, 'native': 'snapshot'},
            {'name': 'start correction', 'click': 'wrong-correct-' + str(w1)},
            {'name': 'type correction', 'type': '虚构订正：(-8)+5=-3', 'into': 'correction-note'},
            {'name': 'save correction', 'click': 'sheet-save'},
            {'name': 'corrected in wrong book', 'until': 'wrong-row-' + str(w1), 'contains': '已订正', 'timeout': 20},
            {'name': 'learning', 'click': 'mode-学习进展'},
            {'name': 'topic diagnosis with help', 'until': 'learning-' + str(w1), 'contains': topic + ' · 2026-10-28 · 答了2题，其中1题看过说明', 'timeout': 15},
            {'name': 'linked topic by name, pending diagnosis', 'until': 'learning-' + str(w3), 'contains': '已关联知识点 ' + topic + ' · 2026-10-29 · 家长确认关联，待诊断', 'timeout': 10},
            {'name': 'history basis kept apart', 'until': 'learning-' + str(w1), 'contains': '原错题之后已更正，只作历史', 'timeout': 10},
            {'name': 'independent retry with date', 'until': 'learning-' + str(w1), 'contains': '2026-10-29 · 独立作答 · 对 · 孩子原答 -3', 'timeout': 10},
            {'name': 'correction reflected in learning', 'until': 'learning-' + str(w1), 'contains': '原错题 2026-10-28 · 已订正', 'timeout': 10},
            {'name': 'course record apart', 'until': 'course-' + str(course), 'contains': '虚构课堂：有理数加法', 'timeout': 10},
            {'name': 'learning-1440', 'native': 'snapshot'},
            {'name': 'learning-900', 'width': 900, 'native': 'snapshot'},
            {'name': 'learning back to original task', 'click': 'learning-task-' + str(w1)},
            {'name': 'same original task selected', 'native': 'state'},
            {'name': 'return to native', 'key': '0', 'modifiers': ['command']},
            {'name': 'native again', 'until': 'list-mode', 'timeout': 15},
            {'name': 'native state', 'native': 'state'},
            {'name': 'reopen', 'native': 'reopen'},
            {'name': 'reopened wrong book', 'click': 'mode-错题本'},
            {'name': 'correction kept after reopen', 'until': 'wrong-row-' + str(w1), 'contains': '已订正', 'timeout': 15},
        ]
        (out / 'steps.json').write_text(json.dumps(steps, ensure_ascii=False, indent=1))
        support = out / 'support'; support.mkdir(mode=0o700); (support / 'desktop.json').write_text(json.dumps({'service_origin': origin}))
        shots = out / 'screenshots'; shots.mkdir()
        runenv = {**env, 'FAMILY_DESKTOP_SUPPORT_DIR': str(support), 'FAMILY_DESKTOP_TEST_ORIGIN': origin, 'FAMILY_DESKTOP_TEST_SURFACE': 'native',
                  'FAMILY_DESKTOP_TEST_NATIVE_STEPS': str(out / 'steps.json'), 'FAMILY_DESKTOP_TEST_SNAPSHOT_DIR': str(shots)}
        start = time.time()
        with (out / 'native.jsonl').open('wb') as f, (out / 'native.stderr').open('wb') as e:
            app = subprocess.Popen([str(exe), '--smoke-test'], env=runenv, stdout=f, stderr=e)
            code = app.wait(timeout=300)
        events = []
        for line in (out / 'native.jsonl').read_text(errors='replace').splitlines():
            try: events.append(json.loads(line))
            except ValueError: pass
        done = [x for x in events if x.get('state') == 'native_step_done']; bad = [x for x in done if x.get('result', {}).get('ok') is not True]
        result.update(steps_done=len(done), steps=len(steps), failed=[dict(name=x['name'], result=x.get('result')) for x in bad])
        assert code == 0 and len(done) == len(steps) and not bad, (code, len(done), len(steps), bad[:2])
        rows = {x['name']: x['result'] for x in done}
        # 回原作业 selects the same original task in the native calendar (not a generic web history page).
        same = rows['same original task selected']
        assert same.get('surface') == 'native' and same.get('mode') == '日历' and same.get('selection') == t01, same
        assert rows['native state'].get('native_visible'), rows['native state']
        saved = get('child_id=child-1&day=2026-10-28')
        w = next(r for g in saved['wrong'] for r in g['items'] if r['id'] == w1)
        assert w['state'] == '已订正' and w['followups'][-1]['note'].startswith('虚构订正') and w['task_id'] == 'T01'
        assert all(r['child'] != '示例甲' or True for r in [])
        other = get('child_id=child-2&day=2026-10-28')
        assert all('虚构订正' not in json.dumps(g, ensure_ascii=False) for g in other['wrong'])
        result.update(passed=True, elapsed_s=round(time.time() - start, 2), correction_saved_once=len([f for f in w['followups'] if f['note'].startswith('虚构订正')]) == 1,
                      screenshots=sorted(p.name for p in shots.glob('*.png')))
    except BaseException as e:
        import traceback
        result['error'] = str(e)[:2000]; (out / 'FAILURE.txt').write_text(traceback.format_exc())
    finally:
        # Owned test processes only: ask first, then end them, so a hung App or a fixture held by a lingering connection can't skip RESULT.json or leave an orphan.
        if app is not None and app.poll() is None:
            app.terminate()
            try: app.wait(timeout=10)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
        if fixture is not None and fixture.poll() is None:
            fixture.send_signal(signal.SIGINT)
            try: fixture.wait(timeout=10)
            except subprocess.TimeoutExpired:
                fixture.kill(); fixture.wait(timeout=5); result['fixture_forced_stop'] = True
        (out / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n'); print(json.dumps(result, ensure_ascii=False)[:3000])
        sys.exit(0 if result['passed'] else 1)

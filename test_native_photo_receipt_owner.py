#!/usr/bin/env python3
"""Native photo receipts belong to the child context that sent them (PRD 5.1; fictional; no app, no window).

Run: python3 test_native_photo_receipt_owner.py OUTDIR [--sources TREE]
Compiles the real Swift WorkspaceStore/WorkspaceClient (macOS SDK, no NSApplication or window) against a loopback
fixture built on test_native_context.Backend. Every case makes exactly one explicit continue POST for child-1; the
fixture holds its reply until the contract has made a real store.change(child:) (late-*: to child-2; back-*: to child-2
and back to child-1) and that context has its own notice/problems/batches, then releases it. A receipt that returns into
another context must not change them; same-* show the same receipt still works without a change; 401/queued keep an
unknown continue on a failed or unfinished re-read. Evidence: fictional fixture replies, not the product backend or any
model; 0 product provider calls; outputs only under OUTDIR.
"""
import importlib.util, json, os, subprocess, sys, threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CASES = ['same-unknown', 'same-refused', 'same-saved', '401', 'queued', 'late-unknown', 'late-refused', 'late-saved', 'back-unknown', 'back-saved']
UNKNOWN = {'same-unknown', '401', 'queued', 'late-unknown', 'back-unknown'}
REFUSED = {'same-refused', 'late-refused'}
CONTRACT = r'''import AppKit
import Foundation
@main struct PhotoReceiptOwnerContract {
 @MainActor static func main() async {
  let client = WorkspaceClient(origin: ServiceOrigin.parse(CommandLine.arguments[1])!, ephemeral: true)
  let store = WorkspaceStore(client: client)
  let mode = CommandLine.arguments[2]
  var loginCalls = 0
  store.openLogin = { loginCalls += 1 }
  func control(_ path: String) async { _ = try? await client.get("/__fixture/" + path) }
  func reached() async -> Bool {
   for _ in 0..<500 {
    if let d = try? await client.get("/__fixture/status"), let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any], o["post_started"] as? Bool == true { return true }
    try? await Task.sleep(nanoseconds: 10_000_000)
   }
   return false
  }
  func shown() -> [String] { store.photoBatchesShown.map { "\($0.id)|\($0.child_id)|\($0.version)|\($0.state)" } }
  let unknown = "没有收到回执，结果未知；不会自动重发。", queued = "已排入后台，只重做未完成的步骤。"
  await store.load(); await store.loadPhotoBatches()
  guard let batch = store.photoBatchesShown.first(where: { $0.id == "pb-qa-existing" && $0.can_continue }) else { print("fixture missing target"); exit(2) }
  if CommandLine.arguments[3] == "1" { workspaceTestFaults = ["drop_reply"] }
  var checks: [String: Bool] = [:]
  async let sent: Void = store.continuePhotoBatch(batch)
  checks["post_reached_before_change"] = await reached()
  if mode.hasPrefix("late") || mode.hasPrefix("back") {
   store.change(child: "child-2"); await store.load(); await store.loadPhotoBatches()
   if mode.hasPrefix("back") { store.change(child: "child-1"); await store.load(); await store.loadPhotoBatches() }
   let owner = mode.hasPrefix("back") ? "child-1" : "child-2"
   // 这一轮自己已有的提示与原图读回入口（换孩子已清掉上一轮的）：迟到回执不能改它们。
   store.photoNotice = "QA：这一轮自己的提示。"
   store.photoProblems["image:QA-own"] = "原图暂时读不到；点“重新读取”再试，结果不受影响。"
   let notice = store.photoNotice, problems = store.photoProblems, batches = shown()
   checks["current_context_loaded"] = store.childID == owner && store.current?.child_id == owner && store.photoChild == owner && !batches.isEmpty
   await control("release"); await sent
   checks["current_notice_kept"] = store.photoNotice == notice
   checks["current_problems_kept"] = store.photoProblems == problems
   checks["current_batches_kept"] = shown() == batches
   checks["no_unknown_carried"] = store.photoContinueUnknown.isEmpty
   checks["still_on_current_child"] = store.childID == owner
  } else {
   await control("release"); await sent
   switch mode {
   case "same-saved":
    checks["saved_receipt_shown"] = store.photoNotice == queued && shown().contains("pb-qa-existing|child-1|1|queued")
   case "same-refused":
    checks["refusal_shown"] = !store.photoNotice.isEmpty && store.photoNotice != unknown && store.photoNotice != queued && store.photoProblems["batch"] == nil
   default:
    checks["unknown_shown"] = store.photoNotice == unknown && store.photoProblems["batch"] != nil
     && store.photoContinueUnknown == [PhotoContinueOrigin(child: "child-1", batch: "pb-qa-existing", version: 1)]
    if mode == "401" || mode == "queued" {
     await control("mode/" + mode); await store.loadPhotoBatches()
     checks["unknown_notice_retained"] = store.photoNotice == unknown
     checks["unknown_recovery_retained"] = store.photoProblems["batch"] != nil && !store.photoContinueUnknown.isEmpty
     if mode == "401" { checks["original_login_callback"] = store.loginRequired && loginCalls == 1 }
     if mode == "queued" { checks["queued_not_completed"] = shown() == ["pb-qa-existing|child-1|1|queued"] && !store.photoNotice.contains("处理已结束") }
    }
   }
  }
  if mode != "401" { checks["no_login_callback"] = loginCalls == 0 }
  let report: [String: Any] = ["mode": mode, "checks": checks, "child": store.childID, "loaded_child": store.current?.child_id ?? "", "photoNotice": store.photoNotice,
   "photoProblems": store.photoProblems, "photoChild": store.photoChild, "batches": shown(), "loginCalls": loginCalls, "windows": NSApp == nil ? 0 : -1]
  print(String(decoding: try! JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]), as: UTF8.self))
  exit(checks.values.allSatisfy { $0 } ? 0 : 1)
 }
}
'''


def batch(bid, child, version, state):
    return dict(id=bid, child_id=child, version=version, created='2026-01-01T19:00:00', state=state, pages=[], papers=[], pending=[], stale=[],
                progress=dict(done=1, total=2, failed=[]), can_continue=state == 'needs_attention')


def main():
    args = sys.argv[1:]
    sources = HERE
    if '--sources' in args:
        i = args.index('--sources'); sources = Path(args[i + 1]).resolve(); del args[i:i + 2]
    out = Path(args[0]).resolve(); out.mkdir(mode=0o700, parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('synthetic_native_context', str(HERE / 'test_native_context.py'))
    t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
    env = {k: v for k, v in os.environ.items() if not (k.startswith(('FAMILY_', 'OPENAI', 'ANTHROPIC', 'ARK_', 'DOUBAO', 'VOLC', 'TYPESAFE'))
                                                         or any(x in k.upper() for x in ['API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'PROXY']))}
    env['SDKROOT'] = subprocess.check_output(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip(); env['TMPDIR'] = str(out)
    (out / 'contract.swift').write_text(CONTRACT)
    binary = out / 'receipt-owner-contract'
    cmd = ['/usr/bin/xcrun', '--sdk', 'macosx', 'swiftc', '-swift-version', '5', '-parse-as-library', '-target', 'arm64-apple-macos13.0'] + [
        str(sources / 'packaging/macos/Sources' / f) for f in ['DesktopPolicy.swift', 'WorkspaceAPI.swift', 'Workspace.swift']] + [str(out / 'contract.swift'), '-o', str(binary)]
    built = subprocess.run(cmd, cwd=out, env=env, capture_output=True, text=True, timeout=300)
    (out / 'compile.json').write_text(json.dumps({'cmd': cmd, 'exit': built.returncode, 'stderr': built.stderr[-4000:]}, ensure_ascii=False, indent=1) + '\n')
    if built.returncode:
        print(built.stderr[-2000:]); sys.exit(2)
    results = []
    for case in CASES:
        state = dict(list='attention', post_started=False, release=threading.Event(), posts=[], gets=[])

        class Handler(t.Backend):
            def do_GET(self):
                u = urlparse(self.path); state['gets'].append(self.path)
                if u.path == '/__fixture/status': return self.reply(200, {'post_started': state['post_started']})
                if u.path == '/__fixture/release': state['release'].set(); return self.reply(200, {'ok': True})
                if u.path.startswith('/__fixture/mode/'): state['list'] = u.path.rsplit('/', 1)[1]; return self.reply(200, {'ok': True})
                if u.path == '/api/photo-batches':
                    child = parse_qs(u.query).get('child_id', [''])[0]
                    if state['list'] == '401': return self.reply(401, {'error': '虚构：请先登录'})
                    batches = {'child-1': [batch('pb-qa-existing', 'child-1', 1, 'queued' if state['list'] == 'queued' else 'needs_attention')],
                               'child-2': [batch('pb-qa-two', 'child-2', 3, 'needs_attention')]}.get(child, [])
                    return self.reply(200, {'child_id': child, 'batches': batches})
                return super().do_GET()

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                state['posts'].append({'path': urlparse(self.path).path, 'body': json.loads(raw or b'{}')}); state['post_started'] = True
                state['release'].wait(15)
                if case in REFUSED: return self.reply(409, {'error': '虚构：这一批已经变了，请重新读取。', 'code': 'photo_batch_changed'})
                return self.reply(200, batch('pb-qa-existing', 'child-1', 1, 'queued'))

        server = t.ThreadingHTTPServer(('127.0.0.1', 0), Handler); threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            run = subprocess.run([str(binary), 'http://127.0.0.1:%d' % server.server_address[1], case, '1' if case in UNKNOWN else '0'],
                                 cwd=out, env=env, capture_output=True, text=True, timeout=60)
        finally:
            state['release'].set(); server.shutdown(); server.server_close()
        posts = state['posts']
        one = len(posts) == 1 and posts[0]['path'] == '/api/photo-batch/continue' and posts[0]['body'].get('batch_id') == 'pb-qa-existing' and posts[0]['body'].get('version') == 1
        result = dict(case=case, exit=run.returncode, posts=posts, one_explicit_child1_post=one, gets=len(state['gets']), stderr=run.stderr[-2000:])
        try: result['output'] = json.loads(run.stdout.strip().splitlines()[-1])
        except Exception as error: result['parse_error'] = str(error); result['stdout'] = run.stdout[-2000:]
        result['passed'] = run.returncode == 0 and one and result.get('output', {}).get('windows') == 0
        results.append(result)
        print(json.dumps({'case': case, 'passed': result['passed'], 'exit': run.returncode, 'checks': result.get('output', {}).get('checks')}, ensure_ascii=False), flush=True)
    report = dict(sources=str(sources), results=results, passed=all(r['passed'] for r in results), windows=0, product_provider_calls=0, fixture_not_product_backend=True)
    (out / 'RESULT.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    sys.exit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()

"""原生工作台：选中的孩子/日期必须就是正在显示、可以操作的那份清单，读取失败时也一样。

无界面状态检查：用系统 swiftc 编译真实的 WorkspaceStore/WorkspaceClient 和最小命令行入口 test_native_context.swift
（不含 Sources/main.swift，不创建 NSApplication 或窗口，不打开 App、浏览器），接本进程起的本机虚构后台逐项操作。
只有虚构孩子与事项，不读写任何家庭记录。可见界面的验收另在独立测试 Mac 上做，本检查不能代替。
"""
import json
import platform
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "packaging" / "macos" / "Sources"
TODAY, NEXT = "2026-11-04", "2026-11-05"
CHILDREN = [{"id": "child-1", "name": "示例甲"}, {"id": "child-2", "name": "示例乙"}]
ITEMS = {
    ("child-1", TODAY): [("FICTION-A1", "数学", "虚构数学作业甲")],
    ("child-1", NEXT): [("FICTION-A2", "数学", "虚构数学作业甲·后一天")],
    ("child-2", TODAY): [("FICTION-B1", "语文", "虚构语文作业乙"), ("FICTION-B2", "英语", "虚构英语作业乙")],
    ("child-2", NEXT): [("FICTION-B3", "语文", "虚构语文作业乙·后一天")],
}
WRONG = {"child-1": [{"id": 9001, "day": TODAY, "created": TODAY + "T19:00:00", "title": "虚构错题甲", "subject": "数学", "note": "",
                      "note_truncated": False, "attachments": [], "followup_kind": "", "state": "待订正"}], "child-2": []}


def day_view(child, day):
    rows, groups = ITEMS[(child, day)], {}
    for item_id, subject, title in rows:
        groups.setdefault(subject, []).append({
            "id": item_id, "kind": "task", "task_id": "T-" + item_id, "title": title, "subject": subject, "category": "homework",
            "status": "待跟进", "closed": False, "pending_review": False, "origin": "school", "origin_label": "学校",
            "lines": ["完成" + title], "complete_words": "完成" + title, "facts": [], "today": True, "records": [], "wrong": []})
    return {"today": TODAY, "day": day, "child_id": child, "child_name": next(c["name"] for c in CHILDREN if c["id"] == child),
            "children": CHILDREN, "token": "synthetic-only", "groups": [{"subject": s, "items": i} for s, i in groups.items()],
            "closed": [], "wrong": [{"subject": "数学", "items": WRONG[child]}] if WRONG[child] else [],
            "counts": {"open": len(rows), "closed": 0, "today": len(rows)}}


class Backend(BaseHTTPRequestHandler):
    state = {"fail": 0, "day_reads": 0, "posts": 0}

    def log_message(self, *args):
        pass

    def reply(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url, state = urlparse(self.path), Backend.state
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/control":
            if "fail" in query:
                state["fail"] = int(query["fail"])
            return self.reply(200, state)
        if url.path == "/api/day":
            state["day_reads"] += 1
            if not state["fail"]:
                return self.reply(200, day_view(query.get("child_id", "child-1"), query.get("day", TODAY)))
        elif url.path == "/api/print/homework/materials" and not state["fail"]:
            return self.reply(200, {"files": []})
        self.reply(500, {"error": "虚构后台暂时读不到"})

    def do_POST(self):
        Backend.state["posts"] += 1
        self.reply(403, {"error": "虚构后台不接受写入"})


@unittest.skipUnless(shutil.which("xcrun"), "需要 macOS 系统 swiftc")
class NativeContextStateTests(unittest.TestCase):
    def test_selected_child_and_day_own_everything_shown_and_actionable(self):
        Backend.state.update(fail=0, day_reads=0, posts=0)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        arch = "arm64" if platform.machine() == "arm64" else "x86_64"
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "context-state"
            build = subprocess.run(
                ["xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-target", arch + "-apple-macos13.0",
                 *(str(SOURCES / name) for name in ("DesktopPolicy.swift", "WorkspaceAPI.swift", "Workspace.swift")),
                 str(HERE / "test_native_context.swift"), "-o", str(binary)],
                capture_output=True, text=True, timeout=600)
            self.assertEqual(build.returncode, 0, build.stderr[-4000:])
            run = subprocess.run([str(binary), "http://127.0.0.1:%d" % server.server_address[1]], capture_output=True, text=True, timeout=120)
        print(run.stdout)
        report = json.loads(run.stdout) if run.stdout.strip().startswith("{") else {}
        self.assertEqual(report.get("failures"), [], run.stdout[-6000:] + run.stderr[-2000:])
        self.assertEqual(run.returncode, 0)
        self.assertEqual(Backend.state["posts"], 0)


if __name__ == "__main__":
    unittest.main()

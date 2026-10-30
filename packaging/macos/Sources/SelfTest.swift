// --self-test：不开窗口、不联网，直接运行同源/外链/下载策略的正反例。
import Foundation

enum DesktopSelfTest {
    static func run() -> Int32 {
        var failures: [String] = []
        func check(_ ok: Bool, _ label: String) { if !ok { failures.append(label) } }
        for good in ["http://127.0.0.1:8765", "https://localhost:8443/", "http://[::1]:8765"] {
            check(ServiceOrigin.parse(good) != nil, "accept " + good)
        }
        for bad in ["http://192.168.1.2:8765", "http://127.0.0.1.evil.example:8765", "http://user:pw@127.0.0.1:8765",
                    "file:///etc/hosts", "http://127.0.0.1:8765/path", "ftp://127.0.0.1:21", "http://127.0.0.1:0",
                    "http://127.0.0.1:70000", "http://127.0.0.1:8765?x=1", "data:text/html,x", "javascript:alert(1)"] {
            check(ServiceOrigin.parse(bad) == nil, "reject origin " + bad)
        }
        let origin = ServiceOrigin.parse("http://127.0.0.1:8765")!
        let policy = DesktopPolicy(origin: origin, externalHosts: ["example.org"])
        func url(_ s: String) -> URL? { URL(string: s) }
        check(policy.navigation(url("http://127.0.0.1:8765/upload/abc")) == .allow, "same origin path")
        for bad in ["http://127.0.0.1:87650/", "http://127.0.0.1:876/", "http://127.0.0.1:8765@evil.example/",
                    "https://127.0.0.1:8765/", "http://localhost:8765/", "http://127.0.0.1.evil.example:8765/",
                    "http://127.0.0.1/", "file:///etc/hosts", "data:text/html,x", "javascript:alert(1)",
                    "x-apple.systempreferences:com.apple.preference.security", "https://user@example.org/",
                    "https://example.org:8443/", "ftp://example.org/", "https://evil-example.org/", "https://example.org.evil.example/"] {
            check(policy.navigation(url(bad)) == .block, "block " + bad)
        }
        check(policy.navigation(url("https://example.org/help")) == .external, "allowlisted external https")
        check(policy.navigation(url("http://example.org/")) == .external, "allowlisted external http")
        check(DesktopPolicy(origin: origin, externalHosts: []).navigation(url("https://example.org/")) == .block, "empty allowlist blocks")
        check(policy.download(url("blob:http://127.0.0.1:8765/1f2e")), "same-origin blob download")
        check(!policy.download(url("blob:http://127.0.0.1:87650/1f2e")), "other-port blob download")
        check(!policy.download(url("blob:https://example.org/1f2e")), "external blob download")
        check(origin.matches(scheme: "http", host: "127.0.0.1", port: 8765), "security origin")
        check(!origin.matches(scheme: "http", host: "127.0.0.1", port: 0), "security origin default port")
        let report: [String: Any] = ["self_test": failures.isEmpty ? "pass" : "fail", "failures": failures]
        if let data = try? JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]) { print(String(decoding: data, as: UTF8.self)) }
        return failures.isEmpty ? 0 : 1
    }
}

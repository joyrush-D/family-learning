// 一起成长桌面入口的同源与外链策略（纯 Foundation，可在 --self-test 中独立运行）。
// 只连接家长配置的本机原服务；按解析后的 scheme/host/port 完全相等判断，绝不按字符串前缀。
import Foundation

struct ServiceOrigin: Equatable {
    let scheme: String
    let host: String
    let port: Int

    static let loopbackHosts: Set<String> = ["127.0.0.1", "::1", "localhost"]

    var string: String { "\(scheme)://\(host.contains(":") ? "[\(host)]" : host):\(port)" }
    var url: URL { URL(string: string + "/")! }

    static func defaultPort(_ scheme: String) -> Int? { scheme == "https" ? 443 : scheme == "http" ? 80 : nil }

    static func host(_ components: URLComponents) -> String? {
        guard let raw = components.host?.lowercased(), !raw.isEmpty else { return nil }
        return raw.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
    }

    /// 只接受本机 http(s) 源：无账号密码、路径、查询或片段。
    static func parse(_ text: String) -> ServiceOrigin? {
        guard let c = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = c.scheme?.lowercased(), let fallback = defaultPort(scheme),
              c.user == nil, c.password == nil, c.query == nil, c.fragment == nil,
              c.path.isEmpty || c.path == "/", let host = host(c), loopbackHosts.contains(host) else { return nil }
        let port = c.port ?? fallback
        guard (1...65535).contains(port) else { return nil }
        return ServiceOrigin(scheme: scheme, host: host, port: port)
    }

    func matches(_ url: URL?) -> Bool {
        guard let url, let c = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let scheme = c.scheme?.lowercased(), let fallback = ServiceOrigin.defaultPort(scheme),
              c.user == nil, c.password == nil, let host = ServiceOrigin.host(c) else { return false }
        return scheme == self.scheme && host == self.host && (c.port ?? fallback) == port
    }

    /// WebKit 的安全源（默认端口记为 0）。
    func matches(scheme: String, host: String, port: Int) -> Bool {
        let h = host.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        let p = port == 0 ? (ServiceOrigin.defaultPort(scheme.lowercased()) ?? -1) : port
        return scheme.lowercased() == self.scheme && h == self.host && p == self.port
    }
}

enum NavigationDecision: Equatable { case allow, external, block }

struct DesktopPolicy {
    let origin: ServiceOrigin
    let externalHosts: Set<String>

    func navigation(_ url: URL?) -> NavigationDecision {
        guard let url else { return .block }
        if origin.matches(url) { return .allow }
        return external(url) ? .external : .block
    }

    /// 外部链接只交系统浏览器，且必须是白名单主机的 http(s) 默认端口、无账号密码。
    func external(_ url: URL) -> Bool {
        guard let c = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let scheme = c.scheme?.lowercased(), let fallback = ServiceOrigin.defaultPort(scheme),
              c.user == nil, c.password == nil, let host = ServiceOrigin.host(c),
              (c.port ?? fallback) == fallback else { return false }
        return externalHosts.contains(host)
    }

    /// 下载只来自原服务，或原服务页面生成的 blob（blob:<origin>/<id>）。
    func download(_ url: URL?) -> Bool {
        guard let url else { return false }
        if origin.matches(url) { return true }
        let text = url.absoluteString
        guard text.lowercased().hasPrefix("blob:"), let inner = URL(string: String(text.dropFirst(5))) else { return false }
        return origin.matches(inner)
    }
}

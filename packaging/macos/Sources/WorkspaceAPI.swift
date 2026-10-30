// 原生工作台的数据：只解码服务端 GET /api/day 已归类好的一个孩子一天（选哪些、排序、科目、日期角色都在服务端），
// 写入沿用原接口与原守卫（X-Family-Token、request_key 幂等、409 冲突）。只连 DesktopPolicy 的同一本机 origin，不跟随重定向。
import Foundation

struct DayFact: Decodable, Hashable {
    let role: String
    let label: String
    let value: String
    let known: Bool
    let state: String?
    let today: Bool?
}

struct SavedRecord: Decodable, Hashable, Identifiable {
    let id: Int
    let day: String
    let created: String
    let title: String
    let subject: String
    let note: String
    let note_truncated: Bool
    let attachments: [String]
    let followup_kind: String
    let related_record_id: Int?
    let state: String?
    let followups: [SavedRecord]?
}

struct Publication: Decodable, Hashable { let ref: String; let source_name: String; let sender: String }

/// 同一份作业已保存的进展，与网页 /api/state 的 task_progress 同一份：反馈、错题、知识点线索（不等于掌握）、独立再试、历史诊断。
struct TaskProgress: Decodable, Hashable { let feedback: Int; let wrong: Int; let wrong_ids: [Int]?; let clues: Int; let retries: Int; let history: Int }

struct DayItem: Decodable, Hashable, Identifiable {
    let id: String
    let kind: String
    let task_id: String
    let title: String
    let subject: String
    let category: String
    let status: String
    let closed: Bool
    let pending_review: Bool
    let origin: String
    let origin_label: String
    let lines: [String]
    let complete_words: String
    let facts: [DayFact]
    let today: Bool
    let records: [SavedRecord]
    let wrong: [SavedRecord]
    // 较早的后台没有这些字段时按“未提供”显示，不猜。
    let when: String?
    let publications: [Publication]?
    let published_at: String?
    let publisher: String?
    let progress: TaskProgress?
}

struct ItemGroup: Decodable, Hashable { let subject: String; let items: [DayItem] }
struct WrongGroup: Decodable, Hashable { let subject: String; let items: [SavedRecord] }
struct DayChild: Decodable, Hashable, Identifiable { let id: String; let name: String }

struct DayView: Decodable {
    let today: String
    let day: String
    let child_id: String
    let child_name: String?
    let children: [DayChild]
    let token: String
    let source_error: String?
    let groups: [ItemGroup]
    let closed: [ItemGroup]
    let wrong: [WrongGroup]
    let counts: [String: Int]
}

/// 一份原作业的资料，服务端 /api/print/homework/materials 原样：出处（学校消息原件、孩子报来的作业……）与已保存的读取状态
/// （已整理 / 有看不清的地方 / 尚未读清 / 等待整理 / 原件已保存）分开；不从文件名或出处猜“教师答案”等用途。
struct Material: Hashable, Identifiable {
    let id: String
    let name: String
    let origin: String
    let roleLabel: String
    let state: String
    let stateLabel: String
    let summary: String
    let unclear: [String]
    let explanation: String
}

struct MaterialState: Equatable {
    var files: [Material] = []
    var gap = ""        // 服务端说明的尚未读清/不可用原因；空表示没有已知缺口
    var error = ""      // 读取本身失败
    var loaded = false
}

enum PostOutcome {
    case saved([String: Any])
    case refused(status: Int, message: String, code: String)
    case unknown(String)   // 已发出但没拿到回执：保留同一 request_key 与输入，可用同一次提交重试
}

/// 测试模式（--smoke-test）才读的写入故障：按顺序作用于接下来的写入；正常使用从不注入。
var workspaceTestFaults: [String] = []

final class WorkspaceClient: NSObject, URLSessionTaskDelegate {
    let origin: ServiceOrigin
    var token = ""
    private var session: URLSession!
    /// 网页版工具同一 WKWebsiteDataStore 的 cookie（App 提供）。原生请求只带这个已核实 origin 的家长登录 cookie，
    /// 密钥只在内存里，不写配置、不进 URL；退出、过期或改密后由服务端照常拒绝（401），这里不另做判断。
    var sessionCookies: (@MainActor () async -> [HTTPCookie])?
    static let sessionCookie = "family_parent_session"

    /// 只认同一 host（不带 Domain 的 host-only cookie）、路径覆盖本服务、https 时必须 Secure、尚未过期的唯一一个家长登录 cookie。
    static func session(_ cookies: [HTTPCookie], for origin: ServiceOrigin, now: Date = Date()) -> HTTPCookie? {
        let path = origin.url.path.isEmpty ? "/" : origin.url.path
        let found = cookies.filter { c in
            c.name == sessionCookie && c.domain.lowercased() == origin.host.lowercased() && path.hasPrefix(c.path)
                && (origin.scheme != "https" || c.isSecure) && (c.expiresDate.map { $0 > now } ?? true)
        }
        return found.count == 1 ? found[0] : nil
    }

    func authorize(_ request: inout URLRequest) async {
        request.httpShouldHandleCookies = false
        guard let read = sessionCookies, let cookie = WorkspaceClient.session(await read(), for: origin) else { return }
        request.setValue(WorkspaceClient.sessionCookie + "=" + cookie.value, forHTTPHeaderField: "Cookie")
    }

    init(origin: ServiceOrigin, ephemeral: Bool) {
        self.origin = origin
        super.init()
        let configuration: URLSessionConfiguration = ephemeral ? .ephemeral : .default
        configuration.timeoutIntervalForRequest = 25
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
    }

    // 不跟随任何重定向（例如去登录页）：交给调用方说明“需要登录”，不离开原服务。
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }

    func url(_ path: String, _ query: [String: String] = [:]) -> URL {
        var c = URLComponents(url: origin.url, resolvingAgainstBaseURL: false)!
        c.path = path
        if !query.isEmpty { c.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) } }
        return c.url!
    }

    func message(_ data: Data, _ fallback: String) -> (String, String) {
        let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        return ((object?["error"] as? String) ?? fallback, (object?["code"] as? String) ?? "")
    }

    func get(_ path: String, _ query: [String: String] = [:]) async throws -> Data {
        var request = URLRequest(url: url(path, query))
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        await authorize(&request)
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard origin.matches(response.url), (200..<300).contains(status) else {
            if status == 401 || (300..<400).contains(status) { throw WorkspaceError("需要先登录家庭账号。", login: true) }
            throw WorkspaceError(message(data, "读取失败（\(status)），记录未更改，请重试。").0)
        }
        return data
    }

    func day(child: String, day: String) async throws -> DayView {
        var query: [String: String] = [:]
        if !child.isEmpty { query["child_id"] = child }
        if !day.isEmpty { query["day"] = day }
        let data = try await get("/api/day", query)
        do {
            let view = try JSONDecoder().decode(DayView.self, from: data)
            token = view.token
            return view
        } catch { throw WorkspaceError("清单格式无法读取，请更新后台或重试。") }
    }

    func materials(task: String) async -> MaterialState {
        do {
            let data = try await get("/api/print/homework/materials", ["task_id": task])
            let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
            let files = (object["files"] as? [[String: Any]] ?? []).compactMap { f -> Material? in
                guard let source = f["source"] as? [String: Any], let id = source["id"] as? String else { return nil }
                return Material(id: id, name: f["name"] as? String ?? "原件", origin: f["origin"] as? String ?? "",
                                roleLabel: f["role_label"] as? String ?? "原件（用途未注明）", state: f["state"] as? String ?? "saved",
                                stateLabel: f["label"] as? String ?? "原件已保存", summary: f["summary"] as? String ?? "",
                                unclear: f["unclear"] as? [String] ?? [], explanation: f["explanation"] as? String ?? "")
            }
            var gap = ""
            if let text = object["school_error"] as? String { gap = text }
            else if let dict = object["school_error"] as? [String: Any] { gap = dict["error"] as? String ?? dict["message"] as? String ?? "部分原件尚未读清，请看原件。" }
            return MaterialState(files: files, gap: gap, error: "", loaded: true)
        } catch {
            return MaterialState(files: [], gap: "", error: (error as? WorkspaceError)?.text ?? "资料暂时读不到，请重试。", loaded: true)
        }
    }

    func send(_ request: URLRequest) async -> PostOutcome {
        var request = request
        request.setValue(token, forHTTPHeaderField: "X-Family-Token")
        await authorize(&request)
        let fault = workspaceTestFaults.isEmpty ? "" : workspaceTestFaults.removeFirst()
        if fault == "fail_before_send" { return .refused(status: 0, message: "没有连上后台，这次没有保存；输入已保留，可以重试。", code: "not_sent") }
        do {
            let (data, response) = try await session.data(for: request)
            if fault == "drop_reply" { return .unknown("没有收到保存结果，不确定是否已保存；输入和这次提交标识都保留，可用同一次提交重试。") }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
            if (200..<300).contains(status) { return .saved(object) }
            let (text, code) = message(data, "没有保存（\(status)）。输入已保留。")
            if code == "csrf_expired", let fresh = object["token"] as? String { token = fresh }
            if status == 401 || (300..<400).contains(status) { return .refused(status: status, message: "需要重新登录：点下面的“登录家庭账号”，在登录窗口登录后回到这里，再点“用同一次提交重试”。输入已保留。", code: "login_required") }
            return .refused(status: status, message: text, code: code)
        } catch {
            let code = (error as? URLError)?.code
            if code == .cannotConnectToHost || code == .cannotFindHost || code == .notConnectedToInternet {
                return .refused(status: 0, message: "没有连上后台，这次没有保存；输入已保留，可以重试。", code: "not_sent")
            }
            return .unknown("没有收到保存结果，不确定是否已保存；输入和这次提交标识都保留，可用同一次提交重试。")
        }
    }

    func post(_ path: String, _ body: [String: Any]) async -> PostOutcome {
        var request = URLRequest(url: url(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys])
        return await send(request)
    }

    func upload(_ data: Data, name: String) async -> PostOutcome {
        var request = URLRequest(url: url("/api/upload"))
        request.httpMethod = "POST"
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue(name.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "photo", forHTTPHeaderField: "X-File-Name")
        request.httpBody = data
        return await send(request)
    }

    func studyVersion(child: String, day: String) async throws -> Int {
        let data = try await get("/api/study", ["child_id": child, "day": day])
        let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        return ((object?["day"] as? [String: Any])?["version"] as? Int) ?? 0
    }
}

struct WorkspaceError: Error { let text: String; let login: Bool; init(_ text: String, login: Bool = false) { self.text = text; self.login = login } }

/// 每次提交一个稳定标识：重试、丢回执后重发都用同一个，服务端据此不重复写。
func requestKey() -> String { "mac" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }

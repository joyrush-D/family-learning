// 一起成长桌面入口（内部候选）：AppKit 生命周期 + SwiftUI 原生每日工作台；富文档与次级旧功能经 WKWebView 打开本机原服务。关窗/退出只影响本窗口。
// 只有全新 Mac 上家长明确点击“安装后台”，或本入口安装的后台要更新/卸载时，才经包内运行时执行 backend.py；网页不获得任何原生桥接。
import AppKit
import SwiftUI
import WebKit

let bundleID = Bundle.main.bundleIdentifier ?? "local.yiqichengzhang.desktop"
let environment = ProcessInfo.processInfo.environment
let smoke = CommandLine.arguments.contains("--smoke-test")
let suggestedOrigin = "http://127.0.0.1:8765"

func defaultSupportDirectory() -> URL {
    FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent(bundleID, isDirectory: true)
}

func supportDirectory() -> URL {
    if let dir = environment["FAMILY_DESKTOP_SUPPORT_DIR"], !dir.isEmpty { return URL(fileURLWithPath: dir, isDirectory: true) }
    return defaultSupportDirectory()
}

// 桌面入口自己的 Support 目录只给本用户读写：目录 0700、设置文件 0600；不碰其他家庭配置或服务目录。
func preparePrivateSupport() throws {
    let dir = supportDirectory()
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: dir.path)
}

// --smoke-test 只用于虚构本地服务：必须另给独立 Support 目录和受信虚构 origin。测试时网页数据不落盘
// （不读写本用户默认会话的 Cookie/网页存储），不保存窗口位置；测试控制只从原生一侧执行，网页拿不到任何桥接。
let testOrigin: ServiceOrigin? = smoke ? environment["FAMILY_DESKTOP_TEST_ORIGIN"].flatMap(ServiceOrigin.parse) : nil

func testModeAllowed() -> Bool {
    guard let dir = environment["FAMILY_DESKTOP_SUPPORT_DIR"], !dir.isEmpty, testOrigin != nil else { return false }
    func real(_ url: URL) -> String { url.standardizedFileURL.resolvingSymlinksInPath().path }
    return real(URL(fileURLWithPath: dir, isDirectory: true)) != real(defaultSupportDirectory())
}

func emit(_ object: [String: Any]) {
    guard smoke else { return }
    // 网页返回值含 JSON 不能表示的内容时只报状态和文字描述，测试进程不因序列化中止。
    let safe: [String: Any] = JSONSerialization.isValidJSONObject(object) ? object : ["state": object["state"] as? String ?? "", "unserializable": String(describing: object)]
    guard let data = try? JSONSerialization.data(withJSONObject: safe, options: [.sortedKeys]) else { return }
    print(String(decoding: data, as: UTF8.self)); fflush(stdout)
}

struct DesktopConfig {
    let policy: DesktopPolicy?
    let problem: String  // 给家长看的说明，不含内部路径或文件格式
    let typed: String
    let externalHosts: [String]

    static let rule = "只接受这台 Mac 本机的地址：http(s)://127.0.0.1、[::1] 或 localhost 加端口，例如 \(suggestedOrigin)。"
    static var path: URL { supportDirectory().appendingPathComponent("desktop.json") }

    static func load() -> DesktopConfig {
        guard let data = try? Data(contentsOf: path) else {
            return DesktopConfig(policy: nil, problem: "", typed: suggestedOrigin, externalHosts: [])
        }
        let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let hosts = (object?["external_hosts"] as? [String]) ?? []
        guard let text = object?["service_origin"] as? String, let origin = ServiceOrigin.parse(text) else {
            return DesktopConfig(policy: nil, problem: "已保存的地址不能使用，请重新填写。" + rule,
                                 typed: (object?["service_origin"] as? String) ?? suggestedOrigin, externalHosts: hosts)
        }
        return DesktopConfig(policy: DesktopPolicy(origin: origin, externalHosts: Set(hosts.map { $0.lowercased() })),
                             problem: "", typed: origin.string, externalHosts: hosts)
    }

    /// 只在确认是一起成长网页后保存；原外链白名单原样保留。
    static func save(_ origin: ServiceOrigin, externalHosts: [String]) -> Bool {
        var object: [String: Any] = ["service_origin": origin.string]
        if !externalHosts.isEmpty { object["external_hosts"] = externalHosts }
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else { return false }
        do {
            try preparePrivateSupport()
            try data.write(to: path, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: path.path)
            return true
        } catch { return false }
    }
}

enum ProbeResult: String { case family, notFamily = "not_family_service", tls = "tls_untrusted", unreachable }

// 只探测这一个地址是否在、是否确为一起成长网页；不探测其他端口，不启动任何进程。
func probe(_ origin: ServiceOrigin, _ done: @escaping @MainActor (ProbeResult) -> Void) {
    var request = URLRequest(url: origin.url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 3)
    request.httpMethod = "GET"
    let session = URLSession(configuration: .ephemeral)
    session.dataTask(with: request) { data, response, error in
        let http = response as? HTTPURLResponse
        let body = String(decoding: data ?? Data(), as: UTF8.self)
        let location = http?.value(forHTTPHeaderField: "Location") ?? ""
        let family = http.map { origin.matches($0.url) && ((200..<300).contains($0.statusCode) && body.contains("app.bundle.js")
            || (300..<400).contains($0.statusCode) && location.contains("login")) } ?? false
        let tls = (error as NSError?)?.domain == NSURLErrorDomain && [NSURLErrorServerCertificateUntrusted, NSURLErrorServerCertificateHasBadDate,
            NSURLErrorServerCertificateNotYetValid, NSURLErrorServerCertificateHasUnknownRoot, NSURLErrorSecureConnectionFailed].contains((error as NSError?)?.code ?? 0)
        let result: ProbeResult = family ? .family : tls ? .tls : http != nil ? .notFamily : .unreachable
        DispatchQueue.main.async { done(result) }
        session.finishTasksAndInvalidate()
    }.resume()
}

// 后台安装/更新/卸载：只在家长明确点击后运行包内 backend.py，结果是一行 JSON，给家长看的文字由它提供（不含路径或命令）。
// 测试模式只把测试声明的虚构目录和端口交给它；正常使用从不带测试参数。技术细节只写进本入口自己的 Support 目录。
struct BackendReply {
    let ok: Bool
    let state: String
    let message: String
    let origin: String
    let raw: [String: Any]
}

let testProfile: String? = smoke ? environment["FAMILY_DESKTOP_TEST_PROFILE"].flatMap { $0.isEmpty ? nil : $0 } : nil

func backendAvailable() -> Bool {
    guard let res = Bundle.main.resourceURL else { return false }
    return FileManager.default.isExecutableFile(atPath: res.appendingPathComponent("runtime/bin/python3.11").path)
        && FileManager.default.fileExists(atPath: res.appendingPathComponent("app/packaging/macos/backend.py").path)
        && (!smoke || (testProfile != nil && testOrigin != nil))
}

func runBackend(_ command: String, fault: String? = nil, _ done: @escaping @MainActor (BackendReply) -> Void) {
    let failed = BackendReply(ok: false, state: "unavailable", message: "后台操作没有完成，未改动家庭资料；请稍后再试。", origin: "", raw: [:])
    guard backendAvailable(), let res = Bundle.main.resourceURL else { DispatchQueue.main.async { done(failed) }; return }
    var arguments = ["-I", "-B", res.appendingPathComponent("app/packaging/macos/backend.py").path, command,
                     "--resources", res.path, "--support", supportDirectory().path]
    if smoke, let profile = testProfile, let origin = testOrigin {
        arguments += ["--test-profile", profile, "--port", String(origin.port)]
        if let fault { arguments += ["--test-fault", fault] }
    }
    let process = Process()
    process.executableURL = res.appendingPathComponent("runtime/bin/python3.11")
    process.arguments = arguments
    process.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": NSHomeDirectory(), "LANG": "en_US.UTF-8", "TMPDIR": NSTemporaryDirectory()]
    process.standardInput = FileHandle.nullDevice
    let output = Pipe()
    process.standardOutput = output
    try? preparePrivateSupport()
    let logPath = supportDirectory().appendingPathComponent("backend.log").path
    let size = (try? FileManager.default.attributesOfItem(atPath: logPath)[.size] as? Int) ?? nil
    if size == nil || size! > 1_000_000 { FileManager.default.createFile(atPath: logPath, contents: nil, attributes: [.posixPermissions: 0o600]) }
    if let log = FileHandle(forWritingAtPath: logPath) { log.seekToEndOfFile(); process.standardError = log } else { process.standardError = FileHandle.nullDevice }
    DispatchQueue.global(qos: .userInitiated).async {
        var reply = failed
        do {
            try process.run()
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let line = String(decoding: data, as: UTF8.self).split(separator: "\n").last.map(String.init) ?? ""
            if let object = (try? JSONSerialization.jsonObject(with: Data(line.utf8))) as? [String: Any], let message = object["message"] as? String {
                reply = BackendReply(ok: object["ok"] as? Bool == true, state: object["state"] as? String ?? "", message: message,
                                     origin: object["origin"] as? String ?? "", raw: object)
            }
        } catch {}
        let final = reply
        DispatchQueue.main.async { done(final) }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, NSMenuItemValidation, WKHTTPCookieStoreObserver {
    var config = DesktopConfig.load()
    var window: NSWindow?
    var webView: WKWebView?
    var statusLabel = NSTextField(wrappingLabelWithString: "")
    var retryButton = NSButton(title: "重试", target: nil, action: nil)
    var changeButton = NSButton(title: "更改地址", target: nil, action: nil)
    var statusView = NSStackView()
    // 首次使用/地址不能用时的最小原生表单：填写或确认本机地址，确认是一起成长网页后才保存并打开原清单。
    var setupView = NSStackView()
    var setupField = NSTextField(string: "")
    var setupMessage = NSTextField(wrappingLabelWithString: "")
    var setupButton = NSButton(title: "连接并打开", target: nil, action: nil)
    var setupBusy = false
    // 全新 Mac 上的“安装后台”：只在只读检查确认没有已有设置、安装、已知服务且端口空闲时显示。
    var installNote = NSTextField(wrappingLabelWithString: "")
    var installButton = NSButton(title: "在这台 Mac 上安装后台", target: nil, action: nil)
    var backendBusy = false
    var backendState = ""
    var backendReplies: [[String: Any]] = []
    var faultPending: String? = smoke ? environment["FAMILY_DESKTOP_TEST_UPDATE_FAULT"].flatMap { $0.isEmpty ? nil : $0 } : nil
    var installScripted = smoke && environment["FAMILY_DESKTOP_TEST_INSTALL"] == "1"
    var popups: [NSWindow] = []
    var loginPending = false      // 工作台发起的登录：同一 origin 的家长登录 cookie 出现后自动回到工作台
    var loginWindow: NSWindow?    // 单独的登录窗口：工作台和打开着的填写框都不动
    var loginWeb: WKWebView?
    var loginBaseline = ""        // 打开登录窗口时已有的登录 cookie；换成新的才算登录完成
    var observingCookies = false
    // 主界面是原生工作台；网页只在家长打开“网页版工具”、原件或照片检查时载入。测试默认沿用原网页验收，声明 native 才验原生工作台。
    var surface = smoke ? (environment["FAMILY_DESKTOP_TEST_SURFACE"] == "native" ? "native" : "web") : "native"
    var workspace: WorkspaceStore?
    var workspaceHost: NSHostingController<WorkspaceView>?
    var container: NSView?
    var nativeRan = false
    var attempts = 0
    var mainLoads = 0
    var blocked: [String] = []
    var closeApproved = false
    var quitApproved = false
    var lastQuitReply: Bool?
    var smokeQuitRequests = 0  // read-only test observation; no production branch changes
    var lockHandle: Int32 = -1
    var scriptedInputs: [String] = smoke ? ((try? JSONSerialization.jsonObject(with: Data((environment["FAMILY_DESKTOP_TEST_SETUP_INPUTS"] ?? "[]").utf8))) as? [String] ?? []) : []
    var testEvents: [[String: Any]] = []
    var setupShots = 0
    var testDiscardNext = false  // 测试声明下一次未保存确认选“放弃”；默认仍是“继续编辑”
    var smokeActivity: NSObjectProtocol?
    let retrySeconds = Double(environment["FAMILY_DESKTOP_RETRY_SECONDS"] ?? "") ?? 3
    let maxRetries = Int(environment["FAMILY_DESKTOP_MAX_RETRIES"] ?? "") ?? 10
    let configuration: WKWebViewConfiguration = {
        let c = WKWebViewConfiguration()
        // 正常使用：登录态保存在本用户的应用数据目录；测试：不落盘的独立数据，不碰默认会话。
        c.websiteDataStore = smoke ? .nonPersistent() : .default()
        c.preferences.javaScriptCanOpenWindowsAutomatically = false
        return c
    }()

    func applicationWillFinishLaunching(_ notification: Notification) {
        // 单实例：第二次打开只聚焦锁持有者的窗口，不刷新、不丢草稿。
        try? preparePrivateSupport()
        // 早先写下的设置文件同样收紧为仅本用户可读写。
        if FileManager.default.fileExists(atPath: DesktopConfig.path.path) {
            try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: DesktopConfig.path.path)
        }
        let lockPath = supportDirectory().appendingPathComponent("desktop.lock").path
        lockHandle = open(lockPath, O_CREAT | O_RDWR, 0o600)
        if lockHandle < 0 || flock(lockHandle, LOCK_EX | LOCK_NB) != 0 {
            let holder = (try? String(contentsOfFile: lockPath, encoding: .utf8)).flatMap { Int32($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
            if let holder, holder != getpid() { NSRunningApplication(processIdentifier: holder)?.activate(options: []) }
            emit(["state": "focused_existing_instance"])
            exit(0)
        }
        let pid = "\(getpid())"
        _ = ftruncate(lockHandle, 0)
        _ = pid.withCString { write(lockHandle, $0, strlen($0)) }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if smoke { smokeActivity = ProcessInfo.processInfo.beginActivity(options: .userInitiated, reason: "虚构验收") }  // 测试期间不被 App Nap 降速
        NSApp.mainMenu = menu()
        showWindow()
        NSApp.activate(ignoringOtherApps: true)
        refreshBackendStatus()
    }

    // 已连接过后台时只读查看：本入口安装的后台有新版本，菜单里才提供“更新后台”；从不自动更新。
    func refreshBackendStatus() {
        guard backendAvailable(), FileManager.default.fileExists(atPath: DesktopConfig.path.path) else { return }
        runBackend("status") { reply in
            self.backendState = reply.state
            if testProfile != nil { emit(["state": "backend_status", "result": reply.state]) }
            if reply.state == "update_available" { self.window?.subtitle = "可以更新后台：菜单“一起成长”→“更新后台到这个版本…”" }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow(); return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    // 退出（含 Cmd+Q）先按页面原有 beforeunload 判断；有未保存内容时默认继续编辑。后台服务不受影响。
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if smoke { smokeQuitRequests += 1 }
        if backendBusy && !quitApproved {
            if !smoke {
                let alert = NSAlert(); alert.messageText = "后台正在安装或更新"
                alert.informativeText = "请等它完成后再退出，大约一两分钟。"; alert.addButton(withTitle: "好"); alert.runModal()
            }
            return .terminateCancel
        }
        guard !quitApproved, webView != nil || workspace != nil else { return .terminateNow }
        unsavedAny { dirty in
            let reply = !dirty || self.confirmDiscard("退出")
            self.lastQuitReply = reply
            NSApp.reply(toApplicationShouldTerminate: reply)
        }
        return .terminateLater
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard sender === window, !closeApproved, webView != nil || workspace != nil else { return true }
        unsavedAny { dirty in
            if !dirty || self.confirmDiscard("关闭窗口") { self.closeApproved = true; sender.close() }
        }
        return false
    }

    func windowWillClose(_ notification: Notification) {
        guard let closing = notification.object as? NSWindow else { return }
        if closing === window { window = nil; webView = nil; closeApproved = false }
        popups.removeAll { $0 === closing }
        if closing === loginWindow { loginWindow = nil; loginWeb = nil; loginPending = false }
    }

    /// 原生弹出层有未保存输入，或网页版页面自己的 beforeunload 判断有草稿，都算未保存。
    func unsavedAny(_ done: @escaping (Bool) -> Void) {
        if workspace?.hasUnsavedInput == true { return done(true) }
        guard let web = webView, surface == "web" else { return done(false) }
        unsaved(web, done)
    }

    func unsaved(_ web: WKWebView, _ done: @escaping (Bool) -> Void) {
        guard config.policy?.origin.matches(web.url) == true else { return done(false) }
        let js = "(()=>{try{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented===true}catch(_){return true}})()"
        web.evaluateJavaScript(js) { value, error in done(error != nil || (value as? Bool) == true) }
    }

    func confirmDiscard(_ action: String) -> Bool {
        if smoke {
            let discard = testDiscardNext; testDiscardNext = false
            testEvents.append(["discard_prompt": action, "choice": discard ? "放弃" : "继续编辑"]); return discard
        }
        let alert = NSAlert()
        alert.messageText = "还有未保存的内容"
        alert.informativeText = "选择“继续编辑”可保留当前输入。放弃只影响这个窗口，后台服务继续运行。"
        alert.addButton(withTitle: "继续编辑")
        alert.addButton(withTitle: "放弃并" + action)
        return alert.runModal() == .alertSecondButtonReturn
    }

    func showWindow() {
        if let window { window.makeKeyAndOrderFront(nil); return }
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        w.title = "一起成长"
        w.minSize = NSSize(width: 360, height: 560)
        w.delegate = self
        w.isReleasedWhenClosed = false
        if !smoke { w.setFrameAutosaveName("FamilyDesktopMain") }
        let web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.translatesAutoresizingMaskIntoConstraints = false
        let container = NSView()
        container.addSubview(web)
        statusView.orientation = .vertical
        statusView.alignment = .centerX
        statusView.spacing = 12
        statusView.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.alignment = .center
        statusLabel.preferredMaxLayoutWidth = 320
        retryButton.target = self
        retryButton.action = #selector(retry)
        changeButton.target = self
        changeButton.action = #selector(changeAddress)
        statusView.setViews([statusLabel, retryButton, changeButton], in: .center)
        container.addSubview(statusView)
        let title = NSTextField(labelWithString: "连接本机一起成长服务")
        title.font = .boldSystemFont(ofSize: 17)
        let hint = NSTextField(wrappingLabelWithString: "填写这台 Mac 上一起成长后台的网页地址，或直接使用下面的默认地址。桌面入口不会启动、停止或更改已有后台。")
        hint.preferredMaxLayoutWidth = 300
        setupMessage.preferredMaxLayoutWidth = 300
        setupMessage.textColor = .secondaryLabelColor
        setupField.placeholderString = suggestedOrigin
        setupField.target = self
        setupField.action = #selector(submitSetup)
        setupField.translatesAutoresizingMaskIntoConstraints = false
        setupField.widthAnchor.constraint(equalToConstant: 300).isActive = true
        setupButton.target = self
        setupButton.action = #selector(submitSetup)
        setupButton.keyEquivalent = "\r"
        setupView.orientation = .vertical
        setupView.alignment = .leading
        setupView.spacing = 10
        setupView.translatesAutoresizingMaskIntoConstraints = false
        installNote.preferredMaxLayoutWidth = 300
        installButton.target = self
        installButton.action = #selector(installBackend)
        installNote.isHidden = true
        installButton.isHidden = true
        setupView.setViews([title, hint, setupField, setupButton, setupMessage, installNote, installButton], in: .top)
        setupView.isHidden = true
        container.addSubview(setupView)
        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: container.leadingAnchor), web.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            web.topAnchor.constraint(equalTo: container.topAnchor), web.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            statusView.centerXAnchor.constraint(equalTo: container.centerXAnchor), statusView.centerYAnchor.constraint(equalTo: container.centerYAnchor),
            statusView.widthAnchor.constraint(lessThanOrEqualTo: container.widthAnchor, constant: -32),
            setupView.centerXAnchor.constraint(equalTo: container.centerXAnchor), setupView.centerYAnchor.constraint(equalTo: container.centerYAnchor),
            setupView.widthAnchor.constraint(lessThanOrEqualTo: container.widthAnchor, constant: -32),
        ])
        w.contentView = container
        self.container = container
        if smoke || w.frame.origin == .zero { w.center() }
        window = w; webView = web
        w.makeKeyAndOrderFront(nil)
        attempts = 0
        connect()
    }

    func status(_ text: String, retry: Bool) {
        restoreContainer()
        webView?.isHidden = true
        setupView.isHidden = true
        statusView.isHidden = false
        statusLabel.stringValue = text
        retryButton.isHidden = !retry
        changeButton.isHidden = !retry
    }

    @objc func retry() { attempts = 0; config = DesktopConfig.load(); connect() }

    // 页面已打开时先按原有未保存判断：默认“继续编辑”保留原画面、草稿和原地址；明确放弃后才显示地址表单，新地址确认后才重新载入。
    // 首次使用或失败状态下没有可见网页，直接显示表单，不多问。
    @objc func changeAddress() {
        let typed = config.policy?.origin.string ?? config.typed
        guard webView?.isHidden == false || nativeVisible else { attempts = 0; return showSetup("", typed: typed) }
        unsavedAny { dirty in
            guard !dirty || self.confirmDiscard("更改地址") else { return }
            self.attempts = 0
            self.showSetup("", typed: typed)
        }
    }

    func showSetup(_ message: String, typed: String) {
        restoreContainer()
        webView?.isHidden = true
        statusView.isHidden = true
        setupView.isHidden = false
        setupField.stringValue = typed
        setupField.isEnabled = true
        setupButton.isEnabled = true
        setupMessage.stringValue = message
        setupMessage.isHidden = message.isEmpty
        window?.makeFirstResponder(setupField)
        emit(["state": "setup_shown", "typed": typed, "message": message])
        if smoke { setupShots += 1; let name = "setup-\(setupShots)"; Task { await self.snapshot(name) } }
        offerInstall()
        nextScriptedSetup()
    }

    // 没有已保存的连接设置时才做只读检查；确认全新才显示“安装后台”，已有后台或端口被占只说明原因。
    func offerInstall(_ prefix: String = "") {
        installNote.isHidden = true
        installButton.isHidden = true
        guard !backendBusy, backendAvailable(), !FileManager.default.fileExists(atPath: DesktopConfig.path.path) else {
            if installScripted { installScripted = false; finishSmoke() }
            return
        }
        runBackend("check") { reply in
            if testProfile != nil { emit(["state": "backend_check", "result": reply.state, "message": reply.message]) }
            guard !self.setupView.isHidden, !self.backendBusy else { return }
            self.installNote.stringValue = (prefix.isEmpty ? "" : prefix + "\n") + reply.message
            self.installNote.isHidden = reply.state == "unavailable"
            self.installButton.isHidden = reply.state != "fresh"
            self.installButton.isEnabled = true
            guard self.installScripted else { return }
            self.installScripted = false
            if reply.state == "fresh" {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { self.installButton.performClick(nil) }
            } else {
                Task { await self.snapshot("install-not-offered") }
                self.finishSmoke()
            }
        }
    }

    @objc func installBackend() {
        guard !backendBusy, !installButton.isHidden else { return }
        backendBusy = true
        installButton.isEnabled = false; setupButton.isEnabled = false; setupField.isEnabled = false
        installNote.stringValue = "正在安装后台，通常一两分钟；资料只保存在这台 Mac 上，装好后直接打开清单。"
        emit(["state": "backend_install_started"])
        Task { await self.snapshot("install-running") }
        runBackend("install") { reply in
            self.backendBusy = false
            self.backendReplies.append(reply.raw)
            emit(["state": "backend_install", "ok": reply.ok, "result": reply.state, "message": reply.message])
            self.setupButton.isEnabled = true; self.setupField.isEnabled = true
            guard reply.ok, let origin = ServiceOrigin.parse(reply.origin) else {
                Task { await self.snapshot("install-failed") }
                self.offerInstall(reply.message)
                return self.nextScriptedSetup()
            }
            self.backendState = "current"
            self.setupField.stringValue = origin.string
            self.submitSetup()  // 与“连接并打开”同一确认：确为一起成长网页后才保存地址并打开原清单
        }
    }

    func confirmBackend(_ title: String, _ detail: String, _ action: String) -> Bool {
        if smoke { testEvents.append(["backend_confirm": title]); return true }
        let alert = NSAlert(); alert.messageText = title; alert.informativeText = detail
        alert.addButton(withTitle: action); alert.addButton(withTitle: "取消")
        return alert.runModal() == .alertFirstButtonReturn
    }

    @objc func updateBackend() { backendChange("update") }
    @objc func uninstallBackend() { backendChange("uninstall") }

    // 更新/卸载先按页面原有未保存判断（默认继续编辑），再请家长确认；只处理本入口安装且记录可核对的后台。
    func backendChange(_ command: String) {
        let update = command == "update"
        guard !backendBusy, update ? backendState == "update_available" : ["update_available", "current"].contains(backendState) else { return }
        let go = {
            guard self.confirmBackend(update ? "更新后台到这个版本？" : "卸载后台？",
                                      update ? "更新前会先做完整备份并核对；更新时网页暂停一两分钟。没有完成会自动恢复原版本，资料都保留。"
                                             : "会停止后台并删除程序文件；家庭资料和备份全部保留在这台 Mac 上，不会删除。",
                                      update ? "更新" : "卸载") else { return }
            self.backendBusy = true
            self.status(update ? "正在更新后台，请稍候；完成后自动重新打开。" : "正在卸载后台…", retry: false)
            let fault = update ? self.faultPending : nil
            if update { self.faultPending = nil }
            runBackend(command, fault: fault) { reply in
                self.backendBusy = false
                self.backendReplies.append(reply.raw)
                emit(["state": "backend_" + command, "ok": reply.ok, "result": reply.state, "message": reply.message])
                self.window?.subtitle = reply.message
                if update || !reply.ok {
                    if reply.ok { self.backendState = "current" }
                    self.attempts = 0
                    self.connect()
                } else {
                    self.backendState = reply.state
                    self.status(reply.message, retry: false)
                }
                if !smoke { let alert = NSAlert(); alert.messageText = reply.message; alert.addButton(withTitle: "好"); alert.runModal() }
            }
        }
        if webView?.isHidden == false || nativeVisible {
            unsavedAny { dirty in if !dirty || self.confirmDiscard(update ? "更新后台" : "卸载后台") { go() } }
        } else { go() }
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        if item.action == #selector(updateBackend) { return !backendBusy && backendState == "update_available" }
        if item.action == #selector(uninstallBackend) { return !backendBusy && ["update_available", "current"].contains(backendState) }
        if item.action == #selector(menuWorkbench) { return surface == "web" && config.policy != nil && webView?.isHidden == false }
        if [#selector(menuPrintOriginal), #selector(menuPrintReference)].contains(item.action) { return nativeVisible && workspace?.sheet == nil && workspace?.selected?.task_id.isEmpty == false }
        // 补录只记在已读到的所选孩子这一天；切换孩子、前后一天、重读在读失败时照常可用（已知孩子可切回、可重试）。
        if item.action == #selector(menuOral) { return nativeVisible && workspace?.sheet == nil && workspace?.current != nil }
        if [#selector(menuPrev), #selector(menuNext), #selector(menuToday), #selector(menuChild1), #selector(menuChild2), #selector(menuReload), #selector(menuWebTools)].contains(item.action) {
            return nativeVisible && workspace?.sheet == nil && workspace?.view != nil
        }
        return true
    }

    @objc func submitSetup() {
        guard !setupBusy else { return }
        guard let origin = ServiceOrigin.parse(setupField.stringValue) else {
            setupMessage.stringValue = "地址不正确，未保存。" + DesktopConfig.rule
            setupMessage.isHidden = false
            emit(["state": "setup_rejected", "message": setupMessage.stringValue])
            return nextScriptedSetup()
        }
        setupBusy = true
        setupField.isEnabled = false
        setupButton.isEnabled = false
        setupMessage.stringValue = "正在连接 \(origin.string)…"
        setupMessage.isHidden = false
        probe(origin) { result in
            self.setupBusy = false
            self.setupField.isEnabled = true
            self.setupButton.isEnabled = true
            switch result {
            case .family:
                guard DesktopConfig.save(origin, externalHosts: self.config.externalHosts) else {
                    self.setupMessage.stringValue = "已连上，但没能保存这个地址，请再点一次“连接并打开”。"
                    emit(["state": "setup_save_failed"]); return self.nextScriptedSetup()
                }
                self.config = DesktopConfig.load()
                emit(["state": "setup_saved", "origin": origin.string])
                self.attempts = 0
                return self.connect()
            case .notFamily: self.setupMessage.stringValue = "\(origin.string) 上的服务不是一起成长网页，未保存。请核对端口。"
            case .tls: self.setupMessage.stringValue = "这个地址的证书不受这台 Mac 信任，未保存。桌面入口不会忽略证书错误。"
            case .unreachable: self.setupMessage.stringValue = "连不上 \(origin.string)，未保存。请确认一起成长后台已在运行、端口正确后再试；桌面入口不会自行启动后台或改用其他端口。"
            }
            emit(["state": "setup_probe_failed", "reason": result.rawValue, "message": self.setupMessage.stringValue])
            self.setupShots += 1; let name = "setup-\(self.setupShots)-\(result.rawValue)"
            Task { await self.snapshot(name) }
            self.nextScriptedSetup()
        }
    }

    // 测试模式：把虚构输入逐个填进同一原生输入框并点同一按钮；输入用完仍未连上则结束测试。
    func nextScriptedSetup() {
        guard smoke else { return }
        // 页面已打开后由页面检查负责结束测试；这里只在首用表单阶段输入用完时结束。
        guard !scriptedInputs.isEmpty else { if mainLoads == 0 && !installScripted && !backendBusy { finishSmoke() }; return }
        let text = scriptedInputs.removeFirst()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            guard !self.setupView.isHidden else { return }
            self.setupField.stringValue = text
            self.setupButton.performClick(nil)
        }
    }

    func failed(_ text: String, _ state: String) {
        status(text, retry: true)
        emit(["state": state, "attempts": attempts, "message": text])
        if smoke && !scriptedInputs.isEmpty {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { self.changeButton.performClick(nil) }
        } else { finishSmoke() }
    }

    func connect() {
        guard let policy = config.policy else {
            emit(["state": "unconfigured"])
            return showSetup(config.problem, typed: config.typed)
        }
        attempts += 1
        status("正在连接本机一起成长服务…", retry: false)
        probe(policy.origin) { self.probed($0, policy: policy) }
    }

    func probed(_ result: ProbeResult, policy: DesktopPolicy) {
        guard let web = webView else { return }
        switch result {
        case .family:
            if surface == "native" { return showWorkspace(policy) }
            status("正在打开…", retry: false)
            web.load(URLRequest(url: policy.origin.url))
        case .tls:
            failed("本机服务的证书不受这台 Mac 信任，未打开。桌面入口不会忽略证书错误。", "tls_untrusted")
        case .notFamily:
            failed("\(policy.origin.string) 上的服务不是一起成长网页，未打开。可点“更改地址”核对端口。", "not_family_service")
        case .unreachable where attempts < maxRetries:
            status("暂时连不上本机一起成长服务（第\(attempts)次）。后台可能尚未启动，稍后自动重试。", retry: true)
            DispatchQueue.main.asyncAfter(deadline: .now() + retrySeconds) { [weak self] in
                guard let self, self.webView === web, self.webView?.isHidden == true, !self.statusView.isHidden, self.attempts > 0 else { return }
                self.connect()
            }
        case .unreachable:
            failed("仍连不上本机一起成长服务，已停止自动重试。桌面入口不会自行启动服务或改用其他端口；请确认后台已运行后点“重试”，或点“更改地址”。", "unavailable")
        }
    }

    // MARK: 导航：只留在原服务同源内；白名单外链交系统浏览器；其余（file/data/javascript/其他程序）一律阻止。
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void) {
        guard let policy = config.policy else { return decisionHandler(.cancel) }
        let url = action.request.url
        if action.shouldPerformDownload { return decisionHandler(policy.download(url) ? .download : .cancel) }
        if action.targetFrame?.isMainFrame == false, let text = url?.absoluteString, text == "about:blank" || text == "about:srcdoc" {
            return decisionHandler(.allow)
        }
        switch policy.navigation(url) {
        case .allow: decisionHandler(.allow)
        case .external:
            decisionHandler(.cancel)
            if action.navigationType == .linkActivated, let url { NSWorkspace.shared.open(url) }
        case .block:
            decisionHandler(.cancel)
            blocked.append(url?.absoluteString ?? "")
            window?.subtitle = "已阻止离开本机服务的链接"
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping @MainActor @Sendable (WKNavigationResponsePolicy) -> Void) {
        guard config.policy?.origin.matches(response.response.url) == true else { return decisionHandler(.cancel) }
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard webView === self.webView else { return }
        statusView.isHidden = true
        setupView.isHidden = true
        webView.isHidden = false
        mainLoads += 1
        if smoke && mainLoads == 1 && environment["FAMILY_DESKTOP_TEST_SURFACE"] != "native" { Task { await self.runSmokeChecks(webView) } }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { loadFailed(webView, error) }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { loadFailed(webView, error) }

    func loadFailed(_ web: WKWebView, _ error: Error) {
        let code = (error as NSError).code
        if code == NSURLErrorCancelled || (error as NSError).domain == "WebKitErrorDomain" && code == 102 { return }  // 被策略取消/转为下载
        guard web === webView, web.url == nil || web.isHidden else { return }
        attempts = 0
        status("打开本机一起成长服务失败：\(error.localizedDescription)", retry: true)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        status("页面进程意外结束；点“重试”重新打开。未保存的输入可能需要重新填写。", retry: true)
    }

    // MARK: 下载、选文件、弹窗与对话框：沿原网页流程，限定原服务同源。
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping @MainActor @Sendable (URL?) -> Void) {
        let dir = smoke ? supportDirectory().appendingPathComponent("downloads", isDirectory: true)
                        : FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let name = (suggestedFilename as NSString).lastPathComponent.replacingOccurrences(of: ":", with: "_")
        let base = ((name.isEmpty ? "download" : name) as NSString).deletingPathExtension
        let ext = (name as NSString).pathExtension
        var target = dir.appendingPathComponent(name.isEmpty ? "download" : name)
        var n = 1
        while FileManager.default.fileExists(atPath: target.path) {
            target = dir.appendingPathComponent("\(base) (\(n))" + (ext.isEmpty ? "" : "." + ext)); n += 1
        }
        completionHandler(target)
    }

    func downloadDidFinish(_ download: WKDownload) { window?.subtitle = "已保存到“下载”文件夹"; emit(["state": "download_finished"]) }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) { window?.subtitle = "下载未完成：" + error.localizedDescription }

    func sameOrigin(_ origin: WKSecurityOrigin) -> Bool {
        config.policy?.origin.matches(scheme: origin.protocol, host: origin.host, port: origin.port) == true
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable ([URL]?) -> Void) {
        guard sameOrigin(frame.securityOrigin) else { return completionHandler(nil) }
        // 测试模式不弹系统面板：只回给受信虚构 origin 一个测试声明的虚构文件，走同一原网页文件输入。
        if smoke {
            let file = environment["FAMILY_DESKTOP_TEST_OPEN_FILE"].map { URL(fileURLWithPath: $0) }
            let ok = file != nil && config.policy?.origin == testOrigin
            testEvents.append(["open_panel": ok ? "test_file" : "cancelled"])
            return completionHandler(ok ? [file!] : nil)
        }
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.begin { completionHandler($0 == .OK ? panel.urls : nil) }
    }

    // 录音等媒体只在原服务主页面实际请求时交给系统询问；摄像头等其他类型默认拒绝，不在启动时索权。
    // 测试模式一律拒绝，不触发系统权限询问，用来核对“无权限”时原表单仍可用。
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping @MainActor @Sendable (WKPermissionDecision) -> Void) {
        if smoke { testEvents.append(["media_request": type == .microphone ? "microphone" : "other", "decision": "deny"]); return decisionHandler(.deny) }
        decisionHandler(type == .microphone && frame.isMainFrame && sameOrigin(origin) ? .prompt : .deny)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard let policy = config.policy, let url = action.request.url else { return nil }
        switch policy.navigation(url) {
        case .allow:
            // 同源新窗口（如原件）另开窗口，原页面草稿保留。
            let popup = WKWebView(frame: .zero, configuration: configuration)
            popup.navigationDelegate = self
            popup.uiDelegate = self
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 760), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            w.isReleasedWhenClosed = false
            w.minSize = NSSize(width: 360, height: 400)
            w.contentView = popup
            w.delegate = self
            w.center()
            w.makeKeyAndOrderFront(nil)
            popups.append(w)
            return popup
        case .external:
            NSWorkspace.shared.open(url); return nil
        case .block:
            blocked.append(url.absoluteString); window?.subtitle = "已阻止弹出窗口"; return nil
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable () -> Void) {
        if smoke { testEvents.append(["alert": message]); return completionHandler() }
        let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "好"); alert.runModal(); completionHandler()
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable (Bool) -> Void) {
        // 测试模式按家长保守选择“取消”：页面自己的放弃确认不丢草稿。
        if smoke { testEvents.append(["confirm": message, "choice": false]); return completionHandler(false) }
        let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "确定"); alert.addButton(withTitle: "取消")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable (String?) -> Void) {
        if smoke { testEvents.append(["prompt": prompt]); return completionHandler(nil) }
        let alert = NSAlert(); alert.messageText = prompt; alert.addButton(withTitle: "确定"); alert.addButton(withTitle: "取消")
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 260, height: 24)); field.stringValue = defaultText ?? ""; alert.accessoryView = field
        completionHandler(alert.runModal() == .alertFirstButtonReturn ? field.stringValue : nil)
    }

    // MARK: 菜单：退出、窗口与编辑快捷键（复制粘贴需要编辑菜单）。
    func menu() -> NSMenu {
        let main = NSMenu()
        func add(_ title: String, _ items: [NSMenuItem]) {
            let item = NSMenuItem(); let sub = NSMenu(title: title); items.forEach(sub.addItem); item.submenu = sub; main.addItem(item)
        }
        add("一起成长", [NSMenuItem(title: "更改本机服务地址…", action: #selector(changeAddress), keyEquivalent: ""),
                     NSMenuItem(title: "更新后台到这个版本…", action: #selector(updateBackend), keyEquivalent: ""),
                     NSMenuItem(title: "卸载后台（保留家庭资料）…", action: #selector(uninstallBackend), keyEquivalent: ""),
                     NSMenuItem.separator(),
                     NSMenuItem(title: "隐藏一起成长", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h"),
                     NSMenuItem.separator(),
                     NSMenuItem(title: "退出桌面入口（后台继续）", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")])
        func command(_ title: String, _ action: Selector, _ key: String) -> NSMenuItem { NSMenuItem(title: title, action: action, keyEquivalent: key) }
        add("清单", [command("补录口头作业…", #selector(menuOral), "n"), NSMenuItem.separator(),
                   command("前一天", #selector(menuPrev), "["), command("后一天", #selector(menuNext), "]"), command("回到今天", #selector(menuToday), "t"),
                   NSMenuItem.separator(), command("第一个孩子", #selector(menuChild1), "1"), command("第二个孩子", #selector(menuChild2), "2"),
                   NSMenuItem.separator(), command("打印原卷…", #selector(menuPrintOriginal), "p"), command("打印家长参考…", #selector(menuPrintReference), "P"),
                   NSMenuItem.separator(), command("刷新清单", #selector(menuReload), "r"), command("网页版工具", #selector(menuWebTools), "e"),
                   command("回到原生工作台", #selector(menuWorkbench), "0")])
        add("编辑", [NSMenuItem(title: "撤销", action: Selector(("undo:")), keyEquivalent: "z"),
                   NSMenuItem(title: "重做", action: Selector(("redo:")), keyEquivalent: "Z"), NSMenuItem.separator(),
                   NSMenuItem(title: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x"),
                   NSMenuItem(title: "拷贝", action: #selector(NSText.copy(_:)), keyEquivalent: "c"),
                   NSMenuItem(title: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v"),
                   NSMenuItem(title: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")])
        add("窗口", [NSMenuItem(title: "最小化", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m"),
                   NSMenuItem(title: "关闭窗口", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")])
        return main
    }

    // MARK: --smoke-test（仅虚构本地服务验收）：真实 WebKit 窗口读取版面，执行测试声明的原网页操作，并尝试被禁止的导航。
    func finishSmoke() {
        guard smoke else { return }
        let hold = Double(environment["FAMILY_DESKTOP_SMOKE_HOLD"] ?? "") ?? 0
        DispatchQueue.main.asyncAfter(deadline: .now() + hold) {
            emit(["state": "exiting", "main_frame_loads": self.mainLoads])
            self.quitApproved = true
            NSApp.terminate(nil)
        }
    }

    // 测试里每次网页调用都有原生时限：异常或超时如实回执（含窗口是否可见），不再等到整轮总超时才没有结果。
    func page(_ web: WKWebView, _ body: String, timeout: Double = 20) async -> Any? {
        final class Once { var done = false }
        let once = Once()
        return await withCheckedContinuation { (k: CheckedContinuation<Any?, Never>) in
            let finish = { (value: Any?) in if !once.done { once.done = true; k.resume(returning: value) } }
            web.callAsyncJavaScript(body, arguments: [:], in: nil, in: .defaultClient) { result in
                switch result {
                case .success(let value): finish(value)
                case .failure(let error):
                    let e = error as NSError
                    finish(["ok": false, "error": e.userInfo["WKJavaScriptExceptionMessage"] as? String ?? e.localizedDescription])
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                finish(["ok": false, "error": "timeout", "seconds": timeout, "window_visible": self.window?.occlusionState.contains(.visible) ?? false])
            }
        }
    }

    // 一步原网页操作：先执行一次动作，再由原生一侧有界轮询完成条件，不依赖可能被 WebKit 降速的页面计时器；失败或超时如实回执。
    func runStep(_ web: WKWebView, _ step: [String: Any]) async -> Any {
        let limit = step["timeout"] as? Double ?? 15
        let start = Date()
        let action = await page(web, step["js"] as? String ?? "return {ok:true}", timeout: limit)
        guard let until = step["until"] as? String, (action as? [String: Any])?["ok"] as? Bool != false else { return action ?? NSNull() }
        var last: Any?
        while Date().timeIntervalSince(start) < limit {
            last = await page(web, until, timeout: max(1, limit - Date().timeIntervalSince(start)))
            if (last as? [String: Any])?["ok"] as? Bool == true { return ["ok": true, "action": action ?? NSNull(), "state": last ?? NSNull()] }
            await sleep(0.25)
        }
        return ["ok": false, "error": "timeout", "seconds": limit, "action": action ?? NSNull(), "last": last ?? NSNull(),
                "open_panel_requests": testEvents.filter { $0["open_panel"] != nil }.count,
                "window_visible": window?.occlusionState.contains(.visible) ?? false]
    }

    // 更改地址：页面有草稿时经同一未保存确认；测试声明 discard 时选“放弃”，否则选默认的“继续编辑”。
    func changeAddressAttempt(discard: Bool) async -> [String: Any] {
        let loads = mainLoads, seen = testEvents.count
        testDiscardNext = discard
        changeAddress()
        var shown = false, typed = ""
        for _ in 0..<20 where !shown {
            await sleep(0.1)
            if !setupView.isHidden { shown = true; typed = setupField.stringValue }
        }
        if discard { for _ in 0..<100 where mainLoads == loads { await sleep(0.1) } }
        testDiscardNext = false
        return ["ok": true, "prompt": testEvents.dropFirst(seen).filter { $0["discard_prompt"] != nil }, "setup_shown": shown, "typed": typed,
                "web_visible": webView?.isHidden == false, "saved_origin": DesktopConfig.load().policy?.origin.string ?? "", "main_frame_loads": mainLoads]
    }

    func dirty(_ web: WKWebView) async -> Bool {
        await withCheckedContinuation { (k: CheckedContinuation<Bool, Never>) in unsaved(web) { k.resume(returning: $0) } }
    }

    // 测试截图：网页用 WebKit 自身快照，原生表单用视图缓存；只写进测试声明的目录。
    func snapshot(_ name: String) async {
        guard smoke, let dir = environment["FAMILY_DESKTOP_TEST_SNAPSHOT_DIR"], let window, let view = window.contentView else { return }
        var image: NSImage?
        if let web = webView, !web.isHidden { image = try? await web.takeSnapshot(configuration: nil) }
        else if let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
            view.cacheDisplay(in: view.bounds, to: rep); let i = NSImage(size: view.bounds.size); i.addRepresentation(rep); image = i
        }
        guard let tiff = image?.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { return }
        try? png.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func sleep(_ seconds: Double) async { try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000)) }

    // 测试：经菜单同一路径更新/卸载（确认框自动选执行），等到后台回执；更新后等原页面重新打开。
    func backendStep(_ command: String) async -> [String: Any] {
        for _ in 0..<100 where backendState.isEmpty { await sleep(0.1) }
        let before = backendReplies.count, loads = mainLoads
        backendChange(command)
        for _ in 0..<3000 where backendReplies.count == before { await sleep(0.1) }
        guard backendReplies.count > before, let reply = backendReplies.last else {
            return ["ok": false, "error": "no backend reply", "backend_state": backendState]
        }
        if command == "update" { for _ in 0..<600 where mainLoads == loads { await sleep(0.1) } }
        return ["ok": true, "reply": reply, "main_frame_loads": mainLoads, "reloaded": mainLoads > loads,
                "web_visible": webView?.isHidden == false, "subtitle": window?.subtitle ?? "", "backend_state": backendState]
    }

    // 关窗、Esc、Cmd+Q 实际经过同一窗口/应用委托；测试模式里确认框自动选默认的“继续编辑”。
    func closeAttempts(_ web: WKWebView, _ window: NSWindow) async -> [String: Any] {
        let wasDirty = await dirty(web)
        window.performClose(nil)
        await sleep(1)
        let afterClose = self.window === window && window.isVisible
        window.makeFirstResponder(web)
        if let esc = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0, windowNumber: window.windowNumber,
                                      context: nil, characters: "\u{1b}", charactersIgnoringModifiers: "\u{1b}", isARepeat: false, keyCode: 53) {
            window.sendEvent(esc)
        }
        await sleep(0.6)
        let afterEsc = self.window === window && window.isVisible
        lastQuitReply = nil
        // 像菜单 Cmd+Q 一样从运行循环发起；在主队列任务里直接调用会让 terminateLater 等不到页面回复。
        NSApp.perform(#selector(NSApplication.terminate(_:)), with: nil, afterDelay: 0)
        await sleep(2)
        return ["dirty": wasDirty, "window_open_after_close": afterClose, "window_open_after_esc": afterEsc,
                "quit_reply": lastQuitReply.map { $0 ? "terminate" : "cancelled" } ?? "none", "main_frame_loads": mainLoads]
    }

    func runSmokeChecks(_ web: WKWebView) async {
        guard let window, let origin = config.policy?.origin, origin == testOrigin else {
            emit(["state": "loaded_untrusted_origin"]); return finishSmoke()
        }
        await sleep(1.5)
        let markerBefore = await page(web, "return document.cookie.includes('desktop_test_marker=1') || localStorage.getItem('desktop_test_marker') === '1'")
        _ = await page(web, "document.cookie='desktop_test_marker=1; path=/; max-age=3600'; localStorage.setItem('desktop_test_marker','1'); return true")
        let layout = "return JSON.stringify({href:location.href,width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,child_filters:document.querySelectorAll('[data-child-filter]').length,buttons:[...document.querySelectorAll('button')].filter(b=>b.offsetParent&&!b.disabled).length,all_children:/全部孩子/.test(document.body.innerText)})"
        var widths: [Any] = []
        for width in [360.0, 1440.0] {
            window.setContentSize(NSSize(width: width, height: 860))
            await sleep(0.9)
            if let text = await page(web, layout) as? String, let value = try? JSONSerialization.jsonObject(with: Data(text.utf8)) { widths.append(value) }
        }
        // 测试声明的原网页操作（虚构资料）：[{name,width?,js?,until?,timeout?,required?,native?,discard?}]；js/until 是在隔离脚本世界执行的
        // async 函数体。每步结果立即输出；必需步骤失败就停在这里并保留原因，后面的同源与隔离检查照常进行。
        var steps: [[String: Any]] = []
        if let file = environment["FAMILY_DESKTOP_TEST_STEPS"], let data = FileManager.default.contents(atPath: file),
           let list = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] {
            for step in list {
                let name = step["name"] as? String ?? ""
                emit(["state": "step", "name": name])
                if let width = step["width"] as? Double {
                    window.setContentSize(NSSize(width: width, height: 860)); await sleep(0.9)
                }
                let result: Any
                switch step["native"] as? String ?? "" {
                case "snapshot": await snapshot(name); result = ["ok": true]
                case "close_attempts": result = await closeAttempts(web, window)
                case "change_address": result = await changeAddressAttempt(discard: step["discard"] as? Bool == true)
                case "update_backend": result = await backendStep("update")
                case "uninstall_backend": result = await backendStep("uninstall")
                default: result = await runStep(web, step)
                }
                steps.append(["name": name, "result": result])
                emit(["state": "step_done", "name": name, "result": result])
                if (result as? [String: Any])?["ok"] as? Bool == false, step["required"] as? Bool != false {
                    await snapshot(name + "-failed")  // 失败时的实际画面一并保留
                    emit(["state": "steps_stopped", "after": name]); break
                }
            }
        }
        let attempts = ["file:///etc/hosts", "data:text/html,x", "http://\(origin.host):\(origin.port)@example.invalid/",
                        "http://\(origin.host):\(origin.port + 1)/", "x-apple.systempreferences:com.apple.preference.security"]
        for target in attempts {
            _ = await page(web, "location.href=\(String(reflecting: target)); return true")
            await sleep(0.4)
        }
        let still = await page(web, "return location.origin") as? String
        let fresh = await dirty(web)
        emit(["state": "loaded", "origin": origin.string, "widths": widths, "blocked": blocked, "location_origin_after_attempts": still ?? "",
              "main_frame_loads": mainLoads, "unsaved_after_steps": fresh, "steps": steps, "events": testEvents,
              "isolation": ["data_store_persistent": web.configuration.websiteDataStore.isPersistent, "frame_autosave": window.frameAutosaveName,
                            "marker_seen_at_start": markerBefore ?? NSNull(), "support_is_default": supportDirectory().path == defaultSupportDirectory().path]])
        finishSmoke()
    }
}


// MARK: 原生工作台：SwiftUI 视图由 NSHostingController 挂进原窗口；设置、状态与网页版仍用原 AppKit 容器。
extension AppDelegate {
    var nativeVisible: Bool { surface == "native" && window?.contentViewController is NSHostingController<WorkspaceView> }

    func restoreContainer() {
        guard let window, let container, window.contentView !== container else { return }
        let frame = window.frame
        window.contentViewController = nil
        window.toolbar = nil
        window.appearance = nil
        window.contentView = container
        window.setFrame(frame, display: true)
    }

    func showWorkspace(_ policy: DesktopPolicy) {
        guard let window else { return }
        if workspace?.client.origin != policy.origin {
            let client = WorkspaceClient(origin: policy.origin, ephemeral: smoke)
            // 原生请求与网页版工具共用同一个网页数据存储里的家长登录（测试模式是不落盘的临时存储，从不读本机默认 cookie）。
            client.sessionCookies = { [weak self] in await self?.configuration.websiteDataStore.httpCookieStore.allCookies() ?? [] }
            let store = WorkspaceStore(client: client)
            store.openDocument = { [weak self] url, name in self?.openDocument(url, name) }
            store.openWebTools = { [weak self] task, intent in self?.openWebTools(task, intent) }
            store.openLogin = { [weak self] in self?.openLogin() }
            store.confirmDiscard = { [weak self] action in self?.confirmDiscard(action) ?? false }
            store.onLoaded = { [weak self] in self?.workspaceLoaded() }
            workspace = store
        }
        guard let store = workspace else { return }
        if !observingCookies { observingCookies = true; configuration.websiteDataStore.httpCookieStore.add(self) }
        surface = "native"
        TestTargets.enabled = smoke && environment["FAMILY_DESKTOP_TEST_SURFACE"] == "native"
        let frame = window.frame
        if let shown = window.contentViewController as? NSHostingController<WorkspaceView> {
            // 工作台已显示在这个窗口里（例如重新读取）：只把视图换成这份清单，不替换窗口内容控制器——替换后真实点击清单行不再选中。
            shown.rootView = WorkspaceView(store: store)
        } else {
            // 从网页版或状态页回来：装回同一个工作台控制器（只换成这份清单），不另建新控制器。
            let host = workspaceHost ?? NSHostingController(rootView: WorkspaceView(store: store))
            host.rootView = WorkspaceView(store: store)
            host.sizingOptions = []
            workspaceHost = host
            window.contentViewController = host
            window.setFrame(frame, display: true)
        }
        window.toolbarStyle = .unified
        window.appearance = NSAppearance(named: .aqua)  // 工作台配色只设计了浅色
        window.subtitle = ""
        Task { await store.load() }
    }

    /// 网页版工具（日历、学校消息、照片检查、打印确认等原功能）在同一窗口打开；指定作业时打开同一份原作业，并带上意图
    /// （print-original 打印原卷、print-reference 打印家长参考、check 照片检查、original 原消息、history 错题诊断与再试）：
    /// 网页只打开对应的原流程，确认、依据核对和防重复照旧，不会自动打印或保存。
    static let webIntents: Set<String> = ["", "print-original", "print-reference", "check", "original", "history"]
    func openWebTools(_ task: String, _ intent: String = "") {
        guard let policy = config.policy, let web = webView, AppDelegate.webIntents.contains(intent) else { return }
        guard workspace?.hasUnsavedInput != true || confirmDiscard("打开网页版") else { return }
        workspace?.sheet = nil; workspace?.sheetDirty = false
        var c = URLComponents(url: policy.origin.url, resolvingAgainstBaseURL: false)!
        if !task.isEmpty {
            let id = task.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-_."))) ?? ""
            c.percentEncodedFragment = "task=" + id + (intent.isEmpty ? "" : "&do=" + intent)
        }
        let target = c.url!
        // 每次从原生进入都整页重新载入，网页按 #task= 重读这一项最新保存的状态；同一页面只差 # 时 WebKit 只做同文档跳转、不会重读。
        // 重新载入前沿网页原有 beforeunload 判断（含知识点面板未提交的作答、保存中或回执不明）：有就先问，不同意就原样显示那页、不丢输入。
        unsaved(web) { [weak self] dirty in
            guard let self, web === self.webView else { return }
            self.surface = "web"
            if dirty && !self.confirmDiscard("重新打开网页版") {
                self.statusView.isHidden = true; self.setupView.isHidden = true; web.isHidden = false
                emit(["state": "web_tools_kept_unsaved", "task": task, "intent": intent]); return
            }
            self.status("正在打开网页版…", retry: false)
            let same = web.url.map { AppDelegate.sameDocument($0, target) } ?? false
            if same, let literal = String(data: (try? JSONSerialization.data(withJSONObject: [target.absoluteString])) ?? Data(), encoding: .utf8) {
                web.evaluateJavaScript("history.replaceState(history.state,'',\(literal)[0]);true") { _, error in
                    if error == nil { web.reload() } else { web.load(URLRequest(url: target)) }
                }
            } else { web.load(URLRequest(url: target)) }
            emit(["state": "web_tools_opened", "task": task, "intent": intent, "reload": same])
        }
    }

    /// 只差 # 片段（或完全相同）的两个网址是同一网页文档。
    static func sameDocument(_ a: URL, _ b: URL) -> Bool {
        func base(_ u: URL) -> String? { var c = URLComponents(url: u, resolvingAgainstBaseURL: false); c?.fragment = nil; return c?.string }
        return base(a) != nil && base(a) == base(b)
    }

    /// 登录用原服务自己的登录页（同一 origin、同一网页数据存储），开在单独的登录窗口：工作台视图不被替换，打开着的填写框、
    /// 草稿、已选附件和提交标识都原样保留。新的家长登录 cookie 出现后关掉登录窗口、重读清单；保存仍由家长自己再点一次。
    func openLogin() {
        guard let policy = config.policy else { return }
        if let open = loginWindow { open.makeKeyAndOrderFront(nil); return }
        Task { @MainActor in
            loginBaseline = WorkspaceClient.session(await configuration.websiteDataStore.httpCookieStore.allCookies(), for: policy.origin)?.value ?? ""
            loginPending = true
            let login = WKWebView(frame: .zero, configuration: configuration)
            login.navigationDelegate = self
            login.uiDelegate = self
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 640), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            w.title = "登录家庭账号"
            w.isReleasedWhenClosed = false
            w.minSize = NSSize(width: 360, height: 420)
            w.contentView = login
            w.delegate = self
            w.center()
            w.makeKeyAndOrderFront(nil)
            popups.append(w)
            loginWindow = w; loginWeb = login
            login.load(URLRequest(url: policy.origin.url.appendingPathComponent("login")))
            emit(["state": "login_opened", "window": true])
        }
    }

    nonisolated func cookiesDidChange(in cookieStore: WKHTTPCookieStore) {
        Task { @MainActor in await self.sessionChanged() }
    }

    /// 家长登录状态变了：登录完成就回工作台；工作台开着时重读（退出后服务端会拒绝，工作台显示需要登录）。
    func sessionChanged() async {
        guard let policy = config.policy else { return }
        let current = WorkspaceClient.session(await configuration.websiteDataStore.httpCookieStore.allCookies(), for: policy.origin)
        if loginPending, let current, current.value != loginBaseline {
            loginPending = false
            emit(["state": "login_returned"])
            loginWindow?.close()
            window?.makeKeyAndOrderFront(nil)  // 登录窗口关掉后回到工作台（和它打开着的填写框），下一次点击直接生效
            // 工作台一直开着：只重读清单，不换掉工作台视图（换掉会丢掉打开着的填写框）。
            if surface == "native", let store = workspace { await store.load() } else { showWorkspace(policy) }
            return
        }
        if surface == "native", let store = workspace { await store.load() }
    }

    /// 原件等富文档：只开原服务同源地址，另开窗口，工作台与草稿不受影响。
    func openDocument(_ url: URL, _ name: String) {
        guard config.policy?.origin.matches(url) == true else { return }
        let popup = WKWebView(frame: .zero, configuration: configuration)
        popup.navigationDelegate = self
        popup.uiDelegate = self
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 760), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        w.title = name
        w.isReleasedWhenClosed = false
        w.minSize = NSSize(width: 360, height: 400)
        w.contentView = popup
        w.delegate = self
        w.center()
        w.makeKeyAndOrderFront(nil)
        popups.append(w)
        popup.load(URLRequest(url: url))
        emit(["state": "document_opened"])
    }

    @objc func menuOral() { workspace?.sheetDirty = false; workspace?.sheet = .oral }
    @objc func menuPrev() { workspace?.shift(-1) }
    @objc func menuNext() { workspace?.shift(1) }
    @objc func menuToday() { workspace?.change(day: workspace?.view?.today ?? "") }
    @objc func menuChild1() { workspace?.childAt(0) }
    @objc func menuChild2() { workspace?.childAt(1) }
    @objc func menuReload() { Task { await workspace?.load() } }
    @objc func menuWebTools() { openWebTools("") }
    @objc func menuPrintOriginal() { if let id = workspace?.selected?.task_id, !id.isEmpty { openWebTools(id, "print-original") } }
    @objc func menuPrintReference() { if let id = workspace?.selected?.task_id, !id.isEmpty { openWebTools(id, "print-reference") } }
    @objc func menuWorkbench() {
        guard let policy = config.policy else { return }
        guard let web = webView, surface == "web" else { return showWorkspace(policy) }
        unsaved(web) { dirty in if !dirty || self.confirmDiscard("回到工作台") { self.showWorkspace(policy) } }
    }

    func workspaceLoaded() {
        guard smoke, surface == "native", !nativeRan, workspace?.view != nil || workspace?.error.isEmpty == false else { return }
        nativeRan = true
        Task { await runNativeChecks() }
    }

    // MARK: 原生验收（仅 --smoke-test + 虚构后台）：经无障碍树找控件，在其位置投递真实鼠标/键盘事件，读回控件文字；截图只取本窗口。
    struct AXNode { let id: String; let text: String; let frame: NSRect }

    func axNodes(_ root: NSObject, _ out: inout [AXNode], _ depth: Int = 0) {
        guard depth < 80, out.count < 4000 else { return }
        func string(_ key: String) -> String {
            guard root.responds(to: NSSelectorFromString(key)) else { return "" }
            let v = root.value(forKey: key)
            return (v as? String) ?? (v as? NSAttributedString)?.string ?? (v.map { "\($0)" } ?? "")
        }
        let id = string("accessibilityIdentifier")
        let text = [string("accessibilityLabel"), string("accessibilityTitle"), string("accessibilityValue")].filter { !$0.isEmpty }.joined(separator: " ")
        var frame = NSRect.zero
        if root.responds(to: NSSelectorFromString("accessibilityFrame")), let v = root.value(forKey: "accessibilityFrame") as? NSValue { frame = v.rectValue }
        out.append(AXNode(id: id, text: text, frame: frame))
        guard root.responds(to: NSSelectorFromString("accessibilityChildren")), let children = root.value(forKey: "accessibilityChildren") as? [Any] else { return }
        for child in children { if let o = child as? NSObject { axNodes(o, &out, depth + 1) } }
    }

    func testWindows() -> [NSWindow] { [window?.attachedSheet, window].compactMap { $0 } }

    func nodes() -> [AXNode] {
        var out: [AXNode] = []
        for w in testWindows() { axNodes(w, &out) }
        return out
    }

    /// 先找无障碍树；SwiftUI 没有在进程内提供节点时，用工作台登记的控件位置（换算成屏幕坐标）与其显示文字。
    func find(_ id: String, contains: String = "") -> AXNode? {
        if let node = nodes().first(where: { $0.id == id && (contains.isEmpty || $0.text.contains(contains)) && $0.frame.width > 0 }) { return node }
        guard let (view, text) = TestTargets.live(id), contains.isEmpty || text.contains(contains), let w = view.window else { return nil }
        let frame = w.convertToScreen(view.convert(view.bounds, to: nil))
        return frame.width > 0 ? AXNode(id: id, text: text, frame: frame) : nil
    }

    /// 控件不在可见区域时，像滚轮一样让它所在的真实滚动视图滚到那里（不调用工作台自己的任何动作）。
    func reveal(_ id: String) async -> Bool {
        guard let (view, _) = TestTargets.live(id), !onScreen(view) else { return false }
        var moved = view.scrollToVisible(view.bounds)
        if !moved, let scroll = view.enclosingScrollView, let doc = scroll.documentView {
            // 真实滚动视图自己的滚动：把控件移到可见区域中间。
            let target = doc.convert(view.bounds, from: view), page = scroll.contentView.bounds
            scroll.contentView.scroll(to: NSPoint(x: page.origin.x, y: max(0, min(target.midY - page.height / 2, doc.bounds.height - page.height))))
            scroll.reflectScrolledClipView(scroll.contentView); moved = true
        }
        if moved { await sleep(0.5) }
        return moved
    }

    /// 控件中心在它所在滚动视图的可见区域内，也在窗口内容里。
    func onScreen(_ view: NSView) -> Bool {
        guard let w = view.window, w.isVisible, let content = w.contentView else { return false }
        let rect = content.convert(view.bounds, from: view), center = NSPoint(x: rect.midX, y: rect.midY)
        let seen = view.enclosingScrollView.map { content.convert($0.contentView.bounds, from: $0.contentView) } ?? content.bounds
        return seen.contains(center) && content.bounds.contains(center)
    }

    /// 只认真正显示在窗口里的文字：登记了显示文字的控件可见（必要时先滚过去）；不读清单数据本身。
    func shown(_ text: String) async -> [String] {
        var ids: [String] = []
        for id in TestTargets.anchors.keys.sorted() where (TestTargets.live(id)?.1 ?? "").contains(text) {
            _ = await reveal(id)
            if let (view, _) = TestTargets.live(id), onScreen(view) { ids.append(id) }
        }
        return ids
    }

    func post(_ type: NSEvent.EventType, at screen: NSPoint, in w: NSWindow) {
        let p = w.convertFromScreen(NSRect(origin: screen, size: .zero)).origin
        if let e = NSEvent.mouseEvent(with: type, location: p, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: w.windowNumber,
                                      context: nil, eventNumber: 0, clickCount: 1, pressure: type == .leftMouseDown ? 1 : 0) { NSApp.postEvent(e, atStart: false) }
    }

    func click(_ id: String, contains: String = "") async -> [String: Any] {
        let scrolled = await reveal(id)
        guard let node = find(id, contains: contains) else { return ["ok": false, "error": "control not found", "id": id] }
        var center = NSPoint(x: node.frame.midX, y: node.frame.midY), row = -1
        var rowTable: NSTableView?
        // 列表里的一行：用表格自己的那一行（锚点所在的那一行）的位置；先让表格自己滚到这一行，再点这一行的中间。
        if let (anchor, _) = TestTargets.live(id), let (table, index) = TestTargets.row(of: anchor), let tw = table.window {
            // 用表格公开的显露行操作；不直接改 clip-view 偏移去强行居中。
            // SwiftUI 的 cell-hosting 命中布局必须跟着其真实滚动更新，已可见的行无需再移动。
            table.scrollRowToVisible(index)
            await sleep(0.4); row = index; rowTable = table
            // Click the current control's own frame, not the arbitrary centre of its layout row.
            // The row can include empty padding beside a short SwiftUI label. The selected original ID below is still mandatory.
            let r = tw.convertToScreen(anchor.convert(anchor.bounds, to: nil)); center = NSPoint(x: r.midX, y: r.midY)
        }
        guard let w = testWindows().first(where: { $0.frame.contains(center) }) else { return ["ok": false, "error": "control outside the test window", "id": id, "scrolled": scrolled, "has_scroll_view": TestTargets.live(id)?.0.enclosingScrollView != nil] }
        // 像家长先把窗口点到最前面：App 不在前台、窗口不是当前窗口时先激活（只激活，不算这一步的点击）。
        var activated = false
        if !w.isKeyWindow { NSApp.activate(ignoringOtherApps: true); w.makeKeyAndOrderFront(nil); await sleep(0.5); activated = true }
        let local = w.convertFromScreen(NSRect(origin: center, size: .zero)).origin
        // NSView.hitTest 接收父视图坐标；这里只修正测试定位，不修改控件选择。
        let hit = w.contentView?.hitTest(w.contentView?.superview?.convert(local, from: nil) ?? local)
        // 测试定位：新版 SwiftUI 会由表格本身接收行内点击。核真实行坐标和随后读回的选中项，不能仅凭命中视图类型拒绝它。
        // 空白处、科目标题、另一窗口仍拒绝；下面只投递鼠标事件，不直接设置选择。
        let atRow = rowTable.map { $0.row(at: $0.convert(local, from: nil)) } ?? -1
        if id.hasPrefix("row-"), row < 0 || atRow != row || rowTable?.window !== w || hit.map({ String(describing: type(of: $0)).contains("HeaderForSection") }) == true {
            let correctedHit = w.contentView?.hitTest(w.contentView?.superview?.convert(local, from: nil) ?? local)
            var chain: [String] = [], next = hit
            while let v = next, chain.count < 12 { chain.append("\(String(describing: type(of: v))) frame=\(v.frame) bounds=\(v.bounds)"); next = v.superview }
            return ["ok": false, "error": "not on this list row", "id": id, "row": row, "point_row": atRow, "hit": hit.map { String(describing: type(of: $0)) } ?? "none",
                    "corrected_hit": correctedHit.map { String(describing: type(of: $0)) } ?? "none", "hit_chain": chain,
                    "table_bounds": rowTable.map { NSStringFromRect($0.bounds) } ?? "", "table_visible": rowTable.map { NSStringFromRect($0.visibleRect) } ?? "",
                    "row_rect": rowTable.map { NSStringFromRect($0.rect(ofRow: row)) } ?? "", "click_screen": NSStringFromPoint(center), "click_window": NSStringFromPoint(local),
                    "app_active": NSApp.isActive, "key": w.isKeyWindow, "app_key_window": NSApp.keyWindow?.windowNumber ?? -1, "window_number": w.windowNumber,
                    "window_can_key": w.canBecomeKey, "window_visible": w.isVisible, "window_sheet": w.attachedSheet?.windowNumber ?? -1]
        }
        workspaceTestSelectCalls = []; workspaceTestTableChanges = []
        let watch = NotificationCenter.default.addObserver(forName: NSTableView.selectionDidChangeNotification, object: rowTable, queue: nil) { note in
            workspaceTestTableChanges.append(Array((note.object as? NSTableView)?.selectedRowIndexes ?? []))
        }
        var observedMouse: [[String: Any]] = []
        let mouseWatch = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .leftMouseUp]) { event in
            observedMouse.append(["type": event.type.rawValue, "window": event.windowNumber,
                                  "location": NSStringFromPoint(event.locationInWindow), "event_window": event.window?.windowNumber ?? -1])
            return event
        }
        defer { NotificationCenter.default.removeObserver(watch); if let mouseWatch { NSEvent.removeMonitor(mouseWatch) } }
        post(.leftMouseDown, at: center, in: w); post(.leftMouseUp, at: center, in: w)
        await sleep(0.6)
        let target = String(id.dropFirst(4))
        if id.hasPrefix("row-") {
            for _ in 0..<20 where workspace?.selection != target { await sleep(0.1) }
            guard workspace?.selection == target else {
                // 只读诊断：表格自己的点击/选中行、命中视图是否在这一行里、各行挂着的锚点、清单选择回调是否被调用。
                let rv = rowTable?.rowView(atRow: row, makeIfNecessary: false)
                let anchors = TestTargets.anchors.flatMap { key, list in list.compactMap(\.view).filter { key.hasPrefix("row-") && $0.window != nil }
                    .map { "\($0.probeID.suffix(6))@\(TestTargets.row(of: $0)?.1 ?? -1)\($0.isHiddenOrHasHiddenAncestor ? "h" : "")" } }.sorted()
                func chain(_ start: NSView?) -> [String] {
                    var result: [String] = [], next = start
                    while let v = next, result.count < 16 {
                        result.append("\(String(describing: type(of: v))) frame=\(v.frame) bounds=\(v.bounds)")
                        next = v.superview
                    }
                    return result
                }
                let content = w.contentView
                let correctedHit = content?.hitTest(content?.superview?.convert(local, from: nil) ?? local)
                let pointInTable = rowTable?.convert(local, from: nil) ?? .zero
                return ["ok": false, "error": "mouse click did not select the intended original item", "id": id, "row": row, "point_row": atRow, "selected": workspace?.selection ?? "",
                        "app_active": NSApp.isActive, "app_key_window": NSApp.keyWindow?.windowNumber ?? -1, "window_number": w.windowNumber,
                        "window_can_key": w.canBecomeKey, "window_visible": w.isVisible, "window_main": w.isMainWindow,
                        "window_sheet": w.attachedSheet?.windowNumber ?? -1,
                        "click_screen": NSStringFromPoint(center), "click_window": NSStringFromPoint(local), "click_table": NSStringFromPoint(pointInTable),
                        "table_bounds": rowTable.map { NSStringFromRect($0.bounds) } ?? "", "table_visible": rowTable.map { NSStringFromRect($0.visibleRect) } ?? "",
                        "row_rect": rowTable.map { NSStringFromRect($0.rect(ofRow: row)) } ?? "", "row_view_frame": rv.map { NSStringFromRect($0.frame) } ?? "",
                        "hit_row": hit.flatMap { h in rowTable.map { $0.row(for: h) } } ?? -1,
                        "hit_chain": chain(hit), "row_chain": chain(rv), "corrected_hit_chain": chain(correctedHit),
                        "windows": NSApp.windows.map { "\($0.windowNumber):visible=\($0.isVisible):key=\($0.isKeyWindow):frame=\($0.frame)" },
                        "hit": hit.map { String(describing: type(of: $0)) } ?? "none", "hit_in_row_view": hit.flatMap { h in rv.map { h.isDescendant(of: $0) } } ?? false,
                        "row_view_selected": rv?.isSelected ?? false, "table_selected": Array(rowTable?.selectedRowIndexes ?? []), "clicked_row": rowTable?.clickedRow ?? -2,
                        "table_changes": workspaceTestTableChanges, "select_calls": workspaceTestSelectCalls, "mouse_dispatch": observedMouse, "rows": rowTable?.numberOfRows ?? -1, "row_anchors": anchors,
                        "key": w.isKeyWindow, "activated": activated, "first_responder": w.firstResponder.map { String(describing: type(of: $0)) } ?? "none"]
            }
        }
        return ["ok": true, "id": id, "hit": hit.map { String(describing: type(of: $0)) } ?? "none", "sheet": w !== window,
                "located_by": nodes().contains { $0.id == id } ? "accessibility" : "workbench_frame", "scrolled": scrolled, "row": row, "point_row": atRow, "selected": workspace?.selection ?? "", "key": w.isKeyWindow, "activated": activated]
    }

    func key(_ chars: String, _ modifiers: [String], code: UInt16 = 0) async {
        guard let w = testWindows().first else { return }
        var flags: NSEvent.ModifierFlags = []
        if modifiers.contains("command") { flags.insert(.command) }
        if modifiers.contains("shift") { flags.insert(.shift) }
        for type in [NSEvent.EventType.keyDown, .keyUp] {
            if let e = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: flags, timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: w.windowNumber,
                                        context: nil, characters: chars, charactersIgnoringModifiers: chars.lowercased(), isARepeat: false, keyCode: code) { NSApp.postEvent(e, atStart: false) }
        }
        await sleep(0.6)
    }

    func nativeStep(_ step: [String: Any]) async -> [String: Any] {
        let limit = step["timeout"] as? Double ?? 10
        // 仅 --smoke-test 隔离 Support 与受信虚构 origin 上的网页面板：把测试声明交给现有 runStep，不新增接口或正式入口。
        if let declared = step["web_step"] as? [String: Any] {
            guard smoke, testModeAllowed(), surface == "web", let web = webView, let origin = testOrigin, origin.matches(web.url) else {
                return ["ok": false, "error": "web_step only runs in the smoke test on the web surface of the test origin", "surface": surface]
            }
            let value = await runStep(web, declared)
            return ["ok": (value as? [String: Any])?["ok"] as? Bool == true, "web": value]
        }
        if let faults = step["faults"] as? [String] { workspaceTestFaults = faults; return ["ok": true, "faults": faults] }
        // 系统文件选择框在这里无法自动操作：声明下一次点“选择照片或 PDF…”交回的文件（null 为取消），走弹出层同一个选取结果处理；这不是真实选择框测试。
        if let pick = step["pick"] {
            let files = (pick as? [String])?.map { URL(fileURLWithPath: $0) }
            workspaceTestPicks.append(files); return ["ok": true, "pick": files?.map(\.lastPathComponent) ?? ["cancel"]]
        }
        if let id = step["click"] as? String { return await click(id, contains: step["contains"] as? String ?? "") }
        if let prefix = step["click_prefix"] as? String {
            let id = nodes().first(where: { $0.id.hasPrefix(prefix) && $0.frame.width > 0 })?.id ?? TestTargets.anchors.keys.sorted().first { $0.hasPrefix(prefix) && TestTargets.live($0) != nil }
            guard let id else { return ["ok": false, "error": "control not found", "prefix": prefix] }
            return await click(id)
        }
        if let text = step["find_text"] as? String {
            let start = Date(), absent = step["absent"] as? Bool == true
            while Date().timeIntervalSince(start) < limit {
                let hits = nodes().filter { $0.text.contains(text) && $0.frame.width > 0 }
                if absent {
                    let anywhere = TestTargets.anchors.keys.filter { (TestTargets.live($0)?.1 ?? "").contains(text) }
                    if hits.isEmpty && anywhere.isEmpty { return ["ok": true, "text": text, "absent": true] }
                } else {
                    let visible = await shown(text)
                    if !visible.isEmpty || !hits.isEmpty { return ["ok": true, "text": text, "ax_ids": hits.map(\.id).filter { !$0.isEmpty }, "shown_ids": visible] }
                }
                await sleep(0.25)
            }
            return ["ok": false, "error": "timeout", "text": text, "absent": absent]
        }
        if let text = step["type"] as? String {
            guard let w = testWindows().first, let tv = w.firstResponder as? NSTextView else { return ["ok": false, "error": "no focused text field"] }
            // 真实按键：逐字投递 keyDown/keyUp，走文本框自己的 keyDown → interpretKeyEvents → insertText。
            for ch in text {
                for type in [NSEvent.EventType.keyDown, .keyUp] {
                    if let e = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: w.windowNumber,
                                                context: nil, characters: String(ch), charactersIgnoringModifiers: String(ch), isARepeat: false, keyCode: 0) { NSApp.postEvent(e, atStart: false) }
                }
            }
            await sleep(0.8)
            // 只认真实按键送达；不再用 insertText 直接写入文本框。
            var result: [String: Any] = ["ok": tv.string.contains(text), "responder": String(describing: type(of: tv)), "method": "key_events",
                                         "field": String(tv.string.prefix(80)), "sheet_dirty": workspace?.sheetDirty == true]
            // 指定了目标控件时：输入必须恰好落在那个控件里（正在编辑的控件与它的位置重合），且内容正好是这次输入的文字。
            if let target = step["into"] as? String {
                let editing: NSView = tv.isFieldEditor ? (tv.delegate as? NSView ?? tv) : tv
                let anchor = TestTargets.live(target)?.0
                let same = anchor != nil && editing.window === anchor?.window
                    && editing.convert(editing.bounds, to: nil).intersects(anchor.map { $0.convert($0.bounds, to: nil) } ?? .zero)
                result["ok"] = same && tv.string == text
                result["into"] = target; result["same_control"] = same; result["exact"] = tv.string == text; result["editing"] = String(describing: type(of: editing))
            }
            return result
        }
        if let chars = step["key"] as? String {
            await key(chars, step["modifiers"] as? [String] ?? [], code: UInt16(step["code"] as? Int ?? 0)); return ["ok": true, "key": chars]
        }
        if let id = step["until"] as? String {
            let start = Date(), wanted = step["contains"] as? String ?? "", absent = step["absent"] as? Bool == true
            while Date().timeIntervalSince(start) < limit {
                let found = find(id, contains: wanted)
                if absent ? found == nil : found != nil { return ["ok": true, "id": id, "text": found?.text ?? ""] }
                await sleep(0.25)
            }
            let near = nodes().filter { !$0.id.isEmpty }.prefix(80).map { $0.id + ": " + String($0.text.prefix(60)) }
            return ["ok": false, "error": "timeout", "id": id, "contains": wanted, "visible_ids": Array(near), "ax_nodes": nodes().count,
                    "registered": TestTargets.anchors.keys.sorted().filter { TestTargets.live($0) != nil }.prefix(80).map { $0 + ": " + String((TestTargets.live($0)?.1 ?? "").prefix(60)) }]
        }
        switch step["native"] as? String ?? "" {
        case "snapshot":
            await snapshot(step["name"] as? String ?? "native")
            if let sheet = window?.attachedSheet, let dir = environment["FAMILY_DESKTOP_TEST_SNAPSHOT_DIR"], let v = sheet.contentView,
               let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) {
                v.cacheDisplay(in: v.bounds, to: rep)
                try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: dir).appendingPathComponent((step["name"] as? String ?? "native") + "-sheet.png"))
            }
            return ["ok": true]
        case "dirty": return ["ok": true, "dirty": workspace?.hasUnsavedInput == true]
        case "web_login", "web_logout":
            // 虚构登录（测试声明的虚构账号）：在网页版自己的登录页里填写并提交，或用网页自己的退出请求；原生端不碰 cookie。
            guard let web = loginWeb ?? webView, loginWeb != nil || surface == "web" || step["native"] as? String == "web_logout" else { return ["ok": false, "error": "web tools not open"] }
            let login = (try? JSONSerialization.jsonObject(with: Data((environment["FAMILY_DESKTOP_TEST_LOGIN"] ?? "[]").utf8))) as? [String] ?? []
            let script: String
            if step["native"] as? String == "web_login" {
                guard login.count == 2 else { return ["ok": false, "error": "no fictional login"] }
                let quoted = login.map { String(data: try! JSONSerialization.data(withJSONObject: [$0]), encoding: .utf8)!.dropFirst().dropLast() }
                script = "document.getElementById('username').value=\(quoted[0]);document.getElementById('password').value=\(quoted[1]);document.getElementById('loginForm').requestSubmit();'submitted'"
            } else {
                script = "fetch('/api/parent/logout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Family-Login':'1'},body:'{}'}).then(r=>r.status)"
            }
            let start = Date()
            // 等登录页真正载入完（地址在开始载入时就变了，表单还没出来）。
            while Date().timeIntervalSince(start) < 10, step["native"] as? String == "web_login" {
                if web.url?.path.hasSuffix("login") == true, !web.isLoading,
                   (try? await web.evaluateJavaScript("document.readyState==='complete'&&document.getElementById('loginForm')?1:0")) as? Int == 1 { break }
                await sleep(0.25)
            }
            let value = try? await web.callAsyncJavaScript(script.hasPrefix("fetch") ? "return await " + script : "return (()=>{" + script.replacingOccurrences(of: ";'submitted'", with: ";return 'submitted'") + "})()", contentWorld: .page)
            await sleep(1.5)
            return ["ok": value != nil, "result": value.map { "\($0)" } ?? "", "url_path": web.url?.path ?? ""]
        case "fixture_get":
            // 只给虚构后台的测试控制地址（/__fixture/…），不带任何 cookie。
            guard let path = step["path"] as? String, path.hasPrefix("/__fixture/"), let origin = config.policy?.origin else { return ["ok": false] }
            let reply = try? await URLSession(configuration: .ephemeral).data(from: origin.url.appendingPathComponent(String(path.dropFirst())))
            return ["ok": (reply?.1 as? HTTPURLResponse)?.statusCode == 200, "path": path]
        case "discard_next": testDiscardNext = true; return ["ok": true]
        case "reopen":
            // 像重新打开 App 一样：丢掉内存里的清单，从后台重新读同一天。
            guard let policy = config.policy, let keep = workspace?.selection, let child = workspace?.childID, let day = workspace?.day else { return ["ok": false, "error": "nothing open"] }
            workspace = nil; showWorkspace(policy); workspace?.childID = child; workspace?.day = day
            await workspace?.load(); workspace?.select(keep); await sleep(0.8)
            return ["ok": workspace?.selected != nil, "selection": workspace?.selection ?? ""]
        case "close_attempts":
            guard let window else { return ["ok": false] }
            let dirty = workspace?.hasUnsavedInput == true
            window.performClose(nil); await sleep(0.8)
            let open = self.window === window && window.isVisible
            lastQuitReply = nil
            // 验收实际 Cmd+Q：原来的 perform(afterDelay:) 在 sheet 的事件循环里可能根本没被投递。
            // 系统可能在调用应用委托之前拦住退出；用实际窗口/草稿与后续保存读回验，不伪造委托回执。
            let keyTarget = testWindows().first
            let quitKeyWindow = keyTarget?.isKeyWindow == true
            var keyDeliveredToTarget = false
            let keyWatch = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
                if event.windowNumber == keyTarget?.windowNumber, event.modifierFlags.contains(.command),
                   event.charactersIgnoringModifiers?.lowercased() == "q" { keyDeliveredToTarget = true }
                return event
            }
            await key("q", ["command"], code: 12); await sleep(1.5)
            if let keyWatch { NSEvent.removeMonitor(keyWatch) }
            let keyboardReply = lastQuitReply
            // A direct Quit action separately exercises the real App delegate guard, even on an inactive test Mac.
            // Do not infer keyboard focus from successful posted events or invent a cancellation callback.
            lastQuitReply = nil
            let requestsBefore = smokeQuitRequests
            let ownModalBefore = keyTarget != nil && window.attachedSheet === keyTarget && keyTarget?.isVisible == true
            NSApp.terminate(nil); await sleep(0.8)
            let ownModalAfter = keyTarget != nil && window.attachedSheet === keyTarget && keyTarget?.isVisible == true
            return ["ok": true, "dirty": dirty, "window_open_after_close": open, "quit_reply": keyboardReply.map { $0 ? "terminate" : "cancelled" } ?? "none",
                    "quit_key_posted": true, "quit_key_window": quitKeyWindow, "quit_key_delivered_to_target": keyDeliveredToTarget,
                    "guarded_quit_delegate_calls": smokeQuitRequests - requestsBefore,
                    "quit_own_modal_preserved": ownModalBefore && ownModalAfter,
                    "guarded_quit_reply": lastQuitReply.map { $0 ? "terminate" : "cancelled" } ?? "none",
                    "window_open_after_quit": self.window === window && window.isVisible,
                    "still_dirty": workspace?.hasUnsavedInput == true]
        case "state":
            let s = workspace
            return ["ok": true, "child": s?.childID ?? "", "day": s?.day ?? "", "selection": s?.selection ?? "", "error": s?.error ?? "",
                    "login_required": s?.loginRequired == true, "summary": s?.summary ?? "", "surface": surface, "web_url": webView?.url?.absoluteString ?? "",
                    "groups": (s?.view?.groups ?? []).map { ["subject": $0.subject, "items": $0.items.map(\.id)] },
                    "web_visible": webView?.isHidden == false && surface == "web", "native_visible": nativeVisible, "windows": NSApp.windows.filter(\.isVisible).count,
                    "login_window": loginWindow != nil, "sheet": s?.sheet?.id ?? "", "dirty": s?.hasUnsavedInput == true]
        default: return ["ok": false, "error": "unknown step"]
        }
    }

    func runNativeChecks() async {
        guard let window, config.policy?.origin == testOrigin else { emit(["state": "loaded_untrusted_origin"]); return finishSmoke() }
        NSApp.activate(ignoringOtherApps: true); window.makeKeyAndOrderFront(nil)
        await sleep(1.2)
        var results: [[String: Any]] = []
        if let file = environment["FAMILY_DESKTOP_TEST_NATIVE_STEPS"], let data = FileManager.default.contents(atPath: file),
           let list = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] {
            for step in list {
                let name = step["name"] as? String ?? ""
                if let width = step["width"] as? Double { window.setContentSize(NSSize(width: width, height: step["height"] as? Double ?? 860)); await sleep(0.8) }
                let result = await nativeStep(step)
                results.append(["name": name, "result": result])
                emit(["state": "native_step_done", "name": name, "result": result])
                if result["ok"] as? Bool == false, step["required"] as? Bool != false {
                    await snapshot(name + "-failed"); emit(["state": "native_steps_stopped", "after": name]); break
                }
            }
        }
        emit(["state": "native_loaded", "steps": results, "events": testEvents, "main_frame_loads": mainLoads,
              "isolation": ["support_is_default": supportDirectory().path == defaultSupportDirectory().path, "frame_autosave": window.frameAutosaveName]])
        finishSmoke()
    }
}

if CommandLine.arguments.contains("--self-test") { exit(DesktopSelfTest.run()) }
if smoke && !testModeAllowed() {
    print("{\"state\":\"test_mode_refused\"}"); exit(2)  // 测试模式不得用本用户默认数据目录或未声明的 origin
}
MainActor.assumeIsolated {
    let application = NSApplication.shared
    let delegate = AppDelegate()
    application.delegate = delegate
    application.setActivationPolicy(.regular)
    application.run()
    _ = delegate
}

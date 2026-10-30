// 一起成长桌面入口（内部候选）：AppKit + WKWebView 薄壳，只打开家长已配置的本机原服务。
// 不启动、停止或改动任何后台服务与配置；关窗/退出只影响本窗口。网页不获得任何原生桥接。
import AppKit
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

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
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
    var popups: [NSWindow] = []
    var attempts = 0
    var mainLoads = 0
    var blocked: [String] = []
    var closeApproved = false
    var quitApproved = false
    var lastQuitReply: Bool?
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
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow(); return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    // 退出（含 Cmd+Q）先按页面原有 beforeunload 判断；有未保存内容时默认继续编辑。后台服务不受影响。
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !quitApproved, let web = webView else { return .terminateNow }
        unsaved(web) { dirty in
            let reply = !dirty || self.confirmDiscard("退出")
            self.lastQuitReply = reply
            NSApp.reply(toApplicationShouldTerminate: reply)
        }
        return .terminateLater
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard sender === window, !closeApproved, let web = webView else { return true }
        unsaved(web) { dirty in
            if !dirty || self.confirmDiscard("关闭窗口") { self.closeApproved = true; sender.close() }
        }
        return false
    }

    func windowWillClose(_ notification: Notification) {
        guard let closing = notification.object as? NSWindow else { return }
        if closing === window { window = nil; webView = nil; closeApproved = false }
        popups.removeAll { $0 === closing }
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
        let hint = NSTextField(wrappingLabelWithString: "填写这台 Mac 上一起成长后台的网页地址，或直接使用下面的默认地址。桌面入口不会启动、停止或更改后台。")
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
        setupView.setViews([title, hint, setupField, setupButton, setupMessage], in: .top)
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
        if smoke || w.frame.origin == .zero { w.center() }
        window = w; webView = web
        w.makeKeyAndOrderFront(nil)
        attempts = 0
        connect()
    }

    func status(_ text: String, retry: Bool) {
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
        guard let web = webView, !web.isHidden else { attempts = 0; return showSetup("", typed: typed) }
        unsaved(web) { dirty in
            guard !dirty || self.confirmDiscard("更改地址") else { return }
            self.attempts = 0
            self.showSetup("", typed: typed)
        }
    }

    func showSetup(_ message: String, typed: String) {
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
        nextScriptedSetup()
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
        guard !scriptedInputs.isEmpty else { if mainLoads == 0 { finishSmoke() }; return }
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
        if smoke && mainLoads == 1 { Task { await self.runSmokeChecks(webView) } }
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
                     NSMenuItem.separator(),
                     NSMenuItem(title: "隐藏一起成长", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h"),
                     NSMenuItem.separator(),
                     NSMenuItem(title: "退出桌面入口（后台继续）", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")])
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

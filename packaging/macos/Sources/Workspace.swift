// 一起成长 Mac 原生每日工作台（SwiftUI，挂在原 AppKit 窗口里）：一次一个孩子、按科目平铺的当天清单 + 所选事项详情。
// 只读服务端已准备好的结果，打开不触发采集或模型；写入经原接口与原守卫。原件等富文档、照片检查与其他旧功能经次级网页入口。
import AppKit
import SwiftUI
import UniformTypeIdentifiers

// 颜色、字号与可点高度取自原型 designs/family-grove/styles.css 的 :root（--paper、--leaf-*、--wood-*、--coral-*、--t-*、--hit）。
enum Palette {
    static let paper = Color(red: 0xFB / 255, green: 0xF6 / 255, blue: 0xEA / 255)
    static let paper2 = Color(red: 0xF4 / 255, green: 0xED / 255, blue: 0xDB / 255)
    static let card = Color(red: 0xFF / 255, green: 0xFD / 255, blue: 0xF7 / 255)
    static let desk = Color(red: 0xEA / 255, green: 0xE0 / 255, blue: 0xCA / 255)
    static let line = Color(red: 0xE7 / 255, green: 0xDD / 255, blue: 0xC8 / 255)
    static let line2 = Color(red: 0xD6 / 255, green: 0xC8 / 255, blue: 0xAB / 255)
    static let ink = Color(red: 0x3B / 255, green: 0x33 / 255, blue: 0x26 / 255)
    static let ink2 = Color(red: 0x66 / 255, green: 0x5A / 255, blue: 0x48 / 255)
    static let leaf = Color(red: 0xA8 / 255, green: 0xD9 / 255, blue: 0x78 / 255)
    static let leaf50 = Color(red: 0xF2 / 255, green: 0xF8 / 255, blue: 0xE7 / 255)
    static let leaf100 = Color(red: 0xE3 / 255, green: 0xF1 / 255, blue: 0xD0 / 255)
    static let leaf400 = Color(red: 0x86 / 255, green: 0xBE / 255, blue: 0x59 / 255)
    static let leaf700 = Color(red: 0x2D / 255, green: 0x5A / 255, blue: 0x26 / 255)
    static let leafInk = Color(red: 0x1F / 255, green: 0x4A / 255, blue: 0x1C / 255)
    static let wood = Color(red: 0xF1 / 255, green: 0xE2 / 255, blue: 0xCC / 255)
    static let wood300 = Color(red: 0xD8 / 255, green: 0xB8 / 255, blue: 0x8C / 255)
    static let woodInk = Color(red: 0x6B / 255, green: 0x45 / 255, blue: 0x20 / 255)
    static let coral = Color(red: 0xFD / 255, green: 0xE6 / 255, blue: 0xDD / 255)
    static let coral400 = Color(red: 0xE9 / 255, green: 0x8A / 255, blue: 0x6E / 255)
    static let coralInk = Color(red: 0xA1 / 255, green: 0x3F / 255, blue: 0x2A / 255)
    static let cardShadow = Color(red: 0x6B / 255, green: 0x45 / 255, blue: 0x20 / 255).opacity(0.13)
    static let rounded = Font.system(.body, design: .rounded)
    /// 标题与控件用圆体（--font-round），正文 15、说明 13（--t-m / --t-xs），主要可点区域 44pt 高（--hit）。
    static func round(_ size: CGFloat, _ weight: Font.Weight = .semibold) -> Font { .system(size: size, weight: weight, design: .rounded) }
    static let body = Font.system(size: 15)
    static let small = Font.system(size: 13)
    static let hit: CGFloat = 44
}

/// 三个主入口：日历（本周与所选日，日历内保留“待办/已办”切换）、错题本、学习进展。
enum ListMode: String, CaseIterable, Identifiable { case calendar = "日历", wrong = "错题本", learning = "学习进展"; var id: String { rawValue } }

enum SheetKind: Identifiable {
    case feedback(DayItem), oral, wrong(DayItem, SavedRecord), correction(SavedRecord), addWrong, taskWrong(DayItem), source(DayItem, Publication, String)
    var id: String {
        switch self {
        case .feedback(let i): return "feedback-" + i.id
        case .oral: return "oral"
        case .wrong(let i, let r): return "wrong-\(i.id)-\(r.id)"
        case .correction(let r): return "correction-\(r.id)"
        case .addWrong: return "wrong-add"
        case .taskWrong(let i): return "wrong-task-" + i.id
        case .source(let i, let p, _): return "source-\(i.id)-" + p.ref
        }
    }
}

@MainActor
final class WorkspaceStore: ObservableObject {
    @Published var view: DayView?
    @Published var childID = ""
    @Published var day = ""
    @Published var loading = false
    @Published var error = ""
    @Published var loginRequired = false
    @Published var mode: ListMode = .calendar
    @Published var showDone = false
    /// 日历里“日期未定”一段：服务端 undated 的同一行（与待办/已办同一个切换）。
    @Published var showUndated = false
    @Published var selection: String?
    /// 上一次打开详情的那一项：返回清单后仍标出它（清单本身与滚动位置原样保留）；换孩子时清空。
    @Published var lastOpened: String?
    @Published var sheet: SheetKind?
    @Published var materials: [String: MaterialState] = [:]
    @Published var notice = ""
    /// 错题本 / 学习进展里选中的那一道原错题：按记录编号，不按标题或数组第一个猜；换孩子时清空。
    @Published var record: Int?
    /// 批量照片（PRD 5.1）：当前孩子已导入批次的只读结果与这次还没登记完的导入草稿；换孩子时不带过去，迟到读回不覆盖。
    @Published var photoBatches: [PhotoBatch] = []
    @Published var photoChild = ""
    @Published var photoNotice = ""
    @Published var photoLoadError = ""
    @Published var photoBusy = false
    @Published var photoDraft: PhotoImportDraft?
    @Published var photoPaper: String?
    @Published var photoPaperBatch: String?
    @Published var photoQuestion: String?
    @Published var photoPollToken = 0
    /// 当前页需要读回（GET失败、continue/include 回执不明、原图读不到）：同孩同批同原图只读重读，不重发写入、不调模型。
    /// 按资源分开（批次列表 list、批次状态 batch、每张原图 image:编号）：只有那个资源读成功才清它那一条；显示取其一。
    @Published var photoProblems: [String: String] = [:]
    /// 已按原 /api/day 读回过的批次原错题编号：同一组编号不重复读（有界）；换孩子时清空。
    var photoSyncedRecords: Set<Int> = []
    var photoRecovery: String { photoProblems.sorted { $0.key < $1.key }.first?.value ?? "" }
    @Published var photoImageEpoch = 0
    var photoImages: [String: NSImage] = [:]
    var photoSequence = 0
    /// “回原作业”要在日历里选中的原作业：不在正看的这一天时，先换到原错题记下的那一天，再按作业编号选中。
    var pendingTask: String?
    /// 知识点与练习：同一道原错题（记录编号、孩子编号）的知识点面板。
    var openTopic: (Int, String) -> Void = { _, _ in }
    var sheetDirty = false
    /// 家庭复习卡片的改期草稿与这次提交（按安排编号）：收起、换日/换孩子、列表复用都不丢；只是界面状态，不另存安排。
    var reviewDrafts: [String: ReviewDraft] = [:]
    let client: WorkspaceClient
    var openDocument: (URL, String) -> Void = { _, _ in }
    /// 次级网页：同一份原作业，带明确意图（print-original / print-reference / check / original / history），由网页原流程接着做。
    var openWebTools: (String, String) -> Void = { _, _ in }
    var openSchoolInfo: (String) -> Void = { _ in }
    var openLogin: () -> Void = {}
    var confirmDiscard: (String) -> Bool = { _ in false }
    var onLoaded: () -> Void = {}
    private var sequence = 0

    init(client: WorkspaceClient) { self.client = client }

    /// 未保存的填写：打开着的表单有改动，或家庭复习卡片有改动/保存中/回执不明（关闭窗口、退出与打开网页都先确认）。
    var hasUnsavedInput: Bool { (sheet != nil && sheetDirty) || reviewDrafts.values.contains { $0.dirty || $0.locked } || photoDraft != nil || photoBusy }
    /// 有家庭复习的保存还在进行或回执不明。
    var reviewLocked: Bool { reviewDrafts.values.contains { $0.locked } }
    /// 这时不换孩子、日期，不重读也不换成网页：原卡片和“用同一次提交重试”留在原处（只是有改动的草稿按编号保留，可以照常切换）。
    func reviewHold() -> Bool {
        guard reviewLocked else { return false }
        notice = "有一条家庭复习的保存还没确认：请先在原卡片上“用同一次提交重试”核对，再换孩子、日期或刷新。"
        return true
    }
    /// 待办 / 日期未定 / 已办切换与换孩子、日期走同一守卫：保存未确认的家庭复习卡片和“用同一次提交重试”留在原处，
    /// 弹出层未保存的内容先问；只换显示哪一段，所选事项、草稿和各行原样保留。
    func setScope(_ key: String) {
        if reviewHold() { return }
        guard sheet == nil || !sheetDirty || confirmDiscard("离开当前填写") else { return }
        sheet = nil; sheetDirty = false
        showDone = key == "closed"; showUndated = key == "undated"
    }
    /// 正在显示、可以操作的这一天：只有读回的正是所选孩子、所选日期才算。切换后还没读到或读失败时为 nil——
    /// 上一个孩子/上一天的读取结果只留作缓存（已知孩子仍可切回、重试），不在新选中的孩子/日期下显示、选中、计数或写入。
    var current: DayView? {
        guard let v = view, childID.isEmpty || v.child_id == childID, day.isEmpty || v.day == day else { return nil }
        return v
    }
    var childName: String { current?.child_name ?? "" }
    var groups: [ItemGroup] { showDone ? (current?.closed ?? []) : showUndated ? (current?.undated ?? []) : (current?.groups ?? []) }

    /// 所选日所在的周一至周日。数量只取同一孩子最近一次读回的 week（服务端同一口径）；换了孩子或还没读到时不显示数量，不当 0。
    var weekDays: [WeekDay] {
        guard let base = WorkspaceStore.date(day.isEmpty ? (view?.today ?? "") : day) else { return [] }
        var cal = Calendar(identifier: .gregorian); cal.timeZone = TimeZone(secondsFromGMT: 8 * 3600)!
        let back = (cal.component(.weekday, from: base) + 5) % 7
        let known = (view.map { childID.isEmpty || $0.child_id == childID } ?? false) ? (view?.week ?? []) : []
        return (0..<7).compactMap { n in
            guard let d = cal.date(byAdding: .day, value: n - back, to: base) else { return nil }
            let text = WorkspaceStore.text(d)
            return known.first { $0.day == text } ?? WeekDay(day: text, open: 0, today: 0, overdue: 0, closed: 0, schedule: nil)
        }
    }
    var weekTitle: String {
        let days = weekDays.map(\.day)
        guard let a = days.first, let b = days.last else { return "" }
        return WorkspaceStore.short(a) + " – " + WorkspaceStore.short(b)
    }
    var wrongGroups: [WrongGroup] { current?.wrong ?? [] }
    var allItems: [DayItem] { (current?.groups ?? []).flatMap(\.items) + (current?.undated ?? []).flatMap(\.items) + (current?.closed ?? []).flatMap(\.items) }
    func undatedHas(_ id: String) -> Bool { (current?.undated ?? []).contains { $0.items.contains { $0.id == id } } }
    var selected: DayItem? { allItems.first { $0.id == selection } }
    var wrongItems: [SavedRecord] { wrongGroups.flatMap(\.items) }
    var selectedRecord: SavedRecord? { record.flatMap { id in wrongItems.first { $0.id == id } } }
    func learning(for id: Int) -> LearningEntry? { current?.learning?.subjects.flatMap(\.evidence).first { $0.record_id == id } }

    /// 从学习进展或日历详情打开错题本里的那一道（同一个编号），右栏随即是它的原题、订正与知识点练习。
    func showRecord(_ id: Int) { mode = .wrong; record = id }

    /// 回到同一份原作业：在日历里按作业编号选中；它不在正看的这一天（以前的作业、已办）时，换到原错题记下的那天再选。
    func backToTask(_ task: String, day recordDay: String) {
        guard !task.isEmpty else { return }
        if let item = allItems.first(where: { $0.task_id == task }) { mode = .calendar; showDone = item.closed; showUndated = undatedHas(item.id); select(item.id); return }
        guard sheet == nil || !sheetDirty || confirmDiscard("离开当前填写") else { return }
        mode = .calendar; pendingTask = task
        change(day: recordDay.isEmpty ? day : recordDay)
    }

    func load(keepSelection: Bool = true) async {
        if reviewHold() { return }  // no reload may replace the locked review card (a saved move/cancel/complete would remove it)
        sequence += 1
        let mine = sequence, child = childID, wanted = day
        loading = true
        do {
            let fresh = try await client.day(child: child, day: wanted)
            guard mine == sequence else { return }
            view = fresh; childID = fresh.child_id; day = fresh.day; error = ""; loginRequired = false
            if !keepSelection || !allItems.contains(where: { $0.id == selection }) { selection = nil }
            if let task = pendingTask {
                pendingTask = nil
                if let item = allItems.first(where: { $0.task_id == task }) { showDone = item.closed; showUndated = undatedHas(item.id); selection = item.id; lastOpened = item.id }
                else { notice = "原作业不在这一天的清单里；原错题和订正仍在错题本。" }
            }
            if let id = record, !wrongItems.contains(where: { $0.id == id }) { record = nil }
            if let item = selected, !item.task_id.isEmpty { await loadMaterials(item) }
        } catch {
            guard mine == sequence else { return }
            let e = error as? WorkspaceError
            loginRequired = e?.login == true
            self.error = e?.text ?? "暂时读不到清单，已有记录不受影响；请重试。"
        }
        loading = false
        onLoaded()
    }

    func loadMaterials(_ item: DayItem) async {
        guard !item.task_id.isEmpty else { return }
        let state = await client.materials(task: item.task_id)
        materials[item.task_id] = state
    }

    /// 口头补录交给 /api/study/item 的内容（与网页同一契约）：要做什么必填，第一行作标题；科目可后补（空即“科目待定”）；
    /// 老师要求的完成日、交回日分开，未知留空；做的日子（day）是家里安排的那天，不当作老师日期。重试时同一 key、同一内容。
    static func oralBody(child: String, day: String, key: String, version: Int, subject: String, what: String,
                         completeOn: String, handbackOn: String, attachments: [String] = []) -> [String: Any] {
        let words = what.trimmingCharacters(in: .whitespacesAndNewlines)
        let title = String(words.split(separator: "\n").first ?? Substring(words)).prefix(80).description
        let report: [String: Any] = ["text": words, "explanation": "", "excerpt": "", "goal": "", "attachments": attachments,
                                     "complete_on": completeOn, "handback_on": handbackOn]
        return ["child_id": child, "day": day, "request_key": key, "version": version, "title": title,
                "subject": subject.trimmingCharacters(in: .whitespaces), "planned_minutes": NSNull(), "report": report]
    }

    enum PhotoStop { case unreadable, noID, outcome(PostOutcome) }

    /// 选好的照片按顺序逐张上传，上传过的（同一文件路径）沿用原编号：同一次填写里再按保存不重传。每张照片在第一次发送前定下
    /// 自己的上传标识并一直沿用：回执丢失后再按保存，用同一标识重传，服务端读回已存的那份原件、不另存；换了文件内容或名字会被拒绝。
    /// 读不到文件或某张没保存成功就停下，已得到的编号和标识留着、填写原样保留，不自动重传。反馈、补录与记错题共用；照片上传和
    /// 保存事项是两步，未挂上的原件不算事项；归属由保存接口按孩子核对，这里不挂别的孩子的原件。
    static func uploadPhotos(_ photos: [URL], cached: [String: String], keys: [String: String], read: (URL) -> Data?,
                             send: (Data, String, String) async -> PostOutcome) async
        -> (ids: [String], cached: [String: String], keys: [String: String], stop: PhotoStop?) {
        var cached = cached, keys = keys, ids: [String] = []
        for url in photos {
            if let id = cached[url.path] { ids.append(id); continue }
            guard let data = read(url) else { return (ids, cached, keys, .unreadable) }
            let key = keys[url.path] ?? requestKey(); keys[url.path] = key
            switch await send(data, url.lastPathComponent, key) {
            case .saved(let reply):
                guard let id = (reply["attachment"] as? [String: Any])?["id"] as? String else { return (ids, cached, keys, .noID) }
                cached[url.path] = id; ids.append(id)
            case let other:
                // 同一标识下文件已变（服务端拒绝、未存）：这张照片下次按新的一次选取上传，不拿旧标识反复撞拒绝。
                if case .refused(_, _, let code) = other, code == "upload_key_conflict" { keys.removeValue(forKey: url.path) }
                return (ids, cached, keys, .outcome(other))
            }
        }
        return (ids, cached, keys, nil)
    }

    nonisolated static func readPicked(_ url: URL) -> Data? {
        let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
        return try? Data(contentsOf: url)
    }

    func select(_ id: String?) {
        if TestTargets.enabled { workspaceTestSelectCalls.append(id ?? "nil") }
        selection = id
        if let id { lastOpened = id }
        if let item = selected, !item.task_id.isEmpty, materials[item.task_id] == nil { Task { await loadMaterials(item) } }
    }

    /// 详情的“返回清单/收起详情”：只是不再显示详情，所选项仍在清单里标出，孩子、日期、段落与草稿都不变。
    func closeDetail() { lastOpened = selection ?? lastOpened; selection = nil }

    /// 切换孩子/日期：弹出层有未保存内容时默认留下；不带着上一个孩子的提示。
    func change(child: String? = nil, day newDay: String? = nil) {
        if reviewHold() { return }  // before the header changes: the shown child/day stay what the locked card belongs to
        guard sheet == nil || !sheetDirty || confirmDiscard("离开当前填写") else { return }
        if let child, child != childID {
            // 照片导入草稿属于原孩子：上传/登记进行中不换；还没登记完的先问，放弃后只清草稿，已上传的原件不动。
            if photoBusy { notice = "照片还在上传或登记，请等这一步结束再换孩子。"; return }
            if let draft = photoDraft {
                if draft.sent { notice = "这批照片的登记回执还没确认：请先“用同一提交重试”核对，再换孩子。"; return }
                guard confirmDiscard("放弃这次还没登记的照片导入（已上传的原件保留）") else { return }
                photoDraft = nil
            }
            photoPaper = nil; photoPaperBatch = nil; photoQuestion = nil; photoNotice = ""; photoLoadError = ""; photoProblems = [:]; photoSyncedRecords = []
        }
        sheet = nil; sheetDirty = false; notice = ""
        if let child, child != childID { childID = child; selection = nil; lastOpened = nil; materials = [:]; record = nil; pendingTask = nil }
        if let newDay { day = newDay; selection = selection }
        Task { await load() }
    }

    func shift(_ days: Int) {
        guard let base = WorkspaceStore.date(day.isEmpty ? (view?.today ?? "") : day),
              let next = Calendar(identifier: .gregorian).date(byAdding: .day, value: days, to: base) else { return }
        change(day: WorkspaceStore.text(next))
    }

    func childAt(_ index: Int) { if let list = view?.children, list.indices.contains(index) { change(child: list[index].id) } }

    /// 顶栏日期：所选的那一天（读失败时也不显示上一天）；“今天”用后台给出的今天。
    var dayTitle: String { day.isEmpty ? (loading ? "正在读取…" : "") : WorkspaceStore.spoken(day) }
    var daySub: String {
        guard !day.isEmpty, let today = view?.today else { return "" }
        if day == today { return "今天" }
        return (day < today ? "以前的一天" : "以后的一天") + " · 今天是 \(WorkspaceStore.spoken(today))"
    }

    /// 当天清单的说明：今天要做的、以后安排的、日期未写明的分开数，不把以后安排的算成今天的作业。
    var summary: String {
        guard let v = current else { return loading ? "正在读取…" : "" }
        switch mode {
        case .wrong:
            let all = v.wrong.flatMap(\.items)
            return "错题 \(all.count) 道 · 待订正 \(all.filter { ($0.state ?? "待订正") == "待订正" }.count)"
        case .learning:
            guard let l = v.learning else { return "这一版后台还没有提供学习进展" }
            let n = l.subjects.reduce(0) { $0 + $1.evidence.count }
            return n == 0 ? "按科目看原记录与知识点线索" : "原错题 \(n) 道 · 线索不等于掌握"
        case .calendar:
            if showDone { return "已办 \(v.counts["closed"] ?? 0) 项" }
            if showUndated { return "日期未定 \(v.counts["undated"] ?? 0) 项 · 不算这一天" }
            var parts = ["共 \(v.counts["open"] ?? 0) 项", "今天要做 \(v.counts["today"] ?? 0)"]
            for (key, label) in [("later", "以后安排"), ("overdue", "已过期限"), ("earlier", "之前安排"), ("unknown", "日期未写明"), ("passed", "已过"), ("upcoming", "即将/待补")] {
                if let n = v.counts[key], n > 0 { parts.append("\(label) \(n)") }
            }
            return parts.joined(separator: " · ")
        }
    }

    /// 以后课堂/待补范围的事项（服务端 day_view 同一 upcoming，与网页同一行）：日期、标题、待补与变化；发生日完整列出，不算今天。
    var upcomingLine: String? {
        guard mode == .calendar, !showDone, !showUndated, let u = current?.upcoming, !u.isEmpty else { return nil }
        return "即将/待补：" + u.map { x in
            "\(x.day.dropFirst(5)) \(x.title)" + (x.pending_review ? "（待补）" : "") + ((x.change ?? "").isEmpty ? "" : "（\(x.change ?? "")）")
        }.joined(separator: "；")
    }

    /// 尚无已读行动的学校资料（服务端 day_view 同一 materials，与网页同一行）：每科条数，不算当天要做；原消息与整理状态在网页版。
    var materialsLine: String? {
        guard mode == .calendar, !showDone, !showUndated, let m = current?.materials, !m.isEmpty else { return nil }
        return "学校资料待整理，不算当天要做：" + m.map { "\($0.subject) \($0.items.count) 条" }.joined(separator: "；") + "。"
    }

    static func formatter() -> DateFormatter {
        let f = DateFormatter(); f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 8 * 3600); f.dateFormat = "yyyy-MM-dd"; return f
    }
    static func date(_ text: String) -> Date? { formatter().date(from: text) }
    static func text(_ date: Date) -> String { formatter().string(from: date) }
    static func short(_ text: String) -> String { pattern(text, "M月d日") }
    static func weekday(_ text: String) -> String { pattern(text, "EEE") }
    static func dayNumber(_ text: String) -> String { pattern(text, "d") }
    static func pattern(_ text: String, _ format: String) -> String {
        guard let d = date(text) else { return text }
        let f = DateFormatter(); f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "zh_CN")
        f.timeZone = TimeZone(secondsFromGMT: 8 * 3600); f.dateFormat = format; return f.string(from: d)
    }
    static func spoken(_ text: String) -> String {
        guard let d = date(text) else { return text }
        let f = DateFormatter(); f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "zh_CN")
        f.timeZone = TimeZone(secondsFromGMT: 8 * 3600); f.dateFormat = "M月d日 EEE"; return f.string(from: d)
    }
}

/// 新题再试的短视图：题目、孩子原答、本次结果、知识点、原错题，然后下一步；追溯细节一行小字。行文由后台给出，这里只排版。
struct RetryLines: View {
    let v: RetryView; let note: String
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if !v.status.isEmpty { Text(v.status).font(.caption).foregroundStyle(Palette.coralInk) }
            ForEach(Array(v.lines.enumerated()), id: \.offset) { _, l in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(l.first ?? "").font(.caption).foregroundStyle(Palette.ink2).frame(width: 64, alignment: .leading)
                    Text(l.count > 1 ? l[1] : "").foregroundStyle(Palette.ink).textSelection(.enabled)
                }
            }
            if v.show_note { Text(note).foregroundStyle(Palette.ink).textSelection(.enabled) }
            Text("下一步 " + v.next).font(.callout).foregroundStyle(Palette.ink)
            Text("追溯：" + v.trace).font(.caption2).foregroundStyle(Palette.ink2).textSelection(.enabled)
        }
    }
}

func progressWords(_ p: TaskProgress) -> String {
    var parts: [String] = []
    if p.feedback > 0 { parts.append("反馈\(p.feedback)条") }
    if p.wrong > 0 { parts.append("错题\(p.wrong)道") }
    if p.clues > 0 { parts.append("知识点线索\(p.clues)条（不等于掌握）") }
    if p.retries > 0 { parts.append("独立再试\(p.retries)次") }
    if p.history > 0 { parts.append("更正前的诊断\(p.history)条作历史") }
    return parts.joined(separator: " · ")
}

extension DayItem {
    var whenLabel: String { ["later": "以后安排", "overdue": "已过期限", "earlier": "之前安排", "unknown": "时间未明确", "passed": "已过"][when ?? ""] ?? "" }
    var publishedTime: String { String((published_at ?? "").dropFirst(11).prefix(5)) }
    var source: String { [publisher ?? "", publishedTime].filter { !$0.isEmpty }.joined(separator: " ") }
    var webID: String { task_id.isEmpty ? id : task_id }
    /// 发布一类的事实只是出处，不是要做的日期。
    static let publishRoles: Set<String> = ["published", "publish"]
    var actionFacts: [DayFact] { facts.filter { !DayItem.publishRoles.contains($0.role) } }
    /// 行内的日期角色：完成、交回、提交、检查各写一条，同一天的不同角色也分开写。
    var dayRoles: [DayFact] { facts.filter { ["due", "complete", "submit", "check"].contains($0.role) } }
    /// “时间未明确”只说一次：已有角色写了时间未明确，就不再叠一个同义的整行标记。
    var showsWhen: Bool { !whenLabel.isEmpty && !(when == "unknown" && dayRoles.contains { !$0.known }) }
    /// 来源消息按唯一原消息 ref 计：原布置、更正都只是一条来源消息，不统称“提醒”。
    var sourceRefs: [Publication] { var seen = Set<String>(); return (publications ?? []).filter { seen.insert($0.ref).inserted } }
    /// 行内完整标准：各句照原文接起来，句末已有标点的不再补“；”（不出现“。；”）。
    var standardWords: String { lines.reduce("") { s, l in s.isEmpty ? l : s + ("。；！？!?;".contains(s.last!) ? "" : "；") + l } }
    var sourceWords: String { sourceRefs.count > 1 ? "来源消息\(sourceRefs.count)条" : "" }
    /// 老师与完整发布时间：有发布事实就照写它的原值（未知照写它的原话，如“发布 待核对”）；没有时用原始发布时间的完整日期与时刻。
    var publishWords: String? {
        let when: String
        if let f = facts.first(where: { DayItem.publishRoles.contains($0.role) }) { when = f.known ? f.value + " " + f.label : f.label + " " + f.value }
        else if let at = published_at, !at.isEmpty { when = String(at.prefix(16)).replacingOccurrences(of: "T", with: " ") + " 发布" }
        else { when = "" }
        let words = [publisher ?? "", when].filter { !$0.isEmpty }.joined(separator: " · ")
        return words.isEmpty ? nil : words
    }
}

// MARK: 原型的小部件：44pt 药丸按钮（底部厚边、按下下沉）、木牌、小标记、叶形状态、自动换行的标记行。

/// 原型 .btn / .btn-primary / .btn-quiet：44pt 高的圆角药丸，底部 3pt 厚边，按下时下沉；不可用时虚线框、深灰字仍可读。
struct GroveButtonStyle: ButtonStyle {
    enum Kind { case primary, secondary, quiet }
    var kind: Kind = .secondary
    @Environment(\.isEnabled) private var enabled

    private func colors(_ pressed: Bool) -> (fill: Color, ink: Color, edge: Color) {
        if !enabled { return (kind == .quiet ? Color.clear : Palette.paper2, Palette.ink2, kind == .quiet ? Color.clear : Palette.line2) }
        switch kind {
        case .primary: return (Palette.leaf, Palette.leafInk, Palette.leaf400)
        case .secondary: return (Palette.card, Palette.ink, Palette.line2)
        case .quiet: return (pressed ? Palette.leaf50 : Color.clear, Palette.leaf700, Color.clear)
        }
    }

    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed && enabled
        let c = colors(pressed)
        let lip = kind != .quiet && enabled
        return configuration.label
            .font(Palette.round(14))
            .foregroundStyle(c.ink)
            .padding(.horizontal, kind == .quiet ? 12 : 18)
            .frame(minHeight: Palette.hit)
            .background(Capsule().fill(c.fill))
            .overlay(Capsule().strokeBorder(c.edge, style: StrokeStyle(lineWidth: 1, dash: enabled ? [] : [4, 3])))
            .background(Capsule().fill(lip ? c.edge : Color.clear).offset(y: pressed ? 1 : 3))
            .offset(y: pressed && lip ? 2 : 0)
            .contentShape(Capsule())
    }
}

/// 小标记按行排，放不下就换到下一行：日期、状态与出处文字不被截断。
struct FlowRow: Layout {
    var spacing: CGFloat = 6
    var lineSpacing: CGFloat = 6

    private func measure(_ s: LayoutSubview, _ width: CGFloat) -> CGSize {
        let natural = s.sizeThatFits(.unspecified)
        return natural.width <= width ? natural : s.sizeThatFits(ProposedViewSize(width: width, height: nil))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0, widest: CGFloat = 0
        for s in subviews {
            let size = measure(s, width)
            if x > 0 && x + size.width > width { y += line + lineSpacing; x = 0; line = 0 }
            x += size.width + spacing; line = max(line, size.height); widest = max(widest, x - spacing)
        }
        return CGSize(width: min(widest, width), height: y + line)
    }

    /// 先分好行，再在每行里垂直居中：44pt 按钮和小标记、出处文字排在同一行时中线对齐。
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var lines: [[(LayoutSubview, CGSize)]] = [[]]
        var x = bounds.minX
        for s in subviews {
            let size = measure(s, bounds.width)
            if x > bounds.minX && x + size.width > bounds.maxX { lines.append([]); x = bounds.minX }
            lines[lines.count - 1].append((s, size)); x += size.width + spacing
        }
        var y = bounds.minY
        for line in lines where !line.isEmpty {
            let height = line.map(\.1.height).max() ?? 0
            var x = bounds.minX
            for (s, size) in line {
                s.place(at: CGPoint(x: x, y: y + (height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += height + lineSpacing
        }
    }
}

/// 科目木牌（原型 .sign）：两颗钉眼、木色底和 2pt 下沿；可带项数。
struct WoodTag: View {
    let text: String
    var count = ""
    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(Palette.wood300).frame(width: 4, height: 4)
            Text(text).font(Palette.round(14, .bold))
            if !count.isEmpty { Text(count).font(Palette.round(12)).opacity(0.85) }
            Circle().fill(Palette.wood300).frame(width: 4, height: 4)
        }
        .foregroundStyle(Palette.woodInk)
        .padding(.horizontal, 12).padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(Palette.wood).shadow(color: Palette.wood300, radius: 0, x: 0, y: 2))
        .fixedSize()
        .accessibilityElement(children: .combine)
    }
}

/// 小标记（原型 .chip）：文字自身决定宽度，不截断；dashed 用于“尚未读清”这类需要家长看原件的状态。
struct Badge: View {
    let text: String
    var tone: Color = Palette.wood
    var ink: Color = Palette.woodInk
    var dashed = false
    var body: some View {
        Text(text).font(Palette.round(12.5)).foregroundStyle(ink)
            .padding(.horizontal, 9).padding(.vertical, 3)
            .background(Capsule().fill(dashed ? Palette.card : tone))
            .overlay(Capsule().strokeBorder(dashed ? Palette.coral400 : Color.clear, style: StrokeStyle(lineWidth: 1.5, dash: [4, 3])))
            .fixedSize()
    }
}

/// 原型的叶形勾选：待办是空心圆，已办长成一片带勾的叶子。这里只表示状态，不是“标记已办”按钮。
struct LeafMark: View {
    let closed: Bool
    var body: some View {
        Group {
            if closed {
                ZStack(alignment: .topLeading) { Circle().fill(Palette.leaf400); Rectangle().fill(Palette.leaf400).frame(width: 13, height: 13) }
                    .frame(width: 26, height: 26)
                    .overlay(ZStack(alignment: .topLeading) { Circle().fill(Palette.leaf); Rectangle().fill(Palette.leaf).frame(width: 11.5, height: 11.5) }.frame(width: 23, height: 23))
                    .overlay(Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)).foregroundStyle(Palette.leafInk))
                    .rotationEffect(.degrees(-8))
            } else {
                Circle().strokeBorder(Palette.line2, lineWidth: 2).background(Circle().fill(Palette.card)).frame(width: 26, height: 26)
            }
        }
        .frame(width: 32, height: 32)
    }
}

/// 清单仍是系统 List（键盘上下、真实点击选择照旧），只是不画系统选中底色：选中由行卡片自己的嫩绿底和绿边表达，文字一直是深色。
/// 侧栏样式的系统选中底色是材质，深色字在上面看不清，截图里还会成黑块。
struct HighlightOff: NSViewRepresentable {
    final class Hook: NSView {
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); apply() }
        func apply() {
            var next: NSView? = superview
            while let v = next {
                if let table = v as? NSTableView {
                    if table.selectionHighlightStyle != .none { table.selectionHighlightStyle = .none }
                    if table.backgroundColor != .clear { table.backgroundColor = .clear }
                    // 清单换宽度时是新表格：原表格移出窗口时焦点落回窗口，交给新表格，上下键照旧选行（别处有焦点时不抢）。
                    if let w = table.window, w.firstResponder === w { w.makeFirstResponder(table) }
                    return
                }
                next = v.superview
            }
        }
    }
    func makeNSView(context: Context) -> Hook { Hook() }
    func updateNSView(_ view: Hook, context: Context) { view.apply() }
}

// MARK: 主工作台：顶栏（孩子 / 日期 / 补录 / 网页版）是窗口内容里的真实按钮；左栏清单 + 右栏所选事项详情（两栏，不另加导航栏）。

struct WorkspaceView: View {
    @ObservedObject var store: WorkspaceStore

    var body: some View {
        GeometryReader { geo in
            let compact = geo.size.width < 1180
            VStack(spacing: 0) {
                HeaderBar(store: store, compact: compact)
                if store.mode == .calendar { calendar(compact, width: geo.size.width) } else {
                    // 错题本/学习进展：左栏同宽、位置不动，右栏是所选那一道原错题。
                    HStack(spacing: 0) {
                        SubjectList(store: store).frame(width: compact ? 340 : 400)
                        Rectangle().fill(Palette.line).frame(width: 1)
                        RecordDetail(store: store).frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            }
        }
        .background(Palette.paper)
        .environment(\.colorScheme, .light)
        .sheet(item: $store.sheet) { kind in SheetHost(store: store, kind: kind) }
    }

    /// 日历：没选事项时清单用主要宽度（最宽 860、居中），不留空的右栏。选中后宽窗（≥1180）右侧是这一项的详情；窄窗是带
    /// “返回清单”的详情页，清单只是隐去、不重建，返回时所选项、滚动位置、孩子与日期原样。窗口大小与位置不随之改变。
    func calendar(_ compact: Bool, width: CGFloat) -> some View {
        let open = store.selected != nil
        let side = open && !compact, page = open && compact
        // 清单给确切宽度（与原来固定 340/400 同一做法），不只给上限：系统列表按收到的宽度给每行量高度，只有上限时会按不限宽
        // 量成一行，之后在窄处排开也不重量，长完成标准就被截成省略号。整宽时外层再居中。
        let list: CGFloat = side ? 440 : max(320, min(860, width))
        return ZStack {
            HStack(spacing: 0) {
                SubjectList(store: store, side: side, width: list)
                    .frame(width: list)
                    .frame(maxWidth: side ? nil : .infinity)
                    .opacity(page ? 0 : 1).allowsHitTesting(!page).accessibilityHidden(page)
                if side {
                    Rectangle().fill(Palette.line).frame(width: 1)
                    Inspector(store: store).frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            if page { Inspector(store: store, page: true).frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
    }
}

struct HeaderBar: View {
    @ObservedObject var store: WorkspaceStore
    var compact = false

    var body: some View {
        HStack(spacing: compact ? 8 : 12) {
            Group {
                if compact { Image(systemName: "leaf").accessibilityLabel("一起成长") } else { Label("一起成长", systemImage: "leaf") }
            }
            .font(Palette.round(15, .bold)).foregroundStyle(Palette.leafInk)
            HStack(spacing: 3) {
                ForEach(Array((store.view?.children ?? []).enumerated()), id: \.element.id) { index, c in
                    let on = c.id == store.childID
                    Button { store.change(child: c.id) } label: {
                        Text(c.name).font(Palette.round(14)).lineLimit(1).fixedSize().padding(.horizontal, 12).frame(minWidth: 64, minHeight: Palette.hit).contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(on ? Palette.leafInk : Palette.woodInk)
                    .background(Capsule().fill(on ? Palette.card : Color.clear).shadow(color: on ? Palette.wood300 : Color.clear, radius: 0, x: 0, y: 2))
                    .accessibilityAddTraits(on ? .isSelected : [])
                    .help("只看\(c.name)（⌘\(index + 1)）")
                    .probe("child-" + c.id, text: c.name + (on ? " 当前" : ""))
                }
            }
            .padding(3).background(Capsule().fill(Palette.wood))
            Spacer(minLength: 8)
            Button { store.shift(-1) } label: { Image(systemName: "chevron.left").font(.system(size: 15, weight: .semibold)).frame(width: Palette.hit, height: Palette.hit).contentShape(Circle()) }
                .buttonStyle(.plain).foregroundStyle(Palette.ink).accessibilityLabel("前一天").help("前一天 ⌘[").probe("day-prev")
            VStack(spacing: 1) {
                Text(store.dayTitle).font(Palette.round(17, .bold)).foregroundStyle(Palette.ink)
                Text(store.daySub).font(.system(size: 12)).foregroundStyle(Palette.ink2).lineLimit(1)
            }
            .frame(minWidth: compact ? 120 : 150).accessibilityElement(children: .combine)
            .probe("day-title", text: store.day + " " + store.daySub)
            Button { store.shift(1) } label: { Image(systemName: "chevron.right").font(.system(size: 15, weight: .semibold)).frame(width: Palette.hit, height: Palette.hit).contentShape(Circle()) }
                .buttonStyle(.plain).foregroundStyle(Palette.ink).accessibilityLabel("后一天").help("后一天 ⌘]").probe("day-next")
            Button(compact ? "今天" : "回到今天") { store.change(day: store.view?.today ?? "") }
                .buttonStyle(GroveButtonStyle(kind: .quiet))
                .disabled(store.view == nil || store.day == store.view?.today).help("回到今天 ⌘T").probe("day-today")
            Spacer(minLength: 8)
            Button { store.sheetDirty = false; store.sheet = .oral } label: { Label(compact ? "补录" : "补录口头作业", systemImage: "plus") }
                .buttonStyle(GroveButtonStyle(kind: .primary))
                .disabled(store.current == nil).help("补录孩子口头转述的作业 ⌘N").probe("oral-new")
            Button { store.openWebTools("", "") } label: { Label(compact ? "网页版" : "网页版工具", systemImage: "square.grid.2x2") }
                .buttonStyle(GroveButtonStyle())
                .help("学校消息、打印、设置，以及日历编辑与课表导入 ⌘E；网页上方有“← 返回清单”").probe("web-tools")
        }
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 11)
        .background(Palette.paper2)
        .overlay(alignment: .bottom) { Rectangle().fill(Palette.line).frame(height: 1) }
    }
}

func factTone(_ f: DayFact) -> (Color, Color) {
    f.state == "next_morning" || f.state == "overdue" ? (Palette.coral, Palette.coralInk) : f.known ? (Palette.wood, Palette.woodInk) : (Palette.paper2, Palette.ink2)
}

func factWords(_ f: DayFact) -> String {
    if f.state == "next_morning" { return f.label + " 明天" }  // 只知道日期是明天，不写“明早”
    if f.state == "overdue" { return "已逾期 · " + f.value }
    if f.role == "complete", f.today == true { return "今天完成" }
    if f.role == "submit", f.today == true { return "今天先提交" }
    if f.role == "check", f.today == true { return "今天先检查" }
    return f.known ? f.label + " " + f.value : f.label + "时间未明确"
}

struct SubjectList: View {
    @ObservedObject var store: WorkspaceStore
    /// 宽窗里所选项的详情在右侧时清单变窄：行高要按新宽度重算。
    var side = false
    /// 日历清单的确切宽度（0：错题本/学习进展，不用）。
    var width: CGFloat = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            modeSwitch.frame(maxWidth: 520).padding(.horizontal, 14).padding(.top, 14)
            if store.mode == .calendar { WeekStrip(store: store).padding(.horizontal, 14).padding(.top, 8) }
            HStack(alignment: .center, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(store.mode == .calendar ? (store.showDone ? "这一天已办" : store.showUndated ? "日期未定/待安排" : "当天清单") : store.mode.rawValue).font(Palette.round(21, .bold)).foregroundStyle(Palette.ink)
                    Text(store.summary).font(.system(size: 14)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("list-summary", text: store.summary)
                }
                Spacer(minLength: 4)
                if store.mode == .calendar { doneSwitch }
            }.padding(.horizontal, 18).padding(.top, 10).padding(.bottom, 6)
            if store.loginRequired {
                VStack(alignment: .leading, spacing: 10) {
                    Text("需要先登录家庭账号。点下面的按钮会打开登录窗口，登录成功后窗口自动关闭、清单随即更新；填写中的内容不会丢。").font(Palette.body).foregroundStyle(Palette.coralInk)
                        .fixedSize(horizontal: false, vertical: true)
                    Button("登录家庭账号") { store.openLogin() }.buttonStyle(GroveButtonStyle(kind: .primary)).probe("login-open")
                }
                .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.coral))
                .padding(.horizontal, 14).padding(.vertical, 6).probe("login-needed", text: "需要登录")
            } else if !store.error.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text(store.error).font(Palette.body).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true).probe("load-error", text: store.error)
                    Button("重试") { Task { await store.load() } }.buttonStyle(GroveButtonStyle()).probe("load-retry")
                }
                .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.coral))
                .padding(.horizontal, 14).padding(.vertical, 6)
            }
            // 保存成功、回原作业找不到等结果的一句话：直接显示在清单上方，可收起；换孩子/日期时清空。
            if !store.notice.isEmpty {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "info.circle").foregroundStyle(Palette.leafInk).frame(minHeight: 22)
                    Text(store.notice).font(Palette.body).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                        .probe("workspace-notice", text: store.notice)
                    Button { store.notice = "" } label: { Image(systemName: "xmark").frame(width: 28, height: 28) }
                        .buttonStyle(.plain).foregroundStyle(Palette.ink2).help("收起这条提示").probe("notice-dismiss")
                }
                .padding(EdgeInsets(top: 10, leading: 14, bottom: 10, trailing: 8)).frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Palette.leaf100))
                .padding(.horizontal, 14).padding(.vertical, 4)
            }
            if let text = store.current?.source_error, !text.isEmpty {
                Text(text).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true).padding(.horizontal, 18).padding(.vertical, 6)
            }
            // 与网页清单同一条提示：这个孩子还有学校消息没整理完，清单可能不完整（读取成功与整理完是两回事）；整理状态沿网页版查看。
            if let count = store.current?.school_pending, count > 0 {
                let words = "还有 \(count) 条学校消息尚未整理，作业清单可能不完整。原消息已保存。"
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(words).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true).probe("school-pending", text: words)
                    Button("在网页版查看整理状态") { store.openSchoolInfo(store.current?.child_id ?? store.childID) }.buttonStyle(.borderless).controlSize(.small).probe("school-pending-open")
                }
                .padding(.horizontal, 18).padding(.vertical, 6)
            }
            // 与网页同一规则：这个孩子的来源最近没读成功或待核对时清单可能缺项（读成功但 0 条新消息不算缺口）；状态本身读不到就如实说无法核对。
            if let gaps = store.current?.school_read_gaps, !gaps.isEmpty {
                let words = "消息读取有缺口，清单可能缺项：" + gaps.map { $0.name + " " + $0.status }.joined(separator: "；") + "。"
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(words).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true).probe("school-read-gap", text: words)
                    Button("在网页版检查最新消息") { store.openWebTools("", "") }.buttonStyle(.borderless).controlSize(.small).probe("school-read-gap-open")
                }
                .padding(.horizontal, 18).padding(.vertical, 6)
            } else if store.current?.school_unknown == true {
                let words = "学校消息的读取状态暂时无法核对，清单可能不完整。"
                Text(words).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 18).padding(.vertical, 6).probe("school-read-unknown", text: words)
            }
            switch store.mode {
            case .calendar: itemList
            case .wrong: WrongList(store: store)
            case .learning: LearningList(store: store)
            }
        }
        .background(Palette.paper)
    }

    func label(_ mode: ListMode) -> String {
        guard let v = store.current else { return mode.rawValue }
        switch mode {
        case .calendar: return "日历"
        case .wrong: let n = v.wrong.flatMap(\.items).count; return n > 0 ? "错题本 \(n)" : "错题本"
        case .learning: return "学习进展"
        }
    }

    /// 日历内保留原来的“待办 / 已办”切换（同一份服务端 groups/closed），每段 44pt。
    var doneSwitch: some View {
        HStack(spacing: 3) {
            ForEach(["open", "undated", "closed"].filter { $0 != "undated" || store.showUndated || (store.current?.counts["undated"] ?? 0) > 0 }, id: \.self) { key in
                let on = key == "closed" ? store.showDone : key == "undated" ? store.showUndated : !store.showDone && !store.showUndated
                let n = store.current?.counts[key] ?? 0
                let text = (key == "closed" ? "已办" : key == "undated" ? "日期未定" : "待办") + (n > 0 ? " \(n)" : "")
                Button { store.setScope(key) } label: {
                    Text(text).font(Palette.round(13)).padding(.horizontal, 10).frame(minWidth: 58, minHeight: Palette.hit).contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .foregroundStyle(on ? Palette.leafInk : Palette.woodInk)
                .background(Capsule().fill(on ? Palette.card : Color.clear).shadow(color: on ? Palette.wood300 : Color.clear, radius: 0, x: 0, y: 2))
                .accessibilityAddTraits(on ? .isSelected : [])
                .probe(key == "closed" ? "mode-已办" : key == "undated" ? "mode-日期未定" : "mode-当天", text: text)
            }
        }
        .padding(3).background(Capsule().fill(Palette.wood))
    }

    /// 所选日的课表节次与日程，排在按科事项之前；读不到时如实说明，不当作没课。
    @ViewBuilder var scheduleSection: some View {
        if let text = store.current?.schedule_error, !text.isEmpty {
            Section {
                Text(text).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                    .listRowSeparator(.hidden).probe("schedule-error", text: text)
            } header: { WoodTag(text: "课表与日程").padding(.top, 8).padding(.bottom, 2) }
        } else if let s = store.current?.schedule, !(s.lessons.isEmpty && s.plans.isEmpty) {
            Section {
                ForEach(s.lessons) { t in LessonCard(table: t).listRowSeparator(.hidden) }
                // 家庭复习卡片不参加任务列表的选中（行键不是 String、也不加 tag）：点日期/时间直接交给控件，列表不选中这条复习、不抢焦点；
                // 其他日程行仍按原编号 tag，选中照旧。
                ForEach(s.plans, id: \.listKey) { p in
                    let row = PlanRow(plan: p, openReview: { r in store.openTopic(r.record_id, r.child_id) },
                                      draft: p.review == nil ? nil : store.reviewDraft(p, day: store.day),
                                      edit: { d, status in await store.saveReview(p.id, from: store.day, draft: d, status: status) },
                                      restart: { store.reviewDrafts[p.id] = nil; Task { await store.load() } })
                        .listRowSeparator(.hidden)
                    if p.review == nil { row.tag(p.id) } else { row }
                }
                if s.cancelled > 0 { Text("另有 \(s.cancelled) 项安排已取消，未列出。").font(Palette.small).foregroundStyle(Palette.ink2).listRowSeparator(.hidden) }
            } header: {
                WoodTag(text: "课表与日程", count: "\(s.lessons.reduce(0) { $0 + $1.sessions.count } + s.plans.count) 项").padding(.top, 8).padding(.bottom, 2)
                    .probe("schedule-head")
            }
        }
    }

    /// 日历 / 错题本 / 学习进展：原型的木色分段，每段 44pt 高，选中段是卡片色和绿字。
    var modeSwitch: some View {
        HStack(spacing: 3) {
            ForEach(ListMode.allCases) { m in
                let on = store.mode == m
                Button { store.mode = m } label: {
                    Text(label(m)).font(Palette.round(14)).frame(maxWidth: .infinity, minHeight: Palette.hit).contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .foregroundStyle(on ? Palette.leafInk : Palette.woodInk)
                .background(Capsule().fill(on ? Palette.card : Color.clear).shadow(color: on ? Palette.wood300 : Color.clear, radius: 0, x: 0, y: 2))
                .accessibilityAddTraits(on ? .isSelected : [])
                .probe("mode-" + m.id, text: label(m))
            }
        }
        .padding(3).background(Capsule().fill(Palette.wood))
        .probe("list-mode")
    }

    var itemList: some View {
        ScrollViewReader { proxy in
        List(selection: Binding(get: { store.selection }, set: { store.select($0) })) {
            // 课表与日程只属于这一天的待办；日期未定、已办不混入当天课程和计划。换段走 setScope 的 reviewHold：未确认保存的复习卡片
            // 留在待办可见可重试，草稿仍在 reviewDrafts。
            if !store.showDone && !store.showUndated { scheduleSection }
            ForEach(store.groups, id: \.subject) { group in
                Section {
                    ForEach(group.items) { item in
                        ItemRow(item: item, selected: store.selection == item.id || (store.selection == nil && store.lastOpened == item.id),
                                textWidth: width > 0 ? ItemRow.textWidth(list: width) : nil).tag(item.id).probe("row-" + item.id, text: item.title)
                            .listRowSeparator(.hidden)
                    }
                } header: {
                    WoodTag(text: group.subject, count: group.countWords).padding(.top, 8).padding(.bottom, 2)
                        .probe("subject-" + group.subject)
                }
            }
            if store.groups.isEmpty && store.current != nil {
                Text(store.showDone ? "这一天没有已办的事项。" : store.showUndated ? "没有日期未定的事项。" : "这一天没有已整理的未完成事项；没有反馈不等于没做。")
                    .font(Palette.body).foregroundStyle(Palette.ink2).probe("list-empty")
            }
            if let line = store.upcomingLine {
                Text(line).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                    .listRowSeparator(.hidden).probe("upcoming", text: line)
            }
            if let line = store.materialsLine {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(line).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("materials", text: line)
                    Button("在网页版查看原消息与整理状态") { store.openSchoolInfo(store.current?.child_id ?? store.childID) }.buttonStyle(.borderless).controlSize(.small).probe("materials-open")
                }
                .listRowSeparator(.hidden)
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        // 整宽与右侧详情之间换一张清单：每张只在自己的确切宽度下量行高、不在使用中改宽；随即滚回所选/刚看过的那一项，
        // 键盘焦点由行里的 HighlightOff 交给新表格。
        .id(side)
        .onAppear { if let id = store.selection ?? store.lastOpened { proxy.scrollTo(id, anchor: .center) } }
        .probe("subject-list")
        }
    }
}

/// 清单一行是一张卡片（原型 .row）：做什么、完整完成标准、完成/交回日、出处与已有进展；选中是嫩绿底加绿边，文字保持深色。
struct ItemRow: View {
    let item: DayItem
    var selected = false
    /// 文字一栏的确切宽度。系统列表按行的理想尺寸（不限宽）定行高：只靠 fixedSize 时长文字被量成一行，排开时截成“…”，
    /// 与有无验收锚点无关。给文字栏定宽后，理想尺寸就是这个宽度下完整换行的高度，正式与验收同一布局。
    var textWidth: CGFloat? = nil
    /// 清单宽度减去：卡片内 58（左 6、叶形 32、间距 8、右 12），行左右留白至多 20+20（M6 截图 860 宽时实测约 16/17），
    /// 常显滚动条至多 16。宁可右侧多留一点空，也不让文字栏比行宽。
    static func textWidth(list: CGFloat) -> CGFloat { max(160, list - 114) }
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            LeafMark(closed: item.closed).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(item.title).font(Palette.round(15, .bold)).foregroundStyle(item.closed ? Palette.ink2 : Palette.ink)
                    .lineLimit(nil).fixedSize(horizontal: false, vertical: true)
                if let first = item.lines.first {
                    // 完整写出，不截断；不加 .help（它把文字包进平台视图，清单行高只按一行算，会截成省略号）。
                    Text(item.standardWords).font(Palette.small).foregroundStyle(Palette.ink2).lineSpacing(2).lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true).accessibilityHint(first).modifier(FitProbe(id: "row-fit-" + item.id))
                    if let v = item.version {
                        // 冒烟锚点只给这一行此刻显示的同一句话，按事项 id 区分（各行的版本提示不再共用一个标识）。
                        let words = v.state == "latest" ? "学校要求已更新：\(v.change ?? "")" : (v.note ?? "有新通知待核对")
                        Text(words).font(Palette.small).foregroundStyle(Palette.coralInk).probe("row-version-" + item.id, text: words)
                    }
                } else { Text("完成标准未提供，待补充").font(Palette.small).foregroundStyle(Palette.coralInk) }
                FlowRow(spacing: 6, lineSpacing: 4) {
                    if item.showsWhen { Badge(text: item.whenLabel, tone: Palette.paper2, ink: Palette.ink2) }
                    ForEach(item.dayRoles, id: \.self) { f in
                        let (tone, ink) = factTone(f)
                        Badge(text: factWords(f), tone: tone, ink: ink)
                    }
                    ForEach(item.times ?? [], id: \.self) { t in Badge(text: "日程 " + planClock(t.start_time, t.end_time), tone: Palette.leaf100, ink: Palette.leafInk) }
                    if item.pending_review { Badge(text: "待核对", tone: Palette.coral, ink: Palette.coralInk) }
                }
                .padding(.top, 2)
                let meta = [item.source, item.sourceWords, item.progress.map(progressWords) ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
                if !meta.isEmpty { Text(meta).font(.system(size: 12.5)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("row-meta-" + item.id, text: meta) }
            }
            .frame(width: textWidth, alignment: .leading)
            Spacer(minLength: 0)
        }
        .padding(EdgeInsets(top: 10, leading: 6, bottom: 12, trailing: 12))
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(selected ? Palette.leaf50 : Palette.card).shadow(color: Palette.cardShadow, radius: 4, x: 0, y: 2))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(selected ? Palette.leaf400 : Palette.line, lineWidth: selected ? 1.5 : 1))
        .padding(.vertical, 4)
        .background(HighlightOff())
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// 只在原生验收里：这段文字实际排开的高度与同宽下完整排开所需的高度（同一 SwiftUI 排版，隐藏副本量），给出 fits/cut 与两者数值；
/// 量的是几何高度，不凭文字内容判断有没有截断。正式使用时不加任何视图。
struct FitProbe: ViewModifier {
    let id: String
    @State private var shown: CGFloat = 0
    @State private var need: CGFloat = 0
    func body(content: Content) -> some View {
        if TestTargets.enabled {
            content
                .background(GeometryReader { g in Color.clear.onAppear { shown = g.size.height }.onChange(of: g.size.height) { shown = $0 } })
                .overlay(alignment: .topLeading) {
                    content.fixedSize(horizontal: false, vertical: true).hidden()
                        .background(GeometryReader { g in Color.clear.onAppear { need = g.size.height }.onChange(of: g.size.height) { need = $0 } })
                }
                .probe(id, text: (need > 0 && shown + 0.5 >= need ? "fits" : "cut") + " h=\(Int(shown.rounded())) need=\(Int(need.rounded(.up)))")
        } else { content }
    }
}

/// 错题本：左栏是可选中的错题（按编号），右栏是所选那一道；空本和有错题时都能直接记一道。
struct WrongList: View {
    @ObservedObject var store: WorkspaceStore
    var body: some View {
        List(selection: Binding(get: { store.record }, set: { store.record = $0 })) {
            if store.current != nil { PhotoImportSection(store: store).listRowSeparator(.hidden); addRow.listRowSeparator(.hidden) }
            ForEach(store.wrongGroups, id: \.subject) { group in
                Section {
                    ForEach(group.items) { r in
                        WrongRow(record: r, selected: store.record == r.id).tag(r.id).probe("wrong-row-\(r.id)", text: r.title + " " + (r.state ?? ""))
                            .listRowSeparator(.hidden)
                    }
                } header: { WoodTag(text: group.subject, count: "\(group.items.count) 道").padding(.top, 8).padding(.bottom, 2) }
            }
        }
        .listStyle(.sidebar).scrollContentBackground(.hidden).probe("wrong-list")
    }

    /// 作业里的错题从那一项的反馈记（挂在同一份作业下）；没有原作业的题在这里用照片单独记，不新建作业或反馈。
    var addRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            if store.wrongGroups.isEmpty {
                Text(store.photoProblems["day"] != nil ? "导入的错题已保存，原错题清单待更新。" : "还没有记下的错题。").font(Palette.round(15, .bold)).foregroundStyle(Palette.ink).probe("wrong-empty")
                Text("作业里的错题：在日历里选那一项，写反馈后点“记一道错题”。没有原作业的题，用下面的按钮拍照记下。")
                    .font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
            }
            Button { store.sheet = .addWrong; store.sheetDirty = false } label: { Label("记一道错题（没有原作业）", systemImage: "plus") }
                .buttonStyle(GroveButtonStyle(kind: store.wrongGroups.isEmpty ? .primary : .secondary)).probe("wrong-add")
        }
        .padding(.vertical, 6).frame(maxWidth: .infinity, alignment: .leading)
    }
}

func stateBadge(_ state: String?) -> Badge {
    let s = state ?? "待订正"
    return Badge(text: s, tone: s == "待订正" ? Palette.coral : Palette.leaf100, ink: s == "待订正" ? Palette.coralInk : Palette.leafInk)
}

/// 错题本一行：题目、原记录开头两行、记下的日子与原作业（或未关联）；选中同日历行：嫩绿底加绿边。操作都在右栏。
struct WrongRow: View {
    let record: SavedRecord
    var selected = false
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(record.title).font(Palette.round(15, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 6)
                stateBadge(record.state)
            }
            if !record.note.isEmpty {
                Text(record.note.replacingOccurrences(of: "\n", with: "；")).font(Palette.small).foregroundStyle(Palette.ink2).lineSpacing(2).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text([record.day, record.task_title.map { "原作业：" + $0 } ?? "未关联原作业"].filter { !$0.isEmpty }.joined(separator: " · "))
                .font(.system(size: 12.5)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
        }
        .padding(EdgeInsets(top: 10, leading: 12, bottom: 12, trailing: 12))
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(selected ? Palette.leaf50 : Palette.card).shadow(color: Palette.cardShadow, radius: 4, x: 0, y: 2))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(selected ? Palette.leaf400 : Palette.line, lineWidth: selected ? 1.5 : 1))
        .padding(.vertical, 4)
        .background(HighlightOff())
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

func topicWords(_ t: LearningTopic) -> String {
    let current = t.basis == "current"
    if t.state == "linked" { return (current ? "已关联 " : "历史关联 ") + t.name + (current ? " · 待诊断" : "") }
    return (current ? "知识点 " : "历史 ") + t.name
}

/// 错题本与学习进展的右栏：所选那一道原错题——原题与作答、知识点与练习、订正与原作业；和日历右栏同一位置、同一宽度。
struct RecordDetail: View {
    @ObservedObject var store: WorkspaceStore
    /// 较长原记录：按编号只读取同一条记录的完整原文（GET /api/record/history/编号 的 current），不改记录。
    @State var full: [Int: String] = [:]
    @State var fullError: [Int: String] = [:]
    @State var fullBusy = false

    func readFull(_ id: Int) async {
        fullBusy = true; fullError[id] = nil
        do {
            let data = try await store.client.get("/api/record/history/\(id)")
            let current = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["current"] as? [String: Any]
            if let note = current?["note"] as? String, current?["id"] as? Int == id { full[id] = note }
            else { fullError[id] = "完整原记录暂时读不到，记录未更改；可以重试。" }
        } catch { fullError[id] = (error as? WorkspaceError)?.text ?? "完整原记录暂时读不到，记录未更改；可以重试。" }
        fullBusy = false
    }
    var body: some View {
        Group {
            if let r = store.selectedRecord { detail(r) }
            else if let shown = store.selectedPhotoPaper { PhotoPaperDetail(store: store, batch: shown.0, paper: shown.1) }
            else {
                VStack(spacing: 10) {
                    Image(systemName: "leaf").font(.largeTitle).foregroundStyle(Palette.leafInk)
                    Text(store.current == nil ? (store.loading || store.error.isEmpty ? "正在读取…" : "还没读到所选孩子的记录，可在左边重试。")
                         : store.wrongItems.isEmpty ? "还没有错题。可在左边记一道，或在日历里那一项的反馈下记。" : "从左边选一道错题，查看原题、订正和知识点练习。")
                        .font(Palette.body).foregroundStyle(Palette.ink2).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true).padding(.horizontal, 32)
                        .probe("record-placeholder")
                }.frame(maxWidth: .infinity, maxHeight: .infinity).background(Palette.paper)
            }
        }
    }

    func card<Content: View>(_ title: String, _ symbol: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: symbol).font(Palette.round(17, .bold)).foregroundStyle(Palette.ink)
            VStack(alignment: .leading, spacing: 10) { content() }
                .padding(EdgeInsets(top: 14, leading: 18, bottom: 16, trailing: 18)).frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card).shadow(color: Palette.cardShadow, radius: 6, x: 0, y: 3))
        }
    }

    /// 知识点练习只有数学知识包；知识包缺失或科目不符时写明原因，原题与订正照常。
    func practiceGap(_ r: SavedRecord) -> String {
        guard let l = store.current?.learning else { return "这一版后台还没有提供知识点练习；原题与订正照常可用。" }
        if !l.pack.installed { return "数学知识包未安装或版本不符：原题与订正照常可用，暂不能做知识点练习。" }
        if r.subject.isEmpty { return "这道错题没写科目，不会被猜成数学：知识点练习目前只有数学知识包。原题、原图和订正照常可用；以后记数学错题时科目写“数学”，就能做知识点练习。" }
        if !r.subject.contains("数学") { return "知识点练习目前只有数学知识包；\(r.subject)的错题照常记订正。" }
        return ""
    }

    func detail(_ r: SavedRecord) -> some View {
        let entry = store.learning(for: r.id)
        let taskWords = r.task_title.map { "原作业：" + $0 } ?? "未关联原作业（单独记下的错题）"
        let gap = practiceGap(r)
        let note = full[r.id] ?? r.note
        return ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 10) {
                    FlowRow(spacing: 10, lineSpacing: 6) {
                        WoodTag(text: r.subject.isEmpty ? WorkspaceStore.unknown : r.subject)
                        stateBadge(r.state)
                        Text("\(store.childName) · 记于 \(r.day)").font(Palette.small).foregroundStyle(Palette.ink2).frame(minHeight: 26)
                    }
                    Text(r.title).font(Palette.round(26, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    FlowRow(spacing: 10, lineSpacing: 6) {
                        Text(taskWords).font(Palette.body).foregroundStyle(Palette.ink2).frame(minHeight: Palette.hit)
                        if let task = r.task_id, !task.isEmpty {
                            Button { store.backToTask(task, day: r.day) } label: { Label("回原作业", systemImage: "arrow.uturn.left") }
                                .buttonStyle(GroveButtonStyle(kind: .quiet)).help("回到日历，选中同一份原作业").probe("record-task-\(r.id)")
                        }
                    }
                }
                .probe("wrong-detail-\(r.id)", text: r.title + " " + taskWords + " " + r.note)
                card("原题与作答", "doc.text") {
                    if note.isEmpty { Text("原记录没有写题面和作答。").font(Palette.body).foregroundStyle(Palette.ink2) }
                    ForEach(Array(note.split(separator: "\n").enumerated()), id: \.offset) { _, line in
                        Text(String(line)).font(Palette.body).foregroundStyle(Palette.ink).lineSpacing(3).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    }
                    if r.note_truncated && full[r.id] == nil {
                        FlowRow(spacing: 10, lineSpacing: 6) {
                            Text("原记录更长，这里只显示前一部分。").font(Palette.small).foregroundStyle(Palette.ink2).frame(minHeight: Palette.hit)
                            Button { Task { await readFull(r.id) } } label: { Label(fullBusy ? "正在读取…" : "读完整原记录", systemImage: "text.justify.left") }
                                .buttonStyle(GroveButtonStyle(kind: .quiet)).disabled(fullBusy).help("只读取这一条记录的完整原文，不改记录").probe("record-full-\(r.id)")
                        }
                        if let e = fullError[r.id] { Text(e).font(Palette.small).foregroundStyle(Palette.coralInk).probe("record-full-error", text: e) }
                    }
                    if !r.attachments.isEmpty {
                        // 原图逐张可开：同源 /upload/编号，与资料“打开原件”同一个窗口和登录；原图不重做、不经模型。
                        FlowRow(spacing: 8, lineSpacing: 6) {
                            ForEach(Array(r.attachments.enumerated()), id: \.offset) { n, id in
                                Button { store.openDocument(store.client.url("/upload/" + id), r.title + (r.attachments.count > 1 ? " · 原图 \(n + 1)" : " · 原图")) } label: {
                                    Label(r.attachments.count > 1 ? "看原图 \(n + 1)" : "看原图", systemImage: "photo")
                                }
                                .buttonStyle(GroveButtonStyle(kind: .quiet)).help("另开窗口看原样保留的原图").probe("record-original-\(r.id)-\(n)")
                            }
                            Text("原图 \(r.attachments.count) 张，原样保留").font(Palette.small).foregroundStyle(Palette.ink2).frame(minHeight: Palette.hit)
                        }
                    }
                }
                card("知识点与练习", "leaf") {
                    if let topics = entry?.topics, !topics.isEmpty {
                        FlowRow(spacing: 6, lineSpacing: 4) {
                            ForEach(topics, id: \.self) { t in
                                Badge(text: topicWords(t), tone: t.basis == "current" && t.state != "linked" ? Palette.leaf100 : Palette.paper2,
                                      ink: t.basis == "current" && t.state != "linked" ? Palette.leafInk : Palette.ink2)
                            }
                        }
                    }
                    ForEach(Array((entry?.lines ?? []).enumerated()), id: \.offset) { _, line in
                        HStack(alignment: .top, spacing: 8) {
                            Text(line.first ?? "").font(.system(size: 12.5, weight: .semibold)).foregroundStyle(Palette.woodInk).frame(width: 78, alignment: .leading)
                            Text(line.count > 1 ? line[1] : "").font(Palette.small).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if let next = entry?.next, !next.isEmpty { Text("下一步：" + next).font(Palette.small).foregroundStyle(Palette.leafInk).fixedSize(horizontal: false, vertical: true) }
                    if gap.isEmpty {
                        Button { store.openTopic(r.id, store.childID) } label: { Label("知识点与练习", systemImage: "leaf") }
                            .buttonStyle(GroveButtonStyle(kind: .primary)).probe("record-topic-\(r.id)")
                        Text("就这一道原错题：确认知识点，做诊断小题、看说明，再做一道没见过的新题；结果存回这道错题。一次做对不等于掌握。")
                            .font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                    } else { Text(gap).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("record-topic-gap-\(r.id)", text: gap) }
                }
                card("订正", "pencil") {
                    if (r.followups ?? []).isEmpty { Text("还没有订正记录。").font(Palette.small).foregroundStyle(Palette.ink2) }
                    ForEach(r.followups ?? []) { f in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                Badge(text: f.followup_kind.isEmpty ? "跟进" : f.followup_kind)
                                Text(f.created.prefix(16).replacingOccurrences(of: "T", with: " ")).font(Palette.small).foregroundStyle(Palette.ink2)
                            }
                            Text(f.note.isEmpty ? f.title : f.note).font(Palette.body).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                            if let line = f.evidenceLine { Text(line).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("followup-evidence-\(f.id)", text: line) }
                        }
                    }
                    Button("记订正") { store.sheet = .correction(r); store.sheetDirty = false }.buttonStyle(GroveButtonStyle()).probe("wrong-correct-\(r.id)")
                }
            }
            .padding(.horizontal, 32).padding(.top, 24).padding(.bottom, 40)
            .frame(maxWidth: 860, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Palette.paper)
        .probe("record-detail")
    }
}

func planClock(_ start: String, _ end: String) -> String { start.isEmpty ? "时间未写明" : end.isEmpty ? start : start + "–" + end }

/// 本周一至周日：每天一格（星期、日期、与单日同口径的“当天要做”数量、有课表或日程时一个小点），点哪天看哪天。
struct WeekStrip: View {
    @ObservedObject var store: WorkspaceStore
    var body: some View {
        VStack(spacing: 4) {
            HStack(spacing: 2) {
                Text(store.weekTitle).font(Palette.round(14, .bold)).foregroundStyle(Palette.ink).probe("week-title", text: store.weekTitle)
                Spacer(minLength: 4)
                Button { store.shift(-7) } label: { Image(systemName: "chevron.left").font(.system(size: 13, weight: .semibold)).frame(width: Palette.hit, height: Palette.hit).contentShape(Rectangle()) }
                    .buttonStyle(.plain).foregroundStyle(Palette.ink).accessibilityLabel("前一周").help("前一周").probe("week-prev")
                Button { store.shift(7) } label: { Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).frame(width: Palette.hit, height: Palette.hit).contentShape(Rectangle()) }
                    .buttonStyle(.plain).foregroundStyle(Palette.ink).accessibilityLabel("后一周").help("后一周").probe("week-next")
            }
            HStack(spacing: 3) {
                ForEach(store.weekDays, id: \.day) { d in
                    let on = d.day == store.day, isToday = d.day == store.view?.today
                    let words = (d.today > 0 ? "当天要做\(d.today)项" : "") + ((d.schedule ?? 0) > 0 ? " 有课表或日程" : "")
                    Button { store.change(day: d.day) } label: {
                        VStack(spacing: 1) {
                            Text(isToday ? "今天" : WorkspaceStore.weekday(d.day)).font(.system(size: 11.5, weight: isToday ? .bold : .medium))
                            Text(WorkspaceStore.dayNumber(d.day)).font(Palette.round(17, .bold))
                            HStack(spacing: 3) {
                                if d.today > 0 { Text("\(d.today)项").font(.system(size: 10.5, weight: .semibold)) }
                                if (d.schedule ?? 0) > 0 { Circle().fill(Palette.leaf400).frame(width: 5, height: 5) }
                            }.frame(height: 13)
                        }
                        .frame(maxWidth: .infinity, minHeight: 56).contentShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(on ? Palette.leafInk : Palette.ink)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(on ? Palette.card : Color.clear).shadow(color: on ? Palette.wood300 : Color.clear, radius: 0, x: 0, y: 2))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(isToday && !on ? Palette.leaf400 : Color.clear, lineWidth: 1.5))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(WorkspaceStore.spoken(d.day) + (words.isEmpty ? "" : "，" + words))
                    .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
                    .probe("week-" + d.day, text: d.day + (on ? " 所选" : "") + " " + words)
                }
            }
            .padding(3).background(RoundedRectangle(cornerRadius: 15, style: .continuous).fill(Palette.wood))
        }
    }
}

/// 课表的一天：节次与课程原文，不写钟点。
struct LessonCard: View {
    let table: LessonTable
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(table.title).font(Palette.round(14, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
            FlowRow(spacing: 6, lineSpacing: 6) {
                ForEach(table.sessions, id: \.self) { s in
                    HStack(spacing: 5) {
                        Text(s.slot).font(.system(size: 12, weight: .semibold)).foregroundStyle(Palette.woodInk)
                        Text(s.title).font(Palette.small).foregroundStyle(Palette.ink)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 5).background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(Palette.paper2))
                }
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.line, lineWidth: 1))
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
        .probe("lessons-" + table.id, text: table.sessions.map { $0.slot + " " + $0.title }.joined(separator: " "))
    }
}

/// 一条日程：钟点（没写就说没写）、名称、地点与来源；关联事项不在本孩子当天清单时如实写“未合并”。
/// 家庭复习改期用的日期写法（与服务端 YYYY-MM-DD 一致，不随系统地区变）。
let reviewDayFormat: DateFormatter = {
    let f = DateFormatter(); f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = .current; f.dateFormat = "yyyy-MM-dd"; return f
}()

/// 任务列表里日程行的行键：类型不是 String，ForEach 就不会按编号把这一行默认当成可选中的任务（只有显式 tag 的行可选）。
struct PlanListKey: Hashable { let id: String }
extension PlanItem { var listKey: PlanListKey { PlanListKey(id: id) } }

struct PlanRow: View {
    let plan: PlanItem
    /// A family review opens the same original wrong record and topic through the existing route (store.openTopic).
    var openReview: (PlanReview) -> Void = { _ in }
    /// 家庭复习：工作台按编号保存的卡片草稿（收起、换日/换孩子、列表复用都不丢）与改期/取消/完成（原保存规则）。
    var draft: ReviewDraft? = nil
    var edit: (ReviewDraft, String) async -> Void = { _, _ in }
    var restart: () -> Void = {}
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                Text(planClock(plan.start_time, plan.end_time)).font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(plan.start_time.isEmpty ? Palette.ink2 : Palette.leafInk).frame(width: 92, alignment: .leading)
                VStack(alignment: .leading, spacing: 3) {
                    Text(plan.title).font(Palette.round(15, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                    let meta = [plan.review == nil ? "" : "家庭复习 · 家长安排，不是老师作业", plan.review?.basis_state == "basis_changed" ? "原错题之后更正过，请核对" : "",
                                plan.location, plan.status == "tentative" ? "待确认" : "", plan.repeat ? "重复安排" : "", plan.shared ? "几个孩子共同" : "",
                                plan.source.isEmpty ? "" : "学校来源"].filter { !$0.isEmpty }.joined(separator: " · ")
                    if !meta.isEmpty { Text(meta).font(.system(size: 12.5)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true) }
                    if let text = plan.unmerged { Text(text).font(.system(size: 12.5)).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true) }
                }
                Spacer(minLength: 0)
            }
            // The review editor takes the card's whole width under the title (the list column is 340pt in a 900 window), in rows
            // that each fit that width, so the date, both times and every action stay inside the column.
            if let review = plan.review, let draft {
                ReviewEditor(plan: plan, review: review, draft: draft, save: draft.save, openReview: openReview, edit: edit, restart: restart)
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.line, lineWidth: 1))
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
        .probe("plan-" + plan.id, text: planClock(plan.start_time, plan.end_time) + " " + plan.title)
    }
}

/// 家庭复习卡片里的改期/取消/完成：只改这条复习的日期/时间或状态；孩子、原错题、知识点与原作业固定。保存中或回执不明时，
/// 输入、收起和打开原错题都锁住，只能“用同一次提交重试”原样核对；完成提示只按服务端回执写。
struct ReviewEditor: View {
    let plan: PlanItem
    let review: PlanReview
    @ObservedObject var draft: ReviewDraft
    @ObservedObject var save: SaveState
    var openReview: (PlanReview) -> Void
    var edit: (ReviewDraft, String) async -> Void
    var restart: () -> Void
    var state: String { save.busy ? "busy" : save.unknown ? "unknown" : save.conflict ? "conflict" : draft.dirty ? "dirty" : "idle" }
    /// 回执不明时冻结的那次提交：它的日期与操作（不是卡片里后来改的值）。
    var frozen: String {
        guard let b = save.body else { return "" }
        let action = ["completed": "完成", "cancelled": "取消"][b["status"] as? String ?? ""] ?? "改期"
        return (b["day"] as? String ?? "") + " · " + action
    }
    func act(_ status: String) { Task { await edit(draft, status) } }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            VStack(alignment: .leading, spacing: 4) {
                Button { openReview(review) } label: { Label("打开原错题与知识点", systemImage: "leaf") }
                    .probe("plan-review-open-" + plan.id, text: "打开原错题与知识点")
                Button { draft.editing.toggle() } label: { Label(draft.editing ? "收起" : "改期 / 取消 / 完成", systemImage: "calendar") }
                    .probe("plan-review-edit-" + plan.id, text: draft.editing ? "收起" : "改期 / 取消 / 完成")
            }
            .disabled(draft.locked)
            .buttonStyle(.borderless).font(.system(size: 12.5, weight: .semibold)).foregroundStyle(Palette.leafInk)
            if draft.editing {
                VStack(alignment: .leading, spacing: 6) {
                    Text("原错题、知识点和原作业固定不变；完成只记这条复习，不改老师作业，也不算掌握。")
                        .font(.system(size: 12)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                    VStack(alignment: .leading, spacing: 6) {
                        DatePicker("日期", selection: $draft.day, displayedComponents: .date).labelsHidden()
                            .probe("plan-review-day-" + plan.id, text: reviewDayFormat.string(from: draft.day))
                        HStack(spacing: 8) {
                            TextField("开始，如 19:00", text: $draft.start).frame(minWidth: 70, maxWidth: 130).probe("plan-review-start-" + plan.id, text: draft.start)
                            TextField("结束，如 19:30", text: $draft.end).frame(minWidth: 70, maxWidth: 130).probe("plan-review-end-" + plan.id, text: draft.end)
                        }
                    }
                    .disabled(draft.locked)
                    if save.unknown {
                        Text("上次提交（\(frozen)）还不确定是否已保存；这次提交原样保留，不能改日期或换操作，请先用同一次提交核对。")
                            .font(.system(size: 12.5)).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                            .probe("plan-review-frozen-" + plan.id, text: frozen)
                        Button("用同一次提交重试") { act("") }.disabled(save.busy).probe("plan-review-retry-" + plan.id, text: "用同一次提交重试")
                    } else {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 10) {
                                Button("保存改期") { act(plan.status == "tentative" ? "tentative" : "confirmed") }.probe("plan-review-move-" + plan.id, text: "保存改期")
                                Button("完成这次复习") { act("completed") }.probe("plan-review-complete-" + plan.id, text: "完成这次复习")
                            }
                            Button("取消这次复习") { act("cancelled") }.probe("plan-review-cancel-" + plan.id, text: "取消这次复习")
                        }
                        .disabled(save.busy)
                    }
                    if !save.message.isEmpty {
                        Text(save.message).font(.system(size: 12.5)).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                            .probe("plan-review-message-" + plan.id, text: save.message)
                    }
                    if save.conflict && !draft.locked {
                        Button("按最新的安排重新开始") { restart() }.probe("plan-review-restart-" + plan.id, text: "按最新的安排重新开始")
                    }
                }
                .font(.system(size: 12.5))
            }
        }
        .probe("plan-review-state-" + plan.id, text: state)
    }
}

/// 学习进展：按科目，先孩子表现（每道原错题的知识点、诊断与再试日期、帮助/独立、当前或历史依据、下一步与原作业），
/// 再单列课程记录（原出处，不是孩子表现）。没有记录就说没有，不当 0 掌握。
struct LearningList: View {
    @ObservedObject var store: WorkspaceStore
    var body: some View {
        List(selection: Binding(get: { store.record }, set: { store.record = $0 })) {
            if let l = store.current?.learning {
                if !l.pack.installed {
                    Text("数学知识包未安装或版本不符：原错题、订正和清单照常可用，暂不能做知识点诊断。").font(Palette.small).foregroundStyle(Palette.ink2)
                        .fixedSize(horizontal: false, vertical: true).listRowSeparator(.hidden).probe("learning-pack", text: "知识包未安装")
                }
                ForEach(l.subjects, id: \.subject) { s in
                    Section {
                        ForEach(s.evidence) { e in LearningCard(store: store, entry: e).tag(e.record_id).listRowSeparator(.hidden) }
                        if !s.course.isEmpty { CourseCard(entries: s.course).listRowSeparator(.hidden) }
                    } header: {
                        WoodTag(text: s.subject, count: s.evidence.isEmpty ? "" : "\(s.evidence.count) 道原错题").padding(.top, 8).padding(.bottom, 2)
                            .probe("learning-subject-" + s.subject)
                    }
                }
                if l.subjects.isEmpty {
                    Text("还没有可核对的学习记录。记下错题或课程记录后，这里按科目列出原记录与知识点线索。").font(Palette.body).foregroundStyle(Palette.ink2)
                        .fixedSize(horizontal: false, vertical: true).probe("learning-empty")
                }
            } else if store.current != nil {
                Text("这一版后台还没有提供学习进展；原错题仍在错题本。").font(Palette.body).foregroundStyle(Palette.ink2)
            }
        }
        .listStyle(.sidebar).scrollContentBackground(.hidden).probe("learning-list")
    }
}

struct LearningCard: View {
    @ObservedObject var store: WorkspaceStore
    let entry: LearningEntry
    /// A linked topic is not a diagnosis: it says so and waits for one; a diagnosis keeps its current/history label.
    private func topicLabel(_ t: LearningTopic) -> String { topicWords(t) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(entry.title).font(Palette.round(15, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 6)
                Badge(text: entry.state ?? "待订正", tone: entry.state == "待订正" ? Palette.coral : Palette.leaf100, ink: entry.state == "待订正" ? Palette.coralInk : Palette.leafInk)
            }
            if let topics = entry.topics, !topics.isEmpty {
                FlowRow(spacing: 6, lineSpacing: 4) {
                    ForEach(topics, id: \.self) { t in
                        Badge(text: topicLabel(t), tone: t.basis == "current" && t.state != "linked" ? Palette.leaf100 : Palette.paper2,
                              ink: t.basis == "current" && t.state != "linked" ? Palette.leafInk : Palette.ink2)
                    }
                }
            }
            ForEach(Array((entry.lines ?? []).enumerated()), id: \.offset) { _, line in
                HStack(alignment: .top, spacing: 8) {
                    Text(line.first ?? "").font(.system(size: 12.5, weight: .semibold)).foregroundStyle(Palette.woodInk).frame(width: 78, alignment: .leading)
                    Text(line.count > 1 ? line[1] : "").font(Palette.small).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                }
            }
            if let task = entry.task_title, !task.isEmpty {
                Text("原作业：" + task).font(.system(size: 12.5)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
            }
            if let next = entry.next, !next.isEmpty {
                Text("下一步：" + next).font(Palette.small).foregroundStyle(Palette.leafInk).fixedSize(horizontal: false, vertical: true)
            }
            // 都按这道原错题的编号：看原错题选中错题本里的同一道；回原作业在日历里选中同一份作业。
            FlowRow(spacing: 8, lineSpacing: 6) {
                Button("看原错题") { store.showRecord(entry.record_id) }.buttonStyle(GroveButtonStyle()).probe("learning-wrong-\(entry.record_id)")
                if let task = entry.task_id, !task.isEmpty {
                    Button("回原作业") { store.backToTask(task, day: entry.day) }.buttonStyle(GroveButtonStyle(kind: .quiet)).probe("learning-task-\(entry.record_id)")
                }
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card).shadow(color: Palette.cardShadow, radius: 4, x: 0, y: 2))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.line, lineWidth: 1))
        .padding(.vertical, 4)
        .probe("learning-\(entry.record_id)", text: entry.title + " " + (entry.topics ?? []).map(\.name).joined(separator: " ") + " " + (entry.lines ?? []).map { $0.joined(separator: " ") }.joined(separator: " "))
    }
}

/// 课程记录：老师/学校讲到哪里等原记录，保原出处；只列出，不推断老师身份、不当孩子表现。
struct CourseCard: View {
    let entries: [LearningEntry]
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("课程记录（安排与进度，不是孩子表现）").font(.system(size: 12.5, weight: .semibold)).foregroundStyle(Palette.woodInk)
            ForEach(entries) { c in
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.title).font(Palette.round(14, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                    if !c.note.isEmpty { Text(c.note).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true) }
                    Text(c.day + " · 出处：" + (c.source ?? "未写明")).font(.system(size: 12)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                }.probe("course-\(c.record_id)", text: c.title)
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.paper2))
        .padding(.vertical, 4)
    }
}

// MARK: 所选事项详情：出处（老师与发布时间）与标题 → 完成日/交回日等行动日期卡片 → 要做什么与完成标准 → 资料与打印 → 反馈、错题与订正（同一份作业）。

struct Inspector: View {
    @ObservedObject var store: WorkspaceStore
    /// 窄窗的详情页（盖在隐去的清单上）：顶上是“返回清单”；宽窗右栏是“收起详情”。两者都回到同一清单位置。
    var page = false

    var body: some View {
        Group {
            if let item = store.selected { detail(item) }
            else {
                VStack(spacing: 10) {
                    Image(systemName: "leaf").font(.largeTitle).foregroundStyle(Palette.leafInk)
                    Text(store.current != nil ? "从左边选一项，查看要做什么、资料和反馈。" : store.loginRequired ? "登录后显示清单。"
                         : store.loading || store.error.isEmpty ? "正在读取清单…" : "还没读到所选孩子这一天的清单，可在左边重试。").font(Palette.body).foregroundStyle(Palette.ink2)
                }.frame(maxWidth: .infinity, maxHeight: .infinity).background(Palette.paper)
            }
        }
    }

    func header(_ title: String, _ symbol: String) -> some View {
        Label(title, systemImage: symbol).font(Palette.round(17, .bold)).foregroundStyle(Palette.ink)
    }

    func card<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) { content() }
            .padding(EdgeInsets(top: 14, leading: 18, bottom: 16, trailing: 18)).frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card).shadow(color: Palette.cardShadow, radius: 6, x: 0, y: 3))
    }

    func section<Content: View>(_ title: String, _ symbol: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) { header(title, symbol); card(content) }
    }

    func detail(_ item: DayItem) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 10) {
                    Button { store.closeDetail() } label: { Label(page ? "返回清单" : "收起详情", systemImage: page ? "chevron.left" : "xmark") }
                        .buttonStyle(GroveButtonStyle(kind: .quiet)).keyboardShortcut(.cancelAction)
                        .help(page ? "回到清单原来的位置（Esc）" : "收起详情，清单回到整宽（Esc）").probe("detail-back", text: page ? "返回清单" : "收起详情")
                    FlowRow(spacing: 10, lineSpacing: 6) {
                        WoodTag(text: item.subject)
                        // 发布是老师旁的次要出处（原型 .d-source）：老师与完整发布时间一行小字，不占日期卡；原值照写，未知如实写。
                        if let words = item.publishWords {
                            Label(words, systemImage: "bubble.left").font(Palette.small).foregroundStyle(Palette.ink2).frame(minHeight: 26)
                                .probe("detail-publisher", text: words)
                        }
                        // 有逐条出处时在下面“来源消息”里就地看原文；较早后台没有出处时仍沿网页版原消息。
                        if item.sourceRefs.isEmpty && item.origin == "school" {
                            Button { store.openWebTools(item.webID, "original") } label: { Label("看原消息", systemImage: "text.bubble") }
                                .buttonStyle(GroveButtonStyle(kind: .quiet)).help("在网页版打开同一项的原消息与原件").probe("original-message")
                        }
                        Text("\(store.childName) · \(item.origin_label)" + (item.origin == "oral" ? "（老师日期未录入就保持未知）" : "")).font(Palette.small).foregroundStyle(Palette.ink2).frame(minHeight: 26)
                    }
                    Text(item.title).font(Palette.round(26, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled).probe("detail-title", text: item.title)
                    if !item.whenLabel.isEmpty {
                        Text("这一项\(item.whenLabel)，不算这一天要交的作业。").font(Palette.body).foregroundStyle(Palette.ink2).probe("detail-when", text: item.whenLabel)
                    }
                }
                if !item.actionFacts.isEmpty { facts(item) }
                section("要做什么与完成标准", "checklist") {
                    if item.lines.isEmpty { Text("完成标准未提供，待补充").font(Palette.body).foregroundStyle(Palette.coralInk).probe("detail-no-standard") }
                    // 冒烟锚点：当前正文逐行、完成要求和待核对提示各给它自己显示的同一句话（不含历史或隐藏的正文）。
                    ForEach(Array(item.lines.enumerated()), id: \.offset) { index, line in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Image(systemName: "leaf.fill").font(.system(size: 11)).foregroundStyle(Palette.leaf400).accessibilityHidden(true)
                            Text(line).font(Palette.body).foregroundStyle(Palette.ink).lineSpacing(3).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                                .probe("detail-line-\(item.id)-\(index)", text: line)
                        }
                    }
                    if !item.complete_words.isEmpty {
                        let complete = "完成要求：" + item.complete_words
                        Text(complete).font(Palette.body).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("detail-complete-" + item.id, text: complete)
                    }
                    if item.pending_review {
                        let hint = "这条学校消息还在待核对，确认后才算正式事项；可在网页版学校信息中核对。"
                        Text(hint).font(Palette.small).foregroundStyle(Palette.coralInk).probe("detail-pending-" + item.id, text: hint)
                    }
                }
                if !item.sourceRefs.isEmpty { sources(item) }
                if !item.task_id.isEmpty { materials(item) }
                feedback(item)
            }
            .padding(.horizontal, 32).padding(.top, 24).padding(.bottom, 40)
            .frame(maxWidth: 860, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Palette.paper)
        .probe("inspector")
    }

    /// 主要日期卡只放完成、交回等真实行动日期（发布时间在标题上方的出处小字里）：每条写出原值；未知如实写，不猜；明天交、已逾期用珊瑚色。
    func facts(_ item: DayItem) -> some View {
        // 原型 .d-facts：最多三张等宽并排，多出来的换到下一行；每条行动事实都保留，不凑卡。
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10, alignment: .topLeading), count: max(1, min(item.actionFacts.count, 3))), alignment: .leading, spacing: 10) {
            ForEach(item.actionFacts, id: \.self) { f in factCard(f) }
        }
    }

    func factIcon(_ role: String) -> String { ["complete": "clock", "due": "tray.and.arrow.up", "published": "bubble.left", "publish": "bubble.left"][role] ?? "calendar" }

    func factCard(_ f: DayFact) -> some View {
        let urgent = f.state == "next_morning" || f.state == "overdue"
        return VStack(alignment: .leading, spacing: 4) {
            Label(f.label, systemImage: factIcon(f.role)).font(.system(size: 12.5)).foregroundStyle(Palette.ink2)
            Text((f.today == true ? "今天 " : "") + (f.known ? f.value : "时间未明确")).font(Palette.round(15, .bold))
                .foregroundStyle(!f.known ? Palette.ink2 : urgent ? Palette.coralInk : Palette.ink).italic(!f.known)
                .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
            if f.state == "next_morning" { Badge(text: "明天", tone: Palette.coral, ink: Palette.coralInk) }
            if f.state == "overdue" { Badge(text: "已逾期", tone: Palette.coral, ink: Palette.coralInk) }
        }
        .padding(EdgeInsets(top: 12, leading: 14, bottom: 12, trailing: 14)).frame(maxWidth: .infinity, minHeight: 74, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card).shadow(color: Palette.cardShadow, radius: 6, x: 0, y: 3))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(urgent ? Palette.coral400 : Color.clear, lineWidth: 1))
        .accessibilityElement(children: .combine).probe("fact-" + f.role, text: factWords(f))
    }

    func materialTone(_ m: Material) -> (Color, Color) {
        switch m.state {
        case "ready": return (Palette.leaf100, Palette.leaf700)
        case "unread", "error": return (Palette.coral, Palette.coralInk)
        case "pending": return (Palette.paper2, Palette.ink2)
        default: return (Palette.wood, Palette.woodInk)
        }
    }

    /// 资料卡（原型 .mat）：用途和状态分开写——用途牌、文件名、服务端给的状态；有提要就写提要，看不清的只说原因，不猜内容。
    func materialCard(_ m: Material) -> some View {
        let unread = m.state == "unread" || m.state == "error"
        let (tone, ink) = materialTone(m)
        let parent = m.roleLabel.contains("家长")
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                Text(m.roleLabel).font(Palette.round(14, .bold)).foregroundStyle(parent ? Palette.woodInk : Palette.ink)
                    .padding(.horizontal, 10).padding(.vertical, 2)
                    .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(parent ? Palette.wood : Palette.paper2)).fixedSize()
                Text(m.name).font(.system(size: 15, weight: .semibold)).foregroundStyle(Palette.ink).lineLimit(1).truncationMode(.middle).help(m.name)
                Spacer(minLength: 8)
                Badge(text: m.stateLabel, tone: tone, ink: ink, dashed: unread)
            }
            if !m.summary.isEmpty {
                Text(m.summary).font(.system(size: 14)).foregroundStyle(Palette.ink).lineSpacing(2).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
            }
            if !m.scope.isEmpty { Text(m.scope).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("material-scope-" + m.id, text: m.scope) }
            if !m.unclear.isEmpty { Text("看不清：" + m.unclear.joined(separator: "；") + "。请看原件。").font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true) }
            if !m.missing.isEmpty {
                Text("要求已读到，执行还缺：" + m.missing.joined(separator: "；") + "。").font(Palette.small).foregroundStyle(Palette.woodInk).fixedSize(horizontal: false, vertical: true)
                    .probe("material-missing-" + m.id, text: m.missing.joined(separator: "；"))
            }
            if m.state != "ready", m.state != "saved", !m.explanation.isEmpty {
                Text(m.explanation).font(Palette.small).foregroundStyle(m.state == "pending" ? Palette.ink2 : Palette.coralInk).fixedSize(horizontal: false, vertical: true)
            }
            Button { store.openDocument(store.client.url("/upload/" + m.id), m.name) } label: { Label("打开原件", systemImage: "eye") }
                .buttonStyle(GroveButtonStyle()).probe("material-open-" + m.id)
        }
        .padding(EdgeInsets(top: 14, leading: 16, bottom: 16, trailing: 16)).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(unread ? Palette.paper : Palette.card).shadow(color: unread ? Color.clear : Palette.cardShadow, radius: 6, x: 0, y: 3))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(unread ? Palette.line2 : Color.clear, style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).inset(by: 5).strokeBorder(m.state == "ready" ? Palette.leaf100 : Color.clear, style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])).allowsHitTesting(false))
        .probe("material-" + m.id, text: [m.stateLabel, m.name, m.scope, m.summary].filter { !$0.isEmpty }.joined(separator: " "))
    }

    /// 来源消息：每条唯一原消息一行（来源与发布人），在这一项里直接读原文与这条消息自己的附件，关闭后回到同一项。
    func sources(_ item: DayItem) -> some View {
        section("来源消息\(item.sourceRefs.count)条", "text.bubble") {
            ForEach(item.sourceRefs, id: \.ref) { p in
                HStack(alignment: .center, spacing: 10) {
                    Text([p.source_name, p.sender].filter { !$0.isEmpty }.joined(separator: " · ")).font(Palette.body).foregroundStyle(Palette.ink)
                        .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                    Button { store.sheetDirty = false; store.sheet = .source(item, p, store.childID) } label: { Label("看原消息", systemImage: "text.bubble") }
                        .buttonStyle(GroveButtonStyle(kind: .quiet)).help("在这一项里看原文、发布人、时刻与附件").probe("source-open-" + p.ref, text: p.ref)
                }
            }
        }.probe("detail-sources", text: "来源消息\(item.sourceRefs.count)条")
    }

    func materials(_ item: DayItem) -> some View {
        let state = store.materials[item.task_id] ?? MaterialState()
        return VStack(alignment: .leading, spacing: 10) {
            header(item.category == "homework" ? "资料与打印" : "资料", "doc.text")
            if !state.loaded { Text("正在读取资料…").font(Palette.body).foregroundStyle(Palette.ink2) }
            if !state.error.isEmpty {
                card {
                    Text(state.error).font(Palette.body).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                    Button("重新读取资料") { Task { await store.loadMaterials(item) } }.buttonStyle(GroveButtonStyle()).probe("material-retry")
                }
            }
            if state.loaded && state.files.isEmpty && state.error.isEmpty { Text("这一项没有已保存的原件。").font(Palette.body).foregroundStyle(Palette.ink2).probe("material-none") }
            ForEach(state.files) { m in materialCard(m) }
            if !state.gap.isEmpty {
                Text("尚未读清：" + state.gap).font(Palette.body).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                    .padding(EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16)).frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.paper))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.coral400, style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])))
                    .probe("material-gap")
            }
            // 有已保存的原件才放打印；没有已关联的参考如实写“尚无已关联参考”，不猜老师没发。
            if item.category == "homework" && state.loaded && !state.files.isEmpty {
                if !state.files.contains(where: { $0.roleLabel.contains("参考") }) {
                    Text("尚无已关联参考。").font(Palette.small).foregroundStyle(Palette.ink2).probe("reference-none")
                }
                FlowRow(spacing: 10, lineSpacing: 8) {
                    Button { store.openWebTools(item.task_id, "print-original") } label: { Label("打印原卷", systemImage: "printer") }
                        .buttonStyle(GroveButtonStyle(kind: .primary)).probe("print-original")
                    Button { store.openWebTools(item.task_id, "print-reference") } label: { Label("打印家长参考", systemImage: "printer") }
                        .buttonStyle(GroveButtonStyle()).probe("print-reference")
                }
                .padding(.top, 2)
                Text("在网页版这份作业的打印确认里打开：先核对依据和所选资料，确认后才排队打印。").font(Palette.small).foregroundStyle(Palette.ink2)
            }
        }
    }

    func feedback(_ item: DayItem) -> some View {
        section("反馈、错题与订正", "pencil") {
            if let note = item.same_affair?.note, !note.isEmpty { Text(note).font(Palette.body).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("same-affair-note") }
            if item.task_id.isEmpty { Text("这一项还不是正式事项，确认后才能记反馈。").font(Palette.body).foregroundStyle(Palette.ink2) }
            if let p = item.progress, !progressWords(p).isEmpty {
                FlowRow(spacing: 10, lineSpacing: 6) {
                    Text("已有进展：" + progressWords(p)).font(Palette.round(15, .bold)).foregroundStyle(Palette.ink).frame(minHeight: Palette.hit)
                        .probe("detail-progress", text: progressWords(p))
                    if p.wrong + p.clues + p.retries + p.history > 0 {
                        Button("看错题诊断与再试") { store.openWebTools(item.task_id, "history") }.buttonStyle(GroveButtonStyle(kind: .quiet)).probe("history-web")
                    }
                }
            }
            if !item.task_id.isEmpty {
                FlowRow(spacing: 10, lineSpacing: 8) {
                    Button { store.sheet = .feedback(item); store.sheetDirty = false } label: { Label("写文字反馈", systemImage: "square.and.pencil") }
                        .buttonStyle(GroveButtonStyle(kind: .primary)).probe("feedback-new")
                    if item.category == "homework" {
                        Button { store.openWebTools(item.task_id, "check") } label: { Label("交作答照片检查", systemImage: "camera") }
                            .buttonStyle(GroveButtonStyle()).probe("check-web")
                        Button { store.sheet = .taskWrong(item); store.sheetDirty = false } label: { Label("直接记错题", systemImage: "exclamationmark.bubble") }
                            .buttonStyle(GroveButtonStyle()).probe("wrong-task-new")
                    }
                }
                Text("文字反馈在这里写，照片可加可不加，不调用 AI，不自动标已办或判错；照片检查在网页版同一份作业里进行。").font(Palette.small).foregroundStyle(Palette.ink2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(item.records) { r in
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        Badge(text: r.followup_kind.isEmpty ? "反馈" : r.followup_kind)
                        Text(r.created.prefix(16).replacingOccurrences(of: "T", with: " ")).font(Palette.small).foregroundStyle(Palette.ink2)
                        if !r.attachments.isEmpty { Label("\(r.attachments.count)", systemImage: "camera").font(Palette.small).foregroundStyle(Palette.ink2) }
                        Spacer(minLength: 8)
                        Button("记一道错题") { store.sheet = .wrong(item, r); store.sheetDirty = false }.buttonStyle(GroveButtonStyle(kind: .quiet)).probe("wrong-new-\(r.id)")
                    }
                    if let v = r.retry { RetryLines(v: v, note: r.note).probe("retry-\(r.id)", text: v.lines.map { $0.joined(separator: "：") }.joined(separator: "\n") + "\n下一步 " + v.next) }
                    else { Text(r.note.isEmpty ? r.title : r.note).font(Palette.body).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true).textSelection(.enabled) }
                    if r.note_truncated && (r.retry?.show_note ?? true) { Text("（较长，完整内容在网页版记录中）").font(Palette.small).foregroundStyle(Palette.ink2) }
                    if let line = r.evidenceLine { Text(line).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("record-evidence-\(r.id)", text: line) }
                }
                .padding(EdgeInsets(top: 6, leading: 12, bottom: 12, trailing: 6)).frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Palette.paper))
                .probe("record-\(r.id)", text: r.note)
            }
            ForEach(item.wrong) { w in
                HStack(spacing: 10) {
                    Text(w.title).font(Palette.body).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Badge(text: w.state ?? "待订正", tone: w.state == "待订正" ? Palette.coral : Palette.leaf100, ink: w.state == "待订正" ? Palette.coralInk : Palette.leafInk)
                    Button("在错题本看") { store.showRecord(w.id) }.buttonStyle(GroveButtonStyle(kind: .quiet)).probe("detail-wrong-open-\(w.id)")
                    Button("记订正") { store.sheet = .correction(w); store.sheetDirty = false }.buttonStyle(GroveButtonStyle()).probe("wrong-correct-\(w.id)")
                }
                .padding(EdgeInsets(top: 6, leading: 12, bottom: 9, trailing: 8))
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(w.state == "待订正" ? Palette.paper : Palette.leaf50))
                .accessibilityElement(children: .contain).probe("detail-wrong-\(w.id)", text: w.title + " " + (w.state ?? ""))
            }
        }
    }
}

// MARK: 弹出层：每个写入一个稳定提交标识；保存中锁住，失败/结果未知保留输入并用同一标识重试，冲突时读取最新而不盲目重发。

struct SheetHost: View {
    @ObservedObject var store: WorkspaceStore
    let kind: SheetKind
    var body: some View {
        switch kind {
        case .feedback(let item): FeedbackSheet(store: store, item: item)
        case .oral: OralSheet(store: store)
        case .wrong(let item, let record): WrongSheet(store: store, item: item, record: record)
        case .correction(let record): CorrectionSheet(store: store, record: record)
        case .addWrong: WrongAddSheet(store: store)
        case .taskWrong(let item): WrongAddSheet(store: store, item: item)
        case .source(let item, let p, let child): SourceSheet(store: store, item: item, publication: p, child: child)
        }
    }
}

/// 一条来源消息的原文（只读）。先带这条出处自己的事项编号读：服务端核对同一孩子、同一事项、这条原消息属于它，只给本事项选用的原件
/// （本事项已采用）。核对通过后再按同一孩子、来源、消息读这条原消息自己的全部已保存原件，按编号分出“原消息其它附件（未纳入本项检查）”，
/// 不按文件名猜。核对失败（含 403）只给提示与重试，不改用不带事项的读取；全部附件读不到时保留已读内容、说明并可重试，不说没有附件。
/// 只读：不写业务、不调用模型，看过不等于采用或读懂。读回时孩子、事项或出处已不是点开时的那个，就丢弃不显示。
/// 验收锚点：source-item（孩子 事项 出处）、source-attachments（scoped/adopted/other/raw）、source-file-<编号>、source-other-file-<编号>、
/// source-error/source-retry、source-other-error/source-other-retry、source-no-file。
struct SourceSheet: View {
    @ObservedObject var store: WorkspaceStore
    let item: DayItem
    let publication: Publication
    /// 点开时的孩子编号。
    let child: String
    @State private var message: SourceMessage?
    @State private var error = ""
    @State private var others: [SourceFile]?
    @State private var otherUnavailable = 0
    @State private var otherError = ""
    @State private var reads = 0

    /// 同组出处按它自己的原事项编号核对归属（较早后台没有时用这一项的编号）。
    var task: String { publication.task_id ?? item.task_id }
    var stillHere: Bool {
        guard store.childID == child, case .source(let i, let p, let c)? = store.sheet else { return false }
        return i.id == item.id && p.ref == publication.ref && c == child
    }
    var rawState: String { !otherError.isEmpty ? "error" : others == nil ? "loading" : "ok" }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center) {
                Text("原消息").font(Palette.round(19, .bold)).foregroundStyle(Palette.ink)
                Spacer()
                Button { store.sheet = nil } label: { Label("返回事项", systemImage: "chevron.left") }
                    .buttonStyle(GroveButtonStyle()).keyboardShortcut(.cancelAction).probe("source-back")
            }
            Text(store.childName + " · " + item.title).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                .probe("source-item", text: child + " " + item.id + " " + publication.ref)
            if let m = message {
                let meta = [m.sender, m.time, m.sourceName].filter { !$0.isEmpty }.joined(separator: " · ")
                Text(meta.isEmpty ? "发布人与时刻未记录" : meta).font(Palette.round(14)).foregroundStyle(Palette.ink).probe("source-meta", text: meta)
                ScrollView {
                    Text(m.text).font(Palette.body).foregroundStyle(Palette.ink).lineSpacing(3).textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading).probe("source-text", text: m.text)
                }.frame(maxHeight: 220)
                VStack(alignment: .leading, spacing: 8) {
                    if m.scoped || !m.files.isEmpty {
                        let head = m.scoped ? "本事项已采用" : "原消息附件"
                        Text(m.files.isEmpty ? head + "：无" : head).font(Palette.round(14, .bold)).foregroundStyle(Palette.ink)
                        ForEach(m.files) { f in fileRow(f, "source-file-") }
                    }
                    if let o = others, !o.isEmpty {
                        Text("原消息其它附件（未纳入本项检查）").font(Palette.round(14, .bold)).foregroundStyle(Palette.woodInk)
                        ForEach(o) { f in fileRow(f, "source-other-file-") }
                    }
                    if !otherError.isEmpty {
                        Text("这条消息的全部附件暂时读不到：" + otherError).font(Palette.small).foregroundStyle(Palette.coralInk)
                            .fixedSize(horizontal: false, vertical: true).probe("source-other-error", text: otherError)
                        Button("重新读取附件") { Task { await readOthers() } }.buttonStyle(GroveButtonStyle()).probe("source-other-retry")
                    } else if others == nil {
                        Text("正在读取这条消息的全部附件…").font(Palette.small).foregroundStyle(Palette.ink2)
                    } else if m.files.isEmpty && (others ?? []).isEmpty {
                        let n = m.unavailable + otherUnavailable
                        let words = n > 0 ? "这条消息有 \(n) 个附件暂时打不开。" : "未有已保存附件。"
                        Text(words).font(Palette.small).foregroundStyle(Palette.ink2).probe("source-no-file", text: words)
                    }
                }
                .probe("source-attachments", text: "scoped=\(m.scoped) adopted=\(m.files.count) other=\(others.map { String($0.count) } ?? "-") raw=\(rawState)")
            } else if error.isEmpty {
                Text("正在读取原消息…").font(Palette.body).foregroundStyle(Palette.ink2)
            }
            if !error.isEmpty {
                Text(error).font(Palette.body).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true).probe("source-error", text: error)
                Button("重新读取") { Task { await read() } }.buttonStyle(GroveButtonStyle()).probe("source-retry")
            }
        }
        .padding(24).frame(width: 560, alignment: .topLeading).frame(minHeight: 300, alignment: .topLeading)
        .background(Palette.paper)
        .task { await read() }
    }

    func fileRow(_ f: SourceFile, _ anchor: String) -> some View {
        HStack(spacing: 10) {
            Text(f.name).font(.system(size: 14, weight: .semibold)).foregroundStyle(Palette.ink).lineLimit(1).truncationMode(.middle).help(f.name)
            Spacer(minLength: 8)
            Button { store.openDocument(store.client.url("/upload/" + f.id), f.name) } label: { Label("打开原件", systemImage: "eye") }
                .buttonStyle(GroveButtonStyle()).probe(anchor + f.id, text: f.name)
        }
    }

    /// 先核归属：失败只给提示与重试（不改用不带事项的读取）；通过后再读这条消息的全部附件。没有事项编号时第一次读的就是整条消息。
    func read() async {
        reads += 1; let mine = reads
        error = ""
        do {
            let m = try await store.client.message(child: child, ref: publication.ref, task: task)
            guard mine == reads, stillHere else { return }
            message = m
        } catch {
            guard mine == reads, stillHere else { return }
            self.error = (error as? WorkspaceError)?.text ?? "暂时读不到原消息，原记录不受影响；请重试。"
            return
        }
        if task.isEmpty { others = []; return }
        await readOthers()
    }

    /// 归属核对通过后才读：同一孩子、来源、消息的全部已保存原件，去掉上面已列的（按编号）。读不到时已显示的内容都留着。
    func readOthers() async {
        guard let shown = message, !task.isEmpty else { return }
        reads += 1; let mine = reads
        otherError = ""
        do {
            let raw = try await store.client.message(child: child, ref: publication.ref, task: "")
            guard mine == reads, stillHere else { return }
            let ids = Set(shown.files.map(\.id))
            others = raw.files.filter { !ids.contains($0.id) }
            otherUnavailable = max(0, raw.unavailable - shown.unavailable)
        } catch {
            guard mine == reads, stillHere else { return }
            otherError = (error as? WorkspaceError)?.text ?? "请重试。"
        }
    }
}

@MainActor
final class SaveState: ObservableObject {
    @Published var busy = false
    @Published var message = ""
    @Published var conflict = false
    @Published var unknown = false
    @Published var login = false      // 这次被服务端以“需要登录”拒绝：弹出层里直接给登录入口
    let key = requestKey()
    /// 家庭复习改期/取消/完成这次已发出的请求体：回执不明时原样重发同一请求（同编号同版本，服务端只存一份）。
    var body: [String: Any]?
}

/// 一条家庭复习在卡片里的改期草稿（工作台按安排编号保存）：日期/时间与这次提交状态；save.body 是回执不明时冻结的原请求。
@MainActor
final class ReviewDraft: ObservableObject {
    @Published var editing = false
    @Published var day: Date
    @Published var start: String
    @Published var end: String
    let save = SaveState()
    /// 打开卡片时显示的那一版（日期/时间/状态与版本）：保存只按它写，读回已是别人改过的新版就算冲突，不借用新版本。
    let origin: (day: String, start: String, end: String, status: String)
    let version: Int?
    init(day: String, start: String, end: String, status: String = "confirmed", version: Int? = nil) {
        self.day = reviewDayFormat.date(from: day) ?? Date(); self.start = start; self.end = end; origin = (day, start, end, status); self.version = version
    }
    /// 和已存的这条复习不同（还没保存的改动）。
    var dirty: Bool { reviewDayFormat.string(from: day) != origin.day || start != origin.start || end != origin.end }
    /// 保存中或回执不明：输入、收起和离开都锁住，只能用同一次提交核对。
    var locked: Bool { save.busy || save.unknown }
}

struct SheetFrame<Fields: View>: View {
    @ObservedObject var store: WorkspaceStore
    @ObservedObject var save: SaveState
    let title: String
    let context: String
    let dirty: Bool
    let canSave: Bool
    let saveTitle: String
    let onSave: () -> Void
    @ViewBuilder let fields: () -> Fields
    /// 弹出层挡住了后面清单里的登录按钮，所以需要登录时入口就在这里；登录完成后提示用同一次提交重试（不自动重发）。
    var relogin: Bool { save.login && store.loginRequired }
    var message: String { save.login && !store.loginRequired ? "已重新登录。输入已保留；点“用同一次提交重试”保存。" : save.message }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title).font(.system(.title3, design: .rounded).weight(.bold)).foregroundStyle(Palette.ink)
            Text(context).font(.callout).foregroundStyle(Palette.ink2)
            Form { fields() }.formStyle(.grouped).disabled(save.busy)
            if !message.isEmpty {
                Text(message).foregroundStyle(save.unknown || save.conflict || relogin ? Palette.coralInk : Palette.ink).probe("sheet-status", text: message)
            }
            HStack {
                if save.conflict { Button("读取最新") { Task { await store.load() } }.probe("sheet-reload") }
                // 登录在单独的登录窗口里进行：这个填写框、它的输入、已选附件和提交标识都不动。
                if relogin {
                    Button("登录家庭账号") { store.openLogin() }.buttonStyle(.borderedProminent).tint(Palette.leaf).foregroundStyle(Palette.leafInk).probe("sheet-login")
                }
                Spacer()
                Button("取消") { close() }.keyboardShortcut(.cancelAction).disabled(save.busy).probe("sheet-cancel")
                Button(save.busy ? "正在保存…" : save.unknown || !save.message.isEmpty && !save.conflict ? "用同一次提交重试" : saveTitle) { onSave() }
                    .keyboardShortcut(.defaultAction).disabled(save.busy || !canSave || store.current == nil).probe("sheet-save")
            }
        }
        .padding(20).frame(minWidth: 460, idealWidth: 520).background(Palette.paper)
        // 系统默认按 Esc 直接关掉弹出层；改为同一关闭确认：有未保存内容时默认继续编辑。
        .interactiveDismissDisabled(true)
        .onExitCommand { if !save.busy { close() } }
        .onChange(of: dirty) { store.sheetDirty = $0 }
        .onAppear { store.sheetDirty = dirty }
    }

    func close() {
        if dirty && !store.confirmDiscard("关闭这次填写") { return }
        store.sheetDirty = false; store.sheet = nil
    }
}

extension WorkspaceStore {
    /// 一次写入的统一结果处理：成功后重读同一天并保持同一项选中（保存后重开）。
    /// 家庭复习改期/取消/完成：按原读取口径读回这天同一编号的已存安排（全部原字段与版本），只换日期/时间/状态，走原
    /// /api/calendar/save（同编号同版本核对；不带 review，服务端保持原错题/知识点/原作业关联不变）。回执不明时原样重发同一请求。
    /// 一个新请求才用卡片里的日期/时间与所选状态；回执不明时 save.body 冻结，只原样重发它（卡片此时不给别的操作）。
    func saveReview(_ id: String, from: String, draft: ReviewDraft, status: String) async {
        let save = draft.save
        guard !save.busy else { return }
        save.busy = true; save.message = ""; save.conflict = false
        if save.body == nil {
            do {
                // 只读卡片依据的那一天（没有依据日才读正看的这一天），开始结束同一天：自己确认过的保存可能已把它改到很远的日子而重读失败时页面仍停在旧的一天，连同中间整段一起读会超出每次最多31天的查询；别处改到别的日子在这里就读不到、不改任何记录，同一天里改过仍按下面的核对算冲突。
                let o = draft.origin
                let lookupDay = o.day.isEmpty ? from : o.day
                let data = try await client.get("/api/calendar", ["start": lookupDay, "end": lookupDay])
                let events = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["events"] as? [[String: Any]] ?? []
                guard let e = events.first(where: { $0["id"] as? String == id && $0["editable"] as? Bool == true && $0["review"] != nil }) else {
                    save.busy = false; save.message = "这条家庭复习在 \(from) 读不到（可能已改期或删除）；没有改动任何记录，请刷新后核对。"; return
                }
                guard WorkspaceStore.reviewSnapshotMatches(day: o.day, start: o.start, end: o.end, status: o.status, version: draft.version, e) else {
                    save.busy = false; save.conflict = true
                    save.message = "这条复习已在别处改过（现在是 \(e["day"] as? String ?? "") \(e["start_time"] as? String ?? "")），这里的改动没有保存、仍保留；请核对后按最新的重新开始。"
                    return
                }
                var body: [String: Any] = [:]
                for k in ["id", "version", "child_ids", "title", "category", "location", "note", "repeat", "until", "repeat_days", "extra_times"] { body[k] = e[k] }
                if let shown = draft.version { body["version"] = shown }  // the version the card showed, never a newer one read just now
                body["day"] = reviewDayFormat.string(from: draft.day); body["status"] = status
                body["start_time"] = draft.start.trimmingCharacters(in: .whitespaces); body["end_time"] = draft.end.trimmingCharacters(in: .whitespaces)
                save.body = body
            } catch {
                save.busy = false; save.message = (error as? WorkspaceError)?.text ?? "日历暂时读不到；没有改动任何记录，请重试。"; return
            }
        }
        let body = save.body ?? [:]
        var outcome = await client.post("/api/calendar/save", body)
        var done = ""
        if case .saved(let object) = outcome {
            // 核对过的自己回执在重读之前就成为这条复习的新依据：重读中或重读失败时，旧页面里的旧一版也刷不回去。
            if let text = adoptReviewACK(id, body, object) { done = text }
            else { outcome = .unknown("服务端的保存回执对不上这次提交（编号、版本、日期、时间或状态），不确定是否已按它保存；这次提交原样保留，请用同一次提交核对。") }
        }
        if case .unknown = outcome {} else { save.body = nil }
        await finish(outcome, save, done: done)
        if case .refused(let status, _, _) = outcome, status == 409 { save.conflict = true }  // newer saved version: draft kept, explicit restart
    }

    /// 读回的这条复习是否还是卡片显示的那一版：有版本就比版本，并且日期/时间/状态都一致；不一致就是别处改过（冲突，不借用新版本）。
    nonisolated static func reviewSnapshotMatches(day: String, start: String, end: String, status: String, version: Int?, _ e: [String: Any]) -> Bool {
        if let version, (e["version"] as? NSNumber)?.intValue != version { return false }
        return e["day"] as? String == day && e["start_time"] as? String == start && e["end_time"] as? String == end && e["status"] as? String == status
    }

    /// 这条复习的卡片草稿：第一次取已存的日期/时间；之后收起、换日或换孩子再回来仍是同一份（含回执不明的原请求与提示）。
    /// 版本更低或相同的读取结果（如重读失败后旧页面里的这条安排）不换掉它；真正更新的版本只重建没有改动、没在编辑、没在保存或回执不明的卡片，
    /// 否则保留原依据与输入，保存时按冲突处理。
    func reviewDraft(_ plan: PlanItem, day: String) -> ReviewDraft {
        if let d = reviewDrafts[plan.id] {
            guard let newer = plan.version as Int?, let basis = d.version, newer > basis, !d.editing, !d.dirty, !d.locked else { return d }
        }
        let d = ReviewDraft(day: day, start: plan.start_time, end: plan.end_time, status: plan.status, version: plan.version); reviewDrafts[plan.id] = d; return d
    }

    /// 自己这次保存的回执：只有 reviewSaved 核对过（同编号、版本恰好+1、日期/时间/状态与这次提交一致、仍带原关联）才成为这条复习新的卡片依据
    /// （回执里的日期/时间/状态与版本，收起、没有未保存改动）；对不上就不动原卡片与这次提交，返回 nil（按回执不明处理）。
    func adoptReviewACK(_ id: String, _ body: [String: Any], _ object: [String: Any]) -> String? {
        guard let text = WorkspaceStore.reviewSaved(body, object), let e = object["event"] as? [String: Any] else { return nil }
        reviewDrafts[id] = ReviewDraft(day: e["day"] as? String ?? "", start: e["start_time"] as? String ?? "", end: e["end_time"] as? String ?? "",
                                       status: e["status"] as? String ?? "", version: (e["version"] as? NSNumber)?.intValue)
        return text
    }

    /// 家庭复习保存回执：只认同一编号、版本恰好+1、日期/时间/状态与这次提交一致且仍带原关联的回执，并按回执写提示；否则 nil（按回执不明处理）。
    nonisolated static func reviewSaved(_ body: [String: Any], _ object: [String: Any]) -> String? {
        guard let e = object["event"] as? [String: Any], let id = e["id"] as? String, id == body["id"] as? String,
              let version = (e["version"] as? NSNumber)?.intValue, let sent = (body["version"] as? NSNumber)?.intValue, version == sent + 1,
              let day = e["day"] as? String, day == body["day"] as? String, let status = e["status"] as? String, status == body["status"] as? String,
              e["start_time"] as? String == body["start_time"] as? String, e["end_time"] as? String == body["end_time"] as? String,
              e["review"] is [String: Any] else { return nil }
        return status == "completed" ? "\(day) 的这次家庭复习已记为完成；只记这条复习，不改老师作业，也不算掌握。"
            : status == "cancelled" ? "\(day) 的这次家庭复习已取消；原错题和老师作业不变。" : "家庭复习已改到 \(day)。"
    }

    func finish(_ outcome: PostOutcome, _ save: SaveState, done: String) async {
        save.busy = false
        switch outcome {
        case .saved(let object):
            save.login = false
            sheetDirty = false; sheet = nil; notice = done
            // 记下的错题：错题本选中回执里的同一条记录编号（不按标题或第一条猜）；回执没有编号时不改选中。
            if let id = ((object["saved"] as? [[String: Any]])?.first?["id"] as? NSNumber)?.intValue { record = id }
            await load()
        case .unknown(let text):
            save.unknown = true; save.login = false; save.message = text
        case .refused(let status, let text, let code):
            save.unknown = false
            save.login = code == "login_required"
            if save.login { loginRequired = true }
            // 照片上传标识冲突（同一次选取的文件变了）不是别处更新：不提示读取最新，再保存时按现在的文件另传一份。
            let stale = status == 409 && code != "upload_key_conflict"
            save.conflict = stale
            save.message = stale ? text + " 输入已保留；请先“读取最新”核对，再决定是否保存。"
                : code == "upload_key_conflict" ? text + " 输入已保留；再按保存会按现在的文件另传一份。"
                : code == "csrf_expired" ? "连接已更新，输入已保留；请再点一次保存。" : text
        }
    }
}

struct FeedbackSheet: View {
    @ObservedObject var store: WorkspaceStore
    let item: DayItem
    @StateObject var save = SaveState()
    @State var note = ""
    @State var photos: [URL] = []
    @State var uploaded: [String: String] = [:]
    @State var uploadKeys: [String: String] = [:]
    @State var picking = false

    var body: some View {
        SheetFrame(store: store, save: save, title: "写文字反馈", context: "\(store.childName) · \(item.subject) · \(item.title)",
                   dirty: !note.isEmpty || !photos.isEmpty, canSave: !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !photos.isEmpty,
                   saveTitle: "保存反馈", onSave: submit) {
            Section {
                LabeledContent("反馈内容") {
                    TextEditor(text: $note).multilineTextAlignment(.leading).frame(minHeight: 120).probe("feedback-note", text: note).accessibilityLabel("反馈内容")
                }
            }
            Section("照片（可不加）") {
                if photos.isEmpty { Text("还没有选；只写文字也能保存。").font(.caption).foregroundStyle(Palette.ink2).probe("feedback-files-empty", text: "还没有选") }
                ForEach(Array(photos.enumerated()), id: \.element) { index, url in
                    HStack {
                        Text(url.lastPathComponent).lineLimit(1).truncationMode(.middle).probe("feedback-file-\(index)", text: url.lastPathComponent)
                        Spacer()
                        // 只从这次填写里去掉：已上传的原件不删不改，保存时只带留下的附件；再选同一文件沿用已上传的那份。
                        Button("移除") { photos.removeAll { $0 == url } }.buttonStyle(.borderless).controlSize(.small)
                            .help("只从这次反馈里去掉，不删除原件").accessibilityLabel("移除 \(url.lastPathComponent)").probe("feedback-file-remove-\(index)", text: url.lastPathComponent)
                    }
                }
                Button(photos.isEmpty ? "选择照片或 PDF…" : "再加照片或 PDF…") { pick() }.probe("feedback-photo")
            }
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.image, .pdf], allowsMultipleSelection: true) { picked($0) }
    }

    /// 只在 --smoke-test 的原生验收里：系统选择框无法自动操作，取测试声明的文件（或取消）交给同一个选取结果处理。
    func pick() {
        if TestTargets.enabled, !workspaceTestPicks.isEmpty {
            let next = workspaceTestPicks.removeFirst()
            return picked(next.map { .success($0) } ?? .failure(CocoaError(.userCancelled)))
        }
        picking = true
    }

    func picked(_ result: Result<[URL], Error>) {
        if case .success(let urls) = result { photos.append(contentsOf: urls.filter { !photos.contains($0) }) }
    }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        Task {
            let sent = await WorkspaceStore.uploadPhotos(photos, cached: uploaded, keys: uploadKeys, read: WorkspaceStore.readPicked) {
                await store.client.upload($0, name: $1, key: $2)
            }
            uploaded = sent.cached; uploadKeys = sent.keys
            switch sent.stop {
            case .unreadable?: save.busy = false; save.message = "读不到所选文件，未保存；输入已保留。"; return
            case .noID?: save.busy = false; save.message = "照片没有保存成功，未保存反馈；可以重试。"; return
            case .outcome(let other)?: await store.finish(other, save, done: ""); return
            case nil: break
            }
            let ids = sent.ids
            let body: [String: Any] = ["task_id": item.task_id, "child": store.childName, "note": note, "attachments": ids,
                                       "complete": false, "request_key": save.key, "day": store.view?.today ?? store.day]
            await store.finish(await store.client.post("/api/task/feedback", body), save, done: "反馈已保存在这一项下。")
        }
    }
}

struct WrongSheet: View {
    @ObservedObject var store: WorkspaceStore
    let item: DayItem
    let record: SavedRecord
    @StateObject var save = SaveState()
    @State var label = ""
    @State var reason = ""
    @State var text = ""
    @State var answer = ""

    var body: some View {
        SheetFrame(store: store, save: save, title: "记一道错题", context: "\(store.childName) · \(item.subject) · 来自 \(record.created.prefix(16)) 的反馈",
                   dirty: !label.isEmpty || !reason.isEmpty || !text.isEmpty || !answer.isEmpty, canSave: !label.trimmingCharacters(in: .whitespaces).isEmpty, saveTitle: "保存错题", onSave: submit) {
            Section {
                TextField("哪一题（必填）", text: $label).probe("wrong-label")
                TextField("题面（可不填）", text: $text).probe("wrong-text")
                TextField("孩子原答（可不填）", text: $answer).probe("wrong-answer")
                LabeledContent("原因（可不填）") { TextEditor(text: $reason).multilineTextAlignment(.leading).frame(minHeight: 70).probe("wrong-reason").accessibilityLabel("原因") }
            }
        }
    }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        let subject = [WorkspaceStore.general, WorkspaceStore.unknown].contains(item.subject) ? "" : item.subject
        let body: [String: Any] = ["child": store.childName, "day": store.view?.today ?? store.day, "subject": subject, "request_key": save.key,
                                   "items": [["label": label, "note": reason, "text": text, "answer": answer]], "task_id": record.task_id ?? item.task_id,
                                   "feedback_record_id": record.id, "feedback_created": record.created]
        Task { await store.finish(await store.client.post("/api/wrong/save", body), save, done: "错题已记在同一份作业下。") }
    }
}

struct CorrectionSheet: View {
    @ObservedObject var store: WorkspaceStore
    let record: SavedRecord
    @StateObject var save = SaveState()
    @State var kind = "订正"
    @State var note = ""
    /// 与网页记录同一字段与选项（app.ASSISTANCE / PRACTICE_RELATIONS）；空＝未知，不从订正或说明推断帮助、完成或掌握。
    @State var assistance = ""
    @State var practice = ""
    static let assistanceChoices = ["", "独立尝试", "少量提示", "逐步帮助", "看过讲解或答案"]
    static let practiceChoices = ["", "同一道题或同一片段", "相近的新题或新片段", "范围或难度不同"]

    var body: some View {
        SheetFrame(store: store, save: save, title: "记订正", context: "\(store.childName) · \(record.title)", dirty: !note.isEmpty || !assistance.isEmpty || !practice.isEmpty,
                   canSave: !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, saveTitle: "保存", onSave: submit) {
            Section {
                Picker("类型", selection: $kind) { Text("订正").tag("订正"); Text("复测").tag("复测") }.pickerStyle(.segmented).probe("correction-kind")
                LabeledContent("怎么订正的 / 复测结果") { TextEditor(text: $note).multilineTextAlignment(.leading).frame(minHeight: 80).probe("correction-note").accessibilityLabel("订正说明") }
                Picker("这次的帮助", selection: $assistance) { ForEach(Self.assistanceChoices, id: \.self) { Text($0.isEmpty ? "未知" : $0).tag($0) } }.probe("correction-assistance")
                Picker("和原题的关系", selection: $practice) { ForEach(Self.practiceChoices, id: \.self) { Text($0.isEmpty ? "未知" : $0).tag($0) } }.probe("correction-practice")
            }
        }
    }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        let body: [String: Any] = ["child": store.childName, "day": store.view?.today ?? store.day, "category": "学习进展",
                                   "title": (kind + "：" + record.title).prefix(200).description, "subject": record.subject, "note": note,
                                   "related_record_id": record.id, "followup_kind": kind, "assistance": assistance, "practice_relation": practice,
                                   "request_key": save.key]
        Task { await store.finish(await store.client.post("/api/record", body), save, done: "已记下\(kind)。") }
    }
}

/// 没有原作业的一道错题：孩子、科目和题目写明，照片是原件（现有错题保存在没有原作业时要求一张原图，原样保留）；
/// 不新建作业或反馈。保存走原有错题保存与同一提交标识的防重复。
struct WrongAddSheet: View {
    @ObservedObject var store: WorkspaceStore
    /// 有值时是当前原作业：孩子、作业和科目固定，不用先写反馈；题号/题面/原答/订正任一项即可，照片可不选，选了保整张原图。
    var item: DayItem? = nil
    /// 直接错题的记录日：打开时取家庭服务端的今天（store.view.today）定下、显示，并随同一提交标识重试；读不到就待核、不能保存，
    /// 不用所浏览的清单日或本机时钟猜。它不是老师截止、原作答日或安排日，也不改作业。
    @State var recordDay = ""
    @StateObject var save = SaveState()
    @State var subject = ""
    @State var label = ""
    @State var text = ""
    @State var answer = ""
    @State var correction = ""
    @State var photos: [URL] = []
    @State var uploaded: [String: String] = [:]
    @State var uploadKeys: [String: String] = [:]
    @State var picking = false

    var body: some View {
        SheetFrame(store: store, save: save, title: "记一道错题",
                   context: item.map { "\(store.childName) · \($0.subject) · \($0.title)（不用先写反馈，不会新建作业）" } ?? "\(store.childName) · 没有原作业（不会新建作业或反馈）",
                   dirty: !(subject + label + text + answer + correction).isEmpty || !photos.isEmpty,
                   canSave: item == nil ? !label.trimmingCharacters(in: .whitespaces).isEmpty && !photos.isEmpty
                       : !recordDay.isEmpty && [label, text, answer, correction].contains(where: { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
                   saveTitle: "保存错题", onSave: submit) {
            Section {
                if item == nil { TextField("科目（可不填）", text: $subject).probe("wrong-add-subject") }
                else {
                    LabeledContent("记录日") { Text(recordDay.isEmpty ? "待核：还没读到家庭服务的今天，请先刷新清单" : "\(recordDay)（家庭服务今天）").probe("wrong-add-record-day", text: recordDay) }
                    Text("这是记下这道错题的日期，不是老师截止或作业日期，也不会改这份作业。").font(.caption).foregroundStyle(Palette.ink2)
                }
                TextField(item == nil ? "哪一题（必填）" : "哪一题（可不填）", text: $label).probe("wrong-add-label")
                TextField("题面（可不填）", text: $text).probe("wrong-add-text")
                TextField("孩子原答（可不填）", text: $answer).probe("wrong-add-answer")
                TextField("订正 / 正确做法（可不填）", text: $correction).probe("wrong-add-correction")
            }
            Section(item == nil ? "这道题的照片（必选，原图原样保留）" : "这道题的照片（可不选，整张原图保留）") {
                if photos.isEmpty { Text(item == nil ? "没有原作业时，需要一张这道题的照片作原件。" : "可只选照片并写题号；不选照片也能保存。").font(.caption).foregroundStyle(Palette.ink2) }
                ForEach(photos, id: \.self) { url in Text(url.lastPathComponent).lineLimit(1).truncationMode(.middle).probe("wrong-add-photo-name", text: url.lastPathComponent) }
                Button(photos.isEmpty ? "选择照片…" : "换一张照片…") { pick() }.probe("wrong-add-photo")
            }
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.image], allowsMultipleSelection: false) { picked($0) }
        .onAppear { if item != nil && recordDay.isEmpty { recordDay = store.view?.today ?? "" } }
    }

    func pick() {
        if TestTargets.enabled, !workspaceTestPicks.isEmpty {
            let next = workspaceTestPicks.removeFirst()
            return picked(next.map { .success($0) } ?? .failure(CocoaError(.userCancelled)))
        }
        picking = true
    }

    func picked(_ result: Result<[URL], Error>) { if case .success(let urls) = result, let first = urls.first { photos = [first] } }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        Task {
            var id = ""
            if let url = photos.first {
                let sent = await WorkspaceStore.uploadPhotos([url], cached: uploaded, keys: uploadKeys, read: WorkspaceStore.readPicked) {
                    await store.client.upload($0, name: $1, key: $2)
                }
                uploaded = sent.cached; uploadKeys = sent.keys
                switch sent.stop {
                case .unreadable?: save.busy = false; save.message = "读不到所选照片，未保存；输入已保留。"; return
                case .noID?: save.busy = false; save.message = "照片没有保存成功，未保存错题；可以重试。"; return
                case .outcome(let other)?: await store.finish(other, save, done: ""); return
                case nil: break
                }
                id = sent.ids.first ?? ""
            } else if item == nil { save.busy = false; return }
            let today = store.view?.today ?? store.day
            let day = item != nil ? recordDay : store.day.isEmpty || store.day > today ? today : store.day
            var body: [String: Any] = ["child": store.childName, "day": day, "subject": subject.trimmingCharacters(in: .whitespaces), "request_key": save.key,
                                       "items": [["attachment": id, "label": label, "text": text, "answer": answer, "correction": correction]]]
            if let item = item {
                // 只带 task_id、不带任何 feedback_* 键：服务端在保存事务里核同孩原作业，不造反馈、不标完成。
                body["subject"] = [WorkspaceStore.general, WorkspaceStore.unknown].contains(item.subject) ? "" : item.subject
                body["task_id"] = item.task_id
            }
            await store.finish(await store.client.post("/api/wrong/save", body), save, done: item == nil ? "错题已记进错题本。" : "错题已记在这份作业下。")
        }
    }
}

struct OralSheet: View {
    @ObservedObject var store: WorkspaceStore
    @StateObject var save = SaveState()
    @State var subject = ""
    @State var what = ""
    @State var tomorrow = false
    @State var photos: [URL] = []
    @State var uploaded: [String: String] = [:]
    @State var uploadKeys: [String: String] = [:]
    @State var picking = false
    @State var complete = "unknown"
    @State var completeDay = Date()
    @State var handback = "unknown"
    @State var handbackDay = Date()
    @State var version: Int?

    var body: some View {
        SheetFrame(store: store, save: save, title: "补录口头作业", context: "\(store.childName) · 来源：孩子口头转述",
                   dirty: !subject.isEmpty || !what.isEmpty || !photos.isEmpty || complete != "unknown" || handback != "unknown",
                   canSave: !what.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                   saveTitle: "保存补录", onSave: submit) {
            Section {
                // 两个都是系统文本框，点哪个就在哪个里输入；不再另设焦点绑定（它曾把“要做什么”的输入拉回科目框）。
                TextField("科目（可后补）", text: $subject).probe("oral-subject")
                TextField("要做什么（必填）", text: $what, axis: .vertical).lineLimit(3...6).multilineTextAlignment(.leading)
                    .accessibilityLabel("要做什么").probe("oral-what")
                Picker("做的日子", selection: $tomorrow) { Text("正在看的这天").tag(false); Text("后一天").tag(true) }.probe("oral-day")
                // 做的日子是家里安排的那天；老师要求的完成日、交回日各自单独选，不知道就留空，不拿做的日子去填。
                Picker("老师要求完成", selection: $complete) { Text("还不知道").tag("unknown"); Text("指定日期").tag("day") }.probe("oral-complete")
                if complete == "day" { DatePicker("完成日", selection: $completeDay, displayedComponents: .date).probe("oral-complete-day") }
                Picker("老师要求交回", selection: $handback) { Text("还不知道").tag("unknown"); Text("指定日期").tag("day") }.probe("oral-handback")
                if handback == "day" { DatePicker("交回日", selection: $handbackDay, displayedComponents: .date).probe("oral-handback-day") }
            }
            Section("照片（可不加）") {
                if photos.isEmpty { Text("还没有选；只写要做什么也能保存。").font(.caption).foregroundStyle(Palette.ink2).probe("oral-files-empty", text: "还没有选") }
                ForEach(Array(photos.enumerated()), id: \.element) { index, url in
                    HStack {
                        Text(url.lastPathComponent).lineLimit(1).truncationMode(.middle).probe("oral-file-\(index)", text: url.lastPathComponent)
                        Spacer()
                        // 只从这次补录里去掉：已上传的原件不删不改；再选同一文件沿用已上传的那份。
                        Button("移除") { photos.removeAll { $0 == url } }.buttonStyle(.borderless).controlSize(.small)
                            .help("只从这次补录里去掉，不删除原件").accessibilityLabel("移除 \(url.lastPathComponent)").probe("oral-file-remove-\(index)", text: url.lastPathComponent)
                    }
                }
                Button(photos.isEmpty ? "选择照片或 PDF…" : "再加照片或 PDF…") { pick() }.probe("oral-photo")
            }
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.image, .pdf], allowsMultipleSelection: true) { picked($0) }
    }

    /// 与反馈同一取文件方式：--smoke-test 里取测试声明的文件（或取消），正常使用打开系统选择框。
    func pick() {
        if TestTargets.enabled, !workspaceTestPicks.isEmpty {
            let next = workspaceTestPicks.removeFirst()
            return picked(next.map { .success($0) } ?? .failure(CocoaError(.userCancelled)))
        }
        picking = true
    }

    func picked(_ result: Result<[URL], Error>) {
        if case .success(let urls) = result { photos.append(contentsOf: urls.filter { !photos.contains($0) }) }
    }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        let base = WorkspaceStore.date(store.day) ?? Date()
        let day = WorkspaceStore.text(tomorrow ? Calendar(identifier: .gregorian).date(byAdding: .day, value: 1, to: base) ?? base : base)
        let completeOn = complete == "day" ? WorkspaceStore.text(completeDay) : "", handbackOn = handback == "day" ? WorkspaceStore.text(handbackDay) : ""
        Task {
            // 先传照片：失败就不保存补录，填写和已传的编号都留着；重试只补没传成功的那张，同一提交标识与内容不变。
            let sent = await WorkspaceStore.uploadPhotos(photos, cached: uploaded, keys: uploadKeys, read: WorkspaceStore.readPicked) {
                await store.client.upload($0, name: $1, key: $2)
            }
            uploaded = sent.cached; uploadKeys = sent.keys
            switch sent.stop {
            case .unreadable?: save.busy = false; save.message = "读不到所选文件，未保存；输入已保留。"; return
            case .noID?: save.busy = false; save.message = "照片没有保存成功，未保存补录；可以重试。"; return
            case .outcome(let other)?: await store.finish(other, save, done: ""); return
            case nil: break
            }
            do {
                // 重试沿用第一次读到的版本：同一提交标识、同一内容，服务端才认作同一次补录。
                var version = self.version ?? -1
                if version < 0 { version = try await store.client.studyVersion(child: store.childID, day: day) }
                self.version = version
                let body = WorkspaceStore.oralBody(child: store.childID, day: day, key: save.key, version: version, subject: subject, what: what,
                                                   completeOn: completeOn, handbackOn: handbackOn, attachments: sent.ids)
                await store.finish(await store.client.post("/api/study/item", body), save, done: "已补录到\(day)。")
            } catch {
                save.busy = false; save.message = ((error as? WorkspaceError)?.text ?? "暂时读不到这一天的作息，未保存；输入已保留。")
            }
        }
    }
}

extension WorkspaceStore {
    static let general = "综合事务", unknown = "科目待定"
}

// MARK: 原生验收用的控件锚点（仅 --smoke-test 的原生验收打开）：每个控件背后放一个不接收点击的 AppKit 视图，
// 验收时由 AppKit 换算它当下在窗口里的位置，再在那里投递真实鼠标事件；同时记下控件显示的文字。
final class ProbeAnchor: NSView {
    var probeID = ""
    var probeText = ""
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

final class WeakAnchor { weak var view: ProbeAnchor?; init(_ view: ProbeAnchor) { self.view = view } }

@MainActor
enum TestTargets {
    static var enabled = false
    /// 同一标识可能同时挂在几个视图上（列表复用的行、量高度用的行）：只认此刻仍属于这个标识、在窗口里的；
    /// 有多个时选在它中心点下去确实落在它自己那一格上的（而不是列表空白处）。
    static var anchors: [String: [WeakAnchor]] = [:]
    static func register(_ view: ProbeAnchor, _ id: String, _ text: String) {
        view.probeID = id; view.probeText = text
        anchors[id] = (anchors[id] ?? []).filter { $0.view != nil && $0.view !== view } + [WeakAnchor(view)]
    }
    static func live(_ id: String) -> (ProbeAnchor, String)? {
        let shown = (anchors[id] ?? []).reversed().compactMap(\.view).filter { $0.probeID == id && $0.window != nil && !$0.isHiddenOrHasHiddenAncestor }
        // 在列表里的：只认确实在表格某一行里的（复用后闲置的旧行不算）。
        let placed = shown.filter { table(of: $0) == nil || row(of: $0) != nil }
        guard let best = placed.first(where: reachable) ?? placed.first ?? shown.first else { return nil }
        // 行内文字的几何核对（只在验收里）：这段文字的框是否整段落在它那一行表格行之内（行高不够时会被行裁掉，FitProbe 看不到）。
        if id.hasPrefix("row-fit-"), let hit = row(of: best) {
            let f = hit.0.convert(best.bounds, from: best), r = hit.0.rect(ofRow: hit.1)
            return (best, (f.minY >= r.minY - 0.5 && f.maxY <= r.maxY + 0.5 && f.minX >= r.minX - 0.5 && f.maxX <= r.maxX + 0.5 ? "inrow " : "clipped ") + best.probeText)
        }
        return (best, best.probeText)
    }
    static func table(of view: NSView) -> NSTableView? {
        var next = view.superview
        while let v = next { if let t = v as? NSTableView { return t }; next = v.superview }
        return nil
    }
    static func row(of view: NSView) -> (NSTableView, Int)? {
        guard let t = table(of: view) else { return nil }
        let r = t.row(for: view)
        return r >= 0 ? (t, r) : nil
    }
    static func reachable(_ view: ProbeAnchor) -> Bool {
        guard let content = view.window?.contentView else { return false }
        let r = content.convert(view.bounds, from: view)
        guard let hit = content.hitTest(content.convert(NSPoint(x: r.midX, y: r.midY), to: content.superview)) else { return false }
        return view.isDescendant(of: hit) && !(hit is NSTableView)
    }
}

struct ProbeAnchorView: NSViewRepresentable {
    let id: String
    let text: String
    func makeNSView(context: Context) -> ProbeAnchor { let v = ProbeAnchor(); TestTargets.register(v, id, text); return v }
    func updateNSView(_ view: ProbeAnchor, context: Context) { TestTargets.register(view, id, text) }
}

extension View {
    @ViewBuilder func probe(_ id: String, text: String = "") -> some View {
        if TestTargets.enabled { self.accessibilityIdentifier(id).background(ProbeAnchorView(id: id, text: text)) }
        else { self.accessibilityIdentifier(id) }
    }
}


// MARK: - 批量照片导入（PRD 5.1 M1）

/// 一次导入还没登记完的照片：逐张上传的原件编号与上传标识、批次提交标识都留着，失败或回执丢失后用同一组重试。
struct PhotoImportDraft {
    let child: String
    let key: String
    var urls: [URL]
    var cached: [String: String] = [:]
    var keys: [String: String] = [:]
    /// 给已有批次补照片：同一批的编号与当时版本（nil 为新建一批）。
    var target: String? = nil
    var version: Int? = nil
    /// 登记（create/append）已发出但回执不明：只能用同一提交标识与同一内容重试读回，不能放弃或被新导入覆盖。
    var sent = false
}

extension WorkspaceStore {
    var photoBatchesShown: [PhotoBatch] { photoChild == childID ? photoBatches : [] }
    var selectedPhotoPaper: (PhotoBatch, PhotoPaper)? {
        guard record == nil, let id = photoPaper, let batch = photoBatchesShown.first(where: { $0.id == photoPaperBatch }),
              let paper = batch.papers.first(where: { $0.paper_id == id }) else { return nil }
        return (batch, paper)
    }

    /// 只读：按当前孩子读已存批次，不触发后台或模型。换了孩子或有更新的读取时，迟到的读回不覆盖当前显示。
    func loadPhotoBatches() async {
        let child = childID
        guard !child.isEmpty else { return }
        photoSequence += 1
        let mine = photoSequence
        do {
            let data = try await client.get("/api/photo-batches", ["child_id": child])
            let list = try JSONDecoder().decode(PhotoBatchList.self, from: data)
            guard mine == photoSequence, child == childID, list.child_id == child else { return }
            photoBatches = list.batches; photoChild = child; photoLoadError = ""
            // 读回的是批次列表与各批实际状态：只清这两类；原图失败等它自己读成功才清。
            photoProblems = photoProblems.filter { $0.key.hasPrefix("image:") || $0.key == "day" }
            await syncSavedRecords()
        } catch {
            guard mine == photoSequence, child == childID else { return }
            if let e = error as? WorkspaceError, e.login { loginRequired = true; openLogin() }
            photoLoadError = (error as? WorkspaceError)?.text ?? "导入的照片结果暂时读不到；原照片和结果都在。"
            photoProblems["list"] = "点“重新读取”读回当前孩子的照片结果。"
        }
    }

    /// 后台还在处理时每隔几秒只读一次；离开错题本、换孩子或都处理完就停。客户端不触发后台、不重发失败步骤。
    func pollPhotoBatches() async {
        while !Task.isCancelled {
            await loadPhotoBatches()
            guard mode == .wrong, photoBatchesShown.contains(where: { $0.state == "queued" || $0.state == "running" }) else { return }
            try? await Task.sleep(nanoseconds: 3_000_000_000)
        }
    }

    /// 批次里已记下的原错题编号还不在原错题清单里：按原 /api/day（同一孩子、同一天）读回一次，原清单仍是唯一依据，
    /// 不另算错题、不写记录。读不到时标“错题已保存，原清单待更新”，不被普通批次读回清掉，只由当前页“重新读取”再读。
    func syncSavedRecords(force: Bool = false) async {
        let child = childID
        let saved = Set(photoBatchesShown.flatMap(\.papers).flatMap(\.questions).compactMap(\.record_id))
        let missing = saved.subtracting(wrongItems.map(\.id))
        guard !missing.isEmpty, force || photoProblems["day"] == nil, force || !missing.isSubset(of: photoSyncedRecords) else { return }
        await load()
        guard child == childID else { return }
        if current != nil && error.isEmpty { photoSyncedRecords.formUnion(saved); photoProblems["day"] = nil }
        else { photoProblems["day"] = "错题已保存，原错题清单待更新；点“重新读取”再读。" }
    }

    /// 当前页的读回：只 GET 同一孩子的批次与原图（并重新挂上只读轮询），不上传、不重新登记、不重发 continue/include、不调模型。
    func refreshPhotos() async {
        photoImageEpoch += 1
        await loadPhotoBatches()
        if photoProblems["day"] != nil { await syncSavedRecords(force: true) }
        // 仍未读成功的原图：按同一编号再只读一次（成功才清它那一条，失败照旧保留恢复入口）。
        for key in photoProblems.keys.sorted() where key.hasPrefix("image:") { _ = await photoImage(String(key.dropFirst(6))) }
        photoPollToken += 1
    }

    /// 还有没确认的导入时不开始新的一批：回执不明的只能用同一提交重试；明确没写入的可以先放弃。
    func photoDraftBlocks() -> Bool {
        guard let draft = photoDraft else { return false }
        photoNotice = draft.sent ? "上一批的登记回执还没确认：请先点“用同一提交重试”核对，不会重复登记。"
            : "上一批照片还没登记：请先“用同一提交重试”，或“放弃这次导入”后再选新的照片。"
        return true
    }

    func discardPhotoDraft() {
        guard let draft = photoDraft, !draft.sent, !photoBusy else { return }
        guard confirmDiscard("放弃这次还没登记的照片导入（已上传的原件保留）") else { return }
        photoDraft = nil; photoNotice = "已放弃这次导入；已上传的原件仍保存在家庭原件里。"
    }

    /// 给同一批补照片：沿原 append 接口、当前版本与同样的逐张上传/同一提交重试；不新建批次，旧判断在新版本中标待更新。
    func appendPhotos(_ batch: PhotoBatch, _ urls: [URL]) {
        guard !photoBusy, !photoDraftBlocks() else { return }
        guard batch.child_id == childID else { photoNotice = "这批照片属于另一个孩子，没有补入。"; return }
        let images = urls.filter { UTType(filenameExtension: $0.pathExtension)?.conforms(to: .image) ?? false }
        guard !images.isEmpty else { photoNotice = "没有可补的照片（只收图片文件）。"; return }
        guard batch.pages.count + images.count <= 30 else { photoNotice = "每批最多30张，这批已有\(batch.pages.count)张；请另建一批。"; return }
        photoDraft = PhotoImportDraft(child: childID, key: requestKey(), urls: images, target: batch.id, version: batch.version)
        Task { await runPhotoImport() }
    }

    func importPhotos(_ urls: [URL]) {
        guard !photoBusy, !photoDraftBlocks() else { return }
        let images = urls.filter { UTType(filenameExtension: $0.pathExtension)?.conforms(to: .image) ?? false }
        guard !images.isEmpty else { photoNotice = "没有可导入的照片（只收图片文件）。"; return }
        guard images.count <= 30 else { photoNotice = "每批最多30张，这次选了\(images.count)张；请分两批导入。"; return }
        guard !childID.isEmpty else { photoNotice = "请先选一个孩子。"; return }
        photoDraft = PhotoImportDraft(child: childID, key: requestKey(), urls: images)
        Task { await runPhotoImport() }
    }

    /// 逐张按原上传守卫保存（每张一个上传标识并一直沿用），再用同一批次提交标识登记；任何一步没确认就停下，
    /// 已上传的原件编号、上传标识和批次标识都留在草稿里：“用同一提交重试”不重传已存的照片，也不多建批次。
    func runPhotoImport() async {
        guard var draft = photoDraft, !photoBusy else { return }
        guard draft.child == childID else { photoNotice = "这次导入属于另一个孩子，没有继续；请切回原孩子再重试。"; return }
        photoBusy = true
        defer { photoBusy = false }
        photoNotice = "正在保存原件（共\(draft.urls.count)张）…"
        let client = self.client
        let up = await WorkspaceStore.uploadPhotos(draft.urls, cached: draft.cached, keys: draft.keys, read: WorkspaceStore.readPicked,
                                                   send: { data, name, key in await client.upload(data, name: name, key: key) })
        draft.cached = up.cached; draft.keys = up.keys; photoDraft = draft
        if let stop = up.stop {
            photoNotice = "第\(up.ids.count + 1)张照片没有保存（\(photoStopText(stop))）；前\(up.ids.count)张原件已保存，可用同一提交重试。"
            return
        }
        photoNotice = draft.target == nil ? "原件已保存，正在登记这一批…" : "原件已保存，正在补进同一批…"
        var body: [String: Any] = ["request_key": draft.key, "uploads": up.ids]
        if let target = draft.target { body["batch_id"] = target; body["version"] = draft.version ?? 0 } else { body["child_id"] = draft.child }
        draft.sent = true; photoDraft = draft
        switch await client.post(draft.target == nil ? "/api/photo-batch/create" : "/api/photo-batch/append", body) {
        case .saved(let reply):
            guard let batch = decodePhotoBatch(reply) else { photoNotice = "登记回执无法读取；原件已保存，可用同一提交重试。"; return }
            photoDraft = nil
            if draft.child == childID { photoBatches = [batch] + photoBatches.filter { $0.id != batch.id }; photoChild = draft.child }
            photoNotice = (reply["replayed"] as? Bool) == true ? "已找到这一次提交的结果，没有重复登记。"
                : draft.target == nil ? "已登记，后台会自动分科、分卷和检查；可以先离开，回来即可看到结果。"
                : "已补进同一批（第\(batch.version)版）：受影响的卷会重新检查，旧判断标为依据已变，原错题保留。"
            photoPollToken += 1
        case .refused(let status, let message, let code):
            draft.sent = false; photoDraft = draft
            if status == 401 { loginRequired = true; openLogin() }
            photoNotice = message + (code == "photo_batch_changed" || code == "photo_batch_busy"
                ? "（这次补照片没有写入；已上传的原件保留，刷新后可重新补）" : "（这次没有写入；已上传的原件保留）")
        case .unknown:
            photoNotice = "没有收到登记回执；原件已保存，可用同一提交重试，不会重复登记。"
        }
    }

    func photoStopText(_ stop: PhotoStop) -> String {
        switch stop {
        case .unreadable: return "读不到这张照片文件"
        case .noID: return "回执里没有原件编号"
        case .outcome(.refused(let status, let message, _)):
            if status == 401 { loginRequired = true }
            return message
        case .outcome(.unknown): return "没有收到回执"
        case .outcome(.saved): return "回执无法读取"
        }
    }

    func decodePhotoBatch(_ reply: [String: Any]) -> PhotoBatch? {
        guard let data = try? JSONSerialization.data(withJSONObject: reply) else { return nil }
        return try? JSONDecoder().decode(PhotoBatch.self, from: data)
    }

    /// 家长明确“继续失败部分”：只用这一批当前版本提交一次；回执不明不自动重发，到调用上限时服务端不再给继续。
    func continuePhotoBatch(_ batch: PhotoBatch) async {
        guard batch.child_id == childID else { return }
        applyPhotoOutcome(await client.post("/api/photo-batch/continue", ["batch_id": batch.id, "version": batch.version]),
                          done: "已排入后台，只重做未完成的步骤。")
    }

    func includePhotoQuestion(_ batch: PhotoBatch, _ question: PhotoQuestion) async {
        guard batch.child_id == childID else { return }
        applyPhotoOutcome(await client.post("/api/photo-batch/include", ["batch_id": batch.id, "version": batch.version, "question_key": question.key]),
                          done: "已纳入练习，记在原错题里（署名AI判断）。")
        await load()
    }

    func applyPhotoOutcome(_ outcome: PostOutcome, done: String) {
        switch outcome {
        case .saved(let reply):
            if let batch = decodePhotoBatch(reply), batch.child_id == childID {
                photoBatches = photoBatches.map { $0.id == batch.id ? batch : $0 }; photoNotice = done; photoPollToken += 1
            }
        case .refused(let status, let message, _):
            if status == 401 { loginRequired = true; openLogin() }
            photoNotice = message
        case .unknown:
            photoNotice = "没有收到回执，结果未知；不会自动重发。"
            photoProblems["batch"] = "点“重新读取”核对这一批的实际状态。"
        }
    }

    /// AI 判错已记成原错题（同一记录编号）：在错题本打开同一道，订正、知识点和复测都走原链。
    func openPhotoRecord(_ id: Int) async {
        if !wrongItems.contains(where: { $0.id == id }) { await load() }
        if wrongItems.contains(where: { $0.id == id }) { showRecord(id) }
        else { photoNotice = "这道错题的原记录还没读到；请刷新后再打开，记录不会重复建。" }
    }

    /// 原图只读：401 走原登录恢复；其他失败给当前页“重新读取”，不吞成静默空白。
    func photoImage(_ uploadID: String) async -> NSImage? {
        if let image = photoImages[uploadID] { return image }
        guard !uploadID.isEmpty else { return nil }
        let child = childID, key = "image:" + uploadID
        do {
            let data = try await client.get("/upload/" + uploadID)
            guard child == childID else { return nil }  // 换了孩子：迟到的读回不记到新页面
            guard let image = NSImage(data: data) else { photoProblems[key] = "这张原图无法显示；点“重新读取”再试。"; return nil }
            photoImages[uploadID] = image; photoProblems[key] = nil
            return image
        } catch {
            guard child == childID else { return nil }
            if let e = error as? WorkspaceError, e.login { loginRequired = true; openLogin(); photoProblems[key] = "需要先登录家庭账号；登录后点“重新读取”。" }
            else { photoProblems[key] = "原图暂时读不到；点“重新读取”再试，结果不受影响。" }
            return nil
        }
    }
}

/// 错题本左栏最上面：当前孩子的“导入照片…”（多选或拖入），以及最近导入的批次与每份卷；处理中先显示已完成的部分。
struct PhotoImportSection: View {
    @ObservedObject var store: WorkspaceStore
    @State var picking = false
    @State var targeted = false
    @State var appending: PhotoBatch?
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Button { pick() } label: { Label("导入照片…", systemImage: "photo.on.rectangle.angled") }
                    .buttonStyle(GroveButtonStyle(kind: .primary)).disabled(store.photoBusy).probe("photo-import")
                if store.photoDraft != nil && !store.photoBusy {
                    Button("用同一提交重试") { Task { await store.runPhotoImport() } }.buttonStyle(GroveButtonStyle(kind: .secondary)).probe("photo-retry")
                    if store.photoDraft?.sent == false {
                        Button("放弃这次导入") { store.discardPhotoDraft() }.buttonStyle(GroveButtonStyle(kind: .quiet)).probe("photo-discard")
                    }
                }
            }
            if !store.photoRecovery.isEmpty {
                HStack(spacing: 8) {
                    Text(store.photoRecovery).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                    Button("重新读取") { Task { await store.refreshPhotos() } }.buttonStyle(GroveButtonStyle(kind: .secondary)).probe("photo-refresh")
                }
            }
            Text("一次可选或拖入最多30张，不同科目、乱序都可以；系统自动分科、分卷和检查，不用先填科目或题号。")
                .font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
            if !store.photoNotice.isEmpty {
                Text(store.photoNotice).font(Palette.small).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true).probe("photo-notice", text: store.photoNotice)
            }
            if !store.photoLoadError.isEmpty {
                Text(store.photoLoadError).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
            }
            ForEach(store.photoBatchesShown.prefix(5)) { batch in PhotoBatchCard(store: store, batch: batch, append: { pick(append: batch) }) }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(targeted ? Palette.leaf50 : Color.clear))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(targeted ? Palette.leaf400 : Color.clear, style: StrokeStyle(lineWidth: 1.5, dash: [5])))
        .onDrop(of: [UTType.fileURL], isTargeted: $targeted) { providers in drop(providers) }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.image], allowsMultipleSelection: true) { result in
            if case .success(let urls) = result { if let batch = appending { store.appendPhotos(batch, urls) } else { store.importPhotos(urls) } }
            appending = nil
        }
        .task(id: "\(store.childID)|\(store.mode.rawValue)|\(store.photoPollToken)") { await store.pollPhotoBatches() }
    }

    func pick(append batch: PhotoBatch? = nil) {
        if store.photoBusy || store.photoDraftBlocks() { return }
        if TestTargets.enabled, !workspaceTestPicks.isEmpty {
            if let urls = workspaceTestPicks.removeFirst() { if let batch { store.appendPhotos(batch, urls) } else { store.importPhotos(urls) } }
            return
        }
        appending = batch; picking = true
    }

    func drop(_ providers: [NSItemProvider]) -> Bool {
        let wanted = providers.filter { $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }
        guard !wanted.isEmpty else { return false }
        Task { @MainActor in
            var urls: [URL] = []
            for provider in wanted {
                let url: URL? = await withCheckedContinuation { done in _ = provider.loadObject(ofClass: URL.self) { url, _ in done.resume(returning: url) } }
                if let url { urls.append(url) }
            }
            store.importPhotos(urls)
        }
        return true
    }
}

/// 一批照片：导入时间与张数、状态短句；每份卷一行（科目 · 卷名，页数与错/疑似/未判）；待补页、同一张照片、依据已变与失败步骤。
struct PhotoBatchCard: View {
    @ObservedObject var store: WorkspaceStore
    let batch: PhotoBatch
    var append: () -> Void = {}
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(batch.created.prefix(16).replacingOccurrences(of: "T", with: " ") + " 导入 · \(batch.pages.count)张")
                    .font(Palette.round(14, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 6)
                Text(batch.stateWords).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true).probe("photo-state-\(batch.id)", text: batch.state)
            }
            ForEach(batch.papersBySubject) { paper in
                let on = store.record == nil && store.photoPaperBatch == batch.id && store.photoPaper == paper.paper_id
                Button {
                    store.record = nil; store.photoPaperBatch = batch.id; store.photoPaper = paper.paper_id
                    store.photoQuestion = paper.shownQuestions.first?.key
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(paper.subject + " · " + (paper.title.isEmpty ? "未识别卷名" : paper.title))
                            .font(Palette.round(14, .semibold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                        Text(paper.summary).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(8).frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(on ? Palette.leaf50 : Palette.card))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(on ? Palette.leaf400 : Palette.line, lineWidth: on ? 1.5 : 1))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain).probe("photo-paper-\(paper.paper_id)", text: paper.summary)
            }
            ForEach(batch.waitNotes, id: \.self) { note in
                Text(note).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
            }
            if !batch.progress.failed.isEmpty {
                Text(batch.progress.failed.map(\.error).joined(separator: "；")).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 8) {
                if batch.can_continue {
                    Button("继续失败部分") { Task { await store.continuePhotoBatch(batch) } }
                        .buttonStyle(GroveButtonStyle(kind: .secondary)).probe("photo-continue-\(batch.id)")
                }
                Button("给这批补照片…") { append() }.buttonStyle(GroveButtonStyle(kind: .quiet))
                    .disabled(store.photoBusy || batch.state == "running").probe("photo-append-\(batch.id)")
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card).shadow(color: Palette.cardShadow, radius: 4, x: 0, y: 2))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.line, lineWidth: 1))
    }
}

/// 右栏：所选那份卷——科目、卷名/页数、明确错/疑似/未判与覆盖；逐题看原图题框、原答、参考与依据（署名AI判断）。
struct PhotoPaperDetail: View {
    @ObservedObject var store: WorkspaceStore
    let batch: PhotoBatch
    let paper: PhotoPaper
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(paper.subject + " · " + (paper.title.isEmpty ? "未识别卷名" : paper.title))
                    .font(Palette.round(20, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true).probe("photo-paper-title")
                Text(paper.summary).font(Palette.body).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                ForEach(paper.coverageLines, id: \.self) { line in
                    Text(line).font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                }
                if let gaps = paper.unchecked_questions, !gaps.isEmpty {
                    Text("明确未检查：" + gaps.joined(separator: "、")).font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true)
                }
                ForEach(paper.shownQuestions) { q in
                    let on = store.photoQuestion == q.key
                    Button { store.photoQuestion = q.key } label: {
                        HStack(spacing: 8) {
                            Badge(text: q.state_word, tone: q.state == "wrong" ? Palette.coral : Palette.wood, ink: q.state == "wrong" ? Palette.coralInk : Palette.woodInk)
                            Text(q.label + (q.located ? "" : " · 未定位")).font(Palette.body).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 12).frame(minHeight: Palette.hit)
                        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(on ? Palette.leaf50 : Palette.card))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(on ? Palette.leaf400 : Palette.line, lineWidth: on ? 1.5 : 1))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).probe("photo-question-\(q.key)", text: q.state)
                }
                if let q = paper.shownQuestions.first(where: { $0.key == store.photoQuestion }) {
                    PhotoQuestionDetail(store: store, batch: batch, paper: paper, question: q)
                } else if paper.shownQuestions.isEmpty {
                    Text(paper.checked ? "这份卷没有返回错题或未判定题；这不代表全卷正确，未列出的题目仍未检查。" : "这份卷还在检查，先看已完成的部分。")
                        .font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(22).frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Palette.paper)
    }
}

/// 一道题：原图（按实际显示尺寸换算 0…1000 题框）、原答与参考分开、判断依据、署名；已记的错题回到同一条原错题。
struct PhotoQuestionDetail: View {
    @ObservedObject var store: WorkspaceStore
    let batch: PhotoBatch
    let paper: PhotoPaper
    let question: PhotoQuestion
    @State var image: NSImage?
    @State var failed = false
    /// 没有定位到题框时看这一卷第一页的完整原图（不猜框）。
    var uploadID: String {
        if !question.upload_id.isEmpty { return question.upload_id }
        let first = paper.pages.sorted { $0.order < $1.order }.first?.page_id
        return batch.pages.first { $0.page_id == first }?.upload_id ?? ""
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let image {
                Image(nsImage: image).resizable().scaledToFit()
                    .overlay(alignment: .topLeading) {
                        GeometryReader { g in
                            if let b = question.box {
                                Rectangle().strokeBorder(Palette.coral400, lineWidth: 3)
                                    .frame(width: g.size.width * CGFloat(b.w) / 1000, height: g.size.height * CGFloat(b.h) / 1000)
                                    .offset(x: g.size.width * CGFloat(b.x) / 1000, y: g.size.height * CGFloat(b.y) / 1000)
                                    .probe("photo-box", text: "\(b.x),\(b.y),\(b.w),\(b.h)")
                            }
                        }
                    }
                    .frame(maxWidth: 560, maxHeight: 680, alignment: .topLeading)
            } else {
                Text(failed ? "原图暂时读不到；可在左边点“重新读取”，结果不受影响。" : "正在读取原图…").font(Palette.small).foregroundStyle(Palette.ink2)
            }
            if !question.located {
                Text("没有可靠对应的题框，未定位；上面是这一卷的完整原图。").font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
            }
            field("原答（孩子写的）", question.student_answer.isEmpty ? "未能确认" : question.student_answer)
            if !question.answer.isEmpty { field("参考答案", question.answer) }
            if !question.error_reason.isEmpty { field("判断依据", question.error_reason) }
            if !question.uncertainty.isEmpty || !question.conflict.isEmpty {
                field("不确定", [question.conflict, question.uncertainty].filter { !$0.isEmpty }.joined(separator: "；"))
            }
            Text("署名：AI判断，未经老师或家长核定；不代表掌握程度。").font(Palette.small).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true)
            if let followups = question.followups, !followups.isEmpty {
                Text("已记：" + followups.map { ($0.followup_kind.isEmpty ? "跟进" : $0.followup_kind) + " " + $0.day }.joined(separator: "、"))
                    .font(Palette.small).foregroundStyle(Palette.leafInk).fixedSize(horizontal: false, vertical: true)
            }
            if let id = question.record_id {
                Button("打开原错题 · 记订正") { Task { await store.openPhotoRecord(id) } }
                    .buttonStyle(GroveButtonStyle(kind: .primary)).probe("photo-open-record-\(id)")
            } else if question.state == "suspected" {
                Button("纳入练习") { Task { await store.includePhotoQuestion(batch, question) } }
                    .buttonStyle(GroveButtonStyle(kind: .secondary)).probe("photo-include")
            }
        }
        .task(id: "\(uploadID)|\(store.photoImageEpoch)") { image = nil; failed = false; image = await store.photoImage(uploadID); failed = image == nil }
    }

    func field(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(Palette.small).foregroundStyle(Palette.ink2)
            Text(value).font(Palette.body).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
        }
        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Palette.card))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Palette.line, lineWidth: 1))
    }
}

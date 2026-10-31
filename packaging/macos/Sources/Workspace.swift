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
    case feedback(DayItem), oral, wrong(DayItem, SavedRecord), correction(SavedRecord), addWrong
    var id: String {
        switch self {
        case .feedback(let i): return "feedback-" + i.id
        case .oral: return "oral"
        case .wrong(let i, let r): return "wrong-\(i.id)-\(r.id)"
        case .correction(let r): return "correction-\(r.id)"
        case .addWrong: return "wrong-add"
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
    @Published var selection: String?
    @Published var sheet: SheetKind?
    @Published var materials: [String: MaterialState] = [:]
    @Published var notice = ""
    /// 错题本 / 学习进展里选中的那一道原错题：按记录编号，不按标题或数组第一个猜；换孩子时清空。
    @Published var record: Int?
    /// “回原作业”要在日历里选中的原作业：不在正看的这一天时，先换到原错题记下的那一天，再按作业编号选中。
    var pendingTask: String?
    /// 知识点与练习：同一道原错题（记录编号、孩子编号）的知识点面板。
    var openTopic: (Int, String) -> Void = { _, _ in }
    var sheetDirty = false
    let client: WorkspaceClient
    var openDocument: (URL, String) -> Void = { _, _ in }
    /// 次级网页：同一份原作业，带明确意图（print-original / print-reference / check / original / history），由网页原流程接着做。
    var openWebTools: (String, String) -> Void = { _, _ in }
    var openLogin: () -> Void = {}
    var confirmDiscard: (String) -> Bool = { _ in false }
    var onLoaded: () -> Void = {}
    private var sequence = 0

    init(client: WorkspaceClient) { self.client = client }

    var hasUnsavedInput: Bool { sheet != nil && sheetDirty }
    /// 正在显示、可以操作的这一天：只有读回的正是所选孩子、所选日期才算。切换后还没读到或读失败时为 nil——
    /// 上一个孩子/上一天的读取结果只留作缓存（已知孩子仍可切回、重试），不在新选中的孩子/日期下显示、选中、计数或写入。
    var current: DayView? {
        guard let v = view, childID.isEmpty || v.child_id == childID, day.isEmpty || v.day == day else { return nil }
        return v
    }
    var childName: String { current?.child_name ?? "" }
    var groups: [ItemGroup] { showDone ? (current?.closed ?? []) : (current?.groups ?? []) }

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
    var allItems: [DayItem] { (current?.groups ?? []).flatMap(\.items) + (current?.closed ?? []).flatMap(\.items) }
    var selected: DayItem? { allItems.first { $0.id == selection } }
    var wrongItems: [SavedRecord] { wrongGroups.flatMap(\.items) }
    var selectedRecord: SavedRecord? { record.flatMap { id in wrongItems.first { $0.id == id } } }
    func learning(for id: Int) -> LearningEntry? { current?.learning?.subjects.flatMap(\.evidence).first { $0.record_id == id } }

    /// 从学习进展或日历详情打开错题本里的那一道（同一个编号），右栏随即是它的原题、订正与知识点练习。
    func showRecord(_ id: Int) { mode = .wrong; record = id }

    /// 回到同一份原作业：在日历里按作业编号选中；它不在正看的这一天（以前的作业、已办）时，换到原错题记下的那天再选。
    func backToTask(_ task: String, day recordDay: String) {
        guard !task.isEmpty else { return }
        if let item = allItems.first(where: { $0.task_id == task }) { mode = .calendar; showDone = item.closed; select(item.id); return }
        guard sheet == nil || !sheetDirty || confirmDiscard("离开当前填写") else { return }
        mode = .calendar; pendingTask = task
        change(day: recordDay.isEmpty ? day : recordDay)
    }

    func load(keepSelection: Bool = true) async {
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
                if let item = allItems.first(where: { $0.task_id == task }) { showDone = item.closed; selection = item.id }
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

    func select(_ id: String?) {
        if TestTargets.enabled { workspaceTestSelectCalls.append(id ?? "nil") }
        selection = id
        if let item = selected, !item.task_id.isEmpty, materials[item.task_id] == nil { Task { await loadMaterials(item) } }
    }

    /// 切换孩子/日期：弹出层有未保存内容时默认留下；不带着上一个孩子的提示。
    func change(child: String? = nil, day newDay: String? = nil) {
        guard sheet == nil || !sheetDirty || confirmDiscard("离开当前填写") else { return }
        sheet = nil; sheetDirty = false; notice = ""
        if let child, child != childID { childID = child; selection = nil; materials = [:]; record = nil; pendingTask = nil }
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
            var parts = ["共 \(v.counts["open"] ?? 0) 项", "今天要做 \(v.counts["today"] ?? 0)"]
            for (key, label) in [("later", "以后安排"), ("overdue", "已过期限"), ("earlier", "之前安排"), ("unknown", "日期未写明")] {
                if let n = v.counts[key], n > 0 { parts.append("\(label) \(n)") }
            }
            return parts.joined(separator: " · ")
        }
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
    var whenLabel: String { ["later": "以后安排", "overdue": "已过期限", "earlier": "之前安排", "unknown": "日期未写明"][when ?? ""] ?? "" }
    var publishedTime: String { String((published_at ?? "").dropFirst(11).prefix(5)) }
    var source: String { [publisher ?? "", publishedTime].filter { !$0.isEmpty }.joined(separator: " ") }
    var webID: String { task_id.isEmpty ? id : task_id }
    /// 发布一类的事实只是出处，不是要做的日期。
    static let publishRoles: Set<String> = ["published", "publish"]
    var actionFacts: [DayFact] { facts.filter { !DayItem.publishRoles.contains($0.role) } }
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
                // 三个入口同一个外壳：左栏同宽、位置不动，右栏是所选那一项（日历的事项，错题本/学习进展的那一道原错题）。
                HStack(spacing: 0) {
                    SubjectList(store: store).frame(width: compact ? 340 : 400)
                    Rectangle().fill(Palette.line).frame(width: 1)
                    Group {
                        if store.mode == .calendar { Inspector(store: store) } else { RecordDetail(store: store) }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .background(Palette.paper)
        .environment(\.colorScheme, .light)
        .sheet(item: $store.sheet) { kind in SheetHost(store: store, kind: kind) }
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
    return f.label + " " + (f.known ? f.value : "日期未写明")
}

struct SubjectList: View {
    @ObservedObject var store: WorkspaceStore

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            modeSwitch.frame(maxWidth: 520).padding(.horizontal, 14).padding(.top, 14)
            if store.mode == .calendar { WeekStrip(store: store).padding(.horizontal, 14).padding(.top, 8) }
            HStack(alignment: .center, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(store.mode == .calendar ? (store.showDone ? "这一天已办" : "当天清单") : store.mode.rawValue).font(Palette.round(21, .bold)).foregroundStyle(Palette.ink)
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
            ForEach([false, true], id: \.self) { done in
                let on = store.showDone == done, n = store.current?.counts[done ? "closed" : "open"] ?? 0
                let text = (done ? "已办" : "待办") + (n > 0 ? " \(n)" : "")
                Button { store.showDone = done } label: {
                    Text(text).font(Palette.round(13)).padding(.horizontal, 10).frame(minWidth: 58, minHeight: Palette.hit).contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .foregroundStyle(on ? Palette.leafInk : Palette.woodInk)
                .background(Capsule().fill(on ? Palette.card : Color.clear).shadow(color: on ? Palette.wood300 : Color.clear, radius: 0, x: 0, y: 2))
                .accessibilityAddTraits(on ? .isSelected : [])
                .probe(done ? "mode-已办" : "mode-当天", text: text)
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
                ForEach(s.plans) { p in PlanRow(plan: p).listRowSeparator(.hidden) }
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
        List(selection: Binding(get: { store.selection }, set: { store.select($0) })) {
            if !store.showDone { scheduleSection }
            ForEach(store.groups, id: \.subject) { group in
                Section {
                    ForEach(group.items) { item in
                        ItemRow(item: item, selected: store.selection == item.id).tag(item.id).probe("row-" + item.id, text: item.title)
                            .listRowSeparator(.hidden)
                    }
                } header: {
                    WoodTag(text: group.subject, count: "\(group.items.count) 项").padding(.top, 8).padding(.bottom, 2)
                        .probe("subject-" + group.subject)
                }
            }
            if store.groups.isEmpty && store.current != nil {
                Text(store.showDone ? "这一天没有已办的事项。" : "这一天没有已整理的未完成事项；没有反馈不等于没做。")
                    .font(Palette.body).foregroundStyle(Palette.ink2).probe("list-empty")
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .probe("subject-list")
    }
}

/// 清单一行是一张卡片（原型 .row）：做什么、完整完成标准、完成/交回日、出处与已有进展；选中是嫩绿底加绿边，文字保持深色。
struct ItemRow: View {
    let item: DayItem
    var selected = false
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            LeafMark(closed: item.closed).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(item.title).font(Palette.round(15, .bold)).foregroundStyle(item.closed ? Palette.ink2 : Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let first = item.lines.first {
                    // 完整写出，不截断；不加 .help（它把文字包进平台视图，清单行高只按一行算，会截成省略号）。
                    Text(item.lines.joined(separator: "；")).font(Palette.small).foregroundStyle(Palette.ink2).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true).accessibilityHint(first)
                } else { Text("完成标准未提供，待补充").font(Palette.small).foregroundStyle(Palette.coralInk) }
                FlowRow(spacing: 6, lineSpacing: 4) {
                    if !item.whenLabel.isEmpty { Badge(text: item.whenLabel, tone: Palette.paper2, ink: Palette.ink2) }
                    ForEach(item.facts.filter { $0.role == "due" || $0.role == "complete" }, id: \.self) { f in
                        let (tone, ink) = factTone(f)
                        Badge(text: factWords(f), tone: tone, ink: ink)
                    }
                    ForEach(item.times ?? [], id: \.self) { t in Badge(text: "日程 " + planClock(t.start_time, t.end_time), tone: Palette.leaf100, ink: Palette.leafInk) }
                    if item.pending_review { Badge(text: "待核对", tone: Palette.coral, ink: Palette.coralInk) }
                }
                .padding(.top, 2)
                let meta = [item.source, item.progress.map(progressWords) ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
                if !meta.isEmpty { Text(meta).font(.system(size: 12.5)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true) }
            }
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

/// 错题本：左栏是可选中的错题（按编号），右栏是所选那一道；空本和有错题时都能直接记一道。
struct WrongList: View {
    @ObservedObject var store: WorkspaceStore
    var body: some View {
        List(selection: Binding(get: { store.record }, set: { store.record = $0 })) {
            if store.current != nil { addRow.listRowSeparator(.hidden) }
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
                Text("还没有记下的错题。").font(Palette.round(15, .bold)).foregroundStyle(Palette.ink).probe("wrong-empty")
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
struct PlanRow: View {
    let plan: PlanItem
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(planClock(plan.start_time, plan.end_time)).font(.system(size: 13, weight: .semibold))
                .foregroundStyle(plan.start_time.isEmpty ? Palette.ink2 : Palette.leafInk).frame(width: 92, alignment: .leading)
            VStack(alignment: .leading, spacing: 3) {
                Text(plan.title).font(Palette.round(15, .bold)).foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                let meta = [plan.location, plan.status == "tentative" ? "待确认" : "", plan.repeat ? "重复安排" : "", plan.shared ? "几个孩子共同" : "",
                            plan.source.isEmpty ? "" : "学校来源"].filter { !$0.isEmpty }.joined(separator: " · ")
                if !meta.isEmpty { Text(meta).font(.system(size: 12.5)).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true) }
                if let text = plan.unmerged { Text(text).font(.system(size: 12.5)).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true) }
            }
            Spacer(minLength: 0)
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.line, lineWidth: 1))
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
        .probe("plan-" + plan.id, text: planClock(plan.start_time, plan.end_time) + " " + plan.title)
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
                    FlowRow(spacing: 10, lineSpacing: 6) {
                        WoodTag(text: item.subject)
                        // 发布是老师旁的次要出处（原型 .d-source）：老师与完整发布时间一行小字，不占日期卡；原值照写，未知如实写。
                        if let words = item.publishWords {
                            Label(words, systemImage: "bubble.left").font(Palette.small).foregroundStyle(Palette.ink2).frame(minHeight: 26)
                                .probe("detail-publisher", text: words)
                        }
                        if !(item.publications ?? []).isEmpty || item.origin == "school" {
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
                    ForEach(Array(item.lines.enumerated()), id: \.offset) { _, line in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Image(systemName: "leaf.fill").font(.system(size: 11)).foregroundStyle(Palette.leaf400).accessibilityHidden(true)
                            Text(line).font(Palette.body).foregroundStyle(Palette.ink).lineSpacing(3).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                        }
                    }
                    if !item.complete_words.isEmpty { Text("完成要求：" + item.complete_words).font(Palette.body).foregroundStyle(Palette.ink2).fixedSize(horizontal: false, vertical: true) }
                    if item.pending_review {
                        Text("这条学校消息还在待核对，确认后才算正式事项；可在网页版学校信息中核对。").font(Palette.small).foregroundStyle(Palette.coralInk)
                    }
                }
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
            Text((f.today == true ? "今天 " : "") + f.value).font(Palette.round(15, .bold))
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
            if !m.unclear.isEmpty { Text("看不清：" + m.unclear.joined(separator: "；") + "。请看原件。").font(Palette.small).foregroundStyle(Palette.coralInk).fixedSize(horizontal: false, vertical: true) }
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
        .probe("material-" + m.id, text: m.stateLabel + " " + m.name + " " + m.summary)
    }

    func materials(_ item: DayItem) -> some View {
        let state = store.materials[item.task_id] ?? MaterialState()
        return VStack(alignment: .leading, spacing: 10) {
            header("资料与打印", "doc.text")
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
            if item.category == "homework" {
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
            save.conflict = status == 409
            save.message = status == 409 ? text + " 输入已保留；请先“读取最新”核对，再决定是否保存。" : code == "csrf_expired" ? "连接已更新，输入已保留；请再点一次保存。" : text
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
            var ids: [String] = []
            for url in photos {
                if let id = uploaded[url.path] { ids.append(id); continue }
                let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
                guard let data = try? Data(contentsOf: url) else { save.busy = false; save.message = "读不到所选文件，未保存；输入已保留。"; return }
                switch await store.client.upload(data, name: url.lastPathComponent) {
                case .saved(let reply):
                    guard let id = (reply["attachment"] as? [String: Any])?["id"] as? String else { save.busy = false; save.message = "照片没有保存成功，未保存反馈；可以重试。"; return }
                    uploaded[url.path] = id; ids.append(id)
                case let other: await store.finish(other, save, done: ""); return
                }
            }
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

    var body: some View {
        SheetFrame(store: store, save: save, title: "记订正", context: "\(store.childName) · \(record.title)", dirty: !note.isEmpty,
                   canSave: !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, saveTitle: "保存", onSave: submit) {
            Section {
                Picker("类型", selection: $kind) { Text("订正").tag("订正"); Text("复测").tag("复测") }.pickerStyle(.segmented).probe("correction-kind")
                LabeledContent("怎么订正的 / 复测结果") { TextEditor(text: $note).multilineTextAlignment(.leading).frame(minHeight: 80).probe("correction-note").accessibilityLabel("订正说明") }
            }
        }
    }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        let body: [String: Any] = ["child": store.childName, "day": store.view?.today ?? store.day, "category": "学习进展",
                                   "title": (kind + "：" + record.title).prefix(200).description, "subject": record.subject, "note": note,
                                   "related_record_id": record.id, "followup_kind": kind, "request_key": save.key]
        Task { await store.finish(await store.client.post("/api/record", body), save, done: "已记下\(kind)。") }
    }
}

/// 没有原作业的一道错题：孩子、科目和题目写明，照片是原件（现有错题保存在没有原作业时要求一张原图，原样保留）；
/// 不新建作业或反馈。保存走原有错题保存与同一提交标识的防重复。
struct WrongAddSheet: View {
    @ObservedObject var store: WorkspaceStore
    @StateObject var save = SaveState()
    @State var subject = ""
    @State var label = ""
    @State var text = ""
    @State var answer = ""
    @State var correction = ""
    @State var photos: [URL] = []
    @State var uploaded: [String: String] = [:]
    @State var picking = false

    var body: some View {
        SheetFrame(store: store, save: save, title: "记一道错题", context: "\(store.childName) · 没有原作业（不会新建作业或反馈）",
                   dirty: !(subject + label + text + answer + correction).isEmpty || !photos.isEmpty,
                   canSave: !label.trimmingCharacters(in: .whitespaces).isEmpty && !photos.isEmpty, saveTitle: "保存错题", onSave: submit) {
            Section {
                TextField("科目（可不填）", text: $subject).probe("wrong-add-subject")
                TextField("哪一题（必填）", text: $label).probe("wrong-add-label")
                TextField("题面（可不填）", text: $text).probe("wrong-add-text")
                TextField("孩子原答（可不填）", text: $answer).probe("wrong-add-answer")
                TextField("订正 / 正确做法（可不填）", text: $correction).probe("wrong-add-correction")
            }
            Section("这道题的照片（必选，原图原样保留）") {
                if photos.isEmpty { Text("没有原作业时，需要一张这道题的照片作原件。").font(.caption).foregroundStyle(Palette.ink2) }
                ForEach(photos, id: \.self) { url in Text(url.lastPathComponent).lineLimit(1).truncationMode(.middle).probe("wrong-add-photo-name", text: url.lastPathComponent) }
                Button(photos.isEmpty ? "选择照片…" : "换一张照片…") { pick() }.probe("wrong-add-photo")
            }
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.image], allowsMultipleSelection: false) { picked($0) }
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
            guard let url = photos.first else { save.busy = false; return }
            var id = uploaded[url.path] ?? ""
            if id.isEmpty {
                let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
                guard let data = try? Data(contentsOf: url) else { save.busy = false; save.message = "读不到所选照片，未保存；输入已保留。"; return }
                switch await store.client.upload(data, name: url.lastPathComponent) {
                case .saved(let reply):
                    guard let got = (reply["attachment"] as? [String: Any])?["id"] as? String else { save.busy = false; save.message = "照片没有保存成功，未保存错题；可以重试。"; return }
                    uploaded[url.path] = got; id = got
                case let other: await store.finish(other, save, done: ""); return
                }
            }
            let today = store.view?.today ?? store.day
            let day = store.day.isEmpty || store.day > today ? today : store.day
            let body: [String: Any] = ["child": store.childName, "day": day, "subject": subject.trimmingCharacters(in: .whitespaces), "request_key": save.key,
                                       "items": [["attachment": id, "label": label, "text": text, "answer": answer, "correction": correction]]]
            await store.finish(await store.client.post("/api/wrong/save", body), save, done: "错题已记进错题本。")
        }
    }
}

struct OralSheet: View {
    @ObservedObject var store: WorkspaceStore
    @StateObject var save = SaveState()
    @State var subject = ""
    @State var what = ""
    @State var tomorrow = false
    @State var handback = "unknown"
    @State var handbackDay = Date()
    @State var version: Int?

    var body: some View {
        SheetFrame(store: store, save: save, title: "补录口头作业", context: "\(store.childName) · 来源：孩子口头转述",
                   dirty: !subject.isEmpty || !what.isEmpty, canSave: !subject.trimmingCharacters(in: .whitespaces).isEmpty && !what.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                   saveTitle: "保存补录", onSave: submit) {
            Section {
                // 两个都是系统文本框，点哪个就在哪个里输入；不再另设焦点绑定（它曾把“要做什么”的输入拉回科目框）。
                TextField("科目（必填）", text: $subject).probe("oral-subject")
                TextField("要做什么（必填）", text: $what, axis: .vertical).lineLimit(3...6).multilineTextAlignment(.leading)
                    .accessibilityLabel("要做什么").probe("oral-what")
                Picker("做的日子", selection: $tomorrow) { Text("正在看的这天").tag(false); Text("后一天").tag(true) }.probe("oral-day")
                Picker("老师要求交回", selection: $handback) { Text("还不知道").tag("unknown"); Text("指定日期").tag("day") }.probe("oral-handback")
                if handback == "day" { DatePicker("交回日", selection: $handbackDay, displayedComponents: .date) }
            }
        }
    }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        let base = WorkspaceStore.date(store.day) ?? Date()
        let day = WorkspaceStore.text(tomorrow ? Calendar(identifier: .gregorian).date(byAdding: .day, value: 1, to: base) ?? base : base)
        let words = what.trimmingCharacters(in: .whitespacesAndNewlines)
        let title = String(words.split(separator: "\n").first ?? Substring(words)).prefix(80).description
        Task {
            do {
                // 重试沿用第一次读到的版本：同一提交标识、同一内容，服务端才认作同一次补录。
                var version = self.version ?? -1
                if version < 0 { version = try await store.client.studyVersion(child: store.childID, day: day) }
                self.version = version
                let report: [String: Any] = ["text": words, "explanation": "", "excerpt": "", "goal": "", "attachments": [String](),
                                             "complete_on": "", "handback_on": handback == "day" ? WorkspaceStore.text(handbackDay) : ""]
                let body: [String: Any] = ["child_id": store.childID, "day": day, "request_key": save.key, "version": version, "title": title,
                                           "subject": subject.trimmingCharacters(in: .whitespaces), "planned_minutes": NSNull(), "report": report]
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

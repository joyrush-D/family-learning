// 一起成长 Mac 原生每日工作台（SwiftUI，挂在原 AppKit 窗口里）：一次一个孩子、按科目平铺的当天清单 + 所选事项详情。
// 只读服务端已准备好的结果，打开不触发采集或模型；写入经原接口与原守卫。原件等富文档、照片检查与其他旧功能经次级网页入口。
import AppKit
import SwiftUI
import UniformTypeIdentifiers

enum Palette {
    static let paper = Color(red: 0xFB / 255, green: 0xF6 / 255, blue: 0xEA / 255)
    static let card = Color(red: 0xFF / 255, green: 0xFD / 255, blue: 0xF7 / 255)
    static let desk = Color(red: 0xEA / 255, green: 0xE0 / 255, blue: 0xCA / 255)
    static let ink = Color(red: 0x3B / 255, green: 0x33 / 255, blue: 0x26 / 255)
    static let ink2 = Color(red: 0x66 / 255, green: 0x5A / 255, blue: 0x48 / 255)
    static let leaf = Color(red: 0xA8 / 255, green: 0xD9 / 255, blue: 0x78 / 255)
    static let leafInk = Color(red: 0x1F / 255, green: 0x4A / 255, blue: 0x1C / 255)
    static let wood = Color(red: 0xF1 / 255, green: 0xE2 / 255, blue: 0xCC / 255)
    static let woodInk = Color(red: 0x6B / 255, green: 0x45 / 255, blue: 0x20 / 255)
    static let coral = Color(red: 0xFD / 255, green: 0xE6 / 255, blue: 0xDD / 255)
    static let coralInk = Color(red: 0xA1 / 255, green: 0x3F / 255, blue: 0x2A / 255)
    static let rounded = Font.system(.body, design: .rounded)
}

enum ListMode: String, CaseIterable, Identifiable { case today = "当天", done = "已办", wrong = "错题订正"; var id: String { rawValue } }

enum SheetKind: Identifiable {
    case feedback(DayItem), oral, wrong(DayItem, SavedRecord), correction(SavedRecord)
    var id: String {
        switch self {
        case .feedback(let i): return "feedback-" + i.id
        case .oral: return "oral"
        case .wrong(let i, let r): return "wrong-\(i.id)-\(r.id)"
        case .correction(let r): return "correction-\(r.id)"
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
    @Published var mode: ListMode = .today
    @Published var selection: String?
    @Published var sheet: SheetKind?
    @Published var materials: [String: MaterialState] = [:]
    @Published var notice = ""
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
    var groups: [ItemGroup] { mode == .done ? (current?.closed ?? []) : (current?.groups ?? []) }
    var wrongGroups: [WrongGroup] { current?.wrong ?? [] }
    var allItems: [DayItem] { (current?.groups ?? []).flatMap(\.items) + (current?.closed ?? []).flatMap(\.items) }
    var selected: DayItem? { allItems.first { $0.id == selection } }

    func load(keepSelection: Bool = true) async {
        sequence += 1
        let mine = sequence, child = childID, wanted = day
        loading = true
        do {
            let fresh = try await client.day(child: child, day: wanted)
            guard mine == sequence else { return }
            view = fresh; childID = fresh.child_id; day = fresh.day; error = ""; loginRequired = false
            if !keepSelection || !allItems.contains(where: { $0.id == selection }) { selection = nil }
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
        selection = id
        if let item = selected, !item.task_id.isEmpty, materials[item.task_id] == nil { Task { await loadMaterials(item) } }
    }

    /// 切换孩子/日期：弹出层有未保存内容时默认留下；不带着上一个孩子的提示。
    func change(child: String? = nil, day newDay: String? = nil) {
        guard sheet == nil || !sheetDirty || confirmDiscard("离开当前填写") else { return }
        sheet = nil; sheetDirty = false; notice = ""
        if let child, child != childID { childID = child; selection = nil; materials = [:] }
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
        case .done: return "已办 \(v.counts["closed"] ?? 0) 项"
        case .wrong:
            let all = v.wrong.flatMap(\.items)
            return "错题 \(all.count) 道 · 待订正 \(all.filter { ($0.state ?? "待订正") == "待订正" }.count)"
        case .today:
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
}

// MARK: 主工作台：顶栏（孩子 / 日期 / 补录 / 网页版）是窗口内容里的真实按钮；清单 + 所选事项详情。

struct WorkspaceView: View {
    @ObservedObject var store: WorkspaceStore

    var body: some View {
        VStack(spacing: 0) {
            HeaderBar(store: store)
            Divider()
            NavigationSplitView {
                SubjectList(store: store)
                    .navigationSplitViewColumnWidth(min: 320, ideal: 400, max: 520)
            } detail: {
                Inspector(store: store)
            }
        }
        .background(Palette.paper)
        .environment(\.colorScheme, .light)
        .sheet(item: $store.sheet) { kind in SheetHost(store: store, kind: kind) }
    }
}

struct HeaderBar: View {
    @ObservedObject var store: WorkspaceStore

    var body: some View {
        HStack(spacing: 10) {
            Label("一起成长", systemImage: "leaf").font(Palette.rounded.weight(.bold)).foregroundStyle(Palette.leafInk)
            HStack(spacing: 2) {
                ForEach(Array((store.view?.children ?? []).enumerated()), id: \.element.id) { index, c in
                    let on = c.id == store.childID
                    Button { store.change(child: c.id) } label: {
                        Text(c.name).font(Palette.rounded.weight(.semibold)).frame(minWidth: 64, minHeight: 32).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).padding(.horizontal, 6)
                    .foregroundStyle(on ? Palette.leafInk : Palette.woodInk)
                    .background(RoundedRectangle(cornerRadius: 10).fill(on ? Palette.card : Color.clear))
                    .accessibilityAddTraits(on ? .isSelected : [])
                    .help("只看\(c.name)（⌘\(index + 1)）")
                    .probe("child-" + c.id, text: c.name + (on ? " 当前" : ""))
                }
            }
            .padding(3).background(RoundedRectangle(cornerRadius: 12).fill(Palette.wood))
            Spacer(minLength: 8)
            Button { store.shift(-1) } label: { Image(systemName: "chevron.left").frame(width: 32, height: 32).contentShape(Rectangle()) }
                .buttonStyle(.plain).accessibilityLabel("前一天").help("前一天 ⌘[").probe("day-prev")
            VStack(spacing: 1) {
                Text(store.dayTitle).font(Palette.rounded.weight(.bold)).foregroundStyle(Palette.ink)
                Text(store.daySub).font(.caption).foregroundStyle(Palette.ink2)
            }
            .frame(minWidth: 150).accessibilityElement(children: .combine)
            .probe("day-title", text: store.day + " " + store.daySub)
            Button { store.shift(1) } label: { Image(systemName: "chevron.right").frame(width: 32, height: 32).contentShape(Rectangle()) }
                .buttonStyle(.plain).accessibilityLabel("后一天").help("后一天 ⌘]").probe("day-next")
            Button("回到今天") { store.change(day: store.view?.today ?? "") }
                .disabled(store.view == nil || store.day == store.view?.today).help("回到今天 ⌘T").probe("day-today")
            Spacer(minLength: 8)
            Button { store.sheetDirty = false; store.sheet = .oral } label: { Label("补录口头作业", systemImage: "plus") }
                .buttonStyle(.borderedProminent).tint(Palette.leaf).foregroundStyle(Palette.leafInk)
                .disabled(store.current == nil).help("补录孩子口头转述的作业 ⌘N").probe("oral-new")
            Button { store.openWebTools("", "") } label: { Label("网页版工具", systemImage: "square.grid.2x2") }
                .help("日历、学校消息、打印、设置等其他功能 ⌘E").probe("web-tools")
        }
        .padding(.horizontal, 16).padding(.vertical, 8)
        .background(Palette.desk.opacity(0.55))
    }
}

struct WoodTag: View {
    let text: String
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(Palette.woodInk.opacity(0.35)).frame(width: 6, height: 6)
            Text(text).font(Palette.rounded.weight(.bold)).foregroundStyle(Palette.woodInk)
        }
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 8).fill(Palette.wood))
        .accessibilityElement(children: .combine)
    }
}

struct Badge: View {
    let text: String
    var tone: Color = Palette.wood
    var ink: Color = Palette.woodInk
    var body: some View {
        Text(text).font(.callout.weight(.semibold)).foregroundStyle(ink)
            .padding(.horizontal, 8).padding(.vertical, 2)
            .background(Capsule().fill(tone))
    }
}

func factTone(_ f: DayFact) -> (Color, Color) {
    f.state == "next_morning" || f.state == "overdue" ? (Palette.coral, Palette.coralInk) : f.known ? (Palette.wood, Palette.woodInk) : (Palette.paper, Palette.ink2)
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
            Picker("清单", selection: $store.mode) { ForEach(ListMode.allCases) { Text(label($0)).tag($0) } }
                .pickerStyle(.segmented).labelsHidden().padding(.horizontal, 12).padding(.top, 10).probe("list-mode")
            VStack(alignment: .leading, spacing: 2) {
                Text(store.mode == .today ? "当天清单" : store.mode.rawValue).font(.system(.title2, design: .rounded).weight(.bold)).foregroundStyle(Palette.ink)
                Text(store.summary).font(.callout).foregroundStyle(Palette.ink2).probe("list-summary", text: store.summary)
            }.padding(.horizontal, 14).padding(.vertical, 8)
            if store.loginRequired {
                VStack(alignment: .leading, spacing: 8) {
                    Text("需要先登录家庭账号。点下面的按钮会打开登录窗口，登录成功后窗口自动关闭、清单随即更新；填写中的内容不会丢。").foregroundStyle(Palette.coralInk)
                    Button("登录家庭账号") { store.openLogin() }.buttonStyle(.borderedProminent).tint(Palette.leaf).foregroundStyle(Palette.leafInk).probe("login-open")
                }.padding(12).frame(maxWidth: .infinity, alignment: .leading).background(Palette.coral).probe("login-needed", text: "需要登录")
            } else if !store.error.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(store.error).foregroundStyle(Palette.coralInk).probe("load-error", text: store.error)
                    Button("重试") { Task { await store.load() } }.probe("load-retry")
                }.padding(12).frame(maxWidth: .infinity, alignment: .leading).background(Palette.coral)
            }
            if let text = store.current?.source_error, !text.isEmpty {
                Text(text).font(.callout).foregroundStyle(Palette.coralInk).padding(10)
            }
            if store.mode == .wrong { WrongList(store: store) } else { itemList }
        }
        .background(Palette.paper)
    }

    func label(_ mode: ListMode) -> String {
        guard let v = store.current else { return mode.rawValue }
        switch mode {
        case .today: return "当天 \(v.counts["open"] ?? 0)"
        case .done: return "已办 \(v.counts["closed"] ?? 0)"
        case .wrong: return "错题 \(v.wrong.flatMap(\.items).count)"
        }
    }

    var itemList: some View {
        List(selection: Binding(get: { store.selection }, set: { store.select($0) })) {
            ForEach(store.groups, id: \.subject) { group in
                Section {
                    ForEach(group.items) { item in ItemRow(item: item, selected: store.selection == item.id).tag(item.id).probe("row-" + item.id, text: item.title) }
                } header: {
                    HStack { WoodTag(text: group.subject); Text("\(group.items.count) 项").foregroundStyle(Palette.ink2) }
                        .probe("subject-" + group.subject)
                }
            }
            if store.groups.isEmpty && store.current != nil {
                Text(store.mode == .done ? "这一天没有已办的事项。" : "这一天没有已整理的未完成事项；没有反馈不等于没做。")
                    .foregroundStyle(Palette.ink2).probe("list-empty")
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .probe("subject-list")
    }
}

struct ItemRow: View {
    let item: DayItem
    var selected = false
    /// 选中时用系统层级色（随系统选中高亮自动变浅色），没选中时用工作台配色。
    func ink(_ color: Color, _ level: HierarchicalShapeStyle) -> AnyShapeStyle { selected ? AnyShapeStyle(level) : AnyShapeStyle(color) }
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: item.closed ? "leaf.fill" : "circle").foregroundStyle(ink(item.closed ? Palette.leafInk : Palette.ink2, .secondary))
                .font(.title3).padding(.top, 2).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(item.title).font(Palette.rounded.weight(.semibold)).foregroundStyle(ink(Palette.ink, .primary)).lineLimit(2)
                if let first = item.lines.first { Text(item.lines.joined(separator: "；")).font(.callout).foregroundStyle(ink(Palette.ink2, .secondary)).lineLimit(2).help(first) }
                else { Text("完成标准未提供，待补充").font(.callout).foregroundStyle(ink(Palette.coralInk, .primary)) }
                HStack(spacing: 6) {
                    if !item.whenLabel.isEmpty { Badge(text: item.whenLabel, tone: Palette.paper, ink: Palette.ink2) }
                    ForEach(item.facts.filter { $0.role == "due" || $0.role == "complete" }, id: \.self) { f in
                        let (tone, ink) = factTone(f)
                        Badge(text: factWords(f), tone: tone, ink: ink)
                    }
                    if item.pending_review { Badge(text: "待核对", tone: Palette.coral, ink: Palette.coralInk) }
                }
                let meta = [item.source, item.progress.map(progressWords) ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
                if !meta.isEmpty { Text(meta).font(.caption).foregroundStyle(ink(Palette.ink2, .secondary)).lineLimit(1) }
            }
        }
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
    }
}

struct WrongList: View {
    @ObservedObject var store: WorkspaceStore
    var body: some View {
        List {
            ForEach(store.wrongGroups, id: \.subject) { group in
                Section {
                    ForEach(group.items) { r in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(r.title).font(Palette.rounded.weight(.semibold)).foregroundStyle(Palette.ink)
                                Text(r.day).font(.caption).foregroundStyle(Palette.ink2)
                            }
                            Spacer()
                            Badge(text: r.state ?? "待订正", tone: r.state == "待订正" ? Palette.coral : Palette.leaf.opacity(0.5),
                                  ink: r.state == "待订正" ? Palette.coralInk : Palette.leafInk)
                            Button("记订正") { store.sheet = .correction(r); store.sheetDirty = false }
                                .probe("wrong-correct-\(r.id)")
                        }
                        .probe("wrong-\(r.id)", text: r.title + " " + (r.state ?? ""))
                    }
                } header: { WoodTag(text: group.subject) }
            }
            if store.wrongGroups.isEmpty && store.current != nil { Text("还没有记下的错题。").foregroundStyle(Palette.ink2) }
        }
        .listStyle(.sidebar).scrollContentBackground(.hidden).probe("wrong-list")
    }
}

// MARK: 所选事项详情：出处 → 要做什么与完成标准 → 日期 → 资料与打印 → 反馈、错题与订正（同一份作业）。

struct Inspector: View {
    @ObservedObject var store: WorkspaceStore

    var body: some View {
        Group {
            if let item = store.selected { detail(item) }
            else {
                VStack(spacing: 10) {
                    Image(systemName: "leaf").font(.largeTitle).foregroundStyle(Palette.leafInk)
                    Text(store.current != nil ? "从左边选一项，查看要做什么、资料和反馈。" : store.loginRequired ? "登录后显示清单。"
                         : store.loading || store.error.isEmpty ? "正在读取清单…" : "还没读到所选孩子这一天的清单，可在左边重试。").foregroundStyle(Palette.ink2)
                }.frame(maxWidth: .infinity, maxHeight: .infinity).background(Palette.paper)
            }
        }
    }

    func section<Content: View>(_ title: String, _ symbol: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: symbol).font(Palette.rounded.weight(.bold)).foregroundStyle(Palette.ink)
            content()
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14).fill(Palette.card))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Palette.desk, lineWidth: 1))
    }

    func detail(_ item: DayItem) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 10) {
                    WoodTag(text: item.subject)
                    if !item.source.isEmpty { Label(item.source + " 发布", systemImage: "bubble.left").font(.callout).foregroundStyle(Palette.ink2).probe("detail-publisher", text: item.source) }
                    if !(item.publications ?? []).isEmpty || item.origin == "school" {
                        Button("看原消息") { store.openWebTools(item.webID, "original") }.help("在网页版打开同一项的原消息与原件").probe("original-message")
                    }
                    Spacer()
                    Text("\(store.childName) · \(item.origin_label)").font(.callout).foregroundStyle(Palette.ink2)
                }
                Text(item.title).font(.system(.title2, design: .rounded).weight(.bold)).foregroundStyle(Palette.ink)
                    .textSelection(.enabled).probe("detail-title", text: item.title)
                section("要做什么与完成标准", "checkmark") {
                    if item.lines.isEmpty { Text("完成标准未提供，待补充").foregroundStyle(Palette.coralInk).probe("detail-no-standard") }
                    ForEach(Array(item.lines.enumerated()), id: \.offset) { _, line in Text("· " + line).foregroundStyle(Palette.ink).textSelection(.enabled) }
                    if !item.complete_words.isEmpty { Text("完成要求：" + item.complete_words).foregroundStyle(Palette.ink2) }
                    if item.pending_review { Text("这条学校消息还在待核对，确认后才算正式事项；可在网页版学校信息中核对。").font(.callout).foregroundStyle(Palette.coralInk) }
                }
                section("日期", "calendar") {
                    if !item.whenLabel.isEmpty { Text("这一项\(item.whenLabel)，不算这一天要交的作业。").font(.callout).foregroundStyle(Palette.ink2).probe("detail-when", text: item.whenLabel) }
                    ForEach(item.facts, id: \.self) { f in
                        HStack(alignment: .firstTextBaseline) {
                            Text(f.label).foregroundStyle(Palette.ink2).frame(width: 96, alignment: .leading)
                            Text((f.today == true ? "今天 " : "") + f.value)
                                .foregroundStyle(!f.known ? Palette.ink2 : f.state == "next_morning" || f.state == "overdue" ? Palette.coralInk : Palette.ink)
                                .italic(!f.known)
                            if f.state == "next_morning" { Badge(text: "明天", tone: Palette.coral, ink: Palette.coralInk) }
                            if f.state == "overdue" { Badge(text: "已逾期", tone: Palette.coral, ink: Palette.coralInk) }
                        }.accessibilityElement(children: .combine).probe("fact-" + f.role, text: factWords(f))
                    }
                    Text("出处：" + item.origin_label + (item.origin == "oral" ? "（老师日期未录入就保持未知）" : "")).font(.callout).foregroundStyle(Palette.ink2)
                }
                if !item.task_id.isEmpty { materials(item) }
                feedback(item)
            }
            .padding(20).frame(maxWidth: 760, alignment: .leading)
        }
        .background(Palette.paper)
        .probe("inspector")
    }

    func materialTone(_ m: Material) -> (Color, Color) {
        switch m.state {
        case "ready": return (Palette.leaf.opacity(0.45), Palette.leafInk)
        case "unread", "error": return (Palette.coral, Palette.coralInk)
        default: return (Palette.wood, Palette.woodInk)
        }
    }

    func materials(_ item: DayItem) -> some View {
        let state = store.materials[item.task_id] ?? MaterialState()
        return section("资料与打印", "doc.text") {
            if !state.loaded { Text("正在读取资料…").foregroundStyle(Palette.ink2) }
            if !state.error.isEmpty {
                Text(state.error).foregroundStyle(Palette.coralInk)
                Button("重新读取资料") { Task { await store.loadMaterials(item) } }.probe("material-retry")
            }
            if state.loaded && state.files.isEmpty && state.error.isEmpty { Text("这一项没有已保存的原件。").foregroundStyle(Palette.ink2).probe("material-none") }
            ForEach(state.files) { m in
                let (tone, ink) = materialTone(m)
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Badge(text: m.stateLabel, tone: tone, ink: ink)
                        Text(m.name).foregroundStyle(Palette.ink).lineLimit(1)
                        Spacer()
                        Button("打开") { store.openDocument(store.client.url("/upload/" + m.id), m.name) }.probe("material-open-" + m.id)
                    }
                    Text(m.roleLabel).font(.caption).foregroundStyle(Palette.ink2)
                    if !m.summary.isEmpty { Text(m.summary).foregroundStyle(Palette.ink).lineLimit(3).textSelection(.enabled) }
                    if !m.unclear.isEmpty { Text("看不清：" + m.unclear.joined(separator: "；") + "。请看原件。").font(.callout).foregroundStyle(Palette.coralInk) }
                    if m.state != "ready", m.state != "saved", !m.explanation.isEmpty { Text(m.explanation).font(.callout).foregroundStyle(m.state == "pending" ? Palette.ink2 : Palette.coralInk) }
                }
                .padding(8)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(style: StrokeStyle(lineWidth: 1, dash: m.state == "unread" || m.state == "error" ? [4] : [])).foregroundStyle(m.state == "unread" || m.state == "error" ? Palette.coralInk : Palette.desk))
                .probe("material-" + m.id, text: m.stateLabel + " " + m.name + " " + m.summary)
            }
            if !state.gap.isEmpty {
                Text("尚未读清：" + state.gap).foregroundStyle(Palette.coralInk).padding(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(style: StrokeStyle(lineWidth: 1, dash: [4])).foregroundStyle(Palette.coralInk))
                    .probe("material-gap")
            }
            if item.category == "homework" {
                HStack {
                    Button { store.openWebTools(item.task_id, "print-original") } label: { Label("打印原卷", systemImage: "printer") }.probe("print-original")
                    Button { store.openWebTools(item.task_id, "print-reference") } label: { Label("打印家长参考", systemImage: "printer") }.probe("print-reference")
                }
                Text("在网页版这份作业的打印确认里打开：先核对依据和所选资料，确认后才排队打印。").font(.caption).foregroundStyle(Palette.ink2)
            }
        }
    }

    func feedback(_ item: DayItem) -> some View {
        section("反馈、错题与订正", "pencil") {
            if item.task_id.isEmpty { Text("这一项还不是正式事项，确认后才能记反馈。").foregroundStyle(Palette.ink2) }
            if let p = item.progress, !progressWords(p).isEmpty {
                HStack {
                    Text("已有进展：" + progressWords(p)).font(.callout).foregroundStyle(Palette.ink2).probe("detail-progress", text: progressWords(p))
                    Spacer()
                    if p.wrong + p.clues + p.retries + p.history > 0 {
                        Button("看错题诊断与再试") { store.openWebTools(item.task_id, "history") }.probe("history-web")
                    }
                }
            }
            ForEach(item.records) { r in
                VStack(alignment: .leading, spacing: 4) {
                    HStack { Badge(text: r.followup_kind.isEmpty ? "反馈" : r.followup_kind); Text(r.created.prefix(16).replacingOccurrences(of: "T", with: " ")).font(.caption).foregroundStyle(Palette.ink2)
                        if !r.attachments.isEmpty { Label("\(r.attachments.count)", systemImage: "camera").font(.caption).foregroundStyle(Palette.ink2) } }
                    if let v = r.retry { RetryLines(v: v, note: r.note).probe("retry-\(r.id)", text: v.lines.map { $0.joined(separator: "：") }.joined(separator: "\n") + "\n下一步 " + v.next) }
                    else { Text(r.note.isEmpty ? r.title : r.note).foregroundStyle(Palette.ink).textSelection(.enabled) }
                    if r.note_truncated && (r.retry?.show_note ?? true) { Text("（较长，完整内容在网页版记录中）").font(.caption).foregroundStyle(Palette.ink2) }
                    Button("记一道错题") { store.sheet = .wrong(item, r); store.sheetDirty = false }.probe("wrong-new-\(r.id)")
                }.padding(10).background(RoundedRectangle(cornerRadius: 10).fill(Palette.paper)).probe("record-\(r.id)", text: r.note)
            }
            ForEach(item.wrong) { w in
                HStack {
                    Text(w.title).foregroundStyle(Palette.ink)
                    Spacer()
                    Badge(text: w.state ?? "待订正", tone: w.state == "待订正" ? Palette.coral : Palette.leaf.opacity(0.5), ink: w.state == "待订正" ? Palette.coralInk : Palette.leafInk)
                    Button("记订正") { store.sheet = .correction(w); store.sheetDirty = false }.probe("wrong-correct-\(w.id)")
                }.accessibilityElement(children: .contain).probe("detail-wrong-\(w.id)", text: w.title + " " + (w.state ?? ""))
            }
            if !item.task_id.isEmpty {
                HStack {
                    Button { store.sheet = .feedback(item); store.sheetDirty = false } label: { Label("写文字反馈", systemImage: "square.and.pencil") }
                        .buttonStyle(.borderedProminent).tint(Palette.leaf).foregroundStyle(Palette.leafInk).probe("feedback-new")
                    if item.category == "homework" {
                        Button { store.openWebTools(item.task_id, "check") } label: { Label("交作答照片检查", systemImage: "camera") }.probe("check-web")
                    }
                }
                Text("文字反馈在这里写，照片可加可不加，不调用 AI，不自动标已办或判错；照片检查在网页版同一份作业里进行。").font(.caption).foregroundStyle(Palette.ink2)
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
        case .saved:
            save.login = false
            sheetDirty = false; sheet = nil; notice = done
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
                    TextEditor(text: $note).multilineTextAlignment(.leading).frame(minHeight: 120).probe("feedback-note").accessibilityLabel("反馈内容")
                }
            }
            Section("照片（可不加）") {
                ForEach(photos, id: \.self) { Text($0.lastPathComponent) }
                Button("选择照片或 PDF…") { picking = true }.probe("feedback-photo")
            }
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.image, .pdf], allowsMultipleSelection: true) { result in
            if case .success(let urls) = result { photos.append(contentsOf: urls.filter { !photos.contains($0) }) }
        }
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

    var body: some View {
        SheetFrame(store: store, save: save, title: "记一道错题", context: "\(store.childName) · \(item.subject) · 来自 \(record.created.prefix(16)) 的反馈",
                   dirty: !label.isEmpty || !reason.isEmpty, canSave: !label.trimmingCharacters(in: .whitespaces).isEmpty, saveTitle: "保存错题", onSave: submit) {
            Section {
                TextField("哪一题（必填）", text: $label).probe("wrong-label")
                LabeledContent("原因（可不填）") { TextEditor(text: $reason).multilineTextAlignment(.leading).frame(minHeight: 70).probe("wrong-reason").accessibilityLabel("原因") }
            }
        }
    }

    func submit() {
        save.busy = true; save.message = ""; save.conflict = false; save.login = false
        let subject = [WorkspaceStore.general, WorkspaceStore.unknown].contains(item.subject) ? "" : item.subject
        let body: [String: Any] = ["child": store.childName, "day": store.view?.today ?? store.day, "subject": subject, "request_key": save.key,
                                   "items": [["label": label, "note": reason]], "task_id": item.task_id,
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

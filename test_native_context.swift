// 原生工作台的孩子/日期归属：无界面状态检查，由 test_native_context.py 编译真实的 WorkspaceStore/WorkspaceClient 后运行。
// 不含 Sources/main.swift，不创建 NSApplication、窗口或浏览器；只连同一进程测试起的本机虚构后台，只有虚构孩子与事项。
// 这里只证明工作台状态（显示、可选、计数、名字、能否写入），不能代替可见界面验收。
import Foundation

@main struct NativeContextStateCheck {
    @MainActor static func main() async {
        let base = CommandLine.arguments[1], today = "2026-11-04", next = "2026-11-05"
        let store = WorkspaceStore(client: WorkspaceClient(origin: ServiceOrigin.parse(base)!, ephemeral: true))
        var discard = false
        store.confirmDiscard = { _ in discard }
        var failures: [String] = []
        var seen: [String: Any] = [:]
        func expect(_ ok: Bool, _ what: String) { if !ok { failures.append(what) } }
        func ids() -> [String] { store.allItems.map(\.id) }
        func shown() -> [String] { store.groups.flatMap(\.items).map(\.id) }
        func backend(_ query: String) async -> [String: Int] {
            guard let url = URL(string: base + "/control?" + query), let (data, _) = try? await URLSession.shared.data(from: url) else { return [:] }
            return (try? JSONSerialization.jsonObject(with: data)) as? [String: Int] ?? [:]
        }
        // 等这次切换触发的读取结束（工作台读完都会调 onLoaded），不靠固定等待。
        func settle(_ action: () -> Void) async {
            await withCheckedContinuation { (done: CheckedContinuation<Void, Never>) in
                store.onLoaded = { store.onLoaded = {}; done.resume() }
                action()
            }
        }
        func wrongSummary() -> String { store.mode = .wrong; defer { store.mode = .calendar }; return store.summary }
        func snapshot(_ name: String) {
            let entry: [String: Any] = ["requested_child": store.childID, "requested_day": store.day, "child_name": store.childName,
                                        "shown": shown(), "selectable": ids(), "selected": store.selected?.id ?? "", "summary": store.summary,
                                        "wrong_summary": wrongSummary(), "error": store.error, "cached_child": store.view?.child_id ?? "",
                                        "cached_day": store.view?.day ?? "", "known_children": store.view?.children.map(\.id) ?? [],
                                        "current": store.current.map { $0.child_id + " " + $0.day } ?? "", "day_title": store.dayTitle]
            seen[name] = entry
        }

        _ = await backend("fail=0")
        await store.load()
        store.select("FICTION-A1")
        snapshot("loaded")
        expect(store.childID == "child-1" && store.day == today && store.childName == "示例甲" && shown() == ["FICTION-A1"], "首次读到虚构甲当天的清单")
        expect(store.selected?.id == "FICTION-A1", "首次可以选中甲的事项")
        expect(store.current?.school_pending == 1, "甲当天读到 1 条尚未整理的学校消息（与网页同一规则）")
        expect(store.current?.school_read_gaps == [SchoolReadGap(name: "虚构班级群", status: "最近读取未成功")] && store.current?.school_unknown == nil,
               "甲当天读到自己来源的读取缺口，与待整理分开")

        // 1 同一孩子同一天重读失败：已正确归属的清单、选中项和编辑都保留，不因任何一次失败就清空。
        _ = await backend("fail=1")
        await store.load()
        snapshot("same_context_failed")
        expect(!store.error.isEmpty, "同一天重读失败要说明")
        expect(store.childID == "child-1" && store.childName == "示例甲" && shown() == ["FICTION-A1"] && store.selected?.id == "FICTION-A1",
               "同一孩子同一天重读失败保留原清单与选中项")
        expect(store.current != nil, "同一天重读失败时仍可在原孩子原事项下补录、反馈和订正")

        // 2 弹出层有未保存内容时拒绝切换：原孩子、原日期、原填写（同一弹出层）都留着，也不发起读取。
        let readsBefore = await backend("")["day_reads"] ?? -1
        if let item = store.selected {
            for kind in [SheetKind.oral, SheetKind.feedback(item)] {
                store.sheet = kind; store.sheetDirty = true; discard = false
                store.change(child: "child-2"); store.change(day: next); store.shift(1)
                expect(store.childID == "child-1" && store.day == today && store.sheet?.id == kind.id && store.sheetDirty && !store.loading,
                       "有未保存的 \(kind.id) 时拒绝切换，保留原孩子、日期和填写")
                expect(store.childName == "示例甲" && store.selected?.id == item.id, "拒绝切换后仍是原孩子的原事项")
            }
        } else { failures.append("没有可用于拒绝切换检查的选中项") }
        let readsAfter = await backend("")["day_reads"] ?? -2
        expect(readsBefore == readsAfter, "拒绝切换不发起读取")
        store.sheet = nil; store.sheetDirty = false

        // 3 换孩子读失败：甲的清单、错题、计数和名字都不能出现在乙下面，甲的事项也不能被选中。
        await settle { store.change(child: "child-2") }
        store.select("FICTION-A1")
        snapshot("child_change_failed")
        expect(!store.error.isEmpty && store.childID == "child-2", "换到乙读失败要说明，且仍是选中乙")
        expect(store.childName != "示例甲", "换到乙后不能用甲的名字（反馈、补录的抬头与提交）")
        expect(shown().isEmpty && !ids().contains("FICTION-A1") && store.selected == nil, "换到乙读失败后甲的事项不显示，也不能选中")
        expect(!store.summary.contains("共"), "换到乙读失败后不显示甲的计数")
        expect(!wrongSummary().contains("错题 1"), "换到乙读失败后不显示甲的错题")
        expect(store.view?.children.map(\.id) == ["child-1", "child-2"], "已知的孩子保留，可以切回或重试")
        expect(store.current == nil && store.wrongGroups.isEmpty, "换到乙读失败后没有可写入的当前一天：补录、反馈、错题和订正都不能接着用甲的内容")
        expect(store.view?.child_id == "child-1", "甲的读取结果只留作缓存，不靠清空记录掩盖")

        // 4 仍读不到时切回原来的甲：显示已正确归属甲的内容。
        await settle { store.change(child: "child-1") }
        snapshot("returned_while_failing")
        expect(store.childID == "child-1" && store.childName == "示例甲" && shown() == ["FICTION-A1"], "切回甲时显示已正确归属甲的内容")
        expect(store.current?.child_id == "child-1" && store.dayTitle == WorkspaceStore.spoken(today) && store.daySub == "今天", "切回甲时顶栏和可写入的当前一天都是甲当天")

        // 5 换日期读失败：前一天的事项、计数不能挂在后一天下面。
        store.select("FICTION-A1")
        await settle { store.change(day: next) }
        snapshot("day_change_failed")
        expect(!store.error.isEmpty && store.day == next && store.childID == "child-1", "换到后一天读失败要说明，且仍是选中后一天")
        expect(shown().isEmpty && !ids().contains("FICTION-A1") && store.selected == nil, "后一天读失败后前一天的事项不显示，也不能选中")
        expect(!store.summary.contains("共"), "后一天读失败后不显示前一天的计数")
        expect(store.current == nil && store.dayTitle == WorkspaceStore.spoken(next) && store.daySub.hasPrefix("以后的一天"), "后一天读失败时顶栏是后一天，且没有可写入的当前一天")

        // 6 恢复后重试、换孩子、回到原来那一天：每次都正是所选孩子、所选日期的内容，不重复、不混入。
        _ = await backend("fail=0")
        await store.load()
        snapshot("day_retry")
        expect(store.error.isEmpty && store.day == next && store.childName == "示例甲" && ids() == ["FICTION-A2"], "重试读到甲后一天的内容且不重复")
        await settle { store.change(child: "child-2") }
        snapshot("child_two")
        expect(store.childName == "示例乙" && ids() == ["FICTION-B3"], "换到乙读到乙后一天的内容")
        await settle { store.shift(-1) }
        snapshot("child_two_today")
        expect(store.day == today && store.childName == "示例乙" && ids() == ["FICTION-B1", "FICTION-B2"], "回到当天读到乙当天的内容，没有甲的事项")
        expect((store.current?.school_pending ?? 0) == 0 && (store.current?.school_read_gaps ?? []).isEmpty, "乙没有甲的待整理或读取缺口提示")
        expect(wrongSummary().hasPrefix("错题 0"), "乙的错题只算乙的")
        // 7 通知类事项（todo）读自己的原件：同一资料契约（页组范围、缺执行资源与看不清分开），不报作业权限错误。
        if let notice = store.allItems.first(where: { $0.id == "FICTION-B2" }) {
            await store.loadMaterials(notice)
            let m = store.materials[notice.task_id] ?? MaterialState()
            seen["notice_materials"] = ["category": notice.category, "loaded": m.loaded, "error": m.error,
                                        "files": m.files.map { [$0.id, $0.state, $0.stateLabel, $0.scope, $0.missing.joined(separator: "；")] }]
            expect(notice.category == "todo" && m.loaded && m.error.isEmpty && m.files.map(\.id) == ["u-b2-pdf"], "通知类事项读到自己的原件，不报作业权限错误")
            expect(m.files.first?.scope == "共2页，已整理第1–2页" && m.files.first?.missing == ["虚构听力音频未随附"] && m.files.first?.unclear.isEmpty == true
                   && m.files.first?.stateLabel == "已整理全部2页", "PDF页组范围、缺执行资源与看不清分开读到")
        } else { failures.append("乙当天没有通知类事项") }
        // 8 口头补录的提交内容：科目可后补；老师要求的完成日、交回日分开，未知留空；做的日子不当作老师日期。
        let oral = WorkspaceStore.oralBody(child: "child-2", day: today, key: "synthetic-oral-key-0001", version: 3, subject: " ", what: "  读课文两遍\n家长签字  ",
                                           completeOn: next, handbackOn: "")
        let oralReport = oral["report"] as? [String: Any] ?? [:]
        seen["oral_body"] = ["title": oral["title"] as? String ?? "", "subject": oral["subject"] as? String ?? "?", "complete_on": oralReport["complete_on"] as? String ?? "?",
                             "handback_on": oralReport["handback_on"] as? String ?? "?", "day": oral["day"] as? String ?? ""]
        expect(oral["subject"] as? String == "" && oral["title"] as? String == "读课文两遍" && oralReport["text"] as? String == "读课文两遍\n家长签字",
               "科目留空也能补录，标题取要做什么的第一行")
        expect(oralReport["complete_on"] as? String == next && oralReport["handback_on"] as? String == "" && oral["day"] as? String == today
               && oral["request_key"] as? String == "synthetic-oral-key-0001" && oral["version"] as? Int == 3, "完成日与交回日分开，未知留空，做的日子不当老师日期")
        // 9 补录/反馈共用的照片上传：已传的沿用原编号不重传；回执丢失或失败只停在那一张、已传编号留着；读不到文件不发送。全在内存里，不连后台。
        let a = URL(fileURLWithPath: "/synthetic/oral-a.png"), b = URL(fileURLWithPath: "/synthetic/oral-b.png"), gone = URL(fileURLWithPath: "/synthetic/gone.png")
        var sends: [String] = [], sentKeys: [String] = [], replies: [PostOutcome] = [.saved(["attachment": ["id": String(repeating: "a", count: 32)]]), .unknown("虚构回执丢失")]
        let fake: (Data, String, String) async -> PostOutcome = { _, name, key in
            sends.append(name); sentKeys.append(key)
            return replies.isEmpty ? .saved(["attachment": ["id": String(repeating: "b", count: 32)]]) : replies.removeFirst()
        }
        let first = await WorkspaceStore.uploadPhotos([a, b], cached: [:], keys: [:], read: { _ in Data([1]) }, send: fake)
        let stoppedOnLostReceipt: Bool = { if case .outcome(.unknown)? = first.stop { return true }; return false }()
        expect(stoppedOnLostReceipt && first.cached == [a.path: String(repeating: "a", count: 32)] && sends == ["oral-a.png", "oral-b.png"], "回执丢失停在那一张，已传的编号留着")
        expect(first.keys.count == 2 && first.keys[a.path] != first.keys[b.path] && sentKeys == [first.keys[a.path] ?? "", first.keys[b.path] ?? ""],
               "每张照片各有自己的上传标识，回执丢失的那张标识也留着")
        let second = await WorkspaceStore.uploadPhotos([a, b], cached: first.cached, keys: first.keys, read: { _ in Data([1]) }, send: fake)
        expect(sentKeys.count == 3 && sentKeys[2] == sentKeys[1], "回执丢失后重传沿用同一上传标识：服务端按标识读回原件，不另存一份")
        expect(second.stop == nil && second.ids == [String(repeating: "a", count: 32), String(repeating: "b", count: 32)] && sends == ["oral-a.png", "oral-b.png", "oral-b.png"],
               "重试只补没传成功的那张，已传的不重传")
        let third = await WorkspaceStore.uploadPhotos([a, b], cached: second.cached, keys: second.keys, read: { _ in Data([1]) }, send: fake)
        expect(third.stop == nil && third.ids == second.ids && sends.count == 3, "保存回执丢失后再按保存：照片一张都不重传，编号与内容不变")
        let unreadable = await WorkspaceStore.uploadPhotos([gone], cached: [:], keys: [:], read: { _ in nil }, send: fake)
        let stoppedUnreadable: Bool = { if case .unreadable? = unreadable.stop { return true }; return false }()
        expect(stoppedUnreadable && unreadable.ids.isEmpty && unreadable.keys.isEmpty && sends.count == 3, "读不到所选文件不发送、不保存")
        let other = await WorkspaceStore.uploadPhotos([gone], cached: [:], keys: [:], read: { _ in Data([1]) }, send: fake)
        expect(other.keys[gone.path] != nil && other.keys[gone.path] != first.keys[a.path] && other.keys[gone.path] != first.keys[b.path] && sentKeys.last == other.keys[gone.path],
               "另一次选取用新的上传标识：同名同内容也是另一份原件")
        replies = [.refused(status: 409, message: "虚构：这个上传标识已对应另一份文件", code: "upload_key_conflict")]
        let changed = await WorkspaceStore.uploadPhotos([gone], cached: [:], keys: other.keys, read: { _ in Data([2]) }, send: fake)
        let refusedChange: Bool = { if case .outcome(.refused(409, _, "upload_key_conflict"))? = changed.stop { return true }; return false }()
        expect(refusedChange && sentKeys.last == other.keys[gone.path] && changed.keys[gone.path] == nil && changed.ids.isEmpty,
               "同一标识下文件变了被拒绝：不存、不挂，这张照片下次按新的一次选取上传")
        let withPhotos = WorkspaceStore.oralBody(child: "child-2", day: today, key: "synthetic-oral-key-0002", version: 3, subject: "", what: "读课文",
                                                 completeOn: "", handbackOn: "", attachments: second.ids)
        expect((withPhotos["report"] as? [String: Any])?["attachments"] as? [String] == second.ids, "照片编号进同一份补录的原件列表")
        seen["photo_upload"] = ["sends": sends, "ids": second.ids]
        await settle { store.change(child: "child-1") }
        snapshot("child_one_today")
        expect(store.childName == "示例甲" && ids() == ["FICTION-A1"] && wrongSummary().hasPrefix("错题 1"), "回到原来的甲和原来那一天，内容与首次一致")

        let counts = await backend("")
        expect(counts["posts"] == 0, "整个过程没有任何写入")
        let report: [String: Any] = ["all_fictional": true, "windows_opened": 0, "failures": failures, "observed": seen, "backend": counts]
        if let data = try? JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]) { print(String(decoding: data, as: UTF8.self)) }
        exit(failures.isEmpty ? 0 : 1)
    }
}

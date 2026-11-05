#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一起成长 · 全虚构「完整一天」演示数据播种（只通过公开 HTTP API 写入）。

用法：
    python3 演示数据/seed.py --base-url http://127.0.0.1:8766
    python3 演示数据/seed.py --base-url http://127.0.0.1:8766 --snapshot 证据/api-day.json
    python3 演示数据/seed.py --base-url http://127.0.0.1:8766 --child 示例小宇
    python3 演示数据/seed.py --base-url http://127.0.0.1:8766 \
        --from-real-run 演示数据/real-model-run.json

两种数据来源：
  * 默认：本文件内置的 7 条手写「完整一天」故事（5 今天 + 2 明天），用于固定回归演示；
  * --from-real-run：读取真模型（doubao-seed-evolving）从 6 条虚构老师消息里抽出的
    proposals，直接把模型的 task_title / due / task_goal(+task_submission) / task_advice
    写成事项（标题、截止、lines 全部来自模型产物，不手写、不改写）；模型标为
    optional/「参考」的条目会跳过并在输出里列明。模型给的日期是绝对值，换一天运行
    时这些日期可能落在过去，界面会按真实日期显示「已过期限」，这是如实展示。

它会做四件事：
  1. GET /api/state 取 X-Family-Token 与孩子列表（demo.py 的孩子是「示例星星」「示例小宇」）。
  2. POST /api/task/new 写入 7 条全虚构事项：5 条「今天」+ 2 条「明天」（未来事项：听写 / 带物），
     其中「班主任：填写《出游回执》」另带 category=homework 与 advice（家长安排），用于展示
     家庭安排（plan_lines）与「提交要求/补充要求」堆叠表达的修复效果。
  3. 把演示自带、不属于本次播种的「今天」事项通过 POST /api/task 标记为已完成，
     使今天的清单正好是这 5 项（演示自带的另一条「准备周末的自然观察」仍是日期未写明）。
  4. GET /api/day?child_id=<id>&day=<今天>，断言：今天 N 项 / 以后安排 M 项 / 每条 title/lines 非空，
     打印结果并把 /api/day 快照写入 --snapshot（若给了路径）。
     其中「回执」事项带 advice（家长安排）：修复后投影拆到 plan_lines（家庭安排），
     修复前并入 lines；断言两种形态都成立，便于生成修复前/后两份快照做对比。

数据边界：demo.py 把整个后台数据放在 tempfile.TemporaryDirectory(prefix='family-demo-') 里，
退出即删除（见 REPO/demo.py:12-13）。本脚本只经由 http://127.0.0.1 的公开 API 写入，
不读写任何真实家庭目录，也不改 App 的真实配置；一切姓名/老师/事项均为虚构。
"""

import argparse
import datetime
import json
import sys
import urllib.error
import urllib.request

TZ = datetime.timezone(datetime.timedelta(hours=8))

# ---------------------------------------------------------------------------
# 虚构「完整一天」的故事。day 是今天（UTC+8），tomorrow 是明天，monday 是下周一。
# 只用虚构姓名（示例星星）与虚构老师（虚构语文/数学/英语老师、虚构班主任）。
# ---------------------------------------------------------------------------
def build_story(day):
    tomorrow = day + datetime.timedelta(days=1)
    # 严格的下周一：今天是周一时取 7 天后，避免把今天当成下周一。
    monday = day + datetime.timedelta(days=(7 - day.weekday()) % 7 or 7)
    d, t, mon = day.isoformat(), tomorrow.isoformat(), monday.isoformat()
    return [
        # --- 今天完成（5 项） ---
        dict(title='语文：朗读《晚照》', due=d, source='虚构语文老师通知',
             action='朗读《晚照》2遍，请家长听完在当页签字。\n今天完成，明早检查签字。'),
        dict(title='数学：练习册第12页第2至4题', due=d, source='虚构数学老师通知',
             action='练习册第12页第2至4题，每题写出计算过程。\n今天完成，明天（%s）交回。' % t),
        dict(title='英语：跟读Unit 7第3—10个单词', due=d, source='虚构英语老师通知',
             action='跟读Unit 7第3—10个单词，每词3遍，不用抄写。\n今天完成；明天英语课听写这些单词（另见「英语：明天英语课听写Unit 7第3—10个单词」）。'),
        # advice 会变成服务端 focus.next_action：修复后投影把它拆到 plan_lines（家庭安排），
        # 修复前则并进 lines；快照里据此对比修复前后的投影差异。
        dict(title='班主任：填写《出游回执》', due=d, source='虚构班主任通知', category='homework',
             advice='家长今晚先勾选参加意向，明早把回执交给班主任。',
             action='在《出游回执》上勾选参加意向并签名。\n今天完成，下周一（%s）交回。' % mon),
        # 展示本次修复的「重复表达 / 堆叠要求」场景：提交要求 与 补充要求 两行并存。
        dict(title='英语：完成《每日练习》', due=d, source='虚构英语老师通知',
             action='完成《每日练习》第3页。\n提交要求：完成后把照片上传到班级相册。\n补充要求：家长在最后一页签字确认。'),
        # --- 明天 / 未来事项（2 项） ---
        dict(title='英语：明天英语课听写Unit 7第3—10个单词', due=t, source='虚构英语老师通知',
             action='明天英语课听写Unit 7第3—10个单词。\n今天照跟读练3遍即可，不用抄写。'),
        dict(title='英语：明天带《单词听写本》', due=t, source='虚构英语老师通知',
             action='明天带《单词听写本》。\n不用在家练习，带到学校交给英语老师。'),
    ]


def load_real_run_story(path, day):
    """按真模型抽取结果建故事：标题/截止/lines 全部取模型产物。"""
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as error:
        fail('读取真模型抽取结果 %s 失败：%s' % (path, error))
    calls = payload.get('calls') if isinstance(payload, dict) else None
    proposals, model = [], ''
    for call in calls or []:
        result = call.get('result') if isinstance(call, dict) else None
        if isinstance(result, dict) and isinstance(result.get('proposals'), list):
            proposals = result['proposals']
            model = str(call.get('model') or '')
            break
    if not proposals:
        fail('真模型抽取结果里没有 proposals：%s' % path)
    items, skipped = [], []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        title = str(proposal.get('task_title') or '').strip()
        purpose = str(proposal.get('task_purpose') or '').strip()
        if not title:
            continue
        if purpose == 'optional' or title.startswith('参考'):
            skipped.append(title or str(proposal.get('title_quote') or ''))
            continue
        goal = str(proposal.get('task_goal') or '').strip()
        submission = str(proposal.get('task_submission') or '').strip()
        # 模型的 task_goal 已包含交付/提交信息；优先用它当 lines，
        # 没有 goal 时才退回 submission 或原始消息引文（不手写补句）。
        action = goal or submission or str(proposal.get('title_quote') or '').strip()
        due = str(proposal.get('due') or '').strip()
        try:
            datetime.date.fromisoformat(due)
        except (TypeError, ValueError):
            due = '无明确截止'
        advice = str(proposal.get('task_advice') or '').strip()
        item = dict(title=title, due=due,
                    source='真模型抽取：%s' % (model or 'doubao-seed-evolving'),
                    action=action)
        if advice:
            # 模型的 task_advice 会经公开 API 存成 focus.next_action；
            # 修复后的投影把它显示为独立的「家庭安排」行（plan_lines）。
            item['category'] = 'todo' if purpose == 'admin' else 'homework'
            item['advice'] = advice
        items.append(item)
    if not items:
        fail('真模型抽取结果里没有可播种的事项：%s' % path)
    return items, dict(model=model or 'doubao-seed-evolving', path=path,
                       proposals=len(proposals), skipped=skipped)


def request_json(url, data=None, token=None, timeout=10):
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['X-Family-Token'] = token
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method='POST' if data is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fail(message):
    print('自检失败：%s' % message, file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='一起成长全虚构演示数据播种')
    parser.add_argument('--base-url', default='http://127.0.0.1:8766', help='演示后台地址')
    parser.add_argument('--child', default='', help='孩子姓名，默认取演示后台的第一个孩子')
    parser.add_argument('--snapshot', default='', help='把 /api/day 的 JSON 快照写到这个路径')
    parser.add_argument('--from-real-run', default='',
                        help='按真模型抽取结果（real-model-run.json）播种，而不是内置 7 条故事')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    day = datetime.datetime.now(TZ).date()

    # 1. 令牌与孩子
    try:
        state = request_json(base + '/api/state')
    except (urllib.error.URLError, OSError, ValueError) as error:
        fail('连不上演示后台 %s：%s' % (base, error))
    token = state.get('token') or ''
    children = state.get('children') or []
    if not token or not children:
        fail('演示后台没有返回令牌或孩子列表，请确认启动的是 REPO/demo.py（全虚构演示）')
    child = next((c for c in children if c.get('name') == args.child), None) if args.child else children[0]
    if child is None:
        fail('演示后台里没有孩子「%s」，可选：%s' % (args.child, '、'.join(c.get('name', '') for c in children)))
    child_id, child_name = child.get('id', ''), child.get('name', '')
    print('播种对象：%s（%s），演示日期 %s' % (child_name, child_id, day.isoformat()))

    # 2. 写入事项（request_key 固定为「按天」的稳定值，重复执行不会重复创建）
    if args.from_real_run:
        story, real_meta = load_real_run_story(args.from_real_run, day)
        seed_mode = 'real_run'
        print('数据来源：真模型抽取结果 %s（模型 %s，%d 条 proposals）'
              % (real_meta['path'], real_meta['model'], real_meta['proposals']))
        if real_meta['skipped']:
            print('已跳过模型标为非任务的参考条目：%s' % '、'.join(real_meta['skipped']))
        print('播种说明：标题/截止/lines 均为模型产物，未手写改写。')
    else:
        story = build_story(day)
        real_meta = None
        seed_mode = 'builtin'
    seeded = []
    for index, item in enumerate(story, 1):
        payload = dict(item)
        payload['child'] = child_name
        payload['request_key'] = '%s-%s-%02d' % (
            'demo-real' if seed_mode == 'real_run' else 'demo-seed', day.strftime('%Y%m%d'), index)
        try:
            reply = request_json(base + '/api/task/new', payload, token=token)
        except urllib.error.HTTPError as error:
            detail = ''
            try:
                detail = error.read().decode('utf-8', 'replace')
            except Exception:
                pass
            fail('写入第 %d 条「%s」失败：HTTP %s %s' % (index, item['title'], error.code, detail))
        except (urllib.error.URLError, OSError, ValueError) as error:
            fail('写入第 %d 条「%s」失败：%s' % (index, item['title'], error))
        if not reply.get('ok') or not reply.get('task'):
            fail('写入第 %d 条「%s」未返回 ok/task：%s' % (index, item['title'], reply))
        seeded.append(dict(item, id=reply['task'].get('id', '')))
    seeded_ids = {item['id'] for item in seeded}
    seeded_titles = [item['title'] for item in seeded]

    def day_view():
        return request_json('%s/api/day?child_id=%s&day=%s' % (base, child_id, day.isoformat()))

    def collect(view):
        rows = []
        for group in view.get('groups') or []:
            rows.extend(group.get('items') or [])
        return rows

    # 3. 演示自带事项（跟踪台账 T01「阅读后，听听孩子的发现」）也是「今天」，
    #    通过公开 API 标记完成，让今天的清单正好是本次播种的今天事项。
    view = day_view()
    own = [row for row in collect(view) if row.get('id') not in seeded_ids and row.get('when') == 'today']
    marked = []
    for row in own:
        try:
            request_json(base + '/api/task', dict(id=row.get('id', ''), status='已完成',
                                                  note='虚构演示：这条演示自带事项先标记完成，便于展示今天的清单。（示例数据）'),
                         token=token)
            marked.append(row.get('title', ''))
        except urllib.error.HTTPError as error:
            fail('标记演示自带事项「%s」完成时失败：HTTP %s' % (row.get('title', ''), error.code))
    if marked:
        print('已标记完成演示自带事项 %d 条：%s' % (len(marked), '、'.join(marked)))

    # 4. 断言
    view = day_view()
    counts = view.get('counts') or {}
    rows = collect(view)
    today_rows = [row for row in rows if row.get('when') == 'today']
    later_rows = [row for row in rows if row.get('when') == 'later']
    problems = []

    today_iso = day.isoformat()

    def item_role(due):
        """按截止日期推出预期归属：今天 / 以后 / 已过 / 日期未写明。"""
        if due == today_iso:
            return 'today'
        try:
            due_day = datetime.date.fromisoformat(str(due))
        except (TypeError, ValueError):
            return 'unknown'
        return 'later' if due_day > day else 'overdue'

    expected_today = sorted(item['title'] for item in seeded if item_role(item['due']) == 'today')
    expected_later = [item for item in seeded if item_role(item['due']) == 'later']
    expected_undated = [item for item in seeded if item_role(item['due']) == 'unknown']

    if counts.get('today') != len(expected_today):
        problems.append('/api/day counts.today 应为 %d，实际为 %r'
                        % (len(expected_today), counts.get('today')))
    if counts.get('later') != len(expected_later):
        problems.append('/api/day counts.later 应为 %d，实际为 %r'
                        % (len(expected_later), counts.get('later')))
    if counts.get('closed') != len(marked):
        problems.append('/api/day counts.closed 应为 %d（标记完成的演示自带事项），实际为 %r'
                        % (len(marked), counts.get('closed')))
    if [row.get('title') for row in today_rows].count('') or len(today_rows) != len(expected_today):
        problems.append('今天的清单应恰好 %d 项，实际 %d 项' % (len(expected_today), len(today_rows)))

    found = {}
    for row in rows:
        found.setdefault(row.get('id'), row)
    for item in seeded:
        row = found.get(item['id'])
        if row is None:
            problems.append('播种的事项「%s」没有出现在 /api/day 里' % item['title'])
            continue
        if not str(row.get('title') or '').strip():
            problems.append('事项 %s 的 title 为空' % item['id'])
        lines = row.get('lines') or []
        if not lines or any(not str(line).strip() for line in lines):
            problems.append('事项「%s」的 lines 为空' % item['title'])
        expected_when = item_role(item['due'])
        if expected_when != 'unknown' and row.get('when') != expected_when:
            problems.append('事项「%s」截止 %s，when 应为 %r，实际 %r'
                            % (item['title'], item['due'], expected_when, row.get('when')))
        if expected_when in ('later', 'overdue'):
            due_facts = [f for f in (row.get('facts') or []) if f.get('role') == 'due']
            if not due_facts or due_facts[0].get('value') != item['due']:
                problems.append('事项「%s」的截止日期应为 %s，实际 %r'
                                % (item['title'], item['due'], [f.get('value') for f in due_facts]))
            tomorrow_iso = (day + datetime.timedelta(days=1)).isoformat()
            if (expected_when == 'later' and item['due'] == tomorrow_iso
                    and due_facts and due_facts[0].get('state') != 'next_morning'):
                problems.append('明天的事项「%s」应显示「明早/次日」状态，实际 %r'
                                % (item['title'], due_facts[0].get('state')))

    # 4b. 修复前/后投影对比：回执事项带 advice（服务端 focus.next_action）。
    #     修复后：拆到独立的 plan_lines（原生界面显示「家庭安排」）；
    #     修复前：并入 lines（「家庭安排（计划 日期未定）：…」），没有 plan_lines 键。
    projection = 'legacy'
    plan_item = next((item for item in seeded if item.get('advice')), None)
    if plan_item:
        row = found.get(plan_item['id']) or {}
        if 'plan_lines' in row:
            projection = 'plan_lines'
            plan_lines = row.get('plan_lines')
            if not isinstance(plan_lines, list) or not plan_lines or not any(
                    plan_item['advice'] in str(line) for line in plan_lines):
                problems.append('回执事项的 plan_lines 应包含家长安排原文，实际 %r' % (plan_lines,))
        elif not any('家庭安排' in str(line) for line in (row.get('lines') or [])):
            problems.append('旧投影下回执事项的 lines 应包含「家庭安排…」，实际 %r' % (row.get('lines'),))

    # 4c. 「堆叠要求」展示：修复后 action_lines 去掉「提交要求 / 补充要求」标签，
    #     修复前会原样保留带标签的两行。两种都算播种成功，只记录样式供证据对比。
    daily_item = next((item for item in seeded if item['title'] == '英语：完成《每日练习》'), None)
    daily_style = 'unsupported'
    if daily_item:
        row = found.get(daily_item['id']) or {}
        labels = [str(line) for line in (row.get('lines') or [])
                  if str(line).startswith(('提交要求', '补充要求'))]
        daily_style = 'labels' if labels else 'clean'

    actual_today = sorted(row.get('title') or '' for row in today_rows)
    if actual_today != expected_today:
        problems.append('今天的 %d 项与预期不一致：实际 %s'
                        % (len(expected_today), '、'.join(actual_today)))

    upcoming = view.get('upcoming')
    if not isinstance(upcoming, list):
        problems.append('/api/day 的 upcoming 不是数组：%r' % (upcoming,))

    if args.snapshot:
        payload = dict(view)
        payload['_seed'] = dict(base_url=base, child=child_name, child_id=child_id, day=day.isoformat(),
                                mode=seed_mode, real_run=real_meta,
                                seeded=[dict(id=item['id'], title=item['title'], due=item['due'])
                                        for item in seeded],
                                marked_done=marked, projection=projection, daily_style=daily_style,
                                today=expected_today, later=[i['title'] for i in expected_later],
                                undated=[i['title'] for i in expected_undated])
        try:
            with open(args.snapshot, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write('\n')
        except OSError as error:
            problems.append('写入快照 %s 失败：%s' % (args.snapshot, error))

    print()
    print('=== 今天 %s · %s（%s） ===' % (day.isoformat(), child_name, child_id))

    def print_row(row, tag):
        print('  %s %s' % (tag, row.get('title', '')))
        for line in (row.get('lines') or []):
            print('           %s' % line)
        for line in (row.get('plan_lines') or []):
            print('           [家庭安排] %s' % line)

    if today_rows:
        for row in today_rows:
            print_row(row, '[今天]')
    else:
        print('  （今天没有事项）')
    print()
    if later_rows:
        tag = '[以后安排]' if seed_mode == 'real_run' else '[以后安排 · 明天]'
        for row in later_rows:
            print_row(row, tag)
    print()
    print('/api/day 计数：today=%r later=%r open=%r closed=%r undated=%r upcoming=%r'
          % (counts.get('today'), counts.get('later'), counts.get('open'), counts.get('closed'),
             counts.get('undated'), counts.get('upcoming')))
    print('数据来源：%s' % ('真模型抽取（%s）' % real_meta['model'] if seed_mode == 'real_run'
                           else '内置 7 条手写故事'))
    print('投影模式：%s（%s）' % ('plan_lines 独立字段（本次修复后）' if projection == 'plan_lines'
                                else '家庭安排并入 lines（修复前）', projection))
    if daily_style == 'unsupported':
        print('堆叠要求样式：不适用（%s）' % daily_style)
    else:
        print('堆叠要求样式：%s（%s）' % ('标签已去掉（本次修复后）' if daily_style == 'clean'
                                        else '保留「提交要求/补充要求」标签（修复前）', daily_style))
    print('upcoming 列表：%s' % ('（空）' if not upcoming else json.dumps(upcoming, ensure_ascii=False)))
    if seed_mode == 'real_run':
        print('说明：标题/截止/lines 均为真模型（%s）从 6 条虚构老师消息抽取的产物，未手写改写；'
              '模型的绝对日期若已过去，界面会显示「已过期限」，属如实展示；'
              '本演示后台没有学校消息采集器，upcoming 无法离线产生。' % real_meta['model'])
    else:
        print('说明：本演示后台没有学校消息采集器/模型，学校「即将/待补」事项只能由真实采集流程产生；'
              '两条未来事项以「以后安排（明天）」展示，日期与明早状态核对通过。')

    if problems:
        print()
        for problem in problems:
            print('自检失败：%s' % problem, file=sys.stderr)
        sys.exit(1)
    print()
    titles = '、'.join(row.get('title') or '' for row in today_rows) or '（无）'
    print('自检通过：今天 %d 项（%s）；以后安排 %d 项；日期未写明 %d 项；每条 title/lines 非空。'
          % (len(today_rows), titles, len(later_rows), len(expected_undated)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

# 独立运行 Agent

最终交付主体是独立成长陪伴Agent，包含运行服务、网页入口、业务工具与家庭数据。Hermes或其他Agent Harness仅是内部候选，外部宿主插件不能替代交付；LLM须能按配置更换。以下说明当前已实现的Python进程与调度方式，完整自主跟进和跨模型验收仍见[V1交付目标](V1交付目标.md)，不因存在这些进程就认定全部完成。

Agent 和消息采集由操作系统定时运行，不需要打开 Codex 或网页。后台先处理已经保存的资料，家长打开网页时查看结果，并通过原有待办、记录和建议反馈入口跟进。网页展示属于站内提醒；本版本不提供微信、QQ、短信或浏览器后台推送，也不把生成结果记为通知已送达。

## 进程与资料归属

- 应用主机：运行 `app.py` 和 `family_agent.py --once`，主库始终留在这一台机器。Agent 读取已保存的来源、学习记录和家长反馈，按实际日期回看；模型输出是可核对的建议，不能自行认定孩子完成、掌握或获奖。
- 消息所在电脑：运行 `family_collect.py --config private/collector.json --interval 300`。微信和 QQ 必须在这台机器上具备实际可用、已授权的 CLI 读取能力；个人登录态不复制到应用主机。
- 来源授权与游标由应用主机维护。采集器仅按后台允许的会话读取，后台确认接收后才能推进游标；采集器不改本地数据库镜像，不以空结果覆盖读取失败。
- Agent 的处理状态和产物保存于应用主机的私有 SQLite。原有采集电脑维护的 Markdown、`采集状态.json`、`陪伴建议.json` 和 `陪伴提醒状态.json` 继续保留各自归属，不把服务器新产物写回这些会被旧同步覆盖的文件。

当前实现没有额外引入 Agent 框架、向量库或消息队列服务。模型只连接本家庭配置的端点；模型未配置或离线时，已有记录、待办、文件导入和到期事项仍可查看处理，到期回看提醒不依赖模型。需要模型的工作保留在队列中，失败后先按 5、10、20 分钟间隔重试，之后每小时自动探测恢复；家长也可在网页立即重试。等待重试的旧批次不会堵住新资料，每轮最多调用模型三次，不用编造内容填满建议区。只有有依据的新变化才更新结果，无回复不表示已采纳或已完成。

## 家庭网页配置

手机日历由家长认证入口下的 `calendar.ics` 提供，只读取现有事件与明确的参与决定，不调用模型、不另建日程库、不开放匿名订阅。保留 HTTPS 与现有反向代理认证；手机日历需单独提供家庭服务凭据。事件 UID 使用配置的 `FAMILY_CALENDAR_ID`，未配置则使用 `FAMILY_HOST`，本地默认 `local-family-learning`；已订阅后迁移域名时，将旧值保留为 `FAMILY_CALENDAR_ID`，避免所有事件被视为新事件。该值是稳定标识，不是密码。

首版每个订阅最多1000条原始安排（每周系列计一条），保留历史与取消。超限或来源读取失败返回错误，不截断或用空日历覆盖。课表节次不导出，未知钟点作为透明的时间待定日期，原始消息与备注不进入订阅。协议和认证接口检查通过不等于真实 iPhone 已同步；首次认证与后续刷新需家庭实测。

应用已安装启动后，空家庭自动进入“家庭设置”；已有家庭从顶部进入。网页可以添加或更正孩子，填写微信／QQ来源的明确会话 ID、名称、孩子归属与启停；本轮不自动列举群。已有历史来源不可改绑或清空游标；停用保留既有信息。模型地址、模型名和可选密钥可以稍后填写，已有进程环境配置继续优先。

模型保存后可点“检查已保存的连接”，仅发送固定测试文字并验证响应及要求的返回格式，不发送家庭学习记录；图片和语音能力仍须单独验证。家庭设置已通过隔离 API、360／1440 CSS 像素浏览器及空家庭源码包检查，实际手机和全新 Mac 整机尚待实测。

这些设置保存在本家庭私有资料中。消息仍由下面的采集电脑、已登录 CLI 和系统定时器读取；配置完成不表示已经读到消息。应用不会通过网页安装微信／QQ、复制登录态或运行用户填写的任意命令。CLI路径及系统服务仍由部署者配置，浏览器只展示实际运行结果和缺口。页面配置和管理员文件配置共用同一授权内容；不要同时编辑私有文件和保存页面。

## 新 Mac 同机运行

应用、Python 和所需第三方工具已安装后，在普通用户的图形登录会话中配置，不使用 sudo：

若刚才在终端手动运行了本应用的 `python3 app.py`，先在原终端按 Ctrl+C 停止它，再安装登录服务，避免端口占用。也可以直接安装服务，无需先手动启动；已有家庭服务按升级流程维护，不重复安装。

```sh
python3 configure_mac.py
python3 configure_mac.py --install
```

第一条只显示计划，无写入或启动；第二条明确安装加载本应用服务。默认程序目录为脚本所在目录，可用 `--root` 指定；程序和资料在同一应用目录，`FAMILY_DATA` 固定为该目录的 `private`。默认本地网页 `http://127.0.0.1:8765`，可用 `--app-url` 改为另一本机端口；本机配置命令不配置公网或远程服务。

安装产物是 `private/collector.json` 及 `~/Library/LaunchAgents/local.family-learning.web.plist`、`local.family-learning.agent.plist`、`local.family-learning.collector.plist`。网页服务保持运行，Agent 每分钟检查，已配置的采集器每 5 分钟读取；无 CLI 时采集器保留停用。各进程使用同一应用目录，日志位于私有目录。首次打开网页创建孩子、绑定来源后，再明确启用 Agent；进程已加载不表示消息或模型已连通。

`--wechat-cli /absolute/path/to/wechat-cli` 可指定已安装可执行文件，省略时从 PATH 探测；`--qq-cli /absolute/path/to/qq_reader.py` 可指定兼容只读脚本。仅生成检查文件可用 `--output-dir /absolute/path/to/new-directory`，不会安装或启动服务。未发现 CLI 可先使用网页；后续补接需按下文核对采集配置和登录服务。

已有服务、私有采集配置或占用端口会使安装停止，保留原部署；不自动更新或卸载既有服务。升级沿用备份和服务维护流程。Mac 休眠、关机或退出登录会中断运行，登录服务不等同于无人登录的服务器服务；实际冷开机恢复与手机访问需另验收。

`python3 test_configure_mac.py` 已通过隔离测试，覆盖配置产物、私有权限、已有安装保护和失败撤销；未在生产机器重复安装，也未将模拟启动结果当作新 Mac 的实际登录与消息验证。

## 先核对本机路径

以下 Linux 模板假定程序在 `~/family-learning`，Python 3.10 或以上位于 `/usr/bin/python3`；路径不同时先改模板。正式部署先按 README 初始化家庭、启用应用和认证入口，并保留一致的主库及附件备份。网页模型配置保存于私有 `private/model.json`；原有环境管理方式继续使用 `private/model.env`且优先，不把密钥写入模板、命令行或公开仓库。两个模型配置文件均不进入家庭数据备份，换机器或恢复后单独重配。

网页配置来源后无需再创建另一份授权文件。管理员也可在首次启动前创建 `private/agent.json`，先只处理网页中已有记录，不接消息来源；已有文件不可直接用下面的空示例覆盖：

```json
{"enabled": true, "sources": []}
```

```sh
chmod 600 private/agent.json
```

缺少配置时 Agent 默认停用。`sources` 最多 20 项，每项必须包含以下字段，不能增加其他字段：

| 字段 | 内容 |
| --- | --- |
| `id` | 已授权会话的真实标识；微信为 chatroom ID，QQ 按已核验 CLI 的群标识填写 |
| `platform` | `wechat` 或 `qq` |
| `child_id` | 本家庭已存在的稳定孩子编号，如 `child-1` |
| `name` | 家长能够辨认的来源名称 |
| `cursor` | 字符串；已有来源保持已确认读取位置；网页新增微信来源使用 `0` 作为本机记录起读位置，不表示已经读取 |
| `enabled` | 布尔值；核对身份与范围后再设为 `true` |

新微信来源从本机可读取记录起点分批处理；`0`只是起读请求，不表示完整历史已覆盖。只有后台确认接收才推进游标，旧来源不重置。QQ没有可核验原生历史时保留未就绪状态。不凭群名猜孩子，未配置的来源不扫描，历史和附件缺口单独保留。首次接收之后以主库保存的游标为准，修改配置中的初始游标不会重置它；已有来源不能改绑到另一孩子。

## 应用主机的定时执行

确认私有 Agent 配置后，先在程序目录运行一轮：

```sh
python3 family_agent.py --once
```

该命令结束后退出，定时唤起由 systemd 完成。直接从终端运行时，模型变量须已导出到当前进程；创建 `model.env` 文件不会自动注入终端环境。下面的 service 会读取此文件。检查真实退出状态及网页中的实际结果；仅进程存在或定时器已启用不代表模型、消息或回看成功。

安装同一普通用户的 systemd 模板：

```sh
mkdir -p ~/.config/systemd/user
cp deploy/family-agent.service deploy/family-agent.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now family-agent.timer
systemctl --user list-timers family-agent.timer
journalctl --user -u family-agent.service -n 30 --no-pager
```

模板每分钟唤起一次，不以家长访问页面作为触发条件。同一个 service 仍在执行时 systemd 不会并行启动第二次；恢复后会补一次错过的定时检查。主机需在用户退出后继续运行时，由该机器管理员启用该用户的 lingering，例如 `loginctl enable-linger "$USER"`。模型服务仍须独立保持可用；若模型通过另一台电脑的隧道提供，那台电脑离线时模型能力暂不可用。

手动停启调度：

```sh
systemctl --user stop family-agent.timer
systemctl --user start family-agent.timer
```

停止 timer 不会中断已开始的一轮。迁移或恢复主库前还须等该轮结束，并停止网页写入和采集。

## 消息电脑的采集

只为已授权、实际可读的来源配置采集。创建 `private/collector.json` 并设为 `0600`：

```json
{
  "app_url": "http://127.0.0.1:8765/",
  "wechat_cli": "/absolute/path/to/wechat-cli"
}
```

可选 `qq_cli` 填已核验的 QQ 只读脚本绝对路径。配置只接受上述字段：不在这里填写群号、孩子、游标或密码；会话及游标从后台授权列表获取。`app_url` 仅接受 HTTP 回环地址，不能包含账号、查询串或子路径；远程后台通过已经建立的 SSH 回环隧道访问。不要把应用无认证暴露到公网来连接采集器。

```sh
chmod 600 private/collector.json
python3 family_collect.py --config private/collector.json --once
```

每轮每个微信来源最多取一页 200 条，后续轮次从后台确认的游标继续；非文本消息保留未读内容缺口。QQ 只有实际提供历史读取能力且能核对既有原生消息锚点时才推进，不自动猜初始锚点、不登录或重启客户端。接口失败、电脑休眠、隧道断开均保留原游标与旧资料；恢复后下轮再尝试。正文读取成功不表示附件或完整历史已读。

微信采集使用已核验CLI的 `history --view agent --order asc --strict-read-only`，零游标首次读取不传 `after_message`，后续传后台确认的消息锚点。查询顺序与本地消息编号大小并不等价，按接口原顺序及分页锚点继续；不能先取最新一页再排序冒充完整增量。旧CLI或返回契约不一致时保留失败和原游标，不静默跳过历史。

macOS 可复用 `deploy/local.family-learning.collector.plist`：用文本编辑器将 `__PYTHON3__` 替换为 `command -v python3` 得到的绝对路径，将 `__APP_ROOT__` 替换为实际程序目录。路径含 `&` 或 `<` 时须按 XML 转义；launchd 不展开 `~` 或环境变量。确认 `private` 目录存在后安装：

```sh
mkdir -p ~/Library/LaunchAgents
cp deploy/local.family-learning.collector.plist ~/Library/LaunchAgents/
plutil -lint ~/Library/LaunchAgents/local.family-learning.collector.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.family-learning.collector.plist
launchctl print "gui/$(id -u)/local.family-learning.collector"
```

模板在登录后启动并保持同一个采集进程，每轮结束后等五分钟再检查，日志保存在私有目录。正常停止不自动重启，异常退出由系统限速重启。修改已加载的模板时先 `launchctl bootout "gui/$(id -u)/local.family-learning.collector"` 再安装加载；不要重复创建其他采集任务。Mac 退出登录、休眠或 CLI 不可用时不能持续读取消息，系统应显示实际覆盖缺口。

## macOS 采集权限与重复弹窗

`--interval 300`复用同一个Python采集进程，各轮重新读取私有配置、后台授权来源与游标；不新增聊天范围、不更改系统隐私授权。`--once`仍可用于单次诊断。生成的Mac采集配置与上面的模板均使用持续进程，不再每五分钟退出后重建。

[Apple说明](https://developer.apple.com/videos/play/wwdc2023/10053/)：自动弹出的其他应用数据目录访问授权，在应用退出后会重置。因此，定时重建负责采集的进程可能重复弹窗。保持进程存活用于避免这个触发条件，不绕过用户选择；进程重启、退出登录或工具升级后仍可能需要再次授权。文稿文件夹权限与应用数据目录权限应按系统实际提示分别核对，不能只移动项目目录就认定已修好。

隔离测试验证持续轮询、失败等待、正常信号退出和生成配置；实际是否仍弹窗，须对照运行PID、下一轮真实读取和系统权限日志，不能只凭进程存在认定已修复。

## 核对与恢复

公开测试仅使用隔离的虚构资料，不读取家庭聊天或发送消息：

```sh
python3 test_review.py
python3 test_agent.py
python3 test_agent_http.py
python3 test_collect.py
python3 test_backup.py
```

实际验收须确认：无需开发会话或外部通用Agent客户端，关闭 Codex 和网页后仍能由事件或时间唤醒；一条新资料被后台接收后，Agent形成下一步、执行获准工具并保存结果，收到反馈后调整后续安排；重复执行不重复建事项；反馈、延期及更正影响下一次处理；模型或来源离线时保留旧资料并显示实际故障，恢复后继续。还须以至少两种实际可用LLM分别验证网页和后台流程，核对生效配置、权限、状态及重启恢复；当前检查不代表这些完整验收已经通过。测试数据只写隔离演示，不在家庭主库中造反馈或修改回看日期。

升级先备份，再按公开文件清单更新代码和模板，不覆盖私有配置。恢复遵循 README 的停止写入、校验备份、恢复到空目录流程。`private/agent.json` 的来源授权映射纳入数据备份；校验归档后，恢复工具仅在恢复目录将 `enabled` 设为 `false`，防止旧授权立即重启采集和模型处理。来源已确认游标、消息、建议及处理状态仍随主库完整保留，原备份不变；恢复配置的字节哈希会有意变化。旧备份不含 Agent 配置时默认停用。

另行恢复采集电脑的 `collector.json`、模型/转写配置、账号所在电脑及回环隧道。先核对主库、原件、来源归属与当前账号，再由家庭明确启用 `agent.json`，最后恢复 timer 与采集，避免运行中覆盖数据库。损坏的 Agent 配置会阻止这次隔离恢复，不静默丢弃授权映射；修复副本并重新备份核验后再恢复。

默认不自动报名、登录、对外发消息、确认作业完成或发奖。未来增加站外提醒时，需单独配置目标和权限，并记录真实发送结果；站内显示和模型生成均不能替代送达证据。

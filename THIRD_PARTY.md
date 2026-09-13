# 第三方复用与取舍

核查日期：2026-09-08；候选与实际状态更新至2026-09-14。以下分清已使用的代码、可接入的接口，以及交互参考；候选不代表已经接通。组件许可与本项目 MIT 许可分别保留。

## 已直接使用

| 组件 | 当前用途和文件 | 许可与来源 |
| --- | --- | --- |
| Three.js r185 | `growth-world.js` 调用随源码提供的 `vendor/three.module.min.js`、`vendor/three.core.min.js`，绘制成长场景；必要操作保留普通网页入口 | [上游 r185](https://github.com/mrdoob/three.js/tree/r185)，[MIT](https://github.com/mrdoob/three.js/blob/r185/LICENSE)；本地保留 `vendor/THREE-LICENSE.txt` |

本应用的基础后台使用 Python 标准库与 SQLite；操作系统负责定时运行，已有模型、转写、打印和消息工具通过进程或接口接入。第三方应用、模型权重和个人登录态不随本源码包分发。

## QQ读取与渐进式英语学习的新候选（2026-09-11）

本节保留各候选的用途与许可，不把调研当成交付。2026-09-13已明确允许QQ使用Computer Use保底：Cua Driver 0.26.0已在隔离环境安装，解锁后的开发宿主读到指定QQ窗口与群号；新产品命名宿主在自身进程内加载SDK，实际检查两项权限尚未授予。此入口目前只作检查，不读取聊天，不能算持续采集。QQ持续采集仍未恢复，独立后台宿主权限、指定群/原件/增量入库与桌面共存仍待验收。ego-lite与Read Frog尚未接入。需求及路线切换以[V1交付目标](V1交付目标.md)的R08/S02、R21/S05及R33/S07为准。

| 候选 | 本项目取舍 | 尚需核对 |
| --- | --- | --- |
| [Cua Driver](https://cua.ai/docs/how-to-guides/driver/use-sdk-in-process) | 当前正在验证的QQ保底路线：由Family Agent调用SDK读取官方QQ窗口，保留真实出处与覆盖缺口；现有通知入库可复用，但不能伪造原生ID直接套用CLI返回 | 这是界面读取，不是QQ消息API。后台操作仅为[尽力保证](https://cua.ai/docs/concepts/the-no-foreground-contract)，权限属于运行宿主；文档示例与发布版本须分别核对；本轮固定0.26.0，并按实际包内接口与运行回执验证。先验证一个授权群、最近20条和一张图片，核对来源、重复、漏读及日常QQ共存；看见一页不算历史完整 |
| [LLBot Mac CLI 8.2.0](https://github.com/LLOneBot/LuckyLilliaBot/releases/tag/v8.2.0) | 非界面候选；核对发行包哈希后，已验证Mac ARM启动帮助、随包Node和原生模块可在禁网、禁家庭文件及禁子进程条件下运行。未登录、未触碰官方QQ，未恢复采集 | 区分Mac运行平台与QQ协议身份。默认仍是独立Linux协议；[多协议文档](https://github.com/LLOneBot/LuckyLilliaBot/blob/v8.2.0/docs/multi-protocol.md)明确列出其他协议的签名后端和Watch设备参数阻碍。此前同账号共存失败仍有效。GPL及原生SDK/服务单独核对，不随MIT项目分发 |
| [NapCat Mac安装器](https://github.com/NapNeko/NapCat-Mac-Installer) | Mac非界面候选保留；仅核对文档，未安装或改QQ | 上游明确修改QQ启动入口，并在原QQ/NapCat入口间切换；有Mac安装器不证明桌面共存。安装器MIT不涵盖其加载的所有组件，接入前继续核对兼容与许可 |
| [SnowLuma](https://github.com/SnowLuma/SnowLuma) | 仅作协议接口候选调研，未安装或接入 | 当前快速开始列Windows/Linux；许可证为非商业源码可见，并非OSI开源，公开派生分发需书面许可；不并入本项目MIT代码或小盒子交付 |
| [ego-lite](https://github.com/citrolabs/ego-lite) | 保留为学校网站或已有学习平台网页版的可选工具；借鉴独立工作区和结构化页面读取 | 公开接口控制其Chromium浏览器，不能直接读取桌面QQ。支持[自建Agent](https://lite.ego.app/document/en/docs/custom-agent-harness)。仓库MIT不代表另行下载的整个浏览器可以按MIT分发；没有网页需求时不引入 |
| [Read Frog](https://github.com/mengxi-ream/read-frog) | 借鉴按需解释、朗读、阅读材料转学习卡及真实回忆反馈；作为可选学习工具，家庭目标和证据继续留在本应用 | 上游为GPLv3／商业双许可，不复制到本项目MIT文件。Notebase要求云端登录；不能当作已可本地部署的完整学习后台。具体渐进设计见PRD第2.5节 |

Read Frog的[Notebase指南](https://www.readfrog.app/en/docs/notebase-beta)描述笔记、卡片模板及Again／Hard／Good／Easy复习评分；这类回忆评分不等于综合英语能力。[自定义AI动作](https://www.readfrog.app/en/docs/custom-actions)可对选中文字返回固定字段，适合复用小任务。上游说明存在版本差异，具体调度算法不据宣传推断。

它还提供[远程MCP](https://www.readfrog.app/en/docs/mcp)，通过OAuth授权读取或管理笔记、卡片和学习活动；当前要求Ultra权益。MCP不会自行获取任意网页或解析PDF，也没有专用复习队列工具。后续家庭选择使用时先按孩子明确映射Notebase、只读接入并保留外部ID与时间，不把两个孩子记录混合；我们的MCP适配尚未实现。现有手动反馈和原件上传继续独立工作，不为候选创建账号、购买订阅或上传家庭资料。

## 可以直接接入，但本版尚未接入

| 候选 | 可以少写什么 | 具体接法与启用条件 |
| --- | --- | --- |
| Memos | 已有 Memos 家庭不用重复录入笔记 | 家庭提供自己实例的地址与专用令牌，从 `GET /api/v1/memos` 分页读选定记录；核对孩子后复用本项目原件、记录和关联流程。保存来源实例及 memo ID 去重，先做单向导入，不接管原笔记编辑。现在没有此导入器 |
| py-fsrs | 不自行发明记忆卡的复习间隔算法 | 对明确的单词、公式等记忆卡保存 `Card`、真实 `ReviewLog` 和下一次 `due`，用 `Scheduler.review_card(card, rating)` 计算建议日期，再接现有到期回看。现有“作业完成／部分完成／需要帮助”不能当作 FSRS 的回忆评分；先有具体记忆卡和真实评价入口，再启用。现在未安装或调用该包 |
| Anki 文本交换 | 家庭已有卡片时避免逐张重录 | 可按官方文本导出格式做 TSV 字段映射与预览，核对孩子和内容后导入；文本不是完整复习历史。现在仅支持保存上传原件，没有卡片或复习历史导入 |

Memos 官方提供[令牌认证](https://usememos.com/docs/integrations/api-access)与[REST API](https://usememos.com/docs/api/latest)，源码为 [MIT](https://github.com/usememos/memos/blob/main/LICENSE)。当前文档包含 0.31 候选版变化；真正接入时应按家庭安装版本固定接口并测试分页、修改、附件与撤销授权。Memos 的定位是轻量笔记，没有可直接启用的本项目式儿童成长模块；新家庭无需先安装另一套笔记后台。[项目说明](https://github.com/usememos/memos)

[py-fsrs](https://github.com/open-spaced-repetition/py-fsrs)是可单独嵌入 Python 的 [MIT 组件](https://github.com/open-spaced-repetition/py-fsrs/blob/main/LICENSE)，支持序列化卡片与复习日志。此处选它作为算法候选，不复制 Anki 主程序。[Anki 主体许可](https://github.com/ankitects/anki/blob/main/LICENSE)为 AGPL-3.0-or-later，部分文件另有许可；[官方导出说明](https://docs.ankiweb.net/exporting.html)区分纯文本、牌组包和全库包。记忆排期不能用来给综合能力、情绪或社会适应程度评分。

## 借鉴交互，继续使用本应用的数据

| 项目 | 借鉴落点 | 当前边界及许可 |
| --- | --- | --- |
| [Memos](https://github.com/usememos/memos) | “记一下”先收文字或原件，之后再补标签与关系；新用户尽快保存第一条记录 | MIT；本轮未复制界面代码 |
| [Moodle](https://docs.moodle.org/en/Competencies) | 一个学习目标关联前后尝试、完成材料与帮助条件；`records.related_record_id` 和现有订正／复测视图继续承载 | [GPLv3](https://github.com/moodle/moodle/blob/main/COPYING.txt)；未安装其课程、账户或成绩后台，不复制相关代码到 MIT 文件 |
| [Mahara](https://manual.mahara.org/en/26.04/intro/introduction.html) | 作品加孩子自己的反思；从原件中挑少量作品展示，而非用积分代替学习证据 | 官方[许可条款第1.2.2项](https://mahara.org/artefact/file/download.php?file=441441&view=137236)列 GPLv3；仅参考公开手册。本轮[官方代码站](https://git.mahara.org/mahara/mahara)要求登录，并说明临时关闭公开项目访问，未取得最新版代码核查 |
| [Immich](https://docs.immich.app/install/post-install/) | 应用启动后在网页完成首次配置；先完成核心资料，其他成员和附加能力按需配置，回设置页继续 | [AGPLv3](https://github.com/immich-app/immich/blob/main/LICENSE)；仅借鉴安装后引导，不引入其照片服务器、账户或后台 |

Daylio 只作为低负担体验记录的参考，不列为开源组件。ChatGPT Study mode 是产品体验参考，不是可随本项目分发的教学模块。教材全文及第三方题库另核查内容权利，不能因其出现在 GitHub 就纳入 MIT 源码。

## 已有微信项目能否直接复用

[WeChat Obsidian Hub](https://github.com/joyrush-D/wechat-obsidian-hub)是已公开的另一个项目，采用 [Apache-2.0](https://github.com/joyrush-D/wechat-obsidian-hub/blob/main/LICENSE)。它的[消息读取类](https://github.com/joyrush-D/wechat-obsidian-hub/blob/main/src/db/message-reader.ts)依赖 `sql.js`，已有发送者和消息字段读取；[解密脚本](https://github.com/joyrush-D/wechat-obsidian-hub/blob/main/scripts/decrypt_mac.py)产出数据库文件。它们不是本应用现有 `wechat-cli tail` 的可替换入口，也没有本应用的逐群授权与后台确认游标契约。

本轮保留 `family_collect.py` 调用已授权 CLI 的路径，不另起解密和全库分析流程。以后若需要支持该项目产出的已授权资料，应先做保持原消息 ID 与会话归属的适配，并验证缺口和去重；目前未复制或运行其代码。一个微信项目已公开，不代表家庭学习应用也已经在 GitHub 发布。

## 本轮新家庭配置的产品落点

以下是从 [Memos 首次使用](https://usememos.com/docs/getting-started)及 [Immich 安装后步骤](https://docs.immich.app/install/post-install/)提炼的本项目设计，不是复制它们的实现：

1. 应用程序已安装、启动后，空家庭进入网页初始化；先填写孩子称呼和年级，其他未知资料保留空值。已存在的家庭直接进入原数据，初始化不得覆盖它。
2. 固定“家庭设置”入口继续添加或更正孩子，稳定编号不随姓名变化；一个孩子可以有多个群。
3. 群绑定先选平台、可辨认的名称与稳定会话 ID，再选孩子；未登录、未读到、停用必须分别显示。配置来源不等于已经同步，启用后以实际读取结果反馈状态。
4. 模型和消息接入可以稍后做；家长先记一件事、导入一份资料或安排今天。系统不替家庭安装微信／QQ，也不复制账号；微信复用已授权CLI，QQ按现行S02验证非界面或Computer Use路线；保存设置不等于采集已经可用。

上述家庭设置已通过隔离 API、360／1440 CSS 像素浏览器与空家庭源码包检查；实际手机及全新 Mac 整机尚待实测。模型可用固定文字检查已保存连接，图片与语音能力另验。实际设置入口与剩余接入条件见 [README](README.md) 和 [PRD](PRD.md)。本轮没有新增第三方运行依赖。


GTD 在此作为事项处理方法参考：[官方五步介绍](https://gettingthingsdone.com/what-is-gtd/)。本项目采用澄清下一步、区分等待／以后与定期回看的思路；未复制图表或书中文字，不是开源软件依赖，也不代表获其认证。

## 可选的本机微信图片转换

2026-09-09核对：`family_wechat_media.py`依据已观测的V2分段格式独立实现，格式参照[wechatauto-replica媒体模块](https://github.com/fanyuantaier/wechatauto-replica/blob/main/wechatauto/media.py)及其[Apache-2.0许可](https://raw.githubusercontent.com/fanyuantaier/wechatauto-replica/main/LICENSE)；没有复制其下载器、取钥程序或源代码。仅支持既有密钥下的V2和已验证WXGF HEVC首帧，不是通用微信图片协议实现。后续若复制第三方代码，须另外保留其许可与归属。

AES调用macOS系统CommonCrypto的公开API，签名依据[Apple官方头文件](https://github.com/apple-oss-distributions/CommonCrypto/blob/main/include/CommonCryptor.h)，不复制或分发系统库。FFmpeg作为安装者选择的外部命令执行，固定HEVC输入及本地文件/管道协议；其不同构建适用的LGPL/GPL条款见[FFmpeg许可说明](https://ffmpeg.org/legal.html)及[协议文档](https://ffmpeg.org/ffmpeg-protocols.html)。当前机器构建为GPLv3+，不把该二进制打包为本项目MIT内容。微信CLI、账号、密钥与媒体同样不随公开源码分发。

本机CLI适配还核对了路径查找行为：`strict-read-only`本身不关闭默认的图片缓存读取。文字查询显式关闭`include-media-paths`；媒体查询关闭`include-local-paths`并开启`include-debug`保留资源元数据，随后由本应用检查对应群和月份中的固定候选。只支持固定构建，第三方CLI升级须重新验证这些参数和返回契约。

## 可选的Mac QQ独立读取服务

2026-09-10：`family_qq_llbot.py`独立实现对[LLBot v8.1.10](https://github.com/LLOneBot/LuckyLilliaBot/tree/v8.1.10) WebUI HTTP接口的只读适配，没有复制其源码。上游源码标示[GPL-2.0](https://github.com/LLOneBot/LuckyLilliaBot/blob/v8.1.10/LICENSE)；本项目不分发其服务、原生SDK、Node二进制或个人会话。原生签名SDK与Auth Token服务是另外的运行依赖，公开源码不能说明其完整内部数据处理；由家庭自行选择、安装与授权，不能将其当作本项目MIT代码或腾讯官方接口。文字读取与选定原图曾在Mac实测，但后续同账号试用出现桌面QQ退出和操作受影响，共存未通过，已撤回日常采集部署。接口实现保留为实验代码，不据读取成功推荐自动登录或宣称可替代桌面日常使用。

Cua Python SDK 0.26.0的已安装包元数据标示MIT；本项目仅调用其公开接口，未复制SDK源码或分发SDK、原生库、Python运行时。宿主嵌入使用Python标准C API的`Py_BytesMain`；具体家庭需要已有兼容Python动态库和SDK环境。

2026-09-14版本复核：8.2.0的Mac ARM CLI发布资产已下载并核对上游SHA256，三个受限离线检查通过。发行包最初没有执行位，按其启动脚本只补实验目录内CLI/Node执行位；没有运行脚本中的清除隔离属性或登录步骤。新版说明修复假在线、二维码与WebQQ会话问题，没有提供同账号桌面共存验收；源码的多协议支持还明确保留端到端阻碍。后续先核对上游条件及具体账号方式，再决定是否执行新登录测试，不重复旧失败登录。
发行包内也已检出多协议实现；单独运行其中的参数解析函数，六个无账号案例确认默认及错误参数均回退Linux。这解决代码是否打包的疑问，仍不证明其他设备协议或同账号共存可用。

## QQ本地数据库与命令行候选

2026-09-14限定核验：

- [qqcli-rs](https://github.com/2233admin/qqcli-rs)提供会话、历史、搜索和JSON输出；当前README明确安装与解密流程仅支持Windows。旧版包文档曾列macOS，不据旧说明推荐当前Mac安装。保留Windows条件候选，尚未接入。
- [QQLore固定源码](https://github.com/Will-hxw/QQLore/tree/8195c7f9c4c9c56b9eb5ae0a73fba52d2cf81425)的QQProvider确有本地数据库读取、指定群筛选、回复关联与媒体解析。它要求已有数据库密钥、SQLCipher及原生文件扩展；不提供Mac取钥。消息查询允许省略群号，连接未强制只读；接入时须通过本产品既有来源授权限定群，强制只读连接，单独核验版本、消息分页、回复与原件。不能直接启动全群同步，或把SELECT查询等同于底层文件不会写入。只借鉴必要读取部分，不安装其整套检索与模型服务。
- 其扩展的构建依赖清单指向ntdb_unwrap项目路径；进一步核验了独立上游[ntdb_unwrap](https://github.com/artiga033/ntdb_unwrap/tree/b1c5420a1957a833787b57f616243d4fa120526d/sqlite_extension)的1024字节文件头适配。已从固定源码在Mac ARM构建，在虚构数据库验证读取、默认连接允许写入、显式只读拒绝写入且源文件哈希不变、缺失文件不被创建。此项不验证真实QQ解密、消息、并发增量或桌面共存。扩展会注册进程级默认文件接口；后续验证必须与家庭主库进程隔离。QQLore自带二进制未直接执行，不将自行构建结果等同于该二进制的来源证明。
- [QQBackup的Mac取钥说明](https://qqbackup.github.io/QQDecrypt/decrypt/extract/NTQQ%20(macOS%20ARM%EF%BC%8C%E6%97%A0%E9%9C%80%E5%85%B3%E9%97%AD%20SIP).html)虽不要求关闭SIP，仍要求重新签名QQ并用调试器取得密钥；运行期Mac版本兼容未确认，当前7.0.1的离线函数定位见下方增量。本轮没有执行取钥或改变客户端。已有合法密钥、兼容版本及不会影响日常QQ的验证条件具备后，再做指定群实测；不据“支持Mac”自动重新签名、注入或登录家庭账号。

QQLore根目录与ntdb_unwrap扩展分别标示MIT；其余依赖和取钥资料许可仍须分别核对。本轮未把第三方代码、二进制、账号或密钥加入公开分发。新加坡限定评审已返回并核对成功读取材料，确认只读、取钥、群过滤和版本前提；评审不能替代本机实测。非界面读取仍为首选，LLBot、官方机器人与已授权窗口保底继续保留。

2026-09-14补充加密与增量基础检查：从[SQLCipher 4.19.0固定源码](https://github.com/sqlcipher/sqlcipher/tree/c4b275a47932888216bade83aff2bbc73df0ff85)在私有实验目录构建Mac ARM命令行及动态库，使用系统CommonCrypto，未全局安装或加入应用运行依赖。采用QQLore明确的页大小4096、KDF迭代4000、HMAC-SHA1和PBKDF2-HMAC-SHA512参数，配合前轮自行构建的ntdb_unwrap扩展；在虚构普通消息表上验证了加密文件头适配、只读拒绝写入、错误密钥/损坏页面拒绝、缺失文件不创建，以及独立读进程看不到未提交内容、能读到提交后的WAL新增、写连接正常关闭后仍可读取。实际命令行JSON结果与C接口一致。读取前后主文件与WAL哈希不变；不据此推断共享内存侧文件完全不变、崩溃恢复、WAL轮转或真实QQ共存已通过。

当前QQ 7.0.1的实际数据库只读取前1024字节，确认文件头标记与候选匹配，未打开消息页或获取密钥。这是开发执行上下文的文件访问结果，不是独立产品宿主权限验收；真实QQ字段、分页和原件仍待实际密钥与兼容条件具备后核验。新加坡Haiku4.5完成这份小型验证的限定复核，认可实验边界；未据此启用生产采集。SQLCipher社区源码为BSD-3-Clause，SQLite与系统加密库分别适用其许可；本项目未分发上述实验二进制。跨设备不能默认复用同一密钥，必须核对密钥与目标数据库对应，[上游讨论](https://github.com/orgs/QQBackup/discussions/87)仅作为取钥路线的线索，不替代实际解密验收。

2026-09-14补充当前Mac程序的离线定位：公开取钥脚本在整个通用二进制文件中搜索字符串，会先命中Intel片段，却减去ARM64片段的偏移；同时只匹配指令低12位，不能据其“找不到函数”断定新版不兼容。限定ARM64字符串区、按节映射真实地址，再核对完整ADRP/ADD引用和函数边界后，已在QQ 7.0.1（52892）中找到同时引用两条密钥诊断信息的函数；独立离线反汇编确认相关指令。虚构通用文件中的Intel干扰、不同页同低位干扰、节地址偏移及截断拒绝检查通过。此项只读程序文件，不附加或运行QQ进程，未取得密钥、未读消息、未重签或重启QQ，不代表运行期兼容与桌面共存通过。

当前客户端仍为腾讯原始签名，启用Hardened Runtime且没有Get task allow；[Apple调试权限说明](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.debugger)说明普通调试器仍需目标程序允许调试。找到函数不能跳过这一条件，也不将通用文件访问权限当作解决方案。保持日常QQ不变，继续核验一次性取钥方式的影响与可恢复性；既有官方机器人、具名窗口保底及Windows CLI候选不撤销。自写离线诊断仅用于候选核验，QQ二进制、反汇编和任何密钥均未加入公开分发。

## QQ官方机器人候选：普通群消息

2026-09-14核验[腾讯官方Node SDK 1.0.4](https://github.com/tencent-connect/qqbot-nodejs/tree/ca55d9c395b582b7fcfad0ec27209c35dd04e0b3)：[事件解析代码](https://github.com/tencent-connect/qqbot-nodejs/blob/ca55d9c395b582b7fcfad0ec27209c35dd04e0b3/src/protocol/gateway/event-dispatcher.ts)同时处理`GROUP_MESSAGE_CREATE`和`GROUP_AT_MESSAGE_CREATE`。在隔离目录执行该版本的实际解析代码，虚构的未@群消息可保留文字、发言人、原消息ID、时间和附件信息；不同群及引用消息保持各自标识。解析器本身不做持久去重。这是协议代码验证，没有连接机器人、读取家庭群或验证附件下载。

这条路线使用AppID/AppSecret取得机器人身份，不需要让家长的个人QQ再次登录。它是新增的可验证候选，不能笼统排除为“官方机器人只能收@”；但SDK能解析事件不证明当前机器人获准入群或获得普通群消息权限。账号与目标班级群的权限、群主可用设置和实际推送范围仍需在官方平台/群中核验，不通过注入页面选项获得未开放权限。

条件满足后，优先用该SDK的长连接在家庭中心接收，复用现有Agent整理，不引入OpenClaw整套框架。实施须限定机器人身份及指定群，显式核对`group_openid`与本产品来源/孩子的对应关系；它不是数字QQ群号，`member_openid`也不当作个人QQ号。先持久保存原事件，再去重和处理；不注册回复、输入状态或其他发送行为。凭证、原消息和日志不公开。

该SDK的[历史缓冲](https://github.com/tencent-connect/qqbot-nodejs/blob/ca55d9c395b582b7fcfad0ec27209c35dd04e0b3/src/middleware/history-buffer.ts)只缓存已收到的消息，不能证明可拉取入群前或断线期间的历史。SDK也提供会话RESUME与持久化接口，不能断言所有离线消息永远丢失；有效会话恢复与任意历史拉取是不同能力，恢复范围仍需实测。隔离网关检查发现该版本先保存接收序号，再调用异步业务处理；不得把此序号直接当作本产品已入库位置，接入前必须验证业务落盘、恢复位置和失败重放的先后关系。历史缺口、重连、重复事件、原件下载和桌面同时使用均需实测，不能沿用或推进旧个人QQ协议游标。当前未安装到生产、未启用来源；LLBot、具名Cua宿主和人工导入候选继续保留。

SDK源码标示MIT；本轮只在私有实验目录执行公开解析代码，未把SDK或其依赖打包到产品。以后接入时核对实际分发版本和依赖许可。QQDecrypt的Mac ARM教程仍无当前QQ版本验证且要求调试/SIP配合，不作为默认本地数据库读取路线；不修改客户端或系统保护来试错。

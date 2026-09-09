# 第三方复用与取舍

核查日期：2026-09-08。以下分清已使用的代码、可接入的接口，以及交互参考；候选不代表已经接通。组件许可与本项目 MIT 许可分别保留。

## 已直接使用

| 组件 | 当前用途和文件 | 许可与来源 |
| --- | --- | --- |
| Three.js r185 | `world3d.js` 调用随源码提供的 `vendor/three.module.min.js`、`vendor/three.core.min.js`，绘制成长场景；必要操作保留普通网页入口 | [上游 r185](https://github.com/mrdoob/three.js/tree/r185)，[MIT](https://github.com/mrdoob/three.js/blob/r185/LICENSE)；本地保留 `vendor/THREE-LICENSE.txt` |

本应用的基础后台使用 Python 标准库与 SQLite；操作系统负责定时运行，已有模型、转写、打印和消息工具通过进程或接口接入。第三方应用、模型权重和个人登录态不随本源码包分发。

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
4. 模型和消息接入可以稍后做；家长先记一件事、导入一份资料或安排今天。系统不替家庭安装微信／QQ，也不复制账号；采集继续通过已授权 CLI 和 NTQQ 路线。

上述家庭设置已通过隔离 API、360／1440 CSS 像素浏览器与空家庭源码包检查；实际手机及全新 Mac 整机尚待实测。模型可用固定文字检查已保存连接，图片与语音能力另验。实际设置入口与剩余接入条件见 [README](README.md) 和 [PRD](PRD.md)。本轮没有新增第三方运行依赖。


GTD 在此作为事项处理方法参考：[官方五步介绍](https://gettingthingsdone.com/what-is-gtd/)。本项目采用澄清下一步、区分等待／以后与定期回看的思路；未复制图表或书中文字，不是开源软件依赖，也不代表获其认证。

## 可选的本机微信图片转换

2026-09-09核对：`family_wechat_media.py`依据已观测的V2分段格式独立实现，格式参照[wechatauto-replica媒体模块](https://github.com/fanyuantaier/wechatauto-replica/blob/main/wechatauto/media.py)及其[Apache-2.0许可](https://raw.githubusercontent.com/fanyuantaier/wechatauto-replica/main/LICENSE)；没有复制其下载器、取钥程序或源代码。仅支持既有密钥下的V2和已验证WXGF HEVC首帧，不是通用微信图片协议实现。后续若复制第三方代码，须另外保留其许可与归属。

AES调用macOS系统CommonCrypto的公开API，签名依据[Apple官方头文件](https://github.com/apple-oss-distributions/CommonCrypto/blob/main/include/CommonCryptor.h)，不复制或分发系统库。FFmpeg作为安装者选择的外部命令执行，固定HEVC输入及本地文件/管道协议；其不同构建适用的LGPL/GPL条款见[FFmpeg许可说明](https://ffmpeg.org/legal.html)及[协议文档](https://ffmpeg.org/ffmpeg-protocols.html)。当前机器构建为GPLv3+，不把该二进制打包为本项目MIT内容。微信CLI、账号、密钥与媒体同样不随公开源码分发。

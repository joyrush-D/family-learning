# merge18 演示快照（全虚构数据）

这是什么
  18 条多渠道虚构消息（FIXTURE.json：5 个来源、9 个发布者、2 个孩子、2 份附件）经产品自己的通路
  （ingest → Agent 抽取 → 待核对卡 → 接受任务）跑完后的静态数据目录，可在本机打开 2026-11-04 的
  每日清单并核对「多渠道同件事归并」。全部内容为 QA 虚构（孩子名「示例甲」「示例乙」，班级与老师均为虚构）。

数据从哪来
  生成脚本：work/merge18/run_merge18.py（真模型 doubao-seed-evolving；FAMILY_LLM_LIGHT_REASONING_EFFORT=none，
  selection output 6000；7 个 tick 后稳定）。
  产物归档：work/merge18/run-fix9-2.json / model-calls-fix9-2.json。
  产品版本（生成时）：family_agent.py sha1 3d8807c865287b8fc46fc6ff7495df4b40fd1235，
                     family_llm.py  sha1 bf2c974be34b6460d980d18b8e2ffc1498611be1（= git HEAD）。

目录内容
  家庭运行规则.md     两行虚构孩子档案（app.py 只从自己所在目录读这个文件，见“怎么跑”）
  data/agent.json     6 个产品来源定义（fixture 的 5 个来源中 qa-family-manual 按 child_scope 拆成
                      qa-manual-a / qa-manual-b，因为产品一个来源只能绑定一个 child_id）
  data/family.sqlite3 产品数据库：18/18 消息已处理、7 条任务、16 个 Agent 事项、2 份附件、10 个 job 全部 done
  data/uploads/       2 份附件（英语每日练习.pdf 已读完整要求；识字小卡.jpg 保持未读/待处理）

不包含
  model.json / API key / 任何同步、打印、发布脚本；也不含真实家庭目录内容，数据目录只含本快照。

怎么跑（产品 app.py 用 PORT 环境变量，不解析 --port）
  1) 复制快照到任意位置：
       cp -R demo-snapshot /tmp/merge18-demo
  2) 让产品读到虚构档案（app.py 的 ROOT 是源码目录，只从那里 read('家庭运行规则.md')）：
       cp /tmp/merge18-demo/家庭运行规则.md <产品源码目录>/
     （该文件被产品 .gitignore 忽略；演示完删掉即可）
  3) 起服务：
       cd <产品源码目录>
       FAMILY_DATA=/tmp/merge18-demo/data PORT=8799 python3 -B app.py
  4) 打开：
       http://127.0.0.1:8799/?child_id=child-1   （另一个孩子：?child_id=child-2）
  5) 关闭后清理：
       rm -f <产品源码目录>/家庭运行规则.md

预期画面（day=2026-11-04）
  清单共 8 行 = 5 个今天必做 + 2 个明天带物（在“即将”里）+ 1 张已取消待核卡；
  8 组同事项各合 1 行，0 重复卡、0 孤儿卡。
  后续通知不再混进卡片正文：朗读卡的 m18/m10、英语卡的 m13 以「提醒」行出现在 follow_ups；
  数学卡里 16:00 的旧说法（m04，早于 17:00 的更正 m09）以「先前提醒」行出现在 follow_ups，
  不再写成「更正」，卡面正文只有当前生效的「第1—3题 / 第4题不做 / 算式 / 验算 / 签字 / 周五交」。
  自检：cd work/merge18 && ./verify-demo.sh

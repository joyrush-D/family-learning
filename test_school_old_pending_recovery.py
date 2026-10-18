"""The fictional Flash27 day as the r259 program (f0941d0) saved it: five untouched pending reviews and no task.

The rows are the unchanged output of f0941d0 for the HANDOFF 7 originals and the actual Flash27 reply on a fresh fictional
store (no real model, collector or device). The current program reads them again on its ordinary run_once, without a
model call: an item whose unchanged original, generated snapshot and selection receipt prove its own day is collected
on the existing acceptance path; anything a parent, a link, a later change or a past day touched keeps its saved state.
"""
import datetime as dt
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import test_school_native_coverage as native

# agent_items/agent_jobs/agent_messages/agent_runtime/agent_sources exactly as f0941d0 left them after its two rounds.
R259 = json.loads('{"agent_items":[{"id":"agent-1c43a0b386dab94a2dee77228c79eac7","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"语文：完成《星芽阅读练习册》第28页第1、2题","body":"完成《星芽阅读练习册》第28页第1、2题。\\n答案写在练习册上。\\n今晚完成，明天早上交。\\n提交要求：明天早上交练习册。","evidence":"[{\\"ref\\":\\"message:synthetic-group:31\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:08:00+08:00\\\\n今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。今晚完成，明天早上交。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。\\",\\"school_generated_snapshot\\":\\"df77e1f408f676d4c3620de07b11aa0152ce3abc3fea74b3e3b15c25c34ead1d\\",\\"school_goal_id\\":\\"goal-47b93177aabb4f3f89a919a79121db81\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"语文\\"},\\"school_messages\\":[{\\"message_id\\":\\"31\\",\\"source_id\\":\\"synthetic-group\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可先读题再作答，完成后自查是否两题都已写在练习册上。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《星芽阅读练习册》第28页第1、2题。\\\\n答案写在练习册上。\\\\n今晚完成，明天早上交。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第28页第1、2题，答案写在练习册上，今晚完成、明天早上交。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：完成《星芽阅读练习册》第28页第1、2题\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可先读题再作答，完成后自查是否两题都已写在练习册上。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《星芽阅读练习册》第28页第1、2题。\\\\n答案写在练习册上。\\\\n今晚完成，明天早上交。\\\\n提交要求：明天早上交练习册。\\",\\"origin_basis\\":{\\"message:synthetic-group:31\\":\\"c8a8ad49b96ad075e1f52346591b4b9f47257792b5f322b66e2aea96264e9591\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第28页第1、2题，答案写在练习册上，今晚完成、明天早上交。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：完成《星芽阅读练习册》第28页第1、2题\\"}}"},{"id":"agent-06c2fbf8b13789ebaa6f320b4406adea","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"数学：完成《数格练习册》第34页第1—4题","body":"完成《数格练习册》第34页第1—4题。\\n第34页第4题要把计算过程写完整，写在原题下面即可。\\n今晚完成，明天早上交。\\n提交要求：明天早上交练习册。","evidence":"[{\\"ref\\":\\"message:synthetic-group:32\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:12:00+08:00\\\\n数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。\\"},{\\"ref\\":\\"message:synthetic-group:33\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:13:00+08:00\\\\n补充一下，第34页第4题要把计算过程写完整，写在原题下面即可。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。\\",\\"school_generated_snapshot\\":\\"e0e06810185df3fad516e0c899118b382828de32535d37c77656232fcd473d55\\",\\"school_goal_id\\":\\"goal-abb032574f6a363eeb620734538938c2\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"数学\\"},\\"school_messages\\":[{\\"message_id\\":\\"32\\",\\"source_id\\":\\"synthetic-group\\"},{\\"message_id\\":\\"33\\",\\"source_id\\":\\"synthetic-group\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可先完成第1—3题，再重点检查第4题计算过程是否写完整。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《数格练习册》第34页第1—4题。\\\\n第34页第4题要把计算过程写完整，写在原题下面即可。\\\\n今晚完成，明天早上交。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第34页第1—4题，并补充第4题写完整计算过程，今晚完成、明天早上交。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"数学：完成《数格练习册》第34页第1—4题\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可先完成第1—3题，再重点检查第4题计算过程是否写完整。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《数格练习册》第34页第1—4题。\\\\n第34页第4题要把计算过程写完整，写在原题下面即可。\\\\n今晚完成，明天早上交。\\\\n提交要求：明天早上交练习册。\\",\\"origin_basis\\":{\\"message:synthetic-group:32\\":\\"ea83c17bd2b0487a735d0c6883b601abb9683299e912e88cb872db44af35bb34\\",\\"message:synthetic-group:33\\":\\"0a625a5ce52ed0be112be7dc3a47389c9d37b259ebf0eb97e5807a0dd4f7ac35\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第34页第1—4题，并补充第4题写完整计算过程，今晚完成、明天早上交。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"数学：完成《数格练习册》第34页第1—4题\\"}}"},{"id":"agent-befc35098fc6eaefaa1a36acf912f79c","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"英语：跟读Unit 4两遍并家长签字","body":"听录音跟读 Unit 4 A day at the lake 两遍。\\n读完请家长在记录本上签字。\\n今晚完成，明天早读检查记录本。","evidence":"[{\\"ref\\":\\"message:synthetic-group:34\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:22:00+08:00\\\\n英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。\\"}]","due":"","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。\\",\\"school_generated_snapshot\\":\\"6182c75a89f88d675efc43896d4616b20462e743698f05812ef7d437eb1e2e45\\",\\"school_goal_id\\":\\"goal-4aa066595907e486319200acadd6c92f\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"英语\\"},\\"school_messages\\":[{\\"message_id\\":\\"34\\",\\"source_id\\":\\"synthetic-group\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可跟读时注意模仿录音语音语调，读完后请家长及时签字。\\",\\"change\\":\\"new\\",\\"goal\\":\\"听录音跟读 Unit 4 A day at the lake 两遍。\\\\n读完请家长在记录本上签字。\\\\n今晚完成，明天早读检查记录本。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求听录音跟读Unit 4两遍，家长在记录本上签字，今晚完成、明天早读检查记录本。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早读检查记录本。\\",\\"target_id\\":\\"\\",\\"title\\":\\"英语：跟读Unit 4两遍并家长签字\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可跟读时注意模仿录音语音语调，读完后请家长及时签字。\\",\\"change\\":\\"new\\",\\"goal\\":\\"听录音跟读 Unit 4 A day at the lake 两遍。\\\\n读完请家长在记录本上签字。\\\\n今晚完成，明天早读检查记录本。\\",\\"origin_basis\\":{\\"message:synthetic-group:34\\":\\"df93255393090ec19138fc79b8c4638a8cbaea09a6e3df123ba4a169d13e5cbe\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求听录音跟读Unit 4两遍，家长在记录本上签字，今晚完成、明天早读检查记录本。 截止日期尚无法从原文核对，未采用模型日期；请核对原通知。\\",\\"state\\":\\"review\\",\\"submission\\":\\"明天早读检查记录本。\\",\\"target_id\\":\\"\\",\\"title\\":\\"英语：跟读Unit 4两遍并家长签字\\"}}"},{"id":"agent-dc6871c3e9008548adb7f63f9a36c6e3","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"交《秋季校园开放日回执》","body":"《秋季校园开放日回执》今晚请家长签字。\\n明天早上让孩子交给班主任。","evidence":"[{\\"ref\\":\\"message:synthetic-group:35\\",\\"text\\":\\"虚构班级 · 2026-10-19T17:10:00+08:00\\\\n《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。另外，明天来校带一个空透明塑料瓶，科学课用。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。\\",\\"school_generated_snapshot\\":\\"30f1448f014a9fc988fff7d1de6c45df8d34385baa9658c54703f095477b016f\\",\\"school_selection_receipt\\":{\\"advice\\":\\"可今晚请家长签字后，明早提醒孩子带回学校交给班主任。\\",\\"change\\":\\"new\\",\\"goal\\":\\"《秋季校园开放日回执》今晚请家长签字。\\\\n明天早上让孩子交给班主任。\\",\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求家长今晚签字，明天早上让孩子把回执交给班主任。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早上交给班主任。\\",\\"target_id\\":\\"\\",\\"title\\":\\"交《秋季校园开放日回执》\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可今晚请家长签字后，明早提醒孩子带回学校交给班主任。\\",\\"change\\":\\"new\\",\\"goal\\":\\"《秋季校园开放日回执》今晚请家长签字。\\\\n明天早上让孩子交给班主任。\\",\\"origin_basis\\":{\\"message:synthetic-group:35\\":\\"0b4b2fb729a2063e4de5fd530a372038b167c7576c5f80c586d8360d927f6e03\\"},\\"policy\\":10,\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求家长今晚签字，明天早上让孩子把回执交给班主任。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"target_id\\":\\"\\",\\"title\\":\\"交《秋季校园开放日回执》\\"}}"},{"id":"agent-dbb07e3fc13fb52fa2a4421ef38e9f6c","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"科学：带一个空透明塑料瓶","body":"明天来校带一个空透明塑料瓶，科学课用。","evidence":"[{\\"ref\\":\\"message:synthetic-group:35\\",\\"text\\":\\"虚构班级 · 2026-10-19T17:10:00+08:00\\\\n《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。另外，明天来校带一个空透明塑料瓶，科学课用。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"明天来校带一个空透明塑料瓶，科学课用。\\",\\"school_generated_snapshot\\":\\"f153fda3f0ed0b01ea3b32cef03b7c6315c4d39c066c8456c1a3c3107ffe7d87\\",\\"school_selection_receipt\\":{\\"advice\\":\\"可今晚把空透明塑料瓶放进书包，避免明早遗忘。\\",\\"change\\":\\"new\\",\\"goal\\":\\"明天来校带一个空透明塑料瓶，科学课用。\\",\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求明天来校带一个空透明塑料瓶，科学课用。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"科学：带一个空透明塑料瓶\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可今晚把空透明塑料瓶放进书包，避免明早遗忘。\\",\\"change\\":\\"new\\",\\"goal\\":\\"明天来校带一个空透明塑料瓶，科学课用。\\",\\"origin_basis\\":{\\"message:synthetic-group:35\\":\\"0b4b2fb729a2063e4de5fd530a372038b167c7576c5f80c586d8360d927f6e03\\"},\\"policy\\":10,\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求明天来校带一个空透明塑料瓶，科学课用。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"target_id\\":\\"\\",\\"title\\":\\"科学：带一个空透明塑料瓶\\"}}"},{"id":"agent-a6ac67047ccd475447a20d70f33c7191","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"参考资料：今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。","body":"按参考资料保留，不自动加入待办或学习目标；内容以原通知为准。","evidence":"[{\\"ref\\":\\"message:synthetic-group:36\\",\\"text\\":\\"虚构班级 · 2026-10-19T17:35:00+08:00\\\\n今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。\\"}]","due":"","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。\\",\\"school_generated_snapshot\\":\\"e7de01f44be8fc51b44c9a9e3ccfbcb400dea7c18738c289f2e9e8a396df0d0d\\",\\"school_selection_receipt\\":{\\"advice\\":\\"\\",\\"change\\":\\"new\\",\\"goal\\":\\"\\",\\"purpose\\":\\"optional\\",\\"reason\\":\\"该消息仅为本周课程进度说明，供家长了解，没有新增行动要求。\\",\\"state\\":\\"reference\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"\\",\\"change\\":\\"new\\",\\"goal\\":\\"\\",\\"origin_basis\\":{\\"message:synthetic-group:36\\":\\"3c7e4ff1c49cc9403747f0d3817f361d957ccc821ba475ca0d97e32a2f0d35a1\\"},\\"policy\\":10,\\"purpose\\":\\"optional\\",\\"reason\\":\\"该消息仅为本周课程进度说明，供家长了解，没有新增行动要求。\\",\\"state\\":\\"reference\\",\\"target_id\\":\\"\\",\\"title\\":\\"\\"}}"},{"id":"goal-abb032574f6a363eeb620734538938c2","job_id":"manual-goal:goal-abb032574f6a363eeb620734538938c2","child_id":"child-1","kind":"care","title":"数学：学校学习要求","body":"由学校学习要求启动，尚无孩子实际作答或掌握证据。","evidence":"[]","due":"","care_id":"","record_id":null,"state":"draft","created":"2026-10-18T10:44:35.631189+08:00","updated":"2026-10-18T10:44:35.631545+08:00","task_id":"","plan":"{\\"create_hash\\":\\"3dee7b5c8c329cd1948faadf87c75cc23b030821840b6d29dd4f656fa1c2e5fc\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"数学\\",\\"title\\":\\"数学：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"},{"id":"goal-47b93177aabb4f3f89a919a79121db81","job_id":"manual-goal:goal-47b93177aabb4f3f89a919a79121db81","child_id":"child-1","kind":"care","title":"语文：学校学习要求","body":"由学校学习要求启动，尚无孩子实际作答或掌握证据。","evidence":"[]","due":"","care_id":"","record_id":null,"state":"draft","created":"2026-10-18T10:44:35.633359+08:00","updated":"2026-10-18T10:44:35.633559+08:00","task_id":"","plan":"{\\"create_hash\\":\\"0540f0c432a8f4c71632edfd93a7d9abd06ffaad8e9869fc4c5f634946907d6e\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"语文\\",\\"title\\":\\"语文：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"},{"id":"goal-4aa066595907e486319200acadd6c92f","job_id":"manual-goal:goal-4aa066595907e486319200acadd6c92f","child_id":"child-1","kind":"care","title":"英语：学校学习要求","body":"由学校学习要求启动，尚无孩子实际作答或掌握证据。","evidence":"[]","due":"","care_id":"","record_id":null,"state":"draft","created":"2026-10-18T10:44:35.635592+08:00","updated":"2026-10-18T10:44:35.635785+08:00","task_id":"","plan":"{\\"create_hash\\":\\"cdb877951b0c9f31ba8e4a0dc3ef754b6ae2603ae3af950f8ee8dad9bbf40ed5\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"英语\\",\\"title\\":\\"英语：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"}],"agent_jobs":[{"id":"school-audit-boundary","fingerprint":"4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","attempts":0,"next_try":"","error":"","done":1},{"id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","fingerprint":"1727ad6974e376a1f0422b72749d8eac660aa1e985f38b8f9e48e5b969665dcd","attempts":1,"next_try":"","error":"","done":1},{"id":"messages:4c76661874cd89e0582545f5352a7674fddae18e","fingerprint":"98e4d2125c50c14d25faec5ed18b57334de88e14095eaec0dadf980a44bde493","attempts":1,"next_try":"","error":"","done":1}],"agent_messages":[{"source_id":"synthetic-group","id":"31","payload":"{\\"id\\":\\"31\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"31\\",\\"sender\\":\\"虚构语文许老师\\",\\"sender_id\\":\\"synthetic-unseen-cn-xu\\",\\"text\\":\\"今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。今晚完成，明天早上交。\\",\\"time\\":\\"2026-10-19T16:08:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"32","payload":"{\\"id\\":\\"32\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"32\\",\\"sender\\":\\"虚构数学魏老师\\",\\"sender_id\\":\\"synthetic-unseen-math-wei\\",\\"text\\":\\"数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。\\",\\"time\\":\\"2026-10-19T16:12:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"33","payload":"{\\"id\\":\\"33\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"33\\",\\"sender\\":\\"虚构数学魏老师\\",\\"sender_id\\":\\"synthetic-unseen-math-wei\\",\\"text\\":\\"补充一下，第34页第4题要把计算过程写完整，写在原题下面即可。\\",\\"time\\":\\"2026-10-19T16:13:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"34","payload":"{\\"id\\":\\"34\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"34\\",\\"sender\\":\\"虚构英语乔老师\\",\\"sender_id\\":\\"synthetic-unseen-en-qiao\\",\\"text\\":\\"英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。\\",\\"time\\":\\"2026-10-19T16:22:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"35","payload":"{\\"id\\":\\"35\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"35\\",\\"sender\\":\\"虚构班主任温老师\\",\\"sender_id\\":\\"synthetic-unseen-head-wen\\",\\"text\\":\\"《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。另外，明天来校带一个空透明塑料瓶，科学课用。\\",\\"time\\":\\"2026-10-19T17:10:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"36","payload":"{\\"id\\":\\"36\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"36\\",\\"sender\\":\\"虚构科学唐老师\\",\\"sender_id\\":\\"synthetic-unseen-science-tang\\",\\"text\\":\\"今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。\\",\\"time\\":\\"2026-10-19T17:35:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"37","payload":"{\\"id\\":\\"37\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"37\\",\\"sender\\":\\"虚构予澄家长\\",\\"sender_id\\":\\"synthetic-unseen-parent-yucheng\\",\\"text\\":\\"收到，谢谢老师。\\",\\"time\\":\\"2026-10-19T17:42:00+08:00\\",\\"unread\\":false}","processed":1}],"agent_runtime":[{"id":1,"state":"ready","last_run":"2026-10-19T20:06:00+08:00","last_error":""}],"agent_sources":[{"id":"synthetic-group","binding":"[\\"wechat\\",\\"child-1\\"]","cursor":"37","last_attempt":"2026-10-19T20:00:00+08:00","last_success":"2026-10-19T20:00:00+08:00","last_message_time":"2026-10-19T20:00:00+08:00","error":"","receipt":"d04ff71d4236874d76a2c413029e14e6a110419d448a31bf88c7113e9b18e40e","unread_count":0,"check_request":"{}"}]}')
KEYS = ('星芽', '数格', 'Unit 4', '回执', '塑料瓶')


class R259OldPendingRecoveryTests(unittest.TestCase):
    setUp = native.SchoolNativeCoverageTests.setUp

    def _old_store(self, change=None):
        self.now = self.fixture.now = dt.datetime(2026, 10, 19, 20, 30, tzinfo=agent.TZ)
        with self.store._db() as c:
            for table, rows in R259.items():
                c.execute('DELETE FROM ' + table)
                for row in rows:
                    c.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ','.join(row), ','.join('?' * len(row))), tuple(row.values()))
            if change: change(c)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)  # the upgraded program starts
        with self.store._db() as c:
            return {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}

    def _item(self, rows, key):
        return next(r for r in rows.values() if key in r['title'])

    def _rounds(self, count=5, start=0):
        created = 0
        for i in range(count):
            result = agent.run_once(self.app, self.now + dt.timedelta(minutes=6 * (start + i)))
            self.assertEqual(result['failed'], 0, result)
            created += result['created']
        return created

    def _listed(self, day):
        calendar = self.app.calendar_snapshot(day, day)
        return {x['task_id']: x for x in calendar['inbox'] if x['task_id']}

    def test_r259_untouched_reviews_are_collected_with_their_own_days_on_the_natural_round(self):
        before = self._old_store()
        with self.store._db() as c:
            jobs = [dict(r) for r in c.execute('SELECT * FROM agent_jobs ORDER BY id')]
            source = dict(c.execute('SELECT * FROM agent_sources').fetchone())
        self._rounds()
        self.assertEqual(self.model.call_count, 0, 'the stored receipt is read again; no model call')
        with self.store._db() as c:
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
            after = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
            self.assertEqual([dict(r) for r in c.execute('SELECT * FROM agent_jobs ORDER BY id')], jobs, 'no job, attempt or backoff reset')
            self.assertEqual(dict(c.execute('SELECT * FROM agent_sources').fetchone()), source, 'cursor kept')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages WHERE processed=1').fetchone()[0], 7)
        self.assertEqual(set(after), set(before), 'same item IDs, nothing new')
        named = {key: [t for t in tasks.values() if key in t['title']] for key in KEYS}
        for key, found in named.items():
            self.assertEqual(len(found), 1, (key, [t['title'] for t in tasks.values()]))
        self.assertEqual(len(tasks), 5)
        self.assertFalse(any('水的三种状态' in t['title'] + t['action'] for t in tasks.values()), 'course progress is no task')
        for key in KEYS:
            with self.subTest(item=key):
                old = self._item(before, key); new = after[old['id']]
                self.assertEqual((new['state'], new['task_id']), ('accepted', named[key][0]['id']))
                plan, old_plan = json.loads(new['plan']), json.loads(old['plan'])
                for field in ('school_selection_receipt', 'school_generated_snapshot', 'school_date_quote'):
                    self.assertEqual(plan.get(field), old_plan.get(field), field)
                self.assertEqual(plan['school_role_reselect']['previous_row'], old, 'the complete old row stays readable')
        expected = {'星芽': ('2026-10-19', '2026-10-20'), '数格': ('2026-10-19', '2026-10-20'), 'Unit 4': ('2026-10-19', '2026-10-20'),
                    '回执': ('2026-10-19', '2026-10-20'), '塑料瓶': ('', '2026-10-20')}

        def check():
            for day in ('2026-10-19', '2026-10-20'):
                listed = self._listed(day)
                for key, (complete, due) in expected.items():
                    with self.subTest(item=key, day=day):
                        agenda = listed[named[key][0]['id']]['agenda']
                        self.assertEqual((agenda['complete_on'], agenda['due_on']), (complete, due))
        check()
        self.assertEqual({t['due'] for t in tasks.values()}, {'2026-10-20'})
        self.assertNotIn('今晚', named['塑料瓶'][0]['action'])
        # Next rounds, a reopen and the same original batch again never collect twice.
        self.assertEqual(self._rounds(3, start=5), 0)
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        self.assertEqual(self._rounds(1, start=8), 0)
        with self.store._db() as c:
            self.assertEqual({r['id'] for r in c.execute('SELECT id FROM manual_tasks')}, set(tasks))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        self.assertEqual(self.model.call_count, 0)
        check()

    def test_touched_changed_or_rebound_reviews_keep_their_saved_state(self):
        def edit(c):  # a parent edit after generation
            c.execute("UPDATE agent_items SET title=title||'（家长改）' WHERE title LIKE '%Unit 4%'")
        def dismiss(c):
            c.execute("UPDATE agent_items SET state='dismissed' WHERE title LIKE '%Unit 4%'")
        def record(c):
            row = c.execute("SELECT id FROM agent_items WHERE title LIKE '%Unit 4%'").fetchone()
            c.execute("UPDATE agent_items SET record_id=1 WHERE id=?", (row['id'],))
        def source_changed(c):
            c.execute("UPDATE agent_messages SET payload=replace(payload,'两遍','三遍') WHERE id='34'")
        def rebound(c):  # the item now names another child than its source's binding
            c.execute("UPDATE agent_items SET child_id='child-2' WHERE title LIKE '%Unit 4%'")
        for name, change in dict(edit=edit, dismiss=dismiss, record=record, source_changed=source_changed, rebound=rebound).items():
            with self.subTest(case=name):
                self.setUp()
                before = self._old_store(change)
                for i in range(2): agent.run_once(self.app, self.now + dt.timedelta(minutes=6 * i))
                with self.store._db() as c:
                    after = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
                    titles = [r['title'] for r in c.execute('SELECT title FROM manual_tasks')]
                old = self._item(before, 'Unit 4')
                self.assertEqual(after[old['id']], old, 'kept exactly as saved')
                self.assertFalse(any('Unit 4' in t for t in titles), titles)
                self.assertEqual(self.model.call_count, 0)

    def test_a_past_day_never_revives(self):
        before = self._old_store()
        self.now = dt.datetime(2026, 10, 21, 8, tzinfo=agent.TZ)
        self._rounds(2)
        with self.store._db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
            after = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
        for key in KEYS:
            old = self._item(before, key)
            self.assertEqual((after[old['id']]['state'], after[old['id']]['due'], after[old['id']]['task_id']), (old['state'], old['due'], old['task_id']))
        self.assertEqual(self.model.call_count, 0)

    def test_a_change_while_the_round_waits_is_not_overwritten(self):
        before = self._old_store()
        old = self._item(before, 'Unit 4')
        self.assertTrue(hasattr(agent, '_school_role_reselect'), 'the stored-receipt reread exists')
        real = agent._school_role_reselect; calls = []
        def racing(store, c, row, *args, **kwargs):
            proof = real(store, c, row, *args, **kwargs)
            if row['id'] == old['id'] and proof and not calls:
                calls.append(1)
                with self.store._db() as other:
                    other.execute("UPDATE agent_items SET title=title||'（家长改）',updated=? WHERE id=?", ('2026-10-19T20:31:00+08:00', old['id']))
            return proof
        with patch.object(agent, '_school_role_reselect', side_effect=racing):
            agent.run_once(self.app, self.now)
        self.assertTrue(calls)
        with self.store._db() as c:
            row = dict(c.execute('SELECT * FROM agent_items WHERE id=?', (old['id'],)).fetchone())
            titles = [r['title'] for r in c.execute('SELECT title FROM manual_tasks')]
        self.assertEqual((row['state'], row['task_id'], row['due']), ('pending', None, ''))
        self.assertTrue(row['title'].endswith('（家长改）'))
        self.assertFalse(any('Unit 4' in t for t in titles), titles)


if __name__ == '__main__':
    unittest.main()

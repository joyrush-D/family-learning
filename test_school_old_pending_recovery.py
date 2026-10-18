"""The fictional Flash27 day as the r259 program (f0941d0) saved it: five untouched pending reviews and no task.

The rows are the unchanged output of f0941d0 for the HANDOFF 7 originals and the actual Flash27 reply on a fresh fictional
store (no real model, collector or device). The current program reads them again on its ordinary run_once, without a
model call: an item whose unchanged original, generated snapshot and selection receipt prove its own day is collected
on the existing acceptance path; anything a parent, a link, a later change or a past day touched keeps its saved state.
"""
import copy
import datetime as dt
import json
import os
import unittest
from unittest.mock import patch

import family_agent as agent
import test_school_native_coverage as native

# agent_items/agent_jobs/agent_messages/agent_runtime/agent_sources exactly as f0941d0 left them after its two rounds.
R259 = json.loads('{"agent_items":[{"id":"agent-1c43a0b386dab94a2dee77228c79eac7","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"语文：完成《星芽阅读练习册》第28页第1、2题","body":"完成《星芽阅读练习册》第28页第1、2题。\\n答案写在练习册上。\\n今晚完成，明天早上交。\\n提交要求：明天早上交练习册。","evidence":"[{\\"ref\\":\\"message:synthetic-group:31\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:08:00+08:00\\\\n今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。今晚完成，明天早上交。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。\\",\\"school_generated_snapshot\\":\\"df77e1f408f676d4c3620de07b11aa0152ce3abc3fea74b3e3b15c25c34ead1d\\",\\"school_goal_id\\":\\"goal-47b93177aabb4f3f89a919a79121db81\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"语文\\"},\\"school_messages\\":[{\\"message_id\\":\\"31\\",\\"source_id\\":\\"synthetic-group\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可先读题再作答，完成后自查是否两题都已写在练习册上。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《星芽阅读练习册》第28页第1、2题。\\\\n答案写在练习册上。\\\\n今晚完成，明天早上交。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第28页第1、2题，答案写在练习册上，今晚完成、明天早上交。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：完成《星芽阅读练习册》第28页第1、2题\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可先读题再作答，完成后自查是否两题都已写在练习册上。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《星芽阅读练习册》第28页第1、2题。\\\\n答案写在练习册上。\\\\n今晚完成，明天早上交。\\\\n提交要求：明天早上交练习册。\\",\\"origin_basis\\":{\\"message:synthetic-group:31\\":\\"c8a8ad49b96ad075e1f52346591b4b9f47257792b5f322b66e2aea96264e9591\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第28页第1、2题，答案写在练习册上，今晚完成、明天早上交。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"语文：完成《星芽阅读练习册》第28页第1、2题\\"}}"},{"id":"agent-06c2fbf8b13789ebaa6f320b4406adea","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"数学：完成《数格练习册》第34页第1—4题","body":"完成《数格练习册》第34页第1—4题。\\n第34页第4题要把计算过程写完整，写在原题下面即可。\\n今晚完成，明天早上交。\\n提交要求：明天早上交练习册。","evidence":"[{\\"ref\\":\\"message:synthetic-group:32\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:12:00+08:00\\\\n数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。\\"},{\\"ref\\":\\"message:synthetic-group:33\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:13:00+08:00\\\\n补充一下，第34页第4题要把计算过程写完整，写在原题下面即可。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。\\",\\"school_generated_snapshot\\":\\"e0e06810185df3fad516e0c899118b382828de32535d37c77656232fcd473d55\\",\\"school_goal_id\\":\\"goal-abb032574f6a363eeb620734538938c2\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"数学\\"},\\"school_messages\\":[{\\"message_id\\":\\"32\\",\\"source_id\\":\\"synthetic-group\\"},{\\"message_id\\":\\"33\\",\\"source_id\\":\\"synthetic-group\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可先完成第1—3题，再重点检查第4题计算过程是否写完整。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《数格练习册》第34页第1—4题。\\\\n第34页第4题要把计算过程写完整，写在原题下面即可。\\\\n今晚完成，明天早上交。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第34页第1—4题，并补充第4题写完整计算过程，今晚完成、明天早上交。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"数学：完成《数格练习册》第34页第1—4题\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可先完成第1—3题，再重点检查第4题计算过程是否写完整。\\",\\"change\\":\\"new\\",\\"goal\\":\\"完成《数格练习册》第34页第1—4题。\\\\n第34页第4题要把计算过程写完整，写在原题下面即可。\\\\n今晚完成，明天早上交。\\\\n提交要求：明天早上交练习册。\\",\\"origin_basis\\":{\\"message:synthetic-group:32\\":\\"ea83c17bd2b0487a735d0c6883b601abb9683299e912e88cb872db44af35bb34\\",\\"message:synthetic-group:33\\":\\"0a625a5ce52ed0be112be7dc3a47389c9d37b259ebf0eb97e5807a0dd4f7ac35\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求完成练习册第34页第1—4题，并补充第4题写完整计算过程，今晚完成、明天早上交。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"submission\\":\\"明天早上交练习册。\\",\\"target_id\\":\\"\\",\\"title\\":\\"数学：完成《数格练习册》第34页第1—4题\\"}}"},{"id":"agent-befc35098fc6eaefaa1a36acf912f79c","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"英语：跟读Unit 4两遍并家长签字","body":"听录音跟读 Unit 4 A day at the lake 两遍。\\n读完请家长在记录本上签字。\\n今晚完成，明天早读检查记录本。","evidence":"[{\\"ref\\":\\"message:synthetic-group:34\\",\\"text\\":\\"虚构班级 · 2026-10-19T16:22:00+08:00\\\\n英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。\\"}]","due":"","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。\\",\\"school_generated_snapshot\\":\\"6182c75a89f88d675efc43896d4616b20462e743698f05812ef7d437eb1e2e45\\",\\"school_goal_id\\":\\"goal-4aa066595907e486319200acadd6c92f\\",\\"school_learning\\":{\\"goal_id\\":\\"\\",\\"subject\\":\\"英语\\"},\\"school_messages\\":[{\\"message_id\\":\\"34\\",\\"source_id\\":\\"synthetic-group\\"}],\\"school_selection_receipt\\":{\\"advice\\":\\"可跟读时注意模仿录音语音语调，读完后请家长及时签字。\\",\\"change\\":\\"new\\",\\"goal\\":\\"听录音跟读 Unit 4 A day at the lake 两遍。\\\\n读完请家长在记录本上签字。\\\\n今晚完成，明天早读检查记录本。\\",\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求听录音跟读Unit 4两遍，家长在记录本上签字，今晚完成、明天早读检查记录本。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早读检查记录本。\\",\\"target_id\\":\\"\\",\\"title\\":\\"英语：跟读Unit 4两遍并家长签字\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可跟读时注意模仿录音语音语调，读完后请家长及时签字。\\",\\"change\\":\\"new\\",\\"goal\\":\\"听录音跟读 Unit 4 A day at the lake 两遍。\\\\n读完请家长在记录本上签字。\\\\n今晚完成，明天早读检查记录本。\\",\\"origin_basis\\":{\\"message:synthetic-group:34\\":\\"df93255393090ec19138fc79b8c4638a8cbaea09a6e3df123ba4a169d13e5cbe\\"},\\"policy\\":10,\\"purpose\\":\\"learning\\",\\"reason\\":\\"已读文字明确要求听录音跟读Unit 4两遍，家长在记录本上签字，今晚完成、明天早读检查记录本。 截止日期尚无法从原文核对，未采用模型日期；请核对原通知。\\",\\"state\\":\\"review\\",\\"submission\\":\\"明天早读检查记录本。\\",\\"target_id\\":\\"\\",\\"title\\":\\"英语：跟读Unit 4两遍并家长签字\\"}}"},{"id":"agent-dc6871c3e9008548adb7f63f9a36c6e3","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"交《秋季校园开放日回执》","body":"《秋季校园开放日回执》今晚请家长签字。\\n明天早上让孩子交给班主任。","evidence":"[{\\"ref\\":\\"message:synthetic-group:35\\",\\"text\\":\\"虚构班级 · 2026-10-19T17:10:00+08:00\\\\n《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。另外，明天来校带一个空透明塑料瓶，科学课用。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。\\",\\"school_generated_snapshot\\":\\"30f1448f014a9fc988fff7d1de6c45df8d34385baa9658c54703f095477b016f\\",\\"school_selection_receipt\\":{\\"advice\\":\\"可今晚请家长签字后，明早提醒孩子带回学校交给班主任。\\",\\"change\\":\\"new\\",\\"goal\\":\\"《秋季校园开放日回执》今晚请家长签字。\\\\n明天早上让孩子交给班主任。\\",\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求家长今晚签字，明天早上让孩子把回执交给班主任。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"明天早上交给班主任。\\",\\"target_id\\":\\"\\",\\"title\\":\\"交《秋季校园开放日回执》\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可今晚请家长签字后，明早提醒孩子带回学校交给班主任。\\",\\"change\\":\\"new\\",\\"goal\\":\\"《秋季校园开放日回执》今晚请家长签字。\\\\n明天早上让孩子交给班主任。\\",\\"origin_basis\\":{\\"message:synthetic-group:35\\":\\"0b4b2fb729a2063e4de5fd530a372038b167c7576c5f80c586d8360d927f6e03\\"},\\"policy\\":10,\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求家长今晚签字，明天早上让孩子把回执交给班主任。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"target_id\\":\\"\\",\\"title\\":\\"交《秋季校园开放日回执》\\"}}"},{"id":"agent-dbb07e3fc13fb52fa2a4421ef38e9f6c","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"科学：带一个空透明塑料瓶","body":"明天来校带一个空透明塑料瓶，科学课用。","evidence":"[{\\"ref\\":\\"message:synthetic-group:35\\",\\"text\\":\\"虚构班级 · 2026-10-19T17:10:00+08:00\\\\n《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。另外，明天来校带一个空透明塑料瓶，科学课用。\\"}]","due":"2026-10-20","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"明天来校带一个空透明塑料瓶，科学课用。\\",\\"school_generated_snapshot\\":\\"f153fda3f0ed0b01ea3b32cef03b7c6315c4d39c066c8456c1a3c3107ffe7d87\\",\\"school_selection_receipt\\":{\\"advice\\":\\"可今晚把空透明塑料瓶放进书包，避免明早遗忘。\\",\\"change\\":\\"new\\",\\"goal\\":\\"明天来校带一个空透明塑料瓶，科学课用。\\",\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求明天来校带一个空透明塑料瓶，科学课用。\\",\\"state\\":\\"ready\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"科学：带一个空透明塑料瓶\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"可今晚把空透明塑料瓶放进书包，避免明早遗忘。\\",\\"change\\":\\"new\\",\\"goal\\":\\"明天来校带一个空透明塑料瓶，科学课用。\\",\\"origin_basis\\":{\\"message:synthetic-group:35\\":\\"0b4b2fb729a2063e4de5fd530a372038b167c7576c5f80c586d8360d927f6e03\\"},\\"policy\\":10,\\"purpose\\":\\"admin\\",\\"reason\\":\\"已读文字明确要求明天来校带一个空透明塑料瓶，科学课用。 原通知含多个日期，已按原文取2026-10-20；请核对这一天是否属于本事项。\\",\\"state\\":\\"review\\",\\"target_id\\":\\"\\",\\"title\\":\\"科学：带一个空透明塑料瓶\\"}}"},{"id":"agent-a6ac67047ccd475447a20d70f33c7191","job_id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","child_id":"child-1","kind":"school","title":"参考资料：今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。","body":"按参考资料保留，不自动加入待办或学习目标；内容以原通知为准。","evidence":"[{\\"ref\\":\\"message:synthetic-group:36\\",\\"text\\":\\"虚构班级 · 2026-10-19T17:35:00+08:00\\\\n今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。\\"}]","due":"","care_id":"","record_id":null,"state":"pending","created":"2026-10-19T20:00:00+08:00","updated":"2026-10-19T20:00:00+08:00","task_id":"","plan":"{\\"school_date_quote\\":\\"今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。\\",\\"school_generated_snapshot\\":\\"e7de01f44be8fc51b44c9a9e3ccfbcb400dea7c18738c289f2e9e8a396df0d0d\\",\\"school_selection_receipt\\":{\\"advice\\":\\"\\",\\"change\\":\\"new\\",\\"goal\\":\\"\\",\\"purpose\\":\\"optional\\",\\"reason\\":\\"该消息仅为本周课程进度说明，供家长了解，没有新增行动要求。\\",\\"state\\":\\"reference\\",\\"submission\\":\\"\\",\\"target_id\\":\\"\\",\\"title\\":\\"\\"},\\"school_selection_revision\\":2,\\"school_task\\":{\\"advice\\":\\"\\",\\"change\\":\\"new\\",\\"goal\\":\\"\\",\\"origin_basis\\":{\\"message:synthetic-group:36\\":\\"3c7e4ff1c49cc9403747f0d3817f361d957ccc821ba475ca0d97e32a2f0d35a1\\"},\\"policy\\":10,\\"purpose\\":\\"optional\\",\\"reason\\":\\"该消息仅为本周课程进度说明，供家长了解，没有新增行动要求。\\",\\"state\\":\\"reference\\",\\"target_id\\":\\"\\",\\"title\\":\\"\\"}}"},{"id":"goal-abb032574f6a363eeb620734538938c2","job_id":"manual-goal:goal-abb032574f6a363eeb620734538938c2","child_id":"child-1","kind":"care","title":"数学：学校学习要求","body":"由学校学习要求启动，尚无孩子实际作答或掌握证据。","evidence":"[]","due":"","care_id":"","record_id":null,"state":"draft","created":"2026-10-18T10:44:35.631189+08:00","updated":"2026-10-18T10:44:35.631545+08:00","task_id":"","plan":"{\\"create_hash\\":\\"3dee7b5c8c329cd1948faadf87c75cc23b030821840b6d29dd4f656fa1c2e5fc\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"数学\\",\\"title\\":\\"数学：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"},{"id":"goal-47b93177aabb4f3f89a919a79121db81","job_id":"manual-goal:goal-47b93177aabb4f3f89a919a79121db81","child_id":"child-1","kind":"care","title":"语文：学校学习要求","body":"由学校学习要求启动，尚无孩子实际作答或掌握证据。","evidence":"[]","due":"","care_id":"","record_id":null,"state":"draft","created":"2026-10-18T10:44:35.633359+08:00","updated":"2026-10-18T10:44:35.633559+08:00","task_id":"","plan":"{\\"create_hash\\":\\"0540f0c432a8f4c71632edfd93a7d9abd06ffaad8e9869fc4c5f634946907d6e\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"语文\\",\\"title\\":\\"语文：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"},{"id":"goal-4aa066595907e486319200acadd6c92f","job_id":"manual-goal:goal-4aa066595907e486319200acadd6c92f","child_id":"child-1","kind":"care","title":"英语：学校学习要求","body":"由学校学习要求启动，尚无孩子实际作答或掌握证据。","evidence":"[]","due":"","care_id":"","record_id":null,"state":"draft","created":"2026-10-18T10:44:35.635592+08:00","updated":"2026-10-18T10:44:35.635785+08:00","task_id":"","plan":"{\\"create_hash\\":\\"cdb877951b0c9f31ba8e4a0dc3ef754b6ae2603ae3af950f8ee8dad9bbf40ed5\\",\\"goal_history\\":[],\\"goal_version\\":1,\\"learning\\":{\\"baseline\\":\\"由学校学习要求启动，尚无孩子实际作答或掌握证据。\\",\\"curriculum\\":\\"\\",\\"hypotheses\\":\\"\\",\\"record_ids\\":[],\\"resources\\":\\"\\",\\"school_target\\":\\"\\",\\"subject\\":\\"英语\\",\\"title\\":\\"英语：学校学习要求\\",\\"verification\\":\\"\\"},\\"lifecycle\\":\\"active\\",\\"school_origin\\":true}"}],"agent_jobs":[{"id":"school-audit-boundary","fingerprint":"4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","attempts":0,"next_try":"","error":"","done":1},{"id":"messages:e7c6a7be36ff367525bef0b1a0fbea3a6969402a","fingerprint":"1727ad6974e376a1f0422b72749d8eac660aa1e985f38b8f9e48e5b969665dcd","attempts":1,"next_try":"","error":"","done":1},{"id":"messages:4c76661874cd89e0582545f5352a7674fddae18e","fingerprint":"98e4d2125c50c14d25faec5ed18b57334de88e14095eaec0dadf980a44bde493","attempts":1,"next_try":"","error":"","done":1}],"agent_messages":[{"source_id":"synthetic-group","id":"31","payload":"{\\"id\\":\\"31\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"31\\",\\"sender\\":\\"虚构语文许老师\\",\\"sender_id\\":\\"synthetic-unseen-cn-xu\\",\\"text\\":\\"今天语文作业：《星芽阅读练习册》第28页第1、2题，答案写在练习册上。今晚完成，明天早上交。\\",\\"time\\":\\"2026-10-19T16:08:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"32","payload":"{\\"id\\":\\"32\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"32\\",\\"sender\\":\\"虚构数学魏老师\\",\\"sender_id\\":\\"synthetic-unseen-math-wei\\",\\"text\\":\\"数学作业是《数格练习册》第34页第1—4题，今晚完成，明天早上交。\\",\\"time\\":\\"2026-10-19T16:12:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"33","payload":"{\\"id\\":\\"33\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"33\\",\\"sender\\":\\"虚构数学魏老师\\",\\"sender_id\\":\\"synthetic-unseen-math-wei\\",\\"text\\":\\"补充一下，第34页第4题要把计算过程写完整，写在原题下面即可。\\",\\"time\\":\\"2026-10-19T16:13:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"34","payload":"{\\"id\\":\\"34\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"34\\",\\"sender\\":\\"虚构英语乔老师\\",\\"sender_id\\":\\"synthetic-unseen-en-qiao\\",\\"text\\":\\"英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。\\",\\"time\\":\\"2026-10-19T16:22:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"35","payload":"{\\"id\\":\\"35\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"35\\",\\"sender\\":\\"虚构班主任温老师\\",\\"sender_id\\":\\"synthetic-unseen-head-wen\\",\\"text\\":\\"《秋季校园开放日回执》今晚请家长签字，明天早上让孩子交给班主任。另外，明天来校带一个空透明塑料瓶，科学课用。\\",\\"time\\":\\"2026-10-19T17:10:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"36","payload":"{\\"id\\":\\"36\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"36\\",\\"sender\\":\\"虚构科学唐老师\\",\\"sender_id\\":\\"synthetic-unseen-science-tang\\",\\"text\\":\\"今天科学课学完了“水的三种状态”，课堂演示也结束了。这是本周的课程进度，供家长了解。\\",\\"time\\":\\"2026-10-19T17:35:00+08:00\\",\\"unread\\":false}","processed":1},{"source_id":"synthetic-group","id":"37","payload":"{\\"id\\":\\"37\\",\\"kind\\":\\"text\\",\\"message_order\\":\\"37\\",\\"sender\\":\\"虚构予澄家长\\",\\"sender_id\\":\\"synthetic-unseen-parent-yucheng\\",\\"text\\":\\"收到，谢谢老师。\\",\\"time\\":\\"2026-10-19T17:42:00+08:00\\",\\"unread\\":false}","processed":1}],"agent_runtime":[{"id":1,"state":"ready","last_run":"2026-10-19T20:06:00+08:00","last_error":""}],"agent_sources":[{"id":"synthetic-group","binding":"[\\"wechat\\",\\"child-1\\"]","cursor":"37","last_attempt":"2026-10-19T20:00:00+08:00","last_success":"2026-10-19T20:00:00+08:00","last_message_time":"2026-10-19T20:00:00+08:00","error":"","receipt":"d04ff71d4236874d76a2c413029e14e6a110419d448a31bf88c7113e9b18e40e","unread_count":0,"check_request":"{}"}]}')
KEYS = ('星芽', '数格', 'Unit 4', '回执', '塑料瓶')
UNKNOWN = 'Unit 4'  # saved with due cleared and no model day in its receipt: its original model day is unknown
RECOVERED = tuple(k for k in KEYS if k != UNKNOWN)


class R259OldPendingRecoveryTests(unittest.TestCase):
    def setUp(self):
        native.SchoolNativeCoverageTests.setUp(self)
        # No model is configured here (no model.json, no FAMILY_LLM_* environment): these rounds are the zero-model boundary.
        self.stack.enter_context(patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('FAMILY_LLM_')}, clear=True))

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
            self.assertEqual(len(found), 0 if key == UNKNOWN else 1, (key, [t['title'] for t in tasks.values()]))
        self.assertEqual(len(tasks), 4)
        # English 34 was saved with its due cleared and a receipt that kept no model day: the original model day is
        # unknown (a rejected contradiction looks the same), so it stays exactly as saved for the parent's review.
        unknown = self._item(before, UNKNOWN)
        self.assertEqual(after[unknown['id']], unknown, 'kept exactly as saved; no due, no task')
        self.assertIn('未采用模型日期', json.loads(unknown['plan'])['school_task']['reason'])
        self.assertFalse(any('水的三种状态' in t['title'] + t['action'] for t in tasks.values()), 'course progress is no task')
        for key in RECOVERED:
            with self.subTest(item=key):
                old = self._item(before, key); new = after[old['id']]
                self.assertEqual((new['state'], new['task_id']), ('accepted', named[key][0]['id']))
                plan, old_plan = json.loads(new['plan']), json.loads(old['plan'])
                for field in ('school_selection_receipt', 'school_generated_snapshot', 'school_date_quote'):
                    self.assertEqual(plan.get(field), old_plan.get(field), field)
                self.assertEqual(plan['school_role_reselect']['previous_row'], old, 'the complete old row stays readable')
        expected = {'星芽': ('2026-10-19', '2026-10-20'), '数格': ('2026-10-19', '2026-10-20'),
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
            self.assertEqual(dict(c.execute('SELECT * FROM agent_items WHERE id=?', (unknown['id'],)).fetchone()), unknown)
        self.assertEqual(self.model.call_count, 0)
        check()

    def test_touched_changed_or_rebound_reviews_keep_their_saved_state(self):
        def edit(c):  # a parent edit after generation
            c.execute("UPDATE agent_items SET title=title||'（家长改）' WHERE title LIKE '%星芽%'")
        def dismiss(c):
            c.execute("UPDATE agent_items SET state='dismissed' WHERE title LIKE '%星芽%'")
        def record(c):
            row = c.execute("SELECT id FROM agent_items WHERE title LIKE '%星芽%'").fetchone()
            c.execute("UPDATE agent_items SET record_id=1 WHERE id=?", (row['id'],))
        def source_changed(c):
            c.execute("UPDATE agent_messages SET payload=replace(payload,'第28页','第29页') WHERE id='31'")
        def rebound(c):  # the item now names another child than its source's binding
            c.execute("UPDATE agent_items SET child_id='child-2' WHERE title LIKE '%星芽%'")
        for name, change in dict(edit=edit, dismiss=dismiss, record=record, source_changed=source_changed, rebound=rebound).items():
            with self.subTest(case=name):
                self.setUp()
                before = self._old_store(change)
                for i in range(2): agent.run_once(self.app, self.now + dt.timedelta(minutes=6 * i))
                with self.store._db() as c:
                    after = {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
                    titles = [r['title'] for r in c.execute('SELECT title FROM manual_tasks')]
                old = self._item(before, '星芽')
                self.assertEqual(after[old['id']], old, 'kept exactly as saved')
                self.assertFalse(any('星芽' in t for t in titles), titles)
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
        old = self._item(before, '星芽')
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
        self.assertEqual((row['state'], row['task_id'], row['due']), ('pending', old['task_id'], old['due']))
        self.assertTrue(row['title'].endswith('（家长改）'))
        self.assertFalse(any('星芽' in t for t in titles), titles)

    def _saved(self):
        with self.store._db() as c:
            return ({r['id']: dict(r) for r in c.execute('SELECT * FROM agent_items')},
                    [dict(r) for r in c.execute('SELECT * FROM agent_jobs ORDER BY id')],
                    [dict(r) for r in c.execute('SELECT * FROM agent_sources ORDER BY id')],
                    c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0])

    def _resumed(self, start):
        # The unpaused control: the same untouched rows are collected once and never twice.
        self.source['enabled'] = True; self.fixture.config(enabled=True)
        self.assertEqual(self._rounds(5, start=start), 4)
        self.assertEqual(self._rounds(3, start=start + 5), 0)
        with self.store._db() as c:
            titles = [r['title'] for r in c.execute('SELECT title FROM manual_tasks')]
        self.assertEqual([sum(key in t for t in titles) for key in KEYS], [0 if key == UNKNOWN else 1 for key in KEYS], titles)
        self.assertEqual(len(titles), 4)
        self.assertEqual(self.model.call_count, 0)

    def test_a_paused_source_or_agent_keeps_every_saved_review_verbatim(self):
        for case in ('source', 'agent'):
            with self.subTest(case=case):
                self.setUp()
                self._old_store()
                if case == 'source': self.source['enabled'] = False
                self.fixture.config(enabled=case != 'agent')
                before = self._saved()
                for i in range(5): agent.run_once(self.app, self.now + dt.timedelta(minutes=6 * i))
                self.assertEqual(self._saved(), before, 'every saved row, job and cursor kept; no task')
                self.assertEqual(self.model.call_count, 0)
                self._resumed(5)

    def test_a_pause_between_proof_and_save_writes_nothing(self):
        for case in ('source', 'agent'):
            with self.subTest(case=case):
                self.setUp()
                self._old_store()
                before = self._saved()
                real = agent._school_role_reselect; calls = []
                def racing(store, c, row, *args, **kwargs):
                    proof = real(store, c, row, *args, **kwargs)
                    if proof and not calls:  # proven while authorized, paused before the save
                        calls.append(row['id'])
                        if case == 'source': self.source['enabled'] = False
                        self.fixture.config(enabled=case != 'agent')
                    return proof
                with patch.object(agent, '_school_role_reselect', side_effect=racing):
                    agent.run_once(self.app, self.now)
                self.assertTrue(calls, 'the proof was made before the pause')
                self.assertEqual(self._saved(), before, 'nothing written after the pause')
                self.assertEqual(self.model.call_count, 0)
                self._resumed(1)


ENGLISH_REF = 'message:synthetic-group:34'
# A fictional new receipt for English 34 in the existing saved-reread reply shape; the transport is mocked, no request.
NEW_RECEIPT = dict(title='英语：跟读Unit 4两遍并家长签字',
                   goal='听录音跟读 Unit 4 A day at the lake 两遍。\n读完请家长在记录本上签字。\n今晚完成，明天早读检查记录本。',
                   advice='跟读时可模仿录音语调，读完请家长及时签字。', state='ready',
                   reason='虚构新回执：原文写明跟读两遍、家长签字，今晚完成、明天早读检查记录本。', change='new', target_id='',
                   purpose='learning', submission='明天早读检查记录本。', learning_subject='英语', learning_goal_id='')
BAD_RECEIPTS = dict(  # each is a new reply that does not support the item itself; none may collect it
    other_check_day=dict(NEW_RECEIPT, goal=NEW_RECEIPT['goal'].replace('明天早读', '后天早读'), submission='后天早读检查记录本。'),
    other_completion_day=dict(NEW_RECEIPT, goal=NEW_RECEIPT['goal'].replace('今晚完成', '明晚完成')),
    no_day=dict(NEW_RECEIPT, goal='听录音跟读 Unit 4 A day at the lake 两遍。\n读完请家长在记录本上签字。', submission=''),
    check_as_handback=dict(NEW_RECEIPT, goal=NEW_RECEIPT['goal'].replace('明天早读检查记录本', '明天早上交记录本'), submission='明天早上交记录本。'),
    other_purpose=dict(NEW_RECEIPT, purpose='admin', learning_subject=''),
    other_subject=dict(NEW_RECEIPT, learning_subject='语文'),
    still_review=dict(NEW_RECEIPT, state='review', reason='虚构：仍待核对。'),
)
FICTIONAL_MODEL = dict(base_url='http://127.0.0.1:9/v1', model='synthetic-reread-model', api_key='', reasoning_effort='')


class R259ClearedDateRereadTests(unittest.TestCase):
    """English 34: its old program cleared the day and kept no model day, so only a new receipt may collect it.

    The ordinary run_once reads it once more through the existing saved-reread caller (its own school-task job, the batch's
    shared recovery budget, the round's one refresh call), with a configured fictional model whose transport is mocked.
    The new receipt itself must keep the item's purpose and subject and state the original's own days; the lost old model
    day is never guessed and the four rows the stored receipts already proved are not rebuilt.
    """

    def setUp(self):
        R259OldPendingRecoveryTests.setUp(self)
        (self.fixture.data / 'model.json').write_text(json.dumps(FICTIONAL_MODEL))
        self.calls = []

    _old_store = R259OldPendingRecoveryTests._old_store
    _item = R259OldPendingRecoveryTests._item
    _listed = R259OldPendingRecoveryTests._listed
    _saved = R259OldPendingRecoveryTests._saved

    def _replies(self, *replies, during=None):
        def model(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual(name, 'family_school_task', 'only the existing saved-reread caller')
            self.assertEqual(data_path, self.app.DATA)
            context = json.loads(messages[-1]['content'])
            self.assertEqual([e['ref'] for e in context['evidence']], [ENGLISH_REF], 'only the English original is read again')
            self.calls.append(context)
            self.assertLessEqual(len(self.calls), len(replies), 'no further model request')
            if during: during()
            reply = replies[len(self.calls) - 1]
            if isinstance(reply, Exception): raise reply
            return copy.deepcopy(reply)
        self.model.side_effect = model

    def _at(self, minutes):
        return agent.run_once(self.app, self.now + dt.timedelta(minutes=minutes))

    def _state(self):
        with self.store._db() as c:
            return (dict(c.execute('SELECT * FROM agent_sources').fetchone()),
                    [dict(r) for r in c.execute('SELECT * FROM agent_messages ORDER BY rowid')],
                    {r['id']: dict(r) for r in c.execute('SELECT * FROM agent_jobs')},
                    {r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")},
                    {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')})

    def _english_kept(self, before):
        """English 34 is exactly as saved and has no task; the four proven rows are still collected once each."""
        unknown = self._item(before, UNKNOWN)
        source, messages, jobs, items, tasks = self._state()
        self.assertEqual(items[unknown['id']], unknown, 'old row, unknown day and receipt kept verbatim')
        titles = [t['title'] for t in tasks.values()]
        self.assertEqual([sum(key in t for t in titles) for key in KEYS], [0 if key == UNKNOWN else 1 for key in KEYS], titles)
        return jobs.get('school-task:' + unknown['id'])

    def test_a_new_receipt_collects_the_cleared_english_once_under_its_original_id(self):
        before = self._old_store()
        unknown = self._item(before, UNKNOWN)
        source, messages, jobs, _, _ = self._state()
        self._replies(NEW_RECEIPT)
        first = self._at(0)
        self.assertEqual((first['failed'], first['created']), (0, 5), first)
        self.assertEqual(len(self.calls), 1, 'one new ordinary call of the existing saved-reread caller')
        self.assertEqual(self.calls[0]['as_of'], '2026-10-19')
        # Later rounds and a reopen never read or collect it again.
        self.model.side_effect = AssertionError('no second reread')
        self.assertEqual([self._at(6 * i)['created'] for i in range(1, 4)], [0, 0, 0])
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        self.assertEqual(self._at(30)['created'], 0)
        now_source, now_messages, now_jobs, after, tasks = self._state()
        self.assertEqual((now_source, now_messages), (source, messages), 'cursor and originals kept')
        self.assertEqual(set(after), set(before), 'same item IDs, nothing new')
        named = {key: [t for t in tasks.values() if key in t['title']] for key in KEYS}
        self.assertEqual({key: len(found) for key, found in named.items()}, {key: 1 for key in KEYS})
        self.assertEqual(len(tasks), 5)
        english = after[unknown['id']]
        self.assertEqual((english['state'], english['task_id'], english['due']), ('accepted', named[UNKNOWN][0]['id'], '2026-10-20'))
        plan, old_plan = json.loads(english['plan']), json.loads(unknown['plan'])
        for field in ('school_selection_receipt', 'school_generated_snapshot', 'school_date_quote'):
            self.assertEqual(plan.get(field), old_plan.get(field), field)
        self.assertEqual(plan['school_saved_reread']['previous_row'], unknown, 'the complete old row stays readable')
        self.assertEqual(plan['school_saved_reread']['previous'], agent._hash(unknown))
        self.assertNotIn('school_role_reselect', plan, 'the lost old model day is never guessed')
        self.assertEqual((plan['school_task']['state'], plan['school_task']['purpose'], plan['school_learning']['subject']), ('ready', 'learning', '英语'))
        for key in RECOVERED:  # the zero-model recovery of the four saved days is not rebuilt by the reread
            old = self._item(before, key)
            kept = json.loads(after[old['id']]['plan'])
            self.assertEqual(kept['school_role_reselect']['previous_row'], old)
            self.assertNotIn('school_saved_reread', kept)
        key = 'school-task:' + unknown['id']
        self.assertEqual({k: v for k, v in now_jobs.items() if k != key}, jobs, 'the original receipts are untouched')
        self.assertEqual((now_jobs[key]['done'], now_jobs[key]['attempts'], now_jobs[key]['error']), (1, 1, ''))
        expected = {'星芽': ('2026-10-19', '2026-10-20', 'homework'), '数格': ('2026-10-19', '2026-10-20', 'homework'),
                    'Unit 4': ('2026-10-19', '2026-10-20', 'homework'), '回执': ('2026-10-19', '2026-10-20', 'todo'),
                    '塑料瓶': ('', '2026-10-20', 'todo')}
        # Each item's own handback words stay its own: 语文/数学 hand their workbooks in, the receipt goes to the head teacher,
        # the bottle is brought; English is only checked on the 20th, never turned into a handback.
        handback = {'星芽': '明天早上交练习册', '数格': '明天早上交练习册', '回执': '明天早上让孩子交给班主任', '塑料瓶': '明天来校带'}
        for day in ('2026-10-19', '2026-10-20'):
            listed = self._listed(day)
            for k, (complete, due, category) in expected.items():
                with self.subTest(item=k, day=day):
                    agenda = listed[named[k][0]['id']]['agenda']
                    self.assertEqual((agenda['complete_on'], agenda['due_on'], agenda['category']), (complete, due, category))
                    if k == UNKNOWN:
                        self.assertNotEqual(agenda['due_kind'], 'handback', 'a check day is not a handback')
                    else:
                        # Its own 20th stays its own: the workbook's and the receipt's own 明天早上交 read as their handback
                        # (whose saved quotes hold those words); the reading book's quote and the bottle hold no handback.
                        self.assertEqual(agenda['due_kind'], 'handback' if k in ('数格', '回执') else 'deadline', 'its own 20th is its own')
                        self.assertIn(handback[k], named[k][0]['action'])
        task = named[UNKNOWN][0]
        self.assertEqual(task['due'], '2026-10-20')
        self.assertIn('明天早读检查记录本', task['action'])
        self.assertNotIn('交给', task['action'])
        self.assertNotIn('交', task['title'], 'checking the record book is not handing it in')

    def test_a_new_reply_that_does_not_support_the_item_keeps_it_unknown(self):
        cases = dict(BAD_RECEIPTS, failure=agent.family_llm.LLMDraftError('虚构：模型服务连接失败'))
        for name, reply in cases.items():
            with self.subTest(reply=name):
                self.setUp()
                before = self._old_store()
                self._replies(reply)
                result = self._at(0)
                self.assertEqual((len(self.calls), result['failed']), (1, 1), result)
                job = self._english_kept(before)
                self.assertEqual((job['done'], job['attempts']), (0, 1), job)
                self.assertIn('原始资料保留', job['error'], 'a readable status')
                self.assertEqual(job['next_try'], (self.now + dt.timedelta(minutes=5)).isoformat(), 'the original backoff')
                self._at(2)
                self.assertEqual(len(self.calls), 1, 'no retry inside the backoff')

    def test_failed_receipts_keep_the_original_limit_and_backoff_and_a_rename_never_renews_them(self):
        before = self._old_store()
        self._replies(agent.family_llm.LLMDraftError('虚构：模型服务连接失败'), BAD_RECEIPTS['other_check_day'], BAD_RECEIPTS['no_day'])
        for minutes in (0, 2, 6, 12, 17, 30, 60): self._at(minutes)
        self.assertEqual(len(self.calls), 3, 'three attempts, five and ten minutes apart')
        job = self._english_kept(before)
        self.assertEqual((job['done'], job['attempts'], job['next_try']), (0, 3, ''))
        self.assertIn('上限', job['error'])
        self.source['name'] = '虚构班级（改名）'; self.fixture.config()
        for minutes in (90, 120): self._at(minutes)
        self.assertEqual(len(self.calls), 3, 'a source rename never renews the exhausted identity')
        self.assertEqual(self._english_kept(before)['attempts'], 3)

    def test_a_paused_source_or_agent_makes_no_reread_and_the_resumed_round_collects_once(self):
        for case in ('source', 'agent'):
            with self.subTest(case=case):
                self.setUp()
                self._old_store()
                if case == 'source': self.source['enabled'] = False
                self.fixture.config(enabled=case != 'agent')
                self._replies(NEW_RECEIPT)
                saved = self._saved()
                for minutes in (0, 6, 12): self._at(minutes)
                self.assertEqual((self._saved(), len(self.calls)), (saved, 0), 'every row, job and cursor kept; no call')
                self.source['enabled'] = True; self.fixture.config(enabled=True)
                self.assertEqual(self._at(18)['created'], 5)
                self.assertEqual((self._at(24)['created'], len(self.calls)), (0, 1))

    def test_a_pause_while_the_reread_waits_writes_nothing_and_keeps_the_spent_attempts(self):
        before = self._old_store()
        unknown = self._item(before, UNKNOWN)
        self._replies(agent.family_llm.LLMDraftError('虚构：模型服务连接失败'), NEW_RECEIPT)
        self._at(0)  # attempt 1 fails
        real = agent.Store._job; paused = []

        def claim(store, key, *args, **kwargs):
            value = real(store, key, *args, **kwargs)
            if key == 'school-task:' + unknown['id'] and value and not paused:
                paused.append(key); self.source['enabled'] = False; self.fixture.config()
            return value
        with patch.object(agent.Store, '_job', claim):
            self._at(6)  # claimed, then paused before the call
        self.assertEqual((paused, len(self.calls)), (['school-task:' + unknown['id']], 1), 'no call after the pause')
        self.assertEqual(self._english_kept(before)['attempts'], 2)
        self.source['enabled'] = True; self.fixture.config()
        self.assertEqual(self._at(7)['created'], 1)
        _, _, jobs, items, _ = self._state()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual((items[unknown['id']]['state'], items[unknown['id']]['due']), ('accepted', '2026-10-20'))
        self.assertEqual(jobs['school-task:' + unknown['id']]['attempts'], 3, 'the failed and the dropped attempts are never renewed')

    def test_a_parent_edit_while_the_model_runs_is_not_overwritten(self):
        before = self._old_store()
        unknown = self._item(before, UNKNOWN)

        def edit():
            with self.store._db() as other:
                other.execute("UPDATE agent_items SET title=title||'（家长改）',updated=? WHERE id=?", ('2026-10-19T20:31:00+08:00', unknown['id']))
        self._replies(NEW_RECEIPT, during=edit)
        self._at(0)
        for minutes in (6, 12, 18): self._at(minutes)
        _, _, jobs, items, tasks = self._state()
        row = items[unknown['id']]
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((row['state'], row['due'], row['task_id'], row['plan']), ('pending', '', '', unknown['plan']))
        self.assertTrue(row['title'].endswith('（家长改）'))
        self.assertFalse(any('Unit 4' in t['title'] for t in tasks.values()))
        self.assertEqual(len(tasks), 4)

    def test_a_contradiction_the_current_selection_rejected_is_never_reread(self):
        # School B 同步练习 (model 10-09 against the original's 周四 10-08) is saved by the current selection with the day it
        # did not adopt: a known contradiction stays review on this and later rounds even with a configured model.
        import test_model_quality as quality
        with patch.object(agent.family_llm, 'configuration', return_value=('http://127.0.0.1:9/v1/chat/completions', 'synthetic-reread-model')):
            run = quality.ingest_school('school-b', dict(proposals=quality._school_b_reply(wrong_date=True)), runs=3)
        self.assertEqual(len(run['calls']), 1, run['results'])
        item = next(i for i in run['items'] if '同步练习' in i['title'] + i['body'])
        self.assertEqual((item['state'], item['due'], item['plan']['school_task']['state']), ('pending', '', 'review'), item)
        self.assertEqual(item['plan'].get('school_unadopted_due'), '2026-10-09', 'the day it did not adopt is kept, never adopted')
        for marker in ('school_saved_reread', 'school_role_reselect'):
            self.assertNotIn(marker, item['plan'])

    def test_a_reread_dropped_three_times_stops_and_only_the_explicit_retry_continues(self):
        # Root B1 on the ordinary path: the source is paused right after each real claim (eligibility and CAS run for real),
        # restored before the next round; the dropped rounds keep their attempts, no automatic fourth attempt follows, the
        # exhausted identity is visible, and the existing explicit retry of the same identity continues it.
        before = self._old_store()
        key = 'school-task:' + self._item(before, UNKNOWN)['id']
        self._replies(NEW_RECEIPT)
        real = agent.Store._job; drops = []; pausing = [True]

        def claim(store, k, *args, **kwargs):
            value = real(store, k, *args, **kwargs)
            if k == key and value and pausing[0]:
                drops.append(value); self.source['enabled'] = False; self.fixture.config()
            return value
        with patch.object(agent.Store, '_job', claim):
            for minutes in (0, 1, 2):
                self.source['enabled'] = True; self.fixture.config()
                self._at(minutes)
            pausing[0] = False
            self.source['enabled'] = True; self.fixture.config()
            for minutes in (3, 9, 60): self._at(minutes)
        self.assertEqual((len(drops), len(self.calls)), (3, 0), 'three dropped rounds, then no automatic fourth attempt')
        job = self._english_kept(before)
        self.assertEqual((job['attempts'], job['done'], job['next_try']), (3, 0, ''), 'the exhausted identity stays visible')
        self.assertGreaterEqual(self.store.snapshot()['failed_jobs'], 1)
        self.store.act(dict(action='retry', id=key))
        self.assertEqual(self._at(61)['created'], 1)
        self.assertEqual(len(self.calls), 1, 'the explicit retry continues on the ordinary path')
        _, _, jobs, items, _ = self._state()
        self.assertEqual((items[key[len('school-task:'):]]['state'], jobs[key]['done'], jobs[key]['attempts']), ('accepted', 1, 1))

    def test_the_shared_entry_spends_dropped_rounds_once_per_batch_and_retry_renews_only_unfinished(self):
        # Root B1/B2 at the shared entry: three claims dropped by _discard_job spend the batch's one budget for every identity
        # of the same original batch; only the explicit retry renews it, and a real done receipt is neither failure budget
        # nor replayed.
        before = self._old_store()
        batch = self._item(before, UNKNOWN)['job_id']
        first, second, third = ('school-task:' + self._item(before, k)['id'] for k in (UNKNOWN, '星芽', '数格'))
        value = dict(fixture='the same request')
        claim = lambda key: self.store._job(key, value, self.now, model=True, keep_budget=True)
        for _ in range(3):
            fp = claim(first)
            with self.store._db() as c: agent._discard_job(c, first, fp)
        self.assertIsNone(claim(first), 'no fourth automatic attempt')
        agent._school_recovery_inherit(self.store, second, batch, 'child-1')
        self.assertIsNone(claim(second), 'another identity of the same batch inherits the spent attempts')
        self.store.act(dict(action='retry', id=first))
        self.assertTrue(claim(first), 'the explicit retry renews the dropped identity')
        with self.store._db() as c:  # that round now succeeds: a real done receipt
            c.execute("UPDATE agent_jobs SET done=1,error='',next_try='' WHERE id=?", (first,))
            done = dict(c.execute('SELECT * FROM agent_jobs WHERE id=?', (first,)).fetchone())
        self.store.act(dict(action='retry', id=first))
        self.assertIsNone(claim(first), 'a real done receipt is never replayed')
        with self.store._db() as c:
            self.assertEqual(dict(c.execute('SELECT * FROM agent_jobs WHERE id=?', (first,)).fetchone()), done)
            c.execute('DELETE FROM agent_jobs WHERE id=?', (second,))
        agent._school_recovery_inherit(self.store, third, batch, 'child-1')
        self.assertTrue(claim(third), 'a real success spends no failure budget of the batch')

    def _saved_rows(self):
        """Every saved row the reread, its acceptance and its task could touch (the runtime heartbeat aside)."""
        with self.store._db() as c:
            tables = {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return {t: sorted(json.dumps(dict(r), sort_keys=True, ensure_ascii=False) for r in c.execute('SELECT * FROM ' + t))
                    for t in ('agent_items', 'agent_jobs', 'agent_sources', 'agent_messages', 'manual_tasks', 'task_updates',
                              'task_history', 'task_focus', 'study_items', 'records') if t in tables}

    def test_a_natural_success_is_never_replayed_by_the_explicit_retry(self):
        # The ordinary entry closes the chain the shared-entry test builds by hand: the reread succeeds on its own run_once
        # (no SQL, no removed identity), then the existing explicit retry -- by its id, then of everything -- and further
        # ordinary rounds and a reopen make no further model call and leave the task, the job, the old row's kept history
        # and every other saved row exactly as that success saved them.
        before = self._old_store()
        unknown = self._item(before, UNKNOWN)
        key = 'school-task:' + unknown['id']
        self._replies(NEW_RECEIPT)
        first = self._at(0)
        self.assertEqual((first['failed'], first['created'], len(self.calls)), (0, 5, 1), first)
        saved = self._saved_rows()
        _, _, jobs, items, tasks = self._state()
        self.assertEqual((jobs[key]['done'], jobs[key]['attempts'], jobs[key]['error'], jobs[key]['next_try']), (1, 1, '', ''))
        self.assertFalse(jobs[key]['fingerprint'].startswith('discarded:'), 'a real done receipt, made by the success itself')
        english = items[unknown['id']]
        self.assertEqual((english['state'], json.loads(english['plan'])['school_saved_reread']['previous_row']), ('accepted', unknown))
        self.assertEqual([t['id'] for t in tasks.values() if 'Unit 4' in t['title']], [english['task_id']])
        for minutes, retry in ((6, dict(action='retry', id=key)), (12, dict(action='retry'))):
            with self.subTest(retry=retry):
                self.assertEqual(self.store.act(retry), dict(ok=True, state='retry_pending'))
                result = self._at(minutes)
                self.assertEqual((result['failed'], result['created']), (0, 0), result)
                self.assertEqual(len(self.calls), 1, 'no further logical model call')
                self.assertEqual(self._saved_rows(), saved, 'no duplicate task and no job, row or history change')
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, initialize=False)
        self.assertEqual(self._at(30)['created'], 0)
        self.assertEqual((len(self.calls), self._saved_rows()), (1, saved))


# Root's frozen noun cases (cases.json, frozen before execution): one English original, its old review made by the public
# r259 source f0941d0's own Store.ingest -> run_once, then read again by the current ordinary run_once. Only the model
# boundary is fictional: the old selection reply is the Flash27 English proposal with this case's noun, the new receipt is
# the frozen reply. 交流 is inside the noun 家校交流本; it grants no handback.
NOUN_CASES = json.loads(r'''{"as_of": "2026-10-19", "now": "2026-10-19T20:08:00+08:00", "sent": "2026-10-19T16:22:00+08:00",
 "truth": "听录音跟读Unit 4 A day at the lake两遍，读完家长在指定本签字，19日晚完成，20日早读仅检查；交流是本名词内部，不授予交回许可。",
 "cases": [
  {"id": "P1-check-only-noun", "expected": "accept",
   "text": "英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在家校交流本上签字。今晚完成，明天早读检查家校交流本。",
   "reply": {"advice": "", "change": "new", "goal": "听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在家校交流本上签字。今晚完成，明天早读检查家校交流本。", "learning_goal_id": "", "learning_subject": "英语", "purpose": "learning", "reason": "虚构离线新回执，按本项原文核对。", "state": "ready", "submission": "明天早读检查家校交流本。", "target_id": "", "title": "英语：跟读Unit 4两遍并家长签字"}},
  {"id": "P2-correct-signing-title", "expected": "accept",
   "text": "英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在家校交流本上签字。今晚完成，明天早读检查家校交流本。",
   "reply": {"advice": "", "change": "new", "goal": "听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在家校交流本上签字。今晚完成，明天早读检查家校交流本。", "learning_goal_id": "", "learning_subject": "英语", "purpose": "learning", "reason": "虚构离线新回执，按本项原文核对。", "state": "ready", "submission": "明天早读检查家校交流本。", "target_id": "", "title": "英语：今晚跟读并请家长在家校交流本上签字"}},
  {"id": "N1-false-handback-noun", "expected": "reject",
   "text": "英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在家校交流本上签字。今晚完成，明天早读检查家校交流本。",
   "reply": {"advice": "", "change": "new", "goal": "听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在家校交流本上签字。今晚完成，明天早读检查家校交流本。", "learning_goal_id": "", "learning_subject": "英语", "purpose": "learning", "reason": "虚构离线新回执，按本项原文核对。", "state": "ready", "submission": "明天早读检查家校交流本。", "target_id": "", "title": "英语：明天早上交回家校交流本"}},
  {"id": "N2-false-handback-plain-control", "expected": "reject",
   "text": "英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。",
   "reply": {"advice": "", "change": "new", "goal": "听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。今晚完成，明天早读检查记录本。", "learning_goal_id": "", "learning_subject": "英语", "purpose": "learning", "reason": "虚构离线新回执，按本项原文核对。", "state": "ready", "submission": "明天早读检查记录本。", "target_id": "", "title": "英语：明天早上交回记录本"}}]}''')
R259_SOURCE_COMMIT = 'f0941d0ae99ee4689087c2f254a6efa4e8e7d7a7'
NOUN_SOURCE = dict(id='synthetic-noun-group', platform='wechat', child_id='child-1', name='虚构班级', cursor='33', enabled=True)
OLD_FLASH27_ENGLISH = dict(  # the Flash27 English proposal for message 34 (fictional HANDOFF raw), refs and noun of this case
    title_quote='英语：听录音跟读 Unit 4 A day at the lake 两遍，读完请家长在记录本上签字。', focus='school', due='2026-10-20',
    evidence=[dict(ref='message:synthetic-noun-group:34')], task_title='英语：跟读Unit 4两遍并家长签字',
    task_goal='听录音跟读 Unit 4 A day at the lake 两遍。\n读完请家长在记录本上签字。\n今晚完成，明天早读检查记录本。',
    task_advice='可跟读时注意模仿录音语音语调，读完后请家长及时签字。', learning_subject='英语', learning_goal_id='', task_change='new',
    task_target_id='', task_state='ready', task_reason='已读文字明确要求听录音跟读Unit 4两遍，家长在记录本上签字，今晚完成、明天早读检查记录本。',
    task_purpose='learning', task_submission='明天早读检查记录本。')
R259_SEED = r'''
import datetime as dt, json, sys
from pathlib import Path
from unittest.mock import patch
root = Path(sys.argv[1]); data = root / 'private'; data.mkdir(parents=True)
(root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
source, text, reply, sent, now = json.loads(sys.argv[2]), sys.argv[3], json.loads(sys.argv[4]), sys.argv[5], dt.datetime.fromisoformat(sys.argv[6])
(data / 'agent.json').write_text(json.dumps({'enabled': True, 'sources': [source]}))
import family_review, family_agent as agent, family_media
app = family_review.load_app(root, data)
store = agent.Store(app.connect, app.profiles, data, app=app)
store.ingest(dict(source_id=source['id'], expected_cursor='33', cursor='34', checked_at=now.isoformat(), last_message_time=sent, error='',
    messages=[dict(id='34', message_order='34', time=sent, kind='text', sender='虚构英语乔老师', sender_id='synthetic-unseen-en-qiao', text=text, unread=False)]))
with patch('family_qq_capture.run_one', return_value=dict(state='disabled')), \
     patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')), \
     patch.object(family_media, 'run_one', return_value=dict(state='ready')), \
     patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)), \
     patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())), \
     patch.object(agent.family_llm, '_chat_json', return_value=reply) as model:
    result = agent.run_once(app, now)
print(json.dumps(dict(calls=model.call_count, result=result)))
'''


class FrozenNounCaseTests(unittest.TestCase):
    """The new receipt's own action decides its role: 交流 inside 家校交流本 is the notebook's name, 交回 hands one in."""

    def _seed(self, text):
        import subprocess
        import sys
        import tempfile
        from contextlib import ExitStack
        from pathlib import Path
        import family_media
        import family_review
        directory = tempfile.TemporaryDirectory(prefix='synthetic-noun-case-')
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve(); old = root / 'r259-source'; old.mkdir()
        here = Path(__file__).resolve().parent
        archive = subprocess.run(['git', '-C', str(here), 'archive', R259_SOURCE_COMMIT], check=True, capture_output=True).stdout
        subprocess.run(['tar', '-x', '-C', str(old)], input=archive, check=True)
        noun = '家校交流本' if '家校交流本' in text else '记录本'
        reply = json.loads(json.dumps(dict(proposals=[OLD_FLASH27_ENGLISH]), ensure_ascii=False).replace('记录本', noun))
        self.assertEqual(reply['proposals'][0]['title_quote'], text[:text.index('。') + 1])
        out = subprocess.run([sys.executable, '-I', '-c', 'import sys;p,s=sys.argv[1:3];del sys.argv[1:3];sys.path.insert(0,p);exec(s)',
                              str(old), R259_SEED, str(root / 'family'), json.dumps(NOUN_SOURCE), text, json.dumps(reply),
                              NOUN_CASES['sent'], '2026-10-19T20:00:00+08:00'],
                             check=True, capture_output=True, text=True, cwd=old, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')).stdout
        self.assertEqual(json.loads(out.strip().splitlines()[-1])['calls'], 1, 'the old source ran its own ordinary selection once')
        self.data = root / 'family' / 'private'
        self.app = family_review.load_app(root / 'family', self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        stack = ExitStack(); self.addCleanup(stack.close)
        for target in ('family_qq_capture.run_one',):
            stack.enter_context(patch(target, return_value=dict(state='disabled')))
        stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        stack.enter_context(patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('FAMILY_LLM_')}, clear=True))
        (self.data / 'model.json').write_text(json.dumps(FICTIONAL_MODEL))
        self.model = stack.enter_context(patch.object(agent.family_llm, '_chat_json', side_effect=AssertionError('no request')))
        return self._state()

    def _state(self):
        with self.app.connect() as c:
            return ({r['id']: dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")},
                    {r['id']: dict(r) for r in c.execute('SELECT * FROM agent_jobs')},
                    [dict(r) for r in c.execute('SELECT * FROM manual_tasks')])

    def test_the_new_receipt_is_read_by_its_own_actions_not_by_a_character_inside_a_noun(self):
        for case in NOUN_CASES['cases']:
            with self.subTest(case=case['id']):
                items, jobs, tasks = self._seed(case['text'])
                old, = items.values()
                self.assertEqual((old['state'], old['due'], tasks), ('pending', '', []), 'the r259 source left an empty-day review')
                self.assertTrue(json.loads(old['plan'])['school_task']['reason'].endswith('未采用模型日期；请核对原通知。'))
                calls = []

                def model(messages, schema, name, timeout=60, *, data_path=None, reply=case['reply']):
                    calls.append((name, len(schema['required']), timeout, [e['ref'] for e in json.loads(messages[-1]['content'])['evidence']]))
                    return copy.deepcopy(reply)
                self.model.side_effect = model
                result = agent.run_once(self.app, dt.datetime.fromisoformat(NOUN_CASES['now']))
                self.assertEqual(calls, [('family_school_task', 11, 45, ['message:synthetic-noun-group:34'])], 'the existing caller, unchanged')
                items, jobs, tasks = self._state()
                row = items[old['id']]
                if case['expected'] == 'accept':
                    self.assertEqual((result['failed'], result['created']), (0, 1), result)
                    task, = tasks
                    self.assertEqual((row['state'], row['task_id'], row['due'], task['due'], task['title']),
                                     ('accepted', task['id'], '2026-10-20', '2026-10-20', case['reply']['title']))
                    self.assertEqual(json.loads(row['plan'])['school_saved_reread']['previous_row'], old)
                    agenda = next(x for x in self.app.calendar_snapshot('2026-10-19', '2026-10-19')['inbox'] if x['task_id'] == task['id'])['agenda']
                    self.assertEqual((agenda['complete_on'], agenda['due_on']), ('2026-10-19', '2026-10-20'))
                    self.assertNotEqual(agenda['due_kind'], 'handback')
                else:
                    self.assertEqual((result['failed'], result['created'], tasks), (1, 0, []), result)
                    self.assertEqual(row, old, 'old row, unknown day and receipt kept verbatim')
                    job = jobs['school-task:' + old['id']]
                    self.assertEqual((job['attempts'], job['done']), (1, 0))
                    self.assertIn('原始资料保留', job['error'])


class DroppedSavedRereadBatchBudgetTests(unittest.TestCase):
    """Root B2 on the ordinary path: the TB02 review the exact old source 632a778 saved is read again by the saved reread;
    each claim is dropped because the source is paused right after it (eligibility and CAS run for real), then restored.
    Once the original due passes, the batch audit would be its second identity: it must inherit the three spent attempts."""

    def setUp(self):
        import test_school_saved_reread as saved
        self.saved = saved
        saved.natural(self, 'synthetic-dropped-budget-', saved.SOURCE, saved.TEXT, saved.SYNTHETIC)

    def rows(self):
        return self.saved.SavedSchoolRereadTests.rows(self)

    def run_round(self, reply, at):
        return self.saved.SavedSchoolRereadTests.run_round(self, reply, at)

    def _enabled(self, value):
        config = json.loads((self.data / 'agent.json').read_text())  # the isolated fictional config only
        config['sources'][0]['enabled'] = value
        (self.data / 'agent.json').write_text(json.dumps(config))

    def test_a_saved_reread_dropped_three_times_is_not_refilled_by_the_batch_audit(self):
        before = self.rows()
        old_item, = before['items']
        key = 'school-task:' + old_item['id']
        fail = dict(side_effect=agent.family_llm.LLMDraftError('SYNTHETIC：同一旧批次固定失败；0真实provider。'))
        real = agent.Store._job; drops = []

        def claim(store, k, *args, **kwargs):
            value = real(store, k, *args, **kwargs)
            if k == key and value:
                drops.append(k); self._enabled(False)
            return value
        with patch.object(agent.Store, '_job', claim):
            for minutes in (0, 1, 2):
                self._enabled(True)
                self.assertEqual(self.run_round(fail, self.now + dt.timedelta(minutes=minutes))[0], 0)
        self._enabled(True)
        job = self.rows()['jobs'][key]
        self.assertEqual((len(drops), job['attempts'], job['done']), (3, 3, 1), 'three dropped rounds spent three attempts')
        late = dt.datetime(2026, 10, 23, 18, 0, tzinfo=agent.TZ)  # past the original due: the saved reread no longer owns it
        counts = [self.run_round(fail, late + dt.timedelta(minutes=m))[0] for m in (0, 41, 82)]
        self.assertEqual(counts, [0, 0, 0], 'no fourth automatic attempt under another identity of the same batch')
        state = self.rows()
        self.assertFalse([k for k in state['jobs'] if k.startswith('school-history:')], 'the audit is not opened on a spent budget')
        self.assertEqual((state['items'], state['tasks']), (before['items'], []))
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])
        self.assertEqual((state['messages'], state['cursor']), (before['messages'], before['cursor']))
        self.store.act(dict(action='retry', id=key))  # only the existing explicit retry renews the batch's budget
        self.assertEqual(self.run_round(fail, late + dt.timedelta(minutes=200))[0], 1, 'the explicit retry continues')


if __name__ == '__main__':
    unittest.main()

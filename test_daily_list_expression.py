#!/usr/bin/env python3
"""Display-only contract for the daily-list body: one requirement reads once (C1-C8).

The product's daily card used to stack a task's body, 提交要求 and 补充要求 on top of each other, repeat the title's
own words in the body, and fold the family's arrangement into the teacher's words. These tests pin the display contract
on fully fictional tasks: labels never read in the body, a clause reads once, a restatement of the title goes, the
title's opening is not repeated, a line the card already reads goes, labelled lines keep their new words, the family's
arrangement reads apart in plan_lines, and no line this display edited keeps a dangling full-width semicolon. Nothing
here writes a store: the same saved action and the same task dict read unchanged after the call.

The comparison is the display's own: _plain (NFKC, case, whitespace, punctuation) equality, continuous substring, or
the same words with only particles (了/着/里/也/都/就/和…) differing. There is no similarity threshold: a word that is
not exactly (or particle-)equal is never a repeat, so 明天/后天, 练习册/练习本, 1号本/2号本 and a title's 第1题 never
swallow a line that adds one.
"""
import copy
import unittest

import family_agenda


DAY = '2026-11-04'
CHILD = {'id': 'child-display-1', 'name': '小禾'}

# The three fictional tasks from the parent's report, rebuilt from the saved words. The actions are display input only:
# no store and no model is involved in this file.
ENGLISH_TITLE = '英语：完成《每日练习》'
ENGLISH_ACTION = ('完成英语《每日练习》：一、看图选词第1—3题；二、标星单词 under、near 各抄写一遍。不需要录音。'
                  '做完放进英语夹里，明天带来。\n'
                  '提交要求：做完放进英语夹，明天带来。\n'
                  '补充要求：完成英语《每日练习》。\n'
                  '完成后放进英语夹里，明天带到学校。\n'
                  '不用在群里发照片。')
ENGLISH_LINES = ['一、看图选词第1—3题',
                 '二、标星单词 under、near 各抄写一遍。',
                 '不需要录音。',
                 '做完放进英语夹里，明天带来。',
                 # Kept on purpose: 完成后…带到学校 is neither a continuous part of, nor particle-equal to,
                 # 做完…明天带来, so dropping it would delete the words 学校/完成 rather than a pure repetition. This is
                 # exactly the case where a similarity score is not allowed to decide: C2 still reads every identical
                 # clause once, and C3 below shows no line only retells the title.
                 '完成后放进英语夹里，明天带到学校。',
                 '不用在群里发照片。']

MATH_TITLE = '数学：完成《每日练习》第26页第1—3题'
MATH_ACTION = ('完成数学《每日练习》第26页第1—3题；第4题不做。每题写出算式并验算。\n'
               '提交要求：家长签字后周五交给数学周老师')
MATH_LINES = ['第4题不做。', '每题写出算式并验算。', '家长签字后周五交给数学周老师']

CHINESE_TITLE = '语文：朗读《风经过小巷》第2、3自然段'
CHINESE_ACTION = ('朗读《风经过小巷》第2、3自然段。各读两遍，读给家长听。\n'
                  '补充要求：不用录音，也不用上传，明早我抽听。')
CHINESE_LINES = ['各读两遍，读给家长听。', '不用录音，也不用上传，明早我抽听。']
CHINESE_PLAN = '林老师布置的那项朗读，今天18:30我来听，仍按老师说的两遍'

LABELS = ('提交要求', '补充要求', '补充说明', '正文')


def plain(text):
    """The same comparison shape the display uses: NFKC width, case, whitespace and punctuation do not make a word new."""
    import unicodedata
    text = unicodedata.normalize('NFKC', str(text)).lower()
    return ''.join(ch for ch in text if not (ch.isspace() or unicodedata.category(ch).startswith('P')))


class LabelTests(unittest.TestCase):
    """C1: no 提交要求：/补充要求：/补充说明：/正文： tag reads in the body; the colon goes with the tag."""

    def test_each_label_tag_is_left_out_whole_with_its_colon(self):
        for tag in LABELS:
            for mark in ('：', ':'):
                with self.subTest(tag=tag, mark=mark):
                    shown = family_agenda.action_lines('语文：A', tag + mark + '明天早上交练习册。')
                    self.assertEqual(shown, ['明天早上交练习册。'])
                    self.assertFalse(any(line.startswith(tag) for line in shown), shown)
                    self.assertNotIn(tag + mark, ''.join(shown))

    def test_a_label_whose_content_the_body_already_reads_is_dropped_whole(self):
        # 提交要求 repeats 做完放进英语夹里，明天带来, which the card already shows: only the tag word changes.
        shown = family_agenda.action_lines(ENGLISH_TITLE, ENGLISH_ACTION)
        self.assertEqual(shown, ENGLISH_LINES)
        self.assertNotIn('提交要求', ''.join(shown))


class ClauseOnceTests(unittest.TestCase):
    """C2: a clause reads once across lines and inside one line; full-width/half-width and spacing do not hide it."""

    def test_the_same_clause_is_not_read_twice_across_lines(self):
        shown = family_agenda.action_lines('语文：A', '读第3课两遍，家长签字。\n家长签字。')
        self.assertEqual(shown, ['读第3课两遍，家长签字。'])
        self.assertEqual(plain(''.join(shown)).count('家长签字'), 1)

    def test_the_same_clause_is_not_read_twice_inside_one_line_and_keeps_the_full_stop(self):
        shown = family_agenda.action_lines('语文：A', '读第3课，读第3课。')
        self.assertEqual(shown, ['读第3课。'])
        self.assertEqual(plain(''.join(shown)).count('读第3课'), 1)

    def test_a_dropped_middle_clause_keeps_the_remaining_order_and_separator(self):
        self.assertEqual(family_agenda.action_lines('语文：A', '读第3课，读第3课，家长签字。'), ['读第3课，家长签字。'])
        self.assertEqual(''.join(family_agenda.action_lines('语文：A', 'A，A，B。')), 'A，B。')

    def test_spacing_and_punctuation_do_not_make_a_new_clause(self):
        shown = family_agenda.action_lines('语文：A', '家长签字。\n 家长 签字！')
        self.assertEqual(plain(''.join(shown)).count('家长签字'), 1)

    def test_a_shorter_form_of_a_shown_clause_is_a_repeat(self):
        shown = family_agenda.action_lines('语文：A', '做完放进英语夹里，明天带来。\n做完放进英语夹，明天带来。')
        self.assertEqual(shown, ['做完放进英语夹里，明天带来。'])


class RestatementTests(unittest.TestCase):
    """C3: a line the title already says whole is left out, but only when nothing of it is new."""

    def test_a_line_that_only_retells_the_title_is_left_out(self):
        self.assertEqual(family_agenda.action_lines('英语：完成《每日练习》', '完成英语《每日练习》。'), [])
        self.assertEqual(family_agenda.action_lines('英语：完成《每日练习》', '补充要求：完成英语《每日练习》。'), [])

    def test_one_new_word_keeps_the_line_even_when_the_title_says_the_rest(self):
        # 本 is not in the title: this is a different object, not a restatement.
        self.assertEqual(family_agenda.action_lines('英语：完成《每日练习》', '完成英语《每日练习》本。'),
                         ['完成英语《每日练习》本。'])
        # 自然段 says a real word the title's 段 does not: the frozen line stays.
        self.assertEqual(family_agenda.action_lines('语文：朗读《秋天的小院》第2、3段两遍',
                                                   '朗读《秋天的小院》第2、3自然段两遍。'),
                         ['朗读《秋天的小院》第2、3自然段两遍。'])


class TitleOpeningTests(unittest.TestCase):
    """C4: the title's own opening reads once in the title; the rest of the line stays, with its own new words."""

    def test_the_titles_own_opening_gives_way_and_the_new_requirement_stays(self):
        shown = family_agenda.action_lines(MATH_TITLE, '完成数学《每日练习》第26页第1—3题；第4题不做。')
        self.assertEqual(shown, ['第4题不做。'])
        self.assertFalse(any('第26页' in line for line in shown), shown)

    def test_a_title_word_the_line_itself_adds_keeps_the_whole_line(self):
        # 完成 is that line's own word (the title is 数学：练习册第18页第2、4、6题).
        shown = family_agenda.action_lines('数学：练习册第18页第2、4、6题',
                                           '完成练习册第18页第2、4、6题；每题先列式，再写完整计算过程，算完后逐题验算。')
        self.assertEqual(shown, ['完成练习册第18页第2、4、6题；', '每题先列式，再写完整计算过程，算完后逐题验算。'])

    def test_a_new_question_number_is_never_cut_as_a_title_repeat(self):
        # The title says 第1题 only; 第2题 is new, so the opening cannot give way (RED counter-example).
        self.assertEqual(family_agenda.action_lines('数学：完成第20页第1题', '完成第20页第1、2题'),
                         ['完成第20页第1、2题'])

    def test_a_swapped_page_and_question_number_is_not_a_title_repeat(self):
        self.assertEqual(family_agenda.action_lines('语文：完成练习册第2页第3题', '完成练习册第3页第2题'),
                         ['完成练习册第3页第2题'])


class SameContentTests(unittest.TestCase):
    """C5: a line identical to a shown line, or different only by particles, goes; near-but-different words stay."""

    def test_an_identical_later_line_is_dropped(self):
        self.assertEqual(family_agenda.action_lines('语文：A', '读第3课两遍，家长签字。\n读第3课两遍，家长签字！'),
                         ['读第3课两遍，家长签字。'])

    def test_a_line_differing_only_by_particles_is_the_same_clause(self):
        # 里 is a particle: 做完放进英语夹 and 做完放进英语夹里 are the same words.
        self.assertEqual(family_agenda.action_lines('语文：A', '做完放进英语夹里，明天带来。\n做完放进英语夹，明天带来。'),
                         ['做完放进英语夹里，明天带来。'])

    def test_near_but_different_words_are_never_swallowed(self):
        cases = [('明天交练习册。\n明天不交练习册。', ['明天交练习册。', '明天不交练习册。']),
                 ('今天交练习册。\n明天交练习册。', ['今天交练习册。', '明天交练习册。']),
                 ('带上练习册。\n带上练习本。', ['带上练习册。', '带上练习本。']),
                 ('不用明天交。\n不用后天交。', ['不用明天交。', '不用后天交。']),
                 ('1号本写。\n2号本写。', ['1号本写。', '2号本写。'])]
        for action, expected in cases:
            with self.subTest(action=action):
                self.assertEqual(family_agenda.action_lines('英语：完成《每日练习》', action), expected)

    def test_the_english_completion_line_stays_because_it_is_not_the_same_words(self):
        self.assertIn('完成后放进英语夹里，明天带到学校。', family_agenda.action_lines(ENGLISH_TITLE, ENGLISH_ACTION))


class NewInformationTests(unittest.TestCase):
    """C6: a labelled line's new clauses stay; only the clauses the card already reads are left out."""

    def test_a_labels_new_requirement_is_kept_without_its_label(self):
        shown = family_agenda.action_lines(MATH_TITLE, MATH_ACTION)
        self.assertFalse(any(line.startswith('提交要求') for line in shown), shown)
        self.assertTrue(any('交给数学周老师' in line for line in shown), shown)

    def test_a_labelled_extension_folds_into_the_shown_line_once(self):
        # The frozen card from test_child_study_ui.cjs, unchanged: 明天早上交练习册 extends 明天早上交.
        shown = family_agenda.action_lines('语文：完成《星芽阅读练习册》第28页第1、2题',
                                           '完成《星芽阅读练习册》第28页第1、2题。\n答案写在练习册上。\n今晚完成，明天早上交。\n'
                                           '提交要求：明天早上交练习册。')
        self.assertEqual(shown, ['答案写在练习册上。', '今晚完成，明天早上交练习册。'])
        self.assertEqual(''.join(shown).count('明天早上交'), 1)

    def test_a_label_that_does_not_extend_the_last_clause_becomes_its_own_line_not_a_scramble(self):
        # RED counter-example: folding this into the first sentence produced a sentence that is not a continuous part
        # of the saved words (明天交练习册和卷子，然后读课文。). It must instead read as its own line after the saved one.
        shown = family_agenda.action_lines('语文：A', '明天交练习册，然后读课文。\n提交要求：明天交练习册和卷子。')
        self.assertEqual(shown, ['明天交练习册，然后读课文。', '明天交练习册和卷子。'])
        self.assertIn(''.join(shown), '明天交练习册，然后读课文。明天交练习册和卷子。')


class GoldenTaskTests(unittest.TestCase):
    """The three fictional tasks from the parent's report, in their fixed display form (C1-C8 together)."""

    def test_english_card_reads_once(self):
        shown = family_agenda.action_lines(ENGLISH_TITLE, ENGLISH_ACTION)
        self.assertEqual(shown, ENGLISH_LINES)
        self.assertFalse(any(line.startswith(label) for line in shown for label in LABELS), shown)
        self.assertFalse(any('每日练习' in line for line in shown), shown)

    def test_math_card_reads_once_and_keeps_the_new_handback(self):
        self.assertEqual(family_agenda.action_lines(MATH_TITLE, MATH_ACTION), MATH_LINES)

    def test_chinese_body_reads_once(self):
        self.assertEqual(family_agenda.action_lines(CHINESE_TITLE, CHINESE_ACTION), CHINESE_LINES)


class PlanLineTests(unittest.TestCase):
    """C7: the family's arrangement reads apart in plan_lines; lines keeps only the teacher's words."""

    def _row(self, task, item):
        view = family_agenda.day_view([item], [task], [], CHILD, DAY, DAY, 'wrong')
        return view['groups'][0]['items'][0], view

    def _task_and_item(self, focus='next', scheduled=True):
        task = {'id': 'task-display-1', 'child': CHILD['name'], 'title': CHINESE_TITLE, 'action': CHINESE_ACTION,
                'action_lines': family_agenda.action_lines(CHINESE_TITLE, CHINESE_ACTION),
                'focus': {'next_action': CHINESE_PLAN} if focus == 'next' else None,
                'source': 'school', 'school_origin': True, 'progress': None}
        agenda = {'due_on': DAY, 'due_kind': 'deadline', 'category': 'homework'}
        if scheduled:
            agenda['scheduled_on'] = DAY
        item = {'id': 'item-display-1', 'kind': 'task', 'task_id': task['id'], 'title': CHINESE_TITLE,
                'child_ids': [CHILD['id']], 'agenda': agenda, 'closed': False, 'status': '待跟进'}
        return task, item, agenda

    def test_the_family_arrangement_reads_apart_from_the_teachers_words(self):
        task, item, _ = self._task_and_item()
        before = copy.deepcopy(task)
        row, _ = self._row(task, item)
        self.assertEqual(row['lines'], CHINESE_LINES)
        self.assertEqual(row['plan_lines'], [CHINESE_PLAN])
        self.assertFalse(any('家庭安排' in line for line in row['lines']), row['lines'])
        self.assertFalse(any('家庭安排' in line for line in row['plan_lines']), row['plan_lines'])
        self.assertEqual(task, before, 'display only: the task is not rewritten')

    def test_the_family_text_is_truly_removed_from_lines_not_copied(self):
        task, item, _ = self._task_and_item()
        row, _ = self._row(task, item)
        self.assertEqual(len(row['lines']), len(CHINESE_LINES))
        self.assertNotIn(CHINESE_PLAN, row['lines'])

    def test_plan_lines_defaults_to_empty_and_keeps_every_other_row_key(self):
        task, item, _ = self._task_and_item(focus=None)
        row, _ = self._row(task, item)
        self.assertEqual(row['plan_lines'], [])
        self.assertEqual(row['lines'], CHINESE_LINES)
        for key in ('id', 'kind', 'task_id', 'title', 'subject', 'category', 'status', 'closed', 'pending_review',
                    'origin', 'origin_label', 'lines', 'complete_words', 'facts', 'today', 'when',
                    'publications', 'published_at', 'publisher', 'progress', 'records', 'wrong'):
            self.assertIn(key, row)
        # A conditional key stays conditional: no school_material on this item, so no material key and no version key.
        self.assertNotIn('material', row)
        self.assertNotIn('version', row)

    def test_a_version_latest_family_line_is_still_read_as_a_plan(self):
        task, item, _ = self._task_and_item(focus=None)
        item = dict(item, version={'state': 'latest', 'title': CHINESE_TITLE,
                                   'lines': ['家庭安排（计划 ' + DAY + '）：家长自己的安排']})
        row, _ = self._row(task, item)
        self.assertEqual(row['plan_lines'], ['家长自己的安排'])
        self.assertEqual(row['lines'], [])


class FollowUpTests(unittest.TestCase):
    """C9: a later notice's whole original reads apart in follow_ups; a bare line with no label stays in lines.

    The merge labels update/append/cancel originals; a same-fold original is stored bare. The display separates only the
    labelled ones, because a bare line can as well be a new requirement (不用在群里发照片) as a restatement. That choice is
    pinned here so a later cleanup cannot quietly move every same-fold line out of the card.
    """

    BASE = '完成练习册第3页第2题。\n每题写出算式并验算。\n不用在群里发照片。'
    LATER = ('\n后到更正原文（2026-11-04 16:00）：第4题不做。'
             '\n后到补充原文（2026-11-04 17:00）：周五交给数学周老师。'
             '\n取消依据（2026-11-04 18:00）：原订美术课带落叶事项取消。'
             '\n后到原文（更正/取消依据，不进本事项日期判断）：2026-11-04 16:00（message:qa:x）「原第1—4题」')

    def _row(self, task, item):
        view = family_agenda.day_view([item], [task], [], CHILD, DAY, DAY, 'wrong')
        return view['groups'][0]['items'][0]

    def _task_and_item(self, action, focus='next', version=None):
        title = '数学：完成练习册第3页第2题'
        task = {'id': 'task-follow-1', 'child': CHILD['name'], 'title': title, 'action': action,
                'focus': {'next_action': CHINESE_PLAN} if focus == 'next' else None,
                'source': 'school', 'school_origin': True, 'progress': None}
        agenda = {'due_on': DAY, 'due_kind': 'deadline', 'category': 'homework', 'scheduled_on': DAY}
        item = {'id': 'item-follow-1', 'kind': 'task', 'task_id': task['id'], 'title': title,
                'child_ids': [CHILD['id']], 'agenda': agenda, 'closed': False, 'status': '待跟进'}
        if version is not None:
            item['version'] = version
        return task, item

    def test_the_four_labelled_later_notices_read_apart_from_the_requirements(self):
        task, item = self._task_and_item(self.BASE + self.LATER)
        before = copy.deepcopy(task)
        row = self._row(task, item)
        self.assertEqual(row['lines'], self.BASE.splitlines())
        self.assertEqual(row['follow_ups'], [
            {'label': '更正', 'time': '2026-11-04 16:00', 'text': '第4题不做。'},
            {'label': '提醒', 'time': '2026-11-04 16:00', 'text': '（message:qa:x）「原第1—4题」'},
            {'label': '补充', 'time': '2026-11-04 17:00', 'text': '周五交给数学周老师。'},
            {'label': '取消', 'time': '2026-11-04 18:00', 'text': '原订美术课带落叶事项取消。'},
        ])
        self.assertEqual(task, before, 'display only: the task and its saved action are not rewritten')

    def test_a_bare_same_fold_line_without_a_label_stays_in_lines(self):
        task, item = self._task_and_item(self.BASE + '\n朗读仍是《风经过小巷》第2、3自然段各两遍。\n今天18:30由家长听读。')
        row = self._row(task, item)
        self.assertEqual(row['follow_ups'], [])
        self.assertIn('朗读仍是《风经过小巷》第2、3自然段各两遍。', row['lines'])
        self.assertIn('今天18:30由家长听读。', row['lines'])

    def test_a_prior_reminder_reads_before_the_later_correction_and_keeps_its_label(self):
        later = ('\n后到更正原文（2026-11-04 17:00）：只做第1—3题。'
                 '\n先前提醒（2026-11-04 16:00）：再提醒今天那份数学《每日练习》：第26页1—4题，今晚做、签字。')
        task, item = self._task_and_item(self.BASE + later)
        row = self._row(task, item)
        self.assertEqual([f['label'] for f in row['follow_ups']], ['先前提醒', '更正'])
        self.assertEqual([f['time'] for f in row['follow_ups']], ['2026-11-04 16:00', '2026-11-04 17:00'])
        self.assertEqual(row['follow_ups'][0]['text'],
                         '再提醒今天那份数学《每日练习》：第26页1—4题，今晚做、签字。')

    def test_multi_line_originals_are_kept_whole_in_arrival_order_at_the_same_time(self):
        later = ('\n后到补充原文（2026-11-04 17:00）：交回时间不变。'
                 '\n后到补充原文（2026-11-04 17:00）：周五仍交给数学周老师。'
                 '\n后到更正原文（2026-11-04 16:00）：第4题不做。')
        task, item = self._task_and_item(self.BASE + later)
        row = self._row(task, item)
        self.assertEqual([f['text'] for f in row['follow_ups']],
                         ['第4题不做。', '交回时间不变。', '周五仍交给数学周老师。'])
        self.assertEqual([f['time'] for f in row['follow_ups']],
                         ['2026-11-04 16:00', '2026-11-04 17:00', '2026-11-04 17:00'])

    def test_no_follow_up_payload_reads_unchanged_and_keeps_the_row_keys(self):
        task, item = self._task_and_item(self.BASE, focus=None)
        row = self._row(task, item)
        self.assertEqual(row['follow_ups'], [])
        self.assertEqual(row['plan_lines'], [])
        self.assertEqual(row['lines'], self.BASE.splitlines())
        self.assertIn('follow_ups', row)
        self.assertEqual(set(row['follow_ups']), set())

    def test_plan_lines_and_follow_ups_read_side_by_side(self):
        task, item = self._task_and_item(self.BASE + self.LATER)
        row = self._row(task, item)
        self.assertEqual(row['plan_lines'], [CHINESE_PLAN])
        self.assertEqual(len(row['follow_ups']), 4)
        self.assertFalse(any('家庭安排' in line for line in row['lines']), row['lines'])

    def test_a_version_latest_follow_up_is_read_as_a_notice(self):
        task, item = self._task_and_item(self.BASE, focus=None,
                                         version={'state': 'latest', 'title': '数学：完成练习册第3页第2题',
                                                  'lines': ['家庭安排（计划 ' + DAY + '）：家长自己的安排',
                                                            '后到更正原文（2026-11-04 16:00）：第4题不做。']})
        row = self._row(task, item)
        self.assertEqual(row['lines'], [])
        self.assertEqual(row['plan_lines'], ['家长自己的安排'])
        self.assertEqual(row['follow_ups'], [{'label': '更正', 'time': '2026-11-04 16:00', 'text': '第4题不做。'}])


class CompoundRestatementTests(unittest.TestCase):
    """C9b: a line that joins two already-shown requirements with 后/，/； reads once; no similarity, only exact pieces.

    Each piece must read earlier; a digit or negation of its own must also read earlier; and at least two lines stay,
    so a two-line card is never emptied. A compound line with one new piece stays whole instead of being split into a
    fragment (带跳绳，穿运动鞋 keeps 穿运动鞋 and the sentence it was written in)."""

    TITLE = '数学：完成练习册第3页第2题'

    def test_a_line_combining_two_shown_requirements_is_left_out(self):
        shown = family_agenda.action_lines(
            self.TITLE, '完成练习册第3页第2题。\n请家长签字。\n周五交给数学老师。\n家长签字后周五交给数学老师。')
        self.assertEqual(shown, ['请家长签字。', '周五交给数学老师。'])

    def test_a_different_number_keeps_both_lines(self):
        shown = family_agenda.action_lines('语文：A', '交作业到1号本。\n交作业到2号本。')
        self.assertEqual(shown, ['交作业到1号本。', '交作业到2号本。'])

    def test_a_negation_of_its_own_keeps_both_lines(self):
        shown = family_agenda.action_lines('语文：A', '明天交练习册。\n明天不交练习册。')
        self.assertEqual(shown, ['明天交练习册。', '明天不交练习册。'])

    def test_a_compound_line_with_one_new_piece_keeps_its_whole_sentence(self):
        shown = family_agenda.action_lines('语文：A', '带跳绳。\n带跳绳，穿运动鞋。')
        self.assertEqual(shown, ['带跳绳。', '带跳绳，穿运动鞋。'])

    def test_at_least_two_lines_remain(self):
        shown = family_agenda.action_lines('语文：A', '请家长签字，周五交给数学老师。\n家长签字后周五交给数学老师。')
        self.assertEqual(shown, ['请家长签字，周五交给数学老师。', '家长签字后周五交给数学老师。'])


class PunctuationTests(unittest.TestCase):
    """C8: a line this display edited never keeps a dangling full-width semicolon; lines stay whole short phrases."""

    def test_no_edited_line_starts_or_ends_on_a_full_width_semicolon(self):
        for title, action in ((ENGLISH_TITLE, ENGLISH_ACTION), (MATH_TITLE, MATH_ACTION), (CHINESE_TITLE, CHINESE_ACTION)):
            with self.subTest(title=title):
                shown = family_agenda.action_lines(title, action)
                self.assertTrue(all(line.strip() for line in shown), shown)
                self.assertFalse([line for line in shown if line.startswith('；') or line.endswith('；')], shown)

    def test_the_english_first_step_keeps_no_dangling_semicolon(self):
        shown = family_agenda.action_lines(ENGLISH_TITLE, ENGLISH_ACTION)
        self.assertEqual(shown[0], '一、看图选词第1—3题')
        self.assertFalse(shown[0].endswith('；'))


class FoldSemanticsTests(unittest.TestCase):
    """C2/C5: only particles fold; an adverb that adds a step (再/也/还/都/就) never disappears as a repeat."""

    def test_an_incremental_adverb_keeps_its_own_line(self):
        for action, second in (('读一遍。\n再读一遍。', '再读一遍。'),
                               ('语文要交。\n语文也要交。', '语文也要交。'),
                               ('明天带练习册。\n明天再带练习册。', '明天再带练习册。'),
                               ('明天不带练习册。\n明天不再带练习册。', '明天不再带练习册。')):
            with self.subTest(action=action):
                shown = family_agenda.action_lines('语文：A', action)
                self.assertIn(second, shown)

    def test_fold_still_joins_a_true_particle_only_repeat(self):
        shown = family_agenda.action_lines('语文：A', '做完放进英语夹里，明天带来。\n做完放进英语夹，明天带来。')
        self.assertEqual(shown, ['做完放进英语夹里，明天带来。'])


class TitleNumberGuardTests(unittest.TestCase):
    """C3: a title range and a saved single number never flatten into one another."""

    def test_a_saved_single_item_is_not_covered_by_the_title_range(self):
        self.assertEqual(family_agenda.action_lines('数学：完成第1—3题', '完成第13题'), ['完成第13题'])
        self.assertEqual(family_agenda.action_lines('语文：朗读第1、2段', '朗读第12段'), ['朗读第12段'])

    def test_a_title_that_really_covers_the_line_still_reads_once(self):
        self.assertEqual(family_agenda.action_lines('英语：完成《每日练习》', '完成英语《每日练习》。'), [])


class WorkKindTests(unittest.TestCase):
    """Build 320: each card names what kind of work it asks for, so the app requests the right evidence.

    The judgement is display-only and first-match-wins in the product's order; a negated keyword (不用朗读) is not a
    request, and 做题 stays the fallback rather than the label for every card. The three real-snapshot rows pin the
    shapes the app already renders.
    """

    REAL_ENGLISH_TITLE = '英语：完成《每日练习》并放入英语夹'
    REAL_ENGLISH_LINES = ['英语《每日练习》见今天这份附件，今晚完成，做完放进英语夹里，明天带来。',
                          '一、看图选词第1—3题。', '二、标星单词 under、near 各抄写一遍。', '不需要录音。']
    REAL_MATH_TITLE = '数学：完成《每日练习》第26页第1—3题'
    REAL_MATH_LINES = ['第4题不做。', '每题写出算式并验算。', '请家长签字。', '周五交给数学老师。']
    REAL_CHINESE_TITLE = '朗读《风经过小巷》第2、3自然段'
    REAL_CHINESE_LINES = ['今晚朗读《风经过小巷》第2、3自然段，各读两遍，读给家长听；',
                          '不用录音，也不用上传，明早我抽听']

    def _work(self, title, lines=None, subject=''):
        return family_agenda.work_kind(title, lines or [], subject)

    def test_the_reading_card_asks_for_a_parent_confirmation(self):
        work = self._work('朗读《风经过小巷》第2、3自然段')
        self.assertEqual(work, {'kind': 'read_aloud', 'label': '朗读', 'evidence': 'confirm', 'need_photo': False})

    def test_following_the_teacher_aloud_is_read_aloud(self):
        self.assertEqual(self._work('英语：跟读Unit 7第3—10个单词')['kind'], 'read_aloud')

    def test_a_recognition_card_is_practice_not_reading(self):
        self.assertEqual(self._work('语文：完成《识字小卡》练习')['kind'], 'practice')

    def test_a_page_of_items_is_practice(self):
        self.assertEqual(self._work('数学：完成练习册第12页第2至4题')['kind'], 'practice')

    def test_handing_in_a_receipt_asks_for_a_photo(self):
        self.assertEqual(self._work('交回《出游回执》'),
                         {'kind': 'errand', 'label': '事务', 'evidence': 'photo', 'need_photo': True})

    def test_bringing_crayons_asks_for_a_confirmation_not_a_photo(self):
        self.assertEqual(self._work('明天带彩笔'),
                         {'kind': 'errand', 'label': '事务', 'evidence': 'confirm', 'need_photo': False})

    def test_dictation_asks_for_a_photo(self):
        self.assertEqual(self._work('听写第3课单词')['kind'], 'dictation')
        self.assertTrue(self._work('听写第3课单词')['need_photo'])

    def test_a_negated_reading_does_not_make_the_card_reading(self):
        self.assertEqual(self._work('语文：不用朗读，只要抄写两遍')['kind'], 'practice')

    def test_a_negated_signature_is_not_a_photo_request(self):
        work = self._work('明天把表带来，不用签字')
        self.assertEqual(work['kind'], 'errand')
        self.assertFalse(work['need_photo'])

    def test_a_chat_with_a_parent_is_not_learnable_work(self):
        self.assertEqual(self._work('和妈妈聊今天的事'),
                         {'kind': 'other', 'label': '其他', 'evidence': 'none', 'need_photo': False})

    def test_checking_answers_comes_before_practice(self):
        out = self._work('数学：完成第3页后对照答案批改', ['每题写出算式。'])
        self.assertEqual(out['kind'], 'check')
        self.assertTrue(out['need_photo'])

    def test_a_handmade_poster_is_craft(self):
        self.assertEqual(self._work('美术：做一张秋天手抄报')['kind'], 'craft')

    def test_reading_a_book_asks_for_a_log(self):
        self.assertEqual(self._work('阅读《城南旧事》', ['读完写两句摘抄']),
                         {'kind': 'reading', 'label': '阅读', 'evidence': 'log', 'need_photo': False})

    def test_reciting_is_read_aloud_and_never_a_photo(self):
        out = self._work('语文：背诵《静夜思》')
        self.assertEqual((out['kind'], out['evidence'], out['need_photo']), ('read_aloud', 'confirm', False))

    def test_the_title_and_the_lines_are_judged_together(self):
        self.assertEqual(self._work('数学：完成《每日练习》', ['第3页第1—4题。'])['kind'], 'practice')

    def test_a_result_has_exactly_the_four_contract_keys(self):
        work = self._work('和妈妈聊今天的事')
        self.assertEqual(set(work), {'kind', 'label', 'evidence', 'need_photo'})

    def _real_row(self, title, lines):
        task = {'id': 'task-work-1', 'child': CHILD['name'], 'title': title, 'action': '\n'.join(lines),
                'action_lines': list(lines), 'focus': None, 'source': 'school', 'school_origin': True,
                'progress': None}
        agenda = {'due_on': DAY, 'due_kind': 'deadline', 'category': 'homework', 'scheduled_on': DAY}
        item = {'id': 'item-work-1', 'kind': 'task', 'task_id': task['id'], 'title': title,
                'child_ids': [CHILD['id']], 'agenda': agenda, 'closed': False, 'status': '待跟进'}
        view = family_agenda.day_view([item], [task], [], CHILD, DAY, DAY, 'wrong')
        return view['groups'][0]['items'][0]

    def test_the_real_english_card_is_practice(self):
        row = self._real_row(self.REAL_ENGLISH_TITLE, self.REAL_ENGLISH_LINES)
        self.assertIn('work', row)
        self.assertEqual(row['work']['kind'], 'practice')

    def test_the_real_math_card_is_practice(self):
        row = self._real_row(self.REAL_MATH_TITLE, self.REAL_MATH_LINES)
        self.assertIn('work', row)
        self.assertEqual(row['work']['kind'], 'practice')

    def test_the_real_reading_card_is_read_aloud(self):
        row = self._real_row(self.REAL_CHINESE_TITLE, self.REAL_CHINESE_LINES)
        self.assertIn('work', row)
        self.assertEqual(row['work']['kind'], 'read_aloud')


if __name__ == '__main__':
    unittest.main()

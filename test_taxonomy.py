import hashlib, json, os, sqlite3, tempfile, unittest
from unittest import mock
from pathlib import Path
import family_taxonomy as ft

# 全部为虚构小图谱，不代表上游题库或教师审核内容。
TOPICS = [
    {'id': 'cnm_010', 'name': '有理数的加法法则', 'chapter': '七上 第二章 有理数的运算 2.1.1'},
    {'id': 'cnm_011', 'name': '有理数的减法法则', 'chapter': '七上 第二章 有理数的运算 2.1.2'},
    {'id': 'cnm_008', 'name': '绝对值化简与计算', 'chapter': '七上 第一章 有理数 1.2.4'},
    {'id': 'cne_001', 'name': '有理数的加法法则', 'subject': 'english'},
]
REC = {'id': 'w1', 'child_id': 'kid-a', 'question': '(-3)+5=?', 'answer': '-8', 'updated_at': 1}


class TaxonomyTest(unittest.TestCase):
    def setUp(self): self.db = sqlite3.connect(':memory:')

    def test_search_unique_ambiguous_none_unclear(self):
        self.assertEqual(ft.search(TOPICS, '有理数的加法法则')['status'], 'unique')
        self.assertEqual(ft.search(TOPICS, '有理数的加法法则')['candidates'][0]['id'], 'cnm_010')
        self.assertEqual(ft.search(TOPICS, '有理数 七上')['status'], 'ambiguous')
        self.assertEqual(ft.search(TOPICS, '三角函数')['status'], 'none')
        self.assertEqual(ft.search(TOPICS, '  ')['status'], 'unclear')
        self.assertNotIn('cne_001', [c['id'] for c in ft.search(TOPICS, '加法')['candidates']])

    def test_cross_child_rejected_with_zero_write(self):
        with self.assertRaises(ft.TaxonomyError) as e:
            ft.link(self.db, 'kid-b', REC, 'cnm_010', 'confirmed', 'r1', TOPICS)
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(self.db.execute("SELECT count(*) FROM sqlite_master WHERE name='topic_links'").fetchone()[0], 0)
        with self.assertRaises(ft.TaxonomyError): ft.links(self.db, 'kid-b', REC)

    def test_link_idempotent_and_basis_changed_after_correction(self):
        ft.link(self.db, 'kid-a', REC, 'cnm_010', 'confirmed', 'r1', TOPICS)
        out = ft.link(self.db, 'kid-a', REC, 'cnm_010', 'confirmed', 'r1', TOPICS)  # 丢回执重试
        self.assertEqual(len(out), 1); self.assertEqual(out[0]['basis'], 'current')
        corrected = dict(REC, answer='2', updated_at=2)
        after = ft.links(self.db, 'kid-a', corrected)
        self.assertEqual(after[0]['basis'], 'basis_changed'); self.assertEqual(after[0]['topic_id'], 'cnm_010')

    def test_unclear_and_no_match_bind_no_topic(self):
        self.assertEqual(ft.link(self.db, 'kid-a', REC, '', 'no_match', 'r2')[0]['state'], 'no_match')
        with self.assertRaises(ft.TaxonomyError): ft.link(self.db, 'kid-a', REC, 'cnm_010', 'unclear', 'r3')
        with self.assertRaises(ft.TaxonomyError): ft.link(self.db, 'kid-a', REC, 'cnm_999', 'confirmed', 'r4', TOPICS)

    def test_pack_status_missing_and_sha_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(ft.pack_status(tmp)['installed'])
            Path(tmp, 'a.json').write_bytes(b'[]')
            good = {'a.json': (hashlib.sha256(b'[]').hexdigest(), 2)}
            self.assertTrue(ft.pack_status(tmp, good)['installed'])
            Path(tmp, 'a.json').write_bytes(b'[1]')
            self.assertEqual(ft.pack_status(tmp, {'a.json': (good['a.json'][0], 3)})['problems'][0]['problem'], 'sha256_mismatch')


# 虚构：只核对年级分组与排序，不代表上游内容。
GRADED = [
    {'id': 'cnm_g1a', 'name': '10以内的加法', 'grade': 1, 'semester': '上', 'chapter': '一年级上册 第2单元 6～10的认识和加、减法'},
    {'id': 'cnm_g1b', 'name': '20以内不进位加法', 'grade': 1, 'semester': '上', 'chapter': '一年级上册 第4单元 11～20的认识'},
    {'id': 'cnm_g7a', 'name': '有理数的加法法则', 'grade': 7, 'semester': '上', 'chapter': '七上 第二章 有理数的运算 2.1.1'},
    {'id': 'cnm_g7b', 'name': '加法运算律与简便运算', 'grade': 7, 'semester': '上', 'chapter': '七上 第二章 有理数的运算 2.1.1'},
    {'id': 'cnm_g11', 'name': '向量加法', 'grade': 11, 'semester': '上', 'chapter': '高二 第六章 平面向量及其应用 6.2'},
]


class DiscoveryTest(unittest.TestCase):
    """家长日常说法找候选：只是候选，必须再点“就是这个”；不当诊断依据、不改掌握。"""
    def ids(self, out): return [c['id'] for c in out['candidates']]

    def test_everyday_phrase_without_spaces_finds_a_candidate_only(self):
        out = ft.search(TOPICS, '有理数加法')
        self.assertIn(out['status'], ('unique', 'ambiguous')); self.assertEqual(self.ids(out)[0], 'cnm_010')
        self.assertNotIn('cne_001', self.ids(out))
        self.assertFalse({'state', 'link', 'links', 'confirmed'} & set(out))

    def test_existing_queries_keep_their_results(self):
        self.assertEqual(ft.search(TOPICS, '有理数的加法法则')['status'], 'unique')
        self.assertEqual(ft.search(TOPICS, '有理数 七上')['status'], 'ambiguous')
        self.assertEqual(ft.search(TOPICS, '有理数 加法')['candidates'][0]['id'], 'cnm_010')

    def test_true_no_match_nonmath_and_empty_stay_none_or_unclear(self):
        for q in ('三角函数', '现在完成时', 'present perfect', '背诵古诗'):
            self.assertEqual(ft.search(TOPICS, q)['status'], 'none', q)
        for q in ('', '  ', '，。、', None):
            self.assertEqual(ft.search(TOPICS, q)['status'], 'unclear', q)

    def test_broad_query_puts_the_stated_grade_first_and_keeps_other_grades_reachable(self):
        out = ft.search(GRADED, '加法', limit=2, child_grades=(7,))
        self.assertEqual(self.ids(out), ['cnm_g7a', 'cnm_g7b']); self.assertEqual(out['total'], 5)
        self.assertEqual([(g['grade'], g['label'], g['count'], g['child']) for g in out['groups']],
                         [(7, '七年级', 2, True), (1, '一年级', 2, False), (11, '高二', 1, False)])
        only = ft.search(GRADED, '加法', limit=2, child_grades=(7,), grade=1)
        self.assertEqual(self.ids(only), ['cnm_g1a', 'cnm_g1b']); self.assertEqual(only['grade'], 1)
        self.assertEqual(len(only['groups']), 3)  # 只看一个年级时，其他年级仍能点回去
        self.assertEqual(ft.search(GRADED, '加法', grade=5)['status'], 'none')

    def test_unknown_grade_is_not_guessed_and_keeps_the_pack_order(self):
        out = ft.search(GRADED, '加法', limit=2)
        self.assertEqual(self.ids(out), ['cnm_g1a', 'cnm_g1b'])
        self.assertFalse(any(g['child'] for g in out['groups'])); self.assertIn(7, [g['grade'] for g in out['groups']])

    def test_child_grade_comes_only_from_the_stated_grade_text(self):
        for text, want in {'七年级': (7,), '初一': (7,), '初中一年级': (7,), '7年级': (7,), '小学四年级': (4,), '四年级': (4,), '九年级': (9,),
                           '初中': (7, 8, 9), '高二': (10, 11, 12, 13, 14), '未填写': (), '': (), None: (), '12岁': (), '大班': ()}.items():
            self.assertEqual(ft.child_grades(text), want, text)


PACK = os.environ.get('FAMILY_TAXONOMY_DIR', '')


@unittest.skipUnless(PACK and ft.pack_status(PACK)['installed'], '需要本机固定e0f931b原包（FAMILY_TAXONOMY_DIR）')
class OriginalPackDiscoveryTest(unittest.TestCase):
    """固定e0f931b原包：Root复现的反例与留出样例。只核对能找到候选，不是诊断或掌握依据。"""
    @classmethod
    def setUpClass(cls): cls.topics = ft.load_pack(PACK)['topics']

    def names(self, q, **kw): return [c['name'] for c in ft.search(self.topics, q, **kw)['candidates']]

    def test_root_counterexample(self):
        for grades in ((7,), ()):
            self.assertEqual(ft.search(self.topics, '有理数加法', child_grades=grades)['candidates'][0]['id'], 'cnm_010', grades)
        broad = ft.search(self.topics, '加法', child_grades=(7,))
        self.assertIn('cnm_010', [c['id'] for c in broad['candidates']])
        self.assertTrue({1, 2, 4, 5}.issubset({g['grade'] for g in broad['groups']}))  # 先修年级不被排除
        self.assertNotIn('cnm_010', [c['id'] for c in ft.search(self.topics, '加法')['candidates']])  # 年级未填不猜，仍按原包顺序
        chosen = ft.search(self.topics, '加法', grade=7)
        self.assertIn('cnm_010', [c['id'] for c in chosen['candidates']]); self.assertTrue(all(c['grade'] == 7 for c in chosen['candidates']))
        exact = ft.search(self.topics, '有理数的加法法则')
        self.assertEqual((exact['status'], exact['total'], exact['candidates'][0]['id']), ('unique', 1, 'cnm_010'))
        self.assertEqual(ft.search(self.topics, '现在完成时')['status'], 'none')

    def test_held_out_everyday_phrases(self):
        # 改动前写定：取自原包随机抽样（种子20261031）与相邻法则，按家长口头说法改写；不按实现结果挑选。
        cases = {'梯形面积': '梯形的面积', '三角形面积': '三角形的面积', '圆面积': '圆的面积', '二元一次方程的解': '二元一次方程及其解',
                 '一次函数性质': '一次函数的性质', '一元二次方程概念': '一元二次方程的概念', '扇形的面积': '扇形面积',
                 '有理数减法': '有理数的减法法则', '分式混合运算': '分式的混合运算与化简求值', '三角形分类': '三角形的概念与分类'}
        self.assertEqual({q: want for q, want in cases.items() if want not in self.names(q)}, {})


class UnitEvidenceTest(unittest.TestCase):
    """Fictional questions only. The engine and DeepTutor read numbers permissively in both directions (4.3角 judged 对 for a
    4.3元 standard; 43角, equal in amount, judged 错), so a component 对 stands only when numeric_evidence proves the whole answer
    and a 错 only when it proves the answer unequal; anything else goes to a parent. Earlier versions of this class asserted the
    reported gaps (unreadable answers and a missing pack kept as saved; 错 never re-read); those expectations are inverted here."""
    Q = {'id': 'syn_q1', 'topicId': 'syn_t', 'type': 'numeric', 'prompt': '虚构：一支笔2.5元，一把尺1.8元。一共多少元？', 'answer': '4.3'}

    def test_a_pass_stands_only_when_the_whole_answer_is_proved(self):
        for ans in ('4.3', '4.30', '4.3元', '４.３元', ' 4.3元 ', '+4.3', '0004.3', '答：4.3', '答:4.3元', ' 答 ： 4.3 '):
            self.assertEqual(ft.numeric_evidence(self.Q, ans), ('agree', ''), ans); self.assertEqual(ft.verdict_doubt(self.Q, ans, 'correct'), '', ans)
        for ans, state in (('4.3角', 'unproven'), ('4.3分', 'unproven'), ('4.3米', 'unproven'), ('4.3元钱', 'unproven'), ('答：4.3角', 'unproven'), ('43', 'contradicts'),
                           ('-4.3', 'contradicts'), ('5.2元', 'contradicts'), ('4.3，4.3', 'contradicts'), ('答：一共4.3元', 'unread'), ('43/10', 'unread'), ('3.5+0.8', 'unread'),
                           ('约4.3', 'unread'), ('4.3元。。', 'unread'), ('', 'unread'), ('1/2角', 'unread'), ('4.3' + '，4.3' * 150, 'contradicts')):
            self.assertEqual(ft.numeric_evidence(self.Q, ans)[0], state, ans); self.assertIn('现在待家长核对', ft.verdict_doubt(self.Q, ans, 'correct'), ans)
        zero = dict(self.Q, prompt='虚构：还剩多少元？', answer='0')
        for ans in ('0', '0.0', '-0', '0元', '答：0'): self.assertEqual(ft.verdict_doubt(zero, ans, 'correct'), '', ans)  # zero stays
        self.assertIn('角', ft.verdict_doubt(zero, '0角', 'correct'))
        self.assertEqual(ft.verdict_doubt(dict(self.Q, prompt='虚构：绳长多少米？', answer='0.5米'), '50厘米', 'correct'), '')  # metric shift
        self.assertEqual(ft.verdict_doubt(dict(self.Q, prompt='虚构：有几个？', answer='5'), '5个', 'correct'), '')
        fraction = dict(self.Q, answer='3/4')
        self.assertEqual(ft.numeric_evidence(fraction, '0.75')[0], 'unsupported'); self.assertEqual(ft.numeric_evidence(fraction, '３/４'), ('agree', ''))
        self.assertEqual(ft.numeric_evidence(dict(self.Q, answer='4.3元', prompt='虚构：一共多少钱？'), '4.3')[0], 'unproven')  # no unit written
        self.assertEqual(ft.numeric_evidence(dict(self.Q, type='short', answer='12'), '12个')[0], 'unproven')  # a numeric standard is numeric
        self.assertEqual(ft.unit_doubt(self.Q, '4.3角'), ft.verdict_doubt(self.Q, '4.3角', 'correct'))

    def test_a_miss_stands_only_when_the_answer_is_proved_unequal(self):
        for ans in ('43', '5.2', '5.2元', '-4.3', '答：5.2', '0.43'):
            self.assertEqual(ft.verdict_doubt(self.Q, ans, 'wrong'), '', ans)  # clearly unequal stays 错
        for ans in ('43角', '4.3元', '4.3', '答：一共5.2元', '43/10', '5.2角'):
            self.assertIn('“错”没有被证实', ft.verdict_doubt(self.Q, ans, 'wrong'), ans)  # equal, unread or unit-unproven: a parent checks
        for q, ans, verdict in ((dict(self.Q, type='choice', answer='B'), 'C', 'wrong'), (dict(self.Q, type='choice', answer='B'), 'B', 'correct'),
                                (dict(self.Q, type='short', answer='直角'), '锐角', 'wrong'), ({'id': 'x', 'prompt': '虚构'}, '2', 'correct'), (self.Q, '4.3角', 'manual'), (self.Q, '4.3角', 'skip')):
            self.assertEqual(ft.verdict_doubt(q, ans, verdict), '', (q, ans, verdict))  # choice, text, manual and skip: as before

    def test_items_and_attempts_read_the_one_rule_and_keep_the_rows(self):
        pack = {'questions': [self.Q]}
        item = dict(seq=1, kind='answer', qid='syn_q1', topic_id='syn_t', answer='4.3角', verdict='correct', engine_result='correct'); before_item = dict(item)
        row = dict(outcome='independent_correct', qid='syn_q1', topic_id='syn_t', answer='4.3角', taxonomy_verdict='correct', deeptutor='{"is_correct": true, "independent": true}'); before = dict(row)
        miss = dict(row, outcome='independent_wrong', answer='43角', taxonomy_verdict='wrong', deeptutor='{"is_correct": false, "independent": true}')
        with mock.patch.object(ft, 'question', lambda p, qid: next((q for q in p['questions'] if q['id'] == qid), None)):
            self.assertIn('现在待家长核对', ft.item_doubt(item, pack)); self.assertEqual(item, before_item)
            self.assertEqual(ft.item_doubt(dict(item, answer='4.3元'), pack), ''); self.assertIn('“错”没有被证实', ft.item_doubt(dict(item, answer='43角', verdict='wrong'), pack))
            self.assertEqual(ft.item_doubt(dict(item, answer='43', verdict='wrong'), pack), ''); self.assertEqual(ft.item_doubt(dict(item, kind='skip', verdict='skip'), pack), '')
            self.assertEqual(ft.item_doubt(item, None), '')  # no pack: the panel cannot replay; the item stays as saved
            self.assertEqual(ft.evidence_view(row, pack)[0], 'parent_check'); self.assertEqual(row, before)
            for ans in ('4.3元', '答：4.3', '4.30'): self.assertEqual(ft.evidence_view(dict(row, answer=ans), pack), ('independent_correct', ''), ans)
            self.assertEqual(ft.evidence_view(miss, pack)[0], 'parent_check'); self.assertEqual(ft.evidence_view(dict(miss, answer='43'), pack), ('independent_wrong', ''))
            self.assertEqual(ft.evidence_view(dict(row, outcome='not_new'), pack), ('not_new', ''))
            self.assertEqual(ft.evidence_view(dict(row, outcome='parent_check'), pack)[0], 'parent_check')
            for other in (ft.evidence_view(dict(row, answer='4.3'), None), ft.evidence_view(dict(miss, answer='43'), None), ft.evidence_view(dict(row, answer='4.3', topic_id='other'), pack),
                          ft.evidence_view(dict(row, answer='4.3', qid='missing'), pack), ft.evidence_view(dict(row, answer='4.3', deeptutor='not json'), pack),
                          ft.evidence_view(dict(row, answer='4.3', deeptutor='{}'), pack), ft.evidence_view(dict(row, answer='4.3', taxonomy_verdict='manual'), pack),
                          ft.evidence_view(dict(miss, answer='43', taxonomy_verdict='correct', deeptutor='{"is_correct": true}'), pack)):
                self.assertEqual(other[0], 'parent_check', other); self.assertIn('核对不了', other[1])


if __name__ == '__main__':
    unittest.main()

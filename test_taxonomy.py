import hashlib, sqlite3, tempfile, unittest
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


if __name__ == '__main__':
    unittest.main()

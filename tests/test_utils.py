import unittest
from src.api import QuotaEntry, Status
from src.utils import filter_quotas, get_top_offenders, paginate_list, bytes_to_gb

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.quotas = [
            QuotaEntry(
                id="1", path="/ifs/data/share1", 
                hard_limit_bytes=100 * (1024**3), 
                soft_limit_bytes=80 * (1024**3),
                usage_bytes=95 * (1024**3), # 95%
                users=[], groups=[], access_zone="system"
            ),
            QuotaEntry(
                id="2", path="/ifs/data/share2", 
                hard_limit_bytes=100 * (1024**3), 
                soft_limit_bytes=80 * (1024**3),
                usage_bytes=85 * (1024**3), # 85%
                users=[], groups=[], access_zone="dmz"
            ),
            QuotaEntry(
                id="3", path="/ifs/data/archive", 
                hard_limit_bytes=100 * (1024**3), 
                soft_limit_bytes=80 * (1024**3),
                usage_bytes=50 * (1024**3), # 50%
                users=[], groups=[], access_zone="system"
            ),
        ]

    def test_filter_quotas_by_name(self):
        filtered = filter_quotas(self.quotas, share_name="share")
        self.assertEqual(len(filtered), 2)
        
        filtered = filter_quotas(self.quotas, share_name="archive")
        self.assertEqual(len(filtered), 1)

    def test_filter_quotas_by_zone(self):
        filtered = filter_quotas(self.quotas, access_zone="dmz")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, "2")

    def test_top_offenders(self):
        categories = get_top_offenders(self.quotas)
        self.assertEqual(len(categories["critical"]), 1) # >90
        self.assertEqual(len(categories["warning"]), 1)  # 80-90
        self.assertEqual(len(categories["notice"]), 0)   # 70-80 (none in this range)
        
        self.assertEqual(categories["critical"][0]["share_name"], "share1")

    def test_pagination(self):
        items = list(range(50))
        page1, total = paginate_list(items, page=1, page_size=20)
        self.assertEqual(len(page1), 20)
        self.assertEqual(total, 3)
        
        page3, _ = paginate_list(items, page=3, page_size=20)
        self.assertEqual(len(page3), 10)

    def test_bytes_to_gb(self):
        self.assertEqual(bytes_to_gb(1073741824), 1.0)
        self.assertEqual(bytes_to_gb(536870912), 0.5)

if __name__ == "__main__":
    unittest.main()

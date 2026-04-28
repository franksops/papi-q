import unittest
from src.api import QuotaEntry
from src.utils import filter_quotas, get_top_offenders, paginate_list, bytes_to_gb

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.quotas = [
            QuotaEntry("1", "/ifs/data/s1", 100*(1024**3), 0, 96*(1024**3), [], [], "System"), # 96% -> Critical
            QuotaEntry("2", "/ifs/data/s2", 100*(1024**3), 0, 85*(1024**3), [], [], "DMZ"),    # 85% -> Warning
            QuotaEntry("3", "/ifs/data/s3", 100*(1024**3), 0, 75*(1024**3), [], [], "System"), # 75% -> Notice
            QuotaEntry("4", "/ifs/data/s4", 100*(1024**3), 0, 50*(1024**3), [], [], "System"), # 50% -> Healthy
        ]

    def test_top_offenders_thresholds(self):
        cats = get_top_offenders(self.quotas)
        self.assertEqual(len(cats["critical"]), 1)
        self.assertEqual(len(cats["warning"]), 1)
        self.assertEqual(len(cats["notice"]), 1)
        self.assertEqual(cats["critical"][0]["share_name"], "s1")

    def test_filter_zone(self):
        self.assertEqual(len(filter_quotas(self.quotas, access_zone="DMZ")), 1)
        self.assertEqual(len(filter_quotas(self.quotas, access_zone="All")), 4)

    def test_bytes_to_gb_null(self):
        self.assertEqual(bytes_to_gb(0), 0.0)
        self.assertEqual(bytes_to_gb(None), 0.0)

if __name__ == "__main__":
    unittest.main()

import unittest
from src.api import QuotaEntry, _match_path_to_zone
from src.utils import get_top_offenders, bytes_to_gb

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

    def test_bytes_to_gb_null(self):
        self.assertEqual(bytes_to_gb(0), 0.0)
        self.assertEqual(bytes_to_gb(None), 0.0)

    def test_match_path_to_zone(self):
        """Test path to zone matching."""
        zones = {
            "System": "/ifs",
            "Zone1": "/ifs/data/zone1",
            "Zone2": "/ifs/data/zone2"
        }
        
        # Test exact zone base path match
        self.assertEqual(_match_path_to_zone("/ifs/data/zone1", zones), "Zone1")
        
        # Test path under zone
        self.assertEqual(_match_path_to_zone("/ifs/data/zone1/project1", zones), "Zone1")
        self.assertEqual(_match_path_to_zone("/ifs/data/zone1/deep/nested/path", zones), "Zone1")
        
        # Test different zone
        self.assertEqual(_match_path_to_zone("/ifs/data/zone2/project2", zones), "Zone2")
        
        # Test System default
        self.assertEqual(_match_path_to_zone("/ifs/other/path", zones), "System")
        
        # Test without /ifs prefix
        self.assertEqual(_match_path_to_zone("data/zone1/project", zones), "Zone1")
        
        # Test longest match wins
        self.assertEqual(_match_path_to_zone("/ifs/data/zone1", zones), "Zone1")

if __name__ == "__main__":
    unittest.main()

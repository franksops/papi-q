import unittest
import os
import shutil
from pathlib import Path
from unittest.mock import patch
import src.audit as audit

class TestAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("./test_audit_dir")
        self.test_dir.mkdir(exist_ok=True)
        self.patcher = patch('src.audit.DEFAULT_CONFIG_DIR', self.test_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_audit_history_globbing(self):
        # Create fake log files for different days
        cluster = "testcluster"
        day1 = self.test_dir / f"{cluster}_01012026.csv"
        day2 = self.test_dir / f"{cluster}_01022026.csv"
        
        for f in [day1, day2]:
            with open(f, "w") as out:
                out.write("timestamp,admin,cluster,action,share_name,path,old_limit_gb,new_limit_gb\n")
                # Extract day from filename testcluster_MMDDYEAR.csv (index 15)
                day = f.name.split("_")[-1][3] # simplified
                out.write(f"2026-01-0{day},admin,{cluster},TEST,/ifs/test,0,10\n")
        
        entries = audit.read_audit_log(cluster)
        self.assertEqual(len(entries), 2)
        # Verify sorting (newest first)
        self.assertEqual(entries[0]["timestamp"], "2026-01-02")

if __name__ == "__main__":
    unittest.main()

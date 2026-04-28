import unittest
import os
import csv
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import src.audit as audit

class TestAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("./test_audit_dir")
        self.test_dir.mkdir(exist_ok=True)
        self.patcher = patch('src.config.DEFAULT_CONFIG_DIR', self.test_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_write_audit_entry_naming(self):
        # Test that the log file is named correctly hostname_MMDDYEAR.csv
        cluster_name = "testcluster"
        datestamp = datetime.now().strftime("%m%d%Y")
        expected_filename = f"{cluster_name}_{datestamp}.csv"
        
        audit.write_audit_entry(
            admin="admin",
            cluster=cluster_name,
            action="TEST_ACTION",
            share_name="test_share",
            path="/ifs/test",
            old_limit_gb=10,
            new_limit_gb=20
        )
        
        expected_path = self.test_dir / expected_filename
        self.assertTrue(expected_path.exists())

    def test_audit_log_content(self):
        cluster_name = "content_test"
        audit.write_audit_entry(
            admin="admin_user",
            cluster=cluster_name,
            action="MODIFY",
            share_name="share1",
            path="/ifs/path1",
            old_limit_gb=100.5,
            new_limit_gb=200.7
        )
        
        datestamp = datetime.now().strftime("%m%d%Y")
        log_path = self.test_dir / f"{cluster_name}_{datestamp}.csv"
        
        with open(log_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["admin"], "admin_user")
            self.assertEqual(rows[0]["action"], "MODIFY")
            self.assertEqual(float(rows[0]["new_limit_gb"]), 200.7)

if __name__ == "__main__":
    unittest.main()

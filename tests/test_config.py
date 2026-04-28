import unittest
import os
import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import src.config as config

class TestConfig(unittest.TestCase):
    def setUp(self):
        # Use a temporary directory for config tests
        self.test_dir = Path("./test_config_dir")
        self.test_dir.mkdir(exist_ok=True)
        
        # Patch the default paths in the config module
        self.patcher1 = patch('src.config.DEFAULT_CONFIG_DIR', self.test_dir)
        self.patcher2 = patch('src.config.DEFAULT_CONFIG_FILE', self.test_dir / "config.json")
        self.patcher3 = patch('src.config.DEFAULT_CLUSTERS_FILE', self.test_dir / "clusters.json")
        
        self.patcher1.start()
        self.patcher2.start()
        self.patcher3.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_load_config_default(self):
        conf = config.load_config()
        self.assertEqual(conf["verify_ssl"], False)
        self.assertEqual(conf["max_retries"], 3)

    def test_add_and_load_cluster(self):
        config.add_cluster("test_cluster", "https://test:8080")
        clusters = config.load_clusters()
        self.assertIn("test_cluster", clusters)
        self.assertEqual(clusters["test_cluster"], "https://test:8080")

    def test_remove_cluster(self):
        config.add_cluster("to_remove", "https://remove:8080")
        config.remove_cluster("to_remove")
        clusters = config.load_clusters()
        self.assertNotIn("to_remove", clusters)

if __name__ == "__main__":
    unittest.main()

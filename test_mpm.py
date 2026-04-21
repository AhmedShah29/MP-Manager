"""Unit tests for Modpack Manager (mpm/core.py)"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

from mpm.core import (
    ModpackManager,
    handle_network_errors,
    LOADER_DEPENDENCY_MAP,
)


class TestJsonHelpers(unittest.TestCase):
    """Test _read_json and _write_json static helpers."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "test.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_read_missing_file_returns_none(self):
        result = ModpackManager._read_json(self.path)
        self.assertIsNone(result)

    def test_roundtrip_write_and_read(self):
        data = {"name": "test", "mods": [1, 2, 3]}
        ModpackManager._write_json(self.path, data)
        result = ModpackManager._read_json(self.path)
        self.assertEqual(result, data)


class TestExtractModData(unittest.TestCase):
    """Test _extract_mod_data helper."""

    def test_extract_with_valid_files(self):
        version_data = {
            "id": "ver123",
            "files": [{
                "filename": "mod.jar",
                "url": "https://example.com/mod.jar",
                "hashes": {"sha1": "abc", "sha512": "def"},
                "size": 1024
            }]
        }
        result = ModpackManager()._extract_mod_data(version_data)
        self.assertEqual(result["file_id"], "ver123")
        self.assertEqual(result["filename"], "mod.jar")
        self.assertEqual(result["sha1"], "abc")
        self.assertEqual(result["sha512"], "def")
        self.assertEqual(result["fileSize"], 1024)

    def test_extract_no_files_returns_none(self):
        result = ModpackManager()._extract_mod_data({})
        self.assertIsNone(result)


class TestNetworkErrorDecorator(unittest.TestCase):
    """Test handle_network_errors decorator."""

    def test_timeout_caught(self):
        import requests

        @handle_network_errors
        def boom():
            raise requests.Timeout()

        result = boom()
        self.assertIsNone(result)

    def test_connection_error_caught(self):
        import requests

        @handle_network_errors
        def boom():
            raise requests.ConnectionError()

        result = boom()
        self.assertIsNone(result)

    def test_keyboard_interrupt_propagates(self):
        """KeyboardInterrupt must NOT be caught by the network decorator."""
        @handle_network_errors
        def boom():
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            boom()

    def test_normal_return_preserved(self):
        @handle_network_errors
        def ok():
            return 42

        self.assertEqual(ok(), 42)


class TestLoaderVersionFetcher(unittest.TestCase):
    """Test _get_latest_loader_version with mocked responses."""

    @mock.patch("mpm.core.requests.get")
    def test_fabric_loader(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"version": "0.15.11"}]
        result = ModpackManager._get_latest_loader_version("fabric", "1.20.1")
        self.assertEqual(result, "0.15.11")

    @mock.patch("mpm.core.requests.get")
    def test_forge_loader(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "promos": {"1.20.1-recommended": "47.2.0"}
        }
        result = ModpackManager._get_latest_loader_version("forge", "1.20.1")
        self.assertEqual(result, "1.20.1-47.2.0")

    @mock.patch("mpm.core.requests.get")
    def test_neoforge_loader(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"versions": ["20.4.237"]}
        result = ModpackManager._get_latest_loader_version("neoforge", "1.20.4")
        self.assertEqual(result, "20.4.237")

    @mock.patch("mpm.core.requests.get")
    def test_quilt_loader(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"version": "0.26.0"}]
        result = ModpackManager._get_latest_loader_version("quilt", "1.20.1")
        self.assertEqual(result, "0.26.0")

    @mock.patch("mpm.core.requests.get")
    def test_unknown_loader_returns_none(self, mock_get):
        result = ModpackManager._get_latest_loader_version("unknown", "1.20.1")
        self.assertIsNone(result)


class TestModpackDataIO(unittest.TestCase):
    """Test modpack JSON I/O on a real temporary directory."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = ModpackManager.__new__(ModpackManager)
        self.manager.config = {"storage_path": self.tmpdir, "active_modpack": "testpack"}
        self.manager.active_modpack_path = Path(self.tmpdir) / "testpack"
        self.manager.active_modpack_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_missing_modpack_returns_none(self):
        result = self.manager._load_modpack_data("nonexistent")
        self.assertIsNone(result)

    def test_save_and_load_modpack_data(self):
        self.manager._save_modpack_data(
            "testpack", "1.0", "1.20.1", "fabric", "0.15.11", []
        )
        data = self.manager._load_modpack_data("testpack")
        self.assertIsNotNone(data)
        self.assertEqual(data["name"], "testpack")
        self.assertEqual(data["mc_version"], "1.20.1")
        self.assertEqual(data["loader"], "fabric")

    def test_save_and_load_mods_list(self):
        self.manager._save_modpack_data(
            "testpack", "1.0", "1.20.1", "fabric", "0.15.11",
            [{"project_id": "abc", "name": "TestMod"}]
        )
        mods = self.manager._get_mods_list()
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]["name"], "TestMod")


class TestArchiveCleanup(unittest.TestCase):
    """Test _cleanup_old_archives keeps only 10 builds."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = ModpackManager.__new__(ModpackManager)
        self.manager.active_modpack_path = Path(self.tmpdir)
        self.archive_dir = self.manager.active_modpack_path / "build_archive"
        self.archive_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cleanup_removes_oldest(self):
        # Create 12 fake archives
        for i in range(12):
            folder = self.archive_dir / f"build_2024010{i}"
            folder.mkdir()
        self.manager._cleanup_old_archives()
        remaining = list(self.archive_dir.glob("build_*"))
        self.assertEqual(len(remaining), 10)


class TestConstants(unittest.TestCase):
    def test_loader_dependency_map(self):
        self.assertIn("fabric", LOADER_DEPENDENCY_MAP)
        self.assertIn("forge", LOADER_DEPENDENCY_MAP)
        self.assertIn("quilt", LOADER_DEPENDENCY_MAP)
        self.assertIn("neoforge", LOADER_DEPENDENCY_MAP)


if __name__ == "__main__":
    unittest.main()

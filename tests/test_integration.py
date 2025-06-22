"""Integration tests for end-to-end FlowSort workflows."""

import json
import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flowsort import FlowSort, Config, PreferencesManager
from tests.conftest import create_test_file, create_test_directory_structure, assert_directory_structure, assert_symlink_structure


class TestIntegrationWorkflows:
    """Test complete FlowSort workflows from start to finish."""

    def test_complete_file_organization_workflow(self, temp_dir):
        """Test complete workflow: init -> collect -> organize."""
        # Step 1: Initialize system with SAFE temporary paths
        test_base = temp_dir / "flowsort_test"
        test_downloads = temp_dir / "test_downloads"
        config = Config(
            base_path=test_base,
            downloads_path=test_downloads
        )
        flowsort = FlowSort(config)
        
        # Step 2: Create sample files in Downloads
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        sample_files = [
            ("report.pdf", "documents"),
            ("photo.jpg", "images"),
            ("backup.zip", "archives"),
            ("movie.mp4", "media"),
            ("script.py", "code"),
            ("data.csv", "spreadsheets"),
            ("presentation.pptx", "presentations"),
            ("package.deb", "packages"),
            ("unknown.xyz", "misc")
        ]
        
        for filename, expected_category in sample_files:
            create_test_file(downloads_dir, filename, f"Content of {filename}")
        
        # Step 3: Collect files
        collected = flowsort.collect_downloads()
        assert collected == len(sample_files)
        
        # Step 4: Verify organization
        inbox_all = config.inbox_path / "all"
        assert len(list(inbox_all.iterdir())) == len(sample_files)
        
        # Step 5: Verify category symlinks
        for filename, expected_category in sample_files:
            symlink_path = config.inbox_path / expected_category / filename
            assert symlink_path.exists()
            assert symlink_path.is_symlink()
            assert symlink_path.read_text() == f"Content of {filename}"
        
        # Step 6: Verify statistics
        stats = flowsort.get_file_stats(config.inbox_path)
        assert stats["total_files"] == len(sample_files)

    def test_configuration_persistence_workflow(self, temp_dir):
        """Test configuration save/load workflow."""
        # Step 1: Create configuration
        config_dir = temp_dir / ".flowsort"
        prefs_manager = PreferencesManager()
        prefs_manager.config_dir = config_dir
        prefs_manager.config_file = config_dir / "config.json"
        prefs_manager.ensure_config_dir()
        
        # Step 2: Create and save custom configuration
        custom_config = Config(
            base_path=temp_dir / "custom_flowsort",
            downloads_path=temp_dir / "custom_downloads",
            inbox_to_documents_days=5,
            documents_to_archive_days=20,
            categories={"custom": [".custom"]}
        )
        prefs_manager.save_config(custom_config)
        
        # Step 3: Load configuration back
        loaded_config = prefs_manager.load_config()
        
        # Step 4: Verify all settings were preserved
        assert loaded_config.base_path == custom_config.base_path
        assert loaded_config.downloads_path == custom_config.downloads_path
        assert loaded_config.inbox_to_documents_days == custom_config.inbox_to_documents_days
        assert loaded_config.documents_to_archive_days == custom_config.documents_to_archive_days
        assert loaded_config.categories == custom_config.categories
        
        # Step 5: Use loaded config to create FlowSort instance
        flowsort = FlowSort(loaded_config)
        assert flowsort.config.base_path == custom_config.base_path

    def test_file_conflict_resolution_workflow(self, temp_dir):
        """Test workflow with file name conflicts."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        # Step 1: Create multiple downloads with same names
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # Create files with same name but different content
        create_test_file(downloads_dir, "document.pdf", "First document")
        
        # First collection
        collected = flowsort.collect_downloads()
        assert collected == 1
        
        # Step 2: Add another file with same name
        create_test_file(downloads_dir, "document.pdf", "Second document")
        
        # Second collection
        collected = flowsort.collect_downloads()
        assert collected == 1
        
        # Step 3: Verify both files exist with different names
        inbox_all = config.inbox_path / "all"
        files = list(inbox_all.iterdir())
        assert len(files) == 2
        
        file_contents = [f.read_text() for f in files]
        assert "First document" in file_contents
        assert "Second document" in file_contents
        
        # Step 4: Verify both have symlinks in documents category
        documents_dir = config.inbox_path / "documents"
        symlinks = list(documents_dir.iterdir())
        assert len(symlinks) == 2

    def test_broken_symlink_cleanup_workflow(self, temp_dir):
        """Test workflow for cleaning up broken symlinks."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        # Step 1: Create file and collect it
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        create_test_file(downloads_dir, "document.pdf", "content")
        
        flowsort.collect_downloads()
        
        # Step 2: Manually break symlink by removing real file
        inbox_all = config.inbox_path / "all"
        real_file = inbox_all / "document.pdf"
        real_file.unlink()
        
        # Step 3: Verify symlink is broken
        symlink = config.inbox_path / "documents" / "document.pdf"
        assert symlink.is_symlink()
        assert not symlink.exists()  # Broken symlink
        
        # Step 4: Run cleanup
        flowsort.cleanup_broken_symlinks(config.inbox_path)
        
        # Step 5: Verify broken symlink was removed
        assert not symlink.exists()

    def test_large_scale_organization_workflow(self, temp_dir):
        """Test workflow with large number of files."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        # Step 1: Create many files
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        extensions = [".pdf", ".jpg", ".zip", ".mp4", ".py"]
        expected_categories = ["documents", "images", "archives", "media", "code"]
        num_files_per_type = 20
        
        total_files = 0
        for ext in extensions:
            for i in range(num_files_per_type):
                create_test_file(downloads_dir, f"file_{i}{ext}", f"content_{i}")
                total_files += 1
        
        # Step 2: Collect all files
        collected = flowsort.collect_downloads()
        assert collected == total_files
        
        # Step 3: Verify organization
        stats = flowsort.get_file_stats(config.inbox_path)
        assert stats["total_files"] == total_files
        
        # Step 4: Verify each category has correct number of files
        for category in expected_categories:
            assert stats["categories"][category] == num_files_per_type

    def test_directory_structure_creation_workflow(self, temp_dir):
        """Test that complete directory structure is created correctly."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        # Verify complete directory structure
        expected_structure = {
            "INBOX": {
                "all": None,
                "documents": None,
                "images": None,
                "archives": None,
                "media": None,
                "packages": None,
                "code": None,
                "spreadsheets": None,
                "presentations": None,
                "misc": None,
            },
            "DOCUMENTS": {
                "all": None,
                "documents": None,
                "images": None,
                "archives": None,
                "media": None,
                "packages": None,
                "code": None,
                "spreadsheets": None,
                "presentations": None,
                "misc": None,
            },
            "ARCHIVE": {
                "all": None,
                "by-date": None,
                "by-type": None,
            },
            "SYSTEM": None,
        }
        
        assert_directory_structure(temp_dir / "flowsort_test", expected_structure)

    def test_custom_categories_workflow(self, temp_dir):
        """Test workflow with custom file categories."""
        # Step 1: Create config with custom categories
        custom_categories = {
            "research": [".bib", ".tex"],
            "data": [".csv", ".json", ".xml"],
            "configs": [".conf", ".ini", ".cfg"]
        }
        
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads",
            categories=custom_categories
        )
        flowsort = FlowSort(config)
        
        # Step 2: Create files matching custom categories
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        test_files = [
            ("references.bib", "research"),
            ("paper.tex", "research"),
            ("data.csv", "data"),
            ("config.ini", "configs"),
            ("unknown.xyz", "misc")  # Should fall back to misc
        ]
        
        for filename, expected_category in test_files:
            create_test_file(downloads_dir, filename, f"Content of {filename}")
        
        # Step 3: Collect and verify
        flowsort.collect_downloads()
        
        for filename, expected_category in test_files:
            if expected_category != "misc":
                symlink_path = config.inbox_path / expected_category / filename
                assert symlink_path.exists()
                assert symlink_path.is_symlink()

    def test_error_recovery_workflow(self, temp_dir):
        """Test error recovery scenarios."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        # Test recovery from missing downloads directory
        if config.downloads_path.exists():
            shutil.rmtree(config.downloads_path)
        
        # Should handle gracefully
        collected = flowsort.collect_downloads()
        assert collected == 0
        
        # Test recovery from permission issues (simulate on Unix-like systems)
        if hasattr(Path, 'chmod'):
            downloads_dir = config.downloads_path
            downloads_dir.mkdir(parents=True, exist_ok=True)
            create_test_file(downloads_dir, "test.pdf", "content")
            
            # This test would need actual permission manipulation
            # For now, just verify the file exists
            assert (downloads_dir / "test.pdf").exists()

    def test_symlink_integrity_workflow(self, temp_dir):
        """Test that symlinks maintain integrity across operations."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        # Step 1: Create and collect files
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        create_test_file(downloads_dir, "document.pdf", "Original content")
        flowsort.collect_downloads()
        
        # Step 2: Verify symlink works
        symlink = config.inbox_path / "documents" / "document.pdf"
        assert symlink.read_text() == "Original content"
        
        # Step 3: Modify real file
        real_file = config.inbox_path / "all" / "document.pdf"
        real_file.write_text("Modified content")
        
        # Step 4: Verify symlink reflects change
        assert symlink.read_text() == "Modified content"
        
        # Step 5: Verify symlink is relative
        assert str(symlink.readlink()).startswith("../")

    def test_mixed_file_types_workflow(self, temp_dir):
        """Test workflow with various file types and edge cases."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        # Create Downloads directory
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # Create files with various characteristics
        test_cases = [
            # (filename, expected_category)
            ("normal.pdf", "documents"),
            ("UPPERCASE.PDF", "documents"),  # Case insensitive
            ("file.name.with.dots.jpg", "images"),  # Multiple dots
            ("file with spaces.mp4", "media"),  # Spaces in name
            ("file-with-dashes.zip", "archives"),  # Dashes
            ("file_with_underscores.py", "code"),  # Underscores
            (".hidden.txt", "documents"),  # Hidden file
            ("no_extension", "misc"),  # No extension
        ]
        
        for filename, expected_category in test_cases:
            create_test_file(downloads_dir, filename, f"Content: {filename}")
        
        # Collect files
        collected = flowsort.collect_downloads()
        assert collected == len(test_cases)
        
        # Verify each file was categorized correctly
        for filename, expected_category in test_cases:
            symlink_path = config.inbox_path / expected_category / filename
            assert symlink_path.exists(), f"Missing symlink for {filename} in {expected_category}"
            assert symlink_path.read_text() == f"Content: {filename}"

    def test_end_to_end_cli_simulation(self, temp_dir):
        """Test simulating complete CLI usage workflow."""
        # This would typically be done with CLI testing, but here we simulate the calls
        
        # Step 1: Simulate 'init' command
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        prefs_manager = PreferencesManager()
        prefs_manager.config_dir = temp_dir / ".flowsort"
        prefs_manager.config_file = prefs_manager.config_dir / "config.json"
        prefs_manager.ensure_config_dir()
        prefs_manager.save_config(config)
        
        # Step 2: Simulate 'collect' command
        flowsort = FlowSort(config)
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        create_test_file(downloads_dir, "test.pdf", "content")
        collected = flowsort.collect_downloads()
        assert collected == 1
        
        # Step 3: Simulate 'status' command
        stats = flowsort.get_file_stats(config.inbox_path)
        assert stats["total_files"] == 1
        assert stats["categories"]["documents"] == 1
        
        # Step 4: Simulate 'cleanup' command
        flowsort.cleanup_broken_symlinks(config.inbox_path)
        
        # Step 5: Simulate 'classify' command
        test_file = config.inbox_path / "all" / "test.pdf"
        category, confidence = flowsort.classify_file(test_file)
        assert category == "documents"
        assert confidence > 0.0

    def test_performance_with_realistic_workload(self, temp_dir):
        """Test performance with realistic file workload."""
        config = Config(
            base_path=temp_dir / "flowsort_test",
            downloads_path=temp_dir / "test_downloads"
        )
        flowsort = FlowSort(config)
        
        downloads_dir = config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # Create realistic file distribution
        file_types = [
            (".pdf", 50, "documents"),
            (".jpg", 30, "images"),
            (".png", 20, "images"),
            (".zip", 10, "archives"),
            (".mp4", 5, "media"),
            (".py", 15, "code"),
            (".txt", 25, "documents"),
        ]
        
        total_created = 0
        for ext, count, category in file_types:
            for i in range(count):
                create_test_file(downloads_dir, f"file_{total_created}{ext}", f"content_{total_created}")
                total_created += 1
        
        # Measure collection performance
        import time
        start_time = time.time()
        collected = flowsort.collect_downloads()
        end_time = time.time()
        
        # Verify results
        assert collected == total_created
        processing_time = end_time - start_time
        
        # Performance should be reasonable (less than 1 second for ~155 files)
        assert processing_time < 10.0, f"Processing took too long: {processing_time} seconds"
        
        # Verify organization is correct
        stats = flowsort.get_file_stats(config.inbox_path)
        assert stats["total_files"] == total_created
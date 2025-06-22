"""Test core FlowSort functionality."""

import os
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flowsort import FlowSort, Config
from tests.conftest import create_test_file, create_test_directory_structure, assert_directory_structure, assert_symlink_structure


class TestFlowSort:
    """Test the main FlowSort class."""

    def test_flowsort_initialization(self, test_config):
        """Test FlowSort initialization."""
        flowsort = FlowSort(test_config)
        
        assert flowsort.config == test_config
        assert flowsort.heuristic_classifier is not None
        assert flowsort.llm_classifier is not None
        assert not flowsort.llm_classifier.enabled

    def test_setup_directories(self, test_config):
        """Test that directory structure is created correctly."""
        flowsort = FlowSort(test_config)
        
        # Check main directories
        assert test_config.inbox_path.exists()
        assert test_config.documents_path.exists()
        assert test_config.archive_path.exists()
        assert test_config.system_path.exists()
        
        # Check subdirectories
        assert (test_config.inbox_path / "all").exists()
        assert (test_config.documents_path / "all").exists()
        assert (test_config.archive_path / "all").exists()
        assert (test_config.archive_path / "by-date").exists()
        assert (test_config.archive_path / "by-type").exists()
        
        # Check category directories
        for category in test_config.categories.keys():
            assert (test_config.inbox_path / category).exists()
            assert (test_config.documents_path / category).exists()

    def test_setup_directories_with_invalid_config(self, temp_dir):
        """Test setup with invalid config paths."""
        config = Config(base_path=temp_dir)
        config.inbox_path = None
        
        with pytest.raises(ValueError, match="Config is not initialized"):
            FlowSort(config)

    def test_classify_file_heuristic_only(self, flowsort_instance, temp_dir):
        """Test file classification using heuristic classifier."""
        test_files = [
            ("document.pdf", "documents"),
            ("image.jpg", "images"),
            ("unknown.xyz", "misc"),
        ]
        
        for filename, expected_category in test_files:
            file_path = temp_dir / filename
            category, confidence = flowsort_instance.classify_file(file_path)
            
            assert category == expected_category
            assert 0.0 <= confidence <= 1.0

    def test_move_file_to_all_simple(self, flowsort_instance, temp_dir):
        """Test moving file to 'all' directory without conflicts."""
        # Create source file
        source_file = create_test_file(temp_dir / "source", "test.txt", "content")
        target_all_dir = temp_dir / "target" / "all"
        target_all_dir.mkdir(parents=True, exist_ok=True)
        
        # Move file
        result_path = flowsort_instance.move_file_to_all(source_file, target_all_dir)
        
        assert result_path == target_all_dir / "test.txt"
        assert result_path.exists()
        assert result_path.read_text() == "content"
        assert not source_file.exists()

    def test_move_file_to_all_with_conflict(self, flowsort_instance, temp_dir):
        """Test moving file with name conflict resolution."""
        target_all_dir = temp_dir / "target" / "all"
        target_all_dir.mkdir(parents=True, exist_ok=True)
        
        # Create existing file in target
        existing_file = create_test_file(target_all_dir, "test.txt", "existing")
        
        # Create source file with same name
        source_file = create_test_file(temp_dir / "source", "test.txt", "new content")
        
        # Move file
        result_path = flowsort_instance.move_file_to_all(source_file, target_all_dir)
        
        assert result_path == target_all_dir / "test_1.txt"
        assert result_path.exists()
        assert result_path.read_text() == "new content"
        assert existing_file.read_text() == "existing"  # Original unchanged
        assert not source_file.exists()

    def test_move_file_multiple_conflicts(self, flowsort_instance, temp_dir):
        """Test moving file with multiple name conflicts."""
        target_all_dir = temp_dir / "target" / "all"
        target_all_dir.mkdir(parents=True, exist_ok=True)
        
        # Create multiple existing files
        create_test_file(target_all_dir, "test.txt", "content1")
        create_test_file(target_all_dir, "test_1.txt", "content2")
        create_test_file(target_all_dir, "test_2.txt", "content3")
        
        # Create source file
        source_file = create_test_file(temp_dir / "source", "test.txt", "new content")
        
        # Move file
        result_path = flowsort_instance.move_file_to_all(source_file, target_all_dir)
        
        assert result_path == target_all_dir / "test_3.txt"
        assert result_path.exists()
        assert result_path.read_text() == "new content"

    def test_create_category_symlink(self, flowsort_instance, temp_dir):
        """Test creating category symlinks."""
        # Setup directories
        all_dir = temp_dir / "all"
        category_dir = temp_dir / "documents"
        all_dir.mkdir(parents=True, exist_ok=True)
        category_dir.mkdir(parents=True, exist_ok=True)
        
        # Create real file
        real_file = create_test_file(all_dir, "document.pdf", "content")
        
        # Create symlink
        flowsort_instance.create_category_symlink(real_file, category_dir)
        
        symlink_path = category_dir / "document.pdf"
        assert symlink_path.exists()
        assert symlink_path.is_symlink()
        
        # Check that symlink points to correct file with relative path
        expected_target = "../all/document.pdf"
        assert str(symlink_path.readlink()) == expected_target

    def test_create_category_symlink_replaces_existing(self, flowsort_instance, temp_dir):
        """Test that creating symlink replaces existing symlink."""
        all_dir = temp_dir / "all"
        category_dir = temp_dir / "documents"
        all_dir.mkdir(parents=True, exist_ok=True)
        category_dir.mkdir(parents=True, exist_ok=True)
        
        # Create real files
        real_file1 = create_test_file(all_dir, "document.pdf", "content1")
        real_file2 = create_test_file(all_dir, "document2.pdf", "content2")
        
        # Create initial symlink
        flowsort_instance.create_category_symlink(real_file1, category_dir)
        
        # Replace with new symlink (same name, different target)
        symlink_path = category_dir / "document.pdf"
        symlink_path.unlink()
        real_file2_renamed = all_dir / "document.pdf"
        real_file2.rename(real_file2_renamed)
        
        flowsort_instance.create_category_symlink(real_file2_renamed, category_dir)
        
        assert symlink_path.exists()
        assert symlink_path.is_symlink()
        assert symlink_path.read_text() == "content2"

    def test_collect_downloads_empty_directory(self, flowsort_instance, test_config):
        """Test collecting from empty downloads directory."""
        # Ensure downloads directory exists but is empty
        test_config.downloads_path.mkdir(parents=True, exist_ok=True)
        
        collected = flowsort_instance.collect_downloads()
        
        assert collected == 0

    def test_collect_downloads_nonexistent_directory(self, flowsort_instance):
        """Test collecting from non-existent downloads directory."""
        collected = flowsort_instance.collect_downloads()
        
        assert collected == 0

    def test_collect_downloads_with_files(self, flowsort_instance, test_config, create_sample_files):
        """Test collecting files from downloads directory."""
        collected = flowsort_instance.collect_downloads()
        
        assert collected == len(create_sample_files)
        
        # Check that files were moved to INBOX/all
        inbox_all = test_config.inbox_path / "all"
        assert len(list(inbox_all.iterdir())) == len(create_sample_files)
        
        # Check that category symlinks were created
        for file_path in create_sample_files:
            filename = file_path.name
            category, _ = flowsort_instance.classify_file(file_path)
            category_dir = test_config.inbox_path / category
            symlink_path = category_dir / filename
            
            assert symlink_path.exists(), f"Symlink missing for {filename} in {category}"
            assert symlink_path.is_symlink()

    def test_collect_downloads_skips_directories(self, flowsort_instance, test_config):
        """Test that collect_downloads skips directories."""
        downloads_dir = test_config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # Create files and directories
        create_test_file(downloads_dir, "file.txt", "content")
        (downloads_dir / "subdirectory").mkdir()
        
        collected = flowsort_instance.collect_downloads()
        
        assert collected == 1  # Only the file, not the directory
        assert (downloads_dir / "subdirectory").exists()  # Directory should remain

    def test_cleanup_broken_symlinks(self, flowsort_instance, test_config):
        """Test cleanup of broken symlinks."""
        category_dir = test_config.inbox_path / "documents"
        category_dir.mkdir(parents=True, exist_ok=True)
        
        # Create valid symlink
        all_dir = test_config.inbox_path / "all"
        all_dir.mkdir(parents=True, exist_ok=True)
        real_file = create_test_file(all_dir, "valid.pdf", "content")
        valid_symlink = category_dir / "valid.pdf"
        valid_symlink.symlink_to("../all/valid.pdf")
        
        # Create broken symlink
        broken_symlink = category_dir / "broken.pdf"
        broken_symlink.symlink_to("../all/nonexistent.pdf")
        
        # Run cleanup
        flowsort_instance.cleanup_broken_symlinks(test_config.inbox_path)
        
        # Valid symlink should remain, broken should be removed
        assert valid_symlink.exists()
        assert not broken_symlink.exists()

    def test_get_file_stats(self, flowsort_instance, test_config):
        """Test getting file statistics."""
        # Create some files in different categories
        all_dir = test_config.inbox_path / "all"
        documents_dir = test_config.inbox_path / "documents"
        images_dir = test_config.inbox_path / "images"
        
        all_dir.mkdir(parents=True, exist_ok=True)
        documents_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Create files in all directory
        create_test_file(all_dir, "doc1.pdf", "content")
        create_test_file(all_dir, "doc2.pdf", "content")
        create_test_file(all_dir, "img1.jpg", "content")
        
        # Create symlinks in category directories
        flowsort_instance.create_category_symlink(all_dir / "doc1.pdf", documents_dir)
        flowsort_instance.create_category_symlink(all_dir / "doc2.pdf", documents_dir)
        flowsort_instance.create_category_symlink(all_dir / "img1.jpg", images_dir)
        
        # Get stats
        stats = flowsort_instance.get_file_stats(test_config.inbox_path)
        
        assert stats["total_files"] == 3
        assert stats["categories"]["documents"] == 2
        assert stats["categories"]["images"] == 1

    def test_get_file_stats_empty_directory(self, flowsort_instance, test_config):
        """Test getting stats from empty directory."""
        stats = flowsort_instance.get_file_stats(test_config.inbox_path)
        
        assert stats["total_files"] == 0
        for category in test_config.categories.keys():
            assert stats["categories"][category] == 0

    def test_get_file_stats_nonexistent_all_directory(self, flowsort_instance, test_config):
        """Test getting stats when 'all' directory doesn't exist."""
        # Remove the all directory
        all_dir = test_config.inbox_path / "all"
        if all_dir.exists():
            shutil.rmtree(all_dir)
        
        stats = flowsort_instance.get_file_stats(test_config.inbox_path)
        
        assert stats["total_files"] == 0

    def test_error_handling_config_none_paths(self, temp_dir):
        """Test error handling when config has None paths."""
        config = Config(base_path=temp_dir)
        
        # Set some paths to None to trigger error
        config.inbox_path = None
        config.documents_path = temp_dir / "DOCUMENTS"
        config.archive_path = temp_dir / "ARCHIVE"
        config.system_path = temp_dir / "SYSTEM"
        
        with pytest.raises(ValueError):
            FlowSort(config)

    def test_move_file_preserves_permissions(self, flowsort_instance, temp_dir):
        """Test that moving files preserves permissions."""
        source_file = create_test_file(temp_dir / "source", "test.txt", "content")
        target_all_dir = temp_dir / "target" / "all"
        target_all_dir.mkdir(parents=True, exist_ok=True)
        
        # Set specific permissions
        source_file.chmod(0o644)
        original_stat = source_file.stat()
        
        # Move file
        result_path = flowsort_instance.move_file_to_all(source_file, target_all_dir)
        
        # Check permissions are preserved (on Unix-like systems)
        if os.name != 'nt':  # Skip on Windows
            assert result_path.stat().st_mode == original_stat.st_mode

    def test_symlink_creation_with_special_characters(self, flowsort_instance, temp_dir):
        """Test symlink creation with special characters in filenames."""
        all_dir = temp_dir / "all"
        category_dir = temp_dir / "documents"
        all_dir.mkdir(parents=True, exist_ok=True)
        category_dir.mkdir(parents=True, exist_ok=True)
        
        # Test files with special characters
        special_files = [
            "file with spaces.pdf",
            "file-with-dashes.pdf",
            "file_with_underscores.pdf",
            "file.with.dots.pdf",
        ]
        
        for filename in special_files:
            real_file = create_test_file(all_dir, filename, "content")
            flowsort_instance.create_category_symlink(real_file, category_dir)
            
            symlink_path = category_dir / filename
            assert symlink_path.exists()
            assert symlink_path.is_symlink()
            assert symlink_path.read_text() == "content"

    def test_concurrent_file_operations(self, flowsort_instance, temp_dir):
        """Test that file operations handle concurrent access gracefully."""
        target_all_dir = temp_dir / "target" / "all"
        target_all_dir.mkdir(parents=True, exist_ok=True)
        
        # Create multiple source files with same name
        source_files = []
        for i in range(5):
            source_dir = temp_dir / f"source_{i}"
            source_file = create_test_file(source_dir, "test.txt", f"content_{i}")
            source_files.append(source_file)
        
        # Move all files (simulating concurrent operations)
        result_paths = []
        for source_file in source_files:
            result_path = flowsort_instance.move_file_to_all(source_file, target_all_dir)
            result_paths.append(result_path)
        
        # All files should be moved with unique names
        assert len(set(result_paths)) == len(result_paths)  # All paths unique
        for i, result_path in enumerate(result_paths):
            assert result_path.exists()
            assert result_path.read_text() == f"content_{i}"

    def test_large_number_of_files(self, flowsort_instance, test_config):
        """Test performance with large number of files."""
        downloads_dir = test_config.downloads_path
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # Create many files
        num_files = 100
        for i in range(num_files):
            create_test_file(downloads_dir, f"file_{i}.txt", f"content_{i}")
        
        # Collect all files
        collected = flowsort_instance.collect_downloads()
        
        assert collected == num_files
        
        # Verify all files were processed
        inbox_all = test_config.inbox_path / "all"
        assert len(list(inbox_all.iterdir())) == num_files
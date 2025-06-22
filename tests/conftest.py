"""Test fixtures and utilities for FlowSort tests."""

import json
import tempfile
from pathlib import Path
from typing import Dict, List, Any
import pytest
from unittest.mock import Mock

# Import the classes we need to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flowsort import Config, PreferencesManager, FlowSort, HeuristicClassifier


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_config(temp_dir):
    """Create a test configuration with temporary paths - NEVER uses real user directories."""
    # Ensure we NEVER use real user directories in tests
    test_base = temp_dir / "flowsort_test"
    test_downloads = temp_dir / "test_downloads"
    
    return Config(
        base_path=test_base,
        inbox_path=test_base / "INBOX",
        documents_path=test_base / "DOCUMENTS", 
        archive_path=test_base / "ARCHIVE",
        downloads_path=test_downloads,  # Always in temp directory
        system_path=test_base / "SYSTEM",
        inbox_to_documents_days=7,
        documents_to_archive_days=30,
        inbox_to_archive_days=90,
        categories={
            "documents": [".pdf", ".doc", ".docx", ".txt", ".md"],
            "images": [".jpg", ".jpeg", ".png", ".gif"],
            "archives": [".zip", ".tar", ".gz"],
            "media": [".mp4", ".mp3", ".avi"],
            "code": [".py", ".js", ".html", ".css"],
            "spreadsheets": [".csv", ".xls", ".xlsx"],
            "presentations": [".ppt", ".pptx", ".odp"],
            "misc": []  # Catch-all category
        }
    )


@pytest.fixture
def mock_preferences_manager(temp_dir):
    """Create a mock PreferencesManager with temporary config directory."""
    manager = PreferencesManager()
    manager.config_dir = temp_dir / ".flowsort"
    manager.config_file = manager.config_dir / "config.json"
    manager.ensure_config_dir()
    return manager


@pytest.fixture
def sample_files():
    """Return a list of sample file names with various extensions."""
    return [
        "document.pdf",
        "image.jpg", 
        "archive.zip",
        "video.mp4",
        "script.py",
        "unknown.xyz",
        "README.md",
        "data.csv",
        "presentation.pptx",
        "music.mp3"
    ]


@pytest.fixture
def create_sample_files(temp_dir, sample_files):
    """Create actual sample files in the temp directory."""
    downloads_dir = temp_dir / "test_downloads"  # Match test_config downloads_path
    downloads_dir.mkdir(exist_ok=True)
    
    created_files = []
    for filename in sample_files:
        file_path = downloads_dir / filename
        file_path.write_text(f"Sample content for {filename}")
        created_files.append(file_path)
    
    return created_files


@pytest.fixture
def flowsort_instance(test_config):
    """Create a FlowSort instance with test configuration."""
    return FlowSort(test_config)


@pytest.fixture
def heuristic_classifier(test_config):
    """Create a HeuristicClassifier instance with test configuration."""
    return HeuristicClassifier(test_config)


@pytest.fixture
def mock_console():
    """Mock the Rich console for testing CLI output."""
    return Mock()


def create_test_file(directory: Path, filename: str, content: str = "test content") -> Path:
    """Utility function to create a test file."""
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / filename
    file_path.write_text(content)
    return file_path


def create_test_directory_structure(base_path: Path, structure: Dict[str, Any]) -> None:
    """
    Create a directory structure from a nested dictionary.
    
    Args:
        base_path: Base directory to create structure in
        structure: Dict where keys are directory/file names and values are:
                  - Dict for subdirectories
                  - String for file content
                  - None for empty directories
    """
    for name, content in structure.items():
        path = base_path / name
        
        if isinstance(content, dict):
            # It's a directory
            path.mkdir(parents=True, exist_ok=True)
            create_test_directory_structure(path, content)
        elif isinstance(content, str):
            # It's a file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        else:
            # Empty directory
            path.mkdir(parents=True, exist_ok=True)


def assert_directory_structure(path: Path, expected_structure: Dict[str, Any]) -> None:
    """
    Assert that a directory structure matches the expected structure.
    
    Args:
        path: Path to check
        expected_structure: Expected structure dict
    """
    for name, content in expected_structure.items():
        item_path = path / name
        assert item_path.exists(), f"Expected {item_path} to exist"
        
        if isinstance(content, dict):
            assert item_path.is_dir(), f"Expected {item_path} to be a directory"
            assert_directory_structure(item_path, content)
        elif isinstance(content, str):
            assert item_path.is_file(), f"Expected {item_path} to be a file"
            assert item_path.read_text() == content, f"Content mismatch in {item_path}"
        else:
            assert item_path.is_dir(), f"Expected {item_path} to be a directory"


def assert_symlink_structure(path: Path, expected_links: Dict[str, str]) -> None:
    """
    Assert that symlinks point to expected targets.
    
    Args:
        path: Directory containing symlinks
        expected_links: Dict mapping symlink names to expected target paths (relative)
    """
    for link_name, expected_target in expected_links.items():
        link_path = path / link_name
        assert link_path.exists(), f"Expected symlink {link_path} to exist"
        assert link_path.is_symlink(), f"Expected {link_path} to be a symlink"
        
        actual_target = link_path.readlink()
        assert str(actual_target) == expected_target, f"Symlink {link_path} points to {actual_target}, expected {expected_target}"


@pytest.fixture
def classification_test_cases():
    """Test cases for file classification."""
    return [
        # (filename, expected_category, expected_confidence_range)
        ("document.pdf", "documents", (0.8, 1.0)),
        ("image.jpg", "images", (0.8, 1.0)),
        ("archive.zip", "archives", (0.8, 1.0)),
        ("video.mp4", "media", (0.8, 1.0)),
        ("script.py", "code", (0.8, 1.0)),
        ("unknown.xyz", "misc", (0.5, 0.7)),
        ("text_file", "documents", (0.5, 0.7)),  # MIME type fallback
    ]


@pytest.fixture
def cli_test_args():
    """Common CLI test arguments."""
    return {
        "init": ["--base-path", "/tmp/test", "--save"],
        "collect": ["--yes"],
        "config": ["--show"],
        "status": [],
        "cleanup": [],
        "version": [],
    }
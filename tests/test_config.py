"""Test configuration and preferences management."""

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flowsort import Config, PreferencesManager


class TestConfig:
    """Test the Config pydantic model."""

    def test_config_default_values(self):
        """Test that Config creates with default values."""
        config = Config()
        
        assert config.base_path == Path.home()
        assert config.downloads_path == Path.home() / "Downloads"
        assert config.inbox_to_documents_days == 7
        assert config.documents_to_archive_days == 30
        assert config.inbox_to_archive_days == 90
        assert config.categories is not None
        assert "documents" in config.categories

    def test_config_custom_paths(self, temp_dir):
        """Test Config with custom paths."""
        config = Config(
            base_path=temp_dir,
            downloads_path=temp_dir / "CustomDownloads"
        )
        
        assert config.base_path == temp_dir
        assert config.downloads_path == temp_dir / "CustomDownloads"
        assert config.inbox_path == temp_dir / "INBOX"
        assert config.documents_path == temp_dir / "DOCUMENTS"
        assert config.archive_path == temp_dir / "ARCHIVE"
        assert config.system_path == temp_dir / "SYSTEM"

    def test_config_path_validation(self):
        """Test that paths are properly validated and expanded."""
        config = Config(
            base_path="~/test_base",
            downloads_path="~/test_downloads"
        )
        
        assert config.base_path.is_absolute()
        assert config.downloads_path.is_absolute()
        assert str(config.base_path).startswith(str(Path.home()))
        assert str(config.downloads_path).startswith(str(Path.home()))

    def test_config_time_validation(self):
        """Test time rule validation."""
        # Valid time rules
        config = Config(
            inbox_to_documents_days=5,
            documents_to_archive_days=15,
            inbox_to_archive_days=30
        )
        assert config.inbox_to_documents_days == 5
        assert config.documents_to_archive_days == 15
        assert config.inbox_to_archive_days == 30

    def test_config_invalid_time_rules(self):
        """Test that invalid time rules raise validation errors."""
        with pytest.raises(ValidationError):
            Config(inbox_to_documents_days=0)  # Below minimum
        
        with pytest.raises(ValidationError):
            Config(documents_to_archive_days=400)  # Above maximum

    def test_config_categories_structure(self):
        """Test the default categories structure."""
        config = Config()
        
        assert isinstance(config.categories, dict)
        expected_categories = ["documents", "images", "archives", "media", "packages", "code", "spreadsheets", "presentations"]
        
        for category in expected_categories:
            assert category in config.categories
            assert isinstance(config.categories[category], list)
            assert len(config.categories[category]) > 0

    def test_config_custom_categories(self):
        """Test Config with custom categories."""
        custom_categories = {
            "text": [".txt", ".md"],
            "data": [".csv", ".json"]
        }
        
        config = Config(categories=custom_categories)
        assert config.categories == custom_categories

    def test_config_json_serialization(self, temp_dir):
        """Test that Config can be serialized to JSON."""
        config = Config(base_path=temp_dir)
        
        json_data = config.model_dump_json()
        parsed_data = json.loads(json_data)
        
        assert "base_path" in parsed_data
        assert "categories" in parsed_data
        assert isinstance(parsed_data["categories"], dict)

    def test_config_json_deserialization(self, temp_dir):
        """Test that Config can be created from JSON data."""
        json_data = {
            "base_path": str(temp_dir),
            "downloads_path": str(temp_dir / "Downloads"),
            "inbox_to_documents_days": 10,
            "categories": {"test": [".test"]}
        }
        
        config = Config.model_validate(json_data)
        assert config.base_path == temp_dir
        assert config.inbox_to_documents_days == 10
        assert config.categories["test"] == [".test"]


class TestPreferencesManager:
    """Test the PreferencesManager class."""

    def test_preferences_manager_init(self, temp_dir):
        """Test PreferencesManager initialization."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        
        assert manager.config_dir.name == ".flowsort"
        assert manager.config_file.name == "config.json"

    def test_ensure_config_dir(self, temp_dir):
        """Test that config directory is created."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        
        manager.ensure_config_dir()
        
        assert manager.config_dir.exists()
        assert manager.config_dir.is_dir()
        
        gitignore_path = manager.config_dir / ".gitignore"
        assert gitignore_path.exists()
        
        gitignore_content = gitignore_path.read_text()
        assert "*" in gitignore_content
        assert "!.gitignore" in gitignore_content

    def test_load_config_default(self, temp_dir):
        """Test loading default config when no file exists."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        manager.ensure_config_dir()
        
        config = manager.load_config()
        
        assert isinstance(config, Config)
        assert config.base_path == Path.home()

    def test_save_and_load_config(self, temp_dir):
        """Test saving and loading configuration."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        manager.ensure_config_dir()
        
        # Create and save config
        original_config = Config(
            base_path=temp_dir,
            inbox_to_documents_days=5
        )
        manager.save_config(original_config)
        
        # Load config back
        loaded_config = manager.load_config()
        
        assert loaded_config.base_path == temp_dir
        assert loaded_config.inbox_to_documents_days == 5

    def test_load_config_invalid_json(self, temp_dir):
        """Test loading config with invalid JSON."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        manager.ensure_config_dir()
        
        # Write invalid JSON
        manager.config_file.write_text("invalid json content")
        
        # Should return default config
        config = manager.load_config()
        assert isinstance(config, Config)
        assert config.base_path == Path.home()

    def test_load_config_validation_error(self, temp_dir):
        """Test loading config with validation errors."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        manager.ensure_config_dir()
        
        # Write JSON with validation errors
        invalid_data = {
            "base_path": str(temp_dir),
            "inbox_to_documents_days": -5  # Invalid value
        }
        manager.config_file.write_text(json.dumps(invalid_data))
        
        # Should return default config
        config = manager.load_config()
        assert isinstance(config, Config)
        assert config.base_path == Path.home()

    def test_get_config_info(self, temp_dir):
        """Test getting configuration information."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        manager.ensure_config_dir()
        
        info = manager.get_config_info()
        
        assert "config_dir" in info
        assert "config_file" in info
        assert "config_exists" in info
        assert info["config_dir"] == manager.config_dir
        assert info["config_file"] == manager.config_file
        assert isinstance(info["config_exists"], bool)

    def test_config_file_exists_after_save(self, temp_dir):
        """Test that config file exists after saving."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        manager.ensure_config_dir()
        
        config = Config(base_path=temp_dir)
        manager.save_config(config)
        
        info = manager.get_config_info()
        assert info["config_exists"] is True
        assert manager.config_file.exists()

    def test_config_roundtrip_with_all_fields(self, temp_dir):
        """Test complete config roundtrip with all fields."""
        manager = PreferencesManager()
        manager.config_dir = temp_dir / ".flowsort"
        manager.config_file = manager.config_dir / "config.json"
        manager.ensure_config_dir()
        
        original_config = Config(
            base_path=temp_dir,
            downloads_path=temp_dir / "Downloads",
            inbox_to_documents_days=3,
            documents_to_archive_days=21,
            inbox_to_archive_days=60,
            categories={
                "custom1": [".c1", ".c2"],
                "custom2": [".c3", ".c4"]
            }
        )
        
        manager.save_config(original_config)
        loaded_config = manager.load_config()
        
        assert loaded_config.base_path == original_config.base_path
        assert loaded_config.downloads_path == original_config.downloads_path
        assert loaded_config.inbox_to_documents_days == original_config.inbox_to_documents_days
        assert loaded_config.documents_to_archive_days == original_config.documents_to_archive_days
        assert loaded_config.inbox_to_archive_days == original_config.inbox_to_archive_days
        assert loaded_config.categories == original_config.categories
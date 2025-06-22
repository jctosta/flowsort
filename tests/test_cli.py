"""Test CLI command functionality."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, Mock, call
from typer.testing import CliRunner
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flowsort import app, Config, PreferencesManager
from tests.conftest import create_test_file


class TestCLI:
    """Test CLI commands using typer's test runner."""

    def setup_method(self):
        """Set up test runner for each test."""
        self.runner = CliRunner()
    
    def create_mock_config(self, base_path="/test/base", downloads_path="/test/downloads"):
        """Create a properly mocked Config object."""
        mock_config = Mock(spec=Config)
        mock_config.base_path = Path(base_path)
        mock_config.downloads_path = Path(downloads_path)
        mock_config.inbox_path = Path(base_path) / "INBOX"
        mock_config.documents_path = Path(base_path) / "DOCUMENTS"
        mock_config.archive_path = Path(base_path) / "ARCHIVE"
        mock_config.system_path = Path(base_path) / "SYSTEM"
        return mock_config

    def test_version_command(self):
        """Test version command output."""
        result = self.runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        assert "FlowSort v1.0.0" in result.stdout
        assert "Digital Life Organization Tool" in result.stdout

    def test_help_command(self):
        """Test help output."""
        result = self.runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "FlowSort - Keep your digital life organized" in result.stdout
        assert "init" in result.stdout
        assert "collect" in result.stdout
        assert "config" in result.stdout

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_init_command_default(self, mock_flowsort, mock_prefs_manager):
        """Test init command with default settings."""
        # Setup mocks
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = self.create_mock_config()
        mock_manager.load_config.return_value = mock_config
        
        result = self.runner.invoke(app, ["init"])
        
        assert result.exit_code == 0
        assert "FlowSort initialized successfully!" in result.stdout
        mock_manager.load_config.assert_called_once()
        mock_manager.save_config.assert_called_once()
        mock_flowsort.assert_called_once_with(mock_config)

    @patch('flowsort.Config.model_validate')
    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_init_command_with_custom_paths(self, mock_flowsort, mock_prefs_manager, mock_model_validate):
        """Test init command with custom base and downloads paths."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        
        # Create a proper mock config with model_dump method
        mock_config = Mock(spec=Config)
        mock_config.model_dump.return_value = {
            "base_path": "/default/path",
            "downloads_path": "/default/downloads"
        }
        mock_config.base_path = Path("/default/path")
        mock_config.downloads_path = Path("/default/downloads")
        mock_manager.load_config.return_value = mock_config
        
        # Mock the new config created by model_validate
        mock_new_config = Mock(spec=Config)
        mock_new_config.base_path = Path("/custom/path")
        mock_new_config.downloads_path = Path("/custom/downloads")
        mock_model_validate.return_value = mock_new_config
        
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_base = str(Path(temp_dir) / "custom_base")
            custom_downloads = str(Path(temp_dir) / "custom_downloads")
            
            result = self.runner.invoke(app, [
                "init", 
                "--base-path", custom_base,
                "--downloads", custom_downloads
            ])
            
            if result.exit_code != 0:
                print(f"Command output: {result.stdout}")
                print(f"Exception: {result.exception}")
            
            assert result.exit_code == 0
            mock_manager.save_config.assert_called_once()

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_init_command_no_save(self, mock_flowsort, mock_prefs_manager):
        """Test init command with --no-save option."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = self.create_mock_config()
        mock_manager.load_config.return_value = mock_config
        
        result = self.runner.invoke(app, ["init", "--no-save"])
        
        assert result.exit_code == 0
        mock_manager.save_config.assert_not_called()

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_init_command_config_error(self, mock_flowsort, mock_prefs_manager):
        """Test init command with configuration error."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_manager.load_config.return_value = Mock()
        mock_flowsort.side_effect = ValueError("Configuration error")
        
        result = self.runner.invoke(app, ["init"])
        
        assert result.exit_code == 1
        assert "Configuration error" in result.stdout

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    @patch('flowsort.Confirm.ask')
    def test_collect_command_with_confirmation(self, mock_confirm, mock_flowsort, mock_prefs_manager):
        """Test collect command with user confirmation."""
        # Setup mocks
        mock_confirm.return_value = True
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_manager.load_config.return_value = mock_config
        
        mock_flowsort_instance = Mock()
        mock_flowsort.return_value = mock_flowsort_instance
        mock_flowsort_instance.collect_downloads.return_value = 5
        
        result = self.runner.invoke(app, ["collect"])
        
        assert result.exit_code == 0
        assert "Collected 5 files" in result.stdout
        mock_confirm.assert_called_once_with("Collect files from Downloads folder?")
        mock_flowsort_instance.collect_downloads.assert_called_once()

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    @patch('flowsort.Confirm.ask')
    def test_collect_command_with_rejection(self, mock_confirm, mock_flowsort, mock_prefs_manager):
        """Test collect command when user rejects confirmation."""
        mock_confirm.return_value = False
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        
        result = self.runner.invoke(app, ["collect"])
        
        assert result.exit_code == 1  # Aborted
        mock_confirm.assert_called_once()

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_collect_command_auto_confirm(self, mock_flowsort, mock_prefs_manager):
        """Test collect command with auto-confirm flag."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_manager.load_config.return_value = mock_config
        
        mock_flowsort_instance = Mock()
        mock_flowsort.return_value = mock_flowsort_instance
        mock_flowsort_instance.collect_downloads.return_value = 3
        
        result = self.runner.invoke(app, ["collect", "--yes"])
        
        assert result.exit_code == 0
        assert "Collected 3 files" in result.stdout
        mock_flowsort_instance.collect_downloads.assert_called_once()

    @patch('flowsort.PreferencesManager')
    def test_config_show_command(self, mock_prefs_manager):
        """Test config --show command."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        
        # Create a mock config
        mock_config = self.create_mock_config("/test/base", "/test/downloads")
        mock_config.inbox_to_documents_days = 7
        mock_config.documents_to_archive_days = 30
        mock_config.inbox_to_archive_days = 90
        
        mock_manager.load_config.return_value = mock_config
        mock_manager.get_config_info.return_value = {
            "config_dir": Path("/test/.flowsort"),
            "config_file": Path("/test/.flowsort/config.json"),
            "config_exists": True
        }
        
        result = self.runner.invoke(app, ["config", "--show"])
        
        if result.exit_code != 0:
            print(f"Command output: {result.stdout}")
            print(f"Exception: {result.exception}")
        
        assert result.exit_code == 0
        assert "FlowSort Configuration" in result.stdout
        assert "/test/base" in result.stdout

    @patch('flowsort.PreferencesManager')
    def test_config_edit_base_path(self, mock_prefs_manager):
        """Test config command to edit base path."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.model_dump.return_value = {"base_path": "/old/path"}
        mock_manager.load_config.return_value = mock_config
        
        result = self.runner.invoke(app, ["config", "--base-path", "/new/path"])
        
        assert result.exit_code == 0
        assert "Base path updated to: /new/path" in result.stdout
        mock_manager.save_config.assert_called_once()

    @patch('flowsort.PreferencesManager')
    def test_config_edit_time_rules(self, mock_prefs_manager):
        """Test config command to edit time rules."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.model_dump.return_value = {
            "inbox_to_documents_days": 7,
            "documents_to_archive_days": 30
        }
        mock_manager.load_config.return_value = mock_config
        
        result = self.runner.invoke(app, [
            "config", 
            "--inbox-days", "5",
            "--docs-days", "45"
        ])
        
        assert result.exit_code == 0
        assert "INBOX to DOCUMENTS days updated to: 5" in result.stdout
        assert "DOCUMENTS to ARCHIVE days updated to: 45" in result.stdout

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.Config.model_validate')
    def test_config_validation_error(self, mock_validate, mock_prefs_manager):
        """Test config command with validation error."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.model_dump.return_value = {"base_path": "/test"}
        mock_manager.load_config.return_value = mock_config
        
        mock_validate.side_effect = ValueError("Invalid configuration")
        
        result = self.runner.invoke(app, ["config", "--inbox-days", "0"])
        
        assert result.exit_code == 1
        assert "Configuration error" in result.stdout

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_status_command(self, mock_flowsort, mock_prefs_manager):
        """Test status command."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.inbox_path = Path("/test/inbox")
        mock_config.documents_path = Path("/test/documents")
        mock_config.archive_path = Path("/test/archive")
        mock_manager.load_config.return_value = mock_config
        
        mock_flowsort_instance = Mock()
        mock_flowsort.return_value = mock_flowsort_instance
        mock_flowsort_instance.get_file_stats.side_effect = [
            {"total_files": 5, "categories": {"documents": 3, "images": 2}},
            {"total_files": 10, "categories": {"documents": 8, "images": 2}},
            {"total_files": 100, "categories": {"documents": 50, "images": 50}}
        ]
        
        result = self.runner.invoke(app, ["status"])
        
        assert result.exit_code == 0
        assert "FlowSort Status" in result.stdout
        assert "INBOX" in result.stdout
        assert "DOCUMENTS" in result.stdout
        assert "ARCHIVE" in result.stdout

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_cleanup_command(self, mock_flowsort, mock_prefs_manager):
        """Test cleanup command."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.inbox_path = Path("/test/inbox")
        mock_config.documents_path = Path("/test/documents")
        mock_manager.load_config.return_value = mock_config
        
        mock_flowsort_instance = Mock()
        mock_flowsort.return_value = mock_flowsort_instance
        
        result = self.runner.invoke(app, ["cleanup"])
        
        assert result.exit_code == 0
        assert "Cleaning up broken symlinks" in result.stdout
        assert "Cleanup completed" in result.stdout
        assert mock_flowsort_instance.cleanup_broken_symlinks.call_count == 2

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_classify_command_existing_file(self, mock_flowsort, mock_prefs_manager):
        """Test classify command with existing file."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_manager.load_config.return_value = mock_config
        
        mock_flowsort_instance = Mock()
        mock_flowsort.return_value = mock_flowsort_instance
        mock_flowsort_instance.classify_file.return_value = ("documents", 0.9)
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_path = temp_file.name
            
            result = self.runner.invoke(app, ["classify", temp_path])
            
            assert result.exit_code == 0
            assert "documents" in result.stdout
            assert "0.90" in result.stdout
            
            # Clean up
            Path(temp_path).unlink()

    def test_classify_command_nonexistent_file(self):
        """Test classify command with non-existent file."""
        result = self.runner.invoke(app, ["classify", "/nonexistent/file.pdf"])
        
        assert result.exit_code == 1
        assert "File not found" in result.stdout

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_classify_command_no_confidence(self, mock_flowsort, mock_prefs_manager):
        """Test classify command without showing confidence."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_manager.load_config.return_value = mock_config
        
        mock_flowsort_instance = Mock()
        mock_flowsort.return_value = mock_flowsort_instance
        mock_flowsort_instance.classify_file.return_value = ("documents", 0.9)
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_path = temp_file.name
            
            result = self.runner.invoke(app, ["classify", temp_path, "--no-show-confidence"])
            
            assert result.exit_code == 0
            assert "documents" in result.stdout
            assert "0.90" not in result.stdout
            
            # Clean up
            Path(temp_path).unlink()

    def test_invalid_command(self):
        """Test invalid command handling."""
        result = self.runner.invoke(app, ["invalid-command"])
        
        assert result.exit_code != 0

    @patch('flowsort.PreferencesManager')
    def test_config_no_options(self, mock_prefs_manager):
        """Test config command with no options (should do nothing)."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_manager.load_config.return_value = mock_config
        
        result = self.runner.invoke(app, ["config"])
        
        assert result.exit_code == 0
        mock_manager.save_config.assert_not_called()

    @patch('flowsort.console')
    def test_console_output_mocking(self, mock_console):
        """Test that console output can be mocked for testing."""
        result = self.runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        # The console.print calls should work normally in CLI tests

    def test_command_help_outputs(self):
        """Test help output for individual commands."""
        commands = ["init", "collect", "config", "status", "cleanup", "classify"]
        
        for command in commands:
            result = self.runner.invoke(app, [command, "--help"])
            assert result.exit_code == 0
            assert command in result.stdout.lower()

    @patch('flowsort.PreferencesManager')
    @patch('flowsort.FlowSort')
    def test_multiple_config_edits(self, mock_flowsort, mock_prefs_manager):
        """Test multiple configuration edits in one command."""
        mock_manager = Mock()
        mock_prefs_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.model_dump.return_value = {
            "base_path": "/old/path",
            "downloads_path": "/old/downloads",
            "inbox_to_documents_days": 7
        }
        mock_manager.load_config.return_value = mock_config
        
        result = self.runner.invoke(app, [
            "config",
            "--base-path", "/new/path",
            "--downloads", "/new/downloads", 
            "--inbox-days", "5"
        ])
        
        assert result.exit_code == 0
        assert "Base path updated" in result.stdout
        assert "Downloads path updated" in result.stdout
        assert "INBOX to DOCUMENTS days updated" in result.stdout
        mock_manager.save_config.assert_called_once()

    def test_cli_with_missing_dependencies(self):
        """Test CLI behavior when dependencies are missing."""
        # This test would need to be run in an environment without the dependencies
        # For now, we just ensure the imports work
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
"""Test file classification functionality."""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flowsort import HeuristicClassifier, Config


class TestHeuristicClassifier:
    """Test the HeuristicClassifier class."""

    def test_classifier_initialization(self, test_config):
        """Test classifier initialization with config."""
        classifier = HeuristicClassifier(test_config)
        
        assert classifier.config == test_config
        assert isinstance(classifier.extension_map, dict)
        
        # Check that extension map is built correctly
        assert ".pdf" in classifier.extension_map
        assert classifier.extension_map[".pdf"] == "documents"
        assert ".jpg" in classifier.extension_map
        assert classifier.extension_map[".jpg"] == "images"

    def test_extension_map_building(self, temp_dir):
        """Test that extension map is built correctly from config."""
        config = Config(
            base_path=temp_dir,
            categories={
                "test_category": [".test1", ".test2"],
                "another_category": [".test3"]
            }
        )
        
        classifier = HeuristicClassifier(config)
        
        assert classifier.extension_map[".test1"] == "test_category"
        assert classifier.extension_map[".test2"] == "test_category"
        assert classifier.extension_map[".test3"] == "another_category"

    def test_extension_map_case_insensitive(self, temp_dir):
        """Test that extension mapping is case insensitive."""
        config = Config(
            base_path=temp_dir,
            categories={"docs": [".PDF", ".Doc"]}
        )
        
        classifier = HeuristicClassifier(config)
        
        # Extensions should be stored in lowercase
        assert ".pdf" in classifier.extension_map
        assert ".doc" in classifier.extension_map
        assert ".PDF" not in classifier.extension_map

    def test_classify_by_extension_direct_match(self, heuristic_classifier, temp_dir):
        """Test classification by direct extension match."""
        test_files = [
            ("document.pdf", "documents"),
            ("image.jpg", "images"),
            ("archive.zip", "archives"),
            ("video.mp4", "media"),
            ("script.py", "code"),
        ]
        
        for filename, expected_category in test_files:
            file_path = temp_dir / filename
            result = heuristic_classifier.classify_file(file_path)
            assert result == expected_category, f"Failed for {filename}"

    def test_classify_case_insensitive_extensions(self, heuristic_classifier, temp_dir):
        """Test that classification works with different case extensions."""
        test_files = [
            ("document.PDF", "documents"),
            ("image.JPG", "images"),
            ("archive.ZIP", "archives"),
        ]
        
        for filename, expected_category in test_files:
            file_path = temp_dir / filename
            result = heuristic_classifier.classify_file(file_path)
            assert result == expected_category, f"Failed for {filename}"

    @patch('mimetypes.guess_type')
    def test_classify_by_mime_type_fallback(self, mock_guess_type, heuristic_classifier, temp_dir):
        """Test classification fallback to MIME type."""
        test_cases = [
            ("unknown_file", "text/plain", "documents"),
            ("image_file", "image/png", "images"), 
            ("video_file", "video/mp4", "media"),
            ("audio_file", "audio/mpeg", "media"),
            ("pdf_file", "application/pdf", "documents"),
            ("zip_file", "application/zip", "archives"),
        ]
        
        for filename, mime_type, expected_category in test_cases:
            mock_guess_type.return_value = (mime_type, None)
            file_path = temp_dir / filename
            
            result = heuristic_classifier.classify_file(file_path)
            assert result == expected_category, f"Failed for {filename} with MIME {mime_type}"

    @patch('mimetypes.guess_type')
    def test_classify_unknown_file(self, mock_guess_type, heuristic_classifier, temp_dir):
        """Test classification of unknown file types."""
        mock_guess_type.return_value = (None, None)
        
        file_path = temp_dir / "unknown.xyz"
        result = heuristic_classifier.classify_file(file_path)
        
        assert result == "misc"

    @patch('mimetypes.guess_type')
    def test_classify_unknown_mime_type(self, mock_guess_type, heuristic_classifier, temp_dir):
        """Test classification with unknown MIME type."""
        mock_guess_type.return_value = ("application/unknown", None)
        
        file_path = temp_dir / "unknown.xyz"
        result = heuristic_classifier.classify_file(file_path)
        
        assert result == "misc"

    def test_get_confidence_direct_extension_match(self, heuristic_classifier, temp_dir):
        """Test confidence score for direct extension matches."""
        file_path = temp_dir / "document.pdf"
        category = "documents"
        
        confidence = heuristic_classifier.get_confidence(file_path, category)
        assert confidence == 0.9

    def test_get_confidence_mime_fallback(self, heuristic_classifier, temp_dir):
        """Test confidence score for MIME type fallback."""
        file_path = temp_dir / "unknown.xyz"  # No direct extension match
        category = "documents"
        
        confidence = heuristic_classifier.get_confidence(file_path, category)
        assert confidence == 0.6

    def test_get_confidence_wrong_category(self, heuristic_classifier, temp_dir):
        """Test confidence score when category doesn't match extension."""
        file_path = temp_dir / "document.pdf"
        wrong_category = "images"  # PDF should be documents, not images
        
        confidence = heuristic_classifier.get_confidence(file_path, wrong_category)
        assert confidence == 0.6  # Should be MIME fallback confidence

    def test_classify_files_with_no_extension(self, heuristic_classifier, temp_dir):
        """Test classification of files without extensions."""
        with patch('mimetypes.guess_type') as mock_guess_type:
            mock_guess_type.return_value = ("text/plain", None)
            
            file_path = temp_dir / "README"  # No extension
            result = heuristic_classifier.classify_file(file_path)
            
            assert result == "documents"

    def test_classify_files_with_multiple_dots(self, heuristic_classifier, temp_dir):
        """Test classification of files with multiple dots in name."""
        file_path = temp_dir / "file.name.with.dots.pdf"
        result = heuristic_classifier.classify_file(file_path)
        
        assert result == "documents"  # Should use the last extension (.pdf)

    def test_empty_categories_config(self, temp_dir):
        """Test classifier with empty categories configuration."""
        config = Config(base_path=temp_dir, categories={})
        classifier = HeuristicClassifier(config)
        
        assert len(classifier.extension_map) == 0
        
        file_path = temp_dir / "document.pdf"
        result = classifier.classify_file(file_path)
        
        # Should fall back to MIME type or misc
        assert result in ["documents", "misc"]

    def test_none_categories_config(self, temp_dir):
        """Test classifier with None categories configuration."""
        config = Config(base_path=temp_dir, categories=None)
        classifier = HeuristicClassifier(config)
        
        assert len(classifier.extension_map) == 0

    @patch('mimetypes.guess_type')
    def test_specific_mime_type_classifications(self, mock_guess_type, heuristic_classifier, temp_dir):
        """Test specific MIME type classification rules."""
        test_cases = [
            ("application/pdf", "documents"),
            ("application/zip", "archives"),
            ("application/x-tar", "archives"),
            ("application/x-compressed", "archives"),
            ("application/json", "misc"),  # Generic application type
        ]
        
        for mime_type, expected_category in test_cases:
            mock_guess_type.return_value = (mime_type, None)
            file_path = temp_dir / "test_file"
            
            result = heuristic_classifier.classify_file(file_path)
            assert result == expected_category, f"Failed for MIME type {mime_type}"

    def test_classification_with_symlinks(self, heuristic_classifier, temp_dir):
        """Test that classification works with symlinks."""
        # Create original file
        real_file = temp_dir / "real_document.pdf"
        real_file.write_text("content")
        
        # Create symlink
        symlink = temp_dir / "link_to_document.pdf"
        symlink.symlink_to(real_file)
        
        result = heuristic_classifier.classify_file(symlink)
        assert result == "documents"

    def test_classification_performance_with_many_categories(self, temp_dir):
        """Test classification performance with many categories."""
        # Create config with many categories
        categories = {}
        for i in range(100):
            categories[f"category_{i}"] = [f".ext{i}"]
        
        config = Config(base_path=temp_dir, categories=categories)
        classifier = HeuristicClassifier(config)
        
        # Test that classification still works
        file_path = temp_dir / "test.ext50"
        result = classifier.classify_file(file_path)
        assert result == "category_50"

    def test_extension_map_thread_safety(self, heuristic_classifier):
        """Test that extension map is not modified during classification."""
        original_map = heuristic_classifier.extension_map.copy()
        
        # Perform multiple classifications
        test_paths = [Path(f"test{i}.pdf") for i in range(10)]
        for path in test_paths:
            heuristic_classifier.classify_file(path)
        
        # Extension map should remain unchanged
        assert heuristic_classifier.extension_map == original_map

    def test_edge_case_empty_filename(self, heuristic_classifier, temp_dir):
        """Test classification with edge case filenames."""
        edge_cases = [
            temp_dir / ".hidden",
            temp_dir / ".",
            temp_dir / "..",
            temp_dir / "file.",
            temp_dir / ".file.pdf",
        ]
        
        for file_path in edge_cases:
            # Should not raise exceptions
            result = heuristic_classifier.classify_file(file_path)
            assert isinstance(result, str)
            assert result in ["documents", "images", "archives", "media", "code", "spreadsheets", "presentations", "packages", "misc"]
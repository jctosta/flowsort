#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "rich>=14.0.0",
#     "typer>=0.16.0",
#     "pydantic>=2.11.7"
# ]
# ///
"""
FlowSort - Digital Life Organization CLI Tool
A file classification and organization system with pluggable classification strategies.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Protocol
import mimetypes
import json

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from pydantic import BaseModel, Field, field_validator, ConfigDict

import traceback

app = typer.Typer(help="FlowSort - Keep your digital life organized")
console = Console()


# Configuration and Preferences Management
class Config(BaseModel):
    """Configuration for FlowSort file organization system."""

    base_path: Path = Field(default_factory=lambda: Path.home())
    inbox_path: Optional[Path] = Field(default=None)
    documents_path: Optional[Path] = Field(default=None)
    archive_path: Optional[Path] = Field(default=None)
    downloads_path: Path = Field(default_factory=lambda: Path.home() / "Downloads")
    system_path: Optional[Path] = Field(default=None)

    # Time rules (in days)
    inbox_to_documents_days: int = Field(default=7, ge=1, le=365)
    documents_to_archive_days: int = Field(default=30, ge=1, le=365)
    inbox_to_archive_days: int = Field(default=90, ge=1, le=365)

    # Categories
    categories: Optional[Dict[str, List[str]]] = Field(
        default={
            "documents": [".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf", ".md"],
            "images": [".jpg", ".jpeg", ".png", ".gif", ".svg", ".bmp", ".tiff"],
            "archives": [".zip", ".tar", ".gz", ".rar", ".7z", ".xz", ".bz2"],
            "media": [".mp4", ".avi", ".mkv", ".mov", ".mp3", ".wav", ".flac"],
            "packages": [".deb", ".rpm", ".appimage", ".snap", ".flatpak"],
            "code": [
                ".py",
                ".js",
                ".html",
                ".css",
                ".json",
                ".xml",
                ".yml",
                ".yaml",
            ],
            "spreadsheets": [".xls", ".xlsx", ".csv", ".ods"],
            "presentations": [".ppt", ".pptx", ".odp"],
        },
        description="A dictionary of categories and their corresponding file extensions.",
    )

    # Tagging system configuration
    enable_tagging: bool = Field(default=True, description="Enable xattr-based tagging system")
    tag_namespace: str = Field(default="user.flowsort", description="Xattr namespace for FlowSort tags")
    auto_tag_categories: bool = Field(default=True, description="Automatically tag files with their categories")
    preserve_existing_tags: bool = Field(default=True, description="Preserve existing tags when updating")
    xdg_tags_compatibility: bool = Field(default=True, description="Enable compatibility with XDG tags (user.xdg.tags)")
    prefer_xdg_tags: bool = Field(default=True, description="Prefer writing to XDG tags namespace when available")

    model_config = ConfigDict(arbitrary_types_allowed=True, json_encoders={Path: str})

    def model_post_init(self, __context):
        """Set derived paths after model initialization."""
        if self.inbox_path is None:
            self.inbox_path = self.base_path / "INBOX"
        if self.documents_path is None:
            self.documents_path = self.base_path / "DOCUMENTS"
        if self.archive_path is None:
            self.archive_path = self.base_path / "ARCHIVE"
        if self.system_path is None:
            self.system_path = self.base_path / "SYSTEM"

    @field_validator("base_path", "downloads_path", mode="before")
    @classmethod
    def validate_paths(cls, v):
        """Convert string paths to Path objects and expand user paths."""
        if isinstance(v, str):
            return Path(v).expanduser().resolve()
        elif isinstance(v, Path):
            return v.expanduser().resolve()
        return v

    @field_validator(
        "inbox_path", "documents_path", "archive_path", "system_path", mode="before"
    )
    @classmethod
    def validate_optional_paths(cls, v):
        """Convert string paths to Path objects for optional paths."""
        if v is None:
            return v
        if isinstance(v, str):
            return Path(v).expanduser().resolve()
        elif isinstance(v, Path):
            return v.expanduser().resolve()
        return v


# Extended Attributes (xattr) Tagging System
class XattrTagManager:
    """Manages file tags using extended attributes (xattrs)."""

    def __init__(self, config: Config):
        self.config = config
        self.tag_namespace = config.tag_namespace
        self.category_attr = f"{self.tag_namespace}.category"
        self.tags_attr = f"{self.tag_namespace}.tags"
        self.confidence_attr = f"{self.tag_namespace}.confidence"
        # XDG standard attributes
        self.xdg_tags_attr = "user.xdg.tags"
        self.enabled = config.enable_tagging and self._check_xattr_support()

    def _check_xattr_support(self) -> bool:
        """Check if the current filesystem supports extended attributes."""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile() as temp_file:
                test_attr = f"{self.tag_namespace}.test"
                os.setxattr(temp_file.name, test_attr.encode(), b"test")
                os.getxattr(temp_file.name, test_attr.encode())
                os.removexattr(temp_file.name, test_attr.encode())
                return True
        except (OSError, AttributeError):
            return False

    def is_enabled(self) -> bool:
        """Check if tagging is enabled and supported."""
        return self.enabled

    def _get_flowsort_tags(self, file_path: Path) -> Optional[List[str]]:
        """Get tags from FlowSort namespace only."""
        try:
            tags_bytes = os.getxattr(str(file_path), self.tags_attr.encode())
            tags_str = tags_bytes.decode()
            return [tag.strip() for tag in tags_str.split(",") if tag.strip()]
        except OSError:
            return None

    def _get_xdg_tags(self, file_path: Path) -> Optional[List[str]]:
        """Get tags from XDG namespace only."""
        if not self.config.xdg_tags_compatibility:
            return None
        try:
            tags_bytes = os.getxattr(str(file_path), self.xdg_tags_attr.encode())
            tags_str = tags_bytes.decode()
            return [tag.strip() for tag in tags_str.split(",") if tag.strip()]
        except OSError:
            return None

    def set_category(self, file_path: Path, category: str, confidence: float = None) -> bool:
        """Set the category tag for a file."""
        if not self.enabled:
            return False

        try:
            # Set FlowSort category and confidence
            os.setxattr(str(file_path), self.category_attr.encode(), category.encode())
            if confidence is not None:
                os.setxattr(str(file_path), self.confidence_attr.encode(), str(confidence).encode())
            
            # If XDG compatibility is enabled, also add category as an XDG tag
            if self.config.xdg_tags_compatibility and self.config.auto_tag_categories:
                try:
                    # Get existing XDG tags
                    existing_xdg_tags = self._get_xdg_tags(file_path) or []
                    
                    # Add category to XDG tags if not already present
                    if category not in existing_xdg_tags:
                        all_xdg_tags = existing_xdg_tags + [category]
                        xdg_tags_str = ",".join(sorted(all_xdg_tags))
                        os.setxattr(str(file_path), self.xdg_tags_attr.encode(), xdg_tags_str.encode())
                except OSError:
                    pass  # Don't fail if XDG write fails
            
            return True
        except OSError as e:
            print(f"Error setting category tag: {e}")
            print(traceback.format_exc())
            return False

    def get_category(self, file_path: Path) -> Optional[str]:
        """Get the category tag from a file."""
        if not self.enabled:
            return None

        try:
            category_bytes = os.getxattr(str(file_path), self.category_attr.encode())
            return category_bytes.decode()
        except OSError as e:
            # Errno 61 (ENODATA) means attribute doesn't exist - this is normal
            if e.errno != 61:  # Only log if it's not "attribute doesn't exist"
                print(f"Debug: Error getting category from {file_path}: {e}")
            return None

    def get_confidence(self, file_path: Path) -> Optional[float]:
        """Get the confidence score from a file."""
        if not self.enabled:
            return None

        try:
            confidence_bytes = os.getxattr(str(file_path), self.confidence_attr.encode())
            return float(confidence_bytes.decode())
        except OSError as e:
            # Errno 61 (ENODATA) means attribute doesn't exist - this is normal
            if e.errno != 61:
                print(f"Debug: Error getting confidence from {file_path}: {e}")
            return None
        except ValueError as e:
            print(f"Debug: Invalid confidence value in {file_path}: {e}")
            return None

    def add_tags(self, file_path: Path, tags: List[str]) -> bool:
        """Add custom tags to a file."""
        if not self.enabled:
            return False

        try:
            # Get existing tags from both namespaces
            existing_tags = self._get_flowsort_tags(file_path) or []
            existing_xdg_tags = self._get_xdg_tags(file_path) or []

            if self.config.preserve_existing_tags:
                # Merge with existing tags, avoiding duplicates
                all_tags = list(set(existing_tags + tags))
                all_xdg_tags = list(set(existing_xdg_tags + tags))
            else:
                all_tags = tags
                all_xdg_tags = tags

            success = True

            # Write to preferred namespace
            if self.config.xdg_tags_compatibility and self.config.prefer_xdg_tags:
                # Write to XDG namespace first
                try:
                    xdg_tags_str = ",".join(sorted(all_xdg_tags))
                    os.setxattr(str(file_path), self.xdg_tags_attr.encode(), xdg_tags_str.encode())
                except OSError:
                    success = False

                # Also write to FlowSort namespace as backup
                try:
                    flowsort_tags_str = ",".join(sorted(all_tags))
                    os.setxattr(str(file_path), self.tags_attr.encode(), flowsort_tags_str.encode())
                except OSError:
                    pass  # Don't fail if backup write fails
            else:
                # Write to FlowSort namespace only
                tags_str = ",".join(sorted(all_tags))
                os.setxattr(str(file_path), self.tags_attr.encode(), tags_str.encode())

            return success
        except OSError:
            return False

    def get_tags(self, file_path: Path) -> Optional[List[str]]:
        """Get custom tags from a file, merging both FlowSort and XDG tags."""
        if not self.enabled:
            return None

        all_tags = []

        # Get FlowSort tags
        try:
            tags_bytes = os.getxattr(str(file_path), self.tags_attr.encode())
            tags_str = tags_bytes.decode()
            flowsort_tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
            all_tags.extend(flowsort_tags)
        except OSError:
            pass

        # Get XDG tags if compatibility is enabled
        if self.config.xdg_tags_compatibility:
            try:
                xdg_tags_bytes = os.getxattr(str(file_path), self.xdg_tags_attr.encode())
                xdg_tags_str = xdg_tags_bytes.decode()
                xdg_tags = [tag.strip() for tag in xdg_tags_str.split(",") if tag.strip()]
                all_tags.extend(xdg_tags)
            except OSError:
                pass

        # Remove duplicates and return
        if all_tags:
            return list(dict.fromkeys(all_tags))  # Preserves order while removing duplicates
        return None

    def remove_tags(self, file_path: Path, tags: List[str]) -> bool:
        """Remove specific tags from a file in both namespaces."""
        if not self.enabled:
            return False

        success = True

        try:
            # Remove from FlowSort namespace
            existing_flowsort_tags = self._get_flowsort_tags(file_path) or []
            remaining_flowsort_tags = [tag for tag in existing_flowsort_tags if tag not in tags]

            if remaining_flowsort_tags:
                tags_str = ",".join(sorted(remaining_flowsort_tags))
                os.setxattr(str(file_path), self.tags_attr.encode(), tags_str.encode())
            else:
                # Remove the attribute entirely if no tags remain
                try:
                    os.removexattr(str(file_path), self.tags_attr.encode())
                except OSError:
                    pass

            # Remove from XDG namespace if compatibility is enabled
            if self.config.xdg_tags_compatibility:
                existing_xdg_tags = self._get_xdg_tags(file_path) or []
                remaining_xdg_tags = [tag for tag in existing_xdg_tags if tag not in tags]

                if remaining_xdg_tags:
                    xdg_tags_str = ",".join(sorted(remaining_xdg_tags))
                    try:
                        os.setxattr(str(file_path), self.xdg_tags_attr.encode(), xdg_tags_str.encode())
                    except OSError:
                        success = False
                else:
                    # Remove the attribute entirely if no tags remain
                    try:
                        os.removexattr(str(file_path), self.xdg_tags_attr.encode())
                    except OSError:
                        pass

            return success
        except OSError:
            return False

    def clear_all_tags(self, file_path: Path) -> bool:
        """Remove all FlowSort-related xattrs from a file, optionally including XDG tags."""
        if not self.enabled:
            return False

        success = True
        
        # Remove FlowSort attributes
        for attr in [self.category_attr, self.tags_attr, self.confidence_attr]:
            try:
                os.removexattr(str(file_path), attr.encode())
            except OSError:
                success = False
        
        # Remove XDG tags if compatibility is enabled
        if self.config.xdg_tags_compatibility:
            try:
                os.removexattr(str(file_path), self.xdg_tags_attr.encode())
            except OSError:
                pass  # Don't fail if XDG tags don't exist
        
        return success

    def get_all_metadata(self, file_path: Path) -> Dict[str, any]:
        """Get all FlowSort metadata from a file."""
        if not self.enabled:
            return {}

        metadata = {}

        category = self.get_category(file_path)
        if category:
            metadata["category"] = category

        confidence = self.get_confidence(file_path)
        if confidence is not None:
            metadata["confidence"] = confidence

        tags = self.get_tags(file_path)
        if tags:
            metadata["tags"] = tags

        return metadata

    def list_all_xattrs(self, file_path: Path) -> List[str]:
        """List all extended attributes on a file related to FlowSort and XDG tags."""
        if not self.enabled:
            return []

        try:
            attrs = os.listxattr(str(file_path))
            relevant_attrs = []
            
            # Include FlowSort namespace attributes
            for attr in attrs:
                if attr.startswith(self.tag_namespace):
                    relevant_attrs.append(attr)
            
            # Include XDG tags if compatibility is enabled
            if self.config.xdg_tags_compatibility and self.xdg_tags_attr in attrs:
                relevant_attrs.append(self.xdg_tags_attr)
            
            return relevant_attrs
        except OSError:
            return []

    def copy_tags(self, source_path: Path, dest_path: Path) -> bool:
        """Copy all FlowSort tags from source to destination file."""
        if not self.enabled:
            return False

        metadata = self.get_all_metadata(source_path)
        if not metadata:
            return True  # Nothing to copy

        success = True
        if "category" in metadata:
            success &= self.set_category(dest_path, metadata["category"], metadata.get("confidence"))

        if "tags" in metadata:
            success &= self.add_tags(dest_path, metadata["tags"])

        return success


class PreferencesManager:
    """Manages FlowSort preferences and configuration."""

    def __init__(self):
        self.config_dir = Path.home() / ".flowsort"
        self.config_file = self.config_dir / "config.json"
        self.ensure_config_dir()

    def ensure_config_dir(self):
        """Create .flowsort directory if it doesn't exist."""
        self.config_dir.mkdir(exist_ok=True)

        # Create .gitignore to avoid accidentally committing preferences
        gitignore_file = self.config_dir / ".gitignore"
        if not gitignore_file.exists():
            gitignore_file.write_text("*\n!.gitignore\n")

    def load_config(self) -> Config:
        """Load configuration from file or create default."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                return Config.model_validate(data)
            except (json.JSONDecodeError, ValueError) as e:
                console.print(f"⚠️  Error loading config: {e}")
                console.print("Using default configuration.")

        return Config()

    def save_config(self, config: Config):
        """Save configuration to file."""
        with open(self.config_file, "w") as f:
            f.write(config.model_dump_json(indent=2))
        console.print(f"✓ Configuration saved to {self.config_file}")

    def get_config_info(self) -> dict:
        """Get information about current configuration."""
        return {
            "config_dir": self.config_dir,
            "config_file": self.config_file,
            "config_exists": self.config_file.exists(),
        }


# Classification Strategy Protocol
class ClassificationStrategy(Protocol):
    """Protocol for file classification strategies."""

    def classify_file(self, file_path: Path) -> Optional[str]:
        """Classify a file and return the category name."""
        ...

    def get_confidence(self, file_path: Path, category: str) -> float:
        """Return confidence score (0-1) for the classification."""
        ...


# Heuristic Classification Implementation
class HeuristicClassifier:
    """Heuristic-based file classification using file extensions and MIME types."""

    def __init__(self, config: Config):
        self.config = config
        self.extension_map = {}
        # Build reverse mapping from extensions to categories
        for category, extensions in (
            config.categories.items() if config.categories else []
        ):
            for ext in extensions:
                self.extension_map[ext.lower()] = category

    def classify_file(self, file_path: Path) -> Optional[str]:
        """Classify file based on extension and MIME type."""
        # Primary classification by extension
        suffix = file_path.suffix.lower()
        if suffix in self.extension_map:
            return self.extension_map[suffix]

        # Fallback to MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            if mime_type.startswith("text/"):
                return "documents"
            elif mime_type.startswith("image/"):
                return "images"
            elif mime_type.startswith("video/") or mime_type.startswith("audio/"):
                return "media"
            elif mime_type.startswith("application/"):
                if "pdf" in mime_type:
                    return "documents"
                elif any(x in mime_type for x in ["zip", "tar", "compressed"]):
                    return "archives"

        return "misc"

    def get_confidence(self, file_path: Path, category: str) -> float:
        """Return confidence score for heuristic classification."""
        suffix = file_path.suffix.lower()
        if suffix in self.extension_map and self.extension_map[suffix] == category:
            return 0.9  # High confidence for direct extension match
        return 0.6  # Medium confidence for MIME type fallback


# Future LLM Classification Hook
class LLMClassifier:
    """Placeholder for future LLM-based classification with tag integration."""

    def __init__(self, config: Config):
        self.config = config
        self.enabled = False  # Set to True when LLM integration is ready

    def classify_file(self, file_path: Path, tag_manager: Optional['XattrTagManager'] = None) -> Optional[str]:
        """Classify file using LLM with existing tag information."""
        if not self.enabled:
            return None

        # TODO: Implement LLM classification
        # - Read file content/metadata
        # - Include existing tags in classification context
        # - Send to LLM with classification prompt including tag context
        # - Parse response and return category

        # Example context building for future LLM integration:
        context = self._build_classification_context(file_path, tag_manager)

        # Placeholder for actual LLM call
        # response = llm_client.classify(file_path, context)
        # return self._parse_llm_response(response)

        pass

    def _build_classification_context(self, file_path: Path, tag_manager: Optional['XattrTagManager']) -> Dict[str, any]:
        """Build context for LLM classification including existing tags."""
        context = {
            "filename": file_path.name,
            "file_size": file_path.stat().st_size if file_path.exists() else 0,
            "file_extension": file_path.suffix.lower(),
        }

        # Include existing tag information if available
        if tag_manager and tag_manager.is_enabled():
            existing_metadata = tag_manager.get_all_metadata(file_path)
            if existing_metadata:
                context["existing_tags"] = existing_metadata.get("tags", [])
                context["existing_category"] = existing_metadata.get("category")
                context["existing_confidence"] = existing_metadata.get("confidence")

        return context

    def get_confidence(self, file_path: Path, category: str) -> float:
        """Return confidence score for LLM classification."""
        return 0.8 if self.enabled else 0.0


# File Organization System
class FlowSort:
    """Main FlowSort file organization system."""

    def __init__(self, config: Config):
        self.config = config
        self.heuristic_classifier = HeuristicClassifier(config)
        self.llm_classifier = LLMClassifier(config)
        self.tag_manager = XattrTagManager(config)
        self.setup_directories()

    def setup_directories(self):
        """Create necessary directory structure."""
        if (
            not self.config
            or not self.config.inbox_path
            or not self.config.documents_path
            or not self.config.archive_path
            or not self.config.system_path
        ):
            raise ValueError("Config is not initialized")

        directories = [
            self.config.inbox_path / "all",
            self.config.documents_path / "all",
            self.config.archive_path / "all",
            self.config.archive_path / "by-date",
            self.config.archive_path / "by-type",
            self.config.system_path,
        ]

        # Create category directories
        for base_path in [self.config.inbox_path, self.config.documents_path]:
            for category in (
                self.config.categories.keys() if self.config.categories else []
            ):
                directories.append(base_path / category)

            # Always create a "misc" directory for unclassified files
            directories.append(base_path / "misc")

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def classify_file(self, file_path: Path) -> tuple[str, float]:
        """Classify a file using available strategies."""
        # Try LLM first if available
        if self.llm_classifier.enabled:
            category = self.llm_classifier.classify_file(file_path, self.tag_manager)
            if category:
                confidence = self.llm_classifier.get_confidence(file_path, category)
                return category, confidence

        # Fallback to heuristic classification
        category = self.heuristic_classifier.classify_file(file_path) or "misc"
        confidence = self.heuristic_classifier.get_confidence(file_path, category)
        return category, confidence

    def move_file_to_all(self, source_path: Path, target_all_path: Path) -> Path:
        """Move file to target 'all' folder, handling name conflicts."""
        target_file = target_all_path / source_path.name

        # Handle name conflicts
        counter = 1
        while target_file.exists():
            stem = source_path.stem
            suffix = source_path.suffix
            target_file = target_all_path / f"{stem}_{counter}{suffix}"
            counter += 1

        shutil.move(str(source_path), str(target_file))
        return target_file

    def create_category_symlink(self, real_file: Path, category_dir: Path):
        """Create symlink in category directory pointing to real file."""
        symlink_path = category_dir / real_file.name

        # Remove existing symlink if it exists
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()

        # Create relative symlink
        relative_path = os.path.relpath(real_file, category_dir)
        symlink_path.symlink_to(relative_path)

    def collect_downloads(self) -> int:
        """Collect files from Downloads folder to INBOX."""

        if not self.config.inbox_path:
            console.print("Error: INBOX path not configured.")
            raise ValueError("INBOX path not configured.")

        collected = 0

        if not self.config.downloads_path.exists():
            return collected

        for file_path in self.config.downloads_path.iterdir():
            if file_path.is_file():
                # Move to INBOX/all
                target_file = self.move_file_to_all(
                    file_path, self.config.inbox_path / "all"
                )

                # Classify and create symlink
                category, confidence = self.classify_file(target_file)
                category_dir = self.config.inbox_path / category
                self.create_category_symlink(target_file, category_dir)

                # Apply tags if enabled
                if self.tag_manager.is_enabled() and self.config.auto_tag_categories:
                    self.tag_manager.set_category(target_file, category, confidence)

                collected += 1
                console.print(
                    f"✓ Collected {file_path.name} → {category} (confidence: {confidence:.2f})"
                )

        return collected

    def cleanup_broken_symlinks(self, directory: Path):
        """Remove broken symlinks from a directory."""
        for item in directory.rglob("*"):
            if item.is_symlink() and not item.exists():
                item.unlink()
                console.print(f"✓ Removed broken symlink: {item}")

    def get_file_stats(self, directory: Path) -> Dict[str, int]:
        """Get statistics about files in directory structure."""
        stats = {"total_files": 0, "categories": {}}

        all_dir = directory / "all"
        if all_dir.exists():
            stats["total_files"] = len(list(all_dir.iterdir()))

        for category in self.config.categories.keys() if self.config.categories else []:
            category_dir = directory / category
            if category_dir.exists():
                stats["categories"][category] = len(list(category_dir.iterdir()))

        return stats


# CLI Commands
@app.command()
def init(
    base_path: Optional[str] = typer.Option(
        None, "--base-path", "-b", help="Base path for organization system"
    ),
    downloads_path: Optional[str] = typer.Option(
        None, "--downloads", "-d", help="Downloads folder path"
    ),
    save_prefs: bool = typer.Option(
        True, "--save/--no-save", help="Save preferences to config file"
    ),
):
    """Initialize FlowSort file organization system."""
    prefs = PreferencesManager()

    try:
        config = prefs.load_config()

        # Update config with provided options
        update_data = {}
        if base_path:
            update_data["base_path"] = base_path
        if downloads_path:
            update_data["downloads_path"] = downloads_path

        if update_data:
            # Create new config with updated data
            config_dict = config.model_dump()
            config_dict.update(update_data)
            config = Config.model_validate(config_dict)

        # Initialize the system
        FlowSort(config)

        # Save preferences if requested
        if save_prefs:
            prefs.save_config(config)

        console.print("🌊 FlowSort initialized successfully!")
        console.print(f"📁 Base path: {config.base_path}")
        console.print(f"📥 Downloads: {config.downloads_path}")
        console.print(f"⚙️  Config: {prefs.config_file}")

    except ValueError as e:
        console.print(f"❌ Configuration error: {e}")
        raise typer.Exit(1)


@app.command(name="config")
def config_cmd(
    show: bool = typer.Option(False, "--show", "-s", help="Show current configuration"),
    edit_base_path: Optional[str] = typer.Option(
        None, "--base-path", help="Set base path"
    ),
    edit_downloads: Optional[str] = typer.Option(
        None, "--downloads", help="Set downloads path"
    ),
    edit_inbox_days: Optional[int] = typer.Option(
        None, "--inbox-days", help="Days before moving from INBOX to DOCUMENTS"
    ),
    edit_docs_days: Optional[int] = typer.Option(
        None, "--docs-days", help="Days before moving from DOCUMENTS to ARCHIVE"
    ),
    edit_archive_days: Optional[int] = typer.Option(
        None, "--archive-days", help="Days before moving from INBOX to ARCHIVE"
    ),
    edit_enable_tagging: Optional[bool] = typer.Option(
        None, "--enable-tagging/--disable-tagging", help="Enable/disable xattr-based tagging"
    ),
    edit_auto_tag: Optional[bool] = typer.Option(
        None, "--auto-tag/--no-auto-tag", help="Enable/disable automatic category tagging"
    ),
    edit_xdg_compat: Optional[bool] = typer.Option(
        None, "--xdg-compat/--no-xdg-compat", help="Enable/disable XDG tags compatibility"
    ),
    edit_prefer_xdg: Optional[bool] = typer.Option(
        None, "--prefer-xdg/--prefer-flowsort", help="Prefer XDG tags namespace over FlowSort"
    ),
    edit_preserve_tags: Optional[bool] = typer.Option(
        None, "--preserve-tags/--replace-tags", help="Preserve existing tags when adding new ones"
    ),
):
    """Manage FlowSort configuration."""
    prefs = PreferencesManager()

    if show:
        try:
            config = prefs.load_config()
            info = prefs.get_config_info()

            table = Table(title="FlowSort Configuration")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Config Directory", str(info["config_dir"]))
            table.add_row("Config File", str(info["config_file"]))
            table.add_row("Config Exists", "✓" if info["config_exists"] else "✗")
            table.add_row("Base Path", str(config.base_path))
            table.add_row("Downloads Path", str(config.downloads_path))
            table.add_row("INBOX", str(config.inbox_path))
            table.add_row("DOCUMENTS", str(config.documents_path))
            table.add_row("ARCHIVE", str(config.archive_path))
            table.add_row("", "")  # Separator
            table.add_row("INBOX → DOCUMENTS", f"{config.inbox_to_documents_days} days")
            table.add_row(
                "DOCUMENTS → ARCHIVE", f"{config.documents_to_archive_days} days"
            )
            table.add_row("INBOX → ARCHIVE", f"{config.inbox_to_archive_days} days")
            table.add_row("", "")  # Separator
            table.add_row("Enable Tagging", "✓" if config.enable_tagging else "✗")
            table.add_row("Auto Tag Categories", "✓" if config.auto_tag_categories else "✗")
            table.add_row("XDG Compatibility", "✓" if config.xdg_tags_compatibility else "✗")
            table.add_row("Prefer XDG Tags", "✓" if config.prefer_xdg_tags else "✗")
            table.add_row("Preserve Existing Tags", "✓" if config.preserve_existing_tags else "✗")
            table.add_row("Tag Namespace", config.tag_namespace)

            console.print(table)
        except ValueError as e:
            console.print(f"❌ Configuration error: {e}")
            raise typer.Exit(1)
        return

    # Edit configuration
    try:
        config = prefs.load_config()
        config_dict = config.model_dump()
        changed = False

        if edit_base_path:
            config_dict["base_path"] = edit_base_path
            changed = True
            console.print(f"✓ Base path updated to: {edit_base_path}")

        if edit_downloads:
            config_dict["downloads_path"] = edit_downloads
            changed = True
            console.print(f"✓ Downloads path updated to: {edit_downloads}")

        if edit_inbox_days is not None:
            config_dict["inbox_to_documents_days"] = edit_inbox_days
            changed = True
            console.print(f"✓ INBOX to DOCUMENTS days updated to: {edit_inbox_days}")

        if edit_docs_days is not None:
            config_dict["documents_to_archive_days"] = edit_docs_days
            changed = True
            console.print(f"✓ DOCUMENTS to ARCHIVE days updated to: {edit_docs_days}")

        if edit_archive_days is not None:
            config_dict["inbox_to_archive_days"] = edit_archive_days
            changed = True
            console.print(f"✓ INBOX to ARCHIVE days updated to: {edit_archive_days}")

        if edit_enable_tagging is not None:
            config_dict["enable_tagging"] = edit_enable_tagging
            changed = True
            status = "enabled" if edit_enable_tagging else "disabled"
            console.print(f"✓ Tagging system {status}")

        if edit_auto_tag is not None:
            config_dict["auto_tag_categories"] = edit_auto_tag
            changed = True
            status = "enabled" if edit_auto_tag else "disabled"
            console.print(f"✓ Automatic category tagging {status}")

        if edit_xdg_compat is not None:
            config_dict["xdg_tags_compatibility"] = edit_xdg_compat
            changed = True
            status = "enabled" if edit_xdg_compat else "disabled"
            console.print(f"✓ XDG tags compatibility {status}")

        if edit_prefer_xdg is not None:
            config_dict["prefer_xdg_tags"] = edit_prefer_xdg
            changed = True
            namespace = "XDG" if edit_prefer_xdg else "FlowSort"
            console.print(f"✓ Preferred tags namespace set to: {namespace}")

        if edit_preserve_tags is not None:
            config_dict["preserve_existing_tags"] = edit_preserve_tags
            changed = True
            behavior = "preserve" if edit_preserve_tags else "replace"
            console.print(f"✓ Tag behavior set to: {behavior} existing tags")

        if changed:
            # Validate the new configuration
            config = Config.model_validate(config_dict)
            prefs.save_config(config)

    except ValueError as e:
        console.print(f"❌ Configuration error: {e}")
        console.print("Configuration not saved due to validation errors.")
        raise typer.Exit(1)


@app.command()
def collect(
    auto_confirm: bool = typer.Option(
        False, "--yes", "-y", help="Auto-confirm actions"
    ),
):
    """Collect files from Downloads folder."""
    prefs = PreferencesManager()
    config = prefs.load_config()
    flowsort = FlowSort(config)

    if not auto_confirm:
        if not Confirm.ask("Collect files from Downloads folder?"):
            raise typer.Abort()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(description="Collecting files...", total=None)
        collected = flowsort.collect_downloads()
        progress.update(task, completed=True)

    console.print(f"✓ Collected {collected} files")


@app.command()
def status():
    """Show current FlowSort system status."""
    prefs = PreferencesManager()
    config = prefs.load_config()
    flowsort = FlowSort(config)

    table = Table(title="FlowSort Status")
    table.add_column("Location", style="cyan")
    table.add_column("Total Files", style="magenta")
    table.add_column("Categories", style="green")

    for name, path in [
        ("INBOX", config.inbox_path),
        ("DOCUMENTS", config.documents_path),
        ("ARCHIVE", config.archive_path),
    ]:
        if not path:
            print(f"Skipping status check for non-existent path: {path}")
            continue
        stats = flowsort.get_file_stats(path)
        categories_str = ", ".join(
            [f"{k}: {v}" for k, v in stats["categories"].items() if v > 0]
        )
        table.add_row(name, str(stats["total_files"]), categories_str)

    console.print(table)


@app.command()
def cleanup():
    """Clean up broken symlinks."""
    prefs = PreferencesManager()
    config = prefs.load_config()
    flowsort = FlowSort(config)

    console.print("🧹 Cleaning up broken symlinks...")
    for path in [config.inbox_path, config.documents_path]:
        flowsort.cleanup_broken_symlinks(path) if path else print(
            f"Skipping cleanup for non-existent path: {path}"
        )

    console.print("✓ Cleanup completed")


@app.command()
def classify(
    file_path: str = typer.Argument(..., help="Path to file to classify"),
    show_confidence: bool = typer.Option(True, help="Show confidence score"),
):
    """Classify a single file."""
    prefs = PreferencesManager()
    config = prefs.load_config()
    flowsort = FlowSort(config)

    path = Path(file_path)
    if not path.exists():
        console.print(f"❌ File not found: {file_path}")
        raise typer.Exit(1)

    category, confidence = flowsort.classify_file(path)

    if show_confidence:
        console.print(f"📁 {path.name} → {category} (confidence: {confidence:.2f})")
    else:
        console.print(f"📁 {path.name} → {category}")


@app.command()
def tags(
    file_path: str = typer.Argument(..., help="Path to file to manage tags for"),
    list_tags: bool = typer.Option(False, "--list", "-l", help="List all tags on file"),
    add: Optional[str] = typer.Option(None, "--add", "-a", help="Add tags (comma-separated)"),
    remove: Optional[str] = typer.Option(None, "--remove", "-r", help="Remove tags (comma-separated)"),
    clear: bool = typer.Option(False, "--clear", "-c", help="Clear all FlowSort tags"),
    show_metadata: bool = typer.Option(False, "--metadata", "-m", help="Show all FlowSort metadata"),
):
    """Manage file tags using extended attributes."""
    prefs = PreferencesManager()
    config = prefs.load_config()
    flowsort = FlowSort(config)

    path = Path(file_path)
    if not path.exists():
        console.print(f"❌ File not found: {file_path}")
        raise typer.Exit(1)

    if not flowsort.tag_manager.is_enabled():
        console.print("❌ Tagging is disabled or not supported on this filesystem")
        raise typer.Exit(1)

    # Clear all tags
    if clear:
        if flowsort.tag_manager.clear_all_tags(path):
            console.print(f"✓ Cleared all FlowSort tags from {path.name}")
        else:
            console.print(f"❌ Failed to clear tags from {path.name}")
        return

    # Add tags
    if add:
        tags_to_add = [tag.strip() for tag in add.split(",") if tag.strip()]
        if flowsort.tag_manager.add_tags(path, tags_to_add):
            console.print(f"✓ Added tags to {path.name}: {', '.join(tags_to_add)}")
        else:
            console.print(f"❌ Failed to add tags to {path.name}")

    # Remove tags
    if remove:
        tags_to_remove = [tag.strip() for tag in remove.split(",") if tag.strip()]
        if flowsort.tag_manager.remove_tags(path, tags_to_remove):
            console.print(f"✓ Removed tags from {path.name}: {', '.join(tags_to_remove)}")
        else:
            console.print(f"❌ Failed to remove tags from {path.name}")

    # Show metadata or list tags
    if show_metadata:
        metadata = flowsort.tag_manager.get_all_metadata(path)
        if metadata:
            table = Table(title=f"FlowSort Metadata: {path.name}")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")

            for key, value in metadata.items():
                if isinstance(value, list):
                    value = ", ".join(value)
                table.add_row(key.title(), str(value))

            console.print(table)
        else:
            console.print(f"No FlowSort metadata found for {path.name}")
    elif list_tags or not (add or remove or clear):
        # Default action: list tags
        tags = flowsort.tag_manager.get_tags(path)
        category = flowsort.tag_manager.get_category(path)
        confidence = flowsort.tag_manager.get_confidence(path)

        if tags or category:
            console.print(f"📁 File: {path.name}")
            if category:
                conf_str = f" (confidence: {confidence:.2f})" if confidence is not None else ""
                console.print(f"   Category: {category}{conf_str}")
            if tags:
                console.print(f"   Tags: {', '.join(tags)}")
        else:
            console.print(f"No tags found for {path.name}")


@app.command()
def retag(
    path: Path = typer.Option(None, "--path", "-p", help="Path to retag (file or directory)"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Process directories recursively"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing tags"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without making changes"),
):
    """Re-apply automatic tags to files based on current classification."""
    prefs = PreferencesManager()
    config = prefs.load_config()
    flowsort = FlowSort(config)

    if not path:
        target_path = Path(config.inbox_path, "all")
    elif path and path.exists():
        target_path = Path(path)
    elif path:
        console.print(f"❌ Path not found: {path}")
        raise typer.Exit(1)
    else:
        console.print(f"❌ Path not found: {path}")
        raise typer.Exit(1)

    console.print(f"Processing files in {target_path}")

    if not flowsort.tag_manager.is_enabled():
        console.print("❌ Tagging is disabled or not supported on this filesystem")
        raise typer.Exit(1)

    # Collect files to process
    files_to_process = []
    if target_path.is_file():
        files_to_process.append(target_path)
    elif target_path.is_dir():
        if recursive:
            files_to_process.extend([f for f in target_path.rglob("*") if f.is_file()])
        else:
            files_to_process.extend([f for f in target_path.iterdir() if f.is_file()])

    if not files_to_process:
        console.print("No files found to process")
        return

    processed = 0
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(description="Re-tagging files...", total=len(files_to_process))

        for file_path in files_to_process:
            # Check if file already has tags and force is not enabled
            existing_category = flowsort.tag_manager.get_category(file_path)
            if existing_category and not force:
                skipped += 1
                progress.advance(task)
                continue

            # Classify the file
            category, confidence = flowsort.classify_file(file_path)

            if dry_run:
                console.print(f"Would tag {file_path.name} → {category} (confidence: {confidence:.2f})")
            else:
                # Apply the tag
                if flowsort.tag_manager.set_category(file_path, category, confidence):
                    processed += 1
                else:
                    console.print(f"❌ Failed to tag {file_path.name}")

            progress.advance(task)

    if dry_run:
        console.print(f"Dry run completed. Would process {len(files_to_process) - skipped} files")
    else:
        console.print(f"✓ Re-tagged {processed} files, skipped {skipped} files")


@app.command()
def recent(
    location: str = typer.Option("inbox", "--location", "-l", help="Location to check (inbox, documents, archive)"),
    count: int = typer.Option(5, "--count", "-n", help="Number of recent files to show"),
    show_tags: bool = typer.Option(True, "--tags/--no-tags", help="Show file tags"),
):
    """Show recently added files and their tags."""
    prefs = PreferencesManager()
    config = prefs.load_config()
    flowsort = FlowSort(config)

    # Map location to actual path
    location_map = {
        "inbox": config.inbox_path,
        "documents": config.documents_path,
        "archive": config.archive_path,
    }

    if location not in location_map:
        console.print(f"❌ Invalid location: {location}. Use: inbox, documents, archive")
        raise typer.Exit(1)

    target_path = location_map[location]
    all_dir = target_path / "all"

    if not all_dir.exists():
        console.print(f"❌ Directory not found: {all_dir}")
        raise typer.Exit(1)

    # Get files sorted by modification time (most recent first)
    try:
        files = [f for f in all_dir.iterdir() if f.is_file()]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        recent_files = files[:count]
    except PermissionError:
        console.print(f"❌ Permission denied accessing {all_dir}")
        raise typer.Exit(1)

    if not recent_files:
        console.print(f"No files found in {location}")
        return

    # Display results
    table = Table(title=f"Recent Files in {location.upper()}")
    table.add_column("File", style="cyan")
    table.add_column("Modified", style="yellow")

    if show_tags and flowsort.tag_manager.is_enabled():
        table.add_column("Category", style="green")
        table.add_column("Confidence", style="magenta")
        table.add_column("Tags", style="blue")

    import datetime

    for file_path in recent_files:
        # Format modification time
        mtime = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
        time_str = mtime.strftime("%Y-%m-%d %H:%M")

        row = [file_path.name, time_str]

        if show_tags and flowsort.tag_manager.is_enabled():
            # Get tag information
            category = flowsort.tag_manager.get_category(file_path) or "none"
            confidence = flowsort.tag_manager.get_confidence(file_path)
            tags = flowsort.tag_manager.get_tags(file_path) or []

            confidence_str = f"{confidence:.2f}" if confidence is not None else "none"
            tags_str = ", ".join(tags) if tags else "none"

            row.extend([category, confidence_str, tags_str])

        table.add_row(*row)

    console.print(table)

    # Show summary
    if show_tags and flowsort.tag_manager.is_enabled():
        console.print(f"\n📊 Showing {len(recent_files)} of {len(files)} files in {location}")
    else:
        console.print(f"\n📊 Showing {len(recent_files)} of {len(files)} files in {location}")
        if flowsort.tag_manager.is_enabled():
            console.print("💡 Use --tags to see file metadata")
        else:
            console.print("ℹ️  Tagging is disabled")


@app.command()
def version():
    """Show FlowSort version information."""
    console.print("🌊 FlowSort v1.0.0")
    console.print("Digital Life Organization Tool")
    console.print("Built with ❤️  for keeping your files tidy")


if __name__ == "__main__":
    app()

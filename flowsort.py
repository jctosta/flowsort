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

app = typer.Typer(help="FlowSort - Keep your digital life organized")
console = Console()


# Configuration and Preferences Management
class Config(BaseModel):
    """Configuration for FlowSort file organization system."""

    base_path: Path = Field(default_factory=lambda: Path.home())
    inbox_path: Optional[Path] = Field(
        default_factory=lambda data: Path(data["base_path"], Path("INBOX"))
    )
    documents_path: Optional[Path] = Field(
        default_factory=lambda data: Path(data["base_path"], Path("DOCUMENTS"))
    )
    archive_path: Optional[Path] = Field(
        default_factory=lambda data: Path(data["base_path"], Path("ARCHIVE"))
    )
    downloads_path: Path = Field(default_factory=lambda: Path.home() / "Downloads")
    system_path: Optional[Path] = Field(
        default_factory=lambda data: Path(data["base_path"], Path("SYSTEM"))
    )

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

    model_config = ConfigDict(arbitrary_types_allowed=True, json_encoders={Path: str})

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
    """Placeholder for future LLM-based classification."""

    def __init__(self, config: Config):
        self.config = config
        self.enabled = False  # Set to True when LLM integration is ready

    def classify_file(self, file_path: Path) -> Optional[str]:
        """Classify file using LLM (placeholder)."""
        if not self.enabled:
            return None

        # TODO: Implement LLM classification
        # - Read file content/metadata
        # - Send to LLM with classification prompt
        # - Parse response and return category
        pass

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

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def classify_file(self, file_path: Path) -> tuple[str, float]:
        """Classify a file using available strategies."""
        # Try LLM first if available
        if self.llm_classifier.enabled:
            category = self.llm_classifier.classify_file(file_path)
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


@app.command()
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
def version():
    """Show FlowSort version information."""
    console.print("🌊 FlowSort v1.0.0")
    console.print("Digital Life Organization Tool")
    console.print("Built with ❤️  for keeping your files tidy")


if __name__ == "__main__":
    app()

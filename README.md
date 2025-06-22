# FlowSort

**CLI-based file classification and organization**

*Automatically categorizes and organizes files using a flow-based methodology*

---

## Quick Start

### Installation

**Requirements**: Only `uv` needs to be installed on your system.

```bash
mkdir -p ~/.local/bin && curl -sSL https://raw.githubusercontent.com/jctosta/flowsort/main/flowsort.py -o ~/.local/bin/flowsort && chmod +x ~/.local/bin/flowsort
```

### Get Started

```bash
# Initialize FlowSort
flowsort init

# Collect files from Downloads
flowsort collect

# Check status
flowsort status
```

**How it works**: The script uses `uv`'s inline script capabilities - no manual dependency installation needed! `uv` automatically handles everything in an isolated environment.

**Need help?** Most Linux distributions include `~/.local/bin` in PATH by default. If `flowsort` isn't found, add `export PATH="$HOME/.local/bin:$PATH"` to your shell profile.

---

## Table of Contents

1. [Overview](#overview)
2. [Core Philosophy](#core-philosophy)
3. [File Flow Methodology](#file-flow-methodology)
4. [Directory Structure](#directory-structure)
5. [Classification System](#classification-system)
6. [Usage Guide](#usage-guide)
7. [Configuration](#configuration)
8. [Time-Based Rules](#time-based-rules)
9. [Architecture](#architecture)
10. [Advanced Features](#advanced-features)
11. [Best Practices](#best-practices)

---

## Overview

FlowSort is a digital life organization system that automatically manages file classification and organization using a flow-based methodology. It's designed to keep your digital workspace clean and organized with minimal manual intervention.

### Key Principles

- **Zero Data Loss**: Files are never deleted, only moved and archived
- **Automated Classification**: Intelligent file categorization with minimal user input
- **Flow-Based Organization**: Files flow through stages (Downloads → INBOX → DOCUMENTS → ARCHIVE)
- **Symlink-Based Categories**: Single source of truth with categorized views via symlinks
- **Time-Based Management**: Automatic archival based on file age and access patterns

---

## Core Philosophy

### The Flow Concept

FlowSort treats file organization like water flowing through a river system:

```
Downloads (Collection Point)
    ↓
INBOX (Classification & Temporary Storage)
    ↓
DOCUMENTS (Active Work Area)
    ↓
ARCHIVE (Long-term Storage)
```

### Design Principles

1. **Single Source of Truth**: Each file exists exactly once in an `/all/` folder
2. **Multiple Views**: Symlinks provide categorized views without file duplication
3. **Gradual Organization**: Files naturally flow from chaotic to organized states
4. **Minimal Friction**: System works automatically with optional manual intervention
5. **Reversible Actions**: All operations can be undone or corrected

---

## File Flow Methodology

### Stage 1: Collection

**Source**: Downloads folder (or any scattered files)
**Destination**: `INBOX/all/`
**Process**:
- Files are moved from Downloads to INBOX/all
- Automatic classification creates symlinks in category folders
- No manual sorting required

### Stage 2: Classification

**Location**: `INBOX/`
**Process**:
- Heuristic classification based on file extensions and MIME types
- Future LLM integration for content-based classification
- Manual reclassification available for edge cases

### Stage 3: Active Use

**Transition**: `INBOX/all/` → `DOCUMENTS/all/`
**Trigger**: Files accessed within classification period (default: 7 days)
**Purpose**: Active working files remain easily accessible

### Stage 4: Archival

**Transition**: `DOCUMENTS/all/` → `ARCHIVE/all/`
**Triggers**:
- Files not accessed for extended period (default: 30 days)
- Files remaining in INBOX too long (default: 90 days)
**Purpose**: Long-term storage with organized retrieval

---

## Directory Structure

### Main Directories

```
~/
├── INBOX/           # Temporary classification area
├── DOCUMENTS/       # Active working files
├── ARCHIVE/         # Long-term storage
└── SYSTEM/          # FlowSort scripts and configs
```

### Internal Structure

Each main directory follows the same pattern:

```
INBOX/
├── all/                    # Real files live here
│   ├── document1.pdf
│   ├── image1.jpg
│   └── video1.mp4
├── documents/              # Symlinks to classified files
│   └── document1.pdf -> ../all/document1.pdf
├── images/
│   └── image1.jpg -> ../all/image1.jpg
├── media/
│   └── video1.mp4 -> ../all/video1.mp4
├── archives/
├── packages/
├── code/
├── spreadsheets/
├── presentations/
└── misc/                   # Unclassified items
```

### Archive Organization

```
ARCHIVE/
├── all/                    # All archived files
├── by-date/               # Organized by archival date
│   ├── 2025/
│   │   ├── january/
│   │   ├── february/
│   │   └── ...
│   └── 2024/
├── by-type/               # Organized by file type
│   ├── documents/
│   ├── images/
│   └── media/
└── from-downloads/        # Bulk moves from Downloads
```

---

## Classification System

### Heuristic Classification

Primary classification method using:

#### File Extensions
```
documents:     .pdf, .doc, .docx, .txt, .odt, .rtf, .md
images:        .jpg, .jpeg, .png, .gif, .svg, .bmp, .tiff
archives:      .zip, .tar, .gz, .rar, .7z, .xz, .bz2
media:         .mp4, .avi, .mkv, .mov, .mp3, .wav, .flac
packages:      .deb, .rpm, .appimage, .snap, .flatpak
code:          .py, .js, .html, .css, .json, .xml, .yml, .yaml
spreadsheets:  .xls, .xlsx, .csv, .ods
presentations: .ppt, .pptx, .odp
```

#### MIME Type Fallback
- `text/*` → documents
- `image/*` → images
- `video/*` or `audio/*` → media
- `application/pdf` → documents
- Archives by content type → archives

#### Confidence Scoring
- **0.9**: Direct extension match
- **0.6**: MIME type fallback
- **0.8**: Future LLM classification

### Future LLM Integration

Planned enhancement for content-based classification:
- Document content analysis
- Image recognition
- Contextual understanding
- Learning from user corrections

---

## Time-Based Rules

### Default Timeframes

| Transition | Default | Range | Description |
|------------|---------|-------|-------------|
| INBOX → DOCUMENTS | 7 days | 1-365 | Files accessed recently |
| DOCUMENTS → ARCHIVE | 30 days | 1-365 | Files not accessed |
| INBOX → ARCHIVE | 90 days | 1-365 | Unprocessed files |

### Access Pattern Detection

- **atime** (access time): Determines active files
- **mtime** (modification time): Secondary consideration
- **Age since collection**: Prevents indefinite accumulation

### Validation Rules

- `documents_to_archive_days` > `inbox_to_documents_days`
- `inbox_to_archive_days` > max(`inbox_to_documents_days`, `documents_to_archive_days`)

---

## Architecture

### Component Design

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  CLI Interface  │────│  FlowSort Core   │────│  Classification │
│   (Typer)       │    │                  │    │   Strategies    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                       ┌────────┴────────┐
                       │  Configuration  │
                       │   Management    │
                       │   (Pydantic)    │
                       └─────────────────┘
```

### Key Classes

#### `Config` (Pydantic Model)
- Manages all configuration settings
- Automatic path validation and derivation
- Time rule validation
- JSON serialization/deserialization

#### `FlowSort` (Core System)
- Directory setup and management
- File movement and symlink creation
- Statistics and reporting

#### `HeuristicClassifier`
- Extension-based classification
- MIME type fallback
- Confidence scoring

#### `LLMClassifier` (Future)
- Content-based classification
- Learning capabilities
- Higher accuracy for ambiguous files

#### `PreferencesManager`
- Configuration persistence
- User preference handling
- Migration support

---

## Usage Guide

### Basic Commands

```bash
# Collect files from Downloads
flowsort collect

# Auto-confirm collection
flowsort collect --yes

# Check system status
flowsort status

# View configuration
flowsort config --show

# Clean up broken symlinks
flowsort cleanup

# Classify a single file
flowsort classify path/to/file.pdf

# Show version
flowsort version
```

### Configuration Management

```bash
# Update base path
flowsort config --base-path ~/NewPath

# Update Downloads location
flowsort config --downloads ~/Downloads

# Adjust time rules
flowsort config --inbox-days 5
flowsort config --docs-days 45
flowsort config --archive-days 120
```

### Daily Workflow

1. **Morning**: `flowsort collect` to organize overnight downloads
2. **Work**: Files naturally flow to DOCUMENTS as you access them
3. **Weekly**: Review INBOX categories for manual adjustments
4. **Monthly**: Check ARCHIVE for any misplaced important files

---

## Configuration

### JSON Structure

```json
{
  "base_path": "/home/user",
  "inbox_path": "/home/user/INBOX",
  "documents_path": "/home/user/DOCUMENTS",
  "archive_path": "/home/user/ARCHIVE",
  "downloads_path": "/home/user/Downloads",
  "system_path": "/home/user/SYSTEM",
  "inbox_to_documents_days": 7,
  "documents_to_archive_days": 30,
  "inbox_to_archive_days": 90,
  "categories": {
    "documents": [".pdf", ".doc", ".docx", ...],
    "images": [".jpg", ".png", ".gif", ...],
    ...
  }
}
```

### Customization Options

#### Custom Categories
Add or modify file type classifications by editing the configuration file or extending the code.

#### Time Rules
Adjust based on your workflow:
- **Fast-paced**: Shorter timeframes (3, 14, 60 days)
- **Deliberate**: Longer timeframes (14, 60, 180 days)

#### Path Structure
Customize directory names and locations to match existing workflows.

---

## Advanced Features

### Symlink Management

FlowSort uses relative symlinks for portability:
```bash
# Example symlink
documents/report.pdf -> ../all/report.pdf
```

**Benefits**:
- No broken links when moving directories
- Cross-platform compatibility
- Efficient storage usage

### Conflict Resolution

When moving files with duplicate names:
```
original.pdf
original_1.pdf
original_2.pdf
```

### Statistics Tracking

The `status` command provides insights:
- Total files per directory
- Files per category
- System health indicators

### Future Automation

Planned features:
- Daemon mode for real-time processing
- Scheduled archival operations
- Integration with file watchers
- Backup system integration

---

## Best Practices

### Organization Tips

1. **Trust the System**: Let files flow naturally through stages
2. **Weekly Reviews**: Manually check INBOX categories for accuracy
3. **Custom Categories**: Add project-specific categories as needed
4. **Archive Exploration**: Periodically review archived content

### Performance Considerations

1. **Large Files**: Consider separate handling for videos/archives
2. **Network Drives**: Be cautious with remote storage locations
3. **Backup Strategy**: Ensure ARCHIVE directory is backed up
4. **Monitoring**: Regular `flowsort status` checks

### Workflow Integration

1. **Development**: Keep code files in active DOCUMENTS
2. **Research**: Let PDFs flow to ARCHIVE after projects complete
3. **Media**: Separate personal vs. work media classifications
4. **Temporary Files**: Use INBOX for quick file exchanges

### Troubleshooting

#### Common Issues

**Broken Symlinks**:
```bash
flowsort cleanup
```

**Configuration Errors**:
```bash
flowsort config --show
flowsort init  # Reset if needed
```

**Missing Files**:
- Check ARCHIVE/by-date for auto-moved files
- Use system file search in ARCHIVE directory

#### Recovery Procedures

1. **Lost Configuration**: Re-run `flowsort init`
2. **Corrupted Symlinks**: Use `flowsort cleanup`
3. **Wrong Classifications**: Manually move files between category folders
4. **Accidental Archival**: Move files back from ARCHIVE/all to DOCUMENTS/all

---

## Conclusion

FlowSort provides a systematic approach to digital organization that balances automation with user control. By treating file organization as a natural flow process, it reduces cognitive overhead while maintaining flexibility for different workflows and preferences.

The system grows with your needs, starting simple with heuristic classification and expanding to include AI-powered organization as your requirements evolve.

**Remember**: The goal isn't perfect organization from day one, but sustainable, improving organization over time. Let FlowSort handle the mechanics while you focus on your work.

---

*FlowSort v1.0.0 - Built with ❤️ for keeping your digital life tidy*

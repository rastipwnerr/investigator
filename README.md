# ForensicParser - Windows Artifact Analysis Tool

A comprehensive Python-based forensic artifact parser that automates the extraction, processing, and ingestion of Windows forensic artifacts into Elasticsearch/Kibana for timeline analysis and investigation.

## 📋 Table of Contents

- [Features](#features)
- [Supported Artifacts](#supported-artifacts)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Use Cases & Examples](#use-cases--examples)
- [Configuration](#configuration)
- [License](#license)

## ✨ Features

- **Automatic File Organization**: Intelligently sorts forensic artifacts by type into case-specific folders
- **Multi-Parser Support**: Processes EVTX, MFT, Amcache, LNK, Registry, and other artifacts
- **ELK Integration**: Direct ingestion into Elasticsearch with automatic Kibana index pattern creation
- **Timesketch Support**: Export to Timesketch timeline format (JSONL)
- **Case Management**: Organize investigations by case name with isolated data
- **Cleanup Utilities**: Easily remove case data and Elasticsearch indices
- **Log2Timeline Integration**: Plaso support for additional artifact types
- **Batch Processing**: Process entire evidence directories in one command

## 🗂️ Supported Artifacts

| Artifact Type | Parser | Description |
|---------------|--------|-------------|
| **EVTX** | evtx_dump | Windows Event Logs (.evtx files) |
| **MFT** | MFTECmd | Master File Table ($MFT) - filesystem timeline |
| **Amcache** | AmcacheParser | Application execution history (Amcache.hve) |
| **LNK** | LECmd | Windows shortcuts - file access artifacts |
| **Registry** | RECmd | Registry hives (SYSTEM, SOFTWARE, SAM, SECURITY, NTUSER.DAT, UsrClass.dat) |
| **Other** | log2timeline (Plaso) | Browser history, prefetch, and other artifacts |

## 📋 Prerequisites

### System Requirements

- **Python**: 3.8 or higher
- **Operating System**: Linux (primary), Windows (with WSL), macOS
- **RAM**: 8GB minimum (16GB+ recommended for large datasets)
- **Disk Space**: Sufficient for evidence files and parsed JSON output

### Required Tools

1. **Python Packages**:
   ```bash
   pip install elasticsearch>=8.0.0
   pip install timesketch-api-client>=20230809
   pip install timesketch-import-client>=20230809
   pip install requests>=2.28.0
   ```

2. **Eric Zimmerman Tools** (for Windows artifact parsing):
   - [MFTECmd](https://github.com/EricZimmerman/MFTECmd) - MFT parser
   - [AmcacheParser](https://github.com/EricZimmerman/AmcacheParser) - Amcache parser
   - [LECmd](https://github.com/EricZimmerman/LECmd) - LNK parser
   - [RECmd](https://github.com/EricZimmerman/RECmd) - Registry parser

3. **EVTX Parser**:
   - [evtx_dump](https://github.com/omerbenamram/evtx) - Rust-based EVTX parser

4. **Plaso (optional, for log2timeline)**:
   ```bash
   pip install plaso-tools
   ```

5. **ELK Stack**:
   - Elasticsearch 8.x
   - Kibana 8.x

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd parserthethings-main
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Download Forensic Tools

Place the following binaries in the project root directory or in your system PATH:

```bash
# Linux example
wget https://github.com/EricZimmerman/MFTECmd/releases/latest/download/MFTECmd.zip
unzip MFTECmd.zip
chmod +x MFTECmd

# Repeat for AmcacheParser, LECmd, RECmd
# For evtx_dump on Linux:
cargo install evtx
# Or download pre-compiled binary
```

### 4. Configure Elasticsearch/Kibana

Edit `config.py` to match your environment:

```python
# Elasticsearch / Kibana Configuration
ES_HOST = "http://localhost:9200"
KIBANA_HOST = "http://localhost:5601"

# Timesketch Configuration (optional)
TIMESKETCH_HOST = "http://localhost:80"
TIMESKETCH_USERNAME = os.environ.get("TIMESKETCH_USERNAME", "admin")
TIMESKETCH_PASSWORD = os.environ.get("TIMESKETCH_PASSWORD", "admin")
```

### 5. Verify Installation

```bash
python main_app.py --help
```

## 🎯 Quick Start

### Basic Workflow

```bash
# 1. Organize evidence files by artifact type
python main_app.py --organize --source-dir /path/to/evidence --case-name Investigation-001

# 2. Parse and ingest into Elasticsearch
python main_app.py --case-name Investigation-001 --platform elk --all

# 3. Access Kibana to view timeline
# Open: http://localhost:5601/app/discover
```

## 📖 Usage

### Command-Line Options

```
python main_app.py [OPTIONS]
```

#### File Organization

| Option | Description |
|--------|-------------|
| `--organize` | Automatically organize files by artifact type |
| `--source-dir DIR` | Source directory containing evidence files |
| `--case-name NAME` | Case name (creates subfolder for organized files) |
| `--move` | Move files instead of copying (default: copy) |
| `--list-cases` | List all organized cases |

#### Parsing Options

| Option | Description |
|--------|-------------|
| `--platform {elk,timesketch}` | Target platform for ingestion |
| `--evtx` | Parse EVTX files |
| `--mft` | Parse MFT files |
| `--amcache` | Parse Amcache.hve files |
| `--lnk` | Parse LNK shortcut files |
| `--registry` | Parse Registry hive files |
| `--log2timeline` | Parse with Plaso (other file types) |
| `--all` | Parse all artifact types |

#### Output Options

| Option | Description |
|--------|-------------|
| `--index-name NAME` | Custom Elasticsearch index name |
| `--sketch-name NAME` | Timesketch sketch name (required for Timesketch) |

#### Cleanup Options

| Option | Description |
|--------|-------------|
| `--clean-case NAME` | Remove all files for a specific case |
| `--clean-case-indices NAME` | Remove Elasticsearch indices for a case |
| `--clean-all-indices` | Remove ALL Elasticsearch indices (requires confirmation) |
| `--clean-logs` | Remove log2timeline/psort log files |
| `--dry-run` | Simulation mode (show what would be deleted) |

## 💡 Use Cases & Examples

### Use Case 1: Specifying the logs parsed

```bash
# Step 1: Organize evidence from mounted forensic image
python main_app.py \
    --organize \
    --source-dir /mnt/evidence/C_Drive \
    --case-name Ransomware-2024-001

# Step 2: Parse critical artifacts
python main_app.py \
    --case-name Ransomware-2024-001 \
    --platform elk \
    --evtx \
    --mft \
    --amcache \
    --lnk

```

### Use Case 2: Complete Timeline Analysis

```bash
# Full parsing with log2timeline for maximum coverage
python main_app.py \
    --organize \
    --source-dir /mnt/forensic_image \
    --move \
    --case-name FullTimeline \
    --platform elk \
    --all

# This will parse:
# - All EVTX logs
# - Complete MFT timeline
# - Amcache execution history
# - All LNK files
# - Registry hives
# - Browser history, prefetch, etc. (via log2timeline)
```

### Use Case 3: Quick Triage - Event Log Analysis Only

```bash
# Parse only EVTX files
python main_app.py \
    --case-name QuickTriage \
    --source-dir /evidence/evtx_logs \
    --platform elk \
    --evtx \
    --organize
```

### Use Case 4: File System Timeline

```bash
# Parse MFT only for filesystem timeline
python main_app.py \
    --case-name FileSystem-2024-005 \
    --platform elk \
    --mft
```

### Use Case 5: Case Cleanup

**Scenario**: Remove old investigation data.

```bash
# Preview what will be deleted
python main_app.py \
    --clean-case Investigation-001 \
    --dry-run

# Actually delete case files and indices
python main_app.py \
    --clean-case Investigation-001 \
    --platform elk

# Or just clean indices, keep files
python main_app.py \
    --clean-case-indices Investigation-001

```

### Case Organization

Each case creates the following structure:

```
evtx/[case-name]/           # Organized EVTX files
mft/[case-name]/            # Organized MFT files
amcache/[case-name]/        # Organized Amcache files
lnk/[case-name]/            # Organized LNK files
registry/[case-name]/       # Organized registry hives
other/[case-name]/          # Other files (for log2timeline)
jsons_elk/[case-name]/      # Parsed JSON for ELK
jsons_timesketch/[case-name]/ # Parsed JSONL for Timesketch
```

## ⚙️ Configuration

### Elasticsearch Settings

The tool automatically creates:
- **Indices**: `[case-name]_[artifact-type]` (e.g., `investigation-001_evtx`)
- **Index Pattern**: `[case-name]_*`
- **Time Field**: `@timestamp`
- **Timezone**: UTC





## 📄 License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2024 ForensicParser Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```




## 🙏 Acknowledgments

- **Eric Zimmerman** - For the excellent suite of forensic tools
- **Plaso Team** - For log2timeline framework
- **evtx_dump** - Rust-based EVTX parser
- **ELK Stack** - Elasticsearch, Kibana for visualization
- **Timesketch** - Timeline analysis platform

**Note**: This tool is designed for legitimate forensic analysis and incident response activities. Users are responsible for ensuring they have proper authorization before analyzing any systems or data.

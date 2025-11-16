#!/usr/bin/env python3
"""
Centralized configuration for forensic artifact parser
"""

import os

# Elasticsearch / Kibana Configuration
ES_HOST = "http://localhost:9200"
KIBANA_HOST = "http://localhost:5601"

# Timesketch Configuration
TIMESKETCH_HOST = "http://localhost:80"
TIMESKETCH_USERNAME = os.environ.get("TIMESKETCH_USERNAME", "admin")
TIMESKETCH_PASSWORD = os.environ.get("TIMESKETCH_PASSWORD", "admin")

# Source Folders for Forensic Artifacts
EVTX_FOLDER = "./evtx"
MFT_FOLDER = "./mft"
AMCACHE_FOLDER = "./amcache"
LNK_FOLDER = "./lnk"
REGISTRY_FOLDER = "./registry"
OTHER_FOLDER = "./other"  # For unsupported files (will be processed with log2timeline)

# JSON Output Folders
JSON_FOLDER_ELK_BASE = "./jsons_elk"
JSON_FOLDER_TIMESKETCH_BASE = "./jsons_timesketch"


def get_json_folder(platform: str, case_name: str = None) -> str:
    """
    Get the appropriate JSON output folder based on platform and case name

    Args:
        platform: Target platform ("elk" or "timesketch")
        case_name: Case name (optional)

    Returns:
        Full path to the JSON output folder
    """
    base_folder = JSON_FOLDER_ELK_BASE if platform == "elk" else JSON_FOLDER_TIMESKETCH_BASE

    if case_name:
        return os.path.join(base_folder, case_name)
    return base_folder


# Possible paths for forensic tool binaries
EVTX_DUMP_PATHS = [
    "./evtx_dump",
    "evtx_dump",
    "/usr/local/bin/evtx_dump",
    "/usr/bin/evtx_dump",
]

MFT_DUMP_PATHS = [
    "./MFTECmd",
    "MFTECmd",
    "./MFTECmd.exe",
    "MFTECmd.exe",
    "/usr/local/bin/MFTECmd",
    "/usr/bin/MFTECmd",
]

AMCACHE_PARSER_PATHS = [
    "./AmcacheParser",
    "AmcacheParser",
    "./AmcacheParser.exe",
    "AmcacheParser.exe",
    "/usr/local/bin/AmcacheParser",
    "/usr/bin/AmcacheParser",
]

LECMD_PATHS = [
    "./LECmd",
    "LECmd",
    "./LECmd.exe",
    "LECmd.exe",
    "/usr/local/bin/LECmd",
    "/usr/bin/LECmd",
]

RECMD_PATHS = [
    "./RECmd",
    "RECmd",
    "./RECmd.exe",
    "RECmd.exe",
    "/usr/local/bin/RECmd",
    "/usr/bin/RECmd",
]

LOG2TIMELINE_PATHS = [
    "log2timeline.py",
    "/usr/local/bin/log2timeline.py",
    "/usr/bin/log2timeline.py",
]

PSORT_PATHS = [
    "psort.py",
    "/usr/local/bin/psort.py",
    "/usr/bin/psort.py",
]
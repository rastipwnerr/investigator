#!/usr/bin/env python3
"""
Parser for MFT ($MFT - Master File Table) files
"""

import os
import json
import subprocess
import sys
import csv
import glob
import shutil
import tempfile
import time
from datetime import datetime
from typing import Optional


class MFTParser:
    """Class to parse MFT files using MFTECmd"""

    def __init__(self, mft_dump_path: str):
        """
        Initialize the MFT parser

        Args:
            mft_dump_path: Path to the MFTECmd binary
        """
        self.mft_dump_path = mft_dump_path

    @staticmethod
    def parse_mft_timestamp(timestamp_str: str) -> Optional[str]:
        """Convert MFT timestamp to ISO format"""
        if not timestamp_str or timestamp_str in ['', '1601-01-01 00:00:00', '1601-01-01 00:00:00.0000000']:
            return None

        try:
            # MFTECmd format: "2024-01-15 14:30:45.1234567" (with microseconds)
            if '.' in timestamp_str:
                base, microseconds = timestamp_str.split('.')
                microseconds = microseconds[:6].ljust(6, '0')
                timestamp_str = f"{base}.{microseconds}"

            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
            return dt.isoformat() + 'Z'
        except:
            try:
                dt = datetime.strptime(timestamp_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                return dt.isoformat() + 'Z'
            except:
                try:
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    return dt.isoformat() + 'Z'
                except:
                    return None

    @staticmethod
    def safe_rmtree(path: str, max_attempts: int = 5) -> bool:
        """
        Safely remove a directory with multiple attempts

        Args:
            path: Path to the directory to remove
            max_attempts: Maximum number of attempts

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_attempts):
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
                return True
            except (PermissionError, OSError) as e:
                if attempt < max_attempts - 1:
                    time.sleep(0.5)  # Wait a bit before retrying
                else:
                    print(f"    Unable to remove {path}: {e}")
                    return False
        return False

    def parse_file(self, mft_path: str, output_json_path: str, platform: str = "elk") -> bool:
        """
        Parse an MFT file and save the result as JSON

        Args:
            mft_path: Path to the MFT file
            output_json_path: Path to the JSON output file
            platform: Target platform ("elk" or "timesketch")

        Returns:
            True if successful, False otherwise
        """
        print(f"  Parsing: {os.path.basename(mft_path)}")

        if not self.mft_dump_path:
            print(f"    MFTECmd not found.", file=sys.stderr)
            print(f"    Place the MFTECmd binary in the current directory", file=sys.stderr)
            return False

        # Create a unique temporary directory with tempfile
        temp_dir = tempfile.mkdtemp(prefix="mft_")

        try:
            # MFTECmd command
            cmd = [
                self.mft_dump_path,
                '-f', mft_path,
                '--csv', temp_dir,
                '--csvf', 'output.csv'
            ]

            print(f"    Command: {' '.join(cmd)}")

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
                if result.stdout:
                    print(f"    Output: {result.stdout[:200]}")
            except subprocess.CalledProcessError as e:
                print(f"    MFTECmd error (code {e.returncode})", file=sys.stderr)
                print(f"       stdout: {e.stdout[:300]}", file=sys.stderr)
                print(f"       stderr: {e.stderr[:300]}", file=sys.stderr)
                return False
            except subprocess.TimeoutExpired:
                print(f"    Timeout during MFT parsing (>300s)", file=sys.stderr)
                return False
            except FileNotFoundError:
                print(f"    MFTECmd not executable: {self.mft_dump_path}", file=sys.stderr)
                return False

            # Find the generated CSV file
            csv_files = glob.glob(os.path.join(temp_dir, "*.csv"))
            if not csv_files:
                print(f"    No CSV file generated in {temp_dir}", file=sys.stderr)
                return False

            temp_csv = csv_files[0]
            print(f"    CSV generated: {os.path.basename(temp_csv)}")

            # Read CSV and convert to JSON
            entries = []
            try:
                with open(temp_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
                    reader = csv.DictReader(csvfile)

                    for row_num, row in enumerate(reader, 1):
                        try:
                            entry = {}

                            # Clean and structure the data
                            for key, value in row.items():
                                if not key:
                                    continue

                                if value and str(value).strip():
                                    clean_key = str(key).strip().replace(' ', '_').replace('/', '_').replace('\\',
                                                                                                             '_').replace(
                                        '(', '').replace(')', '').lower()
                                    entry[clean_key] = str(value).strip()

                            if not entry:
                                continue

                            # Common timestamp fields in MFTECmd output
                            timestamp_fields = [
                                'created0x10', 'modified0x10', 'accessed0x10', 'recordmodified0x10',
                                'created0x30', 'modified0x30', 'accessed0x30', 'recordmodified0x30',
                                'created', 'modified', 'accessed', 'mftrecordnumber'
                            ]

                            timestamps = []
                            for ts_field in timestamp_fields:
                                if ts_field in entry:
                                    parsed_ts = self.parse_mft_timestamp(entry[ts_field])
                                    if parsed_ts:
                                        timestamps.append(parsed_ts)
                                        entry[f'{ts_field}_iso'] = parsed_ts

                            # Use the most recent timestamp
                            if timestamps:
                                latest_timestamp = max(timestamps)
                            else:
                                latest_timestamp = datetime.now().isoformat() + 'Z'

                            if platform == "elk":
                                # Format for Elasticsearch
                                entry['@timestamp'] = latest_timestamp
                            elif platform == "timesketch":
                                # Format for Timesketch
                                entry['datetime'] = latest_timestamp
                                # Use created0x10 as timestamp_desc
                                if 'created0x10_iso' in entry:
                                    entry['timestamp_desc'] = entry['created0x10_iso']
                                # Duplicate nametype as message
                                if 'nametype' in entry:
                                    entry['message'] = entry['nametype']

                            # Add metadata
                            entry['source_file'] = os.path.basename(mft_path)
                            entry['log_type'] = 'mft'
                            entry['parser'] = 'mftecmd'

                            entries.append(entry)

                        except Exception as e:
                            print(f"    Error on line {row_num}: {e}")
                            continue

            except Exception as e:
                print(f"    CSV read error: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                return False

            if not entries:
                print(f"    No MFT entries extracted", file=sys.stderr)
                return False

            # Sort by timestamp
            if platform == "elk":
                entries.sort(key=lambda x: x.get('@timestamp', ''))
            else:
                entries.sort(key=lambda x: x.get('datetime', ''))

            # Save as JSONL
            with open(output_json_path, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')

            print(f"    {len(entries)} MFT entries extracted -> {os.path.basename(output_json_path)}")
            return True

        except Exception as e:
            print(f"    Unexpected error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return False

        finally:
            # Clean temporary directory with multiple attempts
            self.safe_rmtree(temp_dir)
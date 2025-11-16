#!/usr/bin/env python3
"""
Parser for Amcache.hve files
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


class AmcacheParser:
    """Class to parse Amcache.hve files with AmcacheParser"""

    def __init__(self, amcache_parser_path: str):
        """
        Initialize the Amcache parser

        Args:
            amcache_parser_path: Path to the AmcacheParser binary
        """
        self.amcache_parser_path = amcache_parser_path

    @staticmethod
    def parse_timestamp(timestamp_str: str) -> Optional[str]:
        """Convert a timestamp to ISO format"""
        if not timestamp_str or timestamp_str.strip() == '':
            return None

        try:
            # Common timestamp formats
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%m/%d/%Y %H:%M:%S',
                '%m/%d/%Y %I:%M:%S %p'
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(timestamp_str.strip(), fmt)
                    return dt.isoformat() + 'Z'
                except ValueError:
                    continue

            # Try direct ISO format
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
                    print(f"    Warning: Unable to remove {path}: {e}")
                    return False
        return False

    def parse_file(self, amcache_path: str, output_json_path: str, platform: str = "elk") -> bool:
        """
        Parse an Amcache.hve file and save the result as JSON

        Args:
            amcache_path: Path to the Amcache.hve file
            output_json_path: Path to the output JSON file
            platform: "elk" or "timesketch"

        Returns:
            True if successful, False otherwise
        """
        print(f"  Parsing: {os.path.basename(amcache_path)}")

        if not self.amcache_parser_path:
            print(f"    Error: AmcacheParser not found.", file=sys.stderr)
            return False

        # Create a unique temporary directory with tempfile
        temp_dir = tempfile.mkdtemp(prefix="amcache_")

        try:
            # AmcacheParser command
            cmd = [
                self.amcache_parser_path,
                '-f', amcache_path,
                '--csv', temp_dir,
                '-i'  # Include all data
            ]

            print(f"    Command: {' '.join(cmd)}")

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
                if result.stdout:
                    print(f"    Output: {result.stdout[:200]}")
            except subprocess.CalledProcessError as e:
                print(f"    Error: AmcacheParser failed (code {e.returncode})", file=sys.stderr)
                print(f"       stderr: {e.stderr[:300]}", file=sys.stderr)
                return False
            except subprocess.TimeoutExpired:
                print(f"    Error: Timeout during Amcache parsing (>300s)", file=sys.stderr)
                return False
            except FileNotFoundError:
                print(f"    Error: AmcacheParser not executable: {self.amcache_parser_path}", file=sys.stderr)
                return False

            # Find generated CSV files (AmcacheParser generates multiple CSVs)
            csv_files = glob.glob(os.path.join(temp_dir, "*.csv"))
            if not csv_files:
                print(f"    Error: No CSV file generated in {temp_dir}", file=sys.stderr)
                return False

            print(f"    {len(csv_files)} CSV file(s) generated")

            # Read all CSVs and convert to JSON
            entries = []

            for csv_file in csv_files:
                csv_basename = os.path.splitext(os.path.basename(csv_file))[0]
                print(f"    Reading: {os.path.basename(csv_file)}")

                try:
                    with open(csv_file, 'r', encoding='utf-8', errors='ignore') as csvfile:
                        reader = csv.DictReader(csvfile)

                        for row in reader:
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

                                # Common timestamp fields in AmcacheParser
                                timestamp_fields = [
                                    'keymodifiedtimestamp', 'compiledtime', 'created',
                                    'modified', 'linkdate', 'lastmodifiedtimestamp',
                                    'lastmodifiedtimestamp2', 'filekeylastaccessedtime'
                                ]

                                timestamps = []
                                for ts_field in timestamp_fields:
                                    if ts_field in entry:
                                        parsed_ts = self.parse_timestamp(entry[ts_field])
                                        if parsed_ts:
                                            timestamps.append(parsed_ts)
                                            entry[f'{ts_field}_iso'] = parsed_ts

                                # Use the most recent timestamp or default
                                if timestamps:
                                    latest_timestamp = max(timestamps)
                                else:
                                    latest_timestamp = datetime.now().isoformat() + 'Z'

                                if platform == "elk":
                                    entry['@timestamp'] = latest_timestamp
                                elif platform == "timesketch":
                                    entry['datetime'] = latest_timestamp
                                    entry['timestamp_desc'] = 'Amcache Entry'
                                    # Create a descriptive message
                                    if 'applicationname' in entry:
                                        entry['message'] = f"Amcache: {entry['applicationname']}"
                                    elif 'fullpath' in entry:
                                        entry['message'] = f"Amcache: {entry['fullpath']}"
                                    else:
                                        entry['message'] = f"Amcache entry from {csv_basename}"

                                # Add metadata
                                entry['source_file'] = os.path.basename(amcache_path)
                                entry['csv_source'] = csv_basename
                                entry['log_type'] = 'amcache'
                                entry['parser'] = 'amcacheparser'

                                entries.append(entry)

                            except Exception as e:
                                print(f"    Warning: Error reading row: {e}")
                                continue

                except Exception as e:
                    print(f"    Error: Failed to read CSV {csv_file}: {e}", file=sys.stderr)
                    continue

            if not entries:
                print(f"    Warning: No Amcache entries extracted", file=sys.stderr)
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

            print(f"    ✓ {len(entries)} Amcache entries extracted -> {os.path.basename(output_json_path)}")
            return True

        except Exception as e:
            print(f"    Error: Unexpected error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return False

        finally:
            # Clean up temporary directory with multiple attempts
            self.safe_rmtree(temp_dir)

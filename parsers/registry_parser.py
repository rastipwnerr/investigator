#!/usr/bin/env python3
"""
Parser for Registry Hive files (SYSTEM, SOFTWARE, SAM, SECURITY, etc.)
"""

import os
import json
import subprocess
import sys
import csv
import glob
import shutil
from datetime import datetime
from typing import Optional


class RegistryParser:
    """Class to parse Registry Hive files with RECmd"""

    def __init__(self, recmd_path: str):
        """
        Initialize the Registry parser

        Args:
            recmd_path: Path to the RECmd binary
        """
        self.recmd_path = recmd_path

    @staticmethod
    def parse_timestamp(timestamp_str: str) -> Optional[str]:
        """Converts a timestamp to ISO format"""
        if not timestamp_str or timestamp_str.strip() == '':
            return None

        try:
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

            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.isoformat() + 'Z'
        except:
            return None

    def parse_file(self, registry_path: str, output_json_path: str, platform: str = "elk") -> bool:
        """
        Parse a Registry Hive file and save the result to JSON

        Args:
            registry_path: Path to the registry hive file
            output_json_path: Path to the output JSON file
            platform: "elk" or "timesketch"

        Returns:
            True if successful, False otherwise
        """
        print(f"  Parsing: {os.path.basename(registry_path)}")

        if not self.recmd_path:
            print(f"    Error: RECmd not found.", file=sys.stderr)
            return False

        # Create temporary folder for CSV
        temp_dir = "./temp_registry"
        os.makedirs(temp_dir, exist_ok=True)

        # RECmd command to process a hive
        # RECmd can use batch plugins to extract specific information
        cmd = [
            self.recmd_path,
            '-f', registry_path,
            '--csv', temp_dir,
            '--bn', './parsers/BatchExamples/DFIRBatch.reb'  # Use a batch to extract data
        ]

        # If no batch available, use basic dump mode
        # Try first with batch, then without if it fails
        print(f"    Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            if result.stdout:
                print(f"    Output: {result.stdout[:200]}")
        except subprocess.CalledProcessError as e:
            # If batch fails, try without batch
            print(f"    Batch not available, trying standard mode...")
            cmd = [
                self.recmd_path,
                '-f', registry_path,
                '--csv', temp_dir
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
                if result.stdout:
                    print(f"    Output: {result.stdout[:200]}")
            except subprocess.CalledProcessError as e2:
                print(f"    Error: RECmd failed (code {e2.returncode})", file=sys.stderr)
                print(f"       stderr: {e2.stderr[:300]}", file=sys.stderr)
                return False
        except subprocess.TimeoutExpired:
            print(f"    Error: Timeout during Registry parsing (>300s)", file=sys.stderr)
            return False
        except FileNotFoundError:
            print(f"    Error: RECmd not executable: {self.recmd_path}", file=sys.stderr)
            return False

        # Find generated CSV files
        csv_files = glob.glob(os.path.join(temp_dir, "*.csv"))
        if not csv_files:
            print(f"    Error: No CSV file generated in {temp_dir}", file=sys.stderr)
            return False

        print(f"    {len(csv_files)} CSV file(s) generated")

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

                            # Common timestamp fields in RECmd
                            timestamp_fields = [
                                'lastwritetime', 'lastmodified', 'timestamp',
                                'installdate', 'created', 'modified',
                                'lastconnected', 'lastaccessed'
                            ]

                            timestamps = []
                            for ts_field in timestamp_fields:
                                if ts_field in entry:
                                    parsed_ts = self.parse_timestamp(entry[ts_field])
                                    if parsed_ts:
                                        timestamps.append(parsed_ts)
                                        entry[f'{ts_field}_iso'] = parsed_ts

                            if timestamps:
                                latest_timestamp = max(timestamps)
                            else:
                                latest_timestamp = datetime.now().isoformat() + 'Z'

                            if platform == "elk":
                                entry['@timestamp'] = latest_timestamp
                            elif platform == "timesketch":
                                entry['datetime'] = latest_timestamp
                                entry['timestamp_desc'] = 'Registry Key Modified'
                                # Create a descriptive message
                                if 'keypath' in entry:
                                    entry['message'] = f"Registry: {entry['keypath']}"
                                elif 'valuename' in entry:
                                    entry['message'] = f"Registry value: {entry['valuename']}"
                                elif 'path' in entry:
                                    entry['message'] = f"Registry: {entry['path']}"
                                else:
                                    entry['message'] = f"Registry entry from {csv_basename}"

                            # Add metadata
                            entry['source_file'] = os.path.basename(registry_path)
                            entry['csv_source'] = csv_basename
                            entry['log_type'] = 'registry'
                            entry['parser'] = 'recmd'

                            # Determine hive type from filename
                            hive_name = os.path.basename(registry_path).upper()
                            if 'SYSTEM' in hive_name:
                                entry['hive_type'] = 'SYSTEM'
                            elif 'SOFTWARE' in hive_name:
                                entry['hive_type'] = 'SOFTWARE'
                            elif 'SAM' in hive_name:
                                entry['hive_type'] = 'SAM'
                            elif 'SECURITY' in hive_name:
                                entry['hive_type'] = 'SECURITY'
                            elif 'NTUSER' in hive_name:
                                entry['hive_type'] = 'NTUSER.DAT'
                            elif 'USRCLASS' in hive_name:
                                entry['hive_type'] = 'UsrClass.dat'
                            else:
                                entry['hive_type'] = 'UNKNOWN'

                            entries.append(entry)

                        except Exception as e:
                            print(f"    Warning: Error reading line: {e}")
                            continue

            except Exception as e:
                print(f"    Error: Error reading CSV {csv_file}: {e}", file=sys.stderr)
                continue

        # Clean up temporary folder
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

        if not entries:
            print(f"    Warning: No Registry entries extracted", file=sys.stderr)
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

        print(f"    ✓ {len(entries)} Registry entries extracted -> {os.path.basename(output_json_path)}")
        return True
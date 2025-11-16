#!/usr/bin/env python3
"""
Cleanup utility for cases and indices
"""

import os
import shutil
import glob
import requests
from typing import List, Optional
from elasticsearch import Elasticsearch


class CleanupUtility:
    """Class to clean up cases, files, and indices"""

    def __init__(self, config):
        """
        Initialize the cleanup utility

        Args:
            config: Configuration module containing paths
        """
        self.config = config
        self.base_folders = {
            'evtx': config.EVTX_FOLDER,
            'mft': config.MFT_FOLDER,
            'amcache': config.AMCACHE_FOLDER,
            'lnk': config.LNK_FOLDER,
            'registry': config.REGISTRY_FOLDER,
            'other': config.OTHER_FOLDER
        }
        self.json_folders = {
            'elk': config.JSON_FOLDER_ELK_BASE,
            'timesketch': config.JSON_FOLDER_TIMESKETCH_BASE
        }

    def list_all_cases(self) -> List[str]:
        """
        List all organized cases

        Returns:
            List of unique case names
        """
        all_cases = set()

        for folder_type, base_folder in self.base_folders.items():
            if os.path.exists(base_folder):
                subdirs = [d for d in os.listdir(base_folder)
                           if os.path.isdir(os.path.join(base_folder, d))]
                all_cases.update(subdirs)

        return sorted(list(all_cases))

    def clean_case_files(self, case_name: str, dry_run: bool = False) -> bool:
        """
        Clean all files for a specific case

        Args:
            case_name: Case name to clean
            dry_run: If True, only display what would be deleted

        Returns:
            True if successful, False otherwise
        """
        print(f"\nCleaning case files: {case_name}")

        if dry_run:
            print("   SIMULATION MODE (no actual deletion)")

        deleted_count = 0
        total_size = 0

        # Clean source folders (evtx, mft, etc.)
        for folder_type, base_folder in self.base_folders.items():
            case_folder = os.path.join(base_folder, case_name)

            if os.path.exists(case_folder):
                # Calculate size
                folder_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                                  for dirpath, dirnames, filenames in os.walk(case_folder)
                                  for filename in filenames)

                file_count = sum(len(filenames)
                                 for _, _, filenames in os.walk(case_folder))

                total_size += folder_size
                deleted_count += file_count

                print(f"   {folder_type}: {case_folder}")
                print(f"      {file_count} file(s), {folder_size / (1024 * 1024):.2f} MB")

                if not dry_run:
                    try:
                        shutil.rmtree(case_folder)
                        print(f"      Deleted")
                    except Exception as e:
                        print(f"      Error: {e}")
                        return False

        # Clean JSON folders
        for platform, json_base in self.json_folders.items():
            json_case_folder = os.path.join(json_base, case_name)

            if os.path.exists(json_case_folder):
                folder_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                                  for dirpath, dirnames, filenames in os.walk(json_case_folder)
                                  for filename in filenames)

                file_count = sum(len(filenames)
                                 for _, _, filenames in os.walk(json_case_folder))

                total_size += folder_size
                deleted_count += file_count

                print(f"   jsons_{platform}: {json_case_folder}")
                print(f"      {file_count} file(s), {folder_size / (1024 * 1024):.2f} MB")

                if not dry_run:
                    try:
                        shutil.rmtree(json_case_folder)
                        print(f"      Deleted")
                    except Exception as e:
                        print(f"      Error: {e}")
                        return False

        if dry_run:
            print(f"\n   Total: {deleted_count} file(s), {total_size / (1024 * 1024):.2f} MB would be deleted")
        else:
            print(f"\n   Cleanup complete: {deleted_count} file(s), {total_size / (1024 * 1024):.2f} MB deleted")

        return True

    def clean_case_indices_elk(self, case_name: str, es_host: str, kibana_host: str,
                               dry_run: bool = False) -> bool:
        """
        Clean all Elasticsearch indices for a specific case

        Args:
            case_name: Case name
            es_host: Elasticsearch URL
            kibana_host: Kibana URL
            dry_run: If True, only display what would be deleted

        Returns:
            True if successful, False otherwise
        """
        print(f"\nCleaning Elasticsearch indices for case: {case_name}")

        if dry_run:
            print("   SIMULATION MODE (no actual deletion)")

        try:
            es = Elasticsearch(
                es_host,
                verify_certs=False,
                ssl_show_warn=False,
                basic_auth=None
            )

            if not es.ping():
                print(f"   Unable to connect to Elasticsearch")
                return False

            # Sanitize case name to match indices
            from ingesters.elasticsearch_ingester import ElasticsearchIngester
            sanitized_case = ElasticsearchIngester.sanitize_index_name(case_name)

            # Search for indices
            indices_resp = es.cat.indices(index=f"*{sanitized_case}*", format="json")
            indices = [idx["index"] for idx in indices_resp]

            if not indices:
                print(f"   No indices found for case '{case_name}' (pattern: *{sanitized_case}*)")
                return True

            print(f"   {len(indices)} index/indices found:")
            for idx in indices:
                print(f"      - {idx}")

            if not dry_run:
                for idx in indices:
                    try:
                        es.indices.delete(index=idx)
                        print(f"      Index deleted: {idx}")
                    except Exception as e:
                        print(f"      Error deleting {idx}: {e}")

                # Clean Kibana index patterns
                try:
                    res = requests.get(
                        f"{kibana_host}/api/saved_objects/_find?type=index-pattern&search={sanitized_case}&search_fields=title",
                        headers={"kbn-xsrf": "true"}
                    )
                    if res.status_code == 200:
                        objects = res.json().get("saved_objects", [])
                        for obj in objects:
                            obj_id = obj["id"]
                            requests.delete(
                                f"{kibana_host}/api/saved_objects/index-pattern/{obj_id}",
                                headers={"kbn-xsrf": "true"}
                            )
                            print(f"      Index Pattern deleted: {obj['attributes']['title']}")
                except Exception as e:
                    print(f"      Kibana cleanup error: {e}")

                print(f"\n   Cleanup complete: {len(indices)} index/indices deleted")
            else:
                print(f"\n   {len(indices)} index/indices would be deleted")

            return True

        except Exception as e:
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def clean_all_indices_elk(self, es_host: str, kibana_host: str,
                              pattern: str = "*", dry_run: bool = False) -> bool:
        """
        Clean ALL Elasticsearch indices (or by pattern)

        Args:
            es_host: Elasticsearch URL
            kibana_host: Kibana URL
            pattern: Index search pattern (default: all)
            dry_run: If True, only display what would be deleted

        Returns:
            True if successful, False otherwise
        """
        print(f"\nCleaning all Elasticsearch indices (pattern: {pattern})")
        print("   WARNING: This operation is irreversible!")

        if dry_run:
            print("   SIMULATION MODE (no actual deletion)")

        try:
            es = Elasticsearch(
                es_host,
                verify_certs=False,
                ssl_show_warn=False,
                basic_auth=None
            )

            if not es.ping():
                print(f"   Unable to connect to Elasticsearch")
                return False

            # Search for all indices
            indices_resp = es.cat.indices(index=pattern, format="json")
            # Exclude system indices (.kibana, .security, etc.)
            indices = [idx["index"] for idx in indices_resp
                       if not idx["index"].startswith('.')]

            if not indices:
                print(f"   No indices found")
                return True

            print(f"   {len(indices)} index/indices found:")
            for idx in indices:
                print(f"      - {idx}")

            if not dry_run:
                # Request confirmation
                confirm = input(f"\n   WARNING: Are you sure you want to delete {len(indices)} index/indices? (yes/no): ")
                if confirm.lower() not in ['yes', 'y']:
                    print("   Operation cancelled")
                    return False

                for idx in indices:
                    try:
                        es.indices.delete(index=idx)
                        print(f"      Index deleted: {idx}")
                    except Exception as e:
                        print(f"      Error deleting {idx}: {e}")

                # Clean all Kibana index patterns
                try:
                    res = requests.get(
                        f"{kibana_host}/api/saved_objects/_find?type=index-pattern",
                        headers={"kbn-xsrf": "true"}
                    )
                    if res.status_code == 200:
                        objects = res.json().get("saved_objects", [])
                        for obj in objects:
                            obj_id = obj["id"]
                            requests.delete(
                                f"{kibana_host}/api/saved_objects/index-pattern/{obj_id}",
                                headers={"kbn-xsrf": "true"}
                            )
                            print(f"      Index Pattern deleted: {obj['attributes']['title']}")
                except Exception as e:
                    print(f"      Kibana cleanup error: {e}")

                print(f"\n   Cleanup complete: {len(indices)} index/indices deleted")
            else:
                print(f"\n   {len(indices)} index/indices would be deleted")

            return True

        except Exception as e:
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def clean_log2timeline_logs(self, base_dir: str = ".") -> int:
        """
        Clean log files generated by log2timeline

        Args:
            base_dir: Root directory to search

        Returns:
            Number of deleted files
        """
        print(f"\nCleaning log2timeline logs...")

        log_patterns = [
            "log2timeline-*.log.gz",
            "psort-*.log.gz",
            "Worker_*_log2timeline-*.log.gz"
        ]

        cleaned_count = 0
        for pattern in log_patterns:
            log_files = glob.glob(os.path.join(base_dir, pattern))
            for log_file in log_files:
                try:
                    os.remove(log_file)
                    print(f"   Deleted: {os.path.basename(log_file)}")
                    cleaned_count += 1
                except Exception as e:
                    print(f"   Error: {e}")

        if cleaned_count > 0:
            print(f"\n   {cleaned_count} log file(s) cleaned")
        else:
            print(f"   No log files found")

        return cleaned_count

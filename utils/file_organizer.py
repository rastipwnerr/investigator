#!/usr/bin/env python3
"""
Module to automatically organize forensic files by type
"""

import os
import shutil
import glob
from typing import Dict, List


class FileOrganizer:
    """Class to organize forensic files into folders by type"""

    # File type definitions and their characteristics
    FILE_TYPES = {
        'evtx': {
            'extensions': ['.evtx', '.EVTX'],
            'patterns': ['*.evtx', '*.EVTX'],
            'name_contains': []
        },
        'mft': {
            'extensions': ['.mft', '.MFT'],
            'patterns': ['*$MFT*', '*mft*', '*.mft'],
            'name_contains': ['$mft']
        },
        'amcache': {
            'extensions': ['.hve', '.HVE'],
            'patterns': ['*Amcache*', '*amcache*'],
            'name_contains': ['amcache']
        },
        'lnk': {
            'extensions': ['.lnk', '.LNK'],
            'patterns': ['*.lnk', '*.LNK'],
            'name_contains': []
        },
        'registry': {
            'extensions': [],
            'patterns': [],
            'name_contains': [],
            'exact_names': ['SYSTEM', 'SOFTWARE', 'SAM', 'SECURITY', 'DEFAULT'],
            'exact_names_with_ext': ['NTUSER.DAT', 'ntuser.dat', 'UsrClass.dat', 'usrclass.dat']
        }
    }

    def __init__(self, base_evtx_folder: str, base_mft_folder: str,
                 base_amcache_folder: str, base_lnk_folder: str,
                 base_registry_folder: str, base_other_folder: str):
        """
        Initialize the file organizer

        Args:
            base_*_folder: Base folders for each file type
        """
        self.base_folders = {
            'evtx': base_evtx_folder,
            'mft': base_mft_folder,
            'amcache': base_amcache_folder,
            'lnk': base_lnk_folder,
            'registry': base_registry_folder,
            'other': base_other_folder  # For unsupported files
        }

    @staticmethod
    def identify_file_type(filepath: str) -> str:
        """
        Identify file type based on its name and extension

        Args:
            filepath: Path to the file

        Returns:
            File type ('evtx', 'mft', 'amcache', etc.) or 'other'
        """
        filename = os.path.basename(filepath)
        filename_lower = filename.lower()
        file_ext = os.path.splitext(filepath)[1].lower()

        # Check EVTX first (very specific)
        if file_ext in ['.evtx']:
            return 'evtx'

        # Check LNK (very specific)
        if file_ext in ['.lnk']:
            return 'lnk'

        # Check MFT (must be before registry since $MFT has no extension)
        if filename in ['$MFT', '$mft'] or filename_lower.startswith('$mft'):
            return 'mft'
        if file_ext in ['.mft'] or 'mft' in filename_lower and file_ext == '':
            return 'mft'

        # Check Amcache (.hve files with "amcache" in the name)
        if 'amcache' in filename_lower and file_ext in ['.hve', '.log', '.log1', '.log2', '']:
            return 'amcache'

        # Check Registry (more restrictive)
        characteristics = FileOrganizer.FILE_TYPES['registry']

        # Check exact names (SYSTEM, SOFTWARE, SAM, SECURITY, DEFAULT)
        basename_no_ext = os.path.splitext(filename)[0]
        if basename_no_ext in characteristics.get('exact_names', []):
            # Exclude certain file types (.pf, .etl, etc.)
            if file_ext not in ['.pf', '.etl', '.log', '.txt', '.dat', '.db', '.csv']:
                return 'registry'

        # Check exact names with extension (NTUSER.DAT, UsrClass.dat)
        if filename in characteristics.get('exact_names_with_ext', []):
            return 'registry'

        # Check registry transaction files (.LOG1, .LOG2)
        if file_ext in ['.log1', '.log2']:
            base = os.path.splitext(filename)[0]
            # If the base corresponds to a registry hive
            if base in characteristics.get('exact_names', []) or \
                    base + '.DAT' in characteristics.get('exact_names_with_ext', []) or \
                    base + '.dat' in characteristics.get('exact_names_with_ext', []):
                return 'registry'

        # If no type is recognized, return 'other'
        return 'other'

    def find_files_recursive(self, source_dir: str) -> Dict[str, List[str]]:
        """
        Recursively find all forensic files in a directory

        Args:
            source_dir: Source directory to scan

        Returns:
            Dictionary {type: [list of files]}
        """
        files_by_type = {
            'evtx': [],
            'mft': [],
            'amcache': [],
            'lnk': [],
            'registry': [],
            'other': []
        }

        print(f"Recursive scan of: {source_dir}")

        # Walk through all files recursively
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                filepath = os.path.join(root, file)

                # Ignore temporary and hidden files
                if file.startswith('.') or file.startswith('~'):
                    continue

                # Identify file type
                file_type = self.identify_file_type(filepath)
                files_by_type[file_type].append(filepath)

        # Display summary
        print("\nFiles found:")
        total_files = 0
        for file_type, file_list in files_by_type.items():
            if file_list:
                if file_type == 'other':
                    print(f"  - {file_type.upper()}: {len(file_list)} file(s) (will be parsed with log2timeline)")
                else:
                    print(f"  - {file_type.upper()}: {len(file_list)} file(s)")
                total_files += len(file_list)

        print(f"\nTotal: {total_files} files detected\n")

        return files_by_type

    def organize_files(self, source_dir: str, case_name: str, copy_mode: bool = True) -> bool:
        """
        Organize files from source directory to destination folders

        Args:
            source_dir: Source directory containing files
            case_name: Sub-folder name to create in each type folder
            copy_mode: True to copy, False to move

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(source_dir):
            print(f"Source directory does not exist: {source_dir}")
            return False

        # Find all files
        files_by_type = self.find_files_recursive(source_dir)

        # Organize files by type
        action = "Copying" if copy_mode else "Moving"
        print(f"{action} files to destination folders...\n")

        total_organized = 0

        for file_type, file_list in files_by_type.items():
            if not file_list:
                continue

            # Create destination folder
            dest_folder = os.path.join(self.base_folders[file_type], case_name)
            os.makedirs(dest_folder, exist_ok=True)

            print(f"{file_type.upper()}: {dest_folder}")

            for filepath in file_list:
                try:
                    filename = os.path.basename(filepath)
                    dest_path = os.path.join(dest_folder, filename)

                    # Handle duplicates
                    if os.path.exists(dest_path):
                        base, ext = os.path.splitext(filename)
                        counter = 1
                        while os.path.exists(dest_path):
                            new_filename = f"{base}_{counter}{ext}"
                            dest_path = os.path.join(dest_folder, new_filename)
                            counter += 1

                    # Copy or move
                    if copy_mode:
                        shutil.copy2(filepath, dest_path)
                    else:
                        shutil.move(filepath, dest_path)

                    print(f"  {filename}")
                    total_organized += 1

                except Exception as e:
                    print(f"  Error with {filename}: {e}")

            print()

        print(f"Organization complete: {total_organized} files organized\n")
        return total_organized > 0

    def list_organized_folders(self) -> Dict[str, List[str]]:
        """
        List all sub-folders (cases) in each type folder

        Returns:
            Dictionary {type: [list of case names]}
        """
        organized = {}

        for file_type, base_folder in self.base_folders.items():
            if os.path.exists(base_folder):
                subdirs = [d for d in os.listdir(base_folder)
                           if os.path.isdir(os.path.join(base_folder, d))]
                organized[file_type] = subdirs
            else:
                organized[file_type] = []

        return organized

    def update_folder_paths(self, case_name: str) -> Dict[str, str]:
        """
        Get full paths to folders for a given case

        Args:
            case_name: Case name

        Returns:
            Dictionary {type: full_path}
        """
        paths = {}
        for file_type, base_folder in self.base_folders.items():
            paths[file_type] = os.path.join(base_folder, case_name)
        return paths
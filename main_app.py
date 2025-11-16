#!/usr/bin/env python3
"""
Main application to parse EVTX, MFT, Amcache, LNK, Registry and other logs
and ingest them into Elasticsearch or Timesketch
"""

import os
import sys
import glob
import argparse

# Local imports
import config
from utils.binary_finder import find_binary
from utils.file_organizer import FileOrganizer
from utils.cleanup_utility import CleanupUtility
from parsers.evtx_parser import EVTXParser
from parsers.mft_parser import MFTParser
from parsers.amcache_parser import AmcacheParser
from parsers.lnk_parser import LnkParser
from parsers.registry_parser import RegistryParser
from parsers.log2timeline_parser import Log2TimelineParser
from ingesters.elasticsearch_ingester import ElasticsearchIngester
from ingesters.timesketch_ingester import TimesketchIngester


def main():
    # --------------------------
    # ARGUMENTS
    # --------------------------
    parser = argparse.ArgumentParser(
        description="Parse EVTX/MFT/Amcache/LNK/Registry and other logs to Elasticsearch or Timesketch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage Examples:
  # Automatically organize files from a folder
  python main_app.py --organize --source-dir /mnt/evidence --case-name "Investigation-2024"

  # Organize and parse directly (with log2timeline for other files)
  python main_app.py --organize --source-dir /mnt/evidence --case-name "Case01" --platform elk --all

  # Parse already organized files
  python main_app.py --case-name "Case01" --platform timesketch --all --sketch-name "Timeline"

  # Parse only with log2timeline
  python main_app.py --case-name "Case01" --platform elk --log2timeline

  # Clean Elasticsearch indices
  python main_app.py --platform elk --clean --case-name "Case01"

  # List organized cases
  python main_app.py --list-cases
        """
    )

    # Group: File organization
    organize_group = parser.add_argument_group('File organization')
    organize_group.add_argument(
        "--organize",
        action="store_true",
        help="Automatically organize files by type"
    )
    organize_group.add_argument(
        "--source-dir",
        type=str,
        help="Source directory containing files to organize"
    )
    organize_group.add_argument(
        "--case-name",
        type=str,
        help="Case name (subdirectory to create or use)"
    )
    organize_group.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying them (default: copy)"
    )
    organize_group.add_argument(
        "--list-cases",
        action="store_true",
        help="List all organized cases"
    )

    # Group: Cleanup
    cleanup_group = parser.add_argument_group('Cleanup')
    cleanup_group.add_argument(
        "--clean-case",
        type=str,
        metavar="CASE_NAME",
        help="Clean all files from a specific case"
    )
    cleanup_group.add_argument(
        "--clean-case-indices",
        type=str,
        metavar="CASE_NAME",
        help="Clean all Elasticsearch indices for a case"
    )
    cleanup_group.add_argument(
        "--clean-all-indices",
        action="store_true",
        help="Clean ALL Elasticsearch indices (requires confirmation)"
    )
    cleanup_group.add_argument(
        "--clean-logs",
        action="store_true",
        help="Clean log2timeline/psort log files"
    )
    cleanup_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation mode: show what would be deleted without deleting"
    )

    # Group: Target platform
    platform_group = parser.add_argument_group('Target platform')
    platform_group.add_argument(
        "--platform",
        type=str,
        choices=["elk", "timesketch"],
        help="Target platform: 'elk' (Elasticsearch/Kibana) or 'timesketch'"
    )
    platform_group.add_argument(
        "--clean",
        action="store_true",
        help="[ELK only] Delete all indices and index patterns"
    )

    # Group: File types to parse
    parse_group = parser.add_argument_group('File types to parse')
    parse_group.add_argument(
        "--evtx",
        action="store_true",
        help="Parse all EVTX files"
    )
    parse_group.add_argument(
        "--mft",
        action="store_true",
        help="Parse all MFT files"
    )
    parse_group.add_argument(
        "--amcache",
        action="store_true",
        help="Parse all Amcache.hve files"
    )
    parse_group.add_argument(
        "--lnk",
        action="store_true",
        help="Parse all LNK files"
    )
    parse_group.add_argument(
        "--registry",
        action="store_true",
        help="Parse all Registry Hive files"
    )
    parse_group.add_argument(
        "--log2timeline",
        action="store_true",
        help="Parse other files with log2timeline (Plaso)"
    )
    parse_group.add_argument(
        "--all",
        action="store_true",
        help="Parse all available file types (includes log2timeline)"
    )

    # Group: Output options
    output_group = parser.add_argument_group('Output options')
    output_group.add_argument(
        "--index-name",
        type=str,
        default=None,
        help="[ELK only] Custom index name (otherwise based on case name)"
    )
    output_group.add_argument(
        "--sketch-name",
        type=str,
        default=None,
        help="[Timesketch only] Name of the sketch to create"
    )

    args = parser.parse_args()

    # --------------------------
    # LOG CLEANUP
    # --------------------------
    if args.clean_logs:
        cleanup = CleanupUtility(config)
        cleanup.clean_log2timeline_logs()
        sys.exit(0)

    # --------------------------
    # CASE CLEANUP
    # --------------------------
    if args.clean_case:
        print("=" * 60)
        print(f"CASE CLEANUP: {args.clean_case}")
        print("=" * 60)

        cleanup = CleanupUtility(config)

        # Clean files
        if not cleanup.clean_case_files(args.clean_case, args.dry_run):
            print("\n✗ File cleanup failed")
            sys.exit(1)

        # Clean indices if ELK platform
        if args.platform == "elk":
            if not cleanup.clean_case_indices_elk(
                    args.clean_case,
                    config.ES_HOST,
                    config.KIBANA_HOST,
                    args.dry_run
            ):
                print("\n✗ Index cleanup failed")
                sys.exit(1)

        print("\n✅ Cleanup completed!")
        sys.exit(0)

    # --------------------------
    # CASE INDICES CLEANUP
    # --------------------------
    if args.clean_case_indices:
        print("=" * 60)
        print(f"INDICES CLEANUP: {args.clean_case_indices}")
        print("=" * 60)

        cleanup = CleanupUtility(config)

        if not cleanup.clean_case_indices_elk(
                args.clean_case_indices,
                config.ES_HOST,
                config.KIBANA_HOST,
                args.dry_run
        ):
            print("\n✗ Cleanup failed")
            sys.exit(1)

        print("\n✅ Cleanup completed!")
        sys.exit(0)

    # --------------------------
    # ALL INDICES CLEANUP
    # --------------------------
    if args.clean_all_indices:
        print("=" * 60)
        print("CLEANUP OF ALL INDICES")
        print("=" * 60)

        cleanup = CleanupUtility(config)

        if not cleanup.clean_all_indices_elk(
                config.ES_HOST,
                config.KIBANA_HOST,
                "*",
                args.dry_run
        ):
            print("\n✗ Cleanup failed")
            sys.exit(1)

        print("\n✅ Cleanup completed!")
        sys.exit(0)

    # --------------------------
    # LIST CASES
    # --------------------------
    if args.list_cases:
        organizer = FileOrganizer(
            config.EVTX_FOLDER,
            config.MFT_FOLDER,
            config.AMCACHE_FOLDER,
            config.LNK_FOLDER,
            config.REGISTRY_FOLDER,
            config.OTHER_FOLDER
        )

        organized = organizer.list_organized_folders()

        print("=" * 60)
        print("ORGANIZED CASES")
        print("=" * 60 + "\n")

        all_cases = set()
        for file_type, cases in organized.items():
            all_cases.update(cases)

        if not all_cases:
            print("No cases found. Use --organize to organize files.\n")
        else:
            print(f"{len(all_cases)} case(s) found:\n")
            for case in sorted(all_cases):
                print(f"  • {case}")
                for file_type, cases in organized.items():
                    if case in cases:
                        case_folder = os.path.join(organizer.base_folders[file_type], case)
                        if os.path.exists(case_folder):
                            file_count = len(
                                [f for f in os.listdir(case_folder) if os.path.isfile(os.path.join(case_folder, f))])
                            if file_count > 0:
                                print(f"      - {file_type}: {file_count} file(s)")
                print()

        sys.exit(0)

    # --------------------------
    # FILE ORGANIZATION
    # --------------------------
    if args.organize:
        if not args.source_dir:
            print("✗ --source-dir is required with --organize")
            sys.exit(1)

        if not args.case_name:
            print("✗ --case-name is required with --organize")
            sys.exit(1)

        print("=" * 60)
        print("FILE ORGANIZATION")
        print("=" * 60 + "\n")

        organizer = FileOrganizer(
            config.EVTX_FOLDER,
            config.MFT_FOLDER,
            config.AMCACHE_FOLDER,
            config.LNK_FOLDER,
            config.REGISTRY_FOLDER,
            config.OTHER_FOLDER
        )

        copy_mode = not args.move
        if not organizer.organize_files(args.source_dir, args.case_name, copy_mode):
            print("✗ File organization failed")
            sys.exit(1)

        print("✅ Files organized successfully!\n")

        # If no parsing option is specified, stop here
        if not args.platform:
            print("Use --platform and parsing options to process these files")
            sys.exit(0)

    # --all activates all parsing types
    if args.all:
        args.evtx = True
        args.mft = True
        args.amcache = True
        args.lnk = True
        args.registry = True
        args.log2timeline = True

    # Argument consistency check
    if args.platform == "timesketch" and (
            args.evtx or args.mft or args.amcache or args.lnk or args.registry or args.log2timeline) and not args.sketch_name:
        print("✗ --sketch-name is required for Timesketch")
        sys.exit(1)

    if args.platform == "elk" and args.sketch_name:
        print("⚠ --sketch-name is ignored for ELK platform")

    if args.platform == "timesketch" and args.clean:
        print("⚠ --clean is not supported for Timesketch")
        sys.exit(1)

    # If no platform specified and no organization, error
    if not args.platform and not args.organize and not args.list_cases:
        parser.print_help()
        sys.exit(1)

    # --------------------------
    # CONFIGURATION
    # --------------------------
    platform = args.platform

    # Determine JSON folder based on case
    json_folder = config.get_json_folder(platform, args.case_name)
    os.makedirs(json_folder, exist_ok=True)

    print("=" * 60)
    print(f"LOG PARSER - Platform: {platform.upper()}")
    if args.case_name:
        print(f"Case: {args.case_name}")
    print("=" * 60 + "\n")

    # If a case-name is specified, use case paths
    working_folders = {
        'evtx': config.EVTX_FOLDER,
        'mft': config.MFT_FOLDER,
        'amcache': config.AMCACHE_FOLDER,
        'lnk': config.LNK_FOLDER,
        'registry': config.REGISTRY_FOLDER,
        'other': config.OTHER_FOLDER
    }

    # FIX: Update paths if case_name is present (whether organized or not)
    if args.case_name:
        print(f"Using case files: {args.case_name}\n")
        organizer = FileOrganizer(
            config.EVTX_FOLDER,
            config.MFT_FOLDER,
            config.AMCACHE_FOLDER,
            config.LNK_FOLDER,
            config.REGISTRY_FOLDER,
            config.OTHER_FOLDER
        )
        working_folders = organizer.update_folder_paths(args.case_name)

    # --------------------------
    # BINARY SEARCH
    # --------------------------
    evtx_dump_path = None
    mft_dump_path = None
    amcache_parser_path = None
    lecmd_path = None
    recmd_path = None
    log2timeline_path = None
    psort_path = None

    if args.evtx:
        evtx_dump_path = find_binary(config.EVTX_DUMP_PATHS, "evtx_dump")
        if not evtx_dump_path:
            print("✗ evtx_dump not found. Unable to parse EVTX files.")
            print("  Install evtx_dump or place it in the current directory")
            sys.exit(1)

    if args.mft:
        mft_dump_path = find_binary(config.MFT_DUMP_PATHS, "MFTECmd")
        if not mft_dump_path:
            print("✗ MFTECmd not found. Unable to parse MFT files.")
            print("  Download MFTECmd.exe and place it in the current directory")
            sys.exit(1)

    if args.amcache:
        amcache_parser_path = find_binary(config.AMCACHE_PARSER_PATHS, "AmcacheParser")
        if not amcache_parser_path:
            print("✗ AmcacheParser not found. Unable to parse Amcache files.")
            print("  Download AmcacheParser.exe and place it in the current directory")
            sys.exit(1)

    if args.lnk:
        lecmd_path = find_binary(config.LECMD_PATHS, "LECmd")
        if not lecmd_path:
            print("✗ LECmd not found. Unable to parse LNK files.")
            print("  Download LECmd.exe and place it in the current directory")
            sys.exit(1)

    if args.registry:
        recmd_path = find_binary(config.RECMD_PATHS, "RECmd")
        if not recmd_path:
            print("✗ RECmd not found. Unable to parse Registry files.")
            print("  Download RECmd.exe and place it in the current directory")
            sys.exit(1)

    if args.log2timeline:
        log2timeline_path = find_binary(config.LOG2TIMELINE_PATHS, "log2timeline.py")
        psort_path = find_binary(config.PSORT_PATHS, "psort.py")

        if not log2timeline_path or not psort_path:
            print("✗ log2timeline.py or psort.py not found. Unable to use Plaso.")
            print("  Install Plaso: pip install plaso-tools")
            sys.exit(1)

    # --------------------------
    # CLEAN (ELK only)
    # --------------------------
    if args.clean and platform == "elk":
        base_name = args.index_name or args.case_name or "default"

        ingester = ElasticsearchIngester(config.ES_HOST, config.KIBANA_HOST)
        if not ingester.connect():
            sys.exit(1)

        ingester.clean_indices(base_name)
        sys.exit(0)

    # Extension based on platform
    file_extension = ".jsonl" if platform == "timesketch" else ".json"

    # --------------------------
    # EVTX PARSING
    # --------------------------
    if args.evtx:
        evtx_folder = working_folders['evtx']
        print(f"\nSearching for EVTX files in: {evtx_folder}")

        if not os.path.exists(evtx_folder):
            print(f"⚠ EVTX folder does not exist: {evtx_folder}")
        else:
            evtx_files = glob.glob(os.path.join(evtx_folder, "*.evtx"))
            evtx_files.extend(glob.glob(os.path.join(evtx_folder, "*.EVTX")))

            if not evtx_files:
                print(f"✗ No EVTX files found in {evtx_folder}")
            else:
                print(f"{len(evtx_files)} EVTX file(s) found\n")

                evtx_parser = EVTXParser(evtx_dump_path)
                success_count = 0

                for evtx_path in evtx_files:
                    evtx_basename = os.path.splitext(os.path.basename(evtx_path))[0]
                    output_json = os.path.join(json_folder, f"{evtx_basename}{file_extension}")

                    if evtx_parser.parse_file(evtx_path, output_json, platform):
                        success_count += 1

                print(f"\n✅ EVTX parsing completed: {success_count}/{len(evtx_files)} files processed\n")

    # --------------------------
    # MFT PARSING
    # --------------------------
    if args.mft:
        mft_folder = working_folders['mft']
        print(f"\nSearching for MFT files in: {mft_folder}")

        if not os.path.exists(mft_folder):
            print(f"⚠ MFT folder does not exist: {mft_folder}")
        else:
            mft_files = glob.glob(os.path.join(mft_folder, "*"))
            mft_files = [f for f in mft_files if os.path.isfile(f) and
                         (f.lower().endswith('.mft') or 'mft' in os.path.basename(f).lower() or
                          not os.path.splitext(f)[1])]

            if not mft_files:
                print(f"✗ No MFT files found in {mft_folder}")
            else:
                print(f"{len(mft_files)} MFT file(s) found\n")

                mft_parser = MFTParser(mft_dump_path)
                success_count = 0

                for mft_path in mft_files:
                    mft_basename = os.path.splitext(os.path.basename(mft_path))[0]
                    if not mft_basename:
                        mft_basename = os.path.basename(mft_path)
                    output_json = os.path.join(json_folder, f"mft_{mft_basename}{file_extension}")

                    if mft_parser.parse_file(mft_path, output_json, platform):
                        success_count += 1

                print(f"\n✅ MFT parsing completed: {success_count}/{len(mft_files)} files processed\n")

    # --------------------------
    # AMCACHE PARSING
    # --------------------------
    if args.amcache:
        amcache_folder = working_folders['amcache']
        print(f"\nSearching for Amcache files in: {amcache_folder}")

        if not os.path.exists(amcache_folder):
            print(f"⚠ Amcache folder does not exist: {amcache_folder}")
        else:
            amcache_files = glob.glob(os.path.join(amcache_folder, "*.hve"))
            amcache_files.extend(glob.glob(os.path.join(amcache_folder, "*Amcache*")))

            if not amcache_files:
                print(f"✗ No Amcache files found in {amcache_folder}")
            else:
                print(f"{len(amcache_files)} Amcache file(s) found\n")

                amcache_parser = AmcacheParser(amcache_parser_path)
                success_count = 0

                for amcache_path in amcache_files:
                    amcache_basename = os.path.splitext(os.path.basename(amcache_path))[0]
                    output_json = os.path.join(json_folder, f"amcache_{amcache_basename}{file_extension}")

                    if amcache_parser.parse_file(amcache_path, output_json, platform):
                        success_count += 1

                print(f"\n✅ Amcache parsing completed: {success_count}/{len(amcache_files)} files processed\n")

    # --------------------------
    # LNK PARSING
    # --------------------------
    if args.lnk:
        lnk_folder = working_folders['lnk']
        print(f"\nSearching for LNK files in: {lnk_folder}")

        if not os.path.exists(lnk_folder):
            print(f"⚠ LNK folder does not exist: {lnk_folder}")
        else:
            lnk_files = glob.glob(os.path.join(lnk_folder, "*.lnk"))
            lnk_files.extend(glob.glob(os.path.join(lnk_folder, "*.LNK")))

            if not lnk_files:
                print(f"✗ No LNK files found in {lnk_folder}")
            else:
                print(f"{len(lnk_files)} LNK file(s) found\n")

                lnk_parser = LnkParser(lecmd_path)
                success_count = 0

                for lnk_path in lnk_files:
                    lnk_basename = os.path.splitext(os.path.basename(lnk_path))[0]
                    output_json = os.path.join(json_folder, f"lnk_{lnk_basename}{file_extension}")

                    if lnk_parser.parse_file(lnk_path, output_json, platform):
                        success_count += 1

                print(f"\n✅ LNK parsing completed: {success_count}/{len(lnk_files)} files processed\n")

    # --------------------------
    # REGISTRY PARSING
    # --------------------------
    if args.registry:
        registry_folder = working_folders['registry']
        print(f"\nSearching for Registry files in: {registry_folder}")

        if not os.path.exists(registry_folder):
            print(f"⚠ Registry folder does not exist: {registry_folder}")
        else:
            # Search for common hives
            registry_files = []
            common_hives = ['SYSTEM', 'SOFTWARE', 'SAM', 'SECURITY', 'NTUSER.DAT', 'UsrClass.dat']

            for root, dirs, files in os.walk(registry_folder):
                for file in files:
                    file_upper = file.upper()
                    # Check if it's a known hive or a file without extension
                    if any(hive in file_upper for hive in common_hives) or not os.path.splitext(file)[1]:
                        registry_files.append(os.path.join(root, file))

            if not registry_files:
                print(f"✗ No Registry files found in {registry_folder}")
            else:
                print(f"{len(registry_files)} Registry file(s) found\n")

                registry_parser = RegistryParser(recmd_path)
                success_count = 0

                for registry_path in registry_files:
                    registry_basename = os.path.splitext(os.path.basename(registry_path))[0]
                    if not registry_basename:
                        registry_basename = os.path.basename(registry_path)
                    output_json = os.path.join(json_folder, f"registry_{registry_basename}{file_extension}")

                    if registry_parser.parse_file(registry_path, output_json, platform):
                        success_count += 1

                print(f"\n✅ Registry parsing completed: {success_count}/{len(registry_files)} files processed\n")

    # --------------------------
    # LOG2TIMELINE PARSING
    # --------------------------
    if args.log2timeline:
        other_folder = working_folders['other']
        print(f"\nParsing with log2timeline from folder: {other_folder}")

        if not os.path.exists(other_folder):
            print(f"⚠ 'other' folder does not exist: {other_folder}")
        else:
            # Check if folder contains files
            all_files = []
            for root, dirs, files in os.walk(other_folder):
                all_files.extend([os.path.join(root, f) for f in files if not f.startswith('.')])

            if not all_files:
                print(f"✗ No files found in {other_folder}")
            else:
                print(f"{len(all_files)} file(s) found in 'other'\n")

                l2t_parser = Log2TimelineParser(log2timeline_path, psort_path)

                # Create output filename based on case
                case_name = args.case_name or "default"
                output_json = os.path.join(json_folder, f"plaso_{case_name}{file_extension}")

                if l2t_parser.parse_directory(other_folder, output_json, platform, case_name):
                    print(f"\n✅ log2timeline parsing completed\n")
                else:
                    print(f"\n⚠ Error during log2timeline parsing\n")

    # --------------------------
    # INGESTION
    # --------------------------
    if not (args.evtx or args.mft or args.amcache or args.lnk or args.registry or args.log2timeline):
        print("⚠ No files to parse. Use --evtx, --mft, --amcache, --lnk, --registry, --log2timeline or --all")
        sys.exit(0)

    if platform == "elk":
        # --------------------------
        # ELASTICSEARCH INGESTION
        # --------------------------
        base_name = args.index_name or args.case_name or "default"

        ingester = ElasticsearchIngester(config.ES_HOST, config.KIBANA_HOST)
        if not ingester.connect():
            sys.exit(1)

        total_docs, all_indices = ingester.ingest_json_files(json_folder, base_name)

        if total_docs > 0:
            print(f"✅ Ingestion completed: {total_docs} total documents")
            print(f"{len(all_indices)} index/indices created: {', '.join(all_indices)}\n")

            # Create index pattern
            ingester.create_index_pattern(base_name)
            ingester.set_kibana_timezone()

            # Final summary
            print("\n" + "=" * 60)
            print("COMPLETED!")
            print("=" * 60)
            if args.case_name:
                print(f"\nCase: {args.case_name}")
            print(f"\nElasticsearch indices created:")
            for idx in all_indices:
                print(f"   - {idx}")
            print(f"\nKibana Index Pattern: {base_name}_*")
            print(f"Time field: @timestamp")
            print(f"\nAccess Kibana Discover to view your events")
            print(f"   {config.KIBANA_HOST}/app/discover")
            print("=" * 60 + "\n")
        else:
            print("⚠ No documents were ingested")

    elif platform == "timesketch":
        # --------------------------
        # TIMESKETCH INGESTION
        # --------------------------
        sketch_name = args.sketch_name or args.case_name or "Auto-Import"

        ingester = TimesketchIngester(
            config.TIMESKETCH_HOST,
            config.TIMESKETCH_USERNAME,
            config.TIMESKETCH_PASSWORD
        )

        success_count, sketch_id = ingester.ingest_json_files(json_folder, sketch_name)

        if success_count > 0:
            print(f"\n✅ Timesketch import completed: {success_count} timeline(s) imported")

            # Final summary
            print("\n" + "=" * 60)
            print("COMPLETED!")
            print("=" * 60)
            if args.case_name:
                print(f"\nCase: {args.case_name}")
            print(f"\nSketch created: {sketch_name}")
            if sketch_id > 0:
                print(f"   ID: {sketch_id}")
            print(f"\nTimelines imported: {success_count}")
            print(f"\nAccess Timesketch to view your sketch")
            print(f"   {config.TIMESKETCH_HOST}/sketch/{sketch_id}/")
            print("=" * 60 + "\n")
        else:
            print("\n⚠ No timelines were imported")


if __name__ == "__main__":
    main()

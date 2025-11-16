#!/usr/bin/env python3
"""
Ingester for Timesketch using the Python API
"""

import os
import glob
import sys
from typing import Optional, Tuple

from timesketch_api_client.client import TimesketchApi
from timesketch_import_client import importer


class TimesketchIngester:
    """Class to ingest data into Timesketch via the Python API"""

    def __init__(self, timesketch_host: str, username: str = "admin", password: str = "admin"):
        """
        Initialize the Timesketch ingester

        Args:
            timesketch_host: URL of the Timesketch server (e.g., http://localhost:5000)
            username: Timesketch username
            password: Timesketch password
        """
        self.timesketch_host = timesketch_host
        self.username = username
        self.password = password
        self.client = None

    def connect(self) -> bool:
        """
        Connect to Timesketch

        Returns:
            True if connection succeeds, False otherwise
        """
        print(f"\nConnecting to Timesketch: {self.timesketch_host}")

        try:
            # Create the client directly with connection parameters
            self.client = TimesketchApi(
                host_uri=self.timesketch_host,
                username=self.username,
                password=self.password,
                verify=False  # Disable SSL verification for local dev
            )

            if self.client:
                print(f"  ✓ Connected as: {self.username}")
                return True
            else:
                print(f"  Error: Failed to connect to Timesketch")
                return False

        except Exception as e:
            print(f"  Error: Connection failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_sketch(self, sketch_name: str, description: str = "") -> Optional[object]:
        """
        Create a new sketch in Timesketch

        Args:
            sketch_name: Name of the sketch
            description: Description of the sketch

        Returns:
            Sketch object or None on error
        """
        if not self.client:
            print("  Error: Client not connected")
            return None

        print(f"\nCreating sketch: {sketch_name}")

        try:
            sketch = self.client.create_sketch(
                name=sketch_name,
                description=description or f"Sketch created automatically"
            )

            print(f"  ✓ Sketch created with ID: {sketch.id}")
            return sketch

        except Exception as e:
            print(f"  Error: Failed to create sketch: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_or_create_sketch(self, sketch_name: str, description: str = "") -> Optional[object]:
        """
        Retrieve an existing sketch or create a new one

        Args:
            sketch_name: Name of the sketch
            description: Description of the sketch

        Returns:
            Sketch object or None on error
        """
        if not self.client:
            print("  Error: Client not connected")
            return None

        try:
            # Check if a sketch with this name already exists
            sketches = self.client.list_sketches()
            for sketch in sketches:
                if sketch.name == sketch_name:
                    print(f"\nUsing existing sketch: {sketch_name} (ID: {sketch.id})")
                    return sketch

            # Otherwise, create a new sketch
            return self.create_sketch(sketch_name, description)

        except Exception as e:
            print(f"  Error: Failed to search/create sketch: {e}")
            import traceback
            traceback.print_exc()
            return None

    def import_timeline(self, sketch: object, json_file: str, timeline_name: Optional[str] = None) -> bool:
        """
        Import a JSON file as a timeline into a sketch

        Args:
            sketch: Timesketch sketch object
            json_file: Path to the JSON file
            timeline_name: Name of the timeline (otherwise based on file name)

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(json_file):
            print(f"  Error: File not found: {json_file}")
            return False

        if timeline_name is None:
            timeline_name = os.path.splitext(os.path.basename(json_file))[0]

        print(f"\nImporting timeline: {timeline_name}")
        print(f"    File: {os.path.basename(json_file)}")
        print(f"    Sketch ID: {sketch.id}")

        try:
            with importer.ImportStreamer() as streamer:
                streamer.set_sketch(sketch)
                streamer.set_timeline_name(timeline_name)
                streamer.set_timestamp_description('Event timestamp')

                # Add the JSON file
                streamer.add_file(json_file)

            print(f"  ✓ Timeline imported successfully")
            return True

        except Exception as e:
            print(f"  Error: Failed to import timeline: {e}")
            import traceback
            traceback.print_exc()
            return False

    def ingest_json_files(self, json_folder: str, sketch_name: str) -> Tuple[int, int]:
        """
        Ingest all JSON/JSONL files into a Timesketch sketch

        Args:
            json_folder: Folder containing JSON/JSONL files
            sketch_name: Name of the sketch to create or use

        Returns:
            Tuple (number of timelines imported, sketch_id)
        """
        if not self.connect():
            return 0, -1

        print(f"\nSearching for JSON/JSONL files in: {json_folder}")

        # Search for .jsonl and .json files
        json_files = glob.glob(os.path.join(json_folder, "*.jsonl"))
        json_files.extend(glob.glob(os.path.join(json_folder, "*.json")))

        if not json_files:
            print(f"Error: No JSON/JSONL files found in {json_folder}")
            return 0, -1

        print(f"{len(json_files)} file(s) found")

        # Create or retrieve the sketch
        sketch = self.get_or_create_sketch(
            sketch_name,
            f"Sketch created automatically for {len(json_files)} timeline(s)"
        )

        if sketch is None:
            print("Error: Unable to create/retrieve sketch, aborting")
            return 0, -1

        # Import each file as a timeline
        success_count = 0
        for json_file in json_files:
            if self.import_timeline(sketch, json_file):
                success_count += 1

        return success_count, sketch.id

    def list_sketches(self) -> None:
        """List all available sketches"""
        if not self.client:
            if not self.connect():
                return

        print("\nList of sketches:")
        try:
            sketches = self.client.list_sketches()
            for sketch in sketches:
                print(f"  - {sketch.name} (ID: {sketch.id})")
        except Exception as e:
            print(f"  Error: Unable to list sketches: {e}")

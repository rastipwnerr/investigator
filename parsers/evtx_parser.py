#!/usr/bin/env python3
"""
Parser for EVTX (Windows Event Log) files
"""

import os
import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List
import xml.etree.ElementTree as ET


class EVTXParser:
    """Class to parse EVTX files using evtx_dump"""

    def __init__(self, evtx_dump_path: str):
        """
        Initialize the EVTX parser

        Args:
            evtx_dump_path: Path to the evtx_dump binary
        """
        self.evtx_dump_path = evtx_dump_path
    
    @staticmethod
    def parse_xml_string(xml_string: str) -> Optional[Dict[str, Any]]:
        """Parse an XML string and convert it to a dictionary"""
        try:
            xml_clean = xml_string.replace('\\r\\n', '').replace('\r\n', '')
            root = ET.fromstring(xml_clean)
            
            def element_to_dict(element):
                result = {}
                
                if element.attrib:
                    for key, value in element.attrib.items():
                        clean_key = key.split('}')[-1] if '}' in key else key
                        result[f"attr_{clean_key}"] = value
                
                if element.text and element.text.strip():
                    result['text'] = element.text.strip()
                
                children = list(element)
                if children:
                    child_dict = {}
                    for child in children:
                        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        child_data = element_to_dict(child)
                        
                        if tag in child_dict:
                            if not isinstance(child_dict[tag], list):
                                child_dict[tag] = [child_dict[tag]]
                            child_dict[tag].append(child_data)
                        else:
                            child_dict[tag] = child_data
                    
                    result.update(child_dict)
                
                if len(result) == 1 and 'text' in result:
                    return result['text']
                
                return result if result else None
            
            return element_to_dict(root)
        except:
            return None
    
    @staticmethod
    def is_xml_content(value: str) -> bool:
        """Detect if a string contains XML"""
        if not isinstance(value, str):
            return False
        return (value.strip().startswith('<?xml') or
                (value.strip().startswith('<') and value.strip().endswith('>')))

    def flatten_dict(self, d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
        """Recursively flatten a nested dictionary"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            new_key = new_key.replace('#attributes_', '').replace('#attributes', 'attributes')
            
            if isinstance(v, str) and self.is_xml_content(v):
                parsed_xml = self.parse_xml_string(v)
                if parsed_xml:
                    items.append((f"{new_key}_raw", v))
                    items.extend(self.flatten_dict(parsed_xml, f"{new_key}_parsed", sep=sep).items())
                else:
                    items.append((new_key, v))
            elif isinstance(v, dict):
                items.extend(self.flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                items.append((new_key, json.dumps(v, ensure_ascii=False)))
            else:
                items.append((new_key, v))
        
        return dict(items)
    
    def parse_file(self, evtx_path: str, output_json_path: str, platform: str = "elk") -> bool:
        """
        Parse an EVTX file and save the result as JSON

        Args:
            evtx_path: Path to the EVTX file
            output_json_path: Path to the JSON output file
            platform: Target platform ("elk" or "timesketch")

        Returns:
            True if successful, False otherwise
        """
        print(f"  Parsing: {os.path.basename(evtx_path)}")
        
        cmd = [self.evtx_dump_path, evtx_path, '-o', 'json', '--no-indent']
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            raw_output = result.stdout
        except subprocess.CalledProcessError as e:
            print(f"    evtx_dump error: {e}", file=sys.stderr)
            return False
        except FileNotFoundError:
            print(f"    evtx_dump not found at: {self.evtx_dump_path}", file=sys.stderr)
            return False
        
        events = []
        lines = raw_output.strip().split('\n')
        
        for line in lines:
            if line.startswith('Record ') or not line.strip():
                continue
            
            try:
                event = json.loads(line)
                flat_event = self.flatten_dict(event)
                
                timestamp_field = flat_event.get('Event_System_TimeCreated_attributes_SystemTime')
                
                if platform == "elk":
                    # Format pour Elasticsearch
                    if timestamp_field:
                        flat_event['@timestamp'] = timestamp_field
                        try:
                            dt = datetime.fromisoformat(timestamp_field.replace('Z', '+00:00'))
                            flat_event['timestamp_parsed'] = dt.isoformat()
                        except:
                            pass
                
                elif platform == "timesketch":
                    # Format pour Timesketch
                    if timestamp_field:
                        flat_event['datetime'] = timestamp_field
                        try:
                            dt = datetime.fromisoformat(timestamp_field.replace('Z', '+00:00'))
                            flat_event['timestamp_desc'] = dt.isoformat()
                        except:
                            pass
                    
                    # Dupliquer le Provider Name en message
                    provider_name = flat_event.get('Event_System_Provider_attributes_Name')
                    if provider_name:
                        flat_event['message'] = provider_name
                
                events.append(flat_event)
            except json.JSONDecodeError:
                continue
        
        # Sort by timestamp
        if platform == "elk":
            events.sort(key=lambda x: x.get('@timestamp', ''))
        else:
            events.sort(key=lambda x: x.get('datetime', ''))

        # Save as JSONL
        with open(output_json_path, 'w', encoding='utf-8') as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')

        print(f"    {len(events)} events extracted -> {os.path.basename(output_json_path)}")
        return True

#!/usr/bin/env python3
"""
Script pour parser des EVTX et MFT, les convertir en JSON et les injecter dans Elasticsearch
"""

import os
import json
import subprocess
import glob
from datetime import datetime
import argparse
import requests
from elasticsearch import Elasticsearch, helpers
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import sys
import csv

# --------------------------
# CONFIG
# --------------------------
ES_HOST = "http://localhost:9200"
KIBANA_HOST = "http://localhost:5601"
EVTX_FOLDER = "./evtx"
MFT_FOLDER = "./mft"
JSON_FOLDER = "./jsons"

# Chercher evtx_dump dans différents emplacements possibles
EVTX_DUMP_PATHS = [
    "./evtx_dump",
    "evtx_dump",
    "/usr/local/bin/evtx_dump",
    "/usr/bin/evtx_dump",
]

# Chercher MFTECmd (Eric Zimmerman's tool)
MFT_DUMP_PATHS = [
    "./MFTECmd",
    "MFTECmd",
    "./MFTECmd.exe",
    "MFTECmd.exe",
]

# Trouver le bon chemin pour evtx_dump
EVTX_DUMP_PATH = None
for path in EVTX_DUMP_PATHS:
    if os.path.isfile(path) and os.access(path, os.X_OK):
        EVTX_DUMP_PATH = path
        break
    try:
        result = subprocess.run(['which', 'evtx_dump'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            EVTX_DUMP_PATH = result.stdout.strip()
            break
    except:
        pass

# Trouver le bon chemin pour MFTECmd
MFT_DUMP_PATH = None

# Chercher MFTECmd dans le répertoire courant et PATH
for path in MFT_DUMP_PATHS:
    if os.path.isfile(path) and os.access(path, os.X_OK):
        MFT_DUMP_PATH = path
        print(f"[DEBUG] MFTECmd trouvé à: {MFT_DUMP_PATH}")
        break

if not MFT_DUMP_PATH:
    try:
        result = subprocess.run(['which', 'MFTECmd'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            MFT_DUMP_PATH = result.stdout.strip()
            print(f"[DEBUG] MFTECmd trouvé via which: {MFT_DUMP_PATH}")
    except:
        pass

# --------------------------
# FONCTIONS DE PARSING EVTX
# --------------------------

def parse_xml_string(xml_string: str) -> Optional[Dict[str, Any]]:
    """Parse une chaîne XML et la convertit en dictionnaire"""
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


def is_xml_content(value: str) -> bool:
    """Détecte si une chaîne contient du XML"""
    if not isinstance(value, str):
        return False
    return (value.strip().startswith('<?xml') or 
            (value.strip().startswith('<') and value.strip().endswith('>')))


def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """Aplatit un dictionnaire imbriqué de manière récursive"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        new_key = new_key.replace('#attributes_', '').replace('#attributes', 'attributes')
        
        if isinstance(v, str) and is_xml_content(v):
            parsed_xml = parse_xml_string(v)
            if parsed_xml:
                items.append((f"{new_key}_raw", v))
                items.extend(flatten_dict(parsed_xml, f"{new_key}_parsed", sep=sep).items())
            else:
                items.append((new_key, v))
        elif isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v, ensure_ascii=False)))
        else:
            items.append((new_key, v))
    
    return dict(items)


def parse_evtx_file(evtx_path: str, output_json_path: str) -> bool:
    """Parse un fichier EVTX et sauvegarde le résultat en JSON"""
    print(f"  Parsing: {os.path.basename(evtx_path)}")
    
    cmd = [EVTX_DUMP_PATH, evtx_path, '-o', 'json', '--no-indent']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw_output = result.stdout
    except subprocess.CalledProcessError as e:
        print(f"    ✗ Erreur evtx_dump: {e}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"    ✗ evtx_dump non trouvé à : {EVTX_DUMP_PATH}", file=sys.stderr)
        return False
    
    events = []
    lines = raw_output.strip().split('\n')
    
    for line in lines:
        if line.startswith('Record ') or not line.strip():
            continue
        
        try:
            event = json.loads(line)
            flat_event = flatten_dict(event)
            
            timestamp_field = flat_event.get('Event_System_TimeCreated_attributes_SystemTime')
            if timestamp_field:
                flat_event['@timestamp'] = timestamp_field
                try:
                    dt = datetime.fromisoformat(timestamp_field.replace('Z', '+00:00'))
                    flat_event['timestamp_parsed'] = dt.isoformat()
                except:
                    pass
            
            events.append(flat_event)
        except json.JSONDecodeError:
            continue
    
    events.sort(key=lambda x: x.get('@timestamp', ''))
    
    with open(output_json_path, 'w', encoding='utf-8') as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    
    print(f"    ✓ {len(events)} événements extraits → {os.path.basename(output_json_path)}")
    return True


# --------------------------
# FONCTIONS DE PARSING MFT
# --------------------------

def parse_mft_timestamp(timestamp_str: str) -> Optional[str]:
    """Convertit un timestamp MFT en format ISO"""
    if not timestamp_str or timestamp_str in ['', '1601-01-01 00:00:00', '1601-01-01 00:00:00.0000000']:
        return None
    
    try:
        # Format MFTECmd: "2024-01-15 14:30:45.1234567" (avec microsecondes)
        # Enlever les microsecondes au-delà de 6 chiffres
        if '.' in timestamp_str:
            base, microseconds = timestamp_str.split('.')
            microseconds = microseconds[:6].ljust(6, '0')  # Garder 6 chiffres
            timestamp_str = f"{base}.{microseconds}"
        
        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
        return dt.isoformat() + 'Z'
    except:
        try:
            # Essayer sans microsecondes
            dt = datetime.strptime(timestamp_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            return dt.isoformat() + 'Z'
        except:
            try:
                # Essayer format ISO
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return dt.isoformat() + 'Z'
            except:
                return None


def parse_mft_file(mft_path: str, output_json_path: str) -> bool:
    """Parse un fichier MFT avec MFTECmd et sauvegarde le résultat en JSON"""
    print(f"  Parsing: {os.path.basename(mft_path)}")
    
    if not MFT_DUMP_PATH:
        print(f"    ✗ MFTECmd non trouvé.", file=sys.stderr)
        print(f"    💡 Placez le binaire MFTECmd dans le répertoire courant", file=sys.stderr)
        return False
    
    # Créer un dossier temporaire pour le CSV
    temp_dir = "./temp_mft"
    os.makedirs(temp_dir, exist_ok=True)
    
    # MFTECmd génère un fichier avec un nom spécifique dans le dossier de sortie
    # Format: <timestamp>_MFTECmd_$MFT_Output.csv
    
    # Commande MFTECmd
    cmd = [
        MFT_DUMP_PATH,
        '-f', mft_path,           # Fichier MFT source
        '--csv', temp_dir,        # Dossier de sortie CSV
        '--csvf', 'output.csv'    # Nom du fichier CSV
    ]
    
    print(f"    🔧 Commande: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
        if result.stdout:
            print(f"    ℹ Output: {result.stdout[:200]}")
    except subprocess.CalledProcessError as e:
        print(f"    ✗ Erreur MFTECmd (code {e.returncode})", file=sys.stderr)
        print(f"       stdout: {e.stdout[:300]}", file=sys.stderr)
        print(f"       stderr: {e.stderr[:300]}", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"    ✗ Timeout lors du parsing MFT (>300s)", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"    ✗ MFTECmd non exécutable: {MFT_DUMP_PATH}", file=sys.stderr)
        return False
    
    # Trouver le fichier CSV généré
    csv_files = glob.glob(os.path.join(temp_dir, "*.csv"))
    if not csv_files:
        print(f"    ✗ Aucun fichier CSV généré dans {temp_dir}", file=sys.stderr)
        return False
    
    temp_csv = csv_files[0]  # Prendre le premier (devrait être le seul)
    print(f"    📄 CSV généré: {os.path.basename(temp_csv)}")
    
    # Lire le CSV et convertir en JSON
    entries = []
    try:
        with open(temp_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row_num, row in enumerate(reader, 1):
                try:
                    # Nettoyer et structurer les données
                    entry = {}
                    
                    # MFTECmd génère beaucoup de colonnes, on les garde toutes
                    for key, value in row.items():
                        if not key:  # Ignorer les clés vides
                            continue
                        
                        if value and str(value).strip():
                            # Nettoyer le nom de la clé
                            clean_key = str(key).strip().replace(' ', '_').replace('/', '_').replace('\\', '_').replace('(', '').replace(')', '').lower()
                            entry[clean_key] = str(value).strip()
                    
                    if not entry:  # Ignorer les lignes vides
                        continue
                    
                    # Champs de timestamp communs dans MFTECmd
                    timestamp_fields = [
                        'created0x10', 'modified0x10', 'accessed0x10', 'recordmodified0x10',
                        'created0x30', 'modified0x30', 'accessed0x30', 'recordmodified0x30',
                        'created', 'modified', 'accessed', 'mftrecordnumber'
                    ]
                    
                    timestamps = []
                    for ts_field in timestamp_fields:
                        if ts_field in entry:
                            parsed_ts = parse_mft_timestamp(entry[ts_field])
                            if parsed_ts:
                                timestamps.append(parsed_ts)
                                entry[f'{ts_field}_iso'] = parsed_ts
                    
                    # Utiliser le timestamp le plus récent comme @timestamp
                    if timestamps:
                        entry['@timestamp'] = max(timestamps)
                    else:
                        # Utiliser la date actuelle si aucun timestamp valide
                        entry['@timestamp'] = datetime.now().isoformat() + 'Z'
                    
                    # Ajouter des métadonnées
                    entry['source_file'] = os.path.basename(mft_path)
                    entry['log_type'] = 'mft'
                    entry['parser'] = 'mftecmd'
                    
                    entries.append(entry)
                    
                except Exception as e:
                    print(f"    ⚠ Erreur ligne {row_num}: {e}")
                    continue
        
    except Exception as e:
        print(f"    ✗ Erreur lecture CSV: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Nettoyer le dossier temporaire
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass
    
    if not entries:
        print(f"    ⚠ Aucune entrée MFT extraite", file=sys.stderr)
        return False
    
    # Trier par timestamp
    entries.sort(key=lambda x: x.get('@timestamp', ''))
    
    # Sauvegarder en JSONL
    with open(output_json_path, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    print(f"    ✓ {len(entries)} entrées MFT extraites → {os.path.basename(output_json_path)}")
    return True


# --------------------------
# ARGUMENTS
# --------------------------
parser = argparse.ArgumentParser(description="Parser EVTX/MFT et push vers Elasticsearch")
parser.add_argument("--clean", action="store_true", 
                    help="Supprime tous les indices et index patterns")
parser.add_argument("--evtx", action="store_true", 
                    help="Parse tous les fichiers EVTX du dossier evtx/")
parser.add_argument("--mft", action="store_true",
                    help="Parse tous les fichiers MFT du dossier mft/")
parser.add_argument("--all", action="store_true",
                    help="Parse tous les fichiers EVTX et MFT")
parser.add_argument("--index-name", type=str, default=None,
                    help="Nom personnalisé pour l'index (sinon basé sur le dossier)")
args = parser.parse_args()

# --all active les deux types de parsing
if args.all:
    args.evtx = True
    args.mft = True

# --------------------------
# PARSING EVTX SI DEMANDÉ
# --------------------------
if args.evtx:
    print(f"\n🔍 Recherche des fichiers EVTX dans: {EVTX_FOLDER}")
    
    os.makedirs(JSON_FOLDER, exist_ok=True)
    
    evtx_files = glob.glob(os.path.join(EVTX_FOLDER, "*.evtx"))
    evtx_files.extend(glob.glob(os.path.join(EVTX_FOLDER, "*.EVTX")))
    
    if not evtx_files:
        print(f"✗ Aucun fichier EVTX trouvé dans {EVTX_FOLDER}")
    else:
        print(f"📂 {len(evtx_files)} fichier(s) EVTX trouvé(s)\n")
        
        success_count = 0
        for evtx_path in evtx_files:
            evtx_basename = os.path.splitext(os.path.basename(evtx_path))[0]
            output_json = os.path.join(JSON_FOLDER, f"{evtx_basename}.json")
            
            if parse_evtx_file(evtx_path, output_json):
                success_count += 1
        
        print(f"\n✅ Parsing EVTX terminé: {success_count}/{len(evtx_files)} fichiers traités\n")

# --------------------------
# PARSING MFT SI DEMANDÉ
# --------------------------
if args.mft:
    print(f"\n🔍 Recherche des fichiers MFT dans: {MFT_FOLDER}")
    
    os.makedirs(JSON_FOLDER, exist_ok=True)
    
    # Chercher les fichiers MFT (extensions courantes)
    mft_files = glob.glob(os.path.join(MFT_FOLDER, "*"))
    mft_files = [f for f in mft_files if os.path.isfile(f) and 
                 (f.lower().endswith('.mft') or 'mft' in os.path.basename(f).lower() or
                  not os.path.splitext(f)[1])]  # Fichiers sans extension
    
    if not mft_files:
        print(f"✗ Aucun fichier MFT trouvé dans {MFT_FOLDER}")
        print(f"  💡 Les fichiers MFT peuvent avoir l'extension .mft ou aucune extension")
    else:
        print(f"📂 {len(mft_files)} fichier(s) MFT trouvé(s)\n")
        
        success_count = 0
        for mft_path in mft_files:
            mft_basename = os.path.splitext(os.path.basename(mft_path))[0]
            if not mft_basename:
                mft_basename = os.path.basename(mft_path)
            output_json = os.path.join(JSON_FOLDER, f"mft_{mft_basename}.json")
            
            if parse_mft_file(mft_path, output_json):
                success_count += 1
        
        print(f"\n✅ Parsing MFT terminé: {success_count}/{len(mft_files)} fichiers traités\n")

# --------------------------
# INITIALISATION ELASTICSEARCH
# --------------------------
print("🔌 Connexion à Elasticsearch...")
es = Elasticsearch(
    ES_HOST,
    verify_certs=False,
    ssl_show_warn=False,
    basic_auth=None
)

try:
    if es.ping():
        print("✓ Connexion Elasticsearch OK\n")
    else:
        raise ValueError("Elasticsearch non joignable")
except Exception as e:
    print(f"✗ Erreur de connexion : {e}")
    exit(1)

# Nom de base pour indices et patterns
if args.index_name:
    base_name = args.index_name.lower()
else:
    base_name = os.path.basename(os.path.abspath(JSON_FOLDER)).lower()

# --------------------------
# CLEAN SI DEMANDÉ
# --------------------------
if args.clean:
    print(f"🧹 Nettoyage des indices et patterns contenant: {base_name}")
    
    try:
        indices_resp = es.cat.indices(index=f"*{base_name}*", format="json")
        indices = [idx["index"] for idx in indices_resp]
        for idx in indices:
            es.indices.delete(index=idx)
            print(f"  ✓ Indice supprimé : {idx}")
    except:
        print("  ℹ Aucun indice à supprimer")
    
    try:
        res = requests.get(
            f"{KIBANA_HOST}/api/saved_objects/_find?type=index-pattern&search={base_name}&search_fields=title",
            headers={"kbn-xsrf": "true"}
        )
        if res.status_code == 200:
            objects = res.json().get("saved_objects", [])
            for obj in objects:
                obj_id = obj["id"]
                requests.delete(
                    f"{KIBANA_HOST}/api/saved_objects/index-pattern/{obj_id}",
                    headers={"kbn-xsrf": "true"}
                )
                print(f"  ✓ Index Pattern supprimé : {obj['attributes']['title']}")
    except:
        pass
    
    print("\n✅ Nettoyage terminé\n")
    exit(0)

# --------------------------
# INGEST TOUS LES JSON
# --------------------------
print(f"📂 Recherche des fichiers JSON dans: {JSON_FOLDER}")

json_files = glob.glob(os.path.join(JSON_FOLDER, "*.json"))

if not json_files:
    print(f"✗ Aucun fichier JSON trouvé dans {JSON_FOLDER}")
    exit(1)

print(f"📄 {len(json_files)} fichier(s) JSON trouvé(s)\n")

total_docs = 0
all_indices = []

for json_file in json_files:
    json_basename = os.path.splitext(os.path.basename(json_file))[0]
    index_name = f"{base_name}_{json_basename}".lower()
    
    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name)
        print(f"📊 Index créé : {index_name}")
        all_indices.append(index_name)
    else:
        print(f"ℹ Index existe déjà : {index_name}")
        all_indices.append(index_name)
    
    print(f"📤 Ingestion: {os.path.basename(json_file)} → {index_name}")
    
    actions = []
    with open(json_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                actions.append({"_index": index_name, "_source": data})
            except json.JSONDecodeError as e:
                print(f"  ⚠ Erreur JSON ligne {line_num}: {e}")
                continue
    
    if actions:
        try:
            helpers.bulk(es, actions)
            print(f"  ✓ {len(actions)} documents injectés\n")
            total_docs += len(actions)
        except Exception as e:
            print(f"  ✗ Erreur bulk: {e}\n")
    else:
        print(f"  ⚠ Aucun document valide\n")

print(f"✅ Ingestion terminée : {total_docs} documents au total")
print(f"📊 {len(all_indices)} index créé(s) : {', '.join(all_indices)}\n")

# --------------------------
# CREATION INDEX PATTERN KIBANA
# --------------------------
print("🔧 Création de l'Index Pattern dans Kibana...")

pattern_payload = {
    "attributes": {
        "title": f"{base_name}_*",
        "timeFieldName": "@timestamp"
    }
}

response = requests.post(
    f"{KIBANA_HOST}/api/saved_objects/index-pattern",
    headers={"kbn-xsrf": "true", "Content-Type": "application/json"},
    json=pattern_payload
)

if response.status_code in [200, 201]:
    print(f"✓ Index Pattern créé : {base_name}_* (avec @timestamp)")
elif response.status_code == 409:
    print(f"ℹ Index Pattern '{base_name}_*' existe déjà")
else:
    print(f"⚠ Erreur création Index Pattern : {response.status_code}")

print("\n" + "="*60)
print("🎉 TERMINÉ !")
print("="*60)
print(f"\n📊 Index Elasticsearch créés :")
for idx in all_indices:
    print(f"   - {idx}")
print(f"\n🔍 Index Pattern Kibana : {base_name}_*")
print(f"🕐 Time field : @timestamp")
print(f"\n💡 Accédez à Kibana Discover pour visualiser vos événements")
print(f"   {KIBANA_HOST}/app/discover")
print("="*60 + "\n")

payload = {"changes":{"dateFormat:tz":"UTC"}}
HEADERS = {
    "kbn-xsrf": "true",
    "Content-Type": "application/json"
}
r = requests.post(f"{KIBANA_HOST}/api/kibana/settings", headers=HEADERS, json=payload)

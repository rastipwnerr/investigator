#!/usr/bin/env python3
"""
Ingester pour Elasticsearch et Kibana
"""

import os
import json
import glob
import requests
import re
from elasticsearch import Elasticsearch, helpers
from typing import List


class ElasticsearchIngester:
    """Classe pour ingérer les données dans Elasticsearch"""

    def __init__(self, es_host: str, kibana_host: str):
        """
        Initialise l'ingester Elasticsearch

        Args:
            es_host: URL du serveur Elasticsearch
            kibana_host: URL du serveur Kibana
        """
        self.es_host = es_host
        self.kibana_host = kibana_host
        self.es = None

    @staticmethod
    def sanitize_index_name(name: str) -> str:
        """
        Nettoie un nom d'index pour Elasticsearch

        Elasticsearch n'autorise pas ces caractères: espace, ", *, \, /, <, >, ?, |, #, :
        Le nom doit aussi être en minuscules

        Args:
            name: Nom d'index brut

        Returns:
            Nom d'index nettoyé
        """
        # Remplacer les caractères interdits par des underscores
        forbidden_chars = r'[\s"*\\/<>?|#:%]'
        sanitized = re.sub(forbidden_chars, '_', name)

        # Supprimer les underscores multiples
        sanitized = re.sub(r'_+', '_', sanitized)

        # Supprimer les underscores au début et à la fin
        sanitized = sanitized.strip('_')

        # Convertir en minuscules
        sanitized = sanitized.lower()

        # S'assurer que le nom n'est pas vide
        if not sanitized:
            sanitized = "index"

        # S'assurer que le nom ne commence pas par -, _, ou +
        if sanitized[0] in ['-', '_', '+']:
            sanitized = 'idx' + sanitized

        # Limiter la longueur à 255 caractères
        if len(sanitized) > 255:
            sanitized = sanitized[:255]

        return sanitized

    def connect(self) -> bool:
        """
        Connexion à Elasticsearch

        Returns:
            True si succès, False sinon
        """
        print("🔌 Connexion à Elasticsearch...")
        self.es = Elasticsearch(
            self.es_host,
            verify_certs=False,
            ssl_show_warn=False,
            basic_auth=None
        )

        try:
            if self.es.ping():
                print("✓ Connexion Elasticsearch OK\n")
                return True
            else:
                raise ValueError("Elasticsearch non joignable")
        except Exception as e:
            print(f"✗ Erreur de connexion : {e}")
            return False

    def clean_indices(self, base_name: str) -> None:
        """
        Supprime tous les indices et patterns contenant base_name

        Args:
            base_name: Nom de base pour filtrer les indices
        """
        # Nettoyer le nom de base
        base_name = self.sanitize_index_name(base_name)

        print(f"🧹 Nettoyage des indices et patterns contenant: {base_name}")

        try:
            indices_resp = self.es.cat.indices(index=f"*{base_name}*", format="json")
            indices = [idx["index"] for idx in indices_resp]
            for idx in indices:
                self.es.indices.delete(index=idx)
                print(f"  ✓ Indice supprimé : {idx}")
        except:
            print("  ℹ Aucun indice à supprimer")

        try:
            res = requests.get(
                f"{self.kibana_host}/api/saved_objects/_find?type=index-pattern&search={base_name}&search_fields=title",
                headers={"kbn-xsrf": "true"}
            )
            if res.status_code == 200:
                objects = res.json().get("saved_objects", [])
                for obj in objects:
                    obj_id = obj["id"]
                    requests.delete(
                        f"{self.kibana_host}/api/saved_objects/index-pattern/{obj_id}",
                        headers={"kbn-xsrf": "true"}
                    )
                    print(f"  ✓ Index Pattern supprimé : {obj['attributes']['title']}")
        except:
            pass

        print("\n✅ Nettoyage terminé\n")

    def ingest_json_files(self, json_folder: str, base_name: str) -> tuple[int, List[str]]:
        """
        Ingère tous les fichiers JSON dans Elasticsearch

        Args:
            json_folder: Dossier contenant les fichiers JSON
            base_name: Nom de base pour les indices

        Returns:
            Tuple (nombre total de documents, liste des indices créés)
        """
        print(f"📂 Recherche des fichiers JSON dans: {json_folder}")

        json_files = glob.glob(os.path.join(json_folder, "*.json"))

        if not json_files:
            print(f"✗ Aucun fichier JSON trouvé dans {json_folder}")
            return 0, []

        print(f"📄 {len(json_files)} fichier(s) JSON trouvé(s)\n")

        # Nettoyer le nom de base
        base_name = self.sanitize_index_name(base_name)

        total_docs = 0
        all_indices = []

        for json_file in json_files:
            json_basename = os.path.splitext(os.path.basename(json_file))[0]

            # Nettoyer le nom du fichier aussi
            json_basename_clean = self.sanitize_index_name(json_basename)

            # Créer le nom d'index
            index_name = f"{base_name}_{json_basename_clean}"

            # Double vérification du nom d'index
            index_name = self.sanitize_index_name(index_name)

            if not self.es.indices.exists(index=index_name):
                self.es.indices.create(index=index_name)
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
                    helpers.bulk(self.es, actions)
                    print(f"  ✓ {len(actions)} documents injectés\n")
                    total_docs += len(actions)
                except Exception as e:
                    print(f"  ✗ Erreur bulk: {e}\n")
            else:
                print(f"  ⚠ Aucun document valide\n")

        return total_docs, all_indices

    def create_index_pattern(self, base_name: str) -> bool:
        """
        Crée un Index Pattern dans Kibana

        Args:
            base_name: Nom de base pour le pattern

        Returns:
            True si succès, False sinon
        """
        # Nettoyer le nom de base
        base_name = self.sanitize_index_name(base_name)

        print("🔧 Création de l'Index Pattern dans Kibana...")

        pattern_payload = {
            "attributes": {
                "title": f"{base_name}_*",
                "timeFieldName": "@timestamp"
            }
        }

        response = requests.post(
            f"{self.kibana_host}/api/saved_objects/index-pattern",
            headers={"kbn-xsrf": "true", "Content-Type": "application/json"},
            json=pattern_payload
        )

        if response.status_code in [200, 201]:
            print(f"✓ Index Pattern créé : {base_name}_* (avec @timestamp)")
            return True
        elif response.status_code == 409:
            print(f"ℹ Index Pattern '{base_name}_*' existe déjà")
            return True
        else:
            print(f"⚠ Erreur création Index Pattern : {response.status_code}")
            return False

    def set_kibana_timezone(self) -> None:
        """Configure le timezone de Kibana sur UTC"""
        payload = {"changes": {"dateFormat:tz": "UTC"}}
        headers = {
            "kbn-xsrf": "true",
            "Content-Type": "application/json"
        }
        requests.post(f"{self.kibana_host}/api/kibana/settings", headers=headers, json=payload)
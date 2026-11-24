"""Ontology drafts, publish, clone, and pull."""
from __future__ import annotations

import unittest

from renglo.blueprint.ontology_format import ontology_skeleton
from renglo_api.client.ontologies import (
    clone_ontology,
    commit_ontology,
    deprecate_ontology,
    get_ontology,
    list_ontologies,
    list_ontology_versions,
    new_ontology,
    publish_ontology,
    pull_ontology,
)


class _Ontologies:
    def __init__(self):
        self.docs = {}
        self.remote = {}

    def list_ontology_versions(self, handle, name):
        items = [
            document
            for (stored_handle, stored_name, _version), document in self.docs.items()
            if stored_handle == handle and stored_name == name
        ]
        return {"success": True, "items": items, "status": 200}

    def list_ontology_names(self, handle):
        names = sorted({
            name
            for (stored_handle, name, _version) in self.docs
            if stored_handle == handle
        })
        return {"success": True, "items": names, "status": 200}

    def get_ontology(self, handle, name, version):
        document = self.docs.get((handle, name, version))
        if document is None:
            return {"success": False, "message": "Document not found"}
        return document

    def put_ontology_document(self, handle, name, document):
        stored = dict(document)
        stored["handle"] = handle
        stored["name"] = name
        stored["irn"] = f"irn:ontology:{handle}:{name}"
        self.docs[(handle, name, stored["version"])] = stored
        return {"success": True, "document": stored, "status": 200}

    def delete_ontology(self, handle, name, version):
        self.docs.pop((handle, name, version), None)
        return {"success": True, "status": 200}

    def fetch_ontology(self, uri):
        document = self.remote.get(uri)
        if document is None:
            return {"success": False, "message": "Ontology URI could not be read", "status": 400}
        return document


def _type(name, semantic, parent=None, abstract=False):
    item = {
        "type": name,
        "semantic": semantic,
        "description": name,
        "examples": [],
    }
    if parent:
        item["parent_type"] = parent
    if abstract:
        item["abstract"] = True
    return item


def _food(extra_type=False):
    types = [
        _type("Food", "food.item", abstract=True),
        _type("Fruit", "food.fruit", parent="Food"),
    ]
    domains = [{
        "id": "sweet",
        "label": "Sweet",
        "semantic": "food.domain.sweet",
        "root_type": "Food",
        "types": ["Fruit"],
    }]
    if extra_type:
        types.append(_type("Vegetable", "food.vegetable", parent="Food"))
        domains.append({
            "id": "savory",
            "label": "Savory",
            "semantic": "food.domain.savory",
            "root_type": "Food",
            "types": ["Vegetable"],
        })
    return {"description": "Edible things.", "node_types": types, "functional_domains": domains}


class OntologyContractTests(unittest.TestCase):
    def setUp(self):
        self.blueprints = _Ontologies()

    def test_a_new_ontology_is_a_draft_and_an_empty_body_still_creates_one(self):
        created, status = new_ontology(self.blueprints, "portfolio", "food.groups", {})
        self.assertEqual(status, 201)
        self.assertEqual(created["name"], "food.groups")
        self.assertEqual(created["description"], "")
        self.assertEqual(created["dictionaries"], [])
        self.assertEqual(created["node_types"], [])
        self.assertEqual(created["functional_domains"], [])
        self.assertEqual(created["relationship_types"], [])
        self.assertEqual(created["rules"], [])
        self.assertEqual(created["edge_taxonomies"], [])
        self.assertEqual(created["classification_policy"], {"description": "", "derivation": ""})
        self.assertEqual(created["version"], "x.y.z")
        self.assertEqual(created["status"], "draft")
        self.assertEqual(created["origin"], "")
        self.assertEqual(self.blueprints.docs[("portfolio", "food.groups", "x.y.z")]["irn"], "irn:ontology:portfolio:food.groups")
        again, again_status = new_ontology(self.blueprints, "portfolio", "food.groups", {})
        self.assertEqual(again_status, 409)
        self.assertEqual(again["error"]["type"], "OntologyExists")
        self.assertIn("commitOntology", again["message"])

    def test_commit_updates_the_draft_and_publish_bumps_from_the_change(self):
        new_ontology(self.blueprints, "portfolio", "food.groups", {})
        committed, commit_status = commit_ontology(self.blueprints, "portfolio", "food.groups", _food())
        self.assertEqual(commit_status, 200)
        self.assertEqual(committed["version"], "x.y.z")
        self.assertEqual(committed["node_types"][1]["type"], "Fruit")

        published, publish_status = publish_ontology(self.blueprints, "portfolio", "food.groups")
        self.assertEqual(publish_status, 200)
        self.assertEqual(published["version"], "1.0.0")
        self.assertEqual(published["status"], "final")
        current, _status = get_ontology(self.blueprints, "portfolio", "food.groups")
        self.assertEqual(current["version"], "x.y.z")
        self.assertEqual(current["status"], "draft")

        commit_ontology(self.blueprints, "portfolio", "food.groups", {"description": "A menu ontology."})
        patched, _status = publish_ontology(self.blueprints, "portfolio", "food.groups")
        self.assertEqual(patched["version"], "1.0.1")

        commit_ontology(self.blueprints, "portfolio", "food.groups", _food(extra_type=True))
        added, _status = publish_ontology(self.blueprints, "portfolio", "food.groups")
        self.assertEqual(added["version"], "1.1.0")

        removed = _food()
        commit_ontology(self.blueprints, "portfolio", "food.groups", removed)
        major, _status = publish_ontology(self.blueprints, "portfolio", "food.groups")
        self.assertEqual(major["version"], "2.0.0")

        listed, _status = list_ontology_versions(self.blueprints, "portfolio", "food.groups")
        versions = [item["version"] for item in listed["items"]]
        self.assertEqual(versions, ["1.0.0", "1.0.1", "1.1.0", "2.0.0", "x.y.z"])
        names, _status = list_ontologies(self.blueprints, "portfolio")
        self.assertEqual(names, {"items": [{"name": "food.groups"}]})

    def test_a_type_with_no_domain_is_refused(self):
        new_ontology(self.blueprints, "portfolio", "food.groups", {})
        broken = _food()
        broken["functional_domains"] = []
        refused, status = commit_ontology(self.blueprints, "portfolio", "food.groups", broken)
        self.assertEqual(status, 400)
        self.assertEqual(refused["error"]["type"], "InvalidOntology")
        self.assertIn("functional domain", refused["message"])

    def test_a_cloned_ontology_rejects_commit_and_pulls_its_origin(self):
        remote = ontology_skeleton("food.groups")
        remote["version"] = "1.0.0"
        remote["status"] = "final"
        remote["description"] = "Edible things."
        self.blueprints.remote["https://example.test/_ontology/public/food.groups/1.0.0"] = remote
        latest = ontology_skeleton("food.groups")
        latest.update(_food())
        latest["version"] = "1.1.0"
        latest["status"] = "final"
        self.blueprints.remote["https://example.test/_ontology/public/food.groups/last"] = latest

        cloned, status = clone_ontology(
            self.blueprints, "portfolio", "https://example.test/_ontology/public/food.groups/1.0.0"
        )
        self.assertEqual(status, 201)
        self.assertEqual(cloned["origin"], "https://example.test/_ontology/public/food.groups/1.0.0")
        self.assertEqual(cloned["version"], "1.0.0")
        refused, refused_status = commit_ontology(self.blueprints, "portfolio", "food.groups", {"description": "local"})
        self.assertEqual(refused_status, 400)
        self.assertEqual(refused["error"]["type"], "ClonedOntology")
        self.assertIn("pullOntology", refused["message"])

        pulled, pull_status = pull_ontology(self.blueprints, "portfolio", "food.groups")
        self.assertEqual(pull_status, 200)
        self.assertEqual(pulled["version"], "1.1.0")
        self.assertEqual(pulled["node_types"][1]["type"], "Fruit")
        self.assertNotIn(("portfolio", "food.groups", "1.0.0"), self.blueprints.docs)

    def test_deprecate_marks_one_version(self):
        new_ontology(self.blueprints, "portfolio", "food.groups", {})
        publish_ontology(self.blueprints, "portfolio", "food.groups")
        deprecated, status = deprecate_ontology(self.blueprints, "portfolio", "food.groups", "1.0.0")
        self.assertEqual(status, 200)
        self.assertEqual(deprecated["status"], "deprecated")
        self.assertEqual(deprecated["version"], "1.0.0")
        draft, _status = get_ontology(self.blueprints, "portfolio", "food.groups", "x.y.z")
        self.assertEqual(draft["status"], "draft")

"""Dictionary drafts, publish, clone, and pull."""
from __future__ import annotations

import unittest

from renglo.blueprint.dictionary_format import dictionary_skeleton
from renglo_api.client.dictionaries import (
    clone_dictionary,
    commit_dictionary,
    deprecate_dictionary,
    get_dictionary,
    list_dictionaries,
    list_dictionary_versions,
    new_dictionary,
    publish_dictionary,
    pull_dictionary,
)


class _Dictionaries:
    def __init__(self):
        self.docs = {}
        self.remote = {}

    def list_dictionary_versions(self, handle, name):
        items = [
            document
            for (stored_handle, stored_name, _version), document in self.docs.items()
            if stored_handle == handle and stored_name == name
        ]
        return {"success": True, "items": items, "status": 200}

    def list_dictionary_names(self, handle):
        names = sorted({
            name
            for (stored_handle, name, _version) in self.docs
            if stored_handle == handle
        })
        return {"success": True, "items": names, "status": 200}

    def get_dictionary(self, handle, name, version):
        document = self.docs.get((handle, name, version))
        if document is None:
            return {"success": False, "message": "Document not found"}
        return document

    def put_dictionary_document(self, handle, name, document):
        stored = dict(document)
        stored["handle"] = handle
        stored["name"] = name
        stored["irn"] = f"irn:dictionary:{handle}:{name}"
        self.docs[(handle, name, stored["version"])] = stored
        return {"success": True, "document": stored, "status": 200}

    def delete_dictionary(self, handle, name, version):
        self.docs.pop((handle, name, version), None)
        return {"success": True, "status": 200}

    def fetch_dictionary(self, uri):
        document = self.remote.get(uri)
        if document is None:
            return {"success": False, "message": "Dictionary URI could not be read", "status": 400}
        return document


def _term(dictionary, key, label, inverse=None, mappings=None):
    item = {
        "label": label,
        "description": label,
        "external_mappings": list(mappings or []),
        "status": "active",
    }
    if inverse:
        item["inverse"] = f"{dictionary}.{inverse}"
    return item


def _food(extra=False):
    terms = {
        "food": _term("food", "food", "Food"),
        "contains": _term("food", "contains", "Contains", inverse="belongs_to"),
        "belongs_to": _term("food", "belongs_to", "Belongs To", inverse="contains"),
    }
    if extra:
        terms["fruit"] = _term("food", "fruit", "Fruit", mappings=["apple"])
    return {"description": "Edible things.", "terms": terms}


class DictionaryContractTests(unittest.TestCase):
    def setUp(self):
        self.blueprints = _Dictionaries()

    def test_a_new_dictionary_is_a_draft_and_an_empty_body_still_creates_one(self):
        created, status = new_dictionary(self.blueprints, "portfolio", "food", {})
        self.assertEqual(status, 201)
        self.assertEqual(created["name"], "food")
        self.assertEqual(created["id"], "food.x.y.z")
        self.assertEqual(created["description"], "")
        self.assertEqual(created["terms"], {})
        self.assertEqual(created["version"], "x.y.z")
        self.assertEqual(created["status"], "draft")
        self.assertEqual(created["origin"], "")
        self.assertEqual(self.blueprints.docs[("portfolio", "food", "x.y.z")]["irn"], "irn:dictionary:portfolio:food")
        again, again_status = new_dictionary(self.blueprints, "portfolio", "food", {})
        self.assertEqual(again_status, 409)
        self.assertEqual(again["error"]["type"], "DictionaryExists")
        self.assertIn("commitDictionary", again["message"])

    def test_commit_updates_the_draft_and_publish_bumps_from_the_change(self):
        new_dictionary(self.blueprints, "portfolio", "food", {})
        committed, commit_status = commit_dictionary(self.blueprints, "portfolio", "food", _food())
        self.assertEqual(commit_status, 200)
        self.assertEqual(committed["version"], "x.y.z")
        self.assertEqual(committed["id"], "food.x.y.z")
        self.assertEqual(committed["terms"]["food"]["id"], "food.food")

        published, publish_status = publish_dictionary(self.blueprints, "portfolio", "food")
        self.assertEqual(publish_status, 200)
        self.assertEqual(published["version"], "1.0.0")
        self.assertEqual(published["id"], "food.1.0.0")
        self.assertEqual(published["status"], "final")
        current, _status = get_dictionary(self.blueprints, "portfolio", "food")
        self.assertEqual(current["version"], "x.y.z")
        self.assertEqual(current["status"], "draft")

        commit_dictionary(self.blueprints, "portfolio", "food", {"description": "A menu dictionary."})
        patched, _status = publish_dictionary(self.blueprints, "portfolio", "food")
        self.assertEqual(patched["version"], "1.0.1")
        self.assertEqual(patched["id"], "food.1.0.1")

        commit_dictionary(self.blueprints, "portfolio", "food", _food(extra=True))
        added, _status = publish_dictionary(self.blueprints, "portfolio", "food")
        self.assertEqual(added["version"], "1.1.0")

        commit_dictionary(self.blueprints, "portfolio", "food", _food())
        major, _status = publish_dictionary(self.blueprints, "portfolio", "food")
        self.assertEqual(major["version"], "2.0.0")

        listed, _status = list_dictionary_versions(self.blueprints, "portfolio", "food")
        versions = [item["version"] for item in listed["items"]]
        self.assertEqual(versions, ["1.0.0", "1.0.1", "1.1.0", "2.0.0", "x.y.z"])
        names, _status = list_dictionaries(self.blueprints, "portfolio")
        self.assertEqual(names, {"items": [{"name": "food"}]})

    def test_a_one_sided_inverse_is_refused(self):
        new_dictionary(self.blueprints, "portfolio", "food", {})
        broken = _food()
        del broken["terms"]["contains"]["inverse"]
        refused, status = commit_dictionary(self.blueprints, "portfolio", "food", broken)
        self.assertEqual(status, 400)
        self.assertEqual(refused["error"]["type"], "InvalidDictionary")
        self.assertIn("do not reverse each other", refused["message"])

    def test_a_cloned_dictionary_rejects_commit_and_pulls_its_origin(self):
        remote = dictionary_skeleton("food")
        remote["version"] = "1.0.0"
        remote["id"] = "food.1.0.0"
        remote["status"] = "final"
        remote["description"] = "Edible things."
        self.blueprints.remote["https://example.test/_dictionary/public/food/1.0.0"] = remote
        latest = dictionary_skeleton("food")
        latest.update(_food())
        latest["version"] = "1.1.0"
        latest["id"] = "food.1.1.0"
        latest["status"] = "final"
        self.blueprints.remote["https://example.test/_dictionary/public/food/last"] = latest

        cloned, status = clone_dictionary(
            self.blueprints, "portfolio", "https://example.test/_dictionary/public/food/1.0.0"
        )
        self.assertEqual(status, 201)
        self.assertEqual(cloned["origin"], "https://example.test/_dictionary/public/food/1.0.0")
        self.assertEqual(cloned["version"], "1.0.0")
        self.assertEqual(cloned["id"], "food.1.0.0")
        refused, refused_status = commit_dictionary(self.blueprints, "portfolio", "food", {"description": "local"})
        self.assertEqual(refused_status, 400)
        self.assertEqual(refused["error"]["type"], "ClonedDictionary")
        self.assertIn("pullDictionary", refused["message"])

        pulled, pull_status = pull_dictionary(self.blueprints, "portfolio", "food")
        self.assertEqual(pull_status, 200)
        self.assertEqual(pulled["version"], "1.1.0")
        self.assertEqual(pulled["terms"]["food"]["id"], "food.food")
        self.assertNotIn(("portfolio", "food", "1.0.0"), self.blueprints.docs)

    def test_deprecate_marks_one_version(self):
        new_dictionary(self.blueprints, "portfolio", "food", {})
        publish_dictionary(self.blueprints, "portfolio", "food")
        deprecated, status = deprecate_dictionary(self.blueprints, "portfolio", "food", "1.0.0")
        self.assertEqual(status, 200)
        self.assertEqual(deprecated["status"], "deprecated")
        self.assertEqual(deprecated["version"], "1.0.0")
        self.assertEqual(deprecated["id"], "food.1.0.0")
        draft, _status = get_dictionary(self.blueprints, "portfolio", "food", "x.y.z")
        self.assertEqual(draft["status"], "draft")

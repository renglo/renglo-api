"""Schema drafts, publish, clone, and pull."""
from __future__ import annotations

import unittest

from renglo_api.client.contracts import (
    clone_schema,
    commit_schema,
    deprecate_schema,
    get_schema,
    list_schemas,
    list_versions,
    new_schema,
    publish_schema,
    pull_schema,
)


class _Blueprints:
    def __init__(self):
        self.docs = {}
        self.remote = {}

    def list_blueprint_versions(self, handle, name):
        items = [
            document
            for (stored_handle, stored_name, _version), document in self.docs.items()
            if stored_handle == handle and stored_name == name
        ]
        return {"success": True, "items": items, "status": 200}

    def list_blueprint_names(self, handle):
        names = sorted({
            name
            for (stored_handle, name, _version) in self.docs
            if stored_handle == handle
        })
        return {"success": True, "items": names, "status": 200}

    def get_blueprint(self, handle, name, version):
        document = self.docs.get((handle, name, version))
        if document is None:
            return {"success": False, "message": "Document not found"}
        return document

    def put_blueprint_document(self, handle, name, document):
        stored = dict(document)
        stored["handle"] = handle
        stored["name"] = name
        stored["irn"] = f"irn:blueprint:{handle}:{name}"
        self.docs[(handle, name, stored["version"])] = stored
        return {"success": True, "document": stored, "status": 200}

    def delete_blueprint(self, handle, name, version):
        self.docs.pop((handle, name, version), None)
        return {"success": True, "status": 200}

    def fetch_blueprint(self, uri):
        document = self.remote.get(uri)
        if document is None:
            return {"success": False, "message": "Schema URI could not be read", "status": 400}
        return document


def _field(name, field_type="string"):
    return {
        "name": name,
        "label": name.replace("_", " ").title(),
        "type": field_type,
        "widget": "number" if field_type == "number" else "text",
        "cardinality": "single",
        "layer": "0",
        "required": False,
        "default": 0 if field_type == "number" else "",
    }


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.blueprints = _Blueprints()

    def test_a_new_schema_is_a_draft_and_an_empty_body_still_creates_one(self):
        created, status = new_schema(self.blueprints, "portfolio", "projects", {})
        self.assertEqual(status, 201)
        self.assertEqual(created["name"], "projects")
        self.assertEqual(created["label"], "projects")
        self.assertEqual(created["description"], "")
        self.assertEqual(created["fields"], [])
        self.assertEqual(created["dictionaries"], [])
        self.assertEqual(created["license"], "CC BY")
        self.assertIs(created["public"], True)
        self.assertIs(created["singleton"], False)
        self.assertEqual(created["blueprint_origin"], "")
        self.assertEqual(created["uri"], "")
        self.assertEqual(created["version"], "x.y.z")
        self.assertEqual(created["status"], "draft")
        self.assertEqual(created["origin"], "")
        self.assertEqual(self.blueprints.docs[("portfolio", "projects", "x.y.z")]["handle"], "portfolio")
        custom, custom_status = new_schema(self.blueprints, "portfolio", "shots", {
            "public": False,
            "singleton": True,
            "license": "MIT",
        })
        self.assertEqual(custom_status, 201)
        self.assertIs(custom["public"], False)
        self.assertIs(custom["singleton"], True)
        self.assertEqual(custom["license"], "MIT")
        self.assertEqual(custom["fields"], [])
        self.assertEqual(custom["status"], "draft")
        again, again_status = new_schema(self.blueprints, "portfolio", "projects", {"fields": []})
        self.assertEqual(again_status, 409)
        self.assertEqual(again["error"]["type"], "SchemaExists")
        self.assertIn("commitSchema", again["message"])
        self.assertIn("cloneSchema", again["message"])

    def test_commit_updates_the_draft_and_publish_assigns_the_version(self):
        new_schema(self.blueprints, "portfolio", "projects", {})
        committed, commit_status = commit_schema(self.blueprints, "portfolio", "projects", {
            "fields": [_field("title")],
        })
        self.assertEqual(commit_status, 200)
        self.assertEqual(committed["version"], "x.y.z")
        self.assertEqual(committed["status"], "draft")
        self.assertEqual(committed["fields"][0]["name"], "title")

        published, publish_status = publish_schema(self.blueprints, "portfolio", "projects")
        self.assertEqual(publish_status, 200)
        self.assertEqual(published["version"], "1.0.0")
        self.assertEqual(published["status"], "final")
        current, _status = get_schema(self.blueprints, "portfolio", "projects")
        self.assertEqual(current["version"], "x.y.z")
        self.assertEqual(current["status"], "draft")
        self.assertEqual(current["fields"][0]["name"], "title")

        commit_schema(self.blueprints, "portfolio", "projects", {
            "fields": [_field("title"), _field("budget", "number")],
        })
        second, _status = publish_schema(self.blueprints, "portfolio", "projects")
        self.assertEqual(second["version"], "1.1.0")
        self.assertEqual(second["status"], "final")
        listed, _status = list_versions(self.blueprints, "portfolio", "projects")
        versions = [item["version"] for item in listed["items"]]
        self.assertEqual(versions, ["1.0.0", "1.1.0", "x.y.z"])
        names, _status = list_schemas(self.blueprints, "portfolio")
        self.assertEqual(names, {"items": [{"name": "projects"}]})

    def test_a_cloned_schema_rejects_commit_and_pulls_its_origin(self):
        self.blueprints.remote["https://example.test/_blueprint/public/projects/1.0.0"] = {
            "name": "projects",
            "label": "Projects",
            "version": "1.0.0",
            "status": "final",
            "fields": [_field("title")],
        }
        self.blueprints.remote["https://example.test/_blueprint/public/projects/last"] = {
            "name": "projects",
            "label": "Projects",
            "version": "1.2.0",
            "status": "final",
            "fields": [_field("title"), _field("budget", "number")],
        }
        cloned, status = clone_schema(
            self.blueprints, "portfolio", "https://example.test/_blueprint/public/projects/1.0.0"
        )
        self.assertEqual(status, 201)
        self.assertEqual(cloned["origin"], "https://example.test/_blueprint/public/projects/1.0.0")
        self.assertEqual(cloned["version"], "1.0.0")
        refused, refused_status = commit_schema(self.blueprints, "portfolio", "projects", {"fields": []})
        self.assertEqual(refused_status, 400)
        self.assertEqual(refused["error"]["type"], "ClonedSchema")
        self.assertIn("pullSchema", refused["message"])

        pulled, pull_status = pull_schema(self.blueprints, "portfolio", "projects")
        self.assertEqual(pull_status, 200)
        self.assertEqual(pulled["version"], "1.2.0")
        self.assertEqual(pulled["origin"], "https://example.test/_blueprint/public/projects/1.0.0")
        self.assertEqual(len(pulled["fields"]), 2)
        self.assertNotIn(("portfolio", "projects", "1.0.0"), self.blueprints.docs)

    def test_commit_opens_a_draft_when_the_last_one_was_published(self):
        new_schema(self.blueprints, "portfolio", "projects", {
            "fields": [_field("title")],
        })
        publish_schema(self.blueprints, "portfolio", "projects")
        del self.blueprints.docs[("portfolio", "projects", "x.y.z")]
        committed, status = commit_schema(self.blueprints, "portfolio", "projects", {
            "fields": [_field("title"), _field("owner")],
        })
        self.assertEqual(status, 200)
        self.assertEqual(committed["version"], "x.y.z")
        self.assertEqual(committed["status"], "draft")
        self.assertEqual(committed["fields"][1]["name"], "owner")

    def test_deprecate_marks_one_version(self):
        new_schema(self.blueprints, "portfolio", "projects", {})
        publish_schema(self.blueprints, "portfolio", "projects")
        deprecated, status = deprecate_schema(self.blueprints, "portfolio", "projects", "1.0.0")
        self.assertEqual(status, 200)
        self.assertEqual(deprecated["status"], "deprecated")
        self.assertEqual(deprecated["version"], "1.0.0")
        draft, _status = get_schema(self.blueprints, "portfolio", "projects", "x.y.z")
        self.assertEqual(draft["status"], "draft")

    def test_commit_refuses_a_field_that_breaks_the_schema_shape(self):
        new_schema(self.blueprints, "portfolio", "projects", {"fields": [_field("title")]})
        refused, status = commit_schema(self.blueprints, "portfolio", "projects", {
            "fields": [{
                "name": "title",
                "label": "Title",
                "type": "string",
                "widget": "text",
                "cardinality": "many",
                "layer": "9",
                "required": False,
                "default": "",
            }],
        })
        self.assertEqual(status, 400)
        self.assertEqual(refused["error"]["type"], "InvalidSchema")
        self.assertIn("cardinality", refused["message"])
        self.assertIn("layer", refused["message"])
        current, _status = get_schema(self.blueprints, "portfolio", "projects")
        self.assertEqual(current["fields"][0]["cardinality"], "single")


if __name__ == "__main__":
    unittest.main()

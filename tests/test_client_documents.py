"""/v1 document translation: query operators, collections, and document writes."""
from __future__ import annotations

import unittest

from renglo_api.client.data_types import create_data_type, get_data_type, update_data_type
from renglo_api.client.document_query import DocumentQueryError, translate_document_query
from renglo_api.client.documents import (
    count_documents,
    create_collection,
    create_index,
    delete_index,
    get_collection,
    parse_project_id,
    query_documents,
    upsert_document,
)


BLUEPRINT = {
    "name": "projects",
    "fields": [
        {"name": "status", "type": "string"},
        {"name": "ownerId", "type": "string"},
        {"name": "createdAt", "type": "timestamp"},
        {"name": "location", "type": "string"},
    ],
    "indexes": {
        "path": ["status", "ownerId"],
        "time": ["createdAt"],
        "geo": ["location"],
    },
}


class QueryTranslationTests(unittest.TestCase):
    def test_path_prefix_becomes_begins_with_and_sort_desc_passes_through(self):
        translated = translate_document_query(BLUEPRINT, {
            "filter": {"status": "active"},
            "sort": [{"field": "createdAt", "direction": "desc"}],
        })
        self.assertEqual(translated["operator"], "begins_with")
        self.assertEqual(translated["value"], "active")
        self.assertEqual(translated["sort"], "desc")
        both = translate_document_query(BLUEPRINT, {
            "filter": {"status": "active", "ownerId": "user-1"},
            "sort": "asc",
        })
        self.assertEqual(both["value"], "active:user-1")
        self.assertEqual(both["sort"], "asc")

    def test_time_and_geo_use_the_existing_operators(self):
        timed = translate_document_query(BLUEPRINT, {"filter": {"createdAt": 17234432453}})
        self.assertEqual(timed["operator"], "chrono")
        self.assertEqual(timed["filter"]["value"], "17234432453")
        geo = translate_document_query(BLUEPRINT, {"filter": {"location": "9.1,45.2"}})
        self.assertEqual(geo["operator"], "begins_with")
        self.assertEqual(geo["value"], "9.1,45.2")

    def test_a_filter_that_is_not_a_prefix_is_rejected(self):
        with self.assertRaises(DocumentQueryError) as caught:
            translate_document_query(BLUEPRINT, {"filter": {"ownerId": "user-1"}})
        self.assertEqual(caught.exception.error_type, "UnindexedFilter")


class _Auth:
    def __init__(self):
        self.rings = {}
        self.versions = {}

    def get_entity(self, entity_type, **kwargs):
        key = (kwargs["portfolio_id"], kwargs["org_id"], kwargs["ring_id"])
        document = self.rings.get(key)
        if not document or (document.get("status") == "deleted" and not kwargs.get("include_deleted")):
            return {"success": False, "message": "Entity not found", "status": 404}
        return {"success": True, "document": document, "status": 200}

    def create_entity(self, entity_type, **kwargs):
        key = (kwargs["portfolio_id"], kwargs["org_id"], kwargs["name"])
        if key in self.rings:
            return {"success": False, "message": "Collection already exists", "status": 409}
        document = {
            "_id": kwargs["name"],
            "name": kwargs["name"],
            "status": "active",
            "document_count": 0,
            "blueprint": {"version": kwargs.get("blueprint_version") or "1.0.0"},
        }
        self.rings[key] = document
        return {"success": True, "document": document, "status": 200}

    def create_rel(self, reltype, **data):
        return {"success": True, "status": 200}

    def set_ring_blueprint(self, portfolio, org, name, blueprint):
        self.versions[(portfolio, org, name)] = blueprint["version"]
        return {"success": True}

    def set_ring_data_type(self, portfolio, org, name, data_type):
        document = self.rings.get((portfolio, org, name))
        if isinstance(document, dict):
            document["data_type"] = data_type
        return {"success": True}


class _Blueprints:
    def __init__(self):
        self.docs = {}

    def create_blueprint(self, data, user_handle=None):
        document = dict(data)
        document["handle"] = user_handle
        document["version"] = "1.0.0"
        self.docs[(user_handle, data["name"])] = document
        return {"success": True, "document": document, "status": 201}

    def update_blueprint(self, handle, name, data=None):
        document = dict(self.docs[(handle, name)])
        document.update(data or {})
        document["version"] = "1.1.0" if "indexes" in (data or {}) else "1.0.1"
        self.docs[(handle, name)] = document
        return {"success": True, "document": document, "status": 200}

    def get_blueprint(self, handle, name, version):
        return self.docs.get((handle, name), {"success": False, "message": "Document not found"})

    def extract_blueprint_data(self, uri):
        return {
            "name": "remote",
            "fields": [{"name": "title", "type": "string"}],
            "version": "9.0.0",
            "status": "final",
        }


class _Data:
    def __init__(self):
        self.docs = {}
        self.deleted = False
        self.seq = 0

    def ring_is_deleted(self, portfolio, org, ring):
        return self.deleted

    def post_a_b(self, portfolio, org, ring, payload, document_id=None):
        self.seq += 1
        doc_id = document_id or f"id-{self.seq}"
        item = {"_id": doc_id, "attributes": dict(payload)}
        self.docs[(ring, doc_id)] = item
        return {"success": True, "item": item}, 200

    def get_a_b_c(self, portfolio, org, ring, doc_id):
        item = self.docs.get((ring, doc_id))
        if not item:
            return {"success": False, "message": "Item could not be retrieved"}
        body = dict(item["attributes"])
        body["_id"] = doc_id
        return body

    def put_a_b_c(self, portfolio, org, ring, doc_id, payload):
        current = self.docs.get((ring, doc_id))
        if not current:
            return {"success": False, "message": "Item could not be saved"}, 400
        current["attributes"].update(payload)
        return {"success": True}, 200

    def get_a_b_query(self, query):
        self.last_query = query
        return {"success": True, "items": [], "last_id": None}


class DocumentRouteTests(unittest.TestCase):
    def setUp(self):
        self.auth = _Auth()
        self.blueprints = _Blueprints()
        self.data = _Data()

    def test_project_id_splits_on_the_first_dash(self):
        self.assertEqual(parse_project_id("portfolio-org-west"), ("portfolio", "org-west"))
        self.assertIsNone(parse_project_id("portfolio"))

    def test_create_collection_writes_a_ring_and_refuses_index_changes_with_documents(self):
        created, status = create_collection(self.auth, self.blueprints, "portfolio", "org", "projects", {
            "blueprint_object": {"fields": BLUEPRINT["fields"]},
        })
        self.assertEqual(status, 201)
        self.assertEqual(created["version"], "1.0.0")
        copied, _status = create_collection(self.auth, self.blueprints, "portfolio", "org", "from-uri", {
            "blueprint_uri": "https://example.test/_blueprint/public/projects/9.0.0",
        })
        self.assertEqual(copied["name"], "from-uri")
        self.assertEqual(self.blueprints.docs[("portfolio", "from-uri")]["fields"][0]["name"], "title")

        indexed, index_status = create_index(self.auth, self.blueprints, "portfolio", "org", "projects", {
            "kind": "path",
            "fields": ["status", "ownerId"],
        })
        self.assertEqual(index_status, 201)
        self.assertEqual(indexed["items"][0]["kind"], "path")

        self.auth.rings[("portfolio", "org", "projects")]["document_count"] = 2
        refused, refused_status = create_index(self.auth, self.blueprints, "portfolio", "org", "projects", {
            "kind": "geo",
            "field": "location",
        })
        self.assertEqual(refused_status, 409)
        self.assertEqual(refused["error"]["type"], "ReindexRequired")
        deleted, deleted_status = delete_index(self.auth, "portfolio", "org", "projects", "path")
        self.assertEqual(deleted_status, 409)
        self.assertEqual(deleted["error"]["type"], "ReindexRequired")

    def test_query_count_and_upsert(self):
        create_collection(self.auth, self.blueprints, "portfolio", "org", "projects", {
            "blueprint_object": BLUEPRINT,
        })
        queried, _status = query_documents(self.data, self.blueprints, "portfolio", "org", "projects", {
            "filter": {"status": "active"},
            "sort": "desc",
            "limit": 5,
        })
        self.assertEqual(queried["items"], [])
        self.assertEqual(self.data.last_query["operator"], "begins_with")
        self.assertEqual(self.data.last_query["sort"], "desc")
        rejected, rejected_status = query_documents(self.data, self.blueprints, "portfolio", "org", "projects", {
            "filter": {"ownerId": "user-1"},
        })
        self.assertEqual(rejected_status, 400)
        self.assertEqual(rejected["error"]["type"], "UnindexedFilter")

        counted, _status = count_documents(self.auth, "portfolio", "org", "projects")
        self.assertEqual(counted["count"], 0)
        filtered, filtered_status = count_documents(
            self.auth, "portfolio", "org", "projects", {"filter": {"status": "active"}}
        )
        self.assertEqual(filtered_status, 400)

        created_type, type_status = create_data_type(self.blueprints, "portfolio", "character", {
            "fields": [{"name": "name", "type": "string"}],
        })
        self.assertEqual(type_status, 201)
        self.assertEqual(created_type["version"], "1.0.0")
        opened, opened_status = create_collection(self.auth, self.blueprints, "portfolio", "org", "cast", {
            "dataType": "character",
        })
        self.assertEqual(opened_status, 201)
        self.assertEqual(opened["dataType"], "character")
        self.assertEqual(self.auth.rings[("portfolio", "org", "cast")]["data_type"], "character")
        update_data_type(self.blueprints, "portfolio", "character", {
            "fields": [
                {"name": "name", "type": "string"},
                {"name": "age", "type": "number"},
            ],
            "migration": {"from": "1.0.0"},
        })
        current, _current_status = get_data_type(self.blueprints, "portfolio", "character")
        self.assertEqual(current["version"], "1.0.1")
        self.assertEqual(current["migration"]["from"], "1.0.0")
        followed, _followed_status = get_collection(self.auth, self.blueprints, "portfolio", "org", "cast")
        self.assertEqual(followed["dataType"], "character")
        self.assertEqual(followed["version"], "1.0.1")

        created, _status = upsert_document(self.data, "portfolio", "org", "projects", "doc-1", {"status": "active"})
        self.assertEqual(created["id"], "doc-1")
        replaced, _status = upsert_document(self.data, "portfolio", "org", "projects", "doc-1", {"status": "paused"})
        self.assertEqual(replaced["status"], "paused")


if __name__ == "__main__":
    unittest.main()

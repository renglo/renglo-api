"""/v1 document translation: query operators, collections, and document writes."""
from __future__ import annotations

import unittest

from renglo.auth.entity_status import ENTITY_STATUS_DELETED, entity_is_deleted
from renglo_api.client.data_types import create_data_type, get_data_type, update_data_type
from renglo_api.client.document_query import DocumentQueryError, translate_document_query
from renglo_api.client.documents import (
    create_collection,
    create_document,
    get_collection,
    list_collections,
    parse_project_id,
    query_documents,
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
        self.collections = {}
        self.links = []

    def get_entity(self, entity_type, **kwargs):
        self.assert_collection = entity_type
        key = (kwargs["portfolio_id"], kwargs["org_id"], kwargs["collection_id"])
        document = self.collections.get(key)
        if not document or (entity_is_deleted(document) and not kwargs.get("include_deleted")):
            return {"success": False, "message": "Entity not found", "status": 404}
        return {"success": True, "document": document, "status": 200}

    def create_entity(self, entity_type, **kwargs):
        key = (kwargs["portfolio_id"], kwargs["org_id"], kwargs["name"])
        current = self.collections.get(key)
        if current and not entity_is_deleted(current):
            return {"success": False, "message": "Collection already exists", "status": 409}
        if current and entity_is_deleted(current):
            current["status"] = "active"
            current["type"] = entity_type
            return {"success": True, "document": current, "status": 200}
        document = {
            "_id": kwargs["name"],
            "name": kwargs["name"],
            "type": entity_type,
            "status": "active",
            "document_count": 0,
        }
        self.collections[key] = document
        return {"success": True, "document": document, "status": 200}

    def create_rel(self, reltype, **data):
        self.links.append((reltype, data))
        return {"success": True, "status": 200}

    def list_entity(self, entity_type, **kwargs):
        items = []
        for (portfolio, org, _name), document in self.collections.items():
            if portfolio != kwargs["portfolio_id"] or org != kwargs["org_id"]:
                continue
            if document.get("type") != entity_type or entity_is_deleted(document):
                continue
            if kwargs.get("team_id"):
                linked = any(
                    reltype == "team:collection"
                    and data.get("team_id") == kwargs["team_id"]
                    and data.get("collection_name") == document["name"]
                    for reltype, data in self.links
                )
                if not linked:
                    continue
            items.append(document)
        return {"success": True, "document": {"items": items}, "status": 200}


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
        document["version"] = "1.0.1"
        self.docs[(handle, name)] = document
        return {"success": True, "document": document, "status": 200}

    def get_blueprint(self, handle, name, version):
        return self.docs.get((handle, name), {"success": False, "message": "Document not found"})


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

    def test_create_collection_requires_the_schema_and_does_not_write_one(self):
        missing, missing_status = create_collection(
            self.auth, self.blueprints, "portfolio", "org", "projects"
        )
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing["error"]["type"], "SchemaNotFound")
        self.assertEqual(self.blueprints.docs, {})

        create_data_type(self.blueprints, "portfolio", "projects", {"fields": BLUEPRINT["fields"]})
        created, status = create_collection(
            self.auth, self.blueprints, "portfolio", "org", "projects", team_id="team-1"
        )
        self.assertEqual(status, 201)
        self.assertEqual(created, {"name": "projects", "count": 0})
        self.assertNotIn("blueprint", self.auth.collections[("portfolio", "org", "projects")])
        self.assertNotIn("version", created)
        self.assertEqual(self.auth.collections[("portfolio", "org", "projects")]["type"], "collection")
        self.assertEqual(self.auth.links[0][0], "team:collection")
        again, again_status = create_collection(
            self.auth, self.blueprints, "portfolio", "org", "projects"
        )
        self.assertEqual(again_status, 409)
        self.assertEqual(again["error"]["type"], "CollectionExists")

    def test_saving_a_document_opens_the_collection_and_a_deleted_entity_returns(self):
        create_data_type(self.blueprints, "portfolio", "projects", BLUEPRINT)
        saved, status = create_document(
            self.data, self.auth, self.blueprints, "portfolio", "org", "projects",
            {"status": "active"}, team_id="team-1",
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved["id"], "id-1")
        self.assertEqual(self.auth.collections[("portfolio", "org", "projects")]["type"], "collection")
        opened, opened_status = get_collection(self.auth, "portfolio", "org", "projects")
        self.assertEqual(opened_status, 200)
        self.assertEqual(opened, {"name": "projects", "count": 0})

        self.auth.collections[("portfolio", "org", "projects")]["status"] = ENTITY_STATUS_DELETED
        hidden, hidden_status = get_collection(self.auth, "portfolio", "org", "projects")
        self.assertEqual(hidden_status, 404)
        create_document(
            self.data, self.auth, self.blueprints, "portfolio", "org", "projects", {"status": "active"}
        )
        self.assertEqual(self.auth.collections[("portfolio", "org", "projects")]["status"], "active")

        listed, _listed_status = list_collections(self.auth, "portfolio", "org", team_id="team-1")
        self.assertEqual(listed["items"], [{"name": "projects", "count": 0}])
        other, _other_status = list_collections(self.auth, "portfolio", "org", team_id="team-2")
        self.assertEqual(other["items"], [])

    def test_query_uses_the_schema_path_prefix(self):
        create_data_type(self.blueprints, "portfolio", "projects", BLUEPRINT)
        queried, _status = query_documents(self.data, self.blueprints, "portfolio", "org", "projects", {
            "filter": {"status": "active"},
            "sort": "desc",
            "limit": 5,
        })
        self.assertEqual(queried["items"], [])
        self.assertEqual(self.data.last_query["operator"], "begins_with")
        self.assertEqual(self.data.last_query["value"], "active")
        self.assertEqual(self.data.last_query["sort"], "desc")
        rejected, rejected_status = query_documents(self.data, self.blueprints, "portfolio", "org", "projects", {
            "filter": {"ownerId": "user-1"},
        })
        self.assertEqual(rejected_status, 400)
        self.assertEqual(rejected["error"]["type"], "UnindexedFilter")

        created_type, type_status = create_data_type(self.blueprints, "portfolio", "character", {
            "fields": [{"name": "name", "type": "string"}],
        })
        self.assertEqual(type_status, 201)
        self.assertEqual(created_type["version"], "1.0.0")
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


if __name__ == "__main__":
    unittest.main()

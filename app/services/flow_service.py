# app/services/flow_service.py
from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia
from app.services.flow_validation import (
    build_blocks_index,
    validate_block_configs,
    validate_flow_graph_structure,
)

FLOWS_COLLECTION = "flows"
VERSIONS_COLLECTION = "flow_versions"

ALLOWED_FLOW_STATUS = frozenset({"draft", "published"})


def validate_object_id(fid: str) -> ObjectId:
    try:
        return ObjectId(fid)
    except InvalidId:
        raise ValueError("Invalid flow id")


def _default_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "start-1",
                "type": "flowStart",
                "position": {"x": 260, "y": 40},
                "data": {"blockType": "start", "label": "Início"},
            },
            {
                "id": "end-1",
                "type": "flowEnd",
                "position": {"x": 260, "y": 420},
                "data": {"blockType": "end", "label": "Fim"},
            },
        ],
        "edges": [
            {
                "id": "e-start-end",
                "source": "start-1",
                "target": "end-1",
                "type": "smoothstep",
                "animated": True,
            },
        ],
    }


def serialize_flow(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    if "is_active" not in out:
        out["is_active"] = True
    if "is_main" not in out:
        out["is_main"] = False
    return out


def serialize_version(
    doc: dict,
    *,
    include_graph: bool = True,
    include_blocks_index: bool = True,
) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    out["flow_id"] = str(out["flow_id"])
    if not include_graph:
        out.pop("graph", None)
    if not include_blocks_index:
        out.pop("blocks_index", None)
    return out


def _prepare_graph(graph: dict | None) -> dict[str, Any]:
    if not graph:
        return _default_graph()
    if not isinstance(graph, dict):
        raise ValueError("graph must be an object")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if nodes is not None and not isinstance(nodes, list):
        raise ValueError("graph.nodes must be a list")
    if edges is not None and not isinstance(edges, list):
        raise ValueError("graph.edges must be a list")
    return {
        "nodes": list(nodes or []),
        "edges": list(edges or []),
    }


def _validate_and_index(tenant_database: str, graph: dict[str, Any]) -> dict[str, Any]:
    start_id, end_id, logic_nodes = validate_flow_graph_structure(graph)
    validate_block_configs(tenant_database, logic_nodes)
    return build_blocks_index(graph, start_id, end_id, logic_nodes)


def list_flows(tenant_database: str) -> list[dict]:
    """Active flows only; legacy docs without `is_active` are treated as active."""
    try:
        db = get_tenant_db(tenant_database)
        cursor = db[FLOWS_COLLECTION].find(
            {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
        ).sort(
            [("updated_at", -1), ("name", 1)],
        )
        return [serialize_flow(d) for d in cursor]
    except Exception as e:
        raise RuntimeError(f"Erro ao listar fluxos: {e}")


def create_flow(tenant_database: str, data: dict, created_by: str | None) -> dict:
    db = get_tenant_db(tenant_database)
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Flow name is required")

    desc = data.get("description")
    if desc is not None:
        desc = str(desc).strip()
    else:
        desc = ""

    graph = _prepare_graph(data.get("graph"))
    blocks_index = _validate_and_index(tenant_database, graph)

    now = now_brasilia()
    flow_doc = {
        "name": name,
        "description": desc,
        "status": "draft",
        "current_version": 1,
        "is_active": True,
        "is_main": False,
        "created_at": now,
        "updated_at": now,
    }
    fres = db[FLOWS_COLLECTION].insert_one(flow_doc)
    flow_oid = fres.inserted_id

    ver_doc = {
        "flow_id": flow_oid,
        "version": 1,
        "is_current": True,
        "graph": graph,
        "blocks_index": blocks_index,
        "created_at": now,
        "created_by": created_by,
    }
    db[VERSIONS_COLLECTION].insert_one(ver_doc)

    flow_doc["_id"] = flow_oid
    return get_flow_with_current(tenant_database, str(flow_oid))


def get_flow_header(tenant_database: str, flow_id: str) -> dict:
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(flow_id)
    doc = db[FLOWS_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Flow not found")
    return serialize_flow(doc)


def get_flow_with_current(tenant_database: str, flow_id: str) -> dict:
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(flow_id)
    flow = db[FLOWS_COLLECTION].find_one({"_id": oid})
    if not flow:
        raise ValueError("Flow not found")

    cur_ver = flow.get("current_version") or 1
    vdoc = db[VERSIONS_COLLECTION].find_one(
        {"flow_id": oid, "version": int(cur_ver), "is_current": True},
    )
    if not vdoc:
        vdoc = db[VERSIONS_COLLECTION].find_one(
            {"flow_id": oid, "is_current": True},
        )
    if not vdoc:
        raise ValueError("Current flow version not found")

    out = serialize_flow(flow)
    out["current"] = serialize_version(
        vdoc,
        include_graph=True,
        include_blocks_index=True,
    )
    return out


def list_flow_versions(tenant_database: str, flow_id: str) -> list[dict]:
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(flow_id)
    flow = db[FLOWS_COLLECTION].find_one({"_id": oid})
    if not flow:
        raise ValueError("Flow not found")

    cursor = (
        db[VERSIONS_COLLECTION]
        .find({"flow_id": oid})
        .sort("version", -1)
    )
    return [
        serialize_version(
            d,
            include_graph=False,
            include_blocks_index=True,
        )
        for d in cursor
    ]


def get_flow_version(
    tenant_database: str,
    flow_id: str,
    version: int,
    *,
    include_graph: bool = True,
) -> dict:
    db = get_tenant_db(tenant_database)
    foid = validate_object_id(flow_id)
    flow = db[FLOWS_COLLECTION].find_one({"_id": foid})
    if not flow:
        raise ValueError("Flow not found")

    vdoc = db[VERSIONS_COLLECTION].find_one({"flow_id": foid, "version": int(version)})
    if not vdoc:
        raise ValueError("Flow version not found")
    return serialize_version(
        vdoc,
        include_graph=include_graph,
        include_blocks_index=True,
    )


def save_new_version(
    tenant_database: str,
    flow_id: str,
    graph: dict,
    created_by: str | None,
) -> dict:
    db = get_tenant_db(tenant_database)
    foid = validate_object_id(flow_id)
    flow = db[FLOWS_COLLECTION].find_one({"_id": foid})
    if not flow:
        raise ValueError("Flow not found")

    graph = _prepare_graph(graph)
    blocks_index = _validate_and_index(tenant_database, graph)

    now = now_brasilia()
    last = db[VERSIONS_COLLECTION].find_one(
        {"flow_id": foid},
        sort=[("version", -1)],
    )
    next_v = int(last["version"]) + 1 if last else 1

    db[VERSIONS_COLLECTION].update_many(
        {"flow_id": foid, "is_current": True},
        {"$set": {"is_current": False}},
    )

    ver_doc = {
        "flow_id": foid,
        "version": next_v,
        "is_current": True,
        "graph": graph,
        "blocks_index": blocks_index,
        "created_at": now,
        "created_by": created_by,
    }
    db[VERSIONS_COLLECTION].insert_one(ver_doc)

    db[FLOWS_COLLECTION].update_one(
        {"_id": foid},
        {"$set": {"current_version": next_v, "updated_at": now}},
    )

    return get_flow_with_current(tenant_database, flow_id)


def rollback_to_version(
    tenant_database: str,
    flow_id: str,
    version: int,
    created_by: str | None,
) -> dict:
    db = get_tenant_db(tenant_database)
    foid = validate_object_id(flow_id)
    flow = db[FLOWS_COLLECTION].find_one({"_id": foid})
    if not flow:
        raise ValueError("Flow not found")

    src = db[VERSIONS_COLLECTION].find_one({"flow_id": foid, "version": int(version)})
    if not src:
        raise ValueError("Flow version not found")

    graph = deepcopy(src.get("graph") or {})
    blocks_index = _validate_and_index(tenant_database, _prepare_graph(graph))

    now = now_brasilia()
    last = db[VERSIONS_COLLECTION].find_one(
        {"flow_id": foid},
        sort=[("version", -1)],
    )
    next_v = int(last["version"]) + 1 if last else 1

    db[VERSIONS_COLLECTION].update_many(
        {"flow_id": foid, "is_current": True},
        {"$set": {"is_current": False}},
    )

    ver_doc = {
        "flow_id": foid,
        "version": next_v,
        "is_current": True,
        "graph": graph,
        "blocks_index": blocks_index,
        "created_at": now,
        "created_by": created_by,
        "rolled_back_from_version": int(version),
    }
    db[VERSIONS_COLLECTION].insert_one(ver_doc)

    db[FLOWS_COLLECTION].update_one(
        {"_id": foid},
        {"$set": {"current_version": next_v, "updated_at": now}},
    )

    return get_flow_with_current(tenant_database, flow_id)


def update_flow(tenant_database: str, flow_id: str, data: dict) -> dict:
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(flow_id)
    current = db[FLOWS_COLLECTION].find_one({"_id": oid})
    if not current:
        raise ValueError("Flow not found")

    for f in ["_id", "created_at", "current_version"]:
        data.pop(f, None)

    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
        if not data["name"]:
            raise ValueError("Name cannot be empty")

    if "description" in data and data["description"] is not None:
        data["description"] = str(data["description"]).strip()

    if "status" in data and data["status"] is not None:
        st = str(data["status"]).strip().lower()
        if st not in ALLOWED_FLOW_STATUS:
            raise ValueError(f"status must be one of: {', '.join(sorted(ALLOWED_FLOW_STATUS))}")
        data["status"] = st

    if "is_active" in data and data["is_active"] is not None:
        data["is_active"] = bool(data["is_active"])
        if data["is_active"] is False:
            data["is_main"] = False

    if "is_main" in data and data["is_main"] is not None:
        data["is_main"] = bool(data["is_main"])
        if data["is_main"] is True:
            now = now_brasilia()
            db[FLOWS_COLLECTION].update_many(
                {"_id": {"$ne": oid}},
                {"$set": {"is_main": False, "updated_at": now}},
            )

    if not data:
        raise ValueError("No fields provided for update")

    data["updated_at"] = now_brasilia()
    res = db[FLOWS_COLLECTION].update_one({"_id": oid}, {"$set": data})
    if res.matched_count == 0:
        raise ValueError("Flow not found")

    return get_flow_with_current(tenant_database, flow_id)

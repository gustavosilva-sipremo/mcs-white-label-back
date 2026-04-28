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
    build_execution_plan,
    build_nodes_runtime_snapshot,
    validate_block_configs,
    validate_execution_plan_rules,
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
        ],
        "edges": [],
    }


def serialize_flow(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    if "is_active" not in out:
        out["is_active"] = True
    if "is_main" not in out:
        out["is_main"] = False
    hrv = out.pop("home_runtime_version", None)
    if isinstance(hrv, (int, float)) and float(hrv).is_integer():
        out["home_runtime_version"] = int(hrv)
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
        out.pop("execution_plan", None)
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
    validate_execution_plan_rules(logic_nodes)
    blocks_index = build_blocks_index(graph, start_id, end_id, logic_nodes)
    execution_plan = build_execution_plan(logic_nodes)
    return {
        "blocks_index": blocks_index,
        "execution_plan": execution_plan,
    }


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
    pack = _validate_and_index(tenant_database, graph)

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
        "blocks_index": pack["blocks_index"],
        "execution_plan": pack["execution_plan"],
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


def get_main_flow_current_plan(tenant_database: str) -> dict[str, Any]:
    """Main active flow + execution_plan para Home/runtime (opcionalmente versão antiga)."""
    db = get_tenant_db(tenant_database)
    flow = db[FLOWS_COLLECTION].find_one(
        {
            "is_main": True,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        },
    )
    if not flow:
        raise ValueError("No main flow found for this tenant")
    foid = flow["_id"]
    published_ver = int(flow.get("current_version") or 1)

    hr_raw = flow.get("home_runtime_version")
    hr_ver: int | None = None
    if isinstance(hr_raw, (int, float)) and float(hr_raw).is_integer():
        hr_candidate = int(hr_raw)
        if hr_candidate >= 1:
            hr_ver = hr_candidate

    vdoc = None

    if hr_ver is not None:
        v_override = db[VERSIONS_COLLECTION].find_one(
            {"flow_id": foid, "version": hr_ver},
        )
        if v_override:
            vdoc = v_override

    if vdoc is None:
        vdoc = db[VERSIONS_COLLECTION].find_one(
            {"flow_id": foid, "version": published_ver, "is_current": True},
        )
    if not vdoc:
        vdoc = db[VERSIONS_COLLECTION].find_one(
            {"flow_id": foid, "is_current": True},
        )
    if not vdoc:
        raise ValueError("Current flow version not found")

    eff_ver = int(vdoc.get("version") or published_ver or 1)
    runtime_version_is_override = eff_ver != published_ver
    exec_plan = vdoc.get("execution_plan")
    if not isinstance(exec_plan, dict):
        exec_plan = {}
    idx = vdoc.get("blocks_index")
    if not isinstance(idx, dict):
        idx = {}
    triggers_full = idx.get("triggers") if isinstance(idx.get("triggers"), list) else []
    graph = vdoc.get("graph") if isinstance(vdoc.get("graph"), dict) else {}
    nodes_by_id = build_nodes_runtime_snapshot(graph)
    return {
        "tenant": tenant_database,
        "flow_id": str(flow["_id"]),
        "flow_name": str(flow.get("name") or ""),
        "published_version": published_ver,
        "runtime_version": eff_ver,
        "runtime_version_is_override": runtime_version_is_override,
        # Compatível: versão efetiva do snapshot servido (= runtime_version)
        "current_version": eff_ver,
        "execution_plan": exec_plan,
        "triggers_index": triggers_full,
        "triggers_meta": exec_plan.get("entryBranches") or [],
        "nodes_by_id": nodes_by_id,
    }


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
    pack = _validate_and_index(tenant_database, graph)

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
        "blocks_index": pack["blocks_index"],
        "execution_plan": pack["execution_plan"],
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
    pack = _validate_and_index(tenant_database, _prepare_graph(graph))

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
        "blocks_index": pack["blocks_index"],
        "execution_plan": pack["execution_plan"],
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

    home_runtime_provided = "home_runtime_version" in data
    home_runtime_payload = data.pop("home_runtime_version") if home_runtime_provided else None

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

    unset_home_runtime = False
    will_deactivate = "is_active" in data and data["is_active"] is False
    losing_main = "is_main" in data and data["is_main"] is False

    if home_runtime_provided and not will_deactivate:
        if not current.get("is_main"):
            raise ValueError("home_runtime_version only applies to the main flow")
        if home_runtime_payload is None:
            unset_home_runtime = True
        else:
            try:
                hrv = int(home_runtime_payload)
            except (TypeError, ValueError) as e:
                raise ValueError("home_runtime_version must be an integer") from e
            if hrv < 1:
                raise ValueError("home_runtime_version must be >= 1")
            v_ok = db[VERSIONS_COLLECTION].find_one({"flow_id": oid, "version": hrv})
            if not v_ok:
                raise ValueError("Flow version not found")
            data["home_runtime_version"] = hrv

    if losing_main:
        unset_home_runtime = True
        data.pop("home_runtime_version", None)

    if will_deactivate:
        unset_home_runtime = True
        data.pop("home_runtime_version", None)

    if not data and not unset_home_runtime:
        raise ValueError("No fields provided for update")

    now = now_brasilia()
    if data:
        data["updated_at"] = now

    update_ops: dict[str, Any] = {}
    if data:
        update_ops["$set"] = data
    if unset_home_runtime:
        update_ops.setdefault("$unset", {})["home_runtime_version"] = ""
    if unset_home_runtime and not data:
        update_ops["$set"] = {"updated_at": now}

    res = db[FLOWS_COLLECTION].update_one({"_id": oid}, update_ops)
    if res.matched_count == 0:
        raise ValueError("Flow not found")

    return get_flow_with_current(tenant_database, flow_id)

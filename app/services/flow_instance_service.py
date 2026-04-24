# app/services/flow_instance_service.py
from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia
from app.services import flow_service

FLOW_INSTANCES_COLLECTION = "flow_instances"


def _validate_object_id(sid: str) -> ObjectId:
    try:
        return ObjectId(sid)
    except InvalidId as e:
        raise ValueError("Invalid instance id") from e


def _serialize_instance(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    out["flow_id"] = str(out["flow_id"])
    if out.get("created_by") is not None:
        out["created_by"] = str(out["created_by"])
    return out


def create_flow_instance(
    tenant_database: str,
    *,
    entry_branch_key: str,
    created_by: str | None,
    client_request_id: str | None = None,
) -> dict:
    key = str(entry_branch_key).strip()
    if not key:
        raise ValueError("entryBranchKey is required")

    main = flow_service.get_main_flow_current_plan(tenant_database)
    plan = main.get("execution_plan")
    if not isinstance(plan, dict):
        raise ValueError("Main flow has no execution plan")

    valid_entry = False
    for row in plan.get("entryBranches") or []:
        if not isinstance(row, dict):
            continue
        for bk in row.get("branchKeys") or []:
            if str(bk).strip() == key:
                valid_entry = True
                break
        if valid_entry:
            break
    if not valid_entry:
        raise ValueError(
            f"entryBranchKey {key!r} does not match any trigger entry branch",
        )

    steps_by_branch = plan.get("stepsByBranch")
    if not isinstance(steps_by_branch, dict):
        steps_by_branch = {}
    steps = steps_by_branch.get(key) or []
    if not steps:
        raise ValueError(f"No placed steps for branch {key!r}")

    min_order = min(int(s["order"]) for s in steps if isinstance(s, dict))

    db = get_tenant_db(tenant_database)
    now = now_brasilia()
    flow_oid = ObjectId(main["flow_id"])
    ver = int(main["current_version"])

    created_by_oid: ObjectId | None = None
    if created_by:
        created_by_oid = ObjectId(created_by)

    if client_request_id and str(client_request_id).strip() and created_by_oid:
        cid = str(client_request_id).strip()
        dup = db[FLOW_INSTANCES_COLLECTION].find_one(
            {
                "client_request_id": cid,
                "created_by": created_by_oid,
            },
        )
        if dup:
            return _serialize_instance(dup)

    doc = {
        "flow_id": flow_oid,
        "flow_version": ver,
        "execution_plan": deepcopy(plan),
        "status": "active",
        "compass": {"branchKey": key, "stepOrder": min_order},
        "events": [
            {
                "type": "instance_started",
                "at": now,
                "entryBranchKey": key,
                "flowVersion": ver,
            },
        ],
        "summary": {"lastEvent": "instance_started"},
        "created_at": now,
        "updated_at": now,
        "created_by": created_by_oid,
        "client_request_id": str(client_request_id).strip() if client_request_id else None,
    }
    ins = db[FLOW_INSTANCES_COLLECTION].insert_one(doc)
    doc["_id"] = ins.inserted_id
    return _serialize_instance(doc)


def advance_flow_instance(
    tenant_database: str,
    instance_id: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict:
    oid = _validate_object_id(instance_id)
    db = get_tenant_db(tenant_database)
    doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Flow instance not found")
    if str(doc.get("status")) != "active":
        raise ValueError("Flow instance is not active")

    plan = doc.get("execution_plan")
    if not isinstance(plan, dict):
        raise ValueError("Instance has no execution_plan snapshot")

    compass = doc.get("compass")
    if not isinstance(compass, dict):
        raise ValueError("Instance has no compass")
    branch = str(compass.get("branchKey", "")).strip()
    order = compass.get("stepOrder")
    if not branch or not isinstance(order, int):
        raise ValueError("Invalid compass state")

    steps_by_branch = plan.get("stepsByBranch")
    if not isinstance(steps_by_branch, dict):
        steps_by_branch = {}
    steps = steps_by_branch.get(branch) or []
    orders = sorted(
        {int(s["order"]) for s in steps if isinstance(s, dict) and "order" in s},
    )
    next_orders = [o for o in orders if o > order]
    now = now_brasilia()

    events = list(doc.get("events") or [])
    ev: dict[str, Any] = {
        "type": "advance",
        "at": now,
        "branchKey": branch,
        "fromOrder": order,
        "payload": payload or {},
    }

    if next_orders:
        next_o = next_orders[0]
        ev["toOrder"] = next_o
        events.append(ev)
        db[FLOW_INSTANCES_COLLECTION].update_one(
            {"_id": oid},
            {
                "$set": {
                    "compass": {"branchKey": branch, "stepOrder": next_o},
                    "events": events,
                    "summary.lastEvent": "advance",
                    "updated_at": now,
                },
            },
        )
    else:
        ev["type"] = "branch_completed"
        events.append(ev)
        db[FLOW_INSTANCES_COLLECTION].update_one(
            {"_id": oid},
            {
                "$set": {
                    "status": "completed",
                    "events": events,
                    "summary.lastEvent": "branch_completed",
                    "updated_at": now,
                },
            },
        )

    out = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    return _serialize_instance(out or doc)


def get_flow_instance(tenant_database: str, instance_id: str) -> dict:
    oid = _validate_object_id(instance_id)
    db = get_tenant_db(tenant_database)
    doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Flow instance not found")
    return _serialize_instance(doc)

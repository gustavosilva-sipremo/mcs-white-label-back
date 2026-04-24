# app/services/flow_instance_service.py
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia
from app.services import flow_service, questionnaire_service, team_service

FLOW_INSTANCES_COLLECTION = "flow_instances"
FLOW_OCCURRENCES_COLLECTION = "flow_occurrences"
FLOW_NOTIFICATION_LOG_COLLECTION = "flow_instance_notification_logs"


def _validate_object_id(sid: str) -> ObjectId:
    try:
        return ObjectId(sid)
    except InvalidId as e:
        raise ValueError("Invalid instance id") from e


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(x) for x in value]
    return value


def _serialize_instance(doc: dict) -> dict:
    out = _json_safe(dict(doc))
    out["_id"] = str(doc["_id"])
    out["flow_id"] = str(doc["flow_id"])
    if out.get("created_by") is not None:
        out["created_by"] = str(out["created_by"])
    if out.get("occurrence_id") is not None:
        out["occurrence_id"] = str(out["occurrence_id"])
    return out


def _user_snapshot(user: dict | None) -> dict[str, Any]:
    if not user:
        return {}
    return {
        "user_id": str(user.get("_id") or ""),
        "name": str(user.get("name") or "").strip(),
        "phone": user.get("phone"),
        "email": user.get("email"),
    }


def _steps_for_branch(doc: dict, branch: str) -> list[dict]:
    plan = doc.get("execution_plan")
    if not isinstance(plan, dict):
        return []
    sb = plan.get("stepsByBranch")
    if not isinstance(sb, dict):
        return []
    steps = sb.get(branch) or []
    return [s for s in steps if isinstance(s, dict)]


def _step_at_order(doc: dict, branch: str, order: int) -> dict | None:
    for s in _steps_for_branch(doc, branch):
        try:
            if int(s.get("order", -1)) == order:
                return s
        except (TypeError, ValueError):
            continue
    return None


def _next_order_after(doc: dict, branch: str, order: int) -> int | None:
    orders = sorted(
        int(s["order"])
        for s in _steps_for_branch(doc, branch)
        if "order" in s and str(s.get("order", "")).strip() != ""
    )
    try:
        o = int(order)
    except (TypeError, ValueError):
        return None
    nxt = [x for x in orders if x > o]
    return nxt[0] if nxt else None


def _node_cfg(doc: dict, node_id: str) -> dict[str, Any]:
    idx = doc.get("nodes_by_id")
    if not isinstance(idx, dict):
        return {}
    n = idx.get(node_id)
    if not isinstance(n, dict):
        return {}
    c = n.get("config")
    return c if isinstance(c, dict) else {}


def _actor_matches_block_auth(
    tenant_database: str,
    actor: dict,
    cfg: dict[str, Any],
) -> bool:
    uref = cfg.get("allowedUserRef")
    tref = cfg.get("allowedTeamRef")
    if not uref and not tref:
        return True
    aid = str(actor.get("_id") or "")
    if isinstance(uref, dict) and uref.get("id"):
        return aid == str(uref.get("id"))
    if isinstance(tref, dict) and tref.get("id"):
        tid = str(tref.get("id"))
        try:
            team = team_service.get_team_by_id(tenant_database, tid)
        except ValueError:
            return False
        members = team.get("member_user_ids") or []
        return aid in [str(x) for x in members]
    return True


def assert_user_may_act_on_instance(
    tenant_database: str,
    actor: dict | None,
    doc: dict,
) -> None:
    if not actor:
        raise ValueError("Authenticated user required")
    aid = str(actor.get("_id") or "")
    if str(doc.get("created_by") or "") == aid:
        return
    compass = doc.get("compass")
    if not isinstance(compass, dict):
        return
    branch = str(compass.get("branchKey", "")).strip()
    order = compass.get("stepOrder")
    if not branch or not isinstance(order, int):
        return
    step = _step_at_order(doc, branch, order)
    if not step:
        return
    nid = str(step.get("nodeId") or "")
    cfg = _node_cfg(doc, nid)
    if _actor_matches_block_auth(tenant_database, actor, cfg):
        return
    raise ValueError("You are not allowed to act on this step of the flow")


def _occurrence_title(doc: dict) -> str:
    name = str(doc.get("flow_name") or "Fluxo").strip()
    tb = doc.get("triggered_by") if isinstance(doc.get("triggered_by"), dict) else {}
    who = str(tb.get("name") or "").strip()
    if who:
        return f"{name} · {who}"
    return name


def _create_occurrence_if_needed(db, oid: ObjectId, now) -> ObjectId | None:
    fresh = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    if not fresh or fresh.get("occurrence_id"):
        return None
    title = _occurrence_title(fresh)
    occ = {
        "flow_instance_id": oid,
        "flow_id": fresh["flow_id"],
        "flow_version": int(fresh.get("flow_version") or 1),
        "status": "active",
        "title": title,
        "created_at": now,
        "updated_at": now,
        "triggered_by": deepcopy(fresh.get("triggered_by") or {}),
    }
    ins = db[FLOW_OCCURRENCES_COLLECTION].insert_one(occ)
    occ_id = ins.inserted_id
    db[FLOW_INSTANCES_COLLECTION].update_one(
        {"_id": oid},
        {"$set": {"occurrence_id": occ_id, "updated_at": now}},
    )
    return occ_id


def _run_notification_step(
    tenant_database: str,
    db,
    oid: ObjectId,
    doc: dict,
    *,
    node_id: str,
    order: int,
    acting_user: dict | None,
) -> dict[str, Any]:
    """Persist per-recipient log rows + summary event. Returns event dict."""
    now = now_brasilia()
    cfg = _node_cfg(doc, node_id)
    template_ref = cfg.get("templateRef") if isinstance(cfg.get("templateRef"), dict) else {}
    template_id = str(template_ref.get("id") or "").strip()
    template_name = ""
    snap = template_ref.get("snapshot")
    if isinstance(snap, dict):
        template_name = str(snap.get("name") or "").strip()

    channels = [
        str(c).strip().lower()
        for c in (cfg.get("channels") or [])
        if str(c).strip()
    ]
    recipient_refs = cfg.get("recipientUserRefs")
    if not isinstance(recipient_refs, list):
        recipient_refs = []

    notification_ids: list[str] = []
    deliveries: list[dict[str, Any]] = []

    for ref in recipient_refs:
        if not isinstance(ref, dict):
            continue
        uid = str(ref.get("id") or "").strip()
        rname = ""
        rs = ref.get("snapshot")
        if isinstance(rs, dict):
            rname = str(rs.get("name") or "").strip()
        for ch in channels or ["pwa"]:
            log_doc = {
                "flow_instance_id": oid,
                "node_id": node_id,
                "step_order": order,
                "template_id": template_id or None,
                "template_name": template_name or None,
                "recipient_user_id": uid or None,
                "recipient_name": rname or None,
                "channel": ch,
                "created_at": now,
                "acting_user_id": str(acting_user.get("_id")) if acting_user else None,
            }
            ins = db[FLOW_NOTIFICATION_LOG_COLLECTION].insert_one(log_doc)
            nid = str(ins.inserted_id)
            notification_ids.append(nid)
            deliveries.append(
                {
                    "notification_id": nid,
                    "recipient_user_id": uid,
                    "recipient_name": rname,
                    "channel": ch,
                    "template_id": template_id,
                    "template_name": template_name,
                },
            )

    ev = {
        "type": "notification_executed",
        "at": now,
        "node_id": node_id,
        "order": order,
        "notification_ids": notification_ids,
        "template": {"id": template_id, "name": template_name},
        "channels": channels,
        "deliveries": deliveries,
        "acting_user": _user_snapshot(acting_user),
    }
    return ev


def create_flow_instance(
    tenant_database: str,
    *,
    entry_branch_key: str,
    created_by: str | None,
    acting_user: dict | None,
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

    nodes_by_id = main.get("nodes_by_id")
    if not isinstance(nodes_by_id, dict):
        nodes_by_id = {}

    doc = {
        "flow_id": flow_oid,
        "flow_version": ver,
        "flow_name": str(main.get("flow_name") or ""),
        "execution_plan": deepcopy(plan),
        "nodes_by_id": deepcopy(nodes_by_id),
        "status": "active",
        "compass": {"branchKey": key, "stepOrder": min_order},
        "events": [
            {
                "type": "instance_started",
                "at": now,
                "entryBranchKey": key,
                "flowVersion": ver,
                "triggered_by": _user_snapshot(acting_user),
            },
        ],
        "summary": {"lastEvent": "instance_started"},
        "started_at": now,
        "ended_at": None,
        "triggered_by": _user_snapshot(acting_user),
        "data_submissions": [],
        "notification_events": [],
        "occurrence_id": None,
        "created_at": now,
        "updated_at": now,
        "created_by": created_by_oid,
        "client_request_id": str(client_request_id).strip() if client_request_id else None,
    }
    ins = db[FLOW_INSTANCES_COLLECTION].insert_one(doc)
    oid = ins.inserted_id
    _create_occurrence_if_needed(db, oid, now)
    out = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    if not out:
        raise ValueError("Failed to load new flow instance")
    return _serialize_instance(out)


def list_active_flow_instances(tenant_database: str, *, limit: int = 100) -> list[dict]:
    db = get_tenant_db(tenant_database)
    cur = (
        db[FLOW_INSTANCES_COLLECTION]
        .find({"status": "active"})
        .sort("updated_at", -1)
        .limit(max(1, min(limit, 200)))
    )
    return [_serialize_instance(d) for d in cur]


def advance_flow_instance(
    tenant_database: str,
    instance_id: str,
    *,
    payload: dict[str, Any] | None = None,
    acting_user: dict | None = None,
) -> dict:
    oid = _validate_object_id(instance_id)
    db = get_tenant_db(tenant_database)
    doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Flow instance not found")
    if str(doc.get("status")) != "active":
        raise ValueError("Flow instance is not active")

    assert_user_may_act_on_instance(tenant_database, acting_user, doc)

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

    step = _step_at_order(doc, branch, order)
    if not step:
        raise ValueError("Current compass step not found")

    node_id = str(step.get("nodeId") or "")
    block_type = str(step.get("blockType") or "").strip().lower()
    now = now_brasilia()
    pl = payload if isinstance(payload, dict) else {}

    if block_type == "data":
        answers = pl.get("answers")
        if not isinstance(answers, dict):
            raise ValueError("payload.answers (object) is required for data steps")

        cfg = _node_cfg(doc, node_id)
        form_ref = cfg.get("formRef") if isinstance(cfg.get("formRef"), dict) else {}
        form_id = str(form_ref.get("id") or "").strip()
        if not form_id:
            raise ValueError("Data block has no formRef")

        try:
            qdoc = questionnaire_service.get_questionnaire_by_id(
                tenant_database,
                form_id,
            )
        except ValueError as e:
            raise ValueError(f"Questionnaire not found: {e}") from e

        qs = qdoc.get("questions") if isinstance(qdoc.get("questions"), list) else []
        questions_snapshot = []
        for q in qs:
            if not isinstance(q, dict):
                continue
            qid = q.get("id") if q.get("id") is not None else q.get("_id")
            questions_snapshot.append(
                {
                    "id": str(qid or ""),
                    "title": str(q.get("title") or ""),
                    "type": str(q.get("type") or ""),
                },
            )

        submission = {
            "node_id": node_id,
            "order": order,
            "form_id": form_id,
            "form_snapshot": {
                "id": form_id,
                "name": str(qdoc.get("name") or ""),
            },
            "questions_snapshot": questions_snapshot,
            "answers": _json_safe(answers),
            "finished_at": now,
            "submitted_by": _user_snapshot(acting_user),
        }

        submissions = list(doc.get("data_submissions") or [])
        submissions.append(submission)

        ev_data = {
            "type": "data_completed",
            "at": now,
            "branchKey": branch,
            "order": order,
            "node_id": node_id,
            "form_id": form_id,
            "acting_user": _user_snapshot(acting_user),
        }

        next_o = _next_order_after(doc, branch, order)
        if next_o is None:
            raise ValueError("No step after data block")

        db[FLOW_INSTANCES_COLLECTION].update_one(
            {"_id": oid},
            {
                "$push": {"events": {"$each": [ev_data]}},
                "$set": {
                    "data_submissions": submissions,
                    "compass": {"branchKey": branch, "stepOrder": next_o},
                    "updated_at": now,
                    "summary.lastEvent": "data_completed",
                },
            },
        )

        doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid}) or doc
        doc["data_submissions"] = submissions
        doc["compass"] = {"branchKey": branch, "stepOrder": next_o}

        while True:
            st = _step_at_order(doc, branch, doc["compass"]["stepOrder"])
            if not st or str(st.get("blockType") or "").lower() != "notification":
                break
            nid = str(st.get("nodeId") or "")
            ord_i = int(st["order"])
            assert_user_may_act_on_instance(tenant_database, acting_user, doc)
            nev = _run_notification_step(
                tenant_database,
                db,
                oid,
                doc,
                node_id=nid,
                order=ord_i,
                acting_user=acting_user,
            )
            nevents = list(doc.get("notification_events") or [])
            nevents.append(nev)

            next_after = _next_order_after(doc, branch, ord_i)
            if next_after is None:
                db[FLOW_INSTANCES_COLLECTION].update_one(
                    {"_id": oid},
                    {
                        "$push": {"events": nev},
                        "$set": {
                            "notification_events": nevents,
                            "status": "completed",
                            "ended_at": now,
                            "compass": doc["compass"],
                            "updated_at": now,
                            "summary.lastEvent": "branch_completed",
                        },
                    },
                )
                doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
                return _serialize_instance(doc or {})

            db[FLOW_INSTANCES_COLLECTION].update_one(
                {"_id": oid},
                {
                    "$push": {"events": nev},
                    "$set": {
                        "notification_events": nevents,
                        "compass": {"branchKey": branch, "stepOrder": next_after},
                        "updated_at": now,
                        "summary.lastEvent": "notification_executed",
                    },
                },
            )
            doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid}) or doc

        out = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
        return _serialize_instance(out or doc)

    if block_type == "notification":
        nev = _run_notification_step(
            tenant_database,
            db,
            oid,
            doc,
            node_id=node_id,
            order=order,
            acting_user=acting_user,
        )
        nevents = list(doc.get("notification_events") or [])
        nevents.append(nev)

        next_o = _next_order_after(doc, branch, order)
        if next_o is None:
            db[FLOW_INSTANCES_COLLECTION].update_one(
                {"_id": oid},
                {
                    "$push": {"events": nev},
                    "$set": {
                        "notification_events": nevents,
                        "status": "completed",
                        "ended_at": now,
                        "updated_at": now,
                        "summary.lastEvent": "branch_completed",
                    },
                },
            )
        else:
            db[FLOW_INSTANCES_COLLECTION].update_one(
                {"_id": oid},
                {
                    "$push": {"events": nev},
                    "$set": {
                        "notification_events": nevents,
                        "compass": {"branchKey": branch, "stepOrder": next_o},
                        "updated_at": now,
                        "summary.lastEvent": "notification_executed",
                    },
                },
            )
        doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
        return _serialize_instance(doc or {})

    if block_type == "action":
        cfg = _node_cfg(doc, node_id)
        kind = str(cfg.get("kind") or "").strip()
        if kind == "finish_occurrence":
            conf = pl.get("confirm")
            if conf not in (True, "true", 1, "1"):
                raise ValueError("payload.confirm must be true to finish occurrence")
        ev = {
            "type": "action_executed",
            "at": now,
            "branchKey": branch,
            "order": order,
            "node_id": node_id,
            "kind": kind,
            "acting_user": _user_snapshot(acting_user),
            "payload": _json_safe(pl),
        }
        next_o = _next_order_after(doc, branch, order)
        if next_o is None:
            db[FLOW_INSTANCES_COLLECTION].update_one(
                {"_id": oid},
                {
                    "$push": {"events": ev},
                    "$set": {
                        "status": "completed",
                        "ended_at": now,
                        "updated_at": now,
                        "summary.lastEvent": "branch_completed",
                    },
                },
            )
        else:
            db[FLOW_INSTANCES_COLLECTION].update_one(
                {"_id": oid},
                {
                    "$push": {"events": ev},
                    "$set": {
                        "compass": {"branchKey": branch, "stepOrder": next_o},
                        "updated_at": now,
                        "summary.lastEvent": "action_executed",
                    },
                },
            )
        doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
        return _serialize_instance(doc or {})

    if block_type == "gateway":
        raise ValueError("Gateway steps are not supported on Home runtime yet")

    raise ValueError(f"Cannot advance unsupported block type: {block_type!r}")


def end_flow_instance_by_user(
    tenant_database: str,
    instance_id: str,
    *,
    acting_user: dict | None = None,
) -> dict:
    """
    Mark an active instance as completed from the Home card (user chose to end
    the occurrence without advancing the current compass step).
    """
    oid = _validate_object_id(instance_id)
    db = get_tenant_db(tenant_database)
    doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Flow instance not found")
    if str(doc.get("status")) != "active":
        raise ValueError("Flow instance is not active")

    assert_user_may_act_on_instance(tenant_database, acting_user, doc)

    compass = doc.get("compass")
    if not isinstance(compass, dict):
        raise ValueError("Instance has no compass")
    branch = str(compass.get("branchKey", "")).strip()
    order = compass.get("stepOrder")
    ord_i = int(order) if isinstance(order, int) else -1

    now = now_brasilia()
    ev = {
        "type": "occurrence_ended_by_user",
        "at": now,
        "branchKey": branch,
        "order": ord_i,
        "acting_user": _user_snapshot(acting_user),
    }

    db[FLOW_INSTANCES_COLLECTION].update_one(
        {"_id": oid},
        {
            "$push": {"events": ev},
            "$set": {
                "status": "completed",
                "ended_at": now,
                "updated_at": now,
                "summary.lastEvent": "occurrence_ended_by_user",
            },
        },
    )
    out = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    return _serialize_instance(out or {})


def get_flow_instance(
    tenant_database: str,
    instance_id: str,
    *,
    actor: dict | None = None,
) -> dict:
    oid = _validate_object_id(instance_id)
    db = get_tenant_db(tenant_database)
    doc = db[FLOW_INSTANCES_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Flow instance not found")
    if actor is not None:
        assert_user_may_act_on_instance(tenant_database, actor, doc)
    return _serialize_instance(doc)

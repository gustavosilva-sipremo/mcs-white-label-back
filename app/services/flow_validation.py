# app/services/flow_validation.py
"""
Structural and semantic validation for flow graphs persisted as React Flow JSON.
"""
from __future__ import annotations

import re
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.services import (
    questionnaire_service,
    notification_template_service,
    team_service,
    tenant_list_service,
    user_service,
)

STRUCTURAL_TYPES = frozenset({"start", "end"})
INTERMEDIATE_TYPES = frozenset(
    {"trigger", "data", "notification", "action", "gateway"},
)
ALL_BLOCK_TYPES = STRUCTURAL_TYPES | INTERMEDIATE_TYPES

NOTIFICATION_BLOCK_CHANNELS = frozenset({"email", "sms", "whatsapp", "pwa"})


def _node_block_type(node: dict) -> str | None:
    data = node.get("data")
    if not isinstance(data, dict):
        return None
    bt = data.get("blockType")
    if bt is None:
        return None
    return str(bt).strip().lower()


def _edges_list(graph: dict) -> list[dict]:
    edges = graph.get("edges")
    return edges if isinstance(edges, list) else []


def _nodes_list(graph: dict) -> list[dict]:
    nodes = graph.get("nodes")
    return nodes if isinstance(nodes, list) else []


def _build_adjacency(edges: list[dict]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        s = e.get("source")
        t = e.get("target")
        if not s or not t:
            continue
        s, t = str(s), str(t)
        adj.setdefault(s, []).append(t)
    return adj


def _build_reverse_adjacency(edges: list[dict]) -> dict[str, list[str]]:
    radj: dict[str, list[str]] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        s = e.get("source")
        t = e.get("target")
        if not s or not t:
            continue
        s, t = str(s), str(t)
        radj.setdefault(t, []).append(s)
    return radj


def _reachable_from(start_id: str, adj: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [start_id]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for nb in adj.get(n, []):
            if nb not in seen:
                stack.append(nb)
    return seen


def validate_flow_graph_structure(graph: dict) -> tuple[str, str, list[dict]]:
    """
    Returns (start_node_id, end_node_id, logic_nodes) or raises ValueError.
    """
    nodes = _nodes_list(graph)
    edges = _edges_list(graph)

    start_ids: list[str] = []
    end_ids: list[str] = []
    logic_nodes: list[dict] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not nid:
            raise ValueError("Each node must have an id")
        nid = str(nid)
        bt = _node_block_type(node)
        if not bt:
            raise ValueError(f"Node {nid}: data.blockType is required")
        if bt not in ALL_BLOCK_TYPES:
            raise ValueError(
                f"Node {nid}: invalid blockType '{bt}'. "
                f"Allowed: {', '.join(sorted(ALL_BLOCK_TYPES))}",
            )
        if bt in STRUCTURAL_TYPES:
            if bt == "start":
                start_ids.append(nid)
            else:
                end_ids.append(nid)
        else:
            logic_nodes.append(node)

    if len(start_ids) != 1:
        raise ValueError("Flow must contain exactly one Start block")
    if len(end_ids) != 1:
        raise ValueError("Flow must contain exactly one End block")

    start_id = start_ids[0]
    end_id = end_ids[0]

    adj = _build_adjacency(edges)
    radj = _build_reverse_adjacency(edges)

    forward = _reachable_from(start_id, adj)
    if end_id not in forward:
        raise ValueError("End block is not reachable from Start block")

    backward = _reachable_from(end_id, radj)
    if start_id not in backward:
        raise ValueError("Start block cannot reach End block through edges")

    all_ids = {str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id")}
    for nid in all_ids:
        if nid == start_id or nid == end_id:
            continue
        if nid not in forward:
            raise ValueError(f"Orphan node '{nid}': not reachable from Start")
        if nid not in backward:
            raise ValueError(f"Orphan node '{nid}': cannot reach End")

    return start_id, end_id, logic_nodes


def _validate_ref_object(
    tenant_database: str,
    ref: Any,
    *,
    kind: str,
    loader,
) -> None:
    if ref is None:
        return
    if not isinstance(ref, dict):
        raise ValueError(f"{kind}: reference must be an object")
    rid = ref.get("id")
    if not rid or not str(rid).strip():
        raise ValueError(f"{kind}: reference id is required")
    rid = str(rid).strip()
    try:
        doc = loader(tenant_database, rid)
    except ValueError as e:
        raise ValueError(f"{kind}: {e}") from e
    snap = ref.get("snapshot")
    if snap is not None and not isinstance(snap, dict):
        raise ValueError(f"{kind}: snapshot must be an object when provided")


def validate_block_configs(tenant_database: str, logic_nodes: list[dict]) -> None:
    """Validate known config references against tenant collections."""
    trigger_branch_rows: list[tuple[str, str]] = []
    for node in logic_nodes:
        nid = str(node.get("id", "?"))
        data = node.get("data")
        if not isinstance(data, dict):
            continue
        raw_cfg = data.get("config")
        if raw_cfg is None:
            cfg: dict = {}
        elif isinstance(raw_cfg, dict):
            cfg = raw_cfg
        else:
            raise ValueError(f"Node {nid}: config must be an object")

        bt = _node_block_type(node)

        if bt == "trigger":
            mode = cfg.get("mode")
            if mode is not None:
                m = str(mode).strip().lower()
                if m not in ("preset", "customizable"):
                    raise ValueError(
                        f"Node {nid}: trigger config.mode must be 'preset' or 'customizable'",
                    )
            m_final = str(mode or "preset").strip().lower()
            branch_key = str(cfg.get("branchKey", "")).strip()
            if not branch_key:
                raise ValueError(
                    f"Node {nid}: trigger config.branchKey is required",
                )
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", branch_key):
                raise ValueError(
                    f"Node {nid}: trigger branchKey may contain only letters, "
                    "digits, hyphen and underscore",
                )
            try:
                ObjectId(branch_key)
            except InvalidId:
                pass
            else:
                try:
                    questionnaire_service.get_questionnaire_by_id(
                        tenant_database,
                        branch_key,
                    )
                except ValueError as e:
                    raise ValueError(
                        f"Node {nid}: trigger branchKey (questionnaire id): {e}",
                    ) from e
            trigger_branch_rows.append((nid, branch_key))
            home_cta = cfg.get("homeCtaLabel")
            if home_cta is not None and len(str(home_cta)) > 200:
                raise ValueError(
                    f"Node {nid}: trigger homeCtaLabel must be at most 200 characters",
                )
            summary = cfg.get("summary")
            if summary is not None and len(str(summary)) > 300:
                raise ValueError(
                    f"Node {nid}: trigger summary must be at most 300 characters",
                )
            if m_final == "customizable":
                try:
                    ObjectId(branch_key)
                    form_questionnaire_branch = True
                except InvalidId:
                    form_questionnaire_branch = False

                if not form_questionnaire_branch:
                    fields = cfg.get("fields")
                    if not isinstance(fields, list) or len(fields) == 0:
                        raise ValueError(
                            f"Node {nid}: customizable trigger (non-questionnaire "
                            "branchKey) requires config.fields with at least one field",
                        )
                    key_pat = re.compile(r"^[a-z][a-z0-9_]*$")
                    for i, field in enumerate(fields):
                        if not isinstance(field, dict):
                            raise ValueError(
                                f"Node {nid}: trigger fields[{i}] must be an object",
                            )
                        fk = str(field.get("key", "")).strip()
                        fl = str(field.get("label", "")).strip()
                        if not fk or not key_pat.match(fk):
                            raise ValueError(
                                f"Node {nid}: trigger fields[{i}].key must be "
                                "snake_case starting with a letter (a-z)",
                            )
                        if not fl:
                            raise ValueError(
                                f"Node {nid}: trigger fields[{i}].label is required",
                            )
                        ft = field.get("type")
                        if ft is not None and str(ft).strip().lower() not in (
                            "text",
                            "textarea",
                            "number",
                        ):
                            raise ValueError(
                                f"Node {nid}: trigger fields[{i}].type must be "
                                "text, textarea, or number when set",
                            )

        if bt == "data":
            ref = cfg.get("formRef")
            if ref is not None:
                _validate_ref_object(
                    tenant_database,
                    ref,
                    kind=f"Node {nid} formRef",
                    loader=questionnaire_service.get_questionnaire_by_id,
                )

        if bt == "notification":
            ref = cfg.get("templateRef")
            if ref is not None:
                _validate_ref_object(
                    tenant_database,
                    ref,
                    kind=f"Node {nid} templateRef",
                    loader=notification_template_service.get_notification_template_by_id,
                )
                template_doc = (
                    notification_template_service.get_notification_template_by_id(
                        tenant_database,
                        str(ref.get("id", "")).strip(),
                    )
                )
                ch_raw = cfg.get("channels")
                if not isinstance(ch_raw, list) or len(ch_raw) == 0:
                    raise ValueError(
                        f"Node {nid}: notification config.channels must be a non-empty "
                        "list when templateRef is set",
                    )
                tmpl_channels = {
                    str(x).strip().lower()
                    for x in (template_doc.get("channels") or [])
                }
                seen_ch: set[str] = set()
                for i, c in enumerate(ch_raw):
                    s = str(c).strip().lower()
                    if s not in NOTIFICATION_BLOCK_CHANNELS:
                        raise ValueError(
                            f"Node {nid}: notification channels[{i}] must be one of "
                            f"email, sms, whatsapp, pwa (got {c!r})",
                        )
                    if s not in tmpl_channels:
                        raise ValueError(
                            f"Node {nid}: notification channel {s!r} is not enabled on "
                            "the selected template",
                        )
                    seen_ch.add(s)
                if not seen_ch:
                    raise ValueError(
                        f"Node {nid}: notification channels must include at least one "
                        "valid channel",
                    )
            for key, loader in (
                ("recipientUserRefs", user_service.get_user_by_id),
                ("recipientTeamRefs", team_service.get_team_by_id),
            ):
                arr = cfg.get(key)
                if arr is None:
                    continue
                if not isinstance(arr, list):
                    raise ValueError(f"Node {nid}: {key} must be a list")
                for i, item in enumerate(arr):
                    _validate_ref_object(
                        tenant_database,
                        item,
                        kind=f"Node {nid} {key}[{i}]",
                        loader=loader,
                    )

        if bt == "gateway":
            ref = cfg.get("listRef")
            if ref is not None:
                _validate_ref_object(
                    tenant_database,
                    ref,
                    kind=f"Node {nid} listRef",
                    loader=tenant_list_service.get_generic_list_by_id,
                )

    seen_branch: dict[str, str] = {}
    for nid, bk in trigger_branch_rows:
        if bk in seen_branch:
            raise ValueError(
                f"Duplicate trigger branchKey '{bk}' on nodes "
                f"'{seen_branch[bk]}' and '{nid}'",
            )
        seen_branch[bk] = nid


def _append_ref(
    refs: list[dict[str, Any]],
    node_id: str,
    field: str,
    ref: Any,
) -> None:
    if not isinstance(ref, dict):
        return
    if not ref.get("id"):
        return
    refs.append(
        {
            "nodeId": node_id,
            "field": field,
            "id": str(ref.get("id", "")).strip(),
            "snapshot": ref.get("snapshot"),
        },
    )


def build_blocks_index(
    graph: dict,
    start_id: str,
    end_id: str,
    logic_nodes: list[dict],
) -> dict[str, Any]:
    """Normalized summary for dashboards / future runtime."""
    triggers: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []

    for node in logic_nodes:
        bt = _node_block_type(node)
        nid = str(node.get("id", ""))
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        cfg = data.get("config") if isinstance(data.get("config"), dict) else {}
        if bt == "trigger":
            flds = cfg.get("fields")
            field_count = len(flds) if isinstance(flds, list) else 0
            triggers.append(
                {
                    "nodeId": nid,
                    "mode": cfg.get("mode"),
                    "branchKey": cfg.get("branchKey"),
                    "label": data.get("label"),
                    "homeCtaLabel": cfg.get("homeCtaLabel"),
                    "summary": cfg.get("summary"),
                    "fieldCount": field_count,
                },
            )
        if bt == "data":
            _append_ref(refs, nid, "formRef", cfg.get("formRef"))
        if bt == "notification":
            _append_ref(refs, nid, "templateRef", cfg.get("templateRef"))
            for item in cfg.get("recipientUserRefs") or []:
                _append_ref(refs, nid, "recipientUserRefs", item)
            for item in cfg.get("recipientTeamRefs") or []:
                _append_ref(refs, nid, "recipientTeamRefs", item)
        if bt == "gateway":
            _append_ref(refs, nid, "listRef", cfg.get("listRef"))

    return {
        "startNodeId": start_id,
        "endNodeId": end_id,
        "triggers": triggers,
        "entityRefs": refs,
        "intermediateCount": len(logic_nodes),
    }

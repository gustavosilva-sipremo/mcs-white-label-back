# app/services/flow_validation.py
"""
Structural and semantic validation for flow graphs persisted as React Flow JSON.
"""
from __future__ import annotations

from typing import Any

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
    for node in logic_nodes:
        nid = str(node.get("id", "?"))
        data = node.get("data")
        if not isinstance(data, dict):
            continue
        cfg = data.get("config")
        if cfg is None:
            continue
        if not isinstance(cfg, dict):
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
            triggers.append(
                {
                    "nodeId": nid,
                    "mode": cfg.get("mode"),
                    "branchKey": cfg.get("branchKey"),
                    "label": data.get("label"),
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

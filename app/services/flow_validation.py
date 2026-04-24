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


def _nodes_list(graph: dict) -> list[dict]:
    nodes = graph.get("nodes")
    return nodes if isinstance(nodes, list) else []


def validate_flow_graph_structure(graph: dict) -> tuple[str, str, list[dict]]:
    """
    Returns (start_node_id, end_node_id, logic_nodes) or raises ValueError.

    Edges are not validated for connectivity; they are optional layout hints only.
    """
    nodes = _nodes_list(graph)

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

    return start_id, end_id, logic_nodes


def _validate_interaction_auth(
    tenant_database: str,
    node_label: str,
    cfg: dict,
) -> None:
    """Optional allowedUserRef / allowedTeamRef (mutually exclusive) on data & trigger."""
    u = cfg.get("allowedUserRef")
    t = cfg.get("allowedTeamRef")
    if u is None and t is None:
        return
    if u is not None and t is not None:
        raise ValueError(
            f"{node_label}: allowedUserRef and allowedTeamRef are mutually exclusive",
        )
    if u is not None:
        _validate_ref_object(
            tenant_database,
            u,
            kind=f"{node_label} allowedUserRef",
            loader=user_service.get_user_by_id,
        )
    if t is not None:
        _validate_ref_object(
            tenant_database,
            t,
            kind=f"{node_label} allowedTeamRef",
            loader=team_service.get_team_by_id,
        )


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
    customizable_trigger_ids: list[str] = []
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
            raw_extras = cfg.get("extraBranchKeys")
            extra_slugs: list[str] = []
            if raw_extras is not None:
                if not isinstance(raw_extras, list):
                    raise ValueError(
                        f"Node {nid}: trigger extraBranchKeys must be a list when set",
                    )
                for item in raw_extras:
                    s = str(item).strip() if item is not None else ""
                    if s:
                        extra_slugs.append(s)

            if m_final == "preset" and extra_slugs:
                raise ValueError(
                    f"Node {nid}: trigger extraBranchKeys is only allowed when "
                    "mode is 'customizable'",
                )

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

                bk_extra_pat = re.compile(r"^[a-zA-Z0-9_-]+$")
                for j, ek in enumerate(extra_slugs):
                    if ek == branch_key:
                        raise ValueError(
                            f"Node {nid}: extraBranchKeys[{j}] duplicates branchKey",
                        )
                    if not bk_extra_pat.fullmatch(ek):
                        raise ValueError(
                            f"Node {nid}: extraBranchKeys[{j}] may contain only letters, "
                            "digits, hyphen and underscore",
                        )
                    try:
                        ObjectId(ek)
                    except InvalidId:
                        pass
                    else:
                        raise ValueError(
                            f"Node {nid}: extraBranchKeys[{j}] must be a slug identifier, "
                            "not an ObjectId",
                        )

            combined_keys = [branch_key, *extra_slugs]
            if len(combined_keys) != len(set(combined_keys)):
                raise ValueError(
                    f"Node {nid}: duplicate branchKey values among branchKey and "
                    "extraBranchKeys",
                )
            for bk_one in combined_keys:
                trigger_branch_rows.append((nid, bk_one))

            if m_final == "customizable":
                customizable_trigger_ids.append(nid)
            _validate_interaction_auth(tenant_database, f"Node {nid}", cfg)

        if bt == "data":
            ref = cfg.get("formRef")
            if ref is not None:
                _validate_ref_object(
                    tenant_database,
                    ref,
                    kind=f"Node {nid} formRef",
                    loader=questionnaire_service.get_questionnaire_by_id,
                )
            _validate_interaction_auth(tenant_database, f"Node {nid}", cfg)

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
            tc = cfg.get("triggerCondition")
            if tc is not None:
                if not isinstance(tc, dict):
                    raise ValueError(
                        f"Node {nid}: notification triggerCondition must be an object",
                    )
                vp = str(tc.get("valuePath", "")).strip()
                mv = str(tc.get("matchValue", "")).strip()
                if bool(vp) ^ bool(mv):
                    raise ValueError(
                        f"Node {nid}: notification triggerCondition requires both "
                        "valuePath and matchValue when set",
                    )
                if vp or mv:
                    if len(vp) > 200:
                        raise ValueError(
                            f"Node {nid}: notification triggerCondition.valuePath "
                            "must be at most 200 characters",
                        )
                    if len(mv) > 500:
                        raise ValueError(
                            f"Node {nid}: notification triggerCondition.matchValue "
                            "must be at most 500 characters",
                        )
            afc = cfg.get("advanceFlowCompass")
            if afc is not None and not isinstance(afc, bool):
                raise ValueError(
                    f"Node {nid}: notification advanceFlowCompass must be a boolean",
                )
            for key, loader in (
                ("recipientUserRefs", user_service.get_user_by_id),
                ("recipientTeamRefs", team_service.get_team_by_id),
                ("recipientListRefs", tenant_list_service.get_generic_list_by_id),
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

            vp_raw = cfg.get("valuePath")
            brules = cfg.get("branchRules")
            def_bk_raw = cfg.get("defaultBranchKey")
            vp_s = str(vp_raw).strip() if vp_raw is not None else ""
            has_routing = bool(vp_s) or brules is not None

            if has_routing:
                if not vp_s:
                    raise ValueError(
                        f"Node {nid}: gateway valuePath is required when branch "
                        "routing is configured",
                    )
                if len(vp_s) > 200:
                    raise ValueError(
                        f"Node {nid}: gateway valuePath must be at most 200 characters",
                    )
                if not isinstance(brules, list) or len(brules) == 0:
                    raise ValueError(
                        f"Node {nid}: gateway branchRules must be a non-empty list when "
                        "routing is configured",
                    )
                bk_pat = re.compile(r"^[a-zA-Z0-9_-]+$")
                seen_when_lower: set[str] = set()
                for i, rule in enumerate(brules):
                    if not isinstance(rule, dict):
                        raise ValueError(
                            f"Node {nid}: gateway branchRules[{i}] must be an object",
                        )
                    wv = str(rule.get("whenValue", "")).strip()
                    bk = str(rule.get("branchKey", "")).strip()
                    if not wv:
                        raise ValueError(
                            f"Node {nid}: gateway branchRules[{i}].whenValue is required",
                        )
                    if not bk or not bk_pat.match(bk):
                        raise ValueError(
                            f"Node {nid}: gateway branchRules[{i}].branchKey must be "
                            "non-empty and contain only letters, digits, hyphen and underscore",
                        )
                    wl = wv.lower()
                    if wl in seen_when_lower:
                        raise ValueError(
                            f"Node {nid}: duplicate gateway branchRules whenValue "
                            f"(case-insensitive): {wv!r}",
                        )
                    seen_when_lower.add(wl)
                if def_bk_raw is not None:
                    ds = str(def_bk_raw).strip()
                    if ds and not bk_pat.match(ds):
                        raise ValueError(
                            f"Node {nid}: gateway defaultBranchKey may contain only "
                            "letters, digits, hyphen and underscore",
                        )

    if len(customizable_trigger_ids) > 1:
        joined = ", ".join(customizable_trigger_ids)
        raise ValueError(
            "Flow may contain at most one customizable trigger block "
            f"(found: {joined})",
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
            extra_raw = cfg.get("extraBranchKeys")
            extra_list: list[str] = []
            if isinstance(extra_raw, list):
                for x in extra_raw:
                    s = str(x).strip() if x is not None else ""
                    if s:
                        extra_list.append(s)
            row: dict[str, Any] = {
                "nodeId": nid,
                "mode": cfg.get("mode"),
                "branchKey": cfg.get("branchKey"),
                "label": data.get("label"),
                "homeCtaLabel": cfg.get("homeCtaLabel"),
                "summary": cfg.get("summary"),
                "fieldCount": field_count,
            }
            if extra_list:
                row["extraBranchKeys"] = extra_list
            triggers.append(row)
            _append_ref(refs, nid, "allowedUserRef", cfg.get("allowedUserRef"))
            _append_ref(refs, nid, "allowedTeamRef", cfg.get("allowedTeamRef"))
        if bt == "data":
            _append_ref(refs, nid, "formRef", cfg.get("formRef"))
            _append_ref(refs, nid, "allowedUserRef", cfg.get("allowedUserRef"))
            _append_ref(refs, nid, "allowedTeamRef", cfg.get("allowedTeamRef"))
        if bt == "notification":
            _append_ref(refs, nid, "templateRef", cfg.get("templateRef"))
            for item in cfg.get("recipientUserRefs") or []:
                _append_ref(refs, nid, "recipientUserRefs", item)
            for item in cfg.get("recipientTeamRefs") or []:
                _append_ref(refs, nid, "recipientTeamRefs", item)
            for item in cfg.get("recipientListRefs") or []:
                _append_ref(refs, nid, "recipientListRefs", item)
        if bt == "gateway":
            _append_ref(refs, nid, "listRef", cfg.get("listRef"))

    return {
        "startNodeId": start_id,
        "endNodeId": end_id,
        "triggers": triggers,
        "entityRefs": refs,
        "intermediateCount": len(logic_nodes),
    }


def _node_config_dict(node: dict) -> dict:
    data = node.get("data")
    if not isinstance(data, dict):
        return {}
    raw = data.get("config")
    return raw if isinstance(raw, dict) else {}


def _collect_trigger_entry_keys(cfg: dict) -> list[str]:
    keys: list[str] = []
    bk = str(cfg.get("branchKey", "")).strip()
    if bk:
        keys.append(bk)
    ex = cfg.get("extraBranchKeys")
    if isinstance(ex, list):
        for x in ex:
            s = str(x).strip() if x is not None else ""
            if s and s not in keys:
                keys.append(s)
    return keys


def _parse_flow_step_order(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw == int(raw):
        return int(raw)
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        try:
            return int(raw.strip())
        except ValueError:
            return None
    return None


def build_execution_plan(logic_nodes: list[dict]) -> dict[str, Any]:
    """Materialized plan for home/runtime (branch lanes + ordered steps)."""
    entry_branches: list[dict[str, Any]] = []
    steps_by_branch: dict[str, list[dict[str, Any]]] = {}
    gateways: list[dict[str, Any]] = []
    terminals: list[dict[str, Any]] = []
    unplaced: list[str] = []

    for node in logic_nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id", ""))
        bt = _node_block_type(node)
        if not bt:
            continue
        cfg = _node_config_dict(node)
        if bt == "trigger":
            entry_branches.append(
                {"nodeId": nid, "branchKeys": _collect_trigger_entry_keys(cfg)},
            )
            continue
        if bt in ("data", "notification", "action", "gateway"):
            fbk = str(cfg.get("flowBranchKey", "")).strip()
            order = _parse_flow_step_order(cfg.get("flowStepOrder"))
            if fbk and order is not None:
                steps_by_branch.setdefault(fbk, []).append(
                    {"nodeId": nid, "blockType": bt, "order": order},
                )
            else:
                unplaced.append(nid)
            if bt == "gateway":
                brules = cfg.get("branchRules")
                gateways.append(
                    {
                        "nodeId": nid,
                        "valuePath": str(cfg.get("valuePath", "")).strip() or None,
                        "branchRules": brules if isinstance(brules, list) else None,
                        "defaultBranchKey": str(cfg.get("defaultBranchKey", "")).strip()
                        or None,
                    },
                )
            if bt == "action" and str(cfg.get("kind", "")).strip() == "finish_occurrence":
                terminals.append(
                    {
                        "nodeId": nid,
                        "branchKey": fbk,
                        "kind": "finish_occurrence",
                    },
                )
            continue

    for _bk, steps in steps_by_branch.items():
        steps.sort(key=lambda s: (s["order"], s["nodeId"]))

    return {
        "entryBranches": entry_branches,
        "stepsByBranch": steps_by_branch,
        "gateways": gateways,
        "terminals": terminals,
        "unplacedNodeIds": unplaced,
    }


def validate_execution_plan_rules(logic_nodes: list[dict]) -> None:
    """Placement uniqueness and gateway targets vs known branch lanes."""
    placed: dict[tuple[str, int], str] = {}
    entry_keys: set[str] = set()
    step_branch_keys: set[str] = set()

    for node in logic_nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id", "?"))
        bt = _node_block_type(node)
        cfg = _node_config_dict(node)
        if bt == "trigger":
            entry_keys.update(_collect_trigger_entry_keys(cfg))
            continue
        if bt in ("data", "notification", "action", "gateway"):
            fbk = str(cfg.get("flowBranchKey", "")).strip()
            order = _parse_flow_step_order(cfg.get("flowStepOrder"))
            if fbk and order is not None:
                key = (fbk, order)
                if key in placed:
                    raise ValueError(
                        f"Duplicate flow placement (flowBranchKey, flowStepOrder) "
                        f"{key!r} on nodes '{placed[key]}' and '{nid}'",
                    )
                placed[key] = nid
                step_branch_keys.add(fbk)

    known = entry_keys | step_branch_keys

    for node in logic_nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id", "?"))
        if _node_block_type(node) != "gateway":
            continue
        cfg = _node_config_dict(node)
        vp_raw = cfg.get("valuePath")
        brules = cfg.get("branchRules")
        vp_s = str(vp_raw).strip() if vp_raw is not None else ""
        has_routing = bool(vp_s) or brules is not None
        if not has_routing:
            continue
        if not isinstance(brules, list):
            continue
        for i, rule in enumerate(brules):
            if not isinstance(rule, dict):
                continue
            bk = str(rule.get("branchKey", "")).strip()
            if bk and bk not in known:
                raise ValueError(
                    f"Node {nid}: gateway branchRules[{i}].branchKey {bk!r} "
                    "must match a trigger entry branch or a flowBranchKey on a placed block",
                )
        def_bk = str(cfg.get("defaultBranchKey", "")).strip()
        if def_bk and def_bk not in known:
            raise ValueError(
                f"Node {nid}: gateway defaultBranchKey {def_bk!r} "
                "must match a trigger entry branch or a flowBranchKey on a placed block",
            )

    non_trigger = [
        n
        for n in logic_nodes
        if isinstance(n, dict)
        and _node_block_type(n)
        and _node_block_type(n) != "trigger"
    ]
    if not non_trigger:
        return

    finish_count = 0
    for node in logic_nodes:
        if not isinstance(node, dict):
            continue
        if _node_block_type(node) != "action":
            continue
        cfg = _node_config_dict(node)
        if str(cfg.get("kind", "")).strip() == "finish_occurrence":
            finish_count += 1
    if finish_count == 0:
        raise ValueError(
            "Flow must contain at least one action block with kind "
            "'finish_occurrence' (terminal step) when non-trigger blocks exist",
        )


def _json_safe_for_plan(value: Any) -> Any:
    """Recursively convert BSON-ish values for JSON responses."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe_for_plan(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_for_plan(x) for x in value]
    return value


def build_nodes_runtime_snapshot(graph: dict) -> dict[str, dict[str, Any]]:
    """
    Intermediate flow blocks only: nodeId -> { blockType, label, config }.
    Used by Home/runtime without shipping the full React Flow graph.
    """
    out: dict[str, dict[str, Any]] = {}
    for node in _nodes_list(graph):
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not nid:
            continue
        nid = str(nid)
        bt = _node_block_type(node)
        if not bt or bt not in INTERMEDIATE_TYPES:
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        cfg = data.get("config")
        cfg_out = cfg if isinstance(cfg, dict) else {}
        out[nid] = _json_safe_for_plan(
            {
                "blockType": str(bt),
                "label": str(data.get("label") or ""),
                "config": cfg_out,
            },
        )
    return out

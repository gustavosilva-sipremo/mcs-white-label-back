from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia


def validate_object_id(team_id: str):
    try:
        return ObjectId(team_id)
    except InvalidId:
        raise ValueError("Invalid team_id")


def serialize_team(team: dict) -> dict:
    out = dict(team)
    out["_id"] = str(out["_id"])
    raw_ids = out.get("member_user_ids") or []
    out["member_user_ids"] = [str(x) for x in raw_ids]
    out["membersCount"] = len(out["member_user_ids"])
    return out


def _member_ids_from_strings(ids: list) -> list:
    out = []
    for uid in ids or []:
        if not uid:
            continue
        try:
            out.append(ObjectId(str(uid).strip()))
        except InvalidId:
            raise ValueError(f"Invalid member user id: {uid}")
    return out


def _validate_members_exist(db, member_oids: list):
    if not member_oids:
        return
    count = db.users.count_documents({"_id": {"$in": member_oids}})
    if count != len(member_oids):
        raise ValueError("One or more members were not found")


def list_teams(tenant_database: str):
    try:
        db = get_tenant_db(tenant_database)
        teams = list(db.teams.find({}).sort("name", 1))
        return [serialize_team(t) for t in teams]
    except Exception as e:
        raise RuntimeError(f"Erro ao listar equipes: {e}")


def create_team(tenant_database: str, data: dict):
    db = get_tenant_db(tenant_database)
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Team name is required")

    desc = data.get("description")
    if desc is not None:
        desc = str(desc).strip() or None

    member_oids = _member_ids_from_strings(data.get("member_user_ids", []))
    _validate_members_exist(db, member_oids)

    doc = {
        "name": name,
        "description": desc,
        "member_user_ids": member_oids,
        "created_at": now_brasilia(),
        "updated_at": now_brasilia(),
    }
    result = db.teams.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_team(doc)


def get_team_by_id(tenant_database: str, team_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(team_id)
    team = db.teams.find_one({"_id": oid})
    if not team:
        raise ValueError("Team not found")
    return serialize_team(team)


def update_team(tenant_database: str, team_id: str, data: dict):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(team_id)

    forbidden = ["_id", "created_at"]
    for f in forbidden:
        data.pop(f, None)

    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
        if not data["name"]:
            raise ValueError("Team name cannot be empty")

    if "description" in data:
        if data["description"] is None:
            pass
        else:
            data["description"] = str(data["description"]).strip() or None

    if "member_user_ids" in data and data["member_user_ids"] is not None:
        member_oids = _member_ids_from_strings(data["member_user_ids"])
        _validate_members_exist(db, member_oids)
        data["member_user_ids"] = member_oids

    if not data:
        raise ValueError("No fields provided for update")

    data["updated_at"] = now_brasilia()

    result = db.teams.update_one({"_id": oid}, {"$set": data})
    if result.matched_count == 0:
        raise ValueError("Team not found")

    return get_team_by_id(tenant_database, team_id)


def delete_team(tenant_database: str, team_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(team_id)
    res = db.teams.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise ValueError("Team not found")
    return {"message": "Team deleted successfully"}

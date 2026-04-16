from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.services import tenant_list_service
from app.utils.datetime_utils import now_brasilia

COLLECTION = "questionnaires"


def validate_object_id(qid: str):
    try:
        return ObjectId(qid)
    except InvalidId:
        raise ValueError("Invalid questionnaire id")


def _validate_list_references(tenant_database: str, questions: list) -> None:
    if not isinstance(questions, list):
        raise ValueError("questions must be a list")

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        qtype = q.get("type")
        if qtype not in ("single", "multiple"):
            continue
        mode = q.get("optionsMode") or "manual"
        if mode != "list":
            continue
        list_id = q.get("optionsListId")
        if not list_id or not str(list_id).strip():
            raise ValueError(
                f"Question at index {i}: optionsListId is required when optionsMode is 'list'",
            )
        try:
            tenant_list_service.get_generic_list_by_id(
                tenant_database,
                str(list_id).strip(),
            )
        except ValueError as e:
            raise ValueError(f"Question at index {i}: {e}") from e


def serialize_questionnaire(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    qs = out.get("questions")
    out["questions"] = qs if isinstance(qs, list) else []
    return out


def list_questionnaires(tenant_database: str):
    try:
        db = get_tenant_db(tenant_database)
        cursor = (
            db[COLLECTION]
            .find({})
            .sort([("updated_at", -1), ("name", 1)])
        )
        return [serialize_questionnaire(d) for d in cursor]
    except Exception as e:
        raise RuntimeError(f"Erro ao listar questionários: {e}")


def create_questionnaire(tenant_database: str, data: dict):
    db = get_tenant_db(tenant_database)
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Questionnaire name is required")

    desc = data.get("description")
    if desc is not None:
        desc = str(desc).strip()
    else:
        desc = ""

    questions = data.get("questions") or []
    if not isinstance(questions, list):
        raise ValueError("questions must be a list")

    _validate_list_references(tenant_database, questions)

    doc = {
        "name": name,
        "description": desc,
        "questions": questions,
        "created_at": now_brasilia(),
        "updated_at": now_brasilia(),
    }
    result = db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_questionnaire(doc)


def get_questionnaire_by_id(tenant_database: str, questionnaire_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(questionnaire_id)
    doc = db[COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Questionnaire not found")
    return serialize_questionnaire(doc)


def update_questionnaire(tenant_database: str, questionnaire_id: str, data: dict):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(questionnaire_id)
    current = db[COLLECTION].find_one({"_id": oid})
    if not current:
        raise ValueError("Questionnaire not found")

    for f in ["_id", "created_at"]:
        data.pop(f, None)

    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
        if not data["name"]:
            raise ValueError("Name cannot be empty")

    if "description" in data and data["description"] is not None:
        data["description"] = str(data["description"]).strip()

    if "questions" in data:
        qs = data["questions"]
        if qs is None:
            data["questions"] = []
        elif not isinstance(qs, list):
            raise ValueError("questions must be a list")
        _validate_list_references(tenant_database, data["questions"])

    if not data:
        raise ValueError("No fields provided for update")

    data["updated_at"] = now_brasilia()

    result = db[COLLECTION].update_one({"_id": oid}, {"$set": data})
    if result.matched_count == 0:
        raise ValueError("Questionnaire not found")

    return get_questionnaire_by_id(tenant_database, questionnaire_id)


def delete_questionnaire(tenant_database: str, questionnaire_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(questionnaire_id)
    res = db[COLLECTION].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise ValueError("Questionnaire not found")
    return {"message": "Questionnaire deleted successfully"}

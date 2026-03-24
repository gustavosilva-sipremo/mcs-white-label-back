import bcrypt
from datetime import datetime
from app.database.client import get_tenant_db


def list_users(tenant_slug: str):
    """
    Lista todos os usuários do tenant passado pelo slug.
    """
    try:
        db = get_tenant_db(tenant_slug)  # pega o DB correto dinamicamente
        users_cursor = db.users.find({})  # acessa a collection 'users'
        users = list(users_cursor)
        # converte ObjectId para str
        for user in users:
            user["_id"] = str(user["_id"])
        return users
    except ValueError:
        # levantado pelo get_tenant_db se tenant não existir
        raise
    except Exception as e:
        raise RuntimeError(f"Erro ao listar usuários do tenant '{tenant_slug}': {e}")


def create_user(tenant_slug: str, user_data: dict):

    db = get_tenant_db(tenant_slug)

    # hash da senha
    password_hash = bcrypt.hashpw(
        user_data["password"].encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user_document = {
        "tenant_id": tenant_slug,
        "name": user_data["name"],
        "username": user_data["username"],
        "password_hash": password_hash,
        "email": user_data["email"],
        "phone": user_data.get("phone"),
        "type": user_data["type"],
        "assignments": user_data.get("assignments", []),
        "teams": user_data.get("teams", []),
        "active": True,
        "terms": user_data.get("terms", []),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = db.users.insert_one(user_document)

    user_document["_id"] = str(result.inserted_id)

    return user_document

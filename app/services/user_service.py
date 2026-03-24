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

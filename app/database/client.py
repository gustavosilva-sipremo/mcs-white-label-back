from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(MONGO_URI)

# Banco de identidade
identity_db = mongo_client["identity"]


def get_tenant_db(tenant_database: str):
    tenant = identity_db.tenants.find_one({"database": tenant_database})
    if not tenant:
        raise ValueError(f"Tenant '{tenant_database}' not found")

    # usa o campo 'database' do tenant
    db_name = tenant["database"]
    return mongo_client[db_name]

from fastapi import FastAPI
from app.routes import tenants

app = FastAPI(title="MCS White Label Backend")

app.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])


@app.get("/")
def root():
    return {"message": "MCS White Label Backend is running"}

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import Base, engine
from .routers import (
    agent,
    applications,
    auth,
    brands,
    buyer,
    files,
    franchise_owner,
    franchise_owner_ops,
    messages,
    notifications,
    protected,
    search,
)


Base.metadata.create_all(bind=engine)

_log = logging.getLogger("uvicorn.error")

app = FastAPI(title="FranchiseHub API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://[::1]:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(agent.router)
app.include_router(brands.router)
app.include_router(files.router)
app.include_router(franchise_owner.router)
app.include_router(franchise_owner_ops.router)
app.include_router(buyer.router)
app.include_router(applications.router)
app.include_router(messages.router)
app.include_router(protected.router)
app.include_router(notifications.router)
app.include_router(search.router)


@app.on_event("startup")
def _log_registered_franchise_paths() -> None:
    paths = sorted(
        {
            getattr(route, "path", "")
            for route in app.routes
            if getattr(route, "path", "").startswith("/franchise-owner")
        }
    )
    _log.info("Registered /franchise-owner paths: %s", paths)


@app.get("/health")
def health_check():
    return {"status": "ok"}

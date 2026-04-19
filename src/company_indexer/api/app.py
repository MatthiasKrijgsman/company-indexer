from contextlib import asynccontextmanager

from fastapi import FastAPI

from company_indexer.api.routes import companies, geocoding, jobs, scrapes, website_searches
from company_indexer.db import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP: create tables from models on startup. Will be replaced with Alembic
    # once the schema stabilizes and there's data worth preserving.
    await create_all()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="company-indexer", version="0.1.0", lifespan=lifespan)
    app.include_router(companies.router)
    app.include_router(website_searches.router)
    app.include_router(geocoding.router)
    app.include_router(scrapes.router)
    app.include_router(jobs.router)
    return app


app = create_app()

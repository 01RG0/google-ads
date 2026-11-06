"""Small FastAPI facade over the async client."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from client import TransparencyClient
from client.errors import ResponseShapeError, UnsupportedFilterError, UpstreamHTTPError
from client.models import CreativeSearchRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ads_client = TransparencyClient()
    yield
    await app.state.ads_client.close()


app = FastAPI(title="Ads Transparency API", version="0.1.0", lifespan=lifespan)


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, UnsupportedFilterError):
        return HTTPException(status_code=501, detail=str(exc))
    if isinstance(exc, UpstreamHTTPError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, ResponseShapeError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=502, detail="Transparency Center request failed")


@app.get("/advertisers/search")
async def search_advertisers(q: str = Query(min_length=1), limit: int = Query(10, ge=1, le=40)):
    try:
        return await app.state.ads_client.search_advertisers(q, limit=limit)
    except Exception as exc:
        raise _translate(exc) from exc


@app.get("/domains/{domain}/creatives")
async def search_domain(domain: str, cursor: str | None = None, page_size: int = Query(40, ge=1, le=40)):
    try:
        return await app.state.ads_client.search_by_domain(domain, cursor=cursor, page_size=page_size)
    except Exception as exc:
        raise _translate(exc) from exc


@app.post("/creatives/search")
async def list_creatives(request: CreativeSearchRequest):
    try:
        return await app.state.ads_client.list_creatives(**request.model_dump())
    except Exception as exc:
        raise _translate(exc) from exc


@app.get("/advertisers/{advertiser_id}")
async def get_advertiser(advertiser_id: str):
    try:
        result = await app.state.ads_client.get_advertiser(advertiser_id)
    except Exception as exc:
        raise _translate(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Advertiser not found")
    return result


@app.get("/advertisers/{advertiser_id}/creatives/{creative_id}")
async def get_creative(advertiser_id: str, creative_id: str):
    try:
        result = await app.state.ads_client.get_creative(advertiser_id, creative_id)
    except Exception as exc:
        raise _translate(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Creative not found")
    return result

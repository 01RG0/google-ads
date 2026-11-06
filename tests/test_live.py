"""Opt-in network smoke test: run with pytest -m live."""
import os

import pytest

from client import TransparencyClient

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_advertiser_search():
    if os.getenv("ADS_TRANSPARENCY_LIVE") != "1":
        pytest.skip("set ADS_TRANSPARENCY_LIVE=1 to enable the live smoke test")
    async with TransparencyClient() as client:
        results = await client.search_advertisers("Nike", limit=2)
        assert isinstance(results, list) and results
        advertiser_id = results[0].advertiser_id
        assert advertiser_id and advertiser_id.startswith("AR")
        page = await client.list_creatives(advertiser_id=advertiser_id, region="US")
    assert page.creatives is not None

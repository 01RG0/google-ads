# Google Ads Transparency Center client

Async Python client and a small FastAPI facade for the public RPCs observed in
the saved Playwright captures. The client uses plain `httpx`; it does not start
a browser or reuse browser state.

## Install and run

```powershell
python -m pip install -e ".[dev]"
uvicorn api.app:app --reload
```

The API docs are at `http://127.0.0.1:8000/docs`.

## Client example

```python
import asyncio
from client import TransparencyClient

async def main():
    async with TransparencyClient() as ads:
        advertisers = await ads.search_advertisers("Nike")
        page = await ads.list_creatives(advertiser_id=advertisers[0].advertiser_id)
        print(page.creatives, page.next_cursor)

asyncio.run(main())
```

Use `next_cursor` unchanged on the next `list_creatives` call. `region` accepts
an active country or territory's ISO alpha-2 code or official English name.
The mapping includes 219 active country/territory entries from Google's
published geo-target data; `anywhere` omits the filter. `date_from` / `date_to`
accept ISO dates (`YYYY-MM-DD`). `get_creative` uses the captured
`LookupService/GetCreativeById` RPC.

## Tests

Contract tests use sanitized samples under `docs/samples/`. The live smoke test
is opt-in: `ADS_TRANSPARENCY_LIVE=1 pytest -m live`.

GitHub Actions runs the offline contracts and the two-request live smoke test
daily at 09:17 UTC. You can also run it from the Actions tab with
`workflow_dispatch`.

See [docs/endpoints.md](docs/endpoints.md) for the observed request and response
contracts and the limits of the capture.

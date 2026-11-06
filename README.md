# Google Ads Transparency Center client

An async Python client and small FastAPI service for searching public ads in
Google's Ads Transparency Center. The client sends the site's observed RPC
requests with `httpx`; it does not start a browser. Playwright is used only by
the capture scripts under `scripts/`.

## What it supports

- Advertiser autocomplete by name with `search_advertisers(query)`.
- Creative search by advertiser or domain, including cursor pagination.
- Country and territory filters using an ISO alpha-2 code or official English
  name. The bundled mapping contains 219 active entries from Google's
  geo-target dataset, plus the separately captured Palestine mapping. Use
  `region="anywhere"` to leave region unrestricted. The Transparency Center
  selector does not offer Iran.
- Custom date ranges with ISO dates (`YYYY-MM-DD`). The UI's selected end date
  is inclusive; the RPC encodes the following day as its exclusive upper
  bound.
- Advertiser and creative detail lookups.
- Request throttling, timeouts, retries with jitter, typed Pydantic models, and
  explicit errors when the upstream response shape changes.

The numeric RPC field meanings and capture evidence are documented in
[docs/endpoints.md](docs/endpoints.md). Raw HARs are kept in the ignored
`captures/` directory and must not be committed.

## Install

Python 3.11 or newer is required.

```powershell
python -m pip install -e ".[dev]"
```

## Use the Python client

```python
import asyncio
from client import TransparencyClient


async def main():
    async with TransparencyClient() as ads:
        matches = await ads.search_advertisers("Nike")
        if not matches:
            return

        advertiser_id = matches[0].advertiser_id
        page = await ads.list_creatives(
            advertiser_id=advertiser_id,
            region="EG",                 # ISO country code or official name
            date_from="2026-10-01",      # optional; supply both dates together
            date_to="2026-10-31",
        )

        for creative in page.creatives:
            print(creative.creative_id, creative.advertiser_name)

        if page.next_cursor:
            next_page = await ads.list_creatives(
                advertiser_id=advertiser_id,
                region="Egypt",
                date_from="2026-10-01",
                date_to="2026-10-31",
                cursor=page.next_cursor,
            )
            print("next page:", len(next_page.creatives))

        if page.creatives:
            detail = await ads.get_creative(advertiser_id, page.creatives[0].creative_id)
            print(detail)


asyncio.run(main())
```

Search by domain with `await ads.search_by_domain("nike.com")`. Continue
pagination by passing `page.next_cursor` unchanged. `get_creative` calls the
captured detail RPC directly.

### Region data

Country and territory IDs come from the
[Google Ads geo-target dataset](https://developers.google.com/google-ads/api/data/geotargets),
version `2026-10-06`; the source URL and attribution are also recorded in
`client/geo_targets_countries.json`. The client accepts both codes such as
`EG` and names such as `Egypt`. Palestine (`PS`, ID 2275) is a site-captured
override because it is absent from that CSV. Unknown or unsupported values
raise `UnsupportedFilterError` instead of silently omitting the filter.

## Run the HTTP API

```powershell
uvicorn api.app:app --reload
```

Interactive API documentation: <http://127.0.0.1:8000/docs>

| Route | Purpose |
|---|---|
| `GET /advertisers/search?q=Nike` | Search advertiser suggestions |
| `GET /advertisers/{advertiser_id}` | Get advertiser details |
| `GET /domains/{domain}/creatives` | Search creatives by domain |
| `POST /creatives/search` | Search with advertiser, region, date, and cursor filters |
| `GET /advertisers/{advertiser_id}/creatives/{creative_id}` | Get creative details |

Example request body for `POST /creatives/search`:

```json
{
  "advertiser_id": "AR…",
  "region": "EG",
  "date_from": "2026-10-01",
  "date_to": "2026-10-31",
  "page_size": 40
}
```

## Tests and daily monitoring

Run the saved response-contract tests without network access:

```powershell
python -m pytest -q -m "not live"
```

The live smoke test makes two requests to the public site: advertiser search,
then creative listing. Run it manually in PowerShell with:

```powershell
$env:ADS_TRANSPARENCY_LIVE = "1"
python -m pytest -q -m live
```

GitHub Actions runs the offline contracts and live smoke test every day at
09:17 UTC. Use **Actions → Daily Transparency Center smoke test → Run workflow**
to trigger it manually. A failed run indicates that the public service was
unavailable or its response no longer matches the current client contract.

# Google Ads Transparency Center — Endpoint Findings

> Captured via Playwright HAR (fresh isolated Chromium context, no user profile).  
> Request shapes below are observed in the HARs. Plain `httpx` replayability has not been independently verified yet.  
> HAR files are in `captures/` (git-ignored). Never commit them.

---

## Transport layer

All API calls share the same transport contract:

| Property | Value |
|----------|-------|
| Base URL | `https://adstransparency.google.com/anji/_/rpc/` |
| Method | `POST` |
| Content-Type | `application/x-www-form-urlencoded` |
| Body format | Single field `f.req=<url-encoded JSON>` |
| Response | `application/json; charset=utf-8` |

### Required headers

```
content-type: application/x-www-form-urlencoded
origin: https://adstransparency.google.com
x-same-domain: 1
referer: https://adstransparency.google.com/
```

`x-same-domain: 1` is a non-standard header present on RPC calls; its necessity has not been tested independently.  
`authuser=` appears as a URL query parameter on every call (always blank; the site is fully public and unauthenticated).

### Dynamic token verdict

**No dynamic token or signature was required on the captured RPC requests.** No `Authorization` header or session cookie appears in the captured RPC calls. The static `x-same-domain: 1` header is present. The `GetCreativeById` response does contain preview URLs with a `sig` query parameter; that signature belongs to the returned creative preview URL, not the RPC request. Consumers fetching preview assets should use the URL returned by the RPC rather than trying to construct one. If that URL expires or cannot be fetched with `httpx`, use Playwright response interception for the preview response instead of guessing the signature.

---

## Field encoding note

The API uses numeric protobuf-style field keys in its JSON (`"1"`, `"2"`, etc.). Field names below are inferred from context; Google does not publish the schema.

---

## Endpoints

### 1. `SearchService/SearchSuggestions` — advertiser autocomplete

**URL:** `POST /anji/_/rpc/SearchService/SearchSuggestions?authuser=`  
**Purpose:** Autocomplete suggestions when the user types an advertiser name.

#### Request body

```json
{
  "1": "Nike",   // query string
  "2": 10,       // max results
  "3": 10,       // max results (duplicate — always match "2")
  "5": {"1": 1}  // unknown flag; always send as-is
}
```

#### Response body

```json
{
  "1": [                        // list of suggestion items
    {
      "1": {
        "1": "Nike, Inc.",      // advertiser_name
        "2": "AR16735076...",   // advertiser_id
        "3": "US",              // country_code  (ISO 3166-1 alpha-2)
        "4": {
          "2": {
            "1": "9000",        // ad_count_lower (bucket floor)
            "2": "10000"        // ad_count_upper (bucket ceiling)
          }
        },
        "5": true               // exact_match (present only when true)
      }
    }
    // ... more suggestions
  ]
}
```

**Field explanations:**

| Field | Meaning |
|-------|---------|
| `[n].1.1` | Advertiser display name |
| `[n].1.2` | Advertiser ID (`AR` + 17-digit number) |
| `[n].1.3` | Country code where advertiser is registered |
| `[n].1.4.2.1` | Lower bound of ad count bucket (e.g. "9000") |
| `[n].1.4.2.2` | Upper bound of ad count bucket (e.g. "10000") |
| `[n].1.5` | `true` when this is an exact-match result |

---

### 2. `LookupService/GetAdvertiserById` — advertiser detail

**URL:** `POST /anji/_/rpc/LookupService/GetAdvertiserById?authuser=`  
**Purpose:** Fetch full advertiser metadata by its ID.

#### Request body

```json
{
  "1": "AR16735076323512287233",  // advertiser_id
  "3": {"1": 1}                  // unknown flag; always send as-is
}
```

#### Response body (found advertiser)

```json
{
  "1": {
    "1": "AR16735076323512287233",  // advertiser_id
    "2": "Nike, Inc.",              // advertiser_name
    "3": "US",                      // country_code
    "9": {
      "1": "Nike, Inc.",            // legal_name (display)
      "2": "Nike, Inc.",            // legal_name (variant)
      "4": 1                        // name_type
    },
    "11": "US",                     // country_code (duplicate)
    "15": [1]                       // platform_types list (see below)
  }
}
```

**Response when ID is not found:** `{}`

**Platform type codes** (`field 15`):

| Code | Platform |
|------|----------|
| `1` | Google Search |
| `2` | YouTube |
| `3` | Google Display / Shopping |
| `4` | Google Maps |
| `5` | Google Play |

---

### 3. `SearchService/SearchCreatives` — creative (ad) search

**URL:** `POST /anji/_/rpc/SearchService/SearchCreatives?authuser=`  
**Purpose:** List ad creatives with optional filters. The primary workhorse of the API.

#### Request body

```json
{
  "2": 40,          // page_size (observed values: 5–40; default 40)
  "3": {            // filter object — all sub-fields are optional
    "12": {         // domain filter
      "1": "nike.com",  // domain string (empty string = no domain filter)
      "2": true         // include_subdomains
    },
    "13": {         // advertiser filter
      "1": ["AR16735076323512287233"]  // list of advertiser_ids
    },
    "6": 20261101,    // inclusive date_from as YYYYMMDD integer
    "7": 20261106,    // exclusive day after date_to
    "8": [2840]       // region filter captured after selecting United States
  },
  "4": "<cursor>",  // pagination cursor — omit on first page
  "7": {            // sort descriptor
    "1": 1,         // sort_field  (1 = last_shown date)
    "2": 0,         // sort_direction (0 = descending)
    "3": 2818       // unknown (constant in all observed calls; send as-is)
  }
}
```

**Filter logic:** `"3"."12"`, `"3"."13"`, `"3"."6"`/`"3"."7"`, and `"3"."8"` can be combined. Domain can be empty string if only filtering by advertiser. `"3"."8"` contains a Google geo target criterion ID; `anywhere` omits it.

#### Response body

```json
{
  "1": [ ... ],                                    // list of creative objects (see below)
  "2": "CgoAP7zmga+yW8Df...",                      // next_page_cursor (base64; absent on last page)
  "4": "50000",                                    // total_count (approximate, string)
  "5": "60000"                                     // another_count (purpose unclear; also approximate)
}
```

#### Creative object

```json
{
  "1": "AR06365026152670560257",   // advertiser_id
  "2": "CR00397654116945362945",   // creative_id
  "3": {                           // ad content (format-dependent; see below)
    "3": {
      "2": "<img src=\"https://tpc.googlesyndication.com/archive/simgad/...\">"
    },
    "5": true
  },
  "4": 1,                          // format_type (see table below)
  "6": {"1": "1635145200"},        // first_shown  {seconds_epoch, optional_nanoseconds}
  "7": {"1": "1793939486", "2": 47472000},  // last_shown {seconds, nanoseconds}
  "12": "WPP MEDIA MANAGEMENT",    // advertiser_name
  "13": 1838,                      // region_count (number of regions ad ran in)
  "14": "nike.com"                 // domain
}
```

**Format type codes** (`field 4`):

| Code | Format |
|------|--------|
| `1` | Display / image ad |
| `2` | Video ad (YouTube) |
| `3` | Text / search ad |

**Timestamp format:** Both `"6"` and `"7"` are objects with `"1"` = Unix timestamp in seconds (string), `"2"` = fractional nanoseconds (integer, optional). Parse as `int(field["1"]) + int(field.get("2", 0)) / 1e9`.

#### Pagination

Pass `response["2"]` verbatim as `request["4"]` in the next call. When `response["2"]` is absent, the response indicates no next page. Cursor handoff was observed in the response, but a subsequent cursor request and overlap behavior were not verified in the saved captures.

---

### 5. `TfaarAdvertiserService/GetAdvertiserDunsMapping` — full advertiser list

**URL:** `POST /anji/_/rpc/TfaarAdvertiserService/GetAdvertiserDunsMapping?authuser=`  
**Purpose:** Returns all advertisers known to the system with their DUNS number. The site calls this on every page load to build a local DUNS→advertiser mapping (for CSRD/political-ad compliance display). Returns 6600+ entries as of the capture date.

#### Request body

```json
{}
```

#### Response body

```json
{
  "1": [
    {
      "1": "AR07720753547683299329",  // advertiser_id
      "2": "614152143"                // duns_number
    }
    // ... thousands more
  ]
}
```

**Note:** This call returns the entire dataset in one shot (no pagination observed). It is called on every page load, implying the site caches it client-side. Do not hammer it — call once and cache locally.

---

### 5. `/_/logging` — client telemetry (irrelevant)

**URL:** `POST /_/logging?authuser=`  
**Purpose:** Client-side event logging. Returns `200 {}`. Ignore entirely.

---

## Endpoint summary table

| # | Endpoint | Client method | Notes |
|---|----------|---------------|-------|
| 1 | `SearchService/SearchSuggestions` | `search_advertisers(query)` | Autocomplete; returns name + ID |
| 2 | `LookupService/GetAdvertiserById` | `get_advertiser(advertiser_id)` | Returns `{}` for unknown IDs |
| 3 | `SearchService/SearchCreatives` | `list_creatives(...)`, `search_by_domain(...)` | Main search; supports pagination |
| 4 | `LookupService/GetCreativeById` | `get_creative(advertiser_id, creative_id)` | Dedicated detail RPC |
| 5 | `TfaarAdvertiserService/GetAdvertiserDunsMapping` | _(not in client scope)_ | Heavy call; cache aggressively |

---

## Region, date, and creative-detail findings

Selecting a region adds its Google geo target criterion ID as a one-item list in `SearchCreatives` filter field `"3"."8"`. Browser captures verified US=`2840`, UK=`2826`, Egypt=`2818`, Saudi Arabia=`2682`, United Arab Emirates=`2784`, Qatar=`2634`, and Palestine=`2275`. The client accepts active country/territory ISO alpha-2 codes or official names from Google's published [Geo targets dataset](https://developers.google.com/google-ads/api/data/geotargets), using the 2026-10-06 CSV's 219 active entries, plus Palestine's directly captured selector mapping. `anywhere` omits the filter. Google's dataset notes that some active locations may not be targetable. Iran is absent from the dataset and was not offered by the captured Transparency Center selector.

The advertiser page exposes `Today`, `Yesterday`, `Last 7 days`, `Last 30 days`, and custom date choices. Selecting built-in ranges did not change the observed request body, but applying a custom range did. Setting Nov 1–5, 2026 produced `"3"."6": 20261101` and `"3"."7": 20261106`. This indicates integer `YYYYMMDD` dates, with the end encoded as the day after the inclusive date selected in the UI. The client accepts ISO dates (`YYYY-MM-DD`) and converts them to this shape.

### `LookupService/GetCreativeById` — creative details

**URL:** `POST /anji/_/rpc/LookupService/GetCreativeById?authuser=`

**Request body:**

```json
{
  "1": "<advertiser_id>",
  "2": "<creative_id>",
  "5": {"1": 1, "2": 0, "3": 2818}
}
```

The response wraps the detail record in field `"1"`. Observed fields are `"1"` advertiser ID, `"2"` creative ID, `"4"` last-shown timestamp, `"5"` creative variations (each variation has a preview URL at `"1"."4"`), `"8"` format code, `"17"` region/date records, and `"22"` advertiser display data. Unknown fields are retained by the Pydantic model.

The format filter and `GetAdvertiserDunsMapping` pagination behavior remain uncaptured.

## Capture coverage

The saved HARs contain `SearchSuggestions`, `LookupService/GetAdvertiserById`,
`LookupService/GetCreativeById`, `SearchCreatives`, and
`GetAdvertiserDunsMapping`, plus `/_/logging` telemetry. Captures show a
domain-filtered request, advertiser-filtered requests, region filters for the
US, UK, Egypt, Saudi Arabia, UAE, Qatar, and Palestine, and a custom date range filter. A later
creative page whose cursor was sent by the client has not been captured.
Pagination is indicated by response field `"2"`, but end-to-end pagination
replay remains to be verified.

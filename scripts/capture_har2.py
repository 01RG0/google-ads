"""
Phase 1b - Targeted capture: focus on search-by-name UI interaction
and real advertiser page navigation, to catch SearchAdvertisers endpoint.
"""

import asyncio
import json
import sys
import urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

HAR_PATH = Path(__file__).parent.parent / "captures" / "adstransparency2.har"
BASE = "https://adstransparency.google.com"
SENSITIVE = {"cookie", "set-cookie", "authorization", "x-client-data"}


def strip_sensitive(har: dict) -> dict:
    for entry in har.get("log", {}).get("entries", []):
        for msg in (entry.get("request", {}), entry.get("response", {})):
            msg["headers"] = [
                h for h in msg.get("headers", [])
                if h.get("name", "").lower() not in SENSITIVE
            ]
            if "cookies" in msg:
                msg["cookies"] = []
    return har


async def main() -> None:
    HAR_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            record_har_path=str(HAR_PATH),
            record_har_url_filter="**/anji/_/rpc/**",
            locale="en-US",
            timezone_id="UTC",
            storage_state=None,
        )
        page = await context.new_page()

        # Step 1: Load home, wait for JS to initialize
        print("[1] Loading home page...")
        await page.goto(f"{BASE}/?region=anywhere", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Step 2: Find and use the actual search input
        print("[2] Trying to use the advertiser search box...")
        # Dump all input elements for debugging
        inputs = await page.eval_on_selector_all("input,textarea,[contenteditable]",
            "els => els.map(e => ({tag: e.tagName, type: e.type, placeholder: e.placeholder, "
            "ariaLabel: e.getAttribute('aria-label'), id: e.id, class: e.className.substring(0,60)}))")
        print("   Inputs found:", json.dumps(inputs, indent=2)[:600])

        # Try clicking the search/filter input
        for sel in [
            "input[placeholder*='Search' i]",
            "input[aria-label*='Search' i]",
            "input[aria-label*='Advertiser' i]",
            "input[type='search']",
            "[data-testid*='search' i] input",
            "search-input input",
            ".input-area",
            "input",
        ]:
            el = page.locator(sel)
            if await el.count() > 0:
                print(f"   Found input with selector: {sel}")
                await el.first.click()
                await el.first.fill("Nike")
                await page.wait_for_timeout(1000)
                # Check for autocomplete suggestions
                suggestions = page.locator("[role='listbox'] [role='option'], [role='list'] [role='listitem']")
                count = await suggestions.count()
                print(f"   Autocomplete suggestions: {count}")
                if count > 0:
                    text = await suggestions.first.inner_text()
                    print(f"   First suggestion: {text[:80].encode('ascii', 'replace').decode()}")
                    await suggestions.first.click()
                    await page.wait_for_timeout(3000)
                else:
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(3000)
                break

        # Step 3: Navigate to the search page with Nike to see what RPC fires
        print("[3] Direct URL search for Nike...")
        await page.goto(f"{BASE}/?region=anywhere&advertiser_name=Nike", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Dump page content to understand structure
        title = await page.title()
        print(f"   Page title: {title}")

        # Step 4: Click an advertiser result if present
        print("[4] Looking for advertiser links to click...")
        links = await page.eval_on_selector_all(
            "a[href*='/advertiser/AR']",
            "els => els.map(e => ({href: e.href, text: e.textContent.trim().substring(0,60)}))"
        )
        print(f"   Advertiser links: {json.dumps(links[:5], indent=2)}")
        if links:
            href = links[0]["href"]
            print(f"   Navigating to: {href}")
            await page.goto(href, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            # Scroll to load more
            for _ in range(4):
                await page.keyboard.press("End")
                await page.wait_for_timeout(1500)

        # Step 5: Try direct SearchCreatives with advertiser name filter variations
        # The body field "3" seems to be the filter. Let's try to find advertiser search.
        print("[5] Trying SearchCreatives with advertiser_name filter via page interaction...")
        await page.goto(f"{BASE}/?region=anywhere", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Intercept ALL XHR/fetch to log them
        rpc_calls = []
        async def on_request(req):
            if "/anji/_/rpc/" in req.url:
                pd = req.post_data or ""
                if pd.startswith("f.req="):
                    try:
                        body = json.loads(urllib.parse.unquote(pd[6:]))
                    except Exception:
                        body = pd[:200]
                else:
                    body = pd[:200]
                rpc_calls.append({
                    "url": req.url.split("?")[0],
                    "body": body
                })
        page.on("request", on_request)

        # Navigate to a known advertiser (Google LLC - AR15139968863988736001)
        print("[6] Opening a real advertiser page (Google LLC)...")
        await page.goto(
            f"{BASE}/advertiser/AR15139968863988736001?region=anywhere",
            wait_until="networkidle", timeout=30000
        )
        await page.wait_for_timeout(3000)
        for _ in range(3):
            await page.keyboard.press("End")
            await page.wait_for_timeout(2000)

        print(f"\n  Observed RPC calls ({len(rpc_calls)}):")
        for c in rpc_calls:
            print(f"  {c['url'].split('/')[-1]}: {json.dumps(c['body'])[:200]}")

        await context.close()
        await browser.close()

    with open(HAR_PATH, encoding="utf-8") as f:
        har = json.load(f)
    har = strip_sensitive(har)
    with open(HAR_PATH, "w", encoding="utf-8") as f:
        json.dump(har, f, indent=2)

    entries = har.get("log", {}).get("entries", [])
    print(f"\nHAR2 saved: {len(entries)} RPC entries")
    for e in entries:
        req = e["request"]
        pd = req.get("postData", {}).get("text", "")
        if pd.startswith("f.req="):
            try:
                body = json.loads(urllib.parse.unquote(pd[6:]))
                body_str = json.dumps(body)[:120]
            except Exception:
                body_str = pd[:80]
        else:
            body_str = pd[:80]
        resp = e.get("response", {})
        resp_text = resp.get("content", {}).get("text", "")
        resp_keys = ""
        try:
            resp_keys = str(list(json.loads(resp_text).keys()))
        except Exception:
            pass
        print(f"  {req['method']} {req['url'].split('/')[-1].split('?')[0]}: body={body_str} -> keys={resp_keys}")


if __name__ == "__main__":
    asyncio.run(main())

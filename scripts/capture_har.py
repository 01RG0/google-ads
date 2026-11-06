"""
Phase 1 - HAR capture for Google Ads Transparency Center.

Launches a fresh, isolated Chromium context (no user profile, no cookies,
no extensions).  Records a HAR while exercising the main search flows, then
strips any Set-Cookie / Cookie / Authorization headers before saving.

Usage:
    python -I scripts/capture_har.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

HAR_PATH = Path(__file__).parent.parent / "captures" / "adstransparency.har"
BASE = "https://adstransparency.google.com"

# Headers we must never persist
SENSITIVE_HEADERS = {"cookie", "set-cookie", "authorization", "x-client-data"}


def strip_sensitive(har: dict) -> dict:
    """Remove sensitive headers from all HAR entries in-place."""
    for entry in har.get("log", {}).get("entries", []):
        for msg in (entry.get("request", {}), entry.get("response", {})):
            msg["headers"] = [
                h for h in msg.get("headers", [])
                if h.get("name", "").lower() not in SENSITIVE_HEADERS
            ]
            if "cookies" in msg:
                msg["cookies"] = []
    return har


async def main() -> None:
    HAR_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        # Isolated context: temp dir, no persistent storage, no extensions.
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-extensions", "--incognito"],
        )
        context = await browser.new_context(
            record_har_path=str(HAR_PATH),
            record_har_url_filter=re.compile(
                r"https://adstransparency\.google\.com/.*"
            ),
            # No locale/timezone leakage
            locale="en-US",
            timezone_id="UTC",
            # No stored state at all
            storage_state=None,
        )
        page = await context.new_page()

        print("[1/5] Searching by advertiser name: 'Nike'")
        await page.goto(f"{BASE}/?region=anywhere", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Try the search input
        search_input = page.locator("input[type='search'], input[placeholder*='search' i], [aria-label*='search' i]")
        if await search_input.count() > 0:
            await search_input.first.fill("Nike")
            await search_input.first.press("Enter")
            await page.wait_for_timeout(3000)
        else:
            # Navigate directly via URL pattern
            await page.goto(f"{BASE}/?region=anywhere&advertiser_name=Nike", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

        print("[2/5] Searching by domain: 'nike.com'")
        await page.goto(f"{BASE}/advertiser/AR?region=anywhere", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        # Try domain search URL
        await page.goto(f"{BASE}/?region=anywhere&domain=nike.com", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        print("[3/5] Opening an advertiser page and scrolling for more ads")
        # Navigate to a known advertiser search result page
        await page.goto(f"{BASE}/?region=anywhere&advertiser_name=Google+LLC", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Click on first advertiser result if available
        advertiser_link = page.locator("a[href*='/advertiser/']")
        if await advertiser_link.count() > 0:
            href = await advertiser_link.first.get_attribute("href")
            print(f"   -> Following advertiser link: {href}")
            await advertiser_link.first.click()
            await page.wait_for_timeout(3000)
            # Scroll to trigger pagination
            for _ in range(3):
                await page.keyboard.press("End")
                await page.wait_for_timeout(2000)

        print("[4/5] Changing region and date filters")
        await page.goto(f"{BASE}/?region=US", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.goto(f"{BASE}/?region=GB", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        print("[5/5] Opening a creative detail page")
        # Try to find and click a creative card
        creative_card = page.locator("[data-creative-id], .creative-card, [class*='creative']")
        if await creative_card.count() > 0:
            await creative_card.first.click()
            await page.wait_for_timeout(3000)
        else:
            # Try clicking any ad preview link
            ad_link = page.locator("a[href*='/creative/']")
            if await ad_link.count() > 0:
                await ad_link.first.click()
                await page.wait_for_timeout(3000)

        print("Closing context and flushing HAR...")
        await context.close()
        await browser.close()

    # Load, strip sensitive headers, re-save
    with open(HAR_PATH, encoding="utf-8") as f:
        har = json.load(f)
    har = strip_sensitive(har)
    with open(HAR_PATH, "w", encoding="utf-8") as f:
        json.dump(har, f, indent=2)

    # Quick summary
    entries = har.get("log", {}).get("entries", [])
    transparency_entries = [
        e for e in entries
        if "adstransparency.google.com" in e.get("request", {}).get("url", "")
    ]
    print(f"\nHAR saved to: {HAR_PATH}")
    print(f"Total entries: {len(entries)}")
    print(f"adstransparency.google.com entries: {len(transparency_entries)}")
    for e in transparency_entries[:30]:
        req = e["request"]
        resp = e.get("response", {})
        print(f"  {req['method']} {req['url'][:120]}  -> {resp.get('status', '?')}")


if __name__ == "__main__":
    asyncio.run(main())

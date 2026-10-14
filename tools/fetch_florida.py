#!/usr/bin/env python3
"""Florida resident fares for the Joy sailing, read while logged in to the owner's NCL account.

Runs on the owner's AI PC only (it needs a browser profile that stays logged in). Setup and
daily steps for the owner: tools/florida-runner/README.md.

  py -3 tools\\fetch_florida.py --setup     first time: log in by hand, then one test price
  py -3 tools\\fetch_florida.py --record    if the test shows no Florida price: records what
                                            NCL's own site sends, names removed
  py -3 tools\\fetch_florida.py --push      daily: every cabin, writes data/florida.json,
                                            commits and pushes it to main (publishes the page)
  py -3 tools\\fetch_florida.py             daily without committing (writes the file only)

How it works (NOTES.md, "Florida resident rates"): NCL's app sends no residency field in its
price calls. Login lives in the NCLAuth cookie, and the price call goes to www.ncl.com, so a
logged-in browser gets the account's Florida fares from the same read-only price-summary call
the public page uses. For each cabin category at 2 guests this script makes:
  - one anonymous price-summary call (plain request, no cookies): the website fare
  - one logged-in price-summary call (from inside the logged-in browser page): the Florida fare
and stores only numbers: website fare, Florida fare and the difference per guest. Never names,
email, Latitudes number or anything else from the account (public repo).

Safety: only stateroom-types-availability and price-summary are ever called. Every address goes
through fetch_prices.FORBIDDEN ("manage-cabin", "hold") and every answer through
fetch_prices.HOLD_IN_RESPONSE ("hold", "heldUntil"); the run stops on either. The browser profile
folder IS the logged-in NCL account: keep it on the AI PC, never in a repo.
"""
import argparse
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_prices as fp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES = os.path.join(ROOT, "data", "prices.json")
OUT = os.path.join(ROOT, "data", "florida.json")
DEFAULT_PROFILE = r"D:\AI-VAULT\ncl-profile" if os.name == "nt" else os.path.expanduser("~/.ncl-profile")
SCHEMA_VERSION = 1
GUESTS = 2
PAUSE_SECONDS = 2
HOME = "https://www.ncl.com/"
# Keys allowed in a recorded request body; every other string value is replaced (names, emails...).
SAFE_KEYS = {"packageId", "stateroomFilters", "id", "mainCabin", "numberOfGuests", "stateroomTypeCode",
             "pricedCategoryCode", "fareCodes", "vouchers", "userFareCodes", "guests", "reservationOwner"}


def log(msg):
    print(msg, flush=True)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------- browser ----------

def open_browser(profile, show):
    """Real Chrome with the saved profile (keeps the login between runs)."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    os.makedirs(profile, exist_ok=True)
    try:
        ctx = pw.chromium.launch_persistent_context(profile, channel="chrome", headless=not show,
                                                    viewport={"width": 1280, "height": 900})
    except Exception:
        # Chrome not installed: Playwright's own Chromium.
        ctx = pw.chromium.launch_persistent_context(profile, headless=not show, viewport={"width": 1280, "height": 900})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, ctx, page


def login_state(ctx):
    """(logged_in, expires_text). Reads only the token's expiry, never the name or email in it."""
    for c in ctx.cookies(HOME):
        if c["name"] != "NCLAuth":
            continue
        try:
            from urllib.parse import unquote
            data = json.loads(unquote(c["value"]))
            token = data.get("accessToken") or ""
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            exp = claims.get("exp")
            if exp:
                when = dt.datetime.fromtimestamp(exp, dt.timezone.utc)
                return when > dt.datetime.now(dt.timezone.utc), when.strftime("%Y-%m-%d %H:%M UTC")
            return bool(token), "unknown"
        except Exception:
            return False, "unreadable"
    return False, "no login cookie"


def browser_post(page, url, body):
    """POST from inside the logged-in page, like NCL's own app (sends the login cookie)."""
    if fp.FORBIDDEN.search(url):
        raise RuntimeError(f"Refusing to call {url}: it could hold a cabin")
    time.sleep(PAUSE_SECONDS)
    r = page.evaluate("""async ({url, body}) => {
        const res = await fetch(url, {method: "POST", credentials: "include", redirect: "manual",
            headers: {"Content-Type": "application/json", "Accept": "application/json"},
            body: JSON.stringify(body)});
        return {status: res.status, text: await res.text()};
    }""", {"url": url, "body": body})
    if r["status"] != 200:
        raise RuntimeError(f"NCL answered HTTP {r['status']} (logged in)")
    if fp.HOLD_IN_RESPONSE.search(r["text"].encode()):
        raise RuntimeError("NCL's answer mentioned a hold; stopping")
    return json.loads(r["text"])


def per_guest_fare(summary, res=None):
    """Fare per guest for guests 1 and 2, checked against NCL's own total.

    Signed out, NCL lists the fare per guest (STATEROOM group). Signed in to a Florida resident
    account it doesn't (seen 2026-10-14 on the AI PC; the owner's Florida screenshots had no
    "Stateroom" section either), so the fare is worked out from NCL's totals the way the
    screenshots were read: subtotal minus the Free at Sea gratuity lines, for 2 guests.
    """
    s = summary
    tot = (res or {}).get("total") or {}
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    gratuities = sum(sum(x["per_guest"]) for x in (s["open_bar"], s["specialty_dining"]) if x)
    taxes = sum(s["taxes_per_guest"]) if s["taxes_per_guest"] else tot.get("taxesAndFees")
    if not num(taxes):
        raise RuntimeError("no tax line and no taxesAndFees total")
    fares = s["fare_per_guest"]
    if len(fares) >= GUESTS and abs(fares[0] - fares[1]) <= 0.01:
        fare_total, per = s["fare_total"], float(fares[0])
    elif num(tot.get("subtotal")):
        fare_total = tot["subtotal"] - gratuities
        per = fare_total / GUESTS
    elif num(tot.get("grandTotal")):
        fare_total = tot["grandTotal"] - taxes - gratuities
        per = fare_total / GUESTS
    else:
        raise RuntimeError(f"no fare lines {fares} and no totals")
    if fare_total < 0:
        raise RuntimeError(f"worked-out fare {fare_total} is below zero")
    if abs(fare_total + taxes + gratuities - s["grand_total"]) > 1:
        raise RuntimeError(f"fare {fare_total} + taxes {taxes} + gratuities {gratuities} don't add up to NCL's total {s['grand_total']}")
    return round(per, 2)


def layout(res):
    """NCL's answer, amounts and codes only (never titles or guest entries' names), for diagnosis."""
    lines = []
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    try:
        for room in res.get("staterooms") or []:
            for g in ((room.get("pricing") or {}).get("priceGroups") or []):
                lines.append(f"  group {g.get('code')}")
                for it in g.get("priceItems") or []:
                    amounts = [x.get("price") for x in it.get("guests") or [] if num(x.get("price"))]
                    own = {k: v for k, v in it.items() if num(v)}
                    lines.append(f"    item {it.get('code')} ({it.get('itemType')}): {len(it.get('guests') or [])} guest entries {amounts} {own}")
        lines.append(f"  total {{{', '.join(f'{k}: {v}' for k, v in (res.get('total') or {}).items() if num(v))}}}")
    except Exception as e:
        lines.append(f"  (could not describe: {type(e).__name__})")
    return "\n".join(lines)


# ---------- the sailing and its categories ----------

def sailing_and_categories():
    prices = load_json(PRICES)
    if not prices or not prices.get("sailings"):
        raise SystemExit(f"Cannot read {PRICES}")
    s = prices["sailings"][0]
    cfg = dict(fp.SAILING, itinerary_code=s["itinerary_code"], package_id=s["package_id"])
    # Today's default Free at Sea promotion per cabin type (what the page prices).
    fare_codes = fp.default_fare_codes(fp.fetch_availability(cfg, GUESTS))
    cats = [(t["code"], c["code"]) for t in s["types"] for c in t["categories"]
            if not c["solo"] and c["by_guests"][str(GUESTS)]["available"]]
    return s, cfg, fare_codes, cats


def one_category(page, cfg, type_code, code, fare_code):
    body = fp.price_summary_body(cfg, GUESTS, type_code, code, fare_code)
    website = per_guest_fare(fp.fetch_price_summary(cfg, GUESTS, type_code, code, fare_code))
    res = browser_post(page, fp.PRICE_SUMMARY_URL, body)
    if (res.get("total") or {}).get("grandTotal", 0) <= 0:
        raise RuntimeError("empty logged-in price summary")
    try:
        florida = per_guest_fare(fp.parse_price_summary(res, GUESTS, type_code, code, fare_code), res)
    except Exception:
        log(f"  Signed-in answer for {code} couldn't be read. Its layout (amounts and codes only):\n{layout(res)}")
        raise
    return website, florida


# ---------- modes ----------

def setup(profile):
    pw, ctx, page = open_browser(profile, show=True)
    page.goto(HOME, wait_until="domcontentloaded")
    log("A Chrome window opened on ncl.com.")
    log("1. In that window, sign in to your NCL account (the one with your Florida address).")
    log("2. If NCL offers 'Remember me' or 'Keep me signed in', tick it.")
    input("3. When you see you're signed in, come back here and press Enter. ")
    ok, expires = login_state(ctx)
    log(f"Login cookie: {'found' if ok else 'NOT found'} (expires: {expires})")
    if not ok:
        log("Not signed in yet. Run --setup again and finish signing in before pressing Enter.")
        ctx.close(); pw.stop(); return 1
    s, cfg, fare_codes, cats = sailing_and_categories()
    test = next(((t, c) for t, c in cats if c == "IB"), cats[0])
    page.goto(HOME, wait_until="domcontentloaded")
    website, florida = one_category(page, cfg, test[0], test[1], fare_codes[test[0]])
    log(f"Test {test[1]} at 2 guests: website fare ${website:.2f} per guest, signed-in fare ${florida:.2f} per guest.")
    if florida < website:
        log("PASS: NCL gives this account a lower Florida fare. The daily run can use this profile.")
    else:
        log("No difference. NCL may need something else from its own pages. Run --record next (README, step 5).")
    ctx.close(); pw.stop()
    return 0


def redact(x, key=None):
    if isinstance(x, dict):
        return {k: redact(v, k) for k, v in x.items()}
    if isinstance(x, list):
        return [redact(v, key) for v in x]
    if isinstance(x, str) and key not in SAFE_KEYS:
        return "REMOVED"
    return x


def record(profile):
    """Saves NCL's own price-summary requests (names removed) while you click through the site."""
    out = os.path.join(profile, "florida-record.json")
    seen = []
    pw, ctx, page = open_browser(profile, show=True)

    def on_request(req):
        if "price-summary" in req.url and req.method == "POST":
            try:
                seen.append({"url": req.url, "body": redact(json.loads(req.post_data or "{}")),
                             "header_names": sorted(req.headers.keys())})
            except Exception:
                pass
    ctx.on("request", on_request)
    page.goto(HOME, wait_until="domcontentloaded")
    log("In the Chrome window: pick the Joy Nov 20 sailing, choose an Inside cabin, and open")
    input("'View Guest Breakdown' so it shows your Florida price. Then press Enter here. ")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=1)
    log(f"Saved {len(seen)} request(s) to {out}. Names and other text are replaced with REMOVED.")
    ctx.close(); pw.stop()
    return 0


def daily(profile, show, push):
    if push:
        subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "--autostash", "-q"], check=True)
    if dt.datetime.now(dt.timezone.utc).date() >= dt.date.fromisoformat(fp.SAILING["depart"]):
        log("The ship has sailed; nothing to check.")
        return 0
    pw, ctx, page = open_browser(profile, show)
    try:
        page.goto(HOME, wait_until="domcontentloaded")
        ok, expires = login_state(ctx)
        if not ok:
            log(f"NOT SIGNED IN ({expires}). Sign in again: README, 'When the login expires'. File not changed.")
            return 2
        log(f"Signed in (login expires {expires}).")
        s, cfg, fare_codes, cats = sailing_and_categories()
        prev = (load_json(OUT) or {}).get("categories") or {}
        out, failed = dict(prev), []
        for type_code, code in cats:
            try:
                website, florida = one_category(page, cfg, type_code, code, fare_codes[type_code])
            except Exception as e:
                failed.append(code)
                log(f"  {code}: failed ({e}); keeping the previous entry if any")
                continue
            out[code] = {"type": type_code, "website_fare_pp": website, "florida_fare_pp": florida,
                         "off_pp": round(website - florida, 2), "checked_at": now_iso(), "source": "logged-in NCL account"}
            log(f"  {code}: website ${website:.2f}, Florida ${florida:.2f}, off ${website - florida:.2f} per guest")
        fresh = [out[c] for t, c in cats if c not in failed]
        if fresh and not any(e["off_pp"] > 0 for e in fresh):
            log("No cabin got a Florida price today: NCL probably didn't apply the login. File not changed.")
            return 3
        if not fresh:
            log("Every cabin failed. File not changed.")
            return 4
    finally:
        ctx.close(); pw.stop()
    data = {"schema_version": SCHEMA_VERSION, "saved_at": now_iso(), "sailing_id": s["id"],
            "package_id": s["package_id"], "guests": GUESTS,
            "source": "NCL price-summary while signed in to a Florida resident NCL account (owner's AI PC)",
            "categories": dict(sorted(out.items()))}
    import check_florida
    errors = check_florida.check(data)
    if errors:
        log("Format check failed, file not changed: " + "; ".join(errors))
        return 5
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    log(f"Wrote {OUT}: {len(fresh)} cabins checked today, {len(failed)} failed.")
    if push:
        subprocess.run(["git", "-C", ROOT, "add", "data/florida.json"], check=True)
        if subprocess.run(["git", "-C", ROOT, "diff", "--cached", "--quiet"]).returncode == 0:
            log("No change to commit.")
            return 0
        subprocess.run(["git", "-C", ROOT, "commit", "-q", "-m", f"Refresh Florida rates {now_iso()[:10]}"], check=True)
        for attempt in range(4):
            if subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "-q"]).returncode == 0 and \
               subprocess.run(["git", "-C", ROOT, "push", "-q", "origin", "HEAD:main"]).returncode == 0:
                log("Pushed to main; the page republishes in about a minute.")
                return 0
            time.sleep(2 ** (attempt + 1))
        log("Push failed. The file is saved here; run 'git push' by hand.")
        return 6
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=os.environ.get("NCL_PROFILE", DEFAULT_PROFILE),
                    help="browser profile folder that keeps the NCL login (never inside a repo)")
    ap.add_argument("--setup", action="store_true", help="sign in by hand, then one test price")
    ap.add_argument("--record", action="store_true", help="record NCL's own price requests, names removed")
    ap.add_argument("--show", action="store_true", help="show the browser window during the daily run")
    ap.add_argument("--push", action="store_true", help="commit and push data/florida.json to main")
    args = ap.parse_args()
    if os.path.abspath(args.profile).startswith(ROOT):
        raise SystemExit("The profile folder must not be inside the repository.")
    if args.setup:
        return setup(args.profile)
    if args.record:
        return record(args.profile)
    return daily(args.profile, args.show, args.push)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fetch cabin prices for the Norwegian Joy, Nov 20, 2026 sailing from NCL's vacation-builder API.

Writes a new data file. It never touches the old one: the workflow runs the format
check on the new file and only then replaces data/prices.json.

  python3 tools/fetch_prices.py --out data/prices.new.json --previous data/prices.json

Nothing about NCL's ids is typed in here except the ship, the sail date and the length.
Every run finds them again:
  - the Joy's 3 night Miami cruise page (GET, header Accept: */*) lists its sailings with
    itineraryCode and packageId; the one departing 2026-11-20 is ours
  - the vacation-builder itinerary call (GET) for that itinerary and packageId gives the
    sailingId, ship code, destination codes and length, and must match the date and ship

Calls per run (2 seconds apart, no cookies, nothing is held or booked):
  - cruise page: 1 (2 if the first page doesn't list the sailing)
  - itinerary: 1
  - route-events: 1, for the day by day itinerary and to confirm the departure date
  - stateroom-types-availability: 1 per party size 2, 3, 4, 5 (4)
  - price-summary: 1 per party size, for the cheapest available category, to read NCL's
    tax line and Free at Sea gratuity lines (4)
  - price-summary age test: 1, guests 1 adult (reservation owner), a 15 year old and a
    7 year old (birth dates only), to read the adult Open Bar, the under 21 soda package
    and the Specialty Dining amounts per guest
  - NCL's promotion terms and service charge FAQ pages: 2
POST requests never follow redirects; redirects, 5xx and network errors are retried after
30, 60 and 120 seconds. Every NCL API answer is refused if it mentions "hold" or "heldUntil".

Cabin counts are not fetched here. They live in tools/fetch_counts.py and data/counts.json,
so prices never depend on them.

A number that can't be found on NCL (taxes, a gratuity, a rate) is stored as null with a
warning, never guessed; the page then says it wasn't found.

Cross checks are logged in the data file under "checks":
  - extra_guest: per category, (total at N minus total at 2) / (N minus 2) should match
    across 3, 4 and 5 guests within $5. A mismatch is logged, never fatal.
  - formula: average per person price x guests + gratuities x guests should match the
    price summary total within $5. A mismatch fails the run (exit 1).
  - ages: the page's age formula for 1 adult + 15 + 7 should match NCL's total for that
    party within $5. A mismatch fails the run (exit 1).
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
GUEST_COUNTS = [2, 3, 4, 5]
PAUSE_SECONDS = 2
TOLERANCE = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
API = "https://www.ncl.com/api"
AVAILABILITY_URL = API + "/vacation-builder/v2/stateroom-types-availability"
PRICE_SUMMARY_URL = API + "/vacation-builder/price-summary"
ROUTE_EVENTS_URL = API + "/cruises/v1/route-events/{package_id}"
ITINERARY_URL = API + "/vacation-builder/itinerary/{code}?packageId={package_id}"
CABIN_AVAILABILITY_URL = API + "/vacation-builder/cabin/availability"
CRUISE_PAGE_URL = "https://www.ncl.com/cruises/{code}"
# No NCL API answer may mention a hold; stop the run if one does.
HOLD_IN_RESPONSE = re.compile(rb"hold|helduntil", re.I)
LOCATION_ORDER = ["Forward", "Mid", "Aft"]
MIAMI = ZoneInfo("America/New_York")

# The one sailing. Only the ship, date, length and home port are fixed; NCL's ids are
# looked up on every run (find_sailing). The cruise pages are where to start looking: both
# of the Joy's 3 night Miami itineraries list every sailing of both (checked 2026-10-13).
SAILING = {
    "id": "joy-2026-11-20", "ship": "Norwegian Joy", "ship_short": "Joy", "ship_code": "JOY",
    "depart": "2026-11-20", "nights": 3, "itinerary_prefix": "JOY3MIA",
    "start_pages": ["JOY3MIANASNPIMIA", "JOY3MIANPINASMIA"],
}
SAILINGS = [SAILING]

MATCH_KEYS = {
    "STUDIO": "studio", "INSIDE": "inside", "OCEANVIEW": "oceanview", "BALCONY": "balcony",
    "MINISUITE": "mini_suite", "SUITE": "suite", "HAVEN": "haven",
}
SOLO_CODES = {"T1", "IT", "OT", "BT"}          # one-guest cabins, hidden on the page
GUARANTEE_CODES = {"IX", "OX", "BX", "MX"}     # NCL picks the cabin location
TERMINAL = {"confirmed": False, "text": "Expected: Terminal B (confirm on your eDocs)"}
LOCATION_WORDS = {"Forward": "forward", "Mid": "midship", "Aft": "aft"}

# Never touch anything that holds a cabin. NCL's cabin/manage-cabin call carries
# recommendAndHold and puts a temporary hold on a real cabin.
FORBIDDEN = re.compile(r"manage-cabin|hold", re.I)

_last_call = 0.0


def log(msg):
    print(msg, file=sys.stderr, flush=True)


RETRY_WAITS = [30, 60, 120]   # seconds before retries 1, 2 and 3


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects. NCL once answered a POST with a 302 to an address that gave 404."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_no_redirect_opener = urllib.request.build_opener(_NoRedirect)


def request(url, body=None, raw=False, page=False):
    """GET (body None) or POST JSON. Refuses forbidden addresses. Pauses between calls.

    POST requests never follow redirects. A redirect, a 5xx or a network error is logged
    (status code and Location header) and retried up to 3 times, after 30, 60 and 120 seconds.
    401, 403 and 404 fail at once. With raw=True the response bytes are returned as well.
    With page=True the answer is a web page (header Accept: */*, which NCL needs to include
    the embedded sailing data) and its text is returned; the hold check applies to API
    answers only, since ordinary page text can contain words like "placeholder".
    """
    global _last_call
    if FORBIDDEN.search(url):
        raise RuntimeError(f"Refusing to call {url}: it could hold a cabin")
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*" if page else "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    last = None
    for attempt in range(len(RETRY_WAITS) + 1):
        if attempt:
            log(f"  retry {attempt} of {len(RETRY_WAITS)} in {RETRY_WAITS[attempt - 1]} s: {url}")
            time.sleep(RETRY_WAITS[attempt - 1])
        wait = PAUSE_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        opener = _no_redirect_opener if data else urllib.request.build_opener()
        try:
            with opener.open(req, timeout=60) as res:
                content = res.read()
        except urllib.error.HTTPError as e:
            location = e.headers.get("Location") if e.headers else None
            if e.code in (401, 403, 404):
                raise RuntimeError(f"NCL answered HTTP {e.code} for {url} (blocked or moved)")
            if 300 <= e.code < 400 or e.code >= 500:
                log(f"  NCL answered HTTP {e.code} for {url}" + (f", Location: {location}" if location else ""))
            else:
                log(f"  NCL answered HTTP {e.code} for {url}")
            last = f"HTTP {e.code}" + (f" to {location}" if location else "")
            continue
        except Exception as e:
            log(f"  {type(e).__name__} for {url}: {e}")
            last = f"{type(e).__name__}: {e}"
            continue
        if page:
            return content.decode("utf-8", errors="replace")
        if HOLD_IN_RESPONSE.search(content):
            raise RuntimeError(f"NCL's answer for {url} mentioned a hold; stopping")
        return (json.loads(content), content) if raw else json.loads(content)
    raise RuntimeError(f"Request failed after {len(RETRY_WAITS) + 1} tries: {url} ({last})")


def utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)


def hhmm(text):
    """'4:00 PM' -> '16:00'."""
    if not text:
        return None
    t = dt.datetime.strptime(text.strip().upper(), "%I:%M %p")
    return t.strftime("%H:%M")


def sailings_on_page(code):
    """The sailings NCL lists on a cruise page (data-pricing-sailings, HTML-escaped JSON)."""
    text = request(CRUISE_PAGE_URL.format(code=code), page=True)
    m = re.search(r'data-pricing-sailings="([^"]*)"', text)
    if not m:
        raise RuntimeError(f"no sailing list on the {code} cruise page")
    return json.loads(html.unescape(m.group(1)))


def find_sailing(cfg, previous_ids=None):
    """Look up today's NCL ids for the sailing: itinerary code and packageId from the cruise
    page, then sailingId, ship code, destinations and length from the itinerary call.

    The itinerary call must agree on the packageId, the sail date, the ship and the length.
    If the cruise pages can't be read, the previous run's itinerary code and packageId are
    tried instead (with a warning), and the itinerary call still has to confirm them.
    """
    warnings, found, page_errors = [], None, []
    for code in cfg["start_pages"]:
        try:
            for s in sailings_on_page(code):
                when = s.get("departureDate") or s.get("sailStartDate")
                if not isinstance(when, (int, float)):
                    continue
                days = {utc(when).strftime("%Y-%m-%d"), utc(when).astimezone(MIAMI).strftime("%Y-%m-%d")}
                if cfg["depart"] in days and str(s.get("itineraryCode", "")).startswith(cfg["itinerary_prefix"]):
                    found = {"itinerary_code": s["itineraryCode"], "package_id": str(s["packageId"]),
                             "found_on": CRUISE_PAGE_URL.format(code=code)}
                    break
        except Exception as e:
            page_errors.append(f"{code}: {e}")
        if found:
            break
    if not found:
        why = "; ".join(page_errors) or f"no {cfg['ship_short']} sailing on {cfg['depart']} on the cruise pages"
        if not previous_ids:
            raise RuntimeError(f"Could not find the sailing on NCL ({why})")
        found = {"itinerary_code": previous_ids["itinerary_code"], "package_id": previous_ids["package_id"],
                 "found_on": "previous run"}
        warnings.append(f"Could not find the sailing on NCL's cruise pages ({why}); tried yesterday's ids")
        log("Warning: " + warnings[-1])

    it = request(ITINERARY_URL.format(code=found["itinerary_code"], package_id=found["package_id"]))
    s = it.get("sailing") or {}
    ship_code = (it.get("ship") or {}).get("code")
    if str(s.get("packageId")) != found["package_id"] or not (s.get("sailStartDate") or "").startswith(cfg["depart"]):
        raise RuntimeError(f"NCL's itinerary for {found['itinerary_code']} does not match packageId {found['package_id']} on {cfg['depart']}")
    if ship_code != cfg["ship_code"] or it.get("duration") != cfg["nights"]:
        raise RuntimeError(f"NCL's itinerary says ship {ship_code}, {it.get('duration')} nights; expected {cfg['ship_code']}, {cfg['nights']}")
    if not s.get("sailingId"):
        raise RuntimeError("NCL's itinerary has no sailingId")
    ids = dict(found,
               sailing_id=str(s["sailingId"]),
               ship_code=ship_code,
               destination_codes=[d.get("code") for d in it.get("destinations") or [] if d.get("code")],
               duration=it.get("duration"),
               sail_start=s["sailStartDate"])
    log(f"  NCL ids: itinerary {ids['itinerary_code']}, packageId {ids['package_id']}, sailingId {ids['sailing_id']}, ship {ship_code}")
    return ids, warnings


def fetch_ports(cfg):
    events = request(ROUTE_EVENTS_URL.format(package_id=cfg["package_id"]))
    if not events:
        raise RuntimeError(f"No itinerary for {cfg['ship']} packageId {cfg['package_id']}")
    # NCL stores times as local clock time written in UTC, so the UTC date is the local date.
    first = utc(events[0]["date"]).strftime("%Y-%m-%d")
    if first != cfg["depart"]:
        raise RuntimeError(f"packageId {cfg['package_id']} departs {first}, expected {cfg['depart']}")
    ports = []
    for e in events:
        day = utc(e["date"]).strftime("%Y-%m-%d")
        if e.get("eventType") == "sea":
            ports.append({"date": day, "sea": True})
        else:
            ports.append({"date": day, "port": e.get("title"), "arrive": hhmm(e.get("arrivalTime")),
                          "depart": hhmm(e.get("departureTime"))})
    return ports


def fetch_availability(cfg, guests):
    """Availability for one party size.

    NCL has briefly answered with every category unavailable, or available at a price of $0
    (both seen 2026-10-09 on the Getaway at 4 and 5 guests). An answer with nothing available
    at a real price is retried after 30, 60 and 120 seconds before the party size fails.
    """
    body = {"sailingFilters": [{"packageId": cfg["package_id"], "numberOfGuests": guests, "filterId": "0"}]}
    for attempt in range(len(RETRY_WAITS) + 1):
        if attempt:
            log(f"  NCL showed nothing available at {guests} guests; retry {attempt} of {len(RETRY_WAITS)} in {RETRY_WAITS[attempt - 1]} s")
            time.sleep(RETRY_WAITS[attempt - 1])
        res = request(AVAILABILITY_URL, body)
        try:
            result = res["results"][0]["result"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"Unexpected availability answer at {guests} guests")
        if any(cp.get("isAvailable") and ((cp.get("standardOption") or {}).get("price") or 0) > 0
               for t in result.get("stateroomTypesPricing", [])
               for sp in t.get("stateroomsPricing", []) for cp in sp.get("categoryPricing", [])):
            return result
    return result


def default_fare_codes(result):
    """Free at Sea promotion code for each broad cabin type (e.g. ALL4CHO, CHOALL4M)."""
    codes = {}
    for group in result.get("offerGroups", []):
        if group.get("code") != "FREE-AT-SEA":
            continue
        for p in group.get("promotionsInGroup", []):
            if not p.get("isDefaultInGroup"):
                continue
            promo = p.get("promotion", {})
            for t in promo.get("stateroomTypes", []):
                if promo.get("promotionCodes"):
                    codes.setdefault(t, promo["promotionCodes"][0])
    return codes


def kids_sail_free(result):
    """NCL's "Kids Sail Free" offer when the availability answer lists it (MORE-OFFERS group),
    exactly as NCL words it, with the broad cabin types it covers. None when not listed.
    Seen on 2026-10-13: code 34CHO, "3rd and 4th guests sailing in the same stateroom sail for
    taxes, fees, and port expenses only", Inside, Oceanview, Balcony and Club Balcony Suite."""
    for group in result.get("offerGroups", []):
        for p in group.get("promotionsInGroup", []):
            promo = p.get("promotion", {})
            for o in promo.get("offers", []):
                if o.get("code") == "Kids-Sail-Free-Offer" or (o.get("title") or "").lower() == "kids sail free":
                    return {"title": o.get("title"), "short": o.get("shortDescription"), "description": o.get("description"),
                            "codes": promo.get("promotionCodes") or [], "types": promo.get("stateroomTypes") or []}
    return None


def price_summary_body(cfg, guests, type_code, cat_code, fare_code, guest_list=None):
    """The price-summary request body, as NCL's own app sends it (also used by fetch_florida.py)."""
    return {
        "packageId": cfg["package_id"],
        "stateroomFilters": [{"id": "0", "mainCabin": True, "numberOfGuests": guests,
                              "stateroomTypeCode": type_code, "pricedCategoryCode": cat_code,
                              "fareCodes": [fare_code], "guests": guest_list or [], "vouchers": []}],
        "userFareCodes": [],
    }


def fetch_price_summary(cfg, guests, type_code, cat_code, fare_code, guest_list=None):
    body = price_summary_body(cfg, guests, type_code, cat_code, fare_code, guest_list)
    # NCL has briefly answered with a total of $0 (seen 2026-10-09); retry before giving up.
    for attempt in range(len(RETRY_WAITS) + 1):
        if attempt:
            log(f"  NCL price summary for {cat_code} at {guests} guests was empty; retry {attempt} of {len(RETRY_WAITS)} in {RETRY_WAITS[attempt - 1]} s")
            time.sleep(RETRY_WAITS[attempt - 1])
        res = request(PRICE_SUMMARY_URL, body)
        if "total" not in res:
            raise RuntimeError(f"Unexpected price summary for {cat_code} at {guests} guests")
        if (res["total"].get("grandTotal") or 0) > 0:
            break
    return parse_price_summary(res, guests, type_code, cat_code, fare_code)


def parse_price_summary(res, guests, type_code, cat_code, fare_code):
    """Fare, taxes and Free at Sea gratuity lines from a price-summary answer (amounts only)."""
    lines = {}
    for group in res["staterooms"][0]["pricing"]["priceGroups"]:
        for item in group.get("priceItems", []):
            if item.get("itemType") == "strikethrough" or not item.get("guests"):
                continue
            lines[item["code"]] = {"group": group["code"], "title": item.get("title"),
                                   "per_guest": [g.get("price") for g in item["guests"]]}
    fare = sum(sum(l["per_guest"]) for l in lines.values() if l["group"] == "STATEROOM")
    taxes = lines.get("taxes-and-fees", {}).get("per_guest") or []
    bar = next((l for c, l in lines.items() if c.startswith("unlimited-open-bar")), None)
    dining = next((l for c, l in lines.items() if c.startswith("specialty-dining")), None)
    return {
        "guests": guests,
        "type": type_code,
        "category": cat_code,
        "fare_code": fare_code,
        "fare_total": fare,
        "fare_per_guest": next((l["per_guest"] for l in lines.values() if l["group"] == "STATEROOM"), []),
        "taxes_per_guest": taxes,
        "open_bar": {"title": bar["title"], "per_guest": bar["per_guest"]} if bar else None,
        "specialty_dining": {"title": dining["title"], "per_guest": dining["per_guest"]} if dining else None,
        "grand_total": res["total"]["grandTotal"],
    }


def deck_text(decks):
    """[5, 8] -> 'Decks 5 and 8'; [10, 11, 13, 14] -> 'Decks 10, 11, 13 and 14'; [5, 9..16] -> 'Decks 5 and 9 to 16'."""
    decks = sorted(set(decks))
    if len(decks) == 1:
        return f"Deck {decks[0]}"
    parts, run = [], [decks[0]]
    for d in decks[1:] + [None]:
        if d is not None and d == run[-1] + 1:
            run.append(d)
            continue
        parts += [f"{run[0]} to {run[-1]}"] if len(run) >= 3 else [str(x) for x in run]
        run = [d]
    return "Decks " + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0])


def location_text(locs):
    words = [LOCATION_WORDS[l] for l in ("Forward", "Mid", "Aft") if l in locs]
    return " and ".join(words) if len(words) < 3 else "forward, midship and aft"


def size_text(info):
    lo, hi = info.get("stateroomMin"), info.get("stateroomMax")
    if not lo:
        return None
    room = f"{lo} sq ft" if lo == hi or not hi else f"{lo} to {hi} sq ft"
    blo, bhi = info.get("balconyMin"), info.get("balconyMax")
    if blo:
        room += f", balcony {blo} sq ft" if blo == bhi or not bhi else f", balcony {blo} to {bhi} sq ft"
    return room


def describe_categories(types):
    """Plain description per category, from NCL only, never guessed.

    - NCL gives title, decks, location (Forward/Mid/Aft) and sizes per group of codes.
      When a group has one code, all of that is confirmed for the code.
    - When a group has several codes, NCL's decks and location cover the whole group, so they
      are not used for one code (the page fills them from where that code's own cabins are
      open, from data/counts.json). Until then it says how many guests the code holds.
    - Guarantee cabins: NCL picks the cabin, so decks and location are left out.
    """
    for t in types.values():
        for cat in t["categories"].values():
            room = cat.pop("_group", None) or {}
            ids = room.get("categoryIds") or [cat["code"]]
            ncl_decks = {d["deck"]: set(d.get("locations") or []) for d in room.get("deckLocations") or []}
            decks, locs, source = None, None, None
            if not cat["guarantee"] and len(ids) == 1 and ncl_decks:
                decks = sorted(ncl_decks)
                locs = sorted(set().union(*ncl_decks.values()), key=["Forward", "Mid", "Aft"].index)
                source = "NCL"
            size = size_text(room.get("sizeInfo") or {}) if len(ids) == 1 and not cat["guarantee"] else None
            parts = [cat["title"]]
            if decks:
                parts.append(deck_text(decks))
            if locs:
                parts.append(location_text(locs))
            if not decks and not cat["guarantee"] and len(ids) > 1 and cat["capacity"]:
                # Nothing else tells these codes apart, so say how many guests each holds.
                parts.append(f"holds up to {cat['capacity']}")
            cat["description"] = ", ".join(parts)
            cat["decks"] = decks
            cat["location"] = [LOCATION_WORDS[l] for l in locs] if locs else None
            cat["size"] = size
            cat["details_source"] = source
            cat["shares_ncl_description_with"] = [c for c in ids if c != cat["code"]]


def age_test_guests(depart):
    """1 adult (reservation owner), a 15 year old and a 7 year old on the sail date. Birth dates only, no names."""
    sail = dt.date.fromisoformat(depart)
    def born(age):
        # Birthday 60 days before the sail date, so the age is exact on the sail date.
        return (dt.date(sail.year - age, sail.month, sail.day) - dt.timedelta(days=60)).isoformat()
    return [{"birthDate": born(45), "reservationOwner": True},
            {"birthDate": born(15), "reservationOwner": False},
            {"birthDate": born(7), "reservationOwner": False}]


MAX_STALE_DAYS = 3   # kept prices older than this fail the run


def parse_iso_z(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def fetch_party_size(cfg, g, fare_codes, offers):
    """Availability and the price summary for one party size, checked before use.

    Returns (rows, summary, formula). Raises if anything is missing or NCL's numbers disagree,
    so a failed party size never leaves half its data behind.
    """
    result = fetch_availability(cfg, g)
    for tcode, code in default_fare_codes(result).items():
        fare_codes.setdefault(tcode, code)
    offers.setdefault("kids_sail_free", kids_sail_free(result))
    rows, cheapest = [], None
    for t in result.get("stateroomTypesPricing", []):
        for sp in t.get("stateroomsPricing", []):
            room = sp.get("stateroom") or {}
            for cp in sp.get("categoryPricing", []):
                so = cp.get("standardOption") or {}
                code = so.get("pricedCategoryCode")
                if not code:
                    continue
                title = room.get("title")
                solo = code in SOLO_CODES or (title or "").lower().startswith("solo")
                price = so.get("price")
                available = bool(cp.get("isAvailable")) and isinstance(price, (int, float)) and price > 0
                entry = {"available": available, "sold_out": bool(cp.get("isSoldOut"))}
                if available:
                    # NCL sends the average with cents (like 455.66); round only the cabin total,
                    # which then equals NCL's fare plus taxes for the party.
                    entry["price_pp"] = round(float(price), 2)
                    entry["cabin_total"] = int(round(price * g))
                    if not solo and (cheapest is None or price < cheapest[2]):
                        cheapest = (t["code"], code, price, entry["cabin_total"])
                rows.append({"type": t, "room": room, "so": so, "code": code, "title": title, "solo": solo, "entry": entry})
    if cheapest is None:
        raise RuntimeError(f"no cabin available at a real price for {g} guests")
    tcode, ccode, _, cabin_total = cheapest
    fare_code = fare_codes.get(tcode)
    if not fare_code:
        raise RuntimeError(f"no Free at Sea promotion code found for {tcode}")
    summary = fetch_price_summary(cfg, g, tcode, ccode, fare_code)
    if (summary["grand_total"] or 0) <= 0:
        raise RuntimeError(f"NCL's price summary for {ccode} at {g} guests was empty")
    # Cross check: availability price x guests + this summary's own gratuity lines = its total.
    grat = sum(sum(x["per_guest"]) for x in (summary["open_bar"], summary["specialty_dining"]) if x)
    expected = cabin_total + grat
    formula = {"sailing": cfg["id"], "guests": g, "category": ccode, "expected": expected,
               "ncl_total": summary["grand_total"], "ok": abs(expected - summary["grand_total"]) <= TOLERANCE}
    if not formula["ok"]:
        raise RuntimeError(f"formula check failed for {ccode} at {g} guests: expected {expected}, NCL total {summary['grand_total']}")
    return rows, summary, formula


def fetch_sailing(cfg, checks, warnings, previous=None):
    """The sailing. Each party size (2 to 5) succeeds or fails on its own.

    A failed party size keeps the previous file's prices for that party size, marked in
    `party_sizes` as not updated, with the time they are from. The run fails if every party
    size fails, if there is nothing to keep, or if kept prices are more than 3 days old.
    """
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    prev_s = next((s for s in (previous or {}).get("sailings", []) if s.get("id") == cfg["id"]), None)
    log(f"{cfg['ship']} {cfg['depart']}")
    ids, id_warnings = find_sailing(cfg, (prev_s or {}).get("ncl_ids"))
    warnings += id_warnings
    cfg = dict(cfg, itinerary_code=ids["itinerary_code"], package_id=ids["package_id"])
    ports = fetch_ports(cfg)
    nights = len(ports) - 1
    types, fare_codes, summaries, status, offers = {}, {}, {}, {}, {}
    for g in GUEST_COUNTS:
        try:
            rows, summary, formula = fetch_party_size(cfg, g, fare_codes, offers)
        except Exception as e:
            status[str(g)] = {"updated": False, "why": f"{type(e).__name__}: {e}"}
            log(f"  {g} guests FAILED: {e}")
            continue
        for r in rows:
            t = r["type"]
            tentry = types.setdefault(t["code"], {"code": t["code"], "title": t.get("title") or t["code"].title(),
                                                  "match": MATCH_KEYS.get(t["code"], t["code"].lower()), "categories": {}})
            cat = tentry["categories"].setdefault(r["code"], {
                "code": r["code"], "title": r["title"] or r["code"],
                "guarantee": r["code"] in GUARANTEE_CODES or bool(r["so"].get("isGTY")),
                "solo": r["solo"], "capacity": None, "by_guests": {}})
            if g == 2:
                # Capacity only from the 2-guest call: it reads 0 whenever a category is unavailable.
                cap = r["so"].get("guestCapacity")
                cat["capacity"] = cap if isinstance(cap, int) and cap > 0 else None
                cat["_group"] = r["room"]
            cat["by_guests"][str(g)] = r["entry"]
        summaries[g] = summary
        checks["formula"].append(formula)
        status[str(g)] = {"updated": True, "as_of": now_iso, "why": None}
        log(f"  {g} guests: cheapest {summary['category']} ({summary['type']}), price summary {summary['grand_total']}")

    if not summaries:
        raise RuntimeError(f"Every party size failed on the {cfg['ship']}")

    # Keep the previous prices for any party size that failed today.
    for g in GUEST_COUNTS:
        st = status[str(g)]
        if st["updated"]:
            continue
        if not prev_s:
            raise RuntimeError(f"{g} guests failed and there are no previous prices to keep")
        prev_st = (prev_s.get("party_sizes") or {}).get(str(g)) or {}
        as_of = prev_st.get("as_of") or previous.get("saved_at")
        age_days = (now - parse_iso_z(as_of)).total_seconds() / 86400
        if age_days > MAX_STALE_DAYS:
            raise RuntimeError(f"{g} guests failed and the kept prices are {age_days:.1f} days old (limit {MAX_STALE_DAYS})")
        st["as_of"] = as_of
        log(f"  {g} guests: keeping prices from {as_of}")
        for pt in prev_s["types"]:
            tentry = types.setdefault(pt["code"], {"code": pt["code"], "title": pt["title"], "match": pt["match"], "categories": {}})
            for pc in pt["categories"]:
                cat = tentry["categories"].setdefault(pc["code"], {
                    "code": pc["code"], "title": pc["title"], "guarantee": pc["guarantee"], "solo": pc["solo"],
                    "capacity": pc.get("capacity"), "by_guests": {}, "_prev": pc})
                cat.setdefault("_prev", pc)
                e = dict(pc["by_guests"][str(g)])
                e.pop("added_vs_2", None)
                e.pop("reason", None)
                cat["by_guests"][str(g)] = e
        prev_sum = next((x for x in prev_s.get("price_summaries", []) if x.get("guests") == g), None)
        if prev_sum:
            summaries[g] = prev_sum
        prev_formula = next((x for x in (previous.get("checks") or {}).get("formula", [])
                             if x.get("sailing") == cfg["id"] and x.get("guests") == g), None)
        if prev_formula:
            checks["formula"].append(dict(prev_formula, kept_from=as_of))

    # Fill in categories that were missing from some calls, and the reasons.
    for t in types.values():
        for cat in t["categories"].values():
            if cat["capacity"] is None and cat.get("_prev"):
                cat["capacity"] = cat["_prev"].get("capacity")
            two = cat["by_guests"].get("2", {})
            for g in GUEST_COUNTS:
                e = cat["by_guests"].setdefault(str(g), {"available": False, "sold_out": False})
                if e["available"]:
                    if g > 2 and two.get("available"):
                        e["added_vs_2"] = e["cabin_total"] - two["cabin_total"]
                    continue
                if e["sold_out"]:
                    e["reason"] = "Sold out"
                elif cat["capacity"] is not None and cat["capacity"] < g:
                    e["reason"] = f"Holds only {cat['capacity']} guests"
                elif cat["capacity"] is not None:
                    e["reason"] = "Sold out for this party size"
                else:
                    e["reason"] = f"Not available for {g} guests"
            # Cross check: the extra guest price should be the same for guests 3, 4 and 5.
            if two.get("available"):
                per_extra = {g: (cat["by_guests"][str(g)]["cabin_total"] - two["cabin_total"]) / (g - 2)
                             for g in GUEST_COUNTS[1:] if cat["by_guests"][str(g)]["available"]}
                if len(per_extra) > 1 and max(per_extra.values()) - min(per_extra.values()) > TOLERANCE:
                    checks["extra_guest_mismatches"].append({
                        "sailing": cfg["id"], "category": cat["code"],
                        "per_extra_guest": {str(k): round(v, 2) for k, v in per_extra.items()},
                    })

    # Taxes per guest (the same for every guest at any age), from today's first good summary.
    # If NCL's summary has no tax line, taxes are left empty (null), never guessed.
    fresh = [summaries[g] for g in GUEST_COUNTS if status[str(g)]["updated"]]
    taxes = fresh[0]["taxes_per_guest"]
    taxes_per_guest = taxes[0] if taxes and isinstance(taxes[0], (int, float)) and taxes[0] > 0 else None
    if taxes_per_guest is None:
        warnings.append("No tax line in NCL's price summary today; taxes per guest left empty")
        log("Warning: " + warnings[-1])

    # Gratuities per guest by age and position, read from NCL with an age test party:
    # guest 1 an adult (reservation owner), guest 2 a 15 year old, guest 3 a 7 year old.
    try:
        s3 = summaries.get(3)
        if not s3:
            raise RuntimeError("no price summary at 3 guests to base the age test on")
        age_summary = fetch_price_summary(cfg, 3, s3["type"], s3["category"], s3["fare_code"], age_test_guests(cfg["depart"]))
        bar, dining = age_summary["open_bar"], age_summary["specialty_dining"]
        if not bar or not dining or len(bar["per_guest"]) != 3 or len(dining["per_guest"]) != 3:
            raise RuntimeError("unexpected gratuity lines in the age test price summary")
        b, d = bar["per_guest"], dining["per_guest"]
        # The confirmed rules: Open Bar adult full, under 21 in position 2 a soda package, under 21
        # in position 3 or later nothing; Specialty Dining 13 and over pay, under 13 free.
        if not (b[0] > 0 and 0 < b[1] < b[0] and b[2] == 0 and d[0] > 0 and d[1] == d[0] and d[2] == 0):
            raise RuntimeError(f"NCL's age rules changed: Open Bar {b}, Specialty Dining {d}")
        read_on = now.strftime("%Y-%m-%d")
        gratuities = {
            "open_bar": {"title": bar["title"], "per_guest": b[0], "soda_under_21_position_2": b[1],
                         "under_21_position_3_plus": 0, "source": "NCL price-summary (age test)", "checked_at": read_on},
            "specialty_dining": {"title": dining["title"], "per_guest": d[0], "under_13": 0,
                                 "source": "NCL price-summary (age test)", "checked_at": read_on},
        }
        cat = next(c for t in types.values() for c in t["categories"].values() if c["code"] == s3["category"])
        expected = (cat["by_guests"]["3"]["cabin_total"]
                    + gratuities["open_bar"]["per_guest"] + gratuities["open_bar"]["soda_under_21_position_2"]
                    + 2 * gratuities["specialty_dining"]["per_guest"])
        age_check = {"sailing": cfg["id"], "party": "1 adult, 15, 7", "category": s3["category"],
                     "expected": expected, "ncl_total": age_summary["grand_total"],
                     "ok": abs(expected - age_summary["grand_total"]) <= TOLERANCE}
        if not age_check["ok"]:
            raise RuntimeError(f"age check failed: expected {expected}, NCL total {age_summary['grand_total']}")
        log(f"  age test (1 adult, 15, 7) {s3['category']}: NCL {age_summary['grand_total']}, formula {expected}")
    except Exception as e:
        # Keep yesterday's gratuities (they change rarely) if they are recent enough; otherwise
        # leave them empty, never guessed, and the page says they weren't found.
        prev_g = (prev_s or {}).get("gratuities")
        kept_on = (prev_g["open_bar"].get("checked_at") or previous["saved_at"][:10]) if prev_g else None
        prev_age = next((x for x in ((previous or {}).get("checks") or {}).get("ages", [])
                         if x.get("sailing") == cfg["id"] and x.get("ok") is True), None)
        if prev_g and prev_age and (now.date() - dt.date.fromisoformat(kept_on)).days <= MAX_STALE_DAYS:
            log(f"  age test FAILED ({e}); keeping gratuities from {kept_on}")
            gratuities, age_check = prev_g, dict(prev_age, kept_from=kept_on)
        else:
            gratuities = None
            age_check = {"sailing": cfg["id"], "party": "1 adult, 15, 7", "ok": None, "why": f"{type(e).__name__}: {e}"}
            warnings.append(f"Free at Sea gratuities not found on NCL today ({e}); left empty")
            log("Warning: " + warnings[-1])
    checks["ages"].append(age_check)

    describe_categories(types)
    # A category described only from kept data (its 2-guest call failed today) keeps yesterday's description.
    for t in types.values():
        for cat in t["categories"].values():
            pc = cat.pop("_prev", None)
            if pc and not status["2"]["updated"]:
                for k in ("description", "decks", "location", "size", "details_source", "shares_ncl_description_with"):
                    if k in pc:
                        cat[k] = pc[k]

    out_types = []
    for t in types.values():
        cats = sorted(t["categories"].values(), key=lambda c: (c["by_guests"]["2"].get("price_pp") or 10 ** 9, c["code"]))
        out_types.append({"code": t["code"], "title": t["title"], "match": t["match"], "categories": cats})
    return {
        "id": cfg["id"],
        "ship": cfg["ship"],
        "ship_short": cfg["ship_short"],
        "itinerary_code": cfg["itinerary_code"],
        "package_id": cfg["package_id"],
        "ncl_ids": dict(ids, checked_at=now_iso),
        "depart": cfg["depart"],
        "return": ports[-1]["date"],
        "nights": nights,
        "url": f"https://www.ncl.com/cruises/{cfg['itinerary_code']}",
        "source": "NCL vacation-builder API",
        "saved_at": now.strftime("%Y-%m-%d"),
        "party_sizes": status,
        "taxes_per_guest": taxes_per_guest,
        "gratuities": gratuities,
        # NCL's own offer text when listed today; the prices above already include it.
        "kids_sail_free": dict(offers["kids_sail_free"], checked_at=now.strftime("%Y-%m-%d")) if offers.get("kids_sail_free") else None,
        "terminal": TERMINAL,
        "ports": ports,
        "price_summaries": [summaries[g] for g in GUEST_COUNTS if g in summaries],
        "types": out_types,
    }


TERMS_URL = "https://www.ncl.com/cruise-deals/promotion-terms"
SERVICE_CHARGE_URL = "https://www.ncl.com/faq/what-is-ncl-onboard-service-charge"


def page_text(url):
    """A public NCL page as plain text (GET; following redirects is fine for GET)."""
    raw = request(url, page=True)
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw)).replace("\\r\\n", " ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text)


def money_in(pattern, text, what):
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"{what} not found")
    return [float(x) for x in m.groups()]


def fetch_rates(previous):
    """Free at Sea Plus, Open Bar, soda and service charge rates from NCL's own pages.

    Each rate is stored with its source and the date it was read. If a page can't be read or
    its wording changed, the previous day's rate is carried forward with a warning. With no
    previous rate it is left empty (null) with a warning, and the page says it wasn't found.
    """
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    prev = (previous or {}).get("rates") or {}
    rates, warnings, pages = {}, [], {}

    def read(key, url, build):
        try:
            if url not in pages:
                pages[url] = page_text(url)
            rates[key] = dict(build(pages[url]), source=url, checked_at=today)
        except Exception as e:
            if prev.get(key):
                rates[key] = dict(prev[key], stale_since=prev[key].get("stale_since") or prev[key].get("checked_at"))
                warnings.append(f"{key}: could not read {url} ({e}); kept the rate from {prev[key].get('checked_at')}")
            else:
                rates[key] = None
                warnings.append(f"{key}: could not read {url} ({e}); left empty")

    def plus(text):
        adult, child = money_in(r"1-8 \(Adult\) \$ ?([\d.]+).{0,120}?1-2 \(Child\) \$ ?([\d.]+)", text, "Free at Sea Plus rates")
        if not (20 <= adult <= 200 and 10 <= child <= 200):
            raise RuntimeError(f"Free at Sea Plus rates look wrong: {adult}, {child}")
        return {"adult_per_day": adult, "child_per_day": child,
                "rules": "21 and over pay the adult rate; guests 1 and 2 aged 3 to 20 pay the child rate; "
                         "2 and under are not eligible; under 21 in position 3 or later do not get it and are not charged. "
                         "Includes prepaid service charges."}

    def open_bar(text):
        short, long_ = money_in(r"2 - 5 Nights \$([\d.]+) USD 6\+ Nights \$([\d.]+) USD", text, "Open Bar gratuity rates")
        soda, = money_in(r"Unlimited Soda Beverage Package is \$([\d.]+) USD per person per day", text, "soda package rate")
        return {"per_day_2_to_5_nights": short, "per_day_6_plus_nights": long_, "soda_per_day": soda}

    def service(text):
        suite, std = money_in(r"\$([\d.]+) USD per person per day for The Haven and Suites; \$([\d.]+) USD per person per day for Club Balcony Suite and below", text, "service charge rates")
        age, = money_in(r"All guests (\d+) years or older", text, "service charge minimum age")
        if not (5 <= std <= 60 and 5 <= suite <= 60):
            raise RuntimeError(f"service charge rates look wrong: {suite}, {std}")
        return {"suite_haven_per_night": suite, "standard_per_night": std, "min_age": int(age),
                "suite_haven_types": ["SUITE", "HAVEN"]}

    read("free_at_sea_plus", TERMS_URL, plus)
    read("open_bar", TERMS_URL, open_bar)
    read("service_charge", SERVICE_CHARGE_URL, service)
    return rates, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--previous", help="the current data/prices.json, to carry data forward if NCL fails")
    args = ap.parse_args()

    previous = None
    if args.previous and os.path.exists(args.previous):
        try:
            with open(args.previous, encoding="utf-8") as f:
                previous = json.load(f)
        except Exception:
            previous = None

    checks = {"extra_guest_mismatches": [], "formula": [], "ages": [], "rates": []}
    warnings = []
    sailings = [fetch_sailing(cfg, checks, warnings, previous) for cfg in SAILINGS]
    rates, rate_warnings = fetch_rates(previous)
    for w in rate_warnings:
        log("Warning: " + w)
    # Cross check NCL's price summary gratuities against the terms page rates (logged, not fatal).
    for s in sailings:
        n, gr, ob = s["nights"], s["gratuities"], rates.get("open_bar")
        if not gr or not ob:
            continue
        per_day = ob["per_day_2_to_5_nights"] if n <= 5 else ob["per_day_6_plus_nights"]
        for what, got, want in [("open bar", gr["open_bar"]["per_guest"], per_day * n),
                                ("soda", gr["open_bar"]["soda_under_21_position_2"], ob["soda_per_day"] * n)]:
            checks["rates"].append({"sailing": s["id"], "item": what, "price_summary": got, "terms_rate_x_nights": round(want, 2),
                                    "ok": abs(got - want) <= TOLERANCE})
    out = {
        "schema_version": SCHEMA_VERSION,
        "saved_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "NCL vacation-builder API (stateroom-types-availability and price-summary)",
        "guest_counts": GUEST_COUNTS,
        "rates": rates,
        "rate_warnings": rate_warnings,
        "warnings": warnings,
        "checks": checks,
        "sailings": sailings,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log(f"Wrote {args.out}")

    for c in checks["rates"]:
        if not c["ok"]:
            log(f"Note: {c['sailing']} {c['item']} gratuity {c['price_summary']} differs from the terms rate x nights {c['terms_rate_x_nights']}")
    for m in checks["extra_guest_mismatches"]:
        log(f"Note: extra guest price differs for {m['sailing']} {m['category']}: {m['per_extra_guest']}")
    bad = [c for c in checks["formula"] + checks["ages"] if c["ok"] is False]
    for c in bad:
        log(f"CROSS CHECK FAILED: {c['sailing']} {c['category']} {c.get('party') or str(c.get('guests')) + ' guests'}: "
            f"expected {c['expected']}, NCL total {c['ncl_total']}")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()

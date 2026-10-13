# NOTES

Background, decisions and probe findings for the Norwegian Joy page. Read this before changing pricing logic.

## What this is

A public page that lets a friend's family compare Norwegian Cruise Line's published cabin prices on one sailing:

- Norwegian Joy, Friday Nov 20 to Monday Nov 23, 2026, 3 nights round trip from Miami.
- Miami 4:00 PM, Nassau Sat 7:00 AM to 5:00 PM, Great Stirrup Cay Sun 7:00 AM to 5:00 PM, Miami Mon 7:00 AM (NCL route-events, 2026-10-13).

It compares published rates only. It never books, holds or reserves a cabin.

It reuses the code and lessons of the owner's public repo DASatizabal/cruise-cabin-comparison (the June 2027 tool, version 4.10.0 on 2026-10-13): `tools/fetch_prices.py`, `tools/fetch_counts.py`, the format checks, `.github/workflows/refresh-prices.yml` and `deploy-pages.yml`, and the page. That repo's NOTES.md has the full history of every NCL probe; the parts that matter here are repeated below.

## Owner decisions (2026-10-13)

1. New public repo `DASatizabal/joy-cabin-compare`. The owner created it on GitHub (the Claude GitHub app could not: "403 Resource not accessible by integration").
2. Work on branch `joy-page-build`, preview through raw.githack.com, merge to `main` once, at the end, after the owner approves.
3. Everything the same as the June tool unless written here: guest selector, age rules, Free at Sea switches, Free at Sea Plus, service charges with the prepay switch, cabin counts, hold guard, Node.js 24 actions, the deploy-pages fix, publishing through GitHub Actions.
4. Refresh trigger: GitHub's schedule only (three times a day), no Cloudflare Worker.
5. CruiseFeed is never called, to protect the owner's API allowance.
6. Privacy: public repo, so no guest names, dates of birth, Latitudes numbers or reservation numbers, ever. The page asks for ages only.

## NCL ids are looked up every day, never typed in

`tools/fetch_prices.py` knows only the ship (JOY), the date (2026-11-20), the length (3 nights) and that it is a Miami round trip (itinerary codes starting `JOY3MIA`). Each run:

1. Reads the cruise page `https://www.ncl.com/cruises/JOY3MIANASNPIMIA` (GET, header `Accept: */*`; `Accept: text/html` gets a stripped page) and its `data-pricing-sailings` list. Both of the Joy's 3 night Miami itineraries (`JOY3MIANASNPIMIA` and `JOY3MIANPINASMIA`) list every sailing of both, so the second page is only a fallback. The sailing departing 2026-11-20 gives the itinerary code and packageId.
2. Calls `https://www.ncl.com/api/vacation-builder/itinerary/<itineraryCode>?packageId=<packageId>` (GET) for the sailingId, ship code, destination codes and length. The run stops if the packageId, date, ship or length disagree.
3. If the cruise pages can't be read, it tries the previous run's itinerary code and packageId (with a warning in the data file); step 2 still has to confirm them.
4. The ids are stored in `data/prices.json` under `ncl_ids` with the time they were checked. `tools/fetch_counts.py` reads them from there and confirms them again with the itinerary call before its cabin calls.

Found on 2026-10-13: itinerary `JOY3MIANASNPIMIA`, packageId 23379711, sailingId 59333, ship code JOY, destinations BAHAMAS and WEEKEND, duration 3.

## Hold guard (never relaxed)

- NEVER call `cabin/manage-cabin` (it carries recommendAndHold and puts a temporary hold on a real cabin), `api/book`, `booking/api/recommended-cabin`, or anything that holds or books.
- `request()` in `tools/fetch_prices.py` refuses any address containing "manage-cabin" or "hold".
- Stricter than June: every NCL API answer (availability, price summary, itinerary, route-events and cabin availability) is checked, and the run stops if it contains "hold" or "heldUntil". On 2026-10-13 none of them did (0 matches in each). Web pages (the cruise page and the terms pages) are not checked this way, because ordinary page text contains words like "placeholder"; nothing is ever sent to them.
- `tools/fetch_counts.py` also keeps June's own check on every cabin availability answer.

## Age and gratuity rules (in full)

Confirmed by NCL price summaries on the June sailings (2026-10-07) and again on this Joy sailing on 2026-10-13 (the daily age test, below). NCL lists guests adults first, then kids oldest first. Kid ages are taken on the sail date, Nov 20, 2026.

1. Party size: 2, 3, 4 or 5 guests per cabin, at least 1 adult (21 or older). The page asks for the number of adults and kids and each kid's age (0 to 20). It never asks for names or birth dates.
2. Cruise fare: set by guest position, not age. NCL's cabin price for the party already covers it.
3. Taxes, fees and port expenses: the same for every guest at any age ($150 per guest on this sailing on 2026-10-13). NCL's cabin prices already include them; the page shows them as their own line.
4. Unlimited Open Bar gratuity (when the Open Bar switch is on):
   - 21 and over: the full gratuity ($96 per guest on this sailing, $32 per day for 3 nights).
   - Under 21 in guest position 1 or 2 (only possible with 1 adult): a soda package instead ($37.50, $12.50 per day for 3 nights), shown on the same Open Bar line.
   - Under 21 in guest position 3 or later: $0, and no drink package.
5. Specialty Dining gratuity (when the Specialty Dining switch is on): 13 and over pay ($20 per guest, 1 meal on a 3 night sailing); 13 to 20 therefore pay Specialty Dining only; under 13 pay nothing, in any position.
6. Free at Sea Plus (optional switch, from NCL's promotion terms): 21 and over pay the adult rate ($49.99 per night); a guest 1 or 2 aged 3 to 20 pays the child rate ($40 per night); 2 and under are not eligible; under 21 in position 3 or later don't get it and aren't charged. Plus includes prepaid service charges. Turning Plus on also turns Open Bar and Specialty Dining on; turning either off turns Plus off.
7. Service charges (crew gratuities, NCL FAQ): $20 per guest per night for Club Balcony Suite and below, $25 for Suites and The Haven, for every guest 3 and older, except guests covered by Free at Sea Plus. The prepay switch only moves them between "Due before you sail" and "Charged onboard".
8. Under 13 sailing free: the owner's rule says "under 13 sails free where the promo applies". What NCL actually lists on this sailing (2026-10-13) is "Kids Sail Free" (promotion code 34CHO): "3rd and 4th guests sailing in the same stateroom sail for taxes, fees, and port expenses only." It covers Inside, Oceanview, Balcony and Club Balcony Suite (not Suite or The Haven). NCL applies it by guest position at any age, not by age: price summaries show a $0 fare for guests 3 and 4 with no birth dates sent, and in the age test the 7 year old in position 3 also had a $0 fare. A 5th guest pays a fare (Oceanview O5: $179). The page's prices come from NCL, so they already include it; while NCL lists the offer, the page shows one line between the Adults and Kids counters (owner's choice, 2026-10-13): "Kids Sail Free: 3rd and 4th guests sail free. They pay only taxes, fees and port expenses. Inside, Oceanview, Balcony and Club Balcony Suite only." Nothing shows when NCL doesn't list it.

The daily age test (`fetch_prices.py`): one price summary with 1 adult (reservation owner), a 15 year old and a 7 year old, sent as birth dates 60 days before the sail date, no names. It reads the adult Open Bar, the soda package and Specialty Dining amounts, stops if they no longer follow rules 4 and 5, and checks the page formula against NCL's total within $5. On 2026-10-13, Inside IA: NCL $1,081.50, formula $1,081.50.

## Taxes, fees and Free at Sea per guest

- Shown as their own lines, from NCL: taxes from the price summary's tax line; Open Bar, soda and Specialty Dining from the age test; Free at Sea Plus and the Open Bar per day rates from https://www.ncl.com/cruise-deals/promotion-terms; service charges from https://www.ncl.com/faq/what-is-ncl-onboard-service-charge.
- They appear the same way as on the June page: as lines in the cabin's price breakdown with the per guest amount (for example "Taxes, fees and port expenses: 3 x $150", "Unlimited Open Bar: 2 guests x $96"). A separate "Per guest charges" panel was tried on 2026-10-13 and removed at the owner's request, to match June.
- If a number can't be found, it is never guessed. Order: today's NCL value; else the previous run's value if it is at most 3 days old (gratuities) or any age (rates, with `stale_since`); else null with a warning in the data file. `tools/check_prices.py` allows null only with a matching warning. The page then shows "Not found on NCL today" on that line, leaves it out of the total, and says which items are not included. Tested 2026-10-13 with a copy of the data file with taxes, gratuities, Plus and service charges all null.

## Cabin counts

Same technique as June (`tools/fetch_counts.py`):

- POST `https://www.ncl.com/api/vacation-builder/cabin/availability` with the sailing details from the itinerary call. The answer covers the requested category plus every pricier category of the same broad type, as per location totals (Forward, Mid, Aft). Cabin lists are capped at 15 per deck, so only location totals are used.
- Count for a category = its call's location totals minus those of the call for the next pricier non-Guarantee category (calls made from the most expensive down).
- Unreliable (stored as null, page shows "Count not available"): the call returns another broad type's code; two categories tie in price; the subtraction is negative or not positive.
- Full sweep every 3 days, light re-check (counts under 15 plus the next pricier category each needs) on the other days, 3 seconds between calls.
- First full sweep, 2026-10-13: 75 calls, about 6 minutes, 18 of 75 counts unreliable. Most are price ties, which the Joy has many of at 2 and 3 guests: Inside IB and IF ($369), Oceanview OA and OB ($409), Balcony BA and BB ($429), Club Balcony Suite MA and MB ($459). Others: Balcony B4's call listed Club Balcony Suite MC (same price), Suite SC's call listed Balcony B1, and BF and HI subtractions gave 0. One connection reset was recovered by the automatic retry.
- Display (owner asked for an availability count): reliable counts show the number ("19 cabins left"), green at 50 or more, gold 10 to 49, red under 10. June showed "Plenty left" at 50 or more instead of the number.
- Counts never block prices: separate job, separate file, own format check. The page hides counts when the file is missing or more than 7 days old.

## Daily refresh and publishing

- `.github/workflows/refresh-prices.yml`: scheduled 10:17, 14:47 and 19:37 UTC (GitHub's schedule is best effort; the June repo saw runs 1 to 7 hours late). The `decide` job skips work already done that UTC day on scheduled runs, and skips everything from the sail date (2026-11-20) on, so the refresh stops by itself after the cruise. Manual runs ("Run workflow") always run fully, with a choice of count mode.
- Prices job: about 14 NCL calls (cruise page, itinerary, route-events, 4 availability, 4 price summaries, 1 age test) plus the 2 NCL pages, about 45 seconds. The new file goes to `data/prices.new.json`, is format checked, and only then replaces `data/prices.json`.
- Pushes to `joy-page-build` that touch the fetch tools or the workflow run both jobs on GitHub's runners as a test, and never commit data.
- No keepalive job: GitHub only disables schedules after 60 days without activity, and the refresh ends on Nov 20, about 5 weeks away.
- Publishing: GitHub Pages source must be "GitHub Actions". With "Deploy from a branch", commits made by the workflow's GITHUB_TOKEN never start a Pages build (GitHub docs), so daily prices would never reach the page. `deploy-pages.yml` publishes `index.html`, `data/prices.json` and `data/counts.json` from `main`'s root.
- Deploy fix from June 4.4.0 (actions/deploy-pages issue 451): upload and deploy are separate jobs, the artifact is named `github-pages-<label>-<run attempt>`, and the deploy is retried once after 30 seconds.
- Actions on their Node.js 24 majors: checkout v7, configure-pages v6, upload-pages-artifact v5, deploy-pages v5. Every job pinned to `ubuntu-24.04`. actionlint 1.7.7: no problems (2026-10-13).

## Cabin descriptions

NCL first, never guessed. No Deck Finder data exists for the Joy (`ships/ncl/joy/geometry.json` returned 404 on 2026-10-13), so only NCL's own decks, location and size are used, and only when NCL's group has that one code. For grouped codes the page says how many guests the cabin holds, and fills decks and location from where that code's open cabins are (counts file, while fresh). Guarantee cabins (IX, OX, BX, MX) list no decks: "Guarantee: NCL picks your cabin location". Solo cabins (IT, OT, BT) are hidden. The Joy lists no Studio.

## Categories on 2026-10-13 (2 guests, per person)

Inside: IX $349, IB and IF $369, IA $379, I4 $389. Oceanview: OX $359, OA and OB $409, O4 $419, O5 $449. Balcony: BX $369, BF $419, BA and BB $429, B4 $439, B1 $529; B6 not available. Club Balcony Suite: MX $419, MC $439, MA and MB $459, M4 $479, M6 $509. Suite: SC $529, SP $549. The Haven: HI $799 to H6 $1,999 (10 categories); H2 not available. All include taxes, not gratuities.

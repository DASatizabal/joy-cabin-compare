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

## Cabin prices in the lists (Joy only, owner's request 2026-10-13)

Unlike the June page, every cabin price in the tap list and the full table is that cabin's full total with the current choices: cabin fare and taxes, service charges (Suite and Haven rate where it applies), Open Bar, Specialty Dining and Free at Sea Plus as switched on, for the chosen guests and ages. It is the same number as the card's Total and changes when a switch, a guest or an age changes. The small "pp" figure under it is that total divided by the guests. Until every kid's age is chosen, the lists show fare and taxes only and say so, because gratuities depend on age. Amounts NCL didn't show today are left out, as in the card.

## Florida resident rates (checked on NCL, 2026-10-14; read daily from version 1.3.0)

NCL's public website doesn't show Florida resident rates. On 2026-10-14 the owner opened NCL's "View Guest Breakdown" for the same category twice, once in NCL's Florida resident view and once in the regular website view, for 2 adults with Open Bar and Specialty Dining. In every pair, Open Bar ($96 each), Specialty Dining ($20 each) and taxes ($150 each) were identical; only the cruise fare changed, by a fixed dollar amount per guest that differs by category:

| Category | Website fare per guest | Florida fare per guest | Off per guest | Totals for 2 (website, Florida) |
|---|---|---|---|---|
| IB Inside (#9535 website) | $219 | $159 | $60 | $970, $850 |
| I4 Family Inside (#12653 website) | $239 | $179 | $60 | $1,010, $890 |
| BF Balcony (sold as "Balcony Guarantee") | $269 | $189 | $80 | $1,070, $910 |
| B4 Family Balcony (#14876 website) | $289 | $239 | $50 | $1,110, $1,010 |
| BX Guarantee Balcony | $219 | $204 | $15 | $970, $940 |
| OA/OB Oceanview with Picture Window (#11706 Florida, #12102 website) | $259 | $259 | $0 | $1,050, $1,050 |
| O4 Family Oceanview (very likely; #11700 Florida at $269, the website O4 fare; its category wasn't confirmed) | $269 | $269 | $0 | |

The Florida fare for each category is the subtotal minus Open Bar and Specialty Dining, divided by 2 (the Florida view doesn't list the fare line). The website fares match the page's data exactly, and the page showed the same website totals.

Daily reading (version 1.3.0, owner's choice 2026-10-14): how NCL decides who is a Florida resident, from a read-only look at NCL's own vacation-builder app code (`ncl-vacation-builder-app/iife.js`, 2026-10-14): every price call sends `userFareCodes: []` and no residency field; login is kept in the `NCLAuth` cookie (an access token with an expiry), and the price calls go to www.ncl.com, so a signed-in browser gets the account's Florida fares from the same read-only price-summary call. Scripted logins from this cloud session or GitHub's runners are not an option (no password in chat, both computers start fresh, Akamai bot protection), so it runs on the owner's 24/7 AI PC with a browser profile that stays signed in:

- `tools/fetch_florida.py` (setup and daily steps for the owner: `tools/florida-runner/README.md`). `--setup` opens Chrome with the profile `D:\AI-VAULT\ncl-profile` (never in a repo), the owner signs in by hand, and one test price is compared. `--record` saves NCL's own price-summary requests with every text value except codes replaced by `REMOVED`, in case the signed-in call alone doesn't get Florida fares. The daily run (Windows Task Scheduler, 7:00 AM, `--push`) makes, per available non-solo category at 2 guests, one anonymous price-summary call (website fare) and one from inside the signed-in page (Florida fare), each checked so fare + taxes + gratuities equal NCL's total; about 70 calls, 2 seconds apart. It writes `data/florida.json` (numbers only; `tools/check_florida.py` rejects any other key), commits and pushes to main with the owner's git login, which publishes the page. A category that fails keeps its previous entry and date. It doesn't write when not signed in, or when no category shows a Florida difference. It stops from the sail date. Only availability and price-summary are called; addresses and answers go through the same hold guards as `fetch_prices.py`.
- Skip and retry (1.3.2, owner's request): like the GitHub refresh, a run only checks what isn't done yet that UTC day (a category counts as done when today's entry came from the signed-in account), so the task runs at 7:00 AM and every 4 hours until 7:00 PM; later runs finish in seconds or retry what failed. First full signed-in run (2026-10-14, 34 categories): every screenshot amount matched (IB, IF, IA, I4 $60; BF, BB $80; BA $70; B4 $50; B1 $40; BX $15; IX $30; OX $15; Club Balcony Suite MB $70, MA and M4 $60, MC $50, MX $15, M6 $0; Oceanview OA, OB, O4, O5 $0; Suites and The Haven $0). HF failed once with HTTP 404 on the signed-out call (likely sold out at 2 guests that afternoon). NCL's website Oceanview fares had dropped $30 since the morning (OA $259 to $229).
- First `--setup` on the AI PC (2026-10-14): signed in, login cookie expires 2026-12-13 (past the sailing). The signed-in price summary had no per-guest fare lines, so 1.3.1 works the fare out from NCL's totals (subtotal minus Open Bar and Specialty Dining, for 2 guests; checked against the grand total). Tested on a real answer with its per-guest fare lines removed: IB still $219.
- Tested 2026-10-14 from the cloud session, signed out, with Chromium: the in-page call reaches NCL and returns the website fares (IB $219, BF $269), 34 categories found. The signed-in result is only known after the owner's `--setup`.
- `data/florida.json` was seeded with the screenshot amounts above (source "owner's screenshots of NCL's Florida resident view", checked 2026-10-14), so the page is unchanged until the first AI PC run replaces them.

Page rule: with the "Florida resident rate" switch on (default), a category's Florida difference per guest (website fare minus Florida fare, from `data/florida.json`) comes off the fare of guests 1 and 2, never more than the fare (guests 3 and 4 pay $0 fare under Kids Sail Free; a 5th guest's Florida fare isn't read, so it isn't discounted). A $0 difference says "same as the website". A category not in the file says "not checked for this cabin"; one checked more than 7 days ago says "too old to use"; both get no discount. The top of the page shows "Florida rates as of [date]", amber after 3 days. If the file is missing or unreadable, the page shows website prices. The page never shows or stores any guest names.

Consultant quotes (2026-10-13), explained by these rates: 2 adults Inside $850 is IB at the Florida rate; 4 guests Inside $1,190 is IB for 2 adults and 2 kids (NCL's website doesn't sell IB for 4, so the consultant booked it); 2 adults Balcony $900 and 4 guests $1,240 are $10 under BF at the Florida rate ($910 and $1,250), likely a small price move.

History: before the Florida view was checked, the page estimated the rate from the consultant's quotes alone: 1.0.0 used 14.9% off fare and taxes (and briefly priced BF for 4 as "Available through David's consultant"), 1.1.0 used 33.8% off the fare. Both were replaced in 1.2.0 by the checked amounts above, because the real discount is a different dollar amount per category, not one percentage.

Service charges (4 guests x $20 x 3 nights = $240 for this family) are not in the consultant's quote. Owner's rule (2026-10-14): with the prepay switch off (the default), every total on the page is what's paid now, without service charges, and the Total line adds "+ $240 service charges paid onboard (can be removed at Guest Services)"; the service charge line in the breakdown is grey and marked "onboard". With prepay on, totals include them ($1,480 for this family). So with the defaults, this family's Balcony BB reads $1,240, the consultant's number.

Same day, the prepay gratuities switch default changed to off (service charges charged onboard), owner's request. The saved-choices key moved to `joy-cabin-compare-v2` so earlier previews pick up both new defaults.

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

- `.github/workflows/refresh-prices.yml`: scheduled 10:17, 14:47 and 19:37 UTC (GitHub's schedule is best effort; the June repo saw runs 1 to 7 hours late). The `decide` job skips work already done that day (Eastern date, see below) on scheduled runs, and skips everything from the sail date (2026-11-20, Eastern) on, so the refresh stops by itself after the cruise. Manual runs ("Run workflow") always run fully, with a choice of count mode.
- Prices job: about 14 NCL calls (cruise page, itinerary, route-events, 4 availability, 4 price summaries, 1 age test) plus the 2 NCL pages, about 45 seconds. The new file goes to `data/prices.new.json`, is format checked, and only then replaces `data/prices.json`.
- "That day" means the Eastern date (version 1.4.0, 2026-10-15). Before, `tools/decide_run.py` compared UTC dates. A manual run on Oct 13 at 8:27 PM Eastern saved `data/prices.json` at `2026-10-14T00:27:47Z`, which is Oct 14 in UTC, so all three scheduled runs on Oct 14 (10:17, 14:47 and 19:37 UTC) skipped the prices job and the page kept prices almost 24 hours old. In that time NCL cut Oceanview fares $30 per guest: the AI PC's Florida run at `2026-10-14T18:07:38Z` read website fares OA and OB $229, O4 $239, O5 $269, while `data/prices.json` still had $259, $259, $269, $299, about $60 high for 2 guests. Now every "done that day" check uses the America/New_York date: `decide_run.py` (prices, counts and the sail-date stop), `fetch_counts.py` (3-day full sweep cadence) and `fetch_florida.py` (which cabins are already done, and its sail-date stop). The zone, not a fixed UTC-5 or UTC-4 offset, because daylight saving time ends on 2026-11-01. That matters most for the Florida runner: after Nov 1 its 7:00 PM Eastern run is at 00:00 UTC, the next UTC day, so a UTC check would have redone every signed-in call. An evening run now counts as that evening's day, so the next morning's scheduled run refreshes. Tested with `decide_run.py --now`: prices saved `2026-10-14T00:27:47Z` and a scheduled run at `2026-10-14T10:17:00Z` is a full run; a run at 14:47Z after a 10:20Z refresh skips; after Nov 1, a 7:30 PM EST run after a 7:00 AM EST refresh skips; Nov 19 at 10:00 PM EST still runs and Nov 20 stops.
- NCL calls per day, before and after 1.4.0 (no calls, runs or retries were added):
  - GitHub prices job: cruise page 1 (2 if the first page fails), itinerary 1, route-events 1, availability 4, price summaries 4, age test 1, NCL promotion terms and service charge pages 2 = 14 (15). At most one scheduled full run per day before (per UTC day) and after (per Eastern day); the fix only moves the day boundary from 8:00 PM Eastern (EDT; 7:00 PM in EST) to midnight Eastern. Manual runs still always run fully. Unchanged: 14 a day.
  - GitHub counts job: itinerary 1 plus cabin calls (75 on the 2026-10-13 full sweep, every 3 days; fewer on light days). Unchanged.
  - GitHub decide job: 0.
  - Florida runner on the AI PC (runs at 7:00 AM, 11:00 AM, 3:00 PM and 7:00 PM Eastern): before, the first run made 70 (ncl.com page 1, availability 1, 34 cabin types x 2 price summaries) and each later run 1 (availability, even with nothing to check), 73 a day; after Nov 1 the 7:00 PM run would have landed on the next UTC day and redone everything, 142 a day. After: the first run 70, later runs 0 (the cabin list now comes from `data/prices.json`, and availability is only called when something is due), 70 a day before and after Nov 1. A cabin that fails is retried by the next run: availability 1, ncl.com page 1, and 2 per failed cabin.
- Page staleness warning (1.4.0, no NCL calls): the Florida runner also reads NCL's website fare for every cabin type at 2 guests. For each reading from the last 24 hours, the page compares it with the 2-guest fare in `data/prices.json` (`price_pp` minus `taxes_per_guest`, within $1). If any differ and `data/florida.json` is newer than `data/prices.json`, an amber line under the dates says "NCL prices have moved since the last refresh. Totals may be off until the next update." It never changes a total. "Prices as of" now shows Eastern date and time, for example "Oct 13, 8:27 PM ET". Tested in Chromium with a fixed clock: Oct 14 data (Oceanview differs) shows it; fares matching, Florida run older than prices, or readings over 24 hours old do not; totals identical with and without it.
- Pushes to `joy-page-build` that touch the fetch tools or the workflow run both jobs on GitHub's runners as a test, and never commit data.
- No keepalive job: GitHub only disables schedules after 60 days without activity, and the refresh ends on Nov 20, about 5 weeks away.
- Publishing: GitHub Pages source must be "GitHub Actions". With "Deploy from a branch", commits made by the workflow's GITHUB_TOKEN never start a Pages build (GitHub docs), so daily prices would never reach the page. `deploy-pages.yml` publishes `index.html`, `data/prices.json` and `data/counts.json` from `main`'s root.
- Deploy fix from June 4.4.0 (actions/deploy-pages issue 451): upload and deploy are separate jobs, the artifact is named `github-pages-<label>-<run attempt>`, and the deploy is retried once after 30 seconds.
- Actions on their Node.js 24 majors: checkout v7, configure-pages v6, upload-pages-artifact v5, deploy-pages v5. Every job pinned to `ubuntu-24.04`. actionlint 1.7.7: no problems (2026-10-13).

## Cabin descriptions

NCL first, never guessed. No Deck Finder data exists for the Joy (`ships/ncl/joy/geometry.json` returned 404 on 2026-10-13), so only NCL's own decks, location and size are used, and only when NCL's group has that one code. For grouped codes the page says how many guests the cabin holds, and fills decks and location from where that code's open cabins are (counts file, while fresh). Guarantee cabins (IX, OX, BX, MX) list no decks: "Guarantee: NCL picks your cabin location". Solo cabins (IT, OT, BT) are hidden. The Joy lists no Studio.

## Categories on 2026-10-13 (2 guests, per person)

Inside: IX $349, IB and IF $369, IA $379, I4 $389. Oceanview: OX $359, OA and OB $409, O4 $419, O5 $449. Balcony: BX $369, BF $419, BA and BB $429, B4 $439, B1 $529; B6 not available. Club Balcony Suite: MX $419, MC $439, MA and MB $459, M4 $479, M6 $509. Suite: SC $529, SP $549. The Haven: HI $799 to H6 $1,999 (10 categories); H2 not available. All include taxes, not gratuities.

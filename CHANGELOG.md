# Changelog

All notable changes to this project are listed here. Versions follow Semantic Versioning (MAJOR.MINOR.PATCH). The version in `index.html` (`APP_VERSION`) must match the newest entry below; `tools/check_release.py` enforces this.

## [1.3.0] - 2026-10-14

### Added
- `tools/fetch_florida.py` and `tools/florida-runner/README.md`: reads NCL's Florida resident fares for every cabin type daily on the owner's AI PC, from a browser profile that stays signed in to a Florida resident NCL account, and publishes them as `data/florida.json` (numbers only). Setup mode for the first sign-in and a test price; record mode, with names removed, if NCL needs more than the sign-in.
- `tools/check_florida.py`: format check for `data/florida.json`; it rejects any key that isn't a number or code, so nothing personal can be published. Part of the release check. "Deploy site" publishes the file.
- "Florida rates as of [date]" at the top of the page, amber when more than 3 days old.

### Changed
- The page reads Florida rates from `data/florida.json` instead of a fixed table. Seeded with the amounts from the owner's screenshots, so prices are unchanged until the AI PC's first run. A category checked more than 7 days ago gets no discount and says so.

## [1.2.1] - 2026-10-14

### Removed
- The "Added cost in [cabin] (fare and taxes): guest 3 +$X, guest 4 +$X" line under each cabin's total (owner's request).

## [1.2.0] - 2026-10-14

### Changed
- Florida resident rate: now the exact amounts from NCL's own Florida resident view, compared with the regular website view for the same category (2 adults): off the fare of guests 1 and 2, Inside IB and I4 $60 each, Balcony BF $80, B4 $50, BX $15, Oceanview OA, OB and O4 $0. Every other cabin shows "Florida resident rate: not checked for this cabin" and no discount. Replaces the 33.8% estimate, since the real discount is a different dollar amount per category. The switch is now labeled "Florida resident rate" (no longer "estimate").

## [1.1.0] - 2026-10-14

### Changed
- Florida resident rate estimate: now 33.8% off the cruise fare only; taxes are not discounted. Worked out by taking taxes, Open Bar and Specialty Dining out of the consultant's quotes ($318 Inside and $368 Balcony in fare) and comparing with NCL's fares for every Inside and Balcony cabin; the closest pair is Inside I4 and Balcony BB. For 2 adults and kids 15 and 17: I4 $1,188.51 (quote $1,190), BB $1,241.49 (quote $1,240). Was 14.9% off fare and taxes.

### Removed
- The "Not available online. Available through David's consultant." note and the 4-guest price for Balcony BF. With taxes taken out, the quotes match cabins NCL sells online, so nothing points to a cabin only the consultant can book. BF for 4 shows NCL's own answer again.

## [1.0.0] - 2026-10-13

First version, built from the June 2027 tool (DASatizabal/cruise-cabin-comparison 4.10.0) for one sailing: Norwegian Joy, Nov 20, 2026, 3 nights from Miami.

### Added
- `index.html`: guest selector (adults, kids and each kid's age, 2 to 5 guests), cabin type buttons, every cabin category for the party with price and cabins left, Free at Sea switches (Open Bar, Specialty Dining, Free at Sea Plus), and service charges with the prepay switch, laid out like the June page. Taxes and Free at Sea gratuities show per guest in each price breakdown. Any amount NCL doesn't show reads "Not found on NCL today" and is left out of the total.
- Each cabin's price in the tap list and the full table is its full total with the current choices (guests, ages, Open Bar, Specialty Dining, Free at Sea Plus), the same number as the card's Total, and updates when a switch changes. Until every kid's age is chosen, they show fare and taxes.
- "Florida resident rate (estimate)" switch, on by default, in the card with the prepay switch: 14.9% off NCL's cabin price (fare and taxes): the consultant's Inside and Balcony quotes minus Open Bar and Specialty Dining ($918 and $968) divided by NCL's website prices for the cabins they match, Inside I4 and Balcony BF ($1,078 and $1,138), worked out from an NCL cruise consultant's Florida resident quote on Oct 13, 2026 (NCL's website doesn't show these rates). Shown as its own line in the breakdown and applied to the list prices; switch it off for NCL's published prices.
- Balcony BF for 4 guests, which NCL's website doesn't sell for 4: priced from its 2-guest fare plus taxes and labeled "Not available online. Available through David's consultant."
- The prepay gratuities switch is off by default. With it off, every total (the card, the tap list and the table) is what's paid now, without service charges, and the Total line adds "+ $X service charges paid onboard (can be removed at Guest Services)". With it on, the totals include the service charges. The "Due before you sail" and "Charged onboard" lines were removed.
- A "Kids Sail Free" line between the Adults and Kids counters (3rd and 4th guests sail free and pay only taxes, fees and port expenses; Inside to Club Balcony Suite), shown only while NCL lists the offer.
- `tools/fetch_prices.py`: finds the sailing's itinerary code and packageId on NCL's cruise page and its sailingId and ship code from the itinerary call on every run, then NCL's availability and price summaries at 2 to 5 guests and the daily age test. Every NCL API answer is refused if it mentions a hold.
- `tools/fetch_counts.py`: cabins left per category and party size, with the June subtraction method.
- Format checks for both data files, the release check, and the daily "Refresh prices" and "Deploy site" workflows. The refresh stops by itself from the sail date on.

# Changelog

All notable changes to this project are listed here. Versions follow Semantic Versioning (MAJOR.MINOR.PATCH). The version in `index.html` (`APP_VERSION`) must match the newest entry below; `tools/check_release.py` enforces this.

## [1.0.0] - 2026-10-13

First version, built from the June 2027 tool (DASatizabal/cruise-cabin-comparison 4.10.0) for one sailing: Norwegian Joy, Nov 20, 2026, 3 nights from Miami.

### Added
- `index.html`: guest selector (adults, kids and each kid's age, 2 to 5 guests), cabin type buttons, every cabin category for the party with price and cabins left, Free at Sea switches (Open Bar, Specialty Dining, Free at Sea Plus), and service charges with the prepay switch, laid out like the June page. Taxes and Free at Sea gratuities show per guest in each price breakdown. Any amount NCL doesn't show reads "Not found on NCL today" and is left out of the total.
- Each cabin's price in the tap list and the full table is its full total with the current choices (guests, ages, Open Bar, Specialty Dining, Free at Sea Plus), the same number as the card's Total, and updates when a switch changes. Until every kid's age is chosen, they show fare and taxes.
- "Florida resident rate (estimate)" switch, on by default, in the card with the prepay switch: 16.4% off NCL's cabin price (fare and taxes), the consultant's Balcony quote ($1,240 minus Open Bar and Specialty Dining = $968) divided by NCL's website price for the same cabin ($1,158), worked out from an NCL cruise consultant's Florida resident quote on Oct 13, 2026 (NCL's website doesn't show these rates). Shown as its own line in the breakdown and applied to the list prices; switch it off for NCL's published prices.
- The prepay gratuities switch is off by default (service charges charged onboard).
- A "Kids Sail Free" line between the Adults and Kids counters (3rd and 4th guests sail free and pay only taxes, fees and port expenses; Inside to Club Balcony Suite), shown only while NCL lists the offer.
- `tools/fetch_prices.py`: finds the sailing's itinerary code and packageId on NCL's cruise page and its sailingId and ship code from the itinerary call on every run, then NCL's availability and price summaries at 2 to 5 guests and the daily age test. Every NCL API answer is refused if it mentions a hold.
- `tools/fetch_counts.py`: cabins left per category and party size, with the June subtraction method.
- Format checks for both data files, the release check, and the daily "Refresh prices" and "Deploy site" workflows. The refresh stops by itself from the sail date on.

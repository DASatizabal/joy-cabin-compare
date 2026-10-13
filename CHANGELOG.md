# Changelog

All notable changes to this project are listed here. Versions follow Semantic Versioning (MAJOR.MINOR.PATCH). The version in `index.html` (`APP_VERSION`) must match the newest entry below; `tools/check_release.py` enforces this.

## [1.0.0] - 2026-10-13

First version, built from the June 2027 tool (DASatizabal/cruise-cabin-comparison 4.10.0) for one sailing: Norwegian Joy, Nov 20, 2026, 3 nights from Miami.

### Added
- `index.html`: guest selector (adults, kids and each kid's age, 2 to 5 guests), cabin type buttons, every cabin category for the party with price and cabins left, Free at Sea switches (Open Bar, Specialty Dining, Free at Sea Plus), service charges with the prepay switch, and a "Per guest charges on this sailing" panel. Any amount NCL doesn't show reads "Not found on NCL today" and is left out of the total.
- NCL's "Kids Sail Free" offer (3rd and 4th guests pay only taxes, fees and port expenses, Inside to Club Balcony Suite) shown in NCL's words while NCL lists it.
- `tools/fetch_prices.py`: finds the sailing's itinerary code and packageId on NCL's cruise page and its sailingId and ship code from the itinerary call on every run, then NCL's availability and price summaries at 2 to 5 guests and the daily age test. Every NCL API answer is refused if it mentions a hold.
- `tools/fetch_counts.py`: cabins left per category and party size, with the June subtraction method.
- Format checks for both data files, the release check, and the daily "Refresh prices" and "Deploy site" workflows. The refresh stops by itself from the sail date on.

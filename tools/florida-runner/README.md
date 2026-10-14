# Florida resident rates on the AI PC

This sets up the AI PC to read NCL's Florida resident prices for the Joy Nov 20, 2026 sailing every morning and publish them on the page. NCL only shows these prices to an account with a Florida address, so a browser on the AI PC stays signed in to your NCL account, and `tools/fetch_florida.py` uses it.

What it does each run: for every cabin type at 2 guests, it asks NCL for the website price (signed out) and the Florida price (signed in), and saves only the numbers in `data/florida.json`. No names, email, Latitudes number or anything else from your account. It only uses NCL's price calls, never anything that books or holds a cabin. About 70 calls, 2 seconds apart, about 3 minutes.

It only does what isn't done yet today (by the UTC date, like the GitHub refresh): if every cabin already has today's Florida price, a run finishes in seconds; if a run failed, the next one tries again; if a few cabins failed, the next run checks only those. Add `--force` to check every cabin anyway.

The two ways to run it:
- `py -3 tools\fetch_florida.py` checks and saves `data\florida.json` on the AI PC only. The page doesn't change.
- `py -3 tools\fetch_florida.py --push` first gets the latest files from GitHub, then checks, saves, and sends the file to GitHub, which republishes the page in about a minute.

Important: the folder `D:\AI-VAULT\ncl-profile` holds your signed-in NCL session. Anyone with that folder could act as you on ncl.com. Keep it on the AI PC. Never copy it into a repository or send it to anyone.

## First-time setup

1. On the AI PC, press the Windows key, type `PowerShell`, and press Enter.
2. Check that Python is installed: type `py -3 --version` and press Enter. It should print `Python 3.` followed by numbers. If it says it is not recognized, install Python from https://www.python.org/downloads/ (tick "Add python.exe to PATH" on the first screen), close PowerShell, and start again at step 1.
3. Check that Git is installed: type `git --version` and press Enter. It should print `git version`. If it says it is not recognized, install Git from https://git-scm.com/download/win with all the default choices, close PowerShell, and start again at step 1.
4. Make sure Google Chrome is installed (the script uses your real Chrome, which NCL is least likely to block). If it isn't, install it from https://www.google.com/chrome/.
5. Copy the repository to the AI PC. Type each line and press Enter after each:
   ```
   New-Item -ItemType Directory -Force D:\Repos
   cd D:\Repos
   git clone https://github.com/DASatizabal/joy-cabin-compare.git
   cd D:\Repos\joy-cabin-compare
   git config user.name "DASatizabal"
   git config user.email "174554998+DASatizabal@users.noreply.github.com"
   ```
   The last two lines make this copy sign its updates with GitHub's private address instead of your personal email, because the repository is public (GitHub blocks pushes that would publish a personal email, and the script refuses to publish without this).
6. Install the browser tool. Type each line and press Enter after each (the second one downloads a backup browser and takes a minute):
   ```
   py -3 -m pip install playwright
   py -3 -m playwright install chromium
   ```
7. Sign in once. Type this and press Enter:
   ```
   py -3 tools\fetch_florida.py --setup
   ```
   A Chrome window opens on ncl.com.
   1. In that window, sign in to your NCL account (the one with your Florida address).
   2. If NCL shows "Remember me" or "Keep me signed in", tick it.
   3. When the page shows you're signed in, click back on the PowerShell window and press Enter.
8. Read the last lines PowerShell prints:
   - `Login cookie: found (expires: ...)`: write down the expiry date and time. That tells us how often you'll need to sign in again.
   - `Test IB at 2 guests: website fare $219.00 per guest, signed-in fare $159.00 per guest.` (the numbers may differ if NCL's prices changed)
   - `PASS: ...` means it works. Go to step 10.
   - `No difference. ...` means NCL needs something more. Go to step 9.
9. Only if step 8 said "No difference": type `py -3 tools\fetch_florida.py --record` and press Enter. In the Chrome window that opens, go to the Joy Nov 20 sailing, choose an Inside cabin, and open "View Guest Breakdown" so it shows your Florida price. Then press Enter in PowerShell. It saves `D:\AI-VAULT\ncl-profile\florida-record.json`, with names and other text replaced by `REMOVED`. Open that file in Notepad, check that you see no names, email or numbers that are yours, and paste its contents to Claude. Stop here until Claude updates the script.
10. Test a full run without publishing. Type this and press Enter:
    ```
    py -3 tools\fetch_florida.py
    ```
    It lists each cabin type with its website and Florida fare, then `Wrote ...florida.json`. It takes about 3 minutes.
11. Publish, by hand this first time. Type this and press Enter:
    ```
    py -3 tools\fetch_florida.py --push
    ```
    If step 10 ran today, it only rechecks the cabins that failed, so it takes seconds. The first time, Git may open a browser window asking you to sign in to GitHub. Sign in as DASatizabal and allow access (the scheduled task runs in the background and can't show that window, so this has to happen once by hand). It should end with `Pushed to main; the page republishes in about a minute.`
12. Check the page: open https://dasatizabal.github.io/joy-cabin-compare/ and look at the top. It should say "Florida rates as of" with today's date.

## Run it every morning

13. In PowerShell, type this as one line and press Enter. It runs the check every day at 7:00 AM and again every 4 hours until 7:00 PM (the AI PC's clock), and writes a log. The later runs finish in seconds when the morning run worked, and try again when it didn't. If you already created the task, running this replaces it:
    ```
    schtasks /Create /TN "Joy Florida rates" /SC DAILY /ST 07:00 /RI 240 /DU 0012:00 /F /TR "cmd /c cd /d D:\Repos\joy-cabin-compare && py -3 tools\fetch_florida.py --push >> D:\AI-VAULT\ncl-profile\florida-log.txt 2>&1"
    ```
    It should print `SUCCESS: The scheduled task "Joy Florida rates" has successfully been created.` The task runs while you're signed in to Windows, which is how the AI PC normally runs.
14. The next morning, open `D:\AI-VAULT\ncl-profile\florida-log.txt` in Notepad. The 7:00 AM run's lines should end with `Pushed to main`, and the later runs' with `Already checked today` and `Nothing new to publish.` The page should show "Florida rates as of" with that day's date.

## When the login expires

You'll notice one of these: the log's last lines say `NOT SIGNED IN`, or the "Florida rates as of" date at the top of the page turns amber (more than 3 days old). After 7 days without a check, the page stops using the old Florida prices and shows website prices.

To fix it, open PowerShell and type each line, pressing Enter after each:
```
cd D:\Repos\joy-cabin-compare
py -3 tools\fetch_florida.py --setup
```
Sign in again in the Chrome window (step 7), then press Enter in PowerShell. Nothing else changes; the next morning's run picks it up.

## If NCL blocks the hidden browser

If the log shows `failed` for every cabin, or `HTTP 403`, NCL may be blocking the hidden browser window. Type this as one line and press Enter, to make the daily run use a visible window instead:
```
schtasks /Create /TN "Joy Florida rates" /SC DAILY /ST 07:00 /RI 240 /DU 0012:00 /F /TR "cmd /c cd /d D:\Repos\joy-cabin-compare && py -3 tools\fetch_florida.py --push --show >> D:\AI-VAULT\ncl-profile\florida-log.txt 2>&1"
```

## After the cruise

The script stops checking by itself from Nov 20, 2026. To remove the daily task, type this and press Enter:
```
schtasks /Delete /TN "Joy Florida rates" /F
```
You can also delete the folder `D:\AI-VAULT\ncl-profile` then, which signs that browser out of NCL for good.

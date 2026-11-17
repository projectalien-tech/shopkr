# Tests

Browser tests that load `index.html` in headless Chrome, click through it like a participant, and check what reaches the logging server. The server is the real `apps-script/Code.gs`, run in Node with stand-ins for Google's SpreadsheetApp, LockService, PropertiesService and ContentService, so the Sheet logic is tested too. Nothing goes to Google.

## Setup (once)

- Python 3.9+ and Node 18+
- `pip install playwright`
- Either `python -m playwright install chromium`, or point at an installed Chrome with `CHROME_PATH`, e.g. `export CHROME_PATH=/usr/bin/google-chrome` (macOS: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`)

## Run

From this folder:

```
python run_all.py            # every suite; exits 1 if any check fails
python test_catalog.py       # one suite
```

Each suite starts the mock server on port 8765 and serves the repository on port 8766, so close anything else using those ports. A full run takes a few minutes.

## Suites

| File | Checks |
| --- | --- |
| `test_regression.py` | Consent gating, logging and the send queue, refresh and offline recovery, every pattern toggle, checkout, debrief and withdrawal |
| `test_fixes.py` | One test per finding from the v6.0 code review (withdrawal, orphan queues, back button, formula injection, and more) |
| `test_assign.py` | 2×2 cells and balanced server assignment: even splits, idempotency, slots reopening, withdrawals freeing slots, Sheet upgrades |
| `test_assign_refresh.py` | A refresh during assignment keeps the same cell |
| `test_membership.py` | Membership study: one offer in A0, repeats with the 7-day escape in A1, the 6-show cap, paid joining, Fresh gating, the task finishable without joining |
| `test_catalog.py` | The 58-product catalogue: counts, search keywords, ranking under the search patterns, filters, product pages, cheapest valid basket |

`harness.py` holds the shared setup and helpers; `mock_server.js` is the mock Google environment. Run the suites after any change to `index.html` or `Code.gs`, and before freezing the app for data collection.

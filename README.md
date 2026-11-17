# ShopKR study app

A fictional, mobile-first Korean shopping app used as a research instrument for studying dark patterns in e-commerce. Participants shop on their phone from a study link; every interaction is logged to a Google Sheet.

**Current version: 6.4.0** (app); Apps Script backend unchanged at 6.3.0

## What's in this repository

| Path | What it is |
| --- | --- |
| `index.html` | The whole app: one self-contained HTML file (no build step, no external requests except to your logging server) |
| `apps-script/Code.gs` | The logging and condition-assignment backend, run as a Google Apps Script web app bound to a Google Sheet |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are |

## Studies built in

Both designs live in `CONFIG.DESIGNS` near the top of `index.html`. A plain link opens the default study (`CONFIG.ACTIVE_DESIGN`); add `&design=<id>` to open another.

| Design id | Conditions | What differs |
| --- | --- | --- |
| `membership-nag-v1` (default) | `A0` no nagging · `A1` nagging with escape | After "Not now" on the ShopKR+ offer, A1 shows it again every 2nd product view and when the cart opens (max 6), with a "Don't show again for 7 days" option. ShopKR+ costs ₩4,990, counted in the task budget, and unlocks the members-only ShopKR Fresh section. |
| `search-x-drip-v1` | `A0B0`, `A1B0`, `A0B1`, `A1B1` | 2×2: search distortion (disguised ads + sponsored items pinned above any sort) × drip pricing (₩1,500 fee hidden until checkout) |

All 23 dark patterns can be switched individually from the hidden researcher panel (long-press the ShopKR logo), each with an honest control version.

## Participant flow

Consent → task brief → (condition assigned by the server) → shopping → debrief → completion code. Nothing is recorded before consent; declining leaves no trace; participants can withdraw their data at the debrief.

## Links

- `https://<user>.github.io/shopkr/?pid=P017`: assigned automatically after consent, balanced across all devices by the server.
- `…&cond=A1`: pins a condition (lab sessions).
- `…&design=search-x-drip-v1`: opens the 2×2 study.

## Setup

1. **Sheet and backend.** Create a Google Sheet → Extensions → Apps Script → paste `apps-script/Code.gs` → Deploy → New deployment → Web app, *Execute as: Me*, *Who has access: Anyone* → copy the `/exec` URL.
2. **Connect the app.** In `index.html`, put that URL in `ENDPOINT_URL` (inside `CONFIG`).
3. **Study text.** Replace the bracketed placeholders in `CONFIG.CONSENT`, `CONFIG.TASK_TEXT` and `CONFIG.CONTACT` with your IRB-approved wording.
4. **Publish.** Repository Settings → Pages → Deploy from a branch → `main`, folder `/ (root)`.
5. **Check.** Open the Pages address with `?pid=TEST1`, long-press the logo, and tap *Test server*. Complete one session and confirm rows appear in the `events`, `sessions` and `assignments` tabs. Delete test rows before real data collection.

**Updating the backend later:** Deploy → Manage deployments → Edit → *Version: New version* → Deploy (the URL stays the same).

## Data

- `events`: one row per interaction (screen, taps, impressions, choices, dark-pattern exposures), with participant ID, condition and timing.
- `sessions`: one row per participant with outcomes (order total, total spent, membership, nagging counts, `joinedAgainstInterest`, completion code, withdrawal flag).
- `assignments`: every condition assignment and its status, used to keep the groups balanced.

Run `purgeWithdrawn()` in the Apps Script editor before each export to delete the data of participants who withdrew.

## Notes

- Catalogue: 58 fictional products. Food & Snacks and Groceries have 10 each (the task's protein, staple and seasoning options), the other six categories 5 each, plus 8 members-only ShopKR Fresh items.
- All brands, products and prices are fictional. Payment uses a prefilled saved card only; the app never asks for card numbers, OTPs or passwords.
- The repository is public so GitHub Pages can serve it on a free plan. The Apps Script URL can add rows but cannot read the Sheet; keep the Sheet shared with the research team only.

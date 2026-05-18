# AGENTS.md — Cursor Agent context for Personalized Drive-Thru

> Read this file before every task. It is the source of truth for how this codebase works and how Cursor must behave inside it.

---

## Product context

Personalized Drive-Thru is a Spanish-language SaaS prototype for drive-thru personalization. A camera reads a vehicle's license plate, the system looks up the customer, greets them by nickname ("¡Hola Will!"), and suggests their usual order on a tablet/screen interface for the operator to confirm with one tap. No app, no card, no scan — plate is the identifier.

Target market: Guatemala first, Latin America next, global later. Built region-agnostic from the start (pluggable plate formats, i18n-ready, multi-currency-ready) but currently hardcoded to Guatemala for the first pilot.

Owner: Will (solo founder, mechatronics engineer in Guatemala). Workflow: Will writes prompts with Claude → pastes into Cursor → reviews summary → tests → commits.

---

## Tech stack

**Backend:** Python 3.x · Flask (runs on `0.0.0.0:5000`) · `threading` (camera simulation + preview daemon threads) · `RLock` for plate-state mutation.

**Computer Vision / OCR:** OpenCV (capture, preprocessing, ROI detection) · EasyOCR (text recognition with multi-frame voting) · Pipeline: grayscale → CLAHE → bilateral filter · Confidence threshold 0.25 · Multi-frame burst: 5 frames in 0.8s · 30s memory for last valid plate.

**Plate format (current, hardcoded GT only):** `^P[A-Z0-9]{6}$` — P + 6 alphanumeric uppercase. Refactor into pluggable region config is on the roadmap, not now.

**Storage:** Local filesystem only. `data/clientes.csv` (customer summary) + `data/historial_visitas.json` (full visit history). Cloud DB migration is planned but not started.

**Frontend:** Server-rendered Jinja templates (`templates/operator.html`) · Vanilla JavaScript (`static/js/main.js`, no framework) · CSS (`static/css/style.css`, tablet-first, custom palette) · Polling-based UI updates every 2s via `GET /api/current` · State machine driven by `document.body.dataset.viewState` (`idle | new | returning | detection_failed | cart_building`).

**Camera selector UI (frontend convention):** Camera mode is presented to the operator as a **three-option segmented control** (`Simulado` / `Cámara PC` / `Cámara Hikvision`), never as a boolean toggle. The frontend state variable is the string `currentCameraMode ∈ {"simulated", "real", "hikvision_rtsp"}`. Preview polling runs for `real` and `hikvision_rtsp`; it is off only for `simulated`.

**Languages used in product:** UI is Spanish-only. Code comments are mixed Spanish/English. Don't translate UI strings to English.

---

## Folder structure

Prototype_cursor/
├── app.py                       # Main Flask app, all routes, _build_operator_state()
├── config.py                    # Paths, camera mode, simulation flags, SUGGESTION_THRESHOLD
├── run.bat / stop.bat           # Windows scripts to start/stop the Flask server
├── services/
│   ├── plate_ocr.py             # Camera capture + OCR (real and simulated modes)
│   ├── customer_db.py           # CSV read/write for clientes.csv
│   ├── visit_history.py         # JSON read/write, suggestion_from_history(), tier logic
│   └── menu_data.py             # Café Barista Guatemala menu data, is_valid_order()
├── templates/
│   └── operator.html            # Operator screen markup
├── static/
│   ├── js/main.js               # Frontend polling, UI updates, cart logic
│   └── css/style.css            # Tablet/mobile responsive styles
└── data/
├── clientes.csv             # Customer summary table
└── historial_visitas.json   # Full visit log

---

## API endpoints (current contract — do not change without explicit request)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Render `operator.html` |
| GET | `/api/menu` | Categories + valid items |
| GET | `/api/current` | Polled state every 2s — single source of truth for UI |
| GET | `/api/lookup/<plate>` | Build state for an arbitrary plate |
| POST | `/api/set-plate` | Set or clear `_current_plate` (manual or programmatic) |
| GET | `/api/simulate-arrival` | Trigger one simulated or real detection |
| GET | `/api/camera-mode` | Get effective + env default mode |
| POST | `/api/camera-mode` | Hot-switch simulated/real; releases or starts preview |
| GET | `/api/camera-preview` | Latest cached JPEG (real mode only) |
| POST | `/api/update-nickname` | Update nickname; creates minimal CSV row if customer doesn't exist |
| POST | `/api/record-visit` | Save multi-item visit + analytics flag, returns fresh state |

`_build_operator_state(plate)` in `app.py` is the single function every screen update flows through. Returned fields: `type` (`idle | new | returning | detection_failed`), `plate`, `customer`, `prior_visits`, `suggestion_text`, `suggested_order`, `show_suggestion_actions`, `hint_nickname`, `needs_nickname`, `camera_mode`.

---

## Data contracts (exact field names)

### `data/clientes.csv` columns (in order)

- `placa` — uppercase, normalized (non-alphanumerics stripped).
- `nickname` — string, the customer's preferred name.
- `orden_favorita` — human-readable summary string built by `format_order_summary()`. Format: `"2x Cappuccino (16oz), 1x Croissant"`, items sorted alphabetically.
- `visitas` — integer count.
- `fecha_registro` — ISO 8601 with timezone offset, set once on first save, never overwritten.
- `ultima_visita` — ISO 8601 with timezone offset, refreshed on every visit.

### `data/historial_visitas.json` record shape

```json
{
  "placa_normalizada": "BPV658",
  "placa_original": "BPV658",
  "nombre": "Keni",
  "orden": [
    { "item": "Cappuccino (12oz)", "quantity": 1 },
    { "item": "Croissant dulce", "quantity": 1 }
  ],
  "fecha_hora": "2026-04-28T20:17:07-06:00",
  "suggestion_accepted": null
}
```

- `nombre` field name is **legacy and preserved for back-compat** — it stores the nickname string, not a person's name. Don't rename it.
- `orden` is **always an array of `{item, quantity}` objects**. Never a string. Never a flat list of strings.
- `suggestion_accepted` values: `true` (operator clicked "Mismo pedido"), `false` (operator clicked "Otro pedido" and built a different cart), `null` (no suggestion was offered — new customer or no history).

### Validation rules (enforced server-side in `_parse_and_validate_items`)

- Items list length: 1 to 10.
- Quantities: integer, 1 to 99.
- Total units across all items: ≤ 10 (this is the cart cap, not number of distinct lines).
- Every `item` string must exist in `menu_data` (`is_valid_order` check).
- Duplicate item lines are merged server-side before save.

---

## Key decisions already locked in (do not revisit without explicit request)

- **`orden` is an array.** Multi-item orders with quantities. The legacy `nombre` field name is kept for back-compat but stores the nickname.
- **`orden_favorita` in CSV is a derived summary string**, recomputed from full visit history on every visit via `most_common_order()` → `format_order_summary()`.
- **`canonical_order_key()`** (in `visit_history.py`) sorts items alphabetically and pipe-joins them. This is how two carts are compared for equality. Reuse it. Don't write a parallel comparison function.
- **`suggestion_accepted` analytics field** is recorded on every visit. Don't remove it.
- **Polling pauses while the cart is open** (`cartBuilding` flag in `main.js`). Don't break this — it prevents a new plate arrival from wiping the operator's in-progress order.
- **Server-side merging of duplicate cart lines** in `_parse_and_validate_items`. Don't move this to the frontend.
- **Maximum 10 units total per order**. Hard cap. Both UI and backend enforce it.
- **Spanish-only operator UI.** Do not introduce English strings into operator-facing copy.
- **Cart starts empty when "Otro pedido" is clicked.** Pre-fill is a deferred future refinement, not a current behavior.
- **30-second memory for last valid plate** in real OCR mode. Covers brief OCR failures. Don't shorten without discussion.
- **Camera mode UI is a three-option selector, never a boolean toggle.** Domain is exactly `simulated | real | hikvision_rtsp`. Active button uses the existing `--accent` color via `.camera-mode-seg__btn.is-active`. The simulate-arrival button is always enabled in all three modes; only its label changes (`Simular llegada` ↔ `Detectar placa`).

### Phase 2 suggestion logic (current state)

`suggestion_from_history()` in `services/visit_history.py` implements 4 tiers based on visit count:

| Visits | Logic | Message |
|---|---|---|
| 1–2 | Most recent complete order | `"Última vez pediste: …"` |
| 3–10 | Most-repeated exact combo, fallback to last order | `"¿Tu pedido de siempre? …"` or fallback message |
| 11–19 | Items appearing in ≥ `SUGGESTION_THRESHOLD` of visits | `"Sueles pedir: …"` |
| 20+ | Same probabilistic logic | `"Tu usual: …"` |

Tier boundary constants (`TIER_1_MAX_VISITS`, `TIER_2_MAX_VISITS`, `TIER_3_MAX_VISITS`, `TIER_3_PLUS_MIN_VISITS`) and `SUGGESTION_THRESHOLD` (in `config.py`, currently `0.60`) are tunable. Don't hardcode these values inline.

Always produce a suggestion if there are any visits — never return `(None, None)` with non-empty history. Fallback chain: Tier 3 → Tier 2 → Tier 1.

---

## Coding conventions

- **Don't change function signatures of anything `app.py` calls** without explicitly flagging it. Especially `suggestion_from_history`, `most_common_order`, `format_order_summary`, `canonical_order_key`, `last_complete_order`, `order_as_list`.
- **Constants over magic numbers.** Tier boundaries, thresholds, caps, timeouts — name them at the top of the relevant module.
- **Config goes in `config.py`.** Anything tunable (thresholds, paths, modes, intervals) lives there, not inline.
- **Don't write parallel utilities.** If a helper already exists (`canonical_order_key`, `format_order_summary`, etc.), reuse it. Don't reimplement.
- **Plate normalization:** strip non-alphanumerics, uppercase. Use the existing `normalize_plate()` helper everywhere.
- **Comments in Spanish or English are both fine.** Match the surrounding file.
- **No frontend frameworks.** Vanilla JS only. Don't introduce React, Vue, jQuery, etc.
- **No new dependencies without explicit approval.** If you think one is needed, flag it in the deliverable summary instead of adding it.
- **Threading is sensitive.** `_plate_lock` (RLock) protects `_current_plate`, `_last_valid_plate`, `_last_valid_plate_monotonic`, `_detection_failed_until`. Acquire it for every read or write of those.

---

## What Cursor must NEVER do

- **Never rename the `nombre` field** in `historial_visitas.json`. It's legacy back-compat and stores the nickname.
- **Never change `orden` from an array back to a string.** The data model is array-of-`{item, quantity}`. Period.
- **Never remove or rename the `suggestion_accepted` field.** It's the analytics hook that will sell future contracts.
- **Never translate operator UI to English.** Spanish-only. Always.
- **Never modify `app.py` when the task is scoped to `services/`** unless explicitly told to. Same the other way.
- **Never introduce a frontend framework.** Vanilla JS only.
- **Never add new third-party dependencies** without flagging it first in the deliverable summary and waiting for approval.
- **Never delete or migrate `data/clientes.csv` or `data/historial_visitas.json`.** They're real test data. If a schema change is needed, write a migration script and stop for review.
- **Never hardcode values that already live in `config.py`.** Read from config.
- **Never bypass `_parse_and_validate_items` validation** in the visit-record path. Items must be validated against the menu and quantity caps.
- **Never break the polling-pause-while-cart-is-open behavior.** It's a hard-won UX detail.
- **Never auto-commit or auto-push to git.** Will commits manually after testing.
- **Never write tests as a side effect of another task.** If tests are wanted, they'll be requested explicitly.

---

## Mandatory pre-task and post-task behavior

### Before editing anything:

1. **Read `AGENTS.md`** (this file).
2. **Read `startup_state.md`** if it exists in the repo root or `/mnt/project/` — it's the project's strategic context document.
3. **Read every file you're about to modify in full** before changing it. Do not edit blind.
4. **Read every file that imports from a file you're about to modify.** If `services/visit_history.py` is changing, check how `app.py` uses it.
5. If a task touches data shape (`orden`, `clientes.csv` columns, JSON field names), **stop and re-read the "Data contracts" section of this file** before writing code.

### After completing a task, output a deliverable summary with:

1. **Files modified** — full list, no exceptions.
2. **Files created** — full list.
3. **Files deleted** — full list.
4. **Function signatures added or changed** — with old vs. new shape.
5. **New constants or config values** — name, location, value, purpose.
6. **New dependencies** — if any. (There should usually be none. Flag and ask if you think one is needed.)
7. **Behavior changes the user will see** — UI, API, data, anything observable.
8. **Edge cases handled** — and edge cases knowingly NOT handled.
9. **Tests run** — what was manually verified, what was not.
10. **Anything skipped or deferred** — explicitly called out, not hidden.

Keep the summary tight and scannable. No prose paragraphs. Bullet lists only.

If a task is ambiguous or the request conflicts with this file, **stop and ask Will before writing code.**

---

## When AGENTS.md itself must be updated

After completing any task that changes any of the following, propose an
AGENTS.md update as part of the deliverable summary:

- A new API endpoint, or a changed endpoint contract
- A new file or folder in the structure
- A change to data contracts (CSV columns, JSON field names/shapes)
- A new locked decision, or reversal of an existing one
- A new "never do" rule learned from a mistake
- A change to coding conventions or threading rules
- A new module-level constant that other modules will read

Output the proposed AGENTS.md diff in the deliverable summary. Do not
edit AGENTS.md directly. I will review and approve the diff before it lands.

---

*Last updated: May 2026, three-mode camera UI (hikvision_rtsp) landed.*
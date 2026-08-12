# Plan: Hourly PAGASA Scraper Cron + MongoDB Geofence Activation

## 1. Goal

Every hour, scrape two PAGASA pages, then update the MongoDB `GEOs` database (`geofences` collection) so the geofences **matching the scraped hazard type are activated** (`status: true`).

Pipeline per run:

```
PAGASA site
   ├─ /weather/weather-advisory          -> get-weather-advisory.py  -> rainfall tiers
   └─ /regional-forecast/slprsd          -> get-regional-forecast.py -> provincial outlook
        │
        ▼
   scripts/update_geofences.py  (new)
        │  reads scraped JSON / imports parsers
        ▼
   MongoDB  GEOs > geofences  (activate matching geofences)
```

## 2. Type mapping (decision)

The user delegated the choice of which geofence `type` each script activates:

| Script | Source page | Output | Geofence `type` activated | Rationale |
|---|---|---|---|---|
| `get-weather-advisory.py` | weather-advisory | Rainfall tiers (`>200 mm`, `100–200 mm`, ...) with municipalities + impact | `Flood prone` **and** `Landslide prone` | Heavy-rainfall advisory == flood hazard; impacts explicitly mention landslides |
| `get-regional-forecast.py` | regional-forecast/slprsd | `headline`, `issued`, `valid`, per-province day/night outlook | `Flood prone` | Daily weather outlook (rain, wind) == flood watch for the forecast provinces |

> Note: the live `geofences` collection only contains `Flood prone` (21 docs) and `Landslide prone` (1 doc). There is no `Weather prone` type, so the forecast maps to `Flood prone` instead of the originally planned `Weather prone`.

Both values are module-level constants so they are trivially changeable.

## 3. Matching logic (activation)

For each geofence doc in `geofences`:

1. Read `geojson.properties.type` (the real schema nests everything under `geojson.properties`; top-level fields are fallbacks) — if it does not equal the script's target type → skip.
2. Build the location string as `"municipality, province"` (e.g. `"Legazpi City, Albay"`) from `geojson.properties`.
3. Case-insensitive **substring** match (either direction):
   - weather advisory: any `municipalities[i]` (from any rainfall tier) appears in the location, OR the location appears in the municipality string.
   - regional forecast: any `provinces[i]` key (province name) appears in the location, OR the location contains the province name.
4. On match → set `geojson.properties.status = true` (top-level `status` also set defensively).

Actual doc shape (verified against the live DB):

```json
{
  "_id": "6a79d8b0907ce7c2a2a0f591",
  "user_id": "50f4ba94-908c-44cf-981c-4545485595e7",
  "fence_id": "07f7d4fc-ca17-4c9d-a88b-b656535c97cc",
  "geojson": {
    "properties": {
      "name": "dsfgsdf",
      "type": "Flood prone",
      "status": true,
      "color": "#2c5a82",
      "municipality": "Legazpi City",
      "province": "Albay"
    }
  }
}
```

## 4. New file: `scripts/update_geofences.py` (implemented)

Single entrypoint for the cron run. Responsibilities:

1. Run the advisory scrape (`get_html_element` + `parse_pagasa_comment_advisory`) → tiers dict.
2. Run the regional forecast scrape (`get_html_element` + `parse_regional_forecast`) → forecast dict.
3. Connect via `pymongo`:
   - `MONGODB_URI` and `DATABASE_NAME` from `.env` (already present: `mongodb+srv://...@geos.cjkdqdt.mongodb.net/`, `GEOs`).
   - Collection: `geofences` (exists, 22 docs).
4. For each doc: match per §3, set `status=true` on match (`update_one` per doc with `_id` filter; updates `geojson.properties.status` and top-level `status`).
5. Print a run summary (counts scraped, matched, activated) and exit `0` on success, `1` on failure.

Supports `--dry-run` (prints what *would* be activated without writing).

## 5. Scratch scripts refactor (done)

- `scripts/get-weather-advisory.py`: prints the parsed advisory as JSON.
- `scripts/get-regional-forecast.py`: prints the parsed forecast JSON to stdout (dropped the old `something.txt` file write).

## 6. Config changes (done)

- `requirements.txt`: added `pymongo>=4.10` (4.17.0 present in `.venv`).
- `app/core/config.py`: added `MONGODB_URI: str` + `DATABASE_NAME: str` to `Settings`, and `extra="ignore"` on the settings config so the unrelated supabase/embedding keys in `.env` don't fail validation.

## 7. Cron / scheduler (implemented)

Platform is Windows → use **Task Scheduler** as the cron equivalent.

Registered task: `GEOs-PAGASA-Hourly` (created via `schtasks /create ... /sc hourly /st 00:00 /f`):

```powershell
schtasks /create /tn "GEOs-PAGASA-Hourly" /tr "<project>\scripts\run_pagasa_hourly.bat" /sc hourly /st 00:00 /f
```

- The task runs `scripts/run_pagasa_hourly.bat`, which `cd`s to the project root, runs `update_geofences.py` with the project venv, and appends output to `logs/pagasa_hourly.log` (dir auto-created).
- Verify: `schtasks /query /tn "GEOs-PAGASA-Hourly"`.
- Run now: `schtasks /run /tn "GEOs-PAGASA-Hourly"` (verified: Last Result 0, fresh log entries appended).
- Delete/replace: `schtasks /delete /tn "GEOs-PAGASA-Hourly" /f`.

## 8. Testing (done)

1. `pymongo` import + connection verified against live Atlas (`geos.cjkdqdt.mongodb.net`).
2. `--dry-run` verified: 21 `Flood prone` docs scanned, 21 matched (Albay/Sorsogon zones covered by today's forecast).
3. Live run verified: `geojson.properties.status` set `true` on the 21 matched geofences; summary printed.
4. Scheduled task registered and triggered manually — log appended, Last Result 0.
5. Note: no test framework is set up in this repo; verification was manual runs.

## 9. Open questions (ask user if unclear)

- Landslide-prone zones (1 doc) only activate when the advisory lists their municipality/province — none matched today (current advisory covers only Occidental Mindoro).
- Should previously activated geofences be deactivated when no longer mentioned (e.g. reset `status=false` after 24h), or only ever activate? Current behavior: only activate; deactivation = follow-up.
- Keep `get-flood-information.py` out of the hourly cron (not requested) — it remains standalone.
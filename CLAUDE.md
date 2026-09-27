# CLAUDE.md — Tahaqqaq / Bahith Al-Suwar

Media verification & provenance platform: AI-generation detection (image/video/audio/text), reverse image search, and asset provenance timelines ("who posted it first, where did it spread"). Arabic-first UX.

## The three planning documents (read before large tasks)

1. **PROJECT_IMPROVEMENT_PLAN.md** — full audit + 5-phase roadmap. The master plan.
2. **VISUAL_VERIFICATION_ENGINE.md** — flagship feature spec: 3-tier visual funnel (pHash/DINOv2 embeddings → VLM tools → date verification), agent loop, pgvector provenance index.
3. **REVERSE_SEARCH_PROVIDERS.md** — provider portfolio (Lens exact_matches, Vision Web Detection, TinEye, Yandex), harvesting rules, bake-off protocol.
4. **ORIGIN_V2_PLAN.md** — the rebuild of the origin feature (image/video first publication). **Active work.** `services/origin_engine.py` and `services/origin_agent.py` are FROZEN (v1): no edits, they are deleted at the end of phase 4. New code goes in `origin/`; the job runner routes there when `ORIGIN_V2=true`. Gate before every merge: `python scripts/bench_origin.py --engine v2 --check` (seed cases in `benchmark/benchmark.yaml`, baseline in `benchmark/baseline_v1.json`; each run spends SerpAPI credits — run it deliberately, not in a loop).

Work follows the roadmap phases in order unless Faisal says otherwise. Current status: **nothing implemented yet — Phase 0 (security) is the mandatory first task.**

## Stack

- **Backend:** Flask + SQLAlchemy + Bcrypt + PyJWT. Currently ONE file: `app.py` (~3,050 lines) — being split into `api/` (blueprints) + `services/` + `providers/` per the plan.
- **Frontend:** React 18 + Vite + Tailwind in `frontend/` (pages in `frontend/src/pages/`). Flask serves the built SPA from `frontend/dist`.
- **DB:** SQLite dev / Postgres on Render. Models in `models.py`.
- **Deploy:** Render.com — `render.yaml`, `build.sh`, gunicorn.
- **External APIs:** AIOrNot (image/video/audio/text detection), SerpAPI, Zenserp, Sightengine, xAI/Grok, ImgBB (being replaced by R2/S3), Google Cloud Vision (credentialed but unused — wire it in).

## Commands

```bash
# Backend (root)
pip install -r requirements.txt
python app.py                    # dev server :5000

# Frontend
cd frontend && npm install
npm run dev                      # dev :5173, proxies /api → :5000
npm run build                    # outputs frontend/dist (Flask serves this)

# Tests (as they get written)
pytest tests/
```

## Hard rules

1. **NEVER commit secrets.** The repo currently contains leaked credentials (Sightengine inline in app.py ~1517, `google-credentials.json`, `nskl.json`, ImgBB key in render.yaml, Zenserp key in README_MIGRATION.md). Until Phase 0 rotates them, treat the repo as compromised; never add new keys outside `.env` (gitignored) / Render env vars with `sync: false`.
2. **All external API calls go through `providers/`** (once created) — one module per vendor, shared retry/timeout/circuit-breaker base, normalized return types, usage metering. No `requests.post(vendor_url)` inside route handlers.
3. **Anything that can exceed ~5 s runs as a queued job** (Celery/RQ + Redis), returns `202 {job_id}`, streams progress via SSE. No blocking calls in gunicorn workers (today xAI blocks 180 s — that's the anti-pattern being removed).
4. **Persist results.** Every detection → `Analysis` row; every search → `Search` + `SearchResult`. (Today nothing is persisted — that's a bug, not a design.)
5. **Reverse-search harvesting: visual-match sections ONLY.** Never treat `organic_results`, `inline_images`, or Zenserp `organic` as image matches (root cause of the historical noise). Engine of record is `google_lens` (`type=exact_matches` / `visual_matches`), NOT the legacy `google_reverse_image`.
6. **Logging via the `logging` module**, structured, no `print()`. Never log keys or full API payloads at info level.
7. **Schema changes via Alembic migrations** once introduced — no `db.create_all()` in production paths.
8. **Keep Arabic-first UX**: user-facing strings in Arabic, RTL layouts; translation work happens in background jobs, never inline in request handlers.
9. **Write tests alongside extractions:** when moving logic out of app.py, pin behavior with pytest + `responses` (mock HTTP) before/while moving. Target: services/ and providers/ covered.
10. Prefer small, reviewable diffs — one blueprint/provider/service per commit. Git checkpoint before each extraction.

## Known landmines in the current code

- Duplicate route `/api/extract-frames` (app.py ~402 and ~531 — second handler unreachable dead code).
- Two `download_image()` definitions (~217, ~1335); duplicated imports throughout the header.
- `templates/` is the deprecated pre-React UI — delete once parity is confirmed (React SPA is the product).
- Playwright/captcha leftovers (`utils/captcha_handler.py`, yescaptcha env vars in render.yaml) are dead — remove, and drop the heavy `playwright` dependency (unless/until the VLM `read_post` screenshotter needs it in Phase 3; decide then).
- `Search`/`SearchResult`/`Analysis`/`AnalysisFrame` models exist but no endpoint writes them.
- Junk files at root: `clean (1)/`, `test.txt`, `test_output.txt`, `Untitled-1.png`, `zenserp_response.json`, ad-hoc `test_zenserp*.py`/`testzen.py` → fold into `tests/` + `tests/fixtures/` or delete.
- AIOrNot audio is on v1 (`/v1/reports/voice`); everything else on v2. Migrate during Phase 4.
- `MAX_CONTENT_LENGTH` is 256 MB with synchronous processing — reduce/gate until the queue exists.

## Environment variables

`SECRET_KEY, DATABASE_URL, ADMIN_EMAIL/PASSWORD/NAME, IMGBB_API_KEY (until R2), AIORNOT_API_KEY, SERPAPI_API_KEY, ZENSERP_API_KEY, XAI_API_KEY, SIGHTENGINE_API_USER, SIGHTENGINE_API_SECRET (new — replacing hardcoded), GOOGLE_APPLICATION_CREDENTIALS (path, file gitignored), later: R2_*, REDIS_URL, TINEYE_API_KEY, SENTRY_DSN`

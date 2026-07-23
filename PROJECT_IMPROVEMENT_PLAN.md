# Tahaqqaq / Bahith Al-Suwar — Master Improvement Plan
**Media Verification & Provenance Platform — Technical Audit + Refactor & Feature Roadmap**
*Prepared: July 23, 2026 — based on a full review of the current codebase*

---

## 1. Executive Summary

The platform today is a working proof-of-concept: a Flask monolith (`app.py`, ~3,050 lines) serving a React/Vite SPA, wired directly to five external APIs (AIOrNot, SerpAPI, Zenserp, Sightengine, xAI/Grok) plus ImgBB for image hosting. It does what it promises — AI detection for image/video/audio/text, reverse search, and a provenance timeline — but every capability is implemented as an inline, blocking, single-shot API call with no persistence, no caching, no verification of results, and several serious security leaks.

This plan is organized in five parts:

1. **Critical fixes (do first, ~1 day)** — leaked secrets and privacy issues that should be fixed before anything else.
2. **Architecture refactor (Phase 1–2)** — break the monolith into a service-oriented layout, add a job queue, caching, and result persistence, so the same API budget produces far more value.
3. **Getting full advantage of the APIs you already pay for** — concrete, unused capabilities in AIOrNot, SerpAPI, Google Vision, and xAI that can be turned on with small changes.
4. **The Agentic Reverse Search Engine (Phase 3)** — a full design for the autonomous search-verify-filter loop you described.
5. **Provenance 2.0 + roadmap, testing, and Claude Code workflow** — new feature ideas, phased timeline, and how to drive this work with Claude Code.

---

## 2. Current State Assessment

### 2.1 Stack inventory

| Layer | Technology | Status |
|---|---|---|
| Backend | Flask + Flask-SQLAlchemy + Flask-Bcrypt + PyJWT | Monolith in `app.py` (3,048 lines) |
| Frontend | React 18 + Vite + Tailwind + lucide-react | Clean SPA, 12 pages, minimal `apiClient` |
| DB | SQLite dev / Postgres (Render) | Models exist; **analysis results never saved** |
| Hosting | Render.com (`render.yaml`, gunicorn) | Free-tier Postgres |
| Image detection | Sightengine (`genai` model) + AIOrNot v2 | Working |
| Video detection | AIOrNot v2 `/video/sync` | Working, 120s blocking call |
| Audio detection | AIOrNot v1 `/reports/voice` | Working (v1 — outdated) |
| Text detection | AIOrNot v2 `/text/sync` | Working |
| Reverse search | SerpAPI `google_reverse_image` + Zenserp | Redundant double integration |
| Context investigation | xAI `grok-4.20-reasoning` + web_search tool | Working, 180s blocking call |
| Image hosting | ImgBB (public!) | Privacy + reliability problem |
| Google Cloud Vision | Imported, credentials shipped | **Never actually called** |

### 2.2 What already works well (keep)

- The provenance date-extraction heuristic chain in `process_urls_for_provenance()` (meta tags → JSON-LD → CSS selectors → URL path → text patterns, each with a confidence score and evidence trail) is genuinely good design. It becomes a core *tool* of the agentic engine.
- The DB schema (`models.py`) is ahead of the app: `Search`, `SearchResult`, `Analysis`, `AnalysisFrame`, `Source`, `Country`, `Keyword` with sensible indexes and an `image_hash` column ready for perceptual hashing. The schema anticipated the product the app hasn't become yet.
- Video → frame extraction → per-frame reverse search flow is a differentiating feature.
- Arabic-first UX with on-the-fly translation is a real market differentiator; keep it, but move translation out of the request path.

---

## 3. CRITICAL — Security & Privacy Fixes (Phase 0, do immediately)

These are ranked by severity. All of them are quick.

**3.1 Hardcoded Sightengine credentials in source.** `app.py` line ~1517 contains `api_user: "1797817014"` and `api_secret: "A4Y8VjQbRGgRsxwDSkMCQSh3tU4VTTcG"` inline. Anyone with repo access can burn your quota. → Move to env vars, **rotate the secret at Sightengine**.

**3.2 Google service-account private keys committed to the repo.** `google-credentials.json` and `nskl.json` (both 2.3 KB service account files) are in the project root and the repo history. → Revoke both keys in Google Cloud IAM, add `*.json` credentials to `.gitignore`, load via `GOOGLE_APPLICATION_CREDENTIALS` env path only. Because they're in git history, rotation (not just deletion) is mandatory.

**3.3 ImgBB API key committed in `render.yaml`** (`8a0183d939bb1db66e0e505b80c758e6`) and a Zenserp key printed in `README_MIGRATION.md`. → Rotate both, set `sync: false` in render.yaml like you already do for `ADMIN_PASSWORD`.

**3.4 Every user upload goes to a public image host.** All flows (`/api/upload`, `/api/ai-detection`, `/api/direct-search`, reverse search) push the user's image to ImgBB, making it publicly accessible on the internet — for a *verification* platform whose users may be journalists handling sensitive material, this is the most important trust issue in the product. → Replace with S3/Cloudflare R2 + short-lived presigned URLs (SerpAPI/Zenserp/AIOrNot only need the URL to be fetchable for minutes). R2 has zero egress fees and a generous free tier. Where APIs accept direct file upload (AIOrNot does), skip hosting entirely.

**3.5 Secrets partially leaked into logs.** `upload_to_imgbb()` prints the first/last 4 chars of the API key; debug prints dump full API responses. → Part of the logging cleanup in Phase 1.

**3.6 Other hardening (roll into Phase 1):** `CORS(app)` is wide open → restrict origins; no rate limiting on any endpoint (each anonymous request can burn paid API credits) → Flask-Limiter keyed to user/IP; `db.create_all()` at import time → Alembic migrations; JWT with no refresh/revocation; `MAX_CONTENT_LENGTH` of 256 MB with synchronous processing invites trivial DoS; uploaded files saved under their original (if secured) filename → always prefix with UUID (some endpoints do, some don't).

---

## 4. Architecture Refactor (Phases 1–2)

### 4.1 Problems in the current shape

- **One 3,048-line file** mixing routing, business logic, API clients, HTML parsing, translation, and date parsing. Duplicate route (`/api/extract-frames` registered twice at lines 402 and 531 — the second handler is dead code), duplicate `download_image()` definitions, duplicated imports (`requests`, `traceback`, `uuid`, `hashlib` each imported 2–3×), leftover Playwright/captcha machinery (`utils/captcha_handler.py`, `yescaptcha` paths in render.yaml) from a scraping era the code has already left behind.
- **Everything is synchronous inside gunicorn workers.** The xAI call blocks a worker for up to 180 s, video analysis 120 s, Zenserp 90 s. A handful of concurrent users exhausts all workers and the whole site stops responding.
- **Nothing is persisted.** The `Search`/`SearchResult`/`Analysis` tables are written by *zero* endpoints (verified: the only `db.session.add()` calls are for users, keywords, countries, sources, and file uploads). "My searches" and "My analyses" pages will always be empty, and every repeated search re-spends API credits.
- **No caching or dedup.** The same image searched twice = double SerpAPI + Zenserp + ImgBB spend. The `image_hash` column exists but nothing computes a hash.
- **`print()` everywhere** (hundreds of calls) instead of structured logging; broad `except:` blocks that swallow root causes.
- **Frontend `apiClient` is 10 lines** — no auth token interceptor, no retry, no shared error mapping; each page re-implements error handling.

### 4.2 Target backend layout

```
backend/
  app.py                    # app factory only (~50 lines)
  config.py
  extensions.py             # db, bcrypt, limiter, cache, cors
  api/                      # Blueprints: thin HTTP layer, no business logic
    detection.py            #   /api/detect/{image|video|audio|text}
    search.py               #   /api/search/{reverse|direct}
    provenance.py           #   /api/provenance, /api/agent/investigate
    media.py                #   /api/upload, /api/extract-frames
    auth.py, admin.py, files.py
  services/                 # Business logic, provider-agnostic
    detection_service.py    # ensemble logic, verdict normalization
    search_service.py
    provenance_service.py
    media_service.py        # hashing, EXIF, frame extraction, storage
    agent/                  # Phase 3 (section 6)
  providers/                # One client per external API, common interface
    base.py                 # retry/backoff, timeout, circuit breaker, usage metering
    aiornot.py  sightengine.py  serpapi.py  zenserp.py  xai.py
    vision.py  wayback.py  storage.py (R2/S3)
  tasks/                    # Celery/RQ jobs
  models/  migrations/  tests/
```

Design rules that make this pay off:

- **Provider interface + registry.** Every detector implements `detect(media) -> DetectionResult` with a normalized result (`verdict`, `ai_confidence`, `generator`, `raw`). Every search provider implements `search(image_url|query) -> list[Candidate]`. Adding/dropping a vendor becomes a one-file change; the ensemble and agent layers don't care who's underneath. This directly fixes today's problem where AIOrNot response parsing is copy-pasted with slight differences in four places.
- **Central HTTP policy in `providers/base.py`:** shared `requests.Session` with retry/backoff, per-provider timeout budget, circuit breaker (after N failures, mark provider down and skip it instead of hanging users), and a per-call usage log (provider, endpoint, latency, cost estimate, success) written to a `provider_calls` table → gives you a real API spend dashboard for the admin panel.
- **Job queue (Celery or RQ + Redis; Render supports both).** Anything > ~5 s becomes a job: video analysis, xAI investigation, provenance crawling, the agentic search. API returns `202 {job_id}`; frontend subscribes to progress via SSE (simpler than websockets on Render). This is also the substrate the agent needs to stream its "thinking" to the UI.
- **Cache + dedup by perceptual hash.** On every upload compute SHA-256 + pHash (`imagehash` lib). Before spending API credits, look up recent `Search`/`Analysis` rows by hash and serve cached verdicts (with a "cached from <date>, re-run?" option). This is the single biggest cost-saver available.
- **Persist everything.** Every detection → `Analysis` row; every search → `Search` + `SearchResult` rows. This instantly lights up the existing My Files / My Searches / Admin dashboards, creates the dataset for the source-reputation scoring in section 6, and makes results shareable via permalink.

### 4.3 Frontend refactor (smaller, parallel effort)

- `apiClient`: attach JWT from AuthContext, central 401 handling, retry-once on network error, and a `useJob(jobId)` hook that consumes SSE progress events.
- Extract the duplicated result-card / confidence-gauge / error-banner patterns from the six analysis pages into shared components.
- One new page: **Investigation view** (section 6.5) — the agent's live activity feed + final report. This becomes the product's signature screen.
- Delete the deprecated `templates/` folder (the React SPA replaced it) and dead files: `clean (1)/`, `test.txt`, `test_output.txt`, `zenserp_response.json`, `Untitled-1.png`, stray test scripts → move anything worth keeping into `tests/` and `docs/samples/`.

---

## 5. Take Full Advantage of the APIs You Already Use

This is what you asked about specifically — the current integrations use a fraction of what these vendors offer.

### 5.1 AIOrNot (biggest untapped value)

| Today | Available & unused |
|---|---|
| Image: v2 `/image/sync`, only `ai_generated` read | The same response also carries **deepfake/face manipulation**, **NSFW**, and **quality** reports — you already receive them and throw them away. Parse and display them. |
| Audio: **v1** `/reports/voice` | Migrate to **v2 voice/music endpoints** — voice-clone detection + AI-music detection with generator attribution, consistent with the rest of your v2 usage. |
| Video: `/video/sync` blocking 120 s | Use the **async endpoint + webhook/polling** from the job queue — no more worker starvation, and larger files become possible. |
| Text: confidence only | You already request `include_annotations=True` — the per-block annotations come back but are flattened (`annotations` array re-uses the overall verdict per block, `app.py` ~1645). Render real **per-sentence heat-mapping** in the UI. |
| — | **`external_id` + reports listing**: you already send an `external_id` for images; do it everywhere, keyed to your `Analysis.id`, so you can reconcile usage/billing against your DB. |

### 5.2 SerpAPI

- `google_reverse_image` is the **legacy** engine. Switch to **`google_lens`** (visual matches with much richer structure: exact matches vs. similar, per-match source metadata) and **`google_lens_exact_matches`** — exact matches are precisely what provenance needs and dramatically cut noise before filtering.
- Add **`google_images` with `image_url` + `tbs=qdr:`/custom date ranges** for time-bounded sweeps ("was this image online before 2023-01-01?") — this is the binary-search primitive the agent uses to bracket first-appearance dates (section 6.3).
- You send `gl=sa&hl=ar` for reverse image (line ~291) — good for Arabic recall, but run **two passes** (ar + en/us) and merge; single-locale search misses a large share of first-postings.

### 5.3 Google Cloud Vision — you ship credentials but never call it

`app.py` imports `google.cloud.vision`, the setup guide exists, credentials exist — and there's not a single Vision API call. Vision's **Web Detection** is arguably the single best-value provenance API available (1,000 free calls/month): it returns `full_matching_images`, `partial_matching_images` (crops!), `pages_with_matching_images`, and `web_entities`. Wire `providers/vision.py` into the reverse-search fan-out immediately — it's effectively a free third engine and its "partial match" capability catches cropped reposts that SerpAPI/Zenserp miss.

### 5.4 Zenserp vs. SerpAPI — stop paying twice

You run both for overlapping jobs (SerpAPI in `scrape_reverse_search` + provenance; Zenserp in direct search + timeline). After the provider abstraction exists, measure result quality per engine for 2 weeks (the `provider_calls` + `SearchResult` tables make this trivial), then either keep both as *complementary* engines inside the agent's fan-out, or cut one. Prediction based on the code: SerpAPI `google_lens` + Vision Web Detection covers Zenserp's reverse-image role; Zenserp stays useful only if its text-SERP pricing beats SerpAPI for direct search.

### 5.5 xAI / Grok

- The 180-second blocking call must become a queued job regardless.
- Today the xAI investigation receives **only the image URL** and searches blind. After the agentic pipeline exists, feed it the *evidence pack* (top verified matches, dates, domains) and change its job from "search the web for this image" to "**synthesize and narrate** this verified evidence in Arabic" — dramatically better output, fewer hallucinated origins, and cheaper (less tool-use).
- The response parsing at `app.py` ~770 guesses between three response shapes; pin the Responses API format and parse `output → message → output_text` deterministically. Also consider making the model configurable (`XAI_MODEL` env) instead of the hardcoded `grok-4.20-reasoning`.
- Alternative worth evaluating: the same "investigator/synthesizer" role can be served by the Claude API (Sonnet + web search tool) — for Arabic narrative quality, run a bake-off.

### 5.6 New provider candidates (fill capability gaps)

- **TinEye API** — the only commercial engine that *sorts by crawl date* ("oldest first"), which is literally your "first post on the internet" feature as a service. Currently you only deep-link to their web UI.
- **Wayback Machine CDX API (free)** — for any candidate URL, get the earliest archive capture: independent, tamper-proof lower-bound on "this page existed by date X", plus it can recover deleted first posts. A must-have tool for the agent.
- **C2PA / Content Credentials verification (free, `c2pa-python`)** — read cryptographic provenance metadata now embedded by DALL·E/Firefly/Leica/etc. Instant, zero-cost, standards-based "declared AI" signal *before* any paid API call; also its absence/stripping is itself a signal.
- **EXIF/XMP/IPTC forensics (free, local)** — creation dates, GPS, software tags (e.g. "Stable Diffusion" in Software field), thumbnail mismatch. Cheap first-pass triage.
- Optional later: Hive AI-generated-media API (you reference "TheHive" in names but actually call Sightengine), Reality Defender, or open-source deepfake models self-hosted for margin control.

---

## 6. The Agentic Reverse Search Engine (Phase 3 — flagship)

### 6.1 Concept

Replace "call one API, dump links" with an **investigation loop** run by an orchestrator (LLM with tool-use, e.g. Claude via API, or a deterministic planner + LLM only for judgment calls). The agent plans, fans out searches, *verifies* that each candidate page really contains the image, extracts and cross-checks dates, filters noise, iterates with query mutations until the evidence converges, and produces a sourced report. Every step is streamed to the UI so the user watches the investigation happen — that's the "highly autonomous and smart" feel you want.

### 6.2 Tool belt (each is a small, testable module in `services/agent/tools/`)

1. `normalize_media` — pHash/SHA-256, EXIF/XMP scan, C2PA verify, quality check, auto-crop borders/watermark strips, generate flipped + center-crop variants.
2. `reverse_search(engine, image_url, locale, date_range)` — unified over SerpAPI Lens, Vision Web Detection, Zenserp, TinEye. Returns normalized `Candidate[]`.
3. `text_search(query, locale, date_range)` — SERP text search for captions/keywords the agent derives from matches.
4. `fetch_and_verify(url)` — fetch page (your existing session/retry code), confirm the image is actually present via pHash similarity of page images (kills the #1 noise source: pages that merely *look* related), extract publish date with the existing evidence-chain extractor, pull title/author/og:tags.
5. `wayback_lookup(url)` — earliest CDX capture; also `wayback_search(image)` against archived pages when a candidate 404s.
6. `date_bracket(image, date)` — time-bounded reverse search to binary-search the first-appearance window.
7. `source_reputation(domain)` — score from your `Source` table (verified news vs. content farm vs. social), enriched over time by admin curation — this is where your existing Sources/Countries admin panel finally earns its place.
8. `report(evidence)` — LLM synthesis (xAI or Claude) of the verified evidence pack into the Arabic narrative + structured JSON.

### 6.3 The loop

```
INGEST      normalize_media → cache check by pHash (stop early if seen)
PLAN        agent picks engines/locales based on media type & EXIF/C2PA hints
FAN-OUT     parallel reverse_search across engines × {ar, en} locales
HARVEST     dedupe candidates (canonical URL + pHash of thumbnails)
VERIFY      fetch_and_verify top-N by prior score; drop pages w/o pHash match
DATE        for each verified page: extractor date + wayback capture date
            → keep earliest corroborated date per page
ITERATE     if evidence weak: mutate (crops/flips), derive text queries from
            match titles/entities, date_bracket around earliest candidate;
            loop until convergence or budget (max tool calls / $) exhausted
SCORE       confidence per finding = f(pHash similarity, date evidence
            strength, source reputation, corroboration count)
REPORT      first_seen + ranked timeline + spread map + narrative, all with
            per-claim evidence links; persist Search/SearchResult rows
```

Key engineering properties: **budgeted** (hard cap on tool calls and spend per investigation, tiered by user plan), **resumable** (each step is a queued task writing to an `investigations` table, so a crash resumes instead of re-spending), **streamed** (SSE events: `plan`, `tool_call`, `candidate_found`, `verified`, `rejected(reason)`, `done`), and **honest** (every claim in the report carries its evidence URLs and confidence; the agent says "inconclusive" rather than inventing an origin).

### 6.4 Noise-filtering stack (the "catch real data" part)

Layered, cheapest first: canonical-URL dedup → domain blocklist (stock-photo mirrors, image proxies, known scrapers) → pHash verification on the actual page (≥ ~0.85 similarity to count as "same image"; lower band flagged as "modified variant" — itself useful provenance data) → date-evidence quality gate (reuse your confidence/evidence system; a date from `article:published_time` outranks a regex hit in body text) → cross-corroboration (an "earliest" claim needs Wayback or second-source support to be labeled *confirmed*, else *probable*) → reputation weighting.

### 6.5 UX: the Investigation page

Left: live agent activity feed (searching Google Lens (Arabic)… 43 candidates → verifying top 12… 7 confirmed, 5 rejected (image not on page)… earliest so far: twitter.com, 2021-03-14, checking archive…). Right: results assembling in real time — First Seen card (date + source + confidence badge), vertical timeline (your existing `ResultsTimeline` component upgraded with confidence chips and evidence popovers), and a spread visualization (domain/platform clusters over time). Export as PDF report (you already have PDF tooling ambitions — this is the killer artifact for journalist users).

---

## 7. Additional Feature Ideas (Phase 4+ backlog)

- **Ensemble verdicts:** run Sightengine + AIOrNot (+ Hive later) on every image and present a weighted combined verdict with per-model breakdown — "2 of 3 models say AI (87% avg)" is far more trustworthy than one number, and you already integrate both vendors.
- **Video provenance:** you extract frames for detection; feed representative frames (scene-change detection via OpenCV histogram diff instead of fixed intervals) into the agentic reverse search → provenance for *videos*, which almost no competitor does well.
- **Monitoring/alerts:** users already can save keywords (`Keyword` model exists) — add a scheduled job that re-runs saved searches and emails/pushes when a tracked image reappears somewhere new. Turns one-shot tool into a subscription-worthy service.
- **Public share pages & API:** read-only permalink for a completed investigation (great for journalists citing you), then a metered public REST API as a revenue line.
- **Browser extension:** right-click → "Verify with Tahaqqaq" (uses the public API).
- **Batch mode:** CSV/folder of images → queued investigations → consolidated report.

---

## 8. Phased Roadmap & Effort

| Phase | Scope | Effort (focused) | Exit criteria |
|---|---|---|---|
| **0 — Security hotfix** | Rotate ALL leaked keys (Sightengine, Google SA ×2, ImgBB, Zenserp); purge secrets from repo + history; R2/S3 replaces ImgBB; CORS restricted | 1–2 days | No secret in repo; uploads private |
| **1 — Restructure** | Blueprints + services + providers split; logging; delete dead code/templates; Alembic; rate limiting; frontend apiClient hardening | 1–1.5 weeks | `app.py` < 100 lines; all endpoints green |
| **2 — Infra** | Redis + Celery/RQ; SSE progress; pHash cache & dedup; persist Search/Analysis; provider usage metering; admin spend dashboard | 1–1.5 weeks | Video/xAI run as jobs; repeat search = cache hit; My Searches populated |
| **3 — Agentic engine** | Tool belt (6.2) incl. Vision, Wayback, C2PA, TinEye; loop + budget + scoring; Investigation UI | 2–3 weeks | Investigation beats old reverse search on a 30-image benchmark you curate |
| **4 — Provenance 2.0 + ensemble** | google_lens migration, dual-locale, date bracketing, ensemble verdicts, AIOrNot v2 audio, per-sentence text heatmap, video provenance | 1–2 weeks | — |
| **5 — Quality & growth** | pytest suite (providers mocked via `responses`), CI, error tracking (Sentry), monitoring/alerts feature, share pages, PDF export | ongoing | ≥70% coverage on services/ |

Benchmark note for Phase 3: build a small ground-truth set (30–50 images where *you know* the true first posting) early — it's the only way to prove the agent beats the current pipeline and to tune the scoring weights.

---

## 9. Working This Plan with Claude Code

When you open this project in Claude Code:

1. **Add a `CLAUDE.md`** at repo root: stack summary, "never commit secrets", "all provider calls go through `providers/`", "all long tasks go through the queue", test command, and a pointer to this plan.
2. **Sequence sessions to the phases** — one phase (or one provider/tool module) per session keeps diffs reviewable. Phase 0 and the `app.py` split are ideal first sessions: mechanical, high-value, low-risk.
3. Ask Claude Code to **write tests alongside every provider/service it extracts** (mock HTTP with the `responses` lib) — the refactor stays safe because behavior is pinned before moving code.
4. Keep `git` checkpoints per module extraction; the split of a 3,000-line file is where version control earns its keep.

---

## Appendix A — Dead code & cleanup inventory

`templates/` (7 legacy HTML pages superseded by React) · duplicate `/api/extract-frames` route (line ~531, unreachable) · duplicate `download_image()` (lines ~217 and ~1335) · duplicated imports throughout `app.py` header · `utils/captcha_handler.py` + yescaptcha/Playwright env vars in `render.yaml` (scraping-era leftovers; also lets you drop the heavy `playwright` dependency) · `clean (1)/`, `test.txt`, `test_output.txt`, `testzen.py`, `test_zenserp*.py` (fold into `tests/`), `zenserp_response.json` (move to `tests/fixtures/`), `Untitled-1.png` · unused `SpeechRecognition`/`pydub` deps if no transcription feature is planned (or keep and actually ship transcription).

## Appendix B — Env var checklist after Phase 0

`SECRET_KEY, DATABASE_URL, ADMIN_*, AIORNOT_API_KEY, SERPAPI_API_KEY, ZENSERP_API_KEY, XAI_API_KEY, XAI_MODEL, SIGHTENGINE_API_USER, SIGHTENGINE_API_SECRET, GOOGLE_APPLICATION_CREDENTIALS, R2_ACCOUNT_ID/R2_ACCESS_KEY/R2_SECRET/R2_BUCKET, REDIS_URL, TINEYE_API_KEY (later), SENTRY_DSN (later)` — all `sync: false` in `render.yaml`.

# Claude Code Session Playbook
**Ordered sessions with ready-to-paste prompts. One session = one reviewable chunk.**
*Companion to CLAUDE.md — July 23, 2026*

Rules of thumb: start each session with a clean git state; let each session end with passing checks and a commit; don't mix phases in one session. Prompts below assume CLAUDE.md and the three planning docs are in the repo root (they are).

---

## Session 1 — Phase 0: Security hotfix  *(do this first, ~half a day)*

> Read CLAUDE.md and section 3 of PROJECT_IMPROVEMENT_PLAN.md. Execute Phase 0:
> 1. Remove the hardcoded Sightengine credentials from app.py (~line 1517) → env vars SIGHTENGINE_API_USER / SIGHTENGINE_API_SECRET.
> 2. Delete google-credentials.json and nskl.json from the repo; add a .gitignore covering credentials, .env, uploads/, user-data/, __pycache__, frontend/node_modules, frontend/dist.
> 3. Remove the ImgBB key value from render.yaml (make it sync: false like ADMIN_PASSWORD); remove the Zenserp key from README_MIGRATION.md.
> 4. Restrict CORS to configured origins (env CORS_ORIGINS, default localhost dev ports).
> 5. Write docs/KEY_ROTATION.md listing every leaked key and where to rotate it (Sightengine dashboard, Google Cloud IAM ×2, ImgBB, Zenserp).
> Don't refactor anything else in this session.

**Manual follow-ups (only you can do these):** rotate all five credentials at the vendors; update Render env vars; if the repo was ever pushed anywhere, scrub history (`git filter-repo`) or treat old keys as burned (rotation makes this moot).

## Session 2 — Repo hygiene *(quick)*

> Per CLAUDE.md "Known landmines": delete the deprecated templates/ folder, utils/captcha_handler.py and yescaptcha/playwright env vars from render.yaml, the dead duplicate /api/extract-frames route and duplicate download_image() in app.py, and root junk files (clean (1)/, test.txt, test_output.txt, Untitled-1.png). Move zenserp_response.json to tests/fixtures/ and the ad-hoc test_zenserp*/testzen scripts into tests/manual/. Deduplicate the import block at the top of app.py. Remove playwright from requirements.txt. Verify the app still boots and the React build still serves.

## Session 3 — Quick-win result quality *(ships user-visible improvement immediately)*

> Read REVERSE_SEARCH_PROVIDERS.md section 5. In the current app.py (pre-refactor, keep changes minimal):
> 1. In scrape_reverse_search(): switch engine google_reverse_image → google_lens, run type=exact_matches and type=visual_matches, harvest ONLY visual-match sections (never organic_results / inline_images), and tag each result exact|similar.
> 2. In direct_search_api() image path: stop harvesting the Zenserp 'organic' section as image matches.
> 3. Add providers/vision.py-style helper (single function for now) calling Google Vision Web Detection (credentials via GOOGLE_APPLICATION_CREDENTIALS) and merge full/partial matching images + pages into the same normalized result list, tagged by bucket.
> 4. Update the ReverseSearch/Provenance frontend cards to show the exact/similar/page-mention labels.

## Session 4 — Phase 1: Split the monolith (backend)

> Read PROJECT_IMPROVEMENT_PLAN.md section 4.2. Restructure into the target layout: app factory + extensions.py; blueprints api/{detection,search,provenance,media,auth,admin,files}.py; move business logic to services/; create providers/{base,aiornot,sightengine,serpapi,zenserp,xai,vision}.py with the shared session/retry/timeout base and normalized DetectionResult/Candidate dataclasses. Replace all print() with logging. Pin behavior first: write pytest tests (responses lib for HTTP mocks) for each provider's parsing before moving it. One provider/blueprint per commit. Exit: app.py < 100 lines, all routes respond as before, tests green.

## Session 5 — Phase 1: Frontend hardening + rate limiting

> Frontend: upgrade services/apiClient.js — attach JWT from AuthContext, central 401 → logout/redirect, one retry on network error; extract shared ResultCard/ConfidenceGauge/ErrorBanner components from the six analysis pages. Backend: add Flask-Limiter (per-user/IP; strict limits on endpoints that spend API credits) and Alembic (baseline migration replacing db.create_all). 

## Session 6 — Phase 2: Queue + SSE + persistence + cache

> Read PROJECT_IMPROVEMENT_PLAN.md section 4.2 (queue/cache/persist). Add Redis + RQ (or Celery — pick simpler on Render). Convert video analysis, xAI investigation, and provenance to jobs returning 202 {job_id} with an SSE /api/jobs/<id>/events stream; add useJob(jobId) hook in the frontend. Compute SHA-256 + pHash on every upload; persist every detection → Analysis and every search → Search/SearchResult; serve cache hits for repeat hashes with a "re-run" option. Add provider_calls usage metering table + a simple admin spend view.

## Session 7 — Storage privacy

> Replace ImgBB with Cloudflare R2 (boto3 S3-compatible): private bucket, presigned GET URLs (15 min) for APIs that need a fetchable URL; direct file upload to AIOrNot where supported. Keep an IMGBB fallback flag for rollback. Delete upload_to_imgbb after cutover.

## Sessions 8–11 — Phase 3: Visual Verification Engine (one component per session)

> **8 — Tier 1 core:** per VISUAL_VERIFICATION_ENGINE.md §2: media_service embedding pipeline (DINOv2-S via torch, CPU), pgvector migration + image_vectors table, fetch_and_verify(url) (page fetch → extract og:image/large <img> → download → pHash + embedding vs query → verdict bands 0.90/0.75). Bolt onto existing search output as a post-filter behind a feature flag. Include unit tests with fixture images (same/cropped/different).
> **9 — Benchmark + bake-off:** build tests/benchmark/manifest.json tooling + scripts/bakeoff.py per REVERSE_SEARCH_PROVIDERS.md §4 (I supply the 40 images). Run, tune thresholds, decide engine portfolio.
> **10 — VLM tool belt:** visual_judge, describe_and_queryize, read_post, suggest_recrop per §2 Tier 2 — one adapter interface, Claude vision + Grok vision implementations, budget metering.
> **11 — Agent loop + Investigation UI:** the state-machine loop (§3) as chained jobs writing investigation_steps; SSE-streamed Investigation page (activity feed + assembling results + first-seen card); TinEye (sort=crawl_date) + Wayback CDX + Yandex providers.

## Session 12+ — Phase 4/5 per the roadmap

AIOrNot v2 audio migration, unused-field surfacing (deepfake/nsfw/quality), per-sentence text heatmap, ensemble verdicts, video provenance via keyframes, monitoring/alerts on saved keywords, share pages, PDF report export, Sentry + CI.

---

## Benchmark set — your homework (needed by Session 9)

Collect ~40 images with known ground truth into `tests/benchmark/`: 10 Arabic news, 8 global news, 6 viral memes, 6 social-media originals, 5 AI-generated that circulated, 5 fresh personal photos (controls, must return 0). For each: the image file + first-post URL + first-post date + category in manifest.json. This set is what makes every tuning decision objective.

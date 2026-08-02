# Full Investigation — Improvements vs Plan (2026-07-29)

Evidence-based audit after live-driving the app. Sources: `provider_calls`
metering (our own data), server logs from the live session, code inspection,
and the three planning documents.

---

## 1. Why Reverse Image Search "takes forever"

The ReverseSearch page = `POST /api/upload` + `POST /api/direct-search`,
both **synchronous**. Measured contributors, worst-first:

| # | Contributor | Measured | Where |
|---|---|---|---|
| 1 | **Zenserp is DEAD and slow to die** | 3/3 calls failed; avg **31s**, worst **61s** just to receive a 500 | `provider_calls`; timeout is 90s in `providers/zenserp.py` |
| 2 | **direct-search never became a job** | whole pipeline runs inside the HTTP request | Phase 2 converted video/xai/provenance only |
| 3 | **Inline translation** | ~20 items × GoogleTranslator HTTP calls (10 threads) ≈ 2–6s | `build_direct_search_timeline` — violates CLAUDE.md rule 8 ("translation in background jobs, never inline") |
| 4 | **Visual post-filter inline** (when VISUAL_VERIFY=true) | 8 page fetches × (5,10)s timeouts + downloads ≈ 10–60s (ajel.sa alone burned ~40s retrying) | `apply_visual_post_filter` in the request/job |
| 5 | **DINOv2 cold start in-request** | first embed after boot: **5.3s** (warm: **0.105s**) | `/api/upload` → `index_file` |
| 6 | R2 upload | ~1.0s avg (0.5–2.1s) | fine |
| 7 | SerpAPI Lens | ~7.3s per call × 2 | inherent; fine when parallelized/async |

**Verdict:** the single biggest cause is Zenserp — a dead account that every
search waits 15–90 seconds on before failing. Structural cause #2: the
plan's own rule ("anything >5s runs as a queued job") was applied to three
endpoints but **not** to `direct-search`, `ai-detection`, `verify-audio`,
`text-detection`, `image-source-search`, or `upload` — all still synchronous.
In dev (no Redis) even the converted jobs run inline, which is expected
locally but means local timings overstate prod pain for provenance/video.

Reference good news: warm embeds are 0.105s — Tier-1 math is effectively
free, as the spec predicted. The costs are network waits, not the model.

---

## 2. Plan compliance audit

### Phase 0 — Security (plan §3) — DONE (code side)
- Secrets → env; credential files deleted; .gitignore hardened ✅
- CORS allowlist ✅ · KEY_ROTATION.md ✅ · .env/.env.example exist ✅
- ⚠️ OPEN (user actions): key rotation still not done — **Zenserp account
  is dead** (confirmed live: our key → 500 on every call; bogus key → 403,
  so the account is recognized but broken); Google Vision has **no
  credentials file** (old ones revoked/deleted; new SA key not yet created);
  git history still contains the old secrets (filter-repo pending).

### Quick wins (REVERSE_SEARCH_PROVIDERS §5) — DONE
- google_lens engine of record, visual-match-only harvesting ✅
- Vision Web Detection wired (currently inert — no credentials) ✅/⚠️
- exact/similar/page_match labels end-to-end ✅ (verified live)

### Phase 1 — Architecture (plan §4) — DONE
- app.py 73-line factory; api/ (8 blueprints), services/ (8), providers/ (9,
  shared base with retry/breaker/metering) ✅
- Flask-Limiter (spend endpoints 10/min) ✅ · Alembic (3 migrations,
  self-stamping baseline) ✅ · frontend apiClient + shared components ✅
- 53 tests / 20 commits ahead of origin (unpushed, per rule)

### Phase 2 — Queue/persist/cache (plan §4.2) — PARTIAL
- RQ + Redis + worker + SSE + useJob ✅ — but only video/xai/provenance.
  **Rule 3 not finished**: 6 spend endpoints still block workers (list above).
- SHA-256+pHash, Analysis/Search persistence, hash-cache with rerun ✅
  (verified live; note Zenserp failures mean no direct-search rows persisted
  yet — only provenance×2, ai_image×2)
- provider_calls metering + admin spend view ✅ (this audit used it)

### Phase 3 — Visual Verification Engine — Tier 1 DONE (session 8 of 8–11)
- DINOv2-S via timm ✅ (live: first-seen confirmed at sim 0.971 where pHash
  distance 15 would have MISSED it — the spec's core claim proven)
- image_vectors + pgvector-on-Postgres migration ✅ · post-filter behind
  VISUAL_VERIFY ✅ (live: 8 checked → 5 confirmed / 1 ambiguous / 2 rejected)
- ⏳ Session 9 bake-off (**blocked on the 40 ground-truth images**),
  10 VLM tool belt, 11 agent loop + Investigation UI + TinEye/Wayback/Yandex

### CLAUDE.md landmines still open
- Frontend date fields NEVER matched the backend (pre-existing):
  ReverseSearch reads `item.date_found` (backend sends `date_text`);
  Provenance reads `item.timestamp` / `first_seen.date` (backend sends
  `published_at`). **Live impact: 8 extracted dates displayed as
  "تاريخ غير معروف"** — the provenance feature looks broken even when it works.
- `MAX_CONTENT_LENGTH` still 256 MB with sync uploads.
- AIOrNot voice still v1 (Phase 4 item).
- FaceOnLive endpoint is an intentional 500 stub — decide: remove or rebuild.
- Visual verdicts (confirmed/similarity) not yet shown in UI (session 11).
- Facebook/blocked pages produce timeline entries titled "Error: 400…" —
  ugly; needs junk-domain blocklist (spec Tier 0, not yet built).

---

## 3. Defects found by the live run (already fixed + committed)
- numpy int64 crashed SSE serialization (frontend spun forever) → cast.
- dotenv kept inline `#` comments as env values (broke Vision + ImgBB) → fixed.
- Dev DB unmigrated → upgraded; image_vectors now populated.

## 4. Ranked recommendations (next session order)

1. **Stop the Zenserp bleeding** (biggest UX win, ~1h): fail fast when the
   provider is erroring (breaker threshold is 5; drop Zenserp timeout to
   ~20s), and/or build the ReverseSearch timeline from the Lens harvest we
   already pay for (`/api/image-source-search` results) so the page works
   with Zenserp dead. Faisal in parallel: fix or abandon the Zenserp account
   (plan §7 says measure survivor-rate and consider cutting it anyway).
2. **Fix the date-field mismatches** (30 min, huge visible win — dates
   currently never render on two pages).
3. **Finish rule 3**: convert direct-search (+ ai-detection) to jobs with
   SSE; move translation into the job; preload DINOv2 at worker boot;
   defer upload-time embedding indexing to a job.
4. **Tier-0 junk filtering** (spec): canonical-URL dedup + domain blocklist
   (kills the facebook "Error: 400" entries) before Tier 1 spends fetches.
5. Then resume the session plan: 9 (needs the 40 images) → 10 → 11.

## 5. Cost note (this session's real spend)
serpapi ×6 (~$0.06–0.12), aiornot ×1, sightengine ×1, r2 ×7 (free tier),
zenserp ×3 (failed, likely uncharged). All visible in the admin spend view.

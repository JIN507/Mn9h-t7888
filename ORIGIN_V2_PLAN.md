# Origin v2 — rebuild plan for "البحث عن مصدر الصورة / الفيديو"

Goal: given an image or a video, find where and when it was first published,
show how it spread, and give the user the verified evidence to judge a claim.
Nothing else. AI-generation detection is a separate tab and is not part of this
feature.

This document is the contract for the rebuild. Every phase has a gate that is a
command, not an opinion.

---

## 1. What we learned (why v1 failed)

| Failure | Root cause | Rule for v2 |
|---|---|---|
| Google returned nothing, engine said "0 results" | "no results" answer swallowed as success | Every engine answer is one of: `results`, `empty`, `refused`, `error`. Never silently 0. |
| The uploaded file was refused by Google's fetcher (AI-restored copy) | The pipeline searched only the uploaded bytes | Search a **set of copies** (uploaded, downscaled, every full-size copy found on verified pages, platform media) until no new copy appears. |
| False origins (2021 Facebook post, 2019 Pinterest pin) | An engine thumbnail was accepted as proof the page shows the image | A sighting is an origin candidate only if the image was seen **on the page itself or via the platform's own media**. Engine thumbnails only rank candidates. |
| Same image, five different answers in eight runs | Lens/Google results vary per call; the pipeline was serial and time-starved so the decisive step (pivot to the original copy) often never ran | Deterministic rounds, everything inside a round in parallel, decisive steps first. Target ≤ 120 s. |
| 20–40 % of LLM steps were engines re-run for zero new results | The LLM was asked to do mechanical work | The LLM does two things only: extract names/place/event from text we collected, and write 2–3 search queries. No tool loop. |
| 24 thresholds, 13 guard flags, whack-a-mole patches | Confidence numbers mixed "image seen", "engine claims", "date quality" | One evidence model with two independent axes (image evidence, date evidence) and one eligibility rule. |
| 365 SerpAPI credits burned in a week | No credit accounting | Hard budget per investigation (12 credits image, 20 video), metered and shown in the report. |
| Optimising on one hard anecdote | No ground truth | A benchmark file with known origins runs before every change. Ship only when the benchmark does not regress. |

---

## 2. Resources — what each one really gives us (verified this month)

| Resource | Input | Gives | Cost | Verified limits |
|---|---|---|---|---|
| **SerpAPI Google Lens** `exact_matches` | public URL | pages holding the same file (0–400 rows), dates for some | 1 credit/call | URL only; refuses some files (AI-processed) with a "no results" answer; results vary per call; en/ar locales differ |
| **SerpAPI Google Lens** `visual_matches` (default call) | public URL | ~30–60 similar pages, **titles that name people/events**, `related_content` entity chips | 1 credit | same fetch limits; entity chip can be a look-alike |
| **SerpAPI Yandex Images** | public URL | 9–30 pages, strong on faces / Arabic & Russian web | 1 credit | needs plain public URL (R2 public works, presigned does not) |
| **SerpAPI Google text** | query | 10–20 organic results | 1 credit | ranking drifts day to day; `site:` queries slow |
| **SerpAPI google_reverse_image** | public URL | "pages with matching images" (0–10) | 1 credit | often refused; low value — optional |
| **TinEye website** (Playwright) | public URL | 3–20 copies with **crawl dates** (upper bounds) | free | ~25 s; upload not needed |
| **Twitter syndication** (`providers/tweet.py`) | tweet URL | full-res photos, caption, exact time | free | none seen |
| **Instagram /media redirect, Facebook crawler UA, Telegram embed, TikTok/IG/X IDs** | post URL | the post's image and exact time | free | Instagram/Facebook occasionally 400; Reddit blocked |
| **YouTube Data API** | query / video id | upload time, storyboard frames | free quota | needs YOUTUBE_API_KEY (set) |
| **Wayback CDX / Save** | URL | first capture (upper bound), archive copy | free | throttle 2 concurrent; anonymous save often 500 |
| **DeepSeek** (vision + chat) | image / text | description, name extraction, query writing | cheap | mis-identifies events when asked open-ended — use only to extract from text we give it |
| **Grok** (xAI, `grok_key`) | question (+image) | X and web leads | paid tokens | leads are generic unless the question names the people/event; use once, late, with names |
| **Google Cloud Vision Web Detection** | **image bytes** | full/partial matching images, pages, **web entities** | ~$1.5–3.5 per 1000 | **not configured** — needs the credentials JSON. It is the only engine that takes bytes, so it bypasses Google's URL-fetch refusal. Strongly recommended. |
| **Own index** (`image_vectors`, pgvector) | embedding | "we saw this before" across investigations | free | grows with use |
| **R2 public + ImgBB** | bytes | public URLs for the copies we search with | free | both configured now |
| Bing Visual Search | — | — | — | website flow broken for headless browsers; API is paid (Azure) — out |
| Zenserp | — | — | — | quota exhausted — out |
| AIOrNot / Sightengine | — | AI verdicts | — | **out of scope for this feature** (separate tab) |

Hard limits no design removes: Google Lens is URL-only and refuses some files;
its results vary per call; Google's upload UI is CAPTCHA-protected (tested, not
bypassed); social platforms are JavaScript-only (we go through their media
endpoints instead); SerpAPI credits are finite.

---

## 3. Principles

1. **Copies, not the upload.** The investigation searches a growing set of copies of the same photo. The uploaded file is copy #1.
2. **Page evidence or nothing.** Only a sighting whose image we saw on the page or via the platform's media can be an origin. Everything else is a lead, shown as "غير مؤكد".
3. **Two axes, one rule.** `image_evidence ∈ {page, platform, engine_claim, none}`, `date_evidence ∈ {platform_id, structured, weak, none}`. Origin candidate ⇔ image ∈ {page, platform} and date ∈ {platform_id, structured}.
4. **Rounds, parallel inside.** Round = search every new copy on every engine at once → verify all candidate pages at once → collect new copies. Stop when no new copy or the budget is spent.
5. **LLM for language only.** Extract names/place/event from titles and captions; write queries. Never choose engines, never decide origins.
6. **Budgets are code.** Time 120 s image / 180 s video; credits 12 / 20; page fetches 60 / 90. The report shows what was spent and what was skipped.
7. **Benchmark before merge.** `python scripts/bench_origin.py` must not regress.

---

## 4. Architecture (new package `origin/`, ~900 lines total)

```
origin/
  copies.py      Copy set: bytes, public URL, pHash, source (upload|small|page|platform). Dedupe pHash ≤ 4.
  engines.py     Adapters returning EngineAnswer{status, candidates, credits}: lens_exact, lens_visual,
                 yandex, tineye_web, vision_web (bytes), google_text, youtube. Credit meter.
  verify.py      For one page: fetch (platform-aware) → candidate images (og/img/platform media) →
                 hash + geometry → ImageEvidence{level, matched_url, size, inliers}. Reuses
                 geometric_verify.py, tweet.py, date_evidence.platform_fetch_date.
  dates.py       Thin wrapper over date_evidence → DateEvidence{level, when, sources}.
  identify.py    names/place/event from Lens titles + related_content + verified captions
                 (DeepSeek, one call) → 2–3 queries (ar + en, each with one distinctive detail).
  investigate.py Orchestrator: rounds, budgets, eligibility rule, timeline, video scenes.
  report.py      Payload for the UI (see §7).
scripts/bench_origin.py   Runs benchmark.yaml, prints hit/miss table, exits non-zero on regression.
```

Kept as-is: `services/geometric_verify.py`, `services/date_evidence.py`,
`providers/tweet.py`, `providers/serpapi.py` (+ `SerpApiNoResults`),
`providers/yandex.py`, `providers/tineye.py`, `providers/browser_search.py`
(TinEye only), `providers/wayback.py`, `providers/youtube.py`, `providers/xai.py`,
`providers/deepseek.py`, `services/keyframes.py`, `services/vector_index.py`,
`services/screenshot_crop.py`, storage/media routes, `tasks/queue.py` + SSE.

Deleted once the benchmark gate passes: `services/origin_engine.py`,
`services/origin_agent.py`, the Zenserp direct-search path in `tasks/jobs.py`,
forensics/AI hooks inside the origin flow (the AI tab keeps its own).

### Data model

```
Copy       {id, bytes?, url, phash, width, height, source, found_on: page_url|None}
Candidate  {url, engine, engine_thumb, copy_id, rank}
Sighting   {url, domain, platform, title, caption,
            image: {level: page|platform|engine_claim|none, matched_url, inliers, phash},
            date:  {level: platform_id|structured|weak|none, when, sources[], upper_bound?},
            copy_id, frame_ids[]}
Report     §7
```

---

## 5. The algorithm (image)

```
0. Prepare (≤ 5 s, 0 credits)
   copies = {upload}; if upload is a post screenshot → crop the photo (existing detector) and make it copy #1
   copies += small (512 px re-encoded)           # the copy Google accepts when it refuses the file
   host copies on R2 public (+ ImgBB mirror)
   own-index lookup → prior sightings

1. Round 1 (parallel, ~25 s, 4–5 credits)
   lens_exact(en) + lens_exact(ar) + lens_visual on copy #1   (if "refused": same three on the small copy)
   yandex on copy #1 ; tineye_web on copy #1 ; vision_web(bytes) if configured
   → candidates (deduped by canonical URL). Rank: exact > tineye-dated > social > visual.

2. Verify (parallel, ≤ 40 pages, ~30 s, 0 credits)
   per page: platform media first (X syndication, IG media, FB crawler, TG embed, YouTube storyboard),
   then og/img images; hash then geometry → image evidence; dates → date evidence.
   Every page-level or platform-level matched image with min side ≥ 400 px becomes a NEW COPY.

3. Round 2 (parallel, ~25 s, ≤ 4 credits)
   for the 2 largest new copies not yet searched: lens_exact(en) (+ ar for the first) ; yandex on the first
   → verify new candidates as in 2. Repeat once more only if a new copy appeared AND budget remains.

4. Identify + text (parallel with round 2, 1 LLM call, ≤ 3 credits)
   text pool = Lens visual titles + related_content + captions of page/platform-verified sightings
   DeepSeek: {people[], place, event, distinctive_detail, queries_ar[], queries_en[]}
   google_text for up to 3 queries → verify social posts / articles among results.
   Optional (names known, budget left): one Grok X-search question with the names.

5. Decide (0 s)
   candidates = sightings with image ∈ {page, platform} and date ∈ {platform_id, structured}
   origin = earliest by day, ties by date level then time
   first_seen_exact = earliest candidate whose matched copy is hash-identical to the upload
   version_note when the upload is a variant of the origin's image
   timeline = all sightings sorted, each carrying its evidence levels (the UI shows the level)

6. Persist: Search + SearchResult rows, own-index entries for verified copies, archive of the origin URL.
```

Budget guard: the orchestrator checks time and credits before every round; a
skipped step is recorded in `report.skipped` with its reason.

## 6. Video

Frames: existing keyframe selector (≤ 8, always frame 0). Each frame is a copy set
of its own. Round 1 runs lens_exact(en) per frame (8 credits) + lens_visual and
yandex on frame 0 only; verification accepts a page if ANY frame matches
(min hash / geometry over frames); a sighting keeps `frame_ids`. Scenes = frames
whose sightings form separate clusters; the report shows an origin per scene
and the earliest overall. Consensus rule (many same-scene sightings within days
→ "probable") is kept but labeled as such. Budget 180 s / 20 credits.

## 7. Report (what the UI gets)

```
origin            Sighting | null            # first confirmed, with evidence levels
first_seen_exact  Sighting | null            # earliest hash-identical copy (when different)
version_note      str | null                 # "the upload is a modified copy of …"
identity          {people[], place_ar, event_ar}   # from identify.py, marked "استنتاج"
timeline          Sighting[]                 # every sighting, evidence levels included
leads             Sighting[]                 # unconfirmed: engine_claim / weak dates
copies            [{url, size, found_on}]    # what we searched with
engines           {name: {status, count, credits}}   # incl. refused / skipped
budget            {seconds, credits, pages}
scenes            (video) [{frame_ids, origin}]
```

UI: keep `components/OriginReport.jsx` (palette already right). Changes: the
first-seen card shows the evidence pills (صفحة / منصة / محرك فقط · معرّف المنشور /
بيانات منظمة / ضعيف), a "نسخ بحثنا بها" strip, "محركات لم تقبل الصورة" line, and the
AI banner is removed from this feature.

## 8. Tests and benchmark

- Unit: engines (mocked answers incl. refused), verify (synthetic textured images: crop, restored, look-alike, engine-claim vs page), dates (existing), identify (fixture texts), investigate (fake engines: rounds, budgets, eligibility).
- `benchmark.yaml`: `{file, expected_origin_url, expected_date, notes}` per case. Seed: Maersk Frankfurt (ICG X 2024-07-19), the restored singers photo (X 2015-02-25, "reachable" flag), Abha airport clip (Telegram 2026-02-09), Instagram screenshot case (Facebook 2024-12-06). **Faisal adds 6+ more with known answers.**
- `scripts/bench_origin.py`: runs each case once, prints `case | origin found | correct? | date | seconds | credits`, exits 1 if any previously-passing case fails.

## 9. Phases and gates (≈ 3 working days)

| Phase | Work | Gate |
|---|---|---|
| 0 (½ d) | Freeze v1. `benchmark.yaml` + runner against v1 to record the baseline. Credit meter. Decide Vision credentials. | baseline table committed |
| 1 (1 d) | `origin/` copies, engines, verify, dates, investigate (rounds 0–3, 5, 6), report; wire `/api/direct-search` image mode to v2 behind `ORIGIN_V2=true`. | unit tests green; bench ≥ baseline on images; ≤ 12 credits/case; ≤ 120 s |
| 2 (½ d) | identify.py + text round (4); Grok optional. | bench: restored-photo case finds a page-verified origin every run; identity block correct on 3 cases |
| 3 (½ d) | video: frames → per-frame copies → scenes; VideoAnalysis tab on v2. | bench video cases ≥ baseline; ≤ 20 credits |
| 4 (½ d) | UI evidence pills + copies strip; delete v1 files; update CLAUDE.md and .env.example; README section for the benchmark. | full suite green; v1 removed; bench unchanged |

Rules while building: Git checkpoint per phase; never edit `.py` while a live
job runs; no push without Faisal's word.

## 10. Decisions needed from Faisal

1. **Google Vision credentials JSON** — yes/no. (Recommended yes: bytes upload, entities, ~$0.003 per image.)
2. **Benchmark images** — 6+ images/clips with known first source.
3. **Deletion** — v1 files are deleted at the end of phase 4, only after the gate passes. Confirm.
4. **Credits** — accept 12 credits per image investigation (≈ 80 investigations/month on the current plan), or upgrade SerpAPI.

# Reverse Image Search: Provider Validation & Upgrade Spec
**Why current results are unrelated, which engines to use instead, and how to prove it**
*Companion to VISUAL_VERIFICATION_ENGINE.md — July 23, 2026*

---

## 1. Diagnosis: the unrelated results are mostly self-inflicted

Before replacing any vendor, understand *why* today's output is noisy. Three of the four causes are in our code, not in SerpAPI/Zenserp themselves:

**Cause 1 — We harvest non-visual result buckets as if they were matches.**
`scrape_reverse_search()` (app.py ~311) collects links from `image_results`, `inline_images`, `visual_matches`, **and `organic_results`** and flattens them into one list. But for Google reverse image, `organic_results` are *keyword* results for Google's **guessed text description** of the image ("brown dog on beach") — they have no visual relationship to your picture at all. `inline_images` are "related images," also not matches. The same happens in the Zenserp path: `direct_search_api()` harvests the `organic` section into the timeline. **A large share of the "unrelated data" you've been seeing is these buckets.** No engine swap fixes this; the harvester must keep visual-match sections only.

**Cause 2 — We use the deprecated, weakest engine.**
`google_reverse_image` is SerpAPI's legacy engine (the old images.google.com upload flow). Google's actual visual search is **Lens**, and SerpAPI exposes it as `google_lens` with `type=exact_matches` (same picture) vs `type=visual_matches` (similar pictures) — the exact/similar split is precisely the distinction our product needs, and we're not using it. Zenserp's reverse-image endpoint wraps the same legacy flow, which is why both providers "usually bring unrelated data."

**Cause 3 — No verification layer.** (Solved by the Visual Verification Engine — every candidate visually confirmed on its page before display.)

**Cause 4 — Single-locale, single-shot queries.** One call, one locale, no crops/variants, no text pivot. Recall suffers most for Arabic-world content.

**Conclusion:** the right move is not "find one perfect API" — none exists; every engine has blind spots in its index. The right move is a **portfolio of the strongest engines, harvested correctly, feeding the verification funnel.** Maximum candidates in, only real ones out.

---

## 2. The 2026 Provider Landscape (validated)

| Provider | Status / verdict | Role in our stack |
|---|---|---|
| **SerpAPI `google_lens`** (`type=exact_matches` / `visual_matches`, `country`, `hl`, `auto_crop`) | Active; the modern Google visual search. Exact-matches type returns the same picture across the web with per-match source, title, image URLs. **Uses the SerpAPI key we already have.** | **Primary candidate generator.** Replaces `google_reverse_image` everywhere. |
| **Google Cloud Vision — Web Detection** | Active; returns `full_matching_images`, `partial_matching_images` (catches crops natively!), `pages_with_matching_images`, `web_entities`. ~1,000 units/month free, then ~$3.50/1k. **We already ship the credentials and never call it.** | **Secondary generator + free pre-verifier** (its full/partial split is already a visual-match judgment by Google). |
| **TinEye API** | Active; the only commercial engine with `sort=crawl_date&order=asc` — results ordered by **when TinEye first crawled the image**, oldest first. Pay-per-search bundles. | **The "first seen" specialist.** One call ≈ a machine answer to "earliest known appearance," used as independent corroboration of our own date pipeline. |
| **Yandex reverse image (via SerpAPI/SearchApi)** | Active via SERP providers (no official Yandex API). Historically the strongest engine for faces and for content that Google under-indexes; known OSINT staple. | **Recall booster**, especially for non-Western/regional content. Same SerpAPI account. |
| **Bing Visual Search API** | **Dead — Microsoft retired the entire Bing Search API family (Aug 2025).** No official replacement for visual search. | Remove from plans. Keep the manual bing.com deep-link button only. |
| **Zenserp** | Active but wraps legacy flows; overlaps SerpAPI at lower quality for reverse image. | **Demote to text-SERP only** (its `q` search for the text-pivot step), pending bake-off. Likely cut entirely. |
| **Copyseeker / Lenso.ai / PimEyes** | Niche AI engines. PimEyes = faces of private persons → serious ethical/legal exposure for a journalism tool; avoid. Copyseeker has an API tier; worth a later look, not core. | Watchlist only. |

### Recommended fan-out per investigation
```
google_lens exact_matches   (ar/SA locale)     ← highest-precision core
google_lens exact_matches   (en/US locale)     ← recall for global spread
google_lens visual_matches  (one locale)       ← finds edited/cropped variants
Vision Web Detection        (free)             ← full+partial matches, entities
TinEye sort=crawl_date asc                     ← earliest-appearance anchor
Yandex reverse image        (when faces/regional or low recall)
+ text searches from describe_and_queryize     ← the VLM pivot (often finds the
                                                  true first post when image
                                                  indexes fail)
```
Six to eight cheap calls, all through the `providers/` abstraction, all landing in the same funnel. Each engine's blind spot is covered by another's index.

---

## 3. About the "we'll get 0 results" worry

It's the right worry, and the design answers it three ways:

1. **The new generators emit pre-matched candidates.** Lens `exact_matches`, Vision `full/partial_matching_images`, and TinEye results are *already visual matches by construction* — engines did the matching in their index. Verification against these mostly *confirms and dates*; survival rates are high. It's the legacy engines' keyword-guess buckets that would have been slaughtered by the filter — because they never contained the image in the first place. So the fix isn't a looser filter; it's better candidates.
2. **Recall is engineered, not hoped for:** multi-engine × dual-locale fan-out, `auto_crop`/manual crops and flips, `partial_matching_images` for crops, the VLM text-search pivot, and Wayback lookups for dead pages. When one angle returns nothing, the agent tries another — that's the loop's whole job.
3. **When nothing survives, that is the finding.** For an investigation tool, "no verified appearance of this image anywhere we can search — possibly original, private-source, or AI-generated" (cross-linked with the AI-detection verdict!) is a *legitimate, valuable* result. Showing 20 unrelated links instead — what happens today — is what actually destroys user trust. The report should present the null result confidently, listing what was searched, in which locales, and what near-misses (visual_matches) exist.

---

## 4. The Bake-off: validate with data, not vibes (3–4 days)

Don't take any table's word for it — including this one. Build the harness once; it becomes a permanent regression tool.

**Benchmark set (build first, ~1 day):** 40 images where you *know* ground truth, spread across: Arabic news photos, global news photos, viral memes, social-media originals (Twitter/X, Instagram), AI-generated images that circulated, cropped/watermarked variants, and 5 "unfindable" controls (fresh personal photos that should return 0). Store as `tests/benchmark/manifest.json`: image path + known first URL + known first date + category.

**Harness (`scripts/bakeoff.py`):** for each image × each engine: collect candidates → run Tier-1 verification (pHash + embedding vs. the query) → record:

- `candidates` returned, `verified` count → **precision** = verified/candidates
- `found_origin` (known first URL in verified set) and `origin_rank`
- earliest verified date vs. known date → **date accuracy**
- latency + cost per call → **verified results per dollar** (the decision metric)
- for controls: false-positive count (should be 0)

**Decision rules after the run:** keep any engine that uniquely finds ≥ ~10% of origins (blind-spot coverage matters more than average precision); cut engines whose verified-per-dollar is dominated by another engine across every category; set each engine's default locale/type parameters from what actually won per category. Re-run the harness monthly and after any provider change — engines drift.

Expected outcome (to be confirmed by data): Lens exact_matches becomes the workhorse; Vision Web Detection is the best free supplement; TinEye earns its cost purely on first-seen anchoring; Yandex earns its place on regional/face categories; Zenserp survives only as a text-SERP provider, if at all.

---

## 5. Immediate quick wins (can ship this week, before the engine exists)

1. **Stop harvesting `organic_results`/`inline_images`/`organic` as matches** in `scrape_reverse_search()` and `direct_search_api()` — keep only visual-match sections. One-hour change, kills the worst noise in the current product.
2. **Switch `google_reverse_image` → `google_lens` (`type=exact_matches`, then a second call with `visual_matches`)** in reverse search and provenance. Same SerpAPI key, same cost class, far better structure.
3. **Wire up Vision Web Detection** (credentials already in the project) as a second source merged into the same response.
4. Label each result in the UI with its bucket: **exact match / similar image / page mention** — even before verification exists, honest labeling changes perceived quality dramatically.

These four items alone should visibly transform result relevance while the full Visual Verification Engine is being built.

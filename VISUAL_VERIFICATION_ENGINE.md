# The Visual Verification Engine
**Design spec: vision-powered agentic reverse search — the flagship feature**
*Extends Section 6 of PROJECT_IMPROVEMENT_PLAN.md — July 23, 2026*

---

## 1. The Core Insight (why current results are noisy)

Today's pipeline asks SerpAPI/Zenserp "where does this image appear?" and **trusts the answer blindly**. But reverse-search engines return three kinds of junk mixed with real hits:

1. Pages that are *visually similar* but a **different image** (same event, different photo).
2. Pages that **once contained** the image but no longer do, or only show it as a tiny related-content thumbnail.
3. Aggregators/scrapers that republish everything and bury the true origin.

No text-based filtering can fix this, because the ground truth is **visual**. The fix is a system where *nothing enters the timeline until the platform has actually looked at the candidate image and confirmed it is the same picture* — and the "looking" is done by two layers: fast deterministic vision math, and a vision-language model (VLM) acting as a reasoning tool for the agent. That verification step is what no competitor's cheap wrapper does, and it's what makes this the highlight of the product.

**The one-line pitch:** *Every result in a Tahaqqaq timeline has been visually verified by AI — we show you where the picture actually is, not where a search engine thinks it might be.*

---

## 2. Architecture: A Three-Tier Visual Funnel

Candidates flow through tiers ordered by cost. Each tier kills noise so the next (more expensive) tier only sees survivors.

```
  SerpAPI Lens ─┐
  Zenserp ──────┤   TIER 0            TIER 1                TIER 2              TIER 3
  Vision API ───┼─► URL dedup ──► Deterministic vision ──► VLM judgment ──► Date & origin
  TinEye ───────┤   domain rules     pHash + embeddings      (Claude/Grok       verification
  Wayback ──────┘   (free, µs)       (local, ms, ~free)       vision, $, only    (Wayback, VLM
                                                              for ambiguous/     page reading)
                                                              finalists)
      ~200 raw candidates    →    ~60 unique    →    ~25 confirmed    →    ~15 judged    →    timeline
```

### Tier 0 — Structural filtering (free)
Canonical-URL dedup, strip tracking params, drop known-junk domains (image proxies, CDN mirrors, stock-photo scrapers — a curated blocklist that grows via the admin panel), collapse same-domain duplicates to the earliest.

### Tier 1 — Deterministic visual matching (local, milliseconds, ~zero cost)
For each surviving candidate: fetch the page, extract every meaningful image (`og:image`, `<img>` above a size floor, JSON-LD `image`), download the top few, and compare against the query image with **two complementary signals**:

- **Perceptual hash (pHash + dHash, `imagehash` lib):** catches exact and near-exact duplicates (re-encodes, resizes, slight compression). Hamming distance ≤ 8 → same image, near certainty. Cost: microseconds.
- **Image embeddings (the real workhorse):** encode both images with a vision encoder and compare cosine similarity. Unlike pHash, embeddings survive **crops, watermarks, memes with added text, color grading, flips, screenshots-of-screenshots** — exactly the transformations viral images undergo.
  - Model choice: **DINOv2 (ViT-S/14 or B/14)** — self-supervised features, current best-in-class for "same instance" retrieval robustness; or **SigLIP/OpenCLIP ViT-B** if you also want text-image alignment from the same model. Both run on CPU in tens of ms per image; a $0 self-hosted service (small FastAPI sidecar or just in the Celery worker) handles thousands/day.
  - Similarity bands (tune on your benchmark set):
    - **≥ 0.90** → *same image* (possibly edited) → auto-confirm, tag `exact|variant`
    - **0.75–0.90** → *ambiguous* → escalate to Tier 2 VLM
    - **< 0.75** → *different image* → **reject** (this band is where most of today's "unrelated data" dies, silently and for free)

**Verification is per-page, not per-thumbnail:** we confirm the image on the *actual candidate page*, which is precisely the check SerpAPI/Zenserp never do.

### Tier 2 — The VLM as an agent tool (the idea you proposed)
A multimodal model (Claude vision via API, or Grok vision — the xAI key you already have supports image understanding) is exposed to the agent as a set of callable tools. It is used **surgically** — only on the ambiguous band and on finalists — so cost stays bounded (~10–25 VLM calls per investigation, not 200).

**Tool 1 — `visual_judge(query_image, candidate_image, page_context)`**
"Are these the same photograph? Answer: `same | cropped_variant | edited_variant | different_photo_same_scene | unrelated` + one-line reasoning + confidence." Resolves everything embeddings can't: same scene shot by two photographers, AI-upscaled variants, heavy meme edits. The `different_photo_same_scene` verdict is gold for journalists — it's a finding, not noise.

**Tool 2 — `describe_and_queryize(query_image)`**
The VLM describes the image: entities (people, landmarks, uniforms, logos), any visible text (OCR — signs, captions, timestamps burned into the frame), event guess, language/country hints. Output → **targeted text-search queries** in Arabic and English. This is the breakthrough for the "who posted first" question, because *the true first post is often findable by text search when reverse-image engines fail* (early posts get few backlinks, so image indexes rank them poorly — but "photo collapsed bridge Karachi March 2021" finds them). The agent runs these queries through Tier 0–1 like any other candidate source.

**Tool 3 — `read_post(page_screenshot | page_html, image_region)`**
For finalist candidates, the VLM reads the *page itself* (screenshot via headless Chromium, or extracted DOM text) and answers: Is the image the main content of this post, or a sidebar thumbnail? Who is the stated author/account? What does the visible post date say? Does the caption claim it's original or a repost ("via @…", "circulating on WhatsApp…")? This catches the classic failure where meta tags lie or a 2024 article embeds a 2019 photo — the *article* date isn't the *image* date, and the VLM can tell the difference from the caption ("photo from 2019 shows…").

**Tool 4 — `suggest_recrop(query_image, matches_so_far)`**
When results are thin, the VLM proposes the informative region ("search only the poster in the background", "crop out the meme text band") → agent re-runs reverse search on that crop. This iterative re-search-by-region is something no one-shot API pipeline can do.

### Tier 3 — Date & origin verification (mostly free)
For each visually-confirmed sighting: page-date extraction (your existing evidence-chain extractor) **cross-checked** against the Wayback CDX earliest capture and against what the VLM read on the page. A date only becomes *confirmed* with two independent sources; otherwise it's *probable*. The earliest confirmed sighting + the VLM's `read_post` author extraction = the **"first posted by X on Y at Z"** answer, with the evidence chain displayed to the user.

---

## 3. The Agent Loop Around the Funnel

```
1  INGEST     hash + embed query image; check internal index (§4) — if seen
              before, start from prior findings
2  DESCRIBE   describe_and_queryize → entities, OCR text, search queries
3  FAN-OUT    reverse engines (Lens, Vision WebDetection, TinEye, Zenserp)
              × locales {ar, en} + text searches from step 2
4  FUNNEL     Tier 0 → 1 → 2 as above; stream verify/reject events to UI
5  ASSESS     enough confirmed sightings with strong dates? If not:
              recrop / flip / date-bracket (time-bounded searches around the
              earliest candidate) and GOTO 3 — bounded by call/$ budget
6  ORIGIN     Tier 3 on the earliest cluster; read_post the top candidates
7  REPORT     first-seen card + verified timeline + spread clusters +
              LLM narrative (each claim cites its evidence)
```

Budget discipline: hard caps per investigation (e.g. ≤ 3 loop iterations, ≤ 25 VLM calls, ≤ N engine credits), tiered by user plan. Every tool call is a Celery task writing to `investigation_steps`, so the UI streams progress and crashes resume instead of re-spending.

---

## 4. The Compounding Moat: An Internal Provenance Index

Store the embedding + pHash of **every image the platform ever analyzes** (and every verified sighting thumbnail) in Postgres with **pgvector** — which runs on your existing Render Postgres, no new infrastructure.

- New upload → vector similarity lookup **before any external API call**. Viral images (the bulk of real verification traffic) get instant, cached, already-verified answers at zero marginal cost.
- Every investigation *improves the database*: sightings, dates, and source-reputation stats accumulate. Over time Tahaqqaq develops something none of the API vendors will give you — **your own provenance graph of the Arabic-language web**, the region where global engines are weakest and your users care most.
- This also powers a future "monitor this image" alert feature almost for free (new sighting embeds near a watched vector → notify).

This is the difference between *a product that calls APIs* and *a platform that owns data*. It's the moat.

---

## 5. Cost & Performance Envelope (per investigation, typical)

| Stage | Volume | Unit cost | Total |
|---|---|---|---|
| Engine fan-out (Lens ×2 locales, Vision, TinEye, text ×3) | 6–8 calls | $0.005–0.02 | ~$0.08 |
| Page fetches | ~60 | free | — |
| pHash + embeddings | ~150 images | ~free (local CPU) | — |
| VLM judge/describe/read | 10–25 calls, 1–2 images each | ~$0.003–0.01 | ~$0.10–0.25 |
| Wayback CDX | ~15 | free | — |
| Narrative synthesis | 1 call | ~$0.02–0.05 | ~$0.04 |
| **Total** | | | **≈ $0.20–0.40** |

Latency: 60–120 s end-to-end with parallel fan-out — acceptable because the UI streams the investigation live (users *watch it verify*, which builds more trust than an instant unexplained list). A cache hit from the internal index returns in ~2 s.

Compare: today's pipeline spends ~$0.05–0.10 to return unverified noise. For 3–4× the cost you return a defensible, evidence-cited answer — and the pgvector cache pushes the *average* cost per query well below today's, since repeats are free.

---

## 6. Build Order (slots into roadmap Phase 3, ~3 weeks)

**Week 1 — Deterministic vision core (immediately improves the existing product, even before any agent exists):**
`media_service`: pHash + DINOv2 embedding on upload · pgvector setup + `image_vectors` table · `fetch_and_verify(url)` tool with per-page visual confirmation · bolt Tier 0–1 filtering onto the *current* `/api/direct-search` and `/api/provenance` outputs → users see cleaner results that same week, before the agent ships.

**Week 2 — VLM tool belt:** `visual_judge`, `describe_and_queryize`, `read_post` (headless-Chromium screenshotter reused from your Playwright dependency), `suggest_recrop` · provider adapters for Claude vision and Grok vision behind one interface (bake-off on your benchmark set) · budget/metering plumbing.

**Week 3 — The loop + UI:** planner (deterministic state machine first; LLM planning only where it earns its keep) · iterate/recrop/date-bracket logic · SSE streaming Investigation page (activity feed left, results assembling right) · benchmark run + threshold tuning.

**Prerequisite from the main plan:** the 30–50 image ground-truth benchmark (images whose true first posting you know). It tunes the similarity bands, picks the winning VLM, and gives you the marketing number ("X% of origins correctly identified vs Y% for raw reverse search").

**Definition of "highlight-worthy" (exit criteria):** ≥ 90% of timeline entries visually confirmed on their pages · ≥ 70% of benchmark origins found with correct first-poster · zero unverified claims in the report (everything cited or labeled *probable/inconclusive*) · live investigation view shipped · repeat-image queries answered from the internal index in seconds.

---

## 7. Answers to Design Questions You'll Hit

**"Which VLM?"** Run both Claude (vision) and Grok (you already integrate xAI) through the same adapter on the benchmark; pick per-tool winners — `visual_judge` needs precision, `describe_and_queryize` needs Arabic-world knowledge, `read_post` needs OCR-in-context. They may not be the same model, and the adapter makes mixing free.

**"Self-host the encoder or use an API?"** Self-host DINOv2-S: it's ~80 MB, CPU-fast, and embedding volume (hundreds per investigation) would be expensive and slow over any API. This is the one piece of "AI infrastructure" worth owning — it's tiny.

**"Do we still need Zenserp/SerpAPI?"** Yes — as *candidate generators*. The funnel doesn't replace them; it makes their noise harmless and their recall valuable. But after the funnel exists, measure which engines' candidates actually survive verification (the `provider_calls`/`SearchResult` data shows this) and cut the engine with the worst survivor-rate-per-dollar.

**"What about video?"** Same funnel, keyed on scene-change keyframes instead of the whole file: embed 5–10 representative frames, investigate the 2–3 most distinctive ones, merge timelines. This lands almost free once the image path works, and video provenance is a near-empty competitive field.

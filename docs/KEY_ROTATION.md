# Key Rotation — Phase 0 (URGENT)

Every credential below was committed to this repository and **must be treated as
compromised** — deleting the files/values does not help because they remain in
git history. Rotate (revoke + reissue) each one, then set the new value only in
`.env` locally (gitignored) and in the Render dashboard (env vars with
`sync: false`).

Full secret values are intentionally NOT repeated in this document — only
enough of an identifier to recognize which key to revoke.

## 1. Sightengine (image AI-detection)

- **What leaked:** `api_user` `1797817014` and its `api_secret`
  (`A4Y8...TcG`, 32 chars), hardcoded in `app.py` (Sightengine detection
  function, formerly ~line 1517).
- **Where to rotate:** [Sightengine dashboard](https://dashboard.sightengine.com/)
  → **API credentials** → regenerate the API secret.
- **After rotating:** set `SIGHTENGINE_API_USER` and `SIGHTENGINE_API_SECRET`
  in `.env` and in Render (both already declared `sync: false` in
  `render.yaml`). The code now reads only these env vars.

## 2. Google Cloud service-account keys (×2)

Both files were keys for the **same service account**:
`mns788@testemail-460515.iam.gserviceaccount.com` (project `testemail-460515`).

- **What leaked:**
  - `google-credentials.json` — private key ID `831adaa4...550abe`
  - `nskl.json` — private key ID `d4fa3d89...ebfd25`
- **Where to rotate:** [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts)
  → project `testemail-460515` → service account `mns788@...` → **Keys** tab →
  delete BOTH key IDs above → **Add key → Create new key (JSON)**.
- **After rotating:** save the new JSON file outside the repo (or in the repo
  root — `.gitignore` now blocks `*credentials*.json`, `nskl.json`, and
  `*service-account*.json`) and point `GOOGLE_APPLICATION_CREDENTIALS` at its
  path. Never commit the file.

## 3. ImgBB (image hosting)

- **What leaked:** API key `8a01...58e6` (32 chars) committed as a plaintext
  `value:` in `render.yaml`.
- **Where to rotate:** [ImgBB API page](https://api.imgbb.com/) — delete the
  existing key and generate a new one (ImgBB has no granular key management;
  if the account offers no revoke option, create a fresh account key).
- **After rotating:** set `IMGBB_API_KEY` in `.env` and in the Render
  dashboard (`render.yaml` now declares it `sync: false`).
- **Note:** ImgBB is scheduled to be replaced by R2/S3 presigned URLs
  (Phase 0/1 of PROJECT_IMPROVEMENT_PLAN.md §3.4) — rotation is still required
  in the meantime.

## 4. Zenserp (SERP API)

- **What leaked:** API key `dc270410-...-fb3d50c822e4` (UUID format), printed
  verbatim in `README_MIGRATION.md`.
- **Where to rotate:** [Zenserp dashboard](https://app.zenserp.com/) →
  API key section → regenerate/reset the key (contact Zenserp support if the
  plan does not include self-service reset).
- **After rotating:** set `ZENSERP_API_KEY` in `.env` and in the Render
  dashboard.

## Checklist

- [ ] Sightengine secret regenerated; env vars set in `.env` + Render
- [ ] Google SA key `831adaa4...` deleted in IAM
- [ ] Google SA key `d4fa3d89...` deleted in IAM
- [ ] New Google SA key created; `GOOGLE_APPLICATION_CREDENTIALS` points to it
- [ ] ImgBB key regenerated; env var set in `.env` + Render
- [ ] Zenserp key regenerated; env var set in `.env` + Render
- [ ] Verify the app works end-to-end with the new keys
- [ ] (Recommended, later) purge old secrets from git history with
      `git filter-repo` before making the repo public or adding collaborators

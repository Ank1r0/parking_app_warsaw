# iva_park — delivery plan

Goal: a continuously growing parking-availability dataset collected without a
laptop, fully reproducible from this repo, demoable live in an interview.

## Phases

### Phase 0 — repo goes public
- Verify the git history never contained `secret.json` (gitignore predates the
  first commit, but check before publishing).
- Create the public GitHub repository, push the project.
- Add the Warsaw API token as an Actions secret (`WARSAW_UM_TOKEN`).

### Phase 1 — Terraform foundation
- GCS bucket (region within GCP Always Free: `us-central1` / `us-east1` / `us-west1`).
- Lifecycle rule: raw objects older than 365 days → delete (already compacted
  into silver by then).
- Service account for the collector + IAM binding to the existing
  GitHub↔GCP Workload Identity Federation.
- Terraform state: local first; migrate to a GCS backend as a later exercise.

### Phase 2 — the collector workflow
- Scheduled workflow, `cron: */15 * * * *`, plus `workflow_dispatch` for manual runs.
- Steps: checkout → auth via WIF → run poller → upload
  `raw/date=YYYY-MM-DD/HHMMSS.json.gz` to the bucket.
- After ~48 h: review run history for cron drift and gaps; confirm dedup on
  `source_ts` absorbs them.

### Phase 3 — weekly compaction + visibility
- Weekly workflow: read new raw files → rebuild/extend
  `silver/parking_dataset.parquet` → write dataset stats (rows, days covered,
  last snapshot) into README.
- The README commit doubles as repo activity so GitHub does not auto-disable
  the scheduled workflow after 60 days.

### Phase 4 — later / optional
- BigQuery external table over silver (BQ Always Free: 10 GB storage,
  1 TB query/month) → gold layer + SQL story.
- `dim_date` calendar table (Polish holidays via the `holidays` package,
  shopping events) + Warsaw event feeds as forecast features.
- Occupancy forecasting model; MongoDB Atlas M0 + small API as the app
  serving layer; Android client.

## Cost & limits (FinOps)

| Item | Free tier | Expected usage | Cost |
|---|---|---|---|
| GitHub Actions | unlimited minutes (public repo) | ~2,900 min/month | $0 |
| GCS storage | 5 GB Always Free, no expiry | 250 MB–1.6 GB/year | $0 |
| GCS Class A ops | free quota; verify current docs | ~3,000 writes/month | ~$0 (worst case cents) |
| Terraform | OSS, run locally | — | $0 |
| MongoDB Atlas M0 | 512 MB (app phase only) | deferred | $0 |

Volume math: one snapshot ≈ 45 KB raw / ~6 KB gzipped; 96 snapshots/day.

## Known limits & risks

1. **Cron drift** — GitHub Actions schedules fire 3–15 min late under load and
   occasionally skip. Accepted: dataset dedups on `source_ts`; irregular
   sampling handled downstream by resampling.
2. **60-day auto-disable** of scheduled workflows on inactive repos —
   mitigated by the weekly README-stats commit.
3. **Private-repo trap** — 2,000 free min/month would NOT cover 15-min polling;
   repo must stay public.
4. **Token exposure** — token lives only in Actions secrets; never in code,
   logs, or workflow files. `secret.example.json` documents the shape.
5. **Source coverage** — endpoint serves only 14 sensor-equipped municipal
   garages; no pagination (verified). Expansion = new adapters (P+R feed,
   other cities), same canonical schema.
6. **API availability** — single upstream; failed runs are just missing
   snapshots, next run self-heals. No retry infrastructure needed at this cadence.

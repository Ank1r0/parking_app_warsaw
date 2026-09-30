# Design decisions

Agreed design decisions for iva_park, with the reasoning behind each one.
Entries are final unless a later entry supersedes them. New entries are added as
each part of the design is settled.

| # | Decision | Date |
|---|---|---|
| D1 | [Two products, shipped in sequence](#d1--two-products-shipped-in-sequence) | 2026-09-30 |
| D2 | [Medallion architecture with one shared silver](#d2--medallion-architecture-with-one-shared-silver) | 2026-09-30 |
| D3 | [Change history for prices, capacity and contacts](#d3--change-history-for-prices-capacity-and-contacts) | 2026-09-30 |

---

## D1 — Two products, shipped in sequence

**Goal of the project:** predict how full each Warsaw car park will be in the near
future, and show it on a map.

**Decision.** The project ships as two products, one after the other:

| Phase | What | Notes |
|---|---|---|
| **1. Live app + collection** | a simple app showing the current state of each car park; the same pipeline gathers history for the model | small, snapshot-based |
| **2. Data & model** | silver/gold on the collected history, model training | the app stays unchanged during this phase |
| **3. App + forecast** | each car park shows free places **now** and **in 1–2 hours** | starts only once the model works with measured precision; the exact horizon is chosen from that precision |

**Why.** A snapshot app is far simpler than the data and modelling work, so it ships
first and is useful on its own. Running it also produces the history the model needs,
so no time is lost waiting for data.

**Consequences.**

1. **One fetch, shared.** The scheduled collector is the only component that calls the
   city API. Each run stores the raw snapshot and a small "latest state" file. The app
   reads only that file and never holds the API token, so the token cannot leak through
   a browser.
2. **Short forecasting horizon.** Predicting 1–2 hours ahead lets the model use the most
   recent readings as inputs, and predictions are refreshed after every new snapshot.
   Plan-ahead forecasting ("Saturday at 14:00") is out of scope for now and can be added
   later without redesign.
3. **Freshness is visible.** "Current" means the latest snapshot: up to ~15 minutes old
   plus the city's own refresh delay. The app shows when the data was last updated.
4. **Contact details are app-only.** They are not model inputs.

---

## D2 — Medallion architecture with one shared silver

**Decision.**

```
bronze ──► silver (one, shared) ──┬──► gold: app view    (current state, 14 rows)
                                  └──► gold: model table (history on a 15-min grid)
```

| Layer | Holds | Rules |
|---|---|---|
| **Bronze** | each API response **unchanged**, wrapped in technical metadata: `source` (e.g. `warsaw_um`), `endpoint`, `ingested_at` (UTC), `run_id` | no business enrichment; **kept indefinitely** |
| **Silver** | cleaned, typed data, split into one table per kind of information | **one** silver shared by every consumer; consumer-neutral |
| **Gold** | one output per product, shaped for its purpose | calendar enrichment and the star schema live here |

**Why bronze stays raw.** Bronze is the record of exactly what the source sent and
when. The metadata traces any ingestion problem back to the run that fetched it, and
`source` keeps the design open to additional data sources. Because bronze is complete,
silver and gold can always be rebuilt from it, so a silver design mistake never loses
data.

**Why one silver, not one per product.** Cleaning (types, English names, time zones,
removing duplicate readings) is done once. Two silvers would duplicate that logic, and
the copies would drift apart. The app would then say "van" while the model said
`samochód_dostawczy`, or the two would disagree about times after a clock change.
Information that only one product needs, such as contact details, is handled by
splitting silver into separate tables: each gold reads the tables it needs and skips
the rest.

**Why gold is per product.** The two products need different shapes, not just
different columns:

| Information | App gold | Model gold |
|---|---|---|
| Occupancy readings | latest reading | full history: the target, plus readings from the same slot yesterday and last week |
| Core details (name, location, category) | current | ID, category, levels |
| Capacity | current ("12 / 47 free") | value at each slot's time, the denominator for occupancy % |
| Prices | current | value at each slot's time |
| Opening hours | today's hours, "open now?" | "was it open in this slot?" |
| Vehicle size limits | current | not used |
| Contact details | current | not used |

**Why a star schema in gold.** The main reason is not saving space: Parquet already
compresses repeated values. It is that each attribute has one source of truth, change
history attaches to the entity it belongs to, and joins stay simple.

**Consequences.**

- Each silver step runs **once per snapshot**: new occupancy readings are appended
  (duplicates dropped), then each group of descriptive details is compared with its
  current version and any change is recorded.
- The app's gold refreshes after every snapshot; the model's gold refreshes on its own
  schedule (e.g. nightly). A failed model build never blocks the app.
- A new source (e.g. weather) means a new bronze source, a new silver table and a new
  join in the model's gold. The app is untouched.
- **Supersedes** the 365-day deletion rule for raw data in [`plan.md`](plan.md)
  (Phase 1). Raw data is small (~0.25–1.6 GB/year) and is the only complete history.
- Collection does not wait for silver: bronze stores the raw payload regardless of how
  silver is shaped.

---

## D3 — Change history for prices, capacity and contacts

Descriptive details change rarely but do change: a price rise, a renovation, a new
manager. Each kind of information gets the slowly changing dimension (SCD) type that
fits the product that uses it.

**Decision.**

| Information | SCD type | Stored as |
|---|---|---|
| **Prices** | **Type 2**: every version kept, with `valid_from` / `valid_to` / `is_current` | its own table, one row per car park × vehicle type × stay length, versioned per price row, plus a "current" view for the app |
| **Capacity** | **Type 2** | its own table |
| **Contact details / manager** | **Type 1**: overwritten, current value only | its own table |

The remaining details (opening hours, vehicle size limits, core details) and the
car-park identity rule are decided separately.

**Why Type 2 for prices and capacity.** The model learns from history, so every past
reading must see the price and capacity **valid at that moment**. If prices rise in
January, December's readings must keep December's prices. With overwrite (Type 1),
all history would show today's prices and the model would learn from wrong data.
Capacity is the denominator of occupancy %, so a renovation must not rewrite the past.
Both tables are built as Type 2 from day one, even though phase 1 only reads current
values, so history is recorded from the start.

**Why not Type 4 for prices.** Type 4 means either a *mini-dimension* for attributes
that change **often** (the opposite of prices, which change about yearly), or a
*current table plus a history table*. The second matches our two consumers, but
Type 2 with a "current" view serves both from one table. Two tables would have to be
written on every change and could disagree, and the speed benefit of a current-only
table is irrelevant at ~200 rows. The useful part of the Type 4 idea is kept: prices
live in their own table, so a price change does not create a new version of the
whole car park.

**Why Type 1 for contacts.** Contact details serve only the app, and the app shows the
current state. Keeping their history would add work without a consumer. This is
reversible: bronze keeps every snapshot, so contact history can be rebuilt later if
ever needed.

**Consequences.**

- Change detection handles prices that are **added or removed**, not only changed. A
  dropped price closes its row with no replacement.
- Price is expected to be a **weak** model input: it barely varies within a car park,
  and there are only 14 car parks. Type 2 still matters for correctness when a price
  does change.

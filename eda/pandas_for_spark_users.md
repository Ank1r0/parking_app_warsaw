# Pandas for Spark users — cheat sheet

Every example works on the workbench dataframe:

```python
df = pd.read_csv("../silver/parking_dataset.csv", parse_dates=["source_ts", "ingested_at"])
```

Big picture: Spark methods return a new DataFrame and so do pandas ones —
chain them the same way. The differences: pandas uses `[]` a lot, column
expressions are `df["col"]` instead of `F.col("col")`, and there is no lazy
execution — every line runs immediately.

---

## Select columns

```python
# Spark: df.select("name", "free_public")
df[["name", "free_public"]]

# one column (returns a Series — pandas' 1-D structure, no Spark equivalent)
df["free_public"]
```

## Filter rows (Spark: filter / where)

```python
# Spark: df.filter(F.col("free_public") > 50)
df[df["free_public"] > 50]

# multiple conditions — & | instead of and/or, each condition in ()
df[(df["free_public"] > 50) & (df["total_standard"] < 200)]

# Spark: F.col("name").isin(...)
df[df["name"].isin(["Parking przy ul. Hożej", "Parking przy ul. Bugaj"])]

# Spark: F.col("category").isNull()
df[df["category"].isna()]

# SQL-like alternative (handy, strings in backticks if names have spaces)
df.query("free_public > 50 and total_standard < 200")
```

## Sort (Spark: orderBy)

```python
# Spark: df.orderBy("free_public")
df.sort_values("free_public")

# Spark: df.orderBy(F.col("free_public").desc())
df.sort_values("free_public", ascending=False)

# Spark: df.orderBy(F.col("name"), F.col("source_ts").desc())
df.sort_values(["name", "source_ts"], ascending=[True, False])
```

## New / derived column (Spark: withColumn)

```python
# Spark: df.withColumn("occupancy_pct", 1 - F.col("free_public") / F.col("total_standard"))
df["occupancy_pct"] = 100 * (1 - df["free_public"] / df["total_standard"])

# chainable version (doesn't modify df, like Spark):
df.assign(occupancy_pct=lambda d: 100 * (1 - d["free_public"] / d["total_standard"]))

# Spark: F.when(cond, a).otherwise(b)
df["status"] = np.where(df["free_public"] == 0, "FULL", "available")
```

## Rename / drop (Spark: withColumnRenamed / drop)

```python
df.rename(columns={"free_public": "free"})
df.drop(columns=["manager_email", "manager_phone"])
```

## groupBy + aggregation

```python
# Spark: df.groupBy("name").agg(F.avg("free_public"))
df.groupby("name")["free_public"].mean()

# several aggs — Spark: .agg(F.avg(...), F.max(...), F.count(...))
df.groupby("name").agg(
    avg_free=("free_public", "mean"),
    max_free=("free_public", "max"),
    n_snapshots=("source_ts", "count"),
)

# group by several columns
df.groupby(["manager", "category"])["free_public"].sum()

# groupby turns keys into the index; add .reset_index() to get a flat
# DataFrame back (the shape Spark always gives you)
df.groupby("name")["free_public"].mean().reset_index()
```

## Distinct / duplicates

```python
df["name"].unique()                                  # Spark: .select().distinct()
df["name"].nunique()                                 # Spark: F.countDistinct
df.drop_duplicates(subset=["parking_id", "source_ts"])  # Spark: dropDuplicates([...])
```

## Join

```python
# Spark: a.join(b, on="parking_id", how="left")
a.merge(b, on="parking_id", how="left")     # how: left/right/inner/outer
```

## Window functions (Spark: Window.partitionBy().orderBy())

```python
# Spark: F.lag("free_public").over(Window.partitionBy("parking_id").orderBy("source_ts"))
df = df.sort_values(["parking_id", "source_ts"])          # orderBy first!
df["prev_free"] = df.groupby("parking_id")["free_public"].shift(1)
df["change"]    = df["free_public"] - df["prev_free"]

# row_number per group
df["rn"] = df.groupby("parking_id").cumcount() + 1

# rolling mean over last 4 rows per group
df["rolling_avg"] = (df.groupby("parking_id")["free_public"]
                       .transform(lambda s: s.rolling(4).mean()))
```

## Pivot (Spark: groupBy().pivot().agg())

```python
# rows = time, columns = parking, values = free places
df.pivot_table(index="source_ts", columns="name", values="free_public")
```

## Time series (no direct Spark equivalent — pandas' superpower)

```python
# downsample to 15-minute buckets per parking
(df.set_index("source_ts")
   .groupby("parking_id")["free_public"]
   .resample("15min").mean())

# datetime parts — Spark: F.hour("source_ts")
df["hour"] = df["source_ts"].dt.hour
df["weekday"] = df["source_ts"].dt.day_name()
```

## Nulls

```python
df["category"].fillna("unknown")     # Spark: fillna / na.fill
df.dropna(subset=["free_public"])    # Spark: na.drop
df.isna().sum()                      # null count per column — first EDA move
```

## Inspecting (Spark: show / printSchema / describe)

```python
df.head(10)          # df.show(10)
df.dtypes            # printSchema
df.info()            # schema + null counts + memory
df.describe()        # numeric summary stats
df.shape             # (rows, columns) — Spark: df.count(), len(df.columns)
df["name"].value_counts()   # frequency table — no one-liner in Spark
```

## numpy in one paragraph

You rarely call numpy directly — pandas wraps it. The two you'll actually use:
`np.where(cond, a, b)` (the `F.when().otherwise()` equivalent) and `np.nan`
(the null literal). Everything else (means, sums) — use the pandas methods.

---

**The three habits to unlearn from Spark:**
1. No `F.col()` — the column *is* `df["col"]`.
2. Assignment mutates: `df["x"] = ...` changes `df` in place (use `.assign()` to chain immutably).
3. Everything executes immediately — no `.collect()`, no actions vs transformations.

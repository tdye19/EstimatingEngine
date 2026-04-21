# Sprint DATA-1 Validation Runbook

End-to-end validation for the DATA-1 CityGate load. Runs against the deployed
Railway instance after `sprint-data-1-citygate-load` is merged and deployed.
Replace `$ADMIN_TOKEN` in every command with a live admin JWT obtained at
runtime — never paste real tokens into this file.

Railway base URL: `https://web-production-f87116.up.railway.app`

---

## 1. Prerequisites

- **Railway deployment carries the DATA-1 branch.** Verify the deploy status
  page shows the head commit from `sprint-data-1-citygate-load` (the DATA-1.V
  runbook commit or later).
- **Fresh admin JWT.** Obtain via login — the token expires in 24h, so redo
  this step if your session spans the reboundary:

  ```bash
  ADMIN_TOKEN=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"email":"<admin-email>","password":"<admin-password>"}' \
    https://web-production-f87116.up.railway.app/api/auth/login \
    | jq -r .access_token)
  ```

  Sanity-check: `echo "${ADMIN_TOKEN:0:20}"` should print ~20 chars of a JWT
  header. If empty, login failed — inspect the raw response without `jq`.
- **CityGate source file** locally at a known path, e.g.
  `~/Downloads/CityGate_Master_Productivity_Rates.xlsx`. This is the real
  customer file and is gitignored at
  `apex/backend/tests/fixtures/pb/*.xlsx` in the repo.
- `APEX_ENABLE_DEDUP_PREVIEW` may be set in the Railway environment for
  unrelated Sprint 18.3 HF-21 work. It does not affect DATA-1 endpoints and
  can be ignored for this runbook.

---

## 2. Baseline capture — pre-load state

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://web-production-f87116.up.railway.app/api/library/productivity-brain/diagnostic/sample \
  | jq .data.summary
```

### Expected shape

```json
{
  "total_projects": <int>,
  "total_line_items": <int>,
  "total_distinct_activities": <int>,
  "projects_with_csi_code_nonnull": <int>,
  "projects_with_csi_code_null": <int>
}
```

**Record these four counts in Section 8 before touching anything else.**
Per the DATA-1.0 schema-discovery report, Railway is believed to carry
1 project / 243 line items / 59 distinct activities at the time of
writing — but confirm live before proceeding.

---

## 3. Load CityGate

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@/path/to/CityGate_Master_Productivity_Rates.xlsx" \
  -F 'metadata_json={"region":"CCI Outstate","customer":"Consumers Energy","years":"2024-2025"}' \
  https://web-production-f87116.up.railway.app/api/library/productivity-brain/load-multi-project \
  | jq .
```

### Expected 200 response shape (happy path)

```json
{
  "success": true,
  "message": "Loaded",
  "data": {
    "projects_upserted_new": 4,
    "projects_upserted_existing": 0,
    "line_items_inserted": <int 180 - 200>,
    "line_items_updated": 0,
    "line_items_skipped_empty": 0,
    "pb_project_ids": [<int>, <int>, <int>, <int>],
    "metadata_applied": {"region": "CCI Outstate", "customer": "Consumers Energy", "years": "2024-2025"},
    "warnings": ["<per-activity WBS drift>", "...", "labor_cost_per_unit and material_cost_per_unit are per-activity averages..."]
  },
  "error": null
}
```

Local dry-run of the same file produced 184 line items split 54 / 43 / 44 / 43
across Flint / Bancroft / Hanover / Highland. Railway numbers should match
within rounding (they're read from the same file).

### Failure-shape reference

- **400 Bad Request** (wrong file type, malformed `metadata_json`, or parser
  doesn't recognise layout):
  ```json
  {"detail": "File format not recognised as multi-project rates"}
  ```
  (or `"Expected an .xlsx upload"` / `"Invalid metadata_json: ..."` / `"metadata_json must decode to a JSON object"`)

- **401 Unauthorized** (no token or token expired):
  ```json
  {"detail": "Not authenticated"}
  ```
  or
  ```json
  {"detail": "Invalid token"}
  ```

- **403 Forbidden** (token is valid but role ≠ `admin`):
  ```json
  {"detail": "Insufficient permissions"}
  ```

- **409 Conflict** (file already loaded — every expected PBProject already
  exists with the synthetic file_hash):
  ```json
  {
    "success": false,
    "message": "File already loaded",
    "error": "duplicate_file",
    "data": {
      "existing_project_ids": [<id1>, <id2>, <id3>, <id4>],
      "existing_project_names": ["CCI CityGate Flint", "CCI CityGate Bancroft", "CCI CityGate Hanover", "CCI CityGate Highland"]
    }
  }
  ```

**Record the four `pb_project_ids` from the 200 response — they feed Section 4.**

---

## 4. Post-load verification

### 4a. Global counts (should have grown)

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://web-production-f87116.up.railway.app/api/library/productivity-brain/diagnostic/sample \
  | jq .data.summary
```

**Pass criteria:**
- `total_projects` = baseline + 4
- `total_line_items` ≥ baseline + 180
- `total_distinct_activities` ≥ baseline (new activities may or may not be
  distinct from existing)
- `projects_with_csi_code_null` = baseline null partition + 4 (CityGate
  rows have `csi_code = NULL` — DATA-1.1 intentionally does not populate it)

### 4b. Per-project drill-in (run once per new project_id)

```bash
for PID in <id1> <id2> <id3> <id4>; do
  echo "=== project $PID ==="
  curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "https://web-production-f87116.up.railway.app/api/library/productivity-brain/diagnostic/sample?project_id=$PID&limit=5" \
    | jq '{name: (.data.projects[] | select(.id == ('$PID')) | .project_name), src: (.data.projects[] | select(.id == ('$PID')) | .source_project), count: (.data.projects[] | select(.id == ('$PID')) | .line_item_count), sample: .data.sample_line_items}'
done
```

**Pass criteria per project:**
- `project_name` ∈ { `CCI CityGate Flint`, `CCI CityGate Bancroft`,
  `CCI CityGate Hanover`, `CCI CityGate Highland` }
- `source_project` ∈ { `Flint`, `Bancroft`, `Hanover`, `Highland` }
  and matches the project_name suffix
- `line_item_count` ≥ 40 (parser emits a safety-net warning below this)
- At least 3 of the 4 projects have `line_item_count` ≥ 50. If any is
  substantially lower, cross-check Section 5.

---

## 5. Semantic spot-checks

Pull the rates for a canonical activity via the existing `/rates` endpoint —
simpler to spot-check than raw line-item IDs.

### 5a. Uniform-rate activity: `Field Layout Engineering/Survey`

Source file shows all four projects at `0.04 unit/MH` with unit `week`.

```bash
curl -s -G -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode "activity=Field Layout Engineering/Survey" \
  https://web-production-f87116.up.railway.app/api/library/productivity-brain/rates \
  | jq '.data[] | select(.unit == "week")'
```

**Pass:** `project_count ≥ 4`, `min_rate == max_rate == 0.04`, `spread == 0`,
`unit == "week"`. (If `project_count` shows higher than 4, legacy non-
CityGate rows are also matching — still a pass as long as min/max include
0.04 and `occurrences` ≥ 4.)

### 5b. Divergent-rate activity

Before running, open the source file and pick an activity row where at
least two of Flint/Bancroft/Hanover/Highland have different numeric values
(common under `015 — Site Concrete` — e.g. `Form Strip / Wood Forms`, or
select any row where the `Spread (Hi-Lo)` column is non-zero).

```bash
curl -s -G -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode "activity=<chosen activity exactly>" \
  https://web-production-f87116.up.railway.app/api/library/productivity-brain/rates \
  | jq .data
```

**Pass:** `min_rate` and `max_rate` bracket all four source-file column
values; the computed `avg_rate` is within rounding of the source column
arithmetic mean. (Do the arithmetic manually and record both in Section 8.)

### 5c. Empty-cell activity

Pick an activity where the source file shows one column as `—` / `N/A` /
blank. Examples from the local probe: `Pilaster Forms - Wood` (row 23),
`Strip Rect Column - Plywood` (row 30), `Broom Finish` (row 40).

```bash
for PID in <id1> <id2> <id3> <id4>; do
  echo "=== project $PID ==="
  curl -s -G -H "Authorization: Bearer $ADMIN_TOKEN" \
    --data-urlencode "project_id=$PID" \
    --data-urlencode "limit=50" \
    https://web-production-f87116.up.railway.app/api/library/productivity-brain/diagnostic/sample \
    | jq '.data.sample_line_items[] | select(.activity == "<chosen empty-cell activity>") | {id, project_id, activity, production_rate, source_project}'
done
```

**Pass:** the project whose cell was empty returns NO row for that activity
(jq output empty for that `PID`). The other three projects DO return a row
with a valid non-zero `production_rate`. An empty cell must not have been
coerced into `production_rate = 0`.

---

## 6. Re-run safety

Re-upload the exact same file. DATA-1.2's synthetic file-hash idempotency
must refuse it:

```bash
curl -sw "\nHTTP_STATUS:%{http_code}\n" -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@/path/to/CityGate_Master_Productivity_Rates.xlsx" \
  -F 'metadata_json={"region":"CCI Outstate","customer":"Consumers Energy","years":"2024-2025"}' \
  https://web-production-f87116.up.railway.app/api/library/productivity-brain/load-multi-project
```

**Pass:** final line shows `HTTP_STATUS:409`; body matches the 409 shape in
Section 3 with `existing_project_ids` equal to the four IDs recorded from
Section 3.

---

## 7. Agent 4 regression check (OPTIONAL)

Only run this if there is a project in Railway with an Agent 4 takeoff
that already executed pre-CityGate-load. The goal is to confirm that
adding CityGate data doesn't regress Agent 4's historical-match hit rate
for existing projects.

- Before the load (from Section 2's baseline artifacts), you should have
  captured the pre-load `/rates` counts implicitly. If not, skip this
  section — it's informational only.
- Re-run Agent 4 via the pipeline UI on the chosen project.
- Pull per-line-item match status from Agent 4's output (route TBD by
  estimator — typically `/api/projects/{id}/takeoff/matches`).
- Compare matched / unmatched line counts vs the pre-load run.

**Pass criteria:** matched count ≥ baseline. Unmatched count ≤ baseline.
If unmatched count grew, one of the new CityGate rows is overriding a
previously-correct match — investigate the specific mismatch before
locking DATA-1.

Skip this section if no such comparison project exists. It is not a gating
requirement.

---

## 8. Report template

Fill this table against real Railway responses and paste back into the
validation thread. Do NOT commit filled-in responses containing real
project IDs or line-item counts into this runbook file.

| Step | Field | Expected | Actual | Pass/Fail |
|---|---|---|---|---|
| 2 | baseline `total_projects` | (record value) | | — |
| 2 | baseline `total_line_items` | (record value) | | — |
| 2 | baseline `total_distinct_activities` | (record value) | | — |
| 3 | HTTP status | 200 | | |
| 3 | `projects_upserted_new` | 4 | | |
| 3 | `projects_upserted_existing` | 0 | | |
| 3 | `line_items_inserted` | 180–200 | | |
| 3 | `pb_project_ids` (Flint, Bancroft, Hanover, Highland) | 4 distinct ints | | |
| 4a | `total_projects` delta | +4 | | |
| 4a | `total_line_items` delta | ≥ +180 | | |
| 4b | Flint `project_name` | `CCI CityGate Flint` | | |
| 4b | Flint `source_project` | `Flint` | | |
| 4b | Flint `line_item_count` | ≥ 50 | | |
| 4b | Bancroft `line_item_count` | ≥ 40 | | |
| 4b | Hanover `line_item_count` | ≥ 40 | | |
| 4b | Highland `line_item_count` | ≥ 40 | | |
| 5a | `Field Layout Engineering/Survey` min==max==0.04, unit=week | yes | | |
| 5b | chosen divergent activity, per-project rates match source | yes | | |
| 5b | chosen activity name | | | — |
| 5c | chosen empty-cell activity, missing project has no row | yes | | |
| 5c | chosen activity name + missing project | | | — |
| 6 | re-upload HTTP status | 409 | | |
| 6 | 409 `existing_project_ids` match Section 3 IDs | yes | | |
| 7 | Agent 4 matched-count delta (if run) | ≥ 0 | | |

**Final verdict:** Sprint DATA-1 LOCKED / BLOCKERS: (list any failing rows).

Lock commit (only after every gating row passes):

```
chore: Sprint DATA-1 LOCKED — CityGate 4 projects loaded to PB
```

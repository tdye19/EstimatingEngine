# Apex Estimating Intelligence System
## Technical Architecture for a Decision System for Millions of Dollars

**Version:** 1.0  
**Date:** 2026-04-07

---

## 1. Final blunt take

This system is **not** a chatbot, a document parser, or a generic “AI estimator.”

It is a **decision system for millions of dollars**.

Its job is to take real construction scope, quantities, project context, historical estimating data, market and risk inputs, and produce a **reviewable first-pass bid recommendation** grounded in estimator logic.

The system must answer five questions clearly:

1. **What work is in scope?**
2. **What work is likely missing or ambiguous?**
3. **Given quantities, what is the rough complete estimate?**
4. **How should that estimate change based on this job type, delivery context, and risk?**
5. **Why should an estimator trust this recommendation?**

If the system cannot answer those five questions with traceable evidence, structured math, and clear confidence levels, it is not useful in real preconstruction.

---

## 2. Product definition

### Core mission

Convert scope documents and takeoff quantities into a **reviewable, traceable, first-pass estimate** with:
- missing scope flagged,
- pricing grounded in comparable historical jobs,
- direct and indirect costs separated,
- risk, escalation, and schedule effects made explicit,
- and estimator overrides captured for future learning.

### Product position

This is not “AI that reads blueprints.”

This is:

> **An estimator co-pilot trained on how your company actually prices and manages specific classes of work.**

### Primary users
- Estimators
- Senior estimators
- Preconstruction managers
- Self-perform group leaders
- VDC / innovation support staff
- Eventually project controls and operations teams

---

## 3. First-principles operating standards

The system must follow these standards:

### 3.1 Estimator workflow fidelity
The system must reflect how real estimators work:
- understand scope,
- identify implied work,
- structure cost,
- benchmark pricing,
- review risk,
- frame bid strategy.

### 3.2 Deterministic math before AI
AI should interpret messy text and map it to structured work items.
AI should **not** invent hidden pricing logic.
Final estimate math should be deterministic and auditable.

### 3.3 Traceability
Every recommendation must point back to one or more of:
- source spec section,
- drawing sheet / page,
- estimator-provided quantity,
- historical comparable jobs,
- rule/checklist logic,
- risk input,
- market adjustment input.

### 3.4 Context-aware benchmarking
A hospital is not a school.
A data center is not a warehouse.
Historical rates must be filtered by project context.

### 3.5 Explicit uncertainty
Risk, escalation, and incompleteness must be surfaced explicitly.
They must not be hidden inside arbitrary unit rates.

### 3.6 Closed learning loop
The system must retain:
- estimator overrides,
- bid outcomes,
- project actuals,
- and confidence outcomes,
to improve future recommendations.

---

## 4. Core business problem

Most estimating tools stop at one of two weak endpoints:
- quantity × unit cost worksheets, or
- AI summaries with no pricing trust.

This system must solve a harder problem:

> **Use project-specific scope and company-specific historical memory to produce a reliable first-pass estimating decision framework.**

The output is not a paragraph.
The output is not a magic number.

The output is a **reviewable bid structure**.

---

## 5. Core functional jobs

The system performs six functional jobs.

### 5.1 Scope understanding
Extract work items from:
- specs,
- drawings text,
- addenda,
- inclusions / exclusions,
- estimator notes,
- takeoff metadata.

### 5.2 Scope completeness review
Determine:
- what is explicitly covered,
- what is implied,
- what is usually required but absent,
- what is likely excluded,
- what must be reviewed.

### 5.3 First-pass pricing
Given quantities, produce:
- line-item estimate draft,
- benchmark-based rate recommendations,
- confidence level,
- missing quantity / missing data flags.

### 5.4 Commercial framing
Convert cost into bid structure:
- direct cost,
- indirect cost,
- general conditions,
- contingency,
- fee / overhead,
- alternates,
- clarifications,
- strategic posture.

### 5.5 Risk and market adjustment
Show how estimate changes based on:
- project risk,
- escalation,
- schedule pressure,
- constraints,
- delivery method,
- procurement strategy.

### 5.6 Continuous learning
Capture:
- estimator changes,
- field actuals,
- post-bid outcomes,
- comparable-job performance,
for future calibration.

---

## 6. System architecture overview

The clean architecture is **engine-based**, not agent-marketing-driven.

### Core engines

1. **Document Intake Engine**
2. **Scope Extraction Engine**
3. **Completeness & Gap Engine**
4. **Contextual Benchmarking Engine**
5. **Pricing Engine**
6. **Commercial Structuring Engine**
7. **Risk / Escalation / Schedule Engine**
8. **Estimate Assembly Engine**
9. **Feedback & Learning Engine**

### High-level flow

```text
Upload Package
  ↓
Document Intake + Classification
  ↓
Scope Extraction
  ↓
Completeness / Gap Review
  ↓
Project Context Classification
  ↓
Benchmark Retrieval
  ↓
Pricing Engine
  ↓
Commercial Structuring
  ↓
Risk / Escalation / Schedule Adjustments
  ↓
Estimate Assembly
  ↓
Estimator Review + Override Capture
  ↓
Export / Submission Package
  ↓
Bid Outcome + Actuals + Learning Feedback
```

---

## 7. Recommended technical stack

### Frontend
- **React**
- **TypeScript**
- **Vite**
- **Tailwind CSS**
- **TanStack Table** for line-item review tables
- **React Query** for data fetching / caching
- **Recharts** for distributions and risk visuals

### Backend
- **FastAPI**
- **Python 3.11+**
- **SQLAlchemy**
- **Alembic**
- **Pydantic**

### Data / storage
- **PostgreSQL** for production
- **Redis** for job queues / caching / progress state
- **S3-compatible object storage** for document files and exports

### Background jobs
- **Celery** or **RQ** for long-running document parsing and estimate runs

### Search / retrieval
- **PostgreSQL full-text + pgvector**
or
- dedicated vector store only if required later

### LLM usage
- LLM only for:
  - scope extraction,
  - text normalization,
  - mapping messy scope phrases to canonical work items,
  - optional draft explanations.
- Avoid LLM-driven pricing or risk math.

### OCR / parsing
- PDF text extraction first
- OCR only when required
- PyMuPDF / pdfplumber / python-docx / openpyxl / pandas

### Deployment
- Frontend: Vercel or similar
- Backend/API: Railway / Render / Fly / AWS ECS
- DB: managed PostgreSQL
- Storage: S3 / Cloudflare R2 / equivalent

### Why move off SQLite
SQLite is acceptable for dev.
It is not the right long-term choice for:
- concurrent estimate runs,
- persistent project history,
- auditability,
- queue-driven workflows,
- multi-user estimating.

---

## 8. Bounded contexts / modules

### 8.1 Intake module
Responsibilities:
- file upload
- document classification
- parse text
- identify file type
- store source references
- create project run

### 8.2 Scope module
Responsibilities:
- extract candidate work items
- normalize scope language
- identify inclusions / exclusions / qualifiers
- maintain source evidence

### 8.3 Completeness module
Responsibilities:
- compare against project-type templates
- flag likely missing items
- flag review items
- identify ambiguity and dependency items

### 8.4 Benchmarking module
Responsibilities:
- retrieve comparable historical jobs
- filter by project context
- compute distributions
- compute confidence

### 8.5 Pricing module
Responsibilities:
- combine quantities + benchmark rates + rule logic
- assign recommended rates
- produce line-item subtotals
- flag low-confidence items

### 8.6 Commercial module
Responsibilities:
- direct vs indirect cost structure
- GC/CM framing
- fee and overhead
- contingency structure
- alternates / VE / strategy flags

### 8.7 Risk module
Responsibilities:
- register risk items
- expected value logic
- escalation
- schedule pressure effects
- constraint multipliers

### 8.8 Review module
Responsibilities:
- estimator review UI
- manual add/delete line items
- override reason capture
- approval workflow

### 8.9 Learning module
Responsibilities:
- store overrides
- store won/lost outcomes
- store field actuals
- track recommendation accuracy
- tune confidence and future recommendations

---

## 9. Canonical domain model

The system should center on a few canonical business objects.

### 9.1 Project
Represents the estimate opportunity.

Key fields:
- id
- name
- client
- location
- bid_due_date
- project_type
- delivery_method
- contract_type
- region
- size_sf
- size_cy / relevant size metrics
- scope_types
- complexity_level
- schedule_pressure
- market_sector

### 9.2 EstimateRun
Represents one full analysis pass for a project.

Key fields:
- id
- project_id
- version_number
- run_status
- started_at
- completed_at
- created_by
- source_package_id
- context_snapshot
- total_direct_cost
- total_indirect_cost
- total_risk
- total_escalation
- total_fee
- final_bid_value

### 9.3 SourceDocument
Represents each uploaded document.

Key fields:
- id
- project_id
- filename
- file_type
- source_type
- extracted_text
- parse_status
- page_count
- metadata_json

### 9.4 SourceReference
Allows exact traceability.

Key fields:
- id
- source_document_id
- page_number
- section_label
- snippet_text
- bounding_box_json (optional)
- reference_type

### 9.5 ScopeItem
Canonical work item extracted from project scope.

Key fields:
- id
- estimate_run_id
- canonical_name
- division_code
- work_package
- activity_family
- scope_status
- inclusion_confidence
- description
- notes

Scope status enum:
- included_explicit
- included_implied
- likely_missing
- excluded
- review_required
- not_applicable

### 9.6 ScopeItemEvidence
Links scope items to source references.

Key fields:
- id
- scope_item_id
- source_reference_id
- evidence_type
- confidence

### 9.7 QuantityItem
Represents estimator-provided or parsed quantity.

Key fields:
- id
- estimate_run_id
- scope_item_id
- quantity_value
- unit
- source
- source_reference_id
- quantity_confidence
- missing_flag

### 9.8 ComparableProject
Represents historical projects used for benchmarking.

Key fields:
- id
- project_name
- project_type
- region
- market_sector
- size_sf
- contract_type
- delivery_method
- scope_types
- complexity_level
- start_date
- end_date
- data_quality_score

### 9.9 HistoricalRateObservation
Stores historical pricing / production observations.

Key fields:
- id
- comparable_project_id
- canonical_activity
- unit
- labor_rate
- material_rate
- equipment_rate
- subcontract_rate
- total_unit_cost
- production_rate
- source_system
- observation_date
- recency_weight
- quality_weight

### 9.10 BenchmarkResult
Stores computed benchmark distributions per estimate line.

Key fields:
- id
- estimate_run_id
- scope_item_id
- comparable_filter_json
- sample_size
- p10
- p25
- p50
- p75
- p90
- mean
- std_dev
- context_similarity_score
- benchmark_confidence

### 9.11 EstimateLine
Represents a reviewable estimate line item.

Key fields:
- id
- estimate_run_id
- scope_item_id
- quantity
- unit
- recommended_unit_cost
- recommended_total_cost
- estimator_unit_cost
- estimator_total_cost
- benchmark_result_id
- pricing_basis
- confidence_level
- line_status

### 9.12 CostBreakdown
Commercial rollup structure.

Key fields:
- id
- estimate_run_id
- bucket_type
- amount
- method
- notes

Bucket types:
- direct_labor
- direct_material
- direct_equipment
- subcontract
- general_conditions
- temporary_facilities
- supervision
- logistics
- permits
- testing
- contingency
- escalation
- overhead
- fee

### 9.13 RiskItem
Represents explicit estimate risk.

Key fields:
- id
- estimate_run_id
- name
- category
- probability
- impact_cost
- impact_time_days
- severity
- mitigation
- source
- linked_scope_item_id
- source_reference_id

### 9.14 ScheduleScenario
Represents schedule assumptions impacting cost.

Key fields:
- id
- estimate_run_id
- planned_duration_days
- aggressive_duration_days
- conservative_duration_days
- labor_loading_factor
- gc_duration_factor
- acceleration_cost
- schedule_risk_notes

### 9.15 EscalationInput
Represents market/economic assumptions.

Key fields:
- id
- estimate_run_id
- category
- base_index
- escalation_rate
- start_date
- procurement_date
- install_date
- escalation_amount

### 9.16 EstimatorOverride
Critical learning object.

Key fields:
- id
- estimate_run_id
- estimate_line_id
- original_value
- overridden_value
- override_type
- reason_code
- reason_text
- created_by
- created_at

### 9.17 BidOutcome
Stores post-bid result.

Key fields:
- id
- estimate_run_id
- outcome
- final_bid_submitted
- winning_bid_value
- delta_to_winner
- notes

### 9.18 FieldActual
Stores project actuals after execution.

Key fields:
- id
- comparable_project_id
- canonical_activity
- quantity
- unit
- actual_unit_cost
- actual_total_cost
- actual_production_rate
- variance_to_estimate
- cost_code
- source_system
- data_quality_score

---

## 10. Project context model

This is mandatory.

Historical pricing should never be retrieved without filtering by context.

### Required context fields
- project_type
- market_sector
- region
- size bucket
- contract type
- delivery method
- scope family
- complexity
- schedule pressure
- self-perform vs subcontract mix

### Example

```json
{
  "project_type": "data_center",
  "market_sector": "mission_critical",
  "region": "midwest",
  "size_sf": 250000,
  "contract_type": "self_perform",
  "delivery_method": "cmar",
  "scope_types": ["sitework", "concrete"],
  "complexity_level": "high",
  "schedule_pressure": "high"
}
```

### Why this matters
A rate from a school in low schedule pressure conditions is not a valid primary benchmark for a mission-critical data center.
Context filtering is the difference between “historical noise” and “decision-grade signal.”

---

## 11. Canonical estimating ontology

The system needs a controlled vocabulary for work items.

### Why
LLMs are inconsistent.
Estimating data is messy.
Historical cost codes are inconsistent across time.

### Solution
Maintain a canonical estimating ontology with:
- canonical activity names,
- aliases,
- division mappings,
- unit expectations,
- common dependencies,
- typical cost bucket mappings.

### Example entries
- Mobilization
- Layout / Survey
- Erosion Control
- Clearing and Grubbing
- Earthwork Excavation
- Undercut / Proof Roll
- Aggregate Base
- Formwork
- Rebar
- CIP Concrete Footings
- CIP Concrete Walls
- CIP Concrete Slabs
- Joint Sealants
- Dewatering
- Traffic Control
- Temporary Facilities
- Testing / Inspection
- Cleanup / Closeout

This ontology becomes the shared language between:
- scope extraction,
- takeoff mapping,
- historical data,
- field actuals,
- estimator review.

---

## 12. Engine design

### 12.1 Document Intake Engine

#### Inputs
- PDF
- DOCX
- XLSX
- CSV
- optional WinEst export
- optional takeoff export

#### Responsibilities
- classify file
- extract text
- preserve source metadata
- create page-level references
- detect parsing confidence
- route to downstream engines

#### Output
- structured document objects
- source reference objects
- project package object

#### Rules
- parsing must fail loudly
- no silent “best guesses” for broken files
- each parse should produce confidence + diagnostics

---

### 12.2 Scope Extraction Engine

#### Purpose
Turn messy source text into estimate-ready work items.

#### Inputs
- source documents
- project context
- ontology
- optional prior company templates

#### Responsibilities
- extract candidate scope items
- classify as included / implied / excluded / review
- identify qualifiers and exclusions
- tag to divisions / work packages
- attach evidence

#### AI role
Use LLM for:
- semantic extraction,
- normalization,
- alias resolution,
- implicit work inference.

#### Non-AI role
- validation against ontology,
- required field checks,
- deduplication,
- confidence scoring.

#### Output
- ScopeItems
- ScopeItemEvidence
- inclusion confidence

---

### 12.3 Completeness & Gap Engine

#### Purpose
Find what is missing or ambiguous.

#### Inputs
- scope items
- project type template
- ontology dependency rules

#### Responsibilities
- compare extracted work items to expected checklist
- flag likely omissions
- identify review-required dependencies
- mark not-applicable items
- produce completeness score

#### Example rule
If project includes below-grade concrete, then review:
- dewatering,
- excavation support,
- spoil handling,
- proof rolling,
- testing,
- pumping access.

#### Output
- completeness matrix
- gap flags
- dependency flags
- ambiguity register

---

### 12.4 Contextual Benchmarking Engine

#### Purpose
Retrieve historical context-aware pricing memory.

#### Inputs
- project context
- scope items
- historical observations

#### Responsibilities
- filter comparable projects
- score context similarity
- retrieve activity-level observations
- compute percentiles and dispersion
- return benchmark confidence

#### Minimum output per benchmark
- sample size
- p25
- p50
- p75
- p90
- mean
- standard deviation
- context similarity score
- recency weighting
- confidence label

#### Confidence factors
- sample size
- variance
- context similarity
- data quality
- recency

---

### 12.5 Pricing Engine

#### Purpose
Produce first-pass line-item pricing once quantities are available.

#### Inputs
- scope items
- quantity items
- benchmark results
- manual assemblies / rules
- company standard pricing rules

#### Responsibilities
- assign recommended unit cost
- split labor/material/equipment/sub if available
- calculate totals
- flag missing quantities
- flag low-confidence lines
- support allowances where exact pricing unavailable

#### Pricing hierarchy
1. Contextual historical benchmark
2. Company assembly / rule
3. Manual estimator input required
4. Temporary allowance

#### Output
- EstimateLines
- confidence flags
- missing-data flags
- pricing basis tags

---

### 12.6 Commercial Structuring Engine

#### Purpose
Turn cost into a GC/CM-framed bid structure.

#### Inputs
- estimate lines
- project context
- strategy profile

#### Responsibilities
- group direct costs
- add indirect costs
- calculate general conditions
- add overhead and fee
- structure alternates
- structure clarifications / exclusions

#### Output
- CostBreakdown
- bid summary structure
- alternates / VE options

---

### 12.7 Risk / Escalation / Schedule Engine

#### Purpose
Make uncertainty explicit.

#### Inputs
- scope gaps
- project context
- benchmark variance
- risk template
- market assumptions
- schedule assumptions

#### Responsibilities
- register project risks
- compute expected risk exposure
- recommend contingency
- compute escalation by category
- adjust GC and selected cost items for schedule effects

#### Deterministic formulas
Expected risk:
```text
Σ(probability × impact_cost)
```

Escalation:
```text
base_cost × escalation_rate × exposure_duration
```

Schedule pressure:
- GC duration cost scaling
- labor loading / overtime factors
- acceleration allowances

#### Output
- RiskItems
- EscalationInputs
- ScheduleScenario
- contingency recommendation
- schedule impact summary

---

### 12.8 Estimate Assembly Engine

#### Purpose
Create reviewable estimate deliverables.

#### Responsibilities
- aggregate all estimate data
- produce structured review table
- produce summary totals
- generate export package
- preserve explanation metadata

#### Outputs
- structured JSON
- XLSX export
- PDF export
- API responses for UI
- audit trail bundle

#### Critical requirement
No narrative-only output.
Every export must contain structure, evidence, and flags.

---

### 12.9 Feedback & Learning Engine

#### Purpose
Turn use into improving signal.

#### Inputs
- estimator overrides
- bid outcomes
- field actuals
- estimate variance

#### Responsibilities
- store overrides
- compare suggestions to accepted values
- compare estimates to actuals
- update confidence calibration
- improve context matching over time

#### Output
- override analytics
- benchmark quality scoring
- recommendation hit-rate metrics
- future weighting inputs

---

## 13. API design

### 13.1 Project APIs
- `POST /projects`
- `GET /projects/{id}`
- `PATCH /projects/{id}`

### 13.2 Document APIs
- `POST /projects/{id}/documents`
- `GET /projects/{id}/documents`
- `GET /documents/{id}`

### 13.3 Estimate run APIs
- `POST /projects/{id}/estimate-runs`
- `GET /estimate-runs/{id}`
- `GET /estimate-runs/{id}/status`

### 13.4 Scope APIs
- `GET /estimate-runs/{id}/scope-items`
- `PATCH /scope-items/{id}`
- `POST /estimate-runs/{id}/scope-items/manual`

### 13.5 Quantity APIs
- `POST /estimate-runs/{id}/quantities/import`
- `GET /estimate-runs/{id}/quantities`
- `PATCH /quantity-items/{id}`

### 13.6 Benchmark APIs
- `GET /estimate-runs/{id}/benchmarks`
- `GET /estimate-lines/{id}/benchmark-detail`

### 13.7 Estimate line APIs
- `GET /estimate-runs/{id}/estimate-lines`
- `PATCH /estimate-lines/{id}`
- `POST /estimate-lines/{id}/override`

### 13.8 Risk APIs
- `GET /estimate-runs/{id}/risk-items`
- `POST /estimate-runs/{id}/risk-items`
- `PATCH /risk-items/{id}`

### 13.9 Commercial APIs
- `GET /estimate-runs/{id}/cost-breakdown`
- `PATCH /estimate-runs/{id}/commercial-settings`

### 13.10 Outcome / learning APIs
- `POST /estimate-runs/{id}/bid-outcome`
- `POST /comparable-projects/{id}/field-actuals/import`
- `GET /analytics/recommendation-performance`

---

## 14. Core output contract

This is the central object the system should produce.

```json
{
  "project": {
    "project_type": "data_center",
    "region": "midwest",
    "delivery_method": "cmar",
    "scope_types": ["sitework", "concrete"]
  },
  "scope_items": [
    {
      "id": "scope_001",
      "canonical_name": "CIP Concrete Slab",
      "division_code": "03 30 00",
      "status": "included_explicit",
      "confidence": 0.94,
      "source_refs": ["spec p47", "sheet S3.1"]
    }
  ],
  "gap_flags": [
    {
      "item": "Dewatering",
      "reason": "Common dependency for below-grade concrete not explicitly priced",
      "severity": "review"
    }
  ],
  "estimate_lines": [
    {
      "scope_item_id": "scope_001",
      "quantity": 120.0,
      "unit": "CY",
      "recommended_unit_cost": 910.0,
      "recommended_total_cost": 109200.0,
      "pricing_basis": "contextual_benchmark_p50",
      "confidence_level": "medium",
      "benchmark": {
        "sample_size": 11,
        "p25": 860.0,
        "p50": 910.0,
        "p75": 945.0,
        "p90": 980.0
      }
    }
  ],
  "cost_breakdown": {
    "direct_cost": 4200000.0,
    "general_conditions": 650000.0,
    "contingency": 250000.0,
    "escalation": 120000.0,
    "overhead": 180000.0,
    "fee": 240000.0,
    "final_bid": 5640000.0
  },
  "risk_summary": {
    "expected_risk": 300000.0,
    "top_risks": [
      "Subsurface uncertainty",
      "Schedule compression",
      "Material volatility"
    ]
  }
}
```

---

## 15. UI architecture

The UI should not expose “agents.”
It should expose estimator workflow.

### Screen 1: Project setup
- project metadata
- project type
- region
- delivery method
- upload package

### Screen 2: Scope map
- extracted work items
- source evidence
- included / implied / excluded / review status
- manual add/edit/delete

### Screen 3: Completeness review
- missing items
- checklist coverage
- ambiguity flags
- dependency review items

### Screen 4: Draft estimate
Table columns:
- work item
- quantity
- unit
- recommended unit cost
- benchmark p50
- deviation from benchmark
- confidence
- pricing basis
- total
- source / notes
- override

### Screen 5: Commercial summary
- direct cost
- indirect cost
- GCs
- contingency
- escalation
- fee
- final bid
- alternates / VE options

### Screen 6: Risk & schedule
- risk register
- contingency recommendation
- escalation assumptions
- schedule scenarios

### Screen 7: Review history / learning
- overrides
- accepted changes
- bid outcome
- actuals upload
- future recommendation quality

---

## 16. Confidence model

Every estimate recommendation should carry confidence.

### Inputs to confidence
- sample size
- variance / dispersion
- project context similarity
- recency
- data quality
- extraction confidence
- quantity confidence

### Example simple formula

```text
confidence_score =
  w1 * normalized_sample_size +
  w2 * (1 - normalized_variance) +
  w3 * context_similarity +
  w4 * recency_score +
  w5 * data_quality_score
```

Then map:
- 0.80–1.00 → High
- 0.60–0.79 → Medium
- 0.40–0.59 → Low
- <0.40 → Very Low

### Rule
Low-confidence lines must be visually obvious and require estimator review.

---

## 17. Risk logic

Risk should be explicit and structured.

### Risk categories
- scope ambiguity
- design incompleteness
- procurement risk
- schedule compression
- market volatility
- labor availability
- site logistics
- subsurface uncertainty
- owner decision risk
- permit / utility coordination risk

### Risk modeling method
For MVP:
- probability × impact expected value
- severity classification
- contingency recommendation rules

### Future
- Monte Carlo
- scenario modeling
- risk correlation groups

---

## 18. Escalation logic

Escalation must be category-specific.

### Categories
- concrete
- steel
- rebar
- asphalt
- fuel
- electrical commodities
- specialty systems
- subcontractor market pressure

### Inputs
- base category cost
- assumed escalation rate
- exposure duration
- procurement date
- installation date

### Rule
Do not apply one global escalation factor blindly.
Escalation must follow procurement timing and category exposure.

---

## 19. Schedule logic

Schedule changes cost.

### What to model
- duration-driven GC changes
- labor loading
- overtime / shift premium
- acceleration equipment cost
- procurement compression risk
- inefficiency penalties

### MVP approach
Provide schedule scenarios:
- baseline
- aggressive
- conservative

For each scenario, calculate:
- GC cost delta
- labor loading factor
- acceleration allowances

---

## 20. Historical data strategy

This is a make-or-break area.

### Minimum viable historical data
For each historical project:
- project context
- major scope family
- cost codes or canonical activities
- quantities
- unit costs
- production rates if available
- final actuals if available
- data quality score

### Non-negotiable truth
A “brain” with one project is not a brain.
It is an anecdote.

### Priority
Load as many relevant historical jobs as possible, even if imperfect.
Messy historical data is far more valuable than empty elegance.

---

## 21. Learning loop design

The system improves only when it captures reality.

### Capture points
1. Estimator changes recommended unit cost
2. Estimator adds missing scope item
3. Estimator deletes irrelevant scope item
4. Bid won / lost result
5. Final cost / field actual uploaded
6. Variance analysis against estimate

### Core learning metrics
- recommendation acceptance rate
- average override delta
- estimate-to-actual variance by activity
- benchmark confidence calibration
- project-type-specific model quality

---

## 22. MVP scope

The MVP should be narrower than the grand vision.

### MVP objective
For one or two target self-perform scopes, produce a trustworthy first-pass estimate draft with completeness flags and context-aware rate benchmarks.

### MVP capabilities
- upload scope package
- extract canonical scope items
- compare against project-type checklist
- import quantities
- benchmark against comparable historical jobs
- produce estimate lines with confidence
- show direct cost + basic commercial structure
- capture overrides
- export XLSX

### Explicitly out of scope for MVP
- full autonomous blueprint quantity takeoff
- perfect OCR on all drawings
- Monte Carlo simulation
- live external commodity feeds
- full multi-trade enterprise integration
- autonomous bid submission strategy

---

## 23. Suggested implementation phases

### Phase 1 — Stabilize the center
Goal: make the system useful for one estimating decision.

Build:
- ProjectContext model
- canonical ontology
- historical comparable project schema
- benchmark engine with percentiles
- estimate line object
- estimator review screen

### Phase 2 — Scope-to-estimate workflow
Build:
- source references
- scope extraction improvements
- completeness checker
- manual scope item review
- quantity import and mapping

### Phase 3 — Commercial framing
Build:
- cost breakdown buckets
- basic contingency rules
- overhead and fee logic
- alternates / VE support

### Phase 4 — Risk, escalation, schedule
Build:
- risk register
- escalation model
- schedule scenario module
- structured bid summary

### Phase 5 — Learning loop
Build:
- estimator override capture
- bid outcome capture
- actuals import
- benchmark calibration

---

## 24. Engineering rules for implementation

1. **Do not let LLMs output final money without deterministic validation.**
2. **Every important object must be versioned.**
3. **Every recommendation must store explanation metadata.**
4. **Low-confidence outputs must force visible review.**
5. **No narrative-only outputs in core workflow.**
6. **Store source evidence at page/section level.**
7. **Separate extraction confidence from pricing confidence.**
8. **Separate direct cost from commercial strategy.**
9. **Do not bury contingencies in line-item rates.**
10. **Do not treat all project types as comparable.**

---

## 25. Immediate next build target

The first truly valuable slice is:

> **Scope package + quantities + project context → reviewable estimate lines with benchmark percentiles and confidence**

That one slice should work before anything else gets more complex.

### Concretely, build this first
- `ProjectContext`
- `ComparableProject`
- `HistoricalRateObservation`
- `BenchmarkResult`
- `EstimateLine`
- scope item evidence
- quantity import
- line-item review UI

If this slice works, the system starts becoming real.

---

## 26. Final implementation brief for coding assistant

Build Apex as a modular estimating decision system centered on structured estimator workflow, not chatbot behavior. The architecture must support scope extraction, completeness review, context-aware historical benchmarking, deterministic first-pass pricing, commercial cost structuring, explicit risk and escalation modeling, and a closed feedback loop from estimator overrides and field actuals. Use FastAPI, PostgreSQL, SQLAlchemy, Pydantic, React, and background jobs for long-running parsing. Treat project context as mandatory for historical comparisons. Maintain a canonical ontology of estimating work items. Preserve page-level source references for traceability. Expose reviewable estimate lines with percentiles, sample size, deviation from benchmark, and confidence level. Keep AI limited to interpretation and mapping tasks; keep pricing math auditable and deterministic. Optimize the MVP around one critical workflow: upload scope package and quantities, classify project context, extract work items, detect likely omissions, retrieve comparable historical rates, and produce a structured first-pass estimate draft an estimator can review and override.

---

## 27. Final blunt take

Do not build a flashy AI estimator.

Build a **decision system for millions of dollars**.

That means:
- structured,
- traceable,
- context-aware,
- benchmarked,
- commercially framed,
- risk-explicit,
- and grounded in how real estimators defend real bids.

If it cannot survive scrutiny from a senior estimator, preconstruction manager, or postmortem against actuals, it is not done.

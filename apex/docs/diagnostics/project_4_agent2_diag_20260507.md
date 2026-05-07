# Agent 2 / Agent 2B Diagnostic — Project 4
_Generated: 20260507T142113Z_

## Summary
- **Agent 2 inferred method:** `LLM_LIKELY`
- **Agent 2B inferred method:** `NO_OP_OR_GATE_REJECTED`
- **Spec sections extracted:** 19
- **Work categories extracted:** 0
- **Hypotheses generated:** 2

## Document Inventory

### Doc 4: 2025-11-21 KCCU CI 1 Specifications .pdf
- file_type: `pdf` | classification: `spec`
- page_count: 175 | raw_text_len: 387,352
- **Pattern counts:**
  - csi_section_headers: 0
  - bare_site_civil_6digit: 100
  - wc_headings: 2
  - work_category_no: 0
  - division_headers: 6
- **First 500 chars:**
```
KCCU 
 
2025-006 
New Headquarters 
 
11.21.2025 
Battle Creek, Michigan 
 
 
Table of Contents 
1
TABLE OF CONTENTS 
 
DIVISION 14 - CONVEYING EQUIPMENT
142100 
Electric Traction Elevators 
 
DIVISION 23 – HEATING, VENTILATING AND AIR-CONDITIONING (HVAC) 
231123 
Facility Natural-Gas Piping 
 
DIVISION 26 – ELECTRICAL 
260500 
General Electrical Requirements 
 
260519 
Low-Voltage Electrical Power Conductors and Cables 
 
260526 
Grounding and Bonding for Electrical Systems 
 
260533.13 
Condui
```

### Doc 5: 2021-11-21 KCCU CI 1 Drawings.pdf
- file_type: `pdf` | classification: `None`
- page_count: None | raw_text_len: 0
- **Pattern counts:**
  - csi_section_headers: 0
  - bare_site_civil_6digit: 0
  - wc_headings: 0
  - work_category_no: 0
  - division_headers: 0

## Agent 2 Runs (Spec Parser)

### Run 8
- Status: `failed` | Duration: 55.8 ms
- Started: 2026-05-06T18:44:39.250744 | Completed: 2026-05-06T18:44:39.306475
- **Error:** LLM provider 'ollama' failed health check — spec parsing requires LLM and cannot fall back to regex

### Run 16
- Status: `failed` | Duration: 62.1 ms
- Started: 2026-05-06T18:45:39.372160 | Completed: 2026-05-06T18:45:39.434200
- **Error:** LLM provider 'ollama' failed health check — spec parsing requires LLM and cannot fall back to regex

### Run 24
- Status: `completed` | Duration: 539133.8 ms
- Started: 2026-05-06T18:55:29.605527 | Completed: 2026-05-06T19:04:28.739324
- output_data:
```json
{
  "sections_parsed": 19,
  "documents_processed": 1,
  "parse_method": "llm",
  "results": [
    {
      "document_id": 4,
      "filename": "2025-11-21 KCCU CI 1 Specifications .pdf",
      "sections_found": 19,
      "parse_method": "llm",
      "status": "success"
    }
  ],
  "assembly_parameters": {
    "division_03_count": 0,
    "enriched": 0,
    "extraction_methods": {},
    "warnings": [],
    "duration_ms": 1.909292999698664
  },
  "dedup": {
    "inserted": 19,
    "replaced": 0,
    "skipped": 0,
    "errors": 0,
    "warnings": [
      "Upserted 0 existing sections; inserted 19 new; skipped 0 shorter duplicates"
    ]
  }
}
```

## Agent 2 Coverage Map (by Division)

- Division 14: 1 section(s)
- Division 23: 1 section(s)
- Division 26: 9 section(s)
- Division 31: 2 section(s) ← SITE/CIVIL
- Division 32: 3 section(s) ← SITE/CIVIL
- Division 33: 3 section(s) ← SITE/CIVIL

## Agent 2B Runs (Work Scope Parser)

### Run 9 (agent_number=25)
- Status: `skipped` | Duration: N/A
- Started: None | Completed: None

### Run 17 (agent_number=25)
- Status: `skipped` | Duration: N/A
- Started: None | Completed: None

### Run 25 (agent_number=25)
- Status: `completed` | Duration: 20.9 ms
- Started: 2026-05-06T19:04:28.742290 | Completed: 2026-05-06T19:04:28.763191
- output_data:
```json
{
  "project_id": 4,
  "documents_examined": 2,
  "documents_parsed": 0,
  "work_categories_created": 0,
  "work_categories_updated": 0,
  "parse_methods": {
    "llm": 0,
    "regex": 0,
    "regex_fallback": 0
  },
  "classification_summary": {
    "standalone_work_scope": 0,
    "embedded_work_scope": 0,
    "no_work_scope": 1
  },
  "warnings": [
    "Document 5 (2021-11-21 KCCU CI 1 Drawings.pdf) has empty raw_text; skipped."
  ],
  "duration_ms": 9.712054000374337
}
```

## Work Categories

_None found._

## Document Routing (Classification Gate)

- Doc 4 `2025-11-21 KCCU CI 1 Specifications .pdf`: cls=`spec` | → Agent2=True Agent2B=False | WC-XX count=2
- Doc 5 `2021-11-21 KCCU CI 1 Drawings.pdf`: cls=`None` | → Agent2=False Agent2B=False | WC-XX count=0

## Likely Root Causes

1. Agent 2 working as designed — Div 31/32/33 sections ARE present in DB. Handoff observation may reflect an earlier failed run (regex fallback), not the most recent LLM run. Verify against run timestamps.
2. Agent 2B ran as NO-OP (< 100 ms). No document in this project is classified as a work-scopes document. The KCCU Volume 2 Work Scopes PDF may not have been uploaded to this project yet.

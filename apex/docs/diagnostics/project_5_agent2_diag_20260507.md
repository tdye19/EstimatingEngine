# Agent 2 / Agent 2B Diagnostic — Project 5
_Generated: 20260507T152835Z_

## Summary
- **Agent 2 inferred method:** `LLM_LIKELY`
- **Agent 2B inferred method:** `LLM_LIKELY`
- **Spec sections extracted:** 19
- **Work categories extracted:** 8
- **Hypotheses generated:** 1

## Document Inventory

### Doc 6: 2025-11-21 KCCU CI 1 Specifications .pdf
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

### Doc 7: KCCU_Volume_2_Work_Scopes_12_1_2025.pdf
- file_type: `pdf` | classification: `work_scope`
- page_count: 28 | raw_text_len: 71,482
- **Pattern counts:**
  - csi_section_headers: 0
  - bare_site_civil_6digit: 9
  - wc_headings: 104
  - work_category_no: 16
  - division_headers: 0
- **First 500 chars:**
```
PROJECT MANUAL 
 
 
KCCU Headquarters  
 
Battle Creek, MI 
 
 
 
 
 
 
VOLUME 2 
 
Bid Package No. 1 
 
Monday, December 1, 2025 
 
 
Site, Civil, Elevator, Generator Procurement, Site Electrical & Temp. Electrical 
Service 
 
 
 
CONSTRUCTION MANAGER 
 
The Christman Company 
 
208 N. Capitol Avenue 
 
Lansing, Michigan, 48933-1357 
 
517-482-1488 
 
 
 
Architect
Mechanical & Electrical Engineer
Mayottegroup Architects 
6240 W. Mt. Hope 
Lansing, MI 48917
HED
123 West 5th Street
Royal Oak, MI
```

## Agent 2 Runs (Spec Parser)

### Run 32
- Status: `failed` | Duration: 25.3 ms
- Started: 2026-05-07T14:49:15.769154 | Completed: 2026-05-07T14:49:15.794442
- **Error:** LLM provider 'ollama' failed health check — spec parsing requires LLM and cannot fall back to regex

### Run 40
- Status: `failed` | Duration: 34.1 ms
- Started: 2026-05-07T14:49:45.683734 | Completed: 2026-05-07T14:49:45.717802
- **Error:** LLM provider 'ollama' failed health check — spec parsing requires LLM and cannot fall back to regex

### Run 48
- Status: `completed` | Duration: 665034.9 ms
- Started: 2026-05-07T14:52:12.673248 | Completed: 2026-05-07T15:03:17.708095
- output_data:
```json
{
  "sections_parsed": 19,
  "documents_processed": 1,
  "parse_method": "llm",
  "results": [
    {
      "document_id": 6,
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
    "duration_ms": 2.162644000236469
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

### Run 33 (agent_number=25)
- Status: `skipped` | Duration: N/A
- Started: None | Completed: None

### Run 41 (agent_number=25)
- Status: `skipped` | Duration: N/A
- Started: None | Completed: None

### Run 49 (agent_number=25)
- Status: `completed` | Duration: 247689.5 ms
- Started: 2026-05-07T15:03:17.711569 | Completed: 2026-05-07T15:07:25.401059
- output_data:
```json
{
  "project_id": 5,
  "documents_examined": 2,
  "documents_parsed": 1,
  "work_categories_created": 8,
  "work_categories_updated": 0,
  "parse_methods": {
    "llm": 8,
    "regex": 0,
    "regex_fallback": 0
  },
  "classification_summary": {
    "standalone_work_scope": 1,
    "embedded_work_scope": 0,
    "no_work_scope": 1
  },
  "warnings": [],
  "duration_ms": 247680.88657999987
}
```

## Work Categories

- WC-WC 00: General Requirements for All Subcontractors (incl=0, excl=0, alt=0, allow=0, unit_px=0, method=llm)
- WC-WC 02: Earthwork and Site Utilities (incl=6, excl=10, alt=1, allow=1, unit_px=1, method=llm)
- WC-WC 05: Site Concrete (incl=6, excl=7, alt=1, allow=1, unit_px=1, method=llm)
- WC-WC 06: Asphalt Paving (incl=7, excl=4, alt=0, allow=1, unit_px=1, method=llm)
- WC-WC 07: Fencing (incl=6, excl=1, alt=1, allow=1, unit_px=1, method=llm)
- WC-WC 28A: Generator Procurement, Exterior Site Electrical and Temp. Electric (incl=23, excl=6, alt=1, allow=1, unit_px=1, method=llm)
- WC-WC 30: Elevators (incl=10, excl=7, alt=0, allow=1, unit_px=1, method=llm)
- WC-WC 35: Materials Testing (incl=4, excl=1, alt=0, allow=1, unit_px=1, method=llm)

## Document Routing (Classification Gate)

- Doc 6 `2025-11-21 KCCU CI 1 Specifications .pdf`: cls=`spec` | → Agent2=True Agent2B=False | WC-XX count=2
- Doc 7 `KCCU_Volume_2_Work_Scopes_12_1_2025.pdf`: cls=`work_scope` | → Agent2=False Agent2B=True | WC-XX count=104

## Likely Root Causes

1. Agent 2 working as designed — Div 31/32/33 sections ARE present in DB. Handoff observation may reflect an earlier failed run (regex fallback), not the most recent LLM run. Verify against run timestamps.

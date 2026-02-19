"""Quantity takeoff tools for Agent 4."""

import re
import logging

logger = logging.getLogger("apex.tools.takeoff")

# Common construction units
UNIT_PATTERNS = {
    "SF": [r'\b(\d[\d,]*\.?\d*)\s*(?:sf|sq\.?\s*ft|square\s*feet?)\b'],
    "LF": [r'\b(\d[\d,]*\.?\d*)\s*(?:lf|lin\.?\s*ft|linear\s*feet?)\b'],
    "CY": [r'\b(\d[\d,]*\.?\d*)\s*(?:cy|cu\.?\s*yd|cubic\s*yards?)\b'],
    "EA": [r'\b(\d[\d,]*\.?\d*)\s*(?:ea|each|pcs?|pieces?|units?)\b'],
    "TON": [r'\b(\d[\d,]*\.?\d*)\s*(?:tons?)\b'],
    "GAL": [r'\b(\d[\d,]*\.?\d*)\s*(?:gal|gallons?)\b'],
    "SQ": [r'\b(\d[\d,]*\.?\d*)\s*(?:sq|squares?)\b'],
    "LB": [r'\b(\d[\d,]*\.?\d*)\s*(?:lbs?|pounds?)\b'],
    "CF": [r'\b(\d[\d,]*\.?\d*)\s*(?:cf|cu\.?\s*ft|cubic\s*feet?)\b'],
    "SY": [r'\b(\d[\d,]*\.?\d*)\s*(?:sy|sq\.?\s*yd|square\s*yards?)\b'],
    "HR": [r'\b(\d[\d,]*\.?\d*)\s*(?:hrs?|hours?)\b'],
}


def unit_extractor_tool(text: str) -> list[dict]:
    """Extract quantities with units from text.

    Returns list of {quantity, unit, raw_match, confidence}.
    """
    results = []
    text_lower = text.lower()

    for unit, patterns in UNIT_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text_lower):
                qty_str = match.group(1).replace(",", "")
                try:
                    qty = float(qty_str)
                    results.append({
                        "quantity": qty,
                        "unit": unit,
                        "raw_match": match.group(0),
                        "confidence": 0.85,
                    })
                except ValueError:
                    pass

    return results


def quantity_calculator_tool(line_item_text: str) -> dict:
    """Parse a line item description to extract quantity, unit, and confidence.

    Returns dict: {quantity, unit, confidence, description}
    """
    extractions = unit_extractor_tool(line_item_text)

    if extractions:
        # Pick the most likely extraction (first match with highest confidence)
        best = max(extractions, key=lambda x: x["confidence"])
        return {
            "quantity": best["quantity"],
            "unit": best["unit"],
            "confidence": best["confidence"],
            "description": line_item_text.strip()[:200],
        }

    # If no quantities found in text, provide a default estimate
    return {
        "quantity": 1.0,
        "unit": "LS",  # Lump Sum
        "confidence": 0.3,
        "description": line_item_text.strip()[:200],
    }


def drawing_reference_linker_tool(text: str) -> list[str]:
    """Extract drawing references from text.

    Looks for patterns like: Sheet A-101, DWG S-201, Detail 3/A-501
    """
    references = []

    patterns = [
        r'(?i)(?:sheet|dwg|drawing)\s+([A-Z]-?\d{3,})',
        r'(?i)(?:detail|section)\s+(\d+/[A-Z]-?\d{3,})',
        r'(?i)(?:see|refer\s+to)\s+([A-Z]\d{1,2}-\d{3,})',
        r'\b([ASMEPCL]-\d{3}(?:\.\d+)?)\b',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            ref = match.group(1).strip()
            if ref not in references:
                references.append(ref)

    return references

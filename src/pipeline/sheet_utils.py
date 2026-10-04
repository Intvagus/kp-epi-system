"""Shared helper for matching an expected Excel sheet name against whatever
sheets are actually present in a workbook.

Every real upload failure found in this project so far that wasn't a
genuine content problem traced back to the same root cause: a pipeline
module requiring an EXACT sheet-name string match, while the source system
exports the same sheet with small, harmless naming drift -- a trailing
space present or absent ("District " vs "District"), or different
capitalization. Detection (detect.py) already tolerated this by comparing
normalized (stripped, lowercased) names; the various `_read_sheet`-style
loaders didn't, until this was centralized here so every domain's loader
gets the same tolerance instead of four separate, easy-to-forget fixes.
"""


def resolve_sheet_name(available_sheets: list[str], expected_name: str) -> str | None:
    """Match `expected_name` against `available_sheets` by normalized
    (stripped, case-insensitive) comparison and return the REAL sheet name
    to read -- never guesses which sheet is meant beyond that normalization,
    and returns None (never raises) if nothing matches, so callers can
    produce their own domain-specific error message."""
    target = expected_name.strip().lower()
    for name in available_sheets:
        if name.strip().lower() == target:
            return name
    return None

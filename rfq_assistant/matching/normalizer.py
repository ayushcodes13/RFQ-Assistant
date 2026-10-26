"""Safe normalization for manufacturer names and part numbers."""

import re
from typing import Optional

# Standard aliases for known industrial automation and electrical component OEMs
OEM_ALIASES = {
    "schneider": "Schneider Electric",
    "schneider electric": "Schneider Electric",
    "square d": "Schneider Electric",
    "telemechanique": "Schneider Electric",
    "siemens": "Siemens",
    "siemens ag": "Siemens",
    "omron": "Omron",
    "omron electronics": "Omron",
    "eaton": "Eaton",
    "eaton cutler-hammer": "Eaton",
    "cutler-hammer": "Eaton",
    "phoenix contact": "Phoenix Contact",
    "phoenix": "Phoenix Contact",
    "acme industrial": "Acme Industrial",
    "acme": "Acme Industrial",
    "apex automation": "Apex Automation",
    "apex": "Apex Automation",
    "delta electronics": "Delta Electronics",
    "delta": "Delta Electronics",
    "allen-bradley": "Allen-Bradley",
    "allen bradley": "Allen-Bradley",
    "rockwell": "Allen-Bradley",
    "abb": "ABB",
}


def normalize_manufacturer(oem: Optional[str]) -> Optional[str]:
    """
    Normalizes manufacturer string using known alias mapping.
    Preserves original casing if unknown.
    """
    if not oem or not oem.strip():
        return None
    cleaned = oem.strip().lower()
    return OEM_ALIASES.get(cleaned, oem.strip())


def normalize_mpn(mpn: Optional[str]) -> Optional[str]:
    """
    Normalizes part numbers conservatively.
    Uppercases and strips outer whitespace.
    NEVER strips hyphens, dots, slashes, or trailing suffixes (e.g. -12 vs -12A).
    """
    if not mpn or not mpn.strip():
        return None
    cleaned = mpn.strip().upper()
    # Normalize multiple interior spaces into single space, keep punctuation
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned

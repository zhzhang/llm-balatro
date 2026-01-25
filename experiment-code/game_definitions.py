"""Centralized game data definitions loaded from JSON files.

This module loads all game reference data at import time and provides
convenient access to game definitions throughout the codebase.
"""

import json
from pathlib import Path
from typing import Dict, List


# Base path for all JSON files
_BASE_PATH = Path(__file__).parent

# Load all game definition files
with open(_BASE_PATH / "jokers.json", "r") as f:
    JOKERS: List[Dict] = json.load(f)

with open(_BASE_PATH / "vouchers.json", "r") as f:
    VOUCHERS: List[Dict] = json.load(f)

with open(_BASE_PATH / "tarot_cards.json", "r") as f:
    TAROT_CARDS: List[Dict] = json.load(f)

with open(_BASE_PATH / "spectral_cards.json", "r") as f:
    SPECTRAL_CARDS: List[Dict] = json.load(f)

with open(_BASE_PATH / "seals.json", "r") as f:
    SEALS: List[Dict] = json.load(f)

with open(_BASE_PATH / "enhancements.json", "r") as f:
    ENHANCEMENTS: List[Dict] = json.load(f)

with open(_BASE_PATH / "editions.json", "r") as f:
    EDITIONS: List[Dict] = json.load(f)

with open(_BASE_PATH / "boss_blinds.json", "r") as f:
    BOSS_BLINDS: List[Dict] = json.load(f)

# Convenient lookup dictionaries
VOUCHERS_BY_KEY: Dict[str, Dict] = {v["key"]: v for v in VOUCHERS}
VOUCHERS_BY_NAME: Dict[str, Dict] = {v["name"]: v for v in VOUCHERS}
BOSS_BLINDS_BY_NAME: Dict[str, Dict] = {b["name"]: b for b in BOSS_BLINDS}
JOKERS_BY_NAME: Dict[str, Dict] = {j["name"]: j for j in JOKERS}


def get_all_consumables() -> List[Dict]:
    """Get all consumables (tarot + spectral cards) with category labels."""
    consumables = []
    
    for tarot in TAROT_CARDS:
        consumables.append({**tarot, "category": "tarot"})
    
    for spectral in SPECTRAL_CARDS:
        consumables.append({**spectral, "category": "spectral"})
    
    return consumables

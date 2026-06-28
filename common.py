#!/usr/bin/env python3
"""
common.py — constantes et utilitaires partagés entre les scripts d'import.
"""

from pathlib import Path

GPX_DIR  = Path("gpx")
DATA_DIR = Path("data")
OUT_FILE = DATA_DIR / "rides.json"

SAISON_MAP = {
    1: "hiver", 2: "hiver",  3: "hiver",       4: "intersaison",
    5: "ete",   6: "ete",    7: "ete",          8: "ete",
    9: "ete",  10: "intersaison", 11: "hiver",  12: "hiver",
}

COLORS = {
    "gravel_fait":     "#e8914a",
    "route_fait":      "#5b9ef4",
    "gravel_a_tester": "#f4d45b",
    "route_a_tester":  "#f4d45b",
}


def ask_choice(question, options):
    """Pose une question à choix et retourne la valeur choisie."""
    print(f"\n  {question}")
    for i, (label, value) in enumerate(options, 1):
        print(f"    [{i}] {label}")
    while True:
        raw = input("  → ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][1]
        for label, value in options:
            if raw.lower() == value[0].lower() or raw.lower() == label[0].lower():
                return value
        print(f"  ⚠  Tape un chiffre entre 1 et {len(options)}")


def color_for(ride_type, statut):
    return COLORS.get(f"{ride_type}_{statut}", "#e8914a")

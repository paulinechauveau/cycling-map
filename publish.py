#!/usr/bin/env python3
"""
publish.py — Génère data/rides_public.json avec seulement les sorties marquées publiques.

Usage :
    python publish.py          ← mode interactif pour les rides sans décision
    python publish.py --silent ← utilise juste le champ "public" dans rides.json

Workflow :
    1. python publish.py          ← choisir quelles sorties publier
    2. git add data/rides_public.json gpx/<fichiers_publics>
    3. git commit -m "publish"
    4. git push
"""

import sys
import json
from pathlib import Path

from common import DATA_DIR, GPX_DIR

ALL_FILE = DATA_DIR / "rides.json"
PUB_FILE = DATA_DIR / "rides_public.json"

SILENT = "--silent" in sys.argv


def main():
    if not ALL_FILE.exists():
        print(f"❌  {ALL_FILE} introuvable.")
        return

    with open(ALL_FILE, encoding="utf-8") as f:
        rides = json.load(f)

    print("\n" + "═"*55)
    print("  🌍  Générateur rides_public.json")
    print("═"*55)

    changed = False
    for ride in rides:
        # Si déjà décidé, on n'interrompt pas en mode silencieux
        if "public" in ride and ride["public"] is not None:
            if SILENT:
                continue
        # Mode interactif : demande pour les rides sans décision
        if ride.get("public") is None or not SILENT:
            status = "✅ public" if ride.get("public", True) else "🔒 privé"
            print(f"\n  [{status}] {ride['name']}")
            print(f"     {ride['date']}  ·  {ride['distance_km']} km  ·  {ride['elevation_m']} m D+")
            raw = input("  Publier ? [O/n/entrée=conserver] ").strip().lower()
            if raw in ("n", "non"):
                ride["public"] = False
                changed = True
            elif raw in ("o", "oui", "y", "yes"):
                ride["public"] = True
                changed = True
            # entrée vide = conserver la valeur actuelle

    if changed:
        with open(ALL_FILE, "w", encoding="utf-8") as f:
            json.dump(rides, f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ rides.json mis à jour")

    public_rides = [r for r in rides if r.get("public", True) is not False]
    private_count = len(rides) - len(public_rides)

    with open(PUB_FILE, "w", encoding="utf-8") as f:
        json.dump(public_rides, f, ensure_ascii=False, indent=2)

    gpx_files = [r["gpx"] for r in public_rides if r.get("gpx")]

    print(f"\n{'═'*55}")
    print(f"  ✅ {PUB_FILE} généré")
    print(f"     {len(public_rides)} sortie(s) publique(s)  ·  {private_count} privée(s)")
    print(f"\n  Commandes pour publier :")
    print(f"  git add data/rides_public.json \\")
    for gpx in gpx_files:
        print(f"          {gpx} \\")
    print(f"  git commit -m \"publish\"")
    print(f"  git push")
    print("═"*55 + "\n")


if __name__ == "__main__":
    main()

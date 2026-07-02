#!/usr/bin/env python3
"""
publish.py — Prépare les fichiers publics pour le déploiement.

Ce script :
  1. Définit la visibilité par défaut : "à tester" = public, "fait" = privé
  2. Pose des questions pour les sorties sans décision explicite
  3. Découpe les traces GPX dans les zones de confidentialité (si privacy_zones.json existe)
  4. Génère data/rides_public.json et gpx_public/ (prêts à committer)

Usage :
    python publish.py          ← interactif pour les rides sans décision
    python publish.py --silent ← utilise les champs "public" existants sans demander

Workflow :
    1. Crée data/privacy_zones.json (voir data/privacy_zones.example.json)
    2. python publish.py
    3. git add data/rides_public.json gpx_public/
    4. git commit -m "publish" && git push
"""

import sys
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from common import DATA_DIR, GPX_DIR

ALL_FILE  = DATA_DIR / "rides.json"
PUB_FILE  = DATA_DIR / "rides_public.json"
ZONES_FILE = DATA_DIR / "privacy_zones.json"
GPX_PUB_DIR = Path("gpx_public")

SILENT = "--silent" in sys.argv
GPX_NS = "http://www.topografix.com/GPX/1/1"
ET.register_namespace("", GPX_NS)


# ─── ZONES DE CONFIDENTIALITÉ ─────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def is_in_zone(lat, lon, zones):
    return any(haversine_km(lat, lon, z["lat"], z["lon"]) <= z["radius_km"] for z in zones)

def clip_gpx(src, dst, zones):
    """Copie src vers dst en supprimant les points dans les zones de confidentialité."""
    if not zones:
        shutil.copy2(src, dst)
        return 0

    ns = {"gpx": GPX_NS}
    tree = ET.parse(src)
    root = tree.getroot()
    removed = 0

    for seg in root.findall(".//gpx:trkseg", ns):
        to_remove = []
        for pt in seg.findall("gpx:trkpt", ns):
            try:
                if is_in_zone(float(pt.attrib["lat"]), float(pt.attrib["lon"]), zones):
                    to_remove.append(pt)
                    removed += 1
            except (KeyError, ValueError):
                pass
        for pt in to_remove:
            seg.remove(pt)

    ET.indent(tree, space="  ")
    tree.write(dst, encoding="UTF-8", xml_declaration=True)
    return removed


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    if not ALL_FILE.exists():
        print(f"❌  {ALL_FILE} introuvable.")
        return

    with open(ALL_FILE, encoding="utf-8") as f:
        rides = json.load(f)

    # Charge les zones de confidentialité
    zones = []
    if ZONES_FILE.exists():
        with open(ZONES_FILE, encoding="utf-8") as f:
            zones = json.load(f)
        print(f"\n  🔒 {len(zones)} zone(s) de confidentialité chargée(s) :")
        for z in zones:
            print(f"     · {z['name']} — rayon {z['radius_km']} km")
    else:
        print(f"\n  ℹ  Pas de zones de confidentialité.")
        print(f"     (Crée data/privacy_zones.json depuis data/privacy_zones.example.json)")

    print("\n" + "═"*55)
    print("  🌍  Générateur rides_public.json")
    print("═"*55)

    changed = False
    for ride in rides:
        # Défaut : "à tester" = public, "fait" = privé
        if ride.get("public") is None:
            ride["public"] = (ride.get("statut") == "a_tester")
            changed = True

        # Mode interactif : affiche chaque ride et demande confirmation
        if not SILENT:
            status = "🌍 public" if ride.get("public") else "🔒 privé "
            print(f"\n  [{status}] {ride['name']}")
            print(f"     {ride['date']}  ·  {ride['distance_km']} km  ·  {ride['elevation_m']} m D+  ·  {ride['statut']}")
            raw = input("  Changer ? [o/n/entrée=conserver] ").strip().lower()
            if raw in ("o", "oui", "y", "yes"):
                ride["public"] = not ride["public"]
                changed = True
            elif raw in ("n", "non"):
                pass  # conserver

    if changed:
        with open(ALL_FILE, "w", encoding="utf-8") as f:
            json.dump(rides, f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ rides.json mis à jour")

    # Filtre les rides publiques
    public_rides = [r for r in rides if r.get("public", False)]
    private_count = len(rides) - len(public_rides)

    # Génère les GPX découpés dans gpx_public/
    GPX_PUB_DIR.mkdir(exist_ok=True)
    gpx_to_commit = []
    total_removed = 0

    for ride in public_rides:
        if not ride.get("gpx"):
            continue
        src = Path(ride["gpx"])
        if not src.exists():
            continue
        dst = GPX_PUB_DIR / src.name
        removed = clip_gpx(src, dst, zones)
        total_removed += removed
        # Met à jour le chemin dans rides_public.json
        ride = dict(ride)  # copie pour ne pas modifier l'original
        gpx_to_commit.append(str(dst))

    # Écrit rides_public.json avec les chemins gpx_public/
    public_rides_out = []
    for ride in public_rides:
        r = dict(ride)
        if r.get("gpx"):
            r["gpx"] = f"gpx_public/{Path(r['gpx']).name}"
        public_rides_out.append(r)

    with open(PUB_FILE, "w", encoding="utf-8") as f:
        json.dump(public_rides_out, f, ensure_ascii=False, indent=2)

    print(f"\n{'═'*55}")
    print(f"  ✅ Publication prête !")
    print(f"     {len(public_rides)} sortie(s) publique(s)  ·  {private_count} privée(s)")
    if zones and total_removed:
        print(f"     {total_removed} point(s) GPS supprimé(s) dans les zones de confidentialité")
    print(f"\n  Commandes pour publier :")
    print(f"  git add data/rides_public.json gpx_public/")
    print(f"  git commit -m \"publish\"")
    print(f"  git push")
    print("═"*55 + "\n")


if __name__ == "__main__":
    main()

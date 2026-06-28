#!/usr/bin/env python3
"""
generate_rides.py
-----------------
Scanne le dossier gpx/, extrait les métadonnées des fichiers GPX,
pose 2 questions par sortie (type + statut), et génère data/rides.json.

Usage :
    python generate_rides.py
"""

import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from common import GPX_DIR, DATA_DIR, OUT_FILE, SAISON_MAP, ask_choice, color_for

# ─── CONFIG ───────────────────────────────────────────────────────────────────
NS = {"gpx": "http://www.topografix.com/GPX/1/1"}

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def parse_gpx(path):
    tree = ET.parse(path)
    root = tree.getroot()

    # Cherche les points dans trkseg ou rte
    pts = root.findall(".//gpx:trkpt", NS) or root.findall(".//gpx:rtept", NS)
    if not pts:
        return None

    coords, eles, times = [], [], []
    for pt in pts:
        try:
            lat, lon = float(pt.attrib["lat"]), float(pt.attrib["lon"])
            coords.append((lat, lon))
        except (KeyError, ValueError):
            continue
        ele = pt.find("gpx:ele", NS)
        if ele is not None and ele.text:
            try: eles.append(float(ele.text))
            except ValueError: pass
        t = pt.find("gpx:time", NS)
        if t is not None and t.text:
            times.append(t.text.strip())

    if not coords:
        return None

    # Distance
    dist_km = sum(haversine(*coords[i], *coords[i+1]) for i in range(len(coords)-1))

    # Dénivelé positif
    dplus = 0
    if len(eles) > 1:
        for i in range(1, len(eles)):
            diff = eles[i] - eles[i-1]
            if diff > 0:
                dplus += diff

    # Date — depuis le temps GPS ou le nom du fichier
    date_str = None
    if times:
        try:
            dt = datetime.fromisoformat(times[0].replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    if not date_str:
        # Essaie de lire la date dans le nom du fichier (ex: 2024-03-15_fontainebleau.gpx)
        stem = path.stem
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                dt = datetime.strptime(stem[:len(fmt.replace("%Y","0000").replace("%m","00").replace("%d","00"))], fmt)
                date_str = dt.strftime("%Y-%m-%d")
                break
            except ValueError:
                pass
    if not date_str:
        date_str = datetime.today().strftime("%Y-%m-%d")

    # Nom depuis la balise <name> ou le nom de fichier
    name_el = root.find(".//gpx:trk/gpx:name", NS)
    if name_el is None:
        name_el = root.find(".//gpx:name", NS)
    gpx_name = name_el.text.strip() if name_el is not None and name_el.text else path.stem.replace("_", " ").replace("-", " ").title()

    return {
        "name":        gpx_name,
        "date":        date_str,
        "distance_km": round(dist_km, 1),
        "elevation_m": int(round(dplus)),
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(exist_ok=True)

    gpx_files = sorted(GPX_DIR.glob("*.gpx"))
    if not gpx_files:
        print(f"❌  Aucun fichier .gpx trouvé dans ./{GPX_DIR}/")
        return

    # Charge les rides existants pour ne pas réécraser
    existing = {}
    if OUT_FILE.exists():
        try:
            with open(OUT_FILE, encoding="utf-8") as f:
                for r in json.load(f):
                    existing[r["gpx"]] = r
        except Exception:
            pass

    rides = []
    new_count = 0

    print("\n" + "═"*55)
    print("  🚵  Générateur de rides.json")
    print("═"*55)
    print(f"  {len(gpx_files)} fichier(s) GPX trouvé(s) dans ./{GPX_DIR}/\n")

    for i, gpx_path in enumerate(gpx_files, 1):
        gpx_key = f"gpx/{gpx_path.name}"

        # Déjà existant ?
        if gpx_key in existing:
            print(f"  ✓  [{i}/{len(gpx_files)}] {gpx_path.name}  (déjà dans rides.json — conservé)")
            rides.append(existing[gpx_key])
            continue

        print(f"\n{'─'*55}")
        print(f"  📍 [{i}/{len(gpx_files)}] {gpx_path.name}")

        meta = parse_gpx(gpx_path)
        if meta is None:
            print("  ⚠  Impossible de lire ce fichier GPX, ignoré.")
            continue

        print(f"     Nom    : {meta['name']}")
        print(f"     Date   : {meta['date']}")
        print(f"     Dist.  : {meta['distance_km']} km")
        print(f"     D+     : {meta['elevation_m']} m")

        ride_type = ask_choice(
            "Type de sortie ?",
            [("Gravel", "gravel"), ("Route", "route")]
        )
        statut = ask_choice(
            "Statut ?",
            [("Déjà fait ✅", "fait"), ("À tester 🔍", "a_tester")]
        )

        month = int(meta["date"].split("-")[1])
        saison = SAISON_MAP[month]

        ride_id = f"ride-{str(len(rides)+1).zfill(3)}"

        ride = {
            "id":           ride_id,
            "name":         meta["name"],
            "date":         meta["date"],
            "distance_km":  meta["distance_km"],
            "elevation_m":  meta["elevation_m"],
            "saison":       saison,
            "type":         ride_type,
            "statut":       statut,
            "source":       gpx_path.stem.split("_")[0] if "_" in gpx_path.stem else "gpx",
            "gpx":          gpx_key,
            "color":        color_for(ride_type, statut),
            "description":  ""
        }
        rides.append(ride)
        new_count += 1

    # Sauvegarde
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(rides, f, ensure_ascii=False, indent=2)

    print(f"\n{'═'*55}")
    print(f"  ✅  {OUT_FILE} mis à jour !")
    print(f"     {new_count} nouvelle(s) sortie(s) ajoutée(s)")
    print(f"     {len(rides)} sortie(s) au total")
    print("═"*55 + "\n")


if __name__ == "__main__":
    main()

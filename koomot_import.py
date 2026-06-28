#!/usr/bin/env python3
"""
komoot_import.py
----------------
Importe un parcours Komoot (public ou privé) dans rides.json.

Usage :
    python komoot_import.py https://www.komoot.com/tour/123456789
    python komoot_import.py https://www.komoot.com/tour/123456789 https://www.komoot.com/tour/987654321
"""

import sys
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from common import GPX_DIR, DATA_DIR, OUT_FILE, SAISON_MAP, color_for

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TOKEN_FILE  = Path(".komoot_token")

# ─── AUTH ─────────────────────────────────────────────────────────────────────
def load_credentials():
    """Charge ou demande email/password Komoot."""
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        print(f"  🔑 Compte Komoot : {data['email']}")
        return data["email"], data["password"], data.get("user_id")

    print("\n  Connexion à ton compte Komoot")
    print("  (sauvegardé localement dans .komoot_token)\n")
    email    = input("  Email    : ").strip()
    password = input("  Password : ").strip()
    return email, password, None

def komoot_login(email, password):
    """Auth basique Komoot — retourne (user_id, token)."""
    url = "https://api.komoot.de/v006/account/email/{}/".format(
        urllib.parse.quote(email, safe="")
    )
    credentials = f"{email}:{password}"
    import base64
    b64 = base64.b64encode(credentials.encode()).decode()

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {b64}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0")

    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise Exception(f"Login échoué ({e.code}) : {body}")

    user_id = data["username"]
    token   = data["password"]
    return user_id, token

def get_auth(email, password, user_id):
    """Retourne (user_id, Basic auth header)."""
    if user_id:
        # Token déjà connu — on essaie de le réutiliser
        with open(TOKEN_FILE) as f:
            d = json.load(f)
        return d["user_id"], d["token"]

    print("  🌐 Connexion à Komoot...")
    uid, token = komoot_login(email, password)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"email": email, "password": password,
                   "user_id": uid, "token": token}, f)
    print(f"  ✅ Connecté ! (user_id: {uid})")
    return uid, token

# ─── KOMOOT API ───────────────────────────────────────────────────────────────
def api_get(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")

    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
def extract_tour_id(url):
    """Extrait l'ID depuis une URL Komoot."""
    m = re.search(r"/tour/(\d+)", url)
    if not m:
        raise Exception(f"URL Komoot invalide : {url}")
    return m.group(1)

def fetch_tour(tour_id):
    """Récupère les métadonnées d'un tour."""
    url = f"https://api.komoot.de/v007/tours/{tour_id}?_embedded=coordinates,way_types,surfaces,directions,participants,timeline"
    return api_get(url)

def tour_to_gpx(tour, tour_id):
    """Convertit les données Komoot en GPX string."""
    coords = tour.get("_embedded", {}).get("coordinates", {}).get("items", [])
    if not coords:
        return None

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" creator="komoot_import" xmlns="http://www.topografix.com/GPX/1/1">',
             f'  <trk><name>{tour.get("name","Tour "+tour_id)}</name><trkseg>']

    for pt in coords:
        lat = pt.get("lat")
        lng = pt.get("lng")
        alt = pt.get("alt", "")
        if lat is None or lng is None:
            continue
        lines.append(f'    <trkpt lat="{lat}" lon="{lng}">')
        if alt != "":
            lines.append(f'      <ele>{alt}</ele>')
        lines.append('    </trkpt>')

    lines += ['  </trkseg></trk>', '</gpx>']
    return "\n".join(lines)

def sport_to_type(sport):
    gravel = {"racebike", "mtb", "mtb_easy", "mtb_advanced", "mtb_enduro",
              "mtb_downhill", "touringbicycle", "e_mtb"}
    return "gravel" if sport in gravel else "route"

# ─── RIDES.JSON ───────────────────────────────────────────────────────────────
def load_rides():
    if OUT_FILE.exists():
        with open(OUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_rides(rides):
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(rides, f, ensure_ascii=False, indent=2)

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    GPX_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    urls = [a for a in sys.argv[1:] if "komoot" in a]
    if not urls:
        print("\n  Usage : python komoot_import.py https://www.komoot.com/tour/123456789")
        print("  Tu peux passer plusieurs URLs d'un coup.\n")
        sys.exit(1)

    print("\n" + "═"*55)
    print("  🗺   Komoot → GravelMap importer")
    print("═"*55)

    rides = load_rides()
    existing_komoot = {r.get("komoot_id") for r in rides if r.get("komoot_id")}
    new_count = 0

    for url in urls:
        print(f"\n{'─'*55}")
        try:
            tour_id = extract_tour_id(url)
        except Exception as e:
            print(f"  ❌ {e}")
            continue

        if tour_id in existing_komoot:
            print(f"  ✓  Tour {tour_id} déjà importé — ignoré")
            continue

        print(f"  🌐 Récupération du tour {tour_id}...")
        try:
            tour = fetch_tour(tour_id)
        except Exception as e:
            print(f"  ❌ Erreur : {e}")
            continue

        name      = tour.get("name", f"Tour {tour_id}")
        dist_km   = round(tour.get("distance", 0) / 1000, 1)
        elev_m    = int(tour.get("elevation_up", 0))
        sport     = tour.get("sport", "touringbicycle")
        date_raw  = tour.get("date") or tour.get("changed_at") or ""
        date_str  = date_raw[:10] if date_raw else datetime.today().strftime("%Y-%m-%d")
        month     = int(date_str.split("-")[1])
        saison    = SAISON_MAP[month]
        ride_type = sport_to_type(sport)

        print(f"  📍 {name}")
        print(f"     Dist.  : {dist_km} km   D+ : {elev_m} m")
        print(f"     Sport  : {sport} → {ride_type}")
        print(f"     Date   : {date_str}")

        # GPX
        gpx_content = tour_to_gpx(tour, tour_id)
        gpx_file = f"gpx/komoot_{tour_id}.gpx"
        if gpx_content:
            with open(gpx_file, "w", encoding="utf-8") as f:
                f.write(gpx_content)
            print(f"  ✅ GPX sauvegardé")
        else:
            gpx_file = ""
            print(f"  ⚠  Pas de coordonnées GPS dans ce tour")

        ride = {
            "id":          f"komoot-ride-{str(len(rides)+1).zfill(3)}",
            "komoot_id":   tour_id,
            "name":        name,
            "date":        date_str,
            "distance_km": dist_km,
            "elevation_m": elev_m,
            "saison":      saison,
            "type":        ride_type,
            "statut":      "a_tester",
            "source":      "komoot",
            "gpx":         gpx_file,
            "color":       color_for(ride_type, "a_tester"),
            "description": tour.get("summary", {}).get("text", "") if isinstance(tour.get("summary"), dict) else ""
        }
        rides.append(ride)
        save_rides(rides)
        new_count += 1
        existing_komoot.add(tour_id)

        time.sleep(0.3)

    print(f"\n{'═'*55}")
    print(f"  ✅ Import terminé — {new_count} parcours ajouté(s) comme 'à tester'")
    print("═"*55 + "\n")

if __name__ == "__main__":
    main()
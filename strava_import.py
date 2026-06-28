#!/usr/bin/env python3
"""
strava_import.py
----------------
Télécharge tous tes GPX depuis Strava et met à jour rides.json.

Usage :
    python strava_import.py

Première fois : ouvre un navigateur pour l'authentification OAuth.
Fois suivantes : token sauvegardé dans .strava_token, pas de re-login.
"""

import os
import json
import math
import time
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
import http.server
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from common import GPX_DIR, DATA_DIR, OUT_FILE, SAISON_MAP, ask_choice, color_for

# ─── CONFIG ───────────────────────────────────────────────────────────────────
def _load_dotenv():
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

_load_dotenv()

CLIENT_ID     = os.environ.get("STRAVA_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET", "")
if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("❌  STRAVA_CLIENT_ID ou STRAVA_CLIENT_SECRET manquant — vérifie ton fichier .env")

REDIRECT_URI  = "http://localhost:8765/callback"
TOKEN_FILE    = Path(".strava_token")

# ─── OAUTH ────────────────────────────────────────────────────────────────────
auth_code = None

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Authentification OK ! Retourne dans le terminal.</h2><script>window.close()</script>")
        else:
            self.send_response(400)
            self.end_headers()
    def log_message(self, *args):
        pass  # silence les logs HTTP

def get_token():
    """Retourne un access_token valide (refresh si nécessaire)."""
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)
        # Refresh si expiré
        if token_data["expires_at"] - time.time() < 60:
            print("  🔄 Rafraîchissement du token...")
            token_data = refresh_token(token_data["refresh_token"])
        return token_data["access_token"]
    return oauth_flow()

def oauth_flow():
    """Premier login : ouvre le navigateur pour autoriser l'app."""
    global auth_code
    print("\n  🌐 Ouverture du navigateur pour autoriser l'accès Strava...")
    url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        "&response_type=code"
        "&scope=activity:read_all"
    )
    server = http.server.HTTPServer(("localhost", 8765), OAuthHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    webbrowser.open(url)
    print("  ⏳ En attente de l'autorisation dans le navigateur...")
    thread.join(timeout=120)
    if not auth_code:
        print("  ❌ Timeout — relance le script et autorise dans les 2 minutes.")
        exit(1)
    return exchange_code(auth_code)

def api_post(url, data):
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def exchange_code(code):
    print("  🔑 Échange du code OAuth...")
    data = api_post("https://www.strava.com/oauth/token", {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "code": code, "grant_type": "authorization_code"
    })
    save_token(data)
    return data["access_token"]

def refresh_token(refresh_tok):
    data = api_post("https://www.strava.com/oauth/token", {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_tok, "grant_type": "refresh_token"
    })
    save_token(data)
    return data

def save_token(data):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": data["access_token"],
                   "refresh_token": data["refresh_token"],
                   "expires_at": data["expires_at"]}, f)

# ─── STRAVA API ───────────────────────────────────────────────────────────────
def api_get(url, token, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def fetch_all_activities(token, after_date=None):
    activities, page = [], 1
    after_ts = int(datetime.strptime(after_date, "%Y-%m-%d").timestamp()) if after_date else None
    print("  📋 Récupération des activités...")
    while True:
        params = {"per_page": 100, "page": page}
        if after_ts:
            params["after"] = after_ts
        batch = api_get("https://www.strava.com/api/v3/athlete/activities", token, params)
        if not batch:
            break
        activities.extend(batch)
        print(f"     {len(activities)} activités récupérées...", end="\r")
        page += 1
    print(f"     {len(activities)} activité(s) trouvée(s).          ")
    return activities

def download_gpx(activity_id, token, path):
    """Télécharge le stream GPX d'une activité."""
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    try:
        streams = api_get(url, token, {
            "keys": "latlng,altitude,time", "key_by_type": "true"
        })
    except urllib.error.HTTPError:
        return False

    latlng   = streams.get("latlng",   {}).get("data", [])
    altitude = streams.get("altitude", {}).get("data", [])
    times    = streams.get("time",     {}).get("data", [])

    if not latlng:
        return False

    root = ET.Element("gpx", version="1.1", creator="strava_import")
    root.set("xmlns", "http://www.topografix.com/GPX/1/1")
    trk  = ET.SubElement(root, "trk")
    seg  = ET.SubElement(trk,  "trkseg")

    for i, (lat, lon) in enumerate(latlng):
        pt = ET.SubElement(seg, "trkpt", lat=str(lat), lon=str(lon))
        if i < len(altitude):
            ET.SubElement(pt, "ele").text = str(altitude[i])

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return True

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def sport_to_type(sport_type):
    gravel_types = {"GravelRide", "MountainBikeRide", "Ride"}
    return "gravel" if sport_type in gravel_types else "route"

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    GPX_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    print("\n" + "═"*55)
    print("  🚵  Strava → GravelMap importer")
    print("═"*55)

    # Charge rides.json existant EN PREMIER
    existing_ids = set()
    rides = []
    if OUT_FILE.exists():
        with open(OUT_FILE, encoding="utf-8") as f:
            rides = json.load(f)
            for r in rides:
                if "strava_id" in r:
                    existing_ids.add(r["strava_id"])

    token = get_token()
    print("  ✅ Connecté à Strava !")

    last_date = max((r["date"] for r in rides if r.get("source") == "strava"), default=None)
    if last_date:
        print(f"  📅 Import depuis le {last_date}")
    activities = fetch_all_activities(token, after_date=last_date)

    # Filtre : uniquement les activités vélo
    bike_types = {"Ride","GravelRide","MountainBikeRide","VirtualRide","EBikeRide"}
    activities = [a for a in activities if a.get("sport_type") in bike_types or a.get("type") in bike_types]
    print(f"  🚲 {len(activities)} activité(s) vélo trouvée(s)")

    new_activities = [a for a in activities if a["id"] not in existing_ids]
    print(f"  🆕 {len(new_activities)} nouvelle(s) activité(s) à importer\n")

    if not new_activities:
        print("  ✓  Tout est déjà à jour !")
        print("═"*55 + "\n")
        return

    new_count = 0
    for i, act in enumerate(new_activities, 1):
        name       = act.get("name", f"Activité {act['id']}")
        sport_type = act.get("sport_type") or act.get("type", "Ride")
        date_str   = act["start_date_local"][:10]
        dist_km    = round(act.get("distance", 0) / 1000, 1)
        elev_m     = int(act.get("total_elevation_gain", 0))
        month      = int(date_str.split("-")[1])
        saison     = SAISON_MAP[month]
        ride_type  = sport_to_type(sport_type)
        gpx_file   = f"gpx/strava_{act['id']}.gpx"

        print(f"{'─'*55}")
        print(f"  📍 [{i}/{len(new_activities)}] {name}")
        print(f"     Date   : {date_str}")
        print(f"     Dist.  : {dist_km} km   D+ : {elev_m} m")
        print(f"     Type   : {sport_type} → {ride_type}")

        # Type auto-détecté mais confirmable
        type_auto = ride_type
        ride_type = ask_choice(
            f"Type ? (auto-détecté : {type_auto})",
            [("Gravel", "gravel"), ("Route", "route")]
        )
        statut = "fait"

        # Télécharge le GPX
        print(f"  ⬇  Téléchargement du GPX...", end=" ")
        ok = download_gpx(act["id"], token, Path(gpx_file))
        print("✓" if ok else "⚠ pas de données GPS (activité indoor ?)")

        ride = {
            "id":          f"strava-ride-{str(len(rides)+1).zfill(3)}",
            "strava_id":   act["id"],
            "name":        name,
            "date":        date_str,
            "distance_km": dist_km,
            "elevation_m": elev_m,
            "saison":      saison,
            "type":        ride_type,
            "statut":      statut,
            "source":      "strava",
            "gpx":         gpx_file if ok else "",
            "color":       color_for(ride_type, statut),
            "description": act.get("description", "") or ""
        }
        rides.append(ride)
        new_count += 1

        # Sauvegarde après chaque ride (au cas où on coupe)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(rides, f, ensure_ascii=False, indent=2)

        # Rate limit Strava : max 100 req/15min
        time.sleep(0.5)

    print(f"\n{'═'*55}")
    print(f"  ✅ Import terminé !")
    print(f"     {new_count} nouvelle(s) sortie(s) ajoutée(s)")
    print(f"     {len(rides)} sortie(s) au total dans rides.json")
    print("═"*55 + "\n")

if __name__ == "__main__":
    main()

# 🚵 Mes Sorties Gravel — Map personnelle

Site statique pour visualiser tes itinéraires GPX sur une carte interactive.

## Structure
```
gravel-map/
├── index.html          ← Le site complet (tout-en-un)
├── common.py           ← Constantes et utilitaires Python partagés
├── strava_import.py    ← Import automatique depuis Strava
├── koomot_import.py    ← Import depuis Komoot (URL de tour)
├── generate_rides.py   ← Génère rides.json depuis des GPX locaux
├── data/
│   └── rides.json      ← Métadonnées de toutes les sorties
└── gpx/
    ├── strava_*.gpx
    └── komoot_*.gpx
```

## 1. Configuration initiale

### Fichier `.env` (à créer, jamais committé)
```
STRAVA_CLIENT_ID=256520
STRAVA_CLIENT_SECRET=ton_secret_ici
```

## 2. Importer des sorties

### Depuis Strava (automatique)
```bash
python strava_import.py
```
- Première fois : ouvre le navigateur pour l'auth OAuth
- Fois suivantes : token sauvegardé dans `.strava_token`
- Télécharge tous les GPX manquants et met à jour `rides.json`

### Depuis Komoot (par URL)
```bash
python koomot_import.py https://www.komoot.com/tour/123456789
# Plusieurs URLs en une fois :
python koomot_import.py https://www.komoot.com/tour/111 https://www.komoot.com/tour/222
```

### Depuis des GPX locaux
Place les fichiers `.gpx` dans le dossier `gpx/`, puis :
```bash
python generate_rides.py
```

## 3. Tester en local

```bash
python -m http.server 8080
# → http://localhost:8080
```
⚠️ Ouvrir directement `index.html` ne fonctionnera pas (CORS sur les GPX).

## 4. Déployer sur GitHub Pages

### Première mise en ligne
```bash
git init
git add index.html data/ gpx/ common.py strava_import.py koomot_import.py generate_rides.py README.md
git commit -m "init"
git remote add origin https://github.com/TON_USER/gravel-map.git
git push -u origin main
```
Dans GitHub → Settings → Pages → Source : **main branch / root**.  
Ton site sera sur `https://TON_USER.github.io/gravel-map/`.

### Workflow après import de nouvelles sorties
```bash
python strava_import.py          # importe les nouvelles sorties
git add data/rides.json gpx/     # ajoute les nouveaux fichiers
git commit -m "import sorties juin"
git push
```
Le site GitHub Pages se met à jour automatiquement en ~1 minute.

> **Note :** `.env`, `.strava_token` et `.komoot_token` sont dans `.gitignore` — ils ne seront jamais publiés.

## 5. Fonctionnalités de la carte

- **Filtres** : Type (Gravel / Route), Statut (Déjà fait / À tester), Saison
- **Profil altimétrique** : visible dans le popup au clic sur une trace
- **Changer le statut** : bouton dans le popup (persisté en `localStorage`)
- **Exporter rides.json** : bouton en bas de la sidebar pour récupérer les modifications de statut et les committer

## 6. Couleurs des traces

| Condition | Couleur |
|-----------|---------|
| Gravel déjà fait | 🟠 Orange |
| Route déjà faite | 🔵 Bleu |
| À tester (tous types) | 🟡 Jaune |

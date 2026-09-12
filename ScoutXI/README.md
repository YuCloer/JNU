# ScoutXI

A local football scouting and squad-planning application for exploring players, clubs, and position-constrained formations.

ScoutXI focuses on a transparent planning workflow: inspect available players, filter by position, place them on a formation canvas, and save a squad without pretending that demo data is an official rating system.

## Capabilities

- player and club search with position filters;
- player details, club-season squads, and scouting reports;
- 13 formation layouts with fixed tactical zones;
- starting XI, substitutes, captain, saved squads, and favorites;
- optional synchronization from public football data APIs;
- local demo data when no API key is configured.

## Engineering choices

- **FastAPI + SQLite** keep the default setup lightweight and local.
- **Position constraints** prevent incompatible players from being placed in tactical zones.
- **Source transparency** distinguishes built-in demo data from externally synchronized data.
- **Privacy by default** keeps API keys in a local `.env`; the application listens on `127.0.0.1` by default.
- **Resilient refresh** reports quota or provider limitations instead of presenting stale data as current.

The current scope intentionally excludes advanced analytics, radar charts, video recognition, and AI recommendations.

## Quick start

Requirements: Windows, Python 3.10+, and PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:8000`.

Without API credentials, squad planning, search, favorites, and reports work with the built-in demo dataset.

## Optional data sources

Copy the example configuration and add one or more local API keys:

```powershell
Copy-Item .env.example .env
```

```ini
FOOTBALL_DATA_API_TOKEN=your-token
API_FOOTBALL_KEY=your-key
```

Both providers are optional. Free plans may impose request quotas and season restrictions; the application reports these limits instead of silently substituting old data.

## Project structure

```
ScoutXI/
├── app/
├── static/
├── tests/
├── run.py
└── requirements.txt
```

## Safety and privacy

Do not commit `.env`, provider keys, SQLite databases, logs, virtual environments, or IDE metadata. If the service is exposed beyond localhost, add authentication to administrative synchronization endpoints first.

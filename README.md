# NEA SG Map (Flask + Leaflet)

Interactive Singapore map that highlights dengue hotspots with red polygons and includes a right-panel assistant powered by Azure OpenAI.

## Features
- Leaflet map with OneMap day/night basemaps
- Live layers:
  - Dengue Hotspots (OneMap ThemeSVC)
  - Planning Areas (OneMap PopAPI, 2019)
- Assistant-style chat in the right sidebar
  - Map tool-calling (show/hide layers)
  - Dynamic grounding from live API data
- Modern UI with Bootstrap 5

## Prerequisites
- Python 3.9+
- OneMap API token (ONEMAP_TOKEN)
- Optional: Azure OpenAI credentials for chat enhancements

## Quick Start (Windows PowerShell)

1) Create and activate a virtual environment

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

2) Install dependencies

```powershell
pip install -r requirements.txt
```

3) Configure environment variables

- Copy the template and fill your values:

```powershell
Copy-Item .env.example .env
```

- Edit `.env` and set the following:

Required
- `ONEMAP_TOKEN` = Your OneMap API token

Optional (Azure OpenAI)
- `AZURE_OPENAI_ENDPOINT` = e.g. https://<your-resource>.openai.azure.com
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT` = your chat model deployment name
- `AZURE_OPENAI_API_VERSION` = 2024-02-15-preview (default)

Optional (Azure AI Search grounding)
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_INDEX`
- `AZURE_SEARCH_API_KEY`

4) Run the app

```powershell
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Endpoints
- `/` – Web UI
- `/api/dengue-clusters` – Dengue hotspots (GeoJSON FeatureCollection)
- `/api/planning-areas?year=2019` – Planning areas (GeoJSON FeatureCollection)
- `/api/chat` – Chat endpoint accepting `{ "message": "..." }`
- `/api/welcome` – Dynamic welcome message
- `/api/azure-health` – Checks Azure OpenAI configuration and chat/tool-calling

Quick health check (PowerShell):

```powershell
Invoke-RestMethod -UseBasicParsing -Uri 'http://127.0.0.1:5000/api/azure-health' -Method Get | ConvertTo-Json -Depth 5
```

## Getting an ONEMAP_TOKEN
- Sign up and obtain a token from OneMap (https://www.onemap.gov.sg/docs/)
- Store it in your local `.env` file: `ONEMAP_TOKEN=...`

## Notes
- Do not commit your `.env` file. This repo includes a `.gitignore` that ignores `.env` and virtual environments.
- The assistant can still work without Azure credentials; it will fall back to deterministic logic for summaries/lists.

## Troubleshooting
- 400 Missing ONEMAP_TOKEN: Ensure `.env` is present and contains `ONEMAP_TOKEN`.
- No hotspots shown: Token may be expired/invalid, or OneMap service is unavailable. Check logs and try again.
- Azure not configured: `/api/azure-health` will show `configured: false`. Set the Azure env vars in `.env` if needed.
- Port already in use: Stop other Python/Flask servers or change the port.

## Development
- Map layers are controlled from a top-right “Layers” dropdown.
- The backend uses a dynamic layer registry so you can add new layers by registering a `context_builder` and synonyms.
- Frontend layer toggles are currently wired for Dengue + Planning; add more toggles if you introduce new layers.

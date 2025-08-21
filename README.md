
# Bitpilot — CP-5 Journal 2.0 geïntegreerd

## Installatie
```bash
pip install -r requirements.txt
```

## Starten
```bash
streamlit run cockpit.py
```

## Belangrijk
- **Journal**: links formulier + tabel met klik (checkbox) selectie; rechts detail + **AI‑Coach**.
- **Screenshots**: upload meerdere of plak URL’s; pad = `resources/screens/YYMM/`.
- **AI‑Coach**: zet `OPENAI_API_KEY` in je omgeving. Budget wordt bewaakt; fallback is heuristisch.
- **Settings**: Budget & modelkeuze, Kennisbank, **Events import met overrides**, Backup-retentie, Lijsten (Setup/Strategie).
- **Export**: gefilterde CSV in `data/export/` met filters als comment op regel 1.

- 
- **Roadmap**: CP‑8 voegt definitieve risk/plantrouw KPI’s toe.


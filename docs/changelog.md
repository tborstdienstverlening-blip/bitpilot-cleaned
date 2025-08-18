Build time: 2025-08-10T23:19:26.266634 — CLEAN hotfix build.
## C0-04 Bootfix — 2025-08-18
- Hygiene: `.gitignore` opgeschoond; `requirements.txt` gepind (volgens Cloud-omgeving).
- Compat-laag toegevoegd (`compat.py`) met veilige imports en AI-stubs.
- Healthcheck-paneel dat directories/config controleert en nooit crasht.
- CSV IO gehard (leeg-bestand tolerant) + KPI's veilig bij lege data.
- `cockpit.py` herbouwd om altijd te starten (geen ModuleNotFoundError / geen DuplicateWidgetID).

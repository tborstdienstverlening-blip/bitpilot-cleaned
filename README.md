# Bitpilot — BTC Cockpit

**Status:** Fase **C0 — Stabiel draaien (nu bezig)** · **Release 0.2**  
**Nu actief:** **R0.2-04 — KPI-balk** (Accountwaarde BTC, ROI, Winrate(s), Fees, PnL)  
**Bronnen:** `gekkigheid.docx` (blauwdruk/basis) · `Bitpilot Canvas (2).pdf` (roadmap)

> Bitpilot is een **Streamlit**-gebaseerde BTC-cockpit volgens de **DoopieCash**-aanpak.  
> We bouwen **door op** `gekkigheid.docx` (blauwdruk) en leggen **afwijkingen/verbeteringen** vast via **Blauwdruk-Delta (BD)** + een korte **ADR** (Architecture Decision Record).

---

## 🚀 Wat er nu staat (Release 0.2 – kern)
- **Risk & Position Sizing**
  - Risk% correct geschaald (1.0% ⇒ 0.01)
  - **Contract Size** als **integer (floor)** ⇒ **risk ≤ target**, **fees meegeteld**
  - **RR (Actueel)** rekent met **Kapitaal (trade) × Risk %** (per rij)
- **PnL & Tiles**
  - **Totale PnL (BTC/USD)** is **netto** (TP/Exit − fees)
  - **Actueel = Start + Totale PnL**
- **Journaling**
  - Heldere velden/labels en (later) PDF-bundeling van setups/trades
  - Label: *Passieve trades met correcte uitvoering* (objectieve evaluatie)
- **Methodologie (DoopieCash)**
  - HTF-leidend, markstructuur (HH/HL vs. LH/LL), S/D-zones, traps, invalidatie, confluence
  - Objectief, gedisciplineerd, outcome-neutraal evalueren

> Afwijkingen/hiaten t.o.v. de blauwdruk → **BD-item** in ticket + **ADR** in `/docs/ADR.md`.

---

## 🧭 Roadmap (korte samenvatting)
- **Fase C0 — Stabiel draaien**: C0-01/02/03/04 ✔️ (volgens roadmapbestand in het project)
- **Release 0.2 — Solide cockpitbasis (Journal + KPI)**  
  - R0.2-01/02/03/03a ✔️ · **R0.2-04 (actief)**
- **Volgende staples (indicatief)**
  - Patch 0.2.x – AI-Chat v1 (sleutel/budget-guard, ai_notes.csv), Clean & Governance
  - Release 0.3 – AI Sparren v2 + Zelflerend v1 (modes, journal-koppeling, feedbacklus, risicomodule)

*De volledige volgorde en details staan in `Bitpilot Canvas (2).pdf`. Dit README is een beknopt overzicht.*

---

## 🛠️ Installatie & start (lokaal)

**Vereisten:** Python 3.11+, pip, git

```bash
# 1) Clone
git clone <JOUW-REPO-URL>
cd <repo>

# 2) Virtuele omgeving (aanrader)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3) Dependencies
pip install -r requirements.txt

# 4) Secrets/omgeving
# Kopieer .env.example → .env en vul je keys (bv. OPENAI_API_KEY)
# (Nooit echte sleutels committen)

# 5) Start
streamlit run cockpit.py

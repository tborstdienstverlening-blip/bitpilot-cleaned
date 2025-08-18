from __future__ import annotations
from pathlib import Path
from datetime import datetime
import io, shutil, json, numpy as np, pandas as pd, streamlit as st
import schema as S
from schema import COL
from utils_config import load_config, save_config
import stats_utils as STATS
import import_export as IEX
import copilot as COP
import healthcheck as HC
import events_ui as EVENTS
from theme_manager import inject_theme_css, render_theme_settings
from coach_engine import rebuild_user_index, classify_setup
ROOT = Path.cwd()
DATA = ROOT / 'data'
BAK = DATA / '.bak'
SCREENS = ROOT / 'resources' / 'screens'
EXPORT = DATA / 'export'
JOURNAL = DATA / 'journal_entries.csv'
CONTEXT = DATA / 'trade_context.jsonl'
NOTES = DATA / 'coach_notes.jsonl'

def ensure_dirs():
    for p in (DATA, BAK, SCREENS, EXPORT, DATA / 'logs', ROOT / 'resources' / 'artifacts', DATA / 'snapshots'):
        p.mkdir(parents=True, exist_ok=True)

def canonical_columns():
    cols = [COL['DATUM'], COL['TRADE_ID'], COL['SETUP'], COL['STRATEGIE'], COL['TFS'], COL['PLAN_SHORT'], COL['ENTRY'], COL['STOPLOSS'], COL['RISK_PCT'], COL['R_INZET'], COL['TP1'], COL['TP2'], COL['TP3'], COL['UITKOMST'], COL['RR_REAL'], COL['PLAN_TROUW'], COL['EMOTIES'], COL['TAGS'], COL['NOTITIES'], COL['STATUS'], COL['SCREEN1'], COL['SCREEN2'], COL['SCREEN3'], COL['SCREEN4'], COL['SCREEN5'], COL['SCREEN6'], COL.get('EVENT_IDS', 'Gekoppelde_Events'), COL['RESULT_PNL'], COL['ROI_SIMPLE'], COL['TA_SUMMARY'], COL['AI_PREFLIGHT_STATUS'], COL['AI_PREFLIGHT_NOTES'], COL['AI_LAST_ADVICE'], COL['AI_SETUP']]
    out = []
    seen = set()
    for c in cols:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out

def rotate_backup(path: Path, keep: int=20):
    BAK.mkdir(exist_ok=True, parents=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if path.exists():
        shutil.copy2(path, BAK / f'{path.stem}.{ts}.bak')
    baks = sorted(BAK.glob(f'{path.stem}.*.bak'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in baks[keep:]:
        old.unlink(missing_ok=True)

def read_journal() -> pd.DataFrame:
    ensure_dirs()
    if not JOURNAL.exists():
        pd.DataFrame(columns=canonical_columns()).to_csv(JOURNAL, index=False)
    df = pd.read_csv(JOURNAL)
    for a, canon in (getattr(S, 'ALIAS', {}) or {}).items():
        if a in df.columns and canon not in df.columns:
            df.rename(columns={a: canon}, inplace=True)
    for c in canonical_columns():
        if c not in df.columns:
            df[c] = None
    try:
        df[COL['DATUM']] = pd.to_datetime(df[COL['DATUM']], errors='coerce', format='mixed')
    except TypeError:
        df[COL['DATUM']] = pd.to_datetime(df[COL['DATUM']], errors='coerce')
    for num in [COL['ENTRY'], COL['STOPLOSS'], COL['RISK_PCT'], COL['R_INZET'], COL['TP1'], COL['TP2'], COL['TP3'], COL['RR_REAL'], COL['PLAN_TROUW'], COL['RESULT_PNL']]:
        if num in df.columns:
            df[num] = pd.to_numeric(df[num], errors='coerce')
    if COL['ROI_SIMPLE'] in df.columns:
        base = df[COL['ENTRY']].abs()
        with pd.option_context('future.no_silent_downcasting', True):
            df[COL['ROI_SIMPLE']] = (pd.to_numeric(df[COL['RESULT_PNL']], errors='coerce') / base * 100).replace([np.inf, -np.inf], pd.NA)
    return df

def write_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')

def kpis(df):
    trades = len(df)
    pnl = float(pd.to_numeric(df[COL['RESULT_PNL']], errors='coerce').fillna(0).sum()) if trades else 0.0
    wins = int((pd.to_numeric(df[COL['RESULT_PNL']], errors='coerce') > 0).fillna(False).sum()) if trades else 0
    winrate = wins / trades * 100 if trades else 0.0
    avg_roi = float(pd.to_numeric(df.get(COL['ROI_SIMPLE']), errors='coerce').fillna(0).mean()) if trades else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Trades', f'{trades}')
    c2.metric('Totaal PnL', f'${pnl:,.2f}')
    c3.metric('Winrate', f'{winrate:.1f}%')
    c4.metric('Gem. ROI (simpel)', f'{avg_roi:.1f}%')

def plot_equity(df):
    if df.empty:
        st.info('Geen data om te tonen.')
        return
    tmp = df.sort_values(COL['DATUM'])
    tmp['PnL'] = pd.to_numeric(tmp[COL['RESULT_PNL']], errors='coerce').fillna(0)
    tmp['Equity'] = tmp['PnL'].cumsum()
    st.line_chart(tmp.set_index(COL['DATUM'])[['Equity']], use_container_width=True)

def filters_expander(df):
    with st.expander('Filters', expanded=False):
        a, b, c = st.columns(3)
        d, e = st.columns(2)
        with a:
            f_setup = st.multiselect('Setup', sorted(df[COL['SETUP']].dropna().unique().tolist()), key='filt_setup')
        with b:
            f_strat = st.multiselect('Strategie', sorted(df[COL['STRATEGIE']].dropna().unique().tolist()), key='filt_strat')
        with c:
            f_emo = st.multiselect('Emoties', sorted(df[COL['EMOTIES']].dropna().unique().tolist()), key='filt_emo')
        with d:
            f_tag = st.multiselect('Tags', sorted(df[COL['TAGS']].dropna().unique().tolist()), key='filt_tag')
        with e:
            f_tid = st.text_input('Trade_ID (bevat)', key='filt_tid')
        chips = []
        for k in ('filt_setup', 'filt_strat', 'filt_emo', 'filt_tag', 'filt_tid'):
            v = st.session_state.get(k)
            if v:
                chips.append(f"{k.replace('filt_', '')}: {v}")
        if chips:
            st.caption('Actieve filters — ' + ' | '.join(chips))
        colr, _ = st.columns([1, 5])
        if colr.button('Reset', key='filt_reset'):
            for k in ('filt_setup', 'filt_strat', 'filt_emo', 'filt_tag', 'filt_tid'):
                st.session_state.pop(k, None)
                st.rerun()
    out = df.copy()
    if st.session_state.get('filt_setup'):
        out = out[out[COL['SETUP']].isin(st.session_state['filt_setup'])]
    if st.session_state.get('filt_strat'):
        out = out[out[COL['STRATEGIE']].isin(st.session_state['filt_strat'])]
    if st.session_state.get('filt_emo'):
        out = out[out[COL['EMOTIES']].isin(st.session_state['filt_emo'])]
    if st.session_state.get('filt_tag'):
        mask = False
        for t in st.session_state['filt_tag']:
            mask = mask | out[COL['TAGS']].astype(str).str.contains(f'\\b{t}\\b', case=False, na=False)
        out = out[mask]
    if st.session_state.get('filt_tid'):
        out = out[out[COL['TRADE_ID']].astype(str).str.contains(st.session_state['filt_tid'], case=False, na=False)]
    return out

def export_filtered(df_filtered):
    EXPORT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fn = EXPORT / f'journal_filtered_{ts}.csv'
    filters = {k: v for k, v in st.session_state.items() if k.startswith('filt_')}
    buf = io.StringIO()
    buf.write('# Filters: ' + ', '.join((f'{k}={v}' for k, v in filters.items())) + '\n')
    df_filtered.to_csv(buf, index=False)
    fn.write_text(buf.getvalue(), encoding='utf-8')
    st.success(f'Export gemaakt: {fn.name}')

def ta_drawer(df):
    st.markdown('### TA / Setup')
    screens = st.file_uploader('Screenshots (max 3)', type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key='cockpit_auto_1')
    summary = st.text_area('TA-samenvatting', '', key='cockpit_auto_2')
    confluence = st.multiselect('Confluence', ['liq_sweep', 'reclaim', 'htf_demand', '15m_HH', 'news', 'range'], [], key='cockpit_auto_3')
    bias = st.radio('Bias', ['long', 'short', 'onzeker'], horizontal=True, key='cockpit_auto_4')
    if st.button('AI-analyse (Routine)', key='cockpit_auto_5'):
        setup_suggest = classify_setup(summary + ' ' + ' '.join(confluence))
        st.session_state['ta_ai_output'] = {'setup_type': setup_suggest, 'entry': None, 'sl': None, 'tp': [], 'notes': 'Controleer 15m structuur en events binnen ±1u.'}
        st.success(f'AI setup suggestie: {setup_suggest}')
    ai_out = st.session_state.get('ta_ai_output', {'tp': []})
    c1, c2, c3 = st.columns(3)
    with c1:
        ai_entry = st.number_input('AI Entry (suggestie)', value=float(ai_out.get('entry') or 0.0), key='ta_ai_entry')
    with c2:
        ai_sl = st.number_input('AI SL (suggestie)', value=float(ai_out.get('sl') or 0.0), key='ta_ai_sl')
    with c3:
        ai_tp1 = st.number_input('AI TP1 (suggestie)', value=float((ai_out.get('tp') or [0.0])[0] or 0.0), key='ta_ai_tp1')
    note = st.text_area('AI-notes', ai_out.get('notes', ''), key='cockpit_auto_6')

    def _save_screens(files):
        saved = []
        if not files:
            return saved
        yymm = datetime.now().strftime('%y%m')
        folder = SCREENS / yymm
        folder.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files[:3], start=1):
            name = f"ta_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{i}.png"
            out = folder / name
            out.write_bytes(f.getbuffer())
            saved.append(str(out).replace('\\', '/'))
        return saved
    colA, colB = st.columns(2)
    if colA.button('Sla TA-sessie'):
        paths = _save_screens(screens)
        obj = {'trade_id': None, 'phase': 'ta', 'inputs': {'screens': paths, 'summary': summary, 'confluence': confluence, 'bias': bias}, 'ai_output': {'setup_type': st.session_state.get('ta_ai_output', {}).get('setup_type'), 'entry': ai_entry, 'sl': ai_sl, 'tp': [ai_tp1] if ai_tp1 else [], 'notes': note}, 'ts': datetime.now().isoformat()}
        write_jsonl(CONTEXT, obj)
        st.success('TA-sessie opgeslagen.')
    if colB.button('Maak trade vanuit TA'):
        st.session_state['f_plan'] = summary
        st.session_state['f_tfs'] = ' / '.join(confluence) if confluence else st.session_state.get('f_tfs', '')
        st.session_state['f_setup'] = st.session_state.get('ta_ai_output', {}).get('setup_type', 'Breakout')
        st.session_state['f_entry'] = float(ai_entry or 0.0)
        st.session_state['f_stop'] = float(ai_sl or 0.0)
        st.session_state['f_tp1'] = float(ai_tp1 or 0.0)
        st.toast('Formulier ingevuld vanuit TA. Controleer en klik Opslaan.', icon='✅')

def form(df):
    st.markdown('### Tradeformulier')
    mode = st.session_state.get('_form_mode', 'new')
    idx = st.session_state.get('_edit_idx')
    editing = df.iloc[idx].to_dict() if mode == 'edit' and idx is not None and (0 <= idx < len(df)) else {}
    v = lambda k, d=None: editing.get(k, d)
    st.markdown('#### Kern')
    a, b, c = st.columns(3)
    with a:
        datum = st.date_input('Datum', value=v(COL['DATUM']) or datetime.now(), key='f_datum')
        tid = st.text_input(COL['TRADE_ID'], value=str(v(COL['TRADE_ID'], '')), key='f_tid')
    with b:
        setups = ['Breakout', 'Reversal', 'liq_sweep_reclaim', 'range_retest', 'breakout_fail_trap', 'v_bottom_top', 'htf_reclaim', 'continuation_pullback']
        setup = st.selectbox(COL['SETUP'], setups, index=setups.index(v(COL['SETUP'])) if v(COL['SETUP']) in setups else 0, key='f_setup')
        tfs = st.text_input(COL['TFS'], value=str(v(COL['TFS'], '')), key='f_tfs')
    with c:
        strats = ['HTF Pullback', 'Trend-follow', 'Mean reversion']
        strat = st.selectbox(COL['STRATEGIE'], strats, index=strats.index(v(COL['STRATEGIE'])) if v(COL['STRATEGIE']) in strats else 0, key='f_strat')
    st.markdown('#### Risico & Niveaus')
    d, e, f = st.columns(3)
    with d:
        entry = st.number_input(COL['ENTRY'], value=float(v(COL['ENTRY'], 0.0) or 0.0), key='f_entry')
        stop = st.number_input(COL['STOPLOSS'], value=float(v(COL['STOPLOSS'], 0.0) or 0.0), key='f_stop')
    with e:
        riskpct = st.number_input(COL['RISK_PCT'], 0.0, 100.0, float(v(COL['RISK_PCT'], 0.0) or 0.0), 1.0, key='f_riskpct')
        rinzet = st.number_input(COL['R_INZET'], 0.0, None, float(v(COL['R_INZET'], 0.0) or 0.0), 0.25, key='f_rinzet')
    with f:
        tp1 = st.number_input(COL['TP1'], value=float(v(COL['TP1'], 0.0) or 0.0), key='f_tp1')
        tp2 = st.number_input(COL['TP2'], value=float(v(COL['TP2'], 0.0) or 0.0), key='f_tp2')
        tp3 = st.number_input(COL['TP3'], value=float(v(COL['TP3'], 0.0) or 0.0), key='f_tp3')
        rr = st.number_input(COL['RR_REAL'], value=float(v(COL['RR_REAL'], 0.0) or 0.0), key='f_rr')
    st.markdown('#### Proces')
    plan = st.text_area(COL['PLAN_SHORT'], value=str(v(COL['PLAN_SHORT'], '')), key='f_plan')
    plantrouw = st.slider(COL['PLAN_TROUW'], 0, 100, int(v(COL['PLAN_TROUW'], 0) or 0), key='f_plantrouw')
    st.markdown('#### Status & Media')
    status = st.selectbox(COL['STATUS'], ['Open', 'Gesloten', 'Geannuleerd'], index=['Open', 'Gesloten', 'Geannuleerd'].index(v(COL['STATUS'])) if v(COL['STATUS']) in ['Open', 'Gesloten', 'Geannuleerd'] else 0, key='f_status')
    emoties = st.text_input(COL['EMOTIES'], value=str(v(COL['EMOTIES'], '')), key='f_emoties')
    tags = st.text_input(COL['TAGS'], value=str(v(COL['TAGS'], '')), key='f_tags')
    notes = st.text_area(COL['NOTITIES'], value=str(v(COL['NOTITIES'], '')), key='f_notes')
    urls = st.text_area('Screenshot-URL’s (één per regel)', value=str(v(COL['SCREEN1'], '') or ''), key='f_urls')
    csave, corride, cdel, ccancel = st.columns([1, 1, 1, 1])
    if csave.button('Opslaan', key='f_save'):
        row = {COL['DATUM']: pd.to_datetime(st.session_state['f_datum']), COL['TRADE_ID']: st.session_state['f_tid'].strip(), COL['SETUP']: st.session_state['f_setup'], COL['STRATEGIE']: st.session_state['f_strat'], COL['TFS']: st.session_state['f_tfs'], COL['PLAN_SHORT']: st.session_state['f_plan'], COL['ENTRY']: st.session_state['f_entry'], COL['STOPLOSS']: st.session_state['f_stop'], COL['RISK_PCT']: st.session_state['f_riskpct'], COL['R_INZET']: st.session_state['f_rinzet'], COL['TP1']: st.session_state['f_tp1'], COL['TP2']: st.session_state['f_tp2'], COL['TP3']: st.session_state['f_tp3'], COL['UITKOMST']: '', COL['RR_REAL']: st.session_state['f_rr'], COL['PLAN_TROUW']: plantrouw, COL['EMOTIES']: emoties, COL['TAGS']: tags, COL['NOTITIES']: notes, COL['STATUS']: status, COL.get('EVENT_IDS', 'Gekoppelde_Events'): '', COL['SCREEN1']: urls, COL['TA_SUMMARY']: st.session_state.get('f_ta_summary', ''), COL['AI_PREFLIGHT_STATUS']: None, COL['AI_PREFLIGHT_NOTES']: None}
        errs = []
        req = [COL['DATUM'], COL['TRADE_ID'], COL['SETUP'], COL['STRATEGIE'], COL['TFS'], COL['PLAN_SHORT'], COL['ENTRY'], COL['STOPLOSS']]
        for r in req:
            if row.get(r) in (None, '', float('nan')):
                errs.append(f'Veld ontbreekt: {r}')
        if not (row.get(COL['RISK_PCT']) or row.get(COL['R_INZET'])):
            errs.append('Vul minimaal Risk_% of R_inzet in.')
        id_new = str(row[COL['TRADE_ID']])
        id_exists = (pd.Series(df[COL['TRADE_ID']].astype(str)) == id_new).any()
        if st.session_state.get('_form_mode', 'new') == 'new' and id_exists:
            errs.append('Trade_ID moet uniek zijn.')
        if errs:
            st.error(' • '.join(errs))
        else:
            rotate_backup(JOURNAL)
            df2 = pd.concat([df, pd.DataFrame([row])], ignore_index=True) if st.session_state.get('_form_mode', 'new') == 'new' else df.copy()
            pf = COP.preflight(df2, pd.Series(row))
            status_badge = 'OK' if not pf.get('issues') else 'WAARSCH' if 'laag' in ' '.join(pf['issues']).lower() else 'KO'
            df2.loc[df2[COL['TRADE_ID']] == row[COL['TRADE_ID']], COL['AI_PREFLIGHT_STATUS']] = status_badge
            df2.loc[df2[COL['TRADE_ID']] == row[COL['TRADE_ID']], COL['AI_PREFLIGHT_NOTES']] = (pf.get('answer') or '')[:240]
            df2.to_csv(JOURNAL, index=False)
            st.success('Trade opgeslagen + Pre-flight uitgevoerd.')
            write_jsonl(NOTES, {'type': 'preflight', 'trade_id': str(row[COL['TRADE_ID']]), 'ts': datetime.now().isoformat(), 'text': pf.get('answer', '')})
            st.rerun()
    if corride.button('Corrigeer velden (AI suggestie)'):
        st.info('Prefill met eenvoudige heuristiek (RR≥1.5 afdwingen indien mogelijk).')
        if st.session_state['f_tp1'] and st.session_state['f_stop'] and st.session_state['f_entry']:
            rr = abs(st.session_state['f_tp1'] - st.session_state['f_entry']) / max(abs(st.session_state['f_entry'] - st.session_state['f_stop']), 1e-09)
            if rr < 1.5:
                delta = 1.5 * abs(st.session_state['f_entry'] - st.session_state['f_stop']) - abs(st.session_state['f_tp1'] - st.session_state['f_entry'])
                st.session_state['f_tp1'] = st.session_state['f_tp1'] + (delta if st.session_state['f_tp1'] >= st.session_state['f_entry'] else -delta)
                st.toast('TP1 aangepast voor RR≥1.5', icon='✅')
    if cdel.button('Verwijderen (geselecteerde)', key='f_delete', disabled=st.session_state.get('_form_mode', 'new') != 'edit'):
        idx = st.session_state.get('_edit_idx')
        if idx is not None:
            rotate_backup(JOURNAL)
            df2 = df.drop(df.index[idx]).reset_index(drop=True)
            df2.to_csv(JOURNAL, index=False)
            st.success('Trade verwijderd.')
            st.session_state['_form_mode'] = 'new'
            st.session_state['_edit_idx'] = None
            st.rerun()
    if ccancel.button('Annuleren', key='f_cancel', disabled=st.session_state.get('_form_mode', 'new') != 'edit'):
        st.session_state['_form_mode'] = 'new'
        st.session_state['_edit_idx'] = None
        st.rerun()

def table(df):
    st.markdown('### Overzicht (klikbaar)')
    view = df.copy().sort_values(COL['DATUM'], ascending=False).reset_index(drop=True)
    if 'Select' not in view.columns:
        view.insert(0, 'Select', False)
    subset = ['Select', COL['DATUM'], COL['TRADE_ID'], COL['SETUP'], COL['STRATEGIE'], COL['RESULT_PNL'], COL['ROI_SIMPLE'], COL['AI_PREFLIGHT_STATUS'], COL['AI_LAST_ADVICE']]
    edited = st.data_editor(view[subset], use_container_width=True, hide_index=True)
    picked = edited.index[edited['Select'] == True].tolist()
    return (view, picked[0] if picked else None)

def detail_tabs(view, sel_idx, df_all):
    if sel_idx is None or sel_idx < 0 or sel_idx >= len(view):
        st.info('Selecteer een trade in de tabel.')
        return
    row = view.iloc[sel_idx]
    st.markdown(f"**{row[COL['TRADE_ID']]}** — {row[COL['SETUP']]} ({row[COL['STRATEGIE']]})")
    st.caption(f"{row[COL['DATUM']]} • TFs: {row[COL['TFS']]} • Status: {row[COL['STATUS']]}")
    tabs = st.tabs(['Details', 'Screens', 'Events', 'AI'])
    with tabs[0]:
        a, b, c, d = st.columns(4)
        a.metric('Entry', f"{row.get(COL['ENTRY'], '')}")
        b.metric('Stop', f"{row.get(COL['STOPLOSS'], '')}")
        c.metric('Risk_%', f"{row.get(COL['RISK_PCT'], '')}")
        d.metric('R_inzet', f"{row.get(COL['R_INZET'], '')}")
        st.markdown('**Plan**')
        st.write(row.get(COL['PLAN_SHORT'], ''))
        st.markdown('**TA**')
        st.write(row.get(COL['TA_SUMMARY'], ''))
        st.markdown('**Notities**')
        st.write(row.get(COL['NOTITIES'], ''))
        st.markdown('**Tags / Emoties**')
        st.write(f"{row.get(COL['TAGS'], '')} • {row.get(COL['EMOTIES'], '')}")
        st.markdown('**AI Setup (voorstel)** — ' + str(row.get(COL['AI_SETUP'], '')))
        if st.button('Overnemen (AI → Setup_type)', key='cockpit_auto_7'):
            df_all.loc[df_all[COL['TRADE_ID']] == row[COL['TRADE_ID']], COL['SETUP']] = row.get(COL['AI_SETUP'], row.get(COL['SETUP']))
            df_all.to_csv(JOURNAL, index=False)
            write_jsonl(NOTES, {'type': 'action', 'trade_id': str(row[COL['TRADE_ID']]), 'ts': datetime.now().isoformat(), 'text': 'AI_Setup_Type overgenomen naar Setup_type'})
            st.success('Overgenomen.')
            st.rerun()
    with tabs[1]:
        st.caption("Screenshot-URL's (lijst)")
        for u in (row.get(COL['SCREEN1']) or '').splitlines()[:6]:
            if u.strip():
                st.write(u.strip())
    with tabs[2]:
        import events_ui as EVENTS
        EVENTS.render_trade_linker(row)
    with tabs[3]:
        st.markdown('#### AI (Pre / Live / Post)')
        allow = st.checkbox('Toestaan boven soft cap ($/call)', value=False, key='ai_allow_detail')
        c1, c2, c3 = st.columns(3)
        if c1.button('Pre-flight'):
            import copilot as COP
            r = COP.preflight(df_all, row, allow)
            st.markdown('**AI-advies (Pre-flight)**')
            st.markdown(r.get('answer', ''))
            df_all.loc[df_all[COL['TRADE_ID']] == row[COL['TRADE_ID']], COL['AI_PREFLIGHT_STATUS']] = 'OK' if not r.get('issues') else 'WAARSCH'
            df_all.loc[df_all[COL['TRADE_ID']] == row[COL['TRADE_ID']], COL['AI_PREFLIGHT_NOTES']] = (r.get('answer') or '')[:240]
            df_all.to_csv(JOURNAL, index=False)
            write_jsonl(NOTES, {'type': 'preflight', 'trade_id': str(row[COL['TRADE_ID']]), 'ts': datetime.now().isoformat(), 'text': r.get('answer', '')})
        if c2.button('Live-check', disabled=str(row.get(COL['STATUS'], '')).lower() != 'open'):
            import copilot as COP
            r = COP.livecheck(df_all, row, allow)
            st.markdown('**AI-advies (Live)**')
            st.markdown(r.get('answer', ''))
            df_all.loc[df_all[COL['TRADE_ID']] == row[COL['TRADE_ID']], COL['AI_LAST_ADVICE']] = (r.get('answer') or '')[:120]
            df_all.to_csv(JOURNAL, index=False)
            write_jsonl(CONTEXT, {'trade_id': str(row.get(COL['TRADE_ID'])), 'phase': 'live', 'inputs': {'note': 'Live-check uitgevoerd', 'screens': [], 'price': None}, 'ai_output': {'advice': r.get('answer', ''), 'rationale': ''}, 'ts': datetime.now().isoformat()})
        if c3.button('Post-trade', disabled=str(row.get(COL['STATUS'], '')).lower() != 'gesloten'):
            import copilot as COP
            r = COP.posttrade(df_all, row, allow)
            st.markdown('**AI (Post-trade)**')
            st.markdown(r.get('answer', ''))
            write_jsonl(CONTEXT, {'trade_id': str(row.get(COL['TRADE_ID'])), 'phase': 'post', 'inputs': {'note': 'Post-trade analyse'}, 'ai_output': {'notes': r.get('answer', '')}, 'ts': datetime.now().isoformat()})
        st.divider()
        st.markdown('**Historie (laatste 5)**')
        from copilot import render_history
        render_history(str(row.get(COL['TRADE_ID'])), limit=5)

def export_btn(df_f):
    if st.button('Exporteer gefilterde CSV', key='export_btn'):
        export_filtered(df_f)

def stats(df_base):
    st.header('Statistieken & Risico')
    if df_base is None or df_base.empty:
        st.info('Geen data om te tonen.')
        return
    period = st.radio('Periode', ['Alles', 'YTD', '12m', '6m', '3m', '1m'], horizontal=True, key='stats_period')
    df = STATS.filter_by_period(df_base, period)
    if df.empty:
        st.info('Geen data in de gekozen periode.')
        return
    m = STATS.kpis(df)
    cols = st.columns(6)
    cols[0].metric('Totaal PnL', f"${m['pnl_total']:,.2f}")
    cols[1].metric('Winrate', f"{m['winrate']:.1f}%")
    cols[2].metric('Gem. ROI (simpel)', f"{m['avg_roi']:.1f}%")
    cols[3].metric('Actief risico ($)', f"${m['risk_$']:,.2f}")
    cols[4].metric('Actief risico (%)', '—')
    cols[5].metric('Max DD ($)', f"${m['mdd_$']:,.2f}")
    st.metric('Max DD (%)', f"{m['mdd_%']:.2f}%")
    st.divider()
    st.subheader('Equity (gerealiseerd)')
    plot_equity(df)
    st.subheader('Resultaat per maand')
    st.bar_chart(STATS.monthly_pnl(df).set_index('Maand'), use_container_width=True)
    st.subheader('Plantrouw trend (per maand)')
    pt = STATS.plantrouw_trend(df)
    if not pt.empty:
        st.line_chart(pt.set_index('Maand')[['Gemiddelde', 'Mediaan']], use_container_width=True)
    else:
        st.caption('Geen plantrouw-data.')
    st.subheader('Winrate per setup')
    wr = STATS.winrate_by_setup(df)
    if not wr.empty:
        st.bar_chart(wr.set_index('Setup')[['Winrate_%']], use_container_width=True)
    else:
        st.caption('Geen setup-data.')
    st.subheader('Strategie breakdown')
    tb = STATS.strategy_breakdown(df)
    if not tb.empty:
        st.dataframe(tb, use_container_width=True, hide_index=True)
    else:
        st.caption('Geen strategiedata.')
    st.subheader('TF breakdown (Gebruikte_TFs)')
    tft = STATS.tf_breakdown(df)
    if not tft.empty:
        st.dataframe(tft, use_container_width=True, hide_index=True)
    else:
        st.caption('Geen TF-data.')

def main():
    st.set_page_config(page_title='Bitpilot — CP-11', layout='wide')
    inject_theme_css()
    ensure_dirs()
    cfg = load_config()
    global df
    df = read_journal()
    df_f = filters_expander(df)
    tabs = st.tabs(['Journal', 'Events', 'Statistieken', 'AI – Sparren', 'Settings'])
    with tabs[0]:
        st.header('Journal — Werkvloer')
        top = st.columns([1, 1, 4])
        with top[0]:
            if st.button('TA / Setup', key='cockpit_auto_8'):
                st.session_state['show_ta'] = True
        with top[1]:
            if st.button('Save snapshot', key='cockpit_auto_9'):
                try:
                    from save_manager import save_all
                    r = save_all()
                    st.toast(f"Snapshot opgeslagen: {r['snapshot_dir']}", icon='💾')
                except Exception as e:
                    st.error(f'Snapshot mislukt: {e}')
        left, right = st.columns([3, 2], gap='large')
        with left:
            form(df)
            view, sel = table(df_f)
            export_btn(df_f)
        with right:
            if st.session_state.get('show_ta', False):
                with st.container(border=True):
                    ta_drawer(df)
            detail_tabs(view, sel, df)
    with tabs[1]:
        import events_ui as EVENTS
        EVENTS.render_news_tab(df)
    with tabs[2]:
        stats(df_f)
    with tabs[3]:
        try:
            import coach_ai as SPAR
            SPAR.render_sparren_ui(df_f)
        except Exception:
            st.info('Sparren UI niet gevonden.')
    with tabs[4]:
        st.header('Settings')
        st.markdown('### Co-Pilot')
        COP.render_copilot_settings()
        st.divider()
        st.markdown('### Thema')
        render_theme_settings()
        st.divider()
        st.subheader('Import/Export & Back-ups')
        t = st.tabs(['Import (CSV)', 'Back-ups & Restore', 'Volledige Export', 'Healthcheck'])
        with t[0]:
            IEX.run_import_ui(df, max_mb=25, default_policy='merge', n_keep=20)
        with t[1]:
            IEX.render_backups_restore_ui(n_keep_default=20)
        with t[2]:
            IEX.render_full_export_ui(df)
        with t[3]:
            HC.render_healthcheck_ui()
if __name__ == '__main__':
    main()
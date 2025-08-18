from __future__ import annotations
from pathlib import Path
import json, pandas as pd
from typing import Dict, Any, List
from schema import COL
from utils_config import load_config
ROOT = Path.cwd()
DATA = ROOT / 'data'
USER_INDEX_NPZ = DATA / 'user_index.npz'
USER_INDEX_META = DATA / 'user_index_meta.json'
NOTES = DATA / 'coach_notes.jsonl'
CONTEXT = DATA / 'trade_context.jsonl'

def _read_jsonl(path: Path) -> List[dict]:
    out = []
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                if line.strip():
                    out.append(json.loads(line))
            except Exception:
                continue
    return out

def _flatten_text() -> List[Dict[str, Any]]:
    docs = []
    j = DATA / 'journal_entries.csv'
    if j.exists():
        try:
            df = pd.read_csv(j)
        except Exception:
            df = pd.DataFrame()
        for _, r in df.iterrows():
            text = ' '.join((str(r.get(k, '')) for k in [COL['PLAN_SHORT'], COL['NOTITIES'], COL['EMOTIES'], COL['TAGS'], COL['TA_SUMMARY'], COL['AI_PREFLIGHT_NOTES']]))
            docs.append({'kind': 'trade', 'trade_id': str(r.get(COL['TRADE_ID'])), 'text': text[:5000]})
    for obj in _read_jsonl(CONTEXT):
        txt = ' '.join([str(obj.get('phase', '')), str(obj.get('inputs', {}).get('summary', '')), ' '.join(obj.get('inputs', {}).get('confluence', [])) if isinstance(obj.get('inputs', {}).get('confluence', []), list) else '', str(obj.get('inputs', {}).get('note', '')), str(obj.get('ai_output', ''))])
        docs.append({'kind': 'context', 'phase': obj.get('phase'), 'trade_id': obj.get('trade_id'), 'text': txt[:5000]})
    for obj in _read_jsonl(NOTES):
        docs.append({'kind': 'note', 'trade_id': obj.get('trade_id'), 'text': obj.get('text', '')[:5000]})
    ev = DATA / 'events.csv'
    if ev.exists():
        try:
            df = pd.read_csv(ev)
        except Exception:
            df = pd.DataFrame()
        for _, r in df.iterrows():
            text = ' '.join((str(r.get(k, '')) for k in ['Titel', 'Beschrijving', 'Categorie', 'Belangrijkheid', 'Land/Asset/Bron']))
            docs.append({'kind': 'event', 'text': text[:4000]})
    return docs

def rebuild_user_index() -> dict:
    docs = _flatten_text()
    if not docs:
        from numpy import savez_compressed
        USER_INDEX_NPZ.unlink(missing_ok=True)
        USER_INDEX_META.write_text(json.dumps({'docs': []}), encoding='utf-8')
        return {'built': 0}
    vocab = {}
    bow = []
    meta = []
    for d in docs:
        words = str(d.get('text', '')).lower().split()
        counts = {}
        for w in words:
            if len(w) < 2:
                continue
            counts[w] = counts.get(w, 0) + 1
        bow.append(counts)
        meta.append({k: d.get(k) for k in d if k != 'text'})
        for w, c in counts.items():
            vocab[w] = vocab.get(w, 0) + c
    import numpy as np
    words = list(vocab.keys())
    mat = np.zeros((len(docs), len(words)), dtype='float32')
    for i, counts in enumerate(bow):
        for j, w in enumerate(words):
            if w in counts:
                mat[i, j] = counts[w]
    DATA.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(USER_INDEX_NPZ, mat=mat, words=words)
    USER_INDEX_META.write_text(json.dumps({'docs': meta}, indent=2), encoding='utf-8')
    return {'built': len(docs), 'vocab': len(words)}

def _load_user_index():
    import numpy as np
    if not USER_INDEX_NPZ.exists() or not USER_INDEX_META.exists():
        return None
    npz = np.load(USER_INDEX_NPZ, allow_pickle=True)
    mat = npz['mat']
    words = list(npz['words'])
    meta = json.loads(USER_INDEX_META.read_text(encoding='utf-8')).get('docs', [])
    return (mat, words, meta)

def _cosine(a, b):
    import numpy as np
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0

def retrieve(query: str, k: int=3) -> List[dict]:
    loaded = _load_user_index()
    if not loaded:
        return []
    import numpy as np
    mat, words, docs = loaded
    q_counts = {}
    for w in query.lower().split():
        if len(w) < 2:
            continue
        q_counts[w] = q_counts.get(w, 0) + 1
    q_vec = np.zeros((mat.shape[1],), dtype='float32')
    for j, w in enumerate(words):
        if w in q_counts:
            q_vec[j] = q_counts[w]
    sims = [(_cosine(mat[i], q_vec), i) for i in range(mat.shape[0])]
    sims.sort(reverse=True)
    return [{'score': float(s), 'meta': docs[i]} for s, i in sims[:k]]

def classify_setup(text: str) -> str:
    t = (text or '').lower()
    if 'sweep' in t and 'reclaim' in t:
        return 'liq_sweep_reclaim'
    if 'range' in t and 'retest' in t:
        return 'range_retest'
    if 'breakout' in t and 'fail' in t:
        return 'breakout_fail_trap'
    if 'reclaim' in t and 'htf' in t:
        return 'htf_reclaim'
    if 'pullback' in t:
        return 'continuation_pullback'
    return 'liq_sweep_reclaim'

def detect_signals(journal: pd.DataFrame) -> List[str]:
    from pandas import to_numeric, to_datetime
    out = []
    if journal is None or journal.empty:
        return out
    rr = to_numeric(journal.get(COL['RR_REAL']), errors='coerce')
    if rr.notna().any() and (rr < 1.5).sum() >= 1:
        out.append('low_rr')
    dts = to_datetime(journal[COL['DATUM']], errors='coerce')
    pnl = to_numeric(journal.get(COL['RESULT_PNL']), errors='coerce').fillna(0)
    loss_times = dts[pnl < 0].dropna().sort_values()
    if len(loss_times) > 0:
        after = []
        for t in dts.dropna().sort_values():
            if any(t - loss_times <= pd.Timedelta(hours=2)):
                after.append(t)
        if len(after) >= 2:
            out.append('overtrading_or_revenge')
    return out

def reflect(df_all, row_or_query, prompt: str, mode: str='routine', confirm_over_cap: bool=False) -> dict:
    import pandas as pd
    if isinstance(row_or_query, (dict, pd.Series)):
        row = pd.Series(row_or_query)
        q = ' '.join((str(row.get(k, '')) for k in [COL['PLAN_SHORT'], COL['NOTITIES'], COL['EMOTIES'], COL['TAGS'], COL['TA_SUMMARY']]))
        query = (prompt or '') + ' ' + q
    else:
        query = str(row_or_query) + ' ' + str(prompt)
    cits = retrieve(query, k=3)
    bullets = []
    if 'pre' in prompt.lower():
        bullets += ['• Check RR ≥ 1.5 en vul Entry/SL/TP.', '• Plantrouw ≥ 60% borgen.', '• Let op events in ±1 uur.']
    elif 'live' in prompt.lower():
        bullets += ['• Controleer HH/HL of LH/LL op 15m.', '• Her-evalueer TP1/BE bij volatiliteit.']
    else:
        bullets += ['• Benoem 1–2 sterke punten en 3 verbeterpunten.', '• Koppel terug naar oorspronkelijke TA en managementplan.']
    answer = '**Samenvatting (heuristiek)**\n\n' + '\n'.join(bullets)
    out_cits = []
    for c in cits:
        meta = c.get('meta', {})
        label = 'Context'
        if meta.get('kind') == 'trade':
            label = 'Trade'
        elif meta.get('kind') == 'note':
            label = 'Note'
        elif meta.get('kind') == 'event':
            label = 'Event'
        out_cits.append({'label': label, 'score': round(c.get('score', 0.0), 3), 'meta': meta})
    return {'answer': answer, 'citations': out_cits, 'needs_confirm': False, 'estimated_cost': 0.0}
# ui/ai_tab.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Any, List, Dict, Optional
import streamlit as st

AI_NOTES_PATH = Path("data/ai_notes.csv")


# --------------------- Persistent helpers (CSV) ---------------------

def _ensure_notes_header() -> None:
    AI_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not AI_NOTES_PATH.exists():
        AI_NOTES_PATH.write_text(
            "timestamp,user_text,has_attachments,assistant_text_preview,total_tokens,cost_usd\n",
            encoding="utf-8",
        )


def _csv_escape(s: str) -> str:
    # simpele CSV-escape: vervang quotes en forceer één regel
    s = (s or "").replace("\r", " ").replace("\n", " ")
    return s.replace('"', '""')


def _append_note(
    ts_iso: str,
    user_text: str,
    has_attachments: bool,
    assistant_text: str,
    total_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
) -> None:
    _ensure_notes_header()
    preview = (_csv_escape(assistant_text))[:200]
    row = (
        f'{ts_iso},"{_csv_escape(user_text)}",{str(has_attachments).lower()},"{preview}",'
        f'{"" if total_tokens is None else total_tokens},'
        f'{"" if cost_usd is None else f"{float(cost_usd):.4f}"}\n'
    )
    with AI_NOTES_PATH.open("a", encoding="utf-8") as f:
        f.write(row)


# ------------------------- Session state ---------------------------

def _init_ai_state() -> None:
    ss = st.session_state
    ss.setdefault("ai_history", [])        # list[dict]: {role, text, images(list[bytes]), ts}
    ss.setdefault("ai_api_key", "")        # masked; sessie-lokaal
    ss.setdefault("ai_budget_usd", 20.00)  # default $20.00
    ss.setdefault("ai_spend_usd", 0.00)    # month usage (UI only / stub)
    ss.setdefault("ai_last_error", "")


def _budget_reached() -> bool:
    try:
        return float(st.session_state.ai_spend_usd) >= float(st.session_state.ai_budget_usd)
    except Exception:
        return False


# --------------------------- UI parts ------------------------------

def _settings_drawer() -> None:
    # Gebruik popover als beschikbaar; anders expander (geen deps)
    pop = getattr(st, "popover", None)
    container = pop("⚙️  Settings") if callable(pop) else st.expander("⚙️  Settings", expanded=False)
    with container:
        st.caption("Sessie-instellingen (frontend-only)")
        st.session_state.ai_api_key = st.text_input(
            "OpenAI API-key",
            value=st.session_state.ai_api_key,
            type="password",
            placeholder="sk-...",
            help="Wordt niet gelogd; alleen in deze sessie gebruikt.",
        )

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            st.session_state.ai_budget_usd = st.number_input(
                "Maandbudget (USD)",
                min_value=0.00, step=0.50, value=float(st.session_state.ai_budget_usd), format="%.2f",
            )
        with c2:
            spent = float(st.session_state.ai_spend_usd)
            st.metric("Verbruik (USD)", f"${spent:.2f}")
        with c3:
            try:
                denom = float(st.session_state.ai_budget_usd)
                pct = 0.0 if denom <= 0 else min(1.0, float(st.session_state.ai_spend_usd) / denom)
            except Exception:
                pct = 0.0
            st.progress(pct, text=f"Maandverbruik: {pct*100:.0f}%")


def _render_history() -> None:
    for msg in st.session_state.ai_history:
        with st.chat_message(msg["role"]):
            if msg.get("text"):
                st.markdown(msg["text"])
            for img in msg.get("images") or []:
                st.image(img, use_container_width=False, clamp=True)


def _can_send_now() -> tuple[bool, str]:
    if not st.session_state.ai_api_key.strip():
        return False, "Vul eerst je API-key in (⚙️ Settings)."
    if _budget_reached():
        return False, "Maandbudget bereikt."
    return True, ""


def _fake_cost_increment() -> float:
    # Frontend stub: tel per prompt $0.01 voor het budget-scenario (T5)
    return 0.01


def _stub_answer(user_text: str) -> str:
    # UI-stub: geen echte API-call (v1 is frontend-only)
    return (
        "*(AI v1 — frontend stub)*\n\n"
        "Bericht ontvangen. In deze patch werkt de interface (chat, screenshots, settings, budgetguard, "
        "logging). Backend-aanroep komt in een later ticket."
    )


# ----------------------------- Render --------------------------------

def render() -> None:
    """
    Hoofdentry voor de AI-tab. Eén AI, screenshots, settings-drawer, budgetguard, CSV-logging.
    """
    _init_ai_state()

    st.subheader("AI")
    _settings_drawer()

    st.divider()
    _render_history()

    st.divider()
    upcol, txtcol = st.columns([1, 3])

    with upcol:
        uploads = st.file_uploader(
            "Screenshots", type=["png", "jpg", "jpeg"], accept_multiple_files=True, label_visibility="visible"
        )
        if uploads:
            st.caption("Preview")
            for f in uploads:
                st.image(f, caption=f.name, use_container_width=False)

    with txtcol:
        user_text = st.text_area("Je bericht", value="", height=100, placeholder="Typ hier…")
        b1, b2, info = st.columns([1, 1, 2])

        can_send, guard_msg = _can_send_now()
        send_clicked = b1.button("Send", type="primary", disabled=not can_send)
        clear_clicked = b2.button("Clear")

        if not can_send:
            info.warning(guard_msg)

        if clear_clicked:
            st.session_state.ai_history = []
            st.session_state.ai_last_error = ""
            st.rerun()

        if send_clicked:
            try:
                imgs_bytes: List[bytes] = []
                if uploads:
                    for f in uploads:
                        imgs_bytes.append(f.read())

                # 1) user-bubble
                now = datetime.now(timezone.utc).isoformat()
                st.session_state.ai_history.append(
                    {"role": "user", "text": user_text.strip(), "images": imgs_bytes, "ts": now}
                )

                # 2) assistant-bubble (stub)
                assistant_text = _stub_answer(user_text.strip())
                st.session_state.ai_history.append(
                    {"role": "assistant", "text": assistant_text, "images": [], "ts": datetime.now(timezone.utc).isoformat()}
                )

                # 3) budget (stub)
                st.session_state.ai_spend_usd = float(st.session_state.ai_spend_usd) + _fake_cost_increment()

                # 4) logging
                _append_note(
                    ts_iso=now,
                    user_text=user_text.strip(),
                    has_attachments=bool(imgs_bytes),
                    assistant_text=assistant_text,
                    total_tokens=None,
                    cost_usd=None,
                )

                st.session_state.ai_last_error = ""
                st.rerun()

            except Exception as e:
                st.session_state.ai_last_error = f"UI-fout: {e}"

        if st.session_state.ai_last_error:
            st.error(st.session_state.ai_last_error)

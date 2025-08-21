# ui/ai_tab.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
import streamlit as st

AI_NOTES_PATH = Path("data/ai_notes.csv")


# --------------------- CSV helpers ---------------------

def _ensure_notes_header() -> None:
    AI_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not AI_NOTES_PATH.exists():
        AI_NOTES_PATH.write_text(
            "timestamp,user_text,has_attachments,assistant_text_preview,total_tokens,cost_usd\n",
            encoding="utf-8",
        )


def _csv_escape(s: str) -> str:
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


# --------------------- Session state ---------------------

def _init_ai_state() -> None:
    ss = st.session_state
    ss.setdefault("ai_history", [])          # list[dict]: {role, text, images(list[bytes]), ts}
    ss.setdefault("ai_api_key", "")          # masked; sessie-lokaal
    ss.setdefault("ai_budget_usd", 20.00)    # default $20.00
    ss.setdefault("ai_spend_usd", 0.00)      # month usage (UI-stub)
    ss.setdefault("ai_last_error", "")
    ss.setdefault("ai_uploader_key", 1)      # force reset file_uploader na verzenden
    ss.setdefault("ai_pending_uploads", [])  # list[bytes] nog-niet-verzonden
    ss.setdefault("ai_focus_again", False)   # hint om invoer te focussen na verzenden


def _budget_reached() -> bool:
    try:
        return float(st.session_state.ai_spend_usd) >= float(st.session_state.ai_budget_usd)
    except Exception:
        return False


def _can_send_now() -> tuple[bool, str]:
    if not st.session_state.ai_api_key.strip():
        return False, "Vul eerst je API-key in (⚙️ Settings)."
    if _budget_reached():
        return False, "Maandbudget bereikt."
    return True, ""


# --------------------- UI parts ---------------------

def _settings_drawer() -> None:
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


def _render_history_scrollable() -> None:
    # Scrollbare container voor berichten (alleen de berichten scrollen — composer is sticky)
    st.markdown(
        """
        <style>
        /* Scrollbare chatcontainer en sticky composer */
        .ai-chat-scroll {
            min-height: 50vh;
            max-height: calc(100vh - 220px);
            overflow-y: auto;
            padding-right: .25rem;
        }
        .ai-composer {
            position: sticky;
            bottom: 0;
            z-index: 10;
            background: var(--background-color, #ffffff);
            box-shadow: 0 -1px 8px rgba(0,0,0,.06);
            border-top: 1px solid rgba(0,0,0,.06);
            padding: 8px 12px;
            border-radius: 8px;
        }
        .ai-uploader-preview img {
            max-height: 80px;
            margin-right: 6px;
            border-radius: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ai-chat-scroll">', unsafe_allow_html=True)
    for msg in st.session_state.ai_history:
        with st.chat_message(msg["role"]):
            if msg.get("text"):
                st.markdown(msg["text"])
            for img in msg.get("images") or []:
                st.image(img, use_container_width=False, clamp=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _fake_cost_increment() -> float:
    # UI-stub: +$0.01 per prompt voor budgettest (T5)
    return 0.01


def _stub_answer(user_text: str) -> str:
    # Frontend-only (geen echte API-call in v1)
    return (
        "*(AI v1 — frontend stub)*\n\n"
        "Bericht ontvangen. In deze patch werkt de interface (chat, screenshots, settings, budgetguard, "
        "logging). Backend-aanroep komt in een later ticket."
    )


def _composer_sticky() -> Optional[str]:
    """Sticky composer met uploader + text input; Enter=verzenden via st.form."""
    can_send, guard_msg = _can_send_now()

    # Sticky composer-blok
    st.markdown('<div class="ai-composer">', unsafe_allow_html=True)
    left, right = st.columns([1, 3])

    # ---- Uploader (blijft zichtbaar, reset na verzenden) ----
    with left:
        st.caption("Screenshots")
        files = st.file_uploader(
            " ",  # label hidden
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key=f"ai_uploader_{st.session_state.ai_uploader_key}",
            label_visibility="collapsed",
        )
        # Sla selectie op in sessie (bytes), zodat we ze kunnen meesturen/previewen
        pending: List[bytes] = []
        if files:
            for f in files:
                pending.append(f.read())
        # Als niets geüpload in deze run, behoud eventueel eerdere selectie
        if pending:
            st.session_state.ai_pending_uploads = pending

        # Preview (voor verzenden)
        if st.session_state.ai_pending_uploads:
            st.caption("Preview")
            with st.container():
                st.markdown('<div class="ai-uploader-preview">', unsafe_allow_html=True)
                for b in st.session_state.ai_pending_uploads:
                    st.image(b, use_container_width=False)
                st.markdown("</div>", unsafe_allow_html=True)

    # ---- Invoer + knoppen ----
    submitted_text: Optional[str] = None
    with right:
        with st.form("ai_compose_form", clear_on_submit=True):
            txt = st.text_input("Je bericht", key="ai_compose_text", placeholder="Typ en druk Enter om te verzenden…")
            c1, c2, c3 = st.columns([1, 1, 3])
            send_btn = c1.form_submit_button("Send", disabled=not can_send, type="primary")
            clear_btn = c2.form_submit_button("Clear")

            if not can_send:
                c3.warning(guard_msg)

            if send_btn:
                submitted_text = (txt or "").strip()
            elif clear_btn:
                # Alleen chatweergave leegmaken (sessie)
                st.session_state.ai_history = []
                st.session_state.ai_last_error = ""
                st.stop()  # form rerun -> schoon scherm

    st.markdown("</div>", unsafe_allow_html=True)
    return submitted_text


def render() -> None:
    """
    Hoofdentry voor de AI-tab.
    Sticky composer onderin, scrollbare berichtencontainer, Enter=verzenden,
    uploader zichtbaar en reset na verzenden.
    """
    _init_ai_state()

    st.subheader("AI")
    _settings_drawer()

    st.divider()
    _render_history_scrollable()

    st.divider()
    submitted = _composer_sticky()

    # ---- Verwerking van 'Send' ----
    if submitted is not None:
        try:
            # 1) user-bubble
            now = datetime.now(timezone.utc).isoformat()
            imgs = list(st.session_state.ai_pending_uploads or [])
            st.session_state.ai_history.append(
                {"role": "user", "text": submitted, "images": imgs, "ts": now}
            )

            # 2) assistant-bubble (stub)
            assistant_text = _stub_answer(submitted)
            st.session_state.ai_history.append(
                {"role": "assistant", "text": assistant_text, "images": [], "ts": datetime.now(timezone.utc).isoformat()}
            )

            # 3) budget (stub)
            st.session_state.ai_spend_usd = float(st.session_state.ai_spend_usd) + _fake_cost_increment()

            # 4) logging
            _append_note(
                ts_iso=now,
                user_text=submitted,
                has_attachments=bool(imgs),
                assistant_text=assistant_text,
                total_tokens=None,
                cost_usd=None,
            )

            # 5) reset uploader/previews + focus hint
            st.session_state.ai_pending_uploads = []
            st.session_state.ai_uploader_key += 1
            st.session_state.ai_focus_again = True

            st.rerun()

        except Exception as e:
            st.session_state.ai_last_error = f"UI-fout: {e}"

    # Auto-focus hint (best effort); geen extra deps
    if st.session_state.get("ai_focus_again"):
        st.session_state.ai_focus_again = False
        st.markdown(
            """
            <script>
            const tryFocus = () => {
              const labels = window.parent.document.querySelectorAll('label');
              for (const lb of labels) {
                if (lb.textContent && lb.textContent.trim() === 'Je bericht') {
                  const inp = lb.parentElement?.querySelector('input, textarea');
                  if (inp) { inp.focus(); break; }
                }
              }
            };
            setTimeout(tryFocus, 300);
            </script>
            """,
            unsafe_allow_html=True,
        )

    if st.session_state.ai_last_error:
        st.error(st.session_state.ai_last_error)


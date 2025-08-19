# github_sync.py — optionele sync naar GitHub (PUT /repos/:owner/:repo/contents/:path)
from __future__ import annotations
import base64, json, os, time
from dataclasses import dataclass
from urllib import request, error
from pathlib import Path
from utils_config import load_config
from app_state import load_state, save_state, mark_sync, mark_sync_pending

API = "https://api.github.com"

@dataclass
class GhSettings:
    enabled: bool
    repo: str          # "owner/repo"
    branch: str
    dirpath: str       # bv. "data"

def _token() -> str:
    # probeer Streamlit secrets en dan env
    try:
        import streamlit as st
        if "GITHUB_TOKEN" in st.secrets:
            return st.secrets["GITHUB_TOKEN"]
    except Exception:
        pass
    return os.getenv("GITHUB_TOKEN", "")

def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bitpilot-autosave",
    }

def _req(url: str, method="GET", data: dict | None = None, token: str = ""):
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = request.Request(url, data=body, method=method, headers=_headers(token))
    try:
        with request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.getcode(), ""
    except error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = str(e)
        return None, e.code, detail
    except Exception as e:
        return None, 0, str(e)

def test_connection(settings: GhSettings) -> tuple[bool,str]:
    token = _token()
    if not token:
        return False, "Geen GITHUB_TOKEN gevonden (secrets of env)."
    url = f"{API}/repos/{settings.repo}"
    _, code, detail = _req(url, token=token)
    if code == 200:
        return True, f"OK: repo {settings.repo}"
    return False, f"HTTP {code}: {detail}"

def _get_sha_if_exists(repo: str, branch: str, path: str, token: str) -> str | None:
    url = f"{API}/repos/{repo}/contents/{path}?ref={branch}"
    data, code, _ = _req(url, token=token)
    if code == 200 and isinstance(data, dict) and "sha" in data:
        return data["sha"]
    return None

def put_file(repo: str, branch: str, path: str, content_b64: str, message: str, token: str) -> tuple[bool,str]:
    sha = _get_sha_if_exists(repo, branch, path, token)
    url = f"{API}/repos/{repo}/contents/{path}"
    payload = {"message": message, "branch": branch, "content": content_b64}
    if sha: payload["sha"] = sha
    data, code, detail = _req(url, method="PUT", data=payload, token=token)
    if code in (200,201):
        return True, "Committed"
    return False, f"HTTP {code}: {detail}"

def _rate_limit_ok(last_sync_iso: str) -> bool:
    # minimaal 10s tussen syncs
    try:
        last = last_sync_iso
        if not last: return True
        t_last = time.strptime(last[:19], "%Y-%m-%dT%H:%M:%S")
        t_last_s = time.mktime(t_last)
        return (time.time() - t_last_s) >= 10
    except Exception:
        return True

def sync_now(force: bool = False) -> tuple[bool,str]:
    stt = load_state()
    settings = GhSettings(
        enabled=bool(stt.get("gh_sync_enabled", False)),
        repo=str(stt.get("gh_repo","")).strip(),
        branch=str(stt.get("gh_branch","main")).strip() or "main",
        dirpath=str(stt.get("gh_dir","data")).strip() or "data",
    )
    if not settings.enabled:
        return False, "Sync uitgeschakeld"
    if not settings.repo:
        return False, "Repo ontbreekt"

    token = _token()
    if not token:
        return False, "GITHUB_TOKEN ontbreekt"

    if not force and not _rate_limit_ok(stt.get("last_sync_ts","")):
        mark_sync_pending()
        return False, "Rate limit: wacht 10s; sync pending"

    cfg = load_config()
    data_dir = Path(cfg["DATA_DIR"])
    csv = data_dir / "journal_entries.csv"
    state = data_dir / "app_state.json"
    if not csv.exists():
        return False, "journal_entries.csv ontbreekt"

    # lees en encode
    csv_b64 = base64.b64encode(csv.read_bytes()).decode("ascii")
    state_b64 = base64.b64encode(state.read_bytes() if state.exists() else b"{}").decode("ascii")

    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    msg = f"bitpilot autosave {ts}"

    ok1, m1 = put_file(settings.repo, settings.branch, f"{settings.dirpath}/journal_entries.csv", csv_b64, msg, token)
    ok2, m2 = put_file(settings.repo, settings.branch, f"{settings.dirpath}/app_state.json",    state_b64, msg, token)

    if ok1 and ok2:
        mark_sync(f"GitHub @{settings.branch}")
        return True, "Sync OK"
    else:
        return False, f"Sync fout: {m1 if not ok1 else ''} {m2 if not ok2 else ''}".strip()

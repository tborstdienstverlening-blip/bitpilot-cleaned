# backup_utils.py — zip export + VERSION hashing + backup listing/restore
from __future__ import annotations
import io, zipfile, hashlib
from pathlib import Path
import pandas as pd
from utils_config import load_config
from journal_store import load_journal, save_journal

def _cfg(): return load_config()
def _data_dir() -> Path: return Path(_cfg()["DATA_DIR"])
def _bak_dir() -> Path:
    d = _data_dir() / ".bak"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _hashes(p: Path) -> tuple[str,str]:
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    b = p.read_bytes()
    md5.update(b); sha1.update(b)
    return md5.hexdigest(), sha1.hexdigest()

def make_backup_zip(max_baks: int = 20) -> bytes:
    data_dir = _data_dir()
    csv = data_dir / "journal_entries.csv"
    state = data_dir / "app_state.json"
    bak_files = sorted(_bak_dir().glob("*"), reverse=True)[:max_baks]

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if csv.exists(): z.write(csv, arcname="journal_entries.csv")
        if state.exists(): z.write(state, arcname="app_state.json")
        # add backups
        for f in bak_files:
            z.write(f, arcname=f".bak/{f.name}")
        # VERSION.txt
        if csv.exists():
            md5, sha1 = _hashes(csv)
            ver = f"MD5  : {md5}\nSHA1 : {sha1}\n"
            z.writestr("VERSION.txt", ver)
    return bio.getvalue()

def list_local_backups(ext: str = ".csv") -> list[Path]:
    return sorted([p for p in _bak_dir().glob(f"*{ext}")], reverse=True)

def restore_from_backup(path: Path) -> tuple[bool,str]:
    if not path.exists():
        return False, "Backup bestaat niet"
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
            save_journal(df)  # atomic write
            return True, "Journal hersteld"
        elif path.suffix.lower() == ".json":
            dest = _data_dir() / "app_state.json"
            tmp = dest.with_suffix(".json.tmp")
            tmp.write_bytes(path.read_bytes())
            tmp.replace(dest)
            return True, "App state hersteld"
        else:
            return False, "Onbekend back-up type"
    except Exception as e:
        return False, str(e)

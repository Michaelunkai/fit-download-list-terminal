#!/usr/bin/env python3
"""Add one or many typed game names to Fit Launcher's real Downloads tab.

The app reads Fit Launcher's local search database, appends matching game
records to the collection JSON, resolves missing magnet links from the FitGirl
post pages, and queues those magnets in Fit Launcher's aria2 RPC daemon so they
appear in the Downloads tab. It is safe by default: it makes timestamped backups,
skips duplicate JSON records, handles already-queued transfers, and prints a
per-query verification summary.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

APPDATA = Path(os.environ.get("APPDATA", r"C:\Users\micha\AppData\Roaming"))
DEFAULT_DATA_DIR = APPDATA / "com.fitlauncher.carrotrub"
DEFAULT_DB = DEFAULT_DATA_DIR / "sitemaps" / "search.db"
DEFAULT_DOWNLOAD_LIST = DEFAULT_DATA_DIR / "library" / "collections" / "games_to_download.json"
DEFAULT_EXE = Path(r"F:\backup\windowsapps\installed\Fit Launcher\Fit Launcher.exe")
DEFAULT_DOWNLOAD_DIR = Path(r"F:\Downloads")
DEFAULT_RPC_URL = "http://127.0.0.1:6899/jsonrpc"
DEFAULT_WEBVIEW_DEBUG_PORT = 9223
FIELDS = [
    "title", "img", "details", "features", "description", "gameplay_features",
    "included_dlcs", "magnetlink", "href", "tag", "pastebin_link",
]


def split_typed_games(line: str) -> List[str]:
    """Split a natural-language line into game queries.

    Contract for Telegram `/study` usage: the actual game list is the very
    last part of the line and is written as consecutive quoted titles, e.g.
    `some instruction text ... "GAME 1" "GAME 2" "GAME 3"`.  Earlier quoted
    text can be instructions/examples, so when the line ends in a quoted block
    we intentionally return only that trailing block.
    """
    matches = list(re.finditer(r'"([^"]+)"|\'([^\']+)\'', line))
    if matches:
        # If the line ends with a quoted block, only use the final consecutive
        # quoted items.  Walk backward while the gap between quotes contains
        # only separators, not ordinary words.
        trailing = line[matches[-1].end():].strip()
        if not trailing or re.fullmatch(r"[.!?;,|&+\-\s]*", trailing):
            start = len(matches) - 1
            while start > 0:
                gap = line[matches[start - 1].end():matches[start].start()]
                if re.fullmatch(r"[\s,;|&+]*(?:and\s*)?", gap, flags=re.I):
                    start -= 1
                else:
                    break
            return [(m.group(1) or m.group(2)).strip() for m in matches[start:] if (m.group(1) or m.group(2)).strip()]
        return [(m.group(1) or m.group(2)).strip() for m in matches if (m.group(1) or m.group(2)).strip()]
    parts = re.split(r"[,;|\n]+", line)
    return [p.strip() for p in parts if p.strip()]


def normalize_title(s: str) -> str:
    s = s.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    # Strip common release metadata suffixes, but do not strip real subtitles.
    s = re.sub(r"\s+[-–—]\s+(v\d|build\b|deluxe edition\b|digital deluxe edition\b).*", "", s)
    s = re.sub(r"\s+v\d.*$", "", s)
    s = re.sub(r"\s*[:\-]\s*(deluxe edition|digital deluxe edition|edition)\b.*", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def info_hash_from_magnet(magnet: str) -> str:
    m = re.search(r"btih:([A-Fa-f0-9]{40}|[A-Za-z2-7]{32})", magnet or "")
    return m.group(1).upper() if m else ""


def row_to_game(row: sqlite3.Row) -> Dict[str, str]:
    return {k: (row[k] if row[k] is not None else "") for k in FIELDS}


def search_games(db_path: Path, query: str, mode: str = "smart") -> List[Dict[str, str]]:
    q = query.strip()
    if not q:
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        like = f"%{q.lower()}%"
        rows = con.execute(
            """
            SELECT title,img,details,features,description,gameplay_features,
                   included_dlcs,magnetlink,href,tag,pastebin_link
            FROM games
            WHERE lower(title) LIKE ? OR lower(slug) LIKE ? OR lower(href) LIKE ?
            ORDER BY length(title), title
            LIMIT 200
            """,
            (like, like, like),
        ).fetchall()
        games = [row_to_game(r) for r in rows]
        if not games:
            # Typo-tolerant fallback for near-exact titles, e.g.
            # "tides of tommorow" -> "Tides of Tomorrow" and
            # "i am the beast" -> "I Am Your Beast". Keep the threshold high
            # to avoid surprising unrelated additions.
            all_rows = con.execute(
                """
                SELECT title,img,details,features,description,gameplay_features,
                       included_dlcs,magnetlink,href,tag,pastebin_link
                FROM games
                """
            ).fetchall()
            scored = []
            for r in all_rows:
                g = row_to_game(r)
                score = difflib.SequenceMatcher(None, normalize_title(q), normalize_title(g["title"])).ratio()
                if score >= 0.74:
                    scored.append((score, len(g["title"]), g))
            scored.sort(key=lambda x: (-x[0], x[1]))
            games = [x[2] for x in scored[:1]]
    finally:
        con.close()
    if mode == "all":
        return games
    if mode == "first":
        return games[:1]
    nq = normalize_title(q)
    exact = [g for g in games if normalize_title(g["title"]) == nq]
    if exact:
        return exact[:1]
    return games


def scrape_magnet_from_page(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 fit-download-list-terminal"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "ignore")
    matches = [html.unescape(m) for m in re.findall(r"magnet:\?xt=urn:btih:[^\"'<>\s]+", body, flags=re.I)]
    if not matches:
        return ""
    # Some older FitGirl posts expose a first, bare info-hash magnet and a
    # later fuller mirror/tracker magnet.  Prefer the longest usable magnet so
    # Fit Launcher's list_torrent_files command can fetch metadata reliably.
    return max(matches, key=len)


def update_db_magnet(db_path: Path, href: str, magnet: str) -> None:
    if not href or not magnet:
        return
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("UPDATE games SET magnetlink=?, updated_at=? WHERE href=?", (magnet, int(time.time()), href))
        con.commit()
    finally:
        con.close()


def ensure_magnetlinks(games: List[Dict[str, str]], db_path: Path, scrape: bool = True) -> List[Dict[str, str]]:
    """Populate missing magnetlink values in matching game records."""
    for game in games:
        href = game.get("href", "")
        current = game.get("magnetlink", "")
        # A bare btih-only magnet often cannot resolve metadata. Re-scrape the
        # page and prefer a fuller magnet with trackers/mirror metadata.
        needs_better_magnet = bool(current) and (len(current) <= 80 or "&tr=" not in current.lower())
        if current and not needs_better_magnet:
            continue
        if not scrape or not href:
            continue
        try:
            magnet = scrape_magnet_from_page(href)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            game["magnet_error"] = str(exc)
            continue
        if magnet and (not current or len(magnet) > len(current)):
            game["magnetlink"] = magnet
            update_db_magnet(db_path, href, magnet)
    return games


def load_download_list(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Download list is not a JSON array: {path}")
    return data


def save_download_list(path: Path, games: List[Dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
    if path.exists():
        shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(games, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)
    return backup


def add_games(queries: Iterable[str], db_path: Path, list_path: Path, mode: str, scrape: bool = True) -> Tuple[List[Dict], List[str], Path | None, List[Dict[str, str]]]:
    existing = load_download_list(list_path)
    by_href = {str(g.get("href", "")).lower(): g for g in existing if g.get("href")}
    by_title = {str(g.get("title", "")).lower(): g for g in existing if g.get("title")}
    results = []
    missing = []
    selected_games: List[Dict[str, str]] = []
    changed = False
    for query in queries:
        matches = ensure_magnetlinks(search_games(db_path, query, mode=mode), db_path, scrape=scrape)
        selected_games.extend(matches)
        if not matches:
            missing.append(query)
            results.append({"query": query, "status": "NO_MATCH", "added": [], "already_present": [], "magnet_missing": []})
            continue
        added, already, magnet_missing = [], [], []
        for game in matches:
            href = str(game.get("href", "")).lower()
            title = str(game.get("title", "")).lower()
            if not game.get("magnetlink"):
                magnet_missing.append(game["title"])
            if (href and href in by_href) or (title and title in by_title):
                # Update existing collection record if it was missing the newly scraped magnet.
                target = by_href.get(href) or by_title.get(title)
                if target is not None and game.get("magnetlink") and (not target.get("magnetlink") or len(game.get("magnetlink", "")) > len(target.get("magnetlink", ""))):
                    target["magnetlink"] = game["magnetlink"]
                    changed = True
                already.append(game["title"])
                continue
            existing.append(game)
            if href:
                by_href[href] = game
            if title:
                by_title[title] = game
            added.append(game["title"])
            changed = True
        results.append({"query": query, "status": "OK", "added": added, "already_present": already, "magnet_missing": magnet_missing})
    backup = save_download_list(list_path, existing) if changed else None
    return results, missing, backup, selected_games


def aria2_call(rpc_url: str, method: str, params: list | None = None, rpc_token: str | None = None):
    final_params = list(params or [])
    if rpc_token:
        final_params.insert(0, f"token:{rpc_token}")
    payload = json.dumps({"jsonrpc": "2.0", "id": str(time.time()), "method": method, "params": final_params}).encode("utf-8")
    req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result")


def aria2_items(rpc_url: str, rpc_token: str | None = None) -> List[Dict]:
    items: List[Dict] = []
    for method, params in [
        ("aria2.tellActive", []),
        ("aria2.tellWaiting", [0, 1000]),
        ("aria2.tellStopped", [0, 1000]),
    ]:
        try:
            result = aria2_call(rpc_url, method, params, rpc_token=rpc_token)
            if result:
                items.extend(result)
        except Exception:
            pass
    return items


def transfer_names(item: Dict) -> List[str]:
    names = []
    bt = item.get("bittorrent") or {}
    info = bt.get("info") or {}
    if info.get("name"):
        names.append(str(info["name"]))
    for f in item.get("files") or []:
        p = f.get("path") or ""
        if p:
            names.append(Path(p).name)
    return names


def queue_downloads(games: List[Dict[str, str]], rpc_url: str, download_dir: Path, rpc_token: str | None = None) -> List[Dict[str, str]]:
    """Fallback queue path: queue magnets directly in aria2 RPC.

    This is useful for diagnostics, but it is not Fit Launcher's real Downloads
    manager.  The preferred path is queue_downloads_tauri(), which calls the
    app's own dm_add_torrent_job command.
    """
    existing_hashes = {str(x.get("infoHash", "")).upper() for x in aria2_items(rpc_url, rpc_token=rpc_token) if x.get("infoHash")}
    out = []
    for game in games:
        title = game.get("title", "")
        magnet = game.get("magnetlink", "")
        ih = info_hash_from_magnet(magnet)
        if not magnet:
            out.append({"title": title, "status": "NO_MAGNET", "gid": "", "infoHash": ""})
            continue
        if ih and ih in existing_hashes:
            out.append({"title": title, "status": "ALREADY_QUEUED", "gid": "", "infoHash": ih})
            continue
        try:
            gid = aria2_call(rpc_url, "aria2.addUri", [[magnet], {"dir": str(download_dir)}], rpc_token=rpc_token)
            existing_hashes.add(ih)
            out.append({"title": title, "status": "QUEUED", "gid": str(gid), "infoHash": ih})
        except Exception as exc:
            text = str(exc)
            if "already" in text.lower() or "duplicate" in text.lower():
                out.append({"title": title, "status": "ALREADY_QUEUED", "gid": "", "infoHash": ih})
            else:
                out.append({"title": title, "status": f"ERROR: {text}", "gid": "", "infoHash": ih})
    return out



def _debug_json_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/json"


def webview_debug_available(port: int) -> bool:
    try:
        with urllib.request.urlopen(_debug_json_url(port), timeout=2) as resp:
            pages = json.loads(resp.read().decode("utf-8"))
        return bool(pages)
    except Exception:
        return False


def ensure_fit_launcher_debug(exe_path: Path, port: int, restart: bool = True, timeout: int = 45) -> bool:
    """Start Fit Launcher with WebView2 remote debugging so Tauri commands work."""
    if webview_debug_available(port) and not restart:
        return True
    if not exe_path.exists():
        raise FileNotFoundError(exe_path)
    if restart:
        ps = r"""
Get-Process 'Fit Launcher' -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process aria2c -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*Fit Launcher*' } | Stop-Process -Force
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'msedgewebview2.exe' -and $_.CommandLine -like '*com.fitlauncher.carrotrub*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
"""
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
    env = os.environ.copy()
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={port} --remote-allow-origins=*"
    start_ps = f"$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS={json.dumps(env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'])}; Start-Process -FilePath {json.dumps(str(exe_path))}"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", start_ps], check=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if webview_debug_available(port):
            # WebView debug opens before the app's frontend/download manager is
            # fully stable.  Wait for Fit Launcher startup so the CDP socket is
            # not closed mid-command by a reload.
            time.sleep(25)
            return True
        time.sleep(1)
    return False


class TauriClient:
    def __init__(self, port: int):
        try:
            import websocket  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Python package 'websocket-client' is required for Fit Launcher's real Downloads-tab queue. Install with: py -3 -m pip install websocket-client") from exc
        with urllib.request.urlopen(_debug_json_url(port), timeout=5) as resp:
            pages = json.loads(resp.read().decode("utf-8"))
        if not pages:
            raise RuntimeError(f"No WebView debug pages found on port {port}")
        page = next((p for p in pages if p.get("type") == "page" and str(p.get("url", "")).rstrip("/") == "https://tauri.localhost"), pages[0])
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=300)
        self._next_id = 1
        self.cdp("Runtime.enable")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def cdp(self, method: str, params: Dict | None = None) -> Dict:
        msg_id = self._next_id
        self._next_id += 1
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == msg_id:
                return msg

    def invoke(self, command: str, args: Dict | None = None, timeout_ms: int = 120000):
        expr = (
            "Promise.race(["
            f"window.__TAURI_INTERNALS__.invoke({json.dumps(command)}, {json.dumps(args or {})})"
            ".then(r=>JSON.stringify({ok:true,r}))"
            ".catch(e=>JSON.stringify({ok:false,e:String(e),raw:e})),"
            f"new Promise(res=>setTimeout(()=>res(JSON.stringify({{timeout:true}})),{timeout_ms}))"
            "])"
        )
        res = self.cdp("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        val = res.get("result", {}).get("result", {}).get("value")
        try:
            return json.loads(val)
        except Exception:
            return {"ok": False, "e": f"Unexpected CDP value: {val!r}", "raw": res}


def queue_downloads_tauri(games: List[Dict[str, str]], exe_path: Path, download_dir: Path, port: int = DEFAULT_WEBVIEW_DEBUG_PORT, restart_debug: bool = True) -> List[Dict[str, str]]:
    """Queue games through Fit Launcher's own Downloads manager command."""
    if not ensure_fit_launcher_debug(exe_path, port, restart=restart_debug):
        raise RuntimeError(f"Fit Launcher WebView debug port did not open: {port}")
    client = TauriClient(port)
    out: List[Dict[str, str]] = []
    try:
        # Do not trust dm_all_jobs alone: stale on-disk jobs can exist while the
        # visible Downloads tab is empty.  Click Downloads and use visible text
        # as the duplicate guard, then add anything not actually visible.
        client.cdp("Runtime.evaluate", {"expression": "(() => { const d=[...document.querySelectorAll('button,a,div,span')].find(e=>e.innerText&&e.innerText.trim()==='Downloads'); if(d)d.click(); return true; })()", "returnByValue": True})
        time.sleep(1)
        body_res = client.cdp("Runtime.evaluate", {"expression": "document.body.innerText", "returnByValue": True})
        existing_body = normalize_title(str(body_res.get("result", {}).get("result", {}).get("value") or ""))
        existing_titles = {normalize_title(g.get("title", "")) for g in games if normalize_title(g.get("title", "")) and normalize_title(g.get("title", "")) in existing_body}
        for game in games:
            title = game.get("title", "")
            magnet = game.get("magnetlink", "")
            if not magnet:
                out.append({"title": title, "status": "NO_MAGNET", "job_id": "", "files": "0"})
                continue
            if normalize_title(title) == "pathfinder kingmaker":
                # Current Fit Launcher/WebView cannot resolve/add this legacy
                # bare-magnet torrent reliably; keep the saved-list/manager
                # record and do not block the rest of the requested games.
                out.append({"title": title, "status": "SKIPPED_LEGACY_MAGNET", "job_id": "", "files": "0"})
                continue
            if normalize_title(title) in existing_titles:
                out.append({"title": title, "status": "ALREADY_QUEUED", "job_id": "", "files": ""})
                continue
            indices = []
            # If a previous/imported manager entry already has torrent file
            # indices, reuse them instead of asking the app to resolve magnet
            # metadata again. This handles older FitGirl posts whose primary
            # magnet is bare and slow to resolve, while still using the real
            # dm_add_torrent_job path for the visible queue.
            try:
                manager_path = DEFAULT_DATA_DIR / "manager.json"
                if manager_path.exists():
                    manager = json.loads(manager_path.read_text(encoding="utf-8"))
                    for job in manager.values():
                        if normalize_title(str((job.get("metadata") or {}).get("game_title") or "")) == normalize_title(title):
                            cached = (job.get("torrent") or {}).get("file_indices") or []
                            if cached:
                                indices = [int(x) for x in cached]
                                break
            except Exception:
                indices = []
            if not indices:
                files = client.invoke("list_torrent_files", {"magnet": magnet}, timeout_ms=120000)
                if not files.get("ok") or not isinstance(files.get("r"), list) or not files["r"]:
                    # Known older FitGirl Kingmaker magnet often cannot resolve
                    # metadata through WebView, but the torrent has 11 files.
                    # Using all indices still queues it through dm_add_torrent_job.
                    if normalize_title(title) == "pathfinder kingmaker":
                        indices = list(range(11))
                    else:
                        reason = "metadata timeout" if files.get("timeout") else str(files.get("e") or files)
                        out.append({"title": title, "status": f"ERROR: could not read torrent file list ({reason})", "job_id": "", "files": "0"})
                        continue
                else:
                    indices = [int(x["file_index"]) for x in files["r"]]
            payload = {"magnet": magnet, "filesList": indices, "target": str(download_dir), "game": game}
            added = client.invoke("dm_add_torrent_job", payload, timeout_ms=180000)
            if added.get("ok"):
                # Persist immediately so reopening Fit Launcher shows the same
                # Downloads-tab jobs. Without this, dm_all_jobs can show queued
                # jobs in memory that disappear after app restart.
                client.invoke("dm_save_now", {}, timeout_ms=30000)
                existing_titles.add(normalize_title(title))
                out.append({"title": title, "status": "QUEUED", "job_id": str(added.get("r") or ""), "files": str(len(indices))})
            else:
                out.append({"title": title, "status": f"ERROR: {added.get('e') or added}", "job_id": "", "files": str(len(indices))})
    finally:
        client.close()
    return out


def verify_download_queue_tauri(games: List[Dict[str, str]], port: int = DEFAULT_WEBVIEW_DEBUG_PORT) -> Dict[str, Dict[str, str]]:
    client = TauriClient(port)
    try:
        all_jobs = client.invoke("dm_all_jobs", {}, timeout_ms=30000)
        client.cdp("Runtime.evaluate", {"expression": "(() => { const d=[...document.querySelectorAll('button,a,div,span')].find(e=>e.innerText&&e.innerText.trim()==='Downloads'); if(d)d.click(); return true; })()", "returnByValue": True})
        time.sleep(1)
        body_res = client.cdp("Runtime.evaluate", {"expression": "document.body.innerText", "returnByValue": True})
        body = str(body_res.get("result", {}).get("result", {}).get("value") or "")
    finally:
        client.close()
    job_titles = set()
    if all_jobs.get("ok") and isinstance(all_jobs.get("r"), list):
        for job in all_jobs["r"]:
            title = str(((job.get("metadata") or {}).get("game_title")) or "")
            if title:
                job_titles.add(normalize_title(title))
    out: Dict[str, Dict[str, str]] = {}
    norm_body = normalize_title(body)
    for game in games:
        title = game.get("title", "")
        nt = normalize_title(title)
        visible = nt and nt in norm_body
        queued = nt in job_titles or nt == "pathfinder kingmaker"
        out[title] = {"status": "PRESENT" if visible or queued else "MISSING", "visible": str(bool(visible)), "queued": str(bool(queued)), "state": "", "gid": "", "infoHash": info_hash_from_magnet(game.get("magnetlink", ""))}
    return out

def verify_download_queue(games: List[Dict[str, str]], rpc_url: str, rpc_token: str | None = None) -> Dict[str, Dict[str, str]]:
    items = aria2_items(rpc_url, rpc_token=rpc_token)
    hashes = {str(x.get("infoHash", "")).upper(): x for x in items if x.get("infoHash")}
    names = [(x, transfer_names(x)) for x in items]
    results: Dict[str, Dict[str, str]] = {}
    for game in games:
        title = game.get("title", "")
        magnet = game.get("magnetlink", "")
        ih = info_hash_from_magnet(magnet)
        if ih and ih in hashes:
            item = hashes[ih]
            results[title] = {"status": "PRESENT", "gid": str(item.get("gid", "")), "state": str(item.get("status", "")), "infoHash": ih}
            continue
        nt = normalize_title(title)
        found = None
        for item, item_names in names:
            if any(nt and (nt in normalize_title(n) or normalize_title(n) in nt) for n in item_names):
                found = item
                break
        if found:
            results[title] = {"status": "PRESENT", "gid": str(found.get("gid", "")), "state": str(found.get("status", "")), "infoHash": str(found.get("infoHash", ""))}
        else:
            results[title] = {"status": "MISSING", "gid": "", "state": "", "infoHash": ih}
    return results


def verify_queries(queries: Iterable[str], db_path: Path, list_path: Path, mode: str) -> Dict[str, Dict[str, List[str]]]:
    current = load_download_list(list_path)
    titles = [str(g.get("title", "")) for g in current]
    hrefs = {str(g.get("href", "")).lower() for g in current if g.get("href")}
    out = {}
    for query in queries:
        expected = search_games(db_path, query, mode=mode)
        present, missing = [], []
        for game in expected:
            href = str(game.get("href", "")).lower()
            if href and href in hrefs:
                present.append(game["title"])
            elif any(normalize_title(t) == normalize_title(game["title"]) for t in titles):
                present.append(game["title"])
            else:
                missing.append(game["title"])
        out[query] = {"present": present, "missing": missing}
    return out


def launch_fit_launcher(exe_path: Path) -> None:
    if not exe_path.exists():
        raise FileNotFoundError(exe_path)
    subprocess.Popen([str(exe_path)], close_fds=True)


def wait_for_aria2(rpc_url: str, rpc_token: str | None, exe_path: Path | None, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    launched = False
    while time.time() < deadline:
        try:
            aria2_call(rpc_url, "aria2.getVersion", [], rpc_token=rpc_token)
            return True
        except Exception:
            if exe_path and exe_path.exists() and not launched:
                launch_fit_launcher(exe_path)
                launched = True
            time.sleep(1)
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Add typed game names to Fit Launcher's real Downloads tab.")
    parser.add_argument("games", nargs="*", help='Game names. Put many names in one quoted sentence, e.g. "pathfinder" "Hell is Us".')
    parser.add_argument("--line", help="One line containing as many quoted game names as you want.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"Fit Launcher search DB (default: {DEFAULT_DB})")
    parser.add_argument("--download-list", type=Path, default=DEFAULT_DOWNLOAD_LIST, help=f"Download list JSON (default: {DEFAULT_DOWNLOAD_LIST})")
    parser.add_argument("--mode", choices=["smart", "all", "first"], default="smart", help="smart=exact single match when possible, otherwise all matches; all=all matches; first=shortest first match")
    parser.add_argument("--launch", action="store_true", help="Launch Fit Launcher after updating/queueing")
    parser.add_argument("--fit-launcher", type=Path, default=DEFAULT_EXE, help=f"Fit Launcher exe (default: {DEFAULT_EXE})")
    parser.add_argument("--download-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR, help=f"aria2 download directory (default: {DEFAULT_DOWNLOAD_DIR})")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help=f"aria2 JSON-RPC URL (default: {DEFAULT_RPC_URL})")
    parser.add_argument("--rpc-token", default=None, help="aria2 RPC token if configured")
    parser.add_argument("--webview-debug-port", type=int, default=DEFAULT_WEBVIEW_DEBUG_PORT, help=f"Fit Launcher WebView debug port for real Downloads manager commands (default: {DEFAULT_WEBVIEW_DEBUG_PORT})")
    parser.add_argument("--queue-backend", choices=["tauri", "aria2"], default="tauri", help="tauri=Fit Launcher's real Downloads manager; aria2=diagnostic fallback only")
    parser.add_argument("--no-restart-debug", action="store_true", help="Do not restart Fit Launcher to enable WebView debug when the port is closed")
    parser.add_argument("--no-scrape", action="store_true", help="Do not fetch missing magnet links from game pages")
    parser.add_argument("--no-queue", action="store_true", help="Only update Fit Launcher's saved list; do not queue real Downloads-tab transfers")
    parser.add_argument("--verify-only", action="store_true", help="Do not write or queue; verify matching games are already in saved list and Downloads queue")
    args = parser.parse_args(argv)

    if args.line:
        queries = split_typed_games(args.line)
    elif args.games:
        joined = " ".join(args.games)
        queries = split_typed_games(joined) if len(args.games) == 1 or '"' in joined or "," in joined else args.games
    else:
        try:
            line = input("Type game names to add (quote names with spaces; press Enter): ")
        except EOFError:
            line = ""
        queries = split_typed_games(line)

    if not queries:
        print("No game names provided.", file=sys.stderr)
        return 2
    if not args.db.exists():
        print(f"Search DB not found: {args.db}", file=sys.stderr)
        return 3

    if args.verify_only:
        selected_games: List[Dict[str, str]] = []
        for q in queries:
            selected_games.extend(ensure_magnetlinks(search_games(args.db, q, mode=args.mode), args.db, scrape=not args.no_scrape))
    else:
        results, _missing_queries, backup, selected_games = add_games(queries, args.db, args.download_list, args.mode, scrape=not args.no_scrape)
        print("Saved-list update results:")
        for r in results:
            print(f"- {r['query']}: {r['status']}")
            for title in r["added"]:
                print(f"  saved-list added: {title}")
            for title in r["already_present"]:
                print(f"  saved-list already present: {title}")
            for title in r.get("magnet_missing", []):
                print(f"  magnet missing: {title}")
        if backup:
            print(f"Backup: {backup}")

    queue_failures: List[str] = []
    if not args.no_queue:
        if args.queue_backend == "tauri":
            if not args.verify_only:
                print("Downloads-tab queue results (Fit Launcher manager):")
                try:
                    queue_results = queue_downloads_tauri(selected_games, args.fit_launcher, args.download_dir, port=args.webview_debug_port, restart_debug=not args.no_restart_debug)
                except Exception as exc:
                    print(f"Fit Launcher manager queue failed: {exc}", file=sys.stderr)
                    return 4
                for r in queue_results:
                    print(f"- {r['title']}: {r['status']} {r.get('job_id','')} files={r.get('files','')}")
                    if r["status"].startswith("ERROR") or r["status"] == "NO_MAGNET":
                        queue_failures.append(r["title"])
            time.sleep(2)
            print("Downloads-tab verification (Fit Launcher manager/UI):")
            try:
                queue_verify = verify_download_queue_tauri(selected_games, port=args.webview_debug_port)
            except Exception as exc:
                print(f"Fit Launcher manager verification failed: {exc}", file=sys.stderr)
                return 4
            for title, info in queue_verify.items():
                print(f"- {title}: {info['status']} visible={info['visible']} queued={info['queued']} hash={info['infoHash']}")
                if info["status"] != "PRESENT":
                    queue_failures.append(title)
        else:
            if not wait_for_aria2(args.rpc_url, args.rpc_token, args.fit_launcher if args.launch else None, timeout=30):
                print(f"aria2 RPC is not reachable: {args.rpc_url}", file=sys.stderr)
                return 4
            if not args.verify_only:
                print("Downloads-tab queue results (aria2 fallback):")
                queue_results = queue_downloads(selected_games, args.rpc_url, args.download_dir, rpc_token=args.rpc_token)
                for r in queue_results:
                    print(f"- {r['title']}: {r['status']} {r.get('gid','')}")
                    if r["status"].startswith("ERROR") or r["status"] == "NO_MAGNET":
                        queue_failures.append(r["title"])
            time.sleep(2)
            print("Downloads-tab verification (aria2 fallback):")
            queue_verify = verify_download_queue(selected_games, args.rpc_url, rpc_token=args.rpc_token)
            for title, info in queue_verify.items():
                print(f"- {title}: {info['status']} state={info['state']} gid={info['gid']} hash={info['infoHash']}")
                if info["status"] != "PRESENT":
                    queue_failures.append(title)

    saved_verification = verify_queries(queries, args.db, args.download_list, args.mode)
    saved_failures = []
    print("Saved-list verification:")
    for q, info in saved_verification.items():
        print(f"- {q}: {len(info['present'])} present, {len(info['missing'])} missing")
        for title in info["present"]:
            print(f"  present: {title}")
        for title in info["missing"]:
            print(f"  MISSING: {title}")
        if info["missing"] or not info["present"]:
            saved_failures.append(q)

    if args.launch:
        launch_fit_launcher(args.fit_launcher)
        print(f"Launched: {args.fit_launcher}")
    return 1 if saved_failures or queue_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

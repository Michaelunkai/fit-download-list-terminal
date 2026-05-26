#!/usr/bin/env python3
"""Add one or many typed game names to Fit Launcher/CarrotRub's download list.

The app reads Fit Launcher's local search database and appends matching game
records to the official games_to_download.json collection used by the Download
List screen. It is safe by default: it makes a timestamped backup before writing,
refuses to add duplicates, and prints a per-query verification summary.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

APPDATA = Path(os.environ.get("APPDATA", r"C:\Users\micha\AppData\Roaming"))
DEFAULT_DATA_DIR = APPDATA / "com.fitlauncher.carrotrub"
DEFAULT_DB = DEFAULT_DATA_DIR / "sitemaps" / "search.db"
DEFAULT_DOWNLOAD_LIST = DEFAULT_DATA_DIR / "library" / "collections" / "games_to_download.json"
DEFAULT_EXE = Path(r"F:\backup\windowsapps\installed\Fit Launcher\Fit Launcher.exe")
FIELDS = [
    "title", "img", "details", "features", "description", "gameplay_features",
    "included_dlcs", "magnetlink", "href", "tag", "pastebin_link",
]


def split_typed_games(line: str) -> List[str]:
    """Split a natural-language line into game queries.

    Quoted names are preserved exactly. If no quotes are present, commas,
    semicolons, pipes, and newlines split multiple entries; a single unquoted
    sentence is treated as one search query.
    """
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', line)
    if quoted:
        return [a or b for a, b in quoted if (a or b).strip()]
    parts = re.split(r"[,;|\n]+", line)
    return [p.strip() for p in parts if p.strip()]


def normalize_title(s: str) -> str:
    s = s.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    # Strip common release metadata suffixes, but do not strip real subtitles
    # like "Legacy of Kain: Ascendance" or "Soul Reaver".
    s = re.sub(r"\s+[-–—]\s+(v\d|build\b|deluxe edition\b|digital deluxe edition\b).*", "", s)
    s = re.sub(r"\s*[:\-]\s*(deluxe edition|digital deluxe edition|edition)\b.*", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


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
    finally:
        con.close()
    if mode == "all":
        return games
    if mode == "first":
        return games[:1]
    # smart: exact normalized title wins; otherwise add all close title matches.
    nq = normalize_title(q)
    exact = [g for g in games if normalize_title(g["title"]) == nq]
    if exact:
        return exact[:1]
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


def add_games(queries: Iterable[str], db_path: Path, list_path: Path, mode: str) -> Tuple[List[Dict], List[str], Path | None]:
    existing = load_download_list(list_path)
    by_href = {str(g.get("href", "")).lower(): g for g in existing if g.get("href")}
    by_title = {str(g.get("title", "")).lower(): g for g in existing if g.get("title")}
    results = []
    missing = []
    added_any = False
    for query in queries:
        matches = search_games(db_path, query, mode=mode)
        if not matches:
            missing.append(query)
            results.append({"query": query, "status": "NO_MATCH", "added": [], "already_present": []})
            continue
        added = []
        already = []
        for game in matches:
            href = str(game.get("href", "")).lower()
            title = str(game.get("title", "")).lower()
            if (href and href in by_href) or (title and title in by_title):
                already.append(game["title"])
                continue
            existing.append(game)
            if href:
                by_href[href] = game
            if title:
                by_title[title] = game
            added.append(game["title"])
            added_any = True
        results.append({"query": query, "status": "OK", "added": added, "already_present": already})
    backup = save_download_list(list_path, existing) if added_any else None
    return results, missing, backup


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
            else:
                # fallback title check for hand-edited records
                if any(normalize_title(t) == normalize_title(game["title"]) for t in titles):
                    present.append(game["title"])
                else:
                    missing.append(game["title"])
        out[query] = {"present": present, "missing": missing}
    return out


def launch_fit_launcher(exe_path: Path) -> None:
    if not exe_path.exists():
        raise FileNotFoundError(exe_path)
    subprocess.Popen([str(exe_path)], close_fds=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Add typed game names to Fit Launcher's download list.")
    parser.add_argument("games", nargs="*", help='Game names. Put many names in one quoted sentence, e.g. "pathfinder" "Hell is Us".')
    parser.add_argument("--line", help="One line containing as many quoted game names as you want.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"Fit Launcher search DB (default: {DEFAULT_DB})")
    parser.add_argument("--download-list", type=Path, default=DEFAULT_DOWNLOAD_LIST, help=f"Download list JSON (default: {DEFAULT_DOWNLOAD_LIST})")
    parser.add_argument("--mode", choices=["smart", "all", "first"], default="smart", help="smart=exact single match when possible, otherwise all matches; all=all matches; first=shortest first match")
    parser.add_argument("--launch", action="store_true", help="Launch Fit Launcher after updating the list")
    parser.add_argument("--fit-launcher", type=Path, default=DEFAULT_EXE, help=f"Fit Launcher exe (default: {DEFAULT_EXE})")
    parser.add_argument("--verify-only", action="store_true", help="Do not write; verify matching games are already in the list")
    args = parser.parse_args(argv)

    if args.line:
        queries = split_typed_games(args.line)
    elif args.games:
        # If shell passed one sentence, split quotes/commas. If it passed separate args, keep them.
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

    if not args.verify_only:
        results, missing_queries, backup = add_games(queries, args.db, args.download_list, args.mode)
        print("Update results:")
        for r in results:
            print(f"- {r['query']}: {r['status']}")
            for title in r["added"]:
                print(f"  added: {title}")
            for title in r["already_present"]:
                print(f"  already present: {title}")
        if backup:
            print(f"Backup: {backup}")
    verification = verify_queries(queries, args.db, args.download_list, args.mode)
    failures = []
    print("Verification:")
    for q, info in verification.items():
        print(f"- {q}: {len(info['present'])} present, {len(info['missing'])} missing")
        for title in info["present"]:
            print(f"  present: {title}")
        for title in info["missing"]:
            print(f"  MISSING: {title}")
        if info["missing"] or not info["present"]:
            failures.append(q)
    if args.launch:
        launch_fit_launcher(args.fit_launcher)
        print(f"Launched: {args.fit_launcher}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

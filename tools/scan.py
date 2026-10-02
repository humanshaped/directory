#!/usr/bin/env python3
"""Build the Human Shaped directory and look for apps that may belong in it.

Two outputs, both written to the repository root:

  directory.json   every curated listing in apps/*.json, in display order.
                   humanshaped.org reads this file.
  candidates.json  public repositories that may belong in the directory and
                   are not listed yet: ones with a HUMAN-SHAPED.md
                   declaration, and ones made from the Universal App Template
                   (or the earlier templates it grew out of). Ben reads this
                   file and decides; nothing here is listed automatically.

GitHub has no way to ask "which repositories were made from this template",
so the scan searches for files only template-born projects carry, then
confirms each match against the repository's own template_repository field.
A match that does not come from the template is dropped.

Needs a GitHub token in GITHUB_TOKEN (or a logged-in `gh`) because GitHub's
code search requires one. Standard library only.

    python3 tools/scan.py            # build both files
    python3 tools/scan.py --offline  # rebuild directory.json only
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINEAGE = {
    "bhwilkoff/UniversalAppTemplate",
    "bhwilkoff/QuadAppTemplate",
    "bhwilkoff/DualAppTemplate",
}
# Files that only a project made from the template is likely to carry.
MARKERS = [
    "HUMAN-SHAPED.md",
    "LaunchDoors.swift",
    "LaunchDoors.kt",
    "test_us_english.py",
    "check_workflow_gates.py",
]
STATUS_ORDER = {"founding": 0, "cohort": 1, "template": 2, "listed": 3}
REQUIRED = ["slug", "name", "in_its_own_words", "website", "status", "listed"]


def load_listings():
    listings = []
    problems = []
    for path in sorted((ROOT / "apps").glob("*.json")):
        try:
            entry = json.loads(path.read_text())
        except json.JSONDecodeError as err:
            problems.append(f"{path.name}: not valid JSON ({err})")
            continue
        missing = [k for k in REQUIRED if not entry.get(k)]
        if missing:
            problems.append(f"{path.name}: missing {', '.join(missing)}")
            continue
        if entry["slug"] != path.stem:
            problems.append(f"{path.name}: slug must match the file name")
            continue
        if entry["status"] not in STATUS_ORDER:
            problems.append(f"{path.name}: unknown status {entry['status']!r}")
            continue
        listings.append(entry)
    listings.sort(key=lambda e: (STATUS_ORDER[e["status"]], not e.get("active", True), e["name"].lower()))
    return listings, problems


def token():
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def api(path, tok, params=None, raw=False):
    url = path if path.startswith("http") else f"https://api.github.com/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
        "User-Agent": "humanshaped-directory-scan",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace")
                return body if raw else json.loads(body)
        except urllib.error.HTTPError as err:
            if err.code in (403, 429) and attempt < 2:
                time.sleep(30)
                continue
            if err.code == 404:
                return None
            raise


def front_matter(text):
    """Read the simple key: value header of a HUMAN-SHAPED.md file."""
    m = re.match(r"^---\s*\n(.*?)\n---", text or "", re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def scan(tok, listed_repos):
    found = {}
    for marker in MARKERS:
        page = api("search/code", tok, {"q": f"filename:{marker}", "per_page": 100}) or {}
        for item in page.get("items", []):
            if item.get("name") != marker:
                continue  # filename search is fuzzy; only exact names count
            name = item["repository"]["full_name"]
            found.setdefault(name, {}).setdefault(marker, item["path"])
        time.sleep(7)  # code search allows ten requests a minute

    candidates = []
    for name, markers in sorted(found.items()):
        if name in LINEAGE or f"https://github.com/{name}".lower() in listed_repos:
            continue
        repo = api(f"repos/{name}", tok)
        if not repo or repo.get("private") or repo.get("fork") or repo.get("archived"):
            continue
        template = (repo.get("template_repository") or {}).get("full_name")
        from_template = template in LINEAGE
        decl_path = markers.get("HUMAN-SHAPED.md")
        declared = decl_path is not None
        if not (from_template or declared):
            continue  # the file name matched, but this is someone else's project
        declaration = {}
        if declared:
            text = api(f"repos/{name}/contents/{urllib.parse.quote(decl_path)}", tok, raw=True)
            declaration = front_matter(text)
        candidates.append({
            "repository": repo["html_url"],
            "name": declaration.get("app") or repo["name"],
            "description": repo.get("description") or "",
            "website": declaration.get("website") or repo.get("homepage") or "",
            "made_from_template": template if from_template else None,
            "declaration": f"{repo['html_url']}/blob/{repo['default_branch']}/{decl_path}" if declared else None,
            "declaration_status": declaration.get("status"),
            "principles_version": declaration.get("principles_version"),
            "last_pushed": repo.get("pushed_at"),
        })
    return candidates


def write(name, data):
    (ROOT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main():
    listings, problems = load_listings()
    for p in problems:
        print(f"PROBLEM {p}", file=sys.stderr)
    write("directory.json", {"apps": listings})
    print(f"directory.json: {len(listings)} listings")
    if problems:
        return 1
    if "--offline" in sys.argv:
        return 0
    tok = token()
    if not tok:
        print("No GitHub token, so candidates.json was not refreshed.", file=sys.stderr)
        return 1
    listed = {(e.get("repository") or "").lower() for e in listings}
    try:
        candidates = scan(tok, listed)
    except urllib.error.HTTPError as err:
        # Code search refuses the workflow's built-in token. The directory
        # still published; the candidates wait for a token that can search.
        print(f"::warning::Code search refused this token (HTTP {err.code}), so "
              "candidates.json was left as it was. Add a DIRECTORY_SEARCH_TOKEN "
              "secret (a fine-grained token with public read access) to scan.")
        return 0
    write("candidates.json", {"candidates": candidates})
    print(f"candidates.json: {len(candidates)} candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())

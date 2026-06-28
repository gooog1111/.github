import base64
import json
import os
import random
import re
import shutil
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import requests
from deep_translator import GoogleTranslator


OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "gooog1111")
TOKEN = os.environ.get("REPO_SYNC_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
WORKDIR = Path("readme-work")
API = "https://api.github.com"

HEADERS = {}
GIT_AUTH_HEADER = ""


def run(args, cwd=None, check=True):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError(f"Command failed: {' '.join(args)}")
    return result


def resolve_token():
    token = os.environ.get("REPO_SYNC_TOKEN", "").strip()
    if token:
        return token

    result = run(["gh", "auth", "token"], check=False)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    return ""


def configure_auth(token):
    global TOKEN, HEADERS, GIT_AUTH_HEADER

    TOKEN = token
    HEADERS = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    GIT_AUTH_HEADER = "AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()


def gh(method, path, quiet_statuses=None, **kwargs):
    quiet_statuses = set(quiet_statuses or [])
    url = path if path.startswith("https://") else f"{API}{path}"
    try:
        response = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)
    except Exception as exc:
        print(f"{method} {path} failed: {exc}")
        return None

    if response.status_code >= 400:
        if response.status_code in quiet_statuses:
            return None
        print(f"GitHub API error {response.status_code}: {method} {path}")
        print(response.text[:400])
        return None

    if response.status_code == 204 or not response.content:
        return None

    try:
        return response.json()
    except Exception:
        return None


def list_repositories():
    repos = []
    page = 1
    while True:
        batch = gh(
            "GET",
            "/user/repos",
            params={
                "affiliation": "owner",
                "visibility": "all",
                "sort": "full_name",
                "per_page": 100,
                "page": page,
            },
        )
        if batch is None:
            raise RuntimeError("Cannot list repositories. Check REPO_SYNC_TOKEN credentials.")
        if not batch:
            break

        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    filtered = [
        repo
        for repo in repos
        if not repo.get("archived")
        and not repo.get("disabled")
        and repo.get("owner", {}).get("login", "").lower() == OWNER.lower()
    ]

    if not filtered:
        raise RuntimeError(f"No repositories found for owner {OWNER}. Check token access.")

    return filtered


def cached_get(repo_full_name, path, cache_file, params=None, quiet_statuses=None):
    cache = Path(cache_file)
    if cache.exists():
        age = datetime.now().timestamp() - cache.stat().st_mtime
        if age < 3600:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                pass

    data = gh("GET", f"/repos/{repo_full_name}{path}", params=params, quiet_statuses=quiet_statuses) or {}
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def replace_block(text, start, end, block):
    pattern = rf"<!-- {start} -->.*?<!-- {end} -->"
    if re.search(pattern, text, flags=re.DOTALL):
        return re.sub(pattern, block, text, flags=re.DOTALL)
    return block + "\n\n" + text


def force_lang_switch(text, lang):
    text = re.sub(r"<!-- LANG_START -->.*?<!-- LANG_END -->\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"(?mi)^.*English version.*README\.en\.md.*\n?", "", text)
    text = re.sub(r"(?mi)^.*Русская версия.*README\.md.*\n?", "", text)

    if lang == "ru":
        switch = """<!-- LANG_START -->
🇬🇧 [English version](README.en.md)
<!-- LANG_END -->"""
    else:
        switch = """<!-- LANG_START -->
🇷🇺 [Русская версия](README.md)
<!-- LANG_END -->"""

    return switch + "\n\n" + text.strip() + "\n"


def protect_markdown(text):
    protected = {}

    def protect(match):
        key = f"__PROTECTED_{len(protected)}__"
        protected[key] = match.group(0)
        return key

    patterns = [
        r"```.*?```",
        r"`[^`\n]+`",
        r"<!-- STATS_START -->.*?<!-- STATS_END -->",
        r"<!-- GRAPH_START -->.*?<!-- GRAPH_END -->",
        r"<!-- ISSUES_START -->.*?<!-- ISSUES_END -->",
        r"<!-- LANG_START -->.*?<!-- LANG_END -->",
        r"<p[\s\S]*?</p>",
        r"<div[\s\S]*?</div>",
        r"!\[[^\]]*\]\([^)]+\)",
        r"\[[^\]]+\]\([^)]+\)",
        r"https?://\S+",
    ]

    for pattern in patterns:
        text = re.sub(pattern, protect, text, flags=re.DOTALL)

    return text, protected


def translate_markdown(text):
    protected_text, protected = protect_markdown(text)
    chunks = []
    current = []
    current_len = 0

    for line in protected_text.splitlines(keepends=True):
        if current_len + len(line) > 2800 and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)

    if current:
        chunks.append("".join(current))

    translator = GoogleTranslator(source="ru", target="en")
    translated_chunks = []

    for chunk in chunks:
        if not chunk.strip():
            translated_chunks.append(chunk)
            continue

        try:
            translated_chunks.append(translator.translate(chunk) or chunk)
        except Exception as exc:
            print("Translate failed:", exc)
            translated_chunks.append(chunk)

    translated = "".join(translated_chunks)
    for key, value in protected.items():
        translated = translated.replace(key, value)

    return re.sub(r"(?m)^##\s*", "## ", translated)


def build_chart(repo_full_name, repo_dir, views):
    points = views.get("views", []) if isinstance(views, dict) else []
    labels = [point["timestamp"][:10] for point in points] if points else [datetime.now(timezone.utc).date().isoformat()]
    counts = [point["count"] for point in points] if points else [0]

    chart = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": "Views per day",
                "data": counts,
                "borderColor": "rgba(255,105,0,1)",
                "backgroundColor": "rgba(255,105,0,0.15)",
                "fill": True,
                "tension": 0.25,
                "pointRadius": 2,
            }],
        },
        "options": {
            "responsive": False,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": True, "text": f"GitHub Traffic · {repo_full_name}"},
                "legend": {"display": False},
            },
            "scales": {
                "y": {"beginAtZero": True, "ticks": {"precision": 0}},
                "x": {"ticks": {"maxRotation": 0, "autoSkip": True, "maxTicksLimit": 7}},
            },
            "layout": {"padding": 4},
        },
    }

    try:
        response = requests.post(
            "https://quickchart.io/chart",
            json={"chart": chart, "width": 1200, "height": 180, "format": "png", "backgroundColor": "white"},
            timeout=30,
        )
        if response.status_code == 200 and response.content:
            (repo_dir / "traffic-views.png").write_bytes(response.content)
        else:
            print("QuickChart failed:", response.status_code, response.text[:300])
    except Exception as exc:
        print("QuickChart request failed:", exc)


def ensure_header_svg(repo_dir, repo_name, repo_url):
    header = repo_dir / "resources" / "header.svg"
    if header.exists():
        return False

    palettes = [
        ("#111827", "#1f6feb", "#ff6900"),
        ("#0f172a", "#0891b2", "#f59e0b"),
        ("#18181b", "#16a34a", "#f97316"),
        ("#1f2937", "#2563eb", "#dc2626"),
        ("#0b1120", "#7c3aed", "#06b6d4"),
        ("#172554", "#14b8a6", "#f43f5e"),
        ("#1e1b4b", "#0ea5e9", "#eab308"),
        ("#052e16", "#22c55e", "#e11d48"),
    ]
    directions = [
        ("0", "0", "1", "1"),
        ("1", "0", "0", "1"),
        ("0", "1", "1", "0"),
        ("1", "1", "0", "0"),
        ("0", "0.5", "1", "0.5"),
        ("0.5", "0", "0.5", "1"),
    ]

    colors = random.choice(palettes)
    x1, y1, x2, y2 = random.choice(directions)
    safe_name = escape(repo_name)
    safe_url = escape(repo_url)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="260" viewBox="0 0 1200 260" role="img" aria-label="{safe_name}">
  <defs>
    <linearGradient id="bg" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">
      <stop offset="0" stop-color="{colors[0]}"/>
      <stop offset="0.52" stop-color="{colors[1]}"/>
      <stop offset="1" stop-color="{colors[2]}"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="260" rx="26" fill="url(#bg)"/>
  <rect x="24" y="24" width="1152" height="212" rx="20" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.24)"/>
  <text x="600" y="126" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="54" font-weight="700" fill="#ffffff">{safe_name}</text>
  <text x="600" y="174" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="22" fill="#e5e7eb">{safe_url}</text>
</svg>
"""

    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text(svg, encoding="utf-8")
    print(f"Generated {header}")
    return True


def issue_cards(has_issues, issues, lang):
    if not has_issues:
        message = "Issues отключены в настройках репозитория." if lang == "ru" else "Issues are disabled in this repository."
        return f"""
<p align="center">
  <b>{message}</b>
</p>
"""

    if not issues:
        if lang == "ru":
            return """
<p align="center">
  <b>Открытых issues нет.</b><br>
  <sub>Служебный issue <code>views-counter</code> скрыт из списка.</sub>
</p>
"""
        return """
<p align="center">
  <b>No open issues.</b><br>
  <sub>The service issue <code>views-counter</code> is hidden from the list.</sub>
</p>
"""

    cards = []
    for issue in issues:
        labels = " ".join(f"<code>{label.get('name', '')}</code>" for label in issue.get("labels", [])[:5])
        cards.append(f"""
<tr>
  <td width="90"><a href="{issue['html_url']}"><b>#{issue['number']}</b></a></td>
  <td><b>{issue['title']}</b><br><sub>{labels}</sub></td>
  <td width="120"><sub>{issue['created_at'][:10]}</sub></td>
</tr>""")

    return """
<table>
  <tr>
    <th align="left">Issue</th>
    <th align="left">Title</th>
    <th align="left">Created</th>
  </tr>
""" + "\n".join(cards) + "\n</table>"


def issues_block(repo_url, has_issues, issues, issue_count, updated_at, lang):
    create_badge = (
        f"""<a href="{repo_url}/issues/new/choose">
    <img alt="Create issue" src="https://img.shields.io/badge/Create_issue-new-success?style=for-the-badge&logo=github">
  </a>"""
        if has_issues
        else """<img alt="Issues disabled" src="https://img.shields.io/badge/Create_issue-disabled-lightgrey?style=for-the-badge&logo=github">"""
    )
    summary = "Открытые issues" if lang == "ru" else "Open issues"
    create_text = "Создать issue" if lang == "ru" else "Create new issue"
    all_text = "Все issues" if lang == "ru" else "All issues"
    links = (
        f"""<a href="{repo_url}/issues/new/choose">{create_text}</a> ·
  <a href="{repo_url}/issues">{all_text}</a>"""
        if has_issues
        else f"""<a href="{repo_url}/issues">{all_text}</a>"""
    )

    return f"""<!-- ISSUES_START -->
<!-- auto-updated by GitHub Actions · {updated_at} -->

## Issues

<p>
  <a href="{repo_url}/issues">
    <img alt="Open issues" src="https://img.shields.io/badge/Open_issues-{issue_count}-blue?style=for-the-badge&logo=github">
  </a>
  {create_badge}
</p>

<details open>
<summary><b>{summary}</b></summary>

{issue_cards(has_issues, issues, lang)}

</details>

<p>
  {links}
</p>

<!-- ISSUES_END -->"""


def update_repo(repo):
    repo_full_name = repo["full_name"]
    repo_name = repo["name"]
    repo_dir = WORKDIR / repo_name
    repo_url = f"https://github.com/{repo_full_name}"

    print(f"Updating {repo_full_name}")

    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    run([
        "git",
        "-c",
        f"http.https://github.com/.extraheader={GIT_AUTH_HEADER}",
        "clone",
        "--depth",
        "1",
        repo["clone_url"],
        str(repo_dir),
    ])

    readme = repo_dir / "README.md"
    if not readme.exists():
        print(f"Skipping {repo_full_name}: no root README.md")
        return False

    if repo_full_name.lower() == f"{OWNER.lower()}/.github":
        print("Skipping .github profile README by design")
        return False

    ensure_header_svg(repo_dir, repo_name, repo_url)

    run(["git", "config", "user.name", "github-actions[bot]"], cwd=repo_dir)
    run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=repo_dir)
    run(["git", "config", "http.https://github.com/.extraheader", GIT_AUTH_HEADER], cwd=repo_dir)

    repo_info = cached_get(repo_full_name, "", repo_dir / ".cache_repo.json")
    has_issues = bool(repo_info.get("has_issues", True))
    stars = repo_info.get("stargazers_count", 0)
    forks = repo_info.get("forks_count", 0)

    views = cached_get(
        repo_full_name,
        "/traffic/views",
        repo_dir / ".cache_views.json",
        params={"per": "day"},
        quiet_statuses={403},
    )
    clones = cached_get(
        repo_full_name,
        "/traffic/clones",
        repo_dir / ".cache_clones.json",
        params={"per": "day"},
        quiet_statuses={403},
    )

    local_views = 0
    if has_issues:
        all_issues = gh("GET", f"/repos/{repo_full_name}/issues", params={"state": "open", "per_page": 100}) or []
        view_issue = next((issue for issue in all_issues if issue.get("title") == "views-counter"), None) if isinstance(all_issues, list) else None

        if not view_issue:
            view_issue = gh(
                "POST",
                f"/repos/{repo_full_name}/issues",
                json={"title": "views-counter", "body": "0"},
                quiet_statuses={403},
            )

        if isinstance(view_issue, dict):
            try:
                local_views = int((view_issue.get("body") or "0").strip())
            except Exception:
                local_views = 0

            local_views += 1
            if "number" in view_issue:
                gh(
                    "PATCH",
                    f"/repos/{repo_full_name}/issues/{view_issue['number']}",
                    json={"body": str(local_views)},
                    quiet_statuses={403},
                )

    releases = cached_get(repo_full_name, "/releases", repo_dir / ".cache_releases.json", params={"per_page": 100})
    dl_latest = 0
    dl_total = 0

    if isinstance(releases, list):
        public_releases = [release for release in releases if not release.get("draft") and not release.get("prerelease")]
        latest_release = public_releases[0] if public_releases else (releases[0] if releases else None)
        dl_total = sum(
            asset.get("download_count", 0)
            for release in releases
            for asset in release.get("assets", [])
        )
        if latest_release:
            dl_latest = sum(asset.get("download_count", 0) for asset in latest_release.get("assets", []))

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    gh_views = views.get("count", 0) if isinstance(views, dict) else 0
    gh_unique = views.get("uniques", 0) if isinstance(views, dict) else 0
    gh_clones = clones.get("count", 0) if isinstance(clones, dict) else 0

    stats_block = f"""<!-- STATS_START -->
<!-- auto-updated by GitHub Actions · {updated_at} -->

[![Views local](https://img.shields.io/badge/Views_local-{local_views}-ff6900?style=for-the-badge&logo=github)]({repo_url})
[![Views GitHub](https://img.shields.io/badge/Views_GitHub-{gh_views}-ff6900?style=for-the-badge&logo=github)]({repo_url})
[![Unique visitors](https://img.shields.io/badge/Unique-{gh_unique}-blue?style=for-the-badge&logo=github)]({repo_url})
[![Clones](https://img.shields.io/badge/Clones-{gh_clones}-purple?style=for-the-badge&logo=github)]({repo_url})
[![Stars](https://img.shields.io/badge/Stars-{stars}-yellow?style=for-the-badge&logo=github)]({repo_url}/stargazers)
[![Forks](https://img.shields.io/badge/Forks-{forks}-green?style=for-the-badge&logo=github)]({repo_url}/network/members)
[![Downloads latest release](https://img.shields.io/badge/Downloads_latest_release-{dl_latest}-brightgreen?style=for-the-badge)]({repo_url}/releases/latest)
[![Downloads total assets](https://img.shields.io/badge/Downloads_total_assets-{dl_total}-brightgreen?style=for-the-badge)]({repo_url}/releases)

<!-- STATS_END -->"""

    build_chart(repo_full_name, repo_dir, views)

    graph_block = """<!-- GRAPH_START -->
<p align="center">
  <img src="./traffic-views.png" width="100%" alt="GitHub Traffic">
</p>
<!-- GRAPH_END -->"""

    latest_issues = []
    if has_issues:
        latest_issues = gh(
            "GET",
            f"/repos/{repo_full_name}/issues",
            params={"state": "open", "per_page": 10, "sort": "created", "direction": "desc"},
        ) or []

    issues = [
        issue for issue in latest_issues
        if isinstance(issue, dict)
        and "pull_request" not in issue
        and issue.get("title") != "views-counter"
    ]
    issue_count = len(issues)

    ru = readme.read_text(encoding="utf-8")
    ru = force_lang_switch(ru, "ru")
    ru = replace_block(ru, "STATS_START", "STATS_END", stats_block)
    ru = replace_block(ru, "GRAPH_START", "GRAPH_END", graph_block)
    ru = replace_block(ru, "ISSUES_START", "ISSUES_END", issues_block(repo_url, has_issues, issues, issue_count, updated_at, "ru"))
    readme.write_text(ru, encoding="utf-8")

    en = translate_markdown(ru)
    en = force_lang_switch(en, "en")
    en = replace_block(en, "STATS_START", "STATS_END", stats_block)
    en = replace_block(en, "GRAPH_START", "GRAPH_END", graph_block)
    en = replace_block(en, "ISSUES_START", "ISSUES_END", issues_block(repo_url, has_issues, issues, issue_count, updated_at, "en"))
    (repo_dir / "README.en.md").write_text(en, encoding="utf-8")

    run(["git", "add", "README.md", "README.en.md", "traffic-views.png", "resources/header.svg"], cwd=repo_dir, check=False)
    diff = run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
    if diff.returncode == 0:
        print(f"No changes in {repo_full_name}")
        return False

    run(["git", "commit", "-m", "update README stats, graph, issues and translation [skip ci]"], cwd=repo_dir)
    run(["git", "pull", "--rebase"], cwd=repo_dir)
    run(["git", "push"], cwd=repo_dir)
    return True


def main():
    configure_auth(resolve_token())

    if not TOKEN:
        raise SystemExit("No token available. Set REPO_SYNC_TOKEN or run gh auth login.")

    if TOKEN == GITHUB_TOKEN:
        print("::warning::Using GITHUB_TOKEN. To update all repositories, create a REPO_SYNC_TOKEN secret with repo access.")

    WORKDIR.mkdir(exist_ok=True)
    updated = []
    failed = []

    for repo in list_repositories():
        try:
            if update_repo(repo):
                updated.append(repo["full_name"])
        except Exception as exc:
            print(f"Failed to update {repo['full_name']}: {exc}")
            failed.append(repo["full_name"])

    print("Updated repositories:")
    for repo in updated:
        print(f"- {repo}")

    if failed:
        print("Failed repositories:")
        for repo in failed:
            print(f"- {repo}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import requests


OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "gooog1111")
TOKEN = os.environ.get("REPO_SYNC_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SOURCE_FILE = Path(os.environ.get("SOURCE_FILE", "LICENSE.md"))
TARGET_FILE = os.environ.get("TARGET_FILE", "LICENSE.md")
WORKDIR = Path("license-work")
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


def gh(method, path, **kwargs):
    response = requests.request(method, f"{API}{path}", headers=HEADERS, timeout=30, **kwargs)
    if response.status_code >= 400:
        print(f"GitHub API error {response.status_code}: {method} {path}")
        print(response.text[:400])
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
        repo for repo in repos
        if not repo.get("archived")
        and not repo.get("disabled")
        and repo.get("default_branch")
        and repo.get("owner", {}).get("login", "").lower() == OWNER.lower()
    ]

    if not filtered:
        raise RuntimeError(f"No repositories found for owner {OWNER}. Check token access.")

    return filtered


def sync_repo(repo):
    full_name = repo["full_name"]
    repo_dir = WORKDIR / repo["name"]
    default_branch = repo["default_branch"]

    print(f"Checking {full_name}")

    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    run([
        "git",
        "-c",
        f"http.https://github.com/.extraheader={GIT_AUTH_HEADER}",
        "clone",
        "--depth",
        "1",
        "--branch",
        default_branch,
        repo["clone_url"],
        str(repo_dir),
    ])

    run(["git", "config", "user.name", "github-actions[bot]"], cwd=repo_dir)
    run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=repo_dir)
    run(["git", "config", "http.https://github.com/.extraheader", GIT_AUTH_HEADER], cwd=repo_dir)

    shutil.copy2(SOURCE_FILE, repo_dir / TARGET_FILE)

    run(["git", "add", TARGET_FILE], cwd=repo_dir)
    diff = run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
    if diff.returncode == 0:
        print(f"{full_name} already has the current {TARGET_FILE}")
        return False

    run(["git", "commit", "-m", f"Sync {TARGET_FILE}"], cwd=repo_dir)
    run(["git", "pull", "--rebase"], cwd=repo_dir)
    run(["git", "push", "origin", f"HEAD:{default_branch}"], cwd=repo_dir)
    return True


def main():
    configure_auth(resolve_token())

    if not TOKEN:
        raise SystemExit("No token available. Set REPO_SYNC_TOKEN or run gh auth login.")

    if TOKEN == GITHUB_TOKEN:
        print("::warning::Using GITHUB_TOKEN. Use REPO_SYNC_TOKEN for cross-repository sync.")

    if not SOURCE_FILE.exists() or SOURCE_FILE.stat().st_size == 0:
        raise SystemExit(f"{SOURCE_FILE} is missing or empty.")

    WORKDIR.mkdir(exist_ok=True)
    updated = []
    failed = []

    for repo in list_repositories():
        try:
            if sync_repo(repo):
                updated.append(repo["full_name"])
        except Exception as exc:
            print(f"Failed to sync {repo['full_name']}: {exc}")
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

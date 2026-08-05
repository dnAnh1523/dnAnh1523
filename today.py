#!/usr/bin/env python3
"""
Cap nhat cac chi so GitHub (repos, stars, followers, commits, lines of code)
vao 2 file light_mode.svg / dark_mode.svg.

Yeu cau:
  - Bien moi truong USER_NAME: username GitHub cua ban
  - Bien moi truong ACCESS_TOKEN: Personal Access Token (scope: repo, read:user)

Cach chay thu local:
  USER_NAME=<username> ACCESS_TOKEN=<token> python3 today.py
"""

import os
import re
import sys
import json
import time
import requests
from datetime import date

USER_NAME = os.environ.get("USER_NAME")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")

# Ngay sinh, dung de tu tinh "Uptime" (tuoi) moi lan workflow chay.
# Sua lai ngay/thang/nam cho dung neu ban thay doi.
BIRTH_DATE = date(2003, 2, 15)


def get_age_string():
    """Tra ve chuoi kieu '23 years, 5 months, 21 days' tinh tu BIRTH_DATE den hom nay."""
    today = date.today()
    years = today.year - BIRTH_DATE.year
    months = today.month - BIRTH_DATE.month
    days = today.day - BIRTH_DATE.day
    if days < 0:
        months -= 1
        prev_month = today.month - 1 or 12
        prev_year = today.year if today.month > 1 else today.year - 1
        import calendar
        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    return f"{years} years, {months} months, {days} days"

if not USER_NAME or not ACCESS_TOKEN:
    sys.exit("Thieu bien moi truong USER_NAME hoac ACCESS_TOKEN")

GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"bearer {ACCESS_TOKEN}"}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_FILE = os.path.join(CACHE_DIR, f"{USER_NAME}_loc_cache.json")


def gql(query, variables=None):
    """Goi GitHub GraphQL API, tu dong retry khi bi rate limit."""
    for attempt in range(5):
        r = requests.post(
            GRAPHQL_URL,
            headers=HEADERS,
            json={"query": query, "variables": variables or {}},
        )
        if r.status_code == 200:
            data = r.json()
            if "errors" in data:
                raise RuntimeError(data["errors"])
            return data["data"]
        if r.status_code in (502, 503) or "rate limit" in r.text.lower():
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"GraphQL that bai ({r.status_code}): {r.text}")
    raise RuntimeError("GraphQL that bai sau nhieu lan thu lai")


def get_user_overview():
    """Lay: ngay tao tai khoan, so followers, so repo (khong tinh fork)."""
    query = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        repositories(first: 1, ownerAffiliations: [OWNER], isFork: false) {
          totalCount
        }
      }
    }
    """
    data = gql(query, {"login": USER_NAME})["user"]
    return data


def get_star_count():
    """Cong don so sao (stargazers) tren tat ca repo ban own (khong tinh fork)."""
    total_stars = 0
    cursor = None
    while True:
        query = """
        query($login: String!, $cursor: String) {
          user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: [OWNER], isFork: false) {
              pageInfo { hasNextPage endCursor }
              nodes { stargazerCount }
            }
          }
        }
        """
        data = gql(query, {"login": USER_NAME, "cursor": cursor})["user"]["repositories"]
        total_stars += sum(n["stargazerCount"] for n in data["nodes"])
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    return total_stars


def get_commit_count(created_at):
    """Cong don totalCommitContributions tu nam tao tai khoan den nay."""
    start_year = int(created_at[:4])
    from datetime import datetime, timezone
    end_year = datetime.now(timezone.utc).year
    total = 0
    for year in range(start_year, end_year + 1):
        query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              restrictedContributionsCount
            }
          }
        }
        """
        variables = {
            "login": USER_NAME,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        }
        c = gql(query, variables)["user"]["contributionsCollection"]
        total += c["totalCommitContributions"] + c["restrictedContributionsCount"]
    return total


def get_repo_list():
    """Lay danh sach (owner, name, defaultBranch) cua repo ban own, khong tinh fork."""
    repos = []
    cursor = None
    while True:
        query = """
        query($login: String!, $cursor: String) {
          user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: [OWNER], isFork: false) {
              pageInfo { hasNextPage endCursor }
              nodes {
                name
                defaultBranchRef { name }
              }
            }
          }
        }
        """
        data = gql(query, {"login": USER_NAME, "cursor": cursor})["user"]["repositories"]
        for n in data["nodes"]:
            if n["defaultBranchRef"]:
                repos.append((USER_NAME, n["name"], n["defaultBranchRef"]["name"]))
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    return repos


def get_repo_loc(owner, name, branch, cache):
    """
    Cong don additions/deletions cua cac commit do chinh USER_NAME tao ra,
    tren nhanh mac dinh cua 1 repo. Ket qua duoc cache theo commit cuoi cung
    da xu ly de nhung lan chay sau khong phai quet lai tu dau.
    """
    key = f"{owner}/{name}"
    cached = cache.get(key, {"additions": 0, "deletions": 0, "last_oid": None})
    additions, deletions = cached["additions"], cached["deletions"]
    stop_at = cached["last_oid"]

    cursor = None
    newest_oid = None
    done = False
    while not done:
        query = """
        query($owner: String!, $name: String!, $branch: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            ref(qualifiedName: $branch) {
              target {
                ... on Commit {
                  history(first: 100, after: $cursor) {
                    pageInfo { hasNextPage endCursor }
                    nodes {
                      oid
                      additions
                      deletions
                      author { user { login } }
                    }
                  }
                }
              }
            }
          }
        }
        """
        variables = {"owner": owner, "name": name, "branch": branch, "cursor": cursor}
        data = gql(query, variables)["repository"]["ref"]
        if not data:
            break
        history = data["target"]["history"]
        for commit in history["nodes"]:
            if newest_oid is None:
                newest_oid = commit["oid"]
            if commit["oid"] == stop_at:
                done = True
                break
            author = commit["author"]["user"]
            if author and author["login"] == USER_NAME:
                additions += commit["additions"]
                deletions += commit["deletions"]
        if done or not history["pageInfo"]["hasNextPage"]:
            break
        cursor = history["pageInfo"]["endCursor"]

    cache[key] = {"additions": additions, "deletions": deletions, "last_oid": newest_oid or stop_at}
    return additions, deletions


def get_total_loc(repos):
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    else:
        cache = {}

    total_add, total_del = 0, 0
    for owner, name, branch in repos:
        try:
            a, d = get_repo_loc(owner, name, branch, cache)
        except Exception as e:
            print(f"  [canh bao] bo qua {owner}/{name}: {e}", file=sys.stderr)
            continue
        total_add += a
        total_del += d

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

    return total_add, total_del


def set_tspan_value(svg_text, element_id, value):
    """Thay noi dung text cua tspan co id=... , dung cho ca file svg."""
    pattern = rf'(<tspan[^>]*id="{element_id}"[^>]*>)([^<]*)(</tspan>)'
    return re.sub(pattern, lambda m: f"{m.group(1)}{value}{m.group(3)}", svg_text)


def update_svg_file(path, values):
    with open(path, "r", encoding="utf-8") as f:
        svg = f.read()
    for element_id, value in values.items():
        svg = set_tspan_value(svg, element_id, value)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"  da cap nhat {path}")


def main():
    print(f"Dang lay du lieu GitHub cho {USER_NAME}...")

    overview = get_user_overview()
    followers = overview["followers"]["totalCount"]
    repo_count = overview["repositories"]["totalCount"]
    created_at = overview["createdAt"]

    print("  dang tinh sao (stars)...")
    stars = get_star_count()

    print("  dang tinh commit...")
    commits = get_commit_count(created_at)

    print("  dang liet ke repo...")
    repos = get_repo_list()

    print(f"  dang tinh lines of code cho {len(repos)} repo (co the mat vai phut lan dau)...")
    additions, deletions = get_total_loc(repos)
    net_loc = additions - deletions

    values = {
        "age_data": get_age_string(),
        "repo_data": f"{repo_count}",
        "star_data": f"{stars}",
        "follower_data": f"{followers}",
        "commit_data": f"{commits:,}",
        "loc_data": f"{net_loc:,}",
        "loc_add": f"{additions:,}",
        "loc_del": f"{deletions:,}",
    }

    print("Ket qua:", values)

    for filename in ("light_mode.svg", "dark_mode.svg"):
        path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(path):
            update_svg_file(path, values)


if __name__ == "__main__":
    main()

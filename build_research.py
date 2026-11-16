"""Build the serious Analytics department. Defaults: all performance years; 2025/26 trades."""
import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from import_history import BASE, CURRENT_SEASON, LEAGUE_ID, VIEWS
from research_metrics import season_performance, recover_trades, measure_trade

ROOT = Path(__file__).parent
CACHE = ROOT / ".research-cache"
DIST = ROOT / "website" / "dist"
REFRESH = False


def request(url, filters=None):
    key = hashlib.sha256((url + json.dumps(filters, sort_keys=True)).encode()).hexdigest()
    path = CACHE / (key + ".json")
    if not REFRESH and path.exists() and time.time() - path.stat().st_mtime < 86400:
        return json.loads(path.read_text(encoding="utf-8"))
    headers = {"Accept": "application/json", "User-Agent": "qrffl-research/1.0"}
    if filters:
        headers["X-Fantasy-Filter"] = json.dumps(filters)
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        result = {"data": json.load(response), "player_count": response.headers.get("X-Fantasy-Filter-Player-Count")}
    CACHE.mkdir(exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result), encoding="utf-8")
    temporary.replace(path)
    return result


def league_url(year):
    return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"


def player_pool(year):
    ids = set()
    expected = None
    for offset in range(0, 10000, 500):
        filters = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
                   "limit": 500, "offset": offset, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
        response = request(league_url(year) + "?view=kona_player_info", filters)
        if response["player_count"] is not None:
            count = int(response["player_count"])
            if expected is not None and count != expected:
                raise ValueError("Player pool changed during discovery; rerun with --refresh")
            expected = count
        batch = response["data"].get("players", [])
        if not isinstance(batch, list):
            raise ValueError("Player-pool response is missing its players")
        ids.update(p["id"] for p in batch)
        if len(batch) < 500:
            break
    if not ids or expected is not None and len(ids) != expected:
        raise ValueError("Player-pool pagination was incomplete; no trade report was published")
    return sorted(ids)


def cards(year, ids, full=False):
    output = {}
    def batch(chunk):
        filters = {"players": {"filterIds": {"value": chunk}}}
        if full:
            filters["players"]["filterStatsForTopScoringPeriodIds"] = {"value": 18, "additionalValue": [f"00{year}", f"10{year}"]}
        return request(league_url(year) + "?view=kona_playercard", filters)["data"].get("players", [])
    chunks = [ids[index:index + 40] for index in range(0, len(ids), 40)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(batch, chunks):
            for wrapper in result:
                output[wrapper["id"]] = wrapper
    if set(output) != set(ids):
        raise ValueError("Player-card discovery was incomplete")
    return output


def roster_index(data):
    output = {}
    for team in data.get("teams", []):
        if "entries" not in team.get("roster", {}):
            continue
        rows = {}
        for entry in team["roster"]["entries"]:
            pid = entry.get("playerId", entry.get("playerPoolEntry", {}).get("id"))
            if pid in rows:
                raise ValueError("Duplicate player in a historical roster")
            rows[pid] = {"lineupSlotId": entry.get("lineupSlotId")}
        output[team["id"]] = rows
    return output


def build_trades(year, data, performance):
    print(f"{year}: scanning the complete public player pool for trade receipts…", flush=True)
    ids = player_pool(year)
    discovered = cards(year, ids)
    trades = recover_trades(discovered)
    print(f"{year}: {len(discovered)} player cards scanned; {len(trades)} executed trades recovered.", flush=True)
    through = min(data["status"]["finalScoringPeriod"], data["scoringPeriodId"] - 1) if year == CURRENT_SEASON else data["status"]["finalScoringPeriod"]
    if not trades:
        return [], {"season": year, "players_scanned": len(discovered), "recovered_trades": 0, "through_week": through}
    needed = sorted({leg["playerId"] for trade in trades for leg in trade["legs"]})
    discovered.update(cards(year, needed, True))
    schedules = request(f"{BASE}/seasons/{year}?view=proTeamSchedules_wl")["data"]
    pro_teams = {team["id"]: team for team in schedules["settings"]["proTeams"]}
    first = min(trade["week"] for trade in trades) + 1
    weeks = list(range(first, through + 1))
    rosters = {}
    def week_roster(week):
        data = request(league_url(year) + f"?view=mRoster&scoringPeriodId={week}")["data"]
        return week, roster_index(data)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for week, roster in pool.map(week_roster, weeks):
            rosters[week] = roster
    measured = [measure_trade(trade, discovered, rosters, pro_teams, data, performance, through) for trade in trades]
    print(f"{year}: trade production and historical lineups measured through Week {through}.", flush=True)
    return measured, {"season": year, "players_scanned": len(discovered), "recovered_trades": len(trades), "through_week": through,
                     "measured_trades": sum(t["starter_edge"] is not None for t in measured)}


def main():
    global REFRESH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-seasons", nargs="+", type=int, default=[2025, CURRENT_SEASON])
    parser.add_argument("--refresh", action="store_true", help="Bypass the one-day local data cache")
    args = parser.parse_args()
    REFRESH = args.refresh
    history = json.loads((DIST / "history.json").read_text(encoding="utf-8"))
    years = sorted({entry["season"] for entry in history["seasons"] if entry.get("status") == "verified"} | {CURRENT_SEASON})
    if any(year not in years for year in args.trade_seasons):
        raise ValueError("Trade seasons must have an available ESPN archive")
    datasets = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(request, league_url(year) + "?" + VIEWS): year for year in years}
        for future in as_completed(tasks):
            year = tasks[future]
            data = future.result()["data"]
            if data.get("seasonId") != year or data.get("id") != LEAGUE_ID:
                raise ValueError("Mismatched ESPN season")
            datasets[year] = data
    performance = [row for year in years for row in season_performance(datasets[year])]
    print(f"Performance: {len(performance)} franchise-seasons, {years[0]}–{years[-1]}.", flush=True)
    trades, coverage = [], []
    for year in sorted(set(args.trade_seasons)):
        results, covered = build_trades(year, datasets[year], performance)
        trades.extend(results); coverage.append(covered)
    cached = json.loads((DIST / "analytics.json").read_text(encoding="utf-8"))
    labels = {team["id"]: team["name"] for team in cached["teams"]}
    current_cutoff = datasets[CURRENT_SEASON]["scoringPeriodId"] - 1
    output = {"league_id": LEAGUE_ID, "checked_at": datetime.now(timezone.utc).isoformat(),
              "seasons": years, "current_season": CURRENT_SEASON, "current_through_week": current_cutoff,
              "teams": [{"id": tid, "name": label} for tid, label in sorted(labels.items())],
              "performance": performance, "championships": [{"season": row["season"], "team_id": row["champion"].get("team_id")} for row in history["seasons"] if row.get("champion")],
              "head_to_head": [{key: row[key] for key in ("season", "team_id", "opponent_id", "result")} for row in cached["games"]],
              "trades": sorted(trades, key=lambda tx: (tx["season"], tx["week"]), reverse=True), "trade_coverage": coverage}
    path = DIST / "research.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"Research archive written: {len(performance)} season rows, {len(trades)} recovered trades.", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""懂球帝赛程赛果采集器 v1（sport-data.dongqiudi.com，无鉴权 JSON）。

定位：中文赛程/赛果源 + 球队 ID 对齐锚点。无赔率（平台不提供）。
节奏：请求间隔 >=1s；原始响应先落 raw_snapshots 再解析（同 collect_ttyl 纪律）。
用法：
  python3 collect_dqd.py                # 默认：六联赛各最近 6 个赛季
  python3 collect_dqd.py --seasons 3    # 只拉最近 3 季
落库：data/dqd.db（raw_snapshots / dqd_matches / dqd_teams）
"""
import argparse, json, sqlite3, time, urllib.request, os

BASE = "https://sport-data.dongqiudi.com/soccer/biz/data"
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"}
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dqd.db")

# competition_id 由 2026-11-02 探针按球队名实测确认（见 平台数据源探针记录.md）
LEAGUES = {"英超": 4, "西甲": 3, "德甲": 5, "意甲": 9, "法甲": 12, "中超": 43}  # 中超=43: 33季(1994甲A~2026)按队名实测

DDL = """
CREATE TABLE IF NOT EXISTS raw_snapshots(
  id INTEGER PRIMARY KEY, fetched_at TEXT, kind TEXT, ref TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS dqd_matches(
  match_id TEXT PRIMARY KEY, competition_id INTEGER, league TEXT,
  season_id TEXT, season_name TEXT, gameweek INTEGER,
  team_a_id TEXT, team_a_name TEXT, team_b_id TEXT, team_b_name TEXT,
  fs_a INTEGER, fs_b INTEGER, start_play TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS dqd_teams(
  team_id TEXT, competition_id INTEGER, league TEXT, name TEXT,
  PRIMARY KEY(team_id, competition_id));
"""

def get(url):
    last = None
    for attempt, backoff in enumerate((0, 5, 10, 20)):
        if backoff: time.sleep(backoff)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
    raise last

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=6, help="每联赛拉最近 N 个赛季")
    args = ap.parse_args()
    if not LEAGUES:
        raise SystemExit("LEAGUES 未填：先跑 competition_id 探针")

    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.executescript(DDL); con.commit()
    n_req = n_match = 0

    def fetch(kind, ref, url):
        nonlocal n_req
        if kind == "schedule_gw":  # 断点续跑：已存快照的轮次直接回放，不再请求
            row = cur.execute("SELECT payload FROM raw_snapshots WHERE kind='schedule_gw' AND ref=? LIMIT 1",
                              (ref,)).fetchone()
            if row:
                return json.loads(row[0])
        time.sleep(1.0)
        data = get(url); n_req += 1
        cur.execute("INSERT INTO raw_snapshots(fetched_at,kind,ref,payload) VALUES(datetime('now','localtime'),?,?,?)",
                    (kind, ref, json.dumps(data, ensure_ascii=False)))
        return data

    for league, cid in LEAGUES.items():
        seasons = fetch("seasons", f"cid={cid}", f"{BASE}/seasons?competition_id={cid}")[:args.seasons]
        for s in seasons:
            sid, sname = s["season_id"], s["season_name"]
            idx = fetch("schedule_index", f"{league}/{sname}",
                        f"{BASE}/schedule?season_id={sid}&app=dqd&platform=&version=0&lang=zh-cn")
            for rnd in idx.get("content", {}).get("rounds", []):
                gw = rnd.get("params", {}).get("gameweek")
                page = fetch("schedule_gw", f"{league}/{sname}/gw{gw}", rnd["url"])
                for m in page.get("content", {}).get("matches", []):
                    def toi(v):
                        try: return int(v)
                        except (TypeError, ValueError): return None
                    cur.execute("""INSERT OR REPLACE INTO dqd_matches VALUES
                        (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (str(m["match_id"]), cid, league, str(sid), sname, gw,
                         str(m.get("team_A_id","")), m.get("team_A_name",""),
                         str(m.get("team_B_id","")), m.get("team_B_name",""),
                         toi(m.get("fs_A")), toi(m.get("fs_B")),
                         m.get("start_play",""), m.get("status","")))
                    for tid, tname in ((m.get("team_A_id"), m.get("team_A_name")),
                                       (m.get("team_B_id"), m.get("team_B_name"))):
                        if tid:
                            cur.execute("INSERT OR IGNORE INTO dqd_teams VALUES (?,?,?,?)",
                                        (str(tid), cid, league, tname))
                    n_match += 1
                con.commit()
        print(f"{league}: done", flush=True)
    print(f"requests={n_req} matches_upserted={n_match}")
    for row in cur.execute("SELECT league, COUNT(*), COUNT(DISTINCT team_a_id) FROM dqd_matches GROUP BY league"):
        print(row)

if __name__ == "__main__":
    main()

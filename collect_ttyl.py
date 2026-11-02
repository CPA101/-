"""
天天有料数据源采集器 v1（按《天天有料数据源接入方案》P0 探针结论实现）：
- 探针结论：forecast 列表约 14 天滚动窗口（只能增量+回补近 14 天）；fying 网关无登录可达（竞彩主通道）；
  同赔列表当前参数无数据、/match/sai-cheng 在 www 不通 —— 两者 v1 跳过。
- 只读、限速（≥2 秒/次）、原始快照先行；只收公开返回字段，不登录、不碰付费墙扣发内容。
用法：python3 collect_ttyl.py [--days 14]   （首次回补窗口内全部，日常跑 --days 2 即可）
落库：data/ttyl.db 的 raw_snapshots / jc_races / ttyl_model_results
"""
import argparse, json, os, sqlite3, time
import urllib.request, urllib.parse
from datetime import date, timedelta

BASE = "https://www.tiantianyouliao.cn"
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"}
ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "data", "ttyl.db")
_last = [0.0]

def _wait():
    dt = time.time() - _last[0]
    if dt < 2.0:
        time.sleep(2.0 - dt)
    _last[0] = time.time()

def fetch(url, post_form=False):
    _wait()
    req = urllib.request.Request(url, headers=UA,
                                 data=b"" if post_form else None,
                                 method="POST" if post_form else "GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read().decode("utf-8", "ignore")

def init_db(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS raw_snapshots(
      id INTEGER PRIMARY KEY, endpoint TEXT, params TEXT, fetched_at TEXT,
      http_status INT, body TEXT, UNIQUE(endpoint, params, fetched_at));
    CREATE TABLE IF NOT EXISTS jc_races(
      race_id INT, race_no TEXT, issue_no TEXT, area_date TEXT, week TEXT,
      league_name TEXT, release_time TEXT, payload TEXT, fetched_at TEXT,
      UNIQUE(race_id, area_date));
    CREATE TABLE IF NOT EXISTS ttyl_model_results(
      match_id INT, query_date TEXT, forecast_type INT, type_name TEXT,
      home TEXT, away TEXT, comp_name TEXT, race_no TEXT,
      sp_h REAL, sp_d REAL, sp_a REAL, price REAL, unlocked INT,
      home_score INT, away_score INT, hit TEXT, primary_rec TEXT,
      payload TEXT, fetched_at TEXT,
      UNIQUE(match_id, forecast_type, query_date));
    """)

def snap(con, endpoint, params, status, body, fetched_at):
    con.execute("INSERT OR IGNORE INTO raw_snapshots(endpoint, params, fetched_at, http_status, body)"
                " VALUES (?,?,?,?,?)", (endpoint, params, fetched_at, status, body))

def team_name(side):
    if isinstance(side, dict):
        return side.get("home") or side.get("name") or side.get("teamName")
    return None

FALLBACK_TYPE = {"indexdiff": (4, "指数分歧"), "specialist": (1, "大神风向标"),
                 "margin": (2, "margin模型"), "poisson": (3, "泊松分布")}

def parse_model_list(con, endpoint, qdate, items, fetched_at, tag=None):
    n = 0
    for it in items or []:
        ft = it.get("forecastType") or {}
        if ft.get("type") is None and tag in FALLBACK_TYPE:
            ft = {"type": FALLBACK_TYPE[tag][0], "name": FALLBACK_TYPE[tag][1]}
        sp = it.get("sp") or {}
        attr = it.get("attr") or {}
        mr = it.get("marginResult") or {}
        pdto = it.get("poissonDto") or {}
        hit = mr.get("hit", pdto.get("hit"))
        con.execute(
            "INSERT OR REPLACE INTO ttyl_model_results VALUES (%s)" % ",".join("?" * 19),
            (it.get("matchId"), qdate, ft.get("type"), ft.get("name"),
             team_name(it.get("home")), team_name(it.get("away")), it.get("compName"),
             it.get("raceNo"), sp.get("homeWin"), sp.get("draw"), sp.get("awayWin"),
             attr.get("currentPrice"), 1 if attr.get("unlocked") else 0,
             it.get("homeScore"), it.get("awayScore"),
             None if hit is None else str(hit),
             None if mr.get("primaryRec") is None else str(mr.get("primaryRec")),
             json.dumps(it, ensure_ascii=False), fetched_at))
        n += 1
    return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    today = date.today()
    fetched = today.isoformat()
    con = sqlite3.connect(DB)
    init_db(con)
    total_req = 0

    # 1) 竞彩赛程（fying 网关，当日）
    ep = "router/rest?method=fying.sps.jc.race.get"
    url = (f"{BASE}/router/rest?method=fying.sps.jc.race.get"
           "&v=1.0&aid=1&cid=1&cv=3.0.1&clientType=4&appName=cmd")
    st, body = fetch(url, post_form=True); total_req += 1
    snap(con, ep, "jc_today", st, body, fetched)
    try:
        data = json.loads(body)
        njc = 0
        for day in data.get("dayRaceVoList") or []:
            for rv in day.get("raceVoList") or []:
                race = rv.get("race") or {}
                con.execute(
                    "INSERT OR REPLACE INTO jc_races VALUES (?,?,?,?,?,?,?,?,?)",
                    (race.get("race_id"), race.get("race_no"), race.get("issue_no"),
                     day.get("areaDate"), day.get("week"), race.get("league_name"),
                     race.get("release_time"), json.dumps(rv, ensure_ascii=False), fetched))
                njc += 1
        print(f"竞彩赛程：{njc} 场（{data.get('leagueNames')}）")
    except Exception as e:
        print("竞彩解析失败（原始快照已存）：", e)

    # 2) 模型列表回补窗口
    endpoints = [("/api/forecast/margin/matches", "margin"),
                 ("/api/forecast/poisson/matches", "poisson"),
                 ("/api/forecast/index/diff/matches", "indexdiff"),
                 ("/api/forecast/specialistRecommend/getSpecialistRecommendList", "specialist")]
    grand = 0
    for back in range(args.days):
        d = (today - timedelta(days=back)).isoformat()
        for ep_path, _tag in endpoints:
            if ep_path.startswith("/api/forecast/specialist"):
                url = f"{BASE}{ep_path}?localDate={d}"
            else:
                url = f"{BASE}{ep_path}?date={d}"
            try:
                st, body = fetch(url); total_req += 1
            except Exception as e:
                print("FETCH FAIL", ep_path, d, e); continue
            snap(con, ep_path, d, st, body, fetched)
            try:
                items = json.loads(body).get("data") or []
            except Exception:
                items = []
            if items:
                grand += parse_model_list(con, ep_path, d, items, fetched, tag=_tag)
        con.commit()
    print(f"模型结果入库：{grand} 条（{args.days} 天 × {len(endpoints)} 个端点）")

    # 3) infoTab 快照
    st, body = fetch(f"{BASE}/api/forecast/model/infoTab"); total_req += 1
    snap(con, "/api/forecast/model/infoTab", "today", st, body, fetched)
    con.commit()
    n_raw = con.execute("SELECT COUNT(*) FROM raw_snapshots").fetchone()[0]
    n_jc = con.execute("SELECT COUNT(*) FROM jc_races").fetchone()[0]
    n_mr = con.execute("SELECT COUNT(*) FROM ttyl_model_results").fetchone()[0]
    print(f"请求总数 {total_req}｜raw_snapshots={n_raw} jc_races={n_jc} ttyl_model_results={n_mr}")
    con.close()

if __name__ == "__main__":
    main()

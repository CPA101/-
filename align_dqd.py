#!/usr/bin/env python3
"""懂球帝 ↔ all_leagues.db 球队对齐层。

原理：同一场比赛在两边的日期（±1 天，时区差）与比分必然相同。
用唯一命中的比赛给 (懂球帝球队ID → 英文队名) 投票，多数票且占比≥80% 才认定。
产物：data/dqd_team_map.csv + 控制台覆盖率报告。
"""
import csv, os, sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PAIRS = {  # 懂球帝联赛名 -> all_leagues.db div
    "英超": "E0", "西甲": "SP1", "德甲": "D1",
    "意甲": "I1", "法甲": "F1", "中超": "CHN",
}

def dparse(s):
    y, m, d = s[:10].split("-")
    return date(int(y), int(m), int(d))

def main():
    dqd = sqlite3.connect(os.path.join(HERE, "data", "dqd.db"))
    fd = sqlite3.connect(os.path.join(HERE, "data", "all_leagues.db"))
    votes = defaultdict(Counter)       # (league, dqd_team_id) -> Counter(english)
    team_name = {}
    rows_out = []
    for league, div in PAIRS.items():
        fd_idx = defaultdict(list)     # (date, hg, ag) -> [(home, away)]
        for dt, home, away, hg, ag in fd.execute(
                "SELECT date, home, away, hg, ag FROM matches WHERE div=? AND date>='2021-01-01'", (div,)):
            fd_idx[(dt, hg, ag)].append((home, away))
        played = dqd.execute(
            """SELECT team_a_id, team_a_name, team_b_id, team_b_name, fs_a, fs_b, start_play
               FROM dqd_matches WHERE league=? AND status='Played' AND fs_a IS NOT NULL""",
            (league,)).fetchall()
        n_uniq = n_amb = n_none = 0
        for aid, aname, bid, bname, fa, fb, start in played:
            team_name[(league, aid)] = aname
            team_name[(league, bid)] = bname
            d0 = dparse(start)
            cands = []
            for dd in (-1, 0, 1):
                cands += fd_idx.get(((d0 + timedelta(days=dd)).isoformat(), fa, fb), [])
            if len(cands) == 1:
                n_uniq += 1
                votes[(league, aid)][cands[0][0]] += 1
                votes[(league, bid)][cands[0][1]] += 1
            elif len(cands) > 1:
                n_amb += 1
            else:
                n_none += 1
        mapped = {}
        for (lg, tid), cnt in votes.items():
            if lg != league:
                continue
            top, n = cnt.most_common(1)[0]
            total = sum(cnt.values())
            if n >= 3 and n / total >= 0.8:
                mapped[tid] = top
        # 用映射回验：已映射球队的比赛有多少能在 fd 中唯一对上
        hit = tot = 0
        for aid, aname, bid, bname, fa, fb, start in played:
            if aid in mapped and bid in mapped:
                tot += 1
                d0 = dparse(start)
                cands = []
                for dd in (-1, 0, 1):
                    cands += [c for c in fd_idx.get(((d0 + timedelta(days=dd)).isoformat(), fa, fb), [])
                              if c == (mapped[aid], mapped[bid])]
                if len(cands) == 1:
                    hit += 1
        n_teams = dqd.execute("SELECT COUNT(*) FROM dqd_teams WHERE league=?", (league,)).fetchone()[0]
        print(f"{league}: 球队 {n_teams} 已映射 {len(mapped)} | Played {len(played)} "
              f"唯一命中 {n_uniq} 歧义 {n_amb} 无候选 {n_none} | 映射回验 {hit}/{tot}")
        for (lg, tid), cnt in votes.items():
            if lg != league:
                continue
            top, n = cnt.most_common(1)[0]
            total = sum(cnt.values())
            if tid in mapped:
                rows_out.append([league, tid, team_name.get((league, tid), ""), top, total, f"{n/total:.2f}", "ok"])
            else:
                rows_out.append([league, tid, team_name.get((league, tid), ""), top, total, f"{n/total:.2f}", "unresolved"])
        # 完全没拿到票的球队也登记
        seen = {r[1] for r in rows_out if r[0] == league}
        for tid, tname in dqd.execute("SELECT team_id, name FROM dqd_teams WHERE league=?", (league,)):
            if tid not in seen:
                rows_out.append([league, tid, tname, "", 0, "", "no_votes"])
    out = os.path.join(HERE, "data", "dqd_team_map.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["league", "dqd_team_id", "dqd_name", "english_name", "votes", "top_share", "status"])
        w.writerows(sorted(rows_out))
    ok = sum(1 for r in rows_out if r[6] == "ok")
    print(f"\n映射表 -> {out}：{ok}/{len(rows_out)} 支球队已对齐")

if __name__ == "__main__":
    main()

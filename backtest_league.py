"""
任意联赛 walk-forward 抽查回测：Dixon-Coles vs 市场基准（Pinnacle 收盘去水，缺失时 B365 收盘，再缺失用 AVG 收盘）。
用法：python3 backtest_league.py "China" "Super League" 2023-01-01
"""
import sys
import numpy as np
import pandas as pd
import sqlite3, os
import model as M

def main():
    country, league, test_from = sys.argv[1], sys.argv[2], sys.argv[3]
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "all_leagues.db")
    con = sqlite3.connect(db)
    df = pd.read_sql_query(
        "SELECT m.id, m.date, m.home, m.away, m.hg, m.ag, m.y FROM matches m "
        "WHERE m.country=? AND m.league=? ORDER BY m.date", con, params=(country, league))
    odds = pd.read_sql_query(
        "SELECT o.match_id, o.book, o.oH, o.oD, o.oA FROM odds o JOIN matches m ON m.id=o.match_id "
        "WHERE m.country=? AND m.league=? AND o.kind='close' AND o.book IN ('PIN','B365','AVG')",
        con, params=(country, league))
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    prio = {"PIN": 0, "B365": 1, "AVG": 2}
    odds["prio"] = odds["book"].map(prio)
    odds = odds.sort_values("prio").drop_duplicates("match_id")
    omap = {r.match_id: M.devig(r.oH, r.oD, r.oA) for r in odds.itertuples()}
    test = df[df["date"] >= test_from]
    rows = []
    for per in sorted(test["date"].dt.to_period("M").unique()):
        ms = per.to_timestamp()
        train = df[df["date"] < ms]
        batch = test[test["date"].dt.to_period("M") == per]
        batch = batch[batch["id"].isin(omap)]
        if len(train) < 300 or len(batch) == 0:
            continue
        fit = M.fit_model(train, ms, use_dc=True)
        for r in batch.itertuples():
            Mx, _, _ = M.score_matrix(fit, r.home, r.away)
            p = M.probs_from_matrix(Mx) if Mx is not None else omap[r.id]
            rows.append((r.y, omap[r.id], p))
        print(f"{per}: train={len(train)} test={len(batch)}", flush=True)
    y = np.array([r[0] for r in rows])
    print(f"\n{country}/{league} 抽查：n={len(y)}（{test_from} 起，基准=Pinnacle收盘优先）")
    for name, idx in [("市场基准", 1), ("Dixon-Coles", 2)]:
        P = np.array([r[idx] for r in rows])
        rps = np.mean([M.rps(P[i], y[i]) for i in range(len(y))])
        ll = np.mean([M.logloss(P[i], y[i]) for i in range(len(y))])
        acc = float(np.mean(P.argmax(axis=1) == y))
        print(f"{name}: RPS={rps:.4f} LogLoss={ll:.4f} 命中率={acc:.3f}")

if __name__ == "__main__":
    main()

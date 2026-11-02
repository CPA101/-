"""从 all_leagues.db 读数据的加载器：联赛比赛表 + 赔率向量池。"""
import os, sqlite3
import numpy as np
import pandas as pd

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "all_leagues.db")

def _con():
    return sqlite3.connect(DB)

def list_leagues():
    con = _con()
    rows = con.execute(
        "SELECT country, league, COUNT(*) n FROM matches GROUP BY 1,2 ORDER BY n DESC").fetchall()
    con.close()
    return rows

def find_league(query):
    """模糊匹配联赛：query 命中 country 或 league 名即返回 (country, league)。"""
    q = query.strip().lower()
    leagues = list_leagues()
    for c, l, _ in leagues:
        if q == l.lower() or q == c.lower():
            return c, l
    hits = [(c, l) for c, l, _ in leagues if q in l.lower() or q in c.lower()]
    return hits[0] if len(hits) == 1 else (hits if hits else None)

def load_league(country, league):
    con = _con()
    df = pd.read_sql_query(
        "SELECT date, season, home, away, hg, ag, y FROM matches "
        "WHERE country=? AND league=? ORDER BY date",
        con, params=(country, league))
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    return df

def load_odds_pool(book="PIN", kind="close", country=None, league=None):
    """赔率向量池：每行一场带该公司收盘赔率的比赛（含赛果），供同赔查询。"""
    con = _con()
    sql = ("SELECT m.date, m.country, m.league, m.home, m.away, m.hg, m.ag, m.y, "
           "o.oH, o.oD, o.oA FROM matches m JOIN odds o ON o.match_id=m.id "
           "WHERE o.book=? AND o.kind=?")
    params = [book, kind]
    if country and league:
        sql += " AND m.country=? AND m.league=?"
        params += [country, league]
    df = pd.read_sql_query(sql, con, params=params)
    con.close()
    q = 1.0 / df[["oH", "oD", "oA"]].to_numpy(dtype=float)
    df["p"] = list(q / q.sum(axis=1, keepdims=True))
    return df

def same_odds(query_odds, k=100, country=None, league=None, book="PIN"):
    """历史同赔：与 query_odds（原始赔率三元组）最接近的 k 场历史比赛的赛果分布。
    优先在指定联赛内查；样本不足 k/2 时自动扩到全库并标注。"""
    import model as M
    qp = M.devig(*query_odds)
    scope = "同联赛"
    pool = load_odds_pool(book=book, country=country, league=league) if league else load_odds_pool(book=book)
    if league and len(pool) < k // 2:
        pool = load_odds_pool(book=book)
        scope = "全库（同联赛样本不足）"
    P = np.stack(pool["p"].to_numpy())
    d = np.sqrt(((P - qp) ** 2).sum(axis=1))
    idx = np.argsort(d)[:k]
    sub = pool.iloc[idx]
    cnt = np.bincount(sub["y"].to_numpy(), minlength=3)
    return {"dist": cnt / cnt.sum(), "n": len(sub), "scope": scope,
            "book": book, "avg_dist": float(d[idx].mean()),
            "nearest": sub.head(5), "query_probs": qp}

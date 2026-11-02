"""
全联赛版预测工具：从 all_leagues.db 取任意联赛数据拟合 Dixon-Coles。

用法：
  python3 predict2.py --league "Premier League" "Arsenal" "Liverpool"
  python3 predict2.py --league 中超 "Chengdu Rongcheng" "Dalian Yingbo" --odds 1.81 3.75 3.80
  （--league 可用国家或联赛名的任意子串，如 Spain / La Liga / Serie A / 中超需用 China 或 Super League 并配合球队名消歧）

带 --odds 时额外输出：去水市场概率、分歧、以及历史同赔分布（同联赛优先）。
回测结论仍适用：概率校准可用，但未跑赢收盘市场基准；输出是概率估计，不是投注建议。
"""
import argparse, sys
import numpy as np
import pandas as pd
import model as M
import dbload

ALIASES = {"中超": ("China", "Super League"), "英超": ("England", "Premier League"),
           "西甲": ("Spain", "La Liga"), "意甲": ("Italy", "Serie A"),
           "德甲": ("Germany", "Bundesliga"), "法甲": ("France", "Ligue 1"),
           "日职": ("Japan", "J1 League"), "韩职": ("South Korea", "K League 1"),
           "美职联": ("USA", "MLS"), "巴甲": ("Brazil", "Serie A")}

def find_team(name, teams):
    n = name.strip().lower()
    exact = [t for t in teams if t.lower() == n]
    if exact: return exact[0]
    part = [t for t in teams if n in t.lower()]
    return part[0] if len(part) == 1 else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("home"); ap.add_argument("away")
    ap.add_argument("--odds", nargs=3, type=float, metavar=("H", "D", "A"))
    args = ap.parse_args()
    hit = ALIASES.get(args.league) or dbload.find_league(args.league)
    if hit is None or isinstance(hit, list):
        print("联赛匹配不唯一或不存在，候选：")
        for c, l, n in dbload.list_leagues():
            print(f"  {c} / {l}（{n} 场）")
        sys.exit(1)
    country, league = hit
    df = dbload.load_league(country, league)
    if len(df) < 200:
        print(f"{country}/{league} 样本只有 {len(df)} 场，不足以拟合。"); sys.exit(1)
    fit = M.fit_model(df, df["date"].max() + pd.Timedelta(days=1), use_dc=True)
    home = find_team(args.home, fit["teams"]); away = find_team(args.away, fit["teams"])
    if not home or not away:
        print(f"球队没找到。{league} 当前覆盖球队：", ", ".join(fit["teams"])); sys.exit(1)
    Mx, lh, la = M.score_matrix(fit, home, away)
    p = M.probs_from_matrix(Mx)
    print(f"\n[{country} / {league}] {home}（主） vs {away}（客）")
    print(f"Dixon-Coles 拟合于该联赛 {fit['n_train']} 场，rho={fit['rho']:.3f}")
    print(f"预期进球 λ：{home} {lh:.2f} ｜ {away} {la:.2f}")
    print(f"胜平负概率：主胜 {p[0]*100:.1f}% ｜ 平 {p[1]*100:.1f}% ｜ 客胜 {p[2]*100:.1f}%")
    flat = sorted([(Mx[i, j], i, j) for i in range(6) for j in range(6)], reverse=True)[:5]
    print("最可能比分：" + "，".join(f"{i}-{j}（{v*100:.1f}%）" for v, i, j in flat))
    ou = float(Mx[np.add.outer(np.arange(M.MAXG + 1), np.arange(M.MAXG + 1)) >= 3].sum())
    print(f"总进球大于2.5：{ou*100:.1f}% ｜ 双方都进球：{float(Mx[1:, 1:].sum())*100:.1f}%")
    if args.odds:
        mkt = M.devig(*args.odds)
        d = p - mkt
        print(f"\n你给的赔率去水后：主胜 {mkt[0]*100:.1f}% ｜ 平 {mkt[1]*100:.1f}% ｜ 客胜 {mkt[2]*100:.1f}%")
        print(f"模型分歧：主胜 {d[0]*100:+.1f} ｜ 平 {d[1]*100:+.1f} ｜ 客胜 {d[2]*100:+.1f} 个百分点（回测提示：大分歧时先怀疑模型）")
        r = dbload.same_odds(tuple(args.odds), k=100, country=country, league=league)
        dd = r["dist"]
        print(f"历史同赔（{r['scope']}，{r['book']}收盘，n={r['n']}）：主胜 {dd[0]*100:.1f}% ｜ 平 {dd[1]*100:.1f}% ｜ 客胜 {dd[2]*100:.1f}%")

if __name__ == "__main__":
    main()

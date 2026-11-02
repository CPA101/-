"""
预测工具：用全部已赛数据拟合 Dixon-Coles，输入两支球队输出概率。

用法：
  python3 predict.py "Arsenal" "Liverpool"
  python3 predict.py "Arsenal" "Liverpool" --odds 2.10 3.40 3.20   # 附带某家赔率时同时给出去水市场概率与分歧

注意：回测结论（见 回测报告.md）——本模型概率校准良好，但未跑赢收盘市场基准，
分歧大时历史上是市场更准。输出是概率估计，不是投注建议。
"""
import argparse, sys
import numpy as np
import model as M

def find_team(name, teams):
    n = name.strip().lower()
    exact = [t for t in teams if t.lower() == n]
    if exact: return exact[0]
    part = [t for t in teams if n in t.lower()]
    if len(part) == 1: return part[0]
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("home"); ap.add_argument("away")
    ap.add_argument("--odds", nargs=3, type=float, metavar=("H", "D", "A"))
    args = ap.parse_args()
    import pandas as pd
    df = M.load_all()
    fit = M.fit_model(df, df["date"].max() + pd.Timedelta(days=1), use_dc=True)
    home = find_team(args.home, fit["teams"]); away = find_team(args.away, fit["teams"])
    if not home or not away:
        print("找不到球队。当前数据覆盖球队：", ", ".join(fit["teams"])); sys.exit(1)
    Mx, lh, la = M.score_matrix(fit, home, away)
    p = M.probs_from_matrix(Mx)
    print(f"\n{home}（主） vs {away}（客）  —— Dixon-Coles，拟合于 {fit['n_train']} 场已赛比赛，rho={fit['rho']:.3f}")
    print(f"预期进球 λ：{home} {lh:.2f} ｜ {away} {la:.2f}")
    print(f"胜平负概率：主胜 {p[0]*100:.1f}% ｜ 平 {p[1]*100:.1f}% ｜ 客胜 {p[2]*100:.1f}%")
    if args.odds:
        mkt = M.devig(*args.odds)
        d = p - mkt
        print(f"市场去水概率：主胜 {mkt[0]*100:.1f}% ｜ 平 {mkt[1]*100:.1f}% ｜ 客胜 {mkt[2]*100:.1f}%")
        print(f"分歧（模型−市场）：主胜 {d[0]*100:+.1f} ｜ 平 {d[1]*100:+.1f} ｜ 客胜 {d[2]*100:+.1f} 个百分点")
        print("（回测提示：本模型与市场大分歧的历史场次里，市场更准——分歧先怀疑模型。）")
    flat = sorted([(Mx[i, j], i, j) for i in range(6) for j in range(6)], reverse=True)[:5]
    print("最可能比分：" + "，".join(f"{i}-{j}（{v*100:.1f}%）" for v, i, j in flat))
    ou = float(Mx[np.add.outer(np.arange(M.MAXG + 1), np.arange(M.MAXG + 1)) >= 3].sum())
    btts = float(Mx[1:, 1:].sum())
    print(f"总进球大于2.5：{ou*100:.1f}% ｜ 双方都进球：{btts*100:.1f}%")

if __name__ == "__main__":
    main()

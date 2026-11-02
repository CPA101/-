"""
Walk-forward 回测：测试集 = 2023-24 赛季起的全部已赛比赛。
每月重拟合一次（只用当月 1 日之前的数据），杜绝未来信息泄漏。
四条线同场对比：市场基准（Bet365 收盘赔率去水）/ 历史同赔 kNN / 攻防泊松 / Dixon-Coles。
每场的四组概率全部落盘 predictions_log.csv —— 这张表就是冻结账本。
"""
import numpy as np
import pandas as pd
import model as M

TEST_FROM = "2023-08-01"

def main():
    df = M.load_all()
    df["mkt"] = df.apply(lambda r: M.devig(r["oH"], r["oD"], r["oA"]), axis=1)
    test = df[df["date"] >= TEST_FROM].copy()
    rows = []
    months = sorted(test["date"].dt.to_period("M").unique())
    for per in months:
        month_start = per.to_timestamp()
        train = df[df["date"] < month_start]
        batch = test[test["date"].dt.to_period("M") == per]
        if len(train) < 300 or len(batch) == 0:
            continue
        fit_pois = M.fit_model(train, month_start, use_dc=False)
        fit_dc = M.fit_model(train, month_start, use_dc=True)
        hist_probs = np.stack(train["mkt"].to_numpy())
        hist_y = train["y"].to_numpy()
        for _, r in batch.iterrows():
            mkt = r["mkt"]
            knn = M.knn_odds_probs(hist_probs, hist_y, mkt)
            out = {"date": r["date"].date(), "home": r["home"], "away": r["away"],
                   "hg": r["hg"], "ag": r["ag"], "y": int(r["y"])}
            for name, p in [("mkt", mkt), ("knn", knn)]:
                out[f"{name}_H"], out[f"{name}_D"], out[f"{name}_A"] = p
            for name, fit in [("pois", fit_pois), ("dc", fit_dc)]:
                Mx, lh, la = M.score_matrix(fit, r["home"], r["away"])
                p = M.probs_from_matrix(Mx) if Mx is not None else mkt
                out[f"{name}_H"], out[f"{name}_D"], out[f"{name}_A"] = p
                if name == "dc":
                    out["dc_lh"], out["dc_la"] = lh, la
            rows.append(out)
        print(f"{per}: train={len(train)} test={len(batch)} rho={fit_dc['rho']:.3f}", flush=True)
    log = pd.DataFrame(rows)
    log.to_csv("predictions_log.csv", index=False)

    lines = ["mkt", "knn", "pois", "dc"]
    names = {"mkt": "市场基准(收盘去水)", "knn": "历史同赔kNN", "pois": "攻防泊松", "dc": "Dixon-Coles"}
    print(f"\n测试场次 n={len(log)}（{log['date'].min()} ~ {log['date'].max()}）")
    print(f"{'模型':<22}{'RPS↓':>8}{'LogLoss↓':>10}{'Brier↓':>8}{'命中率':>8}")
    summary = {}
    for ln in lines:
        P = log[[f"{ln}_H", f"{ln}_D", f"{ln}_A"]].to_numpy()
        y = log["y"].to_numpy()
        rpss = np.mean([M.rps(P[i], y[i]) for i in range(len(y))])
        lls = np.mean([M.logloss(P[i], y[i]) for i in range(len(y))])
        brs = np.mean([M.brier(P[i], y[i]) for i in range(len(y))])
        acc = float(np.mean(P.argmax(axis=1) == y))
        summary[ln] = (rpss, lls, brs, acc)
        print(f"{names[ln]:<22}{rpss:>8.4f}{lls:>10.4f}{brs:>8.4f}{acc:>8.3f}")
    # 校准：DC 与市场在 0.5-0.7 桶的对比（主胜概率）
    for ln in ["mkt", "dc"]:
        p = log[f"{ln}_H"].to_numpy(); hit = (log["y"] == 0).to_numpy()
        sel = (p >= 0.5) & (p < 0.7)
        if sel.sum() > 30:
            print(f"校准[{ln}] 主胜概率0.5-0.7桶: n={sel.sum()} 平均预测={p[sel].mean():.3f} 实际发生率={hit[sel].mean():.3f}")

if __name__ == "__main__":
    main()

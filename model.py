"""
赛事预测模型核心：攻防强度泊松 / Dixon-Coles + 市场基准 + 历史同赔基线。

方法论（见 自建比赛预测模型借鉴要点.md）：
- 攻防参数化：log λ_主 = mu + home_adv + att[主] - def[客]；log λ_客 = mu + att[客] - def[主]
- Dixon-Coles：对 (0,0)(1,0)(0,1)(1,1) 四个低比分乘 tau 修正（参数 rho）
- 拟合：带时间衰减权重（半衰期可调）的极大似然，walk-forward 时只用赛前数据
- 市场基准：Bet365 收盘赔率等比去水
- 历史同赔：以市场概率向量为坐标，在历史比赛中找 k 近邻看赛果分布
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAXG = 10  # 比分矩阵截断（0..10 球）


def load_all(data_dir="data"):
    import glob, os
    frames = []
    for f in sorted(glob.glob(os.path.join(data_dir, "E0_*.csv"))):
        d = pd.read_csv(f)
        d["season"] = os.path.basename(f)[3:7]
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    keep = ["date", "season", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
            "B365CH", "B365CD", "B365CA"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.rename(columns={"HomeTeam": "home", "AwayTeam": "away",
                            "FTHG": "hg", "FTAG": "ag",
                            "B365CH": "oH", "B365CD": "oD", "B365CA": "oA"})
    df = df.dropna(subset=["date", "hg", "ag"])  # 只留已赛
    df["hg"] = df["hg"].astype(int); df["ag"] = df["ag"].astype(int)
    df["y"] = np.where(df["hg"] > df["ag"], 0, np.where(df["hg"] == df["ag"], 1, 2))  # 0主胜 1平 2客胜
    df = df.sort_values("date").reset_index(drop=True)
    return df


def devig(oH, oD, oA):
    """等比去水：赔率 -> 隐含概率"""
    q = np.array([1.0 / oH, 1.0 / oD, 1.0 / oA], dtype=float)
    return q / q.sum()


def _tau(x, y, lh, la, rho):
    if x == 0 and y == 0:
        return 1 - lh * la * rho
    if x == 0 and y == 1:
        return 1 + lh * rho
    if x == 1 and y == 0:
        return 1 + la * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def fit_model(train, ref_date, half_life_days=270, use_dc=True):
    """在 train（全部 < ref_date 的比赛）上拟合，返回参数字典。"""
    teams = sorted(set(train["home"]) | set(train["away"]))
    tidx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = train["home"].map(tidx).to_numpy()
    ai = train["away"].map(tidx).to_numpy()
    hg = train["hg"].to_numpy(dtype=float)
    ag = train["ag"].to_numpy(dtype=float)
    age = (pd.Timestamp(ref_date) - train["date"]).dt.days.to_numpy(dtype=float)
    w = 0.5 ** (age / half_life_days)

    def unpack(p):
        att = p[:n] - p[:n].mean()          # 中心化保证可识别
        dfn = p[n:2 * n] - p[n:2 * n].mean()
        mu, home_adv = p[2 * n], p[2 * n + 1]
        rho = p[2 * n + 2] if use_dc else 0.0
        return att, dfn, mu, home_adv, rho

    def nll(p):
        att, dfn, mu, home_adv, rho = unpack(p)
        lh = np.exp(mu + home_adv + att[hi] - dfn[ai])
        la = np.exp(mu + att[ai] - dfn[hi])
        ll = (poisson.logpmf(hg, lh) + poisson.logpmf(ag, la))
        if use_dc:
            tau = np.ones(len(hg))
            m00 = (hg == 0) & (ag == 0); m01 = (hg == 0) & (ag == 1)
            m10 = (hg == 1) & (ag == 0); m11 = (hg == 1) & (ag == 1)
            tau[m00] = 1 - lh[m00] * la[m00] * rho
            tau[m01] = 1 + lh[m01] * rho
            tau[m10] = 1 + la[m10] * rho
            tau[m11] = 1 - rho
            ll = ll + np.log(np.clip(tau, 1e-9, None))
        return -float(np.sum(w * ll))

    p0 = np.zeros(2 * n + 3)
    p0[2 * n] = np.log(1.35)   # mu 初值
    p0[2 * n + 1] = 0.25       # 主场优势初值
    bounds = [(-3, 3)] * (2 * n) + [(-1.5, 1.5), (-0.5, 1.0)]
    bounds += [(-0.3, 0.3)] if use_dc else [(0.0, 0.0)]  # 非 DC 时把 rho 钉死在 0
    res = minimize(nll, p0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 500})
    att, dfn, mu, home_adv, rho = unpack(res.x)
    return {"teams": teams, "att": att, "def": dfn, "mu": mu,
            "home_adv": home_adv, "rho": rho if use_dc else 0.0,
            "nll": res.fun, "n_train": len(train)}


def score_matrix(params, home, away):
    tidx = {t: i for i, t in enumerate(params["teams"])}
    if home not in tidx or away not in tidx:
        return None, None, None
    lh = np.exp(params["mu"] + params["home_adv"] +
                params["att"][tidx[home]] - params["def"][tidx[away]])
    la = np.exp(params["mu"] +
                params["att"][tidx[away]] - params["def"][tidx[home]])
    ph = poisson.pmf(np.arange(MAXG + 1), lh)
    pa = poisson.pmf(np.arange(MAXG + 1), la)
    M = np.outer(ph, pa)
    rho = params["rho"]
    if rho != 0.0:
        M[0, 0] *= _tau(0, 0, lh, la, rho); M[0, 1] *= _tau(0, 1, lh, la, rho)
        M[1, 0] *= _tau(1, 0, lh, la, rho); M[1, 1] *= _tau(1, 1, lh, la, rho)
    M = M / M.sum()
    return M, float(lh), float(la)


def probs_from_matrix(M):
    pH = float(np.tril(M, -1).sum()); pD = float(np.trace(M)); pA = float(np.triu(M, 1).sum())
    return np.array([pH, pD, pA])


def knn_odds_probs(hist_probs, hist_y, query, k=50, base=None):
    """历史同赔：概率空间 k 近邻的赛果分布（向全局基准平滑）。"""
    if base is None:
        base = np.bincount(hist_y, minlength=3) / len(hist_y)
    d = np.sqrt(((hist_probs - query) ** 2).sum(axis=1))
    idx = np.argsort(d)[:k]
    cnt = np.bincount(hist_y[idx], minlength=3).astype(float)
    alpha = 10.0  # 平滑强度
    return (cnt + alpha * base) / (k + alpha)


def rps(p, y):
    e = np.zeros(3); e[y] = 1.0
    return 0.5 * float(np.sum((np.cumsum(p)[:2] - np.cumsum(e)[:2]) ** 2))


def logloss(p, y):
    return float(-np.log(max(p[y], 1e-12)))


def brier(p, y):
    e = np.zeros(3); e[y] = 1.0
    return float(np.sum((p - e) ** 2))

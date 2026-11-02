# 赛事分析预测模型（英超）

按《自建比赛预测模型借鉴要点》（~/workspace/rea-targets/tiantianyouliao/）的路线搭建：
市场基准与历史同赔作对照、攻防泊松为 v1、Dixon-Coles 为 v2，walk-forward 回测裁定去留。

- `model.py` — 模型核心（攻防泊松/DC 拟合与预测、去水、历史同赔 kNN、RPS/LogLoss/Brier）
- `backtest.py` — walk-forward 回测，逐场概率写入 `predictions_log.csv`（冻结账本）
- `predict.py` — 英超版预测工具：`python3 predict.py "Arsenal" "Liverpool" [--odds H D A]`
- `predict2.py` — **全联赛版**：`python3 predict2.py --league 中超 "Chengdu Rongcheng" "Dalian Yingbo" [--odds H D A]`（--league 支持英超/西甲/中超等别名或任意国家/联赛名子串；带 --odds 时附市场分歧 + 历史同赔分布）
- `same_odds.py` — 历史同赔查询：`python3 same_odds.py 1.81 3.75 3.80 [--league X --country Y --book PIN|B365]`
- `dbload.py` — all_leagues.db 加载器（联赛表/赔率池/同赔函数）
- `backtest_league.py` — 任意联赛 walk-forward 抽查：`python3 backtest_league.py "China" "Super League" 2023-01-01`
- `回测报告.md` — 方法、结果与裁定（结论：校准良好，未跑赢收盘市场基准）
- `data/` — 英超 2019-20 ~ 2026-27 原始 CSV（模型 v1/v2 用）
- `data/all_leagues.db` — **全联赛数据库**：41 个联赛、267,457 场（2000~2026）、108 万行多家公司开盘/收盘赔率；原始档在 `data/raw/`，构建脚本 `fetch_all.py` + `build_db.py`，覆盖详情见 `数据覆盖报告.md`

数据刷新：从 football-data.co.uk 重新下载对应赛季 E0.csv 覆盖 data/ 后重跑 backtest.py 即可。

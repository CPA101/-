# 赛事分析预测模型（英超）

## 本仓库说明（GitHub 同步版）

- 本仓库含模型的**全部代码、文档与原始数据**：`data/raw/` 下 608 个联赛原始 CSV（41 个联赛、2000–2026）、`data/` 下英超建模数据、`predictions_log.csv` 回测冻结账本、`data/ttyl_export/` 下天天有料采集数据（jc_races 全量；raw_snapshots 与 ttyl_model_results 因单文件体积拆成 part1/part2(/part3)，拼接即全量）、`data/dqd_export/` 下懂球帝采集数据（六联赛各 6 季共 12,075 场赛程赛果 + 球队表）与 `data/dqd_team_map.csv` 球队中英对齐表（166/166 支球队，比赛回验 99.6%）。数据源评估见 `平台数据源探针记录.md`。
- 三个 SQLite 库文件（`data/all_leagues.db`、`data/ttyl.db`、`data/dqd.db`）因体积/二进制限制未入库，可完全重建：`python3 fetch_all.py && python3 build_db.py` 生成 all_leagues.db；ttyl.db 由 `collect_ttyl.py` 采集生成，其内容已以 CSV 形式存放在 `data/ttyl_export/`；dqd.db 由 `collect_dqd.py` 采集、`align_dqd.py` 对齐生成，解析后数据已以 CSV 存放在 `data/dqd_export/`（原始 JSON 快照为可重抓的回执，未随仓保存）。
- `data/raw/` 中 15 个早期赛季文件原为 Windows-1252 编码，入库时已转码为 UTF-8（文本内容不变）。

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

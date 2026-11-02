"""
把 data/raw 下的全部 football-data CSV 统一入库 SQLite：
  matches(id, source, country, league, div, season, date, home, away, hg, ag, y)
  odds(match_id, book, kind, oH, oD, oA)   -- kind: open / close；book: B365 / PIN / AVG / MAX
列名随年代变化，缺失即跳过；球队名沿用源文件写法（同联赛内一致）。
"""
import glob, os, sqlite3
import numpy as np
import pandas as pd

ROOT = os.path.expanduser("~/workspace/match-prediction-model")
RAW = os.path.join(ROOT, "data", "raw")
DB = os.path.join(ROOT, "data", "all_leagues.db")

DIV_META = {
    "E0": ("England", "Premier League"), "E1": ("England", "Championship"),
    "E2": ("England", "League One"), "E3": ("England", "League Two"),
    "EC": ("England", "National League"),
    "SC0": ("Scotland", "Premiership"), "SC1": ("Scotland", "Championship"),
    "SC2": ("Scotland", "League One"), "SC3": ("Scotland", "League Two"),
    "D1": ("Germany", "Bundesliga"), "D2": ("Germany", "2. Bundesliga"),
    "I1": ("Italy", "Serie A"), "I2": ("Italy", "Serie B"),
    "SP1": ("Spain", "La Liga"), "SP2": ("Spain", "Segunda"),
    "F1": ("France", "Ligue 1"), "F2": ("France", "Ligue 2"),
    "N1": ("Netherlands", "Eredivisie"), "B1": ("Belgium", "Pro League"),
    "P1": ("Portugal", "Primeira Liga"), "T1": ("Turkey", "Super Lig"),
    "G1": ("Greece", "Super League"),
}
EXTRA_META = {
    "ARG": ("Argentina", "Primera"), "AUT": ("Austria", "Bundesliga"),
    "BRA": ("Brazil", "Serie A"), "CHN": ("China", "Super League"),
    "DNK": ("Denmark", "Superliga"), "FIN": ("Finland", "Veikkausliiga"),
    "IRL": ("Ireland", "Premier Division"), "JPN": ("Japan", "J1 League"),
    "MEX": ("Mexico", "Liga MX"), "NOR": ("Norway", "Eliteserien"),
    "POL": ("Poland", "Ekstraklasa"), "ROU": ("Romania", "Liga I"),
    "CHL": ("Chile", "Primera"), "COL": ("Colombia", "Primera A"),
    "KOR": ("South Korea", "K League 1"),
    "RUS": ("Russia", "Premier League"), "SWE": ("Sweden", "Allsvenskan"),
    "SWZ": ("Switzerland", "Super League"), "USA": ("USA", "MLS"),
}
ODDS_MAP = [  # (book, kind, H列, D列, A列)
    ("B365", "open", "B365H", "B365D", "B365A"),
    ("B365", "close", "B365CH", "B365CD", "B365CA"),
    ("PIN", "close", "PSCH", "PSCD", "PSCA"),
    ("PIN", "open", "PSH", "PSD", "PSA"),
    ("AVG", "close", "AvgCH", "AvgCD", "AvgCA"),
    ("AVG", "open", "AvgH", "AvgD", "AvgA"),
    ("MAX", "close", "MaxCH", "MaxCD", "MaxCA"),
    ("MAX", "open", "MaxH", "MaxD", "MaxA"),
    ("BW", "open", "BWH", "BWD", "BWA"),
    ("BF", "close", "BFCH", "BFCD", "BFCA"),
    ("BFE", "close", "BFECH", "BFECD", "BFECA"),
]

ALIASES = {"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG"}

def season_label(code):
    y = 2000 + int(code[:2])
    return f"{y}-{str(y + 1)[-2:]}"

def rows_from(df, source, country, league, div, season):
    df = df.copy()
    df = df.rename(columns={k: v for k, v in ALIASES.items() if k in df.columns})
    df["date"] = pd.to_datetime(df.get("Date"), dayfirst=True, errors="coerce")
    for c in ["HomeTeam", "AwayTeam", "FTHG", "FTAG"]:
        if c not in df.columns:
            return [], []
    df = df.dropna(subset=["date", "FTHG", "FTAG"])
    ms, os_ = [], []
    for _, r in df.iterrows():
        hg, ag = int(r["FTHG"]), int(r["FTAG"])
        y = 0 if hg > ag else (1 if hg == ag else 2)
        ms.append((source, country, league, div, season, r["date"].strftime("%Y-%m-%d"),
                   str(r["HomeTeam"]).strip(), str(r["AwayTeam"]).strip(), hg, ag, y))
        for book, kind, ch, cd, ca in ODDS_MAP:
            if ch in df.columns and pd.notna(r.get(ch)) and pd.notna(r.get(cd)) and pd.notna(r.get(ca)):
                try:
                    os_.append((len(ms) - 1, book, kind, float(r[ch]), float(r[cd]), float(r[ca])))
                except (TypeError, ValueError):
                    pass
    return ms, os_

def main():
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE matches(id INTEGER PRIMARY KEY, source TEXT, country TEXT, league TEXT,
                         div TEXT, season TEXT, date TEXT, home TEXT, away TEXT,
                         hg INT, ag INT, y INT);
    CREATE TABLE odds(match_id INT, book TEXT, kind TEXT, oH REAL, oD REAL, oA REAL);
    CREATE INDEX idx_m ON matches(country, league, date);
    CREATE INDEX idx_o ON odds(match_id, book, kind);
    """)
    base_id = 0
    files = sorted(glob.glob(f"{RAW}/main/*.csv")) + sorted(glob.glob(f"{RAW}/extra/*.csv"))

    def insert_block(ms, os_):
        nonlocal base_id
        if not ms:
            return
        con.executemany("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(base_id + i + 1, *m) for i, m in enumerate(ms)])
        con.executemany("INSERT INTO odds VALUES (?,?,?,?,?,?)",
                        [(base_id + o[0] + 1, *o[1:]) for o in os_])
        base_id += len(ms)

    for f in files:
        name = os.path.basename(f)[:-4]
        try:
            df = pd.read_csv(f, encoding="utf-8", encoding_errors="ignore")
        except Exception:
            try:
                df = pd.read_csv(f, encoding="utf-8", encoding_errors="ignore",
                                 engine="python", on_bad_lines="skip")
                print("recovered with python engine:", name)
            except Exception as e:
                print("SKIP unreadable", name, e); continue
        if "_" in name and name.split("_")[0] in DIV_META:
            div, scode = name.split("_")
            country, league = DIV_META[div]
            ms, os_ = rows_from(df, "main", country, league, div, season_label(scode))
            insert_block(ms, os_)
        elif name in EXTRA_META:
            country, league = EXTRA_META[name]
            if "Season" in df.columns:
                for ssn, sub in df.groupby("Season"):
                    ms, os_ = rows_from(sub, "extra", country, league, name, str(ssn))
                    insert_block(ms, os_)
            else:
                ms, os_ = rows_from(df, "extra", country, league, name, "")
                insert_block(ms, os_)
    con.commit()
    n_m = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    n_o = con.execute("SELECT COUNT(*) FROM odds").fetchone()[0]
    n_l = con.execute("SELECT COUNT(DISTINCT country||league) FROM matches").fetchone()[0]
    rng = con.execute("SELECT MIN(date), MAX(date) FROM matches").fetchone()
    print(f"matches={n_m} odds_rows={n_o} leagues={n_l} range={rng[0]}..{rng[1]}")
    print(f"db size = {os.path.getsize(DB)/1e6:.0f} MB")
    con.close()

if __name__ == "__main__":
    main()

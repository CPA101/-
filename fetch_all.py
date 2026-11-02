import os, time, concurrent.futures, urllib.request, urllib.error
BASE = os.path.expanduser("~/workspace/match-prediction-model/data/raw")
DIVS = ["E0","E1","E2","E3","EC","SC0","SC1","SC2","SC3","D1","D2","I1","I2",
        "SP1","SP2","F1","F2","N1","B1","P1","T1","G1"]
SEASONS = [f"{y%100:02d}{(y+1)%100:02d}" for y in range(2000, 2027)]
EXTRA = ["ARG","AUT","BRA","CHN","DNK","FIN","IRL","JPN","MEX","NOR","POL",
         "ROU","RUS","SWE","SWZ","USA","AUS","KOR","COL","CHL","PER","ISR","ZAF","IND","ECU","URY"]
def fetch(job):
    kind, code, season = job
    if kind == "main":
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
        path = f"{BASE}/main/{code}_{season}.csv"
    else:
        url = f"https://www.football-data.co.uk/new/{code}.csv"
        path = f"{BASE}/extra/{code}.csv"
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return (code, season, "cached")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
        if len(data) < 500 or b"<html" in data[:200].lower():
            return (code, season, "bad")
        open(path, "wb").write(data)
        return (code, season, f"ok {len(data)}")
    except urllib.error.HTTPError as e:
        return (code, season, f"http{e.code}")
    except Exception as e:
        return (code, season, f"err {type(e).__name__}")
jobs = [("main", d, s) for d in DIVS for s in SEASONS] + [("extra", c, "") for c in EXTRA]
ok = bad = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
    for i, res in enumerate(ex.map(fetch, jobs)):
        if res[2].startswith(("ok", "cached")): ok += 1
        else:
            bad += 1
            if res[2] not in ("http404",):
                print("MISS:", res, flush=True)
        if (i + 1) % 150 == 0:
            print(f"progress {i+1}/{len(jobs)} ok={ok} miss={bad}", flush=True)
print(f"DONE total={len(jobs)} ok={ok} miss={bad}")

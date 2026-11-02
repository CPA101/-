"""
历史同赔查询：给一组胜平负赔率，找历史上赔率最接近的 100 场比赛，看赛果分布。
用法：
  python3 same_odds.py 1.81 3.75 3.80                       # 全库查（Pinnacle 收盘）
  python3 same_odds.py 1.81 3.75 3.80 --league "Super League" --country China
  python3 same_odds.py 2.10 3.40 3.20 --book B365 --k 100
这是天天有料"历史同赔"模型的自建版：无参数、纯查库，分布即输出，不做二次加工。
"""
import argparse
import dbload

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("odds", nargs=3, type=float, metavar=("H", "D", "A"))
    ap.add_argument("--league"); ap.add_argument("--country")
    ap.add_argument("--book", default="PIN", choices=["PIN", "B365", "AVG", "MAX"])
    ap.add_argument("--k", type=int, default=100)
    args = ap.parse_args()
    country, league = args.country, args.league
    if args.league and not args.country:
        hit = dbload.find_league(args.league)
        if isinstance(hit, tuple):
            country, league = hit
    r = dbload.same_odds(tuple(args.odds), k=args.k, country=country, league=league, book=args.book)
    d = r["dist"]
    qp = r["query_probs"]
    print(f"\n查询赔率 {args.odds}（去水概率：主胜 {qp[0]*100:.1f}% / 平 {qp[1]*100:.1f}% / 客胜 {qp[2]*100:.1f}%）")
    print(f"历史同赔分布（{r['scope']}，{r['book']}收盘，n={r['n']}，平均概率距离 {r['avg_dist']:.3f}）：")
    print(f"  主胜 {d[0]*100:.1f}% ｜ 平 {d[1]*100:.1f}% ｜ 客胜 {d[2]*100:.1f}%")
    print("最接近的 5 场：")
    for row in r["nearest"].itertuples():
        print(f"  {row.date} [{row.country}/{row.league}] {row.home} {row.hg}-{row.ag} {row.away}（赔率 {row.oH}/{row.oD}/{row.oA}）")

if __name__ == "__main__":
    main()

"""Score the V5 envelope rows under both decision policies.

Reports, per attack: attribution rate at the shipped quorum (>= 2 valid votes)
and at the proposed quorum (>= 1), plus the false-attribution count each policy
would incur on the never-embedded negative fixtures. The looser policy is only
defensible if that second number stays zero.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    rows: list[dict] = []
    for path in sorted(out.glob("envelope-shard-*-rows.json")):
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    if not rows:
        print("no rows found")
        return 1

    positives = [r for r in rows if r["positive"]]
    negatives = [r for r in rows if not r["positive"]]
    print(f"rows: {len(rows)}  (positive {len(positives)}, negative {len(negatives)})")
    errors = [r for r in rows if r.get("error")]
    print(f"execution errors: {len(errors)}")
    for r in errors[:5]:
        print(f"  {r['fixture_id']} p{r['page_index']} {r['attack']}: {r['error']}")

    order: list[str] = []
    for r in rows:
        if r["attack"] not in order:
            order.append(r["attack"])

    agg = defaultdict(lambda: {"n": 0, "q2": 0, "q1": 0})
    for r in positives:
        a = agg[r["attack"]]
        a["n"] += 1
        # Correct attribution requires both a quorum AND the right identity.
        if r["attributed_quorum2"] and r["decoded_matches_expected"]:
            a["q2"] += 1
        if r["attributed_quorum1"] and r["decoded_matches_expected"]:
            a["q1"] += 1

    false_q2 = defaultdict(int)
    false_q1 = defaultdict(int)
    for r in negatives:
        if r["attributed_quorum2"]:
            false_q2[r["attack"]] += 1
        if r["attributed_quorum1"]:
            false_q1[r["attack"]] += 1

    print(f"\n{'attack':26} {'quorum>=2 (shipped)':>20} {'quorum>=1 (proposed)':>21}"
          f" {'false q2':>9} {'false q1':>9}")
    print("-" * 92)
    tot = {"n": 0, "q2": 0, "q1": 0}
    for attack in order:
        a = agg.get(attack)
        if not a or not a["n"]:
            continue
        tot["n"] += a["n"]
        tot["q2"] += a["q2"]
        tot["q1"] += a["q1"]
        print(f"{attack:26} {a['q2']:>8}/{a['n']:<3} {a['q2']/a['n']:>7.3f}"
              f" {a['q1']:>9}/{a['n']:<3} {a['q1']/a['n']:>7.3f}"
              f" {false_q2.get(attack, 0):>9} {false_q1.get(attack, 0):>9}")
    print("-" * 92)
    print(f"{'TOTAL':26} {tot['q2']:>8}/{tot['n']:<3} {tot['q2']/tot['n']:>7.3f}"
          f" {tot['q1']:>9}/{tot['n']:<3} {tot['q1']/tot['n']:>7.3f}"
          f" {sum(false_q2.values()):>9} {sum(false_q1.values()):>9}")

    print("\nDecode status on positive rows that neither policy attributes:")
    stuck = defaultdict(int)
    for r in positives:
        if not (r["attributed_quorum1"] and r["decoded_matches_expected"]):
            stuck[(r["attack"], r.get("decode_status"))] += 1
    for key in sorted(stuck, key=lambda k: (-stuck[k], str(k))):
        print(f"  {key[0]:26} {str(key[1]):32} {stuck[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

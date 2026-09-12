from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ATTACKS = ("identity", "jpeg-70", "resize-075", "crop-025")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    summaries = sorted(out.glob("variant-*-summary.json"))
    if not summaries:
        print("no summaries found")
        return 1

    print(f"{'variant':34} {'chips':>5} {'sat':>5} | "
          + " ".join(f"{a:>10}" for a in ATTACKS)
          + " | minPSNR  minSSIM")
    print("-" * 118)
    rows_by_variant: dict[str, list[dict]] = {}
    for path in summaries:
        s = json.loads(path.read_text(encoding="utf-8"))
        cells = []
        for a in ATTACKS:
            d = s["decode"][a]
            cells.append(f"{d['correct']:>4}/{d['total']:<5}")
        print(f"{s['variant']:34} {s['spread_chips_per_bit']:>5} "
              f"{s['saturated_fraction_min']:>5} | " + " ".join(cells)
              + f" | {s['minimum_psnr_db']:7.2f}  {s['minimum_ssim']:.4f}")
        rows_path = path.with_name(path.name.replace("-summary", "-rows"))
        if rows_path.exists():
            rows_by_variant[s["variant"]] = json.loads(rows_path.read_text(encoding="utf-8"))

    print("\nFailures per variant (fixture/page, attack):")
    for variant, rows in rows_by_variant.items():
        fails = defaultdict(list)
        for r in rows:
            if not r["correct"]:
                fails[f"{r['fixture_id']}/p{r['page_index']}"].append(
                    f"{r['attack']}(votes={r['valid_vote_count']})"
                )
        print(f"  {variant}:")
        if not fails:
            print("    none")
        for key in sorted(fails):
            print(f"    {key:28} {', '.join(fails[key])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

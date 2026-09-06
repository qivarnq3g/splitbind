"""Run the checkout's PDF fidelity checker without reinstalling research code."""

from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from splitbind_bench.pdf_fidelity import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

import os
import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(REPO_ROOT / "research" / "python" / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
os.environ.setdefault(
    "SPLITBIND_ALGORITHM_CONTRACTS",
    str(REPO_ROOT / "contracts" / "algorithm"),
)

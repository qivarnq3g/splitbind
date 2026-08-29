import os
import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

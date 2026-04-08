"""Scan WINEST_EXPORT_DIR (or apex/backend/seed/data/winest/) and bulk-load all XLSX files."""

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(_here)))
for _p in (_repo_root, os.path.dirname(_here)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apex.backend.seed.load_winest_project import run_directory

if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    run_directory(data_dir)

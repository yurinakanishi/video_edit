from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    if "--project-root" not in sys.argv:
        sys.argv.extend(["--project-root", str(project_root)])
    from scripts.build_tokyo_oasis_youtube_thumbnail import main as shared_main

    shared_main()


if __name__ == "__main__":
    main()

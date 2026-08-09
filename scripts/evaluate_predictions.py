"""Source-checkout wrapper for the installed ``selfguard-evaluate`` command."""

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from selfguard.evaluation_cli import main


if __name__ == "__main__":
    main()

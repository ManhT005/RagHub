"""Print opt-in profile defaults for a Compose env-file overlay."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.composition.hardware_profiles import PROFILES  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=sorted(PROFILES))
    args = parser.parse_args()
    print(f"RAG_HARDWARE_PROFILE={args.profile}")
    for key, value in PROFILES[args.profile].items():
        print(f"{key.upper()}={str(value).lower() if isinstance(value, bool) else value}")


if __name__ == "__main__":
    main()

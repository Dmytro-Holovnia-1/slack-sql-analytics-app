import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from init_db.seed_data_lib import write_csv


def main() -> None:
    csv_path = ROOT / "init_db" / "app_metrics.csv"
    print(f"Generating {csv_path}...")
    write_csv(csv_path)
    print("Done.")


if __name__ == "__main__":
    main()

import csv
from io import StringIO


def rows_to_csv(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""

    fieldnames = list(rows[0].keys())
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()

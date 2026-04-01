from app.services.csv_service import rows_to_csv


def test_rows_to_csv():
    rows = [{"app_name": "App1", "installs": 100}, {"app_name": "App2", "installs": 200}]

    csv_str = rows_to_csv(rows)

    assert "app_name,installs" in csv_str
    assert "App1,100" in csv_str
    assert "App2,200" in csv_str


def test_rows_to_csv_empty():
    assert rows_to_csv([]) == ""


def test_rows_to_csv_single_row():
    rows = [{"metric": "DAU", "value": 1000}]

    csv_str = rows_to_csv(rows)

    assert "metric,value" in csv_str
    assert "DAU,1000" in csv_str

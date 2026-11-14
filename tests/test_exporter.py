"""
Unit tests for News Exporter (JSON and CSV).
"""

import csv
import io
import json
import pytest

from exporters.news_exporter import export_to_csv, export_to_json


def test_export_to_json(in_memory_db, sample_records):
    # Export all
    json_str = export_to_json(in_memory_db, limit=50)
    data = json.loads(json_str)

    assert isinstance(data, list)
    assert len(data) == 3
    assert all("id" in item and "title" in item for item in data)

    # Filter by ticker
    rel_json = export_to_json(in_memory_db, ticker="RELIANCE")
    rel_data = json.loads(rel_json)
    assert len(rel_data) == 1
    assert rel_data[0]["ticker"] == "RELIANCE"

    # Filter by source
    bse_json = export_to_json(in_memory_db, source="bse")
    bse_data = json.loads(bse_json)
    assert len(bse_data) == 2


def test_export_to_csv(in_memory_db, sample_records):
    # Export all to CSV
    csv_str = export_to_csv(in_memory_db, limit=50)
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)

    # Check header
    header = rows[0]
    assert "ticker" in header
    assert "title" in header
    assert "source" in header
    assert "published_at" in header

    # Check rows (header + 3 records)
    assert len(rows) == 4

    # Filter by category
    csv_cat = export_to_csv(in_memory_db, category="financial_results")
    cat_rows = list(csv.reader(io.StringIO(csv_cat)))
    assert len(cat_rows) == 2  # header + 1 record
    assert "INFY" in cat_rows[1][1]

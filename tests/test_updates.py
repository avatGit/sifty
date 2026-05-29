"""Tests for the fragile winget upgrade-table parser."""

from __future__ import annotations

from sifty.commands.updates import parse_upgrade_table

SAMPLE = """\
Name                     Id                        Version      Available    Source
-----------------------------------------------------------------------------------
Mozilla Firefox          Mozilla.Firefox           120.0        121.0        winget
Visual Studio Code       Microsoft.VisualStudioCode 1.85.0      1.86.0       winget
7-Zip                    7zip.7zip                 22.01        23.01        winget
"""


def test_parses_all_rows():
    rows = parse_upgrade_table(SAMPLE)
    assert len(rows) == 3


def test_parses_fields():
    rows = parse_upgrade_table(SAMPLE)
    firefox = rows[0]
    assert firefox.name == "Mozilla Firefox"
    assert firefox.id == "Mozilla.Firefox"
    assert firefox.current == "120.0"
    assert firefox.available == "121.0"


def test_empty_output_returns_empty():
    assert parse_upgrade_table("No installed package found.") == []

"""Tests for the read-only health checkup engine (domain scans mocked)."""

from __future__ import annotations

from sifty.core import checkup


def test_run_checkup_reports_all_domains(monkeypatch):
    monkeypatch.setattr(checkup, "CHECKS", [
        ("junk", lambda: checkup.Finding("junk", "Junk files", "1.0 GB reclaimable", "attention", "junk", "Clean junk")),
        ("disk", lambda: checkup.Finding("disk", "Disk space", "all volumes have headroom", "ok", "", "")),
    ])
    findings = checkup.run_checkup()
    assert [f.domain for f in findings] == ["junk", "disk"]
    assert findings[0].severity == "attention"
    assert findings[1].severity == "ok"


def test_run_checkup_only_filter(monkeypatch):
    calls = []
    monkeypatch.setattr(checkup, "CHECKS", [
        ("junk", lambda: calls.append("junk") or checkup.Finding("junk", "Junk files", "x", "ok", "", "")),
        ("disk", lambda: calls.append("disk") or checkup.Finding("disk", "Disk space", "x", "ok", "", "")),
    ])
    findings = checkup.run_checkup(only={"disk"})
    assert [f.domain for f in findings] == ["disk"]
    assert calls == ["disk"]


def test_run_checkup_survives_failing_check(monkeypatch):
    def boom():
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(checkup, "CHECKS", [("junk", boom)])
    findings = checkup.run_checkup()
    assert len(findings) == 1
    assert "check failed" in findings[0].summary
    assert findings[0].severity == "ok"  # a failed probe is reported, not alarmed


def test_junk_check_severity_thresholds(monkeypatch):
    from sifty.core import junk

    class FakeScan:
        def __init__(self, size):
            self.size = size

    monkeypatch.setattr(junk, "scan", lambda: [FakeScan(2 << 30)])
    f = checkup._check_junk()
    assert f.severity == "attention" and f.action_key == "junk"

    monkeypatch.setattr(junk, "scan", lambda: [FakeScan(10)])
    f = checkup._check_junk()
    assert f.severity == "ok" and f.action_label == ""

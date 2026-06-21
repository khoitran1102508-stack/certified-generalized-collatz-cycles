import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.certificate_writer import write_certificate
from src.certificate_writer import write_row_certificate
from verifier.verify_certificate import CertificateError, verify_certificate_file
from verifier.verify_row_certificate import verify_row_certificate_file


def _write_lines(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_certificate_verifier_accepts_fresh_certificate(tmp_path):
    cert = tmp_path / "cert.jsonl"
    stats = write_certificate(cert, r_max=4, A_cap=8, c_max=31)
    assert stats.records > 0
    verified = verify_certificate_file(cert)
    assert verified
    assert verified.records_seen == stats.records
    assert verified.peak_rss_kib >= 0


def test_row_certificate_verifier_accepts_fresh_row_certificate(tmp_path):
    cert = tmp_path / "row.jsonl"
    stats = write_row_certificate(cert, r=5, A=10, c_max=31)
    verified = verify_row_certificate_file(
        cert, expected_r=5, expected_A=10, expected_c_max=31
    )
    assert verified.records_seen == stats.records
    assert verified.retained_cycles_checked == stats.retained_records


def test_certificate_verifier_imports_no_src_modules():
    text = __import__("pathlib").Path("verifier/verify_certificate.py").read_text(
        encoding="utf-8"
    )
    assert "from src" not in text
    assert "import src" not in text
    assert "read_text(" not in text
    assert "splitlines(" not in text


def test_certificate_verifier_cli_checks_expected_domain(tmp_path):
    cert = tmp_path / "cert.jsonl"
    write_certificate(cert, r_max=4, A_cap=8, c_max=31)
    base = [
        sys.executable,
        "verifier/verify_certificate.py",
        str(cert),
        "--expect-r-max",
        "4",
        "--expect-A-cap",
        "8",
        "--expect-c-max",
        "31",
    ]
    valid = subprocess.run(base, cwd=Path.cwd(), text=True, capture_output=True)
    assert valid.returncode == 0, valid.stderr + valid.stdout
    assert "VALID" in valid.stdout
    assert "peak_rss_kib=" in valid.stdout

    for flag, wrong in [
        ("--expect-r-max", "5"),
        ("--expect-A-cap", "9"),
        ("--expect-c-max", "63"),
    ]:
        cmd = base.copy()
        cmd[cmd.index(flag) + 1] = wrong
        rejected = subprocess.run(cmd, cwd=Path.cwd(), text=True, capture_output=True)
        assert rejected.returncode != 0
        assert "INVALID" in rejected.stdout


def test_certificate_verifier_runs_with_src_imports_blocked(tmp_path):
    cert = tmp_path / "cert.jsonl"
    write_certificate(cert, r_max=4, A_cap=8, c_max=31)
    script = """
import importlib.abc
import pathlib
import sys

class BlockSrc(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "src" or fullname.startswith("src."):
            raise ImportError("blocked src import")
        return None

sys.meta_path.insert(0, BlockSrc())
from verifier.verify_certificate import verify_certificate_file

stats = verify_certificate_file(
    pathlib.Path(sys.argv[1]),
    expected_r_max=4,
    expected_A_cap=8,
    expected_c_max=31,
)
print(stats.records_seen)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(cert)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert int(completed.stdout.strip()) > 0


def test_deleting_record_fails(tmp_path):
    cert = tmp_path / "cert.jsonl"
    write_certificate(cert, r_max=4, A_cap=8, c_max=31)
    lines = cert.read_text(encoding="utf-8").splitlines()
    tampered = tmp_path / "deleted.jsonl"
    _write_lines(tampered, [lines[0], *lines[2:]])
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)


def test_adding_record_fails(tmp_path):
    cert = tmp_path / "cert.jsonl"
    write_certificate(cert, r_max=4, A_cap=8, c_max=31)
    lines = cert.read_text(encoding="utf-8").splitlines()
    tampered = tmp_path / "added.jsonl"
    _write_lines(tampered, [*lines, lines[-1]])
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)


def test_reordering_records_fails(tmp_path):
    cert = tmp_path / "cert.jsonl"
    write_certificate(cert, r_max=4, A_cap=8, c_max=31)
    lines = cert.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 3
    reordered = [lines[0], lines[2], lines[1], *lines[3:]]
    tampered = tmp_path / "reordered.jsonl"
    _write_lines(tampered, reordered)
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)


def test_flipping_leaf_status_fails(tmp_path):
    cert = tmp_path / "cert.jsonl"
    write_certificate(cert, r_max=4, A_cap=8, c_max=31)
    lines = cert.read_text(encoding="utf-8").splitlines()
    tampered_lines = [lines[0]]
    flipped = False
    for line in lines[1:]:
        record = json.loads(line)
        if not flipped and record.get("kind") == "leaf":
            record["status"] = "TAMPERED_STATUS"
            flipped = True
            tampered_lines.append(json.dumps(record, sort_keys=True, separators=(",", ":")))
        else:
            tampered_lines.append(line)
    assert flipped
    tampered = tmp_path / "flipped.jsonl"
    _write_lines(tampered, tampered_lines)
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)


def test_wrong_declared_cycle_digest_fails(tmp_path):
    cert = tmp_path / "cert.jsonl"
    write_certificate(
        cert,
        r_max=4,
        A_cap=8,
        c_max=31,
        header_metadata={"normalized_cycle_set_sha256": "0" * 64},
    )
    with pytest.raises(CertificateError, match="digest mismatch"):
        verify_certificate_file(cert)

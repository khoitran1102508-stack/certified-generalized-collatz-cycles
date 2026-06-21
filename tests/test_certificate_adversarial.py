import json

import pytest

from src.certificate_writer import write_certificate
from verifier.verify_certificate import CertificateError, verify_certificate_file


def _write_lines(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mutate_json_line(line, mutator):
    payload = json.loads(line)
    mutator(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _first_record_index(lines, predicate):
    for index, line in enumerate(lines[1:], start=1):
        if predicate(json.loads(line)):
            return index
    raise AssertionError("record not found")


@pytest.fixture()
def representative_certificate(tmp_path):
    cert = tmp_path / "base.jsonl"
    write_certificate(cert, r_max=6, A_cap=14, c_max=31)
    return cert


def test_certificate_wrong_expected_domain_rejects(representative_certificate):
    for expected in [
        {"expected_r_max": 7, "expected_A_cap": 14, "expected_c_max": 31},
        {"expected_r_max": 6, "expected_A_cap": 15, "expected_c_max": 31},
        {"expected_r_max": 6, "expected_A_cap": 14, "expected_c_max": 63},
    ]:
        with pytest.raises(CertificateError):
            verify_certificate_file(representative_certificate, **expected)


def test_certificate_modified_header_rejects(tmp_path, representative_certificate):
    lines = representative_certificate.read_text(encoding="utf-8").splitlines()
    lines[0] = _mutate_json_line(
        lines[0], lambda payload: payload.__setitem__("arithmetic", "tampered")
    )
    tampered = tmp_path / "modified_header.jsonl"
    _write_lines(tampered, lines)
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)


def test_certificate_modified_prune_record_rejects(tmp_path, representative_certificate):
    lines = representative_certificate.read_text(encoding="utf-8").splitlines()
    index = _first_record_index(lines, lambda record: record.get("kind") == "prune")
    lines[index] = _mutate_json_line(
        lines[index], lambda payload: payload.__setitem__("reason", "TAMPERED")
    )
    tampered = tmp_path / "modified_prune.jsonl"
    _write_lines(tampered, lines)
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)


def test_certificate_modified_retained_cycle_record_rejects(
    tmp_path, representative_certificate
):
    lines = representative_certificate.read_text(encoding="utf-8").splitlines()
    index = _first_record_index(
        lines,
        lambda record: record.get("kind") == "leaf"
        and record.get("status") == "RETAINED",
    )
    lines[index] = _mutate_json_line(
        lines[index], lambda payload: payload.__setitem__("c", int(payload["c"]) + 2)
    )
    tampered = tmp_path / "modified_retained.jsonl"
    _write_lines(tampered, lines)
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)


def test_certificate_deleted_duplicated_reordered_extra_and_truncated_reject(
    tmp_path, representative_certificate
):
    lines = representative_certificate.read_text(encoding="utf-8").splitlines()
    variants = {
        "deleted": [lines[0], *lines[2:]],
        "duplicated": [*lines[:2], lines[1], *lines[2:]],
        "appended": [*lines, lines[-1]],
        "truncated": lines[:-1],
    }
    reordered = lines.copy()
    reordered[1], reordered[2] = reordered[2], reordered[1]
    variants["reordered"] = reordered

    for name, variant in variants.items():
        tampered = tmp_path / f"{name}.jsonl"
        _write_lines(tampered, variant)
        with pytest.raises(CertificateError):
            verify_certificate_file(tampered)

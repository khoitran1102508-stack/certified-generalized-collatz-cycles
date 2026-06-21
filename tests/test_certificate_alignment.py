import json

import pytest

from src.certificate_writer import write_certificate
from verifier.verify_certificate import (
    CertificateError,
    _validate_stored_cycle_pair,
    rotate,
    validate_retained_record,
    verify_certificate_file,
)


def _write_lines(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first_retained(lines):
    for index, line in enumerate(lines[1:], start=1):
        record = json.loads(line)
        if record.get("kind") == "leaf" and record.get("status") == "RETAINED":
            return index, record
    raise AssertionError("retained record not found")


def _line(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def test_c37_alignment_regression_accepts_correct_and_rejects_old_vector():
    corrected = {
        "A": 6,
        "c": 37,
        "canonical_offset": 2,
        "cycle_valuations": [2, 1, 3],
        "kind": "leaf",
        "orbit": [29, 31, 65],
        "r": 3,
        "search_valuations": [1, 3, 2],
        "status": "RETAINED",
    }
    validate_retained_record(corrected)

    old_misaligned = dict(corrected)
    old_misaligned["cycle_valuations"] = [1, 3, 2]
    with pytest.raises(CertificateError):
        validate_retained_record(old_misaligned)


def test_every_retained_record_in_representative_certificate_is_aligned(tmp_path):
    cert = tmp_path / "representative.jsonl"
    write_certificate(cert, r_max=6, A_cap=14, c_max=31)
    retained = 0
    for line in cert.read_text(encoding="utf-8").splitlines()[1:]:
        record = json.loads(line)
        if record.get("kind") == "leaf" and record.get("status") == "RETAINED":
            validate_retained_record(record)
            retained += 1
    assert retained > 0


def test_joint_rotations_preserve_pair_alignment_but_not_canonical_record():
    orbit = (29, 31, 65)
    cycle_valuations = (2, 1, 3)
    for offset in range(len(orbit)):
        _validate_stored_cycle_pair(
            c=37,
            orbit=rotate(orbit, offset),
            cycle_valuations=rotate(cycle_valuations, offset),
        )

    noncanonical_record = {
        "A": 6,
        "c": 37,
        "canonical_offset": 0,
        "cycle_valuations": [1, 3, 2],
        "kind": "leaf",
        "orbit": [31, 65, 29],
        "r": 3,
        "search_valuations": [1, 3, 2],
        "status": "RETAINED",
    }
    with pytest.raises(CertificateError):
        validate_retained_record(noncanonical_record)


def test_independent_rotation_or_permutation_of_one_field_rejects():
    orbit = (29, 31, 65)
    cycle_valuations = (2, 1, 3)
    with pytest.raises(CertificateError):
        _validate_stored_cycle_pair(
            c=37,
            orbit=rotate(orbit, 1),
            cycle_valuations=cycle_valuations,
        )
    with pytest.raises(CertificateError):
        _validate_stored_cycle_pair(
            c=37,
            orbit=orbit,
            cycle_valuations=rotate(cycle_valuations, 1),
        )
    with pytest.raises(CertificateError):
        _validate_stored_cycle_pair(
            c=37,
            orbit=orbit,
            cycle_valuations=(1, 2, 3),
        )


def test_changed_valuation_or_orbit_member_rejects(tmp_path):
    cert = tmp_path / "representative.jsonl"
    write_certificate(cert, r_max=6, A_cap=14, c_max=31)
    lines = cert.read_text(encoding="utf-8").splitlines()
    index, record = _first_retained(lines)

    bad_value = json.loads(lines[index])
    bad_value["cycle_valuations"][0] += 1
    lines_bad_value = lines.copy()
    lines_bad_value[index] = _line(bad_value)
    bad_value_path = tmp_path / "bad_value.jsonl"
    _write_lines(bad_value_path, lines_bad_value)
    with pytest.raises(CertificateError):
        verify_certificate_file(bad_value_path)

    bad_orbit = json.loads(lines[index])
    bad_orbit["orbit"][0] += 2
    lines_bad_orbit = lines.copy()
    lines_bad_orbit[index] = _line(bad_orbit)
    bad_orbit_path = tmp_path / "bad_orbit.jsonl"
    _write_lines(bad_orbit_path, lines_bad_orbit)
    with pytest.raises(CertificateError):
        verify_certificate_file(bad_orbit_path)


def test_malformed_lengths_reject():
    record = {
        "A": 6,
        "c": 37,
        "canonical_offset": 2,
        "cycle_valuations": [2, 1, 3],
        "kind": "leaf",
        "orbit": [29, 31, 65],
        "r": 3,
        "search_valuations": [1, 3, 2],
        "status": "RETAINED",
    }
    for field in ["orbit", "cycle_valuations", "search_valuations"]:
        malformed = json.loads(json.dumps(record))
        malformed[field] = malformed[field][:-1]
        with pytest.raises(CertificateError):
            validate_retained_record(malformed)


def test_duplicate_retained_record_rejects(tmp_path):
    cert = tmp_path / "representative.jsonl"
    write_certificate(cert, r_max=6, A_cap=14, c_max=31)
    lines = cert.read_text(encoding="utf-8").splitlines()
    index, _ = _first_retained(lines)
    duplicated = [*lines[: index + 1], lines[index], *lines[index + 1 :]]
    tampered = tmp_path / "duplicated_retained.jsonl"
    _write_lines(tampered, duplicated)
    with pytest.raises(CertificateError):
        verify_certificate_file(tampered)

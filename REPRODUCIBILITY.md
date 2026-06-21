# Reproducibility

Run commands from the artifact root.

## 1. Verify file integrity

```bash
sha256sum -c SHA256SUMS.txt
```

On macOS:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

## 2. Install test dependency

The generator and verifier use the Python standard library. The test suite additionally uses pytest.

```bash
python -m pip install -r requirements-test.txt
```

## 3. Verify the example certificate

```bash
python verifier/verify_certificate.py   certificates/example_certificate_r6_A14_c31.jsonl   --expect-r-max 6 --expect-A-cap 14 --expect-c-max 31
```

Expected result: `VALID`.

## 4. Verify the final certificate

```bash
python verifier/verify_certificate.py   certificates/final_certificate_c9997_r12_A30_v2.jsonl   --expect-r-max 12 --expect-A-cap 30 --expect-c-max 9997
```

Recorded verification processed 608,461 transcript records across 242 rows and checked 4,439 retained cycles.
Measured runtime and memory are reported in `results/verification_metrics.json`; local results depend on hardware and Python version.

## 5. Run tests

```bash
python -m pytest -q -m "not slow"
python -m pytest -q -m slow
```

## 6. Regenerate the complete certificate

```bash
python generate_final_certificate.py all
```

This command regenerates the certificate twice, checks byte-for-byte determinism, verifies the retained certificate,
rewrites the final cycle datasets, reruns the reference comparison, and records validation metrics.
Recorded peak memory was approximately 2.5 GiB for generation and verification.

## Digest terminology

- The certificate SHA-256 is the raw byte hash of the JSONL certificate.
- The cycle-data SHA-256 is the raw byte hash of `results/final_cycles.jsonl`.
- The normalized semantic cycle-set digest hashes the canonical cycle payload rather than the bytes of an ordinary text file.

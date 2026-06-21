# Certified Enumeration of Generalized Odd Collatz Cycles: Computational Artifact

Version `1.0.0`

This artifact supports the certified finite classification reported in
*Certified Enumeration of Generalized Odd Collatz Cycles in a Bounded Valuation--Parameter Domain*.
It contains the final certificate, a separate streaming verifier, the certificate generator,
canonical cycle datasets, the reference-comparison data, tests, and reproducibility metadata.

## Certified domain

- odd integers `c` with `1 <= c <= 9997` and `3` not dividing `c`;
- positive essential primitive cycles;
- odd-map length `r <= 12`;
- total valuation `A <= 30`;
- lower condition `2^A > 3^r`.

## Integrity identifiers

- final certificate SHA-256: `c8d89c766981211147fccf35c29dc4f30bab3977a5f3e16df9f4bbd32c3e0803`
- normalized semantic cycle-set digest: `1daa31c1107756ca895dae77d3420e2997e977fbd7a30714835d3917d5ecaa47`
- raw `results/final_cycles.jsonl` SHA-256: `b47638520bac584d4f29429b973b74766c2cb691ce3a02678125c627918b6f4f`

## Verify the complete certificate

```bash
python verifier/verify_certificate.py   certificates/final_certificate_c9997_r12_A30_v2.jsonl   --expect-r-max 12 --expect-A-cap 30 --expect-c-max 9997
```

## Verify a small example

```bash
python verifier/verify_certificate.py   certificates/example_certificate_r6_A14_c31.jsonl   --expect-r-max 6 --expect-A-cap 14 --expect-c-max 31
```

## Regenerate the full certificate

```bash
python generate_final_certificate.py all
```

Full regeneration is resource-intensive. See `REPRODUCIBILITY.md` and `ENVIRONMENT.md`.
The certificate header retains one immutable historical implementation identifier for provenance;
that identifier is not the public artifact version.

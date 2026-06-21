# Final Certified Theorem Evidence

## Scope

This file states only the finite theorem certified by the certified-domain
certificate.  It is not a manuscript, not a novelty claim, and not a claim
about the full Collatz conjecture.

## Map

For a positive odd integer `c`, define

```text
U_c(n) = (3n + c) / 2^{v_2(3n+c)}
```

on positive odd integers `n`, where `v_2(x)` is the exact exponent of the
largest power of two dividing the positive integer `x`.

## Admissible Parameters

The certified parameter set is exactly:

```text
1 <= c <= 9997,
c odd,
3 does not divide c.
```

No other values of `c` are covered.

## Cycles and Total Valuation

A positive odd cycle of odd length `r` is

```text
n_1 -> n_2 -> ... -> n_r -> n_1
```

under `U_c`, with every `n_i` positive and odd.

For such a cycle, define

```text
a_i = v_2(3 n_i + c),
A = a_1 + ... + a_r.
```

The certified domain requires

```text
1 <= r <= 12,
2^A > 3^r,
A <= 30.
```

Equivalently, for each fixed `r`, `A` ranges from the exact minimum satisfying
`2^A > 3^r` through `30`.

## Primitive and Essential Cycles

A cycle has primitive odd length `r` if it is not a repetition of a shorter
cycle.

A cycle is essential if

```text
gcd(c, n_1, ..., n_r) = 1.
```

Nonessential cycles inherited by odd scaling are outside the counted
normalized output.

## Equivalence Convention

Cycles are identified up to cyclic rotation.  The certified output uses the
canonical representative obtained by rotating the orbit and valuation
word together and selecting the lexicographically least `(orbit, valuations)`
pair.

## Certified Statement

The certified-domain certificate proves the following bounded statement:

```text
For every admissible odd c with 1 <= c <= 9997 and 3 not dividing c,
every positive essential primitive cycle of U_c with odd length r <= 12
and total valuation A <= 30 is, up to cyclic rotation, exactly one of
the 4,439 normalized cycles listed in the certified output.
```

The normalized cycle-set SHA-256 digest is

```text
1daa31c1107756ca895dae77d3420e2997e977fbd7a30714835d3917d5ecaa47
```

The complete corrected certificate-v1 transcript is
`certificates/final_certificate_c9997_r12_A30_v2.jsonl`.

The final normalized cycle datasets are:

- `results/final_cycles.csv`
- `results/final_cycles.jsonl`
- `results/final_row_summary.csv`
- `results/final_cycle_digest.txt`

## Soundness and Completeness Dependency

Soundness and completeness depend on:

- the exact cycle identity and divisor-threshold prefix sieve specified in
  `specification/divisor_threshold_sieve.md`;
- exhaustive traversal of all 242 `(r,A)` rows in the bounded domain;
- deterministic certificate generation by the divisor-threshold search method;
- independent streaming replay by `verifier/verify_certificate.py`;
- direct retained-cycle reconstruction and exact valuation checking;
- exact stored `orbit` and `cycle_valuations` alignment checking for every
  retained record;
- deterministic cycle-set extraction from the verified transcript.

The verifier imports nothing from `src` and recomputes the exact suffix
reachable-residue dynamic program while streaming the certificate records.

## Prior-Table Comparison

All 4,439 certified cycles match the archived Wegner-derived reference
snapshot under the documented `(c, min_orbit, A, r)` comparison key.

This is not a new-cycle discovery claim.  The certified statement is an
exhaustive valuation-bounded classification for the explicit finite domain
above.  Prior trajectory tables are not described as incorrect or incomplete.

## Limitations

This certified theorem does not:

- prove the Collatz conjecture;
- imply convergence of any starting value;
- say anything about divergent trajectories;
- rule out cycles with `r > 12`;
- rule out cycles with `A > 30`;
- cover parameters `c > 9997`;
- cover even `c`;
- cover parameters divisible by `3`;
- claim new generalized cycle identities;
- claim discovery of cycles absent from prior tables.

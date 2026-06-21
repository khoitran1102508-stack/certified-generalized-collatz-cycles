# Certificate v1: deterministic replay format

## Purpose

Certificate v1 is a deterministic search transcript.  It is designed to
establish separation between an untrusted searcher and a small independent
verifier.  It is not a compact, succinct, or tiny proof object.

The transcript does not carry reachable-residue witnesses.  The verifier
recomputes the exact suffix reachable-residue dynamic program while replaying
the declared search domain.

The verifier must not import any module from `src/`.
It may use only the Python standard library and its own exact-integer
implementation of the mathematical contract.

## Schema change from v0

Certificate v0 used one ambiguous retained-record field named `valuations`.
That field mixed two different meanings:

- the valuation composition used by the DFS search leaf; and
- the valuation sequence aligned with the stored canonical orbit.

Final certificate increments the proof-artifact schema to certificate v1.  The two
meanings are now separate:

- `search_valuations`: the positive composition traversed by the deterministic
  search procedure;
- `cycle_valuations`: the valuation sequence aligned position-by-position with
  the stored canonical `orbit`.

The verifier checks both the deterministic search replay and the exact
serialized orbit/valuation alignment.

If the header contains `normalized_cycle_set_sha256`, the verifier also
recomputes the normalized retained-cycle semantic payload and rejects the
certificate unless the digest matches the declared value.

## Header

One JSON object:

```json
{
  "format": "collatz-divisor-sieve-v1",
  "domain": {"r_max": 12, "A_cap": 30, "c_max": 9997},
  "ordering": "r,A,depth-first-parts-ascending",
  "arithmetic": "exact-integers",
  "certificate_schema_version": "certificate-v1",
  "normalized_cycle_set_sha256": "..."
}
```

## Records

JSON Lines after the header, in deterministic DFS order.

Pruned subtree:

```json
{
  "kind": "prune",
  "r": 5,
  "A": 11,
  "prefix": [1, 2],
  "reason": "NO_ELIGIBLE_DIVISOR_REACHABLE"
}
```

Completed leaf:

```json
{
  "kind": "leaf",
  "r": 3,
  "A": 6,
  "search_valuations": [1, 3, 2],
  "status": "RETAINED",
  "c": 37,
  "orbit": [29, 31, 65],
  "cycle_valuations": [2, 1, 3],
  "canonical_offset": 2
}
```

Allowed leaf statuses:

- `NONCANONICAL_ROTATION`
- `IMPRIMITIVE_VALUATION_VECTOR`
- `PARAMETER_ABOVE_CAP`
- `RETAINED`

A `RETAINED` record must include `c` and the canonical orbit.
It must also include:

- `search_valuations`;
- `cycle_valuations`;
- `canonical_offset`.

Other statuses include `search_valuations` but need not include `c`, `orbit`,
`cycle_valuations`, or `canonical_offset`.

## Retained-record alignment invariant

For every retained record and every index `i`, the verifier requires:

```text
cycle_valuations[i] = v_2(3 * orbit[i] + c)
U_c(orbit[i]) = orbit[(i+1) mod r].
```

The stored `orbit` and `cycle_valuations` are produced by applying one shared
cyclic rotation offset to the raw orbit and raw search valuation word.  The
same offset is stored as `canonical_offset`.

The verifier rejects:

- independently rotating only `orbit`;
- independently rotating only `cycle_valuations`;
- changing one valuation entry;
- changing one orbit element;
- malformed orbit or valuation lengths;
- a retained record whose `search_valuations` no longer reconstruct the stored
  canonical cycle.

## Verification algorithm

The verifier independently traverses the complete bounded search in the
specified deterministic order.

At each node:

1. recompute `(D,S,P,m,B)`;
2. recompute eligible divisors;
3. recompute exact reachable-residue sets;
4. if the pruning rule is valid, require the next certificate record to be the
   matching `prune` record and skip the subtree;
5. otherwise descend;
6. at a leaf, recompute the exact status and require the next record to match.
   For retained leaves, independently validate the exact serialized
   `orbit`/`cycle_valuations` pair before accepting the record.

The certificate is accepted only if:

- every expected node/leaf record matches;
- no record is missing;
- no extra record remains;
- all retained cycles pass direct stored-orbit and stored-valuation
  verification;
- the normalized semantic cycle-set digest matches when declared by the header;
- the declared domain is exactly the domain traversed.

For command-line use, an operator may also require an externally expected
domain:

```bash
python3 verifier/verify_certificate.py certificates/certificate_r6_A14_c31.jsonl \
  --expect-r-max 6 --expect-A-cap 14 --expect-c-max 31
```

If any supplied expected value differs from the certificate header, the
verifier must reject the certificate.

This v1 verifier intentionally redoes the suffix DP. Its role is independence
and correctness. Compact proof objects are deferred to future work.

# Prior-Table Comparison Snapshot

This directory contains a derived, citation-annotated normalized snapshot used
to reproduce `results/prior_table_comparison.csv` without any
private path such as `/private/tmp/reference_sources/wegner`.

## Source

- Franz Wegner, *The Collatz Problem generalized to 3x+k*,
  arXiv:2101.08060v1.
- Supplement: *List of limit cycles for the Collatz problem 3x+k*.

## Included Data

`wegner_positive_cycles_normalized.csv` contains only the fields needed for
the domain feasibility analysis/4A.1 comparison:

- `c`: the generalized parameter `k`;
- `min_orbit`: the listed smallest positive cycle element `x_lc`;
- `A`: the total number of divisions by two in Wegner's table row;
- `r`: the odd-step count / odd length;
- source and normalization metadata.

The file is a derived comparison aid, not a republication of Wegner's table.

## Extraction Method

domain feasibility analysis parsed Wegner supplement rows of the form

```text
k & x_0 & x_lc & A & r
```

from the accessible `clst*.tex` supplement source and retained positive rows.
domain validation then reduced the parsed data to the exact normalized keys needed
to compare against the certified primary-domain cycle set.

## Normalization Convention

The comparison key is:

```text
(c, min_orbit, A, r)
```

where `min_orbit` is the minimum element of the canonical positive essential
cycle recovered by the repository.  The comparison does not claim discovery of
new cycles.  For the proposed primary domain, all 4,439 normalized cycle
records currently match Wegner-derived records under this key.

Belaga-Mignotte and Gupta are recorded as not directly comparable in the
machine-readable comparison because no archived exact normalized table
for those sources is included here.

# Mathematical specification

## 1. Map and domain

For a positive odd parameter `c`, define the accelerated odd map on positive odd integers by

\[
U_c(n)=\frac{3n+c}{2^{\nu_2(3n+c)}}.
\]

This project initially studies positive cycles only. Negative parameters, zero, even parameters, and rational starting values are outside the first implementation.

## 2. Valuation encoding and cycle identity

For an ordered length-\(r\) cycle

\[
n_1\mapsto n_2\mapsto\cdots\mapsto n_r\mapsto n_1,
\]

set

\[
a_i=\nu_2(3n_i+c),\qquad A=\sum_{i=1}^r a_i.
\]

Repeated substitution gives

\[
(2^A-3^r)n_1=cC(a_1,\ldots,a_r),
\]

where

\[
C(a_1,\ldots,a_r)
=\sum_{j=0}^{r-1}3^{r-1-j}2^{a_1+\cdots+a_j},
\]

and the exponent for \(j=0\) is the empty sum, equal to zero.

Thus a valuation vector determines at most one candidate start:

\[
n_1=\frac{cC(a)}{2^A-3^r}.
\]

A vector is admissible only if the denominator is positive, the quotient is a positive odd integer, and direct orbit reconstruction reproduces every exact valuation and closes after \(r\) steps.

## 3. Finite search bounds

Every positive cycle satisfies

\[
2^A=\prod_{i=1}^r\left(3+\frac{c}{n_i}\right).
\]

Consequently,

\[
2^A>3^r,
\qquad
A\ge \operatorname{bit\_length}(3^r),
\]

and, since \(n_i\ge1\),

\[
2^A\le(3+c)^r,
\qquad
A\le\left\lfloor\log_2((3+c)^r)\right\rfloor.
\]

The general upper bound grows quickly with `c`. Every computational result must therefore state whether it used the full upper bound or an explicit additional cap `A <= A_cap`. Pilot results are bounded classifications, not unrestricted cycle classifications.

## 4. Equivalences and normalization

Cyclic rotations represent the same ordered cycle up to starting point. Orbit and valuation vectors must always be rotated by the same offset.

For every positive odd `d`,

\[
U_{dc}(dn)=dU_c(n).
\]

Hence a cycle for parameter `c` scales to a cycle for parameter `dc`. A parameter-cycle pair is called **essential** when

\[
\gcd(c,n_1,\ldots,n_r)=1.
\]

If the gcd is larger than one, dividing both the parameter and all orbit entries by the gcd yields the underlying inherited cycle.

If `3 | c`, every image under `U_c` is divisible by 3. Therefore every positive cycle has a common factor 3 with `c`, so no essential cycle occurs. The primary normalized parameter domain is consequently

\[
c>0,\quad c\equiv1\pmod2,\quad 3\nmid c.
\]

## 5. Primitive objects

A cycle is primitive when its least orbit period is exactly `r`. A valuation vector is primitive when its least sequence period is `r`. The baseline can retain imprimitive valuation vectors for regression testing, but the research classification targets essential primitive cycles.

## 6. Completeness claim for a bounded domain

A bounded search domain is a tuple

\[
D=(C,R,A_{\max}),
\]

with an explicit finite parameter set `C`, lengths `1 <= r <= R`, and a stated valuation-sum cap. A classification is complete over `D` only if every positive composition in the domain is either:

1. represented by the selected canonical cyclic representative and checked; or
2. rejected by a mathematically proved rule whose hypotheses are independently verifiable.

The current baseline uses exhaustive composition enumeration and direct candidate verification. It does not yet provide compact search certificates.

# Dependency and Environment Specification

The verifier and generator use Python standard-library exact integer
arithmetic only.  No external Python packages are required for certificate
verification or regeneration.

Recorded final-certificate run metadata:

- Python: 3.14.4
- Platform string: macOS-26.5.1-arm64-arm-64bit-Mach-O
- Peak RSS source: `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`
- macOS RSS unit handling: byte values converted to KiB
- Final generation wall seconds: 27.841342
- Final verification wall seconds: 27.326546

Hardware model, CPU core count, and installed RAM were not recorded in the
recorded run metadata.

Recommended clean environment:

- Python 3.11 or later;
- a POSIX-like shell for the commands in `REPRODUCIBILITY.md`;
- enough memory to replay the full certificate.  Recorded final verification
  used 2,599,936 KiB peak RSS.

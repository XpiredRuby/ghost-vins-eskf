# GHOST-X G6 Consistency Report

Canonical trials: `24`

| Estimator | Metric | Samples | Mean | 95% mean interval | Inside? |
|---|---|---:|---:|---|---|
| `cv` | `nis` | 3417 | 1.586 | [1.933, 2.068] | False |
| `cv` | `position_nees` | 3864 | 1.603 | [1.937, 2.064] | False |
| `formal_imm` | `nis` | 3417 | 1.995 | [1.933, 2.068] | True |
| `formal_imm` | `position_nees` | 3864 | 1.622 | [1.937, 2.064] | False |
| `ghost_mh` | `position_nees` | 3864 | 1.641 | [1.937, 2.064] | False |

## Validity boundaries

- CV NIS has textbook meaning only under the declared linear, white, Gaussian assumptions.
- IMM NIS is a moment-matched mixture diagnostic, not an exact mixture-distribution test.
- GHOST-MH has no single formal NIS during multi-modal intervals.
- Position NEES here is valid only against deterministic synthetic truth; physical NEES remains pending.

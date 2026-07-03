# HF v1 Baseline

## Official Status

`mean_reversion_hf_micro_v1`

STATUS: `FROZEN BASELINE`

Meaning:

- runtime stable;
- diagnostics complete for the first HF research phase;
- no more optimization of this profile;
- future research must compare against HF v1;
- new ideas must not change HF v1 behavior.

## Summary

`mean_reversion_hf_micro_v1` is the first completed high-frequency paper-trading baseline for the USDCUSDT research workspace.

It is not a final real-trading strategy. It is a stable reference point for future diagnostics, simulations, and paper-only experiments.

The profile remains paper/demo only. Real trading is not enabled.

## Development History

HF v1 was developed after the earlier mean-reversion paper profiles proved too slow for the original project goal.

The initial slow profile, `mean_reversion_v2_small_target`, was viable but held positions for hours. That contradicted the target direction of the project:

- many short micro-cycles;
- small profit per cycle;
- high cycle frequency;
- low average holding time.

The project then moved into High Frequency Micro-Cycle research:

- live HF snapshot collection;
- micro-cycle dry-run simulation;
- flexible target and holding-time sweeps;
- paper-only HF profile creation;
- clean paper validation runs;
- loss diagnostics and reporting improvements.

The result of that phase is `mean_reversion_hf_micro_v1`.

## What Was Verified

The following areas were researched and validated around HF v1:

- target optimization;
- timeout and max holding behavior;
- epsilon/tick-safe close behavior;
- flat market handling;
- `short_center` entry logic;
- live `short_center` provider;
- paper safety policy for HF behavior;
- clean collection runs with `--target-new`;
- profit concentration diagnostics;
- outlier-resistant validation;
- losing cycle diagnostics;
- profit scope and extreme move audits;
- run regime comparison;
- velocity filter simulation;
- regime-aware velocity filter simulation;
- grid and guarded grid simulations;
- grid drawdown and risk diagnostics.

## Diagnostics That Remain Useful

The following commands remain useful for monitoring or comparing future ideas against HF v1:

```bash
python manage.py validation-summary --profile mean_reversion_hf_micro_v1
python manage.py profile-performance-summary --profile mean_reversion_hf_micro_v1
python manage.py paper-profit-concentration --profile mean_reversion_hf_micro_v1
python manage.py paper-outlier-validation --profile mean_reversion_hf_micro_v1
python manage.py hf-profit-audit --profile mean_reversion_hf_micro_v1
python manage.py hf-extreme-move-diagnostics --profile mean_reversion_hf_micro_v1
python manage.py hf-losing-cycle-diagnostics --profile mean_reversion_hf_micro_v1
python manage.py hf-run-regime-comparison --profile mean_reversion_hf_micro_v1
python manage.py hf-velocity-filter-sim --profile mean_reversion_hf_micro_v1
python manage.py hf-regime-filter-sim --profile mean_reversion_hf_micro_v1
```

These commands are diagnostics-only unless explicitly documented otherwise.

## Rejected Research

### Grid v1

Grid v1 improved closed/net PnL in simulation but introduced unacceptable floating equity drawdown.

The important result was:

- higher closed PnL than HF v1;
- much worse total equity drawdown;
- added layered exposure;
- did not pass the risk threshold.

Decision: do not promote Grid v1 to paper/runtime.

### Guarded Grid

Directional exposure guard reduced floating drawdown but also reduced frequency and net performance.

The best guarded variants still did not meet the current drawdown threshold for promotion.

Decision: keep guarded grid as research-only.

### Velocity Filter

A universal velocity filter helped one weak run but hurt or failed to improve larger samples.

It was useful for diagnostics because it explained some no-follow-through losses, but it was not stable enough as a global rule.

Decision: do not add a universal velocity filter to HF v1.

### Regime-aware Velocity Filter

Regime-aware filtering showed that velocity filtering can be promising in a narrow regime, such as `HIGH_VELOCITY`, but not consistently across the full sample.

This supports further research into regime detection, but not runtime changes to HF v1.

Decision: keep as diagnostics-only.

## Why HF v1 Is Frozen

HF v1 is frozen because it has become a stable comparison baseline:

- it has enough diagnostics around entry, exit, safety, profit concentration, outliers, and regimes;
- its runtime behavior is known and paper-tested;
- rejected alternatives are documented;
- further tuning risks overfitting the baseline rather than creating a genuinely better strategy.

From this point forward, HF v1 should be treated as the control group.

## Rules for Future Research

Do not change:

- `mean_reversion_hf_micro_v1` entry logic;
- `mean_reversion_hf_micro_v1` target logic;
- `mean_reversion_hf_micro_v1` timeout logic;
- paper collection behavior for HF v1;
- HF v1 safety policy.

Future ideas must:

- be diagnostics-only first;
- use separate commands, documents, or profiles;
- explicitly compare against HF v1;
- avoid mixing HF v1 ordinary micro-cycle performance with extreme-move performance.

## Final Decision

`mean_reversion_hf_micro_v1` is the official frozen baseline for the next research phase.

No new optimization should be applied to HF v1 directly.

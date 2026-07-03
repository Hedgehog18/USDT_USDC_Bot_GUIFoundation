# Extreme Strategy v1 Research

## Status

STATUS: `RESEARCH PLANNED`

This document opens a new research direction.

No runtime code is implemented in this step.

## Why This Exists

During HF v1 analysis, extreme close cycles were repeatedly identified as a separate phenomenon.

Observed facts:

- extreme close cycles: approximately `49`;
- extreme profit share: approximately `90%`;
- lifetime HF profit is formed mostly by Extreme Move cycles;
- ordinary HF micro-cycle performance and extreme-move performance should not be analyzed as one combined strategy.

This means the project has two different behaviors mixed in historical reports:

- ordinary HF micro-cycle behavior;
- rare extreme-move behavior.

They need separate diagnostics and separate research paths.

## What Extreme Strategy v1 Is

Extreme Strategy v1 is a separate research direction.

It is not:

- HF v2;
- an HF v1 improvement;
- a velocity filter;
- a grid variant;
- a patch to `mean_reversion_hf_micro_v1`.

It is a different strategy idea focused on detecting and handling extreme market movement conditions.

## Why HF and Extreme Must Be Separated

HF v1 is designed for frequent small cycles.

Extreme cycles are different:

- they are rare;
- they can dominate total profit;
- they distort win rate and average PnL;
- they can make ordinary HF performance look better than it is;
- they may require different entry, exit, and risk logic.

Because of this, HF v1 ordinary performance should be evaluated with extreme-aware metrics:

- net without extreme;
- extreme profit share;
- outlier-resistant validation;
- recent/current run metrics.

Extreme Strategy v1 should evaluate extreme cycles directly, not hide them inside HF baseline reports.

## Starting Hypotheses

Extreme Strategy v1 begins with these research questions:

- Can an `Extreme Market` state be detected before or during the move?
- Are extreme cycles caused by real Binance movement, data-source behavior, or fallback/execution artifacts?
- Which preconditions appear before extreme close prices?
- Can an activation condition be defined without increasing ordinary HF risk?
- Should extreme entries use different target, holding, or safety rules?
- Can the strategy be compared fairly against the frozen HF v1 baseline?

## Initial Research Goals

The first phase should define diagnostics only:

- define `Extreme Market`;
- identify activation conditions;
- separate ordinary HF cycles from extreme cycles;
- build separate extreme diagnostics;
- compare extreme-only results against HF v1 baseline;
- decide whether a separate paper profile is justified later.

Future work may include:

- `extreme-market-diagnostics`;
- `extreme-entry-sim`;
- `extreme-strategy-v1-sim`;
- a separate paper-only profile, only after diagnostics support it.

## Explicit Non-Goals

Do not implement in this step:

- no runtime strategy profile;
- no paper profile;
- no order logic;
- no real trading;
- no changes to `mean_reversion_hf_micro_v1`;
- no changes to `collect-closed-cycles`;
- no changes to HF v1 safety behavior.

## Comparison Rule

Any future Extreme Strategy v1 result must be compared against:

```text
mean_reversion_hf_micro_v1
```

The comparison must be extreme-aware:

- HF v1 ordinary net without extreme;
- HF v1 total net including extreme;
- Extreme Strategy v1 extreme-only net;
- drawdown and concentration risk;
- cycles/day and holding time;
- outlier dependency.

## Relationship to Existing Diagnostics

Existing commands that motivated this direction:

```bash
python manage.py hf-profit-audit --profile mean_reversion_hf_micro_v1
python manage.py hf-extreme-move-diagnostics --profile mean_reversion_hf_micro_v1
python manage.py paper-profit-concentration --profile mean_reversion_hf_micro_v1
python manage.py paper-outlier-validation --profile mean_reversion_hf_micro_v1
```

These remain diagnostics for HF v1. Extreme Strategy v1 should eventually get its own diagnostics namespace.

## Current Decision

Open Extreme Strategy v1 research as a separate planned phase.

Do not change HF v1.

Do not implement strategy code yet.

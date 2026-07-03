# Extreme Strategy v1 Roadmap

## Purpose

This document designs Phase 2 of the project.

Phase 2 is the research phase for `Extreme Strategy v1`.

No trading logic is implemented here. No runtime profile, paper profile, CLI command, or order logic is created by this roadmap.

## Strategic Context

Phase 1 is complete.

`mean_reversion_hf_micro_v1` is now the frozen HF baseline:

```text
Strategy A: HF v1
Status: FROZEN BASELINE
Role: reference strategy for future comparison
```

Extreme Strategy v1 is a new and separate research direction:

```text
Strategy B: Extreme v1
Status: RESEARCH
Role: investigate rare extreme market moves as a separate strategy class
```

Extreme Strategy v1 is not:

- HF v2;
- an HF v1 optimization;
- a patch to `mean_reversion_hf_micro_v1`;
- a grid variant;
- a velocity filter.

It is a separate strategy concept with separate diagnostics, separate assumptions, and separate future readiness gates.

## Architecture Principle

HF and Extreme must live separately.

The platform should evolve toward multiple independent strategies that can be researched, validated, and compared without changing each other.

Core principles:

- each strategy has its own research documents;
- each strategy has its own diagnostics namespace;
- each strategy has its own readiness criteria;
- paper/runtime profiles are created only after diagnostics justify them;
- all new strategies compare against the frozen HF v1 baseline;
- ordinary HF micro-cycle performance must not be mixed with extreme-move performance.

Future architecture should support:

- Strategy A: HF v1 baseline;
- Strategy B: Extreme v1 research;
- future Strategy C, D, and others if needed;
- shared infrastructure for storage, reporting, safety, and read-only market data;
- separate strategy-specific accounting and validation.

## Phase 2.1: Extreme Market Discovery

### Goal

Define what an `Extreme Move` is.

This phase should discover whether extreme cycles are real market opportunities, data artifacts, fallback effects, or a mixture of these.

### Inputs

Potential data sources:

- existing paper cycles;
- HF paper cycle entry diagnostics;
- `market_snapshots_hf`;
- Binance read-only market data;
- extreme close price audits;
- profit concentration reports;
- outlier validation reports.

### Future Diagnostics To Design

Possible diagnostics:

- price velocity;
- price acceleration;
- price impulse;
- spread behavior before, during, and after the move;
- duration of the extreme move;
- frequency of extreme moves;
- recovery time after the move;
- volume and trade activity if reliable data becomes available;
- time of day;
- market sessions;
- clustering of extreme moves;
- repeatability;
- pre-move flatness or compression;
- post-move reversion behavior;
- data-source quality and fallback involvement;
- distance from short/work/long centers;
- order book pressure if available.

### Key Questions

- How often do extreme moves occur?
- Are they clustered in specific sessions?
- Do they follow flat-market compression?
- Do they have measurable acceleration before the move?
- Does spread widen before or during the move?
- Are known extreme close prices caused by real Binance market data?
- Can extreme conditions be detected before entry, not only after close?

### Expected Output

This phase should produce definitions and diagnostics only.

Possible future output:

- an `Extreme Market` classification proposal;
- an extreme event dataset;
- a summary of candidate activation signals;
- a decision on whether replay is justified.

### Do Not Implement Yet

- no strategy entry rules;
- no paper profile;
- no runtime profile;
- no orders;
- no changes to HF v1.

## Phase 2.2: Extreme Replay

### Goal

Replay historical HF snapshots and paper-cycle contexts to test hypothetical extreme strategy behavior.

Replay should answer:

```text
If an extreme strategy had existed, what would it have done?
```

### Replay Model

Future replay should define:

- activation condition;
- hypothetical entry price;
- hypothetical entry direction;
- hypothetical target;
- hypothetical stop or invalidation;
- hypothetical timeout or max holding;
- exit condition;
- fees;
- slippage assumptions;
- data-source assumptions.

### Replay Statistics

Replay reports should include:

- activated events;
- skipped events;
- hypothetical entries;
- target hits;
- timeout exits;
- stop or invalidation exits;
- net profit;
- net without outliers;
- max drawdown;
- worst adverse movement;
- best favorable movement;
- holding time;
- cycles/day or events/day;
- concentration risk;
- comparison against HF v1 baseline.

### Replay Diagnostics

Replay must explain:

- why activation occurred;
- why activation did not occur;
- whether entry was before, during, or after the extreme move;
- whether the event was tradable or only visible after the fact;
- whether the move was recoverable after entry;
- whether a small number of events dominate all profit.

### Readiness Gate

Replay can move toward paper research only if:

- activation rules are explicit;
- replay uses historical data without lookahead bias;
- performance is not dependent on one or two outliers;
- drawdown is acceptable;
- results are compared against HF v1;
- data-source quality is understood.

### Do Not Implement Yet

This roadmap does not implement replay. It only describes what replay must eventually do.

## Phase 2.3: Extreme Paper

### Goal

Create a separate paper-only Extreme Strategy profile after replay is strong enough.

This is not part of the current implementation.

### Preconditions

Extreme Paper should not begin until:

- Extreme Market Discovery is complete;
- Replay is implemented and reviewed;
- replay passes documented risk thresholds;
- activation rules are stable;
- exit rules are stable;
- data-source behavior is verified;
- concentration risk is acceptable;
- paper safety policy is designed for extreme behavior;
- comparison against HF v1 baseline is positive and honest.

### Paper Profile Design Principles

If paper research is eventually approved, it should:

- use a new profile name, not `mean_reversion_hf_micro_v1`;
- keep HF v1 frozen;
- use separate reporting;
- use separate validation summary mode;
- distinguish ordinary HF cycles from extreme cycles;
- never place real orders;
- support safe stop and recovery behavior.

### Paper Success Criteria

Potential criteria:

- enough closed paper cycles or enough extreme events;
- positive net after removing abnormal data artifacts;
- acceptable drawdown;
- low outlier dependency;
- clear activation explanations;
- clear failure categories;
- no hidden dependency on stale/fallback data.

## Phase 2.4: Extreme Runtime

### Goal

Runtime is a future concept only.

Extreme Runtime should not be considered until Extreme Paper has passed a long validation phase.

### Runtime Preconditions

Before runtime exists, the project would need:

- completed discovery;
- completed replay;
- successful paper profile;
- documented risk controls;
- operator recovery process;
- hardware and network reliability plan;
- explicit real-trading design review;
- API-key and exchange-safety implementation;
- separate audit and monitoring.

### Runtime Non-Goals For Now

No runtime work belongs in Phase 2 planning.

Do not implement:

- real trading;
- exchange orders;
- runtime execution;
- live capital management;
- automated production deployment.

## Strategy Separation Rules

HF v1 and Extreme v1 must remain separate:

- HF v1 is the control group;
- Extreme v1 is a research candidate;
- Extreme results must not be merged into HF v1 performance;
- HF v1 must not be tuned to fit Extreme behavior;
- Extreme v1 must have separate diagnostics before any paper profile exists.

## Comparison Framework

Every future Extreme Strategy result should compare against HF v1 using:

- net profit;
- net profit without extreme;
- win rate;
- drawdown;
- concentration risk;
- outlier dependency;
- cycles or events per day;
- holding time;
- data-source quality;
- recovery and safety behavior.

The comparison should answer:

```text
Does Extreme Strategy v1 add a separate, robust edge beyond HF v1?
```

## Phase 2 Deliverables

Planned deliverables, in order:

1. Extreme Market Discovery specification.
2. Extreme event dataset definition.
3. Extreme diagnostics command design.
4. Extreme Replay design.
5. Replay implementation proposal.
6. Paper readiness criteria.
7. Paper profile proposal, only if replay passes.
8. Runtime readiness criteria, only after paper validation.

## Current Decision

Phase 2 begins as documentation and architecture.

No code should be written yet for Extreme Strategy v1.

HF v1 remains frozen.

Future work must start with diagnostics and replay design, not runtime behavior.

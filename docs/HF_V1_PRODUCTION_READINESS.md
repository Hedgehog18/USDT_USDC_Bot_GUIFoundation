# HF v1 Production Readiness

`mean_reversion_hf_micro_v1` is the frozen HF baseline. This document defines the checklist for a possible future small real-capital pilot.

Real trading is not enabled by this checklist. The readiness command is diagnostics-only:

```bash
python manage.py hf-production-readiness --profile mean_reversion_hf_micro_v1
```

The command must report `READY_FOR_DRY_RUN` before any pilot planning continues. If it reports `NOT_READY`, fix the blocking diagnostics first.

The next exchange-facing dry-run command is also diagnostics-only:

```bash
python manage.py hf-real-dry-run --profile mean_reversion_hf_micro_v1
```

It must report `READY_FOR_SMALL_REAL_PILOT` before a small real-capital pilot can even be considered.

## 1. Diagnostics

Before any dry-run or pilot:

- confirm the profile exists and is the official `FROZEN BASELINE`;
- confirm there are no open paper cycles;
- confirm recovery state is clean;
- review the latest paper performance summary;
- confirm HF paper safety policy is available;
- confirm Binance read-only market data is available;
- confirm configured paper/config balances are readable;
- confirm symbol tick size, quantity step, min notional, and live market depth are readable;
- confirm `config.mode` is not `REAL`;
- confirm emergency stop / recovery commands are available;
- confirm `logs` and `reports` directories are writable.

Useful supporting commands:

```bash
python manage.py validation-summary --profile mean_reversion_hf_micro_v1
python manage.py profile-performance-summary --profile mean_reversion_hf_micro_v1
python manage.py paper-profit-concentration --profile mean_reversion_hf_micro_v1
python manage.py paper-outlier-validation --profile mean_reversion_hf_micro_v1
python manage.py hf-losing-cycle-diagnostics --profile mean_reversion_hf_micro_v1
```

## 2. Dry-Run

Dry-run means operational rehearsal without live orders:

- keep `config.mode=DEMO`;
- run paper collection with `--target-new`;
- keep `--require-binance` enabled;
- verify no recovery cycles exist before start;
- monitor safety blocks, timeout behavior, and open-cycle age;
- compare new-run metrics against the frozen HF v1 baseline;
- archive the run baseline id and final summary.

Suggested paper rehearsal:

```bash
python manage.py collect-closed-cycles --profile mean_reversion_hf_micro_v1 --target-new 50 --interval 5 --require-binance --no-beep --print-every 10
```

### Real Exchange Dry-Run Stage

After paper rehearsal and `hf-production-readiness`, run:

```bash
python manage.py hf-real-dry-run --profile mean_reversion_hf_micro_v1
```

This command checks the real exchange environment without creating orders.

It verifies:

- Binance public API availability;
- authenticated account balance readability;
- USDT and USDC balances;
- `USDCUSDT` symbol existence;
- symbol status is `TRADING`;
- base and quote precision;
- `minQty`;
- `stepSize`;
- `minNotional`;
- `tickSize`;
- current price;
- bid, ask, and spread;
- proposed stake against `minNotional`;
- proposed quantity against `stepSize`;
- target price against `tickSize`;
- `config.mode` is still not `REAL`;
- no order endpoint is called.

Authenticated balance checks require read-only Binance credentials in the environment:

```bash
BINANCE_API_KEY
BINANCE_API_SECRET
```

Without these variables, the command must remain `NOT_READY` because USDT/USDC balances cannot be verified.

It does not:

- create Binance orders;
- create paper cycles;
- enable real trading;
- change HF v1;
- change config;
- mutate balances;
- run entry or close logic.

If the command prints warnings, treat them as operator review items. If it prints `NOT_READY`, do not proceed.

## 3. Small Real Pilot

Small real pilot is a future phase, not part of the current code state.

Minimum criteria before a small real pilot:

- `hf-production-readiness` reports `READY_FOR_DRY_RUN`;
- `hf-real-dry-run` reports `READY_FOR_SMALL_REAL_PILOT`;
- USDT and USDC balances are both sufficient for the proposed stake;
- proposed stake is safely above `minNotional`;
- proposed quantity survives `stepSize` rounding;
- target prices survive `tickSize` rounding;
- spread is within the configured threshold;
- `config.mode` is still `DEMO` until a separate reviewed real-trading implementation exists;
- operator has a tested stop and rollback procedure.

Before any pilot exists, the project still needs:

- explicit real-order implementation review;
- API-key storage and secret handling review;
- hard position limits;
- hard daily loss limit;
- operator confirmation flow;
- separate audit logging for every real order attempt;
- manual emergency stop procedure tested in demo first.

No real pilot should start only because paper diagnostics look good.

## 4. Stop Conditions

Stop the run and do not continue if any of these occur:

- readiness audit returns `NOT_READY`;
- recovery mode is required;
- any open cycle is unresolved before start;
- paper safety policy blocks the profile;
- Binance read-only checks fail repeatedly;
- logs or reports cannot be written;
- outlier or concentration diagnostics show unstable profit dependence;
- new-run net or win rate materially diverges from the HF v1 baseline;
- operator cannot monitor the run continuously.

For a future real pilot, additional stop conditions must include:

- any unexpected real order status;
- any mismatch between local position state and exchange account state;
- daily loss limit reached;
- emergency stop unavailable;
- network instability during an open position.

## 5. Rollback Plan

If readiness fails or a dry-run degrades:

1. Keep `config.mode=DEMO`.
2. Stop collection with safe-stop where appropriate.
3. Resolve or abandon recovery cycles explicitly.
4. Export paper reports and diagnostics.
5. Compare the failed run against the frozen HF v1 baseline.
6. Do not change HF v1 runtime behavior directly.
7. Move any new idea back into diagnostics-only research.

HF v1 remains the control group. Future strategy ideas must be separate diagnostics or separate profiles and must compare against this baseline before promotion.

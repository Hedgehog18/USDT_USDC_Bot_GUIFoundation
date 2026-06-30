# HF Grid Research

Цей документ фіксує результат diagnostics-only дослідження HF Micro Grid.

## Статус

`mean_reversion_hf_micro_v1` залишається основним baseline-кандидатом.

HF Grid залишається `research-only` і не переноситься у paper/runtime profile.

## Що перевіряли

Було перевірено ідею layered/grid підходу для high-frequency micro-cycles:

- базовий HF profile: `mean_reversion_hf_micro_v1`;
- diagnostics-only simulator: `hf-micro-grid-sim`;
- directional exposure guard;
- parameterized guard sweep: `hf-micro-grid-guard-sweep`.

Grid-ідея: дозволити кілька одночасних layers, але не створювати paper cycles, orders або runtime profile.

## Команди

Baseline / grid simulation:

```bash
python manage.py hf-micro-grid-sim --max-layers 10 --layer-size 10 --max-holding-seconds 180
```

Grid з directional exposure guard:

```bash
python manage.py hf-micro-grid-sim --max-layers 10 --layer-size 10 --max-holding-seconds 180 --directional-exposure-guard
```

Parameterized guard sweep:

```bash
python manage.py hf-micro-grid-guard-sweep
```

CSV export:

```bash
python manage.py hf-micro-grid-guard-sweep --export-csv reports/hf_micro_grid_guard_sweep.csv
```

## Основні результати

### HF v1 baseline

- net: `+0.15323674`
- drawdown: `-0.00089896`
- cycles/day: `418.58`

### Grid v1 без guard

- net: `+0.23449701`
- drawdown: `-0.03491126`
- cycles/day: `416.83`
- recommendation: `NOT WORTH TESTING`

Closed/net PnL виглядає краще за HF v1, але floating equity drawdown занадто великий.

### Guarded Grid

- net: `+0.16542611`
- drawdown: `-0.01223561`
- cycles/day: `163.22`
- recommendation: `PAPER CANDIDATE`

Directional guard суттєво зменшив floating drawdown, але одночасно сильно зменшив frequency і net.

### Guard sweep

Balanced candidates при drawdown threshold `-0.01`: `0`.

Найнижчий drawdown у sweep:

- `guard_min_layers=1`
- `guard_loss_threshold=0`
- net: `+0.16542611`
- cycles/day: `163.22`
- drawdown: `-0.01223561`
- recommendation: `PAPER CANDIDATE`

## Висновок

HF Grid у поточному вигляді не проходить risk threshold.

Причина:

- Grid покращує closed/net PnL;
- але додає floating exposure;
- total equity drawdown залишається гіршим за допустимий поріг;
- навіть найкращий guard sweep варіант не проходить threshold `-0.01`.

Тому Grid не переноситься у paper profile.

## Чому directional guard недостатній

Directional guard блокує додавання нового layer у той самий напрямок, якщо same-direction basket вже має unrealized loss.

Це зменшило drawdown з приблизно `-0.0349` до `-0.0122`, але:

- risk threshold все ще не пройдено;
- cycles/day впали з `416.83` до `163.22`;
- balanced candidates при поточному порозі не знайдено.

## Рішення

Не створювати:

- Grid paper profile;
- Grid runtime profile;
- Grid real trading logic.

HF Grid залишається diagnostics/research-only напрямком.

## Наступний напрямок

Повернути фокус до `mean_reversion_hf_micro_v1`.

Наступне дослідження:

```bash
python manage.py hf-losing-cycle-diagnostics --profile mean_reversion_hf_micro_v1
```

Мета: зменшити кількість помилкових входів у HF v1 без додавання layered/grid exposure.

Причина: HF v1 має значно нижчий floating risk, тому покращувати варто entry direction і loss diagnostics, а не нарощувати шари.

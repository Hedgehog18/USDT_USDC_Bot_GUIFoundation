# HF Extreme Move Research

## Що виявлено

`hf-profit-audit` показав, що lifetime/profile profit для `mean_reversion_hf_micro_v1` змішує різні періоди:

- старі експериментальні запуски;
- clean-run результати;
- outlier/extreme close cycles;
- поточні recent-window цикли.

Через це lifetime profit більше не можна використовувати як головну метрику якості HF baseline. Для оперативної оцінки потрібно дивитися на:

- current run profit;
- latest 100 / 250 / 500 cycles net;
- lifetime net лише як історичний контекст;
- net without extreme close cycles.

## Чому `close_price=0.99992000` треба аналізувати окремо

У базі є cycles з `close_price=0.99992000`, які дають непропорційно великий PnL порівняно зі звичайними HF micro cycles. Такі рухи можуть бути реальними, але їх не можна змішувати зі звичайною статистикою baseline без окремого маркування.

Для цього додано diagnostics-only команду:

```bash
python manage.py hf-extreme-move-diagnostics --profile mean_reversion_hf_micro_v1
```

Вона показує:

- top profit cycles;
- extreme close price cycles;
- contribution extreme cycles до lifetime net;
- latest 100 / 250 / 500 windows;
- net without extreme cycles;
- recommendation: `EXTREME_DEPENDENT`, `MODERATE_EXTREME_IMPACT`, `LOW_EXTREME_IMPACT`.

## Поточний baseline

Основним baseline-кандидатом залишається:

```text
mean_reversion_hf_micro_v1
```

Його не змінюємо в межах цього research step. Reporting має чесно відділяти recent/current run performance від lifetime/outlier performance.

## Future Research

Можлива окрема research-ідея: extreme-move strategy/profile, який спеціально аналізує такі великі рухи. На цьому етапі його не реалізуємо:

- не створюємо runtime profile;
- не створюємо paper profile;
- не змінюємо trading behavior;
- не змінюємо `mean_reversion_hf_micro_v1`.

Поточний крок: тільки diagnostics + reporting + documentation.

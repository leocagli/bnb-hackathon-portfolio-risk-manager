# Drawdown Control

Sizing and regime budgeting reduce the *probability* of large losses; drawdown control reacts to losses that
happen anyway. It is the last line of defense and the difference between a bad month and a blown account.

All drawdown logic is measured against a **high-water mark (HWM)** of portfolio equity:

```
drawdown = (HWM - equity) / HWM        # 0.0 at a new high, 0.20 = down 20% from the peak
```

## 1. Throttle ladder

As drawdown deepens, cut exposure in steps. `drawdown_control.throttle` is an ordered list of
`{dd_gte, exposure_mult}` rules; apply the multiplier of the **deepest** threshold breached.

Example ladder:

| Drawdown ≥ | exposure_mult | Effect                          |
|------------|---------------|---------------------------------|
| 0.10       | 0.50          | Halve exposure at -10%          |
| 0.15       | 0.25          | Quarter exposure at -15%        |

Between thresholds, exposure is unchanged. The throttle multiplies the gross *after* regime budgeting, so a
risk-off market in a drawdown compounds both reductions.

## 2. Kill-switch

If drawdown reaches `drawdown_control.kill_switch_dd` (default 0.25), go fully to cash. This caps the
worst-case loss per cycle at roughly the kill-switch level (plus one day of slippage/gap risk).

## 3. Re-entry

A kill-switch in cash freezes equity, so drawdown never "recovers" on its own — you need an explicit
re-entry rule. `drawdown_control.reentry`:

- `cooldown_days` (default 3): wait this many days after the kill-switch before re-engaging. Avoids getting
  chopped up re-entering into the same falling knife.
- On re-entry, **reset the HWM to current equity**. This releases the throttle so the strategy can rebuild
  from a fresh base and participate in the recovery, instead of being permanently throttled by an old peak.
- `recover_to_dd_lte` (default 0.08): if still in the market (not killed) and drawdown improves back below
  this, the throttle naturally releases as the ladder thresholds are no longer breached.

The HWM reset on re-entry is a deliberate design choice: it trades a little extra risk for the ability to
recover. It is documented in the spec so a backtest reproduces it exactly.

## 4. Event de-risking (forward-looking)

Separate from realized drawdown, `event_risk` cuts exposure *before* known catalysts from
`get_upcoming_macro_events`:

- `derisk_before_high_impact_event_hours` (default 24): window before a high-impact event.
- `exposure_mult_during_event_window` (default 0.5): multiplier applied to gross inside the window.

This is multiplicative with the regime budget and the drawdown throttle.

## Why this matters (the math of recovery)

A 50% drawdown requires a 100% gain to recover; a 20% drawdown requires only 25%. Capping drawdown is the
highest-leverage thing a risk system does for long-run compounding. The backtest reports **max drawdown** and
**Calmar (CAGR / max drawdown)** precisely so this trade-off is visible: the overlay typically gives up some
raw upside in exchange for a much smaller hole to climb out of, raising Calmar.

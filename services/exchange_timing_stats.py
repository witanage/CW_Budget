"""
Deterministic statistics for the "Best time to exchange" feature.

Everything here is computed from the stored rate history, so the numbers are
reproducible and do not depend on an LLM. The Gemini analyzer receives these
figures as facts and only has to explain them.

Input shape (same as the analyzer / route):
    bank_data = {'HNB': [{'date': 'YYYY-MM-DD', 'rate': 301.5}, ...], ...}
Higher rate = better for the user (more LKR per unit of foreign currency).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTH_PARTS = [('Days 1-10', 1, 10), ('Days 11-20', 11, 20), ('Days 21-31', 21, 31)]

STALE_DAYS = 2          # a bank whose latest row is older than this is flagged
MIN_PATTERN_SAMPLES = 5  # minimum observations per bucket to call a pattern
MIN_CONDITIONAL_N = 15   # minimum samples for "history says..." statements


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()


def _series(data: List[dict]) -> List[Tuple[date, float]]:
    """Sorted, de-duplicated (last value wins per day) list of (date, rate)."""
    by_day: Dict[date, float] = {}
    for item in data or []:
        try:
            rate = float(item['rate'])
        except (TypeError, ValueError, KeyError):
            continue
        if rate <= 0:
            continue
        by_day[_to_date(item['date'])] = rate
    return sorted(by_day.items())


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)


def _stdev(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _percentile_rank(values: List[float], x: float) -> float:
    """Percent of values that are <= x (0-100). 100 = highest in the window."""
    if not values:
        return 50.0
    return 100.0 * sum(1 for v in values if v <= x) / len(values)


def _r(x: Optional[float], nd: int = 4) -> Optional[float]:
    return None if x is None else round(x, nd)


# ---------------------------------------------------------------------------
# Per-bank position
# ---------------------------------------------------------------------------
def _bank_position(series: List[Tuple[date, float]], today: date) -> Optional[dict]:
    if not series:
        return None
    last_date, current = series[-1]
    rates = [r for _, r in series]

    def window(days: int) -> List[float]:
        cutoff = last_date - timedelta(days=days)
        return [r for d, r in series if d > cutoff]

    w7, w30 = window(7), window(30)
    sd = _stdev(rates)
    avg7 = _mean(w7)
    return {
        'current': _r(current),
        'last_date': last_date.isoformat(),
        'days_stale': (today - last_date).days,
        'is_stale': (today - last_date).days > STALE_DAYS,
        'avg_7d': _r(avg7),
        'avg_30d': _r(_mean(w30)),
        'avg_period': _r(_mean(rates)),
        'min_period': _r(min(rates)),
        'max_period': _r(max(rates)),
        'pct_rank_30d': _r(_percentile_rank(w30, current), 1),
        'pct_rank_period': _r(_percentile_rank(rates, current), 1),
        'z_score': _r((current - _mean(rates)) / sd, 2) if sd > 0 else 0.0,
        'vs_7d_avg': _r(current - avg7),
        'momentum_7d': _r(current - w7[0]) if len(w7) >= 2 else None,
        'volatility_pct': _r(sd / _mean(rates) * 100, 3),
        'samples': len(rates),
    }


# ---------------------------------------------------------------------------
# Calendar patterns (detrended)
# ---------------------------------------------------------------------------
def _detrended(series: List[Tuple[date, float]], half_window: int = 3) -> List[Tuple[date, float]]:
    """Rate minus the mean of neighbouring days (±half_window, excluding itself).

    Removing the local level means a steady uptrend does not make "later in the
    month" look good just because the series is rising.
    """
    out = []
    for i, (d, r) in enumerate(series):
        neigh = [rr for dd, rr in series
                 if dd != d and abs((dd - d).days) <= half_window]
        if len(neigh) >= 3:
            out.append((d, r - _mean(neigh)))
    return out


def _bucket_stats(groups: Dict[str, List[float]], order: List[str]) -> List[dict]:
    rows = []
    for name in order:
        vals = groups.get(name, [])
        if len(vals) < MIN_PATTERN_SAMPLES:
            rows.append({'label': name, 'n': len(vals), 'avg_premium': None, 'significant': False})
            continue
        m = _mean(vals)
        se = _stdev(vals) / math.sqrt(len(vals))
        rows.append({
            'label': name,
            'n': len(vals),
            'avg_premium': _r(m),
            'significant': bool(se > 0 and abs(m) > 3 * se),
        })
    return rows


def calendar_patterns(series: List[Tuple[date, float]]) -> dict:
    dev = _detrended(series)
    by_wd: Dict[str, List[float]] = defaultdict(list)
    by_part: Dict[str, List[float]] = defaultdict(list)
    for d, v in dev:
        by_wd[WEEKDAYS[d.weekday()]].append(v)
        for name, lo, hi in MONTH_PARTS:
            if lo <= d.day <= hi:
                by_part[name].append(v)

    weekday = _bucket_stats(by_wd, [w for w in WEEKDAYS if w in by_wd])
    part = _bucket_stats(by_part, [p[0] for p in MONTH_PARTS])

    def best(rows):
        ok = [r for r in rows if r['avg_premium'] is not None]
        return max(ok, key=lambda r: r['avg_premium']) if ok else None

    bw, bp = best(weekday), best(part)
    return {
        'weekday': weekday,
        'month_part': part,
        'best_weekday': bw['label'] if bw and bw['significant'] else None,
        'best_month_part': bp['label'] if bp and bp['significant'] else None,
        'has_reliable_pattern': bool((bw and bw['significant']) or (bp and bp['significant'])),
        'note': 'Premium = rate minus the average of the surrounding ±3 days (LKR). '
                'A pattern is only called reliable when it is more than 3 standard errors from zero.',
    }


# ---------------------------------------------------------------------------
# "What happened historically if I waited?"
# ---------------------------------------------------------------------------
def _rate_on_or_after(series, idx_by_date, target: date, tolerance: int = 3):
    for off in range(tolerance + 1):
        d = target + timedelta(days=off)
        if d in idx_by_date:
            return idx_by_date[d]
    return None


def waiting_analysis(series: List[Tuple[date, float]], current_pct_30d: Optional[float]) -> dict:
    """For every past day: rate k days later minus rate that day.

    Also conditioned on how high that day's rate was within its trailing 30-day
    range, so we can answer "when the rate looked like today's, did waiting pay?"
    """
    idx = dict(series)
    horizons = (7, 14)
    rows = []  # (pct_at_start, {k: change})
    for d, r in series:
        trail = [rr for dd, rr in series if d - timedelta(days=30) < dd <= d]
        if len(trail) < 10:
            continue
        pct = _percentile_rank(trail, r)
        changes = {}
        for k in horizons:
            later = _rate_on_or_after(series, idx, d + timedelta(days=k))
            if later is not None:
                changes[k] = later - r
        if changes:
            rows.append((pct, changes))

    def summarize(subset, k):
        vals = [c[k] for _, c in subset if k in c]
        if not vals:
            return {'n': 0, 'avg_change': None, 'pct_higher': None}
        return {
            'n': len(vals),
            'avg_change': _r(_mean(vals)),
            'pct_higher': _r(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1),
        }

    if current_pct_30d is None:
        bucket, subset = 'all', rows
    elif current_pct_30d >= 70:
        bucket, subset = 'high', [x for x in rows if x[0] >= 70]
    elif current_pct_30d <= 30:
        bucket, subset = 'low', [x for x in rows if x[0] <= 30]
    else:
        bucket, subset = 'mid', [x for x in rows if 30 < x[0] < 70]

    return {
        'all_days': {f'{k}d': summarize(rows, k) for k in horizons},
        'similar_days': {f'{k}d': summarize(subset, k) for k in horizons},
        'similar_bucket': bucket,
        'note': 'Change = rate k days later minus rate on the day. "Similar days" are past days '
                'whose rate sat in the same part of its trailing 30-day range as today.',
    }


def salary_day_simulation(series: List[Tuple[date, float]], salary_day: int,
                          wait_days: int = 14) -> Optional[dict]:
    """Compare exchanging on the salary day with the following `wait_days` days."""
    if not 1 <= salary_day <= 31:
        return None
    by_month: Dict[Tuple[int, int], List[Tuple[date, float]]] = defaultdict(list)
    for d, r in series:
        by_month[(d.year, d.month)].append((d, r))

    months = []
    for (y, m), pts in sorted(by_month.items()):
        start = next(((d, r) for d, r in pts if d.day >= salary_day), None)
        if not start:
            continue
        d0, r0 = start
        after = [r for d, r in series if d0 < d <= d0 + timedelta(days=wait_days)]
        if len(after) < 3:
            continue
        months.append({
            'month': f'{y}-{m:02d}',
            'salary_date': d0.isoformat(),
            'rate_on_day': _r(r0),
            'avg_next': _r(_mean(after)),
            'best_next': _r(max(after)),
        })
    if not months:
        return None
    avg_gain = _mean([x['avg_next'] - x['rate_on_day'] for x in months])
    best_gain = _mean([x['best_next'] - x['rate_on_day'] for x in months])
    return {
        'salary_day': salary_day,
        'wait_days': wait_days,
        'months': months,
        'n_months': len(months),
        'avg_gain_if_wait': _r(avg_gain),
        'best_case_gain': _r(best_gain),
        'pct_months_waiting_better': _r(
            100.0 * sum(1 for x in months if x['avg_next'] > x['rate_on_day']) / len(months), 1),
        'note': 'best_case_gain uses hindsight (the peak of the following days) and is an upper bound, '
                'not something you can reliably capture.',
    }


# ---------------------------------------------------------------------------
# Bank comparison
# ---------------------------------------------------------------------------
def bank_comparison(positions: Dict[str, dict], user_bank: str, amount: float) -> dict:
    ranked = sorted(((b, p['current']) for b, p in positions.items()),
                    key=lambda x: x[1], reverse=True)
    user_rate = positions[user_bank]['current']
    best_bank, best_rate = ranked[0]
    rows = []
    for b, rate in ranked:
        rows.append({
            'bank': b,
            'rate': _r(rate),
            'lkr_total': round(rate * amount, 2),
            'diff_vs_user_lkr': round((rate - user_rate) * amount, 2),
            'is_stale': positions[b]['is_stale'],
            'last_date': positions[b]['last_date'],
        })
    return {
        'amount': amount,
        'ranking': rows,
        'best_bank': best_bank,
        'user_is_best': best_bank == user_bank or best_rate == user_rate,
        'gain_if_switch_lkr': round((best_rate - user_rate) * amount, 2),
    }


def cbsl_spread(bank_data: Dict[str, List[dict]], user_bank: str) -> Optional[dict]:
    """User bank's rate minus CBSL, now versus its own history."""
    if user_bank == 'CBSL' or 'CBSL' not in bank_data:
        return None
    u, c = dict(_series(bank_data.get(user_bank))), dict(_series(bank_data.get('CBSL')))
    common = sorted(set(u) & set(c))
    if len(common) < 5:
        return None
    spreads = [u[d] - c[d] for d in common]
    now = spreads[-1]
    return {
        'current': _r(now),
        'avg': _r(_mean(spreads)),
        'min': _r(min(spreads)),
        'max': _r(max(spreads)),
        'pct_rank': _r(_percentile_rank(spreads, now), 1),
        'as_of': common[-1].isoformat(),
    }


# ---------------------------------------------------------------------------
# Rule-based verdict
# ---------------------------------------------------------------------------
def rule_based_verdict(pos: dict, waiting: dict, comparison: dict, user_bank: str) -> dict:
    reasons: List[str] = []
    pct = pos['pct_rank_30d']
    mom = pos['momentum_7d']

    if pct >= 75:
        action = 'NOW'
        reasons.append(f"{user_bank} rate is in the top {max(100 - pct, 1):.0f}% of its last 30 days.")
    elif pct <= 35:
        if mom is not None and mom > 0:
            action = 'WAIT'
            reasons.append(f"Rate is low within its 30-day range ({pct:.0f}th percentile) "
                           f"but recovering ({mom:+.2f} LKR over 7 days).")
        else:
            action = 'MONITOR'
            reasons.append(f"Rate is low within its 30-day range ({pct:.0f}th percentile) "
                           "and not yet recovering.")
    else:
        action = 'MONITOR'
        reasons.append(f"Rate is mid-range ({pct:.0f}th percentile of the last 30 days).")

    # Evidence from history for days that looked like today
    sim7 = waiting['similar_days']['7d']
    evidence_ok = sim7['n'] >= MIN_CONDITIONAL_N and sim7['avg_change'] is not None
    if evidence_ok:
        reasons.append(
            f"In {sim7['n']} past days with a similar rate position, waiting 7 days changed the rate by "
            f"{sim7['avg_change']:+.2f} LKR on average and it was higher {sim7['pct_higher']:.0f}% of the time.")
        if action == 'NOW' and sim7['avg_change'] > 0 and sim7['pct_higher'] > 60:
            action = 'MONITOR'
            reasons.append('History suggests rates often kept rising from this level, so NOW is softened to MONITOR.')
        elif action == 'MONITOR' and sim7['avg_change'] < 0 and sim7['pct_higher'] < 40:
            action = 'NOW'
            reasons.append('History suggests rates usually fell from this level, so exchanging sooner is favoured.')
        elif action == 'MONITOR' and sim7['avg_change'] > 0 and sim7['pct_higher'] > 60:
            action = 'WAIT'
            reasons.append('History suggests rates usually rose from this level.')
    else:
        reasons.append(f"Only {sim7['n']} comparable past days: history gives little guidance.")

    if not comparison['user_is_best']:
        reasons.append(
            f"{comparison['best_bank']} currently pays more: +{comparison['gain_if_switch_lkr']:,.2f} LKR "
            f"on {comparison['amount']:,.0f}.")

    stale = [b['bank'] for b in comparison['ranking'] if b['is_stale']]
    if stale:
        reasons.append(f"Stale data for: {', '.join(stale)}. Comparisons involving them may be out of date.")

    # Confidence: sample size and data freshness
    if pos['samples'] < 20 or pos['is_stale']:
        confidence = 'LOW'
    elif evidence_ok and sim7['n'] >= 25:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'

    return {'action': action, 'confidence': confidence, 'reasons': reasons}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def compute_timing_stats(bank_data: Dict[str, List[dict]], user_bank: str,
                         amount: float = 1000.0, salary_day: Optional[int] = None,
                         today: Optional[date] = None) -> Optional[dict]:
    """Build the full deterministic analysis. Returns None if the user bank has no data."""
    today = today or date.today()
    series_by_bank = {b: _series(d) for b, d in bank_data.items()}
    positions = {b: p for b, s in series_by_bank.items() if (p := _bank_position(s, today))}
    if user_bank not in positions:
        return None

    user_series = series_by_bank[user_bank]
    pos = positions[user_bank]
    comparison = bank_comparison(positions, user_bank, amount)
    waiting = waiting_analysis(user_series, pos['pct_rank_30d'])

    return {
        'user_bank': user_bank,
        'amount': amount,
        'position': pos,
        'banks': positions,
        'comparison': comparison,
        'cbsl_spread': cbsl_spread(bank_data, user_bank),
        'calendar': calendar_patterns(user_series),
        'waiting': waiting,
        'salary_simulation': salary_day_simulation(user_series, salary_day) if salary_day else None,
        'verdict': rule_based_verdict(pos, waiting, comparison, user_bank),
    }


def format_for_prompt(stats: dict, currency_to: str = 'LKR') -> str:
    """Render the computed facts as text for the LLM prompt."""
    u = stats['user_bank']
    p = stats['position']
    lines = [f"\nVERIFIED STATISTICS (computed from the database; treat as facts, do not recalculate or contradict):"]
    lines.append(f"- {u} current {p['current']} ({p['last_date']}, {p['days_stale']} day(s) old); "
                 f"30-day percentile {p['pct_rank_30d']}; period percentile {p['pct_rank_period']}; z-score {p['z_score']}")
    lines.append(f"- 7d avg {p['avg_7d']}, 30d avg {p['avg_30d']}, momentum 7d {p['momentum_7d']}")

    c = stats['comparison']
    lines.append(f"- Bank ranking for {c['amount']:,.0f} units: " + '; '.join(
        f"{r['bank']} {r['rate']} ({r['diff_vs_user_lkr']:+,.2f} {currency_to} vs {u})" for r in c['ranking']))

    sp = stats.get('cbsl_spread')
    if sp:
        lines.append(f"- Spread over CBSL: now {sp['current']} (avg {sp['avg']}, range {sp['min']} to {sp['max']}, "
                     f"percentile {sp['pct_rank']})")

    cal = stats['calendar']
    if cal['has_reliable_pattern']:
        lines.append(f"- Reliable calendar pattern: best weekday = {cal['best_weekday']}, "
                     f"best part of month = {cal['best_month_part']}")
    else:
        lines.append("- Calendar patterns: NO statistically reliable weekday or day-of-month pattern was found. "
                     "Do not claim one.")

    for k in ('7d', '14d'):
        s = stats['waiting']['similar_days'][k]
        if s['n']:
            lines.append(f"- History: on {s['n']} similar days, waiting {k} changed the rate by "
                         f"{s['avg_change']:+} on average; higher {s['pct_higher']}% of the time")

    sim = stats.get('salary_simulation')
    if sim:
        lines.append(f"- Salary on day {sim['salary_day']} ({sim['n_months']} months): waiting {sim['wait_days']} days "
                     f"changed the average rate by {sim['avg_gain_if_wait']:+} (waiting was better in "
                     f"{sim['pct_months_waiting_better']}% of months)")

    v = stats['verdict']
    lines.append(f"- Rule-based verdict: {v['action']} (confidence {v['confidence']}). " + ' '.join(v['reasons']))
    return '\n'.join(lines) + '\n'

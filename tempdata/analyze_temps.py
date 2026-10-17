#!/usr/bin/env python3
"""Analyze the templog temperature/power log to design an ambient widget.

Usage:  python3 -I tempdata/analyze_temps.py [path/to/templog.csv]

Stdlib only (no numpy on this machine). Reads the CSV read-only and prints
every table and number quoted in tempdata/analysis.md as markdown, section
by section. Re-run it to regenerate the report numbers.

Definitions (also stated in the report):
  t          = boot_epoch + uptime  (CLOCK_BOOTTIME; epoch is unreliable, see DQ)
  wake       = resume row .. next suspend row (rows sorted by uptime)
  activity   = any wake longer than LONG_WAKE_S, any wake carrying a non-0x00
               wakeup_reason, any sleep shorter than SHORT_SLEEP_S (post-use
               autosleep bursts), any row with current > 0 or charger_online=1,
               and everything before the first suspend (install, on USB)
  tsa        = time since the end of the last activity block
  candidate  = resume row, reason 0x00, preceded by >= RTC_SLEEP_MIN_S of
               sleep, charger offline, current <= 0, not inside activity
  settled    = candidate with tsa >= N (N chosen from the settling curve)
"""
import bisect
import collections
import csv
import datetime as dt
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'raw', 'templog.csv')
EEST = dt.timezone(dt.timedelta(hours=3), 'EEST')

SENS = ('cpu', 'batt', 'board', 'accel')
LONG_WAKE_S = 45          # RTC wakes are ~7 s (~37 s when on charger at 100 %)
SHORT_SLEEP_S = 200       # shorter sleep = post-use autosleep burst
RTC_SLEEP_MIN_S = 240     # a candidate follows a full RTC sleep (~293 s)
GAP_S = 360               # cadence gap threshold
EPISODE_MERGE_S = 20 * 60 # activity blocks closer than this form one episode
HOLDOUT_DAYS = 14
FAST_MA = 1000            # charge current at/above this = constant-current phase
ANCHOR_MAX_S = 12 * 3600  # settled anchors for the interpolated baseline
COOL_MIN_S = 3 * 3600     # minimum undisturbed window for a cooldown fit
COOL_MAX_S = 8 * 3600
PLATEAU_TOL = 0.10        # deg C, inter-sensor delta flatness criterion
ANCHOR_N_H = 4.0          # strict anchors: candidates >= 4 h after activity
ANCHOR_SENS_H = (3.0, 6.0)  # sensitivity check for the anchor threshold
CM_MED_TOL = 0.10         # deg C, common-mode excess: median per bin
CM_P90_TOL = 99.0         # deg C, p90 criterion (disabled; see report)
SUPPRESS_P95 = 0.5        # deg C, acceptable p95 |error| when not flagged


# ---------------------------------------------------------------- helpers
def q(xs, p):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float('nan')
    k = (n - 1) * p
    lo = math.floor(k)
    hi = min(lo + 1, n - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def med(xs):
    return q(xs, 0.5)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float('nan')


def sd(xs):
    xs = list(xs)
    if len(xs) < 2:
        return float('nan')
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def corr(xs, ys):
    mx, my = mean(xs), mean(ys)
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else float('nan')


def f(x, d=2, sign=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return '–'
    return f'{x:+.{d}f}' if sign else f'{x:.{d}f}'


def loc(t):
    return dt.datetime.fromtimestamp(t, EEST)


def ts(t):
    return loc(t).strftime('%b %d %H:%M')


def md(headers, rows):
    print('| ' + ' | '.join(headers) + ' |')
    print('|' + '|'.join('---' for _ in headers) + '|')
    for r in rows:
        print('| ' + ' | '.join(str(x) for x in r) + ' |')
    print()


def h(title):
    print(f'\n## {title}\n')


def lstsq(X, y):
    p = len(X[0])
    M = [[sum(r[i] * r[j] for r in X) for j in range(p)] + [sum(r[i] * v for r, v in zip(X, y))]
         for i in range(p)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        for r in range(p):
            if r != c and M[c][c] != 0:
                fac = M[r][c] / M[c][c]
                for cc in range(c, p + 1):
                    M[r][cc] -= fac * M[c][cc]
    return [M[i][p] / M[i][i] for i in range(p)]


TAU_GRID = [2 * math.exp(i * math.log(400 / 2) / 199) for i in range(200)]  # minutes


def expfit(tm, ys):
    """Fit y = c + A*exp(-t/tau); grid tau, closed-form c and A."""
    best = None
    my = mean(ys)
    for tau in TAU_GRID:
        x = [math.exp(-t / tau) for t in tm]
        mx = mean(x)
        vx = sum((a - mx) ** 2 for a in x)
        if vx <= 1e-12:
            continue
        A = sum((a - mx) * (b - my) for a, b in zip(x, ys)) / vx
        c = my - A * mx
        sse = sum((c + A * a - b) ** 2 for a, b in zip(x, ys))
        if best is None or sse < best[0]:
            best = (sse, tau, A, c)
    sse, tau, A, c = best
    return dict(tau=tau, A=A, c=c, rmse=math.sqrt(sse / len(ys)),
                edge=tau in (TAU_GRID[0], TAU_GRID[-1]))


def stats_row(xs, d=2):
    return [len(xs), f(mean(xs), d, True), f(sd(xs), d), f(q(xs, .05), d, True), f(q(xs, .95), d, True)]


def abs_stats(errs, d=2):
    a = [abs(e) for e in errs]
    return [len(errs), f(mean(errs), d, True), f(sd(errs), d), f(med(a), d), f(q(a, .95), d),
            f(max(a) if a else float('nan'), d)]


# ---------------------------------------------------------------- load
raw = list(csv.DictReader(open(CSV_PATH, newline='')))
cols = list(raw[0].keys())
empty = collections.Counter(k for r in raw for k in cols if r[k] == '')
R = []
for i, r in enumerate(raw):
    if any(r[k] == '' for k in ('uptime', 'cpu_mC', 'batt_dC', 'board_mC', 'accel_mC', 'current_uA')):
        continue
    R.append(dict(i=i, ev=r['event'], epoch=int(r['epoch']), up=float(r['uptime']),
                  cpu=int(r['cpu_mC']) / 1000, batt=int(r['batt_dC']) / 10,
                  board=int(r['board_mC']) / 1000, accel=int(r['accel_mC']) / 1000,
                  cap=int(r['capacity_pct']), status=r['status'], I=int(r['current_uA']) / 1000,
                  chg=int(r['charger_online']), wr=r['wakeup_reason'], iso=r['iso']))

# uptime monotonicity in FILE order (before sorting)
inv = [R[k - 1]['up'] - R[k]['up'] for k in range(1, len(R)) if R[k]['up'] < R[k - 1]['up']]
reboots = [R[k] for k in range(1, len(R)) if R[k]['up'] < R[k - 1]['up'] - 1.0]
BOOT = med([r['epoch'] - r['up'] for r in R])
for r in R:
    r['t'] = BOOT + r['up']
dev = [r['epoch'] - r['t'] for r in R]
epoch_bad = [r for r in R if abs(r['epoch'] - r['t']) > 2]
R.sort(key=lambda r: (r['up'], r['i']))
T0, T_END = R[0]['t'], R[-1]['t']
T_SPLIT = T_END - HOLDOUT_DAYS * 86400

# ---------------------------------------------------------------- wakes
wakes, cur, last_sus = [], None, None
double_res = double_sus = 0
for k, r in enumerate(R):
    r['wake'] = None
    if r['ev'] == 'resume':
        if cur is not None:
            double_res += 1
        cur = dict(k0=k, t0=r['t'], wr=r['wr'], rows=[k],
                   slept=(r['t'] - R[last_sus]['t']) if last_sus is not None else None,
                   prev_sus=last_sus)
        r['wake'] = cur
    elif r['ev'] == 'suspend':
        if cur is None:
            double_sus += 1
        else:
            cur['rows'].append(k)
            cur['k1'], cur['t1'] = k, r['t']
            cur['dur'] = r['t'] - cur['t0']
            r['wake'] = cur
            wakes.append(cur)
        last_sus, cur = k, None
    elif cur is not None:
        cur['rows'].append(k)
        r['wake'] = cur
attached = 0
for k, r in enumerate(R):
    if r['wake'] is None and r['ev'] in ('timer', 'udev-charger'):
        k2 = next((j for j in range(k + 1, min(k + 6, len(R))) if R[j]['ev'] == 'resume'), None)
        if k2 is not None and R[k2]['wake'] is not None and R[k2]['t'] - r['t'] < 2:
            r['wake'] = R[k2]['wake']
            r['wake']['rows'].append(k)
            attached += 1
outside = [r for r in R if r['wake'] is None and r['ev'] not in ('suspend',)]
for w in wakes:
    w['rows'].sort()
    w['reasons'] = {R[k]['wr'] for k in w['rows']}

# ---------------------------------------------------------------- activity
acts = []
first_sus = next(k for k, r in enumerate(R) if r['ev'] == 'suspend')
acts.append((R[0]['t'], R[first_sus]['t'], 'init'))
for w in wakes:
    if w['reasons'] != {'0x00'} or w['dur'] > LONG_WAKE_S:
        acts.append((w['t0'], w['t1'], 'use'))
    if w['slept'] is not None and w['slept'] < SHORT_SLEEP_S:
        acts.append((R[w['prev_sus']]['t'], w['t1'], 'use'))
k = 0
while k < len(R):
    if R[k]['chg'] or R[k]['I'] > 0:
        j = k
        while j + 1 < len(R) and (R[j + 1]['chg'] or R[j + 1]['I'] > 0):
            j += 1
        end = R[j + 1]['t'] if j + 1 < len(R) else R[j]['t']
        acts.append((R[k]['t'], end, 'charge'))
        k = j + 1
    else:
        k += 1
acts.sort()


def merge(intervals, tol):
    out = []
    for s, e, kind in intervals:
        if out and s <= out[-1]['end'] + tol:
            out[-1]['end'] = max(out[-1]['end'], e)
            out[-1]['kinds'].add(kind)
        else:
            out.append(dict(start=s, end=e, kinds={kind}))
    return out


blocks = merge(acts, 1.0)
bstart = [b['start'] for b in blocks]
episodes = merge(acts, EPISODE_MERGE_S)
for ep in episodes:
    ep['type'] = 'init' if 'init' in ep['kinds'] else 'charge' if 'charge' in ep['kinds'] else 'use'
estart = [e['start'] for e in episodes]


def tsa_of(t):
    """Seconds since end of last activity block; None if inside a block."""
    j = bisect.bisect_left(bstart, t) - 1
    if j < 0:
        return None
    if t <= blocks[j]['end']:
        return None
    return t - blocks[j]['end']


def last_episode(t):
    j = bisect.bisect_left(estart, t) - 1
    return episodes[j] if j >= 0 else None


cands = []
for r in R:
    w = r['wake']
    if r['ev'] != 'resume' or w is None or r['wr'] != '0x00':
        continue
    if w['slept'] is None or w['slept'] < RTC_SLEEP_MIN_S or r['chg'] or r['I'] > 0:
        continue
    a = tsa_of(r['t'])
    if a is None:
        continue
    r['tsa'] = a
    ep = last_episode(r['t'])
    r['eptype'] = ep['type'] if ep else 'init'
    v = sorted(r[s] for s in SENS)
    r['med4'] = (v[1] + v[2]) / 2
    r['med4_is_ntc'] = abs(r['med4'] - (r['batt'] + r['board']) / 2) < 1e-9
    cands.append(r)
# Aug 29 (install day: on USB at 100 %, charger-warmed, then cooling) is excluded from baselines.
EXCL_T = dt.datetime.combine(loc(T0).date() + dt.timedelta(days=1), dt.time(0), EEST).timestamp()
for r in cands:
    r['base_ok'] = r['t'] >= EXCL_T

# ================================================================ 1. DATA QUALITY
print(f'# analyze_temps.py output\n\nSource: `{os.path.relpath(CSV_PATH, os.path.dirname(HERE))}`')
h('1. Data quality')
ev = collections.Counter(r['ev'] for r in R)
wrc = collections.Counter(r['wr'] for r in R)
print(f'- Rows: {len(raw)} data rows ({len(R)} parsed), {ts(T0)} -> {ts(T_END)} EEST '
      f'({(T_END - T0) / 86400:.2f} days). Empty fields: {dict(empty) or 0}.')
print(f'- Events: {dict(ev)}')
print(f'- wakeup_reason over all rows: {dict(wrc)}')
print(f'- Uptime inversions in file order: {len(inv)} (max {max(inv) if inv else 0:.2f} s, flock write races); '
      f'drops > 1 s (reboot): {len(reboots)}.')
print(f'- Boot epoch (median epoch - uptime): {dt.datetime.fromtimestamp(BOOT, dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC; '
      f'|epoch - t| p1/p99 = {q(dev, .01):+.2f}/{q(dev, .99):+.2f} s; rows off by > 2 s: '
      + ', '.join(f"{r['iso']} ({r['epoch'] - r['t']:+.0f} s)" for r in epoch_bad))
print(f'- Wakes: {len(wakes)}; double resume (missing suspend row): {double_res}; double suspend: {double_sus}; '
      f'timer/udev rows sampled < 2 s before their own resume row (attached to that wake): {attached}; '
      f'rows outside any wake: {len(outside)} '
      f'({collections.Counter(r["ev"] for r in outside)}, all before the first suspend at {ts(R[first_sus]["t"])}: '
      f'{all(r["t"] < R[first_sus]["t"] for r in outside)}).')
sleeps = [w['slept'] for w in wakes if w['slept'] is not None]
print(f'- Longest single sleep (suspend -> resume): {max(sleeps):.0f} s. Sleeps >= 240 s: '
      f'{sum(s >= 240 for s in sleeps)}; < 200 s: {sum(s < 200 for s in sleeps)}.')

days = collections.Counter(loc(r['t']).date() for r in R if r['ev'] == 'timer')
full = [v for d_, v in days.items() if d_ not in (loc(T0).date(), loc(T_END).date())]
print(f'- Timer rows per full local day: min {min(full)}, max {max(full)}, median {med(full):.0f} (288 = every 5 min).')

print('\n### Wake durations by reason (resume -> suspend)\n')
rows_ = []
byr = collections.defaultdict(list)
for w in wakes:
    byr[w['wr']].append(w['dur'])
for kk in sorted(byr):
    v = byr[kk]
    rows_.append([kk, len(v), f(q(v, .5), 1), f(q(v, .9), 1), f(max(v), 0), sum(x > LONG_WAKE_S for x in v)])
md(['reason at resume', 'wakes', 'p50 s', 'p90 s', 'max s', f'> {LONG_WAKE_S} s'], rows_)
x08 = [r for r in R if r['wr'] == '0x08']
print('0x08 rows (undocumented reason; treated as non-RTC activity): '
      + '; '.join(f"{ts(r['t'])} {r['ev']}" for r in x08) + '\n')
long00 = [w for w in wakes if w['wr'] == '0x00' and w['dur'] > LONG_WAKE_S]
print(f'0x00 wakes longer than {LONG_WAKE_S} s: {len(long00)} — '
      + '; '.join(f"{ts(w['t0'])} {w['dur']:.0f} s"
                  + (' (charging)' if any(R[k]['I'] > 0 for k in w['rows']) else '') for w in long00
                  if w['dur'] > 60) + '\n')
w37 = [w for w in wakes if w['wr'] == '0x00' and 30 < w['dur'] <= LONG_WAKE_S
       and w['slept'] and w['slept'] >= RTC_SLEEP_MIN_S]
print(f'0x00 RTC wakes of 30-{LONG_WAKE_S} s: {len(w37)}; with charger_online=1 on every row: '
      f"{sum(all(R[k]['chg'] for k in w['rows']) for w in w37)}; on charger on resume row: "
      f"{sum(R[w['k0']]['chg'] for w in w37)} (the on-charger-at-100 % regime).\n")

print('### Cadence gaps (> 6 min with no rows)\n')
gaps = []
for k in range(1, len(R)):
    d_ = R[k]['t'] - R[k - 1]['t']
    if d_ > GAP_S:
        gaps.append((R[k - 1], R[k], d_))
rows_ = []
for a, b, d_ in gaps:
    rows_.append([ts(a['t']), ts(b['t']), f(d_ / 60, 1), f"{a['ev']}->{b['ev']}"]
                 + [f(b[s] - a[s], 2, True) for s in ('board', 'batt', 'cpu', 'accel')])
md(['last row', 'next row', 'gap min', 'events', 'Δboard', 'Δbatt', 'Δcpu', 'Δaccel'], rows_)
print(f'Gaps: {len(gaps)}; total {sum(g[2] for g in gaps) / 60:.0f} min; '
      f'longest {max(g[2] for g in gaps) / 60:.1f} min; last gap ends {ts(gaps[-1][1]["t"])}. '
      f'No gap approaches hibernation length.\n')

print('### Stale-read check\n')
eqs = collections.defaultdict(lambda: [0, 0])
dif = collections.defaultdict(list)
prev_sus_row = None
for k, r in enumerate(R):
    if r['ev'] == 'suspend':
        if prev_sus_row is not None and 250 < r['t'] - prev_sus_row['t'] < 350:
            for s in SENS:
                eqs[('sus_vs_prev_sus', s)][0] += r[s] == prev_sus_row[s]
                eqs[('sus_vs_prev_sus', s)][1] += 1
        prev_sus_row = r
    if r['ev'] == 'resume' and r['wake'] and r['wake']['prev_sus'] is not None \
            and r['wake']['slept'] >= RTC_SLEEP_MIN_S:
        p = R[r['wake']['prev_sus']]
        for s in SENS:
            eqs[('res_vs_prev_sus', s)][0] += r[s] == p[s]
            eqs[('res_vs_prev_sus', s)][1] += 1
            dif[('res_minus_prev_sus', s)].append(r[s] - p[s])
    if r['ev'] == 'timer' and r['wake'] and r['wake']['k0'] != k:
        rr = R[r['wake']['k0']]
        if abs(r['t'] - rr['t']) < 2:
            for s in SENS:
                eqs[('timer_vs_res', s)][0] += r[s] == rr[s]
                eqs[('timer_vs_res', s)][1] += 1
                dif[('timer_minus_res', s)].append(r[s] - rr[s])
rows_ = []
for s in SENS:
    a, b, c = eqs[('res_vs_prev_sus', s)], eqs[('sus_vs_prev_sus', s)], eqs[('timer_vs_res', s)]
    dd = dif[('res_minus_prev_sus', s)]
    rows_.append([s, f'{100 * a[0] / a[1]:.1f} % of {a[1]}', f(mean(dd), 2, True), f(q(dd, .05), 2, True),
                  f'{100 * b[0] / b[1]:.1f} %', f'{100 * c[0] / c[1]:.1f} % of {c[1]}'])
md(['sensor', 'resume == prev suspend', 'mean Δ resume−suspend °C', 'p5 Δ',
    'suspend == prev suspend (300 s, fresh)', 'timer == resume (< 2 s apart)'], rows_)
rows_ = []
for s in SENS:
    dd = dif[('timer_minus_res', s)]
    rows_.append([s, len(dd), f(mean(dd), 3, True), f(sd(dd), 3), f(sd(dd) / math.sqrt(2), 3)])
md(['sensor', 'pairs', 'mean timer−resume °C', 'sd °C', 'per-read noise sd/√2 °C'], rows_)


# ================================================================ anchors / baseline
def make_amb(anchors):
    """Interpolated settled level of sensor s at time t: median of the 3 nearest
    anchors on each side (both within ANCHOR_MAX_S), linear in time."""
    at = [r['t'] for r in anchors]

    def amb(t, s):
        j = bisect.bisect_left(at, t)
        if j == 0 or j >= len(anchors):
            return None
        before, after = anchors[max(0, j - 3):j], anchors[j:j + 3]
        tb, ta = before[-1]['t'], after[0]['t']
        if t - tb > ANCHOR_MAX_S or ta - t > ANCHOR_MAX_S:
            return None
        vb, va = med([x[s] for x in before]), med([x[s] for x in after])
        return vb + (va - vb) * (t - tb) / (ta - tb) if ta > tb else vb
    return amb


CM_EDGES = [0, 1 / 6, 1 / 3, .5, .75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6]


def hfmt(x):
    return f'{x * 60:.0f} min' if x < 1 else f'{x:g} h'


def cm_curve(n0_h, typ=None):
    anchors = [r for r in cands if r['base_ok'] and r['tsa'] >= n0_h * 3600]
    amb_ = make_amb(anchors)
    rows = []
    for lo, hi in zip(CM_EDGES[:-1], CM_EDGES[1:]):
        if hi > n0_h + 1e-9:
            break
        sel = [r for r in cands if r['base_ok'] and lo * 3600 <= r['tsa'] < hi * 3600
               and (typ is None or r['eptype'] == typ)]
        ex = {s: [] for s in SENS}
        for r in sel:
            a = {s: amb_(r['t'], s) for s in SENS}
            if a['board'] is None:
                continue
            for s in SENS:
                ex[s].append(r[s] - a[s])
        rows.append(dict(lo=lo, hi=hi, n=len(ex['board']), ex=ex))
    N = None
    for i, b in enumerate(rows):
        later = [bb for bb in rows[i:] if bb['n'] >= 30]
        if all(med(bb['ex'][s]) <= CM_MED_TOL and q(bb['ex'][s], .9) <= CM_P90_TOL
               for bb in later for s in ('batt', 'board', 'accel')):
            N = b['lo']
            break
    return N, rows, amb_, anchors


# ================================================================ 2. SETTLED AGREEMENT
h('2. Settling curve and settled agreement')
print(f'Candidates (0x00 resume after >= {RTC_SLEEP_MIN_S} s sleep, charger offline, I <= 0, outside activity): '
      f'{len(cands)}; {sum(r["base_ok"] for r in cands)} after excluding install day {loc(T0):%b %d}. '
      f'Activity blocks: {len(blocks)}; episodes (merged < {EPISODE_MERGE_S // 60} min): '
      f'{len(episodes)} ({dict(collections.Counter(e["type"] for e in episodes))}).\n')

print('### 2a. Inter-sensor deltas vs time since activity (the requested spread curve)\n')
base = [r for r in cands if r['base_ok']]
EDGES = [0, .25, .5, .75, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 24, 48, 1e9]
PAIRS = (('cpu', 'board'), ('batt', 'board'), ('accel', 'board'))
plateau = {p: med([r[p[0]] - r[p[1]] for r in base if r['tsa'] >= 8 * 3600]) for p in PAIRS}
bins = []
for lo, hi in zip(EDGES[:-1], EDGES[1:]):
    sel = [r for r in base if lo * 3600 <= r['tsa'] < hi * 3600]
    if not sel:
        continue
    b = dict(lo=lo, hi=hi, n=len(sel),
             night=mean([1 if loc(r['t']).hour < 7 or loc(r['t']).hour >= 22 else 0 for r in sel]))
    for p in PAIRS:
        b[p] = med([r[p[0]] - r[p[1]] for r in sel])
    b['spread'] = med([max(r[s] for s in SENS) - min(r[s] for s in SENS) for r in sel])
    b['spread3'] = med([max(r['batt'], r['board'], r['accel']) - min(r['batt'], r['board'], r['accel'])
                        for r in sel])
    bins.append(b)
N_DELTA = None
for idx, b in enumerate(bins):
    if all(all(abs(bb[p] - plateau[p]) <= PLATEAU_TOL for p in PAIRS) for bb in bins[idx:] if bb['n'] >= 30):
        N_DELTA = b['lo']
        break
rows_ = []
for b in bins:
    hi = '∞' if b['hi'] > 1e8 else f"{b['hi']:g}"
    rows_.append([f"{b['lo']:g}–{hi}", b['n'], f"{100 * b['night']:.0f} %"]
                 + [f(b[p], 2, True) for p in PAIRS] + [f(b['spread'], 2), f(b['spread3'], 2)])
md(['hours since activity', 'n', 'night share (22–07 h)', 'cpu−board', 'batt−board', 'accel−board',
    'spread of 4 (max−min)', 'spread without cpu'], rows_)
print(f'Plateau (>= 8 h): ' + ', '.join(f'{a}−{b} {plateau[(a, b)]:+.2f}' for a, b in PAIRS)
      + f' °C. Deltas are within ±{PLATEAU_TOL} °C of plateau from **{N_DELTA:g} h** on. '
      'The deltas settle early because the sensors cool together; the spread cannot see the shared excess.\n')

print(f'### 2b. Common-mode excess vs time since activity (anchors: candidates >= {ANCHOR_N_H:g} h)\n')
print('Excess = reading minus the same sensor\'s level interpolated between the 3 nearest strict anchors on '
      f'each side (both within {ANCHOR_MAX_S // 3600} h). Median / p90, °C.\n')
N_H, cm_rows, amb, anchors = cm_curve(ANCHOR_N_H)
anchor_t = [r['t'] for r in anchors]
rows_ = []
for b in cm_rows:
    rows_.append([f"{hfmt(b['lo'])}–{hfmt(b['hi'])}", b['n']]
                 + [f(med(b['ex'][s]), 2, True) + ' / ' + f(q(b['ex'][s], .9), 2, True) for s in SENS])
md(['time since activity', 'n', 'cpu', 'batt', 'board', 'accel'], rows_)
sens_N = {n0: cm_curve(n0)[0] for n0 in ANCHOR_SENS_H}
print(f'Rule: N = first bin start after which every bin (n >= 30) has median excess <= {CM_MED_TOL} °C and '
      f'p90 <= {CM_P90_TOL} °C for batt, board and accel. **N = {hfmt(N_H)}** '
      f'(anchor threshold sensitivity: ' + ', '.join(f'{n0:g} h anchors -> N = {hfmt(v) if v is not None else "none"}'
                                                    for n0, v in sens_N.items()) + ').\n')
for typ in ('use', 'charge'):
    Nt, rws, _, _ = cm_curve(ANCHOR_N_H, typ)
    print(f'- After {typ} episodes only: N = {hfmt(Nt) if Nt is not None else "> " + hfmt(ANCHOR_N_H)}; '
          + ', '.join(f"{hfmt(b['lo'])} board {f(med(b['ex']['board']), 2, True)}/{f(q(b['ex']['board'], .9), 2, True)} (n {b['n']})"
                      for b in rws if b['lo'] >= 0.5 and b['lo'] <= 2))
print()
print(f'Strict anchors: {len(anchors)}.\n')

N_S = N_H * 3600
settled = [r for r in base if r['tsa'] >= N_S]
for r in settled:
    r['week'] = max(1, 7 - int((T_END - r['t']) // (7 * 86400)))
    r['test'] = r['t'] >= T_SPLIT
print(f'Settled samples (tsa >= {hfmt(N_H)}, from {loc(EXCL_T):%b %d}): {len(settled)} '
      f'({100 * len(settled) / len(base):.0f} % of candidates). Train (< {ts(T_SPLIT)}): '
      f'{sum(not r["test"] for r in settled)}; held-out last {HOLDOUT_DAYS} days: {sum(r["test"] for r in settled)}. '
      f'Median of four equals the batt/board mean in {100 * mean([r["med4_is_ntc"] for r in settled]):.1f} % '
      'of settled samples (cpu always highest, accel always lowest).\n')

print('### 2c. Offsets vs the median of four (all settled samples)\n')
rows_ = []
for s in SENS:
    rows_.append([s] + stats_row([r[s] - r['med4'] for r in settled]))
md(['sensor', 'n', 'mean °C', 'sd °C', 'p5 °C', 'p95 °C'], rows_)
spread = [max(r[s] for s in SENS) - min(r[s] for s in SENS) for r in settled]
spread3 = [max(r['batt'], r['board'], r['accel']) - min(r['batt'], r['board'], r['accel']) for r in settled]
ntc = [r['batt'] - r['board'] for r in settled]
print(f'Spread across the four (max−min): mean {mean(spread):.2f}, p50 {med(spread):.2f}, p95 {q(spread, .95):.2f} °C. '
      f'Without cpu: p50 {med(spread3):.2f}, p95 {q(spread3, .95):.2f} °C. '
      f'NTC pair batt−board: mean {mean(ntc):+.2f}, sd {sd(ntc):.2f}, p5/p95 {q(ntc, .05):+.2f}/{q(ntc, .95):+.2f} °C.\n')

print('### 2d. Per-week stability (mean offset vs median of four, °C)\n')
WEEKS = sorted({r['week'] for r in settled})
wk_lab = {}
for wk in WEEKS:
    a = T_END - (7 - wk + 1) * 7 * 86400
    b = T_END - (7 - wk) * 7 * 86400
    wk_lab[wk] = f"W{wk} {loc(max(a, EXCL_T)):%b %d}–{loc(b):%b %d}"
rows_ = []
for wk in WEEKS:
    sel = [r for r in settled if r['week'] == wk]
    rows_.append([wk_lab[wk] + (' (hold-out)' if wk >= 6 else ''), len(sel)]
                 + [f(mean([r[s] - r['med4'] for r in sel]), 2, True) for s in SENS]
                 + [f(mean([r['batt'] - r['board'] for r in sel]), 2, True), f(med([r['med4'] for r in sel]), 2)])
md(['week', 'n'] + list(SENS) + ['batt−board', 'median of four °C'], rows_)
rows_ = []
deep = [r for r in settled if r['tsa'] >= 6 * 3600]
for s in SENS:
    wm = [mean([r[s] - r['med4'] for r in settled if r['week'] == wk]) for wk in WEEKS]
    out = [s, f(max(wm) - min(wm), 2)]
    for data in (settled, deep):
        xs = [r['med4'] for r in data]
        ys = [r[s] - r['med4'] for r in data]
        mx, my = mean(xs), mean(ys)
        slope = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
        out += [f(slope, 3, True), f(corr(xs, ys), 2, True)]
    rows_.append(out)
md(['sensor', 'week-to-week range of mean offset °C', 'offset slope vs level °C/°C', 'r',
    f'slope, tsa >= 6 h (n {len(deep)})', 'r'], rows_)

# gain vs lag: regress (batt − board) on level and on the 1-h board slope (thermal lag proxy)
st_t_ = [r['t'] for r in settled]
X_, y_ = [], []
for r in settled:
    j = bisect.bisect_left(st_t_, r['t'] - 3600)
    if j < len(settled) and abs(settled[j]['t'] - (r['t'] - 3600)) < 200 \
            and abs((r['tsa'] - settled[j]['tsa']) - (r['t'] - settled[j]['t'])) < 1:
        X_.append([1.0, r['med4'], r['board'] - settled[j]['board']])
        y_.append(r['batt'] - r['board'])
b_lvl = lstsq([[x[0], x[1]] for x in X_], y_)
b_both = lstsq(X_, y_)
calm = [(x, y) for x, y in zip(X_, y_) if abs(x[2]) <= 0.05]
b_calm = lstsq([[x[0], x[1]] for x, y in calm], [y for x, y in calm])
print(f'batt−board vs level, settled samples with a 1-h history (n {len(X_)}): level only {b_lvl[1]:+.3f} °C/°C; '
      f'level + 1-h board slope: level {b_both[1]:+.3f} °C/°C, slope {b_both[2]:+.3f} °C per °C/h; '
      f'only samples with |1-h board change| <= 0.05 °C (n {len(calm)}): level {b_calm[1]:+.3f} °C/°C.\n')

print('### 2e. Quantization and noise\n')
by_t = settled  # already time-ordered
rows_ = []
for s in SENS:
    vals = sorted({round(r[s] * 1000) for r in R})
    steps = collections.Counter(round(abs(b - a)) for a, b in zip(vals, vals[1:]))
    quantum = steps.most_common(1)[0][0] / 1000
    resid = []
    for a, b, c in zip(by_t, by_t[1:], by_t[2:]):
        if 250 < b['t'] - a['t'] < 350 and 250 < c['t'] - b['t'] < 350:
            resid.append(b[s] - (a[s] + c[s]) / 2)
    noise = sd(resid) / math.sqrt(1.5)
    pair = sd(dif[('timer_minus_res', s)]) / math.sqrt(2)
    same5 = mean([1 if b[s] == a[s] else 0 for a, b in zip(by_t, by_t[1:]) if 250 < b['t'] - a['t'] < 350])
    rows_.append([s, f(quantum, 4), f(pair, 3), f(noise, 3), f'{100 * same5:.0f} %'])
md(['sensor', 'quantum °C', 'read noise sd, simultaneous pairs °C', 'sd, detrended 5-min triplets °C',
    'unchanged after 5 min'], rows_)

# ================================================================ 3. ABSOLUTE LEVEL + DRIFT
h('3. Absolute level vs the 22–26 °C recollection, and drift')
rows_ = []
for s in SENS + ('med4',):
    v = [r[s] for r in settled]
    rows_.append([s if s != 'med4' else 'median of four', f(min(v), 1), f(q(v, .05), 1), f(med(v), 1),
                  f(q(v, .95), 1), f(max(v), 1),
                  f'{100 * mean([1 if 22 <= x <= 26 else 0 for x in v]):.0f} %',
                  f'{100 * mean([1 if x < 22 else 0 for x in v]):.0f} %',
                  f'{100 * mean([1 if x > 26 else 0 for x in v]):.0f} %'])
md(['sensor', 'min', 'p5', 'p50', 'p95', 'max', 'in 22–26', 'below 22', 'above 26'], rows_)

print('### Warm settled stretches (board > 27 °C while settled)\n')
runs = []
for r in settled:
    if r['board'] > 27:
        if runs and r['t'] - runs[-1][-1]['t'] < 1200:
            runs[-1].append(r)
        else:
            runs.append([r])
rows_ = []
for run in runs:
    pk = max(run, key=lambda r: r['board'])
    rows_.append([ts(run[0]['t']), f((run[-1]['t'] - run[0]['t']) / 60, 0), len(run), f(pk['board'], 1),
                  f(pk['tsa'] / 3600, 1), f(pk['cpu'] - pk['board'], 2, True), f(pk['batt'] - pk['board'], 2, True),
                  f(pk['accel'] - pk['board'], 2, True)])
md(['start', 'minutes', 'n', 'peak board °C', 'h since activity at peak', 'cpu−board', 'batt−board',
    'accel−board'], rows_)
print(f'{len(runs)} stretches, {sum(len(x) for x in runs)} samples ({100 * sum(len(x) for x in runs) / len(settled):.1f} % '
      f'of settled). Settled plateau for comparison: cpu−board {plateau[("cpu", "board")]:+.2f}, batt−board '
      f'{plateau[("batt", "board")]:+.2f}, accel−board {plateau[("accel", "board")]:+.2f} °C. A batt−board delta '
      'well below plateau means the battery lags a heat source; >= 20 h after any activity that source is external.\n')

print('### Weekly median of settled readings (°C)\n')
rows_ = []
for wk in WEEKS:
    sel = [r for r in settled if r['week'] == wk]
    rows_.append([wk_lab[wk], len(sel)] + [f(med([r[s] for r in sel]), 2) for s in SENS]
                 + [f(q([r['board'] for r in sel], .05), 1) + '–' + f(q([r['board'] for r in sel], .95), 1)])
md(['week', 'n'] + list(SENS) + ['board p5–p95'], rows_)

print('### Diurnal profile, local EEST (settled board)\n')
print('Deviation = board minus the mean of settled board within ±12 h (windows covering >= 16 distinct hours).\n')
tt = [r['t'] for r in by_t]
hour_dev = collections.defaultdict(list)
hour_abs = collections.defaultdict(list)
for r in by_t:
    lo, hi = bisect.bisect_left(tt, r['t'] - 43200), bisect.bisect_right(tt, r['t'] + 43200)
    win = by_t[lo:hi]
    hour_abs[loc(r['t']).hour].append(r['board'])
    if len({loc(x['t']).hour for x in win}) >= 16:
        hour_dev[loc(r['t']).hour].append(r['board'] - mean([x['board'] for x in win]))
rows_ = []
for hr in range(24):
    rows_.append([f'{hr:02d}', len(hour_abs[hr]), f(med(hour_abs[hr]), 2) if hour_abs[hr] else '–',
                  len(hour_dev[hr]), f(med(hour_dev[hr]), 2, True) if hour_dev[hr] else '–'])
md(['hour', 'n', 'median board °C', 'n (dev)', 'median deviation °C'], rows_)
hd = {hr: med(v) for hr, v in hour_dev.items() if len(v) >= 30}
print(f'Diurnal swing (hours with n >= 30): min {min(hd.values()):+.2f} at {min(hd, key=hd.get):02d} h, '
      f'max {max(hd.values()):+.2f} at {max(hd, key=hd.get):02d} h, range {max(hd.values()) - min(hd.values()):.2f} °C.\n')
daily = collections.defaultdict(list)
for r in settled:
    daily[loc(r['t']).date()].append(r['board'])
dm = sorted((d_, med(v), len(v)) for d_, v in daily.items() if len(v) >= 24)
print('Daily median settled board (days with >= 24 settled samples): '
      + ', '.join(f'{d_:%m-%d} {m:.1f}' for d_, m, n in dm))
print(f'Daily medians: min {min(m for _, m, _ in dm):.1f}, max {max(m for _, m, _ in dm):.1f} °C; '
      f'first 7 days mean {mean([m for _, m, _ in dm[:7]]):.2f}, last 7 days mean {mean([m for _, m, _ in dm[-7:]]):.2f} °C.\n')

# ================================================================ 4. SELF-HEATING
h('4. Self-heating and recovery')
print(f'Excess = reading minus the strict-anchor baseline (section 2b).\n')
rk = [r['t'] for r in R]
for ep in episodes:
    lo, hi = bisect.bisect_left(rk, ep['start']), bisect.bisect_right(rk, ep['end'])
    ep['rows'] = R[lo:hi]
    ep['dur'] = ep['end'] - ep['start']
    ep['awake'] = sum(w['dur'] for w in wakes if ep['start'] <= w['t0'] <= ep['end'])
    ep['ok'] = (ep['type'] != 'init' and ep['start'] >= EXCL_T and amb(ep['start'], 'board') is not None
                and amb(ep['end'], 'board') is not None)
    for r in ep['rows']:
        r['exc'] = {s: (r[s] - a) if a is not None else None for s in SENS for a in [amb(r['t'], s)]}
use_eps = [e for e in episodes if e['type'] == 'use' and e['ok']]
chg_eps = [e for e in episodes if e['type'] == 'charge' and e['ok']]
print(f"Episodes with anchors on both sides: use {len(use_eps)} of {sum(e['type'] == 'use' for e in episodes)}, "
      f"charge {len(chg_eps)} of {sum(e['type'] == 'charge' for e in episodes)}.\n")

print('### 4a. Seconds scale: heating inside a normal 7 s RTC wake (suspend row minus resume row)\n')
rtcw = [w for w in wakes if w['reasons'] == {'0x00'} and w['dur'] <= 15 and w['slept'] and w['slept'] >= RTC_SLEEP_MIN_S
        and not R[w['k0']]['chg']]
rows_ = [[s, len(rtcw), f(mean([R[w['k1']][s] - R[w['k0']][s] for w in rtcw]), 2, True),
          f(mean([(R[w['k1']][s] - R[w['k0']][s]) / w['dur'] for w in rtcw]) * 60, 1, True)] for s in SENS]
md(['sensor', 'wakes', 'mean rise over the wake °C', '°C per awake minute (initial slope)'], rows_)
print(f'Median RTC wake {med([w["dur"] for w in rtcw]):.1f} s; the cpu rise is undone during the ~293 s sleep '
      f'(resume row is {mean([R[w["k0"]]["cpu"] - R[w["prev_sus"]]["cpu"] for w in rtcw]):+.2f} °C vs the previous suspend row).\n')

print('### 4b. Use episodes: peak excess by awake time (median, max in parentheses, °C)\n')
UBINS = [(0, 2), (2, 10), (10, 30), (30, 90), (90, 1e9)]
rows_ = []
for lo, hi in UBINS:
    sel = [e for e in use_eps if lo * 60 <= e['awake'] < hi * 60]
    if not sel:
        continue
    cur_ = [mean([r['I'] for r in e['rows'] if r['ev'] == 'timer' and r['I'] < 0]) for e in sel
            if any(r['ev'] == 'timer' and r['I'] < 0 for r in e['rows'])]
    row = [f"{lo:g}–{'∞' if hi > 1e8 else f'{hi:g}'} min", len(sel), f(med(cur_), 0) if cur_ else '–']
    for s in SENS:
        pk = [max(v for v in (r['exc'][s] for r in e['rows']) if v is not None) for e in sel]
        row.append(f(med(pk), 1, True) + f' ({f(max(pk), 1, True)})')
    rows_.append(row)
md(['awake time', 'episodes', 'median timer-row current mA', 'cpu', 'batt', 'board', 'accel'], rows_)
pk = [max(v for v in (r['exc']['board'] for r in e['rows']) if v is not None) for e in use_eps]
aw = [e['awake'] / 60 for e in use_eps]
print(f'Board peak excess vs awake minutes, {len(use_eps)} use episodes: r = {corr(aw, pk):+.2f}; '
      f'vs log(awake minutes): r = {corr([math.log(max(a, .1)) for a in aw], pk):+.2f}.')
long_use = [e for e in use_eps if e['awake'] >= 30 * 60]
ss = []
for e in long_use:
    late = [r for r in e['rows'] if r['t'] >= e['start'] + 30 * 60 and r['I'] < 0 and r['ev'] == 'timer'
            and r['exc']['board'] is not None]
    if late:
        ss.append((mean([-r['I'] for r in late]), {s: mean([r['exc'][s] for r in late if r['exc'][s] is not None])
                                                   for s in SENS}))
if ss:
    print(f'Use >= 30 min awake, timer rows after the first 30 min ({len(ss)} episodes): median discharge '
          f'{med([a for a, b in ss]):.0f} mA; excess ' + ', '.join(f"{s} {med([b[s] for a, b in ss]):+.1f}" for s in SENS)
          + f' °C; board ≈ {med([b["board"] / a * 1000 for a, b in ss]):.1f} °C per A of discharge; '
          f'r(current, board excess) = {corr([a for a, b in ss], [b["board"] for a, b in ss]):+.2f}.\n')

print('### 4c. Charging episodes: excess by phase (median over episodes; p10…p90; °C)\n')
phase_rows = collections.defaultdict(lambda: collections.defaultdict(list))
knees, fast_pairs = [], []
P_FAST, P_TAPER, P_FULL = 'fast: last 3 CC rows', 'taper: mean over phase', 'full on charger, RTC cycling: last 3 wakes'
for e in chg_eps:
    fr = [r for r in e['rows'] if r['I'] >= FAST_MA]
    tr = [r for r in e['rows'] if 0 < r['I'] < FAST_MA and (not fr or r['t'] > fr[-1]['t'])]
    mr = [r for r in e['rows'] if r['chg'] and r['I'] <= 0 and r['ev'] == 'resume' and r['wr'] == '0x00'
          and r['wake'] and r['wake']['slept'] and r['wake']['slept'] >= RTC_SLEEP_MIN_S]
    for name, sel, last in ((P_FAST, fr, True), (P_TAPER, tr, False), (P_FULL, mr, True)):
        if len(sel) < (6 if name == P_FULL else 3):
            continue
        use_rows = sel[-3:] if last else sel
        for s in SENS:
            v = [r['exc'][s] for r in use_rows if r['exc'][s] is not None]
            if v:
                phase_rows[name][s].append(mean(v))
        phase_rows[name]['I'].append(mean([r['I'] for r in sel]))
        phase_rows[name]['soc0'].append(sel[0]['cap'])
        phase_rows[name]['soc'].append(sel[-1]['cap'])
        phase_rows[name]['min'].append((sel[-1]['t'] - sel[0]['t']) / 60)
    if len(fr) >= 3:
        b_ = [r['exc']['board'] for r in fr[-3:] if r['exc']['board'] is not None]
        if b_:
            fast_pairs.append((mean([r['I'] for r in fr]), mean(b_), (fr[-1]['t'] - fr[0]['t']) / 60))
        if tr:
            knees.append(tr[0]['cap'])
rows_ = []
for ph in (P_FAST, P_TAPER, P_FULL):
    d_ = phase_rows[ph]
    rows_.append([ph, len(d_['I']), f(med(d_['I']), 0), f"{med(d_['soc0']):.0f}→{med(d_['soc']):.0f}", f(med(d_['min']), 0)]
                 + [f(med(d_[s]), 1, True) + f' ({f(q(d_[s], .1), 1, True)}…{f(q(d_[s], .9), 1, True)})'
                    for s in SENS])
md(['phase', 'episodes', 'median current mA', 'median SOC % start→end', 'median minutes', 'cpu', 'batt', 'board',
    'accel'], rows_)
print(f'CC→CV knee (SOC at the first sub-{FAST_MA} mA row after the CC plateau): median {med(knees):.0f} %, '
      f'range {min(knees)}–{max(knees)} % ({len(knees)} episodes).')
xs, ys = [a for a, b, c in fast_pairs], [b for a, b, c in fast_pairs]
print(f'Board excess at end of CC vs mean CC current: r = {corr(xs, ys):+.2f} ({len(fast_pairs)} episodes; '
      f'current {min(xs):.0f}–{max(xs):.0f} mA; excess {min(ys):+.1f}…{max(ys):+.1f} °C); vs CC duration '
      f'r = {corr([c for a, b, c in fast_pairs], ys):+.2f}. Charging always runs awake, so charger heat and '
      'CPU/display heat are not separable.')
ch = [r for e in chg_eps for r in e['rows'] if r['ev'] == 'timer' and r['I'] > 0 and r['exc']['board'] is not None]
xs, ys = [r['I'] for r in ch], [r['exc']['board'] for r in ch]
b = lstsq([[1.0, x / 1000] for x in xs], ys)
resid = [y - (b[0] + b[1] * x / 1000) for x, y in zip(xs, ys)]
print(f'All {len(ch)} charging timer rows: board excess median {med(ys):+.1f} °C (p5/p95 {q(ys, .05):+.1f}/{q(ys, .95):+.1f}); '
      f'linear fit excess = {b[0]:+.2f} {b[1]:+.2f}·I[A], residual sd {sd(resid):.2f} vs raw sd {sd(ys):.2f} °C '
      '— a current term cannot rescue readings taken while charging.\n')
full_ex = collections.defaultdict(list)
for e in chg_eps:
    last_pos = None
    for r in e['rows']:
        if r['I'] > 0:
            last_pos = r['t']
        elif (r['chg'] and r['ev'] == 'resume' and r['wr'] == '0x00' and last_pos is not None and r['wake']
              and r['wake']['slept'] and r['wake']['slept'] >= RTC_SLEEP_MIN_S and r['exc']['board'] is not None):
            m = (r['t'] - last_pos) / 60
            k_ = next(x for x in ((0, 30), (30, 60), (60, 120), (120, 1e9)) if x[0] <= m < x[1])
            full_ex[k_].append(r['exc']['board'])
print('Full-on-charger RTC cycling, board excess by minutes since charge current last > 0: '
      + '; '.join(f"{lo}–{'' if hi > 1e8 else hi} min: median {med(v):+.2f}, p95 {q(v, .95):+.2f} °C (n {len(v)})"
                  for (lo, hi), v in sorted(full_ex.items())) + '.\n')

print('### 4d. Heating lag: minutes from episode start to 63 % of peak excess / to peak (5-min cadence)\n')
rows_ = []
for name, eps in (('charge', chg_eps), ('use >= 30 min awake', long_use)):
    lag = collections.defaultdict(list)
    peak_t = collections.defaultdict(list)
    for e in eps:
        for s in SENS:
            pts = [(r['t'], r['exc'][s]) for r in e['rows'] if r['exc'][s] is not None]
            if not pts:
                continue
            pk_ = max(v for _, v in pts)
            if pk_ < 1.0:
                continue
            lag[s].append((next(t for t, v in pts if v >= 0.63 * pk_) - e['start']) / 60)
            peak_t[s].append((next(t for t, v in pts if v == pk_) - e['start']) / 60)
    rows_.append([name, len(eps)] + [f(med(lag[s]), 0) + ' / ' + f(med(peak_t[s]), 0) if lag[s] else '–'
                                     for s in SENS])
md(['episode type', 'n', 'cpu', 'batt', 'board', 'accel'], rows_)

print('### 4e. Cooldown after each episode (single exponential T = c + A·exp(−t/τ) on RTC resume samples)\n')
cool = collections.defaultdict(lambda: collections.defaultdict(list))
cool_fits = []
for k, e in enumerate(episodes):
    if e['type'] == 'init' or e['start'] < EXCL_T:
        continue
    nxt = episodes[k + 1]['start'] if k + 1 < len(episodes) else T_END
    stop = min(nxt, e['end'] + COOL_MAX_S)
    if stop - e['end'] < COOL_MIN_S:
        continue
    pts = [r for r in cands if e['end'] < r['t'] <= stop]
    if len(pts) < 36:
        continue
    tm = [(r['t'] - e['end']) / 60 for r in pts]
    for s in SENS:
        fit = expfit(tm, [r[s] for r in pts])
        if s == 'board' and not fit['edge']:
            cool_fits.append(dict(ep=e, fit=fit, pts=pts))
        c_ = cool[(e['type'], s)]
        c_['all'].append(1)
        if not fit['edge']:
            ex = [r[s] - fit['c'] for r in pts]
            rm = [med(ex[max(0, j - 1):j + 2]) for j in range(len(ex))]
            for thr in (0.5, 0.3):
                tw = next((tm[j] for j in range(len(rm)) if all(v <= thr for v in rm[j:])), tm[-1])
                c_[f'within{thr}'].append(tw)
        if fit['A'] >= 0.5 and not fit['edge']:
            c_['tau'].append(fit['tau'])
            c_['A'].append(fit['A'])
            c_['rmse'].append(fit['rmse'])
            c_['t05'].append(fit['tau'] * math.log(fit['A'] / 0.5))
            ex = [r[s] - fit['c'] for r in pts]
            # empirical: first sample after which a 3-sample running median stays within 0.5 of the fitted floor
            rm = [med(ex[max(0, j - 1):j + 2]) for j in range(len(ex))]
            t05e = next((tm[j] for j in range(len(rm)) if all(v <= 0.5 for v in rm[j:])), None)
            if t05e is not None:
                c_['t05e'].append(t05e)
rows_ = []
for typ in ('use', 'charge'):
    for s in SENS:
        c_ = cool[(typ, s)]
        if not c_['tau']:
            continue
        rows_.append([typ, s, f"{len(c_['tau'])} of {len(c_['all'])}", f(med(c_['A']), 1),
                      f(med(c_['tau']), 0) + f" ({f(q(c_['tau'], .25), 0)}–{f(q(c_['tau'], .75), 0)})",
                      f(med(c_['t05']), 0), f(med(c_['t05e']), 0) if c_['t05e'] else '–', f(med(c_['rmse']), 2)])
md(['after', 'sensor', 'fits kept (A >= 0.5 °C, τ inside grid)', 'median A °C', 'τ min, median (IQR)',
    'fitted time to < 0.5 °C, min', 'empirical time to < 0.5 °C (3-pt median), min', 'fit RMSE °C'], rows_)
TAU_BOARD = med(cool[('use', 'board')]['tau'] + cool[('charge', 'board')]['tau'])
print('Time until a 3-sample running median stays within X °C of the episode\'s own fitted floor c '
      '(all fits with τ inside the grid, including small-A episodes; minutes after the episode ends; p50 / p75 / p90):\n')
rows_ = []
for typ in ('use', 'charge'):
    for s in SENS:
        c_ = cool[(typ, s)]
        rows_.append([typ, s, len(c_['within0.5'])]
                     + [' / '.join(f(q(c_[f'within{thr}'], p_), 0) for p_ in (.5, .75, .9)) for thr in (0.5, 0.3)])
md(['after', 'sensor', 'fits', 'within 0.5 °C', 'within 0.3 °C'], rows_)
W05 = {typ: q(cool[(typ, 'board')]['within0.5'], .9) for typ in ('use', 'charge')}
SLOW_TAU = 60
slow = [cf for cf in cool_fits if cf['fit']['tau'] > SLOW_TAU]
aft = lambda cf: 12 <= loc(cf['ep']['end']).hour <= 17
print(f'Board fits (τ inside grid): {len(cool_fits)}; slow (τ > {SLOW_TAU} min): {len(slow)}, of which '
      f'{sum(aft(cf) for cf in slow)} end 12–17 h local; fast windows ending 12–17 h: '
      f'{sum(aft(cf) for cf in cool_fits if cf not in slow)} of {len(cool_fits) - len(slow)}. '
      f'Fits with A < 0 (device colder than its later floor, i.e. ambient rose during the window): '
      f'{sum(cf["fit"]["A"] < 0 for cf in cool_fits)}.')
fast_fits = [cf for cf in cool_fits if cf['fit']['tau'] <= SLOW_TAU and cf['fit']['A'] > 0]
print('Fast windows only (τ <= 60 min, A > 0), board: '
      f"n {len(fast_fits)}, τ median {med([cf['fit']['tau'] for cf in fast_fits]):.0f} min "
      f"(IQR {q([cf['fit']['tau'] for cf in fast_fits], .25):.0f}–{q([cf['fit']['tau'] for cf in fast_fits], .75):.0f}), "
      f"A median {med([cf['fit']['A'] for cf in fast_fits]):.1f} °C (max {max(cf['fit']['A'] for cf in fast_fits):.1f}).\n")
print(f'Cooldown windows need >= {COOL_MIN_S // 3600} h without activity; τ grid {TAU_GRID[0]:.0f}–{TAU_GRID[-1]:.0f} min. '
      f'Pooled board τ = {TAU_BOARD:.0f} min.\n')

# ================================================================ 5. ESTIMATOR
h('5. Estimator evaluation (train before hold-out; test = last 14 days)')
train = [r for r in settled if not r['test']]
test = [r for r in settled if r['test']]
OFF = {s: mean([r[s] - r['med4'] for r in train]) for s in SENS}
OFFB = {s: mean([r[s] - r['board'] for r in train]) for s in SENS}
print('Training offsets vs median of four: ' + ', '.join(f'{s} {OFF[s]:+.2f}' for s in SENS) + ' °C. '
      'Training offsets vs board: ' + ', '.join(f'{s} {OFFB[s]:+.2f}' for s in SENS if s != 'board') + ' °C.\n')
print('### 5a. Settled hold-out: corrected sensor vs leave-one-out consensus (median of the other three, corrected)\n')
rows_ = []
for s in SENS:
    errs, tr_errs = [], []
    for data, out in ((test, errs), (train, tr_errs)):
        for r in data:
            others = sorted(r[x] - OFF[x] for x in SENS if x != s)
            out.append((r[s] - OFF[s]) - others[1])
    rows_.append([s] + abs_stats(errs) + [f(sd(tr_errs), 2)])
md(['estimator', 'n', 'mean err', 'sd', 'median |err|', 'p95 |err|', 'max |err|', 'train sd'], rows_)
bb = [(r['board'] - r['batt']) - (OFFB['board'] - OFFB['batt']) for r in test]
print('NTC pair on hold-out, (board − batt) minus training offset: '
      + ' | '.join(str(x) for x in abs_stats(bb)) + ' (n | mean | sd | median |err| | p95 |err| | max).')
print('Offset drift, hold-out mean minus training mean (vs median of four): '
      + ', '.join(f"{s} {mean([r[s] - r['med4'] for r in test]) - OFF[s]:+.2f}" for s in SENS) + ' °C.\n')

print('### 5b. Settling-phase corrections for the board estimator (target = strict-anchor baseline)\n')
NS = []
for r in cands:
    if not r['base_ok'] or r['tsa'] >= ANCHOR_N_H * 3600:
        continue
    ex = {s: (r[s] - a) if a is not None else None for s in SENS for a in [amb(r['t'], s)]}
    if any(v is None for v in ex.values()):
        continue
    r['ex'] = ex
    r['ns_test'] = r['t'] >= T_SPLIT
    r['dcb'] = (r['cpu'] - r['board']) - OFFB['cpu']
    r['dbb'] = (r['batt'] - r['board']) - OFFB['batt']
    r['dab'] = (r['accel'] - r['board']) - OFFB['accel']
    NS.append(r)
ns_tr = [r for r in NS if not r['ns_test']]
ns_te = [r for r in NS if r['ns_test']]
te_eps = collections.Counter(r['eptype'] for r in {id(last_episode(r['t'])): r for r in ns_te}.values())
print(f'RTC samples within {ANCHOR_N_H:g} h of activity with anchors: train {len(ns_tr)}, test {len(ns_te)} '
      f'(test episodes: {dict(te_eps)}).\n')
TB = [0, 15, 30, 45, 60, 90, 120, 180, 240]


def tbin(r):
    m = r['tsa'] / 60
    for lo, hi in zip(TB[:-1], TB[1:]):
        if lo <= m < hi:
            return (lo, hi)
    return (TB[-1], None)


tab = collections.defaultdict(list)
for r in ns_tr:
    tab[(tbin(r), r['eptype'])].append(r['ex']['board'])
tabmed = {k: med(v) for k, v in tab.items()}
models = collections.OrderedDict()
models['M0 raw board'] = lambda r: r['ex']['board']
models['M1 minus median excess by (time since activity, episode type)'] = \
    lambda r: r['ex']['board'] - tabmed.get((tbin(r), r['eptype']), 0.0)
FEATS = collections.OrderedDict([
    ('M2a cpu−board delta', ('dcb',)),
    ('M2b batt−board delta', ('dbb',)),
    ('M2c accel−board delta', ('dab',)),
    ('M2d all three deltas', ('dcb', 'dbb', 'dab')),
    ('M2e three deltas + current at resume', ('dcb', 'dbb', 'dab', 'I')),
])
coef = {}
for name, fe in FEATS.items():
    b = lstsq([[1.0] + [r[x] for x in fe] for r in ns_tr], [r['ex']['board'] for r in ns_tr])
    coef[name] = b
    models[name] = (lambda b_, fe_: lambda r: r['ex']['board'] - (b_[0] + sum(c * r[x] for c, x in zip(b_[1:], fe_))))(b, fe)
cand_t = [r['t'] for r in cands]


def m3_factory(base_min):
    def m3(r):
        j = bisect.bisect_left(cand_t, r['t'] - base_min * 60 - 150)
        p = cands[j] if j < len(cands) else None
        if p is None or p['t'] >= r['t'] or abs((r['t'] - p['t']) - base_min * 60) > 150:
            return None
        if abs((r['tsa'] - p['tsa']) - (r['t'] - p['t'])) > 1:  # activity in between
            return None
        rr = math.exp(-(r['t'] - p['t']) / 60 / TAU_BOARD)
        return (r['board'] - rr * p['board']) / (1 - rr) - amb(r['t'], 'board')
    return m3


models[f'M3a exponential extrapolation, 10-min baseline (τ {TAU_BOARD:.0f} min)'] = m3_factory(10)
models[f'M3b exponential extrapolation, 30-min baseline (τ {TAU_BOARD:.0f} min)'] = m3_factory(30)
settled_t = [r['t'] for r in settled]


def m4(r):
    """Hold the last settled board value seen before this sample."""
    j = bisect.bisect_left(settled_t, r['t']) - 1
    if j < 0 or r['t'] - settled[j]['t'] > ANCHOR_MAX_S:
        return None
    return settled[j]['board'] - amb(r['t'], 'board')


models['M4 hold last settled value (optimistic: shares anchors with the target)'] = m4
print('Coefficients (training least squares, excess = b0 + Σ bi·feature): ' + '; '.join(
    f"{k.split()[0]} " + ', '.join(f'{v:+.3f}' for v in b) for k, b in coef.items()) + '\n')
rows_ = []
for name, fn in models.items():
    for part, data in (('train', ns_tr), ('test', ns_te)):
        errs = [e for e in (fn(r) for r in data) if e is not None]
        rows_.append([name, part] + abs_stats(errs))
md(['model', 'set', 'n', 'mean err', 'sd', 'median |err|', 'p95 |err|', 'max |err|'], rows_)
print('Target noise floor: the same interpolation applied to deeply settled samples (tsa >= 8 h, every 5th), with '
      'anchors within ±M h masked so the span matches post-activity samples:\n')
deep_a = [r for r in anchors if r['tsa'] >= 8 * 3600]
rows_ = []
for M in (2, 3, 4):
    exn = []
    for r in deep_a[::5]:
        jb = bisect.bisect_left(anchor_t, r['t'] - M * 3600) - 1
        ja = bisect.bisect_right(anchor_t, r['t'] + M * 3600)
        if jb < 2 or ja + 3 > len(anchors):
            continue
        before, after = anchors[jb - 2:jb + 1], anchors[ja:ja + 3]
        tb, ta = before[-1]['t'], after[0]['t']
        if r['t'] - tb > ANCHOR_MAX_S or ta - r['t'] > ANCHOR_MAX_S:
            continue
        vb, va = med([x['board'] for x in before]), med([x['board'] for x in after])
        exn.append(r['board'] - (vb + (va - vb) * (r['t'] - tb) / (ta - tb)))
    rows_.append([f'±{M} h'] + abs_stats(exn) + [f(q(exn, .1), 2, True), f(q(exn, .9), 2, True)])
md(['mask', 'n', 'mean', 'sd', 'median |e|', 'p95 |e|', 'max |e|', 'p10', 'p90'], rows_)
print('Post-activity excess percentiles (board, all candidates; compare with the null above):\n')
rows_ = []
for lo, hi in ((0, .5), (.5, 1), (1, 1.5), (1.5, 2), (2, 3), (3, 4)):
    ex_ = [r['board'] - a for r in cands if r['base_ok'] and lo * 3600 <= r['tsa'] < hi * 3600
           for a in [amb(r['t'], 'board')] if a is not None]
    rows_.append([f'{hfmt(lo)}–{hfmt(hi)}', len(ex_), f(q(ex_, .1), 2, True), f(med(ex_), 2, True), f(q(ex_, .9), 2, True)])
md(['time since activity', 'n', 'p10', 'p50', 'p90'], rows_)

print('### 5c. Error by time since activity, test set (median |err| / p95 |err|, °C)\n')
show = ['M0 raw board', 'M1 minus median excess by (time since activity, episode type)', 'M2b batt−board delta',
        'M2d all three deltas', [k for k in models if k.startswith('M3a')][0],
        'M4 hold last settled value (optimistic: shares anchors with the target)']
rows_ = []
for lo, hi in zip(TB[:-1], TB[1:]):
    for typ in ('use', 'charge'):
        sel = [r for r in ns_te if tbin(r) == (lo, hi) and r['eptype'] == typ]
        if not sel:
            continue
        row = [f'{lo}–{hi}', typ, len(sel)]
        for name in show:
            errs = [abs(e) for e in (models[name](r) for r in sel) if e is not None]
            row.append(f(med(errs), 2) + ' / ' + f(q(errs, .95), 2) if errs else '–')
        rows_.append(row)
md(['min since activity', 'after', 'n', 'M0 raw', 'M1 time table', 'M2b batt−board', 'M2d deltas', 'M3a extrap.',
    'M4 hold'], rows_)

print('### 5d. Runtime gates for the "settling" flag (target = each cooldown\'s own fitted floor c)\n')
print('Samples: RTC candidates in the first 2 h of every cooldown window with a board fit (section 4e). Within 2 h, '
      'ambient drift is small, so |board − c| is mostly residual self-heating. "Missed" = unflagged samples with '
      '|board − c| > 0.5 °C. False flags = share of settled test samples (tsa >= N) the gate would still flag.\n')
settled_test = [r for r in settled if r['test']]


def prev_board(r, minutes):
    j = bisect.bisect_left(cand_t, r['t'] - minutes * 60 - 150)
    p = cands[j] if j < len(cands) else None
    if p is None or p['t'] >= r['t'] or abs((r['t'] - p['t']) - minutes * 60) > 150:
        return None
    if abs((r['tsa'] - p['tsa']) - (r['t'] - p['t'])) > 1:
        return None
    return p['board']


def slope_flag(r, delta=0.10, minutes=15):
    pb = prev_board(r, minutes)
    return pb is None or pb - r['board'] > delta


def delta_flag(r, tol=0.30):
    return abs((r['batt'] - r['board']) - OFFB['batt']) > tol


def adaptive_flag(r, thr=0.3):
    """Flag while tsa < τ·ln(A/thr), A = first post-activity board minus last settled board before it."""
    j = bisect.bisect_left(settled_t, r['t']) - 1
    if j < 0:
        return r['tsa'] < 2700
    t_end = r['t'] - r['tsa']
    k = bisect.bisect_right(cand_t, t_end)
    if k >= len(cands):
        return True
    A = cands[k]['board'] - settled[j]['board']
    if A <= thr:
        return False
    wait = TAU_BOARD * 60 * math.log(A / thr) + (cands[k]['t'] - t_end)
    return r['tsa'] < wait


gate_samples, slow_samples = [], []
for cf in cool_fits:
    for r in cf['pts']:
        if r['tsa'] <= 7200 and abs(r['tsa'] - (r['t'] - cf['ep']['end'])) < 1:
            (gate_samples if cf in fast_fits else slow_samples).append((r, r['board'] - cf['fit']['c'], cf['ep']['type']))
print(f'Fast windows (τ <= {SLOW_TAU} min, A > 0) only — the self-heating case. Slow/negative windows are reported after the table.\n')
GATES = collections.OrderedDict()
for X in (0, 30, 45, 60, 75, 90):
    GATES[f'T{X}: flag tsa < {X} min'] = (lambda X_: lambda r: r['tsa'] < X_ * 60)(X)
GATES['S: flag while board fell > 0.10 °C over 15 min'] = slope_flag
GATES['S30: flag while board fell > 0.15 °C over 30 min'] = lambda r: slope_flag(r, 0.15, 30)
GATES['T30 + S'] = lambda r: r['tsa'] < 1800 or slope_flag(r)
GATES['T45 + S'] = lambda r: r['tsa'] < 2700 or slope_flag(r)
GATES['A: adaptive wait τ·ln(A/0.3)'] = adaptive_flag
GATES['T30 + A'] = lambda r: r['tsa'] < 1800 or adaptive_flag(r)
rows_ = []
gate_res = {}
for name, g in GATES.items():
    fp = mean([1 if g(r) else 0 for r in settled_test])
    for typ in ('use', 'charge', None):
        sel = [(r, e) for r, e, t_ in gate_samples if typ is None or t_ == typ]
        un = [abs(e) for r, e in sel if not g(r)]
        gate_res[(name, typ)] = (len(un) / len(sel), un, fp)
        if typ is None:
            continue
        rows_.append([name, typ, len(sel), f'{100 * len(un) / len(sel):.0f} %', f(med(un), 2) if un else '–',
                      f(q(un, .9), 2) if un else '–', f(q(un, .95), 2) if un else '–',
                      f'{100 * mean([1 if e > 0.5 else 0 for e in un]):.1f} %' if un else '–', f'{100 * fp:.1f} %'])
md(['gate', 'after', 'n', 'unflagged', 'median |err|', 'p90', 'p95', 'missed > 0.5 °C', 'false flags (settled)'], rows_)
print(f'Gate samples: {len(gate_samples)} from {len(fast_fits)} fast cooldown windows '
      f'({sum(r["t"] >= T_SPLIT for r, e, t_ in gate_samples)} in the hold-out period).')
for X in (45, 60, 90):
    un = [abs(e) for r, e, t_ in slow_samples if r['tsa'] >= X * 60]
    print(f'- Slow/negative windows ({len(cool_fits) - len(fast_fits)}), T{X}: unflagged median |err| {med(un):.2f}, '
          f'p95 {q(un, .95):.2f}, missed > 0.5 °C {100 * mean([1 if e > 0.5 else 0 for e in un]):.0f} % '
          '(environment-driven; no time gate fixes these).')
print()
dflag = [r for r in settled_test if delta_flag(r)]
print(f'Delta gate D (|batt−board − offset| > 0.30 °C): flags {100 * len(dflag) / len(settled_test):.1f} % of settled '
      f'test samples; flags {sum(delta_flag(r) for run in runs for r in run)} of {sum(len(x) for x in runs)} samples in the '
      'warm settled stretches (section 3).\n')

print('### 5e. Recommended estimator, end to end\n')
GATE_NAME = 'T60: flag tsa < 60 min'
GATE_REC = GATES[GATE_NAME]
errs_settled = []
for r in test:
    others = sorted(r[x] - OFF[x] for x in SENS if x != 'board')
    errs_settled.append((r['board'] - OFF['board']) - others[1])
print(f'Estimator: board − {OFF["board"]:.2f} °C. Flag while charger online or I > 0; then gate "{GATE_NAME}".')
print(f'- Settled hold-out vs leave-one-out consensus: ' + ' | '.join(str(x) for x in abs_stats(errs_settled))
      + ' (n | mean | sd | median |err| | p95 |err| | max).')
cov_, un_, fp_ = gate_res[(GATE_NAME, None)]
print(f'- Gate on cooldown samples (first 2 h, all periods): unflagged {100 * cov_:.0f} %, median |err| {med(un_):.2f}, '
      f'p95 {q(un_, .95):.2f}, missed > 0.5 °C {100 * mean([1 if e > 0.5 else 0 for e in un_]):.1f} %; '
      f'false flags on settled test samples {100 * fp_:.1f} %.')
te_g = [(r, e) for r, e, t_ in gate_samples if r['t'] >= T_SPLIT]
un_te = [abs(e) for r, e in te_g if not GATE_REC(r)]
print(f'- Same, hold-out period only: {len(te_g)} samples, unflagged {100 * len(un_te) / max(1, len(te_g)):.0f} %, '
      f'median |err| {f(med(un_te), 2)}, p95 {f(q(un_te, .95), 2)}, max {f(max(un_te) if un_te else float("nan"), 2)}.')
flag = [r for r in R if r['ev'] == 'resume' and r['t'] >= T_SPLIT and r['wr'] == '0x00' and r['wake']
        and r['wake']['slept'] and r['wake']['slept'] >= RTC_SLEEP_MIN_S]
cset = {id(r) for r in cands}
shown = [r for r in flag if id(r) in cset and not GATE_REC(r)]
print(f'- Coverage in the hold-out: {len(shown)} of {len(flag)} RTC wakes ({100 * len(shown) / len(flag):.0f} %) '
      'would show an unflagged reading.\n')

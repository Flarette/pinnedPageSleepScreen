# Ambient-temperature widget: 7-week sensor log analysis (Aug 29 – Oct 17)

Analyzed 2026-10-18 by an Opus subagent from `tempdata/raw/templog.csv`. The file
has 41,831 data rows, from 2026-08-29T10:10Z to 2026-10-17T20:45Z (49.4 days),
recorded by `tools/templog/templog.sh` on the rMPP Move (i.MX93). The recorder was
stopped and uninstalled from the device after the pull on 2026-10-17. The analysis
script is `tempdata/analyze_temps.py`. It uses only the standard library and prints
every number in this report. Run it with `python3 -I tempdata/analyze_temps.py`.

Times are local EEST (UTC+3), which applies to the whole log. "Settled" and
"activity" are defined in [Definitions](#definitions). Every error figure in this
report measures **agreement between sensors, not absolute accuracy**. The log
contains no room-thermometer reading.

Owner context: ambient was "within 22–26 °C" by recollection. The device was not
moved between environments during the log. Temperature changes came from gradual
ambient drift and the device's own self-heating. Sharp environment changes can be
measured deliberately later.

## HEADLINE

**Display the board NTC (`board_mC`, hwmon4 `temp-sense1`) minus 0.20 °C, read on
the RTC-wake `resume` sample. Apply no other correction term. Flag the reading as
"settling" while charging and for 60 min after any activity.**

| Question | Answer |
|---|---|
| Which sensor | **Board NTC.** It has the finest step (0.026 °C) and the lowest read noise (0.018 °C). It agrees best with the other three sensors at rest. |
| Expected error, settled, held-out last 14 days | Against the leave-one-out consensus of the other three sensors (n = 3,413): mean +0.01, sd 0.14, median 0.08, p95 **0.29**, max 0.71 °C. |
| Offset | −0.20 °C. This puts the board on the midpoint of the two NTCs, which is what the median of four reduces to in 99.8 % of settled samples. It held to within 0.09 °C week to week, and drifted +0.02 °C from training to hold-out. |
| Read timing | Sample within 1–2 s of resume. The offset is calibrated on resume rows, and board rises about 0.02 °C/s while awake (+0.15 °C over a 7 s wake). |
| Correction terms | **None earns its place.** Current, CPU−board, accel−board, batt−board, a time-since-activity table and exponential extrapolation do not beat raw board on held-out data by more than the noise of the evaluation target (section 5). |
| Suppress while | Charging (`charger_online=1` and current > 0): board reads **+7.2 °C** (median; p95 +10.9). |
| Suppress after | 60 min after any activity or unplug. In self-heating cooldowns this leaves a median of 0.16 °C, a p95 of 0.62 °C, and 8 % of samples above 0.5 °C. On the charger at 100 %, wait until 2 h after the charge current last went positive. |
| Coverage | 91 % of RTC wakes in the hold-out would show an unflagged reading. |
| Not usable | **CPU TMU** reads +4.3 °C high in 0.5 °C steps and gains +3.4 °C during each 7 s wake. **Accelerometer** reads −1.4 °C low with 0.19 °C read noise. |
| Owner's 22–26 °C recollection | The NTCs agree with it. Settled board p5–p95 is 23.1–25.9 °C, with 95 % of samples inside 22–26. Battery is 22.8–25.3 °C (99 % inside). Ambient was **steady, not cooling** into October: weekly medians were 23.6–24.8 °C, and the diurnal swing was 0.6 °C. |
| Data quality | Clean. There was no reboot, no hibernation and no stale read. |

Four premises in the brief do not hold:
- The device **never hibernated**. The longest sleep is 306 s.
- Ambient did **not** drift down over the 7 weeks.
- The CC→CV knee is at **88 % SOC**, not about 70 %.
- `wakeup_reason` alone **misses activity**. Twelve wakes that read 0x00 lasted more than 45 s, two of them charging sessions.

---

## 1. Data quality

| Check | Result |
|---|---|
| Reboot (would renumber hwmon4) | **None.** Uptime never drops by more than 1 s. Boot epoch (`epoch − uptime`) stays at 2026-08-11 16:54:48 UTC within ±0.5 s for all 49 days. The board column is valid throughout. |
| Uptime inversions | 1,193, max 0.04 s. These are `flock` write races: uptime is read before the lock. Rows are sorted by uptime. |
| `epoch` column | One row is 301 s off (2026-08-29T16:15:11Z). The script was suspended between `date +%s` and the sensor reads. **Use uptime as the time base**, not `epoch`. |
| Hibernation | **None.** The longest single sleep is 306 s. Timer rows number 274–289 per full day (288 = every 5 min). |
| Cadence gaps > 6 min | 9 gaps, 130 min in total, the longest 30 min. All fall before Sep 12 (table below). They are missed ticks, not hibernation, so there is no long-gap "well-settled" sample to exploit. |
| Row pairing | 13,767 wakes (resume → suspend) and 1 duplicate suspend. 1,370 timer rows were sampled < 2 s *before* their own resume row and are attached to that wake. |
| `wakeup_reason` | 0x00 on 40,924 rows, 0x20 on 358, 0x10 on 333, 0x04 on 206 and **0x08 on 10** (undocumented; treated as activity). 12 wakes reading 0x00 lasted > 45 s, including two charging sessions of 8,247 s and 5,350 s. |
| Wakes at 37 s | 262 RTC wakes last 30–45 s instead of 7 s. 257 of them are on the charger at 100 % (`charger_online=1`) and are excluded as charging. |

Gaps, with the temperature step across each:

| Last row | Next row | Gap, min | Δboard | Δbatt | Δcpu | Δaccel |
|---|---|---|---|---|---|---|
| Aug 29 19:05 | Aug 29 19:15 | 10.0 | −1.31 | −1.10 | −2.00 | −1.38 |
| Aug 29 19:45 | Aug 29 19:53 | 8.5 | +1.43 | +0.30 | +4.50 | +2.56 |
| Sep 01 04:20 | Sep 01 04:30 | 10.0 | −0.10 | −0.30 | −0.50 | +0.12 |
| Sep 01 06:10 | Sep 01 06:30 | 20.0 | −0.02 | −0.10 | −1.00 | +0.25 |
| Sep 01 14:20 | Sep 01 14:30 | 10.0 | −0.07 | +0.00 | +1.00 | +0.00 |
| Sep 01 18:55 | Sep 01 19:25 | 30.0 | +1.73 | +0.30 | +5.50 | +2.00 |
| Sep 01 20:10 | Sep 01 20:30 | 20.0 | −1.00 | −0.90 | −1.50 | −0.81 |
| Sep 02 08:50 | Sep 02 09:04 | 14.8 | +0.46 | −0.30 | +2.50 | +0.81 |
| Sep 11 13:00 | Sep 11 13:06 | 6.2 | −0.27 | +0.40 | −6.50 | −0.31 |

Several gaps straddle use, so a sample taken after a gap is not settled. No analysis
fits across a gap.

### Stale-read verdict: no stale reads; use the `resume` row

Resume rows are compared with the previous suspend row, after a sleep of at least
240 s (n = 13,048). For reference, the table also shows two pairs of reads known to
be fresh: consecutive suspend rows 300 s apart, and timer rows taken within 2 s of
the resume row.

| Sensor | resume == prev suspend | Mean Δ resume−suspend | Fresh: suspend == suspend 300 s earlier | Fresh: timer == resume, < 2 s apart |
|---|---|---|---|---|
| cpu | **0.0 %** | −3.48 °C | 68.5 % | 53.6 % |
| batt | 48.0 % | −0.07 °C | 65.2 % | 99.6 % |
| board | 0.5 % | −0.20 °C | 22.6 % | 39.8 % |
| accel | **5.6 %** | −0.30 °C | 8.2 % | 9.4 % |

The TMU never repeats its pre-suspend value. It reads 3.5 °C cooler, which is the
cooling during the ~293 s sleep. The accelerometer repeats less often (5.6 %) than
fresh back-to-back reads do (8–9 %). Battery and board repeat at or below their
fresh-read rate for the same elapsed time.

Timer rows in the same wake match the resume row: the mean difference is +0.19 °C
for cpu (the die heats within the first second) and ≤ 0.003 °C for the others.
**Resume rows are fresh, so this analysis uses them as the settled sample.** There
is one per wake, and each is the earliest reading after sleep.

## 2. Settled agreement

### Definitions

- **Activity** is any of the following:
  - a wake longer than 45 s (a normal RTC wake lasts 7.2 s)
  - any wake carrying a non-0x00 reason
  - any sleep shorter than 200 s (autosleep bursts after use)
  - any row with `current_uA > 0` or `charger_online = 1`
  - the install period before the first suspend
- **Candidate**: a 0x00 `resume` row after a sleep of at least 240 s, with the charger offline, current ≤ 0, and the row outside activity. There are 12,646 candidates after excluding Aug 29 (install day: on USB at 100 %, charger-warmed).
- **Settled**: a candidate taken at least **N = 1.5 h** after the end of the last activity. There are 10,215 settled samples: 6,802 train and 3,413 hold-out. The hold-out is the 14 days from Oct 03 23:45.

### Settling curve and choice of N

The spread curve, as inter-sensor deltas (medians, °C):

| Hours since activity | n | cpu−board | batt−board | accel−board | Spread of 4 | Spread without cpu |
|---|---|---|---|---|---|---|
| 0–0.25 | 491 | +4.20 | **−0.60** | −1.52 | 5.73 | 1.52 |
| 0.25–0.5 | 453 | +4.20 | −0.46 | −1.52 | 5.73 | 1.52 |
| 0.5–0.75 | 406 | +4.22 | −0.45 | −1.55 | 5.73 | 1.55 |
| 0.75–1 | 382 | +4.20 | −0.43 | −1.54 | 5.79 | 1.54 |
| 1–1.5 | 699 | +4.17 | −0.42 | −1.56 | 5.73 | 1.56 |
| 2–2.5 | 585 | +4.14 | −0.40 | −1.56 | 5.73 | 1.56 |
| 6–8 | 1,297 | +4.15 | −0.40 | −1.59 | 5.73 | 1.59 |
| ≥ 8 (plateau) | – | +4.11 | −0.40 | −1.59 | – | – |

The deltas reach their plateau, within ±0.1 °C, by **0.75 h**. That is too early to
call the device settled, because all four sensors cool *together*. A spread across
sensors cannot see heat they share. N therefore comes from the common-mode excess:
each reading minus that sensor's own level, interpolated between strict anchors.
Strict anchors are candidates at least 4 h after activity.

| Time since activity | n | Board excess, median / p90 | Batt | Accel | Cpu |
|---|---|---|---|---|---|
| 0–10 min | 258 | +1.42 / +3.57 | +1.22 / +3.00 | +1.49 / +3.63 | +1.50 / +3.49 |
| 10–20 min | 259 | +0.88 / +2.28 | +0.75 / +1.96 | +0.96 / +2.34 | +1.00 / +2.43 |
| 20–30 min | 238 | +0.55 / +1.76 | +0.48 / +1.56 | +0.62 / +2.01 | +0.58 / +1.87 |
| 30–45 min | 333 | +0.34 / +1.43 | +0.33 / +1.22 | +0.37 / +1.68 | +0.50 / +1.63 |
| 45–60 min | 320 | +0.23 / +1.29 | +0.21 / +1.03 | +0.29 / +1.33 | +0.38 / +1.39 |
| 1–1.25 h | 305 | +0.15 / +1.07 | +0.14 / +0.93 | +0.23 / +1.23 | +0.19 / +1.30 |
| 1.25–1.5 h | 283 | +0.09 / +0.97 | +0.08 / +0.84 | +0.16 / +1.19 | +0.19 / +1.38 |
| **1.5–2 h** | 539 | **+0.05** / +0.97 | +0.05 / +0.84 | +0.10 / +1.07 | +0.12 / +1.21 |
| 2–2.5 h | 506 | +0.04 / +0.89 | +0.03 / +0.76 | +0.06 / +1.13 | +0.09 / +1.07 |
| 3–4 h | 811 | +0.01 / +0.29 | +0.01 / +0.25 | +0.05 / +0.50 | +0.00 / +0.50 |

**N = 1.5 h** is the first bin where the median excess is ≤ 0.1 °C for batt, board
and accel and stays there. Anchors at 3 h give the same N; anchors at 6 h give
2.5 h. Use-only and charge-only episodes both give 1.5 h.

The p90 tail of about 1 °C is **not** residual self-heating. Deeply settled samples
put through the same interpolation, with anchors masked ±3 h, have p10/p90 of
−0.68/+0.64 °C (section 5). The post-activity bins from 1 h onward fall inside that
band. The tail is gradual ambient change across the interpolation span.

### Offsets against the median of four (all settled samples)

| Sensor | Mean | sd | p5 | p95 |
|---|---|---|---|---|
| cpu | **+4.30** | 0.33 | +3.68 | +4.75 |
| batt | −0.21 | 0.07 | −0.33 | −0.12 |
| board | +0.21 | 0.07 | +0.12 | +0.33 |
| accel | **−1.38** | 0.26 | −1.82 | −0.97 |

- The spread across all four (max − min) has a p50 of 5.73 °C and a p95 of 6.23 °C. Without cpu, p50 is 1.59 °C and p95 is 1.98 °C.
- The CPU is always highest and the accelerometer always lowest, so the median of four is the NTC mean in 99.8 % of samples.
- The NTC pair (batt − board) has a mean of −0.42, sd 0.14, and p5/p95 of −0.67/−0.23 °C.

### Per-week stability (mean offset against the median of four, °C)

| Week | n | cpu | batt | board | accel | batt−board | Median of four, °C |
|---|---|---|---|---|---|---|---|
| W1 Aug 30–Sep 05 | 1,330 | +4.37 | −0.22 | +0.22 | −1.35 | −0.45 | 24.34 |
| W2 Sep 05–Sep 12 | 1,321 | +4.44 | −0.25 | +0.24 | −1.29 | −0.49 | 24.53 |
| W3 Sep 12–Sep 19 | 1,263 | +4.31 | −0.19 | +0.19 | −1.42 | −0.37 | 23.69 |
| W4 Sep 19–Sep 26 | 1,225 | +4.18 | −0.16 | +0.16 | −1.49 | −0.32 | 23.47 |
| W5 Sep 26–Oct 03 | 1,663 | +4.24 | −0.19 | +0.19 | −1.42 | −0.38 | 23.66 |
| W6 Oct 03–Oct 10 (hold-out) | 1,680 | +4.39 | −0.25 | +0.25 | −1.30 | −0.49 | 24.55 |
| W7 Oct 10–Oct 17 (hold-out) | 1,733 | +4.21 | −0.20 | +0.20 | −1.42 | −0.40 | 23.70 |

| Sensor | Week-to-week range | Offset slope against level | r | Slope, ≥ 6 h settled only |
|---|---|---|---|---|
| cpu | 0.26 °C | +0.19 °C/°C | +0.49 | +0.19 |
| batt | 0.09 °C | −0.075 °C/°C | −0.90 | −0.074 |
| board | 0.09 °C | +0.073 °C/°C | +0.89 | +0.070 |
| accel | 0.19 °C | +0.17 °C/°C | +0.56 | +0.17 |

The offsets do not drift with time. They track the *level*: weeks with a warm
median of four (W2, W6) have the largest offsets.

The two NTCs diverge by about **0.15 °C per °C** of temperature. Regressing
batt−board on level gives −0.142 °C/°C. Adding the 1-h board slope as a
thermal-lag term barely changes it (−0.144 °C/°C, with a slope term of +0.009). In
thermally calm samples, where board moved ≤ 0.05 °C over 1 h (n = 1,216), it is
−0.148 °C/°C. This points to a **gain mismatch**, not lag. Across the observed
23–26 °C band it amounts to about ±0.2 °C.

### Quantization and noise

| Sensor | Quantum | Read noise sd (pairs < 2 s apart) | sd, detrended 5-min triplets | Unchanged after 5 min |
|---|---|---|---|---|
| cpu | 0.500 °C | 0.245 °C | 0.258 °C | 57 % |
| batt | 0.100 °C | 0.005 °C (register updates slowly) | 0.036 °C | 72 % |
| **board** | **0.026 °C** | **0.018 °C** | **0.035 °C** | 25 % |
| accel | 0.063 °C | 0.191 °C (3× its quantum) | 0.208 °C | 8 % |

## 3. Absolute level against the 22–26 °C recollection, and drift

The owner's range is used only as a sanity check; nothing is fitted to it.

| Sensor (settled) | min | p5 | p50 | p95 | max | In 22–26 | Below 22 | Above 26 |
|---|---|---|---|---|---|---|---|---|
| cpu | 24.9 | 26.9 | 28.4 | 30.4 | 37.9 | 1 % | 0 % | 99 % |
| batt | 21.4 | 22.8 | 23.7 | 25.3 | 33.0 | **99 %** | 1 % | 0 % |
| board | 21.2 | 23.1 | 24.1 | 25.9 | 33.8 | **95 %** | 1 % | 4 % |
| accel | 19.2 | 21.2 | 22.5 | 24.5 | 33.0 | 76 % | 24 % | 0 % |
| Median of four | 21.3 | 22.9 | 23.9 | 25.6 | 33.4 | 98 % | 1 % | 1 % |

- **The NTCs fit the recollection.** The CPU is clearly offset, and the accelerometer reads low enough to put a quarter of samples below 22 °C. The minimums seen in the raw log (board 20.9, batt 21.2, accel 18.6 °C) all come from unsettled rows. The settled minimums are 21.2, 21.4 and 19.2 °C.
- **No downward drift.** Weekly settled board medians are 24.58, 24.77, 23.88, 23.63, 23.83, 24.79 and 23.90 °C. Daily medians range 22.6–25.6 °C. The first 7 days average 24.41 °C and the last 7 days 23.99 °C. Ambient changes day to day by about ±1 °C with no seasonal trend, which fits a heated or insulated room.
- **Diurnal profile.** Settled board was measured against its ±12 h mean (each hour n ≈ 320–450). The low is −0.27 °C at 20 h; 19–22 h all sit at −0.21 to −0.27 °C. The high is +0.35 °C at 14 h and +0.31 °C at 15 h. A second dip of −0.22 °C falls at 08–09 h. The peak-to-peak swing is **0.62 °C**.

Three settled stretches had board above 27 °C:

| Start | Minutes | Peak board | Hours since activity | batt−board (plateau −0.40) | accel−board (plateau −1.59) |
|---|---|---|---|---|---|
| Sep 04 18:20 | 15 | 27.1 °C | 1.6 | −1.02 | −1.31 |
| Oct 07 14:25 | 60 | **33.8 °C** | **23.1** | −0.84 | −0.84 |
| Oct 14 15:05 | 10 | 28.0 °C | 20.3 | −1.67 | −2.03 |

The Oct 07 stretch is a clean heat pulse on a sleeping device. From 14:00 to 14:55
local, board rose from 24.4 to 33.8 °C, then fell back to 24.6 °C by 16:10. Every
row in that window is a normal RTC wake on battery: reason 0x00, discharging, charger
offline. Oct 14 has the same shape at a smaller scale. Both came more than 20 h
after any activity, in the afternoon, and the battery lagged the board. The owner
did not move the device, so the likely source is direct sun crossing the device
where it lay. This is unconfirmed. **The widget reports device temperature, which in
sun is not air temperature.**

## 4. Self-heating and recovery

Excess is the reading minus that sensor's strict-anchor baseline. Episodes are
activity blocks merged when less than 20 min apart: 131 use and 24 charge.
Anchors exist on both sides for 102 use and 18 charge episodes.

### Who heats first: inside one 7 s RTC wake (n = 12,749)

| Sensor | Rise over the wake | Initial slope |
|---|---|---|
| cpu | **+3.39 °C** | +28 °C/min |
| accel | +0.24 °C | +2.0 °C/min |
| board | +0.15 °C | +1.2 °C/min |
| batt | +0.04 °C | +0.3 °C/min |

The sleep undoes this rise: the next resume reads 3.44 °C below the suspend row.
Over minutes, all sensors except the battery reach 63 % of their peak in about
10 min. The **battery lags, at 15 min**. The order is cpu, then accel and board,
then battery. Peaks arrive 25–37 min into long episodes. Resolution is 5 min, the
cadence while awake.

### Use (awake, discharging): peak excess by awake time (median, max in parentheses, °C)

| Awake time | Episodes | Median current | cpu | batt | board | accel |
|---|---|---|---|---|---|---|
| 0–2 min | 16 | 339 mA | +5.5 (+7.0) | +0.9 (+1.6) | +2.2 (+2.7) | +2.3 (+3.6) |
| 2–10 min | 45 | 274 mA | +7.0 (+12.5) | +1.6 (+6.6) | +3.0 (+8.8) | +3.7 (+8.8) |
| 10–30 min | 32 | 315 mA | +12.0 (+18.6) | +4.4 (+8.6) | +7.0 (+11.8) | +8.1 (+14.5) |
| 30–90 min | 9 | 388 mA | +18.0 (+19.6) | +8.2 (+9.8) | +11.0 (+13.2) | +13.1 (+14.2) |

Board peak excess tracks awake time (r = +0.78, n = 102). After the first 30 min of
long sessions (n = 9, 400 mA), the excess is +5.9 °C on board, +4.3 on batt, +6.8
on accel and +8.7 on cpu. That is about **15 °C per A** of discharge for board
(r = +0.69).

### Charging (always awake): excess by phase (median over episodes; p10…p90; °C)

| Phase | Episodes | Current | SOC | Minutes | cpu | batt | board | accel |
|---|---|---|---|---|---|---|---|---|
| Fast (CC), last 3 rows | 13 | 1,483 mA | 39→85 % | 40 | +14.3 (+11.2…+16.6) | +6.7 (+4.1…+8.8) | **+8.7** (+6.2…+10.6) | +13.5 (+9.5…+16.1) |
| Taper (CV), phase mean | 14 | 261 mA | 88→100 % | 70 | +11.5 (+9.4…+13.3) | +4.4 (+2.6…+5.5) | +6.8 (+4.9…+8.2) | +8.0 (+5.8…+9.4) |
| Full on charger, RTC cycling, last 3 wakes | 6 | −51 mA | 100 % | 173 | +0.5 (−0.8…+1.1) | +0.2 (−0.6…+0.6) | +0.3 (−0.7…+0.7) | +0.5 (−0.6…+1.0) |

- **The CC→CV knee is at 88 % SOC** (range 86–91 %, n = 13), not 70 %. Phases here are split by current: fast means at least 1,000 mA.
- **Current is a weak predictor.** End-of-CC board excess correlates with CC current at r = +0.34 (1,191–1,834 mA) and with CC duration at r = +0.75. Over all 314 charging rows, a linear current term only cuts the residual sd from 2.33 to 2.14 °C. Charging always runs awake, so charger heat and CPU or display heat cannot be separated.
- **On the charger at 100 %, the board needs about 2 h after the charge current stops.** Excess by minutes since the current last went positive:

  | Minutes | Median | p95 | n |
  |---|---|---|---|
  | 0–30 | +1.72 | +4.41 | 27 |
  | 30–60 | +0.79 | +1.07 | 35 |
  | 60–120 | +0.30 | +0.78 | 65 |
  | > 120 | −0.12 | +0.67 | 80 |

### Cooldown (single exponential on RTC resume samples; windows of at least 3 h without activity)

| After | Sensor | Fits kept* | Median A | τ, median (IQR) | Fitted time to < 0.5 °C | Empirical time to < 0.5 °C |
|---|---|---|---|---|---|---|
| Use | batt | 50 of 72 | 2.1 °C | 23 (13–45) min | 31 min | 44 min |
| Use | **board** | 51 of 72 | 2.7 °C | **23 (12–46) min** | 33 min | 49 min |
| Use | accel | 49 of 72 | 2.4 °C | 24 (15–53) min | 35 min | 97 min |
| Use | cpu | 49 of 72 | 2.7 °C | 25 (14–60) min | 37 min | 140 min |
| Charge | batt | 6 of 10 | 1.7 °C | 34 (18–77) min | 60 min | 70 min |
| Charge | **board** | 6 of 10 | 2.1 °C | **33 (17–69) min** | 66 min | 75 min |
| Charge | accel | 6 of 10 | 2.7 °C | 35 (20–68) min | 69 min | 162 min |
| Charge | cpu | 7 of 10 | 2.3 °C | 29 (27–78) min | 54 min | 95 min |

\* A fit is kept when A ≥ 0.5 °C and τ falls inside the 2–400 min grid. The
empirical time is the median time until a 3-point running median stays within
0.5 °C of the fitted floor. For cpu and accel, read noise inflates it.

Cooldowns fall into **two populations**:
- **Fast:** 47 of 65 board fits have τ ≤ 60 min and A > 0. Their τ has a median of **17 min** (IQR 11–28) and A a median of 2.6 °C (max 8.7). This is the self-heating case.
- **Slow or negative:** the other **18** windows are slow (τ > 60 min) or start colder than their floor. Of the 16 slow fits, 10 end at 12–17 h local, against 9 of the 49 fits with τ ≤ 60 min. These are afternoon ambient warming overlapping the cooldown. The 5 fits that start colder than their floor mean ambient rose during the window. The owner did not relocate the device, so these are gradual room changes, not moves.

All four sensors share τ on resume samples because each resume row sees the whole
device after 293 s of sleep.

## 5. Widget recommendation

### Estimator: board − 0.20 °C; no correction term

Settled hold-out against the leave-one-out consensus. The consensus is the median of
the other three sensors, with training offsets applied.

| Estimator | n | Mean err | sd | Median abs err | p95 abs err | Max abs err |
|---|---|---|---|---|---|---|
| **board − 0.20** | 3,413 | +0.01 | **0.14** | **0.08** | **0.29** | 0.71 |
| batt + 0.20 | 3,413 | −0.04 | 0.23 | 0.14 | 0.44 | 1.54 |
| accel + 1.39 | 3,413 | +0.02 | 0.25 | 0.17 | 0.47 | 1.66 |
| cpu − 4.31 | 3,413 | −0.02 | 0.31 | 0.21 | 0.61 | 1.40 |

The NTC pair alone, board against battery after the training offset, has a mean of
+0.04, sd 0.15 and p95 0.30 °C.

Correction terms were fitted on the train period. They are evaluated on RTC samples
taken within 4 h of activity in the hold-out (n = 866: 18 use and 4 charge
episodes). The target is the strict-anchor baseline.

| Model | Mean err | Median abs err | p95 abs err | Verdict |
|---|---|---|---|---|
| M0 raw board | +0.12 | 0.29 | 1.34 | Reference |
| M1 − median excess by (time since activity, type) | −0.10 | 0.29 | 1.37 | No gain |
| M2a + k·(cpu−board) | −0.26 | 0.42 | 1.46 | Worse |
| M2b + k·(batt−board), k = −3.4 | −0.30 | 0.49 | 1.42 | Halves error in the first 30 min after use; biased overall |
| M2d three deltas | −0.31 | 0.49 | 1.40 | Same as M2b |
| M2e three deltas + `current_uA` | −0.31 | 0.49 | 1.40 | **The current term adds nothing** (coefficient +0.002 °C/mA) |
| M3b exponential extrapolation, 30 min, τ = 24 min | −0.02 | 0.22 | 1.24 | Small gain; needs 30 min of history |
| M4 hold last settled value | −0.07 | 0.20 | 1.16 | Optimistic: shares pre-episode anchors with the target |
| *Target noise floor* (deep-settled, ±3 h mask) | −0.03 | 0.27 | **1.26** | Every model sits at this floor |

From 1 h onward, every model's p95 equals the target's own noise. Beyond 1 h,
nothing can be gained or measured, so the decision rests on suppression.

### Suppression rules

Gates were scored against each fast cooldown's own fitted floor, over the first 2 h
(1,122 samples from 47 windows). Within 2 h, ambient drift is small.

| Gate | After | Unflagged | Median abs err | p95 abs err | Missed > 0.5 °C | False flags, settled |
|---|---|---|---|---|---|---|
| None | Use | 100 % | 0.25 | 1.74 | 27.4 % | 0 % |
| Flag tsa < 30 min | Use | 76 % | 0.19 | 0.78 | 13.6 % | 0 % |
| Flag tsa < 45 min | Use | 63 % | 0.17 | 0.63 | 9.7 % | 0 % |
| **Flag tsa < 60 min** | Use | 50 % | **0.16** | **0.62** | **7.9 %** | 0 % |
| Flag tsa < 90 min | Use | 25 % | 0.14 | 0.52 | 6.3 % | 0 % |
| **Flag tsa < 60 min** | Charge | 50 % | 0.06 | 0.86 | 8.2 % | 0 % |
| Flag tsa < 90 min | Charge | 26 % | 0.06 | 0.41 | 0.0 % | 0 % |
| Board fell > 0.10 °C in 15 min | Use | 48 % | 0.14 | 0.59 | 6.2 % | **11.3 %** |
| Adaptive: wait τ·ln(A/0.3) | Use | 65 % | 0.17 | 0.63 | 8.5 % | 0 % |

Recommended rules, in order:

1. **Charging** (`charger_online = 1` and current > 0): show "charging" and hide the value. The excess is +7.2 °C (median), and no current term fixes it.
2. **Full on charger** (`charger_online = 1`, current ≤ 0): flag until 120 min after the current was last positive. The median excess falls from +0.79 °C at 30–60 min to −0.12 °C after 120 min.
3. **After activity or unplug**: flag for **60 min**, or 90 min after a charging session if the extra coverage loss is acceptable. Activity means any wake longer than 45 s, any non-0x00 reason, or any sleep shorter than 200 s. Past 60–90 min, longer gates buy almost nothing. The remaining misses come from slow windows, which are ambient warming: even with a 90 min gate they keep a median of 0.52 °C, p95 1.95 °C and 55 % misses.
4. **While flagged, show the last settled value** with a "settling" mark, not the live reading. A held value is stale but unbiased by the device's own heat. The live value runs +1–3 °C high in the first 30 min (section 2).
5. **Optional "not equilibrated" mark:** flag when |batt − board + 0.40| > 0.30 °C. It catches 17 of the 20 warm-stretch samples and falsely flags 5.0 % of settled samples.

Do not trust `wakeup_reason` alone to detect activity: it is latched and misses
0x00 user and charge sessions. One option, **not tested in this log**: CLOCK_MONOTONIC
excludes suspend and CLOCK_BOOTTIME includes it, so their difference between
consecutive RTC invocations gives the awake time. Anything well above the normal
~7 s, for example > 45 s, means activity happened in between.

**Expected error of the recommended estimator:**
- **Settled:** sd 0.14 °C and p95 0.29 °C against the consensus on the 14-day hold-out.
- **Right after the gate opens:** a median of 0.16 °C and a p95 of about 0.6 °C (all periods). The hold-out alone has a median of 0.24 °C and a p95 of 1.00 °C, from n = 144 samples with 50 % unflagged.
- **Coverage:** 91 % of hold-out RTC wakes (3,533 of 3,897) show an unflagged value.

## 6. Confidence and gaps

| Item | Confidence | Note |
|---|---|---|
| No reboot, no hibernation, no stale reads | High | Every check passes on 13,000+ samples. |
| Board is the best single sensor | High | It leads on resolution, noise, and hold-out agreement (sd 0.14 against 0.23–0.31). |
| Offsets are stable over 7 weeks | High | Week-to-week range 0.09 °C (NTCs); hold-out drift ≤ 0.03 °C for every sensor. |
| Absolute level | **Unknown, ±0.2 °C at best** | The NTCs differ by 0.40 °C, plus a gain mismatch of 0.15 °C per °C. The −0.20 °C offset is a convention (the NTC midpoint), not a calibration. The consensus also shares any bias from the RTC-wake duty cycle, which this log cannot measure. |
| N = 1.5 h | Medium | It depends on the anchor rule: 3 h anchors give 1.5 h, 6 h anchors give 2.5 h. Offsets do not change, because the deltas flatten by 0.75 h. |
| Suppression windows | Medium | The fast-window evaluation pools all periods; the hold-out has only 4 charge episodes. Charge cooldowns rest on 7 fits. |
| Ambient warming and sun | Low | 18 of 65 cooldown windows overlap gradual ambient warming, and 3 warm stretches (up to 33.8 °C) look like sun on the device. Only the batt−board delta gate partly detects them. |
| Sharp environment changes | Not measured | The owner did not move the device between environments, so step response to a relocation is untested. It can be measured deliberately later. |
| Correction terms | Medium | They cannot be told apart from the evaluation target's noise beyond 1 h (null p95 1.26 °C). The batt−board delta helps only in the first 30 min after use. |
| 0x08 wake reason | Low | It is undocumented (10 rows) and treated as activity. |

The log records no ambient observation, so every figure above is relative agreement
between sensors. **One room-thermometer reading logged after an overnight sleep would
turn these relative offsets into absolute accuracy.** For example, re-arm the
recorder with `/home/root/templog/install.sh`, then run
`/home/root/templog/note.sh "ambient 23.4C desk"` before waking the device in the
morning. A second reading at a clearly different room temperature would also show
which NTC has the gain error.

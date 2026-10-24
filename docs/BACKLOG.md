# Backlog — v0.46.0 release (updated 2026-10-24)

Inventory of everything still open across DEFERRED.md, fix-wave-plan.md,
mod-wave-plan.md and the v0.45.x commit history. One line each; sources in
parentheses. Update this file when items close.

Owner rulings 2026-10-24: two months of daily use on v0.46.0 with no
problems seen, so move to release. Further refinement buys marginal gains;
everything under "Parked" waits for user feedback. Timezone and locale stay
terminal-settable (README SSH recipe); no picker mod.

## Release (in progress)

- **Build environment** — the gitignored `research/` tree (qmldiff,
  device-qml, preflight set, xovi clone for xovigen) and the zig and Rust
  toolchains are gone from the dev Mac; `package.sh` and `deploy.sh` both
  stop at their first step without them. Rebuild before any packaging.
- **Packaging round** — `scripts/package.sh` across all packages; both
  VELBUILDs bumped to 0.46.0 (2026-10-24). Repo matches the device
  byte-for-byte (qmds, SVGs, hooks, units; fastshot 0.11.0 banner).
- **vellum install/uninstall round-trip** — never run against the current
  recipes: the device's vellum DB still says 0.31.2 and every version since
  arrived through `deploy.sh`. Upgrade, `vellum del` both, check the stock
  hook is back and other mods still load, `vellum add` again.
- **OS target** — recipes pin `remarkable-os>=3.27 <3.28`; upstream vellum
  moved to 3.28 (2026-09) and 3.29 (2026-10-22). Publish 3.27-only or port
  first; owner decision.
- **Publish** — tag, GitHub release with the fastshot `.so` as an asset,
  VELBUILD `source=`/`sha512sums=` (upstream pattern: rm-shot), then the
  upstream submission, which the owner makes (upstream does not accept
  agent-opened PRs). Upstream recipes declare lifecycle scripts as VELBUILD
  functions; the clock recipe's abuild-style `install=` files need porting.

## Closed 2026-10-24

- **Live-use observations** — light→deep escalation fix, luma sampling
  accuracy, live style flip, `pinned.json` write latency: closed by owner
  ruling after two months of use. Log check the same day found no issue:
  xochitl up since the 08-23 deploy with zero restarts; in the 4.5-day
  journal all 8 idle naps escalated with `freeze=true`, 0 of 51 fastshot
  failures, 1,401 suspends with 4 self-recovered aborts, no failed units,
  0.43–0.57 %/h on unplugged sleeps. The journal keeps only 4–5 days
  because clock wakes log ~19k lines a day.
- **Purge hook** — by design: the README documents the manual
  `rm -rf /home/root/.pinnedSleepScreen`; no lifecycle purge. (DEFERRED WP9)
- **Timezone/locale picker rebuild** — dropped; terminal-settable.
  (fix-wave-plan)
- **Battery icon asymmetry** — superseded by the black style's token clone.
  (DEFERRED WP4a)

## Parked — act only on user feedback

- **Forced-freeze skip-flag double grab** — long-press sleep pays one extra
  ~70ms grab; cost only. Fix = Navigator-published one-shot marker.
  (DEFERRED WP10)
- **Chapter-hole axis question** — chrome holes may be computed on swapped
  axes if DocumentView is logical-landscape; needs a landscape-capture
  check. (DEFERRED WP1)
- **Luma sampling refinement** — whole-bar vote or 2-of-3 region votes if
  white-bar or contacts-strip misreads get reported.
- **Smoke-test paths outside daily use** — Sleep bar toggle off (radio,
  clock panel, deep bar and light pill hidden; no white flash on a
  transparent freeze), clock panel absent without the companion, contacts
  verdict on a dark page.
- **`already slept` hibernation counter** — zero point and reset rule
  unknown; no doc may state a time-to-hibernate. (DEFERRED WP9)
- **10"/13" panel checks** — community testing; no Pro hardware on hand.
  (DEFERRED WP2/WP3)
- **Text.Outline vs mod halo weight** — mostly moot since halos replaced
  Text.Outline. (DEFERRED WP4b)
- **Stale battery comment** — both battery Rows carry the wrong-order
  comment; bundle with any future bar edit. (DEFERRED WP4a)
- **Ambient-temperature widget** — sensor analysis done
  (`tempdata/analysis.md`, 2026-10-18: board NTC − 0.20 °C plus suppression
  rules); no widget code.
- **Chromeless capture** — open question: does a forced repaint land in the
  fb inside the <150ms 0→2 window. (fix-wave-plan)
- **Navigate-away capture** — synchronous shot when leaving a dirty page;
  pairs with the parked self-capture merge. (DEFERRED owner idea)
- **Lasso/touch-select work** — separate project. Worktrees under
  `.claude/worktrees`: both `agent-*` trees and `lasso-touch-select-spec`
  hold nothing beyond `main`; `selection-stroke-boundary` contains every
  `intersect-lasso-selection` commit plus one.

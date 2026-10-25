# Backlog — v0.46.1 release (updated 2026-10-25)

Inventory of everything still open across DEFERRED.md, fix-wave-plan.md,
mod-wave-plan.md and the v0.45.x commit history. One line each; sources in
parentheses. Update this file when items close.

Owner rulings 2026-10-24: two months of daily use on v0.46.0 with no
problems seen, so move to release. Further refinement buys marginal gains;
everything under "Parked" waits for user feedback. Timezone and locale stay
terminal-settable (README SSH recipe); no picker mod.

## Release v0.46.1 (published 2026-10-25; upstream PRs pending)

- **Build environment** — DONE 2026-10-25. zig 0.17.0 and Rust stable
  (Homebrew/rustup); `research/qmldiff` at 25681c3 (the submodule pin of
  xovi-extensions v19-23052026 = the device's qt-resource-rebuilder
  19.0.0); `research/xovi` at v0.3.3; `research/device-qml` re-extracted
  (41 files; SceneSelectionHandler now extracts, homescreen CreateMenu
  still does not); `research/preflight` = 27 other installed qmds
  de-hashed one by one, dockButtons' homescreen CreateMenu block stripped.
- **Packaging round** — DONE 2026-10-25, v0.46.1 DEPLOYED via
  `package.sh` (vellum 0.31.2 → 0.46.1, loaded:1 breakage:0). v0.46.1 =
  v0.46.0 plus the error page's issues link moved from the renamed
  YanGeruch account to Flarette. fastshot rebuilt with zig 0.17
  (reproducible: two clean builds, same md5); the tested ELF is kept at
  `dist/release/v0.46.1/fastshot-aarch64.so`. Injected button sleep:
  `captured:true`, current.bmp written, bar shows date, clock, bolt and
  battery %. PDF check passed the same day: the PDF renderer loaded
  fastshot 0.11.0 and rendered pages, with no `Cannot load extension`
  and no `renderer exited`.
- **vellum round-trip** — DONE 2026-10-25: upgrade, `vellum del` both
  (stock `sleep-wifi.sh` restored byte-identical, zz hook, units and mod
  files gone, vpdd back to 30000, xovi drop-in intact; restart = 28 other
  mods load, ours not), fresh `vellum add`, del + add again, restart:
  loaded, timer re-armed at 5 min. Found and fixed: uninstall left the
  volatile `pinsleep-clock.timer.d/cadence.conf` the mod writes at start.
- **w4clamp not packaged** — the dev tablet runs the hand-installed
  w4clamp.so + rootfs drop-in `50-pinsleep-clamp.conf` (2995ac7,
  2026-08-16: 34s re-suspend window clamped to 3s), so the two-month soak
  and its 0.43–0.57 %/h drain include it. The packages do not ship it;
  released users get the README's 34s-window numbers (~0.9 %/h at 5 min).
  Owner ruling 2026-10-25: v0.46.1 ships without it; packaging it is a
  separate study for a future release (branch `w4clamp-packaging`).
- **OS target** — 3.27 only (owner ruling 2026-10-25); 3.28/3.29 ports
  are left to the community.
- **Upstream tooling check** — DONE 2026-10-25 on local-source test
  copies: `validate-velbuild.sh` PASS, vbuild 0.0.36 `gen` + upstream
  `apkbuild-lint` clean, `vbuild checksum` + `vbuild all` build both apks.
  All payload files are byte-identical to the vellum-installed files
  on the tablet; only the post-os-upgrade hook differs (vbuild generates
  it from `postosupgrade()`, same two commands). Harness on macOS:
  vbuild from source (`research/vbuild`, 0.0.36) in `research/vbuild-venv`,
  Homebrew bash 5 first on PATH (its parser reads `declare -p` output;
  macOS bash 3.2 breaks it), `SSL_CERT_FILE=/etc/ssl/cert.pem`, Podman
  socket as CONTAINER_HOST, and a local-only patch pinning the x86_64-only
  vbuild-builder image to `linux/amd64`.
- **Publish** — DONE 2026-10-25 except the upstream PRs. Rewrote main's
  author and committer to yan.geruch@gmail.com (old main kept locally as
  `backup/pre-email-rewrite`; doc-cited commit IDs remapped), force-pushed
  with a lease, tagged `v0.46.1`, GitHub release with
  `fastshot-aarch64.so`. Recipes carry `sha512sums` from the published
  files: all 14 match the tag and the tested binary; a `vbuild all` from
  the published sources gives 16 payload files identical to the tablet.
- **Upstream PRs** — owner: copy each `packaging/<pkg>/VELBUILD` into a
  fork of vellum-dev/vellum under `packages/<pkg>/`, one PR per package
  (main first; the clock depends on it), description written by the
  owner. Upstream closes PRs whose description an LLM wrote and wants
  human-authored commits. `README.md`'s `vellum add` install route works
  only once these are published. Documented flow (vellum README): PR to
  main, CI lints and builds, maintainers publish to the testing repo, the
  owner tests with `vellum testing enable` + `vellum add <pkg>@testing`,
  then comments `/ready-for-review`.
- **Readable qmd vs hashed convention** — vellum never hashes .qmd files
  (no recipe runs qmldiff); hashing is the author's step. The
  qt-resource-rebuilder README says community qmds are qmldiff-hashed "by
  design", and all 14 sampled upstream qmd sources are. Ours ships
  readable; it applies fine (vellum-installed on the tablet), but reviewers
  may ask for a hashed copy: `qmldiff hash-diffs <hashtab> <qmd>`, retest
  on the tablet, ship it as a release asset, bump `pkgrel`.

## Post-release bugs (open 2026-10-25)

Owner reports after pinning NeuroSmug (dense full-color PDF page). Upstream
PRs wait until these are understood.

- **Grey screen sticks after quick sleeps** — after about 12 sleep→wake
  cycles woken within 2–3 s, the panel stays in the grey fast-update mode
  until a full refresh; firmware normally settles it in 5–10 s. Captures
  taken during it hold normal full-color pixels, so the panel's update
  mode is stuck, not the image. Regression A/B, DEPLOYED 2026-10-25 17:02:
  the tablet runs the pre-release build, hand-copied over the vellum files.
  The qmd is v0.46.0 (from 778955d). fastshot 0.11.0 is built from the
  same source with zig 0.16.0, the latest release two months ago (tarball
  sha256 `b23d70de…1489`, .so md5 `756d65bd…53ba`). The v0.46.1 files
  are backed up in `/home/root/.pinnedSleepScreen/ab-backup-v0461/`. To
  restore, stage the .so in `/tmp` and `mv` it into place, copy the qmd
  back, then `systemctl reset-failed xochitl` and restart.
- **Stale chapter 0 after reopen** — `reload()` starts the chrome hold only
  if the toolbar is hidden when the pinned page loads. xochitl reopens a
  document with the toolbar as it was at close, so after a close with the
  toolbar up, no clean ch0 is taken and the last wake's ch0 survives, even
  after strokes in it were erased. Open question: a stale ch0 shows only
  in the toolbar band, yet the owner saw old strokes across the page, so
  ch1 may also be dropped at sleep. The fix (hold on every open vs. drop
  chapters older than the open) waits for that answer.

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

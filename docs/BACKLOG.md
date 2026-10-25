# Backlog — v0.46.0 release (updated 2026-10-24)

Inventory of everything still open across DEFERRED.md, fix-wave-plan.md,
mod-wave-plan.md and the v0.45.x commit history. One line each; sources in
parentheses. Update this file when items close.

Owner rulings 2026-10-24: two months of daily use on v0.46.0 with no
problems seen, so move to release. Further refinement buys marginal gains;
everything under "Parked" waits for user feedback. Timezone and locale stay
terminal-settable (README SSH recipe); no picker mod.

## Release (in progress)

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
  battery %. Still open: open a PDF once (extensions also load in the
  PDF renderer).
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
  Owner decision: ship as is, or package the clamp.
- **OS target** — 3.27 only (owner ruling 2026-10-25); 3.28/3.29 ports
  are left to the community.
- **Upstream tooling check** — DONE 2026-10-25 on local-source test
  copies: `validate-velbuild.sh` PASS, vbuild 0.0.36 `gen` + upstream
  `apkbuild-lint` clean, `vbuild checksum` + `vbuild all` build both apks.
  All 15 payload files are byte-identical to the vellum-installed files
  on the tablet; only the post-os-upgrade hook differs (vbuild generates
  it from `postosupgrade()`, same two commands). Harness on macOS:
  vbuild from source (`research/vbuild`, 0.0.36) in `research/vbuild-venv`,
  Homebrew bash 5 first on PATH (its parser reads `declare -p` output;
  macOS bash 3.2 breaks it), `SSL_CERT_FILE=/etc/ssl/cert.pem`, Podman
  socket as CONTAINER_HOST, and a local-only patch pinning the x86_64-only
  vbuild-builder image to `linux/amd64`.
- **Publish** — recipes are in upstream format (maintainer
  yan.geruch@gmail.com, `source=` from the tag, fastshot as release asset
  `fastshot-aarch64.so`, LICENSE + SOURCES, clock lifecycle as VELBUILD
  functions); `sha512sums` filled after the tag. Steps: force-push the
  author-rewritten main, tag `v0.46.1`, GitHub release with
  `dist/release/v0.46.1/fastshot-aarch64.so`, checksums, then the owner's
  upstream PRs (one per package). Upstream closes PRs whose description an
  LLM wrote and wants human-authored commits, so the owner writes and
  opens them.

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

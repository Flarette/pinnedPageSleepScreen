# Backlog — snapshot at v0.46.0 (2026-08-23, session close)

Inventory of everything still open across DEFERRED.md, fix-wave-plan.md,
mod-wave-plan.md and the v0.45.x commit history. One line each; sources in
parentheses. Update this file when items close.

## Deferred bugs (known, reproducible or root-caused, just not fixed)

- **Forced-freeze skip-flag double grab** — sleep-entry capture reads
  `pinSleepForceFreeze` after the Navigator may have cleared it, so a
  long-press sleep pays one extra ~70ms grab. Cost only, never wrong pixels.
  Fix = Navigator-published one-shot marker. (DEFERRED WP10)
- **Chapter-hole axis question (WP1)** — chapter chrome rects are mapped in
  DocumentView space but `complement()` clips against the sleep window's
  physical-portrait size; if DocumentView is logical-landscape the holes are
  computed on swapped axes. Unverified; needs a landscape-capture device check.

## Observations waiting on data (evaluate in live use before touching)

- **v0.44.5 light→deep escalation fix verification** — still pending one
  natural idle nap through light sleep (frozen screen + `freeze=true` in the
  first applyPower journal line). The v0.46 idle-white-bar change rides the
  same path, so the same nap verifies both.
- **Luma sampling accuracy** — the white-bar test votes only the gap slices
  around the center text (~20% of the bar). Owner ruling: refine only if
  day-to-day misreads appear. Candidates recorded: whole-bar vote or 2-of-3
  region votes. The new contacts-strip verdict (fc24157) adds a second
  sampler to watch with the same eye.
- **Live style-flip rendering** — old observation "outline mode only worked
  after reloading the UI" was never root-caused and its selector is deleted;
  re-test a live white↔transparent flip in Settings before chasing anything.
- **Synchronous pinned.json write latency** — capture-time write sits on the
  pen-lift path (page-cache only, microseconds); watch for any writing hitch,
  conservative fallback design already noted. (DEFERRED, owner question)

## Device checks (need the tablet, cheap)

- **v0.46.0 smoke test** — Display page: Sleep bar (toggle + White/Black/
  Transparent radio) above Sleep clock; toggle off hides radio, clock panel,
  deep bar and light banner; clock panel absent without the companion;
  transparent freeze with the bar off must NOT white-flash (band cover armed).
- **v0.45.x accumulated smoke tests** — contacts verdict on a dark page
  (white ink, black ring), pinned + long-press sleep-now (v0.45.9 fix),
  foldout/quick-settings captures excluded from chapters (v0.45.7/8).
- **`already slept` hibernation counter** — controlled repeat with clock
  off/1/5/15 min to pin down zero point and reset rule; until then no doc may
  state a time-to-hibernate. (DEFERRED WP9)
- **10"/13" panel checks** — `Screen` resolution inside sleep windows,
  bar scale 1.35, date-stamp clearance vs centered time on the narrowest bar.
  Community testing; no Pro hardware on hand. (DEFERRED WP2/WP3)
- **Text.Outline vs mod halo weight** — do the two outline weights read the
  same on-panel. (DEFERRED WP4b; mostly moot since halos replaced Text.Outline,
  confirm and close.)

## Separate-session ideas (new work, own context)

- **Timezone/locale picker rebuild** — v0.1.0 scrapped outright (wrong
  Settings section, wrong controls); start from scratch, old qmd in git
  history for reference only. (fix-wave-plan)
- **Chromeless capture** — mod-forced chrome-hide + repaint inside the <150ms
  0→2 window; passive delayed shots proven negative; v0.41's Bug A finding
  (tree hides chrome at entry anyway) makes the open question "does a repaint
  land in the fb before the sleep window". (fix-wave-plan)
- **Navigate-away capture** — synchronous shot when leaving a dirty page so
  the sleep image can't lag the last strokes; pairs with the parked
  self-capture merge. (DEFERRED owner idea)
- **Lasso/touch-select work** — four worktrees parked under .claude/worktrees
  (lasso-touch-select-spec, intersect-lasso-selection,
  selection-stroke-boundary, two agent scratch trees); separate project,
  triage or delete.

## Long-arc packaging / release (after fix waves are green)

- **Packaging round** — run scripts/package.sh across all 4 packages
  (hardened 2026-08-19: versions single-sourced, fastshot clean-built);
  VELBUILD source/sha512sums at publish time only.
- **Purge hook design round** — nothing removes /home/root/.pinnedSleepScreen;
  naive rm -rf in a deinstall hook would eat pins on upgrades (apk runs
  deinstall on upgrade paths). Needs its own design. (DEFERRED WP9, owner
  decision parked)
- **Battery icon asymmetry** — black style ships its own inverted-token
  treatment; the old "compare mod-drawn vs stock geometry" check (DEFERRED
  WP4a) is largely superseded by the token clone but the entry was never
  formally closed.
- **Stale comment** — both battery Rows still carry the wrong-order comment
  ("percentage, bolt, icon rightmost" vs actual children). Trivial, bundle
  with any future bar edit. (DEFERRED WP4a)

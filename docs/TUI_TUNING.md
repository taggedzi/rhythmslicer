## A lightweight way to handle “lots of little broken/not-finished things”

### 1) Create a single “TUI Tuning” list (one place)

Add a section in `TODO.md` or make `docs/TUI_TUNING.md` with entries like:

* *Symptom:* what feels wrong
* *Trigger:* what you did (keys/mouse/resize/etc.)
* *Expected:* what you wanted
* *Actual:* what happened
* *Severity:* annoying / confusing / blocks use

This keeps the chaos out of your head.

### 2) Triage into 3 buckets

* **Bucket A — Broken (fix first):** wrong behavior, inconsistent state, misleading UI
* **Bucket B — Missing (implement):** feature exists in concept but not fully implemented
* **Bucket C — Polish (later):** alignment, spacing, “feels off”, tuning thresholds

Then only work Bucket A until it’s calm.

### 3) Fix one “vertical slice” at a time

Pick one area per session:

* Playlist navigation
* Scrubbing (time/volume/speed)
* Visualizer modes/HUD
* Open/Save flows
* Resize/layout

Don’t mix.

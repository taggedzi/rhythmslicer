Absolutely — let’s reset the mental stack and lock this down clearly.
Below is a **single, stable, end-to-end roadmap** starting **from exactly where your project is now**, with no drifting “what’s next”.

I’ll mark **Done / Next / Later**, and I’ll keep the scope realistic.

---

# Rhythm-Slicer: Stable Roadmap (Current State → Polished Release)

## ✅ CURRENT STATE (what is already done)

You have completed **all core playback mechanics**. This is a *big* milestone.

### Playback & Control

* ✅ Plays a folder, single file, or playlist
* ✅ Playlist browsing (keyboard + mouse)
* ✅ Scrollable playlist
* ✅ Selection without playback
* ✅ Play on activation
* ✅ Seek / progress bar
* ✅ Repeat modes
* ✅ Shuffle mode
* ✅ VLC backend stable

### UI Foundation

* ✅ TUI layout stable
* ✅ Playlist renders correctly
* ✅ Visualizer stub fills space
* ✅ Status/footer line works
* ✅ Mouse + keyboard coexist cleanly

This means **the player works**. Everything from here is *polish, usability, and completeness*.

---

## PHASE 1 — Playlist UX Completion (IMMEDIATE NEXT)

These are **must-have** for a real playlist editor.

### 1️⃣ Save / Load playlists  *(in progress)*

* Save `.m3u8`
* Load `.m3u/.m3u8`
* Relative paths default
* Optional absolute paths

➡️ *Exit criteria:*
You can save, quit, relaunch, and reload the same playlist reliably.

---

### 2️⃣ Remove tracks from playlist

* `D` = remove selected track
* Correct index adjustment
* If removing current track:

  * play next if available
  * stop if empty
* Playlist UI refreshes correctly

➡️ *Exit criteria:*
User can curate a playlist without restarting the app.

---

### 3️⃣ Playlist footer information

Inside the playlist panel (bottom line):

* `Selected: X / Total: Y`
* Optional: current mode indicators later

➡️ *Exit criteria:*
User always knows where they are in the playlist.

---

## PHASE 2 — In-App Navigation & Session Flow

This removes the “restart the app” friction.

### 4️⃣ Open file / folder from inside the app

* Modal prompt: paste or type a path
* Supports:

  * folder
  * single file
  * `.m3u/.m3u8`
* Replaces current playlist
* Optional autoplay

➡️ *Exit criteria:*
You never need to exit the TUI just to load new music.

---

### 5️⃣ Session persistence (lightweight)

Config file:

* Last opened path
* Volume
* Shuffle / repeat modes
* (Optional later) last track index

➡️ *Exit criteria:*
Restarting the app feels continuous.

---

## PHASE 3 — Visual & UX Polish (Cyberpunk Identity)

This is where it stops feeling like “a text app”.

### 6️⃣ Mode indicators (minimal, compact)

In footer or playlist footer:

* Repeat: `R:OFF | ONE | ALL`
* Shuffle: `S:ON / OFF`
* Checkbox-style if terminal supports it

➡️ *Exit criteria:*
Modes are visible at a glance.

---

### 7️⃣ Transport controls (ASCII art)

Displayed under the progress bar:

```
[<<] [▶/⏸] [■] [>>]
```

* Visual only at first
* Mouse-clickable later if desired

➡️ *Exit criteria:*
UI visually communicates playback controls.

---

### 8️⃣ 50 / 50 layout split

* Playlist = 50% width
* Visualizer = 50% width
* Responsive on resize

➡️ *Exit criteria:*
Balanced, intentional layout.

---

### 9️⃣ Metadata display (title / artist)

* Read metadata when available
* Fallback to filename
* Display in playlist:

  * `Artist – Title`
* Cache results per track

➡️ *Exit criteria:*
Playlist looks human-readable, not file-system-centric.

---

### 🔟 Cyberpunk theme pass

* Neon accent colors
* Styled borders & titles
* High contrast but readable
* Consistent palette

➡️ *Exit criteria:*
Screenshot looks *intentional* and branded.

---

## PHASE 4 — Visualizer (REAL, but Controlled)

Do **after UI is stable**.

### 11️⃣ Visualizer Phase A (polished synthetic)

* Smooth, non-jittery
* Multiple styles (bars/wave)
* Uses playback time

➡️ *Exit criteria:*
Looks good even without audio analysis.

---

### 12️⃣ Visualizer Phase B (audio-based)

* File-based analysis (waveform or spectrum)
* Cached per track
* Syncs with seek

➡️ *Exit criteria:*
Visualizer reflects the actual music.

---

## PHASE 5 — Packaging & Release Quality

This is what makes it *shareable*.

### 13️⃣ Reliability & diagnostics

* Friendly “VLC not installed” errors
* `--debug` mode
* Optional `r-slicer doctor`

---

### 14️⃣ Documentation

* README (install, usage, keybinds)
* VLC requirement documented
* Screenshots

---

### 15️⃣ Tests & CI

* Playlist logic
* Save/load paths
* Shuffle/repeat
* Seek math
* UI selection logic (mocked)

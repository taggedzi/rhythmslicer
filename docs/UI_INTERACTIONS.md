# UI_INTERACTIONS.md

Rhythm Slicer Pro — UI Interaction & Control Semantics

This document defines the **authoritative behavior and keyboard mappings**
for all interactive UI elements in the Rhythm Slicer Pro terminal interface.

This is a **behavioral contract**.  
Implementation must conform to these rules regardless of rendering backend.

---

## 1. General Interaction Principles

1. **Keyboard and mouse interactions are equivalent**
   - Every UI control must be operable via keyboard
   - Mouse interaction must trigger the same logic paths

2. **No interaction may cause layout shifts**
   - Button labels are fixed-width
   - State changes must not resize UI regions

3. **Immediate feedback**
   - All interactions must immediately update:
     - Visual state
     - Player state indicator
     - Relevant UI labels

4. **Clamping**
   - All numeric values (time, volume) are clamped to valid ranges

---

## 2. Playback Controls (Transport)

### 2.1 Play / Pause (Toggle)

**Purpose:** Start or pause playback

- Represented by a **single toggle button**
- Label reflects the **action that will occur**

#### State → Label Mapping

| Player State | Button Label |
|-------------|--------------|
| Playing     | PAUSE |
| Paused      | PLAY |
| Stopped     | PLAY |

#### Behavior

- PLAY:
  - Starts playback from current position
  - If stopped, starts from beginning
- PAUSE:
  - Pauses playback at current position

#### Keyboard Shortcuts

- `Space`
- `Enter` (when transport row is focused)

---

### 2.2 Stop

**Purpose:** Fully stop playback and reset position

#### Behavior

- Stops playback
- Resets current time to `00:00`
- Player state becomes `STOPPED`
- Play/Pause button label updates to `PLAY`

#### Keyboard Shortcuts

- `S`

---

### 2.3 Previous Track `[<<]`

**Purpose:** Restart or go to previous track

#### Behavior

- If current playback time > 3 seconds:
  - Restart current track
- Else:
  - Move to previous track
- If at first track:
  - Behavior depends on repeat mode

#### Keyboard Shortcuts

- `Left Arrow`
- `H`

---

### 2.4 Next Track `[>>]`

**Purpose:** Advance to next track

#### Behavior

- Skips immediately to next track
- If at end of playlist:
  - Behavior depends on repeat mode

#### Keyboard Shortcuts

- `Right Arrow`
- `L`

---

## 3. Playback Modes

### 3.1 Repeat Mode

**Purpose:** Control behavior at end-of-track / end-of-playlist

#### Modes

- `R:OFF` – stop at end of playlist
- `R:ONE` – repeat current track
- `R:ALL` – loop entire playlist

#### Behavior

- Activating cycles modes:

```ascii

OFF → ONE → ALL → OFF

```

- Display is fixed-width

#### Keyboard Shortcuts

- `R`

---

### 3.2 Shuffle Mode

**Purpose:** Randomize playback order

#### Behavior

- Toggles `S:OFF ↔ S:ON`
- When enabled:
- Playback order is randomized
- Current track continues uninterrupted
- Does not reorder visible playlist (unless explicitly implemented)

#### Keyboard Shortcuts

- `F` (for “shuffle” / “random”)

---

## 4. Playlist Interaction

### 4.1 Navigation

#### Behavior

- Moves selection within playlist
- Does not change playback unless explicitly activated

#### Keyboard Shortcuts

- `Up Arrow` / `Down Arrow`
- `K` / `J`
- `Page Up` / `Page Down`
- `Home` / `End`

---

### 4.2 Select / Play Track

**Purpose:** Begin playback of selected track

#### Behavior

- Stops current track (if playing)
- Starts selected track from beginning
- Updates playing-track highlight

#### Keyboard Shortcuts

- `Enter`

---

## 5. Time / Progress Bar

### Purpose

Seek within the current track

#### Behavior

- Seeking clamps between `0` and track duration
- Disabled for non-seekable sources (if applicable)

#### Keyboard Shortcuts

- `[` – seek backward (small step, e.g. −5s)
- `]` – seek forward (small step, e.g. +5s)
- `{` – seek backward (large step, e.g. −30s)
- `}` – seek forward (large step, e.g. +30s)

(Mouse click/drag needs to be supported.)

---

## 6. Volume Control

### Purpose

Adjust playback volume

#### Behavior

- Range: `0–100`
- Clamped at bounds
- Updates volume bar immediately

#### Keyboard Shortcuts

- `-` – volume down (small step)
- `=` – volume up (small step)
- `_` – volume down (large step)
- `+` – volume up (large step)

(Optional: `M` for mute if implemented.)

---

## 7. Visual Feedback Rules

| Condition | Visual Cue |
|---------|------------|
| Selected playlist item | Background highlight |
| Playing track | Bright / bold |
| Selected + playing | Combined styles |
| Active toggle | Accent color |
| Disabled control | Dim |

---

## 8. Non-Goals

The interaction system will NOT:

- Change layout during interaction
- Require mouse input
- Use hidden or undocumented shortcuts
- Allow inconsistent keyboard/mouse behavior

---

## 9. Philosophy

> Every interaction should be predictable, reversible, and visible.

This document defines the **single source of truth**
for all user-facing interactions in Rhythm Slicer Pro.

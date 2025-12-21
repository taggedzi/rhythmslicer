# UI_LAYOUT.md

Rhythm Slicer Pro — Terminal User Interface Layout Specification

This document defines the **authoritative layout, behavior, and constraints**
for the Rhythm Slicer Pro terminal UI (TUI).

The goal is to maximize information density and usability within constrained
terminal dimensions while preserving clarity, consistency, and visual hierarchy.

---

## 1. Design Principles

1. **Playlist-first UI**
   - The playlist is the primary interaction surface.
   - It must remain usable under all supported terminal sizes.

2. **No redundant information**
   - Metadata is shown once, in its appropriate region.
   - The title bar is identity-focused, not informational.

3. **Graceful degradation**
   - Secondary panels shrink or disappear before primary panels.
   - No horizontal scrolling is permitted.

4. **Fixed-width discipline**
   - Layout must function correctly at 80 columns.
   - Minimum enforced width is 41 columns.

5. **Color and style convey meaning**
   - Color is used to indicate importance, state, or attention.
   - Color is never decorative-only.

---

## 2. Global Size Constraints

### Horizontal

- **Minimum width:** 41 columns (hard stop)
- **Baseline design width:** 80 columns
- **Expanded layouts:** >80 columns supported

If the terminal width is less than 41 columns:

- The application must refuse to render or display a resize warning.

### Vertical

- **Minimum height:** 12 rows (barely usable)
- **Recommended minimum:** 15 rows

---

## 3. Frame & Borders

- The UI uses a **single outer frame**
- Internal panels share borders using junction glyphs:
  - `├`, `┤`, `┬`, `┴`, `┼`
- No nested or double borders are permitted
- This minimizes border overhead and maximizes usable width

---

## 4. Top Bar (Application Identity)

### Purpose

- Display application identity only

### Content

```ascii

<< Rhythm Slicer Pro >>

```

- No track metadata
- No playback state
- Always visible if height permits

---

## 5. Main Content Area

### Split Layout

```ascii

| PLAYLIST | VISUALIZER |

```

- Vertical split when space allows
- Playlist always has priority

### Width Allocation Rules

- Playlist minimum width: **41 columns**
- Visualizer shrinks first
- If total width ≥ 80:
  - Playlist and visualizer share space ~50/50
  - If uneven, extra column goes to playlist
- If width < threshold:
  - Visualizer collapses completely

---

## 6. Playlist Panel

### Priority

**Highest priority panel in the UI**

### Behavior

- Never shrinks below 41 columns
- Never scrolls horizontally
- Text truncates with `…` if too long

### Selection & State

- **Selected track:** background highlight
- **Currently playing track:** brighter or bold text
- **Selected + playing:** combined styles
- No selection glyphs (`>>`, `*`, etc.) are used

### Titles

- Playlist has **no title bar**
- The content itself defines the region

---

## 7. Visualizer Panel

### Purpose

- Display animated or informational visualizations
- Purely optional

### Behavior

- Shrinks horizontally before playlist
- Collapses entirely if insufficient space
- Retains a distinct visual boundary

### Borders

- May use top and side borders
- Bottom border may merge into track info panel

---

## 8. Track Information Panel

### Purpose

- Display authoritative metadata for the current track

### Layout

```ascii

CURRENT TRACK
TITLE   <song.title>
ARTIST  <song.artist>
ALBUM   <song.album>
TRACK   <track number>

```

### Rules

- Labels are dim
- Values are bright
- Order reflects importance
- If metadata is missing:
  - TITLE defaults to filename
  - All other fields show `Unknown`

---

## 9. Transport & Status Area (Bottom)

### Always Visible

This region **must never be removed** once minimum height is met.

### Layout

```ascii

TIME: [====================●====] mm:ss/mm:ss
VOL:  [===========●=====] ###     [ PLAYER_STATE ]

```

### Rules

- TIME bar stretches dynamically with width
- VOL bar caps at a reasonable fixed width
- Player state text is concise (e.g. PLAYING, PAUSED)

---

## 10. Input & Interaction

- All controls must support:
  - Keyboard interaction
  - Mouse interaction (where supported)
- Keyboard shortcuts must remain functional regardless of layout changes

---

## 11. Resizing Behavior Summary

### Horizontal Shrink Order

1. Visualizer
2. Track information panel
3. Playlist (never below 41 columns)

### Vertical Shrink Order

1. Visualizer
2. Track information panel
3. Playlist rows
4. Transport bar (never removed)

---

## 12. Text Handling Rules

- No horizontal scrolling
- No text wrapping
- All overflow is truncated with `…`
- Truncation always occurs from the right

---

## 13. Color Usage Guidelines

| Element | Style |
|------|------|
| App title | Accent color |
| Playlist selection | Background highlight |
| Playing track | Bright / bold |
| Labels | Dim |
| Values | Normal / bright |
| Time bar | Accent |
| Volume bar | Neutral |
| Errors / warnings | Red |

Color must always convey meaning.

---

## 14. Non-Goals

The UI will NOT:

- Duplicate metadata across regions
- Require more than 80 columns
- Use decorative-only color
- Allow horizontal scrolling
- Depend on visualizer presence

---

## 15. Philosophy

> If it fits cleanly at 80 columns, it will scale everywhere.
> If it requires more, it does not belong in the default UI.

This document is the single source of truth for TUI layout behavior.

## 16. Transport Control Semantics

### Play / Pause Toggle

- PLAY and PAUSE are represented by a **single toggle control**
- Only one label is visible at any time
- The label reflects the **action that will occur when activated**

#### State-to-Label Mapping

| Player State | Button Label |
|-------------|--------------|
| Playing     | PAUSE |
| Paused      | PLAY |
| Stopped     | PLAY |

### Behavior Guarantees

- The control never changes width or position
- Activating the control immediately:
  1. Changes playback state
  2. Updates the button label
  3. Updates the player state indicator

### Input Consistency

- Keyboard and mouse activation are equivalent
- No interaction method may bypass state synchronization

## Here is the 80 Col Layout

```ascii
┌─<< App Title >> ──────────────────────┬──────────────────────────────────────┐
│ <song> - <artist>                     │ Visualizer content here              │
│ <song> - <artist>                     │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       │                                      │
│                                       ┼─ << Current Track >> ────────────────┤
│                                       │ Track: ###                           │
│                                       │ TITLE: song.title                    │
│ Track: xxx/yyy     R:ALL     S:OFF    │ ALBUM: song.album                    │
│    [<<]  [ PAUSE ] [ STOP ]  [>>]     │ ARTIST: song.artist                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ TIME: [════════════════════════════════════════════════════●═══] mm:ss/mm:ss │
│ VOL:  [═══════════●════] ###                                [ Player_State ] │
└──────────────────────────────────────────────────────────────────────────────┘
```

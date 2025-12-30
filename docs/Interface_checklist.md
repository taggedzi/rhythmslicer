# Rhythm Slicer – TUI Functional Checklist

## 1. App Startup & Layout

* [ ] App launches without errors
* [ ] Minimum size enforcement works (too small → warning / layout clamps)
* [ ] Layout stabilizes after first resize
* [ ] No flicker or runaway redraw on idle
* [ ] Screen title updates correctly

---

## 2. Playlist Loading & Display

### Keyboard

* [ ] Load playlist via keybinding
* [ ] Playlist renders rows correctly
* [ ] Titles and artists ellipsize correctly
* [ ] Track counter shows correct `current/total`
* [ ] Selection defaults to first row

### Mouse

* [ ] Single-click selects a row
* [ ] Double-click plays selected track
* [ ] Scroll wheel moves playlist
* [ ] Click + drag selection behaves sanely

---

## 3. Playlist Navigation

### Keyboard

* [ ] Up / Down moves selection
* [ ] PageUp / PageDown jump correctly
* [ ] Home / End jump to first/last row
* [ ] Selection wraps or clamps correctly
* [ ] Selected row stays visible when navigating

### Mouse

* [ ] Mouse wheel scrolls without losing selection
* [ ] Clicking off rows does not break selection state

---

## 4. Playback Controls

### Keyboard

* [ ] Play / Pause toggle works
* [ ] Stop works
* [ ] Next track
* [ ] Previous track
* [ ] Repeat mode cycles correctly
* [ ] Shuffle toggle works

### Mouse

* [ ] Play button
* [ ] Pause button
* [ ] Stop button
* [ ] Next / Previous buttons reflect state
* [ ] Buttons disable/enable appropriately

---

## 5. Status Bar (Bottom Panel)

* [ ] Time text updates smoothly
* [ ] Time progress bar fills correctly
* [ ] Volume text reflects actual volume
* [ ] Volume bar updates correctly
* [ ] Speed text updates (e.g. `1.00x`)
* [ ] Speed bar reflects ratio correctly
* [ ] State label updates (PLAYING / PAUSED / STOPPED)
* [ ] Warning messages show in yellow
* [ ] Error messages show in red
* [ ] Transient messages clear correctly
* [ ] Cached updates prevent unnecessary redraws

---

## 6. Scrubbing (Mouse Interaction)

### Time

* [ ] Click on time bar seeks correctly
* [ ] Click-drag scrubs smoothly
* [ ] Release applies final seek
* [ ] Scrub cancels cleanly if mouse leaves bar

### Volume

* [ ] Click on volume bar sets volume
* [ ] Drag adjusts volume smoothly
* [ ] Volume clamps to 0–100

### Speed

* [ ] Click on speed bar adjusts rate
* [ ] Drag adjusts rate smoothly
* [ ] Speed clamps to allowed range

---

## 7. Visualizer – Viewport

* [ ] Visualizer appears when enabled
* [ ] Visualizer hides below min width/height
* [ ] “Visualizer too small” message displays correctly
* [ ] Visualizer updates at expected FPS
* [ ] No runaway CPU when idle
* [ ] Switching modes updates content correctly

---

## 8. Visualizer – Modes

* [ ] PLAYING renders bars
* [ ] PAUSED shows centered text
* [ ] STOPPED shows centered text
* [ ] LOADING animates dots
* [ ] Mode text is centered properly
* [ ] Mode text truncates correctly for small widths

---

## 9. Visualizer HUD

* [ ] HUD appears above visualizer
* [ ] Title displays correctly
* [ ] Artist displays correctly
* [ ] Album displays correctly
* [ ] Metadata loads asynchronously without blocking UI
* [ ] HUD truncates long text correctly
* [ ] HUD pads empty lines correctly
* [ ] HUD resizes cleanly

---

## 10. Open / Save Flows

### Keyboard

* [ ] Open prompt opens
* [ ] Recursive toggle works
* [ ] Confirm opens playlist
* [ ] Cancel exits cleanly

### Mouse

* [ ] Buttons clickable
* [ ] Toggle clickable
* [ ] Focus behavior correct

---

## 11. Playlist Builder

* [ ] Builder screen opens
* [ ] Add/remove tracks works
* [ ] Save playlist works
* [ ] Cancel returns without changes

---

## 12. Help & Modals

* [ ] Help screen opens
* [ ] Keybindings listed correctly
* [ ] Help closes cleanly
* [ ] Focus returns to app

---

## 13. Error Handling & Stability

* [ ] Invalid playlist handled gracefully
* [ ] Missing files skipped with message
* [ ] Playback errors show warning
* [ ] App recovers from failed track
* [ ] No crashes on rapid input
* [ ] Quit works from any state

---

## 14. Resize & Focus

* [ ] Resize does not break layout
* [ ] Playlist resizes columns correctly
* [ ] Visualizer resizes correctly
* [ ] HUD resizes correctly
* [ ] Focus remains consistent after resize

---

## 15. Shutdown

* [ ] Quit via keybinding
* [ ] Quit via button
* [ ] Background tasks stop
* [ ] No hanging threads
* [ ] Clean exit

---

### Optional: Refactor Confidence Check

* [ ] All extracted helpers have at least one test
* [ ] No logic duplication left accidentally
* [ ] tui.py reads as “orchestration only”
* [ ] No formatting/math logic left inline

## Playback Semantics (Authoritative Spec)

### Definitions

* **Natural end** = track reaches end on its own
* **Manual navigation** = user presses Next / Previous or selects a track
* **Play order** = ordered list when Shuffle OFF, shuffled order when Shuffle ON

---

## Repeat: OFF

**Natural end**

* Advance to next track in play order
* If at end of list → stop

**Next / Previous**

* Move to next / previous track in play order
* No looping

---

## Repeat: ONE

**Natural end**

* Restart the *current* track

**Next**

* Advance to next track in play order
* **Repeat ONE remains enabled**
* The *new* track will loop on natural end

**Previous**

* Go to previous track (or restart current if you already have that rule)
* Repeat ONE still applies to whichever track is now playing

> Mental model: *“Repeat ONE applies to the currently playing track, not the navigation command.”*

---

## Repeat: ALL

**Natural end**

* Advance to next track
* If at end → wrap to first track in play order

**Next / Previous**

* Move normally through play order
* Wrapping allowed at ends

---

## Shuffle: OFF

* Play order = playlist order
* Repeat behavior applies to that order

---

## Shuffle: ON

* Play order = shuffled list (stable until reshuffle)
* Repeat behavior applies to the shuffled order

**Notes**

* Repeat ONE loops the current track, even in shuffle
* Repeat ALL wraps within the shuffled list
* Manual Next advances within the shuffled list
* Toggling Shuffle typically regenerates play order (your call, but document it)

---

## Non-goals (explicitly *not* done)

* Next does **not** restart the current track
* Repeat ONE does **not** temporarily disable itself on Next
* No implicit mode switching

---

## One-line doc blurb (drop-in)

> Repeat ONE loops the currently playing track on natural end; manual navigation still changes tracks, and repeat-one continues to apply to the newly playing track.


# Playlist Add – Scan Policy

This document defines the policy for how the Playlist **Add** operation scans files and folders.
The goal is to be **safe by default**, **respect explicit user intent**, and remain **cross-platform and predictable**.

---

## Definitions

### Hidden
A file or folder is considered **hidden** if **any** of the following are true:

- The OS marks it as hidden (e.g., Windows hidden attribute)
- The OS marks it as system (e.g., Windows system attribute)
- The file or folder name begins with a dot (`.`) on **any** platform

Examples:
- `.git`
- `.venv`
- `.nox`
- `.cache`
- `.idea`

Dot-prefixed paths are treated as hidden everywhere, including Windows, because they are a strong, intentional signal of non-user content in cross-platform tooling.

---

### System
A file or folder is considered **system** if the OS explicitly marks it as such.

We do **not** attempt to:
- detect renamed system folders
- maintain exhaustive lists of OS directories
- infer system status via heuristics

If the OS does not mark it hidden/system and it is not dot-prefixed, it is treated as a normal path.

---

## Default Behavior (Safe by Default)

During a recursive **Add** operation:

- Hidden files and folders are **skipped**
- System files and folders are **skipped**
- If a directory is hidden/system, traversal **does not descend** into it
- If a file is hidden/system, it is **not added**

This behavior applies automatically and requires no user interaction.

**Rationale:**
- Prevent accidental scanning of OS, tool, cache, backup, or metadata directories
- Avoid massive unintended scans
- Avoid permission issues and poor performance
- Match common user expectations

---

## Explicit User Intent Override

If the user **directly selects** a hidden or system file or folder and chooses **Add**:

- The selection is **respected**
- The scan/add operation is allowed
- A **warning** is shown before proceeding

This includes:
- selecting a hidden/system folder itself
- selecting a file or subfolder inside a hidden/system folder

User intent flows downward from the explicitly selected path.

---

## Warning Policy

Warnings should be:

- Informational and neutral
- Non-blocking unless the user chooses to cancel
- Clear that this path is normally skipped

Example wording (non-binding):

> “This location is marked as hidden and is normally skipped during scans.  
> It will be scanned because you selected it directly.”

or

> “This location is marked as a system path and is normally skipped during scans.  
> Continue scanning?”

Warnings are required only when the override is triggered by explicit selection.

---

## Non-Goals

This policy explicitly does **not** attempt to:

- Exhaustively detect all system directories
- Guess that renamed folders are system folders
- Perform deep inspection to classify paths
- Change scan behavior beyond skip-by-default + explicit override

The policy favors **clarity and predictability over completeness**.

---

## Design Principles

- **Safe by default**
- **Explicit user intent always wins**
- **Minimal OS awareness**
- **No surprise behavior**
- **Cross-platform consistency**

---

## Planned Follow-Ups (Not Implemented Here)

- Make recursive Add scans asynchronous and cancelable
- Add progress/spinner UI with Stop action
- Add preflight warnings for very large scans
- Apply this policy via a single scan classification hook

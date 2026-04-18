# G-Code Tool Remapper — Codebase Overview

## Purpose

This is a desktop utility for CNC machinists that **safely renumbers tool references inside G-code programs**. When a shop reorganises its tool crib — moving a drill from pocket 7 to pocket 12, for example — every G-code program that referenced the old pocket must be updated. Doing this by hand with a text editor is error-prone; a naive find-and-replace can corrupt a file when two tools are being swapped simultaneously (e.g. T10 → T20 and T20 → T10 in the same pass). This tool solves both problems.

---

## What It Does

| Capability | Detail |
|---|---|
| **Loads G-code files** | Supports `.nc`, `.gcode`, `.tap`, `.cnc`, `.txt`, `.has` and any file. Auto-detects encoding via `chardet` (falls back to `latin-1`). |
| **Manages remapping rules** | User enters pairs of old → new tool numbers. Multiple rules can be active at once. Duplicate and no-op rules are rejected. |
| **Remaps T, H, and D registers together** | A single rule `T7 → T12` also rewrites `H07 → H12` and `D07 → D12` — the three registers that always travel together in Fanuc-style G-code (tool select, length offset, diameter offset). |
| **Exact-match substitution** | Uses regex negative look-around (`(?<!\d)T7(?!\d)`) so `T7` never matches inside `T70` or `T17`. |
| **Collision-safe two-phase substitution** | Phase 1 replaces every matched token with a NUL-delimited placeholder (`\x00REMAP_T7\x00`). Phase 2 replaces placeholders with final values. This makes swaps (T10 ↔ T20) safe in a single pass — a plain left-to-right replace would cascade and corrupt both tools. |
| **Diff preview** | Shows every changed line in a colour-coded view: red rows (original) above green rows (remapped), with line numbers, so the operator can verify the changes before committing. |
| **Saves to a new file** | Writes `<original_name>_remapped<ext>` by default, preserving the original file's encoding. The source file is never overwritten automatically. |

---

## Architecture

The project is a single Python file (`gcode_tool_remapper.py`) split into two clear layers:

### Core Logic (lines 24–93)

Three pure functions with no GUI dependencies:

- **`build_pattern(prefix, number)`** — compiles an exact-boundary regex for a given register prefix and tool number.
- **`remap_line(line, rules)`** — applies all rules to a single text line using the two-phase placeholder strategy. Returns the modified line and a boolean indicating whether anything changed.
- **`remap_gcode(content, rules)`** — iterates every line, collects changed line numbers, and returns the full remapped file content.

### GUI Layer (lines 118–397)

A `tkinter`-based desktop application (`RemapperApp`, subclassing `tk.Tk`):

- **File section** — browse button + path display; reads and stores the raw file content on load.
- **Rules section** — entry fields for old/new tool numbers, a listbox showing active rules, and add/remove buttons.
- **Action buttons** — `Preview Changes` (renders the diff in-pane), `Save Remapped File…` (writes to disk), `Clear Preview`.
- **Preview pane** — a `ScrolledText` widget with colour tags rendering an inline diff.

### Distribution

A PyInstaller spec file (`GCode Tool Remapper.spec`) bundles the app into a single Windows executable (`dist/GCode Tool Remapper.exe`) with a custom icon (`gcode_remapper.ico`) and no console window.

---

## Sample Files

`Test Sample Files/` contains real Fanuc-style G-code programs (`.HAS` extension, used by Haas CNC controls) with multi-tool programs — realistic inputs to test the remapper against.

---

## Key Design Decisions

1. **Two-phase placeholder substitution** is the central algorithmic insight. Without it, swapping two tool numbers in one pass would produce incorrect output.
2. **T, H, and D are always remapped together** because Fanuc/Haas programs require all three to stay in sync; remapping only `T` while leaving `H` and `D` unchanged would create a broken program.
3. **The source file is never overwritten** — the save dialog defaults to `_remapped` suffix, protecting the original.
4. **Pure-function core** makes the remapping logic independently testable without launching the GUI.

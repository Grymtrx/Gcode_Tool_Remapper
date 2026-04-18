# Auto Remap All Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Auto Remap All" button that scans loaded G-code for T numbers, renumbers them sequentially in first-appearance order, populates the rules listbox, and immediately shows the diff preview.

**Architecture:** A pure module-level function `auto_build_rules(content)` extracts and sequences the T numbers (making the logic unit-testable without tkinter), and the GUI method `_auto_remap_all()` calls it, updates the listbox, and delegates to the existing `_preview()`. This follows the same pattern already used by `remap_gcode` / `remap_line` — core logic at module level, orchestration in the GUI class.

**Tech Stack:** Python 3, tkinter, re (stdlib only — no new dependencies)

---

## File Map

| File | Change |
|---|---|
| `gcode_tool_remapper.py` | Add `auto_build_rules()` function; add `_auto_remap_all()` method; add button in `_build_ui()` |
| `test_gcode_remapper.py` | Add `TestAutoRemap` class with unit tests for `auto_build_rules` |

---

## Task 1: Write failing tests for `auto_build_rules`

**Files:**
- Modify: `test_gcode_remapper.py`

- [ ] **Step 1: Add the `TestAutoRemap` class to `test_gcode_remapper.py`**

Add this import at the top of the test file (alongside the existing import):

```python
from gcode_tool_remapper import build_pattern, remap_line, remap_gcode, auto_build_rules
```

Then add the following class at the bottom of `test_gcode_remapper.py`:

```python
# ─────────────────────────────────────────────────────────────────────────────
#  auto_build_rules — unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoRemap:

    def test_sequential_from_first_appearance(self):
        """T numbers are renumbered in the order they first appear."""
        content = "T5 M06\nT2 M06\nT8 M06\n"
        rules = auto_build_rules(content)
        assert rules == [(5, 1), (2, 2), (8, 3)]

    def test_already_first_slot_skipped(self):
        """If the first-seen T number is already T1, no rule is added for it."""
        content = "T1 M06\nT3 M06\n"
        rules = auto_build_rules(content)
        # T1 is already slot 1 — skip it; T3 gets slot 2
        assert (1, 1) not in rules
        assert (3, 2) in rules

    def test_already_sequential_returns_empty(self):
        """If all tools are already in order T1, T2, T3... return empty list."""
        content = "T1 M06\nT2 M06\nT3 M06\n"
        rules = auto_build_rules(content)
        assert rules == []

    def test_duplicate_appearances_deduplicated(self):
        """A T number that appears multiple times is only counted once (first seen)."""
        content = "T3 M06\nT3 H3\nT1 M06\n"
        rules = auto_build_rules(content)
        assert rules == [(3, 1), (1, 2)]

    def test_no_t_numbers_returns_empty(self):
        """Content with no T numbers at all returns an empty list."""
        content = "G00 X1.0 Y2.0\nG01 Z-0.5 F100\n"
        rules = auto_build_rules(content)
        assert rules == []

    def test_case_insensitive_scan(self):
        """Lowercase t tokens (e.g. t5) are treated the same as uppercase T5."""
        content = "t5 M06\nt2 M06\n"
        rules = auto_build_rules(content)
        assert rules == [(5, 1), (2, 2)]

    def test_exact_boundary_t1_not_found_in_t10(self):
        """T10 must not be treated as a T1 occurrence when scanning."""
        content = "T10 M06\nT2 M06\n"
        rules = auto_build_rules(content)
        # T10 is slot 1, T2 is slot 2
        assert rules == [(10, 1), (2, 2)]

    def test_real_file_o3012(self):
        """O3012.HAS contains T1, T7, T18, T19 in that order.
        Expected rules: T1 stays (slot 1), T7→2, T18→3, T19→4."""
        import os
        path = os.path.join(os.path.dirname(__file__), "Test Sample Files", "O3012.HAS")
        with open(path, "r", encoding="latin-1", errors="replace") as fh:
            content = fh.read()
        rules = auto_build_rules(content)
        old_tools = [old for old, _ in rules]
        new_tools = [new for _, new in rules]
        # T1 already in slot 1 → not in rules
        assert 1 not in old_tools
        # T7 must become T2
        assert (7, 2) in rules
        # T18 must become T3
        assert (18, 3) in rules
        # T19 must become T4
        assert (19, 4) in rules
        # New numbers must be sequential with no gaps
        assert sorted(new_tools) == list(range(min(new_tools), max(new_tools) + 1))
```

- [ ] **Step 2: Run tests to verify they fail (function not yet defined)**

```
python -m pytest test_gcode_remapper.py::TestAutoRemap -v
```

Expected: All `TestAutoRemap` tests fail with `ImportError: cannot import name 'auto_build_rules'`

---

## Task 2: Implement `auto_build_rules`

**Files:**
- Modify: `gcode_tool_remapper.py`

- [ ] **Step 1: Add the function after the `detect_encoding` function (around line 98), before the GUI constants section**

Insert this block between `detect_encoding` and the `# ── GUI constants ──` comment:

```python
def auto_build_rules(content):
    """
    Scan *content* for T-number tokens in document order.
    Return a list of (old_num, new_num) tuples that renumber tools
    sequentially by first appearance: first tool seen → 1, second → 2, etc.
    Pairs where old_num == new_num are omitted (no-op rules).
    """
    seen = []
    for m in re.finditer(r'(?<!\d)T(\d+)(?!\d)', content, re.IGNORECASE):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return [(old, new) for new, old in enumerate(seen, start=1) if old != new]
```

- [ ] **Step 2: Run tests to verify they pass**

```
python -m pytest test_gcode_remapper.py::TestAutoRemap -v
```

Expected: All 8 `TestAutoRemap` tests pass.

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```
python -m pytest test_gcode_remapper.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add gcode_tool_remapper.py test_gcode_remapper.py
git commit -m "feat: add auto_build_rules — sequential T-number scanning logic"
```

---

## Task 3: Add `_auto_remap_all` GUI method and button

**Files:**
- Modify: `gcode_tool_remapper.py`

- [ ] **Step 1: Add the `_auto_remap_all` method to `RemapperApp`**

Add this method to `RemapperApp` after `_remove_rule` (around line 321) and before `_preview_helpers`:

```python
def _auto_remap_all(self):
    if not self.original_content:
        messagebox.showwarning("No File", "Load a G-code file first.")
        return

    rules = auto_build_rules(self.original_content)

    if not rules and not re.search(r'(?<!\d)T\d+(?!\d)', self.original_content, re.IGNORECASE):
        messagebox.showwarning("No T Numbers", "No T numbers found in file.")
        return

    if not rules:
        messagebox.showinfo("Already Sequential", "Tools are already in sequential order.")
        return

    # Clear existing rules
    self.rules.clear()
    self.rules_list.delete(0, "end")

    # Populate with auto-generated rules
    for old_num, new_num in rules:
        self.rules.append((old_num, new_num))
        self.rules_list.insert(
            "end",
            f"  T{old_num} → T{new_num}    (H{old_num}→H{new_num},  D{old_num}→D{new_num})"
        )

    self._preview()
```

- [ ] **Step 2: Add the "Auto Remap All" button in `_build_ui`**

In `_build_ui`, find the `input_row` section where "Add Rule" and "Remove Selected" are packed. After the "Remove Selected" button pack call, add:

```python
tk.Button(input_row, text="Auto Remap All", command=self._auto_remap_all,
          relief="flat", bg="#e67e22", fg="white", activebackground="#ca6f1e",
          font=("Segoe UI", 9, "bold"), cursor="hand2",
          padx=10).pack(side="left", padx=(8, 0))
```

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

```
python -m pytest test_gcode_remapper.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Manual smoke test**

```
python gcode_tool_remapper.py
```

Verify manually:
1. Launch the app — "Auto Remap All" button appears in the rules section (amber/orange).
2. Click "Auto Remap All" without loading a file → warning dialog "Load a G-code file first."
3. Load `Test Sample Files/O3012.HAS`.
4. Click "Auto Remap All" → rules listbox populates (T7→T2, T18→T3, T19→T4 since T1 is already slot 1), diff preview appears immediately.
5. Verify the preview shows T7 lines changed to T2, T18 lines to T3, etc.
6. Load `Test Sample Files/5400.HAS` (tools T1–T7 in order) → "Already Sequential" info dialog appears, no preview.
7. Add a manual rule first, then click "Auto Remap All" → manual rule is cleared, auto rules replace it.

- [ ] **Step 5: Commit**

```bash
git add gcode_tool_remapper.py
git commit -m "feat: add Auto Remap All button — renumbers tools sequentially by first appearance"
```

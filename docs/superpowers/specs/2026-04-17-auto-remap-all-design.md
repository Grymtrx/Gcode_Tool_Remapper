# Auto Remap All — Design Spec

**Date:** 2026-04-17  
**Version target:** post-v0.0.3  

---

## Summary

Add an "Auto Remap All" button to the Remapping Rules section. When clicked, it scans the loaded G-code for all T numbers, renumbers them sequentially in order of first appearance (first T found → T1, second → T2, etc.), clears any existing rules, populates the rules listbox with the generated rules, and immediately shows the diff preview.

---

## Behavior

### Button

- Placed in `input_row` inside the "Remapping Rules" `LabelFrame`, to the right of the "Remove Selected" button.
- Label: **"Auto Remap All"**
- Style: flat, amber/orange background (`#e67e22`) with white text — visually distinct from the blue "Add Rule" and grey "Remove Selected" buttons to signal it is a bulk destructive action.

### `_auto_remap_all()` method

1. **Guard — no file:** If `self.original_content` is empty, show `messagebox.showwarning("No File", "Load a G-code file first.")` and return.
2. **Scan T numbers:** Use `re.findall(r'(?<!\d)T(\d+)(?!\d)', self.original_content, re.IGNORECASE)` to collect all T number tokens in document order. Deduplicate while preserving first-seen order.
3. **Build rules:** Assign sequential targets — first unique T# → 1, second → 2, etc. Omit any pair where `old == new` (already in the correct slot).
4. **Guard — no T numbers found:** If the scan returns no results, show `messagebox.showwarning("No T Numbers", "No T numbers found in file.")` and return.
5. **Guard — already sequential:** If all rules are no-ops (list is empty after step 3), show `messagebox.showinfo("Already Sequential", "Tools are already in sequential order.")` and return.
6. **Clear existing rules:** Clear `self.rules` and call `self.rules_list.delete(0, "end")`.
7. **Populate rules:** Append each `(old, new)` pair to `self.rules` and insert the display string `  T{old} → T{new}    (H{old}→H{new},  D{old}→D{new})` into `self.rules_list`, matching the format used by `_add_rule`.
8. **Trigger preview:** Call `self._preview()` directly.

---

## What is NOT changing

- Core remapping logic (`remap_line`, `remap_gcode`, `build_pattern`) — untouched.
- The manual Add Rule / Remove Selected workflow — unchanged.
- Save flow — works as normal using whatever is in `self.rules` after auto-remap.
- No new module-level functions are added.

---

## Edge Cases

| Situation | Behavior |
|---|---|
| No file loaded | Warning dialog, early return |
| File has no T numbers | Warning dialog, early return |
| All tools already sequential | Info dialog, early return |
| Some tools already in correct slot | Those pairs are skipped (no no-op rules added) |
| Existing manual rules present | Cleared silently before new rules are applied |

---

## Files Changed

- `gcode_tool_remapper.py` — only file modified. Changes:
  - Add `_auto_remap_all()` method to `RemapperApp`
  - Add "Auto Remap All" button wired to `_auto_remap_all` in `_build_ui`

# Test Suite — G-Code Tool Remapper

Run with:

```
python -m pytest test_gcode_remapper.py -v
```

48 tests, 4 test classes backed by real `.HAS` sample programs, plus 2 unit-test classes that exercise the core functions directly.

---

## Sample Files Used

| File | Program Name | Tools present | Why it was chosen |
|---|---|---|---|
| `O3012.HAS` | Cut Off Die Holder Top | T1, T7, T18 (×3 D18), T19 | T18 has T + H + D all used; T1/T18/T19 test exact-boundary isolation |
| `O3031.HAS` | Notching & Pilot Stripper | T20, T15 (×8 D15), T13 (×2 D13) | Largest number of D-register occurrences for a single tool; tests bulk D replacement |
| `O3020.HAS` | Large Punch Holder Main | T1, T2, T5, T6, T10 (D10), T11, T13 (×2 occ.), T20 | T10 has a D register; T13 appears twice deep in a long file; tests line-number reporting |
| `5400.HAS` | Qualifier/Straightener Base | T1–T7, non-zero-padded H values, T5 with ×4 D5 | Only file with unpadded H registers; best for multi-rule and full T+H+D single-digit coverage |

---

## TestBuildPattern — regex pattern construction

These tests exercise `build_pattern(prefix, number)` directly, before any file is loaded.

| Test | What it verifies |
|---|---|
| `test_matches_exact_token` | `T7` is found inside a typical G-code line (`N175 T7 M06`) |
| `test_no_match_when_trailing_digit` | `T1` pattern does **not** match `T18`, `T10`, or `T19` — the lookahead on digits works |
| `test_no_match_when_leading_digit` | `T5` pattern does **not** match `T55` |
| `test_matches_h_register` | `H18` is found correctly |
| `test_matches_d_register` | `D15` is found inside a cutter-comp line |
| `test_case_insensitive` | Lowercase `t3` is matched (flag `re.IGNORECASE` active) |

---

## TestRemapLine — single-line substitution logic

These tests call `remap_line(line, rules)` with hand-crafted strings to isolate individual behaviours.

| Test | What it verifies |
|---|---|
| `test_basic_substitution` | A simple `T1 M06` line becomes `T99 M06`; `changed` flag is `True` |
| `test_returns_false_when_no_match` | A coordinate-only line (`G00 X1.0 Y2.0`) returns `changed = False` and is unmodified |
| `test_t_h_d_all_remapped_by_one_rule` | A single rule `(18, 99)` updates `T18`, `H18`, and `D18` on the same line in one pass |
| `test_exact_boundary_no_partial_match` | `T10 T11 T18 T19 T21` is untouched when remapping `T1` — no token partially matches |
| `test_swap_no_cascade` | Rules `(1→2)` and `(2→1)` on `"T1 T2"` produce `"T2 T1"` — two-phase placeholder logic prevents cascading |
| `test_original_line_unchanged_object` | Input string is not mutated by `remap_line` |
| `test_comment_content_is_remapped` | Tool numbers inside Fanuc parenthesis comments are treated as plain text and **are** remapped (by design) |

---

## TestO3012 — Cut Off Die Holder Top (`O3012.HAS`)

This file has four tools. T18 is the most interesting: it uses a cutter-radius compensation `D18` register on three separate G42 lines, making it the primary file for testing D-register coverage and isolation between nearby tool numbers (T18 vs T19).

| Test | File lines checked | What it verifies |
|---|---|---|
| `test_t18_tool_select_remapped` | Line 62: `N315 T18 M06` | T register updated after remapping T18→T99 |
| `test_t18_h_register_remapped` | Line 67: `G43 Z0.1 H18` | H register updated in the same rule pass |
| `test_t18_d_register_first_occurrence_remapped` | Line 100: `G42 ... D18 F8.` | D register updated on first cutter-comp line |
| `test_t18_all_three_d18_lines_remapped` | Lines 100, 113, 126 | All three D18 cutter-comp lines update — none are skipped |
| `test_remap_t1_does_not_alter_t18` | Line 62 | Remapping T1 leaves T18 completely unchanged (trailing-digit boundary) |
| `test_remap_t1_does_not_alter_t19` | Line 139 | Remapping T1 leaves T19 unchanged |
| `test_remap_t18_does_not_alter_t1` | Line 9 | Remapping T18 leaves T1 unchanged |
| `test_remap_t18_does_not_alter_t19` | Line 139 | T18 and T19 are independent — remapping one never touches the other |
| `test_t1_tool_select_remapped` | Line 9: `N35 T1 M06` | Basic T1 update confirms single-digit tools work |
| `test_swap_t1_and_t7_tool_select_lines` | Lines 9 and 35 | Swap T1↔T7: original T1 line reads T7 and vice versa |
| `test_swap_t1_and_t7_no_cascade_artifacts` | Whole file | No `T77` or `T11` anywhere — confirms two-phase substitution prevents cascading |

---

## TestO3031 — Notching & Pilot Stripper (`O3031.HAS`)

T15 has 8 D-register appearances spread across the program — the highest D-register count in the test suite. This file validates that every occurrence is caught regardless of depth in a large file.

| Test | File lines checked | What it verifies |
|---|---|---|
| `test_t15_tool_select_remapped` | Line 3113 | T15 tool-select updated |
| `test_t15_h_register_remapped` | Line 3118 | H15 updated |
| `test_t15_all_eight_d15_lines_remapped` | Lines 3123, 3136, 3149, 3162, 3175, 3188, 3201, 3214 | All 8 D15 cutter-comp lines replaced — no occurrence is missed |
| `test_t15_does_not_affect_t13` | Line 3279 | Remapping T15 does not touch the adjacent T13 tool-change |
| `test_t20_tool_select_remapped` | Line 10 | T20 tool-select updated |
| `test_t20_h_register_remapped` | Line 15 | H20 updated |
| `test_no_changes_for_absent_tool` | Whole file | Remapping T99→T100 (tool not in file) returns an empty changed-line list |

---

## TestO3020 — Large Punch Holder Main (`O3020.HAS`)

The longest file in the suite. T10 carries a D10 register, and T13 appears twice — once early and once thousands of lines into the file — verifying that the remapper scans the entire file and reports line numbers correctly.

| Test | File lines checked | What it verifies |
|---|---|---|
| `test_t10_tool_select_remapped` | Line 7079 | T10 updated deep in a large file |
| `test_t10_h_register_remapped` | Line 7084 | H10 updated |
| `test_t10_d_register_remapped` | Line 7089 | D10 updated |
| `test_t10_does_not_affect_t20` | Line 38 | T20 survives a T10 remap — `T20` does not become `T990` |
| `test_t20_and_h20_remapped` | Lines 38, 43 | T20 and H20 both update when remapping T20 |
| `test_t13_both_occurrences_remapped` | Lines 54, 59, 3273, 3278 | T13 appears twice; at least 4 lines must be reported as changed |
| `test_changed_line_numbers_are_correct` | Lines 38, 43 | The returned changed-line list contains the correct 1-indexed line numbers |

---

## Test5400 — Qualifier/Straightener Base (`5400.HAS`)

The only file using non-zero-padded H registers (`H1`, `H2` … `H7` instead of `H01`). This makes it the right file for confirming H-register remapping on single-digit tools. T5 also has four D5 references, providing the same full-register coverage as T15 in O3031 but for a single-digit tool number.

| Test | File lines checked | What it verifies |
|---|---|---|
| `test_t1_tool_select_remapped` | Line 14: `N14 T1 M6` | Single-digit T register updated |
| `test_t1_h_register_remapped` | Line 19: `G43 Z0.1 H1` | Non-zero-padded H1 is matched and updated |
| `test_t5_tool_select_remapped` | Line 7466 | T5 updated |
| `test_t5_h_register_remapped` | Line 7471: `H5` | Non-padded H5 updated |
| `test_t5_all_four_d5_lines_remapped` | Lines 8584, 8595, 8606, 8617 | All 4 D5 cutter-comp lines updated |
| `test_t5_does_not_affect_t4_or_t6` | Lines 7440, 8628 | Adjacent tools T4 and T6 unchanged |
| `test_multi_rule_t1_t2_t3_all_remapped` | Lines 14/19, 46/51, 61/66 | Three rules applied simultaneously all take effect (T+H for each) |
| `test_multi_rule_no_cross_contamination` | Line 46 | When T1→T10 and T2→T20 run together, T2's line becomes T20 not T10 |
| `test_pure_coordinate_lines_unchanged` | Lines 22, 23 | Coordinate-only lines are byte-identical before and after remapping |
| `test_total_line_count_unchanged` | Whole file | Remapping never inserts or removes lines |

---

## Notable Behaviours Covered by Tests

| Behaviour | Test(s) that verify it |
|---|---|
| Exact-match boundary — `T1` never matches `T10`, `T18`, `T19` | `test_no_match_when_trailing_digit`, `test_exact_boundary_no_partial_match`, `test_remap_t1_does_not_alter_t18/t19`, `test_t10_does_not_affect_t20` |
| T, H, D registers all updated by one rule | `test_t_h_d_all_remapped_by_one_rule`, `test_t18_*`, `test_t15_*`, `test_t10_*`, `test_t5_*` |
| Two-phase substitution prevents cascading swaps | `test_swap_no_cascade`, `test_swap_t1_and_t7_*` |
| All D-register occurrences updated (not just the first) | `test_t18_all_three_d18_lines_remapped`, `test_t15_all_eight_d15_lines_remapped`, `test_t5_all_four_d5_lines_remapped` |
| Multiple rules run simultaneously without cross-contamination | `test_multi_rule_t1_t2_t3_all_remapped`, `test_multi_rule_no_cross_contamination` |
| Returned changed-line list is accurate | `test_changed_line_numbers_are_correct`, `test_no_changes_for_absent_tool` |
| Non-matching lines are preserved exactly | `test_returns_false_when_no_match`, `test_pure_coordinate_lines_unchanged`, `test_total_line_count_unchanged` |
| Comments (parenthesis content) are remapped like any other text | `test_comment_content_is_remapped` |

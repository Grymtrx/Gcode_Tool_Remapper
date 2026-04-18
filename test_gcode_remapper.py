"""
Tests for G-Code Tool Remapper core logic.
Uses real .HAS sample programs from Test Sample Files/.

Run with:  python -m pytest test_gcode_remapper.py -v
Requires:  pip install pytest
"""

import os
import pytest
from gcode_tool_remapper import build_pattern, remap_line, remap_gcode, auto_build_rules

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "Test Sample Files")


def load(filename: str) -> str:
    path = os.path.join(SAMPLES_DIR, filename)
    with open(path, "r", encoding="latin-1", errors="replace") as fh:
        return fh.read()


# ─────────────────────────────────────────────────────────────────────────────
#  build_pattern — unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildPattern:

    def test_matches_exact_token(self):
        p = build_pattern("T", 7)
        assert p.search("N175 T7 M06")

    def test_no_match_when_trailing_digit(self):
        """T1 must not match T10, T18, T19."""
        p = build_pattern("T", 1)
        assert not p.search("T18")
        assert not p.search("T10")
        assert not p.search("T19")

    def test_no_match_when_leading_digit(self):
        """T5 must not match inside T55."""
        p = build_pattern("T", 5)
        assert not p.search("T55")

    def test_matches_h_register(self):
        p = build_pattern("H", 18)
        assert p.search("G43 Z0.1 H18")

    def test_matches_d_register(self):
        p = build_pattern("D", 15)
        assert p.search("G42 X1.82 Y-4.225 D15")

    def test_case_insensitive(self):
        p = build_pattern("T", 3)
        assert p.search("t3 M06")

    def test_matches_zero_padded_h_register(self):
        """H01 must match when remapping tool number 1 (leading zero is common in Haas programs)."""
        p = build_pattern("H", 1)
        assert p.search("G43 Z0.1 H01")

    def test_matches_zero_padded_h_two_digit(self):
        """H06 must match when remapping tool number 6."""
        p = build_pattern("H", 6)
        assert p.search("G43 Z0.1 H06")

    def test_zero_padded_does_not_match_longer_number(self):
        """H010 must NOT match when remapping tool 1 — trailing digit boundary holds."""
        p = build_pattern("H", 1)
        assert not p.search("H010")

    def test_zero_padded_does_not_match_different_number(self):
        """H016 must NOT match when remapping tool 6."""
        p = build_pattern("H", 6)
        assert not p.search("H016")


# ─────────────────────────────────────────────────────────────────────────────
#  remap_line — unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRemapLine:

    def test_basic_substitution(self):
        line = "N35 T1 M06\n"
        result, changed = remap_line(line, [(1, 99)])
        assert "T99" in result
        assert changed is True

    def test_returns_false_when_no_match(self):
        line = "G00 X1.0 Y2.0\n"
        result, changed = remap_line(line, [(7, 99)])
        assert result == line
        assert changed is False

    def test_t_h_d_all_remapped_by_one_rule(self):
        """A single rule must update T, H, and D in the same pass."""
        line = "T18 H18 D18\n"
        result, changed = remap_line(line, [(18, 99)])
        assert "T99" in result
        assert "H99" in result
        assert "D99" in result
        assert changed is True

    def test_exact_boundary_no_partial_match(self):
        """Remapping T1 must not alter T10, T11, T18, T19, T21."""
        line = "T10 T11 T18 T19 T21\n"
        result, changed = remap_line(line, [(1, 99)])
        assert result == line
        assert changed is False

    def test_swap_no_cascade(self):
        """Two-phase logic: T1→T2 and T2→T1 on the same line must not cascade."""
        line = "T1 T2\n"
        result, _ = remap_line(line, [(1, 2), (2, 1)])
        # Both must swap cleanly — no T11 or T22 corruption
        assert result.strip() == "T2 T1"

    def test_original_line_unchanged_object(self):
        """remap_line must not mutate the input string."""
        line = "N10 T5 M06\n"
        original = line
        remap_line(line, [(5, 50)])
        assert line == original

    def test_comment_content_is_remapped(self):
        """Tool numbers inside parentheses (Fanuc comments) are treated as plain text
        and are also remapped — the remapper does not skip comments."""
        line = "(T5 D=0.1875 CR=0. - end mill)\n"
        result, changed = remap_line(line, [(5, 55)])
        assert "T55" in result
        assert changed is True

    def test_zero_padded_h_register_remapped(self):
        """H01 must be remapped when the rule targets tool number 1.
        This is the critical safety case: Haas programs commonly write H01/H06
        even when the tool number is a single digit."""
        line = "N19 G43 Z0.1 H01\n"
        result, changed = remap_line(line, [(1, 99)])
        assert "H99" in result
        assert "H01" not in result
        assert changed is True

    def test_zero_padded_h_does_not_bleed_to_adjacent_number(self):
        """H010 must not be matched when remapping tool 1 (boundary safety)."""
        line = "G43 Z0.1 H010\n"
        result, changed = remap_line(line, [(1, 99)])
        assert result == line
        assert changed is False


# ─────────────────────────────────────────────────────────────────────────────
#  O3012.HAS — CUT OFF DIE HOLDER TOP PROGRAM
#  Tools: T1 (spot drill), T7 (parabolic drill), T18 (end mill w/ D), T19 (insert)
# ─────────────────────────────────────────────────────────────────────────────

class TestO3012:

    @pytest.fixture(scope="class")
    def content(self):
        return load("O3012.HAS")

    # ── T18 remapping: T, H, D all update ────────────────────────────────────

    def test_t18_tool_select_remapped(self, content):
        """Line 62 — N315 T18 M06 → N315 T99 M06"""
        new, _ = remap_gcode(content, [(18, 99)])
        line = new.splitlines()[61]
        assert "T99" in line
        assert "T18" not in line

    def test_t18_h_register_remapped(self, content):
        """Line 67 — G43 Z0.1 H18 → G43 Z0.1 H99"""
        new, _ = remap_gcode(content, [(18, 99)])
        line = new.splitlines()[66]
        assert "H99" in line
        assert "H18" not in line

    def test_t18_d_register_first_occurrence_remapped(self, content):
        """Line 100 — D18 F8. → D99 F8.  (first cutter-comp line)"""
        new, _ = remap_gcode(content, [(18, 99)])
        line = new.splitlines()[99]
        assert "D99" in line
        assert "D18" not in line

    def test_t18_all_three_d18_lines_remapped(self, content):
        """D18 appears on lines 100, 113, 126 — all three must update."""
        new, _ = remap_gcode(content, [(18, 99)])
        lines = new.splitlines()
        for idx in (99, 112, 125):
            assert "D99" in lines[idx], f"D18 not remapped on file line {idx + 1}"
            assert "D18" not in lines[idx], f"D18 still present on file line {idx + 1}"

    # ── Exact-match boundary: T1 and T18/T19 are independent ─────────────────

    def test_remap_t1_does_not_alter_t18(self, content):
        """Remapping T1→T99 must leave T18 intact (T18 contains a trailing digit)."""
        new, _ = remap_gcode(content, [(1, 99)])
        line = new.splitlines()[61]  # Line 62: T18 M06
        assert "T18" in line
        assert "T988" not in line    # would indicate a double-sub accident

    def test_remap_t1_does_not_alter_t19(self, content):
        """Remapping T1→T99 must leave T19 intact."""
        new, _ = remap_gcode(content, [(1, 99)])
        line = new.splitlines()[138]  # Line 139: T19 M06
        assert "T19" in line

    def test_remap_t18_does_not_alter_t1(self, content):
        """Remapping T18→T99 must leave the T1 tool-select line unchanged."""
        new, _ = remap_gcode(content, [(18, 99)])
        line = new.splitlines()[8]  # Line 9: T1 M06
        assert "T1 " in line

    def test_remap_t18_does_not_alter_t19(self, content):
        """T18 and T19 are distinct — remapping one must not touch the other."""
        new, _ = remap_gcode(content, [(18, 99)])
        line = new.splitlines()[138]  # Line 139: T19 M06
        assert "T19" in line
        assert "T99" not in line

    # ── T1 tool-select line ───────────────────────────────────────────────────

    def test_t1_h01_zero_padded_remapped(self, content):
        """Line 14 — G43 Z0.1 H01 must update when remapping T1.
        H01 is zero-padded; previously the pattern failed to match it."""
        new, _ = remap_gcode(content, [(1, 99)])
        line = new.splitlines()[13]
        assert "H99" in line
        assert "H01" not in line

    def test_t7_h07_zero_padded_remapped(self, content):
        """Line 40 — G43 Z0.1 H07 must update when remapping T7."""
        new, _ = remap_gcode(content, [(7, 99)])
        line = new.splitlines()[39]
        assert "H99" in line
        assert "H07" not in line

    def test_t1_tool_select_remapped(self, content):
        """Line 9 — N35 T1 M06 → N35 T99 M06"""
        new, _ = remap_gcode(content, [(1, 99)])
        line = new.splitlines()[8]
        assert "T99" in line

    # ── Two-phase swap: T1 ↔ T7 ──────────────────────────────────────────────

    def test_swap_t1_and_t7_tool_select_lines(self, content):
        """Line 9 (was T1) must become T7; line 35 (was T7) must become T1."""
        new, _ = remap_gcode(content, [(1, 7), (7, 1)])
        lines = new.splitlines()
        assert "T7" in lines[8]   # originally T1
        assert "T1" in lines[34]  # originally T7

    def test_swap_t1_and_t7_no_cascade_artifacts(self, content):
        """No cascading: no T77 (T7→T1 then T1→T7 again) or T11 must appear."""
        new, _ = remap_gcode(content, [(1, 7), (7, 1)])
        assert "T77" not in new
        assert "T11" not in new


# ─────────────────────────────────────────────────────────────────────────────
#  O3031.HAS — NOTCHING & PILOT STRIPPER
#  Tools: T20 (insert end mill), T15 (end mill w/ 8× D15), T13 (end mill w/ D13)
# ─────────────────────────────────────────────────────────────────────────────

class TestO3031:

    @pytest.fixture(scope="class")
    def content(self):
        return load("O3031.HAS")

    # ── T15: tool with the most D-register appearances ────────────────────────

    def test_t15_tool_select_remapped(self, content):
        """Line 3113 — N3118 T15 M06 → T50 M06"""
        new, _ = remap_gcode(content, [(15, 50)])
        line = new.splitlines()[3112]
        assert "T50" in line
        assert "T15" not in line

    def test_t15_h_register_remapped(self, content):
        """Line 3118 — G43 Z0.2 H15 → H50"""
        new, _ = remap_gcode(content, [(15, 50)])
        line = new.splitlines()[3117]
        assert "H50" in line
        assert "H15" not in line

    def test_t15_all_eight_d15_lines_remapped(self, content):
        """D15 appears on 8 separate cutter-comp lines — every one must update."""
        new, _ = remap_gcode(content, [(15, 50)])
        lines = new.splitlines()
        # Lines 3123, 3136, 3149, 3162, 3175, 3188, 3201, 3214 (1-indexed)
        for idx in (3122, 3135, 3148, 3161, 3174, 3187, 3200, 3213):
            assert "D50" in lines[idx], f"D15 not remapped on file line {idx + 1}"
            assert "D15" not in lines[idx], f"D15 still present on file line {idx + 1}"

    def test_t15_does_not_affect_t13(self, content):
        """Remapping T15→T50 must leave T13 on line 3279 intact."""
        new, _ = remap_gcode(content, [(15, 50)])
        line = new.splitlines()[3278]
        assert "T13" in line

    # ── T20 remapping ─────────────────────────────────────────────────────────

    def test_t20_tool_select_remapped(self, content):
        """Line 10 — N14 T20 M06 → T99 M06"""
        new, _ = remap_gcode(content, [(20, 99)])
        line = new.splitlines()[9]
        assert "T99" in line
        assert "T20" not in line

    def test_t20_h_register_remapped(self, content):
        """Line 15 — G43 Z0.25 H20 → H99"""
        new, _ = remap_gcode(content, [(20, 99)])
        line = new.splitlines()[14]
        assert "H99" in line
        assert "H20" not in line

    # ── Absent tool: zero changed lines ───────────────────────────────────────

    def test_no_changes_for_absent_tool(self, content):
        """Remapping T99→T100 (tool absent from file) must produce zero changed lines."""
        _, changed = remap_gcode(content, [(99, 100)])
        assert changed == []


# ─────────────────────────────────────────────────────────────────────────────
#  O3020.HAS — LARGE PUNCH HOLDER MAIN PROGRAM
#  Tools: T1, T2, T5, T6, T10 (with D10), T11, T13 (×2), T20
# ─────────────────────────────────────────────────────────────────────────────

class TestO3020:

    @pytest.fixture(scope="class")
    def content(self):
        return load("O3020.HAS")

    # ── T10: multi-digit tool with D register ─────────────────────────────────

    def test_t10_tool_select_remapped(self, content):
        """Line 7079 — N7085 T10 M06 → T99 M06"""
        new, _ = remap_gcode(content, [(10, 99)])
        line = new.splitlines()[7078]
        assert "T99" in line
        assert "T10" not in line

    def test_t10_h_register_remapped(self, content):
        """Line 7084 — G43 Z0.1 H10 → H99"""
        new, _ = remap_gcode(content, [(10, 99)])
        line = new.splitlines()[7083]
        assert "H99" in line
        assert "H10" not in line

    def test_t10_d_register_remapped(self, content):
        """Line 7089 — G42 D10 F13. → D99 F13."""
        new, _ = remap_gcode(content, [(10, 99)])
        line = new.splitlines()[7088]
        assert "D99" in line
        assert "D10" not in line

    def test_t1_h01_zero_padded_remapped(self, content):
        """Line 21 — G43 Z0.1 H01 must update when remapping T1.
        This is the exact line reported as broken: H01 is zero-padded."""
        new, _ = remap_gcode(content, [(1, 99)])
        line = new.splitlines()[20]
        assert "H99" in line
        assert "H01" not in line

    def test_t6_h06_zero_padded_remapped(self, content):
        """Line 7141 — G43 Z0.1 H06 must update when remapping T6.
        This is the second line reported as broken: H06 is zero-padded."""
        new, _ = remap_gcode(content, [(6, 99)])
        line = new.splitlines()[7140]
        assert "H99" in line
        assert "H06" not in line

    def test_t2_h02_zero_padded_remapped(self, content):
        """Line 7111 — G43 Z0.1 H02 must update when remapping T2."""
        new, _ = remap_gcode(content, [(2, 99)])
        line = new.splitlines()[7110]
        assert "H99" in line
        assert "H02" not in line

    def test_t10_does_not_affect_t20(self, content):
        """T20 (line 38) must not be touched when remapping T10."""
        new, _ = remap_gcode(content, [(10, 99)])
        line = new.splitlines()[37]
        assert "T20" in line
        assert "T990" not in new  # T20 would become T990 if boundary failed

    # ── T20 ───────────────────────────────────────────────────────────────────

    def test_t20_and_h20_remapped(self, content):
        new, _ = remap_gcode(content, [(20, 55)])
        lines = new.splitlines()
        assert "T55" in lines[37]   # Line 38: T20 M06
        assert "H55" in lines[42]   # Line 43: H20

    # ── T13 appears twice deep in the file ───────────────────────────────────

    def test_t13_both_occurrences_remapped(self, content):
        """T13 and H13 appear twice each (lines 54/59 and 3273/3278).
        All four lines must be flagged as changed."""
        _, changed = remap_gcode(content, [(13, 88)])
        assert len(changed) >= 4

    # ── changed_lines list accuracy ───────────────────────────────────────────

    def test_changed_line_numbers_are_correct(self, content):
        """remap_gcode must report the exact 1-indexed line numbers that changed."""
        _, changed = remap_gcode(content, [(20, 55)])
        assert 38 in changed   # T20 M06
        assert 43 in changed   # H20


# ─────────────────────────────────────────────────────────────────────────────
#  5400.HAS — QUALIFIER/STRAIGHTENER BASE
#  Tools T1–T7, all with non-zero-padded H registers.
#  T5 has four D5 references — best file for full T+H+D single-digit coverage.
# ─────────────────────────────────────────────────────────────────────────────

class Test5400:

    @pytest.fixture(scope="class")
    def content(self):
        return load("5400.HAS")

    # ── T1 and H1 (non-padded) ────────────────────────────────────────────────

    def test_t1_tool_select_remapped(self, content):
        """Line 14 — N14 T1 M6 → T10 M6"""
        new, _ = remap_gcode(content, [(1, 10)])
        line = new.splitlines()[13]
        assert "T10" in line
        assert "T1 " not in line

    def test_t1_h_register_remapped(self, content):
        """Line 19 — G43 Z0.1 H1 → H10  (non-zero-padded register)"""
        new, _ = remap_gcode(content, [(1, 10)])
        line = new.splitlines()[18]
        assert "H10" in line
        assert "H1" not in line.replace("H10", "")  # H1 itself gone

    # ── T5: full T + H + D (four D5 lines) ───────────────────────────────────

    def test_t5_tool_select_remapped(self, content):
        """Line 7466 — N7474 T5 M6 → T55 M6"""
        new, _ = remap_gcode(content, [(5, 55)])
        line = new.splitlines()[7465]
        assert "T55" in line
        assert "T5 " not in line

    def test_t5_h_register_remapped(self, content):
        """Line 7471 — G43 Z0.1 H5 → H55"""
        new, _ = remap_gcode(content, [(5, 55)])
        line = new.splitlines()[7470]
        assert "H55" in line

    def test_t5_all_four_d5_lines_remapped(self, content):
        """D5 appears on lines 8584, 8595, 8606, 8617 — all must update to D55."""
        new, _ = remap_gcode(content, [(5, 55)])
        lines = new.splitlines()
        for idx in (8583, 8594, 8605, 8616):
            assert "D55" in lines[idx], f"D5 not remapped on file line {idx + 1}"
            assert "D5 " not in lines[idx], f"D5 still present on file line {idx + 1}"

    def test_t5_does_not_affect_t4_or_t6(self, content):
        """T4 (line 7440) and T6 (line 8628) must be untouched."""
        new, _ = remap_gcode(content, [(5, 55)])
        lines = new.splitlines()
        assert "T4 " in lines[7439]   # Line 7440: N7445 T4 M6
        assert "T6 " in lines[8627]   # Line 8628: N8645 T6 M6

    # ── Multi-rule: three tools simultaneously ────────────────────────────────

    def test_multi_rule_t1_t2_t3_all_remapped(self, content):
        """Applying T1→T10, T2→T20, T3→T30 in one pass must update all three tools."""
        new, _ = remap_gcode(content, [(1, 10), (2, 20), (3, 30)])
        lines = new.splitlines()
        assert "T10" in lines[13]   # Line 14: T1 M6
        assert "H10" in lines[18]   # Line 19: H1
        assert "T20" in lines[45]   # Line 46: T2 M6
        assert "H20" in lines[50]   # Line 51: H2
        assert "T30" in lines[60]   # Line 61: T3 M6
        assert "H30" in lines[65]   # Line 66: H3

    def test_multi_rule_no_cross_contamination(self, content):
        """T2 must become T20, not be confused with the T1→T10 expansion."""
        new, _ = remap_gcode(content, [(1, 10), (2, 20)])
        lines = new.splitlines()
        t2_line = lines[45]   # Line 46: originally T2 M6
        assert "T20" in t2_line
        assert "T10" not in t2_line

    # ── Unchanged lines are preserved ─────────────────────────────────────────

    def test_pure_coordinate_lines_unchanged(self, content):
        """Lines containing only coordinates (no T/H/D tokens) must be identical
        before and after remapping."""
        orig = content.splitlines()
        new, _ = remap_gcode(content, [(1, 99)])
        new_lines = new.splitlines()
        # Line 22 (idx 21): N22 G98 G81 X14.0625 Y-5.6875 Z-0.0625 R0.1 F12.
        assert orig[21] == new_lines[21]
        # Line 70 (idx 69): G43 Z0.1104 H3 — this line HAS H3, so it WILL change.
        # Instead sample a deep coordinate-only line
        assert orig[22] == new_lines[22]   # Line 23: X14.75

    def test_total_line_count_unchanged(self, content):
        """Remapping must never add or remove lines."""
        orig_count = len(content.splitlines())
        new, _ = remap_gcode(content, [(1, 99), (2, 88), (5, 55)])
        assert len(new.splitlines()) == orig_count


# ─────────────────────────────────────────────────────────────────────────────
#  auto_build_rules — unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoRemap:

    def test_sequential_from_first_appearance(self):
        """T numbers are renumbered in the order they first appear."""
        content = "T5 M06\nT2 M06\nT8 M06\n"
        rules = auto_build_rules(content)
        # T5 first → slot 1 (rule needed), T2 second → slot 2 (no-op, omitted), T8 third → slot 3 (rule needed)
        assert rules == [(5, 1), (8, 3)]

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
        # t5 first → slot 1 (rule needed), t2 second → slot 2 (no-op, omitted)
        assert rules == [(5, 1)]

    def test_exact_boundary_t1_not_found_in_t10(self):
        """T10 must not be treated as a T1 occurrence when scanning."""
        content = "T10 M06\nT2 M06\n"
        rules = auto_build_rules(content)
        # T10 is slot 1 (rule needed), T2 is slot 2 (no-op, omitted)
        assert rules == [(10, 1)]

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

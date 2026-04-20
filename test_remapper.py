"""
Tests for gcode_tool_remapper.py

Unit tests: build_pattern, remap_line, remap_gcode, auto_build_rules
Integration tests: every file in 'Test Sample Files/' directory
"""

import re
import os
import glob
import pytest

from gcode_tool_remapper import build_pattern, remap_line, remap_gcode, auto_build_rules

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "Test Sample Files")
SAMPLE_FILES = glob.glob(os.path.join(SAMPLE_DIR, "*.HAS")) + \
               glob.glob(os.path.join(SAMPLE_DIR, "*.nc"))

# ─────────────────────────────────────────────────────────────────────────────
# build_pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildPattern:
    def test_matches_exact(self):
        p = build_pattern('T', 1)
        assert p.search('T1 M06')

    def test_no_match_prefix_digit(self):
        """T201 should NOT match a rule for T1."""
        p = build_pattern('T', 1)
        assert not p.search('T201')

    def test_no_match_suffix_digit(self):
        """T10 should NOT match a rule for T1."""
        p = build_pattern('T', 1)
        assert not p.search('T10')

    def test_matches_with_leading_zeros(self):
        """H01 should match a rule for tool 1 (leading zeros are stripped)."""
        p = build_pattern('H', 1)
        assert p.search('H01')

    def test_matches_zero_padded_multi(self):
        p = build_pattern('D', 7)
        assert p.search('D07')

    def test_case_insensitive(self):
        p = build_pattern('T', 5)
        assert p.search('t5')

    def test_matches_at_line_start(self):
        p = build_pattern('T', 3)
        assert p.search('T3M06')

    def test_no_match_in_comment_number(self):
        """Number like 1.175 must not match T1 or H1."""
        p = build_pattern('T', 175)
        # The Y-coord -1.175 should NOT match T175
        assert not p.search('Y-1.175')

    def test_h_prefix(self):
        p = build_pattern('H', 7)
        assert p.search('H07')
        assert not p.search('H70')

    def test_d_prefix(self):
        p = build_pattern('D', 2)
        assert p.search('D2')
        assert not p.search('D20')


# ─────────────────────────────────────────────────────────────────────────────
# remap_line
# ─────────────────────────────────────────────────────────────────────────────

class TestRemapLine:
    def test_basic_remap(self):
        line = 'N35 T1 M06\n'
        result, changed = remap_line(line, [(1, 5)])
        assert result == 'N35 T5 M06\n'
        assert changed

    def test_t_h_d_remapped_together(self):
        """T, H, and D with same number all get remapped."""
        line = 'T2 M06  G43 H2  D2\n'
        result, changed = remap_line(line, [(2, 9)])
        assert result == 'T9 M06  G43 H9  D9\n'
        assert changed

    def test_two_phase_swap(self):
        """T1->T2 and T2->T1 simultaneously must not cascade."""
        line = 'T1 ... T2\n'
        result, changed = remap_line(line, [(1, 2), (2, 1)])
        assert result == 'T2 ... T1\n'
        assert changed

    def test_no_change_when_no_match(self):
        line = 'N100 G00 X1.5 Y2.3\n'
        result, changed = remap_line(line, [(1, 5)])
        assert result == line
        assert not changed

    def test_leading_zero_in_h_register(self):
        """H01 should remap when rule is for tool 1."""
        line = 'G43 Z0.1 H01\n'
        result, changed = remap_line(line, [(1, 7)])
        assert 'H7' in result
        assert changed

    def test_no_partial_match(self):
        """T10 rule must not affect T100 or T101."""
        line = 'T10 M06  T100 M06\n'
        result, _ = remap_line(line, [(10, 3)])
        assert 'T3 ' in result       # T10 → T3
        assert 'T100' in result      # T100 untouched

    def test_no_placeholder_leakage(self):
        """After remapping, no NUL bytes should remain in output."""
        line = 'T5 M06 H05 D5\n'
        result, _ = remap_line(line, [(5, 10)])
        assert '\x00' not in result

    def test_unchanged_line_returns_original(self):
        line = 'G00 X0. Y0.\n'
        result, changed = remap_line(line, [(3, 7)])
        assert result == line
        assert not changed

    def test_multiple_tools_same_line(self):
        """Multiple distinct tool refs on one line all get remapped."""
        line = 'T1 T2 T3\n'
        result, changed = remap_line(line, [(1, 10), (2, 20), (3, 30)])
        assert result == 'T10 T20 T30\n'
        assert changed

    def test_comment_with_tool_number_in_parens(self):
        """Tool numbers inside G-code comments (parentheses) should still remap
        since G-code comments are plain text — the remapper is text-based."""
        line = '(TOOL 1 IS A DRILL)\n'
        result, _ = remap_line(line, [(1, 5)])
        # Just verify no crash and no placeholder leakage
        assert '\x00' not in result


# ─────────────────────────────────────────────────────────────────────────────
# remap_gcode
# ─────────────────────────────────────────────────────────────────────────────

class TestRemapGcode:
    def test_returns_changed_line_numbers(self):
        content = "T1 M06\nG00 X0\nT2 M06\n"
        _, changed = remap_gcode(content, [(1, 10), (2, 20)])
        assert 1 in changed
        assert 3 in changed
        assert 2 not in changed

    def test_unchanged_lines_preserved(self):
        content = "G00 X0 Y0\nT1 M06\nM30\n"
        new, _ = remap_gcode(content, [(1, 5)])
        lines = new.splitlines()
        assert lines[0] == 'G00 X0 Y0'
        assert lines[2] == 'M30'

    def test_content_roundtrip_with_inverse_rules(self):
        """Remapping then reverse-remapping recovers the original.
        Note: the remapper strips leading zeros when writing targets (H03 → H3),
        so the test content must not use leading zeros to get exact equality."""
        content = "T3 M06 H3\nT7 M06 H7\n"
        rules = [(3, 1), (7, 2)]
        remapped, _ = remap_gcode(content, rules)
        inverse = [(new, old) for old, new in rules]
        recovered, _ = remap_gcode(remapped, inverse)
        assert recovered == content

    def test_no_placeholder_leakage_multiline(self):
        content = "T1 M06\nT2 M06\nT1\n"
        result, _ = remap_gcode(content, [(1, 2), (2, 1)])
        assert '\x00' not in result

    def test_empty_content(self):
        result, changed = remap_gcode("", [(1, 2)])
        assert result == ""
        assert changed == []

    def test_line_count_preserved(self):
        content = "T1 M06\nG00 X0\nT2 M06\nM30\n"
        new, _ = remap_gcode(content, [(1, 5), (2, 6)])
        assert new.count('\n') == content.count('\n')


# ─────────────────────────────────────────────────────────────────────────────
# auto_build_rules
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoBuildRules:
    def test_sequential_already(self):
        """T1, T2, T3 in order → no rules needed."""
        rules = auto_build_rules("T1 M06\nT2 M06\nT3 M06\n")
        assert rules == []

    def test_out_of_order(self):
        rules = auto_build_rules("T5 M06\nT3 M06\n")
        assert (5, 1) in rules
        assert (3, 2) in rules

    def test_no_t_numbers(self):
        rules = auto_build_rules("G00 X0 Y0\nM30\n")
        assert rules == []

    def test_duplicates_only_appear_once(self):
        """Same T number appearing multiple times counts as one tool."""
        rules = auto_build_rules("T5 M06\nT5\nT5 D5\nT3 M06\n")
        sources = [old for old, _ in rules]
        assert sources.count(5) == 1

    def test_no_noop_rules(self):
        """Rules where old==new must be excluded."""
        rules = auto_build_rules("T1 M06\nT3 M06\nT2 M06\n")
        for old, new in rules:
            assert old != new

    def test_result_is_sequential(self):
        """After applying rules, tools should appear as 1, 2, 3, ..."""
        content = "T7 M06\nT3 M06\nT12 M06\n"
        rules = auto_build_rules(content)
        new_content, _ = remap_gcode(content, rules)
        found = []
        for m in re.finditer(r'(?<!\d)T(\d+)(?!\d)', new_content, re.IGNORECASE):
            n = int(m.group(1))
            if n not in found:
                found.append(n)
        assert found == list(range(1, len(found) + 1))

    def test_single_tool_no_rule_needed(self):
        rules = auto_build_rules("T1 M06\nT1\n")
        assert rules == []

    def test_single_tool_nonsequential(self):
        rules = auto_build_rules("T5 M06\nT5\n")
        assert rules == [(5, 1)]


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — all sample files
# ─────────────────────────────────────────────────────────────────────────────

def _read_file(path):
    """Read with latin-1 to avoid encoding errors on any file."""
    with open(path, 'r', encoding='latin-1', errors='replace') as f:
        return f.read()


def _tool_call_count(content):
    """Count T[digit]+ M06 (tool change) patterns — case-insensitive."""
    return len(re.findall(r'(?<!\d)T\d+(?!\d)\s+M06', content, re.IGNORECASE))


def _extract_tools_in_order(content):
    seen = []
    for m in re.finditer(r'(?<!\d)T(\d+)(?!\d)', content, re.IGNORECASE):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


@pytest.mark.parametrize("filepath", SAMPLE_FILES, ids=lambda p: os.path.basename(p))
class TestSampleFiles:
    def test_loads_without_error(self, filepath):
        """File must be readable."""
        content = _read_file(filepath)
        assert isinstance(content, str)

    def test_auto_remap_no_crash(self, filepath):
        """auto_build_rules + remap_gcode must not raise."""
        content = _read_file(filepath)
        rules = auto_build_rules(content)
        new_content, _ = remap_gcode(content, rules)
        assert isinstance(new_content, str)

    def test_no_placeholder_leakage(self, filepath):
        """No NUL bytes must appear in output after remapping."""
        content = _read_file(filepath)
        rules = auto_build_rules(content)
        new_content, _ = remap_gcode(content, rules)
        assert '\x00' not in new_content

    def test_tool_change_count_preserved(self, filepath):
        """Number of T[digit]+ M06 calls must be identical after remapping."""
        content = _read_file(filepath)
        rules = auto_build_rules(content)
        new_content, _ = remap_gcode(content, rules)
        assert _tool_call_count(new_content) == _tool_call_count(content)

    def test_output_tools_are_sequential(self, filepath):
        """After auto-remap, tool numbers must start at 1 and be contiguous."""
        content = _read_file(filepath)
        rules = auto_build_rules(content)
        if not rules:
            pytest.skip("No remapping needed — tools already sequential or no T numbers")
        new_content, _ = remap_gcode(content, rules)
        tools = _extract_tools_in_order(new_content)
        if not tools:
            pytest.skip("No T numbers in file")
        assert tools == list(range(1, len(tools) + 1)), \
            f"Expected sequential tools 1..{len(tools)}, got {tools}"

    def test_line_count_unchanged(self, filepath):
        """Remapping must not add or remove lines."""
        content = _read_file(filepath)
        rules = auto_build_rules(content)
        new_content, _ = remap_gcode(content, rules)
        assert new_content.count('\n') == content.count('\n')

    def test_roundtrip_with_inverse_rules(self, filepath):
        """Remapping then reverse-remapping must recover the same tool order.
        Exact string equality is not expected because the remapper strips
        leading zeros from H/D values (H01 → H1) by design."""
        content = _read_file(filepath)
        rules = auto_build_rules(content)
        if not rules:
            pytest.skip("No remapping needed")
        remapped, _ = remap_gcode(content, rules)
        inverse = [(new, old) for old, new in rules]
        recovered, _ = remap_gcode(remapped, inverse)
        assert _extract_tools_in_order(recovered) == _extract_tools_in_order(content), \
            "Round-trip failed: tool sequence after inverse remap differs from original"

    def test_manual_remap_no_placeholder_leakage(self, filepath):
        """Manual rules (swap T_a<->T_b) must not leak placeholders."""
        content = _read_file(filepath)
        tools = _extract_tools_in_order(content)
        if len(tools) < 2:
            pytest.skip("Need at least 2 tools for swap test")
        swap_rules = [(tools[0], tools[1]), (tools[1], tools[0])]
        new_content, _ = remap_gcode(content, swap_rules)
        assert '\x00' not in new_content

    def test_manual_swap_reverses_correctly(self, filepath):
        """Swapping T_a<->T_b and then swapping again must recover the original
        tool order. Leading zeros are not preserved by design, so only the
        tool sequence is compared."""
        content = _read_file(filepath)
        tools = _extract_tools_in_order(content)
        if len(tools) < 2:
            pytest.skip("Need at least 2 tools for swap test")
        swap_rules = [(tools[0], tools[1]), (tools[1], tools[0])]
        swapped, _ = remap_gcode(content, swap_rules)
        recovered, _ = remap_gcode(swapped, swap_rules)
        assert _extract_tools_in_order(recovered) == tools, \
            "Double-swap did not recover original tool order"

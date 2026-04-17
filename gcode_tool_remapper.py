"""
G-Code Tool Number Remapper
Remaps T, H, and D registers together with exact-match precision.
Usage: python gcode_tool_remapper.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import re
import os


# ─────────────────────────────────────────────
#  Core remapping logic
# ─────────────────────────────────────────────

def build_pattern(prefix, number):
    """
    Build a regex that matches e.g. T20 but NOT T201 or T520.
    Uses negative lookbehind/lookahead for digits.
    """
    return re.compile(
        rf'(?<!\d){re.escape(prefix)}{re.escape(str(number))}(?!\d)',
        re.IGNORECASE
    )


def remap_line(line, rules):
    """
    Apply all remapping rules to a single line.
    Rules are processed largest-number-first to avoid cascading replacements.
    Returns (new_line, changed: bool)
    """
    new_line = line
    for old_num, new_num in rules:
        for prefix in ('T', 'H', 'D'):
            pattern = build_pattern(prefix, old_num)
            replacement = f'{prefix}{new_num}'
            new_line = pattern.sub(replacement, new_line)
    return new_line, new_line != line


def remap_gcode(content, rules):
    """
    Remap all tool/offset references in a G-code string.
    Rules: list of (old_num: int, new_num: int)
    Sorts rules so larger numbers are replaced first (avoids T2 matching inside T20).
    Returns (new_content, changed_lines: list of int)
    """
    sorted_rules = sorted(rules, key=lambda r: r[0], reverse=True)
    lines = content.splitlines(keepends=True)
    out_lines = []
    changed_lines = []

    for i, line in enumerate(lines, start=1):
        new_line, changed = remap_line(line, sorted_rules)
        out_lines.append(new_line)
        if changed:
            changed_lines.append(i)

    return ''.join(out_lines), changed_lines


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────

class RemapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("G-Code Tool Remapper")
        self.resizable(True, True)
        self.minsize(720, 560)
        self.configure(bg="#f5f5f5")

        self.file_path = tk.StringVar(value="")
        self.rules = []          # list of (old_num, new_num)
        self.original_content = ""

        self._build_ui()

    # ── Layout ──────────────────────────────

    def _build_ui(self):
        pad = dict(padx=10, pady=6)

        # ── File picker ─────────────────────
        file_frame = tk.LabelFrame(self, text="  G-Code File  ", bg="#f5f5f5",
                                   font=("Segoe UI", 9, "bold"), fg="#333")
        file_frame.pack(fill="x", **pad)

        tk.Entry(file_frame, textvariable=self.file_path, width=60,
                 relief="flat", bg="white", bd=1,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 4), pady=6, fill="x", expand=True)

        tk.Button(file_frame, text="Browse…", command=self._browse,
                  relief="flat", bg="#e0e0e0", activebackground="#c8c8c8",
                  font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=(0, 6), pady=6)

        # ── Rules table ─────────────────────
        rules_frame = tk.LabelFrame(self, text="  Remapping Rules  ", bg="#f5f5f5",
                                    font=("Segoe UI", 9, "bold"), fg="#333")
        rules_frame.pack(fill="x", **pad)

        # Input row
        input_row = tk.Frame(rules_frame, bg="#f5f5f5")
        input_row.pack(fill="x", padx=6, pady=(6, 2))

        tk.Label(input_row, text="Old tool #", bg="#f5f5f5",
                 font=("Segoe UI", 9)).pack(side="left")
        self.old_entry = tk.Entry(input_row, width=8, relief="flat", bg="white",
                                  bd=1, font=("Segoe UI", 10))
        self.old_entry.pack(side="left", padx=(4, 12))

        tk.Label(input_row, text="→  New tool #", bg="#f5f5f5",
                 font=("Segoe UI", 9)).pack(side="left")
        self.new_entry = tk.Entry(input_row, width=8, relief="flat", bg="white",
                                  bd=1, font=("Segoe UI", 10))
        self.new_entry.pack(side="left", padx=(4, 12))

        tk.Button(input_row, text="Add Rule", command=self._add_rule,
                  relief="flat", bg="#4a90d9", fg="white", activebackground="#357abd",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=10).pack(side="left")

        tk.Button(input_row, text="Remove Selected", command=self._remove_rule,
                  relief="flat", bg="#e0e0e0", activebackground="#c8c8c8",
                  font=("Segoe UI", 9), cursor="hand2",
                  padx=8).pack(side="left", padx=(8, 0))

        self.old_entry.bind("<Return>", lambda e: self.new_entry.focus())
        self.new_entry.bind("<Return>", lambda e: self._add_rule())

        # Rules listbox
        list_frame = tk.Frame(rules_frame, bg="#f5f5f5")
        list_frame.pack(fill="x", padx=6, pady=(0, 6))

        self.rules_list = tk.Listbox(list_frame, height=5, relief="flat",
                                     bg="white", bd=1, selectmode="single",
                                     font=("Consolas", 9), activestyle="none",
                                     selectbackground="#4a90d9", selectforeground="white")
        self.rules_list.pack(fill="x")

        # ── Action buttons ───────────────────
        btn_frame = tk.Frame(self, bg="#f5f5f5")
        btn_frame.pack(fill="x", padx=10, pady=(2, 6))

        tk.Button(btn_frame, text="Preview Changes", command=self._preview,
                  relief="flat", bg="#555", fg="white", activebackground="#333",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=14, pady=6).pack(side="left")

        tk.Button(btn_frame, text="Save Remapped File…", command=self._save,
                  relief="flat", bg="#2e7d32", fg="white", activebackground="#1b5e20",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=14, pady=6).pack(side="left", padx=(8, 0))

        tk.Button(btn_frame, text="Clear Preview", command=self._clear_preview,
                  relief="flat", bg="#e0e0e0", activebackground="#c8c8c8",
                  font=("Segoe UI", 9), cursor="hand2",
                  padx=10, pady=6).pack(side="right")

        # ── Preview pane ─────────────────────
        preview_frame = tk.LabelFrame(self, text="  Preview  ", bg="#f5f5f5",
                                      font=("Segoe UI", 9, "bold"), fg="#333")
        preview_frame.pack(fill="both", expand=True, **pad)

        self.status_var = tk.StringVar(value="Load a file and add rules to begin.")
        tk.Label(preview_frame, textvariable=self.status_var, bg="#f5f5f5",
                 font=("Segoe UI", 8), fg="#666", anchor="w").pack(fill="x", padx=6, pady=(2, 0))

        self.preview_text = scrolledtext.ScrolledText(
            preview_frame, font=("Consolas", 9), relief="flat",
            bg="white", bd=1, wrap="none", state="disabled"
        )
        self.preview_text.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        # Tag colors for diff highlighting
        self.preview_text.tag_config("changed", background="#fff3cd", foreground="#7a5800")
        self.preview_text.tag_config("token_old", background="#ffd7d7", foreground="#8b0000")
        self.preview_text.tag_config("token_new", background="#d4edda", foreground="#155724")
        self.preview_text.tag_config("linenum", foreground="#aaa")

    # ── Actions ──────────────────────────────

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select G-Code File",
            filetypes=[("G-Code files", "*.nc *.gcode *.tap *.cnc *.txt"),
                       ("All files", "*.*")]
        )
        if path:
            self.file_path.set(path)
            try:
                with open(path, 'r', errors='replace') as f:
                    self.original_content = f.read()
                lines = self.original_content.count('\n')
                self.status_var.set(f"Loaded: {os.path.basename(path)}  ({lines} lines)")
            except Exception as e:
                messagebox.showerror("Error", f"Could not read file:\n{e}")

    def _add_rule(self):
        old_raw = self.old_entry.get().strip().lstrip('TtHhDd')
        new_raw = self.new_entry.get().strip().lstrip('TtHhDd')

        if not old_raw.isdigit() or not new_raw.isdigit():
            messagebox.showwarning("Invalid Input",
                                   "Enter numeric tool numbers only (e.g. 20 → 10).")
            return

        old_num, new_num = int(old_raw), int(new_raw)

        if old_num == new_num:
            messagebox.showwarning("No-op", "Old and new numbers are the same.")
            return

        # Check for duplicates
        for (o, n) in self.rules:
            if o == old_num:
                messagebox.showwarning("Duplicate", f"T{old_num} already has a rule.")
                return

        self.rules.append((old_num, new_num))
        self.rules_list.insert("end", f"  T{old_num}  →  T{new_num}    (also H{old_num}→H{new_num},  D{old_num}→D{new_num})")
        self.old_entry.delete(0, "end")
        self.new_entry.delete(0, "end")
        self.old_entry.focus()

    def _remove_rule(self):
        sel = self.rules_list.curselection()
        if not sel:
            return
        idx = sel[0]
        self.rules_list.delete(idx)
        self.rules.pop(idx)

    def _preview(self):
        if not self.original_content:
            messagebox.showwarning("No File", "Load a G-code file first.")
            return
        if not self.rules:
            messagebox.showwarning("No Rules", "Add at least one remapping rule.")
            return

        new_content, changed_lines = remap_gcode(self.original_content, self.rules)
        changed_set = set(changed_lines)

        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")

        orig_lines = self.original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        for i, (orig, new) in enumerate(zip(orig_lines, new_lines), start=1):
            linenum = f"{i:>5}  "
            self.preview_text.insert("end", linenum, "linenum")

            if i in changed_set:
                # Show the new (remapped) line highlighted
                self.preview_text.insert("end", new.rstrip('\n'), "changed")
                self.preview_text.insert("end", "\n")
            else:
                self.preview_text.insert("end", orig)

        self.preview_text.configure(state="disabled")

        total = len(changed_lines)
        self.status_var.set(
            f"{total} line{'s' if total != 1 else ''} changed — "
            f"highlighted in yellow. File not yet saved."
        )

    def _save(self):
        if not self.original_content:
            messagebox.showwarning("No File", "Load a G-code file first.")
            return
        if not self.rules:
            messagebox.showwarning("No Rules", "Add at least one remapping rule.")
            return

        new_content, changed_lines = remap_gcode(self.original_content, self.rules)

        orig_path = self.file_path.get()
        base, ext = os.path.splitext(orig_path)
        default_name = os.path.basename(base) + "_remapped" + ext

        save_path = filedialog.asksaveasfilename(
            title="Save Remapped File",
            initialfile=default_name,
            defaultextension=ext,
            filetypes=[("G-Code files", "*.nc *.gcode *.tap *.cnc *.txt"),
                       ("All files", "*.*")]
        )
        if not save_path:
            return

        try:
            with open(save_path, 'w') as f:
                f.write(new_content)
            messagebox.showinfo("Saved",
                                f"Remapped file saved:\n{save_path}\n\n"
                                f"{len(changed_lines)} line(s) modified.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save file:\n{e}")

    def _clear_preview(self):
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.configure(state="disabled")
        self.status_var.set("Preview cleared.")


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = RemapperApp()
    app.mainloop()

"""
G-Code Tool Number Remapper
Remaps T, H, and D registers together with exact-match precision.
Two-phase placeholder substitution prevents swap/cascade collisions.
Usage: python gcode_tool_remapper.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import re
import os

try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False


# ─────────────────────────────────────────────
#  Core remapping logic
# ─────────────────────────────────────────────

def build_pattern(prefix, number):
    """
    Match e.g. T20 but NOT T201 or T520.
    Negative lookbehind/lookahead on digits handles exact boundary.
    """
    return re.compile(
        rf'(?<!\d){re.escape(prefix)}{re.escape(str(number))}(?!\d)',
        re.IGNORECASE
    )


def remap_line(line, rules):
    """
    Two-phase substitution:
      Phase 1 — replace every matched token with a NUL-delimited placeholder.
                NUL chars (\x00) never appear in G-code text.
      Phase 2 — swap all placeholders for their final values.

    This prevents cascading: T10->T20 + T20->T10 in the same pass
    won't turn both tools into T20.
    """
    working = line

    # Phase 1: original tokens -> placeholders
    for old_num, new_num in rules:
        for prefix in ('T', 'H', 'D'):
            pattern = build_pattern(prefix, old_num)
            placeholder = f'\x00REMAP_{prefix}{old_num}\x00'
            working = pattern.sub(placeholder, working)

    # Phase 2: placeholders -> final values
    for old_num, new_num in rules:
        for prefix in ('T', 'H', 'D'):
            placeholder = f'\x00REMAP_{prefix}{old_num}\x00'
            working = working.replace(placeholder, f'{prefix}{new_num}')

    return working, working != line


def remap_gcode(content, rules):
    """
    Apply remap_line to every line.
    Returns (new_content, list_of_changed_line_numbers).
    """
    lines = content.splitlines(keepends=True)
    out_lines = []
    changed_lines = []

    for i, line in enumerate(lines, start=1):
        new_line, changed = remap_line(line, rules)
        out_lines.append(new_line)
        if changed:
            changed_lines.append(i)

    return ''.join(out_lines), changed_lines


def detect_encoding(path):
    if not HAS_CHARDET:
        return 'latin-1'
    try:
        with open(path, 'rb') as f:
            raw = f.read(32768)
        result = chardet.detect(raw)
        enc = result.get('encoding') or 'latin-1'
        if enc.lower() in ('ascii', 'utf-8-sig'):
            enc = 'utf-8'
        return enc
    except Exception:
        return 'latin-1'


# ─────────────────────────────────────────────
#  GUI constants
# ─────────────────────────────────────────────

GCODE_FILETYPES = [
    ("G-Code files", "*.nc *.gcode *.tap *.cnc *.txt *.has"),
    ("All files", "*.*"),
]

CLR_DEL_BG     = "#ffd7d7"
CLR_DEL_FG     = "#8b0000"
CLR_ADD_BG     = "#d4edda"
CLR_ADD_FG     = "#155724"
CLR_GUTTER_DEL = "#f5a6a6"
CLR_GUTTER_ADD = "#a8d5b5"
CLR_LINENUM    = "#aaaaaa"


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────

class RemapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("G-Code Tool Remapper")
        self.resizable(True, True)
        self.minsize(760, 620)
        self.configure(bg="#f5f5f5")

        try:
            self.iconbitmap("gcode_remapper.ico")
        except Exception:
            pass

        self.file_path        = tk.StringVar(value="")
        self.file_enc         = 'latin-1'
        self.rules            = []
        self.original_content = ""

        self._build_ui()

    # ── Layout ──────────────────────────────

    def _build_ui(self):
        pad = dict(padx=10, pady=6)

        # ── File picker ──────────────────────
        file_frame = tk.LabelFrame(self, text="  G-Code File  ", bg="#f5f5f5",
                                   font=("Segoe UI", 9, "bold"), fg="#333")
        file_frame.pack(fill="x", **pad)

        tk.Entry(file_frame, textvariable=self.file_path, width=60,
                 relief="flat", bg="white", bd=1,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 4), pady=6,
                                            fill="x", expand=True)
        tk.Button(file_frame, text="Browse…", command=self._browse,
                  relief="flat", bg="#e0e0e0", activebackground="#c8c8c8",
                  font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=(0, 6), pady=6)

        # ── Rules ────────────────────────────
        rules_frame = tk.LabelFrame(self, text="  Remapping Rules  ", bg="#f5f5f5",
                                    font=("Segoe UI", 9, "bold"), fg="#333")
        rules_frame.pack(fill="x", **pad)

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

        list_frame = tk.Frame(rules_frame, bg="#f5f5f5")
        list_frame.pack(fill="x", padx=6, pady=(0, 6))
        self.rules_list = tk.Listbox(list_frame, height=5, relief="flat",
                                     bg="white", bd=1, selectmode="single",
                                     font=("Consolas", 9), activestyle="none",
                                     selectbackground="#4a90d9", selectforeground="white")
        self.rules_list.pack(fill="x")

        # ── Action buttons ───────────────────
        btn_frame = tk.Frame(self, bg="#f5f5f5")
        btn_frame.pack(fill="x", padx=10, pady=(2, 4))

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

        # ── Legend ───────────────────────────
        legend = tk.Frame(self, bg="#f5f5f5")
        legend.pack(fill="x", padx=10, pady=(0, 2))
        for bg, label in ((CLR_DEL_BG, "  Before (original)  "),
                          (CLR_ADD_BG, "  After (remapped)  ")):
            tk.Label(legend, text="   ", bg=bg).pack(side="left", padx=(0, 2))
            tk.Label(legend, text=label, bg="#f5f5f5",
                     font=("Segoe UI", 8), fg="#555").pack(side="left", padx=(0, 14))

        # ── Preview pane ─────────────────────
        preview_frame = tk.LabelFrame(self, text="  Diff Preview  ", bg="#f5f5f5",
                                      font=("Segoe UI", 9, "bold"), fg="#333")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_var = tk.StringVar(value="Load a file and add rules to begin.")
        tk.Label(preview_frame, textvariable=self.status_var, bg="#f5f5f5",
                 font=("Segoe UI", 8), fg="#666", anchor="w").pack(fill="x", padx=6, pady=(2, 0))

        self.preview_text = scrolledtext.ScrolledText(
            preview_frame, font=("Consolas", 9), relief="flat",
            bg="white", bd=1, wrap="none", state="disabled"
        )
        self.preview_text.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        self.preview_text.tag_config("del_gutter",  background=CLR_GUTTER_DEL, foreground=CLR_DEL_FG)
        self.preview_text.tag_config("del_line",    background=CLR_DEL_BG,     foreground=CLR_DEL_FG)
        self.preview_text.tag_config("add_gutter",  background=CLR_GUTTER_ADD, foreground=CLR_ADD_FG)
        self.preview_text.tag_config("add_line",    background=CLR_ADD_BG,     foreground=CLR_ADD_FG)
        self.preview_text.tag_config("linenum",     foreground=CLR_LINENUM)
        self.preview_text.tag_config("unchanged",   foreground="#444")

    # ── File I/O ─────────────────────────────

    def _browse(self):
        path = filedialog.askopenfilename(title="Select G-Code File",
                                          filetypes=GCODE_FILETYPES)
        if not path:
            return
        self.file_path.set(path)
        self.file_enc = detect_encoding(path)
        try:
            with open(path, 'r', encoding=self.file_enc, errors='replace') as f:
                self.original_content = f.read()
            line_count = self.original_content.count('\n')
            enc_note = self.file_enc if HAS_CHARDET else "latin-1 (install chardet for auto-detect)"
            self.status_var.set(
                f"Loaded: {os.path.basename(path)}  ({line_count} lines, encoding: {enc_note})"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not read file:\n{e}")

    # ── Rules management ─────────────────────

    def _add_rule(self):
        old_raw = self.old_entry.get().strip().lstrip('TtHhDd')
        new_raw = self.new_entry.get().strip().lstrip('TtHhDd')
        if not old_raw.isdigit() or not new_raw.isdigit():
            messagebox.showwarning("Invalid Input", "Enter numeric tool numbers only.")
            return
        old_num, new_num = int(old_raw), int(new_raw)
        if old_num == new_num:
            messagebox.showwarning("No-op", "Old and new numbers are the same.")
            return
        for (o, _) in self.rules:
            if o == old_num:
                messagebox.showwarning("Duplicate Rule", f"A rule for T{old_num} already exists.")
                return
        existing_sources = {o for o, _ in self.rules}
        existing_targets = {n for _, n in self.rules}
        if new_num in existing_sources or old_num in existing_targets:
            if not messagebox.askyesno(
                "Possible Swap Detected",
                f"T{new_num} or T{old_num} already appears in another rule.\n"
                f"The two-phase placeholder logic handles swaps correctly,\n"
                f"but double-check your intent. Add rule anyway?"
            ):
                return
        self.rules.append((old_num, new_num))
        self.rules_list.insert("end",
            f"  T{old_num} → T{new_num}    (H{old_num}→H{new_num},  D{old_num}→D{new_num})")
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

    # ── Preview ──────────────────────────────

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
        new_lines  = new_content.splitlines(keepends=True)

        for i, (orig, new) in enumerate(zip(orig_lines, new_lines), start=1):
            linenum = f"{i:>5} "

            if i in changed_set:
                # Red row — original
                self.preview_text.insert("end", linenum,                    "linenum")
                self.preview_text.insert("end", "- ",                       "del_gutter")
                self.preview_text.insert("end", orig.rstrip('\r\n') + "\n", "del_line")
                # Green row — remapped
                self.preview_text.insert("end", linenum,                    "linenum")
                self.preview_text.insert("end", "+ ",                       "add_gutter")
                self.preview_text.insert("end", new.rstrip('\r\n') + "\n",  "add_line")
                # Blank separator
                self.preview_text.insert("end", "\n")
            else:
                self.preview_text.insert("end", linenum,                    "linenum")
                self.preview_text.insert("end", "  ",                       "linenum")
                self.preview_text.insert("end", orig.rstrip('\r\n') + "\n", "unchanged")

        self.preview_text.configure(state="disabled")

        total = len(changed_lines)
        self.status_var.set(
            f"{total} line{'s' if total != 1 else ''} changed  |  "
            f"Red = original  ·  Green = remapped  |  File not yet saved."
        )

    # ── Save ─────────────────────────────────

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
            filetypes=GCODE_FILETYPES,
        )
        if not save_path:
            return

        try:
            with open(save_path, 'w', encoding=self.file_enc, errors='replace') as f:
                f.write(new_content)
            messagebox.showinfo(
                "Saved",
                f"Remapped file saved:\n{save_path}\n\n"
                f"{len(changed_lines)} line(s) modified.\n"
                f"Encoding preserved: {self.file_enc}"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not save file:\n{e}")

    def _clear_preview(self):
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.configure(state="disabled")
        self.status_var.set("Preview cleared.")


# ─────────────────────────────────────────────
if __name__ == "__main__":
    RemapperApp().mainloop()

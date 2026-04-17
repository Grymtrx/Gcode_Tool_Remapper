"""
G-Code Tool Number Remapper
  - Remaps T / H / D registers atomically via two-phase placeholder substitution
  - Inserts (REMAPPED DATE: YYYY-MM-DD) comment on line 3 of output
  - GitHub-style red/green diff preview with purple T/H/D token highlights
  - Required filename suffix (_T20 or _T50) enforced before save
Usage: python gcode_tool_remapper.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import re
import os
import difflib
from datetime import date

try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False


# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

GCODE_FILETYPES = [
    ("G-Code files", "*.nc *.gcode *.tap *.cnc *.txt *.has"),
    ("All files", "*.*"),
]

# Regex that matches T/H/D register references but not partial numbers
# e.g.  T20 ✓   T201 ✗   T520 ✗
TOKEN_PAT = re.compile(r'(?<!\d)[THD]\d+(?!\d)', re.IGNORECASE)

# Diff colours (GitHub-flavoured)
CLR_DEL_BG     = "#ffd7d7"
CLR_DEL_FG     = "#8b0000"
CLR_ADD_BG     = "#d4edda"
CLR_ADD_FG     = "#155724"
CLR_GUTTER_DEL = "#f5a6a6"
CLR_GUTTER_ADD = "#a8d5b5"
CLR_LINENUM    = "#aaaaaa"

# Purple token highlight (unchanged lines only)
CLR_TOKEN_BG   = "#ede9fe"
CLR_TOKEN_FG   = "#5b21b6"


# ─────────────────────────────────────────────
#  Core logic
# ─────────────────────────────────────────────

def build_pattern(prefix, number):
    """Exact-boundary regex for a single prefix + number, case-insensitive."""
    return re.compile(
        rf'(?<!\d){re.escape(prefix)}{re.escape(str(number))}(?!\d)',
        re.IGNORECASE
    )


def remap_line(line, rules):
    """
    Two-phase substitution so swaps (T10→T20 + T20→T10) are safe:
      Phase 1 – replace matched tokens with NUL-delimited placeholders.
      Phase 2 – replace placeholders with final values.
    NUL (\x00) never appears in G-code text.
    """
    working = line

    for old_num, new_num in rules:
        for prefix in ('T', 'H', 'D'):
            pattern = build_pattern(prefix, old_num)
            placeholder = f'\x00REMAP_{prefix}{old_num}\x00'
            working = pattern.sub(placeholder, working)

    for old_num, new_num in rules:
        for prefix in ('T', 'H', 'D'):
            placeholder = f'\x00REMAP_{prefix}{old_num}\x00'
            working = working.replace(placeholder, f'{prefix}{new_num}')

    return working, working != line


def remap_gcode(content, rules):
    lines = content.splitlines(keepends=True)
    return ''.join(remap_line(ln, rules)[0] for ln in lines)


def insert_date_comment(content):
    """Insert (REMAPPED DATE: YYYY-MM-DD) as the 3rd line of the file."""
    today   = date.today().strftime('%Y-%m-%d')
    comment = f"(REMAPPED DATE: {today})\n"
    lines   = content.splitlines(keepends=True)
    insert_at = min(2, len(lines))   # index 2 = position before original line 3
    lines.insert(insert_at, comment)
    return ''.join(lines)


def build_final_output(content, rules):
    """Remap then insert the date comment."""
    return insert_date_comment(remap_gcode(content, rules))


def make_diff(orig_lines, new_lines):
    """
    Full unified diff using difflib.
    Returns list of ('equal' | 'del' | 'add', orig_lineno_or_None,
                                                new_lineno_or_None, text).
    """
    matcher = difflib.SequenceMatcher(None, orig_lines, new_lines, autojunk=False)
    result  = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                result.append(('equal', i1+k+1, j1+k+1, orig_lines[i1+k]))
        elif tag == 'replace':
            for k in range(i2 - i1):
                result.append(('del', i1+k+1, None, orig_lines[i1+k]))
            for k in range(j2 - j1):
                result.append(('add', None, j1+k+1, new_lines[j1+k]))
        elif tag == 'delete':
            for k in range(i2 - i1):
                result.append(('del', i1+k+1, None, orig_lines[i1+k]))
        elif tag == 'insert':
            for k in range(j2 - j1):
                result.append(('add', None, j1+k+1, new_lines[j1+k]))
    return result


def detect_encoding(path):
    if not HAS_CHARDET:
        return 'latin-1'
    try:
        with open(path, 'rb') as f:
            raw = f.read(32768)
        enc = (chardet.detect(raw).get('encoding') or 'latin-1')
        return 'utf-8' if enc.lower() in ('ascii', 'utf-8-sig') else enc
    except Exception:
        return 'latin-1'


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────

class RemapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("G-Code Tool Remapper")
        self.resizable(True, True)
        self.minsize(780, 700)
        self.configure(bg="#f5f5f5")

        try:
            self.iconbitmap("gcode_remapper.ico")
        except Exception:
            pass

        self.file_path        = tk.StringVar(value="")
        self.file_enc         = 'latin-1'
        self.rules            = []
        self.original_content = ""
        self.suffix_var       = tk.StringVar(value="")   # "" = nothing selected

        self._build_ui()

    # ── Build UI ────────────────────────────

    def _build_ui(self):
        P = dict(padx=10, pady=5)

        # ── 1. File picker ───────────────────
        ff = tk.LabelFrame(self, text="  G-Code File  ", bg="#f5f5f5",
                           font=("Segoe UI", 9, "bold"), fg="#333")
        ff.pack(fill="x", **P)

        tk.Entry(ff, textvariable=self.file_path, relief="flat", bg="white",
                 bd=1, font=("Segoe UI", 9)).pack(side="left", padx=(6,4), pady=6,
                                                   fill="x", expand=True)
        tk.Button(ff, text="Browse…", command=self._browse,
                  relief="flat", bg="#e0e0e0", activebackground="#c8c8c8",
                  font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=(0,6), pady=6)

        # ── 2. Remapping rules ───────────────
        rf = tk.LabelFrame(self, text="  Remapping Rules  ", bg="#f5f5f5",
                           font=("Segoe UI", 9, "bold"), fg="#333")
        rf.pack(fill="x", **P)

        row = tk.Frame(rf, bg="#f5f5f5")
        row.pack(fill="x", padx=6, pady=(6,2))

        tk.Label(row, text="Old tool #", bg="#f5f5f5", font=("Segoe UI", 9)).pack(side="left")
        self.old_entry = tk.Entry(row, width=8, relief="flat", bg="white",
                                  bd=1, font=("Segoe UI", 10))
        self.old_entry.pack(side="left", padx=(4,12))

        tk.Label(row, text="→  New tool #", bg="#f5f5f5", font=("Segoe UI", 9)).pack(side="left")
        self.new_entry = tk.Entry(row, width=8, relief="flat", bg="white",
                                  bd=1, font=("Segoe UI", 10))
        self.new_entry.pack(side="left", padx=(4,12))

        tk.Button(row, text="Add Rule", command=self._add_rule,
                  relief="flat", bg="#4a90d9", fg="white", activebackground="#357abd",
                  font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10).pack(side="left")
        tk.Button(row, text="Remove Selected", command=self._remove_rule,
                  relief="flat", bg="#e0e0e0", activebackground="#c8c8c8",
                  font=("Segoe UI", 9), cursor="hand2", padx=8).pack(side="left", padx=(8,0))

        self.old_entry.bind("<Return>", lambda e: self.new_entry.focus())
        self.new_entry.bind("<Return>", lambda e: self._add_rule())

        lf = tk.Frame(rf, bg="#f5f5f5")
        lf.pack(fill="x", padx=6, pady=(0,6))
        self.rules_list = tk.Listbox(lf, height=4, relief="flat", bg="white", bd=1,
                                     selectmode="single", font=("Consolas", 9),
                                     activestyle="none",
                                     selectbackground="#4a90d9", selectforeground="white")
        self.rules_list.pack(fill="x")

        # ── 3. Output suffix (required) ──────
        sf = tk.LabelFrame(self,
                           text="  Output Filename Suffix  \u2014  must select one to save  ",
                           bg="#f5f5f5", font=("Segoe UI", 9, "bold"), fg="#c0392b")
        sf.pack(fill="x", **P)

        sf_row = tk.Frame(sf, bg="#f5f5f5")
        sf_row.pack(padx=8, pady=8, anchor="w")

        tk.Label(sf_row, text="Append to filename:", bg="#f5f5f5",
                 font=("Segoe UI", 9)).pack(side="left", padx=(0,10))

        for label, val in (("T20", "_T20"), ("T50", "_T50")):
            tk.Radiobutton(sf_row, text=label, variable=self.suffix_var, value=val,
                           bg="#f5f5f5", font=("Consolas", 10, "bold"),
                           activebackground="#f5f5f5",
                           cursor="hand2").pack(side="left", padx=10)

        # Ensure neither button appears selected on launch
        self.suffix_var.set("")

        self.suffix_lbl = tk.Label(sf_row, text="", bg="#f5f5f5",
                                   font=("Segoe UI", 8, "italic"), fg="#666")
        self.suffix_lbl.pack(side="left", padx=(14,0))
        self.suffix_var.trace_add("write", self._on_suffix_change)

        # ── 4. Action buttons ────────────────
        bf = tk.Frame(self, bg="#f5f5f5")
        bf.pack(fill="x", padx=10, pady=(2,4))

        tk.Button(bf, text="Preview Changes", command=self._preview,
                  relief="flat", bg="#555", fg="white", activebackground="#333",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=14, pady=6).pack(side="left")
        tk.Button(bf, text="Save Remapped File…", command=self._save,
                  relief="flat", bg="#2e7d32", fg="white", activebackground="#1b5e20",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=14, pady=6).pack(side="left", padx=(8,0))
        tk.Button(bf, text="Clear Preview", command=self._clear_preview,
                  relief="flat", bg="#e0e0e0", activebackground="#c8c8c8",
                  font=("Segoe UI", 9), cursor="hand2",
                  padx=10, pady=6).pack(side="right")

        # ── 5. Legend ────────────────────────
        leg = tk.Frame(self, bg="#f5f5f5")
        leg.pack(fill="x", padx=10, pady=(0,2))
        for bg, fg, label in (
            (CLR_DEL_BG,   CLR_DEL_FG,   "  Before (original)   "),
            (CLR_ADD_BG,   CLR_ADD_FG,   "  After (remapped)    "),
            (CLR_TOKEN_BG, CLR_TOKEN_FG, "  T / H / D register  "),
        ):
            tk.Label(leg, text="   ", bg=bg).pack(side="left", padx=(0,2))
            tk.Label(leg, text=label, bg="#f5f5f5",
                     font=("Segoe UI", 8), fg=fg).pack(side="left", padx=(0,12))

        # ── 6. Preview pane ──────────────────
        pf = tk.LabelFrame(self, text="  Diff Preview  ", bg="#f5f5f5",
                           font=("Segoe UI", 9, "bold"), fg="#333")
        pf.pack(fill="both", expand=True, padx=10, pady=(0,10))

        self.status_var = tk.StringVar(value="Load a file and add rules to begin.")
        tk.Label(pf, textvariable=self.status_var, bg="#f5f5f5",
                 font=("Segoe UI", 8), fg="#666", anchor="w").pack(fill="x", padx=6, pady=(2,0))

        self.preview_text = scrolledtext.ScrolledText(
            pf, font=("Consolas", 9), relief="flat",
            bg="white", bd=1, wrap="none", state="disabled"
        )
        self.preview_text.pack(fill="both", expand=True, padx=6, pady=(2,6))

        self.preview_text.tag_config("del_gutter", background=CLR_GUTTER_DEL, foreground=CLR_DEL_FG)
        self.preview_text.tag_config("del_line",   background=CLR_DEL_BG,     foreground=CLR_DEL_FG)
        self.preview_text.tag_config("add_gutter", background=CLR_GUTTER_ADD, foreground=CLR_ADD_FG)
        self.preview_text.tag_config("add_line",   background=CLR_ADD_BG,     foreground=CLR_ADD_FG)
        self.preview_text.tag_config("linenum",    foreground=CLR_LINENUM)
        self.preview_text.tag_config("unchanged",  foreground="#444")
        # Token tag raised above line tags so purple is visible on unchanged lines
        self.preview_text.tag_config("token",      background=CLR_TOKEN_BG,
                                                   foreground=CLR_TOKEN_FG)
        self.preview_text.tag_raise("token")

    # ── Suffix label ─────────────────────────

    def _on_suffix_change(self, *_):
        suf  = self.suffix_var.get()
        path = self.file_path.get()
        if not suf:
            self.suffix_lbl.config(text="")
            return
        if path:
            base, ext = os.path.splitext(os.path.basename(path))
            self.suffix_lbl.config(text=f"→  {base}{suf}{ext}")
        else:
            self.suffix_lbl.config(text=f"→  MyFile{suf}.has")

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
            n    = self.original_content.count('\n')
            enc  = self.file_enc if HAS_CHARDET else "latin-1 (install chardet for auto-detect)"
            self.status_var.set(f"Loaded: {os.path.basename(path)}  ({n} lines, {enc})")
            self._on_suffix_change()
        except Exception as e:
            messagebox.showerror("Error", f"Could not read file:\n{e}")

    # ── Rules ────────────────────────────────

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
                messagebox.showwarning("Duplicate", f"A rule for T{old_num} already exists.")
                return
        existing_src = {o for o, _ in self.rules}
        existing_dst = {n for _, n in self.rules}
        if new_num in existing_src or old_num in existing_dst:
            if not messagebox.askyesno(
                "Possible Swap Detected",
                f"T{new_num} or T{old_num} appears in another rule.\n"
                f"The two-phase placeholder logic handles swaps safely,\n"
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

        final = build_final_output(self.original_content, self.rules)
        orig_lines  = self.original_content.splitlines(keepends=True)
        final_lines = final.splitlines(keepends=True)
        diff        = make_diff(orig_lines, final_lines)

        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")

        prev_kind   = 'equal'
        change_count = 0

        for kind, orig_no, new_no, text in diff:
            line_text = text.rstrip('\r\n')

            # Blank separator when transitioning from a changed hunk back to equal
            if kind == 'equal' and prev_kind in ('del', 'add'):
                self.preview_text.insert("end", "\n")

            if kind == 'equal':
                lnum = f"{orig_no:>5} "
                self.preview_text.insert("end", lnum,              "linenum")
                self.preview_text.insert("end", "  ",              "linenum")
                self.preview_text.insert("end", line_text + "\n",  "unchanged")

            elif kind == 'del':
                change_count += 1
                lnum = f"{orig_no:>5} "
                self.preview_text.insert("end", lnum,              "linenum")
                self.preview_text.insert("end", "- ",              "del_gutter")
                self.preview_text.insert("end", line_text + "\n",  "del_line")

            elif kind == 'add':
                lnum = f"{'':>5} "
                self.preview_text.insert("end", lnum,              "linenum")
                self.preview_text.insert("end", "+ ",              "add_gutter")
                self.preview_text.insert("end", line_text + "\n",  "add_line")

            prev_kind = kind

        self.preview_text.configure(state="disabled")

        # Apply purple highlight to T/H/D tokens on unchanged lines only
        self._highlight_tokens()

        self.status_var.set(
            f"{change_count} source line(s) changed  +  date comment added on line 3  |  "
            f"Red = original · Green = remapped · Purple = T/H/D registers  |  Not yet saved."
        )

    def _highlight_tokens(self):
        """
        Scan the entire preview widget for TOKEN_PAT matches.
        Apply purple 'token' tag only where there is no red or green tag
        (i.e. only on unchanged lines).
        """
        self.preview_text.configure(state="normal")

        # Grab full widget text and find all token positions using Python regex.
        # tkinter "1.0+Nc" counts N chars from the very start — handles newlines correctly.
        full = self.preview_text.get("1.0", "end")

        for m in TOKEN_PAT.finditer(full):
            s_idx = f"1.0+{m.start()}c"
            e_idx = f"1.0+{m.end()}c"
            tags  = self.preview_text.tag_names(s_idx)
            if "del_line" not in tags and "add_line" not in tags:
                self.preview_text.tag_add("token", s_idx, e_idx)

        self.preview_text.configure(state="disabled")

    # ── Save ─────────────────────────────────

    def _save(self):
        if not self.original_content:
            messagebox.showwarning("No File", "Load a G-code file first.")
            return
        if not self.rules:
            messagebox.showwarning("No Rules", "Add at least one remapping rule.")
            return

        suffix = self.suffix_var.get()
        if not suffix:
            messagebox.showwarning(
                "Suffix Required",
                "You must select _T20 or _T50 before saving.\n"
                "This suffix is required to create the output file."
            )
            return

        final     = build_final_output(self.original_content, self.rules)
        orig_path = self.file_path.get()
        base, ext = os.path.splitext(orig_path)
        default   = os.path.basename(base) + suffix + ext

        save_path = filedialog.asksaveasfilename(
            title="Save Remapped File",
            initialfile=default,
            defaultextension=ext,
            filetypes=GCODE_FILETYPES,
        )
        if not save_path:
            return

        try:
            with open(save_path, 'w', encoding=self.file_enc, errors='replace') as f:
                f.write(final)
            messagebox.showinfo(
                "Saved",
                f"File saved:\n{save_path}\n\n"
                f"Date comment inserted on line 3.\n"
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

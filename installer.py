"""flow-st8 Windows Installer — GUI wizard."""

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path

# ── palette ───────────────────────────────────────────────────────────────────
BG      = "#141414"
SURFACE = "#1e1e1e"
BORDER  = "#2a2a2a"
ACCENT  = "#4fc3f7"
GREEN   = "#66bb6a"
RED     = "#ef5350"
YELLOW  = "#ffd54f"
FG      = "#e0e0e0"
MUTED   = "#888888"

F    = ("Segoe UI", 10)
F_B  = ("Segoe UI", 10, "bold")
F_H  = ("Segoe UI", 18, "bold")
F_SM = ("Segoe UI", 9)

MODELS = [
    ("large-v3-turbo", "1.5 GB", "Best quality · fastest on GPU"),
    ("medium",         "1.5 GB", "Very good · good for mid-range GPU"),
    ("small",          "460 MB", "Good quality · works on slow GPU / fast CPU"),
    ("base",           "138 MB", "Decent quality · best for CPU only"),
]

LICENSE_TEXT = """\
FLOW-ST8 — MIT License

Copyright (c) 2024 luckmattos

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

────────────────────────────────────────────────────────────────
DISCLAIMER OF LIABILITY

By installing this software, you acknowledge and agree that:

1. You install and use this software entirely at your own risk.

2. The developer makes no warranty of any kind — express, implied, statutory,
   or otherwise — including warranties of merchantability, fitness for a
   particular purpose, or non-infringement.

3. The developer shall not be held liable for any direct, indirect, incidental,
   special, exemplary, or consequential damages of any kind (including loss of
   data, loss of profits, or business interruption), however caused and
   regardless of the theory of liability, even if advised of the possibility
   of such damage.

4. This software operates entirely offline. Audio is processed locally on your
   machine and is never transmitted to any external server or third party.

5. You are solely responsible for ensuring this software complies with all
   applicable laws, regulations, and policies in your jurisdiction.

6. This is a free, open-source project. The developer has no obligation to
   provide updates, maintenance, fixes, or support of any kind.
"""

STEPS = ["welcome", "license", "detecting", "model", "options", "installing", "done"]
APPDATA_DIR = Path(os.environ.get("APPDATA", "")) / "flow-st8"


# ── hardware helpers ──────────────────────────────────────────────────────────

def _detect_gpu():
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            name, mem = r.stdout.strip().split("\n")[0].split(",")
            return True, name.strip(), float(mem.strip().split()[0]) / 1024
    except Exception:
        pass
    return False, "", 0.0


def _find_python():
    for cmd in ("python", "python3", "py"):
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                ver = (r.stdout or r.stderr).strip().split()[1]
                major, minor = int(ver.split(".")[0]), int(ver.split(".")[1])
                if (major, minor) >= (3, 11):
                    return cmd
        except Exception:
            pass
    return None


def _recommend(vram_gb, has_gpu):
    if not has_gpu:  return "base"
    if vram_gb >= 6: return "large-v3-turbo"
    if vram_gb >= 4: return "medium"
    if vram_gb >= 2: return "small"
    return "base"


def _app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", _app_dir()))
    return base / relative


def _is_installed() -> bool:
    return (APPDATA_DIR / "config.toml").exists()


# ── installer window ──────────────────────────────────────────────────────────

class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("flow-st8 Setup")
        self.geometry("600x580")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._logo_img = self._load_logo(36)
        if self._logo_img is not None:
            self.iconphoto(True, self._logo_img)
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # state
        self.has_gpu    = False
        self.gpu_name   = ""
        self.vram_gb    = 0.0
        self.python_cmd = None
        self.selected   = tk.StringVar(value="large-v3-turbo")
        self._autostart_val: bool = True
        self._agreed_val:    bool = False
        self._toggle_guard:  bool = False
        self._current   = ""
        self._model_cards: dict[str, tk.Frame]  = {}
        self._model_dots:  dict[str, tk.Canvas] = {}

        self._build_chrome()
        self._go("welcome")

    def _load_logo(self, size: int):
        try:
            image = tk.PhotoImage(master=self, file=str(_resource_path("assets/flow-st8-icon.png")))
            factor = max(1, image.width() // size)
            return image.subsample(factor, factor)
        except Exception:
            return None

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 600) // 2
        y = (self.winfo_screenheight() - 580) // 2
        self.geometry(f"+{x}+{y}")

    # ── chrome (header + footer, always visible) ──────────────────────────────

    def _build_chrome(self):
        # Header — text only, no icon
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=32, pady=(22, 0))
        if self._logo_img is not None:
            tk.Label(hdr, image=self._logo_img, bg=BG).pack(side="left", padx=(0, 10))
        title_col = tk.Frame(hdr, bg=BG)
        title_col.pack(side="left", fill="x", expand=True)
        tk.Label(title_col, text="flow-st8 Setup",
                 font=("Segoe UI", 15, "bold"), bg=BG, fg=FG).pack(anchor="w")
        tk.Label(title_col, text="Guided installation for Windows",
                 font=F_SM, bg=BG, fg=MUTED).pack(anchor="w")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=(10, 0))

        # Footer — packed to bottom BEFORE content so it's never clipped
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg=BG, height=60)
        footer.pack(fill="x", side="bottom", padx=32)
        footer.pack_propagate(False)

        self.btn_cancel = tk.Button(
            footer, text="Cancel", font=F,
            bg=SURFACE, fg=MUTED, relief="flat", cursor="hand2",
            padx=14, pady=5, command=self._cancel,
        )
        self.btn_cancel.pack(side="left", pady=14)

        self.btn_next = tk.Button(
            footer, text="Next →", font=F_B,
            bg=ACCENT, fg="#000", relief="flat", cursor="hand2",
            padx=20, pady=5, command=self._on_next,
        )
        self.btn_next.pack(side="right", pady=14)

        self.btn_back = tk.Button(
            footer, text="← Back", font=F,
            bg=SURFACE, fg=MUTED, relief="flat", cursor="hand2",
            padx=14, pady=5, command=self._on_back,
        )
        self.btn_back.pack(side="right", pady=14, padx=(0, 8))

        # Content area fills remaining space
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True, padx=32, pady=0)

    def _clear(self):
        for w in self.content.winfo_children():
            w.destroy()
        self._model_cards.clear()
        self._model_dots.clear()

    def _set_nav(self, *, cancel_label="Cancel", cancel_on=True,
                 back_on=True, next_label="Next →", next_on=True,
                 next_bg=None, next_cmd=None):
        self.btn_cancel.config(
            text=cancel_label,
            state="normal" if cancel_on else "disabled",
            fg=MUTED if cancel_on else "#3a3a3a",
            cursor="hand2" if cancel_on else "arrow",
        )
        self.btn_back.config(
            state="normal" if back_on else "disabled",
            fg=MUTED if back_on else "#3a3a3a",
            cursor="hand2" if back_on else "arrow",
        )
        self.btn_next.config(
            text=next_label,
            state="normal" if next_on else "disabled",
            bg=next_bg or (ACCENT if next_on else SURFACE),
            fg="#000" if next_on else "#3a3a3a",
            cursor="hand2" if next_on else "arrow",
            command=next_cmd or self._on_next,
        )

    # ── routing ───────────────────────────────────────────────────────────────

    def _go(self, step: str):
        self._current = step
        {
            "welcome":    self._step_welcome,
            "license":    self._step_license,
            "detecting":  self._step_detecting,
            "model":      self._step_model,
            "options":    self._step_options,
            "installing": self._step_installing,
            "done":       self._step_done,
        }[step]()

    def _on_next(self):
        idx = STEPS.index(self._current)
        if idx + 1 < len(STEPS):
            self._go(STEPS[idx + 1])

    def _on_back(self):
        idx = STEPS.index(self._current)
        if idx > 0:
            self._go(STEPS[idx - 1])

    def _cancel(self):
        if self._current != "installing":
            self.destroy()

    # ── step: welcome ─────────────────────────────────────────────────────────

    def _step_welcome(self):
        self._clear()
        self._set_nav(back_on=False)

        tk.Label(self.content, text="Welcome", font=F_H, bg=BG, fg=FG
                 ).pack(anchor="w", pady=(18, 6))
        tk.Label(self.content,
                 text="This wizard installs flow-st8 and configures the best\n"
                      "setup for your hardware automatically.",
                 font=F, bg=BG, fg=MUTED, justify="left").pack(anchor="w", pady=(0, 22))

        if _is_installed():
            tk.Label(
                self.content,
                text="Existing installation detected. Continuing will update/reinstall flow-st8.",
                font=F_SM,
                bg=BG,
                fg=YELLOW,
                justify="left",
            ).pack(anchor="w", pady=(0, 12))

        tk.Label(self.content, text="Install location", font=F_B, bg=BG, fg=FG
                 ).pack(anchor="w", pady=(0, 5))
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill="x")

        self._install_dir = tk.StringVar(value=str(Path.home() / "flow-st8"))
        tk.Entry(row, textvariable=self._install_dir, font=F,
                 bg=SURFACE, fg=FG, relief="flat", insertbackground=FG, bd=0,
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="left", fill="x", expand=True,
                                             ipady=7, padx=(0, 8))
        tk.Button(row, text="Browse", font=F_SM, bg=SURFACE, fg=FG,
                  relief="flat", cursor="hand2", padx=10, pady=5,
                  command=self._browse).pack(side="right")

        tk.Label(self.content, text="Requires Python 3.11+. Download at python.org if needed.",
                 font=F_SM, bg=BG, fg=MUTED).pack(anchor="w", pady=(10, 0))

    def _browse(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="Choose install location")
        if d:
            self._install_dir.set(d)

    # ── step: license ─────────────────────────────────────────────────────────

    def _step_license(self):
        self._clear()
        self._agreed_val = True
        self._set_nav(next_label="I Agree →", next_on=False)

        self._set_nav(next_label="I Agree", next_on=True)

        tk.Label(self.content, text="License & Disclaimer", font=F_H, bg=BG, fg=FG
                 ).pack(anchor="w", pady=(18, 8))

        box = tk.Frame(self.content, bg=SURFACE,
                       highlightthickness=1, highlightbackground=BORDER)
        box.pack(fill="both", expand=True, pady=(0, 10))

        sb = tk.Scrollbar(box, orient="vertical", bg=SURFACE, troughcolor=SURFACE,
                          highlightthickness=0)
        sb.pack(side="right", fill="y")
        txt = tk.Text(box, font=("Segoe UI", 9), bg=SURFACE, fg=MUTED,
                      relief="flat", bd=8, wrap="word", state="normal",
                      yscrollcommand=sb.set, cursor="arrow",
                      selectbackground=BORDER)
        txt.insert("1.0", LICENSE_TEXT.strip())
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        sb.config(command=txt.yview)

        # Agree row
        row = tk.Frame(self.content, bg=BG, cursor="hand2")
        row.pack(anchor="w", pady=(0, 2))
        self._agree_canvas = tk.Canvas(row, width=18, height=18, bg=BG,
                                        highlightthickness=0, cursor="hand2")
        self._agree_canvas.pack(side="left", padx=(0, 8))
        self._draw_checkbox(self._agree_canvas, False)
        lbl = tk.Label(row, text="I have read and agree to the license and disclaimer",
                       font=F, bg=BG, fg=FG, cursor="hand2")
        lbl.pack(side="left")
        # Bind only to leaves — parent binding would double-fire via propagation
        self._agree_canvas.bind("<Button-1>", self._toggle_agree)
        lbl.bind("<Button-1>", self._toggle_agree)

    def _toggle_agree(self, _=None):
        if self._toggle_guard:
            return "break"
        self._toggle_guard = True
        self._agreed_val = not self._agreed_val
        self._draw_checkbox(self._agree_canvas, self._agreed_val)
        self._set_nav(next_label="I Agree →", next_on=self._agreed_val)
        self.after(50, lambda: setattr(self, "_toggle_guard", False))
        return "break"

    # ── step: detecting ───────────────────────────────────────────────────────

    def _step_detecting(self):
        self._clear()
        self._set_nav(back_on=True, next_on=False, next_label="Detecting…")

        tk.Label(self.content, text="Detecting Hardware", font=F_H, bg=BG, fg=FG
                 ).pack(anchor="w", pady=(18, 16))

        self._hw_labels: dict[str, tk.Label] = {}
        for key, label in [("python", "Python 3.11+"), ("gpu", "NVIDIA GPU"), ("vram", "VRAM")]:
            row = tk.Frame(self.content, bg=BG)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, font=F, bg=BG, fg=FG, width=14, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="checking…", font=F, bg=BG, fg=MUTED)
            lbl.pack(side="left")
            self._hw_labels[key] = lbl

        threading.Thread(target=self._do_detect, daemon=True).start()

    def _do_detect(self):
        self.python_cmd = _find_python()
        self._ui(self._hw_labels["python"].config, {
            "text": self.python_cmd or "Not found — install Python 3.11+ first",
            "fg":   GREEN if self.python_cmd else RED,
        })
        self.has_gpu, self.gpu_name, self.vram_gb = _detect_gpu()
        self._ui(self._hw_labels["gpu"].config, {
            "text": self.gpu_name if self.has_gpu else "Not found (CPU mode)",
            "fg":   GREEN if self.has_gpu else YELLOW,
        })
        self._ui(self._hw_labels["vram"].config, {
            "text": f"{self.vram_gb:.1f} GB" if self.has_gpu else "N/A",
            "fg":   GREEN if self.has_gpu else MUTED,
        })
        self.selected.set(_recommend(self.vram_gb, self.has_gpu))
        self._ui(self._set_nav, next_label="Next →", next_on=True, back_on=True)

    # ── step: model ───────────────────────────────────────────────────────────

    def _step_model(self):
        self._clear()
        self._set_nav(back_on=True)

        tk.Label(self.content, text="Choose Model", font=F_H, bg=BG, fg=FG
                 ).pack(anchor="w", pady=(18, 4))
        hw = f"{self.gpu_name} · {self.vram_gb:.1f} GB VRAM" if self.has_gpu else "CPU only"
        tk.Label(self.content, text=f"Detected: {hw}", font=F_SM, bg=BG, fg=MUTED
                 ).pack(anchor="w", pady=(0, 10))

        rec = _recommend(self.vram_gb, self.has_gpu)
        self.selected.set(rec)

        for name, size, desc in MODELS:
            is_sel = (name == rec)
            card = tk.Frame(self.content, bg=SURFACE, cursor="hand2",
                            highlightthickness=1,
                            highlightbackground=ACCENT if is_sel else BORDER)
            card.pack(fill="x", pady=3)
            self._model_cards[name] = card

            inner = tk.Frame(card, bg=SURFACE)
            inner.pack(fill="x", padx=12, pady=9)

            dot = tk.Canvas(inner, width=18, height=18, bg=SURFACE, highlightthickness=0)
            dot.pack(side="left", padx=(0, 10))
            self._draw_dot(dot, is_sel)
            self._model_dots[name] = dot

            col = tk.Frame(inner, bg=SURFACE)
            col.pack(side="left", fill="x", expand=True)
            top = tk.Frame(col, bg=SURFACE)
            top.pack(anchor="w")
            tk.Label(top, text=name, font=F_B, bg=SURFACE, fg=FG).pack(side="left")
            tk.Label(top, text=f"  {size}", font=F_SM, bg=SURFACE, fg=MUTED).pack(side="left")
            if name == rec:
                tk.Label(top, text="  recommended", font=F_SM, bg=SURFACE, fg=ACCENT
                         ).pack(side="left")
            tk.Label(col, text=desc, font=F_SM, bg=SURFACE, fg=MUTED).pack(anchor="w")

            for w in (card, inner, dot, col, top):
                w.bind("<Button-1>", lambda e, n=name: self._pick_model(n))

    def _pick_model(self, name: str):
        self.selected.set(name)
        for n, card in self._model_cards.items():
            sel = (n == name)
            card.config(highlightbackground=ACCENT if sel else BORDER)
            self._draw_dot(self._model_dots[n], sel)

    # ── step: options ─────────────────────────────────────────────────────────

    def _step_options(self):
        self._clear()
        self._set_nav(back_on=True, next_label="Install →")

        tk.Label(self.content, text="Options", font=F_H, bg=BG, fg=FG
                 ).pack(anchor="w", pady=(18, 6))
        tk.Label(self.content, text="Configure how flow-st8 runs on your system.",
                 font=F, bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 18))

        card = tk.Frame(self.content, bg=SURFACE, cursor="hand2",
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=3)
        inner = tk.Frame(card, bg=SURFACE)
        inner.pack(fill="x", padx=14, pady=12)

        self._cb_canvas = tk.Canvas(inner, width=18, height=18, bg=SURFACE,
                                     highlightthickness=0, cursor="hand2")
        self._cb_canvas.pack(side="left", padx=(0, 12))
        self._draw_checkbox(self._cb_canvas, self._autostart_val)

        col = tk.Frame(inner, bg=SURFACE)
        col.pack(side="left")
        tk.Label(col, text="Start flow-st8 with Windows",
                 font=F_B, bg=SURFACE, fg=FG).pack(anchor="w")
        tk.Label(col, text="Launch automatically in the background when you log in",
                 font=F_SM, bg=SURFACE, fg=MUTED).pack(anchor="w")

        self._cb_canvas.bind("<Button-1>", self._toggle_autostart)
        for w in col.winfo_children():
            w.bind("<Button-1>", self._toggle_autostart)

    def _toggle_autostart(self, _=None):
        if self._toggle_guard:
            return "break"
        self._toggle_guard = True
        self._autostart_val = not self._autostart_val
        self._draw_checkbox(self._cb_canvas, self._autostart_val)
        self.after(50, lambda: setattr(self, "_toggle_guard", False))
        return "break"

    # ── step: installing ──────────────────────────────────────────────────────

    def _step_installing(self):
        self._clear()
        self._set_nav(cancel_on=False, back_on=False,
                      next_label="Installing…", next_on=False)

        tk.Label(self.content, text="Installing", font=F_H, bg=BG, fg=FG
                 ).pack(anchor="w", pady=(18, 6))
        self._status = tk.Label(self.content, text="Starting…", font=F, bg=BG, fg=MUTED)
        self._status.pack(anchor="w", pady=(0, 8))

        bar_bg = tk.Frame(self.content, bg=SURFACE, height=6)
        bar_bg.pack(fill="x", pady=(0, 10))
        bar_bg.pack_propagate(False)
        self._bar = tk.Frame(bar_bg, bg=ACCENT, height=6)
        self._bar.place(x=0, y=0, relheight=1, relwidth=0)

        log_wrap = tk.Frame(self.content, bg=SURFACE,
                            highlightthickness=1, highlightbackground=BORDER)
        log_wrap.pack(fill="both", expand=True, pady=(0, 4))
        self._log_box = tk.Text(log_wrap, font=("Consolas", 8), bg=SURFACE, fg=MUTED,
                                 relief="flat", bd=6, wrap="word", state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=4, pady=4)

        threading.Thread(target=self._do_install, daemon=True).start()

    # ── step: done ────────────────────────────────────────────────────────────

    def _step_done(self):
        self._clear()
        self._set_nav(cancel_label="Close", cancel_on=True,
                      back_on=False, next_label="Launch flow-st8 →",
                      next_bg=GREEN, next_cmd=self._launch)

        c = tk.Canvas(self.content, width=60, height=60, bg=BG, highlightthickness=0)
        c.pack(pady=(28, 12))
        c.create_oval(2, 2, 58, 58, fill=GREEN, outline="")
        c.create_line(16, 30, 26, 40, fill="white", width=3, capstyle="round", joinstyle="round")
        c.create_line(26, 40, 44, 20, fill="white", width=3, capstyle="round", joinstyle="round")

        tk.Label(self.content, text="Installation complete!",
                 font=F_H, bg=BG, fg=FG).pack(pady=(0, 10))
        tk.Label(self.content,
                 text=f"Model selected: {self.selected.get()}\n\n"
                      "A shortcut was created on your Desktop.\n"
                      "On first launch, Whisper downloads the model (~1.5 GB).",
                 font=F, bg=BG, fg=MUTED, justify="center").pack()

        self.btn_cancel.config(command=self.destroy)

    # ── custom widgets ────────────────────────────────────────────────────────

    def _draw_dot(self, canvas: tk.Canvas, selected: bool):
        canvas.delete("all")
        canvas.create_oval(1, 1, 17, 17,
                           outline=ACCENT if selected else MUTED, width=1.5, fill=SURFACE)
        if selected:
            canvas.create_oval(5, 5, 13, 13, fill=ACCENT, outline="")

    def _draw_checkbox(self, canvas: tk.Canvas, checked: bool):
        canvas.delete("all")
        bg = str(canvas["bg"])
        canvas.create_rectangle(1, 1, 17, 17,
                                 outline=ACCENT if checked else MUTED, width=1.5, fill=bg)
        if checked:
            canvas.create_line(4, 9,  8, 14, fill=ACCENT, width=2, capstyle="round")
            canvas.create_line(8, 14, 14, 5, fill=ACCENT, width=2, capstyle="round")

    # ── install logic ─────────────────────────────────────────────────────────

    def _do_install(self):
        src    = _app_dir()
        dest   = Path(self._install_dir.get())
        python = self.python_cmd
        model  = self.selected.get()
        try:
            self._progress("Copying files…", 5)
            dest.mkdir(parents=True, exist_ok=True)
            self._log(f"Destination: {dest}")
            if src.resolve() != dest.resolve():
                for f in [*src.glob("*.py"), src / "requirements.txt",
                           src / "VERSION", src / "flow-st8.vbs"]:
                    if f.exists():
                        shutil.copy2(f, dest / f.name)
                        self._log(f"  {f.name}")

            self._progress("Checking Python…", 15)
            if not python:
                self._fail("Python 3.11+ not found.\nInstall from python.org then re-run setup.")
                return
            self._log(f"Python: {python}")

            self._progress("Installing dependencies…", 25)
            self._log("pip install -r requirements.txt")
            r = subprocess.run(
                [python, "-m", "pip", "install", "-r", str(dest / "requirements.txt")],
                capture_output=True, text=True,
            )
            for line in r.stdout.splitlines()[-8:]:
                self._log(line)
            if r.returncode != 0:
                self._fail("pip install failed:\n" + r.stderr[-400:])
                return

            self._progress("Installing PyTorch…", 50)
            if self.has_gpu:
                self._log("GPU detected → installing CUDA 12.8 build (~2.7 GB)…")
                torch_args = ["torch", "--index-url", "https://download.pytorch.org/whl/cu128"]
            else:
                self._log("No GPU → installing CPU build…")
                torch_args = ["torch"]
            r = subprocess.run(
                [python, "-m", "pip", "install"] + torch_args,
                capture_output=True, text=True,
            )
            for line in r.stdout.splitlines()[-8:]:
                self._log(line)
            if r.returncode != 0:
                self._fail("torch install failed:\n" + r.stderr[-400:])
                return

            self._progress("Writing config…", 82)
            self._write_config(model)
            self._log(f"Model: {model}")

            self._progress("Creating shortcut…", 92)
            self._create_shortcut(dest)

            self._progress("Done!", 100)
            self._ui(self._go, "done")

        except Exception as exc:
            self._fail(str(exc))

    def _write_config(self, model: str):
        cfg_dir = Path(os.environ.get("APPDATA", "")) / "flow-st8"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        autostart = str(self._autostart_val).lower()
        (cfg_dir / "config.toml").write_text(
            f'[model]\nname = "{model}"\nlanguage = "auto"\ninitial_prompt = ""\n\n'
            '[hotkey]\nhold_key = "ctrl+win"\ntoggle_key = "ctrl+win+o"\n\n'
            '[audio]\ndevice_index = -1\nsample_rate = 16000\nchannels = 1\n'
            'chunk_ms = 32\nmax_seconds = 210\ngain = 1.8\n\n'
            '[vad]\nenabled = true\nsilence_threshold_ms = 1200\nspeech_threshold = 0.5\n\n'
            '[injection]\nmethod = "clipboard"\nrestore_clipboard = false\n\n'
            '[feedback]\nenabled = true\n\n'
            f'[startup]\nautostart = {autostart}\n',
            encoding="utf-8",
        )

    def _create_shortcut(self, dest: Path):
        try:
            desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
            vbs = dest / "flow-st8.vbs"
            lnk = str(desktop / "flow-st8.lnk")
            if vbs.exists():
                ps = (
                    f"$ws = New-Object -ComObject WScript.Shell; "
                    f"$s = $ws.CreateShortcut('{lnk}'); "
                    f"$s.TargetPath = 'wscript.exe'; "
                    f"$s.Arguments = '\"$([char]34){vbs}$([char]34)\"'; "
                    f"$s.WorkingDirectory = '{dest}'; "
                    f"$s.Save()"
                )
                subprocess.run(["powershell", "-Command", ps],
                               capture_output=True, timeout=10)
                self._log(f"Shortcut → {lnk}")
        except Exception as e:
            self._log(f"Could not create shortcut: {e}")

    def _fail(self, msg: str):
        self._ui(self._status.config, {"text": "Installation failed", "fg": RED})
        self._log(f"\nERROR: {msg}")
        self._ui(self._set_nav, cancel_label="Close", cancel_on=True,
                 back_on=False, next_on=False)

    def _launch(self):
        vbs = Path(self._install_dir.get()) / "flow-st8.vbs"
        if vbs.exists():
            os.startfile(str(vbs))
        self.destroy()

    # ── log helpers ───────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self._ui(self._append_log, msg)

    def _append_log(self, msg: str):
        self._log_box.config(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.config(state="disabled")

    def _progress(self, msg: str, pct: float):
        self._ui(self._status.config, {"text": msg})
        self._ui(self._bar.place, {"relwidth": pct / 100})

    def _ui(self, fn, *args, **kwargs):
        self.after(0, fn, *args, **kwargs)


if __name__ == "__main__":
    Installer().mainloop()

#!/usr/bin/env python3
"""
Clip Manager — Desktop UI
Run with:  python ui/app.py
"""

import os
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.timestamp import  parse_time, validate_time, format_seconds
from core.downloader import download_clip
from core.detector import detect

# ── Colour palette (works on light & dark OS themes) ──────────────────────────
BG       = "#1e1e2e"
SURFACE  = "#2a2a3e"
BORDER   = "#3a3a5c"
ACCENT   = "#7c6af7"
ACCENT2  = "#5ad4e6"
TEXT     = "#cdd6f4"
SUBTEXT  = "#a6adc8"
SUCCESS  = "#a6e3a1"
ERROR    = "#f38ba8"
WARNING  = "#fab387"


class ClipManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clip Manager")
        self.geometry("680x560")
        self.minsize(580, 480)
        self.configure(bg=BG)
        self.resizable(True, True)

        # State
        self._stream_info = None
        self._download_thread = None

        self._build_ui()
        self._center_window()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        hdr = tk.Frame(self, bg=BG, pady=16)
        hdr.pack(fill="x", padx=24)
        tk.Label(hdr, text="📹  Clip Manager", font=("Helvetica", 18, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text="Download any segment of any video",
                 font=("Helvetica", 11), bg=BG, fg=SUBTEXT).pack(side="left", padx=12)

        # ── Card: Source ──────────────────────────────────────────────────────
        src_card = self._card(self, "Source")

        self._url_var = tk.StringVar()
        url_row = tk.Frame(src_card, bg=SURFACE)
        url_row.pack(fill="x", pady=(0, 8))
        tk.Label(url_row, text="URL", width=6, anchor="w",
                 bg=SURFACE, fg=SUBTEXT, font=("Helvetica", 11)).pack(side="left")
        self._url_entry = self._entry(url_row, self._url_var, width=52)
        self._url_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._detect_btn = self._button(url_row, "Detect", self._on_detect, padx=8)
        self._detect_btn.pack(side="left", padx=(8, 0))

        # Stream info label
        self._info_var = tk.StringVar(value="")
        tk.Label(src_card, textvariable=self._info_var, bg=SURFACE,
                 fg=ACCENT2, font=("Helvetica", 10), anchor="w").pack(fill="x")

        # ── Card: Timestamps ─────────────────────────────────────────────────
        ts_card = self._card(self, "Clip range")

        ts_row = tk.Frame(ts_card, bg=SURFACE)
        ts_row.pack(fill="x")

        self._start_var = tk.StringVar(value="0:00")
        self._end_var   = tk.StringVar(value="0:30")

        tk.Label(ts_row, text="Start", width=6, anchor="w",
                 bg=SURFACE, fg=SUBTEXT, font=("Helvetica", 11)).pack(side="left")
        self._start_entry = self._entry(ts_row, self._start_var, width=12)
        self._start_entry.pack(side="left")

        tk.Label(ts_row, text="  End", width=5, anchor="w",
                 bg=SURFACE, fg=SUBTEXT, font=("Helvetica", 11)).pack(side="left")
        self._end_entry = self._entry(ts_row, self._end_var, width=12)
        self._end_entry.pack(side="left")

        self._duration_lbl = tk.Label(ts_row, text="", bg=SURFACE,
                                       fg=SUBTEXT, font=("Helvetica", 10))
        self._duration_lbl.pack(side="left", padx=12)

        # Bind live duration preview
        self._start_var.trace_add("write", self._update_duration_label)
        self._end_var.trace_add("write", self._update_duration_label)

        # ── Card: Output ──────────────────────────────────────────────────────
        out_card = self._card(self, "Output")

        fmt_row = tk.Frame(out_card, bg=SURFACE)
        fmt_row.pack(fill="x", pady=(0, 8))

        tk.Label(fmt_row, text="Format", width=6, anchor="w",
                 bg=SURFACE, fg=SUBTEXT, font=("Helvetica", 11)).pack(side="left")
        self._fmt_var = tk.StringVar(value="mp4")
        for fmt in ("mp4", "mp3", "mkv"):
            rb = tk.Radiobutton(fmt_row, text=fmt.upper(), variable=self._fmt_var,
                                value=fmt, bg=SURFACE, fg=TEXT,
                                selectcolor=ACCENT, activebackground=SURFACE,
                                font=("Helvetica", 11))
            rb.pack(side="left", padx=8)

        path_row = tk.Frame(out_card, bg=SURFACE)
        path_row.pack(fill="x")
        tk.Label(path_row, text="Save to", width=6, anchor="w",
                 bg=SURFACE, fg=SUBTEXT, font=("Helvetica", 11)).pack(side="left")
        self._path_var = tk.StringVar(value=str(Path.home() / "Downloads" / "clip.mp4"))
        self._path_entry = self._entry(path_row, self._path_var, width=44)
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._button(path_row, "Browse…", self._on_browse).pack(side="left", padx=(8, 0))

        # Auto-update extension when format changes
        self._fmt_var.trace_add("write", self._sync_path_extension)

        # ── Progress ─────────────────────────────────────────────────────────
        prog_frame = tk.Frame(self, bg=BG, padx=24)
        prog_frame.pack(fill="x", pady=(4, 0))

        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(prog_frame, textvariable=self._status_var, bg=BG,
                 fg=SUBTEXT, font=("Helvetica", 10), anchor="w").pack(fill="x")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Custom.Horizontal.TProgressbar",
                         troughcolor=SURFACE, background=ACCENT,
                         bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)
        self._progress = ttk.Progressbar(prog_frame, style="Custom.Horizontal.TProgressbar",
                                          maximum=100, length=400)
        self._progress.pack(fill="x", pady=(4, 0))

        # ── Download button ───────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG, pady=16)
        btn_row.pack()
        self._dl_btn = tk.Button(btn_row, text="⬇  Download Clip",
                                  font=("Helvetica", 13, "bold"),
                                  bg=ACCENT, fg="white",
                                  activebackground="#6a5be0", activeforeground="white",
                                  relief="flat", cursor="hand2", padx=28, pady=10,
                                  command=self._on_download)
        self._dl_btn.pack()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _card(self, parent, title: str) -> tk.Frame:
        wrapper = tk.Frame(parent, bg=BG, padx=24, pady=4)
        wrapper.pack(fill="x")
        tk.Label(wrapper, text=title.upper(), bg=BG, fg=SUBTEXT,
                 font=("Helvetica", 9, "bold")).pack(anchor="w", pady=(6, 2))
        card = tk.Frame(wrapper, bg=SURFACE, padx=16, pady=12,
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill="x")
        return card

    def _entry(self, parent, textvariable, **kwargs) -> tk.Entry:
        e = tk.Entry(parent, textvariable=textvariable,
                     bg=BORDER, fg=TEXT, insertbackground=TEXT,
                     relief="flat", font=("Helvetica", 11),
                     **kwargs)
        e.configure(highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=ACCENT)
        return e

    def _button(self, parent, text, command, **kwargs) -> tk.Button:
        return tk.Button(parent, text=text, command=command,
                         bg=SURFACE, fg=ACCENT, activebackground=BORDER,
                         activeforeground=ACCENT, relief="flat",
                         font=("Helvetica", 10), cursor="hand2",
                         highlightthickness=1, highlightbackground=BORDER,
                         **kwargs)

    def _center_window(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_detect(self):
        url = self._url_var.get().strip()
        if not url:
            self._set_status("Please enter a URL.", ERROR)
            return

        self._set_status("Detecting stream…", SUBTEXT)
        self._detect_btn.configure(state="disabled")

        def _detect():
            try:
                info = detect(url)
                self._stream_info = info
                type_label = {"platform": "Platform (yt-dlp)", "hls": "HLS Stream", "dash": "DASH Stream", "direct": "Direct File"}.get(info.stream_type.value, info.stream_type.value.upper())
                parts = [f"Type: {type_label}"]
                if info.title and info.title != "clip":
                    parts.append(f"  |  {info.title[:50]}")
                if info.duration:
                    parts.append(f"  |  Duration: {format_seconds(info.duration)}")
                    self.after(0, lambda: self._end_var.set(format_seconds(info.duration)))
                self.after(0, lambda: self._info_var.set("  ".join(parts)))
                self.after(0, lambda: self._set_status("Stream detected. Ready to download.", SUCCESS))
            except Exception as e:
                self.after(0, lambda err=e: self._set_status(f"Detection failed: {err}", ERROR))
            finally:
                self.after(0, lambda: self._detect_btn.configure(state="normal"))

        threading.Thread(target=_detect, daemon=True).start()

    def _on_browse(self):
        fmt = self._fmt_var.get()
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(f"{fmt.upper()} files", f"*.{fmt}"), ("All files", "*.*")],
            initialdir=str(Path.home() / "Downloads"),
            initialfile=f"clip.{fmt}",
        )
        if path:
            self._path_var.set(path)

    def _update_duration_label(self, *_):
        try:
            s = parse_time(self._start_var.get())
            e = parse_time(self._end_var.get())
            if e > s:
                self._duration_lbl.configure(
                    text=f"→  {format_seconds(e - s)} clip", fg=ACCENT2)
            else:
                self._duration_lbl.configure(text="", fg=SUBTEXT)
        except Exception:
            self._duration_lbl.configure(text="", fg=SUBTEXT)

    def _sync_path_extension(self, *_):
        fmt = self._fmt_var.get()
        current = self._path_var.get()
        p = Path(current)
        self._path_var.set(str(p.with_suffix(f".{fmt}")))

    def _on_download(self):
        if self._download_thread and self._download_thread.is_alive():
            messagebox.showinfo("In progress", "A download is already running.")
            return

        url = self._url_var.get().strip()
        if not url:
            self._set_status("Please enter a URL.", ERROR)
            return

        # Parse timestamps
        try:
            start = parse_time(self._start_var.get())
            end   = parse_time(self._end_var.get())
        except ValueError as e:
            self._set_status(str(e), ERROR)
            return

        # Detect if not already done
        stream = self._stream_info
        if stream is None or stream.url != url:
            try:
                self._set_status("Detecting stream…", SUBTEXT)
                stream = detect(url)
                self._stream_info = stream
            except Exception as e:
                self._set_status(f"Detection failed: {e}", ERROR)
                return

        # Validate
        try:
            validate_time(start, end, stream.duration)
        except ValueError as e:
            self._set_status(str(e), ERROR)
            return

        output_path = self._path_var.get().strip()
        if not output_path:
            self._set_status("Please choose an output path.", ERROR)
            return

        fmt = self._fmt_var.get()
        self._dl_btn.configure(state="disabled", text="Downloading…")
        self._progress["value"] = 0

        def _download():
            try:
                download_clip(
                    stream=stream,
                    start=start,
                    end=end,
                    output_path=output_path,
                    output_format=fmt,
                    on_progress=lambda pct, msg: self.after(0, lambda p=pct, m=msg: self._on_progress(p, m)),
                )
                self.after(0, lambda: self._set_status(
                    f"✅  Saved: {output_path}", SUCCESS))
            except Exception as e:
                self.after(0, lambda err=e: self._set_status(f"❌  {err}", ERROR))
            finally:
                self.after(0, lambda: self._dl_btn.configure(
                    state="normal", text="⬇  Download Clip"))

        self._download_thread = threading.Thread(target=_download, daemon=True)
        self._download_thread.start()

    def _on_progress(self, pct: float, msg: str):
        self._progress["value"] = pct
        self._set_status(msg, SUBTEXT)

    def _set_status(self, msg: str, colour: str = SUBTEXT):
        self._status_var.set(msg)
        # Find the status label and update its colour
        for widget in self.winfo_children():
            for child in getattr(widget, "winfo_children", lambda: [])():
                if isinstance(child, tk.Frame):
                    for grandchild in child.winfo_children():
                        if isinstance(grandchild, tk.Label) and \
                                grandchild.cget("textvariable") == str(self._status_var):
                            grandchild.configure(fg=colour)


def main():
    app = ClipManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
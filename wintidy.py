#!/usr/bin/env python3
"""
WinTidy - repair and clean Windows. Tick what you want, press Start.
Needs wintidy_core.py in the same folder. Must run as administrator (the Windows build asks
for it automatically). Looks best with the `sv-ttk` package (bundled in the Windows build);
follows the Windows light/dark setting.
"""
import os
import subprocess
import sys
import threading
import time

import wintidy_core as core

CHECK = {"all": "\u2611", "none": "\u2610", "partial": "\u25a3"}
STATUS = {"waiting": "\u25cb Waiting", "running": "\u25b6 Running\u2026", "ok": "\u2714 Done",
          "warn": "\u26a0 Done, check log", "fail": "\u2716 Failed", "skip": "\u2013 Skipped",
          "cancelled": "\u25a0 Stopped"}
REPAIR_TASKS = {"dism", "sfc", "chkdsk", "compclean"}
LOGO_B64 = "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"


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def system_is_dark():
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:  # noqa: BLE001
        return False


def set_dark_titlebar(root, dark):
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:  # noqa: BLE001
        pass


class App:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root = tk, ttk, root
        self.model = core.TaskModel()
        self.job = None
        self.estimates = {}
        self.est_thread = None
        self.est_result = None
        self.busy = False
        self.closing = False
        self.last_log = None
        self.last_notes = {}
        self._dark = None
        self._shown = {}
        self._task_mode = None
        self.log = None

        root.title("WinTidy")
        try:
            root.iconbitmap(resource_path("WinTidy.ico"))
        except Exception:  # noqa: BLE001
            pass
        self.style = ttk.Style()
        try:
            import sv_ttk
            self.sv = sv_ttk
        except Exception:  # noqa: BLE001
            self.sv = None
            for theme in ("vista", "clam"):
                if theme in self.style.theme_names():
                    self.style.theme_use(theme)
                    break
        self.check_theme()
        self._build()
        self.check_theme(force=True)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_all()
        self.start_estimates()

    # ---- theme -----------------------------------------------------------------
    def check_theme(self, force=False):
        dark = system_is_dark()
        if dark != self._dark or force:
            self._dark = dark
            if self.sv:
                try:
                    self.sv.set_theme("dark" if dark else "light")
                except Exception:  # noqa: BLE001
                    self.sv = None
            set_dark_titlebar(self.root, dark)
            if self.log is not None:                      # the log box is a plain Tk widget
                self.log.configure(bg="#1e1e1e" if dark else "#ffffff",
                                   fg="#e6e6e6" if dark else "#1a1a1a",
                                   insertbackground="#e6e6e6" if dark else "#1a1a1a")
        if not self.closing:
            self.root.after(2000, self.check_theme)

    # ---- layout -----------------------------------------------------------------
    def _build(self):
        tk, ttk, root = self.tk, self.ttk, self.root
        try:
            scale = max(1.0, float(root.winfo_fpixels("1i")) / 96)
        except Exception:  # noqa: BLE001
            scale = 1.0
        root.geometry(f"{int(900 * scale)}x{int(800 * scale)}")
        root.minsize(int(760 * scale), int(660 * scale))
        accent = "Accent.TButton" if self.sv else "TButton"

        self.desc = tk.StringVar(value="Click a task to read what it does.")
        self.summary = tk.StringVar()
        self.keep_recent = tk.BooleanVar(value=False)
        self.restart_done = tk.BooleanVar(value=False)
        self.overall_text = tk.StringVar(value="Ready")
        self.task_title = tk.StringVar()
        self.task_text = tk.StringVar()

        outer = ttk.Frame(root, padding=(20, 16))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=3)
        outer.rowconfigure(6, weight=2)

        head = ttk.Frame(outer)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        try:
            self.logo = tk.PhotoImage(data=LOGO_B64)
            ttk.Label(head, image=self.logo).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        except Exception:  # noqa: BLE001
            pass
        ttk.Label(head, text="WinTidy", font=("Segoe UI", 18, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(head, text="Repair and clean Windows. Tick what you want, then press Start.").grid(
            row=1, column=1, sticky="w")

        bar = ttk.Frame(outer)
        bar.grid(row=1, column=0, sticky="ew", pady=(14, 4))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.summary).grid(row=0, column=0, sticky="w")
        self.toolbar = []
        for col, (text, cmd) in enumerate((("Recommended", self.do_recommended),
                                           ("Select all", lambda: self.do_all(True)),
                                           ("Select none", lambda: self.do_all(False))), start=1):
            b = ttk.Button(bar, text=text, command=cmd)
            b.grid(row=0, column=col, padx=(6, 0))
            self.toolbar.append(b)

        box = ttk.Frame(outer)
        box.grid(row=2, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(box, columns=("check", "space", "status"), selectmode="browse", height=10)
        ys = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        self.tree.heading("#0", text="Task", anchor="w")
        self.tree.heading("check", text="Run")
        self.tree.heading("space", text="Can free", anchor="e")
        self.tree.heading("status", text="Result", anchor="w")
        self.tree.column("#0", stretch=True, minwidth=int(260 * scale), width=int(400 * scale))
        self.tree.column("check", width=int(56 * scale), anchor="center", stretch=False)
        self.tree.column("space", width=int(90 * scale), anchor="e", stretch=False)
        self.tree.column("status", width=int(150 * scale), anchor="w", stretch=False)
        self.tree.bind("<Button-1>", self.on_click)
        self.tree.bind("<space>", self.on_space)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        for gid, gtitle in core.GROUPS:
            self.tree.insert("", "end", iid="g:" + gid, text=gtitle, open=True,
                             values=(CHECK["none"], "", ""))
            for t in self.model.tasks:
                if t.group == gid:
                    self.tree.insert("g:" + gid, "end", iid=t.id, text=t.title,
                                     values=(CHECK["none"], "", ""))

        ttk.Label(outer, textvariable=self.desc, wraplength=int(840 * scale), justify="left").grid(
            row=3, column=0, sticky="w", pady=(8, 4))

        opts = ttk.Frame(outer)
        opts.grid(row=4, column=0, sticky="ew")
        self.chk_recent = ttk.Checkbutton(
            opts, text="Keep files changed in the last 24 hours", variable=self.keep_recent,
            command=self.start_estimates)
        self.chk_recent.grid(row=0, column=0, sticky="w", padx=(0, 24))
        self.chk_restart = ttk.Checkbutton(opts, text="Restart the PC when finished",
                                           variable=self.restart_done)
        self.chk_restart.grid(row=0, column=1, sticky="w")

        prog = ttk.Frame(outer)
        prog.grid(row=5, column=0, sticky="ew", pady=(10, 4))
        prog.columnconfigure(0, weight=1)
        ttk.Label(prog, textvariable=self.overall_text).grid(row=0, column=0, sticky="w")
        self.overall_bar = ttk.Progressbar(prog, maximum=100)
        self.overall_bar.grid(row=1, column=0, sticky="ew", pady=(2, 6))
        ttk.Label(prog, textvariable=self.task_title, font=("Segoe UI", 10, "bold")).grid(
            row=2, column=0, sticky="w")
        self.task_bar = ttk.Progressbar(prog, maximum=100)
        self.task_bar.grid(row=3, column=0, sticky="ew", pady=(2, 2))
        ttk.Label(prog, textvariable=self.task_text).grid(row=4, column=0, sticky="w")

        logbox = ttk.Frame(outer)
        logbox.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        logbox.columnconfigure(0, weight=1)
        logbox.rowconfigure(0, weight=1)
        self.log = tk.Text(logbox, height=6, wrap="word", state="disabled", relief="flat",
                           borderwidth=0, padx=8, pady=6, font=("Consolas", 9))
        ls = ttk.Scrollbar(logbox, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=ls.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        ls.grid(row=0, column=1, sticky="ns")

        buttons = ttk.Frame(outer)
        buttons.grid(row=7, column=0, sticky="e", pady=(10, 0))
        self.btn_log = ttk.Button(buttons, text="Open logs folder", command=self.open_logs)
        self.btn_log.grid(row=0, column=0, padx=4)
        self.btn_stop = ttk.Button(buttons, text="Stop", command=self.stop)
        self.btn_stop.grid(row=0, column=1, padx=4)
        self.btn_start = ttk.Button(buttons, text="Start", style=accent, command=self.start)
        self.btn_start.grid(row=0, column=2, padx=(4, 0))
        self._enable(self.btn_stop, False)

    @staticmethod
    def _enable(widget, on):
        widget.state(["!disabled"] if on else ["disabled"])

    # ---- ticking tasks ------------------------------------------------------------
    def refresh_all(self):
        for t in self.model.tasks:
            self.tree.set(t.id, "check", CHECK["all" if self.model.on[t.id] else "none"])
        for gid, _ in core.GROUPS:
            self.tree.set("g:" + gid, "check", CHECK[self.model.group_state(gid)])
        ids = self.model.selected()
        known = [self.estimates.get(i) or 0 for i in ids]
        text = f"{len(ids)} of {len(self.model.tasks)} tasks selected"
        if self.estimates and sum(known):
            text += f" · about {core.human_size(sum(known))} can be freed"
        self.summary.set(text)

    def toggle(self, iid):
        if self.busy:
            return
        if iid.startswith("g:"):
            self.model.toggle_group(iid[2:])
        elif iid in self.model.on:
            self.model.toggle(iid)
        self.refresh_all()

    def on_click(self, event):
        if self.busy or self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self.toggle(iid)

    def on_space(self, event):
        iid = self.tree.focus()
        if iid:
            self.toggle(iid)
        return "break"

    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        tid = sel[0]
        task = next((t for t in self.model.tasks if t.id == tid), None)
        if task is None:
            self.desc.set("")
            return
        text = task.desc
        if self.job and tid in self.job.notes:
            text += f"\nResult: {self.job.notes[tid]}"
        else:
            note = self.last_notes.get(tid)
            if note:
                text += f"\nResult: {note}"
        self.desc.set(text)

    def do_recommended(self):
        if not self.busy:
            self.model.recommended()
            self.refresh_all()

    def do_all(self, value):
        if not self.busy:
            self.model.set_all(value)
            self.refresh_all()

    # ---- size estimates (read-only) ------------------------------------------------
    def options(self):
        return {"keep_recent": self.keep_recent.get()}

    def start_estimates(self):
        if self.busy or (self.est_thread and self.est_thread.is_alive()):
            return
        opts = self.options()
        self.est_result = None

        def work():
            self.est_result = core.estimate_sizes(opts)

        self.est_thread = threading.Thread(target=work, daemon=True)
        self.est_thread.start()
        for t in self.model.tasks:
            if t.paths or t.id == "recycle":
                self.tree.set(t.id, "space", "\u2026")
        self.root.after(250, self.poll_estimates)

    def poll_estimates(self):
        if self.est_thread.is_alive():
            self.root.after(250, self.poll_estimates)
            return
        self.estimates = self.est_result or {}
        for t in self.model.tasks:
            if t.paths or t.id == "recycle":
                size = self.estimates.get(t.id)
                self.tree.set(t.id, "space", core.human_size(size) if size else "")
        self.refresh_all()

    # ---- running ------------------------------------------------------------------
    def set_busy(self, busy):
        self.busy = busy
        self._enable(self.btn_start, not busy)
        self._enable(self.btn_stop, busy)
        for w in (*self.toolbar, self.chk_recent, self.chk_restart):
            self._enable(w, not busy)
        if not busy:
            self.task_bar.stop()
            self.task_bar.configure(mode="determinate", value=0)
            self._task_mode = None

    def start(self):
        from tkinter import messagebox
        if self.busy:
            return
        ids = self.model.selected()
        if not ids:
            messagebox.showinfo("WinTidy", "Tick at least one task first.")
            return
        if core.IS_WIN and not core.is_admin():
            messagebox.showerror("WinTidy", "WinTidy needs administrator rights.\n"
                                            "Close it and start it again with 'Run as administrator'.")
            return
        warn = []
        if "recycle" in ids:
            warn.append("The Recycle Bin will be emptied permanently.")
        if "windows_old" in ids:
            warn.append("You will no longer be able to go back to the previous Windows version.")
        if "netreset" in ids:
            warn.append("Network settings will be reset (a restart is needed).")
        text = (f"Run {len(ids)} task(s)?\n\nRepairs can take 30 minutes or more. Close your other "
                "programs first, and keep the PC plugged in.")
        if warn:
            text += "\n\n" + "\n".join("\u2022 " + w for w in warn)
        if not messagebox.askyesno("WinTidy", text, icon="warning", default="no"):
            return
        self.last_notes = {}
        self.job = core.RunJob(ids, self.options(), self.estimates)
        self.last_log = self.job.log_path
        self._shown = {}
        for t in self.model.tasks:
            self.tree.set(t.id, "status", STATUS["waiting"] if t.id in ids else "")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.set_busy(True)
        self.job.start()
        self.poll()

    def _drain_log(self, job):
        lines = []
        try:
            while True:
                lines.append(job.log_q.get_nowait())
        except Exception:  # noqa: BLE001  (queue.Empty)
            pass
        if lines:
            self.log.configure(state="normal")
            self.log.insert("end", "\n".join(lines) + "\n")
            try:
                if int(self.log.index("end-1c").split(".")[0]) > 3000:
                    self.log.delete("1.0", "1000.0")
            except Exception:  # noqa: BLE001
                pass
            self.log.configure(state="disabled")
            self.log.see("end")

    def _refresh_status(self, job):
        for tid, st in list(job.states.items()):
            if self._shown.get(tid) != st:
                self._shown[tid] = st
                self.tree.set(tid, "status", STATUS[st])
                if st == "running":
                    self.tree.see(tid)

    def poll(self):
        job = self.job
        self._drain_log(job)
        self._refresh_status(job)
        elapsed = int((job.t1 or time.time()) - (job.t0 or time.time()))
        self.overall_bar.configure(value=job.overall * 100)
        self.overall_text.set(f"{job.overall * 100:.0f}% complete  \u00b7  {elapsed // 60}:{elapsed % 60:02d} elapsed")
        cur = job.current
        self.task_title.set(cur.title if cur else "")
        self.task_text.set(job.task_text)
        frac = job.task_fraction
        mode = "indeterminate" if (cur and frac is None) else "determinate"
        if mode != self._task_mode:
            self._task_mode = mode
            self.task_bar.stop()
            self.task_bar.configure(mode=mode)
            if mode == "indeterminate":
                self.task_bar.start(12)
        if mode == "determinate":
            self.task_bar.configure(value=(frac or 0) * 100)
        if job.is_alive() or not job.finished:
            self.root.after(150, self.poll)
        else:
            self.finish()

    def finish(self):
        from tkinter import messagebox
        job = self.job
        self._drain_log(job)
        self._refresh_status(job)
        self.last_notes = dict(job.notes)
        self.job = None
        self.set_busy(False)
        self.overall_bar.configure(value=job.overall * 100)
        self.task_title.set("")
        self.task_text.set("")
        n = {k: sum(1 for s in job.states.values() if s == k) for k in ("ok", "warn", "fail")}
        total = int((job.t1 or time.time()) - job.t0)
        if job.cancelled:
            self.overall_text.set("Stopped")
        else:
            self.overall_text.set(f"Finished in {total // 60}:{total % 60:02d}")
        lines = [("Stopped before finishing." if job.cancelled else f"Finished in {total // 60}:{total % 60:02d}."),
                 f"{n['ok']} done \u00b7 {n['warn']} {'needs' if n['warn'] == 1 else 'need'} a look \u00b7 {n['fail']} failed"]
        if job.freed:
            lines.append(f"Removed about {core.human_size(job.freed)} of files.")
        if job.free_before is not None and job.free_after is not None:
            lines.append(f"Free space on {core.sysdrive()}: {core.human_size(job.free_before)} \u2192 "
                         f"{core.human_size(job.free_after)}")
        lines.append(f"\nFull log: {job.log_path}")
        if not self.closing:
            (messagebox.showwarning if n["fail"] else messagebox.showinfo)("WinTidy", "\n".join(lines))
            if not job.cancelled and self.restart_done.get():
                self.restart(30)
            elif not job.cancelled and job.restart_needed:
                if messagebox.askyesno("WinTidy", "Some changes only finish after a restart.\n\n"
                                                  "Restart the PC now?"):
                    self.restart(10)
        self.on_select()
        if self.closing:
            self.root.destroy()
        else:
            self.start_estimates()

    def restart(self, seconds):
        from tkinter import messagebox
        try:
            subprocess.run([core.system32("shutdown.exe"), "/r", "/t", str(seconds), "/c",
                            "WinTidy finished. Restarting."], creationflags=core.NO_WINDOW)
        except OSError as e:
            messagebox.showerror("WinTidy", f"Couldn't restart: {e}")
            return
        if messagebox.askyesno("WinTidy", f"The PC will restart in {seconds} seconds.\n\n"
                                          "Cancel the restart?"):
            subprocess.run([core.system32("shutdown.exe"), "/a"], creationflags=core.NO_WINDOW)

    def stop(self):
        from tkinter import messagebox
        job = self.job
        if not job:
            return
        if job.current and job.current.id in REPAIR_TASKS and not messagebox.askyesno(
                "WinTidy", "A repair is running. Stopping it half-way is usually safe, but not "
                           "recommended.\n\nStop anyway?", icon="warning", default="no"):
            return
        self._enable(self.btn_stop, False)
        self.overall_text.set("Stopping\u2026")
        job.cancel()

    def open_logs(self):
        path = os.path.dirname(self.last_log) if self.last_log else core.log_dir()
        if sys.platform.startswith("win"):
            os.startfile(path)                                   # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])

    def on_close(self):
        if self.job:
            from tkinter import messagebox
            if not messagebox.askyesno("WinTidy", "Work is in progress. Stop and exit?"):
                return
            self.closing = True
            self._enable(self.btn_stop, False)
            self.job.cancel()                       # the window closes once the job has stopped
            return
        self.closing = True
        self.root.destroy()


def main():
    import tkinter as tk
    from tkinter import messagebox
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
        if not core.is_admin():
            if core.relaunch_as_admin():
                return
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("WinTidy", "WinTidy needs administrator rights to repair Windows.")
            return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

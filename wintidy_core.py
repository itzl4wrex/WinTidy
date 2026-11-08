"""
wintidy_core.py - the engine of WinTidy (repair + clean Windows).

No GUI in here. Everything the window shows comes from a RunJob (a thread) and the TASKS list.
"""
import ctypes
import glob
import os
import queue
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time

IS_WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if IS_WIN else 0          # CREATE_NO_WINDOW
PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def human_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def sysroot():
    return os.environ.get("SystemRoot", r"C:\Windows")


def sysdrive():
    return os.environ.get("SystemDrive", "C:")


def system32(name):
    return os.path.join(sysroot(), "System32", name)


def free_space():
    try:
        return shutil.disk_usage(sysdrive() + os.sep).free
    except OSError:
        return None


def oem_encoding():
    """Console programs (DISM, chkdsk...) write in the OEM code page."""
    if IS_WIN:
        try:
            return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        except Exception:  # noqa: BLE001
            pass
    return "utf-8"


def is_admin():
    if IS_WIN:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # noqa: BLE001
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def relaunch_as_admin():
    """Ask Windows (UAC) to start this program again with administrator rights."""
    if not IS_WIN:
        return False
    quote = lambda a: '"' + a.replace('"', '\\"') + '"'          # noqa: E731
    if getattr(sys, "frozen", False):
        args = " ".join(quote(a) for a in sys.argv[1:])
    else:
        args = " ".join(quote(a) for a in sys.argv)
    try:
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1) > 32
    except Exception:  # noqa: BLE001
        return False


def log_dir():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    path = os.path.join(base, "WinTidy", "logs")
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# Safe deletion: only ever the CONTENTS of a folder, never links, never short paths
# --------------------------------------------------------------------------
class Stats:
    def __init__(self):
        self.files = 0
        self.bytes = 0
        self.skipped = 0


def _is_reparse(entry):
    """Junctions and other reparse points: remove the link itself, never follow it."""
    try:
        return bool(entry.stat(follow_symlinks=False).st_file_attributes & 0x400)
    except (AttributeError, OSError):
        return False


def _too_shallow(path):
    parts = [p for p in os.path.normpath(os.path.abspath(path)).replace("\\", "/").split("/") if p]
    return len(parts) < 3                                      # C:\Windows\Temp = 3 parts


def _remove_file(path, stats, dry_run, cutoff, tick):
    try:
        st = os.lstat(path)
    except OSError:
        stats.skipped += 1
        return False
    if cutoff is not None and st.st_mtime > cutoff:
        stats.skipped += 1                                    # recent file: kept on purpose
        return False
    if not dry_run:
        try:
            os.unlink(path)
        except PermissionError:
            try:
                os.chmod(path, stat.S_IWRITE)                 # read-only file
                os.unlink(path)
            except OSError:
                stats.skipped += 1
                return False
        except OSError:
            stats.skipped += 1                                # in use by a program
            return False
    stats.files += 1
    stats.bytes += st.st_size
    if tick:
        tick()
    return True


def _walk(path, stats, dry_run, cutoff, cancelled, tick):
    """Delete what is inside `path`. Returns True if something remains in it."""
    remaining = False
    try:
        entries = list(os.scandir(path))
    except OSError:
        stats.skipped += 1
        return True
    for e in entries:
        if cancelled():
            raise Cancelled()
        try:
            is_dir = e.is_dir(follow_symlinks=False)
        except OSError:
            is_dir = False
        if is_dir and not _is_reparse(e):
            left = _walk(e.path, stats, dry_run, cutoff, cancelled, tick)
            if not left and not dry_run:
                try:
                    os.rmdir(e.path)
                except OSError:
                    left = True
            remaining = remaining or left
        elif is_dir:                                          # junction: drop the link only
            if not dry_run:
                try:
                    os.rmdir(e.path)
                except OSError:
                    remaining = True
        elif not _remove_file(e.path, stats, dry_run, cutoff, tick):
            remaining = True
    return remaining


def purge_path(path, stats, dry_run=False, cutoff=None, cancelled=None, tick=None):
    """Empty a folder (or delete one file). The folder itself is kept."""
    cancelled = cancelled or (lambda: False)
    if not path or _too_shallow(path):
        raise ValueError(f"Refusing to clean a top-level path: {path!r}")
    if os.path.islink(path):
        return
    if os.path.isfile(path):
        _remove_file(path, stats, dry_run, cutoff, tick)
    elif os.path.isdir(path):
        _walk(path, stats, dry_run, cutoff, cancelled, tick)


# --------------------------------------------------------------------------
# Where the junk lives
# --------------------------------------------------------------------------
def paths_temp_win():
    return [os.path.join(sysroot(), "Temp")]


def paths_temp_user():
    t = os.environ.get("TEMP") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp")
    # Safety net: only ever clean a folder that is really called Temp/Tmp
    if t and os.path.basename(os.path.normpath(t)).lower() in ("temp", "tmp"):
        return [t]
    return []


def paths_prefetch():
    return [os.path.join(sysroot(), "Prefetch")]


def paths_wu_cache():
    return [os.path.join(sysroot(), "SoftwareDistribution", "Download")]


def paths_browsers():
    local = os.environ.get("LOCALAPPDATA", "")
    out = []
    if not local:
        return out
    for vendor in (r"Microsoft\Edge", r"Google\Chrome", r"BraveSoftware\Brave-Browser",
                   r"Vivaldi", r"Opera Software\Opera Stable"):
        ud = os.path.join(local, vendor, "User Data")
        if os.path.isdir(ud):
            for prof in os.listdir(ud):
                if prof == "Default" or prof.startswith("Profile"):
                    for sub in ("Cache", "Code Cache", "GPUCache"):
                        p = os.path.join(ud, prof, sub)
                        if os.path.isdir(p):
                            out.append(p)
    for prof in glob.glob(os.path.join(local, "Mozilla", "Firefox", "Profiles", "*")):
        p = os.path.join(prof, "cache2")
        if os.path.isdir(p):
            out.append(p)
    return out


def paths_crash():
    pd = os.environ.get("ProgramData", r"C:\ProgramData")
    local = os.environ.get("LOCALAPPDATA", "")
    wer = os.path.join(pd, "Microsoft", "Windows", "WER")
    out = [os.path.join(wer, "ReportQueue"), os.path.join(wer, "ReportArchive"),
           os.path.join(wer, "Temp"), os.path.join(sysroot(), "Minidump"),
           os.path.join(sysroot(), "LiveKernelReports"), os.path.join(sysroot(), "MEMORY.DMP")]
    if local:
        out += [os.path.join(local, "CrashDumps"), os.path.join(local, "Microsoft", "Windows", "WER")]
    return [p for p in out if os.path.exists(p)]


def recycle_bin_size():
    if not IS_WIN:
        return None
    try:
        from ctypes import wintypes

        class Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong),
                        ("i64NumItems", ctypes.c_longlong)]
        info = Info()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return info.i64Size
    except Exception:  # noqa: BLE001
        pass
    return None


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------
class Task:
    def __init__(self, id, group, title, desc, default, weight, run, paths=None):
        self.id, self.group, self.title, self.desc = id, group, title, desc
        self.default, self.weight, self.run, self.paths = default, weight, run, paths


def _need_windows(job):
    return "skip", "Only available on Windows"


def t_restore_point(job):
    if not IS_WIN:
        return _need_windows(job)
    ps = system32(r"WindowsPowerShell\v1.0\powershell.exe")
    code = job.run_cmd([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                        "Checkpoint-Computer -Description 'WinTidy' "
                        "-RestorePointType MODIFY_SETTINGS -ErrorAction Stop"])
    if code == 0:
        return "ok", "Restore point created"
    return "warn", ("No restore point (System Protection may be off, or one was made in the "
                    "last 24 hours). Continuing.")


def t_dism_restore(job):
    if not IS_WIN:
        return _need_windows(job)
    code = job.run_cmd([system32("Dism.exe"), "/Online", "/Cleanup-Image", "/RestoreHealth"])
    if code == 0:
        return "ok", "Windows component store checked and repaired"
    if code == 3010:
        job.restart_needed = True
        return "ok", "Repaired. A restart finishes the job"
    return "fail", f"DISM stopped with code {code}. It needs an internet connection; see the log"


def t_sfc(job):
    if not IS_WIN:
        return _need_windows(job)
    code = job.run_cmd([system32("sfc.exe"), "/scannow"])
    text = " ".join(job.output).lower()
    if "unable to fix" in text:
        return "warn", "Some damaged files couldn't be repaired. See the log and CBS.log"
    if "successfully repaired" in text:
        job.restart_needed = True
        return "ok", "Damaged files were found and repaired"
    if "did not find any integrity violations" in text:
        return "ok", "No problems found"
    if code == 0:
        return "ok", "Scan finished. See the log for details"
    return "warn", f"Finished with code {code}. See the log"


def t_chkdsk(job):
    if not IS_WIN:
        return _need_windows(job)
    code = job.run_cmd([system32("chkdsk.exe"), sysdrive(), "/scan"])
    return ("ok", "No disk errors found") if code == 0 else (
        "warn", f"chkdsk reported code {code}. See the log")


def t_component_cleanup(job):
    if not IS_WIN:
        return _need_windows(job)
    code = job.run_cmd([system32("Dism.exe"), "/Online", "/Cleanup-Image", "/StartComponentCleanup"])
    if code == 3010:
        job.restart_needed = True
    return ("ok", "Old Windows update files removed") if code in (0, 3010) else (
        "warn", f"DISM reported code {code}. See the log")


def run_purge(job, paths):
    stats = Stats()
    cutoff = time.time() - 86400 if job.options.get("keep_recent") else None
    est = job.estimates.get(job.current.id) or 0

    def tick():
        frac = min(0.99, stats.bytes / est) if est else None
        job.set_task_progress(frac, f"{stats.files:,} files removed · {human_size(stats.bytes)}")

    for p in paths:
        purge_path(p, stats, cutoff=cutoff, cancelled=lambda: job.cancelled, tick=tick)
    job.freed += stats.bytes
    note = f"Removed {stats.files:,} files ({human_size(stats.bytes)})"
    if stats.skipped:
        note += f"; {stats.skipped:,} in use or kept"
    return "ok", note


def _purge_task(path_fn):
    def run(job):
        paths = path_fn()
        if not paths:
            return "skip", "Nothing to clean here"
        return run_purge(job, paths)
    return run


def _service_running(job, name):
    out = subprocess.run([system32("sc.exe"), "query", name], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    m = re.search(r"STATE\s*:\s*(\d+)", out or "")
    return bool(m) and m.group(1) == "4"


def t_wu_cache(job):
    if not IS_WIN:
        return _need_windows(job)
    stopped = []
    try:
        for svc in ("wuauserv", "bits"):
            if _service_running(job, svc):
                job.run_cmd([system32("net.exe"), "stop", svc, "/y"])
                stopped.append(svc)
        return run_purge(job, paths_wu_cache())
    finally:
        for svc in reversed(stopped):                           # always switch them back on
            job.run_cmd([system32("net.exe"), "start", svc], cancelable=False)


def t_recycle(job):
    if not IS_WIN:
        return _need_windows(job)
    size = recycle_bin_size() or 0
    res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7) & 0xFFFFFFFF
    if res in (0, 0x8000FFFF):                                  # OK / already empty
        job.freed += size
        return "ok", f"Recycle Bin emptied ({human_size(size)})" if size else "Recycle Bin was already empty"
    return "warn", f"Windows reported code {res:#x}"


VOLUME_CACHES = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches"
CLEANMGR_FLAG = "StateFlags0099"
# Never ticked automatically: they can delete personal files or limit what you can undo
CLEANMGR_SKIP = {"DownloadsFolder", "Recycle Bin", "Language Pack", "Previous Installations"}


def _cleanmgr(job, include=None, exclude=()):
    if not IS_WIN:
        return _need_windows(job)
    import winreg
    names, i = [], 0
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VOLUME_CACHES) as k:
        while True:
            try:
                names.append(winreg.EnumKey(k, i))
                i += 1
            except OSError:
                break
    chosen = [n for n in names if (include is None or n in include) and n not in exclude]
    ticked = []
    try:
        for n in chosen:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VOLUME_CACHES + "\\" + n, 0,
                                    winreg.KEY_SET_VALUE) as sk:
                    winreg.SetValueEx(sk, CLEANMGR_FLAG, 0, winreg.REG_DWORD, 2)
                    ticked.append(n)
            except OSError:
                pass
        if not ticked:
            return "skip", "Nothing to clean here"
        job.log(f"Disk Cleanup categories selected: {len(ticked)}")
        job.set_task_progress(None, "Windows Disk Cleanup is running…")
        proc = subprocess.Popen([system32("cleanmgr.exe"), "/sagerun:99"], creationflags=NO_WINDOW)
        job.proc = proc
        while proc.poll() is None:
            if job.cancelled:
                proc.terminate()
                raise Cancelled()
            time.sleep(0.5)
    finally:
        job.proc = None
        for n in ticked:                                        # leave the registry as we found it
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VOLUME_CACHES + "\\" + n, 0,
                                    winreg.KEY_SET_VALUE) as sk:
                    winreg.DeleteValue(sk, CLEANMGR_FLAG)
            except OSError:
                pass
    return "ok", f"Disk Cleanup finished ({len(ticked)} categories)"


def t_cleanmgr(job):
    return _cleanmgr(job, exclude=CLEANMGR_SKIP)


def t_windows_old(job):
    return _cleanmgr(job, include={"Previous Installations"})


def t_flushdns(job):
    if not IS_WIN:
        return _need_windows(job)
    code = job.run_cmd([system32("ipconfig.exe"), "/flushdns"])
    return ("ok", "DNS cache cleared") if code == 0 else ("warn", f"ipconfig reported code {code}")


def t_network_reset(job):
    if not IS_WIN:
        return _need_windows(job)
    a = job.run_cmd([system32("netsh.exe"), "winsock", "reset"])
    b = job.run_cmd([system32("netsh.exe"), "int", "ip", "reset"])
    job.restart_needed = True
    return ("ok", "Network stack reset. Restart to finish") if a == 0 and b == 0 else (
        "warn", "Network reset reported errors. See the log")


def t_optimize(job):
    if not IS_WIN:
        return _need_windows(job)
    code = job.run_cmd([system32("defrag.exe"), sysdrive(), "/O"])
    return ("ok", "Drive optimized") if code == 0 else ("warn", f"defrag reported code {code}")


GROUPS = [("repair", "Repair Windows"), ("clean", "Clean up files"), ("extras", "Network and extras")]

# Order matters: DISM first (it repairs the store that SFC relies on), then cleaning last.
TASKS = [
    Task("restore", "repair", "Create a restore point",
         "A safety net: lets you roll Windows back if a repair ever goes wrong. Skipped quietly if "
         "System Protection is off.", True, 3, t_restore_point),
    Task("dism", "repair", "Repair Windows image (DISM RestoreHealth)",
         "Checks the Windows component store and repairs it using Windows Update. Needs internet. "
         "Can take 10-30 minutes.", True, 25, t_dism_restore),
    Task("sfc", "repair", "Check system files (SFC /scannow)",
         "Scans every protected Windows file and replaces damaged ones. Can take 10-20 minutes.",
         True, 25, t_sfc),
    Task("chkdsk", "repair", "Scan the disk for errors (chkdsk, read-only)",
         "Looks for file system errors without taking the PC offline. Nothing is changed unless "
         "you run a repair yourself later.", False, 10, t_chkdsk),
    Task("compclean", "repair", "Clean old update files (DISM component cleanup)",
         "Removes superseded Windows update files from the component store. Safe, but it means "
         "you can't uninstall the oldest updates.", True, 12, t_component_cleanup),
    Task("temp_win", "clean", "Windows temp folder (C:\\Windows\\Temp)",
         "Temporary files left by Windows and installers. Files in use are skipped.",
         True, 3, _purge_task(paths_temp_win), paths_temp_win),
    Task("temp_user", "clean", "Your temp folder (AppData\\Local\\Temp)",
         "Temporary files from your programs. Files in use are skipped.",
         True, 3, _purge_task(paths_temp_user), paths_temp_user),
    Task("prefetch", "clean", "Prefetch (C:\\Windows\\Prefetch)",
         "Windows' app start-up hints. Harmless to delete; Windows rebuilds it, so the first launch "
         "of each program may be a little slower.", True, 1, _purge_task(paths_prefetch), paths_prefetch),
    Task("wu_cache", "clean", "Windows Update download cache",
         "Downloaded update files that are already installed. Windows Update is paused for a moment "
         "and switched back on.", True, 3, t_wu_cache, paths_wu_cache),
    Task("browsers", "clean", "Browser caches (Edge, Chrome, Firefox...)",
         "Cached web pages and images only. Passwords, history and logins are not touched. Close "
         "your browsers first for the best result.", True, 3, _purge_task(paths_browsers), paths_browsers),
    Task("crash", "clean", "Error reports and crash dumps",
         "Windows error reports and memory dumps. Useful only for troubleshooting crashes.",
         True, 2, _purge_task(paths_crash), paths_crash),
    Task("cleanmgr", "clean", "Windows Disk Cleanup (all categories)",
         "Runs the built-in Disk Cleanup with every category ticked, except your Downloads folder, "
         "the Recycle Bin, language packs and the previous Windows installation (separate options).",
         True, 10, t_cleanmgr),
    Task("recycle", "clean", "Empty the Recycle Bin",
         "Permanently deletes everything in the Recycle Bin. Off by default.", False, 1, t_recycle),
    Task("windows_old", "clean", "Previous Windows installation (Windows.old)",
         "Frees many GB after an upgrade, but you can no longer go back to the old Windows version. "
         "Off by default.", False, 5, t_windows_old),
    Task("dns", "extras", "Flush the DNS cache",
         "Clears stored website addresses. Fixes some 'site not found' problems.", True, 1, t_flushdns),
    Task("netreset", "extras", "Reset network settings (Winsock / IP)",
         "Fixes stubborn connection problems. Resets network settings to default; needs a restart. "
         "Off by default.", False, 1, t_network_reset),
    Task("optimize", "extras", "Optimize the system drive (TRIM / defrag)",
         "Trims an SSD or defragments a hard disk. Can take a while. Off by default.",
         False, 10, t_optimize),
]


def estimate_sizes(options, cancelled=None):
    """How much each cleaning task could free (read-only; deletes nothing)."""
    cancelled = cancelled or (lambda: False)
    cutoff = time.time() - 86400 if options.get("keep_recent") else None
    out = {}
    for t in TASKS:
        if t.paths:
            st = Stats()
            for p in t.paths():
                try:
                    purge_path(p, st, dry_run=True, cutoff=cutoff, cancelled=cancelled)
                except (ValueError, OSError):
                    pass
            out[t.id] = st.bytes
        elif t.id == "recycle":
            out[t.id] = recycle_bin_size()
    return out


# --------------------------------------------------------------------------
# Which tasks are ticked (pure logic, no GUI)
# --------------------------------------------------------------------------
class TaskModel:
    def __init__(self, tasks=None):
        self.tasks = tasks or TASKS
        self.on = {t.id: t.default for t in self.tasks}

    def ids(self, group):
        return [t.id for t in self.tasks if t.group == group]

    def toggle(self, tid):
        self.on[tid] = not self.on[tid]

    def group_state(self, group):
        n = sum(self.on[i] for i in self.ids(group))
        return "none" if n == 0 else "all" if n == len(self.ids(group)) else "partial"

    def toggle_group(self, group):
        target = self.group_state(group) != "all"
        for i in self.ids(group):
            self.on[i] = target

    def set_all(self, value):
        for i in self.on:
            self.on[i] = value

    def recommended(self):
        for t in self.tasks:
            self.on[t.id] = t.default

    def selected(self):
        return [t.id for t in self.tasks if self.on[t.id]]


# --------------------------------------------------------------------------
# The job: runs the chosen tasks one after the other in a thread
# --------------------------------------------------------------------------
class RunJob(threading.Thread):
    def __init__(self, selected_ids, options=None, estimates=None, tasks=None):
        super().__init__(daemon=True)
        tasks = tasks or TASKS
        self.tasks = [t for t in tasks if t.id in set(selected_ids)]
        self.options = options or {}
        self.estimates = estimates or {}
        self.states = {t.id: "waiting" for t in self.tasks}
        self.notes = {}
        self.log_q = queue.Queue()
        self.current = None
        self.task_fraction = None
        self.task_text = ""
        self.overall = 0.0
        self.finished = False
        self.freed = 0
        self.restart_needed = False
        self.output = []                 # lines printed by the command that is running now
        self.proc = None
        self.t0 = self.t1 = None
        self.free_before = self.free_after = None
        self._cancel = threading.Event()
        self._done_weight = 0
        self._total_weight = sum(t.weight for t in self.tasks) or 1
        self.log_path = os.path.join(log_dir(), time.strftime("wintidy-%Y%m%d-%H%M%S.log"))
        self._logfile = None

    # ---- called from the window ---------------------------------------------
    @property
    def cancelled(self):
        return self._cancel.is_set()

    def cancel(self):
        self._cancel.set()
        proc = self.proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    # ---- called by tasks -----------------------------------------------------
    def log(self, msg):
        self.log_q.put(msg)
        if self._logfile:
            try:
                self._logfile.write(msg + "\n")
                self._logfile.flush()
            except OSError:
                pass

    def set_task_progress(self, frac, text=""):
        self.task_fraction = frac
        if text:
            self.task_text = text
        weight = self.current.weight if self.current else 0
        self.overall = min(1.0, (self._done_weight + weight * (frac or 0)) / self._total_weight)

    def run_cmd(self, cmd, cancelable=True):
        """Run a console program, show its output live and turn '45%' into progress."""
        self.log("> " + " ".join(cmd))
        self.output = []
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        except OSError as e:
            raise RuntimeError(f"Couldn't start {os.path.basename(cmd[0])}: {e}")
        self.proc = proc
        enc, carry, partial = oem_encoding(), b"", ""
        try:
            while True:
                chunk = proc.stdout.read1(4096)
                if not chunk:
                    break
                data, carry = carry + chunk, b""
                if data.count(b"\x00") * 4 >= len(data):          # sfc writes UTF-16
                    if len(data) % 2:
                        data, carry = data[:-1], data[-1:]
                    text = data.decode("utf-16-le", "replace").lstrip("\ufeff")
                else:
                    text = data.decode(enc, "replace")
                partial = self._consume(partial + text)
            if partial.strip():
                self._line(partial)
            code = proc.wait()
        finally:
            self.proc = None
            if proc.poll() is None:
                proc.kill()
        if cancelable and self.cancelled:
            raise Cancelled()
        return code

    def _consume(self, buf):
        parts = re.split(r"[\r\n]", buf)
        for seg in parts[:-1]:
            self._line(seg)
        m = PERCENT.findall(parts[-1])                            # progress bar still being drawn
        if m:
            self._percent(m[-1])
        return parts[-1]

    def _percent(self, value):
        try:
            self.set_task_progress(max(0.0, min(100.0, float(value.replace(",", ".")))) / 100)
        except ValueError:
            pass

    def _line(self, seg):
        seg = seg.strip()
        if not seg:
            return
        m = PERCENT.search(seg)
        if m and len(seg) <= 70:                                  # "Verification 45% complete."
            self._percent(m.group(1))
            self.task_text = seg
            return
        self.output.append(seg)
        self.task_text = seg[:100]
        self.log(seg)

    # ---- the thread ---------------------------------------------------------
    def run(self):
        self.t0 = time.time()
        self.free_before = free_space()
        try:
            self._logfile = open(self.log_path, "a", encoding="utf-8")
        except OSError:
            self._logfile = None
        self.log(f"WinTidy started {time.strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            for t in self.tasks:
                if self.cancelled:
                    break
                self.current = t
                self.states[t.id] = "running"
                self.task_fraction, self.task_text = None, ""
                self.set_task_progress(None)
                self.log(f"\n=== {t.title} ===")
                try:
                    status, note = t.run(self)
                except Cancelled:
                    self.states[t.id] = "cancelled"
                    self.notes[t.id] = "Stopped"
                    self.log("Stopped by the user")
                    break
                except Exception as e:  # noqa: BLE001
                    status, note = "fail", str(e)
                self.states[t.id], self.notes[t.id] = status, note
                self.log(f"[{status.upper()}] {note}")
                self._done_weight += t.weight
                self.overall = min(1.0, self._done_weight / self._total_weight)
            for t in self.tasks:
                if self.states[t.id] == "waiting":
                    self.states[t.id], self.notes[t.id] = "skip", "Not run"
        finally:
            self.free_after = free_space()
            self.t1 = time.time()
            self.current = None
            self.task_fraction = None
            if not self.cancelled:
                self.overall = 1.0
            self.log(f"\nFinished. Log saved to {self.log_path}")
            if self._logfile:
                self._logfile.close()
            self.finished = True

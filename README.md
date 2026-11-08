# WinTidy

WinTidy repairs and cleans Windows in one place. Tick the tasks you want, press Start, and watch the progress live.

What it can do

Repair Windows. It runs DISM RestoreHealth and SFC scannow, in that order, because SFC relies on the files DISM repairs. It can also scan the disk for errors and clean out old Windows update files.

Clean up files. It empties the Windows Temp folder, your own temp folder, Prefetch, the Windows Update download cache, browser caches and crash dumps. It also runs the built-in Windows Disk Cleanup with every category ticked, except your Downloads folder, the Recycle Bin, language packs and the previous Windows installation.

Extras. Flush the DNS cache, reset network settings, optimize the system drive, empty the Recycle Bin, or remove the previous Windows installation. The last four are off by default.

You decide what runs

Every task has a checkbox, and clicking a task explains what it does. The Recommended button brings back the default choices. Before you start, WinTidy shows how much space each cleaning task can free, and it warns you about anything that cannot be undone.

Live progress

You see an overall progress bar, a bar for the task that is running, and a live log of what Windows is saying. You can stop at any time. When it finishes, WinTidy shows how many tasks succeeded and how much free space you gained. Every run is saved as a text log that you can open from the program.

Looks like Windows

The window follows your Windows light or dark setting.

Built to be careful

WinTidy creates a restore point first when System Protection is on. It only empties the contents of the folders it names, never follows shortcuts or links out of them, refuses to touch top-level folders, and skips files that are in use instead of forcing them. An option lets you keep files changed in the last 24 hours. There is no registry cleaner.

How to install

Download and run WinTidy-Setup.exe and allow the administrator permission it asks for. Then open WinTidy from the Start menu. Windows asks for administrator permission each time you open it, because repairing Windows needs it. To remove it, open Windows Settings, then Apps, then WinTidy, and choose Uninstall.

Good to know

DISM needs an internet connection. SFC and DISM can each take 10 to 30 minutes.

Deleting Prefetch is harmless, but the first launch of each program afterwards may be a little slower.

Browser cleaning removes cached pages and images only. Passwords, history and logins are not touched.

Some repairs and the network reset finish after a restart. WinTidy offers to restart for you, or you can tick the option to restart when it finishes.

The installer is not code-signed, so Windows may show a "protected your PC" notice. Click More info, then Run anyway.

WinTidy works on Windows 10 and 11.

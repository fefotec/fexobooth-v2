# Controlling a Canon SELPHY CP1000 from Python on Windows

The Canon SELPHY CP1000 can be reset programmatically through escalating Windows APIs—from spooler purge to full USB device restart—but **detecting consumable errors reliably requires workarounds** because Windows only updates printer status during active print jobs. No Python library exists for direct SELPHY USB communication; the only complete protocol implementation is Solomon Peachy's C-based `selphy_print` backend in Gutenprint, which reveals a **12-byte readback structure** with dedicated error codes for paper empty, ink depleted, and paper jam. On Windows, the most practical architecture combines win32print job monitoring, EnumWindows-based dialog suppression, and a custom always-on-top overlay.

## Resetting the printer: five methods from soft to hard

The SELPHY CP1000 connects via USB, and reset approaches range from clearing the Windows print queue to forcing a full USB device re-enumeration. Here they are in order of escalation.

**Method 1 — Purge jobs via win32print** (no admin required). This is the fastest soft reset. `SetPrinter` with command `3` (PRINTER_CONTROL_PURGE) clears all queued jobs instantly:

```python
import win32print, time

PRINTER_NAME = "Canon SELPHY CP1000"

def purge_and_restart_queue(printer_name):
    h = win32print.OpenPrinter(printer_name)
    try:
        win32print.SetPrinter(h, 0, None, 3)  # PRINTER_CONTROL_PURGE
        win32print.SetPrinter(h, 0, None, 1)  # PRINTER_CONTROL_PAUSE
        time.sleep(1)
        win32print.SetPrinter(h, 0, None, 2)  # PRINTER_CONTROL_RESUME
    finally:
        win32print.ClosePrinter(h)
```

This clears stuck jobs but does not reset the USB hardware. If the SELPHY's LCD shows an error, the spooler side is cleaned but the physical device remains in its error state.

**Method 2 — Restart the Print Spooler service** (requires admin). This nuclear option stops and restarts `spoolsv.exe`, clearing all queues for all printers and forcing Windows to re-enumerate printer connections:

```python
import subprocess, os, glob, time

def restart_spooler(clear_spool_files=True):
    subprocess.run(["net", "stop", "spooler"], capture_output=True)
    if clear_spool_files:
        spool_dir = os.path.join(os.environ['SystemRoot'],
                                 'System32', 'spool', 'PRINTERS')
        for f in glob.glob(os.path.join(spool_dir, '*')):
            try: os.remove(f)
            except OSError: pass
    time.sleep(2)
    subprocess.run(["net", "start", "spooler"], capture_output=True)
```

This resolves most "printer offline" states. The downside is it **affects every printer** on the system and temporarily kills all printing for a few seconds.

**Method 3 — USB device disable/enable via pnputil or PowerShell** (requires admin, Windows 10+). This is the gold standard for a true USB-level reset—equivalent to right-clicking the device in Device Manager and selecting Disable then Enable. It forces the Canon driver to fully unload and reinitialize:

```python
import subprocess, time

def find_selphy_instance_id():
    result = subprocess.run(
        ["powershell", "-Command",
         "Get-PnpDevice | Where-Object {"
         "$_.FriendlyName -like '*SELPHY*' -or "
         "$_.FriendlyName -like '*CP1000*'} | "
         "Select-Object InstanceId, FriendlyName, Status"],
        capture_output=True, text=True)
    return result.stdout.strip()

def reset_usb_device(instance_id):
    """Disable and re-enable USB device. Requires admin."""
    subprocess.run(["powershell", "-Command",
        f"Disable-PnpDevice -InstanceId '{instance_id}' -Confirm:$false"])
    time.sleep(3)
    subprocess.run(["powershell", "-Command",
        f"Enable-PnpDevice -InstanceId '{instance_id}' -Confirm:$false"])
```

Alternatively, `pnputil /restart-device <InstanceId>` accomplishes the same thing in a single command. Both are built into Windows 10+ with no additional downloads.

**Method 4 — CfgMgr32 via ctypes** (pure Python, requires admin). For applications that cannot shell out to PowerShell, the `CM_Disable_DevNode`/`CM_Enable_DevNode` API provides the same device restart through ctypes:

```python
import ctypes
from ctypes import wintypes

cfgmgr32 = ctypes.windll.cfgmgr32

def reset_device_cfgmgr32(device_instance_id):
    devInst = wintypes.DWORD()
    cfgmgr32.CM_Locate_DevNodeW(
        ctypes.byref(devInst), device_instance_id, 0)
    cfgmgr32.CM_Disable_DevNode(devInst, 0)
    import time; time.sleep(3)
    cfgmgr32.CM_Locate_DevNodeW(
        ctypes.byref(devInst), device_instance_id, 0)
    cfgmgr32.CM_Enable_DevNode(devInst, 0)
```

**Method 5 — pyusb device reset** is theoretically the cleanest USB-level approach, but **impractical on Windows** because pyusb requires the WinUSB or libusb driver (installed via Zadig), which replaces the Canon printer driver and breaks normal Windows printing. You'd need to swap drivers back and forth, making this unsuitable for production use. Canon also explicitly warns that "the printer may not work correctly if connected via a USB hub," ruling out the uhubctl power-cycling approach.

**The recommended escalation strategy**: try purge first (instant, no admin), then spooler restart, then pnputil device restart. A combined function handles all three:

```python
def full_reset_selphy(printer_name="Canon SELPHY CP1000"):
    # Step 1: Purge jobs
    try:
        h = win32print.OpenPrinter(printer_name)
        win32print.SetPrinter(h, 0, None, 3)
        win32print.ClosePrinter(h)
    except Exception: pass
    # Step 2: Restart spooler
    subprocess.run(["net", "stop", "spooler"], capture_output=True)
    time.sleep(2)
    subprocess.run(["net", "start", "spooler"], capture_output=True)
    time.sleep(2)
    # Step 3: USB device restart
    subprocess.run(["powershell", "-Command",
        "Get-PnpDevice -FriendlyName '*SELPHY*','*CP1000*' | "
        "ForEach-Object { pnputil /restart-device $_.InstanceId }"],
        capture_output=True)
```

## Detecting printer errors: the fundamental limitation and workarounds

The single most important fact about printer status on Windows is this: **`GetPrinter()` and WMI almost always return status 0 (ready) for USB printers when no job is actively printing.** Microsoft's own KB 160129 documents this behavior—the spooler only updates status during active despooling. For the Canon SELPHY, this means you must check status *while a job is in the queue*.

### Polling printer and job status with win32print

The most reliable approach checks **both** the printer-level and job-level status flags, since job status often contains error information that the printer-level status omits:

```python
import win32print

PRINTER_STATUS_FLAGS = {
    0x00000002: "ERROR",         0x00000008: "PAPER_JAM",
    0x00000010: "PAPER_OUT",     0x00000040: "PAPER_PROBLEM",
    0x00000080: "OFFLINE",       0x00020000: "TONER_LOW",
    0x00040000: "NO_TONER",      0x00100000: "USER_INTERVENTION",
    0x00400000: "DOOR_OPEN",
}

def check_selphy_status(printer_name):
    h = win32print.OpenPrinter(printer_name)
    try:
        info = win32print.GetPrinter(h, 2)
        printer_status = info['Status']
        errors = []
        for flag, name in PRINTER_STATUS_FLAGS.items():
            if printer_status & flag:
                errors.append(name)

        # Job-level status is often MORE informative
        jobs = win32print.EnumJobs(h, 0, 999, 1)
        for job in jobs:
            js = job['Status']
            if js & 0x02: errors.append(f"Job {job['JobId']}: ERROR")
            if js & 0x40: errors.append(f"Job {job['JobId']}: PAPEROUT")
            if job.get('pStatus'):
                errors.append(f"Driver: {job['pStatus']}")
        return errors
    finally:
        win32print.ClosePrinter(h)
```

The `pStatus` field on individual jobs is particularly valuable—it contains the **driver-supplied error string** that often says things like "Paper tray empty" or "Ink cassette depleted" when the Canon driver reports an error.

### WMI provides similar data with friendlier field names

```python
import wmi

def check_selphy_wmi(printer_name):
    c = wmi.WMI()
    for p in c.Win32_Printer(Name=printer_name):
        error_states = {4: "No Paper", 5: "Low Toner",
                        6: "No Toner", 8: "Jammed", 9: "Offline"}
        state = error_states.get(p.DetectedErrorState, "OK")
        return {"PrinterStatus": p.PrinterStatus,
                "DetectedErrorState": state,
                "WorkOffline": p.WorkOffline}
```

The same caveat applies: **WMI reads from the spooler**, and consumer USB printers frequently report "Idle" regardless of actual state. Microsoft explicitly documents that "the printer driver may not report its status to the spooler."

### Event-driven monitoring with FindFirstPrinterChangeNotification

Rather than polling, you can register for spooler change events. This is more efficient and catches status changes immediately:

```python
import win32print, win32event, win32con, ctypes
from ctypes import wintypes

def monitor_printer_events(printer_name):
    winspool = ctypes.WinDLL('winspool.drv')
    h = win32print.OpenPrinter(printer_name)
    hNotify = winspool.FindFirstPrinterChangeNotification(
        int(h), 0x7777FFFF, 0, None)  # PRINTER_CHANGE_ALL
    try:
        while True:
            result = win32event.WaitForSingleObject(hNotify, 5000)
            if result == win32con.WAIT_OBJECT_0:
                dwChange = wintypes.DWORD()
                winspool.FindNextPrinterChangeNotification(
                    hNotify, ctypes.byref(dwChange), None, None)
                errors = check_selphy_status(printer_name)
                if errors:
                    print(f"ERRORS DETECTED: {errors}")
    finally:
        winspool.FindClosePrinterChangeNotification(hNotify)
        win32print.ClosePrinter(h)
```

## Intercepting and replacing Windows printer dialogs

When the SELPHY runs out of paper or ink, the Canon driver typically pops up a Windows dialog. The strategy is three-pronged: suppress the system notification via registry, detect and close Canon dialogs via EnumWindows, and show a custom overlay.

### Suppress balloon notifications via registry

```python
import winreg

def disable_printer_notifications():
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
        r"Printers\Settings", 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, "EnableBalloonNotificationsLocal",
                      0, winreg.REG_DWORD, 0)
    winreg.SetValueEx(key, "EnableBalloonNotificationsRemote",
                      0, winreg.REG_DWORD, 0)
    winreg.CloseKey(key)
```

This disables the Windows toast/balloon notifications for printers. It does not suppress driver-specific popup windows from Canon's own software.

### Detect and close Canon dialogs with EnumWindows

A background thread continuously scans for windows matching Canon/SELPHY patterns and closes them. The Windows dialog class `#32770` identifies standard system dialogs:

```python
import win32gui, win32con, threading, time

class DialogSuppressor(threading.Thread):
    def __init__(self, patterns=None, callback=None):
        super().__init__(daemon=True)
        self.patterns = patterns or [
            "Canon", "SELPHY", "Printer Error",
            "Paper", "Ink", "CP1000"]
        self.callback = callback  # called when dialog is found
        self.running = True

    def run(self):
        while self.running:
            def enum_callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if any(p.lower() in title.lower()
                           for p in self.patterns):
                        win32gui.PostMessage(
                            hwnd, win32con.WM_CLOSE, 0, 0)
                        if self.callback:
                            self.callback(title)
                return True
            try:
                win32gui.EnumWindows(enum_callback, None)
            except Exception:
                pass
            time.sleep(0.5)
```

For more sophisticated dialog handling, **pywinauto** can click specific buttons within dialogs (like "OK" or "Cancel") rather than just sending WM_CLOSE:

```python
from pywinauto import Desktop

def find_and_dismiss_canon_dialogs():
    desktop = Desktop(backend="win32")
    for win in desktop.windows():
        title = win.window_text()
        if any(kw in title.lower() for kw in ["canon", "selphy"]):
            try:
                win.child_window(title_re="OK|Close|Cancel",
                                 class_name="Button").click()
            except:
                win.close()
```

### Custom always-on-top status overlay

This tkinter overlay appears when an error is detected and stays visible until consumables are replaced. It polls the printer status every 2 seconds and automatically hides when the error clears:

```python
import tkinter as tk
import win32print, threading

class PrinterStatusOverlay:
    def __init__(self, printer_name):
        self.printer_name = printer_name
        self.root = tk.Tk()
        self.root.title("Printer Status")
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)  # borderless

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"360x100+{sw-380}+{sh-160}")
        self.root.attributes('-alpha', 0.92)

        frame = tk.Frame(self.root, bg='#CC0000', padx=12, pady=8)
        frame.pack(fill='both', expand=True)
        self.title_lbl = tk.Label(frame, text="⚠ PRINTER ERROR",
            font=('Segoe UI', 14, 'bold'), fg='white', bg='#CC0000')
        self.title_lbl.pack(anchor='w')
        self.detail_lbl = tk.Label(frame, text="Checking...",
            font=('Segoe UI', 10), fg='white', bg='#CC0000',
            wraplength=330, justify='left')
        self.detail_lbl.pack(anchor='w')

        self.root.withdraw()
        self._poll()
        self.root.mainloop()

    def _poll(self):
        errors = check_selphy_status(self.printer_name)
        if errors:
            self.detail_lbl.config(text=", ".join(errors))
            self.root.deiconify()
        else:
            self.root.withdraw()
        self.root.after(2000, self._poll)
```

## What the SELPHY protocol actually looks like under the hood

The most revealing source for SELPHY internals is Solomon Peachy's `backend_canonselphyneo.c` in the Gutenprint project—the only open-source implementation that communicates directly with newer SELPHY models (CP820 through CP1500) over USB. The CP1000 uses this "neo" protocol.

**SELPHY printers claim to be standard USB Printer Class devices but violate the specification.** They require bidirectional handshaking that standard USB printer backends cannot provide. The protocol uses a **12-byte readback structure** exchanged over USB bulk endpoints:

```
Readback byte[0] — Printer state:
  0x01 = Idle, 0x02 = Feeding paper, 0x04 = Printing Yellow
  0x08 = Printing Magenta, 0x10 = Printing Cyan, 0x20 = Laminating

Readback byte[2] — Error code:
  0x00 = None,  0x02 = Paper Feed/No Paper,  0x03 = No Paper Tray
  0x05 = Wrong Paper,  0x06 = Ink Cassette Empty,  0x07 = No Ink
  0x09 = No Paper AND No Ink,  0x0B = Paper Jam,  0x0C = Ink Jam

Readback byte[6] — Media type:  0x01=Postcard, 0x02=L, 0x03=Card
Readback byte[7] — Power:  0x00=AC, 0x01=Battery OK, 0x03=Battery Low
```

The reset command is a 12-byte packet: `{ 0x40, 0x10, 0x00, ... }` (remaining bytes zero). This is sent over the bulk OUT endpoint and triggers a full printer reset.

However, **accessing this protocol from Python on Windows requires replacing the Canon driver with WinUSB via Zadig**, which breaks normal Windows printing. This trade-off makes the direct USB approach impractical for a photobooth setup that also needs to send print jobs through the Windows spooler. The DeviceIoControl approach (`IOCTL_USBPRINT_VENDOR_GET_COMMAND`) offers a middle ground—vendor-specific USB commands through the existing printer driver—but Canon's proprietary command codes for querying status this way are undocumented.

The Canon SELPHY USB Vendor ID is **0x04A9**. The CP1000's exact Product ID is not documented in public sources and must be discovered by scanning:

```python
# Run with Zadig/WinUSB, or use PowerShell:
# Get-PnpDevice -FriendlyName '*SELPHY*' | Format-List *
```

Known PIDs from the selphy_print source include CP800 (0x3214), CP900 (~0x3255), and CP1500 (0x3302). The CP1000 is likely in the **0x325x–0x32Ax** range.

## Lessons from open-source photobooth projects

Every Python photobooth project examined—**photobooth-app**, **pibooth**, **reuterbal/photobooth**, and others—delegates printing to CUPS via `pycups` or shell commands (`lp`/`lpr`). None implement direct SELPHY USB communication in Python. The photobooth-app documentation explicitly states: *"There is no feedback to the photobooth app about the status of the print job or the printer itself."*

Pibooth comes closest to status awareness by subscribing to CUPS events (`CUPS_EVT_JOB_COMPLETED`, `CUPS_EVT_PRINTER_STOPPED`), but its own GitHub issues confirm that **Canon SELPHY printers do not reliably report paper status** through CUPS. The workaround used universally across photobooth projects is a **manual print counter**—the SELPHY CP1000 gets **18 prints per paper cassette** and **18 prints per ink cartridge** (postcard size), so the software counts prints and warns the operator. Issue #476 on pibooth's tracker documents a recurring problem where the CP1500 hangs after the first print, requiring a physical restart.

## Conclusion: a practical architecture for SELPHY control on Windows

The most robust Python architecture for controlling a SELPHY CP1000 on Windows combines four layers. First, a **print counter** that tracks consumable usage (18 prints per paper/ink set for postcard size) and warns proactively before the printer errors out. Second, **win32print status polling** during active print jobs, checking both `GetPrinter` status and per-job `pStatus` strings for driver-reported errors. Third, a **DialogSuppressor thread** running EnumWindows to catch and dismiss Canon popup dialogs, feeding detected errors to your application logic. Fourth, a **custom tkinter overlay** that displays errors prominently and persists until the condition is resolved.

For printer reset, the escalation from spooler purge → spooler restart → `pnputil /restart-device` covers every failure mode from stuck jobs to a hung USB device. The one gap that remains is real-time consumable detection without an active print job—this would require either porting the selphy_print C protocol to Python (replacing the Windows driver with WinUSB) or discovering Canon's undocumented IOCTL vendor commands for status queries through the existing printer driver. For most photobooth applications, the print counter approach used by every existing project is the pragmatic solution to this gap.
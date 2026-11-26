"""Optional Pro HWND backend using public Windows control messages only.

This backend is independent of native object layouts. It never attaches a
native bridge, sends physical input, changes system foreground/maximization,
or reads/writes vendor object memory. Cross-process memory is used solely for
documented Scintilla and common-toolbar message buffers. Message acceptance is not a project
compile/check result. Unknown outcomes stop the current plan without replay.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
import ntpath
import struct
import subprocess
from pathlib import Path
import time
import uuid

WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH = 12, 13, 14
WM_COMMAND, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x111, 0x200, 0x201, 0x202
WM_MDIACTIVATE, WM_MDIGETACTIVE, BM_CLICK = 0x222, 0x229, 0xF5
SCI_GETTEXT, SCI_GETTEXTLENGTH, SCI_GETCODEPAGE = 2182, 2183, 2137
SCI_SETSEL, SCI_REPLACESEL, SCI_BEGINUNDOACTION, SCI_ENDUNDOACTION = 2160, 2170, 2078, 2079
TB_GETBUTTON, TB_BUTTONCOUNT, TB_GETITEMRECT = 0x417, 0x418, 0x41D
READ_ONLY = frozenset(('read_text', 'scintilla_get', 'toolbar_inventory'))
UI_ONLY = frozenset(('activate_page', 'respond_dialog'))
SCHEMA = 'mcgs-hwnd-plan/v1'


class BackendError(RuntimeError):
    def __init__(self, description, status='unsupported_operation', **details):
        super().__init__(description)
        self.status, self.details = status, details


class UnknownOutcome(BackendError):
    def __init__(self, description, **details):
        super().__init__(description, status='unknown_outcome', automatic_retry=False, **details)


def normalized(text):
    return ' '.join(str(text).split())


def menu_text(text):
    # Ampersands denote Windows access keys; a doubled ampersand is literal.
    return str(text).split('\t', 1)[0].replace('&&', '\0').replace('&', '').replace('\0', '&').strip()


def full_project(path):
    if not isinstance(path, str):
        return False
    drive, tail = ntpath.splitdrive(path)
    return bool(drive and tail.startswith(('\\', '/')) and ntpath.splitext(tail)[1].casefold() == '.mcp')


def canonical_project(path):
    if os.name == 'nt':
        path = str(Path(path).resolve())
    return ntpath.normcase(ntpath.normpath(path))


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def toolbar_button_size(machine):
    if machine in (0x14c, 0x1c4):
        return 20
    if machine in (0x8664, 0xaa64) and ctypes.sizeof(ctypes.c_void_p) == 8:
        return 32
    raise BackendError('Unsupported toolbar machine or cross-bitness', status='toolbar_abi_unavailable', machine=machine)


def matching_button_area(native, accessible):
    if len(native) != 4 or len(accessible) != 4 or not all(map(math.isfinite, accessible)):
        return False
    x0, y0, x1, y1 = native
    a0, b0, a1, b1 = accessible
    if not (x0 <= (a0 + a1) / 2 <= x1 and y0 <= (b0 + b1) / 2 <= y1
            and a0 <= (x0 + x1) / 2 <= a1 and b0 <= (y0 + y1) / 2 <= b1):
        return False
    overlap = max(0, min(x1, a1) - max(x0, a0)) * max(0, min(y1, b1) - max(y0, b0))
    return overlap > 0 and 2 * overlap >= max((x1 - x0) * (y1 - y0), (a1 - a0) * (b1 - b0))


class Win32:
    """Small lazily initialized ctypes boundary, replaceable by fixture tests."""
    def __init__(self, pid, timeout_ms=3000):
        if os.name != 'nt':
            raise BackendError('The HWND backend requires Windows', status='platform_unavailable')
        self.pid, self.timeout_ms = int(pid), int(timeout_ms)
        if self.pid <= 0 or self.timeout_ms <= 0:
            raise ValueError('PID and message timeout must be positive')
        self.u = ctypes.WinDLL('user32', use_last_error=True)
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        pointer, size, signed = ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ssize_t
        self.u.SendMessageTimeoutW.argtypes = [pointer, wintypes.UINT, size, signed, wintypes.UINT, wintypes.UINT, ctypes.POINTER(size)]
        self.u.SendMessageTimeoutW.restype = signed
        self.u.PostMessageW.argtypes = [pointer, wintypes.UINT, size, signed]
        self.u.PostMessageW.restype = wintypes.BOOL
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, pointer, signed)
        self.u.EnumWindows.argtypes = [self.callback_type, signed]
        self.u.EnumChildWindows.argtypes = [pointer, self.callback_type, signed]
        self.u.GetWindowThreadProcessId.argtypes = [pointer, ctypes.POINTER(wintypes.DWORD)]
        self.u.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.u.GetParent.argtypes = self.u.GetMenu.argtypes = [pointer]
        self.u.GetParent.restype = self.u.GetMenu.restype = pointer
        self.u.GetWindow.argtypes = [pointer, wintypes.UINT]
        self.u.GetWindow.restype = pointer
        for name in ('IsWindow', 'IsWindowVisible', 'IsWindowEnabled'):
            getattr(self.u, name).argtypes = [pointer]
            getattr(self.u, name).restype = wintypes.BOOL
        self.u.GetClassNameW.argtypes = self.u.GetWindowTextW.argtypes = [pointer, wintypes.LPWSTR, ctypes.c_int]
        self.u.GetDlgCtrlID.argtypes = [pointer]
        self.u.GetDlgCtrlID.restype = ctypes.c_int
        self.u.GetWindowLongW.argtypes = [pointer, ctypes.c_int]
        self.u.GetWindowLongW.restype = ctypes.c_long
        self.u.GetMenuItemCount.argtypes = [pointer]
        self.u.GetMenuItemCount.restype = ctypes.c_int
        self.k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.k.OpenProcess.restype = pointer
        self.k.CloseHandle.argtypes = [pointer]
        self.k.GetExitCodeProcess.argtypes = [pointer, ctypes.POINTER(wintypes.DWORD)]
        self.u.ClientToScreen.argtypes = [pointer, ctypes.POINTER(wintypes.POINT)]
        self.k.GetProcessTimes.argtypes = [pointer] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.k.QueryFullProcessImageNameW.argtypes = [pointer, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.k.VirtualAllocEx.argtypes = [pointer, pointer, size, wintypes.DWORD, wintypes.DWORD]
        self.k.VirtualAllocEx.restype = pointer
        self.k.VirtualFreeEx.argtypes = [pointer, pointer, size, wintypes.DWORD]
        self.k.ReadProcessMemory.argtypes = self.k.WriteProcessMemory.argtypes = [pointer, pointer, pointer, size, ctypes.POINTER(size)]
        self.process = self.k.OpenProcess(0x1000, False, self.pid)
        if not self.process:
            raise ctypes.WinError(ctypes.get_last_error())
        self.memory_process = None
        self.retained_buffers = []
        timestamps = [wintypes.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(self.process, *[ctypes.byref(value) for value in timestamps]):
            raise ctypes.WinError(ctypes.get_last_error())
        exe, count = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        self.k.QueryFullProcessImageNameW(self.process, 0, exe, ctypes.byref(count))
        self.identity = {'pid': self.pid, 'creation_filetime': (timestamps[0].dwHighDateTime << 32) | timestamps[0].dwLowDateTime,
                         'executable': exe.value}

    def close(self):
        for name in ('memory_process', 'process'):
            handle = getattr(self, name, None)
            if handle:
                self.k.CloseHandle(handle)
                setattr(self, name, None)

    def live(self):
        code = wintypes.DWORD()
        if not self.process or not self.k.GetExitCodeProcess(self.process, ctypes.byref(code)) or code.value != 259:
            raise BackendError('The selected process has exited; no new process was started', status='process_exited')

    def check(self, hwnd):
        self.live()
        pid = wintypes.DWORD()
        thread = self.u.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
        if not self.u.IsWindow(int(hwnd)) or not thread or pid.value != self.pid:
            raise BackendError('Window no longer belongs to the selected process', status='stale_window', hwnd=int(hwnd))
        return int(hwnd)

    def send(self, hwnd, message, wparam=0, lparam=0, timeout_ms=None, mutating=False):
        hwnd = self.check(hwnd)
        result = ctypes.c_size_t()
        ctypes.set_last_error(0)
        ok = self.u.SendMessageTimeoutW(hwnd, message, wparam, lparam, 0x22,
                                       timeout_ms or self.timeout_ms, ctypes.byref(result))
        if not ok:
            error = ctypes.get_last_error()
            if mutating:
                raise UnknownOutcome('Windows did not confirm completion of the message', hwnd=hwnd, message=message, winerror=error)
            raise BackendError('Read-only Windows message did not complete', status='read_timeout', hwnd=hwnd, message=message, winerror=error)
        return result.value

    def post(self, hwnd, message, wparam=0, lparam=0):
        hwnd = self.check(hwnd)
        if not self.u.PostMessageW(hwnd, message, wparam, lparam):
            raise BackendError('Windows rejected the posted message', status='message_rejected',
                               hwnd=hwnd, message=message, winerror=ctypes.get_last_error())

    def snapshot(self, hwnd):
        hwnd = self.check(hwnd)
        cls, title = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(4096)
        self.u.GetClassNameW(hwnd, cls, len(cls))
        self.u.GetWindowTextW(hwnd, title, len(title))
        style = self.u.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
        password = cls.value.casefold() == 'edit' and bool(style & 0x20)
        if cls.value.casefold() in ('static', 'button'):
            count = self.send(hwnd, WM_GETTEXTLENGTH)
            control_text = ctypes.create_unicode_buffer(count + 1)
            self.send(hwnd, WM_GETTEXT, len(control_text), ctypes.cast(control_text, ctypes.c_void_p).value)
            caption = control_text.value
        else:
            caption = title.value
        # GetParent returns the owner for top-level WS_POPUP windows. Keep
        # actual parentage and ownership separate so dialogs are not MDI pages.
        return {'hwnd': hwnd, 'parent': int(self.u.GetParent(hwnd) or 0) if style & 0x40000000 else 0,
                'owner': int(self.u.GetWindow(hwnd, 4) or 0), 'class_name': cls.value,
                'text': '<password>' if password else caption,
                'visible': bool(self.u.IsWindowVisible(hwnd)), 'enabled': bool(self.u.IsWindowEnabled(hwnd)),
                'control_id': self.u.GetDlgCtrlID(hwnd), 'password': password}

    def top_windows(self):
        tops = []
        def top(hwnd, unused):
            pid = wintypes.DWORD()
            self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.pid:
                tops.append(int(hwnd))
            return True
        callback = self.callback_type(top)
        self.u.EnumWindows(callback, 0)
        return self._observed_windows(tops)

    def children(self, hwnd):
        handles = []
        def child(hwnd, unused):
            pid = wintypes.DWORD()
            self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.pid:
                handles.append(int(hwnd))
            return True
        callback = self.callback_type(child)
        self.u.EnumChildWindows(self.check(hwnd), callback, 0)
        return self._observed_windows(handles)

    def _observed_windows(self, handles):
        rows = []
        for hwnd in dict.fromkeys(handles):
            try:
                rows.append(self.snapshot(hwnd))
            except BackendError as error:
                if error.status != 'stale_window':
                    raise
        return rows

    def windows(self):
        rows = {}
        for top in self.top_windows():
            hwnd = top['hwnd']
            try:
                children = self.children(hwnd)
                self.check(hwnd)
            except BackendError as error:
                # Dialogs can close between the two enumeration calls. Other
                # errors, including editor exit, must still reach the caller.
                if error.status != 'stale_window':
                    raise
                continue
            rows[hwnd] = top
            rows.update({row['hwnd']: row for row in children})
        return list(rows.values())

    def menu(self, hwnd):
        hwnd = self.check(hwnd)
        root = self.u.GetMenu(hwnd)
        if not root:
            return []
        class MENUITEMINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('fMask', wintypes.UINT), ('fType', wintypes.UINT),
                        ('fState', wintypes.UINT), ('wID', wintypes.UINT), ('hSubMenu', ctypes.c_void_p),
                        ('hbmpChecked', ctypes.c_void_p), ('hbmpUnchecked', ctypes.c_void_p),
                        ('dwItemData', ctypes.c_size_t), ('dwTypeData', wintypes.LPWSTR),
                        ('cch', wintypes.UINT), ('hbmpItem', ctypes.c_void_p)]
        self.u.GetMenuItemInfoW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.BOOL, ctypes.POINTER(MENUITEMINFO)]
        def visit(menu, path, seen):
            if int(menu) in seen:
                raise BackendError('Native menu contains a recursive submenu', status='menu_unavailable')
            rows = []
            for index in range(self.u.GetMenuItemCount(menu)):
                item = MENUITEMINFO()
                item.cbSize, item.fMask = ctypes.sizeof(item), 0x147
                if not self.u.GetMenuItemInfoW(menu, index, True, ctypes.byref(item)):
                    raise ctypes.WinError(ctypes.get_last_error())
                label = ctypes.create_unicode_buffer(item.cch + 1)
                item.dwTypeData, item.cch = ctypes.cast(label, wintypes.LPWSTR), len(label)
                if not self.u.GetMenuItemInfoW(menu, index, True, ctypes.byref(item)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if item.fType & 0x800:
                    continue
                caption = menu_text(label.value)
                current = path + [caption]
                row = {'path': current, 'text': label.value, 'id': item.wID,
                       'enabled': not bool(item.fState & 3), 'checked': bool(item.fState & 8),
                       'submenu': bool(item.hSubMenu)}
                rows.append(row)
                if item.hSubMenu:
                    rows.extend(visit(item.hSubMenu, current, seen | {int(menu)}))
            return rows
        return visit(root, [], set())

    def text(self, hwnd):
        row = self.snapshot(hwnd)
        if row['password']:
            raise BackendError('Password controls are excluded from text capture', status='password_control')
        count = self.send(hwnd, WM_GETTEXTLENGTH)
        buf = ctypes.create_unicode_buffer(count + 1)
        self.send(hwnd, WM_GETTEXT, len(buf), ctypes.cast(buf, ctypes.c_void_p).value)
        return buf.value

    def set_text(self, hwnd, text):
        if '\0' in text:
            raise ValueError('Windows text controls do not accept embedded NUL characters')
        if self.snapshot(hwnd)['password']:
            raise BackendError('This property editor operation does not target password controls', status='password_control')
        buf = ctypes.create_unicode_buffer(text)
        return self.send(hwnd, WM_SETTEXT, 0, ctypes.cast(buf, ctypes.c_void_p).value, mutating=True)

    def _remote(self, size, initial=None):
        if not self.memory_process:
            self.memory_process = self.k.OpenProcess(0x1038, False, self.pid)
        if not self.memory_process:
            raise BackendError('Cannot allocate a documented Windows control message buffer', status='message_buffer_unavailable',
                               winerror=ctypes.get_last_error())
        address = self.k.VirtualAllocEx(self.memory_process, None, size, 0x3000, 4)
        if not address:
            raise ctypes.WinError(ctypes.get_last_error())
        if initial is not None:
            local, copied = ctypes.create_string_buffer(initial, size), ctypes.c_size_t()
            if not self.k.WriteProcessMemory(self.memory_process, address, local, size, ctypes.byref(copied)) or copied.value != size:
                self.k.VirtualFreeEx(self.memory_process, address, 0, 0x8000)
                raise ctypes.WinError(ctypes.get_last_error())
        return address

    def _retain(self, address, size):
        # A timed-out message can still consume its buffer later. Freeing it
        # here would invalidate an in-flight pointer. Process exit reclaims it.
        self.retained_buffers.append({'address': address, 'bytes': size, 'reason': 'message_outcome_unknown'})

    def _message_buffer(self, hwnd, message, index, size):
        address = self._remote(size)
        release = True
        try:
            try:
                result = self.send(hwnd, message, index, address)
            except BackendError as error:
                if error.status == 'read_timeout':
                    self._retain(address, size)
                    release = False
                raise
            if not result:
                raise BackendError('Toolbar entry no longer exists', status='toolbar_changed')
            data, copied = ctypes.create_string_buffer(size), ctypes.c_size_t()
            if not self.k.ReadProcessMemory(self.memory_process, address, data, size, ctypes.byref(copied)) or copied.value != size:
                raise ctypes.WinError(ctypes.get_last_error())
            return data.raw
        finally:
            if release:
                self.k.VirtualFreeEx(self.memory_process, address, 0, 0x8000)

    def _toolbar_button_size(self):
        probe = getattr(self.k, 'IsWow64Process2', None)
        if probe is None:
            try:
                # QueryFullProcessImageNameW from the already verified live PID
                # identifies its PE header. The caller still verifies HWND ownership.
                with Path(self.identity['executable']).open('rb') as image:
                    dos = image.read(64)
                    if not dos.startswith(b'MZ') or len(dos) != 64:
                        raise ValueError('Invalid DOS header')
                    image.seek(struct.unpack_from('<I', dos, 60)[0])
                    pe = image.read(6)
                    if not pe.startswith(b'PE\0\0') or len(pe) != 6:
                        raise ValueError('Invalid PE header')
                    return toolbar_button_size(struct.unpack_from('<H', pe, 4)[0])
            except (OSError, ValueError) as error:
                raise BackendError('Cannot determine the target toolbar ABI', status='toolbar_abi_unavailable') from error
        probe.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.USHORT), ctypes.POINTER(wintypes.USHORT)]
        process, native = wintypes.USHORT(), wintypes.USHORT()
        if not probe(self.process, ctypes.byref(process), ctypes.byref(native)):
            raise ctypes.WinError(ctypes.get_last_error())
        machine = process.value or native.value
        return toolbar_button_size(machine)

    def toolbar_buttons(self, hwnd):
        toolbar = self.snapshot(hwnd)
        if toolbar['class_name'].casefold() != 'toolbarwindow32' or not toolbar['visible'] or not toolbar['parent']:
            raise BackendError('Expected a visible common-controls toolbar', status='toolbar_unavailable')
        parent = self.snapshot(toolbar['parent'])
        size = self._toolbar_button_size()
        count = self.send(hwnd, TB_BUTTONCOUNT)
        if count > 4096:
            raise BackendError('Invalid toolbar button count', status='toolbar_changed', count=count)
        dpi = getattr(self.u, 'SetThreadDpiAwarenessContext', None)
        if dpi is None:
            raise BackendError('Cannot match toolbar and UIA screen coordinates', status='toolbar_dpi_unavailable')
        dpi.argtypes = [ctypes.c_void_p]
        dpi.restype = ctypes.c_void_p
        previous = dpi(ctypes.c_void_p(-4))
        if not previous:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            rows = []
            for index in range(count):
                raw = self._message_buffer(hwnd, TB_GETBUTTON, index, size)
                _, command, state, style = struct.unpack_from('<iiBB', raw)
                if state & 8 or style & 1:  # TBSTATE_HIDDEN, BTNS_SEP
                    continue
                coords = struct.unpack('<iiii', self._message_buffer(hwnd, TB_GETITEMRECT, index, 16))
                first, last = wintypes.POINT(*coords[:2]), wintypes.POINT(*coords[2:])
                if not self.u.ClientToScreen(hwnd, ctypes.byref(first)) or not self.u.ClientToScreen(hwnd, ctypes.byref(last)):
                    raise ctypes.WinError(ctypes.get_last_error())
                rows.append({'toolbar': hwnd, 'parent': parent['hwnd'], 'id': command,
                             'screen_rect': [first.x, first.y, last.x, last.y], 'style': style,
                             'enabled': toolbar['enabled'] and parent['enabled'] and bool(state & 4)})
            if self.send(hwnd, TB_BUTTONCOUNT) != count:
                raise BackendError('Toolbar changed during inventory', status='toolbar_changed')
        finally:
            dpi(previous)
        return rows

    def toolbar_labels(self, hwnd):
        self.check(hwnd)
        # Read-only UIA is isolated in a short-lived helper because a provider
        # can block on the editor thread. HWND and PID are integer arguments.
        script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]HANDLE_VALUE)
if ($null -eq $root -or $root.Current.ProcessId -ne PID_VALUE) { throw 'Wrong UIA toolbar owner' }
$condition = [Windows.Automation.PropertyCondition]::new(
    [Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Button)
$rows = @(
    foreach ($button in $root.FindAll([Windows.Automation.TreeScope]::Descendants, $condition)) {
        $b = $button.Current
        $r = $b.BoundingRectangle
        if ($b.ProcessId -eq PID_VALUE -and !$b.IsOffscreen -and !$r.IsEmpty -and $b.Name) {
            @{label=$b.Name; screen_rect=@($r.Left,$r.Top,$r.Right,$r.Bottom); enabled=$b.IsEnabled}
        }
    }
)
ConvertTo-Json -InputObject $rows -Compress -Depth 4
'''
        script = script.replace('HANDLE_VALUE', str(int(hwnd))).replace('PID_VALUE', str(self.pid))
        try:
            powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                                    capture_output=True, check=True, timeout=self.timeout_ms / 1000,
                                    encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
            return json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise BackendError('Could not read the toolbar UIA button labels', status='toolbar_uia_unavailable',
                               error_type=type(error).__name__) from error

    def toolbar_resource_labels(self, command_ids):
        if not command_ids or not self.identity['executable']:
            return {}
        self.live()
        self.k.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
        self.k.LoadLibraryExW.restype = wintypes.HMODULE
        self.k.FreeLibrary.argtypes = [wintypes.HMODULE]
        self.u.LoadStringW.argtypes = [wintypes.HINSTANCE, wintypes.UINT, wintypes.LPWSTR, ctypes.c_int]
        # Load the selected executable only as a data/image resource. Command
        # IDs are sampled from TB_GETBUTTON, never from a vendor ID table.
        module = self.k.LoadLibraryExW(self.identity['executable'], None, 0x22)
        if not module:
            return {}
        try:
            labels = {}
            buffer = ctypes.create_unicode_buffer(4096)
            for command_id in command_ids:
                if not 0 < command_id <= 0xffff:
                    continue
                size = self.u.LoadStringW(module, command_id, buffer, len(buffer))
                if not 0 < size < len(buffer) - 1:
                    continue
                lines = buffer.value.splitlines()
                # MFC command strings have the status prompt, then tooltip.
                # Require both parts so arbitrary matching resources are ignored.
                if len(lines) == 2 and lines[0].strip() and lines[1].strip():
                    labels[command_id] = lines[1].strip()
            return labels
        finally:
            self.k.FreeLibrary(module)

    def scintilla_text(self, hwnd):
        length = self.send(hwnd, SCI_GETTEXTLENGTH)
        codepage = self.send(hwnd, SCI_GETCODEPAGE) or self.k.GetACP()
        address, size = self._remote(length + 1), length + 1
        retain = False
        try:
            try:
                self.send(hwnd, SCI_GETTEXT, size, address)
            except BackendError:
                self._retain(address, size)
                retain = True
                raise
            result, copied = ctypes.create_string_buffer(size), ctypes.c_size_t()
            if not self.k.ReadProcessMemory(self.memory_process, address, result, size, ctypes.byref(copied)) or copied.value != size:
                raise ctypes.WinError(ctypes.get_last_error())
            if self.send(hwnd, SCI_GETTEXTLENGTH) != length:
                raise BackendError('Scintilla text changed during capture; no write was attempted', status='text_changed_during_read')
            return result.raw.split(b'\0', 1)[0].decode('utf-8' if codepage == 65001 else 'cp' + str(codepage))
        finally:
            if not retain:
                self.k.VirtualFreeEx(self.memory_process, address, 0, 0x8000)

    def replace_scintilla(self, hwnd, text):
        if '\0' in text:
            raise ValueError('Scintilla replacement text must not contain NUL characters')
        codepage = self.send(hwnd, SCI_GETCODEPAGE) or self.k.GetACP()
        raw = text.encode('utf-8' if codepage == 65001 else 'cp' + str(codepage)) + b'\0'
        address, retain = self._remote(len(raw), raw), False
        began = False
        try:
            self.send(hwnd, SCI_BEGINUNDOACTION, mutating=True)
            began = True
            self.send(hwnd, SCI_SETSEL, 0, -1, mutating=True)
            try:
                self.send(hwnd, SCI_REPLACESEL, 0, address, mutating=True)
            except UnknownOutcome:
                retain = True
                self._retain(address, len(raw))
                raise
            self.send(hwnd, SCI_ENDUNDOACTION, mutating=True)
            began = False
        finally:
            # Do not send a cleanup command after an unknown result. The
            # receipt records an open undo group for inspection in that case.
            if not retain:
                self.k.VirtualFreeEx(self.memory_process, address, 0, 0x8000)
            if began:
                self.last_open_undo_group = hwnd


class Backend:
    def __init__(self, pid, timeout_ms=3000, api=None, project_probe=None):
        self.api = api or Win32(pid, timeout_ms)
        self.pid, self.cache, self.trace = int(pid), None, []
        self.dialog_responses = []
        self.frame_handle = None
        self.project_probe = project_probe
        self.expected_project = None
        self.verified_project = None

    def verify_project(self):
        if self.expected_project is None:
            return
        if self.project_probe is None:
            raise BackendError('An active bridge read is required to verify the current full project path',
                               status='project_identity_unavailable')
        try:
            actual = self.project_probe(self.expected_project)
        except (OSError, RuntimeError, ValueError, ImportError) as error:
            raise BackendError(str(error), status='project_identity_unavailable') from error
        path = actual.get('actual_project')
        if (actual.get('ok') is not True or actual.get('op') != 'engineering-edit-inspect'
                or actual.get('process_id') != self.pid
                or actual.get('creation_filetime') != self.api.identity['creation_filetime']
                or not full_project(path) or canonical_project(path) != canonical_project(self.expected_project)):
            raise BackendError('Current Pro project or process generation differs from the plan',
                               status='project_identity_mismatch', expected_project=self.expected_project,
                               actual_project=path)
        self.verified_project = path

    def close(self):
        self.api.close()

    def refresh(self):
        self.cache = self.api.windows()
        return self.cache

    def matches(self, row, selector):
        if not isinstance(selector, dict) or not selector:
            raise ValueError('Use a nonempty window selector from inventory')
        fields = ('hwnd', 'parent', 'owner', 'class_name', 'control_id', 'visible', 'enabled')
        if any(key in selector and row[key] != selector[key] for key in fields):
            return False
        if 'text' in selector and row['text'] != selector['text']:
            return False
        if 'class_prefix' in selector and not row['class_name'].startswith(selector['class_prefix']):
            return False
        return True

    def find(self, selector):
        if 'hwnd' in selector:
            row = self.api.snapshot(selector['hwnd'])
            if self.matches(row, selector):
                return row
            raise BackendError('Window handle no longer matches its selector', status='target_changed', selector=selector, actual=row)
        if self.cache is None:
            self.refresh()
        for attempt in range(2):
            rows = [row for row in self.cache if self.matches(row, selector)]
            current = []
            for row in rows:
                try:
                    actual = self.api.snapshot(row['hwnd'])
                    if self.matches(actual, selector):
                        current.append(actual)
                except BackendError:
                    pass
            if len(current) == 1:
                return current[0]
            if attempt == 0:
                self.refresh()
        raise BackendError('Window selector must match exactly one current window', status='target_not_unique',
                           selector=selector, matches=current)

    def _send(self, hwnd, message, wparam=0, lparam=0, **kwargs):
        entry = {'hwnd': int(hwnd), 'message': message, 'status': 'dispatching'}
        self.trace.append(entry)
        try:
            result = self.api.send(hwnd, message, wparam, lparam, mutating=True, **kwargs)
            entry.update(status='returned', native_return=result)
            return result
        except BackendError as error:
            entry.update(status=error.status)
            raise

    def _post(self, hwnd, message, wparam=0, lparam=0):
        self.api.post(hwnd, message, wparam, lparam)
        self.trace.append({'hwnd': int(hwnd), 'message': message, 'status': 'posted', 'completion_verified': False})

    def _native_call(self, hwnd, label, callback):
        entry = {'hwnd': int(hwnd), 'operation': label, 'status': 'dispatching'}
        self.trace.append(entry)
        try:
            value = callback()
            entry['status'] = 'returned'
            return value
        except BackendError as error:
            entry['status'] = error.status
            raise

    def activate(self, selector):
        row = self.find(selector)
        parent = self.api.snapshot(row['parent']) if row['parent'] else None
        while parent and parent['class_name'] != 'MDIClient':
            row, parent = parent, self.api.snapshot(parent['parent']) if parent['parent'] else None
        if not parent:
            raise BackendError('Target is not inside an MDI document page', status='mdi_activation_unavailable', target=row)
        active = self.api.send(parent['hwnd'], WM_MDIGETACTIVE)
        sent = active != row['hwnd']
        if sent:
            self._send(parent['hwnd'], WM_MDIACTIVATE, row['hwnd'])
            active = self.api.send(parent['hwnd'], WM_MDIGETACTIVE)
        if active != row['hwnd']:
            raise BackendError('MDI activation was not confirmed', status='activation_not_verified', expected=row['hwnd'], actual=active)
        return {'sent': sent, 'verified': True, 'verification': 'WM_MDIGETACTIVE', 'page': row, 'mdi_client': parent['hwnd'],
                'system_foreground_changed': False, 'maximized': False}

    def activate_for(self, row):
        current = row
        while True:
            if current['class_name'] == '#32770':
                return {'sent': False, 'verified': True, 'verification': 'target_inside_current_dialog', 'dialog': current['hwnd']}
            if not current['parent']:
                break
            parent = self.api.snapshot(current['parent'])
            if parent['class_name'] == 'MDIClient':
                active = self.api.send(parent['hwnd'], WM_MDIGETACTIVE)
                return self.activate({'hwnd': current['hwnd']}) if active != current['hwnd'] else {
                    'sent': False, 'verified': True, 'verification': 'WM_MDIGETACTIVE', 'page': current}
            current = parent
        raise BackendError('Cannot identify an internal document page for this target', status='target_page_unavailable', target=row)

    def frame(self, selector=None):
        if selector:
            return self.find(selector)
        if self.frame_handle:
            try:
                return self.api.snapshot(self.frame_handle)
            except BackendError:
                self.frame_handle = None
        if self.cache is None:
            self.refresh()
        rows = [row for row in self.cache if row['visible'] and not row['parent']
                and row['class_name'] != '#32770' and self.api.menu(row['hwnd'])]
        if len(rows) != 1:
            raise BackendError('Select the native frame explicitly from inventory', status='frame_not_unique', matches=rows)
        self.frame_handle = rows[0]['hwnd']
        return rows[0]

    def dialogs(self):
        result = []
        # Poll only top-level windows. Repeated canvas/property steps do not
        # rebuild the complete native control tree just to detect a modal.
        for row in self.api.top_windows():
            if row['class_name'] != '#32770' or not row['visible']:
                continue
            children = self.api.children(row['hwnd'])
            body = [item['text'] for item in children if item['visible'] and item['text']
                    and item['class_name'].casefold() == 'static']
            buttons = [item for item in children if item['class_name'].casefold() == 'button' and item['visible']]
            owner_disabled = not self.api.snapshot(row['owner'])['enabled'] if row['owner'] else True
            result.append({**row, 'body_texts': body, 'buttons': buttons, 'modal': owner_disabled})
            if self.cache is not None:
                known = {item['hwnd']: item for item in self.cache}
                known.update({item['hwnd']: item for item in [row, *children]})
                self.cache = list(known.values())
        return result

    @staticmethod
    def dialog_matches(actual, expected):
        if not isinstance(expected, dict) or not any(key in expected for key in ('body_texts', 'text')):
            raise ValueError('Dialog matching requires exact body_texts or exact combined text; a title alone is insufficient')
        if not expected.get('body_texts') and not expected.get('text') and not expected.get('title'):
            raise ValueError('An empty dialog body requires its exact title')
        if 'title' in expected and actual['text'] != expected['title']:
            return False
        if 'hwnd' in expected and actual['hwnd'] != expected['hwnd']:
            return False
        if 'body_texts' in expected and sorted(map(normalized, actual['body_texts'])) != sorted(map(normalized, expected['body_texts'])):
            return False
        if 'text' in expected and normalized('\n'.join(actual['body_texts'])) != normalized(expected['text']):
            return False
        return True

    def wait_dialog(self, expected, timeout_ms=10000):
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            dialogs = self.dialogs()
            matches = [row for row in dialogs if self.dialog_matches(row, expected)]
            if len(matches) == 1:
                return matches[0]
            if dialogs:
                raise BackendError('A native dialog does not match the expected content', status='blocked_unknown_dialog', dialogs=dialogs)
            if time.monotonic() >= deadline:
                raise UnknownOutcome('The posted native command did not expose the expected dialog before timeout')
            time.sleep(0.05)

    def respond_dialog(self, step):
        actual = self.wait_dialog(step['match'], step.get('timeout_ms', 10000))
        buttons = [row for row in actual['buttons'] if menu_text(row['text']) == menu_text(step['button']) and row['enabled']]
        if len(buttons) != 1:
            raise BackendError('The matched dialog has no unique enabled caption for the requested response',
                               status='dialog_button_not_unique', dialog=actual, caption=step['button'])
        button = buttons[0]
        # Standard dialogs receive the same BN_CLICKED notification a button
        # generates. BM_CLICK alone can be ignored by an inactive dialog.
        if button['parent'] == actual['hwnd'] and 0 < button['control_id'] <= 0xffff:
            self._post(actual['hwnd'], WM_COMMAND, button['control_id'], button['hwnd'])
        else:
            self._post(button['hwnd'], BM_CLICK)
        deadline = time.monotonic() + step.get('timeout_ms', 10000) / 1000
        while time.monotonic() < deadline:
            try:
                if not self.api.snapshot(actual['hwnd'])['visible']:
                    break
            except BackendError:
                break
            time.sleep(0.05)
        else:
            raise UnknownOutcome('The response was posted but the native dialog remains visible', dialog=actual['hwnd'])
        return {'sent': True, 'verified': True, 'verification': 'exact_dialog_matched_and_closed',
                'dialog': actual, 'button': buttons[0]['text'], 'project_check_passed': None}

    def guard_dialogs(self, context=None):
        answered = set()
        while True:
            dialogs = [dialog for dialog in self.dialogs() if dialog['modal']
                       and not (context is not None and self.dialog_matches(dialog, context))]
            if not dialogs:
                return
            for dialog in dialogs:
                signature = (dialog['hwnd'], dialog['text'], tuple(dialog['body_texts']))
                matched = [rule for rule in self.dialog_responses if self.dialog_matches(dialog, rule['match'])]
                if len(matched) != 1 or signature in answered:
                    raise BackendError('An unrecognized or repeated native dialog blocks this operation',
                                       status='blocked_unknown_dialog', dialogs=[dialog])
                answered.add(signature)
                self.respond_dialog(matched[0])

    def command(self, step):
        if step.get('page'):
            self.activate(step['page'])
        frame = self.frame(step.get('frame'))
        path = step['path']
        if not isinstance(path, list) or not path or not all(isinstance(part, str) and part for part in path):
            raise ValueError('Native menu commands use a complete text path array')
        path = list(map(menu_text, path))
        rows = [row for row in self.api.menu(frame['hwnd']) if row['path'] == path and not row['submenu']]
        if len(rows) != 1 or not rows[0]['enabled']:
            raise BackendError('Native menu path is unavailable, ambiguous or disabled', status='command_unavailable', path=path, matches=rows)
        command = rows[0]
        if not 0 <= command['id'] <= 0xFFFF:
            raise BackendError('Menu item cannot be represented by WM_COMMAND', status='command_unavailable', menu=command)
        if step.get('expect_dialog') is not None:
            self._post(frame['hwnd'], WM_COMMAND, command['id'])
            dialog = self.wait_dialog(step['expect_dialog'], step.get('timeout_ms', 10000))
            return {'sent': True, 'verified': True, 'verification': 'expected_dialog_observed', 'menu': command, 'dialog': dialog,
                    'project_check_passed': None}
        value = self._send(frame['hwnd'], WM_COMMAND, command['id'], timeout_ms=step.get('timeout_ms'))
        return {'sent': True, 'verified': False, 'verification': 'native_handler_returned_only',
                'menu': command, 'native_return': value, 'project_check_passed': None}

    def discover_toolbar(self, selector):
        toolbar = self.find(selector)
        hwnd = toolbar['hwnd']
        buttons = self.api.toolbar_buttons(hwnd)
        try:
            labels = self.api.toolbar_labels(hwnd)
        except BackendError as error:
            if error.status != 'toolbar_uia_unavailable':
                raise
            labels = []
        matched = []
        for button in buttons:
            matches = [label for label in labels if matching_button_area(button['screen_rect'], label['screen_rect'])]
            accessible = None
            if len(matches) == 1 and sum(matching_button_area(other['screen_rect'], matches[0]['screen_rect'])
                                         for other in buttons) == 1:
                accessible = matches[0]
            matched.append((button, accessible))
        resources = self.api.toolbar_resource_labels({row['id'] for row, label in matched if label is None})
        if self.api.toolbar_buttons(hwnd) != buttons:
            raise BackendError('Toolbar changed during semantic discovery', status='toolbar_changed')
        rows = []
        for button, accessible in matched:
            if accessible is not None:
                rows.append({**button, 'label': accessible['label'], 'label_source': 'uia_button_rect',
                             'enabled': button['enabled'] and accessible['enabled']})
            elif button['id'] in resources:
                rows.append({**button, 'label': resources[button['id']],
                             'label_source': 'executable_command_resource'})
        return rows

    def toolbar_command(self, step):
        if step.get('page'):
            self.activate(step['page'])
        requested = step['label']
        if not isinstance(requested, str) or not requested.strip():
            raise ValueError('Toolbar commands need a nonempty UIA label')
        rows = [row for row in self.discover_toolbar(step['toolbar']) if row['label'] == requested]
        if len(rows) != 1 or not rows[0]['enabled']:
            raise BackendError('Toolbar label is unavailable, ambiguous or disabled',
                               status='toolbar_command_unavailable', label=requested, matches=rows)
        button = rows[0]
        if not 0 < button['id'] <= 0xffff or button['style'] & (0x08 | 0x80):
            raise BackendError('Toolbar entry is a dropdown or cannot be dispatched as WM_COMMAND',
                               status='toolbar_command_unavailable', button=button)
        current = self.api.snapshot(button['toolbar'])
        if current['parent'] != button['parent'] or not current['enabled'] or not self.api.snapshot(button['parent'])['enabled']:
            raise BackendError('Toolbar routing parent or enabled state changed', status='toolbar_changed')
        if step.get('expect_dialog') is not None:
            self._post(button['parent'], WM_COMMAND, button['id'])
            dialog = self.wait_dialog(step['expect_dialog'], step.get('timeout_ms', 10000))
            return {'sent': True, 'verified': True, 'verification': 'expected_dialog_observed',
                    'toolbar_button': button, 'dialog': dialog, 'project_check_passed': None}
        value = self._send(button['parent'], WM_COMMAND, button['id'], timeout_ms=step.get('timeout_ms'))
        return {'sent': True, 'verified': False, 'verification': 'native_handler_returned_only',
                'toolbar_button': button, 'native_return': value, 'project_check_passed': None}

    @staticmethod
    def coordinates(point):
        if not isinstance(point, (list, tuple)) or len(point) != 2 or any(type(value) is not int or not -32768 <= value <= 32767 for value in point):
            raise ValueError('Canvas coordinates must be two signed 16-bit client coordinates')
        return (point[0] & 0xFFFF) | ((point[1] & 0xFFFF) << 16)

    def canvas(self, step):
        if step.get('page'):
            self.activate(step['page'])
        row = self.find(step['canvas'])
        self.activate_for(row)
        return row

    def canvas_owner(self, row):
        """Read the current ownership chain without activating any window."""
        current = self.api.snapshot(row['hwnd'])
        while current['parent']:
            parent = self.api.snapshot(current['parent'])
            if parent['class_name'] == 'MDIClient':
                return current['hwnd'], parent['hwnd']
            current = parent
        raise BackendError('Canvas no longer belongs to an MDI page', status='target_page_unavailable')

    def verify_canvas(self, row, owner):
        dialogs = [dialog for dialog in self.dialogs() if dialog['modal']]
        if dialogs:
            raise BackendError('A native dialog interrupted the drawing tool; canvas input was not sent',
                               status='blocked_unknown_dialog', dialogs=dialogs)
        current = self.api.snapshot(row['hwnd'])
        if (not current['enabled'] or not current['visible']
                or any(current[key] != row[key] for key in ('parent', 'class_name'))
                or self.canvas_owner(current) != owner
                or self.api.send(owner[1], WM_MDIGETACTIVE) != owner[0]):
            raise BackendError('Drawing tool changed the active page or canvas ownership',
                               status='canvas_page_changed', canvas=row['hwnd'], expected_page=owner[0])

    def draw(self, step):
        row = self.canvas(step)
        owner = self.canvas_owner(row)
        if step.get('page') and self.canvas_owner(self.find(step['page'])) != owner:
            raise BackendError('Outer page conflicts with the selected canvas', status='canvas_page_conflict')
        points = step['points']
        if len(points) < 2:
            raise ValueError('Native drawing/moving requires at least two client points')
        packed = [self.coordinates(point) for point in points]
        if step.get('tool_menu') and step.get('tool_toolbar'):
            raise ValueError('Choose one drawing-tool selector')
        if step.get('tool_toolbar'):
            tool = step['tool_toolbar']
            if tool.get('page') and self.canvas_owner(self.find(tool['page'])) != owner:
                raise BackendError('Drawing toolbar page conflicts with the canvas', status='canvas_page_conflict')
            if tool.get('expect_dialog') is not None:
                raise BackendError('A drawing tool cannot wait for a modal before canvas input', status='canvas_modal_tool')
            self.toolbar_command(tool)
        if step.get('tool_menu'):
            self.command({'path': step['tool_menu'], 'frame': step.get('frame')})
        self.verify_canvas(row, owner)
        keys = (8 if step.get('control') else 0) | (4 if step.get('shift') else 0)
        self._send(row['hwnd'], WM_MOUSEMOVE, keys, packed[0])
        self._send(row['hwnd'], WM_LBUTTONDOWN, keys | 1, packed[0])
        for point in packed[1:]:
            self._send(row['hwnd'], WM_MOUSEMOVE, keys | 1, point)
        self._send(row['hwnd'], WM_LBUTTONUP, keys, packed[-1])
        return {'sent': True, 'verified': False, 'verification': 'canvas_message_handlers_returned_only',
                'canvas': row['hwnd'], 'client_points': points, 'native_object_readback': 'not_performed'}

    def select_points(self, step):
        row = self.canvas(step)
        if not step['points']:
            raise ValueError('Native point selection requires at least one point')
        for index, point in enumerate(step['points']):
            packed, keys = self.coordinates(point), (8 if index or step.get('additive') else 0)
            self._send(row['hwnd'], WM_MOUSEMOVE, keys, packed)
            self._send(row['hwnd'], WM_LBUTTONDOWN, keys | 1, packed)
            self._send(row['hwnd'], WM_LBUTTONUP, keys, packed)
        return {'sent': True, 'verified': False, 'canvas': row['hwnd'], 'points': step['points'],
                'verification': 'point_selection_messages_returned_only', 'selection_count_verified': False}

    def property_set(self, step):
        row = self.find(step['target'])
        if row['class_name'].casefold() != 'edit':
            raise BackendError('property_set supports standard Edit controls; inspect custom controls separately', status='control_type_unsupported', target=row)
        self.activate_for(row)
        text = self.input_text(step)
        before = self.api.text(row['hwnd'])
        if 'before_text' in step and before != step['before_text']:
            raise BackendError('Edit text differs from the requested before-value', status='before_text_differs', before_sha256=text_sha(before))
        self._native_call(row['hwnd'], 'WM_SETTEXT', lambda: self.api.set_text(row['hwnd'], text))
        after = self.api.text(row['hwnd'])
        if after != text:
            raise BackendError('Native Edit readback differs from the requested text', status='text_readback_differs',
                               sent=True, expected_sha256=text_sha(text), actual_sha256=text_sha(after))
        return {'sent': True, 'verified': True, 'verification': 'WM_GETTEXT_exact_match',
                'target': row['hwnd'], 'before_sha256': text_sha(before), 'after_sha256': text_sha(after),
                'dialog_committed': False}

    @staticmethod
    def input_text(step):
        if ('text' in step) == ('text_file' in step):
            raise ValueError('Specify exactly one of text or text_file')
        return Path(step['text_file']).read_text(encoding=step.get('encoding', 'utf-8-sig')) if 'text_file' in step else step['text']

    def scintilla(self, step, replace=False):
        row = self.find(step['target'])
        if not row['class_name'].casefold().startswith('scintilla'):
            raise BackendError('This operation requires a native Scintilla window', status='control_type_unsupported', target=row)
        if replace:
            self.activate_for(row)
        before = self.api.scintilla_text(row['hwnd'])
        if replace:
            text = self.input_text(step)
            if 'before_sha256' in step and text_sha(before) != step['before_sha256']:
                raise BackendError('Scintilla source differs from the requested before-image', status='before_text_differs')
            self._native_call(row['hwnd'], 'SCI_REPLACESEL_full_document', lambda: self.api.replace_scintilla(row['hwnd'], text))
            after = self.api.scintilla_text(row['hwnd'])
            if after != text:
                raise BackendError('Scintilla full-text readback differs', status='text_readback_differs', sent=True,
                                   expected_sha256=text_sha(text), actual_sha256=text_sha(after))
            return {'sent': True, 'verified': True, 'verification': 'SCI_GETTEXT_exact_match',
                    'before_sha256': text_sha(before), 'after_sha256': text_sha(after),
                    'characters': len(after), 'compiled': False}
        result = {'sent': False, 'verified': True, 'verification': 'SCI_GETTEXT', 'sha256': text_sha(before), 'characters': len(before)}
        if step.get('output_file'):
            path = Path(step['output_file']).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8', newline='') as output:
                output.write(before)
            result['output_file'] = str(path)
        else:
            result['text'] = before
        return result

    def execute(self, step):
        operation = step['op']
        if operation == 'toolbar_inventory':
            return {'sent': False, 'verified': True, 'items': self.discover_toolbar(step['toolbar'])}
        if operation == 'activate_page':
            return self.activate(step['target'])
        if operation == 'toolbar_command':
            return self.toolbar_command(step)
        if operation == 'menu_command':
            return self.command(step)
        if operation == 'respond_dialog':
            return self.respond_dialog(step)
        if operation in ('draw', 'move'):
            return self.draw(step)
        if operation == 'select':
            return self.select_points(step)
        if operation == 'selection_command':
            selection = self.select_points(step)
            return {'selection': selection, 'command': self.command(step['command']), 'sent': True, 'verified': False}
        if operation == 'copy_paste_move':
            self.canvas(step)
            if step.get('points'):
                self.select_points(step)
            copy = self.command({'path': step['copy_menu'], 'frame': step.get('frame')})
            paste = self.command({'path': step['paste_menu'], 'frame': step.get('frame')})
            move = self.draw({**step, 'points': [step['drag_from'], step['drag_to']]})
            return {'sent': True, 'verified': False, 'copy': copy, 'paste': paste, 'move': move,
                    'native_object_readback': 'not_performed'}
        if operation == 'property_set':
            return self.property_set(step)
        if operation in ('scintilla_get', 'scintilla_replace'):
            return self.scintilla(step, replace=operation == 'scintilla_replace')
        if operation == 'read_text':
            row = self.find(step['target'])
            return {'sent': False, 'verified': True, 'text': self.api.text(row['hwnd']), 'target': row['hwnd']}
        raise BackendError('Unsupported HWND operation: ' + str(operation), status='operation_unavailable')

    def inventory(self):
        windows = self.refresh()
        menus = [{'frame': row['hwnd'], 'items': self.api.menu(row['hwnd'])}
                 for row in windows if row['visible'] and not row['parent'] and row['class_name'] != '#32770']
        active = [{'mdi_client': row['hwnd'], 'active_child': self.api.send(row['hwnd'], WM_MDIGETACTIVE)}
                  for row in windows if row['class_name'] == 'MDIClient']
        return {'schema': 'mcgs-hwnd-inventory/v1', 'status': 'inventory_read', 'process': self.api.identity,
                'windows': windows, 'menus': menus, 'mdi': active, 'dialogs': self.dialogs(),
                'capabilities': {'dynamic_native_menu_paths': True, 'semantic_toolbar_inventory': True, 'mdi_activation_readback': True,
                    'canvas_mouse_messages': True, 'point_selection_command': True, 'native_copy_paste_move': True,
                    'standard_edit_text_readback': True, 'scintilla_full_text_readback': True,
                    'exact_dialog_responses': True, 'arbitrary_native_control_properties': False,
                    'native_object_tree_readback': False, 'native_compile_diagnostics': False},
                'project_written': False, 'project_check_passed': None, 'system_foreground_changed': False}

    def run(self, plan, checkpoint=None):
        if not isinstance(plan, dict) or plan.get('schema') != SCHEMA or not isinstance(plan.get('steps'), list):
            raise ValueError('Use an mcgs-hwnd-plan/v1 object with a steps array')
        if plan.get('pid', self.pid) != self.pid:
            raise ValueError('Plan PID differs from the explicitly selected process')
        allowed = {'activate_page', 'menu_command', 'respond_dialog', 'draw', 'move', 'select', 'selection_command',
                   'copy_paste_move', 'property_set', 'scintilla_get', 'scintilla_replace', 'read_text', 'toolbar_command', 'toolbar_inventory'}
        for step in plan['steps']:
            if not isinstance(step, dict) or step.get('op') not in allowed:
                raise BackendError('Plan contains an unsupported operation', operation=step.get('op') if isinstance(step, dict) else None)
        mutates = bool(plan.get('save_command')) or any(step['op'] not in READ_ONLY | UI_ONLY for step in plan['steps'])
        self.expected_project = plan.get('expected_project') if mutates else None
        self.verified_project = None
        if mutates and not full_project(self.expected_project):
            raise ValueError('A mutating HWND plan needs expected_project as a full absolute .mcp path')
        self.dialog_responses = plan.get('dialog_responses', [])
        self.trace = []
        started = time.perf_counter()
        result = {'schema': 'mcgs-hwnd-receipt/v1', 'id': plan.get('id', uuid.uuid4().hex),
                  'status': 'running', 'process': self.api.identity, 'steps': [], 'trace': self.trace,
                  'automatic_retry': False, 'native_project_check': 'not_performed',
                  'project_check_passed': None, 'save': 'not_requested', 'system_foreground_changed': False,
                  'maximized': False, 'physical_input_sent': False}
        def save():
            result['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 3)
            if checkpoint:
                checkpoint(result)
        save()
        steps = list(plan['steps'])
        if plan.get('save_command'):
            steps.append({**plan['save_command'], 'op': 'menu_command', '_final_save': True})
        for index, step in enumerate(steps):
            phase = time.perf_counter()
            trace_start = len(self.trace)
            entry = {'index': index, 'op': step['op'], 'status': 'dispatching', 'sent': False, 'verified': False}
            result['steps'].append(entry)
            save()
            try:
                if step['op'] not in READ_ONLY | {'respond_dialog', 'property_set'}:
                    self.guard_dialogs(step.get('dialog_context'))
                if step['op'] not in READ_ONLY | UI_ONLY:
                    self.verify_project()
                    result['verified_project'] = self.verified_project
                value = self.execute(step)
                entry.update(value, status='completed')
                if step.get('_final_save'):
                    result['save'] = ('save_dialog_observed_not_confirmed_saved' if step.get('expect_dialog') else
                                      'native_menu_handler_returned_file_readback_not_performed')
            except (BackendError, OSError, ValueError, KeyError, TypeError) as error:
                entry.update(status=getattr(error, 'status', 'failed'), error=str(error),
                             details=getattr(error, 'details', {}),
                             sent=any(item['status'] in ('returned', 'posted') for item in self.trace[trace_start:]))
                if isinstance(error, UnknownOutcome):
                    entry['dispatch_outcome'] = 'unknown'
                result.update(status='stopped', stopped_at=index,
                              unknown_outcome=isinstance(error, UnknownOutcome), remaining_steps=len(steps) - index - 1)
                entry['elapsed_ms'] = round((time.perf_counter() - phase) * 1000, 3)
                if getattr(self.api, 'retained_buffers', None):
                    result['retained_message_buffers'] = self.api.retained_buffers
                if getattr(self.api, 'last_open_undo_group', None):
                    result['scintilla_undo_group_not_confirmed_closed'] = self.api.last_open_undo_group
                save()
                return result
            entry['elapsed_ms'] = round((time.perf_counter() - phase) * 1000, 3)
            save()
        result['status'] = 'completed'
        result['all_requested_readbacks_verified'] = all(row.get('verified') for row in result['steps'])
        save()
        return result

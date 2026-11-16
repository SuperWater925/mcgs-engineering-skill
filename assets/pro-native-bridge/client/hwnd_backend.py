"""Optional Pro HWND backend using public Windows control messages only.

This backend is independent of native object layouts. It never attaches a
native bridge, sends physical input, changes system foreground/maximization,
or reads/writes vendor object memory. Cross-process memory is used solely for
Scintilla's documented message buffers. Message acceptance is not a project
compile/check result. Unknown outcomes stop the current plan without replay.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH = 12, 13, 14
WM_COMMAND, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x111, 0x200, 0x201, 0x202
WM_MDIACTIVATE, WM_MDIGETACTIVE, BM_CLICK = 0x222, 0x229, 0xF5
SCI_GETTEXT, SCI_GETTEXTLENGTH, SCI_GETCODEPAGE = 2182, 2183, 2137
SCI_SETSEL, SCI_REPLACESEL, SCI_BEGINUNDOACTION, SCI_ENDUNDOACTION = 2160, 2170, 2078, 2079
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


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


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
        return [self.snapshot(hwnd) for hwnd in tops]

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
        return [self.snapshot(item) for item in dict.fromkeys(handles)]

    def windows(self):
        tops = self.top_windows()
        rows = {row['hwnd']: row for row in tops}
        for top in tops:
            rows.update({row['hwnd']: row for row in self.children(top['hwnd'])})
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
            raise BackendError('Cannot allocate a documented Scintilla message buffer', status='message_buffer_unavailable',
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
    def __init__(self, pid, timeout_ms=3000, api=None):
        self.api = api or Win32(pid, timeout_ms)
        self.pid, self.cache, self.trace = int(pid), None, []
        self.dialog_responses = []
        self.frame_handle = None

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
        self._send(parent['hwnd'], WM_MDIACTIVATE, row['hwnd'])
        active = self.api.send(parent['hwnd'], WM_MDIGETACTIVE)
        if active != row['hwnd']:
            raise BackendError('MDI activation was not confirmed', status='activation_not_verified', expected=row['hwnd'], actual=active)
        return {'sent': True, 'verified': True, 'verification': 'WM_MDIGETACTIVE', 'page': row, 'mdi_client': parent['hwnd'],
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

    def draw(self, step):
        row = self.canvas(step)
        points = step['points']
        if len(points) < 2:
            raise ValueError('Native drawing/moving requires at least two client points')
        packed = [self.coordinates(point) for point in points]
        if step.get('tool_menu'):
            self.command({'path': step['tool_menu'], 'frame': step.get('frame')})
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
        if operation == 'activate_page':
            return self.activate(step['target'])
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
                'capabilities': {'dynamic_native_menu_paths': True, 'mdi_activation_readback': True,
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
                   'copy_paste_move', 'property_set', 'scintilla_get', 'scintilla_replace', 'read_text'}
        for step in plan['steps']:
            if not isinstance(step, dict) or step.get('op') not in allowed:
                raise BackendError('Plan contains an unsupported operation', operation=step.get('op') if isinstance(step, dict) else None)
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
                if step['op'] not in ('respond_dialog', 'read_text', 'scintilla_get', 'property_set'):
                    self.guard_dialogs(step.get('dialog_context'))
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

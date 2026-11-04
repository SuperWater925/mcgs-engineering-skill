"""Task-only visible-page gate around the unchanged at-most-once session runner.

It never activates/retries a window or submits a request in --check-only mode.
The exact page must first be activated and proved by Confirm-McgsPageForeground.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


class VisibilityGate:
    def __init__(self, proof_file):
        self.file = Path(proof_file).resolve()
        self.proof = read(self.file)
        p = self.proof
        if not (p.get('ok') is True and p.get('exact_page_is_active') is True
                ):
            raise ValueError('A successful exact-page visibility proof is required.')
        if digest(p['native_receipt']) != p['native_receipt_sha256']:
            raise ValueError('The native receipt bound to the visibility proof changed.')
        native = read(p['native_receipt'])
        if native['process_id'] != p['process_id'] or native['creation_filetime'] != p['creation_filetime']:
            raise ValueError('Visibility and native process generations differ.')
        self.pid = p['process_id']
        self.main = int(p['main_hwnd'], 16)
        self.mdi = int(p['mdi_client_hwnd'], 16)
        self.frame = int(p['frame_hwnd'], 16)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        for name in ['IsWindow', 'IsWindowVisible', 'IsIconic']:
            f = getattr(self.user, name)
            f.argtypes = [wintypes.HWND]
            f.restype = wintypes.BOOL
        self.user.GetParent.argtypes = [wintypes.HWND]
        self.user.GetParent.restype = wintypes.HWND
        self.user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.SendMessageW.restype = ctypes.c_ssize_t
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowTextW.restype = ctypes.c_int
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        handle = self.kernel.OpenProcess(0x1000, False, self.pid)
        if not handle:
            raise RuntimeError('The visibility-bound process is not available.')
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            creation = times[0].dwLowDateTime | (times[0].dwHighDateTime << 32)
            if creation != p['creation_filetime']:
                raise RuntimeError('The visibility-bound process generation changed.')
        finally:
            self.kernel.CloseHandle(handle)

    def check(self):
        valid = True
        for handle in [self.main, self.mdi, self.frame]:
            pid = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            valid &= bool(self.user.IsWindow(handle)) and pid.value == self.pid
        active = int(self.user.SendMessageW(self.mdi, 0x0229, 0, 0))
        same_parent = int(self.user.GetParent(self.frame) or 0) == self.mdi
        title_buffer = ctypes.create_unicode_buffer(2048)
        self.user.GetWindowTextW(self.frame, title_buffer, len(title_buffer))
        base_title = self.proof['frame_title'].removesuffix('*')
        same_title = title_buffer.value in (base_title, base_title + '*')
        ok = bool(valid and same_parent and same_title and active == self.frame)
        evidence = dict(utc=datetime.now(timezone.utc).isoformat(), ok=ok,
            process_id=self.pid, page_id=self.proof['page_id'], page_name=self.proof['page_name'],
            active_mdi_child_hwnd=hex(active),
            exact_main_hwnd=hex(self.main), exact_page_hwnd=hex(self.frame),
            owned=bool(valid),
            actual_page_parent_unchanged=bool(same_parent), automatic_activation=False,
            exact_page_frame_title=title_buffer.value, original_page_title_unchanged=same_title,
            activation_or_input_injected=False, project_content_written=False)
        if not ok:
            raise RuntimeError('The exact page is no longer the active MDI child; '
                               'no next write request will be submitted: ' + json.dumps(evidence))
        return evidence


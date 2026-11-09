"""Best-effort local cache of static PE evidence, independent of any Pro process."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


class ResolutionCache:
    def __init__(self, root, namespace, contract):
        self.directory = Path(root).absolute() / namespace
        self.contract = contract

    def _entry(self, identity):
        return self.directory / (fingerprint(_json([self.contract, identity])) + '.cache')

    def load(self, identity):
        entry = self._entry(identity)
        try:
            checksum, raw = entry.read_bytes().split(b'\n', 1)
            if checksum.decode('ascii') != fingerprint(raw):
                return None
            row = json.loads(raw)
            if isinstance(row, dict) and row.get('key') == entry.stem:
                return row.get('value')
        except (OSError, ValueError):
            pass
        return None

    def store(self, identity, value):
        entry = self._entry(identity)
        temporary = None
        try:
            entry.parent.mkdir(parents=True, exist_ok=True)
            raw = _json({'key': entry.stem, 'value': value})
            with tempfile.NamedTemporaryFile(dir=entry.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(fingerprint(raw).encode('ascii') + b'\n')
                stream.write(raw)
            os.replace(temporary, entry)
            return True
        except OSError:
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

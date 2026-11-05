"""Shared product-family recognition; no software release-number admission."""
import json
from pathlib import Path
import re


_contract = json.loads(Path(__file__).with_name('project_family.json').read_text(encoding='utf-8-sig'))
if _contract.get('schema') != 1:
    raise ValueError('Unsupported shared project-family contract')
BRAND_PATTERN = _contract['brand_pattern']


def identify_family(version):
    """Return Pro, Stu or unrecognized while preserving the caller's raw text."""
    if not isinstance(version, str):
        return 'unrecognized'
    match = re.search(BRAND_PATTERN, version.lstrip('\ufeff'), re.IGNORECASE)
    return ('Pro' if match.group(1).lower() == 'pro' else 'Stu') if match else 'unrecognized'

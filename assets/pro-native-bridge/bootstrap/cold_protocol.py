"""Normalize an explicitly supplied cold-loader protocol; no registry access."""
import copy

LEGACY = {
    'preload_section': '预装载构件', 'ini_encoding': 'auto', 'ini_no_bom_encoding': 'cp936',
    'startup': {'value_name': 'Count', 'accepted_values': [0, 1], 'scan_value': 0},
}


def normalize(protocol):
    runtime = copy.deepcopy(LEGACY)
    for source, target in (('addins_ini_preload_section', 'preload_section'),
                           ('addins_ini_encoding', 'ini_encoding'),
                           ('addins_ini_no_bom_encoding', 'ini_no_bom_encoding')):
        if source in protocol:
            runtime[target] = protocol[source]
    if 'startup' in protocol:
        startup = protocol['startup']
        if not isinstance(startup, dict) or set(startup) - set(runtime['startup']):
            raise ValueError('Cold startup protocol has unknown fields')
        runtime['startup'].update(startup)
    section = runtime['preload_section']
    if not isinstance(section, str) or not section or any(c in section for c in '[]\r\n\0'):
        raise ValueError('Supply the actual INI preload section name without brackets')
    for key in ('ini_encoding', 'ini_no_bom_encoding'):
        if not isinstance(runtime[key], str) or not runtime[key] or '\0' in runtime[key]:
            raise ValueError('Cold INI encoding must be an explicit encoding name or auto')
    startup = runtime['startup']
    if not isinstance(startup['value_name'], str) or not startup['value_name'] or '\0' in startup['value_name']:
        raise ValueError('Cold startup value name is missing')
    values = startup['accepted_values']
    if not isinstance(values, list) or not values:
        raise ValueError('Supply distinct observed cold startup DWORD states')
    if any(type(value) is not int or not -(1 << 31) <= value < (1 << 31)
           for value in [*values, startup['scan_value']]):
        raise ValueError('Cold startup states must use actual Int32 DWORD bits')
    if len(set(values)) != len(values):
        raise ValueError('Supply distinct observed cold startup DWORD states')
    return runtime

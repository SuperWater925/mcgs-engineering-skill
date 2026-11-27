"""CDrawHisPic style spans, proven from native writer 90a3c0.

Four LOGPENs, CMcgsFont/ink pairs and the sixteen trace LOGPENs are
independent visual fields. Sources, ranges, selected-point outputs, IDs,
times, flags and the entire remaining archive are preserved as raw slices.
90a3c0 store order; trace 914fb0 + base915130; 904aee/90589b feed the
two ink members to CDC virtual+38 SetTextColor. No vendor code executes.
"""
from dataclasses import dataclass
from decimal import Decimal
import re
import struct
from 原生界面样式 import CommonEnvelope,Reader,CString,Array,_font,set_font,fonts

HISTORY_CURVE_TYPE = 0x502e
HISTORY_CURVE_EDIT_FIELDS = {'history_curve_colors', 'history_curve_pens', 'history_curve_ranges',
                             'history_curve_visibility', 'history_curve_x_length'}
_RANGE_FIELDS = {'minimum': 'min', 'maximum': 'max'}
_FLOAT32_LIMIT = 3.4028234663852886e38
# Both original coordinate tabs initialize the length spinner to 1..10000.
# Unit list order is seconds, minutes, hours, days, months, years. The original
# help gives smaller coordinate length bounds for the last two units.
_X_LENGTH_LIMITS = (10000, 10000, 10000, 10000, 801, 66)

@dataclass
class Span:
 name:str
 raw:bytes
 kind:str
 offset:int

class HistoryCurveStyle:
 def __init__(self,data):
  self.original=bytes(data);self.spans=[];r=Reader(data)
  def take(name,kind):
   start=r.pos
   if kind=='s':CString.parse(r)
   elif kind=='f':_font(r)
   elif kind=='p':r.take(16)
   elif kind=='a':Array.parse(r,True)
   else:r.take(4)
   self.spans.append(Span(name,data[start:r.pos],kind,start))
  take('bindings','a')
  for key in ('fc','10c','11c','12c'):take(key,'p')
  take('4c','s')
  for key in ('13c','140','144','148','14c','150','154'):take(key,'i')
  take('158','s');take('15c','i')
  for key in ('160','164','168','16c','170','174','178','17c'):take(key,'s')
  take('198','f');take('1b0','i');take('1b4','s')
  for key in ('1b8','1bc','1c0','1c4','1c8','1cc','1d0','1d4','1d8','1dc','1e0','1e4'):take(key,'i')
  take('1e8','f');take('200','i');take('curve_count','i')
  self.curve_count=int.from_bytes(self.spans[-1].raw,'little')
  r.count_extent(self.curve_count,47,'History trace')
  for j in range(self.curve_count):
   for key,kind in [('nativeKey','s'),('name','s'),('type','i'),('id','i'),('visible','i'),('source','s'),('unit','s'),('datatype','i'),('min','s'),('max','s'),('output','s'),('reserved','i'),('reserved2','i'),('pen','p')]:take(f'curve{j}_{key}',kind)
  self.spans.append(Span('opaque_tail',data[r.pos:],'b',r.pos))
  assert self.to_bytes()==data
 def to_bytes(self):return b''.join(s.raw for s in self.spans)
 def fields(self):return {s.name:s.raw for s in self.spans}
 def curve_pens(self):
  return [span for span in self.spans if span.kind == 'p' and span.name.startswith('curve')]
 def style(self,*,ink,line,color_map,font_height=20):
  allowed={'fc','10c','11c','12c','198','1b0','1e8','200'}|{f'curve{j}_pen' for j in range(self.curve_count)};changes=[]
  for s in self.spans:
   old=s.raw
   if s.kind=='f':s.raw=set_font(old,height=font_height,family='微软雅黑',weight=400)
   elif s.name in ('1b0','200'):s.raw=struct.pack('<I',ink)
   elif s.name in ('fc','10c','11c','12c'):
    pen=list(struct.unpack('<4I',old));pen[3]=line;s.raw=struct.pack('<4I',*pen)
   elif s.name.startswith('curve') and s.kind=='p':
    pen=list(struct.unpack('<4I',old));pen[3]=color_map(pen[3]);s.raw=struct.pack('<4I',*pen)
   if s.raw!=old:changes.append(dict(field=s.name,old_offset=s.offset,before_hex=old.hex(),after_hex=s.raw.hex()))
   assert s.name in allowed or s.raw==old
  result=self.to_bytes();check=HistoryCurveStyle(result)
  before=HistoryCurveStyle(self.original).fields();after=check.fields()
  assert before.keys()==after.keys()
  assert all(before[k]==after[k] for k in before if k not in allowed)
  return result,dict(changes=changes,allowed_fields=sorted(allowed),business_fields_identical=True,opaque_tail_identical=True)


def _control_style(record):
    if record.type_id != HISTORY_CURVE_TYPE:
        raise ValueError('Trace pens require a native history curve')
    common = CommonEnvelope.parse(record)
    if common.to_record().payload != record.payload:
        raise ValueError('History curve original does not round-trip')
    return common, HistoryCurveStyle(common.content)


def _pen_color(pen):
    return struct.unpack_from('<I', pen.raw, 12)[0]


def history_curve_colors(record):
    _, style = _control_style(record)
    return [{'trace_index': index, 'color': _pen_color(pen) & 0xffffff}
            for index, pen in enumerate(style.curve_pens())]


def history_curve_pens(record):
    _, style = _control_style(record)
    result = []
    for index, pen in enumerate(style.curve_pens()):
        line_style, width, _, color = struct.unpack('<IiiI', pen.raw)
        result.append({'trace_index': index, 'style': line_style, 'width': width, 'color': color & 0xffffff})
    return result


def _history_bindings(style):
    fields = {span.name: span for span in style.spans}
    bindings = [item.value for item in Array.parse(Reader(fields['bindings'].raw), True).items]
    return fields, bindings


def _has_history_time_column(fields, bindings):
    return bool(bindings and bindings[0] == CString.parse(Reader(fields['1b4'].raw)).value == 'MCGS_Time')


def _history_curve_x_length(style, fields, bindings):
    if style.curve_count != 16 or not _has_history_time_column(fields, bindings):
        return None
    if not CString.parse(Reader(fields['158'].raw)).value:
        return None
    # Original Stu and Pro saves map the coordinate length and existing unit
    # to consecutive DWORDs. Other label and starting-point fields are separate.
    unit, = struct.unpack('<I', fields['1bc'].raw)
    if unit >= len(_X_LENGTH_LIMITS):
        return None
    span = fields['1b8']
    length, = struct.unpack('<I', span.raw)
    upper = _X_LENGTH_LIMITS[unit]
    if not 1 <= length <= upper:
        return None
    return span, length, upper


def _constant_float32(raw):
    if len(raw) > 64 or re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', raw) is None:
        return None
    parsed = float(raw)
    return parsed if abs(parsed) <= _FLOAT32_LIMIT else None


def _float32(number):
    return struct.unpack('<f', struct.pack('<f', number))[0]


def _bound_numeric_traces(style, fields, bindings):
    for index in range(style.curve_count):
        prefix = f'curve{index}_'
        source = CString.parse(Reader(fields[prefix + 'source'].raw)).value
        trace_type = struct.unpack('<I', fields[prefix + 'type'].raw)[0]
        flag = fields[prefix + 'visible']
        visible = struct.unpack('<I', flag.raw)[0]
        if source and bindings[1:].count(source) == 1 and trace_type == 2 and visible in (0, 1):
            yield index, source, flag, bool(visible)


def _constant_trace_ranges(style, fields, bindings):
    for index, source, _, visible in _bound_numeric_traces(style, fields, bindings):
        if not visible:
            continue
        prefix = f'curve{index}_'
        spans = {name: fields[prefix + suffix] for name, suffix in _RANGE_FIELDS.items()}
        values = {name: _constant_float32(CString.parse(Reader(span.raw)).value) for name, span in spans.items()}
        low, high = values['minimum'], values['maximum']
        if low is not None and high is not None and _float32(low) < _float32(high):
            yield index, source, spans, values


def history_curve_configuration(record):
    _, style = _control_style(record)
    fields, bindings = _history_bindings(style)
    result = {'history_curve_ranges': [dict(trace_index=index, data_name=source, **values)
              for index, source, _, values in _constant_trace_ranges(style, fields, bindings)]}
    if _has_history_time_column(fields, bindings):
        result['history_curve_configuration'] = {
            key: CString.parse(Reader(fields[offset].raw)).value for key, offset in (
                ('data_group', '158'), ('time_column', '1b4'), ('selected_seconds_output', '160'),
                ('selected_milliseconds_output', '164'))}
        result['history_curve_visibility'] = [dict(trace_index=index, data_name=source, visible=visible)
             for index, source, _, visible in _bound_numeric_traces(style, fields, bindings)]
        axis = _history_curve_x_length(style, fields, bindings)
        if axis is not None:
            result['history_curve_x_length'] = axis[1]
    return result


def edit_history_curve_x_length(record, length):
    common, style = _control_style(record)
    fields, bindings = _history_bindings(style)
    axis = _history_curve_x_length(style, fields, bindings)
    if axis is None:
        raise ValueError('History curve X length requires the recognized bound coordinate archive and valid original unit and length')
    span, _, upper = axis
    if type(length) is not int or not 1 <= length <= upper:
        raise ValueError(f'History curve X length must be an integer in 1..{upper} for the existing unit')
    span.raw = struct.pack('<I', length)
    common.content = style.to_bytes()
    result = common.to_record()
    if history_curve_configuration(result).get('history_curve_x_length') != length:
        raise ValueError('History curve X length did not round-trip')
    return result


def edit_history_curve_ranges(record, edits):
    common, style = _control_style(record)
    fields, bindings = _history_bindings(style)
    ranges = {index: (spans, values) for index, _, spans, values in _constant_trace_ranges(style, fields, bindings)}
    if not isinstance(edits, list) or not edits:
        raise ValueError('History curve ranges require a nonempty list')
    expected = {}
    for edit in edits:
        if not isinstance(edit, dict) or not {'trace_index'} < edit.keys() <= _RANGE_FIELDS.keys() | {'trace_index'}:
            raise ValueError('History curve range requires trace_index and minimum or maximum')
        index = edit['trace_index']
        if type(index) is not int or index not in ranges or index in expected:
            raise ValueError('History curve trace must be a unique visible numeric trace with a bound data column and constant range')
        spans, original = ranges[index]
        values = original | {name: edit[name] for name in _RANGE_FIELDS if name in edit}
        if any(type(number) not in (int, float) or not -_FLOAT32_LIMIT <= number <= _FLOAT32_LIMIT
               for number in values.values()):
            raise ValueError('History curve range requires finite native float values')
        if _float32(values['minimum']) >= _float32(values['maximum']):
            raise ValueError('History curve minimum must be lower than maximum in native precision')
        expected[index] = values
        for name, span in spans.items():
            if values[name] == original[name]:
                continue
            value = CString.parse(Reader(span.raw))
            decimal_text = format(Decimal(str(values[name])), 'f')
            value.value = decimal_text.rstrip('0').rstrip('.') if '.' in decimal_text else decimal_text
            if _constant_float32(value.value) != values[name]:
                raise ValueError('History curve value cannot round-trip as a native decimal string')
            span.raw = value.to_bytes()
    common.content = style.to_bytes()
    result = common.to_record()
    actual = {row['trace_index']: {name: row[name] for name in _RANGE_FIELDS}
              for row in history_curve_configuration(result)['history_curve_ranges']}
    if any(actual.get(index) != values for index, values in expected.items()):
        raise ValueError('History curve ranges did not round-trip')
    return result


def edit_history_curve_visibility(record, edits):
    common, style = _control_style(record)
    fields, bindings = _history_bindings(style)
    timestamp = CString.parse(Reader(fields['1b4'].raw)).value
    if not bindings or bindings[0] != 'MCGS_Time' or timestamp != 'MCGS_Time':
        raise ValueError('History curve visibility requires an exact native MCGS_Time column')
    if not isinstance(edits, list) or not edits:
        raise ValueError('History curve visibility requires a nonempty list')
    traces = {index: (source, flag) for index, source, flag, _ in _bound_numeric_traces(style, fields, bindings)}
    expected = {}
    for edit in edits:
        if not isinstance(edit, dict) or edit.keys() != {'trace_index', 'visible'} or type(edit['visible']) is not bool:
            raise ValueError('History curve visibility requires trace_index and a boolean visible flag')
        index = edit['trace_index']
        if type(index) is not int or index in expected or index not in traces:
            raise ValueError('History curve visibility requires a unique numeric trace bound to an exact data column')
        source, span = traces[index]
        span.raw = struct.pack('<I', edit['visible'])
        expected[index] = (source, edit['visible'])
    common.content = style.to_bytes()
    result = common.to_record()
    actual = {row['trace_index']: (row['data_name'], row['visible'])
              for row in history_curve_configuration(result)['history_curve_visibility']}
    if any(actual.get(index) != before for index, before in expected.items()):
        raise ValueError('History curve visibility did not round-trip')
    return result


def _edit_history_curve_pens(record, edits, fields):
    common, style = _control_style(record)
    if not isinstance(edits, list) or not edits:
        raise ValueError('History curve pens require a nonempty list')
    pens = style.curve_pens()
    requested = {}
    for edit in edits:
        if not isinstance(edit, dict) or not {'trace_index'} < set(edit) <= fields | {'trace_index'}:
            raise ValueError('History curve pen requires trace_index and supported visual fields')
        index = edit['trace_index']
        if type(index) is not int or not 0 <= index < len(pens) or index in requested:
            raise ValueError('History curve trace_index is out of range or repeated')
        line_style, width, width_y, raw_color = struct.unpack('<IiiI', pens[index].raw)
        if 'color' in edit:
            color = edit['color']
            if type(color) is not int or not 0 <= color <= 0xffffff:
                raise ValueError('History curve color uses integer COLORREF 0..0xffffff')
            raw_color = (raw_color & 0xff000000) | color
        if 'style' in edit or 'width' in edit:
            line_style = edit.get('style', line_style)
            width = edit.get('width', width)
            # Both original COwnerSelLine pickers emit four patterned choices
            # at width 1 and six solid choices as PS_INSIDEFRAME at widths 1..6.
            if (type(line_style) is not int or type(width) is not int or
                    not ((line_style in (1, 2, 3, 4) and width == 1) or
                         (line_style == 6 and 1 <= width <= 6))):
                raise ValueError('History curve pen requires style 1..4 at width 1 or style 6 at width 1..6')
        requested[index] = struct.pack('<IiiI', line_style, width, width_y, raw_color)

    content = bytearray(common.content)
    for index, expected in requested.items():
        offset = pens[index].offset
        content[offset:offset + len(expected)] = expected
    common.content = bytes(content)
    result = common.to_record()
    _, checked = _control_style(result)
    after = checked.curve_pens()
    if any(after[index].raw != expected for index, expected in requested.items()):
        raise ValueError('History curve trace pen readback differs')
    return result


def edit_history_curve_colors(record, edits):
    return _edit_history_curve_pens(record, edits, {'color'})


def edit_history_curve_pens(record, edits):
    return _edit_history_curve_pens(record, edits, {'style', 'width', 'color'})

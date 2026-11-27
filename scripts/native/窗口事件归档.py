"""MCGS 窗口脚本、派发列表及公共窗口引用的归档。"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import struct

from mcs_window_archive import Reader, WindowArchive, write_cstring, write_count, FormatError
from mcs_button_control import ByteArray, CString
from 原生界面样式 import EventDispatch, GenericMetadata

目录 = Path(__file__).resolve().parent
STU_COMMON_WINDOW_LAYERS = ('bottom', 'middle', 'top')
WINDOW_CLICK_TYPE = 18
WINDOW_CLICK_ACTIONS = frozenset({'add_click_event_source', 'click_event_source', 'delete_click_event'})
WINDOW_MOUSE_DOWN_SOURCE = 'mouse_down_event_source'
WINDOW_DISPATCH_ACTIONS = WINDOW_CLICK_ACTIONS | {WINDOW_MOUSE_DOWN_SOURCE}
_MOUSE_DOWN_CLASS_REF = b'\x01\x80'
_PUBLIC_WINDOW_SLOT_COUNTS = {'Pro': 1, 'Stu': len(STU_COMMON_WINDOW_LAYERS)}
# The unparameterized window declaration matches native Pro and Stu records
# after clearing their source and compiled bytes.
_EMPTY_WINDOW_CLICK = bytes.fromhex(
    'ffff00000e00434576656e744469737061746368000000000000000012000000'
    'fffeff0543006c00690063006b0000000000fffeff00fffffffffffeff000000')


@dataclass
class 窗口事件:
    打开: str
    循环: str
    周期毫秒: int
    退出: str
    保留整数: bytes
    保留字符串: list[str]
    编译缓存: list[bytes]
    扩展: bytes
    原始字符串编码: list[bytes]
    原始计数编码: list[bytes]

    @classmethod
    def 解析(cls, 数据: bytes):
        读 = Reader(数据)
        开, 开码, _ = 读.cstring()
        循, 循码, _ = 读.cstring()
        周期 = 读.u32()
        退, 退码, _ = 读.cstring()
        保留整数 = 读.take(12)
        保留文本 = [读.cstring() for _ in range(3)]
        缓存 = [读.byte_array() for _ in range(3)]
        扩展 = 数据[读.pos:]
        if len(扩展) < 6:
            raise FormatError('窗口扩展被截断')
        return cls(开, 循, 周期, 退, 保留整数, [项[0] for 项 in 保留文本],
                   [项[0] for 项 in 缓存], 扩展,
                   [开码, 循码, 退码] + [项[1] for 项 in 保留文本], [项[1] for 项 in 缓存])

    def 序列化(self):
        def 字符串(值, 原码):
            return 原码 if Reader(原码).cstring()[0] == 值 else write_cstring(值)
        字符序列 = [self.打开, self.循环, self.退出] + self.保留字符串
        编码 = [字符串(值, 原码) for 值, 原码 in zip(字符序列, self.原始字符串编码)]
        缓存编码 = []
        for 内容, 原计数 in zip(self.编译缓存, self.原始计数编码):
            计数 = 原计数 if Reader(原计数).count() == len(内容) else write_count(len(内容))
            缓存编码.append(计数 + 内容)
        return (编码[0] + 编码[1] + struct.pack('<I', self.周期毫秒) + 编码[2]
                + self.保留整数 + b''.join(编码[3:]) + b''.join(缓存编码) + self.扩展)


def _窗口派发封套(扩展):
    读 = Reader(扩展)
    派发 = ByteArray.parse(读)
    后缀 = 读.take(len(扩展) - 读.pos)
    if len(后缀) == 10 and 后缀[:2] == b'\x06\0' and 后缀[6:] == bytes(4):
        return 派发, 后缀, 1
    if len(后缀) == 78 and 后缀[:2] == b'\x0e\0':
        return 派发, 后缀, len(STU_COMMON_WINDOW_LAYERS)
    raise FormatError('Unrecognized public-window suffix')


def _页面派发列表(扩展):
    派发, 后缀, 槽数 = _窗口派发封套(扩展)
    目录 = GenericMetadata.parse(派发.value, event_parser=_解析窗口派发)
    if (any(Reader(件.argument_arrays).count() for 件 in 目录.events)
            and (目录.count_raw != b'\x02\0' or not _有原厂Click及MouseDown(目录.events))):
        raise FormatError('Expected the original window Click followed by one bound MouseDown')
    if 目录.tail != bytes(2) or 目录.to_bytes() != 派发.value:
        raise FormatError('Unrecognized window dispatch list boundary')
    return 派发, 目录, 后缀, 槽数


def _读MouseDown参数(读, 名称数量):
    if 名称数量 != 4:
        raise FormatError('Window MouseDown requires four native parameter slots')
    名称 = [CString.parse(读).value for _ in range(名称数量)]
    if 读.count() != 4:
        raise FormatError('Unexpected window MouseDown parameter ID count')
    编号 = [读.u32() for _ in range(4)]
    if 读.count() != 4:
        raise FormatError('Unexpected window MouseDown parameter metadata count')
    原生类型字 = [读.u32() for _ in range(4)]
    if (not 名称[0].strip() or '\0' in 名称[0] or any(名称[1:]) or not 0 < 编号[0] <= 0x7fffffff
            or 编号[1:] != [0xffffffff] * 3 or 原生类型字 != [2, 0, 0, 0]):
        raise FormatError('Expected one verified first-parameter number binding and three empty slots')
    return [{'name': 名称[0], 'id': 编号[0], 'native_type_word': 原生类型字[0]}, None, None, None]


def _读取窗口参数(读, 类引用):
    数量 = 读.count()
    if 数量 and 类引用 == _MOUSE_DOWN_CLASS_REF:
        _读MouseDown参数(读, 数量)
    elif 数量 or any(读.count() for _ in range(2)):
        raise FormatError('Nonempty generic-event argument arrays require separate schema')


def _解析窗口派发(读):
    return EventDispatch.parse(读, read_arguments=_读取窗口参数)


def _有原厂Click及MouseDown(条目):
    if len(条目) != 2:
        return False
    Click, MouseDown = 条目
    # The second MFC record refers to the class declaration of the first.
    return (Click.header == _EMPTY_WINDOW_CLICK[:20] and Click.is_unparameterized_click(WINDOW_CLICK_TYPE)
            and MouseDown.header == _MOUSE_DOWN_CLASS_REF and Reader(MouseDown.argument_arrays).count() == 4
            and MouseDown.event_id == WINDOW_CLICK_TYPE and MouseDown.kind == 3
            and MouseDown.event_name.value == 'MouseDown' and not MouseDown.reserved.value
            and MouseDown.unknown == 0xffffffff and not MouseDown.tail_array.value
            and bool(MouseDown.source.value.strip()))


def _选页面Click(目录):
    if len(目录.events) == 1 and 目录.events[0].is_unparameterized_click(WINDOW_CLICK_TYPE):
        return 目录.events[0]
    if _有原厂Click及MouseDown(目录.events):
        return 目录.events[0]
    raise FormatError('Expected one unparameterized native window Click event')


def _选页面MouseDown(目录, 槽数, family):
    if family is not None and _PUBLIC_WINDOW_SLOT_COUNTS.get(family) != 槽数:
        raise FormatError('Window MouseDown public-window suffix does not match the project family')
    if not _有原厂Click及MouseDown(目录.events):
        raise FormatError('Expected the original window Click followed by one bound MouseDown')
    return 目录.events[1]


def 读取页面Click(原事件尾):
    _, 目录, _, _ = _页面派发列表(窗口事件.解析(原事件尾).扩展)
    return _选页面Click(目录)


def 读取页面MouseDown(原事件尾, *, family=None):
    _, 目录, _, 槽数 = _页面派发列表(窗口事件.解析(原事件尾).扩展)
    事件 = _选页面MouseDown(目录, 槽数, family)
    读 = Reader(事件.argument_arrays)
    return 事件, _读MouseDown参数(读, 读.count())


def 编辑页面派发(原事件尾, 操作, 规格, *, family=None):
    事件 = 窗口事件.解析(原事件尾)
    if 事件.序列化() != 原事件尾:
        raise FormatError('Window event tail does not round-trip')
    派发, 目录, 后缀, 槽数 = _页面派发列表(事件.扩展)
    if 操作 == 'add_click_event_source':
        if 目录.events:
            raise FormatError('New window Click requires an empty native dispatch list')
        新件 = EventDispatch.parse(Reader(_EMPTY_WINDOW_CLICK))
        if 新件.to_bytes() != _EMPTY_WINDOW_CLICK or not 新件.is_unparameterized_click(WINDOW_CLICK_TYPE):
            raise FormatError('Native window Click template differs')
        新件.set_click_source({**新件.click_identity(), 'source': 规格})
        目录.events.append(新件)
    elif 操作 == WINDOW_MOUSE_DOWN_SOURCE:
        _选页面MouseDown(目录, 槽数, family).set_script_source(规格)
    elif 操作 == 'click_event_source':
        _选页面Click(目录).set_click_source(规格)
    elif 操作 == 'delete_click_event':
        当前 = _选页面Click(目录)
        if len(目录.events) != 1:
            raise FormatError('Deleting this window Click would discard the class declaration used by MouseDown')
        if (not isinstance(规格, dict) or type(规格.get('event_type_id')) is not int
                or type(规格.get('event_id')) is not int or 规格 != 当前.click_identity()):
            raise ValueError('Native Click event preimage differs')
        目录.events.clear()
    else:
        raise ValueError('Unknown window dispatch operation')
    原计数 = Reader(目录.count_raw).count()
    if 原计数 != len(目录.events):
        目录.count_raw = write_count(len(目录.events))
    派发.value = 目录.to_bytes()
    事件.扩展 = 派发.to_bytes() + 后缀
    结果 = 事件.序列化()
    复读派发, 复读目录, 复读后缀, 复读槽数 = _页面派发列表(窗口事件.解析(结果).扩展)
    if (复读派发.value != 派发.value or 复读目录.to_bytes() != 目录.to_bytes()
            or 复读后缀 != 后缀 or 复读槽数 != 槽数):
        raise FormatError('Changed native window dispatch did not round-trip')
    return 结果


def 初始化页面派发事件(原事件尾):
    事件 = 窗口事件.解析(原事件尾)
    try:
        _窗口派发封套(事件.扩展)
    except FormatError:
        return 原事件尾
    派发, 目录, 后缀, 槽数 = _页面派发列表(事件.扩展)
    if not 目录.events:
        return 原事件尾
    if _有原厂Click及MouseDown(目录.events):
        family = 'Stu' if 槽数 == len(STU_COMMON_WINDOW_LAYERS) else 'Pro'
        raise FormatError(f'New page initialization requires a single unparameterized {family} Click or an empty list')
    if 槽数 == len(STU_COMMON_WINDOW_LAYERS):
        _选页面Click(目录)
    派发.value = bytes(4)
    事件.扩展 = 派发.to_bytes() + 后缀
    return 事件.序列化()


def _公共窗口槽位置(原事件尾: bytes) -> tuple[int, int]:
    事件 = 窗口事件.解析(原事件尾)
    if 事件.序列化() != 原事件尾:
        raise FormatError('Window event tail does not round-trip')
    _, _, 后缀, 槽数 = _页面派发列表(事件.扩展)
    # In both layouts the slot IDs follow the suffix marker; its start
    # moves when the native dispatch ByteArray changes length.
    return len(原事件尾) - len(后缀) + 2, 槽数


def 读取公共窗口槽(原事件尾: bytes) -> tuple[int, ...]:
    """Read the archived reference IDs in wire order, including empty slots."""
    位置, 数量 = _公共窗口槽位置(原事件尾)
    return struct.unpack_from(f'<{数量}i', 原事件尾, 位置)


def 改选公共窗口(原事件尾: bytes, 原编号: int, 新编号: int, *, 层级: str | None = None) -> bytes:
    """Retarget one verified slot and preserve the other slots verbatim."""
    if type(新编号) is not int or not (新编号 == -1 or 0 < 新编号 <= 0x7fffffff):
        raise ValueError('Expected an Int32 public-window ID or the native empty marker')
    位置, 数量 = _公共窗口槽位置(原事件尾)
    编号 = struct.unpack_from(f'<{数量}i', 原事件尾, 位置)
    索引 = 0
    if 层级 is not None:
        if 数量 != len(STU_COMMON_WINDOW_LAYERS) or 层级 not in STU_COMMON_WINDOW_LAYERS:
            raise ValueError('Public-window layer requires a verified Stu three-slot layout and bottom, middle or top')
        索引 = STU_COMMON_WINDOW_LAYERS.index(层级)
    if 编号[索引] != 原编号:
        raise ValueError('Current public-window ID differs from the source selection')
    if 层级 is not None and 新编号 != -1 and 新编号 != 原编号 and 新编号 in 编号:
        raise ValueError('The selected public window already occupies another layer')
    位置 += 索引 * 4
    return 原事件尾[:位置] + struct.pack('<i', 新编号) + 原事件尾[位置 + 4:]


def 设置窗口事件(原事件尾: bytes, 打开脚本='', 循环脚本='', 退出脚本='', 周期毫秒=100):
    """以原厂空窗口的事件尾为模板，保留扩展和未改事件，清除改动事件缓存。"""
    事件 = 窗口事件.解析(原事件尾)
    if 事件.序列化() != 原事件尾:
        raise FormatError('事件模板无法原样回环')
    if not 1 <= 周期毫秒 <= 2147483647:
        raise ValueError('窗口循环周期超出有效整数范围')
    for 索引, 属性, 内容 in [(0, '打开', 打开脚本), (1, '循环', 循环脚本), (2, '退出', 退出脚本)]:
        if not isinstance(内容, str) or '\x00' in 内容:
            raise ValueError('脚本须为不含NUL的文本')
        if getattr(事件, 属性) != 内容:
            setattr(事件, 属性, 内容)
            # 原厂以CByteArray保存事件编译码。源码变化不得保留旧缓存。
            # 新建空数组Serialize写count0，需由原厂编译生成实际运行字节码。
            事件.编译缓存[索引] = b''
    事件.周期毫秒 = 周期毫秒
    结果 = 事件.序列化()
    复读 = 窗口事件.解析(结果)
    assert 复读.序列化() == 结果
    assert [复读.打开, 复读.循环, 复读.退出, 复读.周期毫秒] == [打开脚本, 循环脚本, 退出脚本, 周期毫秒]
    assert 复读.扩展 == 事件.扩展
    assert 复读.保留整数 == 事件.保留整数 and 复读.保留字符串 == 事件.保留字符串
    return 结果

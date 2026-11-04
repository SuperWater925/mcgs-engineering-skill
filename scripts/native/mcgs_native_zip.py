"""已实证MCGSZIPE+双原文长度+标准zlib的纯文件封装；不执行厂商代码。"""
import struct
import zlib


MARKER=b'MCGSZIPE'
MAX_PLAIN=64*1024*1024


def unpack(raw):
    if raw[:8]!=MARKER:raise ValueError('本轮要求保留用户原厂MCGSZIPE封装')
    if len(raw)<18:raise ValueError('MCGSZIPE块过短')
    first,second=struct.unpack('<2I',raw[8:16])
    if first!=second or not 0<first<=MAX_PLAIN:raise ValueError('MCGSZIPE双长度不一致或越界')
    # Compression level is not a schema or software-release gate. The zlib
    # decoder validates CMF/FLG, dictionary requirements and the Adler checksum.
    decoder=zlib.decompressobj()
    try:plain=decoder.decompress(raw[16:],first+1)
    except zlib.error as error:raise ValueError('MCGSZIPE标准zlib流无效: '+str(error)) from None
    if len(plain)>first or decoder.unconsumed_tail:raise ValueError('实际解压长度超过声明')
    try:plain+=decoder.flush()
    except zlib.error as error:raise ValueError('MCGSZIPE标准zlib尾部无效: '+str(error)) from None
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(plain)!=first:
        raise ValueError('MCGSZIPE解压eof/尾部或长度不符')
    return plain


def pack(plain):
    if not 0<len(plain)<=MAX_PLAIN:raise ValueError('归档长度越界')
    raw=MARKER+struct.pack('<2I',len(plain),len(plain))+zlib.compress(plain,1)
    if unpack(raw)!=plain:raise ValueError('MCGSZIPE压缩封装回环失败')
    return raw

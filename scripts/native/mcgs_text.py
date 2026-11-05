"""Explicit locale for native narrow strings; never inferred from release numbers."""
import codecs
import os


class NativeCString(str):
    """An unchanged CString retains its actual width and length-prefix form."""
    def __new__(cls,value,wire=b'',wide=True):
        result=super().__new__(cls,value);result.wire=wire;result.wide=wide;return result
    def __getnewargs__(self):return str(self),self.wire,self.wide


def narrow_encoding():
    """Default to the measured Chinese archive; callers may select its actual code page."""
    return codecs.lookup(os.environ.get('MCGS_ARCHIVE_CODEPAGE','cp936')).name

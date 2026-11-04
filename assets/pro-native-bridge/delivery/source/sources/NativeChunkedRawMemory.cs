// Preserve the existing NativeMemory per-read bound while reading a bounded native buffer.
using System;
namespace McgsInternalBridge {
 internal static class NativeChunkedRawMemory {
  internal static byte[] Read(IntPtr pointer,int length){NativeMemory.Require(length>=0&&length<=64*1024*1024&&(length==0||pointer!=IntPtr.Zero),"Native payload exceeds the declared bounded buffer.");var result=new byte[length];for(int offset=0;offset<length;){int count=Math.Min(1024*1024,length-offset);byte[] block=NativeMemory.Bytes(NativeMemory.Add(pointer,offset),count);Array.Copy(block,0,result,offset,count);offset=checked(offset+count);}return result;}
 }
}

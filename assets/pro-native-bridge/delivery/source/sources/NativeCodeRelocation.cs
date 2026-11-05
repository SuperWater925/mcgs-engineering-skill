// Rebase only the bytes contained in an existing native guard. No native reads.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

namespace McgsInternalBridge {
 internal static class NativeCodeRelocation {
  internal static byte[] Rebase(byte[] canonical,IEnumerable offsets,uint actualBase,uint referenceBase) {
   if(canonical==null)throw new ArgumentNullException("canonical");
   byte[] result=(byte[])canonical.Clone();RebaseInPlace(result,offsets,actualBase,referenceBase);return result;
  }
  internal static void RebaseInPlace(byte[] canonical,IEnumerable offsets,uint actualBase,uint referenceBase) {
   RebaseDeltaInPlace(canonical,offsets,unchecked(actualBase-referenceBase));
  }
  internal static void RebaseDeltaInPlace(byte[] canonical,IEnumerable offsets,uint delta) {
   if(canonical==null)throw new ArgumentNullException("canonical");
   if(offsets==null)throw new ArgumentNullException("offsets");
   var positions=new List<int>();var seen=new HashSet<int>();
   foreach(object value in offsets) {
    if(!(value is int)&&!(value is long)&&!(value is uint)&&!(value is short)&&!(value is ushort)&&!(value is byte))
     throw new InvalidDataException("A native guard relocation offset must be integral.");
    long number=Convert.ToInt64(value,CultureInfo.InvariantCulture);
    if(number<0||number>=canonical.Length||!seen.Add((int)number))
     throw new InvalidDataException("A native guard relocation must identify one unique visible byte.");
    positions.Add((int)number);
   }
   foreach(int at in positions) {
    int count=Math.Min(4,canonical.Length-at);uint low=0;
    for(int i=0;i<count;i++)low|=(uint)canonical[at+i]<<(8*i);
    uint relocated=unchecked(low+delta);
    for(int i=0;i<count;i++)canonical[at+i]=(byte)(relocated>>(8*i));
   }
  }
 }
}

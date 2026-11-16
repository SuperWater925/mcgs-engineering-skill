// Observe the original before-modify boundary. We do not emulate the private
// history serializer or bind unrelated STORE/selection implementation bodies.
using System;using System.Collections;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static class NativeOriginalHistoryObservation {
  static object WithoutTransientState(object value){object copy=NativeDynamicCollections.CopyValue(value,false);foreach(var row in NativeDynamicCollections.DictionaryValues(copy)){row.Remove("raw_DWORD60");row.Remove("raw60");row.Remove("field_60_raw_uint32");}return copy;}
  internal static void VerifyForest(object before,object after){NativePageControlPreparation.Same(WithoutTransientState(before),WithoutTransientState(after),"Original history notification changed existing control identity, geometry or business content.");}
  internal static void VerifyPage(Dictionary<string,object> before,Dictionary<string,object> after){
   foreach(string key in new[]{"pages","page_id","page_name","page_iobject","document","view"})NativePageControlPreparation.Same(before[key],after[key],"Original history notification changed page identity: "+key);
   VerifyForest(before["top_level_controls"],after["top_level_controls"]);
   var left=new List<object>();var right=new List<object>();foreach(object x in(IEnumerable)before["attributes"])left.Add(x);foreach(object x in(IEnumerable)after["attributes"])right.Add(x);
   int relative=NativeLayout.Offset("document.history_generated")-NativeLayout.Offset("document.attributes");NativeMemory.Require(left.Count==right.Count,"Original history changed attribute extent.");if(relative>=0&&relative%4==0&&relative/4<left.Count)left[relative/4]=right[relative/4];
   NativePageControlPreparation.Same(left,right,"Original history notification changed non-cache page attributes.");
  }
 }
}

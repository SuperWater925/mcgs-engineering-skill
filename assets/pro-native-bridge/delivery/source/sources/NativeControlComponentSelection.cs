// A native getter may legally expose repeated component captions on one owner.
using System;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativeControlPropertyEditing {
  static void AnnotateComponentOccurrences(List<Dictionary<string,object>> values){
   var counts=new Dictionary<Tuple<string,string,int>,int>();
   foreach(var row in values){
    var identity=Tuple.Create(Convert.ToString(row["native_owner"]),Convert.ToString(row["native_key"]),Convert.ToInt32(row["native_type_tag"]));
    int ordinal;counts.TryGetValue(identity,out ordinal);row["native_key_occurrence"]=ordinal;counts[identity]=checked(ordinal+1);
   }
  }
  static IntPtr ResolveComponent(Api api,List<Dictionary<string,object>> values,IntPtr owner,object token){
   string key;int occurrence=-1;
   if(token is string)key=(string)token;
   else{
    var item=Map(token);NativeMemory.Require(item.Count==2&&item.ContainsKey("native_key")&&item.ContainsKey("occurrence")&&item["native_key"] is string,"Component selector must be a unique caption or {native_key,occurrence}.");
    object ordinal=item["occurrence"];NativeMemory.Require(ordinal is int||ordinal is long||ordinal is uint,"Component occurrence must be an exact integer.");
    long number=Convert.ToInt64(ordinal);NativeMemory.Require(number>=0&&number<Int32.MaxValue,"Component occurrence is outside the guarded getter bound.");occurrence=(int)number;key=(string)item["native_key"];
   }
   NativeMemory.Require(!String.IsNullOrEmpty(key)&&key.IndexOf('\0')<0,"Component native key is invalid.");
   IntPtr found=IntPtr.Zero;int matches=0;
   foreach(var row in values){if(Convert.ToString(row["native_owner"])!=NativeMemory.Hex(owner)||Convert.ToString(row["native_key"])!=key||Convert.ToInt32(row["native_type_tag"])!=9)continue;
    if(occurrence<0){NativeMemory.Require(found==IntPtr.Zero,"Component caption repeats; select the exact getter occurrence explicitly.");found=new IntPtr(NativeEngine.Number(row["component_iobject"]));}
    else if(matches==occurrence)found=new IntPtr(NativeEngine.Number(row["component_iobject"]));matches++;
   }
   NativeMemory.Require(found!=IntPtr.Zero&&(occurrence<0||occurrence<matches),"Requested native component occurrence is absent.");
   NativePropertyTarget.Describe(api.Engine,found);return found;
  }
 }
}

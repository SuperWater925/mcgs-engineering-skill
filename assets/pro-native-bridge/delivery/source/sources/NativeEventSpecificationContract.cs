// Wire compatibility is retained: source10 is a variable connection, text70 is script.
using System;using System.Collections;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static class NativeEventSpecificationContract {
  internal const string SourceSemantics="source10 is an optional main variable connection; arguments are ordered variable output connections; only text70 is event script";
  static Dictionary<string,object>M(object value){return(Dictionary<string,object>)value;}
  static int N(object value){return Convert.ToInt32(value,System.Globalization.CultureInfo.InvariantCulture);}
  static void Connection(string value){NativeMemory.Require(value!=null&&value.Length<=1048576&&value.IndexOf('\0')<0&&value.IndexOf('\r')<0&&value.IndexOf('\n')<0,"Event connection must be one actual variable name or empty; script/comments belong to text70.");}
  internal static void Validate(Dictionary<string,object> value,IEnumerable definitions){Dictionary<string,object> found=null;foreach(object raw in definitions){var definition=M(raw);if(N(definition["native_event_id"])==N(value["intC"])){NativeMemory.Require(found==null,"Native event definition ID repeats.");found=definition;}}NativeMemory.Require(found!=null,"Event value has no actual native declaration.");Validate(value,found);}
  internal static void Validate(Dictionary<string,object> value,Dictionary<string,object> definition){
   NativeMemory.Require(N(definition["native_event_id"])==N(value["intC"])&&Convert.ToString(definition["native_name"])==Convert.ToString(value["string8"]),"Event value ID/name differs from its actual native declaration.");
   string connection=Convert.ToString(value["string10"]);Connection(connection);int main=N(definition["raw_word_10"]);NativeMemory.Require(connection.Length==0||main==3||main==4||main==8,"This actual event declaration does not accept a main variable connection; put event script/comments only in text70.");
   object rawDescriptors;NativeMemory.Require(definition.TryGetValue("argument_descriptors_raw_uint16",out rawDescriptors)||definition.TryGetValue("argument_descriptors",out rawDescriptors),"Native argument descriptors are absent.");var descriptors=new List<object>();foreach(object raw in(IEnumerable)rawDescriptors)descriptors.Add(raw);int count=0;foreach(object raw in(IEnumerable)value["strings1C"]){NativeMemory.Require(raw is string,"Event output connections require names, not literal values or derived IDs.");Connection((string)raw);count++;}NativeMemory.Require(count==descriptors.Count,"Event output-connection count differs from its actual native declaration.");
   // Existence and resolved IDs/types remain native compiler outputs. This
   // managed guard does not fabricate a variable, call a resolver, or silently
   // convert numeric literals/expressions into connections.
   string script=Convert.ToString(value["string70"]);NativeMemory.Require(script!=null&&script.Length<=1048576&&script.IndexOf('\0')<0,"Event script text70 bound/NUL differs.");
  }
 }
}

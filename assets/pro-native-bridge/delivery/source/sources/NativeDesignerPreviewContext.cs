using System;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal static void RequireDesignerPreviewContext(NativeEngine e,NativeContext c,string project,IntPtr doc){var api=new Api(e,c,project);foreach(Node node in Flatten(api.Forest(doc)))NativeMemory.Require(!node.Class.External,"A native external component needs its own proven designer preview context before opening this page; no frame command entered.");}
 }
}

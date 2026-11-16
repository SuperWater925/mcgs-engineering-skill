using System;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  // Opening an existing page is owned by the original designer. Its controls
  // need not have bridge lifecycle adapters unless an operation targets them.
  internal static void RequireDesignerPreviewContext(NativeEngine e,NativeContext c,string project,IntPtr doc){NativeMemory.Readable(doc,4);}
 }
}

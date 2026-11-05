// Borrowed vector resource objects are not registered page IObjects.
// In particular, never call IObject14/15 to manufacture an identity for them.
using System;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal static Dictionary<string,object> RawPictureDrawTree(NativeEngine engine,NativeContext context,string project,IntPtr root){
   if(root==IntPtr.Zero)return null;
   NativeOperationTrace.SetPhase("picture-vector-raw-api-begin");
   var api=new Api(engine,context,project);
   NativeOperationTrace.SetPhase("picture-vector-raw-owning-tree-begin");
   IntPtr document=NativeMemory.Ptr(root,0x64);
   // Tree validates installed concrete RTTI/vtables/type/size and follows only
   // the raw owning Cell/Unit CObList. NULL is a valid resource document owner.
   Node tree=api.Tree(root,document,new int[]{0},new HashSet<uint>(),0);RequireKnownSubtree(tree,"complete vector-resource payload read");
   NativeOperationTrace.SetPhase("picture-vector-raw-owning-tree-returned");
   return RawPictureDrawNode(api,tree);
  }
  static Dictionary<string,object> RawPictureDrawNode(Api api,Node node){
   NativeOperationTrace.SetPhase("picture-vector-raw-node-begin-"+node.Class.Name);
   byte[] original=NativeChunkedRawMemory.Read(node.Full,node.Class.Size);
   var row=new Dictionary<string,object>{
    {"class",node.Class.Name},{"rtti",".?AV"+node.Class.Name+"@@"},
    {"type_id",node.Class.TypeId},{"size",node.Class.Size},{"path",node.Path},
    {"complete",NativeMemory.Hex(node.Full)},
    {"owner_document",NativeMemory.Hex(NativeMemory.Ptr(node.Full,0x64))},
    {"cached_parent_iobject_raw",NativeMemory.Hex(NativeMemory.Ptr(node.Full,8))},
    // IObject9 B46270 uses IO+48 = complete+4C; copying the existing CString
    // does not construct an MFC return object or invoke any vector virtual.
    {"name",NativeUsableEditPermit.ReadCurrentCString(NativeMemory.Add(node.Full,0x4C),1048576)},
    {"rectangle",NativePageControlAbi.Rectangle(node.Full)},
    {"raw_DWORD44",unchecked((uint)NativeMemory.I32(node.Full,0x44))},
    {"raw_DWORD48",unchecked((uint)NativeMemory.I32(node.Full,0x48))},
    {"raw_DWORD60",unchecked((uint)NativeMemory.I32(node.Full,0x60))},
    {"raw_DWORDB0",unchecked((uint)NativeMemory.I32(node.Full,0xB0))},
    {"native_identity_queried",false},{"native_name_getter_called",false},
    {"raw_native_object_hex",BitConverter.ToString(original).Replace("-","").ToLowerInvariant()},
    {"all_deep_payloads_covered",false}};
   var children=new List<object>();
   foreach(Node child in node.Children)children.Add(RawPictureDrawNode(api,child));
   row["children"]=children;
   NativeMemory.Require(BitConverter.ToString(original)==BitConverter.ToString(NativeChunkedRawMemory.Read(node.Full,node.Class.Size)),"Vector raw object changed during borrowed capture.");
   NativeOperationTrace.SetPhase("picture-vector-raw-node-returned-"+node.Class.Name);
   return row;
  }
 }
}

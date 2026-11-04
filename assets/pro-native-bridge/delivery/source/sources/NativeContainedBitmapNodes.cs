// Exact, already typed Bitmap members inside an existing vector draw tree.
// No serializer, clone, lazy loader or native mutation is used by this reader.
using System;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal sealed class ContainedBitmapNode {
   internal IntPtr Full,Image;internal int[] Path;internal string Name;
  }
  internal static List<ContainedBitmapNode> ContainedBitmapNodes(NativeEngine e,NativeContext c,string project,IntPtr root){
   var result=new List<ContainedBitmapNode>();if(root==IntPtr.Zero)return result;
   var api=new Api(e,c,project);Node tree=api.Tree(root,NativeMemory.Ptr(root,0x64),new int[]{0},new HashSet<uint>(),0);
   foreach(Node node in Flatten(new List<Node>{tree}))if(node.Class.Name=="CDrawBitmap"){
    NativeMemory.Require(node.Class.TypeId==0x5009&&node.Class.Size==0x188,"Contained Bitmap member layout differs.");
    result.Add(new ContainedBitmapNode{Full=node.Full,Image=NativeMemory.Add(node.Full,0xE4),Path=node.Path,Name=NativeStrategyProfile.ReadName(api.Shared.Shared,NativeMemory.Add(node.Full,4))});
   }
   return result;
  }
 }
}

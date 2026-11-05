// Native Bitmap and multi-state image members in an already loaded vector draw tree.
using System;using System.Collections;using System.Collections.Generic;using System.Globalization;using System.IO;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal const string ContainedMembersProfileSha="e484b72d2ef79314ec620422121bfff2eff54b03d6c867e40f9b9ea4848e8060";
  internal sealed class ContainedImageMember {
   internal IntPtr Full,Image,State,Frame;internal int[] Path;internal string Name,Carrier;internal int StateIndex=-1,FrameIndex=-1,NamePointerOffset=-1;
   internal Dictionary<string,object> Selector(){return new Dictionary<string,object>{{"control_path",Path},{"carrier",Carrier},{"state_index",StateIndex},{"frame_index",FrameIndex}};}
  }
  sealed class ImageMembersAbi {
   readonly NativeEngine engine;readonly Dictionary<string,Dictionary<string,object>> tables=new Dictionary<string,Dictionary<string,object>>();
   internal ImageMembersAbi(NativeEngine e){engine=e;string file=System.IO.Path.Combine(NativeUsableEditPermit.DirectoryRoot,"page-control-prep","complex-control-prep","contained-control-image-members-abi-profile.json");NativeMemory.Require(NativeMemory.Hash(file)==ContainedMembersProfileSha,"Contained image-member ABI changed.");var p=Load(file);NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(p["binary_sha256"]),engine.ImageSha256,"NativeContainedImageMembers:12:editor"),"Contained image-member binary differs.");foreach(object value in(IEnumerable)p["tables"]){var row=Map(value);tables.Add(Convert.ToString(row["name"]),row);}foreach(object value in(IEnumerable)p["functions"]){var row=Map(value);string hex=Convert.ToString(row["bytes"]);byte[] bytes=new byte[hex.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);NativeCodeRelocation.RebaseDeltaInPlace(bytes,(IEnumerable)row["reloc_offsets"],unchecked((uint)(NativeMemory.U(engine.ImageBase)-0x400000U)));NativeMemory.Require(BitConverter.ToString(bytes)==BitConverter.ToString(NativeMemory.Bytes(engine.Address(Num(row["rva"])),bytes.Length)),"Contained member original code differs.");}}
   internal void Table(IntPtr value,string name){var t=tables[name];IntPtr vt=engine.Address(Num(t["vtable_rva"])),col=engine.Address(Num(t["col_rva"]));NativeMemory.Require(value!=IntPtr.Zero&&NativeMemory.Ptr(value,0)==vt&&NativeMemory.Ptr(vt,-4)==col&&NativeMemory.I32(col,4)==0&&NativeMemory.Ptr(col,12)==engine.Address(Num(t["type_rva"]))&&NativeMemory.Ascii(NativeMemory.Add(NativeMemory.Ptr(col,12),8),256)==Convert.ToString(t["rtti"]),"Contained image state/frame class differs: "+name);int i=0;foreach(object slot in(IEnumerable)t["slots"])NativeMemory.Require(NativeMemory.Ptr(vt,i++*4)==engine.Address(Num(slot)),"Contained image state/frame slot differs.");}
   internal List<IntPtr> Pointers(IntPtr array,string name){Table(array,name);byte[] h=NativeMemory.Bytes(array,20);IntPtr data=NativeMemory.Ptr(array,4);int count=NativeMemory.I32(array,8),capacity=NativeMemory.I32(array,12);NativeMemory.Require(count>=0&&capacity>=count&&(count==0||data!=IntPtr.Zero),"Contained image state/frame array bounds differ.");var rows=new List<IntPtr>();var seen=new HashSet<uint>();for(int i=0;i<count;i++){IntPtr p=NativeMemory.Ptr(data,4*i);NativeMemory.Require(p!=IntPtr.Zero&&seen.Add(NativeMemory.U(p)),"Contained image state/frame has an aliased/null owning pointer.");rows.Add(p);}NativeMemory.Require(BitConverter.ToString(h)==BitConverter.ToString(NativeMemory.Bytes(array,20)),"Contained image state/frame array changed while reading.");return rows;}
  }
  internal static List<ContainedImageMember> ContainedImageMembers(NativeEngine e,NativeContext c,string project,IntPtr root){
   var rows=new List<ContainedImageMember>();if(root==IntPtr.Zero)return rows;var api=new Api(e,c,project);var abi=new ImageMembersAbi(e);Node tree=api.Tree(root,NativeMemory.Ptr(root,0x64),new int[]{0},new HashSet<uint>(),0);RequireKnownSubtree(tree,"contained image-member ownership read");
   foreach(Node node in Flatten(new List<Node>{tree})){
    NativeMemory.Require(node.Class.Name!="CDrawDll","Dynamic provider-specific image ownership inside a vector resource is not covered by the standard carrier contract.");
    NativeMemory.Require(Array.IndexOf(new string[]{"CDrawBitmap","CDrawMulBtn","CDrawCell","CDrawUnit","CDrawRect","CDrawLine","CDrawLabel","CDrawEdit","CDrawButton","CDrawHisPic","CDrawSaveData"},node.Class.Name)>=0,"This vector control class has no closed standard image-carrier contract.");
    NativeAnimationListEditing.RequireKnownRawList(e,node.Full);
    if(node.Class.Name=="CDrawBitmap"){NativeMemory.Require(node.Class.TypeId==0x5009&&node.Class.Size==0x188,"Contained Bitmap layout differs.");rows.Add(new ContainedImageMember{Full=node.Full,Image=NativeMemory.Add(node.Full,0xE4),Path=node.Path,Carrier="CDrawBitmap.embedded_image",NamePointerOffset=0xF0});}
    else if(node.Class.Name=="CDrawMulBtn"){
     var states=abi.Pointers(NativeMemory.Add(node.Full,0x124),"MultiImageStates");for(int s=0;s<states.Count;s++){IntPtr state=states[s];abi.Table(state,"ImageListInObj");var frames=abi.Pointers(NativeMemory.Add(state,8),"ImageFrameArray");for(int f=0;f<frames.Count;f++){IntPtr frame=frames[f];abi.Table(frame,"ImageInObj");NativeMemory.Readable(frame,0x78);IntPtr image=NativeMemory.Ptr(frame,0x68);NativeMemory.Require(image!=IntPtr.Zero,"Original multi-state image frame has no COwnerBitmap.");rows.Add(new ContainedImageMember{Full=node.Full,Image=image,State=state,Frame=frame,Path=node.Path,Carrier="CDrawMulBtn.state_image",StateIndex=s,FrameIndex=f});}}
    }
   }
   return rows;
  }
 }
}

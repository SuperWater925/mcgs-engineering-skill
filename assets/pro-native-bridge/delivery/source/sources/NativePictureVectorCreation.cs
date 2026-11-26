// Original selected-control archive -> owned vector picture. No opaque image bytes are synthesized.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;using System.Globalization;using System.IO;using System.Runtime.InteropServices;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativePictureResources {
  internal const string VectorCreateKind="picture-create-from-controls";
  const string RectangleVectorSource="current-rectangle-control";
  const string LineVectorSource="current-line-control";
  const string StaticSelectionVectorSource="current-static-controls";
  internal const string VectorCreateProfileSha="ae946ee4eda9fdcf985ce603f8bfd558407cc04c2a32a0a3ebb280459305b676";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr VectorListCtor(IntPtr self,int blockSize);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int VectorLoad(IntPtr self,IntPtr archive);

  sealed class VectorCreateApi {
   internal readonly EditApi Pictures;readonly Dictionary<string,IntPtr> methods=new Dictionary<string,IntPtr>();
   readonly List<KeyValuePair<IntPtr,byte[]>> prefixes=new List<KeyValuePair<IntPtr,byte[]>>();readonly List<KeyValuePair<IntPtr,IntPtr>> iats=new List<KeyValuePair<IntPtr,IntPtr>>();
   internal VectorCreateApi(NativeEngine e,NativeContext c,string p){Pictures=new EditApi(e,c,p);string file=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"resources-prep","picture-vector-create-abi-profile.v2.json");NativeMemory.Require(NativeMemory.Hash(file)==VectorCreateProfileSha,"Original vector creation profile changed.");var profile=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue}.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),e.ImageSha256,"NativePictureVectorCreation:13:editor"),"Vector creation binary differs.");foreach(object item in(IEnumerable)profile["guards"]){var row=Map(item);IntPtr at=e.Address(Number(row["rva"]));prefixes.Add(new KeyValuePair<IntPtr,byte[]>(at,Rebase(row,NativeMemory.U(e.ImageBase),0x400000U)));}foreach(var pair in Map(profile["methods"]))methods.Add(pair.Key,e.Address(Number(pair.Value)));
    string mfcFile=Path.GetFullPath(Convert.ToString(profile["mfc_file"]));IntPtr mfc=IntPtr.Zero;int size=0;foreach(ProcessModule module in Process.GetCurrentProcess().Modules)if(NativeLazyFunctionProfile.SameModule(module,mfcFile)){NativeMemory.Require(mfc==IntPtr.Zero||mfc==module.BaseAddress,"Vector creation MFC owner ambiguous.");mfc=module.BaseAddress;size=module.ModuleMemorySize;}NativeMemory.Require(mfc!=IntPtr.Zero&&NativeBinaryIdentity.Observe(Convert.ToString(profile["mfc_sha256"]),NativeMemory.Hash(mfcFile),"NativePictureVectorCreation:14:module"),"Vector creation MFC owner/hash differs.");foreach(object item in(IEnumerable)profile["imports"]){var row=Map(item);int rva=Number(row["target_rva"]);NativeMemory.Require(rva>=0&&rva<size,"Vector creation MFC export outside verified module.");IntPtr target=NativeMemory.Add(mfc,rva);NativeMemory.Require(PictureExportOrdinal(mfc,new IntPtr(Number(row["ordinal"])))==target,"Vector creation original MFC ordinal differs.");iats.Add(new KeyValuePair<IntPtr,IntPtr>(e.Address(Number(row["iat_rva"])),target));prefixes.Add(new KeyValuePair<IntPtr,byte[]>(target,Rebase(row,NativeMemory.U(mfc),0x10000000U)));}Check();
   }
   static byte[] Rebase(Dictionary<string,object> row,uint actual,uint preferred){string hex=Convert.ToString(row["bytes"]);byte[] value=new byte[hex.Length/2];for(int i=0;i<value.Length;i++)value[i]=Byte.Parse(hex.Substring(2*i,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);NativeCodeRelocation.RebaseDeltaInPlace(value,(IEnumerable)row["reloc_offsets"],unchecked((uint)(actual-preferred)));return value;}
   internal void Check(){Pictures.Raw.Common.Current();foreach(var prefix in prefixes)NativeMemory.Require(Hex(prefix.Value)==Hex(NativeMemory.Bytes(prefix.Key,prefix.Value.Length)),"Vector creation original method prefix changed.");foreach(var iat in iats)NativeMemory.Require(NativeMemory.Ptr(iat.Key,0)==iat.Value,"Vector creation original MFC IAT changed.");}
   internal T Bind<T>(string name)where T:class{return Pictures.Raw.Engine.Bind<T>(methods[name]);}
   NativePageDocumentProperties.Api shapeProperties;
   NativeAnimationListEditing.Api shapeAnimations;
   internal void RequireStaticShape(IntPtr control,int typeId){
    var raw=Pictures.Raw;
    if(shapeProperties==null)shapeProperties=new NativePageDocumentProperties.Api(raw.Engine,raw.Context,raw.Project);
    if(shapeAnimations==null)shapeAnimations=new NativeAnimationListEditing.Api(raw.Engine);
    NativeMemory.Require(NativeMemory.I32(control,12)==typeId&&shapeAnimations.Items(control).Count==0&&
     !NativeControlEventEditing.HasStoredControlEvents(shapeProperties,control),
     "Vector selection requires original static controls without animations or stored events.");
    // The original CDrawObj archive's optional link writes its ID and CString from these members.
    NativeMemory.Require(NativeMemory.I32(control,0xDC)==0&&CString(NativeMemory.Add(control,0xE0),4096)=="",
     "Vector shape carries a native link.");
   }
   internal Dictionary<string,object> StaticShapePayload(IntPtr control,int typeId){
    RequireStaticShape(control,typeId);
    return new Dictionary<string,object>{{"pen_type",unchecked((ushort)Marshal.ReadInt16(control,0x68))},
     {"pen",Hex(NativeMemory.Bytes(NativeMemory.Add(control,0x6C),16))},
     {"brush_type",unchecked((ushort)Marshal.ReadInt16(control,0x7C))},
     {"brush",Hex(NativeMemory.Bytes(NativeMemory.Add(control,0x90),12))}};
   }
  }

  static int[] LineVectorBounds(int[] line){
   int left=Math.Min(line[0],line[2]),top=Math.Min(line[1],line[3]);
   int right=Math.Max(line[0],line[2]),bottom=Math.Max(line[1],line[3]);
   // The original selection worker uses this rectangle as both the canvas and the
   // divisor of its endpoint projection. A single axis-aligned line has zero area.
   NativeMemory.Require(left!=Int32.MinValue&&top!=Int32.MinValue&&
    0L<(long)right-left&&(long)right-left<=Int32.MaxValue&&
    0L<(long)bottom-top&&(long)bottom-top<=Int32.MaxValue,
    "Original selection conversion of one line requires nonzero width and height. Use a positive vector canvas to create a horizontal or vertical line.");
   return new int[]{left,top,right,bottom};
  }

  static int StaticVectorType(string className){
   if(className=="CDrawLine")return 0x5002;
   if(className=="CDrawRect")return 0x5004;
   if(className=="CDrawBitmap")return 0x5009;
   if(className=="CDrawCell")return 0x5039;
   if(className=="CDrawUnit")return 0x503A;
   throw new ArgumentException("Static vector selection requires a rectangle, line, named raster Bitmap or native static group.");
  }
  static bool IsVectorGroup(int typeId){return typeId==0x5039||typeId==0x503A;}

  static IntPtr VectorShapePointer(Dictionary<string,object> shape){
   string pointer=Convert.ToString(shape["complete"]);
   return new IntPtr(unchecked((int)UInt32.Parse(pointer.Substring(2),NumberStyles.HexNumber,CultureInfo.InvariantCulture)));
  }

  static int ExpandGroupCoordinate(int relative,int origin,int end){
   long product=(long)relative*((long)end-origin);
   long scaled=(Math.Abs(product)+5000)/10000;
   if(product<0)scaled=-scaled;
   return checked(origin+(int)scaled);
  }

  static void ReadStaticVectorGroup(VectorCreateApi api,Dictionary<string,object> tree,int[] absolute,int[] path,
   List<Dictionary<string,object>> leaves,List<string> allGroupLinkers){
   int typeId=StaticVectorType(Convert.ToString(tree["class"]));
   IntPtr native=VectorShapePointer(tree);
   bool isGroup=IsVectorGroup(typeId);
   NativeMemory.Require(isGroup||typeId==0x5002||typeId==0x5004,
    "A static vector group requires only group, rectangle and line descendants.");
   string linker=api.Pictures.References.Path(NativeOpaqueDrawState.ControlObject(native));
   allGroupLinkers.Add(linker);
   if(!isGroup){
    leaves.Add(new Dictionary<string,object>{{"control_path",path},{"control_class",tree["class"]},
     {"control_name",tree["name"]},{"draw_tree",tree},{"page_geometry",absolute},
     {"shape_style",api.StaticShapePayload(native,typeId)},{"control_linker",linker}});
    return;
   }
   api.RequireStaticShape(native,typeId);
   long width=(long)absolute[2]-absolute[0],height=(long)absolute[3]-absolute[1];
   var children=(IList)tree["children"];
   NativeMemory.Require(width>0&&width<=Int32.MaxValue&&height>0&&height<=Int32.MaxValue&&children.Count>0,
    "Original group expansion requires a nonempty positive native group rectangle.");
   for(int i=0;i<children.Count;i++){
    var child=Map(children[i]);
    var relative=(int[])child["rectangle"];
    var pageBounds=new[]{
     ExpandGroupCoordinate(relative[0],absolute[0],absolute[2]),ExpandGroupCoordinate(relative[1],absolute[1],absolute[3]),
     ExpandGroupCoordinate(relative[2],absolute[0],absolute[2]),ExpandGroupCoordinate(relative[3],absolute[1],absolute[3])};
    var childPath=new int[path.Length+1];
    Array.Copy(path,childPath,path.Length);
    childPath[path.Length]=i;
    ReadStaticVectorGroup(api,child,pageBounds,childPath,leaves,allGroupLinkers);
   }
  }

  static Dictionary<string,object> NamedVectorImage(VectorCreateApi api,IntPtr control,bool rasterOnly,out string name,out string linker){
   var raw=api.Pictures.Raw;
   var members=NativeCurrentTemplateControlOperations.ContainedImageMembers(raw.Engine,raw.Context,raw.Project,control);
   NativeMemory.Require(members.Count==1&&members[0].Full==control&&members[0].State==IntPtr.Zero&&members[0].Frame==IntPtr.Zero,
    "This source requires exactly the Bitmap's own display-image member.");
   IntPtr image=members[0].Image;
   raw.Table(image,"PictureImage");
   NativeMemory.Require(Marshal.ReadByte(image,8)==1,"Source Bitmap must reference an existing project picture by name.");
   name=CString(NativeMemory.Add(image,12),4096);
   IntPtr picture=api.Pictures.Picture(name);
   var result=Record(raw,picture);
   linker="";
   if(rasterOnly){
    NativeMemory.Require(Number(result["vector_mode_raw_uint32"])==0&&((IList)Map(result["frames"])["rows"]).Count==0&&
     Number(Map(result["cached_bytes"])["length"])>0,
     "A Bitmap in a mixed vector selection must point to a loaded raster picture.");
    linker=api.Pictures.References.Path(picture);
   }
   return result;
  }

  static int NormalizeVectorCoordinate(int value,int origin,int end){
   long extent=(long)end-origin;
   // Win32 MulDiv rounds to the nearest integer. Selection offsets are nonnegative.
   return (int)((((long)value-origin)*10000L+extent/2L)/extent);
  }

  static Dictionary<string,object> VectorStaticSelectionSource(VectorCreateApi api,Dictionary<string,object> source,
   IntPtr page,IntPtr doc,int id,string pageName,out List<IntPtr> controls){
   var raw=api.Pictures.Raw;
   var selectors=source["controls"] as IList;
   var roots=raw.Common.TopControls(doc);
   NativeMemory.Require(selectors!=null&&selectors.Count>0&&selectors.Count<=roots.Count,
    "Static vector selection requires current, distinct top-level controls.");
   var ordered=new SortedDictionary<int,Dictionary<string,object>>();
   foreach(object value in selectors){
    var selector=Map(value);
    var path=selector["control_path"] as IList;
    NativeMemory.Require(path!=null&&path.Count==1,"Static vector selection requires exact top-level control paths.");
    int index=Number(path[0]);
    NativeMemory.Require(index>=0&&index<roots.Count&&!ordered.ContainsKey(index),
     "Static vector selection has a duplicate or missing top-level control.");
    ordered.Add(index,selector);
   }
   controls=new List<IntPtr>(ordered.Count);
   foreach(int index in ordered.Keys)controls.Add(roots[index]);
   var trees=NativeCurrentTemplateControlOperations.RawPictureDrawRoots(raw.Engine,raw.Context,raw.Project,controls,doc);
   var rows=new List<Dictionary<string,object>>(ordered.Count);
   var leaves=new List<Dictionary<string,object>>(ordered.Count);
   var groupLinkers=new List<string>();
   int i=0;
   foreach(var item in ordered){
    var selector=item.Value;
    IntPtr control=controls[i];
    var tree=trees[i++];
    string type=NativePageControlPreparation.Text(selector,"class"),name=NativePageControlPreparation.Text(selector,"control_name");
    int typeId=StaticVectorType(type);
    NativeMemory.Require(Convert.ToString(tree["class"])==type&&Number(tree["type_id"])==typeId&&Convert.ToString(tree["name"])==name,
     "Static vector selection path resolved to another class or name.");
    var path=new[]{item.Key};
    if(IsVectorGroup(typeId)){
     int start=groupLinkers.Count;
     ReadStaticVectorGroup(api,tree,(int[])tree["rectangle"],path,leaves,groupLinkers);
     rows.Add(new Dictionary<string,object>{{"control_path",path},{"control_class",type},
      {"control_name",name},{"draw_tree",tree},{"control_linker",groupLinkers[start]}});
     continue;
    }
    var row=new Dictionary<string,object>{{"control_path",path},{"control_class",type},
     {"control_name",name},{"draw_tree",tree},{"shape_style",api.StaticShapePayload(control,typeId)},
     {"control_linker",api.Pictures.References.Path(NativeOpaqueDrawState.ControlObject(control))}};
    if(typeId==0x5009){
     string imageName,pictureLinker;
     row["source_picture"]=NamedVectorImage(api,control,true,out imageName,out pictureLinker);
     row["source_image_name"]=imageName;
     row["source_picture_linker"]=pictureLinker;
    }
    rows.Add(row);
    leaves.Add(row);
   }
   NativeMemory.Require(leaves.Count>=2,"Static vector selection requires at least two leaf shapes.");
   if(groupLinkers.Count>0)
    NativeMemory.Require(!leaves.Exists(row=>row.ContainsKey("source_picture")),"Original grouped vector selection covers static rectangles and lines.");
   var canvas=new int[]{Int32.MaxValue,Int32.MaxValue,Int32.MinValue,Int32.MinValue};
   foreach(var row in leaves){
    var ends=VectorPageGeometry(row);
    bool line=Convert.ToString(row["control_class"])=="CDrawLine";
    NativeMemory.Require(line?(ends[0]!=ends[2]||ends[1]!=ends[3]):(ends[0]<ends[2]&&ends[1]<ends[3]),
     "Static vector selection includes a degenerate leaf in page coordinates.");
    canvas[0]=Math.Min(canvas[0],Math.Min(ends[0],ends[2]));
    canvas[1]=Math.Min(canvas[1],Math.Min(ends[1],ends[3]));
    canvas[2]=Math.Max(canvas[2],Math.Max(ends[0],ends[2]));
    canvas[3]=Math.Max(canvas[3],Math.Max(ends[1],ends[3]));
   }
   long width=(long)canvas[2]-canvas[0],height=(long)canvas[3]-canvas[1];
   NativeMemory.Require(canvas[0]!=Int32.MinValue&&canvas[1]!=Int32.MinValue&&width>0&&height>0&&
    width<=Int32.MaxValue&&height<=Int32.MaxValue,"Original static vector selection requires positive width and height.");
   foreach(var row in leaves){
    var ends=VectorPageGeometry(row);
    var projected=new[]{
     NormalizeVectorCoordinate(ends[0],canvas[0],canvas[2]),NormalizeVectorCoordinate(ends[1],canvas[1],canvas[3]),
     NormalizeVectorCoordinate(ends[2],canvas[0],canvas[2]),NormalizeVectorCoordinate(ends[3],canvas[1],canvas[3])};
    bool line=Convert.ToString(row["control_class"])=="CDrawLine";
    NativeMemory.Require(line?(projected[0]!=projected[2]||projected[1]!=projected[3]):
     (projected[0]<projected[2]&&projected[1]<projected[3]),"A selected shape collapses at original vector precision.");
    row["normalized_geometry"]=projected;
   }
   var result=new Dictionary<string,object>{{"source_kind",StaticSelectionVectorSource},{"page_id",id},{"page_name",pageName},
    {"page",NativeMemory.Hex(page)},{"document",NativeMemory.Hex(doc)},{"controls",rows},{"canvas_bounds",canvas},
    {"source_page_common",VectorSourcePageCommon(raw,doc,id)}};
   if(groupLinkers.Count>0){
    result["expanded_group_leaf_controls"]=leaves;
    result["group_member_linkers"]=groupLinkers;
   }
   return result;
  }
  static int[] VectorPageGeometry(Dictionary<string,object> row){
   object geometry;
   return (int[])(row.TryGetValue("page_geometry",out geometry)?geometry:Map(row["draw_tree"])["rectangle"]);
  }

  static Dictionary<string,object> VectorCreateSource(VectorCreateApi api,Dictionary<string,object> action,out List<IntPtr> controls,out IntPtr doc,out string imageName){
   var raw=api.Pictures.Raw;var source=Map(action["source"]);string sourceKind=NativePageControlPreparation.Text(source,"kind");
   bool multiple=sourceKind==StaticSelectionVectorSource;
   string sourceClass=multiple?"":NativePageControlPreparation.Text(source,"class");
   bool rectangle=sourceKind==RectangleVectorSource,line=sourceKind==LineVectorSource;
   NativeMemory.Require(multiple||(rectangle&&sourceClass=="CDrawRect")||(line&&sourceClass=="CDrawLine")||
    (sourceKind=="current-bitmap-control"&&sourceClass=="CDrawBitmap"),
    "Vector source requires one named Bitmap or current static shapes on the same page.");
   int id=NativePageControlPreparation.Number(source,"page_id");
   string pageName=NativePageControlPreparation.Text(source,"page_name");
   IntPtr header=NativeMemory.Add(raw.Context.WindowManager,12);
   byte[] oldHeader=NativeMemory.Bytes(header,8);
   IntPtr head=NativeMemory.Ptr(header,0);
   int pageCount=NativeMemory.I32(header,4);
   NativeMemory.Require(head!=IntPtr.Zero&&pageCount>=0&&pageCount<=Int32.MaxValue/4,"Vector source raw page map differs.");
   IntPtr node=NativeMemory.Ptr(head,0),previous=head,page=IntPtr.Zero;
   var nodes=new HashSet<uint>();var ids=new HashSet<int>();
   for(int i=0;i<pageCount;i++){
    NativeMemory.Require(node!=IntPtr.Zero&&node!=head&&nodes.Add(NativeMemory.U(node))&&NativeMemory.Ptr(node,4)==previous,"Vector source raw page map links/cycle differ.");
    IntPtr candidate=NativeMemory.Ptr(node,12);
    NativeMemory.Require(candidate!=IntPtr.Zero&&NativeMemory.Ptr(candidate,0)==raw.Engine.Address(0xDED294),"Vector source raw page class differs.");
    int currentId=NativeMemory.I32(candidate,16);
    NativeMemory.Require(ids.Add(currentId),"Vector source raw page IDs repeat.");
    if(currentId==id)page=candidate;
    previous=node;node=NativeMemory.Ptr(node,0);
   }
   NativeMemory.Require(node==head&&NativeMemory.Ptr(head,4)==previous&&Hex(oldHeader)==Hex(NativeMemory.Bytes(header,8))&&page!=IntPtr.Zero,"Vector source page map changed or target is absent.");
   NativeMemory.Require(CString(NativeMemory.Add(page,12),4096)==pageName,"Vector source page name differs.");
   doc=NativeMemory.Ptr(page,20);
   NativeMemory.Require(doc!=IntPtr.Zero&&NativeMemory.Ptr(doc,0)==raw.Engine.Address(0xDC4D94)&&NativeMemory.I32(doc,NativeLayout.Offset("document.archive_id"))==id,"Vector source document must already be loaded; no lazy load is performed.");
   if(multiple){
    imageName="";
    return VectorStaticSelectionSource(api,source,page,doc,id,pageName,out controls);
   }
   string name=NativePageControlPreparation.Text(source,"control_name");
   IntPtr control;
   if(rectangle||line){
    var path=new List<int>();
    foreach(object value in (IEnumerable)source["control_path"])path.Add(Number(value));
    var roots=raw.Common.TopControls(doc);
    NativeMemory.Require(path.Count==1&&path[0]>=0&&path[0]<roots.Count,
     "Vector shape requires an exact current top-level control path.");
    control=roots[path[0]];
    var tree=NativeCurrentTemplateControlOperations.RawPictureDrawTree(raw.Engine,raw.Context,raw.Project,control);
    NativeMemory.Require(Convert.ToString(tree["class"])==sourceClass&&Number(tree["type_id"])==(line?0x5002:0x5004)&&
     Convert.ToString(tree["name"])==name&&NativeMemory.Ptr(control,NativeLayout.Offset("control.owner_document"))==doc,
     "Vector shape source name, class or page owner differs.");
    if(line)LineVectorBounds(NativePageControlAbi.Rectangle(control));
    imageName="";
    controls=new List<IntPtr>{control};
    return new Dictionary<string,object>{{"page_id",id},{"page_name",pageName},{"page",NativeMemory.Hex(page)},
     {"document",NativeMemory.Hex(doc)},{"control",NativeMemory.Hex(control)},{"control_path",path},
     {"control_name",name},{"control_class",sourceClass},{"draw_tree",tree},
     {line?"line_style":"rectangle_style",api.StaticShapePayload(control,line?0x5002:0x5004)},
     {"control_linker",api.Pictures.References.Path(NativeOpaqueDrawState.ControlObject(control))},
     {"source_page_common",VectorSourcePageCommon(raw,doc,id)}};
   }
   control=IntPtr.Zero;foreach(var row in NativeUsableEditPermit.CurrentDrawControls(raw.Engine,doc,id))if(Convert.ToString(row["name"])==name&&Convert.ToString(row["rtti"])==".?AVCDrawBitmap@@"){NativeMemory.Require(control==IntPtr.Zero,"Vector source Bitmap name is ambiguous.");control=new IntPtr(unchecked((int)UInt32.Parse(Convert.ToString(row["complete"]).Substring(2),NumberStyles.HexNumber,CultureInfo.InvariantCulture)));}NativeMemory.Require(control!=IntPtr.Zero&&NativeMemory.I32(control,12)==0x5009,"Vector source Bitmap is absent or has another actual native type.");
   string ignoredLinker;
   var sourcePicture=NamedVectorImage(api,control,false,out imageName,out ignoredLinker);
   controls=new List<IntPtr>{control};
   return new Dictionary<string,object>{{"page_id",id},{"page_name",pageName},{"page",NativeMemory.Hex(page)},{"document",NativeMemory.Hex(doc)},{"control",NativeMemory.Hex(control)},{"control_name",name},{"control_class","CDrawBitmap"},{"draw_tree",NativeCurrentTemplateControlOperations.RawPictureDrawTree(raw.Engine,raw.Context,raw.Project,control)},{"source_image_name",imageName},{"source_picture",sourcePicture},{"source_page_common",VectorSourcePageCommon(raw,doc,id)}};
  }
  static Dictionary<string,object> VectorSourcePageCommon(Api api,IntPtr doc,int id){var attrs=new int[17];for(int i=0;i<attrs.Length;i++)attrs[i]=NativeMemory.I32(doc,NativeLayout.Offset("document.attributes")+4*i);return new Dictionary<string,object>{{"document",NativeMemory.Hex(doc)},{"modified",NativeMemory.I32(doc,NativeLayout.Offset("document.modified"))},{"compile_raw",NativeMemory.I32(doc,NativeLayout.Offset("document.compile_valid"))},{"attributes",attrs},{"controls",NativeUsableEditPermit.CurrentDrawControls(api.Engine,doc,id)}};}
  static Dictionary<string,object> VectorCreateCapture(VectorCreateApi api,Dictionary<string,object> action,out List<IntPtr> controls,out IntPtr doc,out string imageName){api.Check();var target=Map(action["target"]);NativeMemory.Require(NativePageControlPreparation.Kind(action)==VectorCreateKind&&Number(target["module_id"])==11,"Vector resource action kind/module differs.");string name=NativePageControlPreparation.Text(target,"name");NativePageControlPreparation.Name(name);var catalog=ReadRaw(api.Pictures.Raw.Engine,api.Pictures.Raw.Context,api.Pictures.Raw.Project);foreach(object value in(IEnumerable)catalog["ordered_names"])NativeMemory.Require(!Convert.ToString(value).Equals(name,StringComparison.OrdinalIgnoreCase),"Vector resource destination already exists.");var source=VectorCreateSource(api,action,out controls,out doc,out imageName);
   var graph=NativeReferencedPageEditing.Graph(api.Pictures.References);
   var linkers=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
   if(source.ContainsKey("source_kind")){
    foreach(object value in (IEnumerable)source["controls"]){
     var row=Map(value);
     if(IsVectorGroup(StaticVectorType(Convert.ToString(row["control_class"]))))continue;
     string linker=Convert.ToString(row["control_linker"]);
     NativeMemory.Require(!String.IsNullOrEmpty(linker)&&!linkers.ContainsKey(linker),"Vector selection has missing or duplicate native owning paths.");
     object targetLinker;
     linkers.Add(linker,row.TryGetValue("source_picture_linker",out targetLinker)?Convert.ToString(targetLinker):"");
    }
    object groupMembers;
    if(source.TryGetValue("group_member_linkers",out groupMembers)){
     foreach(string linker in (IEnumerable)groupMembers){
      NativeMemory.Require(!String.IsNullOrEmpty(linker)&&!linkers.ContainsKey(linker),
       "Vector group descendant has a missing or duplicate native owning path.");
      linkers.Add(linker,"");
     }
    }
   }else if(source.ContainsKey("control_linker")){
    string linker=Convert.ToString(source["control_linker"]);
    NativeMemory.Require(!String.IsNullOrEmpty(linker),"Vector shape has no exact native owning path.");
    linkers.Add(linker,"");
   }
   if(linkers.Count>0){
    foreach(object value in (IEnumerable)graph["edges"]){
     var edge=Map(value);
     string from=Convert.ToString(edge["source"]),to=Convert.ToString(edge["target"]);
     foreach(var linker in linkers){
      if(!String.IsNullOrEmpty(linker.Value)&&from.Equals(linker.Key,StringComparison.OrdinalIgnoreCase)&&
       to.Equals(linker.Value,StringComparison.OrdinalIgnoreCase))continue;
      NativeMemory.Require(!VectorGraphPath(from,linker.Key)&&!VectorGraphPath(to,linker.Key),
       "Vector shape participates in a registered reference outside its own display image.");
     }
    }
   }
   return new Dictionary<string,object>{{"abi_profile_sha256",VectorCreateProfileSha},{"kind",VectorCreateKind},{"resource_catalog",catalog},{"source",source},{"reference_graph",graph},{"native_image_registration_mode_raw_int32",NativeMemory.I32(api.Pictures.Raw.Engine.Address(0xFBFF30),0)},{"no_native_serializer_called_by_inspection",true},{"complete_serialization_preimage_claimed",false}};}
  static bool VectorGraphPath(string value,string linker){
   return value.Equals(linker,StringComparison.OrdinalIgnoreCase)||value.StartsWith(linker+".",StringComparison.OrdinalIgnoreCase);
  }
  internal static Dictionary<string,object> ReadVectorCreate(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){List<IntPtr> controls;IntPtr doc;string name;return VectorCreateCapture(new VectorCreateApi(e,c,p),action,out controls,out doc,out name);}
  internal static INativePreparedPageControlEdit PrepareVectorCreate(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){return new PreparedVectorCreate(new VectorCreateApi(e,c,p),action);}

  sealed class PreparedVectorCreate:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {
   readonly VectorCreateApi api;readonly Dictionary<string,object> action,before;readonly string destination,referenceName,sourceClass;readonly bool staticShape,line,multiple,flattenGroups;readonly List<IntPtr> sources;readonly List<string> expectedImageNames=new List<string>();readonly IntPtr sourceDoc;
   readonly VectorListCtor listCtor;readonly VectorLoad loadSelection;readonly PV0 listDtor,seekBegin,scopeEnter,scopeLeave,archiveClose,archiveDtor,memoryDtor,markDirty,initializeReference;readonly PVP listAdd,listSerialize,setImageName;readonly PBP imageHash,setName,add;readonly PB0 pictureHash,save;readonly NewNative allocate;readonly PP0 pictureCtor,imageCtor;readonly PV0 imageDtor;readonly PVP pictureAssign;readonly PVI deletePicture,rootDirty;readonly MemCtor memoryCtor;readonly ArcCtor archiveCtor;
   readonly List<NativeStrategyProfile.CString> nativeReferences=new List<NativeStrategyProfile.CString>();
   NativeStrategyProfile.CString nativeName,computedHash;IntPtr list,file,archive,scope,created,detachedImage;bool listMade,fileMade,archiveMade,scopeActive,pictureMade,detachedImageMade,adoptionEntered,adopted,entered,applied,unknown,disposed;Dictionary<string,object> after;string originalShapeHash;
   internal PreparedVectorCreate(VectorCreateApi a,Dictionary<string,object> request){api=a;action=request;NativeMemory.Require(Convert.ToString(action["abi_profile_sha256"])==VectorCreateProfileSha,"Vector creation action ABI differs.");listCtor=api.Bind<VectorListCtor>("ListCtor");listDtor=api.Bind<PV0>("ListDtor");listAdd=api.Bind<PVP>("ListAddTail");listSerialize=api.Bind<PVP>("ListSerialize");seekBegin=api.Bind<PV0>("MemorySeekBegin");loadSelection=api.Bind<VectorLoad>("ImageLoadControlArchive");imageHash=api.Bind<PBP>("ImageHash");initializeReference=api.Bind<PV0>("ImageInitializeNamedReference");setImageName=api.Bind<PVP>("ImageSetReferenceName");pictureHash=api.Bind<PB0>("PictureRecomputeHash");scopeEnter=api.Pictures.Bind<PV0>("ImageStandaloneScopeEnter");scopeLeave=api.Pictures.Bind<PV0>("ImageStandaloneScopeLeave");pictureCtor=api.Pictures.Bind<PP0>("PictureCtor");imageCtor=api.Pictures.Bind<PP0>("ImageCtor");imageDtor=api.Pictures.Bind<PV0>("ImageDtor");pictureAssign=api.Pictures.Bind<PVP>("PictureAssignImage");setName=api.Pictures.Bind<PBP>("PictureSetName");add=api.Pictures.Bind<PBP>("PictureAdd");allocate=api.Pictures.Bind<NewNative>("NativeNew");deletePicture=api.Pictures.Bind<PVI>("PictureDeleteOwned");markDirty=api.Pictures.Bind<PV0>("PictureMarkDirty");save=api.Pictures.Bind<PB0>("PictureSave");memoryCtor=api.Pictures.Bind<MemCtor>("MemoryFileCtor");archiveCtor=api.Pictures.Bind<ArcCtor>("ArchiveCtor");archiveClose=api.Pictures.Bind<PV0>("ArchiveClose");archiveDtor=api.Pictures.Bind<PV0>("ArchiveDtor");memoryDtor=api.Pictures.Bind<PV0>("MemoryFileDtor");rootDirty=api.Pictures.Raw.Common.Shared.Bind<PVI>("RootSetModified");try{before=VectorCreateCapture(api,action,out sources,out sourceDoc,out referenceName);NativePageControlPreparation.Before(action,before);destination=NativePageControlPreparation.Text(Map(action["target"]),"name");var desired=Map(action["after"]);
   var actualSource=Map(before["source"]);
   multiple=actualSource.ContainsKey("source_kind");
   flattenGroups=actualSource.ContainsKey("expanded_group_leaf_controls");
   sourceClass=multiple?"":Convert.ToString(actualSource["control_class"]);
   line=sourceClass=="CDrawLine";
   staticShape=multiple||line||sourceClass=="CDrawRect";
   if(multiple){
    foreach(var item in (List<Dictionary<string,object>>)actualSource["controls"]){
     object name;
     if(item.TryGetValue("source_image_name",out name))expectedImageNames.Add((string)name);
    }
   }else if(!staticShape)expectedImageNames.Add(referenceName);
   foreach(string key in new[]{"allow_original_selection_vector_creation","allow_original_hash_recompute"})
    NativeMemory.Require(desired.ContainsKey(key)&&Object.Equals(desired[key],true),"Vector creation requires explicit original private conversion effect: "+key);
   NativeMemory.Require(desired.ContainsKey("allow_private_animation_removal")&&
    Object.Equals(desired["allow_private_animation_removal"],!staticShape),"Vector expected private animation removal differs.");
   if(flattenGroups)
    NativeMemory.Require(desired.ContainsKey("allow_original_group_flattening")&&Object.Equals(desired["allow_original_group_flattening"],true),
     "Original vector conversion will flatten the selected groups in the new resource.");
   if(multiple&&expectedImageNames.Count>0){
    NativeMemory.Require(desired.Count==4&&desired.ContainsKey("expected_reference_names")&&desired["expected_reference_names"] is IList,
     "Mixed vector selection requires expected_reference_names in source page order.");
    NativePageControlPreparation.Same(expectedImageNames,desired["expected_reference_names"],"Mixed vector source image names differ.");
   }else{
    NativeMemory.Require(desired.Count==(flattenGroups?6:5)&&desired["expected_reference_name"] is string&&
     Convert.ToString(desired["expected_reference_name"])==referenceName&&Number(desired["expected_reference_count"])==expectedImageNames.Count,
     "Vector expected source image/reference count differs.");
   }
   NativeMemory.Require(Number(before["native_image_registration_mode_raw_int32"])==0,"Vector construction requires exact original registration mode0 before its own scope.");
   nativeName=new NativeStrategyProfile.CString(api.Pictures.Raw.Common.Shared,destination);
   foreach(string image in expectedImageNames)nativeReferences.Add(new NativeStrategyProfile.CString(api.Pictures.Raw.Common.Shared,image));
   if(expectedImageNames.Count>0)computedHash=new NativeStrategyProfile.CString(api.Pictures.Raw.Common.Shared,"");
   list=Marshal.AllocHGlobal(28);file=Marshal.AllocHGlobal(44);archive=Marshal.AllocHGlobal(72);scope=Marshal.AllocHGlobal(8);detachedImage=Marshal.AllocHGlobal(0xA4);}catch{Dispose();throw;}}
   public void ValidatePersistence(NativeUsableEditPermit.Plan plan){if(plan.Commit)plan.RequireModulePersistence(action,11);}
   public void ValidateBefore(){NativeMemory.Require(!disposed&&!entered,"Vector creation already entered/disposed.");List<IntPtr> selected;IntPtr d;string n;NativePageControlPreparation.Same(before,VectorCreateCapture(api,action,out selected,out d,out n),"Vector creation resource/source/reference preimage changed before Claim.");NativeMemory.Require(d==sourceDoc&&n==referenceName&&selected.Count==sources.Count,"Vector source identity changed.");for(int i=0;i<sources.Count;i++)NativeMemory.Require(selected[i]==sources[i],"Vector source identity or order changed.");}
   int Mode(){return NativeMemory.I32(api.Pictures.Raw.Engine.Address(0xFBFF30),0);}
   void Call(string phase,Action call){api.Check();NativeOperationTrace.BeforeMutation(phase);unknown=true;call();unknown=false;}
   void CloseArchive(){if(!archiveMade)return;Call("vector-original-archive-close",()=>archiveClose(archive));archiveMade=false;Call("vector-original-archive-dtor",()=>archiveDtor(archive));}
   void LeaveScope(){if(!scopeActive||unknown)return;Call("vector-original-scope-leave",()=>scopeLeave(scope));NativeMemory.Require(Mode()==0&&NativeMemory.I32(scope,0)==0&&Marshal.ReadByte(scope,4)==1,"Vector original scope did not normally restore mode0.");scopeActive=false;}
   void PreserveExisting(){NativeMemory.Require(Mode()==0,"Original private image operation did not restore registration mode0.");var raw=api.Pictures.Raw;NativePageControlPreparation.Same(before["resource_catalog"],ReadRaw(raw.Engine,raw.Context,raw.Project),"Private vector construction unexpectedly altered an existing picture/catalog.");NativePageControlPreparation.Same(before["reference_graph"],NativeReferencedPageEditing.Graph(api.Pictures.References),"Private vector construction changed the registered graph.");VerifySourceUnchanged();}
   void VerifySourceUnchanged(){
    List<IntPtr> selected;IntPtr doc;string name;
    NativePageControlPreparation.Same(before["source"],VectorCreateSource(api,action,out selected,out doc,out name),
     "Original vector conversion changed source controls or their page.");
   }
   sealed class VectorBitmapCopy {
    internal readonly IntPtr Image;
    internal readonly Dictionary<string,object> SourcePicture;
    internal VectorBitmapCopy(IntPtr image,Dictionary<string,object> sourcePicture){Image=image;SourcePicture=sourcePicture;}
   }
   static void AddVectorSourceTree(HashSet<IntPtr> seen,Dictionary<string,object> tree){
    seen.Add(VectorShapePointer(tree));
    foreach(object child in (IEnumerable)tree["children"])AddVectorSourceTree(seen,Map(child));
   }
   List<VectorBitmapCopy> VerifyStaticShapeRoot(IntPtr root,bool imagesNamed){
    var raw=api.Pictures.Raw;
    var tree=NativeCurrentTemplateControlOperations.RawPictureDrawTree(raw.Engine,raw.Context,raw.Project,root);
    var children=new List<Dictionary<string,object>>();
    foreach(object item in (IEnumerable)tree["children"])children.Add(Map(item));
    var copies=new List<VectorBitmapCopy>();
    if(multiple){
     var selectionBefore=Map(before["source"]);
     var original=(List<Dictionary<string,object>>)selectionBefore[flattenGroups?"expanded_group_leaf_controls":"controls"];
     NativeMemory.Require(Convert.ToString(tree["class"])=="CDrawCell"&&children.Count==original.Count,
      "Original static vector selection did not return all shapes in one independent image.");
     var members=NativeCurrentTemplateControlOperations.ContainedImageMembers(raw.Engine,raw.Context,raw.Project,root);
     NativeMemory.Require(members.Count==expectedImageNames.Count,"Original static vector selection Bitmap carrier count differs.");
     NativePageControlPreparation.Same(selectionBefore["canvas_bounds"],tree["rectangle"],
      "Original static vector selection canvas differs from its source envelope.");
     var used=new HashSet<IntPtr>(sources);
     if(flattenGroups){
      foreach(object selected in (IEnumerable)selectionBefore["controls"])
       AddVectorSourceTree(used,Map(Map(selected)["draw_tree"]));
      NativeMemory.Require(used.Add(root),"Original group conversion reused a source object as its vector root.");
     }
     for(int i=0;i<children.Count;i++){
      var selectionChild=children[i];
      var expected=original[i];
      string type=Convert.ToString(expected["control_class"]);
      int typeId=StaticVectorType(type);
      IntPtr selectionClone=VectorShapePointer(selectionChild);
      NativeMemory.Require(Convert.ToString(selectionChild["class"])==type&&Number(selectionChild["type_id"])==typeId&&
       Object.Equals(selectionChild["name"],expected["control_name"])&&used.Add(selectionClone)&&
       !((IEnumerable)selectionChild["children"]).GetEnumerator().MoveNext(),
       "Original static vector selection changed the child order, class, name or independent ownership.");
      NativePageControlPreparation.Same(expected["normalized_geometry"],selectionChild["rectangle"],
       "Original static vector selection changed a shape's directed geometry.");
      NativePageControlPreparation.Same(expected["shape_style"],api.StaticShapePayload(selectionClone,typeId),
       "Original static vector selection changed a shape's pen or brush.");
      if(typeId==0x5009){
       var member=members[copies.Count];
       NativeMemory.Require(member.Full==selectionClone&&member.Path.Length==2&&member.Path[0]==0&&member.Path[1]==i&&
        member.State==IntPtr.Zero&&member.Frame==IntPtr.Zero,"Original static vector selection Bitmap owner or order differs.");
       raw.Table(member.Image,"PictureImage");
       NativeMemory.Require(Marshal.ReadByte(member.Image,8)==(imagesNamed?1:0),"Mixed vector Bitmap image storage mode differs.");
       if(imagesNamed)NativeMemory.Require(CString(NativeMemory.Add(member.Image,12),4096)==Convert.ToString(expected["source_image_name"]),
        "Mixed vector Bitmap does not retain its corresponding original image name.");
       copies.Add(new VectorBitmapCopy(member.Image,Map(expected["source_picture"])));
      }
     }
     return copies;
    }
    NativeMemory.Require(Convert.ToString(tree["class"])=="CDrawCell"&&children.Count==1&&
     Convert.ToString(children[0]["class"])==sourceClass&&Number(children[0]["type_id"])==(line?0x5002:0x5004),
     "Original vector did not construct one CDrawCell with exactly one expected native shape.");
    var child=children[0];
    IntPtr clone=VectorShapePointer(child);
    NativeMemory.Require(clone!=sources[0]&&!((IEnumerable)child["children"]).GetEnumerator().MoveNext()&&
     NativeCurrentTemplateControlOperations.ContainedImageMembers(raw.Engine,raw.Context,raw.Project,root).Count==0,
     "Original vector does not have one independently owned shape with no contained images.");
    var sourceBefore=Map(before["source"]);
    NativePageControlPreparation.Same(sourceBefore[line?"line_style":"rectangle_style"],api.StaticShapePayload(clone,line?0x5002:0x5004),
     "Original vector changed the source pen or brush.");
    if(line){
     var ends=(int[])Map(sourceBefore["draw_tree"])["rectangle"];
     int[] canvas=LineVectorBounds(ends);
     int x1=ends[0]==canvas[0]?0:10000,y1=ends[1]==canvas[1]?0:10000;
     NativePageControlPreparation.Same(canvas,tree["rectangle"],"Original line vector canvas differs from the endpoint bounds.");
     NativePageControlPreparation.Same(new int[]{x1,y1,10000-x1,10000-y1},child["rectangle"],
      "Original line vector changed the directed normalized endpoints.");
    }
    return copies;
   }
   void RestoreNamedVectorImage(IntPtr childImage,Dictionary<string,object> sourcePicture,NativeStrategyProfile.CString name){
    NativeMemory.Require(Marshal.ReadByte(childImage,8)==0,"Original deep frame clone did not produce the expected embedded private image.");
    bool hashed=false;
    Call("vector-original-private-member-hash",()=>hashed=imageHash(childImage,computedHash.Storage));
    NativeMemory.Require(hashed&&ReadCurrentHash(computedHash.Storage)==Convert.ToString(sourcePicture["content_hash"]),
     "Private embedded image differs from its own existing source resource.");
    NativeMemory.Require(api.Pictures.Raw.Engine.Virtual(childImage,21)==api.Pictures.Raw.Engine.Address(0x26337)&&
     api.Pictures.Raw.Engine.Virtual(childImage,9)==api.Pictures.Raw.Engine.Address(0x48545)&&
     api.Pictures.Raw.Engine.Virtual(childImage,17)==api.Pictures.Raw.Engine.Address(0x97BE),
     "Private image initializer/release/name interface differs.");
    Call("vector-original-private-named-reference-initializer21",()=>initializeReference(childImage));
    NativeMemory.Require(Marshal.ReadByte(childImage,8)==1&&NativeMemory.I32(childImage,0x14)==0&&
     NativeMemory.I32(childImage,0x18)==0&&NativeMemory.I32(childImage,0x1C)==0xC0C0C0&&NativeMemory.I32(childImage,0x20)==0&&
     NativeMemory.I32(childImage,0x24)==0&&NativeMemory.I32(childImage,0x28)==0&&NativeMemory.I32(childImage,0x78)==0&&NativeMemory.I32(childImage,0x7C)==0,
     "Original private named-reference initialization did not return its exact native shape.");
    PreserveExisting();
    Call("vector-original-private-reference-name",()=>setImageName(childImage,name.Storage));
    string reference=Convert.ToString(sourcePicture["name"]);
    NativeMemory.Require(CString(NativeMemory.Add(childImage,12),4096)==reference&&api.Pictures.Picture(reference)!=IntPtr.Zero,
     "Original private image-name setter did not retain its actual existing resource.");
    PreserveExisting();
   }
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);entered=true;
    // This list owns its native nodes, and only borrows the already owned source object.
    Call("vector-original-borrowed-list-ctor",()=>{NativeMemory.Require(listCtor(list,10)==list&&NativeMemory.Ptr(list,0)==api.Pictures.Raw.Engine.Address(0xD3FD70)&&NativeMemory.I32(list,12)==0&&NativeMemory.Ptr(list,4)==IntPtr.Zero&&NativeMemory.Ptr(list,8)==IntPtr.Zero,"Original typed CObList ctor/table/empty state differs.");listMade=true;});
    Call("vector-original-borrowed-list-add",()=>{
     foreach(IntPtr source in sources)listAdd(list,source);
     NativeMemory.Require(NativeMemory.I32(list,12)==sources.Count,"Original borrowed selection count differs.");
    });
    Call("vector-original-memory-file-ctor",()=>{NativeMemory.Require(memoryCtor(file,1024)==file,"Original memory-file ctor returned another pointer.");fileMade=true;});Call("vector-original-store-archive-ctor",()=>{NativeMemory.Require(archiveCtor(archive,file,0,0x400000,IntPtr.Zero)==archive,"Original STORE archive ctor returned another pointer.");archiveMade=true;});NativeMemory.Require(Mode()==0,"Source selection STORE must retain native named-image references at mode0.");Call("vector-original-borrowed-selection-serialize",()=>listSerialize(list,archive));CloseArchive();Call("vector-original-memory-seek-begin",()=>seekBegin(file));PreserveExisting();
    Call("vector-original-picture-allocation",()=>{created=allocate(0xD0);NativeMemory.Require(created!=IntPtr.Zero,"Original CPicture allocation failed.");});Call("vector-original-picture-ctor",()=>{NativeMemory.Require(pictureCtor(created)==created,"Original CPicture ctor returned another pointer.");api.Pictures.Raw.Table(created,"Picture");api.Pictures.Raw.Table(NativeMemory.Add(created,0x18),"PictureImage");pictureMade=true;});Call("vector-original-detached-image-ctor",()=>{NativeMemory.Require(imageCtor(detachedImage)==detachedImage,"Original detached image ctor returned another object.");api.Pictures.Raw.Table(detachedImage,"PictureImage");detachedImageMade=true;});IntPtr image=detachedImage;
    Call("vector-original-load-scope-enter",()=>scopeEnter(scope));scopeActive=true;NativeMemory.Require(Mode()==1&&NativeMemory.I32(scope,0)==0&&Marshal.ReadByte(scope,4)==0,"Original vector scope did not capture0/enter1.");Call("vector-original-load-archive-ctor",()=>{NativeMemory.Require(archiveCtor(archive,file,1,0x400000,IntPtr.Zero)==archive,"Original LOAD archive ctor returned another pointer.");archiveMade=true;});int loaded=0;Call("vector-original-image-from-selection-archive",()=>loaded=loadSelection(image,archive));CloseArchive();LeaveScope();NativeMemory.Require(loaded==1&&Marshal.ReadByte(image,8)==0&&NativeMemory.I32(image,0x14)==1,"Original selected-object image constructor did not yield one embedded vector image.");PreserveExisting();
    var detachedRoots=PictureVectorRoots(api.Pictures.Raw,image);NativeMemory.Require(detachedRoots.Count==1,"Original detached selection image has another frame shape.");bool initialName=false;Call("vector-original-preassign-picture-name",()=>initialName=setName(created,nativeName.Storage));NativeMemory.Require(initialName,"Original new vector name refused before assignment.");Call("vector-original-picture-assign-owned-image",()=>pictureAssign(created,detachedImage));image=NativeMemory.Add(created,0x18);api.Pictures.Raw.Table(image,"PictureImage");NativeMemory.Require(Marshal.ReadByte(image,8)==0&&NativeMemory.I32(image,0x14)==1,"Original picture image assignment did not preserve the embedded vector.");PreserveExisting();var roots=PictureVectorRoots(api.Pictures.Raw,image);NativeMemory.Require(roots.Count==1&&roots[0]!=detachedRoots[0],"Original vector assignment did not deep-own an independent root.");if(staticShape){
     var copies=VerifyStaticShapeRoot(roots[0],false);
     for(int i=0;i<copies.Count;i++)RestoreNamedVectorImage(copies[i].Image,copies[i].SourcePicture,nativeReferences[i]);
     if(copies.Count>0)VerifyStaticShapeRoot(roots[0],true);
    }else{
     var members=NativeCurrentTemplateControlOperations.ContainedImageMembers(api.Pictures.Raw.Engine,
      api.Pictures.Raw.Context,api.Pictures.Raw.Project,roots[0]);
     NativeMemory.Require(members.Count==1&&NativeMemory.I32(members[0].Full,12)==0x5009&&
      members[0].State==IntPtr.Zero&&members[0].Frame==IntPtr.Zero&&members[0].Full!=sources[0],
      "Original vector conversion did not create one independent Bitmap display carrier.");
     RestoreNamedVectorImage(members[0].Image,Map(Map(before["source"])["source_picture"]),nativeReferences[0]);
    }
    bool named=false,rehashed=false;Call("vector-original-picture-name",()=>named=setName(created,nativeName.Storage));NativeMemory.Require(named,"Original new vector picture name refused.");Call("vector-original-new-picture-hash",()=>rehashed=pictureHash(created));NativeMemory.Require(rehashed,"Original new vector picture hash refused.");PreserveExisting();
    if(staticShape){
     originalShapeHash=Convert.ToString(Record(api.Pictures.Raw,created)["content_hash"]);
     NativeMemory.Require(!String.IsNullOrEmpty(originalShapeHash),"Original shape vector has no native picture signature.");
    }
    // No ImageAssign follows reference restoration: deep copy deliberately expands nested named images.
    // The preceding original PictureAssign is necessary: C68410 uses the active document for its private children,
    // while the original image frame STORE/LOAD copy gives the final resource a coherent root/child owner context.
    Call("vector-original-root-dirty",()=>rootDirty(api.Pictures.Raw.Common.Shared.RootDoc(),1));Marshal.WriteInt32(api.Pictures.Raw.Common.Shared.RootDoc(),NativeLayout.Offset("document.compile_valid"),0);bool accepted=false;adoptionEntered=true;Call("vector-original-picture-adopt",()=>accepted=add(api.Pictures.Raw.Preload,created));NativeMemory.Require(accepted&&api.Pictures.Picture(destination)==created,"Original PictureManager did not adopt exactly the new owned vector; no replay/guessed release.");adopted=true;after=ReadRaw(api.Pictures.Raw.Engine,api.Pictures.Raw.Context,api.Pictures.Raw.Project);VerifyCatalog(after);var result=new Dictionary<string,object>{{"ok",true},{"kind",VectorCreateKind},{"created_name",destination},{"created_object",NativeMemory.Hex(created)},{"resource_catalog_after",after},{"contained_reference_name",referenceName},{"contained_reference_count",expectedImageNames.Count},{"source_controls_changed",false},{"source_animation_removed",false},{"private_clone_animation_removed_by_original_worker",!staticShape},{"original_scope_restored",Mode()==0},{"original_register_created_another_resource",false},{"automatic_make_reference_called",false},{"original_private_reference_initializer21_called",expectedImageNames.Count>0},{"existing_hash_index_hit_assumed",false},{"root_save_called",false},{"full_persistence_acceptance_pending",true}};
    if(multiple&&expectedImageNames.Count>0)result["contained_reference_names"]=expectedImageNames;
    if(flattenGroups){
     result["original_groups_flattened_in_created_vector"]=true;
     result["source_group_tree_unchanged"]=true;
    }
    applied=true;lease.CompleteApply(action);return result;
   }
   static string ReadCurrentHash(IntPtr storage){return NativeUsableEditPermit.ReadCurrentCString(storage,128);}
   void VerifyCatalog(Dictionary<string,object> current){var old=RecordMap(Map(before["resource_catalog"]));var now=RecordMap(current);NativeMemory.Require(now.Count==old.Count+1&&now.ContainsKey(destination),"Vector resource catalog count/name differs.");foreach(var item in old){NativeMemory.Require(now.ContainsKey(item.Key),"An original resource disappeared during vector creation.");NativePageControlPreparation.Same(item.Value,now[item.Key],"Vector creation changed another original resource's known raw/model fields.");}var order=new List<object>();foreach(object value in(IEnumerable)Map(before["resource_catalog"])["ordered_names"])order.Add(value);order.Add(destination);NativePageControlPreparation.Same(order,current["ordered_names"],"Vector creation changed original resource order.");NativePageControlPreparation.Same(before["reference_graph"],NativeReferencedPageEditing.Graph(api.Pictures.References),"Vector creation changed registered references beyond the dedicated raw contained relation.");var scan=ContainedScan(api.Pictures);
    var names=new List<string>();
    foreach(ContainedLink link in scan.Links)if(link.Resource==destination)names.Add(link.Name);
    NativePageControlPreparation.Same(expectedImageNames,names,"New vector does not retain exactly its declared contained image-name references.");
    if(staticShape){
     NativeMemory.Require(Convert.ToString(now[destination]["content_hash"])==originalShapeHash,
      "Adopted vector changed the signature computed by the original worker.");
     var roots=PictureVectorRoots(api.Pictures.Raw,NativeMemory.Add(api.Pictures.Picture(destination),0x18));
     NativeMemory.Require(roots.Count==1,"Adopted vector has another frame count.");
     VerifyStaticShapeRoot(roots[0],true);
    }VerifySourceUnchanged();}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(applied&&!unknown&&!disposed,"Only a normally verified vector creation may flush.");lease.BeginFlush(action);lease.RequireModulePersistence(action,11);NativePageControlPreparation.Same(after,ReadRaw(api.Pictures.Raw.Engine,api.Pictures.Raw.Context,api.Pictures.Raw.Project),"Created vector/catalog changed before flush.");bool returned=false;Call("vector-original-module11-save",()=>returned=save(api.Pictures.Raw.Preload));NativeMemory.Require(returned&&Marshal.ReadByte(api.Pictures.Raw.Manager,0x39)==0,"Original vector resource save did not return/clean its module.");var saved=ReadRaw(api.Pictures.Raw.Engine,api.Pictures.Raw.Context,api.Pictures.Raw.Project);VerifyCatalog(saved);RequireExactSavedPictureRecords(after,saved);lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"native_module_save_called",true},{"after",saved},{"root_save_called",false},{"full_persistence_acceptance_pending",true}};}
   public void Dispose(){if(disposed)return;disposed=true;if(unknown||scopeActive){NativeOperationTrace.SetPhase("vector-native-result-or-scope-unknown-no-guessed-cleanup");return;}try{if(archiveMade){archiveMade=false;archiveDtor(archive);}if(fileMade){fileMade=false;memoryDtor(file);}if(listMade){listMade=false;listDtor(list);}if(detachedImageMade){detachedImageMade=false;imageDtor(detachedImage);}if(pictureMade&&!adoptionEntered&&!adopted){pictureMade=false;deletePicture(created,1);created=IntPtr.Zero;}if(computedHash!=null){computedHash.Dispose();computedHash=null;}foreach(var name in nativeReferences)name.Dispose();nativeReferences.Clear();if(nativeName!=null){nativeName.Dispose();nativeName=null;}foreach(IntPtr value in new[]{detachedImage,scope,archive,file,list})if(value!=IntPtr.Zero)Marshal.FreeHGlobal(value);}catch{unknown=true;NativeOperationTrace.SetPhase("vector-native-cleanup-result-unknown-stop-no-further-destructors");throw;}}
  }
 }
}

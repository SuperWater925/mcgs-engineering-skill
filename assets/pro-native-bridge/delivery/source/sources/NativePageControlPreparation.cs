// Parameterized derivatives of the already evidenced engine0050 page/control chains.
// No dispatcher, host invocation, activation or project save is contained here.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
 internal interface INativePreparedPageControlEdit : IDisposable {
  Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease);
  Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease);
 }
 internal interface INativePreparedRelatedPersistence {
  void ValidatePersistence(NativeUsableEditPermit.Plan plan);
 }

 internal static class NativePageControlPreparation {
  internal static Dictionary<string,object> Map(object value){var map=value as Dictionary<string,object>;NativeMemory.Require(map!=null,"Expected page/control object.");return map;}
  internal static string Text(Dictionary<string,object> row,string key){object value;NativeMemory.Require(row.TryGetValue(key,out value)&&value is string,"Expected page/control string: "+key);return (string)value;}
  internal static int Number(Dictionary<string,object> row,string key){object value;NativeMemory.Require(row.TryGetValue(key,out value),"Missing page/control integer: "+key);return NativeEngine.Number(value);}
  internal static string Kind(Dictionary<string,object> action){return Text(action,"kind");}
  internal static string Json(object value){return new JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Serialize(Canonical(value));}
  static object Canonical(object value){var map=value as IDictionary<string,object>;if(map!=null){var result=new SortedDictionary<string,object>(StringComparer.Ordinal);foreach(var pair in map)result.Add(pair.Key,Canonical(pair.Value));return result;}if(value is IEnumerable && !(value is string)){var result=new List<object>();foreach(object item in (IEnumerable)value)result.Add(Canonical(item));return result;}return value;}
  internal static void Same(object expected,object actual,string message){string left=Json(expected),right=Json(actual);if(left!=right)throw NativeEngineeringComparisonEvidence.Mismatch(message,left,right);}
  internal static int[] Rect(Dictionary<string,object> row,string key,int width,int height){object value;NativeMemory.Require(row.TryGetValue(key,out value)&&value is IEnumerable&&!(value is string),"Expected rectangle: "+key);var numbers=new List<int>();foreach(object n in (IEnumerable)value)numbers.Add(NativeEngine.Number(n));NativeMemory.Require(numbers.Count==4&&numbers[0]>=0&&numbers[1]>=0&&numbers[2]>numbers[0]&&numbers[3]>numbers[1]&&numbers[2]<=width&&numbers[3]<=height,"Requested rectangle is outside the actual page.");return numbers.ToArray();}
  internal static void Name(string name){NativeMemory.Require(!String.IsNullOrWhiteSpace(name)&&name.Length<=128&&name.IndexOf('\0')<0&&name.IndexOf('\\')<0&&name.IndexOf('/')<0,"Expected a nonempty bounded native object name.");}
  internal static void Before(Dictionary<string,object> action,object snapshot){object value;NativeMemory.Require(action.TryGetValue("before",out value),"Action requires its full operation preimage.");Same(value,snapshot,"Page/control operation preimage differs; no mutation entered.");}
  internal static Dictionary<string,object> Result(string kind){return new Dictionary<string,object>{{"ok",true},{"kind",kind},{"automatic_retry",false},{"automatic_rollback",false},{"root_save_called",false},{"consolidated_acceptance_pending",true}};}

  internal static INativePreparedPageControlEdit Prepare(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action){
   string kind=Kind(action);
   if(kind=="page-create"||kind=="page-rename"||kind=="page-size"||kind=="page-delete")return NativePreparedPageOperations.Prepare(engine,context,project,action);
   if(kind=="page-copy")return NativePreparedPageCopy.Prepare(engine,context,project,action);
   if(kind=="page-referenced-rename")return NativeReferencedPageEditing.PrepareReferencedRename(engine,context,project,action);
   if(kind=="control-create-label"||kind=="control-clone"||kind=="control-delete")return NativePreparedStandardControlOperations.Prepare(engine,context,project,action);
   if(kind=="control-template-clone"||kind=="control-template-delete"||kind=="control-geometry")return NativeCurrentTemplateControlOperations.Prepare(engine,context,project,action);
   if(kind=="control-layer"||kind=="control-group"||kind=="control-ungroup")return NativeCurrentTemplateControlOperations.PrepareDrawingCommand(engine,context,project,action);
   throw new InvalidOperationException("Page/control implementation is absent for kind: "+kind);
  }
  internal static Dictionary<string,object> Read(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action){
   string kind=Kind(action);
   if(kind=="page-create"||kind=="page-rename"||kind=="page-size"||kind=="page-delete")return NativePreparedPageOperations.Read(engine,context,project,action);
   if(kind=="page-copy")return NativePreparedPageCopy.Read(engine,context,project,action);
   if(kind=="page-referenced-rename")return NativeReferencedPageEditing.ReferenceInspect(engine,context,project,action);
   if(kind=="control-create-label"||kind=="control-clone"||kind=="control-delete")return NativePreparedStandardControlOperations.Read(engine,context,project,action);
   if(kind=="control-template-clone"||kind=="control-template-delete"||kind=="control-geometry")return NativeCurrentTemplateControlOperations.Read(engine,context,project,action);
   if(kind=="control-layer"||kind=="control-group"||kind=="control-ungroup")return NativeCurrentTemplateControlOperations.ReadDrawingCommand(engine,context,project,action);
   throw new InvalidOperationException("Page/control reader is absent for kind: "+kind);
  }
 }

 internal sealed class NativePageControlAbi {
  internal readonly NativeEngine Engine;internal readonly NativeContext Context;internal readonly NativeStrategyProfile.Api Shared;internal readonly string Project;
  readonly Dictionary<string,IntPtr> methods=new Dictionary<string,IntPtr>();
  internal NativePageControlAbi(NativeEngine engine,NativeContext context,string project){Engine=engine;Context=context;Project=Path.GetFullPath(project);Shared=new NativeStrategyProfile.Api(engine);Current();
   Load("page","extensions/page/page-extension-abi-profile.json","88d83926092d6ec0271bb2750643066d38d29d87964d01d99dffb85be3552a31",false);
   Load("size","extensions/page/page-size-abi-profile.json","f796de7910b332cde37cfe5ed5bd325063f96600b59dff861a4fc91de612df7f",false);
   Load("delete","extensions/page/page-delete-abi-profile.json","3b274cb3965bcd0ad4265787aacc2792d1de97fa6eafba74007bc17a53af1520",false);
   Load("label","extensions/control/control-abi-guard-v2.json","ddb36d9e4734ebbe2cdb7365f3aaaa6a0122571994233332b7e98fd3e870df01",true);
   Load("standard","extensions/control/standard-controls-abi-guard-v3.json","3b38a7bafd4d49cc93be51a2b14529c95c8f57924072e42db04f45582a5fc18a",true);
  }
  void Load(string group,string relative,string hash,bool controlFormat){string path=Path.Combine(NativeOperations.TaskRoot,relative.Replace('/',Path.DirectorySeparatorChar));NativeMemory.Require(NativeMemory.Hash(path)==hash,"Page/control ABI proof changed: "+group);var profile=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),Engine.ImageSha256,"NativePageControlPreparation:66:editor"),"Page/control ABI belongs to another editor image.");uint preferred=controlFormat?0x400000U:unchecked((uint)NativeEngine.Number(profile["preferred_base"]));
   foreach(object value in (IEnumerable)profile["functions"]){var f=NativePageControlPreparation.Map(value);string name=Convert.ToString(f["name"]),hex=Convert.ToString(f[controlFormat?"first32":"bytes"]);byte[] bytes=new byte[hex.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);foreach(object n in (IEnumerable)f[controlFormat?"relocations":"reloc_offsets"]){int at=NativeEngine.Number(n);NativeMemory.Require(at>=0&&at+4<=bytes.Length,"Page/control relocation crosses its prefix.");Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(bytes,at)+NativeMemory.U(Engine.ImageBase)-preferred)),0,bytes,at,4);}IntPtr address=Engine.Address(NativeEngine.Number(f["rva"]));NativeMemory.Require(BitConverter.ToString(bytes)==BitConverter.ToString(NativeMemory.Bytes(address,bytes.Length)),"Page/control ABI differs: "+group+"/"+name);methods.Add(group+"/"+name,address);}
  }
  internal T Bind<T>(string group,string name)where T:class{Current();return Engine.Bind<T>(methods[group+"/"+name]);}
  internal void Current(){NativeMemory.Require(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId>0&&NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Page/control operation requires the captured x86 UI thread.");string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;IntPtr root=Shared.RootDoc();NativeMemory.Require(Project.Equals(fixture,StringComparison.OrdinalIgnoreCase)&&Path.GetFullPath(NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(root,0x24),2048)).Equals(Project,StringComparison.OrdinalIgnoreCase)&&NativeMemory.Ptr(root,0x2D4)==Context.ObjectModel,"Page/control current owned project/context differs.");}
  internal void Slot(IntPtr pointer,int slot,int rva){NativeMemory.Require(NativeMemory.Ptr(NativeMemory.Ptr(pointer,0),slot*4)==Engine.Address(rva),"Page/control virtual slot differs.");}
  internal Dictionary<int,IntPtr> Pages(){Current();var rows=new Dictionary<int,IntPtr>();var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);var id=Bind<NativeEngine.ThisInt>("page","PageArchiveId");foreach(IntPtr p in Engine.Children(Context.WindowManager)){NativeMemory.Require(NativeMemory.Ptr(p,0)==Engine.Address(0xDED294),"Unexpected native page type.");int key=id(p);string name=NativeStrategyProfile.ReadName(Shared,p);NativeMemory.Require(key>=0&&!rows.ContainsKey(key)&&names.Add(name),"Duplicate page ID/name.");rows.Add(key,p);}NativeMemory.Require(rows.Count==Engine.Bind<NativeEngine.ThisInt>(Engine.Virtual(Context.WindowManager,19))(Context.WindowManager),"Native page count/iterator differs.");return rows;}
  internal List<object> PageRows(){var list=new List<object>();var pages=Pages();var ids=new List<int>(pages.Keys);ids.Sort();foreach(int id in ids){IntPtr page=pages[id];list.Add(new Dictionary<string,object>{{"id",id},{"name",NativeStrategyProfile.ReadName(Shared,page)},{"iobject",NativeMemory.Hex(page)}});}return list;}
  internal IntPtr Page(Dictionary<string,object> target){int id=NativePageControlPreparation.Number(target,"page_id");var pages=Pages();NativeMemory.Require(pages.ContainsKey(id),"Requested page ID is absent.");IntPtr page=pages[id];NativeMemory.Require(NativeStrategyProfile.ReadName(Shared,page)==NativePageControlPreparation.Text(target,"page_name"),"Requested page name differs.");Engine.Children(page);Document(page,id);return page;}
  internal IntPtr Document(IntPtr page,int id){IntPtr doc=NativeMemory.Ptr(page,0x14);NativeMemory.Require(NativeMemory.Ptr(doc,0)==Engine.Address(0xDC4D94)&&NativeMemory.I32(doc,0x258)==id&&NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(doc,0x25C),256)==NativeStrategyProfile.ReadName(Shared,page),"Native loaded page document identity differs.");return doc;}
  internal List<IntPtr> TopControls(IntPtr doc){IntPtr list=NativeMemory.Add(doc,0x2BC);NativeMemory.Require(NativeMemory.Ptr(list,0)==Engine.Address(0xD3FD70),"Native top-level draw list type differs.");IntPtr node=NativeMemory.Ptr(list,4),tail=NativeMemory.Ptr(list,8),previous=IntPtr.Zero;int count=NativeMemory.I32(list,12);NativeMemory.Require(count>=0&&count<=512&&((count==0)==(node==IntPtr.Zero))&&((count==0)==(tail==IntPtr.Zero)),"Native draw list count/endpoints differ.");var objects=new List<IntPtr>();var visited=new HashSet<uint>();for(int i=0;i<count;i++){NativeMemory.Require(node!=IntPtr.Zero&&visited.Add(NativeMemory.U(node))&&NativeMemory.Ptr(node,4)==previous,"Native draw list back-link/cycle differs.");IntPtr full=NativeMemory.Ptr(node,8);NativeMemory.Require(full!=IntPtr.Zero&&!objects.Contains(full)&&NativeMemory.Ptr(full,0x64)==doc,"Native top-level control owner differs.");objects.Add(full);previous=node;node=NativeMemory.Ptr(node,0);}NativeMemory.Require(node==IntPtr.Zero&&previous==tail,"Native draw list does not end exactly at its tail.");return objects;}
  internal int[] Attributes(IntPtr doc){int[] result=new int[17];for(int i=0;i<17;i++)result[i]=NativeMemory.I32(doc,0x268+i*4);return result;}
  internal List<object> ControlRows(IntPtr doc){var result=new List<object>();foreach(IntPtr full in TopControls(doc)){var description=Engine.Describe(NativeMemory.Add(full,4));NativeMemory.Require(Convert.ToInt32(description["complete_offset"])==4,"Native draw object base offset differs.");result.Add(new Dictionary<string,object>{{"complete",NativeMemory.Hex(full)},{"iobject",NativeMemory.Hex(NativeMemory.Add(full,4))},{"rtti",description["rtti"]},{"type_id",NativeMemory.I32(full,0xC)},{"name",NativeStrategyProfile.ReadName(Shared,NativeMemory.Add(full,4))},{"native_id",NativeStrategyProfile.ReadId(Shared,NativeMemory.Add(full,4))},{"owner_document",NativeMemory.Hex(doc)},{"rectangle",Rectangle(full)},{"raw_DWORD60",unchecked((uint)NativeMemory.I32(full,0x60))},{"raw_DWORDB0",unchecked((uint)NativeMemory.I32(full,0xB0))}});}return result;}
  internal static int[] Rectangle(IntPtr full){return new int[]{NativeMemory.I32(full,0x80),NativeMemory.I32(full,0x84),NativeMemory.I32(full,0x88),NativeMemory.I32(full,0x8C)};}
  internal Dictionary<string,object> PageSnapshot(IntPtr page){int id=Bind<NativeEngine.ThisInt>("page","PageArchiveId")(page);IntPtr doc=Document(page,id);var view=Bind<NativeEngine.ThisPointer>("size","GetUserView")(doc);return new Dictionary<string,object>{{"pages",PageRows()},{"page_id",id},{"page_name",NativeStrategyProfile.ReadName(Shared,page)},{"page_iobject",NativeMemory.Hex(page)},{"document",NativeMemory.Hex(doc)},{"view",NativeMemory.Hex(view)},{"page_modified",Shared.Bind<NativeEngine.ThisInt>("RootIsModified")(doc)},{"attributes",Attributes(doc)},{"top_level_controls",ControlRows(doc)}};}
  internal IntPtr Owner(){IntPtr app=Shared.Bind<NativeEngine.CdeclPointer>("GetAfxApp")();NativeMemory.Require(NativeMemory.Ptr(app,0x520)==Shared.RootDoc(),"Page-list root differs.");IntPtr frame=NativeMemory.Ptr(app,0x524);NativeMemory.Require(NativeMemory.Ptr(frame,0)==Engine.Address(0xDBC034),"Page management frame differs.");IntPtr array=NativeMemory.Add(frame,0x314);NativeMemory.Require(NativeMemory.I32(array,8)==5,"Native page management lists differ.");IntPtr owner=NativeMemory.Ptr(NativeMemory.Ptr(array,4),8);NativeMemory.Require(NativeMemory.Ptr(owner,0)==Engine.Address(0xDBD7E4),"Native user-page list type differs.");Slot(owner,100,0x4AB6);return owner;}
 }
}

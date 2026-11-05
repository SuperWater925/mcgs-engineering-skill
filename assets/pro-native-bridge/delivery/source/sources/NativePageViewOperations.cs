// Open/activate a native page designer through C0FrmMain, without input injection.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;
using System.Globalization;using System.IO;using System.Runtime.InteropServices;using System.Security.Cryptography;
using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativePageViewOperations {
  internal const string Kind="page-view-open",AbiProfileSha="50579ca3e72de9fe6511465eee806ead747f98e56ea5aaa05f819f8968a85d62";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate int OpenPage(IntPtr frame,int pageId);
  [UnmanagedFunctionPointer(CallingConvention.Cdecl)][return:MarshalAs(UnmanagedType.I1)]internal delegate bool FrameProbe(IntPtr doc,out IntPtr frame);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate int Limit(IntPtr unused);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate IntPtr First(IntPtr template);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate IntPtr Next(IntPtr template,ref IntPtr position);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr GetModuleHandleW(string name);
  [DllImport("kernel32.dll",EntryPoint="GetProcAddress",ExactSpelling=true)]static extern IntPtr ExportOrdinal(IntPtr module,IntPtr ordinal);
  [DllImport("user32.dll")][return:MarshalAs(UnmanagedType.Bool)]static extern bool IsWindow(IntPtr hwnd);
  static Dictionary<string,object>M(object x){return NativePageControlPreparation.Map(x);}static int N(object x){return NativeEngine.Number(x);}
  internal sealed class Api {
   internal readonly NativeControlPropertyEditing.Api Common;internal readonly NativeEngine Engine;internal readonly NativeContext Context;
   readonly NativeLazyFunctionProfile methods;internal OpenPage Open{get{return methods.Bind<OpenPage>("OpenPage");}}internal FrameProbe Probe{get{return methods.Bind<FrameProbe>("ProbeDrawingFrame");}}internal Limit Maximum{get{return methods.Bind<Limit>("MaxOpenViews");}}internal First FirstDoc{get{return methods.Bind<First>("TemplateFirstDoc");}}internal Next NextDoc{get{return methods.Bind<Next>("TemplateNextDoc");}}
   internal readonly IntPtr Frame,Template;readonly Dictionary<string,object> profile;
   internal Api(NativeEngine e,NativeContext c,string project){
    Engine=e;Context=c;Common=new NativeControlPropertyEditing.Api(e,c,project);
    string file=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"project-services-prep","page-view-open-abi-profile.v2.json");
    NativeMemory.Require(NativeLazyFunctionProfile.SourceHash(file)==AbiProfileSha,"Native designer-open ABI contract differs.");
    profile=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue}.Deserialize<Dictionary<string,object>>(NativeLazyFunctionProfile.ReadText(file));
    NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),e.ImageSha256,"NativePageViewOperations:26:editor"),"Native designer-open binary differs.");
    string evidence=Path.Combine(NativeUsableEditPermit.DirectoryRoot,Convert.ToString(profile["source_evidence"]).Replace('/',Path.DirectorySeparatorChar));
    NativeMemory.Require(NativeMemory.Hash(evidence)==Convert.ToString(profile["source_evidence_sha256"]),"Native designer-open source derivation differs.");
    methods=new NativeLazyFunctionProfile(e,"coverage-20261101/usable-edit-0001/project-services-prep/page-view-open-abi-profile.v2.json",AbiProfileSha,"editor");
    var mfc=M(profile["mfc"]);IntPtr module=GetModuleHandleW("mfc110u.dll");string actual=null;foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(loaded.BaseAddress==module)actual=loaded.FileName;
    NativeMemory.Require(module!=IntPtr.Zero&&actual!=null&&NativeBinaryIdentity.Observe(Convert.ToString(mfc["sha256"]),NativeMemory.Hash(actual),"NativePageViewOperations:31:module"),"Native document template MFC owner differs.");
    foreach(object value in(IEnumerable)mfc["imports"]){var row=M(value);IntPtr address=NativeMemory.Add(module,N(row["target_rva"]));NativeMemory.Require(ExportOrdinal(module,new IntPtr(N(row["ordinal"])))==address&&NativeMemory.Ptr(e.Address(N(row["iat_rva"])),0)==address,"Native document template import target differs.");Bytes(row,address,module,0x10000000U);}
    IntPtr app=Common.Common.Shared.Bind<NativeEngine.CdeclPointer>("GetAfxApp")();NativeMemory.Require(NativeMemory.Ptr(app,0x520)==Common.Common.Shared.RootDoc(),"Designer application root differs.");
    Frame=NativeMemory.Ptr(app,0x20);Table(Frame,M(profile["main_frame"]));Template=NativeMemory.Ptr(Frame,N(profile["template_frame_offset"]));Table(Template,M(profile["template"]));
    NativeMemory.Require(NativeMemory.Ptr(NativeMemory.Ptr(Template,0),23*4)==methods.Address("TemplateFirstDoc")&&NativeMemory.Ptr(NativeMemory.Ptr(Template,0),24*4)==methods.Address("TemplateNextDoc"),"Native designer template enumerator vtable differs.");
   }
   void Bytes(Dictionary<string,object> row,IntPtr at,IntPtr actual,uint preferred){string h=Convert.ToString(row["bytes"]);byte[] b=new byte[h.Length/2];for(int i=0;i<b.Length;i++)b[i]=Byte.Parse(h.Substring(2*i,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);NativeCodeRelocation.RebaseDeltaInPlace(b,(IEnumerable)row["reloc_offsets"],unchecked((uint)(NativeMemory.U(actual)-preferred)));NativeMemory.Require(BitConverter.ToString(b)==BitConverter.ToString(NativeMemory.Bytes(at,b.Length)),"Native designer ABI prefix differs.");}
   void Table(IntPtr instance,Dictionary<string,object> info){NativeMemory.Require(instance!=IntPtr.Zero&&NativeMemory.Ptr(instance,0)==Engine.Address(N(info["vtable_rva"])),"Native designer owner type differs.");IntPtr table=NativeMemory.Ptr(instance,0),col=NativeMemory.Ptr(table,-4);NativeMemory.Require(col==Engine.Address(N(info["col_rva"]))&&NativeMemory.I32(col,4)==0&&NativeMemory.Ptr(col,12)==Engine.Address(N(info["type_descriptor_rva"]))&&NativeMemory.Ascii(NativeMemory.Add(NativeMemory.Ptr(col,12),8),256)==Convert.ToString(info["rtti"]),"Native designer owner RTTI differs.");}
   internal void Current(){Common.Common.Current();Table(Frame,M(profile["main_frame"]));NativeMemory.Require(NativeMemory.Ptr(Frame,N(profile["template_frame_offset"]))==Template,"Native designer template owner changed.");Table(Template,M(profile["template"]));}
   internal List<object> Frames(){Current();var result=new List<object>();var positions=new HashSet<uint>();var docs=new HashSet<uint>();IntPtr position=FirstDoc(Template);for(int i=0;position!=IntPtr.Zero;i++){
    NativeMemory.Require(positions.Add(NativeMemory.U(position)),"Native designer document list bound/cycle differs.");IntPtr doc=NextDoc(Template,ref position);NativeMemory.Require(doc!=IntPtr.Zero&&docs.Add(NativeMemory.U(doc))&&NativeMemory.Ptr(doc,0)==Engine.Address(0xDC4D94),"Native designer template contains an unknown/duplicate document.");IntPtr frame;bool visible=Probe(doc,out frame);NativeMemory.Require(visible==(frame!=IntPtr.Zero),"Native drawing-frame predicate/result disagree.");if(visible){NativeMemory.Require(IsWindow(NativeMemory.Ptr(frame,0x20)),"Native drawing-frame HWND is invalid.");result.Add(new Dictionary<string,object>{{"page_id",NativeMemory.I32(doc,0x258)},{"document",NativeMemory.Hex(doc)},{"frame",NativeMemory.Hex(frame)}});}
   }return result;}
  }
  static Dictionary<string,object> Password(IntPtr doc){IntPtr data=NativeMemory.Ptr(doc,0x2B4);int n=NativeMemory.I32(data,-12),cap=NativeMemory.I32(data,-8);NativeMemory.Require(n>=0&&cap>=n,"Native window password bounds differ.");byte[] bytes=NativeMemory.Bytes(data,checked(n*2));string sha;using(var h=SHA256.Create())sha=BitConverter.ToString(h.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();return new Dictionary<string,object>{{"utf16_units",n},{"utf16_sha256",sha}};}
  static Dictionary<string,object> Capture(Api api,Dictionary<string,object> action){
   IntPtr page=api.Common.Common.Page(M(action["target"]));int id=Convert.ToInt32(M(action["target"])["page_id"]);IntPtr doc=api.Common.Common.Document(page,id);var frames=api.Frames();IntPtr frame;bool open=api.Probe(doc,out frame);
   int maximum=api.Maximum(IntPtr.Zero);NativeMemory.Require(maximum>0,"Original native designer maximum is not a positive current capability.");
   var password=Password(doc);bool eligible=open||(frames.Count<maximum&&Convert.ToInt32(password["utf16_units"])==0);
   return new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"page",api.Common.Common.PageSnapshot(page)},{"controls",NativeUsableEditPermit.CurrentDrawControls(api.Engine,doc,id)},
    {"document_compile_raw",NativeMemory.I32(doc,0x114)},{"root_modified",NativeMemory.I32(api.Common.Common.Shared.RootDoc(),0x48)},{"root_compile_raw",NativeMemory.I32(api.Common.Common.Shared.RootDoc(),0x114)},
    {"drawing_frames",frames},{"target_frame",NativeMemory.Hex(frame)},{"target_open",open},{"maximum_open_frames",maximum},{"password_preimage",password},{"eligible_without_closing_others_or_password_dialog",eligible},{"full_serialization_preimage",false}};
  }
  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return Capture(new Api(e,c,project),action);}
  internal static Prepared Prepare(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new Prepared(new Api(e,c,project),action);}
  internal sealed class Prepared:INativePreparedPageControlEdit {
   readonly Api api;readonly Dictionary<string,object> action,before;bool disposed,entered;
   internal Prepared(Api a,Dictionary<string,object> request){api=a;action=request;NativeMemory.Require(Convert.ToString(action["kind"])==Kind&&Convert.ToString(action["abi_profile_sha256"])==AbiProfileSha,"Native designer-open kind/ABI differs.");before=Capture(api,action);NativePageControlPreparation.Before(action,before);NativeMemory.Require(Object.Equals(M(action["after"])["open"],true)&&M(action["after"]).Count==1,"Designer action requires explicit open=true only.");NativeMemory.Require(Object.Equals(before["eligible_without_closing_others_or_password_dialog"],true),"Native designer open would require closing another page or the original password dialog; no command entered.");NativeCurrentTemplateControlOperations.RequireDesignerPreviewContext(api.Engine,api.Context,api.Common.Common.Project,NativeMemory.Ptr(new IntPtr(N(NativePageControlPreparation.Map(before["page"])["page_iobject"])),0x14));}
   internal void ValidateBefore(){NativeMemory.Require(!disposed&&!entered,"Native designer action is disposed/already entered.");NativePageControlPreparation.Same(before,Capture(api,action),"Native page/frame/password/controls preimage changed after preparation.");}
   void VerifyAfter(Dictionary<string,object> after){
    NativeMemory.Require(Object.Equals(after["target_open"],true),"Native designer command returned without an actual drawing frame.");var b=new Dictionary<string,object>(M(before["page"]));var a=new Dictionary<string,object>(M(after["page"]));b.Remove("view");a.Remove("view");NativePageControlPreparation.Same(b,a,"Native designer open changed page identity, dirty state, attributes or top-level controls.");
    foreach(string key in new[]{"controls","document_compile_raw","root_modified","root_compile_raw","password_preimage"})NativePageControlPreparation.Same(before[key],after[key],"Native designer open changed a protected project value: "+key);
    var frames=new Dictionary<string,object>();foreach(object value in(IEnumerable)after["drawing_frames"]){var row=M(value);frames.Add(Convert.ToString(row["document"]),row);}
    int id=Convert.ToInt32(M(action["target"])["page_id"]);foreach(object value in(IEnumerable)before["drawing_frames"]){var row=M(value);NativeMemory.Require(frames.ContainsKey(Convert.ToString(row["document"])),"Native designer command closed another document frame.");NativePageControlPreparation.Same(row,frames[Convert.ToString(row["document"])],"Native designer command replaced an existing frame.");}
    int count=((IList)before["drawing_frames"]).Count+(Object.Equals(before["target_open"],true)?0:1);NativeMemory.Require(frames.Count==count,"Native designer frame count changed beyond the selected page.");
   }
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);entered=true;NativeOperationTrace.BeforeMutation("original-c0frmmain-open-or-activate-page");int value=api.Open(api.Frame,Convert.ToInt32(M(action["target"])["page_id"]));NativeMemory.Require(value==0,"Original designer open returned failure; no repeat.");var after=Capture(api,action);VerifyAfter(after);lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",Kind},{"native_return",value},{"after",after},{"computer_input_injected",false},{"project_save_called",false},{"functional_acceptance_pending",true}};}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(entered&&!disposed,"Designer Apply must complete before Flush.");lease.BeginFlush(action);VerifyAfter(Capture(api,action));lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"project_save_called",false}};}
   public void Dispose(){disposed=true;}
  }
 }
}

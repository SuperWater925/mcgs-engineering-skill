// Static-evidence composition of the original no-dialog business segment ABC1DD..ABC400.
// Additional source only. No entry point, deployment, queue or activation code.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static class NativePageDeleteExtensionProfile {
        const string TemporaryName="Codex页面删除临时";
        const string RetainedName="Codex控件接口试验";
        static int attempted;
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V1(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int I0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int I1(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr P0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr PP(IntPtr self,IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Open(IntPtr self,int type,IntPtr sql,int options);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Find(IntPtr self,IntPtr criterion);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Notify(IntPtr self,IntPtr page,int action);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void RemoveList(IntPtr self,int row,int selectNext);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int References(IntPtr self,IntPtr objectPath,IntPtr firstReference);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool TwoPointers(IntPtr self,IntPtr first,IntPtr second);

        sealed class Api {
            internal readonly NativeEngine Engine;internal readonly NativeStrategyProfile.Api Shared;
            readonly Dictionary<string,IntPtr> functions=new Dictionary<string,IntPtr>();
            internal Api(NativeEngine engine) {
                Engine=engine;Shared=new NativeStrategyProfile.Api(engine);
                NativeMemory.Require(IntPtr.Size==4 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Page deletion requires the captured x86 UI thread.");
                var profile=Read(Path.Combine(NativeOperations.TaskRoot,"extensions","page","page-delete-abi-profile.json"));
                NativeMemory.Require(Convert.ToInt32(profile["schema"])==1 && Convert.ToString(profile["binary_sha256"])==engine.ImageSha256,"Page deletion image/profile differs.");
                uint preferred=unchecked((uint)NativeEngine.Number(profile["preferred_base"]));
                foreach(object value in (IEnumerable)profile["functions"]) {
                    var row=(Dictionary<string,object>)value;string hex=Convert.ToString(row["bytes"]),name=Convert.ToString(row["name"]);byte[] bytes=new byte[hex.Length/2];
                    for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(2*i,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                    foreach(object offset in (IEnumerable)row["reloc_offsets"]){int at=Convert.ToInt32(offset);NativeMemory.Require(at>=0 && at+4<=bytes.Length,"Delete ABI relocation exceeds prefix.");Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(bytes,at)+NativeMemory.U(engine.ImageBase)-preferred)),0,bytes,at,4);}
                    IntPtr address=engine.Address(NativeEngine.Number(row["rva"]));NativeMemory.Require(BitConverter.ToString(NativeMemory.Bytes(address,bytes.Length))==BitConverter.ToString(bytes),"Page delete ABI differs: "+name);functions.Add(name,address);
                }
                NativeMemory.Require(NativeMemory.I32(engine.Address(0xCF9AD0),4)==0xB8,"CDBWndUser native CRuntimeClass size differs.");
            }
            internal static Dictionary<string,object> Read(string path){return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path));}
            internal T Bind<T>(string name)where T:class{return Marshal.GetDelegateForFunctionPointer(functions[name],typeof(T))as T;}
            internal void Project(NativeContext context,string expected) {
                string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
                NativeMemory.Require(Path.GetFullPath(expected).Equals(fixture,StringComparison.OrdinalIgnoreCase) && NativePageDuplicateProfile.CurrentProjectPath(Engine).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Delete trial requires the exact isolated fixture.");
                NativeMemory.Require(NativeMemory.Ptr(Shared.RootDoc(),0x2D4)==context.ObjectModel,"Page deletion context changed.");Engine.RequireTable(context.ObjectModel,"ObjectModel");
                NativeMemory.Readable(NativeMemory.Ptr(Shared.RootDoc(),0x2E4),4);
                Engine.RequireTable(context.WindowService,"UserWindowObjectManager.IUserWindowService");
                NativeMemory.Require(Engine.Virtual(context.WindowService,4)==Engine.Address(0x2B3CD) && Engine.Virtual(context.WindowService,5)==Engine.Address(0x538AF),"Page remove/rename service methods differ.");
            }
            internal IntPtr Owner() {
                IntPtr app=Shared.Bind<NativeEngine.CdeclPointer>("GetAfxApp")();NativeMemory.Require(NativeMemory.Ptr(app,0x520)==Shared.RootDoc(),"Page list application root changed.");
                IntPtr frame=NativeMemory.Ptr(app,0x524);NativeMemory.Require(NativeMemory.Ptr(frame,0)==Engine.Address(0xDBC034),"Expected C0FrmManage owner.");
                IntPtr array=NativeMemory.Add(frame,0x314);NativeMemory.Require(NativeMemory.I32(array,8)==5,"Expected five management lists.");
                IntPtr list=NativeMemory.Ptr(NativeMemory.Ptr(array,4),8);NativeMemory.Require(NativeMemory.Ptr(list,0)==Engine.Address(0xDBD7E4) && NativeMemory.Ptr(NativeMemory.Ptr(list,0),400)==Engine.Address(0x4AB6),"Expected original C0ManListUser new method.");return list;
            }
            internal Dictionary<int,IntPtr> Pages(NativeContext context) {
                var pages=new Dictionary<int,IntPtr>();var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach(IntPtr page in Engine.Children(context.WindowManager)) {
                    NativeMemory.Require(NativeMemory.Ptr(page,0)==Engine.Address(0xDED294),"Unexpected page IObject type.");int id=Bind<I0>("PageArchiveId")(page);string name=Name(page);
                    NativeMemory.Require(id>=0 && !pages.ContainsKey(id) && !String.IsNullOrEmpty(name) && names.Add(name),"Repeated/empty native page identity.");pages.Add(id,page);
                }
                NativeMemory.Require(pages.Count==Engine.Bind<NativeEngine.ThisInt>(Engine.Virtual(context.WindowManager,19))(context.WindowManager),"Page count/iterator differs.");return pages;
            }
            internal string Name(IntPtr page){return NativeStrategyProfile.ReadName(Shared,page);}
            internal IntPtr Database() {
                IntPtr expected=NativeMemory.Add(Shared.RootDoc(),0x25C);NativeMemory.Require(Bind<I0>("DatabaseIsOpen")(expected)==1,"Native project database is not already open; never repair/reopen it.");
                IntPtr database=Bind<P0>("RootDatabase")(Shared.RootDoc());NativeMemory.Require(database==expected,"Native project database owner differs.");return database;
            }
            internal IntPtr FontManager() {
                IntPtr owner=NativeMemory.Ptr(Shared.RootDoc(),0x20C);NativeMemory.Require(NativeMemory.Ptr(owner,0)==Engine.Address(0xDB35DC),"Expected the original CLinguist owner.");
                IntPtr manager=Bind<P0>("GetFontManager")(owner);NativeMemory.Require(manager!=IntPtr.Zero && manager==NativeMemory.Ptr(owner,0x5C),"CLinguist font-manager owner differs.");NativeMemory.Readable(manager,0xB0);return manager;
            }
        }
        sealed class Row : IDisposable {
            readonly Api api;internal readonly IntPtr Storage;bool constructed,openAttempted;
            internal Row(Api value,IntPtr database) {
                api=value;Storage=Marshal.AllocHGlobal(0xB8);
                try {for(int i=0;i<0xB8;i++)Marshal.WriteByte(Storage,i,0);NativeMemory.Require(api.Bind<PP>("RowCtor")(Storage,database)==Storage,"Native row constructor returned a different object.");constructed=true;
                    NativeMemory.Require(NativeMemory.Ptr(Storage,0)==api.Engine.Address(0xCF9B1C),"Native CDBWndUser row vtable differs.");openAttempted=true;api.Bind<Open>("RowOpen")(Storage,-1,IntPtr.Zero,0);
                }catch{Dispose();throw;}
            }
            internal int Id{get{return NativeMemory.I32(Storage,0x98);}}
            internal int Flag{get{return NativeMemory.I32(Storage,0xB0);}}
            internal string Name{get{return NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(Storage,0x9C),256);}}
            internal bool Locate(int id) {
                IntPtr filter=Marshal.StringToHGlobalUni("iID = "+id.ToString(CultureInfo.InvariantCulture));
                try{return api.Bind<Find>("RowFind")(Storage,filter)!=0 && Id==id;}finally{Marshal.FreeHGlobal(filter);}
            }
            internal Dictionary<int,string> AllZeroFlags() {
                NativeMemory.Require(api.Bind<I0>("RowBof")(Storage)==0,"Native row cursor is empty/unavailable.");api.Bind<V0>("RowFirst")(Storage);var rows=new Dictionary<int,string>();
                while(api.Bind<I0>("RowEof")(Storage)==0) {
                    NativeMemory.Require(rows.Count<64 && Id>=0 && !rows.ContainsKey(Id) && Flag==0,"Native page rows have unknown identities/delete flags.");rows.Add(Id,Name);api.Bind<V0>("RowNext")(Storage);
                }
                return rows;
            }
            internal void MarkDeleted() {
                NativeMemory.Require(Flag==0,"Temporary row delete preimage differs.");NativeOperationTrace.BeforeMutation("page-temp-native-recordset-edit");api.Bind<V0>("RowEdit")(Storage);
                // Exactly the original ABC398..ABC3B2 buffer edit; native Update performs the database write.
                NativeOperationTrace.BeforeMutation("page-temp-native-delete-flag");Marshal.WriteInt32(Storage,0xB0,-1);NativeOperationTrace.BeforeMutation("page-temp-native-recordset-update");api.Bind<V0>("RowUpdate")(Storage);
            }
            public void Dispose() {
                try {if(constructed){try{if(openAttempted){openAttempted=false;api.Bind<V0>("RowClose")(Storage);}}finally{constructed=false;api.Bind<V0>("RowDtor")(Storage);}}}finally{Marshal.FreeHGlobal(Storage);}
            }
        }
        sealed class NativePath : IDisposable {
            readonly Api api;internal readonly IntPtr Storage;bool constructed;
            internal NativePath(Api value,IntPtr page){api=value;Storage=Marshal.AllocHGlobal(4);Marshal.WriteInt32(Storage,0);try{NativeMemory.Require(api.Bind<PP>("ObjectPath")(page,Storage)==Storage,"Native page path sret differs.");constructed=true;NativeMemory.Require(!String.IsNullOrEmpty(NativeStrategyProfile.ReadBorrowedCString(Storage,2048)),"Native page path is empty.");}catch{Dispose();throw;}}
            public void Dispose(){try{if(constructed){constructed=false;api.Shared.Bind<V0>("CStringDtor")(Storage);}}finally{Marshal.FreeHGlobal(Storage);}}
        }
        static Dictionary<int,string> Names(Api api,Dictionary<int,IntPtr> pages){var result=new Dictionary<int,string>();foreach(var row in pages)result.Add(row.Key,api.Name(row.Value));return result;}
        static void Preserve(Api api,Dictionary<int,IntPtr> old,Dictionary<int,string> names,Dictionary<int,IntPtr> actual) {
            foreach(var row in old)NativeMemory.Require(actual.ContainsKey(row.Key) && actual[row.Key]==row.Value && api.Name(row.Value)==names[row.Key],"An old page identity changed during the isolated temporary-page lifecycle.");
        }
        static void Session(Api api,NativeContext context,string expected,Dictionary<int,IntPtr> pages,Dictionary<int,string> rows) {
            string path=Path.Combine(NativeOperations.TaskRoot,"extensions","page","delete-session-baseline.json");NativeMemory.Require(File.Exists(path),"Fresh root-owned delete-session-baseline.json is required before any mutation.");var guard=Api.Read(path);
            NativeMemory.Require(Convert.ToInt32(guard["schema"])==1 && Convert.ToString(guard["purpose"])=="native-temporary-page-delete" && Convert.ToInt32(guard["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(guard["ui_thread_id"])==EngineEntry.ExpectedUiThreadId,"Deletion baseline is from another purpose/process/thread.");
            NativeMemory.Require(Path.GetFullPath(Convert.ToString(guard["fixture_path"])).Equals(Path.GetFullPath(expected),StringComparison.OrdinalIgnoreCase),"Deletion baseline project path differs.");
            string indexPath=Path.GetFullPath(Convert.ToString(guard["index_path"]));string extensions=Path.GetFullPath(Path.Combine(NativeOperations.TaskRoot,"extensions"))+Path.DirectorySeparatorChar;
            NativeMemory.Require(indexPath.StartsWith(extensions,StringComparison.OrdinalIgnoreCase) && Path.GetFileName(indexPath)=="index.json" && NativeMemory.Hash(indexPath)==Convert.ToString(guard["index_sha256"]),"Delete baseline safe-export file differs.");var index=Api.Read(indexPath);
            NativeMemory.Require(Convert.ToString(index["project_family"])=="Pro" && Convert.ToBoolean(index["source_unchanged"]) && Convert.ToString(index["sha256"])==Convert.ToString(guard["project_sha256"]) && NativeMemory.Hash(expected)==Convert.ToString(guard["project_sha256"]),"Delete baseline physical/semantic capture differs.");
            NativeMemory.Require(pages.Count==13 && rows.Count==13 && pages.ContainsKey(31) && api.Name(pages[31])==RetainedName,"Expected exactly13 existing pages including retained page31.");
            int seen=0;foreach(object value in (IEnumerable)index["rows"]) {
                var row=(Dictionary<string,object>)value;if(Convert.ToString(row["table"])!="WndUser")continue;int id=Convert.ToInt32(row["iID"]);string name=Convert.ToString(row["strName"]);
                NativeMemory.Require(row["iDeleteFlag"]!=null && Convert.ToInt32(row["iDeleteFlag"])==0 && pages.ContainsKey(id) && api.Name(pages[id])==name && rows.ContainsKey(id) && rows[id]==name,"Delete baseline/model/database page identities or flags differ.");seen++;
            }
            NativeMemory.Require(seen==13 && NativeMemory.I32(api.Shared.RootDoc(),0x48)==Convert.ToInt32(guard["root_modified"]) && NativeMemory.I32(api.Shared.RootDoc(),0x114)==Convert.ToInt32(guard["compile_flag"]),"Delete-session page count/dirty/compile state differs.");
        }
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new Api(engine);api.Project(context,Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));var pages=api.Pages(context);IntPtr owner=api.Owner(),database=api.Database(),font=api.FontManager();Dictionary<int,string> rows;
            using(var recordset=new Row(api,database))rows=recordset.AllZeroFlags();
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",false},{"page_count",pages.Count},{"database_rows_all_delete_flags_zero",true},{"database_row_count",rows.Count},{"user_list_count",api.Bind<I0>("ListCount")(owner)},{"font_manager",NativeMemory.Hex(font)},{"fresh_delete_session_manifest_present",File.Exists(Path.Combine(NativeOperations.TaskRoot,"extensions","page","delete-session-baseline.json"))},{"native_delete_executed",false}};
        }
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            var api=new Api(engine);api.Project(context,expected);IntPtr owner=api.Owner(),database=api.Database(),font=api.FontManager(),root=api.Shared.RootDoc();var before=api.Pages(context);var oldNames=Names(api,before);Dictionary<int,string> rows;
            using(var recordset=new Row(api,database))rows=recordset.AllZeroFlags();Session(api,context,expected,before,rows);
            foreach(var row in before)NativeMemory.Require(!String.Equals(api.Name(row.Value),TemporaryName,StringComparison.OrdinalIgnoreCase),"Temporary delete page already exists; never retry a partial lifecycle.");
            NativeMemory.Require(api.Bind<I0>("ListCount")(owner)==13,"Native user list preimage count differs.");NativeMemory.Require(Interlocked.CompareExchange(ref attempted,1,0)==0,"Delete lifecycle was already attempted in this engine.");
            bool write=false;string phase="page-temp-create";int id=-1;
            try {
                write=true;NativeStrategyProfile.MarkRootDirty(api.Shared);NativeOperationTrace.BeforeMutation(phase);api.Bind<V0>("PageNew")(owner);
                var createdPages=api.Pages(context);NativeMemory.Require(createdPages.Count==14,"Temporary page was not the only added page.");Preserve(api,before,oldNames,createdPages);IntPtr page=IntPtr.Zero;
                foreach(var row in createdPages)if(!before.ContainsKey(row.Key)){NativeMemory.Require(page==IntPtr.Zero && row.Key>31,"Temporary new ID is not one fresh ID.");id=row.Key;page=row.Value;}
                NativeMemory.Require(page!=IntPtr.Zero && engine.Children(page).Count==0,"Temporary native page is not blank.");string generated=api.Name(page);
                using(var oldName=new NativeStrategyProfile.CString(api.Shared,generated))using(var newName=new NativeStrategyProfile.CString(api.Shared,TemporaryName)) {
                    phase="page-temp-rename";NativeOperationTrace.BeforeMutation(phase);NativeMemory.Require(api.Bind<TwoPointers>("WindowRename")(context.WindowService,oldName.Storage,newName.Storage),"Native temporary rename failed.");
                }
                NativeMemory.Require(api.Name(page)==TemporaryName && engine.Children(page).Count==0,"Temporary rename/blank-page readback differs.");
                IntPtr temporaryDoc=NativeMemory.Ptr(page,0x14);NativeMemory.Require(NativeMemory.Ptr(temporaryDoc,0)==engine.Address(0xDC4D94) && NativeMemory.I32(temporaryDoc,0x258)==id && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(temporaryDoc,0x25C),256)==TemporaryName && api.Shared.Bind<I0>("RootIsModified")(temporaryDoc)==0,"Temporary page document identity/clean state differs; do not risk a close/save prompt.");
                using(var nativePath=new NativePath(api,page))using(var reference=new NativeStrategyProfile.CString(api.Shared,""))NativeMemory.Require(api.Bind<References>("ReferenceCheck")(context.ObjectModel,nativePath.Storage,reference.Storage)==0,"Temporary page unexpectedly has references; no delete was attempted.");
                int rowIndex=api.Bind<I1>("ListFindId")(owner,id);NativeMemory.Require(rowIndex>=0 && rowIndex<14 && api.Bind<I0>("ListCount")(owner)==14,"Temporary page list identity differs.");
                using(var recordset=new Row(api,database)) {
                    var zeroRows=recordset.AllZeroFlags();NativeMemory.Require(zeroRows.Count==14 && zeroRows.ContainsKey(id) && zeroRows[id]==TemporaryName && recordset.Locate(id) && recordset.Flag==0 && recordset.Name==TemporaryName,"Temporary native database row differs.");
                    phase="page-temp-notify-remove";NativeOperationTrace.BeforeMutation(phase);api.Bind<Notify>("RootNotify")(root,page,2);
                    IntPtr decision=Marshal.AllocHGlobal(3);
                    try {for(int i=0;i<3;i++)Marshal.WriteByte(decision,i,0);using(var name=new NativeStrategyProfile.CString(api.Shared,TemporaryName)) {
                        phase="page-temp-service-remove";NativeOperationTrace.BeforeMutation(phase);NativeMemory.Require(api.Bind<TwoPointers>("WindowRemove")(context.WindowService,name.Storage,decision),"Native service refused removing the unreferenced temporary page.");
                    }}finally{Marshal.FreeHGlobal(decision);}
                    // The service owns/destructs page/document. Never dereference or free either pointer again.
                    page=IntPtr.Zero;temporaryDoc=IntPtr.Zero;var removedPages=api.Pages(context);NativeMemory.Require(removedPages.Count==13 && !removedPages.ContainsKey(id),"Temporary model deletion failed.");Preserve(api,before,oldNames,removedPages);
                    phase="page-temp-list-remove";NativeOperationTrace.BeforeMutation(phase);api.Bind<RemoveList>("ListRemove")(owner,rowIndex,1);
                    NativeMemory.Require(api.Bind<I0>("ListCount")(owner)==13 && api.Bind<I1>("ListFindId")(owner,id)==-1,"Temporary list deletion failed.");
                    NativeMemory.Require(recordset.Locate(id) && recordset.Name==TemporaryName && recordset.Flag==0,"Temporary row changed during native unregister.");phase="page-temp-db-delete-mark";recordset.MarkDeleted();
                }
                using(var check=new Row(api,database))NativeMemory.Require(check.Locate(id) && check.Name==TemporaryName && check.Flag==-1,"Temporary native row deletion mark was not persisted to the current database.");
                phase="page-temp-font-map-cleanup";NativeOperationTrace.BeforeMutation(phase);NativeMemory.Require(api.FontManager()==font,"Font manager owner changed.");api.Bind<V1>("RemovePageFontMaps")(font,id);
                var finalPages=api.Pages(context);NativeMemory.Require(finalPages.Count==13 && !finalPages.ContainsKey(id),"Temporary page reappeared after cleanup.");Preserve(api,before,oldNames,finalPages);NativeOperationTrace.SetPhase("verified");
                return new Dictionary<string,object>{{"ok",true},{"write_attempted",true},{"phase","temporary-page-full-native-lifecycle-complete"},{"temporary_page_id",id},{"temporary_page_name",TemporaryName},{"retained_page_id",31},{"retained_page_name",RetainedName},{"page_count_before",13},{"page_count_during",14},{"page_count_after",13},{"temporary_model_removed",true},{"temporary_list_removed",true},{"temporary_database_delete_flag",-1},{"font_page_maps_cleanup_called",true},{"old_page_identities_unchanged",true},{"native_dialog_called",false},{"final_save_verified",false},{"physical_row_removal_verified",false}};
            }catch(Exception error){error.Data["write_attempted"]=write;error.Data["phase"]=phase;error.Data["temporary_page_id"]=id;throw;}
        }
    }
}

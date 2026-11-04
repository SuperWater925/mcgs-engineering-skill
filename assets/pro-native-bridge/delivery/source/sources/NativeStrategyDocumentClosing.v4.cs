// Candidate: explicitly close one actual native private strategy document.
// The original native close owns teardown; no released pointer is inspected/freed afterward.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;
using System.IO;using System.Text;using System.Web.Script.Serialization;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativeStrategyWorkingModelEditing {
  internal const string CloseKind="strategy-view-close",CloseAbiProfileSha="b23816c46a644cabf04c29cf4ad5846146841bcff4322567dec38160913412ec";
  internal sealed class CloseContract {
   internal readonly TypedContract Typed;internal readonly Api Api;internal readonly NativeStrategyTriggerContextEditing.Api Contexts;
   internal readonly IntPtr Mfc;internal readonly V0 Close;readonly int mfcImageBytes;readonly Dictionary<string,object> profile;
   internal CloseContract(NativeEngine e,NativeContext c,string project){Typed=new TypedContract(new Api(e,c,project));Api=Typed.Native;Contexts=new NativeStrategyTriggerContextEditing.Api(e,c,project);
    string path=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"strategy-prep","node-edit-prep","lifecycle-prep","strategy-document-close-abi-profile.json");
    NativeMemory.Require(NativeMemory.Hash(path)==CloseAbiProfileSha,"Strategy document close ABI profile differs.");
    profile=new JavaScriptSerializer{MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));
    NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),e.ImageSha256,"NativeStrategyDocumentClosing.v4:15:editor")&&Convert.ToString(profile["node_abi_profile_sha256"])==AbiProfileSha&&Convert.ToString(profile["typed_abi_profile_sha256"])==TypedAbiProfileSha,"Strategy close image/node/typed dependency differs.");
    Mfc=GetModuleHandleW("mfc110u.dll");string loaded=null;foreach(ProcessModule mod in Process.GetCurrentProcess().Modules)if(mod.BaseAddress==Mfc){loaded=mod.FileName;mfcImageBytes=mod.ModuleMemorySize;}
    NativeMemory.Require(Mfc!=IntPtr.Zero&&loaded!=null&&NativeBinaryIdentity.Observe(Convert.ToString(profile["mfc_sha256"]),NativeMemory.Hash(loaded),"NativeStrategyDocumentClosing.v4:17:module"),"Original strategy close MFC is not already loaded/exact.");
    Current();int closeRva=N(profile["mfc_close_rva"]);NativeMemory.Require(closeRva>=0&&closeRva<mfcImageBytes,"Original strategy MFC close address is outside its exact loaded module.");Close=(V0)Marshal.GetDelegateForFunctionPointer(NativeMemory.Add(Mfc,closeRva),typeof(V0));
   }
   internal void Current(){Api.Current();Contexts.Current();
    foreach(object value in(IEnumerable)profile["guards"]){var row=M(value);bool mf=Convert.ToString(row["module"])=="mfc110u.dll";IntPtr module=mf?Mfc:Api.Engine.ImageBase;byte[] bytes=B(Convert.ToString(row["bytes"]));if(mf)NativeMemory.Require(N(row["rva"])>=0&&N(row["rva"])<=mfcImageBytes-bytes.Length,"Guarded strategy close body crosses the loaded MFC module.");
     foreach(object rel in(IEnumerable)row["reloc_offsets"]){int i=N(rel);NativeMemory.Require(i>=0&&i+4<=bytes.Length,"Strategy close relocation differs.");Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(bytes,i)+NativeMemory.U(module)-(mf?0x10000000U:0x400000U))),0,bytes,i,4);}
     NativeMemory.Require(H(bytes)==H(NativeMemory.Bytes(NativeMemory.Add(module,N(row["rva"])),bytes.Length)),"Actual loaded strategy close code differs.");
    }
    NativeMemory.Require(ExportOrdinal(Mfc,new IntPtr(N(profile["mfc_close_ordinal"])))==NativeMemory.Add(Mfc,N(profile["mfc_close_rva"]))&&NativeMemory.Ptr(Api.Engine.Address(N(profile["document_close_iat_rva"])),0)==NativeMemory.Add(Mfc,N(profile["mfc_close_rva"])),"Actual native strategy Doc35 close IAT differs.");
   }
   internal void Owns(ViewState view){Api.Owner(view.Document,"StrategyDocument");Api.Owner(view.View,"StrategyView");
    NativeMemory.Require(NativeMemory.Ptr(NativeMemory.Ptr(view.Document,0),35*4)==Api.Engine.Address(N(profile["document_close_entry_rva"])),"Actual strategy document close virtual differs.");
    var blocks=Api.Base.Blocks();IntPtr canonical=NativeMemory.Add(blocks[view.Id],-4),canonicalContext=NativeMemory.Ptr(canonical,0x10),privateContext=NativeMemory.Ptr(view.Document,0x150);
    NativeMemory.Require(view.Block!=canonical&&NativeMemory.Ptr(view.Document,0x154)==view.Block&&privateContext!=IntPtr.Zero&&privateContext!=canonicalContext&&NativeMemory.Ptr(view.Block,0x10)==privateContext,"Private strategy document must own its distinct block/context exactly.");
    NativeMemory.Require(NativeMemory.I32(privateContext,8)==view.Id&&NativeMemory.I32(canonicalContext,8)==view.Id,"Private/canonical context strategy IDs differ.");
    NativeMemory.Require(Convert.ToString(Contexts.Type(privateContext)["rtti"])==Convert.ToString(Contexts.Type(canonicalContext)["rtti"]),"Private/canonical context concrete types differ.");
    // CDocument auto-delete is required by the original close/dtor chain. No manual delete fallback.
    NativeMemory.Require(NativeMemory.I32(view.Document,0x9C)!=0,"Native strategy document has no original auto-delete ownership.");
   }
  }
  static Dictionary<string,object> CloseState(CloseContract contract,Dictionary<string,object> action){var api=contract.Api;contract.Current();var target=M(action["target"]);int id=N(target["block_id"]);var blocks=api.Base.Blocks();
   NativeMemory.Require(blocks.ContainsKey(id)&&NativeStrategyProfile.ReadName(api.Base.Read.Existing,blocks[id])==Text(target["block_name"]),"Strategy close target native ID/name differs.");
   var views=api.Views();object privateState=null;if(views.ContainsKey(id)){var view=views[id];contract.Owns(view);privateState=new Dictionary<string,object>{{"view",view.Describe()},{"private_context",contract.Contexts.Fields(NativeMemory.Ptr(view.Document,0x150))},{"canonical_context",contract.Contexts.Fields(NativeMemory.Ptr(NativeMemory.Add(blocks[id],-4),0x10))}};}
   return new Dictionary<string,object>{{"abi_profile_sha256",CloseAbiProfileSha},{"typed_abi_profile_sha256",TypedAbiProfileSha},{"block_id",id},{"block_name",target["block_name"]},{"open",views.ContainsKey(id)},{"private_owner",privateState},{"all_current_strategy_models",TypedAllModels(contract.Typed)},{"canonical_context_catalog",contract.Contexts.Catalog()},{"provider_registry_raw",ProviderRegistryRaw(contract.Typed)},{"reference_edges",api.Edges()},{"root_modified",NativeMemory.I32(api.Base.Root,0x48)},{"root_compile_raw",NativeMemory.I32(api.Base.Root,0x114)},{"claim_preimage_uses_serialize",false},{"functional_acceptance_pending",true}};
  }
  internal static Dictionary<string,object> CloseRead(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return CloseState(new CloseContract(e,c,project),action);}
  internal static INativePreparedPageControlEdit ClosePrepare(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new ClosePrepared(new CloseContract(e,c,project),action);}
  sealed class ClosePrepared:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {
   readonly CloseContract contract;readonly Api api;readonly Dictionary<string,object> action,before;readonly int id;readonly bool synchronize;readonly ViewState target;readonly List<object> edges;readonly ArchiveWorkspace archive;
   Dictionary<string,object> applied;bool entered,failed,disposed;
   internal ClosePrepared(CloseContract value,Dictionary<string,object> request){contract=value;api=value.Api;action=request;
    NativeMemory.Require(Convert.ToString(action["kind"])==CloseKind&&Convert.ToString(action["abi_profile_sha256"])==CloseAbiProfileSha,"Strategy close kind/ABI differs.");
    before=CloseState(contract,action);NativePageControlPreparation.Before(action,before);NativeMemory.Require(Object.Equals(before["open"],true),"Native target strategy document is not open.");
    id=N(M(action["target"])["block_id"]);target=api.Views()[id];contract.Owns(target);var after=M(action["after"]);
    NativeMemory.Require(after.Count==3&&after.ContainsKey("disposition")&&after.ContainsKey("open")&&Object.Equals(after["open"],false)&&after.ContainsKey("reference_edges"),"Close after requires explicit disposition/open:false/complete reference_edges.");
    string mode=Convert.ToString(after["disposition"]);NativeMemory.Require(mode=="discard"||mode=="synchronize","Unknown native close disposition.");
    synchronize=mode=="synchronize";edges=ExpectedEdges(after);archive=new ArchiveWorkspace(api);
   }
   public void ValidatePersistence(NativeUsableEditPermit.Plan plan){if(synchronize){api.ChildSync.Validate(target);plan.RequireRelatedStrategyPersistence(action,id);}else if(plan.Commit)plan.RequireRelatedStrategyPersistence(action,id);}
   void UnchangedForeign(Dictionary<string,object> after,bool targetCanonicalMayChange){var old=M(before["all_current_strategy_models"]);var now=M(after["all_current_strategy_models"]);var a=MList(old["canonical"]);var b=MList(now["canonical"]);NativeMemory.Require(a.Count==b.Count,"Closing a document changed canonical strategy count.");
    for(int i=0;i<a.Count;i++){var x=M(a[i]);var y=M(b[i]);NativeMemory.Require(N(x["block_id"])==N(y["block_id"]),"Closing a document reordered canonical strategies.");if(!targetCanonicalMayChange||N(x["block_id"])!=id)NativePageControlPreparation.Same(x,y,"Closing a strategy document changed unrelated canonical rows.");}
    var oldWorking=MList(old["working"]);var newWorking=MList(now["working"]);NativeMemory.Require(newWorking.Count==oldWorking.Count-1,"Exactly the target private strategy document must close.");int j=0;
    foreach(object item in oldWorking){var x=M(item);int currentId=N(M(x["view"])["block_id"]);if(currentId==id)continue;NativeMemory.Require(j<newWorking.Count,"A foreign native strategy document disappeared.");NativePageControlPreparation.Same(x,newWorking[j++],"A foreign native working strategy changed during close.");}
    var oldContexts=MList(before["canonical_context_catalog"]);var newContexts=MList(after["canonical_context_catalog"]);NativeMemory.Require(oldContexts.Count==newContexts.Count,"Closing a strategy document changed canonical context count.");
    for(int i=0;i<oldContexts.Count;i++){var x=M(oldContexts[i]);var y=M(newContexts[i]);NativeMemory.Require(N(x["block_id"])==N(y["block_id"]),"Closing a strategy document reordered canonical contexts.");if(!targetCanonicalMayChange||N(x["block_id"])!=id)NativePageControlPreparation.Same(x,y,"Closing a strategy document changed a foreign canonical context.");}
    NativePageControlPreparation.Same(before["provider_registry_raw"],after["provider_registry_raw"],"Closing a strategy document changed loaded provider definitions.");
   }
   Dictionary<string,object> CanonicalTargetSnapshot(Dictionary<string,object> state){object model=null,context=null;
    foreach(object value in(IEnumerable)M(state["all_current_strategy_models"])["canonical"]){var row=M(value);if(N(row["block_id"])==id){NativeMemory.Require(model==null,"Duplicate close target canonical model.");model=row;}}
    foreach(object value in(IEnumerable)state["canonical_context_catalog"]){var row=M(value);if(N(row["block_id"])==id){NativeMemory.Require(context==null,"Duplicate close target canonical context.");context=row;}}
    NativeMemory.Require(model!=null&&context!=null,"Close target canonical model/context disappeared.");return new Dictionary<string,object>{{"canonical_model",model},{"canonical_context",context}};
   }
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){NativeMemory.Require(!entered&&!failed&&!disposed,"Strategy close already entered/failed/disposed.");NativePageControlPreparation.Same(before,CloseState(contract,action),"Complete strategy close preimage drifted.");
    lease.BeginApply(action);entered=true;try{
     contract.Current();contract.Owns(target);
     if(synchronize){lease.RequireRelatedStrategyPersistence(action,id);IntPtr priorCanonicalContext=NativeMemory.Ptr(api.Base.Blocks()[id],0xC),priorPrivateContext=NativeMemory.Ptr(target.Document,0x150);var contextProjection=ContextNativeCopyExpected(contract.Contexts.Fields(priorCanonicalContext),System.Runtime.InteropServices.Marshal.ReadByte(priorCanonicalContext,0x20),contract.Contexts.Fields(priorPrivateContext),System.Runtime.InteropServices.Marshal.ReadByte(priorPrivateContext,0x20));NativeOperationTrace.BeforeMutation("original-strategy-close-pure-sync-before-owner-release");var childSynchronization=api.ChildSync.Synchronize(target,archive,lease,action);VerifyCanonicalMirror(api,target,archive);
      var canonical=NativeMemory.Add(api.Base.Blocks()[id],-4);NativePageControlPreparation.Same(contextProjection,contract.Contexts.Fields(NativeMemory.Ptr(canonical,0x10)),"Original Doc83 complete context differs from its exact native codec/equality projection.");
     }
     lease.RequireApplying(action);contract.Current();contract.Owns(target);NativeOperationTrace.BeforeMutation("original-strategy-canonical-references-before-private-close");api.RebuildReferences(api.Base.Blocks()[id]);
     lease.RequireApplying(action);NativeMemory.Require(api.Views().ContainsKey(id)&&api.Views()[id].Document==target.Document,"Actual target document changed before original close.");
     contract.Current();contract.Owns(target);NativeOperationTrace.BeforeMutation("original-strategy-doc35-close-private-owner");
     // Doc35 closes frames/views and invokes the original derived destructor. Never touch target pointers after this return.
     var canonicalImmediatelyBeforeClose=CanonicalTargetSnapshot(CloseState(contract,action));
     contract.Close(target.Document);
     NativeMemory.Require(!api.Views().ContainsKey(id),"Original native strategy document remains open; no retry or manual delete.");
     applied=CloseState(contract,action);NativePageControlPreparation.Same(canonicalImmediatelyBeforeClose,CanonicalTargetSnapshot(applied),"Original close changed the synchronized canonical target model/context after its final verified snapshot.");UnchangedForeign(applied,synchronize);NativePageControlPreparation.Same(edges,applied["reference_edges"],"Closed strategy complete registered reference graph differs from explicit expected graph.");
     lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"after",applied},{"disposition",synchronize?"synchronize":"discard"},{"original_close_owns_private_teardown",true},{"synchronization_performed_before_close",synchronize},{"root_save_still_required",synchronize},{"functional_acceptance_pending",true}};
    }catch{failed=true;throw;}
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(entered&&!failed&&!disposed&&applied!=null,"Complete native close Apply is required.");NativePageControlPreparation.Same(applied,CloseState(contract,action),"Closed strategy state changed before flush boundary.");lease.BeginFlush(action);lease.RequireRelatedStrategyPersistence(action,id);
    // Synchronization already had to finish before owner release; no freed document is reused.
    lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"after",applied},{"additional_native_flush_required",false},{"synchronization_already_completed_before_close",synchronize},{"root_save_still_required",synchronize}};
   }
   public void Dispose(){if(disposed)return;disposed=true;archive.Dispose();}
  }
 }
}


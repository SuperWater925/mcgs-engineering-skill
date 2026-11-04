using System;
using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativeEngineeringBatch {
  static partial void AddKinds(List<string> kinds) {
   kinds.Add(NativeSliderFillVisualEditing.Kind); kinds.Add(NativeCurrentTemplateControlOperations.MulButtonVisualKind);
   kinds.Add(NativeButtonActionEditing.Kind);
   kinds.Add(NativeControlEventEditing.Kind);
   kinds.Add(NativeCurrentTemplateControlOperations.CollectionKind);
   kinds.Add(NativeCurrentTemplateControlOperations.AnimationKind);
   kinds.Add(NativeUsableDeviceBatch.DriverProperties.Kind);
   kinds.Add(NativeUsableDeviceBatch.DriverProperties.CatalogKind);
   kinds.AddRange(NativeUsableDeviceBatch.DriverProperties.DeviceTree.Kinds);
   kinds.Add(NativeUsableDeviceBatch.DriverProperties.ReferencedRename.Kind);
   kinds.AddRange(NativeUsableDeviceBatch.DriverProperties.InPlaceProperties.Kinds);
   kinds.AddRange(NativeUsableDeviceBatch.DriverProperties.InstalledDriverAdd.Kinds);
   kinds.Add(NativeStrategyWorkingModelEditing.TypedKind);
   kinds.Add(NativeStrategyWorkingModelEditing.CloseKind);
   kinds.Add(NativeStrategyWorkingModelEditing.AdoptionCompletionKind);
   kinds.AddRange(NativeStrategyTriggerContextEditing.Kinds);
   kinds.AddRange(NativeDataPrototypeEditing.Kinds);
   kinds.Add(NativeDataGroupDeleting.Kind);
   kinds.Add("reference-redirect");
   kinds.Add(NativeReferencedPageEditing.ReferenceSyncKind);
   kinds.Add(NativePictureResources.ContainedReferenceKind);
   kinds.Add(NativeLinguistManagementEditing.Kind);
   kinds.Add(NativeStrategyWorkingModelEditing.TriggerPropertiesKind);
   kinds.Add(NativeStrategyWorkingModelEditing.StandardSvrKind);
   foreach(string kind in NativeStrategyWorkingModelEditing.LifecycleKinds)if(Array.IndexOf(BuiltinKinds,kind)<0)kinds.Add(kind);
  }
  static bool ReadLifecycle(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){if(IsLifecycleStrategy(action))return true;if(action.ContainsKey("abi_profile_sha256"))return false;string k=Kind(action);if(k=="strategy-rename"||k=="strategy-delete")return true;if(k==NativeStrategyTriggerContextEditing.Kind){var t=Map(action["target"]);return NativeStrategyWorkingModelEditing.OpenBlockIds(e,c,p).Contains(Convert.ToInt32(t["block_id"]));}return false;}
  static partial void AdditionalRead(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action,ref Dictionary<string,object> result) {
   string k=Kind(action);
   if(k==NativeSliderFillVisualEditing.Kind){result=NativeSliderFillVisualEditing.Read(e,c,p,action);return;}
   if(k==NativeCurrentTemplateControlOperations.MulButtonVisualKind){result=NativeCurrentTemplateControlOperations.ReadMulButtonVisual(e,c,p,action);return;}
   if(k==NativeStrategyWorkingModelEditing.AdoptionCompletionKind){result=NativeStrategyWorkingModelEditing.AdoptionCompletionRead(e,c,p,action);return;}
   if(k==NativeLinguistManagementEditing.Kind||k==NativeLinguistManagementEditing.ReadKind){result=NativeLinguistManagementEditing.Read(e,c,p,action);return;}
   if(k==NativeStrategyWorkingModelEditing.AdoptionDiagnosticKind){result=NativeStrategyWorkingModelEditing.AdoptionDiagnosticRead(e,c,p,action);return;}
   if(ReadLifecycle(e,c,p,action))result=NativeStrategyWorkingModelEditing.LifecycleRead(e,c,p,action);
   else if(k==NativeButtonActionEditing.Kind)result=NativeButtonActionEditing.Read(e,c,p,action);
   else if(k==NativeControlEventEditing.Kind)result=NativeControlEventEditing.Read(e,c,p,action);
   else if(k==NativeCurrentTemplateControlOperations.CollectionKind)result=NativeCurrentTemplateControlOperations.ReadCollection(e,c,p,action);
   else if(k==NativeCurrentTemplateControlOperations.AnimationKind)result=NativeCurrentTemplateControlOperations.ReadAnimations(e,c,p,action);
   else if(k==NativeUsableDeviceBatch.DriverProperties.Kind)result=NativeUsableDeviceBatch.DriverProperties.Read(e,c,p,action);
   else if(k==NativeUsableDeviceBatch.DriverProperties.CatalogKind)result=NativeUsableDeviceBatch.DriverProperties.Read(e,c,p,action);
   else if(Array.IndexOf(NativeUsableDeviceBatch.DriverProperties.DeviceTree.Kinds,k)>=0)result=NativeUsableDeviceBatch.DriverProperties.DeviceTree.Read(e,c,p,action);
   else if(k==NativeUsableDeviceBatch.DriverProperties.InstalledDriverAdd.Kind)result=NativeUsableDeviceBatch.DriverProperties.InstalledDriverAdd.Read(e,c,p,action);
   else if(k==NativeUsableDeviceBatch.DriverProperties.ReferencedRename.Kind)result=NativeUsableDeviceBatch.DriverProperties.ReferencedRename.Read(e,c,p,action);
   else if(Array.IndexOf(NativeUsableDeviceBatch.DriverProperties.InPlaceProperties.Kinds,k)>=0)result=NativeUsableDeviceBatch.DriverProperties.InPlaceProperties.Read(e,c,p,action);
   else if(k==NativeStrategyWorkingModelEditing.TypedKind)result=NativeStrategyWorkingModelEditing.TypedRead(e,c,p,action);
   else if(k==NativeStrategyWorkingModelEditing.CloseKind)result=NativeStrategyWorkingModelEditing.CloseRead(e,c,p,action);
   else if(Array.IndexOf(NativeStrategyTriggerContextEditing.Kinds,k)>=0)result=NativeStrategyTriggerContextEditing.Read(e,c,p,action);
   else if(k=="strategy-provider-catalog")result=NativeStrategyWorkingModelEditing.ProviderCatalog(e,c,p);
   else if(Array.IndexOf(NativeDataPrototypeEditing.Kinds,k)>=0)result=NativeDataPrototypeEditing.Read(e,c,p,action);
   else if(k==NativeDataGroupDeleting.Kind)result=NativeDataGroupDeleting.Read(e,c,p,action);
   else if(k=="reference-redirect")result=NativeReferencedPageEditing.RedirectRead(e,c,p,action);
   else if(k==NativeReferencedPageEditing.ReferenceSyncKind)result=NativeReferencedPageEditing.ReferenceSyncRead(e,c,p,action);
   else if(k==NativePictureResources.ContainedReferenceKind)result=NativePictureResources.ReadContainedReferenceAction(e,c,p,action);
   else if(k==NativeStrategyWorkingModelEditing.TriggerPropertiesKind)result=NativeStrategyWorkingModelEditing.TriggerPropertiesRead(e,c,p,action);
   else if(k==NativeStrategyWorkingModelEditing.StandardSvrKind)result=NativeStrategyWorkingModelEditing.StandardSvrRead(e,c,p,action);
  }
  static Unit PreparedAdditional(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action,INativePreparedPageControlEdit prepared) {
   return new Unit{Kind=Kind(action),Resource=prepared,Validate=delegate{NativePageControlPreparation.Same(action["before"],ReadAction(e,c,p,action),"Additional native engineering preimage changed before Claim.");},Apply=prepared.Apply,Flush=prepared.Flush};
  }
  static partial void AdditionalPrepare(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action,ref Unit result) {
   string k=Kind(action);
   if(k==NativeSliderFillVisualEditing.Kind){result=PreparedAdditional(e,c,p,action,NativeSliderFillVisualEditing.Prepare(e,c,p,action));return;}
   if(k==NativeCurrentTemplateControlOperations.MulButtonVisualKind){result=PreparedAdditional(e,c,p,action,NativeCurrentTemplateControlOperations.PrepareMulButtonVisual(e,c,p,action));return;}
   if(k==NativeStrategyWorkingModelEditing.AdoptionCompletionKind){result=PreparedAdditional(e,c,p,action,NativeStrategyWorkingModelEditing.AdoptionCompletionPrepare(e,c,p,action));return;}
   if(k==NativeLinguistManagementEditing.Kind){var a=NativeLinguistManagementEditing.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};return;}
   if(IsLifecycleStrategy(action))result=PreparedAdditional(e,c,p,action,NativeStrategyWorkingModelEditing.LifecyclePrepare(e,c,p,action));
   else if(k==NativeButtonActionEditing.Kind){var a=NativeButtonActionEditing.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k==NativeControlEventEditing.Kind){var a=NativeControlEventEditing.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k==NativeCurrentTemplateControlOperations.CollectionKind)result=PreparedAdditional(e,c,p,action,NativeCurrentTemplateControlOperations.PrepareCollection(e,c,p,action));
   else if(k==NativeCurrentTemplateControlOperations.AnimationKind)result=PreparedAdditional(e,c,p,action,NativeCurrentTemplateControlOperations.PrepareAnimations(e,c,p,action));
   else if(k==NativeUsableDeviceBatch.DriverProperties.Kind){var a=NativeUsableDeviceBatch.DriverProperties.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k==NativeUsableDeviceBatch.DriverProperties.CatalogKind){var a=NativeUsableDeviceBatch.DriverProperties.PrepareCatalog(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(Array.IndexOf(NativeUsableDeviceBatch.DriverProperties.DeviceTree.Kinds,k)>=0){var a=NativeUsableDeviceBatch.DriverProperties.DeviceTree.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k==NativeUsableDeviceBatch.DriverProperties.InstalledDriverAdd.Kind){var a=NativeUsableDeviceBatch.DriverProperties.InstalledDriverAdd.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k==NativeUsableDeviceBatch.DriverProperties.ReferencedRename.Kind){var a=NativeUsableDeviceBatch.DriverProperties.ReferencedRename.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(Array.IndexOf(NativeUsableDeviceBatch.DriverProperties.InPlaceProperties.Kinds,k)>=0){var a=NativeUsableDeviceBatch.DriverProperties.InPlaceProperties.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k==NativeStrategyWorkingModelEditing.TypedKind)result=PreparedAdditional(e,c,p,action,NativeStrategyWorkingModelEditing.TypedPrepare(e,c,p,action));
   else if(k==NativeStrategyWorkingModelEditing.CloseKind)result=PreparedAdditional(e,c,p,action,NativeStrategyWorkingModelEditing.ClosePrepare(e,c,p,action));
   else if(Array.IndexOf(NativeStrategyTriggerContextEditing.Kinds,k)>=0){var a=NativeStrategyTriggerContextEditing.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(Array.IndexOf(NativeDataPrototypeEditing.Kinds,k)>=0){var a=NativeDataPrototypeEditing.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k==NativeDataGroupDeleting.Kind){var a=NativeDataGroupDeleting.Prepare(e,c,p,action);result=new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   else if(k=="reference-redirect")result=PreparedAdditional(e,c,p,action,NativeReferencedPageEditing.PrepareRedirectAction(e,c,p,action));
   else if(k==NativeReferencedPageEditing.ReferenceSyncKind)result=PreparedAdditional(e,c,p,action,NativeReferencedPageEditing.PrepareReferenceSync(e,c,p,action));
   else if(k==NativePictureResources.ContainedReferenceKind)result=PreparedAdditional(e,c,p,action,NativePictureResources.PrepareContainedReferenceAction(e,c,p,action));
   else if(k==NativeStrategyWorkingModelEditing.TriggerPropertiesKind)result=PreparedAdditional(e,c,p,action,NativeStrategyWorkingModelEditing.TriggerPropertiesPrepare(e,c,p,action));
   else if(k==NativeStrategyWorkingModelEditing.StandardSvrKind)result=PreparedAdditional(e,c,p,action,NativeStrategyWorkingModelEditing.StandardSvrPrepare(e,c,p,action));
  }
 }
}

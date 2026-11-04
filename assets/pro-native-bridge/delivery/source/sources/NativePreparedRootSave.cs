using System;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativePageDuplicateProfile {
  internal sealed class PreparedRootSave {
   readonly Api api;readonly string path;readonly IntPtr root;
   internal PreparedRootSave(NativeEngine engine,string expected) {
    path=Fixture(expected);api=new Api(engine);root=api.Strategy.RootDoc();
    NativeMemory.Require(CurrentProjectPath(api).Equals(path,StringComparison.OrdinalIgnoreCase),"Prepared root save current project differs.");
    api.Virtual(root,34,SaveDocumentThunk);api.Bind<SaveDocument>("C0DocManage_OnSaveDocument");
   }
   internal Dictionary<string,object> Execute(NativeUsableEditPermit.Lease lease) {
    NativeMemory.Require(api.Strategy.RootDoc()==root&&CurrentProjectPath(api).Equals(path,StringComparison.OrdinalIgnoreCase),"Prepared root save identity changed.");
    lease.BeginRootSave();var result=Save(api,path,null,false);lease.CompleteRootSave();return result;
   }
  }
 }
}

using System;
using System.Collections.Generic;
using System.Globalization;

namespace McgsInternalBridge {
    internal static partial class NativeOperations {
        static partial void DispatchAdditional(Dictionary<string,object> request,object datObj,NativeEngine engine,NativeContext context,ref Dictionary<string,object> result) {
            string op=Text(request,"op"),expected=Text(request,"expected_project");
            switch(op) {
                case "strategy-inspect":result=NativeStrategyProfile.Inspect(engine);break;
                case "strategy-source-diagnose":result=NativeStrategyProfile.DiagnoseSource(engine);break;
                case "strategy-flush-test":result=NativeStrategyProfile.Flush(engine,expected);break;
                case "strategy-replace-test":result=NativeStrategyProfile.Write(engine,expected);break;
                case "label-inspect":result=NativeLabelProfile.Inspect(engine,context);break;
                case "label-set-test":result=NativeLabelProfile.Write(engine,context,expected);break;
                case "page-owner-inspect":
                    RequirePageFixture(expected);result=NativePageDuplicateProfile.InspectOwner(engine,context);break;
                case "native-save":
                    RequirePageFixture(expected);result=NativePageDuplicateProfile.Save(engine,expected);break;
                case "native-save-root-only":
                    RequirePageFixture(expected);result=NativePageDuplicateProfile.SaveRootOnly(engine,expected);break;
                case "page-copy-test":
                    RequirePageFixture(expected);RequirePageSourceId(request);result=NativePageDuplicateProfile.Duplicate(engine,context,expected,2);break;
                case "native-read-tree-named":
                    var nodes=engine.ReadTree(context.Root);var api=new NativeStrategyProfile.Api(engine);
                    foreach(object row in nodes) {
                        var item=(Dictionary<string,object>)row;if(item.ContainsKey("reference"))continue;
                        uint address=UInt32.Parse(Convert.ToString(item["address"]).Substring(2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                        IntPtr pointer=new IntPtr(unchecked((int)address));
                        item["name"]=NativeStrategyProfile.ReadName(api,pointer);item["native_identity_id"]=NativeStrategyProfile.ReadId(api,pointer);
                    }
                    result=new Dictionary<string,object>{{"ok",true},{"op",op},{"nodes",nodes}};break;
            }
            if(result==null)DispatchExtension(request,engine,context,expected,ref result);
        }
        static partial void DispatchExtension(Dictionary<string,object> request,NativeEngine engine,NativeContext context,string expected,ref Dictionary<string,object> result);
    }
}

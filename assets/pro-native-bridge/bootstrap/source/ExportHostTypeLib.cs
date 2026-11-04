using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using TYPEATTR=System.Runtime.InteropServices.ComTypes.TYPEATTR;
using TYPEKIND=System.Runtime.InteropServices.ComTypes.TYPEKIND;

// Standard Windows type-library creation interfaces. The unused placeholders
// preserve slots documented in Microsoft's oaidl.h; no vendor ABI is involved.
[ComImport,Guid("00020406-0000-0000-C000-000000000046"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ICreateTypeLibSave {
    void CreateTypeInfo();void SetName();void SetVersion();void SetGuid();void SetDocString();void SetHelpFileName();void SetHelpContext();void SetLcid();void SetLibFlags();void SaveAllChanges();
}
[ComImport,Guid("0002040E-0000-0000-C000-000000000046"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ICreateTypeInfoEdit {
    void SetGuid();void SetTypeFlags();void SetDocString();void SetHelpContext();void SetVersion();
    void AddRefTypeInfo();void AddFuncDesc();void AddImplType();void SetImplTypeFlags();void SetAlignment();void SetSchema();void AddVarDesc();void SetFuncAndParamNames();void SetVarName();void SetTypeDescAlias();void DefineFuncAsDllEntry();void SetFuncDocString();void SetVarDocString();void SetFuncHelpContext();void SetVarHelpContext();void SetMops();void SetTypeIdldesc();void LayOut();
    void DeleteFuncDesc();void DeleteFuncDescByMemId();void DeleteVarDesc();void DeleteVarDescByMemId();void DeleteImplType(uint index);
}
class TypeLibSink:ITypeLibExporterNotifySink {
    [DllImport("oleaut32.dll",PreserveSig=true)]static extern int LoadRegTypeLib(ref Guid guid,short major,short minor,int lcid,out ITypeLib lib);
    public void ReportEvent(ExporterEventKind kind,int code,string message){Console.Error.WriteLine(kind+": "+message);}
    public object ResolveRef(Assembly assembly){
        Guid guid=Marshal.GetTypeLibGuidForAssembly(assembly);int major,minor;Marshal.GetTypeLibVersionForAssembly(assembly,out major,out minor);
        ITypeLib library;int hr=LoadRegTypeLib(ref guid,(short)major,(short)minor,0,out library);if(hr!=0)Marshal.ThrowExceptionForHR(hr);return library;
    }
}
class ExportHostTypeLib {
    [STAThread]static int Main(string[] args){
        try {
            if(args.Length!=2)throw new ArgumentException("Supply own bootstrap assembly and output TLB.");
            string dll=Path.GetFullPath(args[0]),output=Path.GetFullPath(args[1]);
            if(Path.GetFileName(dll)!="McgsInternalBridge.dll" || Path.GetFileName(output)!="McgsInternalBridge.tlb" || Path.GetDirectoryName(dll)!=Path.GetDirectoryName(output))throw new InvalidOperationException("Unexpected bootstrap paths.");
            Assembly assembly=Assembly.LoadFrom(dll);
            if(assembly.GetName().Name!="McgsInternalBridge")throw new InvalidOperationException("Unexpected assembly identity.");
            object converted=new TypeLibConverter().ConvertAssemblyToTypeLib(assembly,output,TypeLibExporterFlags.ExportAs32Bit,new TypeLibSink());
            ITypeLib library=(ITypeLib)converted;int changed=0;
            for(int i=0;i<library.GetTypeInfoCount();i++) {
                ITypeInfo info;library.GetTypeInfo(i,out info);IntPtr attrPointer;info.GetTypeAttr(out attrPointer);TYPEATTR attr;
                try {attr=(TYPEATTR)Marshal.PtrToStructure(attrPointer,typeof(TYPEATTR));}finally{info.ReleaseTypeAttr(attrPointer);}
                if(attr.typekind!=TYPEKIND.TKIND_COCLASS)continue;
                string name,doc,help;int ctx;info.GetDocumentation(-1,out name,out doc,out ctx,out help);
                if(name!="AddInObj")throw new InvalidOperationException("Unexpected coclass.");
                if(attr.cImplTypes!=2)throw new InvalidOperationException("Expected exactly _Object and IAddInObj before normalization.");
                int href;info.GetRefTypeOfImplType(0,out href);ITypeInfo first;info.GetRefTypeInfo(href,out first);first.GetDocumentation(-1,out name,out doc,out ctx,out help);
                if(name!="_Object")throw new InvalidOperationException("Only implicit managed _Object may be removed.");
                info.GetRefTypeOfImplType(1,out href);ITypeInfo second;info.GetRefTypeInfo(href,out second);second.GetDocumentation(-1,out name,out doc,out ctx,out help);
                if(name!="IAddInObj")throw new InvalidOperationException("Explicit bootstrap interface differs.");
                ((ICreateTypeInfoEdit)info).DeleteImplType(0);
                ((ICreateTypeInfoEdit)info).LayOut();changed++;
                info.GetTypeAttr(out attrPointer);
                try {attr=(TYPEATTR)Marshal.PtrToStructure(attrPointer,typeof(TYPEATTR));if(attr.cImplTypes!=1)throw new InvalidOperationException("Coclass interface count remains invalid.");}finally{info.ReleaseTypeAttr(attrPointer);}
            }
            if(changed!=1)throw new InvalidOperationException("Did not normalize exactly one own coclass.");
            ((ICreateTypeLibSave)converted).SaveAllChanges();
            Console.WriteLine("Exported one-default-interface host-compatible TLB; no registration or deployment performed.");return 0;
        }catch(Exception e){Console.Error.WriteLine(e.ToString());return 1;}
    }
}

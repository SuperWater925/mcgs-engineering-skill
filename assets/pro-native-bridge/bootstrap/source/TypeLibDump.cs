using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using System.Web.Script.Serialization;
using TYPEDESC = System.Runtime.InteropServices.ComTypes.TYPEDESC;
using TYPEATTR = System.Runtime.InteropServices.ComTypes.TYPEATTR;
using TYPELIBATTR = System.Runtime.InteropServices.ComTypes.TYPELIBATTR;
using FUNCDESC = System.Runtime.InteropServices.ComTypes.FUNCDESC;
using ELEMDESC = System.Runtime.InteropServices.ComTypes.ELEMDESC;
using IMPLTYPEFLAGS = System.Runtime.InteropServices.ComTypes.IMPLTYPEFLAGS;
class TypeLibDump {
    [DllImport("oleaut32.dll",CharSet=CharSet.Unicode,PreserveSig=true)] static extern int LoadTypeLibEx(string file,int regkind,out ITypeLib lib);
    static object Describe(ITypeInfo info,TYPEDESC type,int depth) {
        if(depth>4)return "depth limit";
        var v=(VarEnum)type.vt;
        if(v==VarEnum.VT_PTR || v==VarEnum.VT_SAFEARRAY) {
            var child=(TYPEDESC)Marshal.PtrToStructure(type.lpValue,typeof(TYPEDESC));
            return new Dictionary<string,object>{{"kind",v.ToString()},{"element",Describe(info,child,depth+1)}};
        }
        if(v==VarEnum.VT_USERDEFINED) {
            ITypeInfo target;info.GetRefTypeInfo(type.lpValue.ToInt32(),out target);
            string name,doc,help;int ctx;target.GetDocumentation(-1,out name,out doc,out ctx,out help);
            return new Dictionary<string,object>{{"kind",v.ToString()},{"name",name}};
        }
        return v.ToString();
    }
    [STAThread] static int Main(string[] args) {
        Console.OutputEncoding=new UTF8Encoding(false);
        try {
            ITypeLib library;int hr=LoadTypeLibEx(args[0],2,out library);if(hr!=0)Marshal.ThrowExceptionForHR(hr);
            string name,doc,help;int context;library.GetDocumentation(-1,out name,out doc,out context,out help);
            var root=new Dictionary<string,object>{{"file",args[0]},{"read_only",true},{"registered",false},{"name",name},{"documentation",doc}};
            IntPtr libAttr;library.GetLibAttr(out libAttr);
            try {var attr=(TYPELIBATTR)Marshal.PtrToStructure(libAttr,typeof(TYPELIBATTR));root["guid"]=attr.guid;root["syskind"]=attr.syskind.ToString();root["major"]=attr.wMajorVerNum;root["minor"]=attr.wMinorVerNum;}finally{library.ReleaseTLibAttr(libAttr);}
            var types=new List<object>();
            for(int index=0;index<library.GetTypeInfoCount();index++) {
                ITypeInfo info;library.GetTypeInfo(index,out info);info.GetDocumentation(-1,out name,out doc,out context,out help);
                IntPtr pointer;info.GetTypeAttr(out pointer);
                try {
                    var attr=(TYPEATTR)Marshal.PtrToStructure(pointer,typeof(TYPEATTR));
                    var row=new Dictionary<string,object>{{"name",name},{"guid",attr.guid},{"kind",attr.typekind.ToString()},{"flags",attr.wTypeFlags.ToString()},{"documentation",doc}};
                    var functions=new List<object>();
                    for(int member=0;member<attr.cFuncs;member++) {
                        IntPtr descriptor;info.GetFuncDesc(member,out descriptor);
                        try {
                            var function=(FUNCDESC)Marshal.PtrToStructure(descriptor,typeof(FUNCDESC));
                            string[] names=new string[Math.Max(1,function.cParams+1)];int count;info.GetNames(function.memid,names,names.Length,out count);
                            var parameters=new List<object>();
                            for(int parameter=0;parameter<function.cParams;parameter++) {
                                var element=(ELEMDESC)Marshal.PtrToStructure(IntPtr.Add(function.lprgelemdescParam,parameter*Marshal.SizeOf(typeof(ELEMDESC))),typeof(ELEMDESC));
                                parameters.Add(new Dictionary<string,object>{{"name",parameter+1<count?names[parameter+1]:null},{"flags",element.desc.paramdesc.wParamFlags.ToString()},{"type",Describe(info,element.tdesc,0)}});
                            }
                            functions.Add(new Dictionary<string,object>{{"name",count>0?names[0]:null},{"memid",function.memid},{"invoke_kind",function.invkind.ToString()},{"callconv",function.callconv.ToString()},{"vtable_offset",function.oVft},{"parameters",parameters},{"return",Describe(info,function.elemdescFunc.tdesc,0)}});
                        }finally {info.ReleaseFuncDesc(descriptor);}
                    }
                    row["functions"]=functions;
                    var implementations=new List<object>();
                    for(int implementation=0;implementation<attr.cImplTypes;implementation++) {
                        int href;info.GetRefTypeOfImplType(implementation,out href);ITypeInfo target;info.GetRefTypeInfo(href,out target);
                        target.GetDocumentation(-1,out name,out doc,out context,out help);IMPLTYPEFLAGS flags;info.GetImplTypeFlags(implementation,out flags);
                        implementations.Add(new Dictionary<string,object>{{"name",name},{"flags",flags.ToString()}});
                    }
                    row["implemented_types"]=implementations;types.Add(row);
                }finally {info.ReleaseTypeAttr(pointer);}
            }
            root["types"]=types;Console.WriteLine(new JavaScriptSerializer{MaxJsonLength=int.MaxValue}.Serialize(root));return 0;
        }catch(Exception e){Console.WriteLine(new JavaScriptSerializer().Serialize(new{ok=false,error=e.Message}));return 1;}
    }
}

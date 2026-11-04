using System;
using System.IO;
using System.Runtime.InteropServices;

// Build utility for this experiment's own unsigned assembly, not vendor files.
class EmbedTypeLib {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr BeginUpdateResource(string file,bool deleteExisting);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool UpdateResource(IntPtr update,string type,IntPtr name,ushort language,byte[] bytes,uint length);
    [DllImport("kernel32.dll",SetLastError=true)]static extern bool EndUpdateResource(IntPtr update,bool discard);
    static int Main(string[] args) {
        try {
            if(args.Length!=2)throw new ArgumentException("Supply own McgsInternalBridge.dll and McgsInternalBridge.tlb.");
            string dll=Path.GetFullPath(args[0]),tlb=Path.GetFullPath(args[1]);
            if(!String.Equals(Path.GetFileName(dll),"McgsInternalBridge.dll",StringComparison.OrdinalIgnoreCase) ||
               !String.Equals(Path.GetFileName(tlb),"McgsInternalBridge.tlb",StringComparison.OrdinalIgnoreCase) ||
               !String.Equals(Path.GetDirectoryName(dll),Path.GetDirectoryName(tlb),StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Only this bootstrap's same-directory own DLL/TLB is allowed.");
            if(!String.Equals(System.Reflection.AssemblyName.GetAssemblyName(dll).Name,"McgsInternalBridge",StringComparison.Ordinal))
                throw new InvalidOperationException("Unexpected assembly identity.");
            byte[] data=File.ReadAllBytes(tlb);IntPtr update=BeginUpdateResource(dll,false);
            if(update==IntPtr.Zero)throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            bool committed=false;
            try {
                // TYPELIB is a string resource type, not RT_VERSION (numeric 16).
                if(!UpdateResource(update,"TYPELIB",new IntPtr(1),0,data,(uint)data.Length))
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                if(!EndUpdateResource(update,false))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                committed=true;
            }finally {if(!committed)EndUpdateResource(update,true);}
            Console.WriteLine("Embedded TYPELIB/#1 in own bootstrap assembly. No registration was performed.");return 0;
        }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}
    }
}

// Own FontValue16/FontRow20, using the executable's constructors/copy/dtors.
// No fabricated native font object, no project/font-provider field overwrite.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal sealed class NativeOriginalFontValue : IDisposable {
  const string ProfileSha="461045f97202c033a85191b1c1615883f5662ba53f67f4e1a76084f2c0b449e2";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr Construct(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Destroy(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Push(IntPtr self,IntPtr row);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr Copy(IntPtr self,IntPtr source);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr AssignWide(IntPtr self,IntPtr text);
  readonly Construct valueCtor,rowCtor;readonly Destroy valueDtor,rowDtor;
  readonly Push push;readonly Copy copy;readonly AssignWide assign;
  IntPtr storage;bool constructed,disposed;
  internal NativeOriginalFontValue(NativeEngine engine,NativeStrategyProfile.Api shared,Dictionary<string,object> specification) {
   string file=Path.Combine(NativeOperations.TaskRoot,"coverage-20261101","usable-edit-0001","typed-properties","font-value-abi-profile.json");
   NativeMemory.Require(NativeMemory.Hash(file)==ProfileSha,"Original FontValue ABI file differs.");
   var profile=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));
   NativeMemory.Require(Convert.ToInt32(profile["schema"])==1&&NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),engine.ImageSha256,"NativeOriginalFontValue:26:editor")&&Convert.ToInt32(profile["owned_value_size"])==16&&Convert.ToInt32(profile["owned_row_size"])==20,"Original FontValue installed ABI differs.");
   var methods=new Dictionary<string,IntPtr>();uint preferred=unchecked((uint)NativeEngine.Number(profile["preferred_base"]));
   foreach(object item in (IEnumerable)profile["functions"]) {
    var guard=(Dictionary<string,object>)item;string hex=Convert.ToString(guard["bytes"]);byte[] bytes=new byte[hex.Length/2];
    for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
    foreach(object raw in (IEnumerable)guard["reloc_offsets"]){int offset=Convert.ToInt32(raw);NativeMemory.Require(offset>=0&&offset+4<=bytes.Length,"FontValue relocation differs.");Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(bytes,offset)+NativeMemory.U(engine.ImageBase)-preferred)),0,bytes,offset,4);}
    IntPtr address=engine.Address(NativeEngine.Number(guard["rva"]));NativeMemory.Require(BitConverter.ToString(bytes)==BitConverter.ToString(NativeMemory.Bytes(address,bytes.Length)),"Original FontValue native prefix differs: "+guard["name"]);methods.Add(Convert.ToString(guard["name"]),address);
   }
   // Resolve ALL constructors and cleanup/copy delegates before owned allocation.
   valueCtor=engine.Bind<Construct>(methods["FontValueCtor"]);rowCtor=engine.Bind<Construct>(methods["FontRowCtor"]);
   valueDtor=engine.Bind<Destroy>(methods["FontValueDtor"]);rowDtor=engine.Bind<Destroy>(methods["FontRowDtor"]);
   push=engine.Bind<Push>(methods["FontVectorPush"]);copy=engine.Bind<Copy>(methods["FontValueAssign"]);assign=shared.Bind<AssignWide>("CStringAssignWide");
   NativeMemory.Require(specification!=null&&(specification.Count==2||(specification.Count==3&&specification.ContainsKey("row_count")))&&specification.ContainsKey("native_flag")&&specification.ContainsKey("rows")&&specification["native_flag"] is bool,"FontValue requires native_flag Boolean and rows; only derived row_count may accompany them.");
   var rows=new List<Dictionary<string,object>>();var ids=new HashSet<int>();
   foreach(object item in (IEnumerable)specification["rows"]) {
    var row=item as Dictionary<string,object>;NativeMemory.Require(row!=null&&row.Count==5&&row.ContainsKey("language_id")&&row.ContainsKey("face_name")&&row.ContainsKey("height")&&row.ContainsKey("weight")&&row.ContainsKey("italic"),"Font row requires language_id/face_name/height/weight/italic.");
    int id=Integral(row["language_id"]),height=Integral(row["height"]),weight=Integral(row["weight"]);
    NativeMemory.Require(rows.Count<32&&ids.Add(id)&&height>=-4096&&height<=4096&&weight>=0&&weight<=1000&&row["italic"] is bool&&row["face_name"] is string,"Font row has repeated language or invalid LOGFONT fields.");
    string face=(string)row["face_name"];NativeMemory.Require(face.Length>0&&face.Length<=31&&face.IndexOf('\0')<0,"LOGFONT face must fit31 UTF16 units plus NUL.");new UnicodeEncoding(false,false,true).GetBytes(face);rows.Add(row);
   }
   NativeMemory.Require(rows.Count>0,"FontValue must retain at least one explicit language row.");
   if(specification.ContainsKey("row_count"))NativeMemory.Require(Integral(specification["row_count"])==rows.Count,"FontValue derived row_count differs from explicit rows.");
   try {
    storage=Marshal.AllocHGlobal(16);IntPtr made=valueCtor(storage);constructed=true;NativeMemory.Require(made==storage,"Original FontValue constructor returned another pointer.");
    Marshal.WriteByte(storage,(bool)specification["native_flag"]?(byte)1:(byte)0);
    foreach(var row in rows)AppendRow(row);
    var actual=Snapshot(storage);NativeMemory.Require(Convert.ToInt32(actual["row_count"])==rows.Count,"Original FontValue vector push count differs.");
   }catch{Dispose();throw;}
  }
  static int Integral(object value){NativeMemory.Require(value is int||value is long||value is uint||value is short||value is byte,"Font integer must be integral JSON number.");long n=Convert.ToInt64(value,CultureInfo.InvariantCulture);NativeMemory.Require(n>=Int32.MinValue&&n<=Int32.MaxValue,"Font integer overflow.");return (int)n;}
  void AppendRow(Dictionary<string,object> row) {
   IntPtr item=IntPtr.Zero,wide=IntPtr.Zero;bool made=false;
   try {
    item=Marshal.AllocHGlobal(20);IntPtr result=rowCtor(item);made=true;NativeMemory.Require(result==item,"Original FontRow constructor differs.");
    Marshal.WriteInt32(item,0,Integral(row["language_id"]));Marshal.WriteInt32(item,4,(bool)row["italic"]?1:0);
    Marshal.WriteInt32(item,8,Integral(row["weight"]));Marshal.WriteInt32(item,12,Integral(row["height"]));
    wide=Marshal.StringToHGlobalUni((string)row["face_name"]);assign(NativeMemory.Add(item,16),wide);push(NativeMemory.Add(storage,4),item);
   }finally{try{if(made)rowDtor(item);}finally{if(wide!=IntPtr.Zero)Marshal.FreeHGlobal(wide);if(item!=IntPtr.Zero)Marshal.FreeHGlobal(item);}}
  }
  internal void AssignTo(IntPtr destination) {
   NativeMemory.Require(!disposed&&constructed&&storage!=IntPtr.Zero&&EngineEntry.ExpectedUiThreadId>0&&NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"FontValue lifetime/UI-thread differs.");
   NativeMemory.Readable(destination,16);NativeMemory.Require(copy(destination,storage)==destination,"Original FontValue assignment returned another pointer.");
  }
  internal static Dictionary<string,object> Snapshot(IntPtr value) {
   NativeMemory.Readable(value,16);byte flag=Marshal.ReadByte(value);NativeMemory.Require(flag<=1,"FontValue native flag is not Boolean.");
   IntPtr first=NativeMemory.Ptr(value,4),last=NativeMemory.Ptr(value,8),end=NativeMemory.Ptr(value,12);
   uint a=NativeMemory.U(first),b=NativeMemory.U(last),c=NativeMemory.U(end);NativeMemory.Require(a<=b&&b<=c&&(b-a)%20==0&&(c-a)%20==0&&b-a<=32*20&&c-a<=128*20,"FontValue vector range differs.");
   int count=(int)((b-a)/20);var rows=new List<Dictionary<string,object>>();var ids=new HashSet<int>();
   for(int i=0;i<count;i++) {
    IntPtr row=NativeMemory.Add(first,20*i);NativeMemory.Readable(row,20);int id=NativeMemory.I32(row,0),italic=NativeMemory.I32(row,4);
    NativeMemory.Require(ids.Add(id)&&(italic==0||italic==1),"FontValue row language/italic differs.");
    IntPtr text=NativeMemory.Ptr(row,16);NativeMemory.Require(text!=IntPtr.Zero,"FontValue face CString is NULL.");int length=NativeMemory.I32(text,-12);NativeMemory.Require(length>=0&&length<=31,"FontValue face length differs.");
    byte[] raw=NativeMemory.Bytes(text,length*2+2);NativeMemory.Require(raw[raw.Length-1]==0&&raw[raw.Length-2]==0,"FontValue face terminator differs.");
    rows.Add(new Dictionary<string,object>{{"language_id",id},{"italic",italic!=0},{"weight",NativeMemory.I32(row,8)},{"height",NativeMemory.I32(row,12)},{"face_name",new UnicodeEncoding(false,false,true).GetString(raw,0,length*2)}});
   }
   return new Dictionary<string,object>{{"native_flag",flag!=0},{"row_count",count},{"rows",rows}};
  }
  public void Dispose(){if(disposed)return;disposed=true;try{if(constructed){constructed=false;valueDtor(storage);}}finally{if(storage!=IntPtr.Zero){Marshal.FreeHGlobal(storage);storage=IntPtr.Zero;}}}
 }
}

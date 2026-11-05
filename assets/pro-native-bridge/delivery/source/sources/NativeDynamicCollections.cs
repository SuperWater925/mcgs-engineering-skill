// Actual native container lengths and iterative managed traversal, with no sample-size gates.
using System;using System.Collections;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static class NativeDynamicCollections {
  internal static void ValidateBuffer(IntPtr pointer,int count,int stride,string label){
   NativeMemory.Require(count>=0&&stride>0&&(count==0||pointer!=IntPtr.Zero),"Invalid native buffer count/pointer: "+label);
   long bytes=checked((long)count*stride);NativeMemory.Require(bytes<=Int32.MaxValue&&(ulong)NativeMemory.U(pointer)+(ulong)bytes<=0x100000000UL,"Native buffer exceeds x86/CLR representation: "+label);
   for(int offset=0;offset<bytes;){int block=(int)Math.Min(1024*1024,bytes-offset);NativeMemory.Readable(NativeMemory.Add(pointer,offset),block);offset=checked(offset+block);}
  }
  internal static List<IntPtr> ReadDrawList(IntPtr list,IntPtr document,IntPtr expectedTable){
   NativeMemory.Require(NativeMemory.Ptr(list,0)==expectedTable,"Current native drawing-list class differs.");
   IntPtr node=NativeMemory.Ptr(list,4),tail=NativeMemory.Ptr(list,8),previous=IntPtr.Zero;int count=NativeMemory.I32(list,12);
   NativeMemory.Require(count>=0&&((count==0)==(node==IntPtr.Zero))&&((count==0)==(tail==IntPtr.Zero)),"Current native drawing-list count/endpoints differ.");
   var result=new List<IntPtr>();var nodes=new HashSet<uint>();var objects=new HashSet<uint>();
   for(int i=0;i<count;i++){
    NativeMemory.Require(node!=IntPtr.Zero&&nodes.Add(NativeMemory.U(node))&&NativeMemory.Ptr(node,4)==previous,"Current native drawing-list link/cycle differs.");
    IntPtr item=NativeMemory.Ptr(node,8);
    NativeMemory.Require(item!=IntPtr.Zero&&objects.Add(NativeMemory.U(item))&&NativeMemory.Ptr(item,0x64)==document,"Current native drawing-list object identity/document owner differs.");
    result.Add(item);previous=node;node=NativeMemory.Ptr(node,0);
   }
   NativeMemory.Require(node==IntPtr.Zero&&previous==tail,"Current native drawing-list tail/count differs.");return result;
  }
  internal static List<IntPtr> ReadUniquePointerArray(IntPtr array){
   IntPtr data=NativeMemory.Ptr(array,4);int count=NativeMemory.I32(array,8),capacity=NativeMemory.I32(array,12);
   NativeMemory.Require(count>=0&&capacity>=count&&(count==0||data!=IntPtr.Zero),"Current native pointer-array size/capacity/data differs.");
   int bytes=checked(count*4);
   // Keep NativeMemory's per-read limit; validate the actual buffer in chunks.
   for(int offset=0;offset<bytes;){int block=Math.Min(1024*1024,bytes-offset);NativeMemory.Readable(NativeMemory.Add(data,offset),block);offset=checked(offset+block);}
   var result=new List<IntPtr>(count);var identities=new HashSet<uint>();
   for(int i=0;i<count;i++){IntPtr item=NativeMemory.Ptr(data,checked(i*4));NativeMemory.Require(item!=IntPtr.Zero&&identities.Add(NativeMemory.U(item)),"Current native pointer-array item is null or repeated.");result.Add(item);}return result;
  }
  sealed class BuildFrame<TSource,TResult>{internal TSource Source;internal TResult Result;internal int[] Path;internal IList<TSource> Children;internal int Next;}
  internal static TResult BuildTree<TSource,TResult,TKey>(TSource root,int[] path,HashSet<TKey> seen,Func<TSource,TKey> key,Func<TSource,int[],TResult> create,Func<TSource,TResult,IList<TSource>> children,Action<TResult,TResult> append){
   NativeMemory.Require(seen.Add(key(root)),"Current native tree has a cycle or aliased object.");
   TResult result=create(root,path);var stack=new Stack<BuildFrame<TSource,TResult>>();stack.Push(new BuildFrame<TSource,TResult>{Source=root,Result=result,Path=path,Children=children(root,result)});
   while(stack.Count>0){var frame=stack.Peek();if(frame.Next==frame.Children.Count){stack.Pop();continue;}int index=frame.Next++;TSource child=frame.Children[index];NativeMemory.Require(seen.Add(key(child)),"Current native tree has a cycle or aliased object.");
    var childPath=new int[checked(frame.Path.Length+1)];Array.Copy(frame.Path,childPath,frame.Path.Length);childPath[childPath.Length-1]=index;
    TResult output=create(child,childPath);append(frame.Result,output);stack.Push(new BuildFrame<TSource,TResult>{Source=child,Result=output,Path=childPath,Children=children(child,output)});
   }return result;
  }
  internal static IEnumerable<T> DepthFirst<T>(IEnumerable<T> roots,Func<T,IEnumerable<T>> children){
   var stack=new Stack<IEnumerator<T>>();stack.Push(roots.GetEnumerator());try{while(stack.Count>0){var top=stack.Peek();if(!top.MoveNext()){stack.Pop().Dispose();continue;}T item=top.Current;yield return item;stack.Push(children(item).GetEnumerator());}}finally{while(stack.Count>0)stack.Pop().Dispose();}
  }
  sealed class ProjectionFrame<TSource,TResult>{internal TSource Source;internal TResult Result;internal IList<TSource> Children;internal int Next;}
  internal static TResult ProjectTree<TSource,TResult>(TSource root,Func<TSource,TResult> enter,Func<TSource,IList<TSource>> children,Action<TResult,TResult> append,Action<TSource,TResult> finish){
   TResult result=enter(root);var stack=new Stack<ProjectionFrame<TSource,TResult>>();stack.Push(new ProjectionFrame<TSource,TResult>{Source=root,Result=result,Children=children(root)});
   while(stack.Count>0){var frame=stack.Peek();if(frame.Next<frame.Children.Count){TSource child=frame.Children[frame.Next++];TResult output=enter(child);stack.Push(new ProjectionFrame<TSource,TResult>{Source=child,Result=output,Children=children(child)});continue;}
    finish(frame.Source,frame.Result);stack.Pop();if(stack.Count>0)append(stack.Peek().Result,frame.Result);
   }return result;
  }
  sealed class CopyFrame {
   internal IDictionary<string,object> Dictionary;internal IEnumerator<KeyValuePair<string,object>> DictionaryRows;
   internal List<object> List;internal IEnumerator ListRows;
   internal void Dispose(){if(DictionaryRows!=null)DictionaryRows.Dispose();var disposable=ListRows as IDisposable;if(disposable!=null)disposable.Dispose();}
  }
  static CopyFrame CopyContainer(object source,bool canonical,out object result){
   var dictionary=source as IDictionary<string,object>;
   if(dictionary!=null&&(canonical||source is Dictionary<string,object>)){
    IDictionary<string,object> output=canonical?(IDictionary<string,object>)new SortedDictionary<string,object>(StringComparer.Ordinal):new Dictionary<string,object>();result=output;return new CopyFrame{Dictionary=output,DictionaryRows=dictionary.GetEnumerator()};
   }
   var sequence=source as IEnumerable;if(sequence!=null&&!(source is string)){var output=new List<object>();result=output;return new CopyFrame{List=output,ListRows=sequence.GetEnumerator()};}
   result=source;return null;
  }
  internal static object CopyValue(object source,bool canonical){
   object result;CopyFrame initial=CopyContainer(source,canonical,out result);if(initial==null)return result;var stack=new Stack<CopyFrame>();stack.Push(initial);
   try{while(stack.Count>0){var frame=stack.Peek();object value;string key=null;
     if(frame.DictionaryRows!=null){if(!frame.DictionaryRows.MoveNext()){stack.Pop().Dispose();continue;}var pair=frame.DictionaryRows.Current;key=pair.Key;value=pair.Value;}
     else{if(!frame.ListRows.MoveNext()){stack.Pop().Dispose();continue;}value=frame.ListRows.Current;}
     object output;CopyFrame child=CopyContainer(value,canonical,out output);if(frame.Dictionary!=null)frame.Dictionary.Add(key,output);else frame.List.Add(output);if(child!=null)stack.Push(child);
    }return result;
   }finally{while(stack.Count>0)stack.Pop().Dispose();}
  }
  static IEnumerable<object> ChildValues(object value){var row=value as Dictionary<string,object>;if(row!=null){foreach(object child in row.Values)yield return child;yield break;}if(value is IEnumerable&&!(value is string))foreach(object child in(IEnumerable)value)yield return child;}
  internal static IEnumerable<Dictionary<string,object>> DictionaryValues(object value){foreach(object item in DepthFirst<object>(new object[]{value},ChildValues)){var row=item as Dictionary<string,object>;if(row!=null)yield return row;}}
 }
}

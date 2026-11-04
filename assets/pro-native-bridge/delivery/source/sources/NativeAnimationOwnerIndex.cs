using System;
using System.Collections;
using System.Collections.Generic;

namespace McgsInternalBridge {
 // A boundary-local index over an already guarded forest. It performs no native
 // read or mutation and is never retained by a prepared action or across Verify.
 internal sealed class NativeAnimationOwnerIndex<T> {
  readonly Dictionary<string,T> owners=new Dictionary<string,T>(StringComparer.Ordinal);

  internal NativeAnimationOwnerIndex(IEnumerable<T> nodes,Func<T,string> identity) {
   if(nodes==null||identity==null)throw new ArgumentNullException();
   foreach(T node in nodes) {
    string key=identity(node);
    if(String.IsNullOrEmpty(key)||owners.ContainsKey(key))
     throw new InvalidOperationException("Animation forest has an empty or duplicate complete identity.");
    owners.Add(key,node);
   }
  }

  internal void VerifyUnchanged(IEnumerable expectedRows,Func<object,string> identity,
   string changedOwner,Action<object,T> verify) {
   if(expectedRows==null||identity==null||verify==null)throw new ArgumentNullException();
   foreach(object row in expectedRows) {
    string key=identity(row);
    if(String.Equals(key,changedOwner,StringComparison.Ordinal))continue;
    T found;
    if(String.IsNullOrEmpty(key)||!owners.TryGetValue(key,out found))
     throw new InvalidOperationException("Another control disappeared during animation commit.");
    // The caller retains its original raw-list and owned-value comparisons.
    verify(row,found);
   }
  }
 }
}

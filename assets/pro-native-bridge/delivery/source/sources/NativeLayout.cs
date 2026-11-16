// Object fields come from the selected editor's own accessor instructions/RTTI.
// An absent field is a local feature failure, never an author-offset fallback.
namespace McgsInternalBridge {
 internal static class NativeLayout {
  internal static int Offset(string key){return NativeAbiTargetProfiles.LayoutField(key);}
 }
}

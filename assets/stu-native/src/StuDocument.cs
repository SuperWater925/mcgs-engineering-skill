using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
            private delegate IntPtr GetModuleObject(int id);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr InitializeIterator(IntPtr self, IntPtr owner);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void DestroyIterator(IntPtr self);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool MoveIterator(IntPtr self, IntPtr iterator);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int GetCount(IntPtr self);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr NextTopLevelControl(IntPtr list, ref IntPtr position);

            private readonly Context context;
            private StuNativeProfile Abi { get { return context.Abi; } }
            private const int MaxCatalogEntries = 65536;

            private sealed class Window {
                internal IntPtr Page, Service;
                internal int Id;
                internal string Name;
            }

            internal StuDocument(Context context) {
                this.context = context;
            }

            internal List<object> ReadPages() {
                var values = new List<object>();
                VisitWindows(window => values.Add(new Dictionary<string, object> {
                    {"page_id", window.Id}, {"name", window.Name},
                    {"native_document_loaded", context.Ptr(window.Page, "page_document") != IntPtr.Zero}
                }));
                return values;
            }

            internal Dictionary<string, object> ReadPage(int pageId, string pageName) {
                return ReadPage(SelectWindow(pageId, pageName));
            }

            private Dictionary<string, object> ReadPage(Window window) {
                var controls = new List<object>();
                var identities = new List<IntPtr>();
                bool verifyStaticLabel;
                try { Abi.RequireFeature("label-static-read"); verifyStaticLabel = true; }
                catch (InvalidOperationException) { verifyStaticLabel = false; }
                IntPtr owner = VisitControls(window, (i, control, rtti, owned) => {
                    var row = new Dictionary<string, object> {
                        {"catalog_index", i}, {"control_path", new[] { i }}, {"native_class", rtti}, {"document_owned", owned}
                    };
                    if (owned) {
                        row["name"] = context.Text(control, "control_name");
                        row["native_type_id"] = context.Word(control, "control_type_id");
                        row["rect"] = ReadRectangle(control);
                        if (rtti == ".?AVCDrawLabel@@" && Abi.IsTable(control, "label")) {
                            Abi.CheckTable(control, "label");
                            ReadLabel(control).Write(row);
                            if (verifyStaticLabel) {
                                try { row["static_label"] = IsStaticLabel(control); }
                                catch (InvalidOperationException error) { row["static_label_unavailable"] = error.Message; }
                            }
                        } else if (rtti == ".?AVCDrawEdit@@" && Abi.IsTable(control, "input_control")) {
                            Abi.CheckTable(control, "input_control");
                            row["input_variable"] = context.Text(control, "input_variable");
                        }
                    }
                    controls.Add(row);
                    identities.Add(owned ? control : IntPtr.Zero);
                });
                var result = new Dictionary<string, object> {
                    {"page_id", window.Id}, {"name", window.Name}, {"controls", controls},
                    {"control_count", controls.Count}, {"page_dirty", context.Word(owner, "document_dirty")},
                    {"project_dirty", context.Word(context.Root, "document_dirty")}
                };
                try {
                    Abi.RequireFeature("top-level-control-catalog");
                    var top = ReadTopLevelControls(owner);
                    var paths = new Dictionary<IntPtr, int>();
                    for (int i = 0; i < top.Count; i++) paths.Add(top[i], i);
                    for (int i = 0; i < controls.Count; i++) {
                        int index;
                        var row = StuNativeProfile.Map(controls[i]);
                        bool isTopLevel = paths.TryGetValue(identities[i], out index);
                        row["top_level"] = isTopLevel;
                        if (isTopLevel) row["top_level_path"] = new[] { index };
                    }
                    result["top_level_control_count"] = top.Count;
                } catch (InvalidOperationException error) {
                    result["top_level_catalog_unavailable"] = error.Message;
                }
                return result;
            }

            private Window SelectWindow(int pageId, string pageName) {
                Window window = null;
                VisitWindows(candidate => {
                    if (candidate.Id != pageId) return;
                    Require(window == null && candidate.Name == pageName, "The Stu page ID/name is not unique or changed.");
                    window = candidate;
                });
                Require(window != null, "The selected Stu page does not exist.");
                return window;
            }

            private IntPtr VisitControls(Window window, Action<int, IntPtr, string, bool> visit) {
                int index = 0;
                IntPtr document = IntPtr.Zero;
                Enumerate(window.Page, "page", "controls_first", "controls_next", null, candidate => {
                    if (document == IntPtr.Zero) document = PageDocument(window);
                    IntPtr control;
                    string rtti = Abi.Drawing(candidate, out control);
                    bool owned = control != IntPtr.Zero && context.Ptr(control, "control_owner") == document;
                    visit(index++, control, rtti, owned);
                });
                IntPtr actualDocument = PageDocument(window);
                Require(document == IntPtr.Zero || document == actualDocument, "The Stu page document changed during catalog read.");
                return actualDocument;
            }

            private IntPtr PageDocument(Window window) {
                IntPtr document = context.Ptr(window.Page, "page_document");
                Abi.CheckTable(document, "page_document");
                Require(context.Word(document, "page_document_id") == window.Id &&
                    context.Text(document, "page_document_name") == window.Name,
                    "The loaded native document differs from the selected Stu page.");
                return document;
            }

            private List<IntPtr> ReadTopLevelControls(IntPtr document) {
                Abi.CheckTable(document, "page_document");
                IntPtr list = Abi.Bind<NativePointer>("page_top_level_controls")(document);
                Require(list != IntPtr.Zero, "The Stu page has no original top-level drawing list.");
                var first = Abi.Bind<NativePointer>("top_level_first");
                var next = Abi.Bind<NextTopLevelControl>("top_level_next");
                var positions = new HashSet<IntPtr>();
                var identities = new HashSet<IntPtr>();
                var controls = new List<IntPtr>();
                IntPtr position = first(list);
                while (position != IntPtr.Zero) {
                    Require(positions.Count < MaxCatalogEntries && positions.Add(position), "The Stu top-level drawing list is inconsistent.");
                    IntPtr control = StuNativeProfile.Pointer(next(list, ref position), 0);
                    Require(control != IntPtr.Zero && identities.Add(control), "The Stu top-level drawing list repeated a missing or duplicate object.");
                    controls.Add(control);
                }
                return controls;
            }

            private IntPtr UserWindowManager() {
                context.RequireProject();
                Abi.CheckTable(context.Ptr(context.Root, "root_window_model"), "root_window_model");
                IntPtr manager = Abi.Bind<GetModuleObject>("get_module_object")(0);
                Abi.CheckTable(manager, "page_manager");
                return manager;
            }

            private void VisitWindows(Action<Window> visit) {
                IntPtr manager = UserWindowManager();
                IntPtr service = IntPtr.Add(manager, Abi.Offset("page_manager_service"));
                Abi.CheckTable(service, "window_service");
                Enumerate(manager, "page_manager", "page_first", "page_next", "page_count", page => {
                    Abi.CheckTable(page, "page");
                    visit(new Window { Page = page, Service = service,
                        Id = context.Word(page, "page_id"), Name = context.Text(page, "page_name") });
                });
            }

            private void Enumerate(IntPtr owner, string table, string firstRole, string nextRole, string countRole, Action<IntPtr> visit) {
                Abi.CheckSlot(owner, table, 17, firstRole);
                Abi.CheckSlot(owner, table, 18, nextRole);
                if (countRole != null) Abi.CheckSlot(owner, table, 19, countRole);
                var first = Abi.Bind<MoveIterator>(firstRole);
                var next = Abi.Bind<MoveIterator>(nextRole);
                var count = countRole == null ? null : Abi.Bind<GetCount>(countRole);
                var init = Abi.Bind<InitializeIterator>("iterator_init");
                var destroy = Abi.Bind<DestroyIterator>("iterator_destroy");
                int size = Abi.Offset("iterator_size");
                Require(size == 16, "Stu iterator native storage has an unsupported size.");
                IntPtr iterator = Marshal.AllocHGlobal(size);
                bool initialized = false;
                try {
                    Marshal.Copy(new byte[size], 0, iterator, size);
                    init(iterator, owner);
                    initialized = true;
                    var seen = new HashSet<IntPtr>();
                    bool more = first(owner, iterator);
                    int total = count == null ? MaxCatalogEntries : count(owner);
                    Require(total >= 0 && total <= MaxCatalogEntries, "Stu native child count is out of range.");
                    while (more) {
                        Require(context.Ptr(iterator, "iterator_owner") == owner && seen.Count < total,
                            "Stu native child iterator owner/count differs.");
                        IntPtr item = context.Ptr(iterator, "iterator_item");
                        Require(item != IntPtr.Zero && seen.Add(item), "Stu child iterator produced a missing or duplicate object.");
                        visit(item);
                        more = next(owner, iterator);
                    }
                    Require(count == null || (seen.Count == total && count(owner) == total), "Stu native child count changed.");
                } finally {
                    try { if (initialized) destroy(iterator); }
                    finally { Marshal.FreeHGlobal(iterator); }
                }
            }
        }
    }
}

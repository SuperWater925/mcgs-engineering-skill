using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void SetNativeFlag(IntPtr self, int value);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool SavePage(IntPtr self, IntPtr page);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int SaveRoot(IntPtr self, IntPtr project);

            [DllImport("user32.dll")]
            [return: MarshalAs(UnmanagedType.Bool)]
            private static extern bool IsChild(IntPtr parent, IntPtr child);

            private static void BeginPageReceipt(Dictionary<string, object> receipt) {
                receipt["write_attempted"] = false;
                receipt["native_result_may_be_partial"] = false;
                receipt["completed_count"] = 0;
                receipt["view_refresh_verified"] = false;
                receipt["page_save_verified"] = false;
                receipt["root_save_verified"] = false;
                receipt["automatic_retry"] = false;
                receipt["changes"] = new List<object>();
                receipt["operation_phase"] = "validate_preimage";
            }

            private static void FailPageWrite(Dictionary<string, object> receipt, InvalidOperationException error) {
                receipt["ok"] = false;
                bool attempted = Object.Equals(receipt["write_attempted"], true);
                receipt["native_result_may_be_partial"] = attempted;
                receipt["status"] = attempted ? "native_partial_state" : "native_preflight_rejected";
                receipt["error"] = error.Message;
            }

            private sealed class PageWrite {
                private readonly StuDocument owner;
                private readonly Window window;
                private readonly IntPtr document;
                private readonly Dictionary<string, object> receipt;
                private readonly SetNativeFlag markPage, markRoot, invalidate;
                private readonly NativePointer viewGetter;
                private readonly NativeVoid update;
                private readonly SavePage storePage;
                private readonly SaveRoot storeRoot;
                private ActiveView view;
                private IntPtr drawing;

                internal PageWrite(StuDocument owner, Window window, IntPtr document, Dictionary<string, object> receipt) {
                    this.owner = owner;
                    this.window = window;
                    this.document = document;
                    this.receipt = receipt;
                    RequireClean();
                    var abi = owner.Abi;
                    abi.CheckSlot(document, "page_document", 27, "set_page_modified");
                    abi.CheckSlot(owner.context.Root, "root", 27, "set_root_modified");
                    abi.CheckSlot(window.Service, "window_service", 12, "save_page");
                    abi.CheckSlot(owner.context.Root, "root", 34, "save_root");
                    markPage = abi.Bind<SetNativeFlag>("set_page_modified");
                    markRoot = abi.Bind<SetNativeFlag>("set_root_modified");
                    viewGetter = abi.Bind<NativePointer>("get_drawing_view");
                    invalidate = abi.Bind<SetNativeFlag>("invalidate_drawing_view");
                    update = abi.Bind<NativeVoid>("update_drawing_view");
                    storePage = abi.Bind<SavePage>("save_page");
                    storeRoot = abi.Bind<SaveRoot>("save_root");
                }

                internal void Begin(Action verifyBefore) {
                    receipt["operation_phase"] = "activate_view";
                    view = owner.EnsureActiveView(window, document, receipt);
                    drawing = DrawingView();
                    RequireClean();
                    verifyBefore();
                    owner.RequireActiveView(window, view);
                    receipt["operation_phase"] = "mark_document";
                    receipt["read_only"] = false;
                    receipt["write_attempted"] = true;
                    markPage(document, 1);
                    markRoot(owner.context.Root, 1);
                    Require(Dirty(document) == 1 && Dirty(owner.context.Root) == 1,
                        "Stu did not retain the native page and root modified flags.");
                    owner.RequireActiveView(window, view);
                }

                internal void RequireActive() {
                    owner.RequireActiveView(window, view);
                }

                internal void RefreshAndSave(Action verifyAfterRefresh, Action verifyAfterSave) {
                    receipt["operation_phase"] = "refresh_view";
                    owner.RequireActiveView(window, view);
                    Require(DrawingView() == drawing, "The original Stu drawing view changed before refresh.");
                    invalidate(drawing, 1);
                    update(drawing);
                    owner.RequireActiveView(window, view);
                    receipt["view_refresh_verified"] = true;
                    verifyAfterRefresh();

                    receipt["operation_phase"] = "save_page";
                    bool pageSaved = storePage(window.Service, window.Page);
                    receipt["native_page_save_return"] = pageSaved;
                    Require(pageSaved && Dirty(document) == 0, "The original Stu page save did not complete.");
                    receipt["page_save_verified"] = true;
                    owner.RequireActiveView(window, view);

                    receipt["operation_phase"] = "save_root";
                    IntPtr filename = Marshal.StringToHGlobalUni(owner.context.Project);
                    try {
                        int result = storeRoot(owner.context.Root, filename);
                        receipt["native_root_save_return"] = result;
                        Require(result == 1 && Dirty(owner.context.Root) == 0, "The original Stu root save did not complete.");
                    } finally { Marshal.FreeHGlobal(filename); }
                    receipt["root_save_verified"] = true;
                    owner.RequireActiveView(window, view);
                    verifyAfterSave();
                }

                private IntPtr DrawingView() {
                    IntPtr current = viewGetter(view.Document);
                    owner.Abi.CheckTable(current, "drawing_view");
                    IntPtr hwnd = owner.context.Ptr(current, "drawing_view_hwnd");
                    Require(hwnd != IntPtr.Zero && owner.context.Ptr(current, "drawing_view_document") == view.Document &&
                        IsChild(view.ChildHwnd, hwnd), "The original Stu drawing view is outside the active page frame.");
                    return current;
                }

                private int Dirty(IntPtr ownerDocument) {
                    return owner.context.Word(ownerDocument, "document_dirty");
                }

                private void RequireClean() {
                    Require(Dirty(document) == 0 && Dirty(owner.context.Root) == 0,
                        "The Stu page or project has unrelated unsaved modifications.");
                }
            }
        }
    }
}

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private sealed partial class StuDocument {
            private const uint MdiActivate = 0x222, MdiGetActive = 0x229, AncestorRoot = 2;

            [DllImport("user32.dll")]
            private static extern IntPtr GetParent(IntPtr hwnd);
            [DllImport("user32.dll")]
            private static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
            [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
            private static extern int GetClassNameW(IntPtr hwnd, StringBuilder name, int capacity);
            [DllImport("user32.dll", ExactSpelling = true)]
            private static extern IntPtr SendMessageW(IntPtr hwnd, uint message, IntPtr wparam, IntPtr lparam);

            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr GetPageDocument(IntPtr service, int id);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int OpenPage(IntPtr frame, int id);
            [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool ProbeFrame(IntPtr document, out IntPtr frame);
            private sealed class ActiveView {
                internal IntPtr Frame, Document, Child, ChildHwnd, MdiClient;
                internal bool IsActive { get { return SendMessageW(MdiClient, MdiGetActive, IntPtr.Zero, IntPtr.Zero) == ChildHwnd; } }
            }

            internal void OpenView(int pageId, string pageName, Dictionary<string, object> receipt) {
                var window = SelectWindow(pageId, pageName);
                IntPtr document = GetDocumentForView(window);
                EnsureActiveView(window, document, receipt);
            }

            private IntPtr GetDocumentForView(Window window) {
                IntPtr document = context.Ptr(window.Page, "page_document");
                if (document == IntPtr.Zero) {
                    Abi.CheckSlot(window.Service, "window_service", 7, "get_page_document");
                    document = Abi.Bind<GetPageDocument>("get_page_document")(window.Service, window.Id);
                }
                Require(document != IntPtr.Zero && document == PageDocument(window),
                    "Stu did not resolve the original document for this page.");
                return document;
            }

            private ActiveView EnsureActiveView(Window window, IntPtr document, Dictionary<string, object> receipt) {
                context.RequireProject();
                IntPtr frame = Abi.Bind<GetApplication>("get_main_frame")();
                Abi.CheckTable(frame, "frame");
                var info = new Dictionary<string, object> {
                    {"page_id", window.Id}, {"page", window.Name}, {"exact_page_is_active", false},
                    {"opened_new_view", false}, {"activated_existing_view", false},
                    {"native_open_called", false}, {"system_foreground_requested", false}, {"system_maximize_requested", false}
                };
                receipt["page_view"] = info;
                ActiveView view = ProbeView(frame, document);
                if (view == null) {
                    Abi.RequireFeature("page-view-open");
                    Require(StuNativeProfile.IsEmptyString(document, Abi.Offset("document_password")),
                        "Stu cannot open the protected page without its original password workflow.");
                    CheckRoomToOpen(frame);
                    context.RequireProject();
                    receipt["read_only"] = false;
                    info["native_open_called"] = true;
                    info["native_open_return"] = Abi.Bind<OpenPage>("open_page")(frame, window.Id);
                    Require(PageDocument(window) == document, "The original Stu page document changed while opening its view.");
                    view = ProbeView(frame, document);
                    Require(view != null, "The original Stu page opener did not produce the selected page frame.");
                    info["opened_new_view"] = true;
                }
                if (!view.IsActive) {
                    receipt["read_only"] = false;
                    info["mdi_activate_called"] = true;
                    SendMessageW(view.MdiClient, MdiActivate, view.ChildHwnd, IntPtr.Zero);
                    info["activated_existing_view"] = !Object.Equals(info["opened_new_view"], true);
                }
                RequireActiveView(window, view);
                info["exact_page_is_active"] = true;
                return view;
            }

            private void CheckRoomToOpen(IntPtr frame) {
                IntPtr template = context.Ptr(frame, "designer_template_offset");
                Abi.CheckSlot(template, "designer_template", 23, "template_first_document");
                Abi.CheckSlot(template, "designer_template", 24, "template_next_document");
                int limit = Abi.Bind<NativeResult>("max_open_views")(IntPtr.Zero);
                Require(limit > 0 && limit <= MaxCatalogEntries, "The original Stu open-page capacity is invalid.");
                var first = Abi.Bind<FirstDocument>("template_first_document");
                var next = Abi.Bind<NextDocument>("template_next_document");
                var seen = new HashSet<IntPtr>();
                IntPtr position = first(template);
                while (position != IntPtr.Zero) {
                    Require(seen.Count < limit - 1 && seen.Add(position), "The original Stu designer has no slot for another page.");
                    Require(next(template, ref position) != IntPtr.Zero, "The original Stu drawing template contains no document at its current iterator.");
                }
            }

            private ActiveView ProbeView(IntPtr frame, IntPtr document) {
                IntPtr child;
                bool exists = Abi.Bind<ProbeFrame>("probe_drawing_frame")(document, out child);
                if (!exists) return null;
                Abi.CheckTable(child, "designer_child");
                IntPtr hwnd = context.Ptr(child, "designer_child_hwnd");
                IntPtr main = context.Ptr(frame, "frame_hwnd");
                Require(hwnd != IntPtr.Zero && main != IntPtr.Zero, "The Stu drawing child or main window has no HWND.");
                IntPtr client = GetParent(hwnd);
                var name = new StringBuilder(64);
                uint owner, childOwner, clientOwner;
                uint thread = (uint)GetCurrentThreadId();
                Require(client != IntPtr.Zero && GetClassNameW(client, name, name.Capacity) != 0 &&
                    String.Equals(name.ToString(), "MDIClient", StringComparison.OrdinalIgnoreCase) &&
                    GetAncestor(client, AncestorRoot) == main &&
                    GetWindowThreadProcessId(main, out owner) == thread &&
                    GetWindowThreadProcessId(client, out clientOwner) == thread && clientOwner == owner &&
                    GetWindowThreadProcessId(hwnd, out childOwner) == thread && childOwner == owner,
                    "The original Stu drawing frame is not a child of its current editor-thread MDI client.");
                return new ActiveView { Frame = frame, Document = document, Child = child, ChildHwnd = hwnd, MdiClient = client };
            }

            private void RequireActiveView(Window window, ActiveView view) {
                context.RequireProject();
                Require(PageDocument(window) == view.Document, "The selected Stu page document changed.");
                ActiveView current = ProbeView(view.Frame, view.Document);
                Require(current != null && current.Child == view.Child && current.ChildHwnd == view.ChildHwnd &&
                    current.MdiClient == view.MdiClient && current.IsActive,
                    "The actual active Stu MDI page differs from the selected page.");
            }
        }
    }
}

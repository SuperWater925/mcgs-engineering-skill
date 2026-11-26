using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string PageCreateAction = "page-native-create";
        private const string PageCopyAction = "page-native-copy";

        private static bool IsPageStructureAction(string action) { return action == PageCreateAction || action == PageCopyAction; }

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool RenameUserPage(IntPtr service, IntPtr oldName, IntPtr newName);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PageStringConstructor(IntPtr self, IntPtr text);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void PageArchiveTransfer(IntPtr list, int sourceId, IntPtr archive);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PageMemoryFileConstructor(IntPtr self, uint growth);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PageArchiveConstructor(IntPtr self, IntPtr file, uint mode, int bufferSize, IntPtr buffer);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate long PageMemoryFileSeek(IntPtr self, long distance, uint origin);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int SelectWorkbenchTab(IntPtr frame, int index);

            [DllImport("user32.dll", ExactSpelling = true, CharSet = CharSet.Unicode)]
            private static extern IntPtr FindWindowExW(IntPtr parent, IntPtr after, string nativeClass, string caption);
            [DllImport("user32.dll", ExactSpelling = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            private static extern bool IsWindowVisible(IntPtr hwnd);

            internal void ApplyPageStructure(string action, IntPtr mainWindow, object rawOptions, Dictionary<string, object> result) {
                bool copying = action == PageCopyAction;
                BeginPageReceipt(result);
                result["native_saved"] = false;
                result["native_page_save_called"] = false;
                result["post_save_page_readback_verified"] = false;
                result["original_active_view_preserved"] = false;
                Dictionary<int, Window> before = null;
                AuthoringWorkbench workbench = null;
                try {
                    VerifyFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == (copying ? 4 : 2) && options.ContainsKey("page_name") && options.ContainsKey("expected_page_count") &&
                        (!copying || (options.ContainsKey("source_page_id") && options.ContainsKey("source_page_name"))),
                        "Stu page creation needs an exact name and catalog count, and copying also needs the original page identity.");
                    string targetName = NativeEngineeringDeliveryLayout.Value(options, "page_name");
                    Require(!String.IsNullOrWhiteSpace(targetName) && targetName.IndexOfAny(new[] { '\r', '\n' }) < 0,
                        "The requested Stu user-window name is empty or contains a line break.");
                    int expectedCount = StuNativeProfile.Number(options["expected_page_count"]);
                    Require(expectedCount >= 0, "The expected Stu page count is invalid.");

                    context.RequireProject();
                    IntPtr frame;
                    workbench = OpenAuthoringWorkbench(mainWindow, result, "authoring_user_list_index", "user_window_workbench", out frame);
                    IntPtr list = workbench.TargetList;
                    before = AuthoringPages();
                    Require(before.Count == expectedCount, "The current Stu page count differs from its preimage.");
                    foreach (var page in before.Values)
                        Require(!String.Equals(page.Name, targetName, StringComparison.OrdinalIgnoreCase), "The requested Stu user-window name already exists.");

                    Window source = null;
                    List<object> sourceControls = null;
                    if (copying) {
                        int sourceId = StuNativeProfile.Number(options["source_page_id"]);
                        string sourceName = NativeEngineeringDeliveryLayout.Value(options, "source_page_name");
                        Require(before.TryGetValue(sourceId, out source) && source.Name == sourceName,
                            "The original Stu source page ID or name differs from its preimage.");
                        IntPtr sourceDoc = GetDocumentForView(source);
                        RequireEmptyPageProtection(sourceDoc);
                        Require(context.Word(sourceDoc, "document_dirty") == 0, "The original Stu source page has unsaved changes.");
                        sourceControls = AuthoringControls(source);
                        Abi.CheckSlot(list, "user_window_workbench", 92, "copy_user_page_archive");
                        result["source_page_id"] = source.Id;
                        result["source_page_name"] = source.Name;
                        result["copy_mode"] = "native-page-archive";
                    } else Abi.CheckSlot(list, "user_window_workbench", 100, "create_user_page");

                    Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                    Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                    Abi.CheckSlot(context.Root, "root", 34, "save_root");
                    var modified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                    var mark = Abi.Bind<SetNativeFlag>("set_root_modified");
                    using (var target = new AuthoringPageString(Abi, targetName))
                    using (var archive = copying ? new AuthoringPageArchive(Abi, list) : null) {
                        if (copying) archive.Capture(source.Id);
                        workbench.Activate();
                        context.RequireProject();
                        Require(modified(context.Root) == 0 && context.Word(context.Root, "document_dirty") == 0,
                            "The current Stu project has unsaved changes.");
                        result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, modified, false);

                        result["read_only"] = false;
                        result["write_attempted"] = true;
                        result["operation_phase"] = "native_page_registration";
                        mark(context.Root, 1);
                        Require(modified(context.Root) != 0, "Stu did not retain the original project modified flag.");
                        if (copying) archive.RegisterCopy();
                        else Abi.Bind<NativeVoid>("create_user_page")(list);

                        Window added = ConfirmPageAddition(before, AuthoringPages());
                        Window named = added;
                        if (added.Name != targetName) {
                            workbench.RequireTargetActive();
                            result["operation_phase"] = "native_page_rename";
                            Abi.CheckSlot(added.Service, "window_service", 5, "rename_user_page");
                            using (var generated = new AuthoringPageString(Abi, added.Name))
                                Require(Abi.Bind<RenameUserPage>("rename_user_page")(added.Service, generated.Storage, target.Storage),
                                    "The original Stu user-window name could not be assigned.");
                            named = ConfirmPageAddition(before, AuthoringPages());
                        }
                        Require(named.Id == added.Id && named.Page == added.Page && named.Name == targetName,
                            "The original Stu new page ID or name differs after registration.");
                        int controls = VerifyPageContents(named, source, sourceControls);
                        workbench.RequireTargetActive();

                        SaveAuthoredPage(named, result);
                        Window saved = ConfirmPageAddition(before, AuthoringPages());
                        Require(saved.Id == named.Id && saved.Page == named.Page && saved.Name == targetName &&
                            VerifyPageContents(saved, source, sourceControls) == controls &&
                            context.Word(PageDocument(saved), "document_dirty") == 0,
                            "The original Stu new page could not be verified after saving.");
                        result["post_save_page_readback_verified"] = true;
                        result["new_page_id"] = saved.Id;
                        result["new_page_name"] = saved.Name;
                        result["top_level_control_count"] = controls;
                        result["page_count"] = before.Count + 1;
                    }
                    result["native_saved"] = true;
                    result["completed_count"] = 1;
                    result["operation_phase"] = "complete";
                    result["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    FailPageWrite(result, error);
                    if (before != null && Object.Equals(result["write_attempted"], true)) ObserveAddedPage(before, result);
                } finally {
                    if (workbench != null && workbench.Entered) {
                        try { workbench.Restore(); }
                        catch (InvalidOperationException error) {
                            result["view_restore_error"] = error.Message;
                            if (Object.Equals(result["ok"], true)) FailPageWrite(result, error);
                        }
                    }
                }
            }

            private AuthoringWorkbench OpenAuthoringWorkbench(IntPtr mainWindow, Dictionary<string, object> result,
                string indexRole, string tableRole, out IntPtr frame) {
                frame = Abi.Bind<GetApplication>("get_main_frame")();
                Abi.CheckTable(frame, "frame");
                Require(context.Ptr(frame, "frame_hwnd") == mainWindow, "The original Stu MDI owner differs from the captured window.");
                IntPtr mdi = FindWindowExW(mainWindow, IntPtr.Zero, "MDIClient", null);
                uint owner = 0, mdiOwner;
                Require(mdi != IntPtr.Zero && FindWindowExW(mainWindow, mdi, "MDIClient", null) == IntPtr.Zero &&
                    GetWindowThreadProcessId(mainWindow, out owner) == (uint)GetCurrentThreadId() &&
                    GetWindowThreadProcessId(mdi, out mdiOwner) == (uint)GetCurrentThreadId() && mdiOwner == owner,
                    "Stu authoring requires its verified internal MDI client.");
                return new AuthoringWorkbench(this, mdi, mainWindow, owner, indexRole, tableRole, result);
            }

            private sealed class AuthoringWorkbench {
                private readonly IntPtr mdi, frame, hwnd, tab, listHwnd, previousActive;
                private readonly int index, previousTab;
                private readonly uint owner;
                private readonly NativeResult getTab;
                private readonly SelectWorkbenchTab selectTab;
                private readonly Dictionary<string, object> result, state;
                internal readonly IntPtr TargetList;
                internal bool Entered { get; private set; }

                internal AuthoringWorkbench(StuDocument author, IntPtr mdi, IntPtr mainWindow, uint owner,
                    string indexRole, string tableRole, Dictionary<string, object> result) {
                    this.mdi = mdi;
                    this.owner = owner;
                    this.result = result;
                    var abi = author.Abi;
                    var context = author.context;
                    frame = context.Ptr(context.App, "authoring_app_workbench");
                    abi.CheckTable(frame, "authoring_workbench");
                    hwnd = context.Ptr(frame, "frame_hwnd");
                    Require(IsOwnedMdiChild(hwnd), "The original Stu workbench is not an internal MDI child.");
                    IntPtr lists = IntPtr.Add(frame, abi.Offset("authoring_workbench_lists"));
                    abi.CheckTable(lists, "authoring_workbench_lists");
                    int count = context.Word(lists, "pointer_array_count");
                    index = abi.Offset(indexRole);
                    Require(index >= 0 && index < count && count <= context.Word(lists, "pointer_array_capacity"),
                        "The original Stu workbench list is unavailable.");
                    TargetList = StuNativeProfile.Pointer(context.Ptr(lists, "pointer_array_data"), checked(index * IntPtr.Size));
                    abi.CheckTable(TargetList, tableRole);
                    listHwnd = context.Ptr(TargetList, "frame_hwnd");
                    tab = IntPtr.Add(frame, abi.Offset("authoring_workbench_tab"));
                    abi.CheckTable(tab, "authoring_tab_control");
                    IntPtr tabHwnd = context.Ptr(tab, "frame_hwnd");
                    Require(IsOwnedWindow(listHwnd) && IsOwnedWindow(tabHwnd) && GetAncestor(listHwnd, AncestorRoot) == mainWindow &&
                        IsChild(hwnd, listHwnd) && IsChild(hwnd, tabHwnd), "The original Stu workbench tab or list has no verified internal pane.");
                    getTab = abi.Bind<NativeResult>("get_workbench_tab_selection");
                    selectTab = abi.Bind<SelectWorkbenchTab>("select_user_workbench_tab");
                    previousTab = getTab(tab);
                    Require(previousTab >= 0 && previousTab < count, "The original Stu workbench has no current tab to preserve.");
                    previousActive = ActiveChild();
                    Require(previousActive == IntPtr.Zero || IsOwnedMdiChild(previousActive), "The existing Stu active child cannot be verified.");
                    result["original_view_was_active"] = previousActive != IntPtr.Zero;
                    state = new Dictionary<string, object> {
                        {"target_tab_index", index}, {"previous_tab_index", previousTab}, {"active_before_write", false},
                        {"system_foreground_requested", false}, {"system_maximize_requested", false}
                    };
                    result["workbench_view"] = state;
                }

                internal void Activate() {
                    Entered = true;
                    if (ActiveChild() != hwnd) {
                        result["read_only"] = false;
                        SendMessageW(mdi, MdiActivate, hwnd, IntPtr.Zero);
                    }
                    Require(ActiveChild() == hwnd, "The original Stu workbench did not become the active MDI child.");
                    if (getTab(tab) != index) {
                        result["read_only"] = false;
                        selectTab(frame, index);
                    }
                    RequireTargetActive();
                    state["active_before_write"] = true;
                }

                internal void RequireTargetActive() {
                    Require(ActiveChild() == hwnd && getTab(tab) == index && IsWindowVisible(listHwnd),
                        "The Stu workbench did not retain its original active tab and visible list.");
                }

                internal void RefreshTarget() {
                    RequireTargetActive();
                    selectTab(frame, index);
                    RequireTargetActive();
                    state["target_tab_refreshed"] = true;
                }

                internal void Restore() {
                    Require(IsOwnedMdiChild(hwnd), "The original Stu workbench is no longer available for restoring its tab.");
                    if (getTab(tab) != previousTab) selectTab(frame, previousTab);
                    state["previous_tab_restored"] = getTab(tab) == previousTab;
                    if (previousActive != IntPtr.Zero && ActiveChild() != previousActive) {
                        Require(IsOwnedMdiChild(previousActive), "The earlier Stu active MDI child is unavailable.");
                        SendMessageW(mdi, MdiActivate, previousActive, IntPtr.Zero);
                    }
                    bool restored = previousActive == IntPtr.Zero || ActiveChild() == previousActive;
                    result["original_active_view_preserved"] = restored;
                    state["active_after_action"] = ActiveChild() == hwnd;
                    Require(restored && Object.Equals(state["previous_tab_restored"], true),
                        "The earlier Stu MDI position or tab could not be restored.");
                }

                private IntPtr ActiveChild() { return SendMessageW(mdi, MdiGetActive, IntPtr.Zero, IntPtr.Zero); }
                private bool IsOwnedMdiChild(IntPtr window) { return IsOwnedWindow(window) && GetParent(window) == mdi; }
                private bool IsOwnedWindow(IntPtr window) {
                    uint process;
                    return window != IntPtr.Zero && GetWindowThreadProcessId(window, out process) == (uint)GetCurrentThreadId() && process == owner;
                }
            }

            private Dictionary<int, Window> AuthoringPages() {
                var pages = new Dictionary<int, Window>();
                VisitWindows(page => {
                    Require(page.Id >= 0 && !String.IsNullOrWhiteSpace(page.Name) && !pages.ContainsKey(page.Id),
                        "The original Stu page catalog contains an invalid or repeated page identity.");
                    pages.Add(page.Id, page);
                });
                return pages;
            }

            private static Window ConfirmPageAddition(Dictionary<int, Window> before, Dictionary<int, Window> after) {
                Require(after.Count == before.Count + 1, "The Stu editor did not register exactly one new page.");
                Window added = null;
                foreach (var item in after) {
                    Window original;
                    if (before.TryGetValue(item.Key, out original))
                        Require(item.Value.Page == original.Page && item.Value.Name == original.Name && item.Value.Service == original.Service,
                            "The native action changed an existing Stu page identity.");
                    else {
                        Require(added == null, "The native action registered more than one Stu page.");
                        added = item.Value;
                    }
                }
                Require(added != null, "The Stu editor has no new page identity.");
                return added;
            }

            private void RequireEmptyPageProtection(IntPtr document) {
                Require(StuNativeProfile.IsEmptyString(document, Abi.Offset("document_password")),
                    "The original Stu source or new page has a protected definition.");
            }

            private List<object> AuthoringControls(Window page) { return (List<object>)ReadPage(page)["controls"]; }

            private int VerifyPageContents(Window candidate, Window source, List<object> sourceControls) {
                IntPtr doc = GetDocumentForView(candidate);
                RequireEmptyPageProtection(doc);
                int count = ReadTopLevelControls(doc).Count;
                if (source == null) Require(count == 0, "The original new Stu page is not empty.");
                else {
                    Require(ReadTopLevelControls(PageDocument(source)).Count == count &&
                        SameAuthoringControls(sourceControls, AuthoringControls(candidate)) &&
                        SameAuthoringControls(sourceControls, AuthoringControls(source)),
                        "The original Stu page copy differs in source or copied control catalog.");
                }
                return count;
            }

            private static bool SameAuthoringControls(List<object> left, List<object> right) {
                if (left.Count != right.Count) return false;
                for (int i = 0; i < left.Count; i++) {
                    var a = StuNativeProfile.Map(left[i]);
                    var b = StuNativeProfile.Map(right[i]);
                    if (a.Count != b.Count) return false;
                    foreach (var field in a) {
                        object value;
                        if (!b.TryGetValue(field.Key, out value)) return false;
                        var first = field.Value as int[];
                        var second = value as int[];
                        if (first == null ? !Object.Equals(field.Value, value) : second == null || !first.SequenceEqual(second)) return false;
                    }
                }
                return true;
            }

            private void SaveAuthoredPage(Window page, Dictionary<string, object> result) {
                IntPtr document = PageDocument(page);
                if (context.Word(document, "document_dirty") != 0) {
                    result["operation_phase"] = "save_page";
                    Abi.CheckSlot(page.Service, "window_service", 12, "save_page");
                    result["native_page_save_called"] = true;
                    bool saved = Abi.Bind<SavePage>("save_page")(page.Service, page.Page);
                    result["native_page_save_return"] = saved;
                    Require(saved && context.Word(document, "document_dirty") == 0, "The original Stu authored page did not save.");
                }
                result["page_save_verified"] = true;
                result["operation_phase"] = "save_root";
                context.RequireProject();
                IntPtr filename = Marshal.StringToHGlobalUni(context.Project);
                try {
                    int saved = Abi.Bind<SaveRoot>("save_root")(context.Root, filename);
                    result["native_root_save_return"] = saved;
                    Require(saved == 1 && context.Word(context.Root, "document_dirty") == 0, "The original Stu project did not save.");
                } finally { Marshal.FreeHGlobal(filename); }
                result["root_save_verified"] = true;
                result["operation_phase"] = "verify_saved_page";
            }

            private void ObserveAddedPage(Dictionary<int, Window> before, Dictionary<string, object> result) {
                try {
                    var current = AuthoringPages();
                    result["observed_page_count"] = current.Count;
                    Window page = ConfirmPageAddition(before, current);
                    result["observed_added_page"] = new Dictionary<string, object> { {"page_id", page.Id}, {"page_name", page.Name} };
                } catch (InvalidOperationException error) { result["page_observation_error"] = error.Message; }
            }

            private sealed class AuthoringPageString : IDisposable {
                private readonly NativeVoid destroy;
                private bool constructed;
                internal IntPtr Storage { get; private set; }

                internal AuthoringPageString(StuNativeProfile abi, string value, int maximumLength = 32768) {
                    var create = abi.BindImport<PageStringConstructor>("page_string_ctor");
                    destroy = abi.BindImport<NativeVoid>("page_string_dtor");
                    IntPtr text = Marshal.StringToHGlobalUni(value);
                    try {
                        Storage = Marshal.AllocHGlobal(IntPtr.Size);
                        constructed = create(Storage, text) == Storage;
                        Require(constructed && StuNativeProfile.Text(Storage, 0, maximumLength) == value, "The original Stu Unicode text could not be constructed.");
                    } catch { Dispose(); throw; }
                    finally { Marshal.FreeHGlobal(text); }
                }

                public void Dispose() {
                    if (Storage == IntPtr.Zero) return;
                    try { if (constructed) destroy(Storage); }
                    finally { Marshal.FreeHGlobal(Storage); Storage = IntPtr.Zero; }
                }
            }

            private sealed class AuthoringPageArchive : IDisposable {
                private readonly IntPtr list;
                private readonly PageArchiveTransfer transfer;
                private readonly PageMemoryFileSeek seek;
                private readonly PageArchiveConstructor createArchive;
                private readonly NativeVoid destroyArchive, destroyFile;
                private IntPtr file, archive;
                private bool fileReady, archiveReady, captured;

                internal AuthoringPageArchive(StuNativeProfile abi, IntPtr list) {
                    this.list = list;
                    transfer = abi.Bind<PageArchiveTransfer>("copy_user_page_archive");
                    var createFile = abi.BindImport<PageMemoryFileConstructor>("page_mem_file_ctor");
                    destroyFile = abi.BindImport<NativeVoid>("page_mem_file_dtor");
                    createArchive = abi.BindImport<PageArchiveConstructor>("page_archive_ctor");
                    destroyArchive = abi.BindImport<NativeVoid>("page_archive_dtor");
                    int fileSize = abi.Offset("page_mem_file_size"), archiveSize = abi.Offset("page_archive_size");
                    Require(fileSize > 0 && archiveSize > 0, "The original Stu page archive object sizes are invalid.");
                    try {
                        file = Marshal.AllocHGlobal(fileSize);
                        archive = Marshal.AllocHGlobal(archiveSize);
                        fileReady = createFile(file, 1024) == file;
                        Require(fileReady, "The original Stu page memory file did not construct.");
                        seek = abi.BindPageMemorySeek<PageMemoryFileSeek>(file);
                    } catch { Dispose(); throw; }
                }

                internal void Capture(int sourceId) {
                    Require(!captured && sourceId >= 0, "The original Stu page archive source is invalid.");
                    Transfer(sourceId, 0);
                    Require(seek(file, 0, 1) > 0 && seek(file, 0, 0) == 0, "The original Stu page archive has no readable contents.");
                    captured = true;
                }

                internal void RegisterCopy() {
                    Require(captured, "The original Stu source page was not archived.");
                    Transfer(-1, 1);
                }

                private void Transfer(int page, uint mode) {
                    archiveReady = createArchive(archive, file, mode, 65536, IntPtr.Zero) == archive;
                    Require(archiveReady, "The original Stu page archive could not construct.");
                    try { transfer(list, page, archive); }
                    finally { CloseArchive(); }
                }

                private void CloseArchive() {
                    if (!archiveReady) return;
                    archiveReady = false;
                    destroyArchive(archive);
                }

                public void Dispose() {
                    try { CloseArchive(); }
                    finally {
                        try { if (fileReady) destroyFile(file); }
                        finally {
                            if (archive != IntPtr.Zero) Marshal.FreeHGlobal(archive);
                            if (file != IntPtr.Zero) Marshal.FreeHGlobal(file);
                            archive = file = IntPtr.Zero;
                            fileReady = false;
                        }
                    }
                }
            }
        }
    }
}

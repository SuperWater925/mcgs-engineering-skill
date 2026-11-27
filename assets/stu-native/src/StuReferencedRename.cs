using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string PageReferenceReadAction = "page-reference-inspect", PageRenameAction = "page-rename-referenced";
        private const string DataReferenceReadAction = "data-reference-inspect", DataRenameAction = "data-rename-referenced";

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int ReferencePresence(IntPtr model, IntPtr path, IntPtr first);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool RenameWithReferences(IntPtr model, IntPtr target, IntPtr name, int confirmation, IntPtr error, int duplicateCheck);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int SaveRenamedDocument(IntPtr document, IntPtr database);

            private static readonly Regex VariableRenameName = new Regex(@"\A[\p{L}_][\p{L}\p{M}\p{Nd}_]{0,63}\z");
            private static readonly Regex PageRenameName = new Regex(@"\A[^.\x00-\x1f]{1,32}\z");
            private static readonly Regex StrategyRenameTokens = new Regex(
                @"""(?:""""|[^""\r\n])*""|'[^\r\n]*|(?<identifier>[\p{L}_][\p{L}\p{M}\p{Nd}_]*)");

            private sealed class ReferenceRecord {
                internal string Path, First;
                internal int Status;

                internal Dictionary<string, object> Readback() {
                    return new Dictionary<string, object> {{"target_linker", Path}, {"first_reference_linker", First}, {"status", Status}};
                }

                internal void RequireExpected(object raw) {
                    var fields = StuNativeProfile.Map(raw);
                    Require(fields.Count == 3 && fields.ContainsKey("target_linker") && fields.ContainsKey("first_reference_linker") &&
                        fields.ContainsKey("status") && Equals(fields["target_linker"], Path) &&
                        Equals(fields["first_reference_linker"], First) && Equals(fields["status"], Status),
                        "The current Stu registered reference differs from the preimage.");
                }
            }

            private sealed class ReferenceEdge {
                internal string Source, Target;
                internal string Key { get { return Source + "\0" + Target; } }
            }

            private IntPtr ReferenceModel() {
                context.RequireProject();
                IntPtr model = context.Ptr(context.Root, "root_window_model");
                Abi.CheckTable(model, "root_window_model");
                return model;
            }

            private string ReferencePath(IntPtr target) {
                IntPtr storage = Marshal.AllocHGlobal(IntPtr.Size);
                bool owned = false;
                var get = Abi.Bind<AssignText>("reference_object_path");
                var release = Abi.BindImport<NativeVoid>("page_string_dtor");
                try {
                    Marshal.WriteIntPtr(storage, IntPtr.Zero);
                    owned = get(target, storage) == storage;
                    Require(owned, "Stu object-path construction did not return its owned output.");
                    string path = StuNativeProfile.Text(storage, 0);
                    Require(path.Length != 0, "The actual Stu object has no reference path.");
                    return path;
                } finally {
                    try { if (owned) release(storage); }
                    finally { Marshal.FreeHGlobal(storage); }
                }
            }

            private ReferenceRecord ReadReference(string path) {
                var inspect = Abi.Bind<ReferencePresence>("reference_presence");
                using (var original = new AuthoringPageString(Abi, path))
                using (var first = new AuthoringPageString(Abi, "")) {
                    int status = inspect(ReferenceModel(), original.Storage, first.Storage);
                    string consumer = StuNativeProfile.Text(first.Storage, 0);
                    Require(status >= 0 && status <= 2 && (status == 0) == (consumer.Length == 0),
                        "The original Stu reference lookup returned inconsistent presence and identity.");
                    return new ReferenceRecord {Path = path, First = consumer, Status = status};
                }
            }

            private List<IntPtr> ReadReferenceNodes(IntPtr list) {
                int next = Abi.Offset("reference_graph_next"), previous = Abi.Offset("reference_graph_previous");
                IntPtr head = StuNativeProfile.Pointer(list, 0);
                int countOffset = Abi.Offset("reference_graph_set_count");
                int count = StuNativeProfile.Word(list, countOffset);
                Require(head != IntPtr.Zero && count >= 0 && count <= MaxCatalogEntries,
                    "The original Stu reference list has an invalid sentinel or count.");
                var result = new List<IntPtr>(count);
                var seen = new HashSet<IntPtr>();
                IntPtr node = StuNativeProfile.Pointer(head, next), last = head;
                for (int i = 0; i < count; i++) {
                    Require(node != IntPtr.Zero && node != head && seen.Add(node) &&
                        StuNativeProfile.Pointer(node, previous) == last, "The original Stu reference list links differ.");
                    result.Add(node);
                    last = node;
                    node = StuNativeProfile.Pointer(node, next);
                }
                Require(node == head && StuNativeProfile.Pointer(head, previous) == last &&
                    StuNativeProfile.Word(list, countOffset) == count, "The original Stu reference list changed while reading.");
                return result;
            }

            private List<ReferenceEdge> ReadReferenceEdges(IntPtr map, bool reverse) {
                int text = Abi.Offset("reference_graph_node_string"), value = Abi.Offset("reference_graph_node_value_set");
                var result = new List<ReferenceEdge>();
                var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (IntPtr node in ReadReferenceNodes(map)) {
                    string path = StuNativeProfile.Text(node, text);
                    Require(path.Length != 0 && path.IndexOf('\0') < 0 && keys.Add(path),
                        "The original Stu reference map has an invalid or repeated key.");
                    foreach (IntPtr item in ReadReferenceNodes(IntPtr.Add(node, value))) {
                        string link = StuNativeProfile.Text(item, text);
                        Require(link.Length != 0 && link.IndexOf('\0') < 0,
                            "The original Stu reference map has an invalid linker path.");
                        result.Add(new ReferenceEdge {Source = reverse ? link : path, Target = reverse ? path : link});
                    }
                }
                return result;
            }

            private List<ReferenceEdge> ReadReferenceGraph() {
                IntPtr model = ReferenceModel();
                var forward = ReadReferenceEdges(IntPtr.Add(model, Abi.Offset("reference_graph_forward")), false);
                var reverse = ReadReferenceEdges(IntPtr.Add(model, Abi.Offset("reference_graph_reverse")), true);
                var keys = new HashSet<string>(forward.Select(edge => edge.Key), StringComparer.OrdinalIgnoreCase);
                Require(keys.Count == forward.Count && keys.Count == reverse.Count &&
                    keys.SetEquals(reverse.Select(edge => edge.Key)) && ReferenceModel() == model,
                    "The original Stu forward and reverse reference graphs differ.");
                return forward;
            }

            private static bool UnderReferencePath(string linker, string root) {
                return linker.Equals(root, StringComparison.OrdinalIgnoreCase) ||
                    linker.StartsWith(root + ".", StringComparison.OrdinalIgnoreCase);
            }

            private static List<ReferenceEdge> IncomingEdges(List<ReferenceEdge> graph, string target) {
                return graph.Where(edge => UnderReferencePath(edge.Target, target)).ToList();
            }

            private static void RequireExactConsumer(ReferenceRecord before, List<ReferenceEdge> incoming) {
                Require((before.Status == 0 && incoming.Count == 0) ||
                    (before.Status == 1 && incoming.Count == 1 && incoming[0].Target == before.Path && incoming[0].Source == before.First),
                    "The original Stu rename requires zero incoming edges or one exact verified Prog consumer edge.");
            }

            private void VerifyReferenceGraph(List<ReferenceEdge> before, string oldPath, string replacement) {
                Func<string, string> rename = linker => UnderReferencePath(linker, oldPath)
                    ? replacement + linker.Substring(oldPath.Length) : linker;
                var expected = before.Select(edge => rename(edge.Source) + "\0" + rename(edge.Target)).OrderBy(key => key, StringComparer.Ordinal);
                var actual = ReadReferenceGraph().Select(edge => edge.Key).OrderBy(key => key, StringComparer.Ordinal);
                Require(expected.SequenceEqual(actual, StringComparer.Ordinal),
                    "The original Stu reference graph changed beyond the exact renamed linker paths.");
            }

            private static void NamedReferenceReadback(ReferenceRecord state, List<ReferenceEdge> incoming,
                Dictionary<string, object> receipt) {
                receipt["before_reference"] = state.Readback();
                receipt["registered_incoming_edges"] = incoming.Select(edge => new Dictionary<string, object> {
                    {"source", edge.Source}, {"target", edge.Target}
                }).ToList();
            }

            private static string ReplacementPath(ReferenceRecord before, string name, string replacement) {
                Require(before.Path == name || before.Path.EndsWith("." + name, StringComparison.Ordinal),
                    "The Stu reference path does not end in the original object name.");
                return before.Path.Substring(0, before.Path.Length - name.Length) + replacement;
            }

            private bool ApplyRegisteredRename(IntPtr target, string replacement, Dictionary<string, object> receipt) {
                IntPtr model = ReferenceModel();
                Abi.CheckSlot(model, "root_window_model", 4, "reference_model_rename");
                var rename = Abi.Bind<RenameWithReferences>("reference_model_rename");
                using (var name = new AuthoringPageString(Abi, replacement))
                using (var error = new AuthoringPageString(Abi, "")) {
                    receipt["operation_phase"] = "native_reference_rename";
                    receipt["read_only"] = false;
                    receipt["write_attempted"] = true;
                    bool success = rename(model, target, name.Storage, 0, error.Storage, 1);
                    string diagnostic = StuNativeProfile.Text(error.Storage, 0);
                    if (diagnostic.Length != 0) receipt["native_rename_diagnostic"] = diagnostic;
                    return success && diagnostic.Length == 0;
                }
            }

            private void VerifyRenamedReference(IntPtr target, ReferenceRecord before, string newPath, Dictionary<string, object> receipt) {
                Require(ReferencePath(target) == newPath, "The renamed Stu object did not receive the expected reference path.");
                ReferenceRecord current = ReadReference(newPath), old = ReadReference(before.Path);
                receipt["after_reference"] = current.Readback();
                receipt["old_reference_after"] = old.Readback();
                Require(old.Status == 0 && current.Status == before.Status && current.First == before.First,
                    "The registered Stu reference state differs after renaming.");
            }

            private void CheckRenameRoot() {
                Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                Abi.CheckSlot(context.Root, "root", 34, "save_root");
                Require(Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified")(context.Root) == 0 &&
                    context.Word(context.Root, "document_dirty") == 0, "The original Stu project has unsaved changes.");
            }

            private Dictionary<int, IntPtr> CaptureRenameWindows(Dictionary<int, Window> pages) {
                var documents = new Dictionary<int, IntPtr>();
                foreach (var item in pages) {
                    IntPtr doc = GetDocumentForView(item.Value);
                    Require(context.Word(doc, "document_dirty") == 0, "A Stu page has unsaved changes: " + item.Value.Name);
                    documents[item.Key] = doc;
                }
                return documents;
            }

            private void VerifyRenameWindows(Dictionary<int, Window> pages, Dictionary<int, IntPtr> documents,
                int renamedId, string replacement, bool allClean) {
                var current = AuthoringPages();
                Require(current.Count == pages.Count, "The Stu window catalog count changed during renaming.");
                foreach (var item in pages) {
                    Window actual;
                    Require(current.TryGetValue(item.Key, out actual) && actual.Page == item.Value.Page &&
                        actual.Service == item.Value.Service && actual.Name == (item.Key == renamedId ? replacement : item.Value.Name) &&
                        PageDocument(actual) == documents[item.Key], "A Stu window identity changed during renaming.");
                    if (allClean || item.Key != renamedId)
                        Require(context.Word(documents[item.Key], "document_dirty") == 0,
                            "The native rename changed an unrelated Stu window document: " + actual.Name);
                }
            }

            private void RestoreRenameWorkbench(AuthoringWorkbench workbench, Dictionary<string, object> receipt) {
                if (workbench == null || !workbench.Entered) return;
                try { workbench.Restore(); }
                catch (InvalidOperationException error) {
                    receipt["view_restore_error"] = error.Message;
                    if (Equals(receipt["ok"], true)) FailPageWrite(receipt, error);
                }
            }

            private sealed class RenameStrategyScope {
                internal StrategySelection Consumer;
                internal List<object> Preserved;
                internal string Wanted;
            }

            private RenameStrategyScope CaptureRenameStrategy(List<StrategyBlock> blocks, IntPtr frame,
                Dictionary<string, object> options, ReferenceRecord before, string name, string replacement, bool page) {
                object raw;
                bool explicitConsumer = options.TryGetValue("expected_consumer", out raw);
                Require((before.Status == 0 && !explicitConsumer) || (before.Status == 1 && explicitConsumer),
                    "Stu rename supports no registered consumer or one explicitly selected Prog consumer.");
                var result = new RenameStrategyScope();
                if (explicitConsumer) {
                    var selector = StuNativeProfile.Map(raw);
                    Require(selector.Count == 4 && selector.ContainsKey("block_id") && selector.ContainsKey("block_name") &&
                        selector.ContainsKey("row_index") && selector.ContainsKey("source_sha256_utf16le"),
                        "Use the full original Prog consumer and exact source SHA-256.");
                    var consumer = SelectStrategyProgram(blocks, StuNativeProfile.Number(selector["block_id"]),
                        NativeEngineeringDeliveryLayout.Value(selector, "block_name"), StuNativeProfile.Number(selector["row_index"]));
                    Require(ReferencePath(consumer.Block.Object) == before.First &&
                        StrategySourceHash(consumer.Source) == NativeEngineeringDeliveryLayout.Value(selector, "source_sha256_utf16le"),
                        "The selected Prog identity or exact source does not match the registered Stu consumer.");
                    RequireClosedStrategyEditor(frame, consumer.Block);
                    result.Consumer = consumer;
                }

                foreach (var block in blocks) {
                    var rows = StrategyMembers(block.Complete, "strategy_block_rows");
                    foreach (IntPtr row in rows) {
                        Abi.CheckTable(row, "strategy_row");
                        IntPtr program = context.Ptr(row, "strategy_row_action");
                        if (program == IntPtr.Zero || !Abi.IsTable(program, "strategy_program")) continue;
                        string source = StrategySource(program);
                        int matches = 0;
                        string expected = StrategyRenameTokens.Replace(source, token => {
                            if (!token.Groups["identifier"].Success ||
                                !String.Equals(token.Value, name, StringComparison.OrdinalIgnoreCase)) return token.Value;
                            if (page && (!Regex.IsMatch(source.Substring(0, token.Index), @"!OpenSubWnd[ \t]*\([ \t]*\z",
                                         RegexOptions.IgnoreCase | RegexOptions.CultureInvariant) ||
                                         !Regex.IsMatch(source.Substring(token.Index + token.Length), @"\A[ \t]*,")))
                                return token.Value;
                            matches++;
                            return replacement;
                        });
                        if (result.Consumer != null && program == result.Consumer.Program) {
                            Require(matches > 0, "The Stu consumer lacks the verified direct page or variable reference in Prog.");
                            result.Wanted = expected;
                        } else Require(matches == 0, "A second Stu Prog contains the old direct reference: " + block.Name);
                    }
                }
                result.Preserved = StrategyPreservationProof(blocks, result.Consumer == null ? (IntPtr?)null : result.Consumer.Program);
                return result;
            }

            private void VerifyRenameStrategy(RenameStrategyScope expectation, Dictionary<string, object> receipt) {
                var current = ReadStrategyBlocks();
                var old = expectation.Consumer;
                Require(EqualPayload(expectation.Preserved, StrategyPreservationProof(current, old == null ? (IntPtr?)null : old.Program)),
                    "The original Stu name change altered a different strategy or condition.");
                if (old == null) return;
                var actual = SelectStrategyProgram(current, old.Block.Id, old.Block.Name, old.Index);
                Require(actual.Row == old.Row && actual.Program == old.Program && actual.Source == expectation.Wanted,
                    "The original Stu Prog did not retain exactly the intended identifier changes.");
                receipt["strategy_consumer"] = new Dictionary<string, object> {
                    {"block_id", old.Block.Id}, {"block_name", old.Block.Name}, {"row_index", old.Index},
                    {"source_before_sha256_utf16le", StrategySourceHash(old.Source)},
                    {"source_after_sha256_utf16le", StrategySourceHash(actual.Source)}
                };
            }

            internal void ApplyPageReference(string action, IntPtr mainWindow, object rawOptions, Dictionary<string, object> receipt) {
                bool editing = action == PageRenameAction;
                if (editing) BeginPageReceipt(receipt);
                AuthoringWorkbench workbench = null;
                try {
                    VerifyFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == (editing ? 4 + (options.ContainsKey("expected_consumer") ? 1 : 0) : 2) &&
                        options.ContainsKey("page_id") && options.ContainsKey("page") &&
                        (!editing || options.ContainsKey("after") && options.ContainsKey("expected_reference")),
                        "Stu page rename needs the exact page, replacement name and current registered reference.");
                    int id = StuNativeProfile.Number(options["page_id"]);
                    string prior = NativeEngineeringDeliveryLayout.Value(options, "page");
                    Window target = SelectWindow(id, prior);
                    ReferenceRecord before = ReadReference(ReferencePath(target.Page));
                    receipt["page_id"] = id;
                    var graph = ReadReferenceGraph();
                    var incoming = IncomingEdges(graph, before.Path);
                    NamedReferenceReadback(before, incoming, receipt);
                    if (!editing) return;

                    string replacement = NativeEngineeringDeliveryLayout.Value(options, "after");
                    Require(PageRenameName.IsMatch(replacement) && replacement.Trim() == replacement &&
                        !String.Equals(prior, replacement, StringComparison.OrdinalIgnoreCase),
                        "The new Stu page name must be distinct and fit the original 32-character field without dots or control characters.");
                    before.RequireExpected(options["expected_reference"]);
                    RequireExactConsumer(before, incoming);
                    string newPath = ReplacementPath(before, prior, replacement);
                    Require(ReadReference(newPath).Status == 0 &&
                        !graph.Any(edge => UnderReferencePath(edge.Source, newPath) || UnderReferencePath(edge.Target, newPath)),
                        "The replacement Stu page path is already registered.");
                    var pages = AuthoringPages();
                    Require(!pages.Values.Any(page => String.Equals(page.Name, replacement, StringComparison.OrdinalIgnoreCase)),
                        "The new Stu window name already exists.");
                    IntPtr frame;
                    workbench = OpenAuthoringWorkbench(mainWindow, receipt, "authoring_user_list_index", "user_window_workbench", out frame);
                    CheckRenameRoot();
                    var blocks = ReadStrategyBlocks();
                    var strategies = CaptureRenameStrategy(blocks, frame, options, before, prior, replacement, true);
                    var documents = CaptureRenameWindows(pages);
                    IntPtr document = documents[id];
                    RequireEmptyPageProtection(document);
                    Abi.CheckSlot(document, "page_description_document", 83, "page_description_database_save");
                    var saveDocument = Abi.Bind<SaveRenamedDocument>("page_description_database_save");
                    var controls = AuthoringControls(target);

                    workbench.Activate();
                    RequireStrategyProjectClean(frame, blocks, receipt);
                    VerifyRenameWindows(pages, documents, id, prior, true);
                    ReadReference(before.Path).RequireExpected(before.Readback());
                    VerifyReferenceGraph(graph, before.Path, before.Path);
                    workbench.RequireTargetActive();
                    Require(ApplyRegisteredRename(target.Page, replacement, receipt), "The original Stu object model rejected the window name.");
                    VerifyRenamedReference(target.Page, before, newPath, receipt);
                    VerifyRenameWindows(pages, documents, id, replacement, false);
                    Window renamed = SelectWindow(id, replacement);
                    Require(SameAuthoringControls(controls, AuthoringControls(renamed)), "Original Stu page controls changed during renaming.");
                    workbench.RequireTargetActive();
                    receipt["operation_phase"] = "save_renamed_page";
                    Require(saveDocument(document, IntPtr.Zero) == 0 && context.Word(document, "document_dirty") == 0,
                        "The original Stu renamed page did not save.");
                    receipt["page_save_verified"] = true;
                    var saved = new List<int> {id};
                    receipt["saved_page_ids"] = saved;
                    Abi.Bind<SetNativeFlag>("set_root_modified")(context.Root, 1);
                    SaveAuthoredPage(renamed, receipt);
                    VerifyRenameWindows(pages, documents, id, replacement, true);
                    VerifyRenamedReference(target.Page, before, newPath, receipt);
                    VerifyReferenceGraph(graph, before.Path, newPath);
                    VerifyRenameStrategy(strategies, receipt);
                    receipt["complete_registered_graph_preserved"] = true;
                    Require(SameAuthoringControls(controls, AuthoringControls(renamed)), "The renamed Stu page controls changed during saving.");
                    workbench.RefreshTarget();
                    CompleteRename(receipt, prior, replacement);
                } catch (InvalidOperationException error) {
                    if (!editing) throw;
                    FailPageWrite(receipt, error);
                } finally { RestoreRenameWorkbench(workbench, receipt); }
            }

            internal void ApplyDataReference(string action, IntPtr mainWindow, object rawOptions, Dictionary<string, object> receipt) {
                bool editing = action == DataRenameAction;
                if (editing) BeginPageReceipt(receipt);
                AuthoringWorkbench workbench = null;
                try {
                    VerifyFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == (editing ? 5 + (options.ContainsKey("expected_consumer") ? 1 : 0) : 3) &&
                        options.ContainsKey("name") &&
                        options.ContainsKey("native_id") && options.ContainsKey("native_type") &&
                        (!editing || options.ContainsKey("after") && options.ContainsKey("expected_reference")),
                        "Stu data rename needs the exact variable, replacement name and current registered reference.");
                    string prior = NativeEngineeringDeliveryLayout.Value(options, "name");
                    int id = StuNativeProfile.Number(options["native_id"]), kind = StuNativeProfile.Number(options["native_type"]);
                    IntPtr manager = DataManager();
                    var objects = ReadVariablePointers(manager);
                    int index = FindVariable(objects, prior, id, kind, editing);
                    VariableRecord variable = ReadVariableRecord(objects[index], index);
                    receipt["record"] = variable.Value();
                    ReferenceRecord before = ReadReference(ReferencePath(variable.Object));
                    var graph = ReadReferenceGraph();
                    var incoming = IncomingEdges(graph, before.Path);
                    NamedReferenceReadback(before, incoming, receipt);
                    if (!editing) return;

                    string replacement = NativeEngineeringDeliveryLayout.Value(options, "after");
                    Require(kind >= 1 && kind <= 3 && VariableRenameName.IsMatch(replacement),
                        "The Stu variable rename requires an existing scalar and a valid original identifier.");
                    before.RequireExpected(options["expected_reference"]);
                    RequireExactConsumer(before, incoming);
                    string newPath = ReplacementPath(before, prior, replacement);
                    Require(ReadReference(newPath).Status == 0 &&
                        !graph.Any(edge => UnderReferencePath(edge.Source, newPath) || UnderReferencePath(edge.Target, newPath)),
                        "The replacement Stu variable path is already registered.");
                    var baseline = new List<VariableRecord>(objects.Count);
                    for (int i = 0; i < objects.Count; i++) {
                        var original = ReadVariableRecord(objects[i], i);
                        Require(!String.Equals(original.Name, replacement, StringComparison.OrdinalIgnoreCase),
                            "The new Stu variable name already exists.");
                        baseline.Add(original);
                    }
                    var pages = AuthoringPages();
                    IntPtr frame;
                    workbench = OpenAuthoringWorkbench(mainWindow, receipt, "authoring_data_list_index", "data_window_workbench", out frame);
                    CheckRenameRoot();
                    Require(DataDirty(manager) == 0, "The original Stu data module has unsaved changes.");
                    var documents = CaptureRenameWindows(pages);
                    IntPtr service = IntPtr.Add(manager, Abi.Offset("data_manager_service"));
                    Abi.CheckSlot(service, "data_service", 2, "save_data_module");
                    Abi.CheckSlot(service, "data_service", 11, "data_refresh_after_rename");
                    Abi.CheckSlot(service, "data_service", 40, "set_data_module_dirty");
                    var strategies = ReadStrategyBlocks();
                    var strategyScope = CaptureRenameStrategy(strategies, frame, options, before, prior, replacement, false);

                    workbench.Activate();
                    RequireStrategyProjectClean(frame, strategies, receipt);
                    Require(DataManager() == manager && DataDirty(manager) == 0, "The current Stu data module changed during activation.");
                    RequireVariableSelection(manager, variable);
                    VerifyVariableRecord(variable, ReadVariableRecord(variable.Object, index), null);
                    ReadReference(before.Path).RequireExpected(before.Readback());
                    VerifyReferenceGraph(graph, before.Path, before.Path);
                    workbench.RequireTargetActive();
                    Require(ApplyRegisteredRename(variable.Object, replacement, receipt), "The original Stu object model rejected the variable name.");
                    VerifyRenamedReference(variable.Object, before, newPath, receipt);
                    VerifyRenameWindows(pages, documents, -1, String.Empty, true);

                    workbench.RequireTargetActive();
                    Abi.Bind<SetNativeFlag>("set_data_module_dirty")(service, 1);
                    Abi.Bind<NativeVoid>("data_refresh_after_rename")(service);
                    VerifyRenamedData(manager, baseline, index, replacement);
                    SaveVariableChanges(manager, service, receipt);
                    receipt["root_save_verified"] = true;
                    VerifyRenamedData(manager, baseline, index, replacement);
                    VerifyRenameWindows(pages, documents, -1, String.Empty, true);
                    VerifyRenamedReference(variable.Object, before, newPath, receipt);
                    VerifyReferenceGraph(graph, before.Path, newPath);
                    VerifyRenameStrategy(strategyScope, receipt);
                    receipt["complete_registered_graph_preserved"] = true;
                    receipt["record"] = ReadVariableRecord(variable.Object, index).Value();
                    receipt["unselected_native_records_verified"] = true;
                    workbench.RefreshTarget();
                    CompleteRename(receipt, prior, replacement);
                } catch (InvalidOperationException error) {
                    if (!editing) throw;
                    FailPageWrite(receipt, error);
                } finally { RestoreRenameWorkbench(workbench, receipt); }
            }

            private void VerifyRenamedData(IntPtr manager, List<VariableRecord> baseline, int index, string replacement) {
                Require(DataManager() == manager, "The original Stu data manager changed after renaming.");
                var current = ReadVariablePointers(manager);
                Require(current.Count == baseline.Count, "The data catalog count changed during Stu renaming.");
                for (int i = 0; i < current.Count; i++)
                    VerifyVariableRecord(baseline[i], ReadVariableRecord(current[i], i), null, i == index ? replacement : null);
            }

            private static void CompleteRename(Dictionary<string, object> receipt, string old, string replacement) {
                receipt["old_name"] = old;
                receipt["new_name"] = replacement;
                receipt["completed_count"] = 1;
                receipt["status"] = "applied_and_saved";
                receipt["operation_phase"] = "complete";
            }
        }
    }
}

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string ControlReferenceReadAction = "control-reference-inspect";
        private const string ControlRenameAction = "control-rename-referenced";
        private const string SavedDataReferenceRead = "saved-data-control-reference-read";
        private const string SavedDataReferenceRename = "saved-data-control-reference-rename";

        private static void VerifyControlRenameFeature(StuNativeProfile abi, string action) {
            abi.RequireFeature(ControlReferenceReadAction);
            if (action == ControlRenameAction) abi.RequireFeature(ControlRenameAction);
        }

        private sealed partial class StuDocument {
            internal void ApplyControlReferenceRename(string action, IntPtr mainWindow, object rawOptions,
                Dictionary<string, object> receipt) {
                bool editing = action == ControlRenameAction;
                if (editing) BeginPageReceipt(receipt);
                try {
                    VerifyControlRenameFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    string[] identity = { "page_id", "page", "top_level_path", "control_name", "native_type_id" };
                    Require(identity.All(options.ContainsKey), "Use the exact Stu page and top-level control identity.");
                    int typeId = StuNativeProfile.Number(options["native_type_id"]);
                    bool linked = typeId == 0x5033;
                    Require(options.Count == identity.Length + (editing ? (linked ? 4 : 2) : 0) &&
                        (!editing || !linked || options.ContainsKey("expected_graph_sha256") && options.ContainsKey("expected_consumers")) &&
                        (!editing || options.ContainsKey("after") && options.ContainsKey("expected_reference")),
                        "Use the exact Stu top-level control and current reference preimage.");
                    int pageId = StuNativeProfile.Number(options["page_id"]);
                    var topPath = options["top_level_path"] as IList;
                    Require(topPath != null && topPath.Count == 1, "Use the one-component Stu top-level control position.");
                    int index = StuNativeProfile.Number(topPath[0]);
                    Require(pageId >= 0 && index >= 0 && (typeId == 0x5008 || linked),
                        "Stu control rename requires a known top-level control class and nonnegative page ID and position.");
                    string oldName = NativeEngineeringDeliveryLayout.Value(options, "control_name");
                    Window window = SelectWindow(pageId, NativeEngineeringDeliveryLayout.Value(options, "page"));
                    if (linked) {
                        ApplySavedDataReference(window, index, oldName, mainWindow, options, editing, receipt);
                        return;
                    }
                    IntPtr document = GetDocumentForView(window);
                    RequireEmptyPageProtection(document);
                    var top = ReadTopLevelControls(document);
                    Require(index >= 0 && index < top.Count, "The selected Stu control position does not exist.");
                    IntPtr native = StaticLabelReference(top[index], document, oldName);
                    string path = ReferencePath(window.Page) + "." + oldName;
                    Require(ReferencePath(native) == path, "The Stu label path differs from the selected page and control.");
                    ReferenceRecord before = ReadReference(path);
                    var graph = ReadReferenceGraph();
                    var incoming = IncomingEdges(graph, path);
                    var outgoing = graph.Where(edge => UnderReferencePath(edge.Source, path)).ToList();
                    bool zeroEdges = before.Status == 0 && incoming.Count == 0 && outgoing.Count == 0;
                    var controls = AuthoringControls(window);
                    var selected = ControlRenameCatalogEntry(controls, index, oldName);
                    var drawing = Abi.Bind<NativePointer>("get_drawing_view");

                    receipt["page_id"] = pageId;
                    receipt["page"] = window.Name;
                    receipt["control"] = new Dictionary<string, object>(selected);
                    receipt["reference_scope_zero_edges"] = zeroEdges;
                    receipt["target_view_closed"] = drawing(document) == IntPtr.Zero;
                    NamedReferenceReadback(before, incoming, receipt);
                    receipt["registered_outgoing_edges"] = outgoing.Select(edge => new Dictionary<string, object> {
                        {"source", edge.Source}, {"target", edge.Target}
                    }).ToList();
                    receipt["registered_reference_edge_count"] = graph.Count;
                    receipt["automatic_retry"] = false;
                    if (!editing) return;

                    before.RequireExpected(options["expected_reference"]);
                    Require(zeroEdges, "Stu label rename requires no registered incoming or outgoing reference, including under its path.");
                    Require(controls.Select(StuNativeProfile.Map).Count(row => row.ContainsKey("name") &&
                        String.Equals(row["name"] as string, oldName, StringComparison.OrdinalIgnoreCase)) == 1,
                        "The original Stu label name must be unambiguous on the selected page.");
                    string replacement = NativeEngineeringDeliveryLayout.Value(options, "after");
                    Require(VariableRenameName.IsMatch(replacement) && !String.Equals(oldName, replacement, StringComparison.OrdinalIgnoreCase)
                        && !controls.Select(StuNativeProfile.Map).Any(row => row.ContainsKey("name") &&
                            String.Equals(row["name"] as string, replacement, StringComparison.OrdinalIgnoreCase)),
                        "The new Stu label name is invalid or already belongs to this page.");
                    string newPath = ReplacementPath(before, oldName, replacement);
                    Require(ReadReference(newPath).Status == 0 &&
                        !graph.Any(edge => UnderReferencePath(edge.Source, newPath) || UnderReferencePath(edge.Target, newPath)),
                        "The replacement Stu control path is already registered.");

                    IntPtr frame = Abi.Bind<GetApplication>("get_main_frame")();
                    Abi.CheckTable(frame, "frame");
                    Require(context.Ptr(frame, "frame_hwnd") == mainWindow && drawing(document) == IntPtr.Zero,
                        "The original Stu workbench changed or the selected drawing view is open.");
                    CheckRenameRoot();
                    var pages = AuthoringPages();
                    var documents = CaptureRenameWindows(pages);
                    Require(documents[pageId] == document, "The selected Stu document changed while capturing clean pages.");
                    var blocks = ReadStrategyBlocks();
                    Require(blocks.All(block => !block.Changed), "An original Stu strategy has unsaved changes.");
                    var cleanChildren = VerifyOpenChildrenClean(Abi, frame, Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified"), false);
                    receipt["clean_open_documents"] = cleanChildren;
                    Require(Object.Equals(cleanChildren["strategy"], 0),
                        "The original Stu strategy editor must be closed during label rename.");
                    var strategies = new RenameStrategyScope { Preserved = StrategyPreservationProof(blocks, null) };
                    Abi.CheckSlot(document, "page_document", 27, "set_page_modified");
                    Abi.CheckSlot(document, "page_description_document", 83, "page_description_database_save");
                    var markPage = Abi.Bind<SetNativeFlag>("set_page_modified");
                    var markRoot = Abi.Bind<SetNativeFlag>("set_root_modified");
                    var save = Abi.Bind<SaveRenamedDocument>("page_description_database_save");

                    VerifyRenameWindows(pages, documents, -1, String.Empty, true);
                    VerifyReferenceGraph(graph, path, path);
                    ReadReference(path).RequireExpected(before.Readback());
                    Require(drawing(document) == IntPtr.Zero && ReadTopLevelControls(document).SequenceEqual(top) &&
                        StaticLabelReference(top[index], document, oldName) == native &&
                        SameAuthoringControls(controls, AuthoringControls(window)),
                        "The selected Stu label or native drawing scope changed before rename.");
                    context.RequireProject();
                    receipt["operation_phase"] = "mark_document";
                    receipt["read_only"] = false;
                    receipt["write_attempted"] = true;
                    markPage(document, 1);
                    markRoot(context.Root, 1);
                    Require(context.Word(document, "document_dirty") == 1 && context.Word(context.Root, "document_dirty") == 1,
                        "The original Stu label page and root did not retain their modified flags.");
                    Require(ApplyRegisteredRename(native, replacement, receipt), "The original Stu object model rejected the label name.");

                    // Keep the original selection and all known control fields except the requested native name.
                    receipt["before_control"] = receipt["control"];
                    selected["name"] = replacement;
                    Action verify = () => {
                        Require(drawing(document) == IntPtr.Zero && ReadTopLevelControls(document).SequenceEqual(top) &&
                            StaticLabelReference(top[index], document, replacement) == native &&
                            SameAuthoringControls(controls, AuthoringControls(window)),
                            "Original Stu label identity, geometry, appearance or neighboring controls changed during rename.");
                        VerifyRenamedReference(native, before, newPath, receipt);
                        VerifyReferenceGraph(graph, path, newPath);
                        receipt["control"] = ControlRenameCatalogEntry(AuthoringControls(window), index, replacement);
                    };
                    verify();
                    VerifyRenameWindows(pages, documents, pageId, window.Name, false);
                    VerifyRenameStrategy(strategies, receipt);
                    receipt["operation_phase"] = "save_renamed_control_page";
                    int pageSaved = save(document, IntPtr.Zero);
                    receipt["native_page_save_return"] = pageSaved;
                    Require(pageSaved == 0 && context.Word(document, "document_dirty") == 0,
                        "The original Stu renamed label page did not save.");
                    receipt["page_save_verified"] = true;
                    receipt["saved_page_ids"] = new[] { pageId };
                    markRoot(context.Root, 1);
                    SaveAuthoredPage(window, receipt);
                    VerifyRenameWindows(pages, documents, -1, String.Empty, true);
                    VerifyRenameStrategy(strategies, receipt);
                    verify();
                    receipt["complete_registered_graph_preserved"] = true;
                    CompleteRename(receipt, oldName, replacement);
                } catch (InvalidOperationException error) {
                    if (!editing) throw;
                    FailPageWrite(receipt, error);
                }
            }

            private IntPtr StaticLabelReference(IntPtr control, IntPtr document, string name) {
                Abi.CheckTable(control, "label");
                Require(context.Ptr(control, "control_owner") == document && context.Text(control, "control_name") == name &&
                    context.Word(control, "control_type_id") == 0x5008 && IsStaticLabel(control),
                    "The exact Stu control is not an owned static top-level label without actions or animations.");
                IntPtr reference = IntPtr.Add(control, Abi.Offset("control_view_offset"));
                Abi.CheckSlot(reference, "label_view", 9, "control_reference_name");
                Abi.CheckSlot(reference, "label_view", 10, "control_reference_set_name");
                Abi.CheckSlot(reference, "label_view", 15, "control_reference_container");
                return reference;
            }

            private sealed class SavedDataConsumer {
                internal Window Page;
                internal IntPtr Document, Button;
                internal int Index;
                internal int[] Rectangle;
                internal StrategySelection Strategy;
                internal string Owner, Kind, Name, Source;
                internal List<object> Preserved;

                internal Dictionary<string, object> Record(string source) {
                    var value = new Dictionary<string, object> {
                        {"owner", Owner}, {"kind", Kind}, {"source_sha256_utf16le", StrategySourceHash(source)}
                    };
                    if (Page != null) {
                        value["page_id"] = Page.Id;
                        value["page"] = Page.Name;
                    }
                    if (Button != IntPtr.Zero) {
                        value["control_name"] = Name;
                        value["top_level_path"] = new[] { Index };
                        value["native_type_id"] = 0x5027;
                    }
                    if (Strategy != null) {
                        value["block_id"] = Strategy.Block.Id;
                        value["block_name"] = Strategy.Block.Name;
                        value["row_index"] = Strategy.Index;
                    }
                    return value;
                }
            }

            private void ApplySavedDataReference(Window window, int index, string oldName, IntPtr mainWindow,
                Dictionary<string, object> options, bool editing, Dictionary<string, object> receipt) {
                Abi.RequireFeature(SavedDataReferenceRead);
                if (editing) Abi.RequireFeature(SavedDataReferenceRename);
                IntPtr document = GetDocumentForView(window);
                RequireEmptyPageProtection(document);
                var top = ReadTopLevelControls(document);
                Require(index < top.Count, "The selected Stu saved-data browser position does not exist.");
                IntPtr native = SavedDataReference(top[index], document, oldName);
                string path = ReferencePath(window.Page) + "." + oldName;
                Require(ReferencePath(native) == path, "The Stu saved-data browser path differs from its exact owner.");
                var before = ReadReference(path);
                var graph = ReadReferenceGraph();
                var incoming = IncomingEdges(graph, path);
                var outgoing = graph.Where(edge => UnderReferencePath(edge.Source, path)).ToList();
                var pages = AuthoringPages();
                var blocks = ReadStrategyBlocks();
                var consumers = ReadSavedDataConsumers(incoming, pages, blocks, path);
                var descriptors = consumers.Select(consumer => consumer.Record(consumer.Source)).ToList();
                var controls = AuthoringControls(window);
                var selected = ControlRenameCatalogEntry(controls, index, oldName);
                Require(Object.Equals(selected["native_class"], ".?AVCDrawSaveData@@") &&
                    Object.Equals(selected["native_type_id"], 0x5033) && Object.Equals(selected["document_owned"], true),
                    "The original Stu browser is not reported with its exact owned catalog identity.");
                var drawing = Abi.Bind<NativePointer>("get_drawing_view");
                string graphHash = ControlReferenceGraphHash(graph);

                receipt["page_id"] = window.Id;
                receipt["page"] = window.Name;
                receipt["control"] = new Dictionary<string, object>(selected);
                receipt["target_view_closed"] = drawing(document) == IntPtr.Zero;
                receipt["reference_scope_zero_edges"] = before.Status == 0 && incoming.Count == 0 && outgoing.Count == 0;
                receipt["registered_reference_edge_count"] = graph.Count;
                receipt["registered_graph_sha256"] = graphHash;
                receipt["reference_consumers"] = descriptors;
                receipt["automatic_retry"] = false;
                NamedReferenceReadback(before, incoming, receipt);
                receipt["registered_outgoing_edges"] = outgoing.Select(edge => new Dictionary<string, object> {
                    {"source", edge.Source}, {"target", edge.Target}
                }).ToList();
                if (!editing) return;

                receipt["strategy_save_verified"] = false;
                before.RequireExpected(options["expected_reference"]);
                Require(before.Status == 1 && consumers.Count(item => item.Strategy != null) == 1 &&
                    consumers.Any(item => item.Owner == before.First) &&
                    graphHash == NativeEngineeringDeliveryLayout.Value(options, "expected_graph_sha256") &&
                    SameConsumerRecords(options["expected_consumers"], descriptors),
                    "The original Stu saved-data reference graph or consumer source preimage differs.");
                string newName = NativeEngineeringDeliveryLayout.Value(options, "after");
                Require(VariableRenameName.IsMatch(newName) && !String.Equals(oldName, newName, StringComparison.OrdinalIgnoreCase) &&
                    controls.Select(StuNativeProfile.Map).Count(row => row.ContainsKey("name") &&
                        String.Equals(row["name"] as string, oldName, StringComparison.OrdinalIgnoreCase)) == 1 &&
                    !controls.Select(StuNativeProfile.Map).Any(row => row.ContainsKey("name") &&
                        String.Equals(row["name"] as string, newName, StringComparison.OrdinalIgnoreCase)),
                    "The old Stu saved-data name is ambiguous or the replacement is invalid or already used.");
                string newPath = ReplacementPath(before, oldName, newName);
                Require(ReadReference(newPath).Status == 0 &&
                    !graph.Any(edge => UnderReferencePath(edge.Source, newPath) || UnderReferencePath(edge.Target, newPath)),
                    "The replacement Stu saved-data path is already registered.");

                IntPtr frame = Abi.Bind<GetApplication>("get_main_frame")();
                Abi.CheckTable(frame, "frame");
                Require(context.Ptr(frame, "frame_hwnd") == mainWindow, "The original Stu workbench changed.");
                CheckRenameRoot();
                var documents = CaptureRenameWindows(pages);
                Require(documents[window.Id] == document && blocks.All(block => !block.Changed),
                    "The selected Stu page changed or an original strategy has unsaved changes.");
                var cleanChildren = VerifyOpenChildrenClean(Abi, frame, Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified"), false);
                receipt["clean_open_documents"] = cleanChildren;
                Require(Object.Equals(cleanChildren["strategy"], 0), "Close original Stu strategy views before migrating saved-data consumers.");
                var affected = new SortedSet<int>(consumers.Where(consumer => consumer.Page != null).Select(consumer => consumer.Page.Id));
                affected.Add(window.Id);
                foreach (int id in affected) {
                    IntPtr item = documents[id];
                    Require(drawing(item) == IntPtr.Zero, "Close each affected original Stu drawing before migrating saved-data consumers.");
                    RequireEmptyPageProtection(item);
                    Abi.CheckSlot(item, "page_description_document", 83, "page_description_database_save");
                }
                var strategy = consumers.Single(consumer => consumer.Strategy != null);
                var expectedSources = consumers.ToDictionary(consumer => consumer.Owner,
                    consumer => consumer.Source.Replace(ControlScriptPath(path) + ".", ControlScriptPath(newPath) + "."));
                var preserved = StrategyPreservationProof(blocks, strategy.Strategy.Program);
                RequireArchivedControlConsumer(strategy.Source, expectedSources[strategy.Owner]);
                var markPage = Abi.Bind<SetNativeFlag>("set_page_modified");
                var markRoot = Abi.Bind<SetNativeFlag>("set_root_modified");
                var save = Abi.Bind<SaveRenamedDocument>("page_description_database_save");
                Abi.CheckSlot(document, "page_document", 27, "set_page_modified");

                VerifyRenameWindows(pages, documents, -1, String.Empty, true);
                VerifyReferenceGraph(graph, path, path);
                ReadReference(path).RequireExpected(before.Readback());
                VerifySavedDataConsumers(consumers, consumers.ToDictionary(item => item.Owner, item => item.Source));
                Require(ReadTopLevelControls(document).SequenceEqual(top) && SavedDataReference(top[index], document, oldName) == native &&
                    SameAuthoringControls(controls, AuthoringControls(window)), "The original Stu saved-data control changed before rename.");
                context.RequireProject();
                receipt["operation_phase"] = "mark_saved_data_document";
                receipt["read_only"] = false;
                receipt["write_attempted"] = true;
                markPage(document, 1);
                markRoot(context.Root, 1);
                Require(context.Word(document, "document_dirty") == 1 && context.Word(context.Root, "document_dirty") == 1,
                    "The original Stu saved-data page and root did not retain their modified flags.");
                Require(ApplyRegisteredRename(native, newName, receipt), "The original Stu model rejected the saved-data browser rename.");

                receipt["before_control"] = receipt["control"];
                selected["name"] = newName;
                Action verify = () => {
                    Require(ReadTopLevelControls(document).SequenceEqual(top) && SavedDataReference(top[index], document, newName) == native &&
                        SameAuthoringControls(controls, AuthoringControls(window)), "The original Stu saved-data browser or neighboring controls changed.");
                    VerifyReferenceGraph(graph, path, newPath);
                    VerifySavedDataRenamedReference(native, before, newPath, consumers, receipt);
                    receipt["reference_consumers_after"] = VerifySavedDataConsumers(consumers, expectedSources);
                    receipt["control"] = ControlRenameCatalogEntry(AuthoringControls(window), index, newName);
                };
                verify();
                Require(documents.All(row => affected.Contains(row.Key) || context.Word(row.Value, "document_dirty") == 0),
                    "The original Stu rename changed a page outside the verified consumer set.");
                receipt["operation_phase"] = "save_saved_data_consumer_pages";
                var savedIds = new List<int>();
                receipt["saved_page_ids"] = savedIds;
                foreach (int id in affected) {
                    IntPtr item = documents[id];
                    Require(drawing(item) == IntPtr.Zero && save(item, IntPtr.Zero) == 0 && context.Word(item, "document_dirty") == 0,
                        "The original Stu saved-data consumer page did not save: " + pages[id].Name);
                    savedIds.Add(id);
                }
                receipt["page_save_verified"] = true;
                markRoot(context.Root, 1);
                Require(documents.Values.All(item => context.Word(item, "document_dirty") == 0),
                    "The original Stu root marker unexpectedly dirtied a drawing after the verified page saves.");
                SaveAuthoredPage(window, receipt);
                VerifyRenameWindows(pages, documents, -1, String.Empty, true);
                Require(EqualPayload(preserved, StrategyPreservationProof(ReadStrategyBlocks(), strategy.Strategy.Program)),
                    "The original Stu saved-data rename altered an unrelated strategy or condition.");
                verify();
                RequireArchivedControlConsumer(expectedSources[strategy.Owner], strategy.Source);
                receipt["strategy_save_verified"] = true;
                receipt["registered_graph_sha256_after"] = ControlReferenceGraphHash(ReadReferenceGraph());
                receipt["complete_registered_graph_preserved"] = true;
                CompleteRename(receipt, oldName, newName);
            }

            private List<SavedDataConsumer> ReadSavedDataConsumers(List<ReferenceEdge> edges, Dictionary<int, Window> pages,
                List<StrategyBlock> blocks, string target) {
                var owners = new HashSet<string>(edges.Select(edge => edge.Source), StringComparer.Ordinal);
                var found = new List<SavedDataConsumer>();
                foreach (Window page in pages.Values) {
                    string owner = ReferencePath(page.Page);
                    if (!owners.Any(path => UnderReferencePath(path, owner))) continue;
                    IntPtr document = GetDocumentForView(page);
                    if (owners.Remove(owner)) {
                        Abi.CheckTable(document, "page_description_document");
                        found.Add(new SavedDataConsumer { Owner = owner, Kind = "page-open", Page = page, Document = document,
                            Source = context.Text(document, "recipe_rename_page_open_source"), Preserved = SavedDataPageOtherSources(document) });
                    }
                    var top = ReadTopLevelControls(document);
                    for (int i = 0; i < top.Count; i++) {
                        IntPtr button = top[i];
                        if (context.Word(button, "control_type_id") != 0x5027) continue;
                        string name = context.Text(button, "control_name"), path = owner + "." + name;
                        if (!owners.Remove(path)) continue;
                        VerifySavedDataButton(button, document, name, path);
                        found.Add(new SavedDataConsumer { Owner = path, Kind = "button-release", Page = page, Document = document,
                            Button = button, Name = name, Index = i, Rectangle = ReadRectangle(button),
                            Source = context.Text(button, "clone_button_condition_1"),
                            Preserved = SavedDataButtonOtherFields(button) });
                    }
                }
                foreach (var block in blocks) {
                    string owner = ReferencePath(block.Object);
                    if (!owners.Remove(owner)) continue;
                    Require(block.Rows == 1, "A Stu saved-data strategy consumer requires one verified Prog row.");
                    var strategy = SelectStrategyProgram(blocks, block.Id, block.Name, 0);
                    found.Add(new SavedDataConsumer { Owner = owner, Kind = "strategy-prog", Strategy = strategy, Source = strategy.Source });
                }
                Require(owners.Count == 0 && found.Count(item => item.Strategy != null) <= 1,
                    "The original Stu saved-data graph contains an unsupported consumer owner.");
                string shortPath = ControlScriptPath(target);
                foreach (var consumer in found) {
                    string methods = consumer.Button == IntPtr.Zero ? "Refresh" : "Home|End|PageUp|PageDown|SetTimeDialog|Refresh";
                    var direct = Regex.Matches(consumer.Source, @"(?m)^[ \t]*" + Regex.Escape(shortPath) +
                        @"\.(?:" + methods + @")[ \t]*\([ \t]*\)[ \t]*(?=\r?$)", RegexOptions.CultureInvariant);
                    string token = shortPath + ".";
                    Require(direct.Count == 1 && consumer.Source.IndexOf(token, StringComparison.Ordinal) ==
                        consumer.Source.LastIndexOf(token, StringComparison.Ordinal),
                        "The original Stu saved-data consumer is not one known direct no-argument call: " + consumer.Owner);
                    if (consumer.Kind == "page-open") Require(consumer.Preserved.Cast<string>().All(source => !source.Contains(token)),
                        "The same Stu page contains an unsupported loop or close saved-data reference.");
                }
                return found.OrderBy(item => item.Owner, StringComparer.Ordinal).ToList();
            }

            private List<Dictionary<string, object>> VerifySavedDataConsumers(List<SavedDataConsumer> consumers,
                Dictionary<string, string> expected) {
                var readback = new List<Dictionary<string, object>>();
                foreach (var item in consumers) {
                    string source;
                    if (item.Strategy != null) {
                        RequireStrategySelection(item.Strategy);
                        source = StrategySource(item.Strategy.Program);
                    } else if (item.Button != IntPtr.Zero) {
                        var controls = ReadTopLevelControls(item.Document);
                        Require(PageDocument(item.Page) == item.Document && item.Index < controls.Count && controls[item.Index] == item.Button,
                            "An original Stu saved-data button changed its position or owner.");
                        VerifySavedDataButton(item.Button, item.Document, item.Name, item.Owner);
                        Require(EqualRectangle(item.Rectangle, ReadRectangle(item.Button)) &&
                            EqualPayload(item.Preserved, SavedDataButtonOtherFields(item.Button)),
                            "An original Stu saved-data button changed its geometry or an unrelated action field.");
                        source = context.Text(item.Button, "clone_button_condition_1");
                    } else {
                        Require(PageDocument(item.Page) == item.Document && ReferencePath(item.Page.Page) == item.Owner &&
                            EqualPayload(item.Preserved, SavedDataPageOtherSources(item.Document)),
                            "An original Stu saved-data page changed an unrelated event source or its owner.");
                        source = context.Text(item.Document, "recipe_rename_page_open_source");
                    }
                    Require(source == expected[item.Owner], "The original Stu saved-data consumer source differs: " + item.Owner);
                    readback.Add(item.Record(source));
                }
                return readback;
            }

            private void VerifySavedDataRenamedReference(IntPtr target, ReferenceRecord before, string newPath,
                List<SavedDataConsumer> consumers, Dictionary<string, object> receipt) {
                Require(ReferencePath(target) == newPath, "The renamed Stu saved-data browser has a different native path.");
                ReferenceRecord renamed = ReadReference(newPath), old = ReadReference(before.Path);
                receipt["after_reference"] = renamed.Readback();
                receipt["old_reference_after"] = old.Readback();
                Require(old.Status == 0 && renamed.Status == 1 && renamed.Status == before.Status &&
                    consumers.Any(consumer => consumer.Owner == renamed.First),
                    "The renamed Stu saved-data browser has an invalid reference status or first consumer.");
            }

            private IntPtr SavedDataReference(IntPtr control, IntPtr document, string name) {
                Abi.CheckTable(control, "saved_data_control");
                Require(context.Word(control, "control_type_id") == 0x5033 && context.Ptr(control, "control_owner") == document &&
                    context.Text(control, "control_name") == name && IsStaticLabel(control),
                    "The original Stu saved-data browser identity or empty local event and animation arrays differ.");
                IntPtr reference = IntPtr.Add(control, Abi.Offset("control_view_offset"));
                Abi.CheckSlot(reference, "saved_data_control_view", 9, "control_reference_name");
                Abi.CheckSlot(reference, "saved_data_control_view", 10, "control_reference_set_name");
                Abi.CheckSlot(reference, "saved_data_control_view", 15, "control_reference_container");
                return reference;
            }

            private void VerifySavedDataButton(IntPtr button, IntPtr document, string name, string path) {
                Abi.CheckTable(button, "standard_button");
                IntPtr reference = IntPtr.Add(button, Abi.Offset("control_view_offset"));
                Abi.CheckSlot(reference, "standard_button_view", 9, "control_reference_name");
                Abi.CheckSlot(reference, "standard_button_view", 15, "control_reference_container");
                Require(context.Word(button, "control_type_id") == 0x5027 && context.Ptr(button, "control_owner") == document &&
                    context.Text(button, "control_name") == name && ReferencePath(reference) == path,
                    "The original Stu saved-data button identity differs.");
            }

            private List<object> SavedDataButtonOtherFields(IntPtr button) {
                var fields = ReadOrdinaryControlPayload(button, 0x5027);
                fields.RemoveAt(fields.Count - 1);
                return fields;
            }

            private List<object> SavedDataPageOtherSources(IntPtr document) {
                return new List<object> {context.Text(document, "recipe_rename_page_cycle_source"),
                    context.Text(document, "recipe_rename_page_close_source")};
            }

            private void RequireArchivedControlConsumer(string present, string absent) {
                var binary = Encoding.GetEncoding(28591);
                string archive = binary.GetString(ReadNamedArchive("StgyAndTrigger"));
                string expected = binary.GetString(Encoding.Unicode.GetBytes(present));
                int offset = archive.IndexOf(expected, StringComparison.Ordinal);
                Require(offset >= 0 && offset == archive.LastIndexOf(expected, StringComparison.Ordinal) &&
                    !archive.Contains(binary.GetString(Encoding.Unicode.GetBytes(absent))),
                    "The persisted Stu strategy archive does not contain exactly the selected consumer source.");
            }

            private static string ControlScriptPath(string nativePath) {
                const string prefix = "MCGS.用户窗口.";
                Require(nativePath.StartsWith(prefix, StringComparison.Ordinal), "The Stu saved-data path has an unsupported reference namespace.");
                return nativePath.Substring(prefix.Length);
            }

            private static string ControlReferenceGraphHash(List<ReferenceEdge> graph) {
                return StrategySourceHash(String.Join("\0", graph.Select(edge => edge.Key).OrderBy(key => key, StringComparer.Ordinal)));
            }

            private static bool SameConsumerRecords(object input, List<Dictionary<string, object>> expected) {
                var rows = input as IList;
                if (rows == null || rows.Count != expected.Count) return false;
                var indexed = new Dictionary<string, Dictionary<string, object>>(StringComparer.Ordinal);
                foreach (object value in rows) {
                    var row = StuNativeProfile.Map(value);
                    object name;
                    if (!row.TryGetValue("owner", out name) || !(name is string) || indexed.ContainsKey((string)name)) return false;
                    indexed.Add((string)name, row);
                }
                foreach (var record in expected) {
                    Dictionary<string, object> actual;
                    if (!indexed.TryGetValue((string)record["owner"], out actual) || actual.Count != record.Count) return false;
                    foreach (var field in record) {
                        object value;
                        if (!actual.TryGetValue(field.Key, out value)) return false;
                        var path = field.Value as int[];
                        var supplied = value as IList;
                        if (path == null ? !Object.Equals(value, field.Value) : supplied == null || supplied.Count != 1 || !Object.Equals(supplied[0], path[0])) return false;
                    }
                }
                return true;
            }

            private static Dictionary<string, object> ControlRenameCatalogEntry(List<object> controls, int index, string name) {
                var matches = controls.Select(StuNativeProfile.Map).Where(row => row.ContainsKey("top_level_path") &&
                    ((int[])row["top_level_path"]).SequenceEqual(new[] { index }) && Object.Equals(row["name"], name)).ToList();
                Require(matches.Count == 1, "The Stu control is not uniquely visible at the selected top-level catalog position.");
                return matches[0];
            }
        }
    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string RecipeReferenceReadAction = "recipe-reference-inspect";
        private const string RecipeRenameAction = "recipe-rename-referenced";

        private static void VerifyRecipeRenameFeature(StuNativeProfile abi, string action) {
            abi.RequireFeature(RecipeEditAction);
            abi.RequireFeature("registered-reference-read");
            abi.RequireFeature("page-view-inspect");
            abi.RequireFeature("top-level-control-catalog");
            abi.RequireFeature(StrategyCatalogAction);
            abi.RequireFeature(TriggerCatalogAction);
            abi.RequireFeature(action);
            if (action == RecipeRenameAction) {
                abi.RequireFeature("registered-reference-rename");
                abi.RequireFeature("page-authoring-common");
                abi.RequireFeature("recipe-edit-workbench");
            }
        }

        private sealed partial class StuDocument {
            private const string RecipeIndexKey = "MCGS_RECIPE_DATA";
            private const string RecipeNamedKeyPrefix = "MCGS_RECIPE_";
            private static readonly Regex RecipeGroupRenameName = new Regex(@"\A[\p{L}_][\p{L}\p{M}\p{Nd}_]{0,19}\z");

            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void MarkRecipeDirectoryDirty(IntPtr service);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool SaveRecipeDirectory(IntPtr service);

            private sealed class RecipeRenamePreimage {
                internal IntPtr Manager;
                internal List<RecipeRecord> Catalog;
                internal RecipeRecord Selected;
                internal int Index;
                internal ReferenceRecord Reference;
                internal List<ReferenceEdge> Graph, Incoming;
                internal byte[] Archive, IndexArchive;
                internal int TargetTail, IndexNameEnd;
            }

            internal void ApplyRecipeRenameAction(string action, IntPtr mainWindow, object rawOptions,
                Dictionary<string, object> result) {
                bool writing = action == RecipeRenameAction;
                if (writing) {
                    result["write_attempted"] = result["native_result_may_be_partial"] = false;
                    result["recipe_save_verified"] = result["root_save_verified"] = result["project_saved"] = false;
                    result["automatic_retry"] = false;
                    result["operation_phase"] = "validate_preimage";
                }
                AuthoringWorkbench workbench = null;
                try {
                    VerifyRecipeRenameFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    object requestedConsumers;
                    bool referenced = writing ? options.TryGetValue("expected_consumers", out requestedConsumers) :
                        options.TryGetValue("include_referenced_consumers", out requestedConsumers);
                    Require(options.Count == (writing ? 6 : 1) + (referenced ? 1 : 0) &&
                        (writing || !referenced || Object.Equals(requestedConsumers, true)),
                        "Use the exact Stu recipe name and rename preimage fields.");
                    string name = RecipeOptionText(options, "group_name", false);
                    var before = ReadRecipeRenamePreimage(name, true);
                    result["group_name"] = name;
                    result["recipe_index"] = before.Index;
                    result["recipe_count"] = before.Catalog.Count;
                    result["record"] = ReadRecipeRows(before.Selected, 0, 1);
                    NamedReferenceReadback(before.Reference, before.Incoming, result);
                    string archiveHash = RecipeArchiveHash(before.Archive), indexHash = RecipeArchiveHash(before.IndexArchive);
                    result["recipe_archive_sha256"] = archiveHash;
                    result["recipe_index_sha256"] = indexHash;
                    result["recipe_module_dirty"] = (int)RecipeDirty(before.Manager);
                    result["root_document_dirty"] = context.Word(context.Root, "document_dirty");

                    var pages = AuthoringPages();
                    var docs = CaptureRenameWindows(pages);
                    var strategies = ReadStrategyBlocks();
                    var scope = ReadRecipeRenameConsumerScope(pages, docs, strategies);
                    result["consumer_scope"] = scope;
                    bool noConsumers = before.Reference.Status == 0 && before.Incoming.Count == 0 &&
                        (int)scope["pages_with_controls"] == 0 && (int)scope["pages_with_source"] == 0 &&
                        (int)scope["pages_with_dispatch"] == 0 && (int)scope["strategies_with_rows"] == 0 &&
                        (int)scope["event_triggers"] == 0;
                    result["no_recipe_consumers_verified"] = noConsumers;
                    string replacement = writing ? RecipeOptionText(options, "after", false) : name;
                    var consumers = referenced ? CaptureRecipeConsumers(pages, docs, strategies, before, name, replacement, scope) : null;
                    if (consumers != null) {
                        result["recipe_consumers"] = consumers.Readback(false);
                        result["referenced_consumers_supported"] = consumers.Supported;
                        result["unsupported_recipe_consumer_reasons"] = consumers.Unsupported.ToArray();
                    }
                    if (!writing) return;

                    Require(before.Selected.RowCount == 0 && (consumers == null ? noConsumers : consumers.Supported),
                        "Stu recipe rename requires an empty recipe and a verified consumer scope.");
                    if (consumers != null) consumers.RequireExpected(requestedConsumers);
                    Require(RecipeIndex(options, "expected_recipe_index", before.Catalog.Count) == before.Index &&
                        RecipeOptionText(options, "expected_archive_sha256", false) == archiveHash &&
                        RecipeOptionText(options, "expected_index_sha256", false) == indexHash &&
                        options.ContainsKey("expected_reference"), "The selected Stu recipe archive or index differs from its preimage.");
                    before.Reference.RequireExpected(options["expected_reference"]);
                    result["before_recipe_archive_sha256"] = archiveHash;
                    result["before_recipe_index_sha256"] = indexHash;
                    Require(RecipeGroupRenameName.IsMatch(name) && RecipeGroupRenameName.IsMatch(replacement) &&
                        replacement.Length <= Abi.Offset("recipe_storage_max_name") && !before.Catalog.Exists(
                            item => String.Equals(item.Name, replacement, StringComparison.OrdinalIgnoreCase)),
                        "The requested Stu recipe destination name is invalid or already exists.");
                    string nextPath = ReplacementPath(before.Reference, name, replacement);
                    Require(ReadReference(nextPath).Status == 0 && IncomingEdges(before.Graph, nextPath).Count == 0 &&
                        !before.Graph.Exists(edge => UnderReferencePath(edge.Source, nextPath)) &&
                        ReadNamedArchive(RecipeNamedKeyPrefix + replacement, true) == null,
                        "The destination recipe path or original named archive is already occupied.");

                    CheckRenameRoot();
                    Require(RecipeDirty(before.Manager) == 0, "The original Stu recipe module has unsaved changes.");
                    IntPtr frame;
                    workbench = OpenAuthoringWorkbench(mainWindow, result, "authoring_data_list_index", "data_window_workbench", out frame);
                    workbench.Activate();
                    var isModified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                    result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, isModified, false);
                    CheckRenameRoot();
                    Require(RecipeDirty(before.Manager) == 0, "The original Stu recipe module became dirty.");
                    VerifyRenameWindows(pages, docs, -1, "", true);
                    var current = ReadRecipeRenamePreimage(name, true);
                    var currentStrategies = ReadStrategyBlocks();
                    var currentScope = ReadRecipeRenameConsumerScope(pages, docs, currentStrategies);
                    Require(before.Manager == current.Manager && before.Index == current.Index &&
                        SameRecipe(before.Selected, current.Selected) && current.Reference.Status == before.Reference.Status &&
                        current.Reference.First == before.Reference.First && current.Reference.Path == before.Reference.Path &&
                        current.Incoming.Count == before.Incoming.Count &&
                        before.Archive.SequenceEqual(current.Archive) && before.IndexArchive.SequenceEqual(current.IndexArchive) &&
                        scope.All(field => Object.Equals(field.Value, currentScope[field.Key])),
                        "The Stu recipe, project consumers, or original disk image changed before writing.");
                    VerifyReferenceGraph(before.Graph, before.Reference.Path, before.Reference.Path);
                    if (consumers != null) {
                        consumers = CaptureRecipeConsumers(pages, docs, currentStrategies, current, name, replacement, currentScope);
                        Require(consumers.Supported, "The current Stu referenced recipe scope is no longer supported.");
                        consumers.RequireExpected(requestedConsumers);
                    }
                    var expectedStrategies = consumers == null ? StrategyPreservationProof(strategies, null) : null;
                    IntPtr service = IntPtr.Add(before.Manager, Abi.Offset("recipe_rename_manager_service_offset"));
                    Abi.CheckSlot(service, "recipe_rename_manager_service", 2, "recipe_rename_save_directory");
                    Abi.CheckSlot(service, "recipe_rename_manager_service", 3, "recipe_rename_mark_dirty");
                    Abi.CheckSlot(current.Selected.Pointer, "recipe_object", 10, "recipe_rename_set_name");
                    var mark = Abi.Bind<MarkRecipeDirectoryDirty>("recipe_rename_mark_dirty");
                    var save = Abi.Bind<SaveRecipeDirectory>("recipe_rename_save_directory");
                    if (consumers != null) {
                        ValidateRecipeConsumerWrites(consumers, pages, docs, currentStrategies, frame, result);
                        VerifyReferenceGraph(before.Graph, before.Reference.Path, before.Reference.Path);
                        Require(RecipeDirty(before.Manager) == 0, "Stu native recipe consumer precompile changed the original recipe module.");
                    }
                    workbench.RequireTargetActive();
                    context.RequireProject();

                    result["read_only"] = false;
                    result["write_attempted"] = true;
                    result["operation_phase"] = "mark_original_recipe_dirty";
                    Abi.Bind<SetNativeFlag>("set_root_modified")(context.Root, 1);
                    Marshal.WriteInt32(context.Root, Abi.Offset("root_compile_valid"), 0);
                    mark(service);
                    Require(RecipeDirty(before.Manager) == 1, "The original Stu recipe module did not become dirty.");
                    Require(ApplyRegisteredRename(current.Selected.Pointer, replacement, result),
                        "The original Stu recipe rename did not return success.");
                    VerifyRenamedReference(current.Selected.Pointer, before.Reference, nextPath, result);
                    VerifyReferenceGraph(before.Graph, before.Reference.Path, nextPath);
                    if (consumers == null) {
                        VerifyRenameWindows(pages, docs, -1, "", true);
                        Require(EqualPayload(expectedStrategies, StrategyPreservationProof(ReadStrategyBlocks(), null)),
                            "The original recipe rename changed a non-consuming strategy.");
                    } else ApplyRecipeConsumerWrites(consumers, pages, docs, name, replacement,
                        () => VerifyReferenceGraph(before.Graph, before.Reference.Path, nextPath), result);

                    result["operation_phase"] = "save_original_recipe_directory";
                    Require(save(service) && RecipeDirty(before.Manager) == 0, "The original Stu recipe directory did not save cleanly.");
                    var saved = VerifySavedRecipeRename(before, replacement);
                    result["recipe_save_verified"] = true;
                    result["operation_phase"] = "save_root";
                    SaveRecipeRoot(isModified);
                    result["root_save_verified"] = result["project_saved"] = true;

                    var final = VerifySavedRecipeRename(before, replacement);
                    Require(saved.Archive.SequenceEqual(final.Archive) && saved.IndexArchive.SequenceEqual(final.IndexArchive) &&
                        RecipeDirty(before.Manager) == 0 && isModified(context.Root) == 0, "Root save changed the checked Stu recipe state.");
                    VerifyRenamedReference(final.Selected.Pointer, before.Reference, nextPath, result);
                    VerifyReferenceGraph(before.Graph, before.Reference.Path, nextPath);
                    VerifyRenameWindows(pages, docs, -1, "", true);
                    if (consumers == null)
                        Require(EqualPayload(expectedStrategies, StrategyPreservationProof(ReadStrategyBlocks(), null)),
                            "Root save changed a non-consuming Stu strategy.");
                    else FinishRecipeConsumerWrites(consumers, pages, docs, replacement, result);
                    result["record"] = ReadRecipeRows(final.Selected, 0, 1);
                    result["old_name"] = name;
                    result["new_name"] = replacement;
                    result["saved_recipe_archive_sha256"] = RecipeArchiveHash(final.Archive);
                    result["saved_recipe_index_sha256"] = RecipeArchiveHash(final.IndexArchive);
                    result["recipe_module_dirty"] = (int)RecipeDirty(before.Manager);
                    result["root_document_dirty"] = isModified(context.Root);
                    result["native_index_verified"] = result["target_recipe_payload_preserved"] =
                        result["old_named_blob_preserved"] = true;
                    result["native_result_may_be_partial"] = false;
                    result["operation_phase"] = "complete";
                    result["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    if (writing) FailPageWrite(result, error);
                    else {
                        result["ok"] = false;
                        result["status"] = "native_read_rejected";
                        result["error"] = error.Message;
                    }
                } finally {
                    RestoreRenameWorkbench(workbench, result);
                }
            }

            private RecipeRenamePreimage ReadRecipeRenamePreimage(string name, bool captureGraph) {
                context.RequireProject();
                var current = new RecipeRenamePreimage();
                current.Manager = RecipeManager();
                current.Catalog = ReadRecipeDirectory(current.Manager);
                current.Selected = SelectRecipe(current.Catalog, name);
                current.Index = current.Catalog.IndexOf(current.Selected);
                Require(context.Ptr(current.Selected.Pointer, "recipe_rename_object_owner") == current.Manager,
                    "The original Stu recipe no longer belongs to the selected manager.");
                current.Archive = ReadNamedArchive(RecipeNamedKeyPrefix + name);
                current.IndexArchive = ReadNamedArchive(RecipeIndexKey);
                try {
                    current.TargetTail = VerifyRecipeRenameArchive(current.Archive, current.Selected);
                    current.IndexNameEnd = VerifyRecipeRenameIndex(current.IndexArchive, current.Catalog);
                } catch (EndOfStreamException error) {
                    throw new InvalidOperationException("The original Stu recipe or index is truncated.", error);
                } catch (DecoderFallbackException error) {
                    throw new InvalidOperationException("The original Stu recipe or index name is not valid UTF-16.", error);
                }
                if (captureGraph) {
                    current.Reference = ReadReference(ReferencePath(current.Selected.Pointer));
                    current.Graph = ReadReferenceGraph();
                    current.Incoming = IncomingEdges(current.Graph, current.Reference.Path);
                }
                return current;
            }

            private Dictionary<string, object> ReadRecipeRenameConsumerScope(Dictionary<int, Window> pages,
                Dictionary<int, IntPtr> documents, List<StrategyBlock> strategies) {
                int controls = 0, pageSources = 0, pageDispatch = 0, strategyRows = 0, eventTriggers = 0;
                foreach (var page in pages) {
                    IntPtr doc = documents[page.Key];
                    Abi.CheckTable(doc, "page_description_document");
                    if (ReadTopLevelControls(doc).Count != 0) controls++;
                    if (context.Text(doc, "recipe_rename_page_open_source").Length != 0 ||
                        context.Text(doc, "recipe_rename_page_cycle_source").Length != 0 ||
                        context.Text(doc, "recipe_rename_page_close_source").Length != 0) pageSources++;
                    IntPtr events = IntPtr.Add(doc, Abi.Offset("recipe_rename_page_dispatch_array"));
                    Abi.CheckTable(events, "control_event_array");
                    int eventCount = context.Word(events, "recipe_rename_page_dispatch_count");
                    Require(eventCount >= 0, "The original Stu page dispatch count is invalid.");
                    if (eventCount != 0) pageDispatch++;
                }
                foreach (var strategy in strategies) {
                    if (strategy.Rows != 0 || strategy.Changed) strategyRows++;
                    var trigger = ReadTrigger(strategy);
                    if (trigger != null && Object.Equals(trigger["native_class"], "CTriggerEvent")) eventTriggers++;
                }
                return new Dictionary<string, object> {
                    {"user_pages", pages.Count}, {"pages_with_controls", controls}, {"pages_with_source", pageSources},
                    {"pages_with_dispatch", pageDispatch}, {"strategy_blocks", strategies.Count},
                    {"strategies_with_rows", strategyRows}, {"event_triggers", eventTriggers}
                };
            }

            private static string RecipeArchiveHash(byte[] archive) {
                using (var hash = SHA256.Create())
                    return BitConverter.ToString(hash.ComputeHash(archive)).Replace("-", "").ToLowerInvariant();
            }

            private int VerifyRecipeRenameArchive(byte[] bytes, RecipeRecord selected) {
                using (var reader = new BinaryReader(new MemoryStream(bytes, false))) {
                    reader.ReadInt32();
                    Require(ReadRecipeString(reader) == selected.Name, "The named Stu recipe archive has a different group name.");
                    int tail = checked((int)reader.BaseStream.Position);
                    Require(reader.ReadInt32() == selected.ColumnCount, "The named Stu recipe archive has other column counts.");
                    for (int index = 0; index < selected.ColumnCount; index++) {
                        IntPtr column = RecipeColumn(selected, index);
                        Require(ReadRecipeString(reader) == context.Text(column, "recipe_column_binding") &&
                            ReadRecipeString(reader) == context.Text(column, "recipe_column_caption") &&
                            reader.ReadInt32() == context.Word(column, "recipe_column_kind"),
                            "The named Stu recipe archive has other column contents.");
                    }
                    Require(reader.ReadInt32() == selected.RowCount, "The named Stu recipe archive has other row counts.");
                    return tail;
                }
            }

            private static int VerifyRecipeRenameIndex(byte[] bytes, List<RecipeRecord> recipes) {
                using (var reader = new BinaryReader(new MemoryStream(bytes, false))) {
                    Require(reader.ReadInt32() == recipes.Count, "The original Stu recipe index has a different count.");
                    foreach (var recipe in recipes)
                        Require(ReadRecipeString(reader) == recipe.Name, "The original Stu index order differs from the live recipe directory.");
                    return checked((int)reader.BaseStream.Position);
                }
            }

            private RecipeRenamePreimage VerifySavedRecipeRename(RecipeRenamePreimage before, string replacement) {
                var after = ReadRecipeRenamePreimage(replacement, false);
                Require(after.Manager == before.Manager && after.Catalog.Count == before.Catalog.Count &&
                    after.Index == before.Index && after.Selected.RowCount == 0, "The saved Stu recipe directory changed identity.");
                for (int i = 0; i < before.Catalog.Count; i++) {
                    var old = before.Catalog[i];
                    var current = after.Catalog[i];
                    Require(i == before.Index ? current.Pointer == old.Pointer && current.Name == replacement &&
                        current.RowCount == old.RowCount && current.ColumnCount == old.ColumnCount : SameRecipe(old, current),
                        "The original Stu recipe directory changed another object, count or position.");
                }
                Require(BitConverter.ToInt32(after.Archive, 0) == Abi.GlobalWord("recipe_wire_version") &&
                    before.Archive.Skip(before.TargetTail).SequenceEqual(after.Archive.Skip(after.TargetTail)) &&
                    before.IndexArchive.Skip(before.IndexNameEnd).SequenceEqual(after.IndexArchive.Skip(after.IndexNameEnd)) &&
                    ReadNamedArchive(RecipeNamedKeyPrefix + before.Selected.Name).SequenceEqual(before.Archive),
                    "The original Stu saved recipe payload, index tail or old unindexed archive differs.");
                return after;
            }
        }
    }
}

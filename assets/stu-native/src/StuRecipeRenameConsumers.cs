using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private sealed partial class StuDocument {
            private const string RecipePluginImageSha = "403bc4ef88020902595609d880cea55d8992c91edf39b046ef96bcaedf7a9aa7";
            private const string RecipePluginPath = @"ActiveX\外挂版本构件\配方构件\DrawRecipe.ui";
            private static readonly Regex RecipeScriptTokens = new Regex(
                @"'[^\r\n]*|""(?:""""|[^""\r\n])*""|(?<call>!Recipe[A-Za-z]+)[ \t]*\(",
                RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            private static readonly Regex RecipeScriptArgument = new Regex(@"\G[ \t]*""(?<name>[^""\r\n]+)""[ \t]*(?=[,)])");
            private static readonly HashSet<string> VerifiedRecipeCalls = new HashSet<string>(StringComparer.OrdinalIgnoreCase) {
                "!RecipeAddNew", "!RecipeClose", "!RecipeDelete", "!RecipeGetCount", "!RecipeLoad",
                "!RecipeSave", "!RecipeSeekToPosition", "!RecipeSetValueTo"
            };

            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int ReplaceRecipeBinding(IntPtr plugin, int kind, IntPtr oldName, IntPtr newName);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void ResizeRecipeCache(IntPtr array, int size, int growth);

            private sealed class RecipeConsumerScript {
                internal string Kind, Owner, Before, After;
                internal int OwnerId, Index, LiteralCount;
                internal IntPtr Field, Document, Cache, Preload;
                internal StrategySelection Strategy;

                internal Dictionary<string, object> Record(bool changed) {
                    return new Dictionary<string, object> {
                        {"kind", Kind}, {"owner_id", OwnerId}, {"owner_name", Owner}, {"index", Index},
                        {"literal_count", LiteralCount}, {"source_sha256_utf16le", StrategySourceHash(changed ? After : Before)}
                    };
                }
            }

            private sealed class RecipePluginConsumer {
                internal Window Window;
                internal string ControlName, Linker, GroupName;
                internal IntPtr Document, Control, Plugin, Replace;

                internal Dictionary<string, object> Record(string renamedGroup) {
                    return new Dictionary<string, object> {
                        {"page_id", Window.Id}, {"page_name", Window.Name}, {"control_name", ControlName},
                        {"reference_linker", Linker}, {"recipe_name", renamedGroup ?? GroupName},
                        {"plugin_image_sha256", RecipePluginImageSha}
                    };
                }
            }

            private sealed class RecipeConsumers {
                internal readonly List<RecipeConsumerScript> Scripts = new List<RecipeConsumerScript>();
                internal readonly List<RecipePluginConsumer> Controls = new List<RecipePluginConsumer>();
                internal readonly SortedSet<string> Unsupported = new SortedSet<string>(StringComparer.Ordinal);
                internal Dictionary<int, List<object>> Strategies;
                internal List<object> Windows;
                internal byte[] StrategyArchiveBefore;
                internal string Replacement;
                internal bool Supported { get { return Unsupported.Count == 0; } }
                internal RecipeConsumerScript Close { get { return Scripts.Single(script => script.Kind == "close"); } }

                internal Dictionary<string, object> Readback(bool changed) {
                    return new Dictionary<string, object> {
                        {"recipe_controls", Controls.Select(control => control.Record(changed ? Replacement : null)).ToList()},
                        {"script_literal_references", Scripts.Select(script => script.Record(changed)).ToList()}
                    };
                }

                internal void RequireExpected(object raw) {
                    var expected = StuNativeProfile.Map(raw);
                    var actual = Readback(false);
                    Require(expected.Count == actual.Count, "Use the complete Stu recipe consumer preimage.");
                    foreach (var list in actual) {
                        object rawRows;
                        Require(expected.TryGetValue(list.Key, out rawRows), "The Stu recipe consumer preimage is missing an inventory.");
                        var rows = rawRows as IList;
                        var actualRows = (List<Dictionary<string, object>>)list.Value;
                        Require(rows != null && rows.Count == actualRows.Count, "The Stu recipe consumer inventory changed.");
                        for (int i = 0; i < actualRows.Count; i++) {
                            var row = StuNativeProfile.Map(rows[i]);
                            Require(row.Count == actualRows[i].Count && actualRows[i].All(field =>
                                row.ContainsKey(field.Key) && Object.Equals(row[field.Key], field.Value)),
                                "A Stu recipe consumer identity or source preimage changed.");
                        }
                    }
                }
            }

            private RecipeConsumers CaptureRecipeConsumers(Dictionary<int, Window> pages, Dictionary<int, IntPtr> docs,
                List<StrategyBlock> strategies, RecipeRenamePreimage before, string name, string replacement,
                Dictionary<string, object> scope) {
                Abi.RequireFeature("recipe-rename-consumer-read");
                var consumers = new RecipeConsumers { Replacement = replacement };
                if (before.Selected.RowCount != 0) consumers.Unsupported.Add("recipe_has_rows");
                if ((int)scope["pages_with_dispatch"] != 0) consumers.Unsupported.Add("page_dispatch_not_supported");
                if ((int)scope["event_triggers"] != 0) consumers.Unsupported.Add("strategy_event_trigger_not_supported");

                IntPtr pluginModule = IntPtr.Zero;
                foreach (var window in pages.Values.OrderBy(item => item.Id)) {
                    IntPtr document = docs[window.Id];
                    var top = new HashSet<IntPtr>(ReadTopLevelControls(document));
                    var visited = new HashSet<IntPtr>();
                    VisitControls(window, (index, control, rtti, owned) => {
                        if (!owned || !visited.Add(control)) return;
                        if (rtti != ".?AVCDrawDll@@") {
                            if (IsStaticRecipeNeighbor(control)) return;
                            consumers.Unsupported.Add("unverified_control_source_scope");
                            return;
                        }
                        Abi.CheckTable(control, "recipe_rename_draw_dll");
                        if (context.Word(control, "control_type_id") != 0x503d || !top.Contains(control)) {
                            consumers.Unsupported.Add("nested_or_unverified_external_control");
                            return;
                        }
                        string path = context.Text(control, "recipe_rename_draw_dll_path").Split('#')[0].Trim();
                        string fileName = path.Substring(path.LastIndexOfAny(new[] { '\\', '/' }) + 1);
                        if (!String.Equals(fileName, "DrawRecipe.ui", StringComparison.OrdinalIgnoreCase)) {
                            consumers.Unsupported.Add("unverified_external_control");
                            return;
                        }
                        // The editor may expand the stored relative control path. The loaded module and object slot establish its actual identity.
                        if (!IsStaticLabel(control)) consumers.Unsupported.Add("external_control_local_actions_not_supported");
                        if (pluginModule == IntPtr.Zero) pluginModule = VerifiedRecipePluginModule();
                        IntPtr plugin = context.Ptr(control, "recipe_rename_draw_dll_plugin");
                        IntPtr replace = CheckRecipePlugin(pluginModule, plugin);
                        string group = StuNativeProfile.Text(plugin, 0x28);
                        if (consumers.Replacement != name && String.Equals(group, consumers.Replacement, StringComparison.OrdinalIgnoreCase))
                            consumers.Unsupported.Add("destination_recipe_consumer_already_present");
                        if (!String.Equals(group, name, StringComparison.OrdinalIgnoreCase)) return;
                        string controlName = context.Text(control, "control_name");
                        string linker = ReferencePath(window.Page) + "." + controlName;
                        Require(group == name && controlName.Length != 0 && ReferencePath(IntPtr.Add(control, Abi.Offset("control_view_offset"))) == linker,
                            "The Stu DrawRecipe group or control registration is ambiguous.");
                        consumers.Controls.Add(new RecipePluginConsumer {
                            Window = window, Document = document, Control = control, Plugin = plugin, Replace = replace,
                            ControlName = controlName, Linker = linker, GroupName = group
                        });
                    });
                    if (!top.IsSubsetOf(visited)) consumers.Unsupported.Add("unverified_control_source_scope");
                    CaptureRecipeScript(consumers, new RecipeConsumerScript { Kind = "open", Owner = window.Name, OwnerId = window.Id, Index = 0,
                        Document = document, Field = IntPtr.Add(document, Abi.Offset("recipe_rename_page_open_source")) }, name);
                    CaptureRecipeScript(consumers, new RecipeConsumerScript { Kind = "loop", Owner = window.Name, OwnerId = window.Id, Index = 1,
                        Document = document, Field = IntPtr.Add(document, Abi.Offset("recipe_rename_page_cycle_source")) }, name);
                    CaptureRecipeScript(consumers, new RecipeConsumerScript { Kind = "close", Owner = window.Name, OwnerId = window.Id, Index = 2,
                        Document = document, Field = IntPtr.Add(document, Abi.Offset("recipe_rename_page_close_source")),
                        Cache = IntPtr.Add(document, Abi.Offset("recipe_rename_page_close_cache")) }, name);
                }

                foreach (var block in strategies.OrderBy(item => item.Id)) {
                    var rows = StrategyMembers(block.Complete, "strategy_block_rows");
                    Require(rows.Count == block.Rows, "The Stu native strategy row count changed.");
                    for (int i = 0; i < rows.Count; i++) {
                        Abi.CheckTable(rows[i], "strategy_row");
                        IntPtr program = context.Ptr(rows[i], "strategy_row_action");
                        IntPtr cell = context.Ptr(rows[i], "strategy_row_cell");
                        if (cell != IntPtr.Zero) {
                            Abi.CheckTable(cell, "strategy_cell");
                            foreach (var condition in StrategyMembers(cell, "strategy_cell_conditions")) {
                                if (!Abi.IsTable(condition, "strategy_condition")) consumers.Unsupported.Add("unverified_strategy_condition");
                                else CaptureRecipeScript(consumers, new RecipeConsumerScript { Kind = "condition", Owner = block.Name,
                                    OwnerId = block.Id, Index = i, Field = IntPtr.Add(condition, Abi.Offset("strategy_condition_expression")) }, name);
                            }
                        }
                        if (program == IntPtr.Zero) continue;
                        if (!Abi.IsTable(program, "strategy_program")) {
                            consumers.Unsupported.Add("unverified_strategy_action");
                            continue;
                        }
                        var selected = SelectStrategyProgram(strategies, block.Id, block.Name, i);
                        CaptureRecipeScript(consumers, new RecipeConsumerScript { Kind = "strategy", Owner = block.Name, OwnerId = block.Id,
                            Index = i, Strategy = selected, Field = IntPtr.Add(program, Abi.Offset("strategy_program_source")) }, name);
                    }
                }

                if (consumers.Controls.Count != 1 || before.Reference.Status != 1 || before.Incoming.Count != 1 ||
                    before.Incoming[0].Target != before.Reference.Path || before.Incoming[0].Source != before.Reference.First ||
                    consumers.Controls[0].Linker != before.Reference.First) consumers.Unsupported.Add("registered_recipe_consumer_scope_not_supported");
                if (consumers.Scripts.Count != 3 || consumers.Scripts.Count(script => script.Kind == "close") != 1 ||
                    consumers.Scripts.Where(script => script.Kind == "strategy").Select(script => script.OwnerId).Distinct().Count() != 2 ||
                    consumers.Controls.Count != 1 || consumers.Close.OwnerId != consumers.Controls[0].Window.Id)
                    consumers.Unsupported.Add("recipe_script_consumer_scope_not_supported");
                if (consumers.Controls.Any(control => !StuNativeProfile.IsEmptyString(control.Document, Abi.Offset("document_password"))))
                    consumers.Unsupported.Add("recipe_consumer_page_protected");
                return consumers;
            }

            private bool IsStaticRecipeNeighbor(IntPtr control) {
                return Abi.IsTable(control, "label") && IsStaticLabel(control);
            }

            private static void CaptureRecipeScript(RecipeConsumers consumers, RecipeConsumerScript script, string name) {
                script.Before = StuNativeProfile.Text(script.Field, 0, MaxStrategySourceLength);
                var offsets = new List<int>();
                foreach (Match token in RecipeScriptTokens.Matches(script.Before)) {
                    Group call = token.Groups["call"];
                    if (!call.Success) continue;
                    Match argument = RecipeScriptArgument.Match(script.Before, token.Index + token.Length);
                    if (!argument.Success) {
                        consumers.Unsupported.Add("indirect_recipe_script_argument");
                        continue;
                    }
                    Group literal = argument.Groups["name"];
                    if (consumers.Replacement != name && String.Equals(literal.Value, consumers.Replacement, StringComparison.OrdinalIgnoreCase))
                        consumers.Unsupported.Add("destination_recipe_consumer_already_present");
                    if (!String.Equals(literal.Value, name, StringComparison.OrdinalIgnoreCase)) continue;
                    if (literal.Value != name || !VerifiedRecipeCalls.Contains(call.Value)) consumers.Unsupported.Add("unverified_recipe_script_call");
                    else offsets.Add(literal.Index);
                }
                int mentions = 0;
                for (int at = 0; (at = script.Before.IndexOf(name, at, StringComparison.OrdinalIgnoreCase)) >= 0; at += name.Length) mentions++;
                if (mentions != offsets.Count) consumers.Unsupported.Add("unverified_recipe_literal_use");
                if (offsets.Count == 0) return;
                if (script.Kind != "close" && script.Kind != "strategy") {
                    consumers.Unsupported.Add("unverified_recipe_script_host");
                    return;
                }
                var after = new StringBuilder(script.Before.Length);
                int start = 0;
                foreach (int offset in offsets) {
                    after.Append(script.Before, start, offset - start).Append(consumers.Replacement);
                    start = offset + name.Length;
                }
                script.After = after.Append(script.Before, start, script.Before.Length - start).ToString();
                script.LiteralCount = offsets.Count;
                consumers.Scripts.Add(script);
            }

            private static IntPtr VerifiedRecipePluginModule() {
                using (var process = Process.GetCurrentProcess()) {
                    string expected = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(process.MainModule.FileName), RecipePluginPath));
                    var modules = process.Modules.Cast<ProcessModule>().Where(candidate =>
                        String.Equals(candidate.ModuleName, "DrawRecipe.ui", StringComparison.OrdinalIgnoreCase)).ToList();
                    Require(modules.Count == 1 && modules[0].ModuleMemorySize > 0x84698 &&
                        String.Equals(Path.GetFullPath(modules[0].FileName), expected, StringComparison.OrdinalIgnoreCase) &&
                        NativeEngineeringDeliveryLayout.HashFile(expected) == RecipePluginImageSha,
                        "The loaded Stu DrawRecipe plug-in does not match the verified original image.");
                    return modules[0].BaseAddress;
                }
            }

            private static IntPtr CheckRecipePlugin(IntPtr module, IntPtr plugin) {
                // These RVAs are from the separately fingerprinted DrawRecipe PE, not the editor profile.
                IntPtr table = StuNativeProfile.Pointer(plugin, 0);
                IntPtr replace = IntPtr.Add(module, 0x55e0);
                Require(table == IntPtr.Add(module, 0x8466c) && StuNativeProfile.Pointer(table, -4) == IntPtr.Add(module, 0x8b7c4) &&
                    StuNativeProfile.Pointer(table, 10 * IntPtr.Size) == replace && StuNativeProfile.Readable(replace, 27, true),
                    "The loaded Stu DrawRecipe replaceName slot does not match its original table.");
                byte[] witness = { 0x55, 0x8b, 0xec, 0x83, 0xec, 0x4c, 0x53, 0x56, 0x57, 0x89, 0x4d, 0xfc, 0xc7, 0x45,
                    0xf8, 0x00, 0x00, 0x00, 0x00, 0x83, 0x7d, 0x08, 0x05, 0x75, 0x1e, 0x8b, 0x45 };
                for (int i = 0; i < witness.Length; i++) Require(Marshal.ReadByte(replace, i) == witness[i], "The loaded Stu recipe binding code differs.");
                return replace;
            }

            private void ValidateRecipeConsumerWrites(RecipeConsumers consumers, Dictionary<int, Window> pages,
                Dictionary<int, IntPtr> docs, List<StrategyBlock> strategies, IntPtr frame, Dictionary<string, object> result) {
                Abi.RequireFeature("recipe-rename-consumer-write");
                var control = consumers.Controls[0];
                RequireEmptyPageProtection(control.Document);
                Abi.CheckSlot(control.Document, "page_document", 27, "set_page_modified");
                Abi.CheckSlot(control.Document, "page_description_document", 83, "page_description_database_save");
                Require(Abi.Bind<NativePointer>("get_drawing_view")(control.Document) == IntPtr.Zero,
                    "Close the selected Stu recipe consumer page before renaming.");
                result["page_close_cache_before_sha256"] = RecipeCloseCacheHash(consumers.Close.Cache, true);
                Require(strategies.All(block => !block.Changed), "An original Stu strategy has unsaved changes.");
                consumers.StrategyArchiveBefore = ReadNamedArchive("StgyAndTrigger");
                VerifyRecipeStrategyArchive(consumers, consumers.StrategyArchiveBefore, false);
                consumers.Strategies = RecipeStrategyProjection(consumers, strategies);
                consumers.Windows = RecipeWindowProjection(pages, docs, consumers.Close);
                foreach (var script in consumers.Scripts.Where(item => item.Strategy != null)) {
                    RequireClosedStrategyEditor(frame, script.Strategy.Block);
                    script.Preload = VerifyStrategyWriteRoles(script.Strategy);
                    using (var requested = new AuthoringPageString(Abi, script.After, MaxStrategySourceLength))
                        ValidateStrategySource(script.Strategy, requested.Storage, result);
                }
                VerifyRecipeConsumerState(consumers, pages, docs, control.GroupName, false);
                CheckRenameRoot();
            }

            private Dictionary<int, List<object>> RecipeStrategyProjection(RecipeConsumers consumers, List<StrategyBlock> strategies) {
                var projection = new Dictionary<int, List<object>>();
                foreach (var block in strategies) {
                    var changed = consumers.Scripts.SingleOrDefault(script => script.Strategy != null && script.OwnerId == block.Id);
                    // Selected owners cross the original dirty/save lifecycle. The caller verifies their state independently.
                    var stable = changed == null ? block : new StrategyBlock {
                        Complete = block.Complete, Object = block.Object, Id = block.Id, Name = block.Name,
                        Comment = block.Comment, Rows = block.Rows, Changed = false
                    };
                    projection[block.Id] = StrategyPreservationProof(new List<StrategyBlock> { stable },
                        changed == null ? (IntPtr?)null : changed.Strategy.Program);
                }
                return projection;
            }

            private List<object> RecipeWindowProjection(Dictionary<int, Window> pages, Dictionary<int, IntPtr> docs, RecipeConsumerScript close) {
                var projection = new List<object>();
                foreach (var window in pages.Values.OrderBy(item => item.Id)) {
                    IntPtr document = docs[window.Id];
                    projection.Add(window.Id);
                    foreach (IntPtr control in ReadTopLevelControls(document)) projection.Add(control);
                    projection.Add(context.Text(document, "recipe_rename_page_open_source"));
                    projection.Add(context.Text(document, "recipe_rename_page_cycle_source"));
                    if (window.Id != close.OwnerId) projection.Add(context.Text(document, "recipe_rename_page_close_source"));
                }
                return projection;
            }

            private void VerifyRecipeConsumerState(RecipeConsumers consumers, Dictionary<int, Window> pages,
                Dictionary<int, IntPtr> docs, string group, bool written, bool pendingRootSave = false) {
                var control = consumers.Controls[0];
                Require(context.Ptr(control.Control, "recipe_rename_draw_dll_plugin") == control.Plugin &&
                    context.Text(control.Control, "control_name") == control.ControlName && StuNativeProfile.Text(control.Plugin, 0x28) == group &&
                    ReferencePath(IntPtr.Add(control.Control, Abi.Offset("control_view_offset"))) == control.Linker,
                    "The selected Stu recipe control changed identity or did not retain its expected group binding.");
                var strategies = ReadStrategyBlocks();
                var strategyProjection = RecipeStrategyProjection(consumers, strategies);
                Require(strategyProjection.Count == consumers.Strategies.Count && consumers.Strategies.All(pair =>
                    strategyProjection.ContainsKey(pair.Key) && EqualPayload(pair.Value, strategyProjection[pair.Key])),
                    "An original Stu strategy changed outside the selected recipe sources.");
                Require(EqualPayload(consumers.Windows, RecipeWindowProjection(pages, docs, consumers.Close)),
                    "An original Stu window changed outside the selected recipe sources.");
                foreach (var script in consumers.Scripts.Where(item => item.Strategy != null))
                    Require(SelectStrategyProgram(strategies, script.OwnerId, script.Owner, script.Index).Block.Changed == pendingRootSave,
                        "The selected original Stu recipe strategy has an unexpected pending-save state: " + script.Owner);
                foreach (var script in consumers.Scripts)
                    Require(StuNativeProfile.Text(script.Field, 0, MaxStrategySourceLength) == (written ? script.After : script.Before),
                        "A selected Stu recipe script differs from its exact expected source: " + script.Owner);
            }

            private void ApplyRecipeConsumerWrites(RecipeConsumers consumers, Dictionary<int, Window> pages, Dictionary<int, IntPtr> docs,
                string name, string replacement, Action verifyGraph, Dictionary<string, object> result) {
                var control = consumers.Controls[0];
                Require(context.Ptr(control.Control, "recipe_rename_draw_dll_plugin") == control.Plugin,
                    "The Stu DrawRecipe instance changed during reference rename.");
                result["operation_phase"] = "migrate_recipe_consumers";
                if (StuNativeProfile.Text(control.Plugin, 0x28) == name) {
                    var replace = (ReplaceRecipeBinding)Marshal.GetDelegateForFunctionPointer(control.Replace, typeof(ReplaceRecipeBinding));
                    using (var original = new AuthoringPageString(Abi, name))
                    using (var requested = new AuthoringPageString(Abi, replacement))
                        Require(replace(control.Plugin, 5, original.Storage, requested.Storage) == 1,
                            "The original Stu DrawRecipe group binding did not migrate.");
                }
                var assign = Abi.BindImport<AssignText>("assign_label_text");
                foreach (var script in consumers.Scripts) {
                    string current = StuNativeProfile.Text(script.Field, 0, MaxStrategySourceLength);
                    Require(current == script.Before || current == script.After,
                        "The original Stu rename made additional script changes: " + script.Owner);
                    if (current == script.After) continue;
                    IntPtr wide = Marshal.StringToHGlobalUni(script.After);
                    try { Require(assign(script.Field, wide) == script.Field, "Original Stu recipe script assignment failed."); }
                    finally { Marshal.FreeHGlobal(wide); }
                }
                result["operation_phase"] = "generate_recipe_strategies";
                var generate = Abi.Bind<FinalizeStrategyBlock>("strategy_block_finalize");
                var strategyScripts = consumers.Scripts.Where(item => item.Strategy != null).ToList();
                foreach (var script in strategyScripts) {
                    RequireStrategySelection(script.Strategy);
                    Require(generate(script.Strategy.Block.Object), "The original Stu recipe strategy generation failed: " + script.Owner);
                }
                Abi.CheckRecipeMfcArray(consumers.Close.Cache, "recipe_byte_array");
                Abi.BindImport<ResizeRecipeCache>("recipe_rename_resize_close_cache")(consumers.Close.Cache, 0, -1);
                Require(context.Word(consumers.Close.Cache, "pointer_array_count") == 0, "The obsolete Stu page Exit cache did not clear.");
                Abi.Bind<SetNativeFlag>("set_page_modified")(control.Document, 1);
                verifyGraph();
                VerifyRenameWindows(pages, docs, control.Window.Id, control.Window.Name, false);

                result["operation_phase"] = "prepare_original_recipe_strategy_save";
                var markStrategy = Abi.Bind<SetNativeFlag>("strategy_preload_mark");
                var strategyModified = Abi.Bind<NativeResult>("strategy_block_modified");
                var saveStrategy = Abi.Bind<NativeVoid>("strategy_preload_save");
                foreach (var script in strategyScripts) {
                    markStrategy(script.Preload, 1);
                    Require((strategyModified(script.Strategy.Block.Object) & 0xff) == 1,
                        "The original Stu recipe strategy did not become dirty for saving: " + script.Owner);
                }
                foreach (var script in strategyScripts) saveStrategy(script.Preload);
                VerifyRecipeConsumerState(consumers, pages, docs, replacement, true, true);
                byte[] pending = ReadNamedArchive("StgyAndTrigger");
                Require(pending.SequenceEqual(consumers.StrategyArchiveBefore),
                    "The original Stu strategy archive changed before the root save.");
                result["strategy_pending_root_save_ids"] = strategyScripts.Select(script => script.OwnerId).ToArray();
                result["strategy_archive_before_root_save_sha256"] = RecipeArchiveHash(pending);

                result["operation_phase"] = "save_recipe_consumer_page";
                int saved = Abi.Bind<SaveRenamedDocument>("page_description_database_save")(control.Document, IntPtr.Zero);
                result["native_page_save_return"] = saved;
                Require(saved == 0 && context.Word(control.Document, "document_dirty") == 0,
                    "The original Stu recipe consumer page save failed.");
                result["page_save_verified"] = true;
                result["saved_page_ids"] = new[] { control.Window.Id };
            }

            private string RecipeCloseCacheHash(IntPtr cache, bool nonempty) {
                Abi.CheckRecipeMfcArray(cache, "recipe_byte_array");
                int extent;
                IntPtr buffer = RecipeArray(cache, 1, out extent);
                Require(extent <= MaxStrategySourceLength && (!nonempty || extent > 0), "The original Stu page Exit cache extent is unsupported.");
                var bytes = new byte[extent];
                if (extent > 0) Marshal.Copy(buffer, bytes, 0, extent);
                return RecipeArchiveHash(bytes);
            }

            private void FinishRecipeConsumerWrites(RecipeConsumers consumers, Dictionary<int, Window> pages,
                Dictionary<int, IntPtr> docs, string replacement, Dictionary<string, object> result) {
                VerifyRecipeConsumerState(consumers, pages, docs, replacement, true);
                byte[] archive = ReadNamedArchive("StgyAndTrigger");
                VerifyRecipeStrategyArchive(consumers, archive, true);
                result["strategy_save_verified"] = true;
                result["strategy_archive_after_root_save_sha256"] = RecipeArchiveHash(archive);
                result["page_close_cache_after_source_save_sha256"] = RecipeCloseCacheHash(consumers.Close.Cache, false);
                result["recipe_consumers_after"] = consumers.Readback(true);
                result["script_updates"] = consumers.Scripts.Select(script => {
                    var row = script.Record(false);
                    row["source_after_sha256_utf16le"] = StrategySourceHash(script.After);
                    return row;
                }).ToList();
                result["complete_registered_graph_preserved"] = true;
            }

            private static void VerifyRecipeStrategyArchive(RecipeConsumers consumers, byte[] raw, bool written) {
                var bytes = Encoding.GetEncoding(28591);
                string archive = bytes.GetString(raw);
                foreach (var script in consumers.Scripts.Where(item => item.Strategy != null)) {
                    var expected = bytes.GetString(Encoding.Unicode.GetBytes(written ? script.After : script.Before));
                    var absent = bytes.GetString(Encoding.Unicode.GetBytes(written ? script.Before : script.After));
                    int offset = archive.IndexOf(expected, StringComparison.Ordinal);
                    Require(offset >= 0 && archive.LastIndexOf(expected, StringComparison.Ordinal) == offset && !archive.Contains(absent),
                        "The original Stu strategy archive does not contain precisely the expected recipe source: " + script.Owner);
                }
            }
        }
    }
}

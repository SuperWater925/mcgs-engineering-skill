using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string StrategyCatalogAction = "strategy-catalog", StrategyReadAction = "strategy-source-read", StrategyEditAction = "strategy-source-edit";

        private static bool IsStrategyAction(string action) {
            return action == StrategyCatalogAction || action == StrategyReadAction || action == StrategyEditAction;
        }

        private sealed partial class StuDocument {
            private const int MaxStrategySourceLength = 1048576;

            [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool CompileStrategySource(IntPtr source, IntPtr owner, IntPtr compiled);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool FinalizeStrategyBlock(IntPtr block);

            private sealed class StrategyBlock {
                internal IntPtr Complete, Object;
                internal int Id, Rows;
                internal string Name, Comment;
                internal bool Changed;

                internal Dictionary<string, object> Value() {
                    return new Dictionary<string, object> {
                        {"block_id", Id}, {"block_name", Name}, {"block_comment", Comment},
                        {"row_count", Rows}, {"changed", Changed}
                    };
                }
            }

            private sealed class StrategySelection {
                internal StrategyBlock Block;
                internal int Index;
                internal IntPtr Row, Program;
                internal string Source;
            }

            internal void ApplyStrategyAction(string action, IntPtr mainWindow, object rawOptions, Dictionary<string, object> result) {
                bool editing = action == StrategyEditAction;
                if (editing) {
                    result["write_attempted"] = result["native_result_may_be_partial"] = false;
                    result["native_script_compile_passed"] = result["native_strategy_compiled"] = false;
                    result["native_strategy_saved"] = result["root_save_verified"] = result["native_saved"] = false;
                    result["native_project_compile_required"] = false;
                    result["automatic_retry"] = false;
                    result["operation_phase"] = "validate_preimage";
                }
                AuthoringWorkbench workbench = null;
                StrategySelection selected = null;
                try {
                    VerifyFeature(Abi, action == StrategyCatalogAction ? StrategyCatalogAction : StrategyReadAction);
                    var options = rawOptions == null && action == StrategyCatalogAction ? new Dictionary<string, object>() : StuNativeProfile.Map(rawOptions);
                    var originals = ReadStrategyBlocks();
                    if (action == StrategyCatalogAction) {
                        Require(options.Count == 0, "The Stu strategy catalog takes no options.");
                        var summaries = new List<object>(originals.Count);
                        foreach (var block in originals) summaries.Add(block.Value());
                        result["strategies"] = summaries;
                        result["strategy_count"] = summaries.Count;
                        return;
                    }
                    Require(options.Count == (editing ? 5 : 3) && options.ContainsKey("block_id") && options.ContainsKey("block_name") &&
                        options.ContainsKey("row_index") && (!editing || (options.ContainsKey("expected_source_sha256_utf16le") && options.ContainsKey("source"))),
                        "Select one Stu strategy by original block ID, full name and Prog row index.");
                    selected = SelectStrategyProgram(originals, StuNativeProfile.Number(options["block_id"]),
                        NativeEngineeringDeliveryLayout.Value(options, "block_name"), StuNativeProfile.Number(options["row_index"]));
                    WriteStrategySourceReadback(result, selected);
                    if (!editing) return;

                    string beforeHash = NativeEngineeringDeliveryLayout.Value(options, "expected_source_sha256_utf16le");
                    Require(String.Equals(beforeHash, StrategySourceHash(selected.Source), StringComparison.OrdinalIgnoreCase),
                        "The original Stu strategy source SHA-256 differs from its preimage.");
                    var wanted = options["source"] as string;
                    Require(wanted != null && wanted.Length <= MaxStrategySourceLength && wanted.IndexOf('\0') < 0,
                        "Stu strategy editing requires the complete valid source string.");
                    result["source_before_sha256_utf16le"] = beforeHash.ToLowerInvariant();
                    result["source_requested_sha256_utf16le"] = StrategySourceHash(wanted);
                    if (wanted == selected.Source) {
                        FinishStrategySource(result, selected, wanted, "no_changes");
                        return;
                    }

                    VerifyFeature(Abi, StrategyEditAction);
                    using (var requested = new AuthoringPageString(Abi, wanted, MaxStrategySourceLength)) {
                        Require(Abi.BindImport<NativePointer>("strategy_source_trim_right")(requested.Storage) == requested.Storage,
                            "The original Stu source normalizer returned another string object.");
                        string normalized = StuNativeProfile.Text(requested.Storage, 0, MaxStrategySourceLength);
                        Require(wanted.StartsWith(normalized, StringComparison.Ordinal), "The original Stu source normalizer changed its content.");
                        if (normalized == selected.Source) {
                            FinishStrategySource(result, selected, wanted, "no_changes");
                            return;
                        }

                        IntPtr frame;
                        workbench = OpenAuthoringWorkbench(mainWindow, result, "authoring_strategy_list_index", "strategy_window_workbench", out frame);
                        workbench.Activate();
                        IntPtr preload = VerifyStrategyWriteRoles(selected);
                        RequireClosedStrategyEditor(frame, selected.Block);
                        RequireStrategyProjectClean(frame, originals, result);
                        var before = StrategyPreservationProof(originals, selected.Program);
                        result["operation_phase"] = "native_source_precompile";
                        ValidateStrategySource(selected, requested.Storage, result);
                        RequireStrategySelection(selected);
                        Require(context.Word(context.Root, "document_dirty") == 0 && StrategySource(selected.Program) == selected.Source,
                            "The Stu precompiler unexpectedly changed the editable strategy source or project state.");
                        workbench.RequireTargetActive();
                        ApplyStrategySource(selected, preload, normalized, result);
                        var current = ReadStrategyBlocks();
                        Require(EqualPayload(before, StrategyPreservationProof(current, selected.Program)),
                            "The original Stu strategy save changed an unrelated strategy, trigger identity or Prog source.");
                        var stored = SelectStrategyProgram(current, selected.Block.Id, selected.Block.Name, selected.Index);
                        Require(stored.Row == selected.Row && stored.Program == selected.Program && stored.Source == normalized && !stored.Block.Changed,
                            "The original Stu strategy source did not remain exact after saving.");
                        result["native_strategy_saved"] = true;
                        result["unselected_strategy_nodes_verified"] = true;
                        result["operation_phase"] = "refresh_strategy_workbench";
                        workbench.RefreshTarget();
                        FinishStrategySource(result, stored, wanted, "applied_and_saved");
                        result["native_saved"] = true;
                    }
                } catch (InvalidOperationException error) {
                    if (editing) {
                        FailPageWrite(result, error);
                        if (selected != null && Object.Equals(result["write_attempted"], true)) ObserveStrategySource(selected, result);
                    } else {
                        result["ok"] = false;
                        result["status"] = "native_read_rejected";
                        result["error"] = error.Message;
                    }
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

            private List<StrategyBlock> ReadStrategyBlocks() {
                context.RequireProject();
                Abi.CheckTable(context.Ptr(context.Root, "root_window_model"), "root_window_model");
                IntPtr manager = Abi.Bind<GetModuleObject>("get_module_object")(3);
                Abi.CheckTable(manager, "strategy_manager");
                var blocks = new List<StrategyBlock>();
                var ids = new HashSet<int>();
                Enumerate(manager, "strategy_manager", "strategy_first", "strategy_next", "strategy_count", pointer => {
                    Abi.CheckTable(pointer, "strategy_block_object");
                    IntPtr complete = IntPtr.Subtract(pointer, Abi.Offset("strategy_block_object_offset"));
                    Abi.CheckTable(complete, "strategy_block");
                    int id = context.Word(pointer, "strategy_block_id");
                    string name = context.Text(pointer, "strategy_block_name");
                    IntPtr rowArray = IntPtr.Add(complete, Abi.Offset("strategy_block_rows"));
                    Abi.CheckTable(rowArray, "strategy_block_rows_table");
                    int rows = context.Word(rowArray, "pointer_array_count");
                    Require(id >= 0 && ids.Add(id) && name.Length != 0 && rows >= 0,
                        "The original Stu strategy block identity or row count is invalid.");
                    blocks.Add(new StrategyBlock { Complete = complete, Object = pointer, Id = id, Name = name, Rows = rows,
                        Comment = context.Text(complete, "strategy_block_comment"),
                        Changed = StuNativeProfile.ReadByte(pointer, Abi.Offset("strategy_block_changed")) != 0 });
                });
                return blocks;
            }

            private List<IntPtr> StrategyMembers(IntPtr owner, string field) {
                IntPtr array = IntPtr.Add(owner, Abi.Offset(field));
                Abi.CheckTable(array, field == "strategy_block_rows" ? "strategy_block_rows_table" : "strategy_cell_conditions_table");
                int count = context.Word(array, "pointer_array_count");
                Require(count >= 0 && count <= MaxCatalogEntries && context.Word(array, "pointer_array_capacity") >= count,
                    "The original Stu strategy array size is invalid.");
                IntPtr data = context.Ptr(array, "pointer_array_data");
                Require(count == 0 || StuNativeProfile.Readable(data, checked(count * IntPtr.Size), false),
                    "The original Stu strategy array items are not readable.");
                var members = new List<IntPtr>();
                var addresses = new HashSet<IntPtr>();
                for (int i = 0; i < count; i++) {
                    IntPtr member = StuNativeProfile.Pointer(data, checked(i * IntPtr.Size));
                    Require(member != IntPtr.Zero && addresses.Add(member), "The original Stu strategy array has an invalid member.");
                    members.Add(member);
                }
                return members;
            }

            private StrategySelection SelectStrategyProgram(List<StrategyBlock> blocks, int id, string name, int index) {
                StrategyBlock block = blocks.Find(candidate => candidate.Id == id);
                Require(block != null && block.Name == name, "The exact original Stu strategy block ID and name are absent or changed.");
                var rows = StrategyMembers(block.Complete, "strategy_block_rows");
                Require(index >= 0 && index < rows.Count && rows.Count == block.Rows, "The original Stu strategy row is absent.");
                IntPtr row = rows[index];
                Abi.CheckTable(row, "strategy_row");
                IntPtr program = context.Ptr(row, "strategy_row_action");
                Abi.CheckTable(program, "strategy_program");
                return new StrategySelection { Block = block, Row = row, Program = program, Index = index, Source = StrategySource(program) };
            }

            private string StrategySource(IntPtr program) {
                return StuNativeProfile.Text(program, Abi.Offset("strategy_program_source"), MaxStrategySourceLength);
            }

            private static string StrategySourceHash(string source) {
                try {
                    using (var hash = SHA256.Create())
                        return BitConverter.ToString(hash.ComputeHash(new UnicodeEncoding(false, false, true).GetBytes(source)))
                            .Replace("-", "").ToLowerInvariant();
                } catch (EncoderFallbackException) { throw new InvalidOperationException("The Stu strategy source contains invalid UTF-16."); }
            }

            private static void WriteStrategySourceReadback(Dictionary<string, object> result, StrategySelection selected) {
                result["strategy"] = selected.Block.Value();
                result["row_index"] = selected.Index;
                result["source"] = selected.Source;
                result["source_sha256_utf16le"] = StrategySourceHash(selected.Source);
            }

            private static void FinishStrategySource(Dictionary<string, object> result, StrategySelection selected, string wanted, string status) {
                WriteStrategySourceReadback(result, selected);
                result["source_after"] = selected.Source;
                result["source_after_sha256_utf16le"] = result["source_sha256_utf16le"];
                result["source_normalization"] = wanted == selected.Source ? "exact" : "native_trim_right";
                result["operation_phase"] = "complete";
                result["status"] = status;
            }

            private void RequireStrategySelection(StrategySelection selected) {
                context.RequireProject();
                Abi.CheckTable(selected.Block.Object, "strategy_block_object");
                var rows = StrategyMembers(selected.Block.Complete, "strategy_block_rows");
                Require(context.Word(selected.Block.Object, "strategy_block_id") == selected.Block.Id &&
                    context.Text(selected.Block.Object, "strategy_block_name") == selected.Block.Name &&
                    selected.Index < rows.Count && rows[selected.Index] == selected.Row && context.Ptr(selected.Row, "strategy_row_action") == selected.Program,
                    "The original Stu strategy source selector changed.");
                Abi.CheckTable(selected.Program, "strategy_program");
            }

            private void ObserveStrategySource(StrategySelection selected, Dictionary<string, object> result) {
                try {
                    RequireStrategySelection(selected);
                    var source = StrategySource(selected.Program);
                    result["source_observed"] = source;
                    result["source_observed_sha256_utf16le"] = StrategySourceHash(source);
                } catch (InvalidOperationException error) { result["strategy_observation_error"] = error.Message; }
            }

            private List<object> StrategyPreservationProof(List<StrategyBlock> blocks, IntPtr? changedProgram) {
                var projection = new List<object>();
                int selectedPositions = 0;
                foreach (var block in blocks) {
                    projection.AddRange(new object[] { block.Id, block.Name, block.Comment, block.Complete, block.Object, block.Rows, block.Changed,
                        context.Ptr(block.Complete, "strategy_block_trigger") });
                    var rows = StrategyMembers(block.Complete, "strategy_block_rows");
                    Require(rows.Count == block.Rows, "The original Stu strategy row count changed.");
                    foreach (var row in rows) {
                        Abi.CheckTable(row, "strategy_row");
                        IntPtr program = context.Ptr(row, "strategy_row_action"), cell = context.Ptr(row, "strategy_row_cell");
                        projection.AddRange(new object[] { row, program, cell });
                        if (changedProgram.HasValue && program == changedProgram.Value) selectedPositions++;
                        else if (program != IntPtr.Zero && Abi.IsTable(program, "strategy_program"))
                            projection.Add(StrategySource(program));
                        if (cell == IntPtr.Zero) continue;
                        Abi.CheckTable(cell, "strategy_cell");
                        var conditions = StrategyMembers(cell, "strategy_cell_conditions");
                        projection.Add(conditions.Count);
                        foreach (var condition in conditions) {
                            projection.Add(condition);
                            if (Abi.IsTable(condition, "strategy_condition")) projection.Add(context.Text(condition, "strategy_condition_expression"));
                        }
                    }
                }
                Require(selectedPositions == (changedProgram.HasValue ? 1 : 0),
                    "The selected original Stu Prog object is absent or shared between strategy rows.");
                return projection;
            }

            private void RequireClosedStrategyEditor(IntPtr frame, StrategyBlock block) {
                IntPtr template = context.Ptr(frame, "lifecycle_frame_template_3");
                Abi.CheckSlot(template, "designer_template", 23, "template_first_document");
                Abi.CheckSlot(template, "designer_template", 24, "template_next_document");
                var first = Abi.Bind<FirstDocument>("template_first_document");
                var next = Abi.Bind<NextDocument>("template_next_document");
                var visited = new HashSet<IntPtr>();
                IntPtr position = first(template);
                while (position != IntPtr.Zero) {
                    Require(visited.Count < MaxCatalogEntries && visited.Add(position), "The original Stu strategy editor list is invalid.");
                    IntPtr document = next(template, ref position);
                    Abi.CheckTable(document, "lifecycle_strategy_document");
                    Require(context.Word(document, "strategy_working_document_id") != block.Id &&
                        context.Text(document, "strategy_working_document_name") != block.Name,
                        "The selected Stu strategy has its independent designer view open.");
                }
            }

            private IntPtr VerifyStrategyWriteRoles(StrategySelection selected) {
                RequireStrategySelection(selected);
                Abi.CheckSlot(selected.Program, "strategy_program", 7, "strategy_program_apply");
                Abi.CheckSlot(selected.Block.Object, "strategy_block_object", 21, "strategy_block_finalize");
                Abi.CheckSlot(selected.Block.Object, "strategy_block_object", 28, "strategy_block_modified");
                IntPtr preload = IntPtr.Add(selected.Block.Complete, Abi.Offset("strategy_block_preload_offset"));
                Abi.CheckSlot(preload, "strategy_block_preload", 2, "strategy_preload_save");
                Abi.CheckSlot(preload, "strategy_block_preload", 3, "strategy_preload_mark");
                Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                Abi.CheckSlot(context.Root, "root", 34, "save_root");
                return preload;
            }

            private void RequireStrategyProjectClean(IntPtr frame, List<StrategyBlock> blocks, Dictionary<string, object> result) {
                var isModified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                Require(isModified(context.Root) == 0 && context.Word(context.Root, "document_dirty") == 0,
                    "The original Stu project has unsaved changes.");
                foreach (var block in blocks) Require(!block.Changed, "The original Stu strategy has unsaved changes: " + block.Name);
                result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, isModified, false);
                int compileState = context.Word(context.Root, "root_compile_valid");
                result["original_project_compile_state_before"] = compileState;
                Require(compileState == 0 || compileState == 1, "The original Stu root compile state is invalid.");
            }

            private void ValidateStrategySource(StrategySelection selected, IntPtr source, Dictionary<string, object> result) {
                var create = Abi.BindImport<NativePointer>("construct_recipe_byte_array");
                var destroy = Abi.BindImport<NativeVoid>("destroy_recipe_byte_array");
                int storage = Abi.Offset("strategy_compile_byte_array_size");
                Require(storage > 0, "The original Stu script precompile storage size is invalid.");
                IntPtr compiled = Marshal.AllocHGlobal(storage);
                bool constructed = false;
                try {
                    constructed = create(compiled) == compiled;
                    Require(constructed, "The original Stu script precompile could not construct its output buffer.");
                    Abi.CheckRecipeMfcArray(compiled, "recipe_byte_array");
                    Abi.Bind<NativeResult>("root_clear_diagnostic")(context.Root);
                    bool accepted = Abi.Bind<CompileStrategySource>("compile_strategy_source")(source, selected.Block.Object, compiled);
                    result["native_script_compile_passed"] = accepted;
                    if (!accepted) {
                        result["first_error_object"] = context.Text(context.Root, "root_first_error_owner");
                        result["first_error_message"] = context.Text(context.Root, "root_first_error_text");
                        throw new InvalidOperationException("The original Stu script precompile rejected the source.");
                    }
                    int count = context.Word(compiled, "pointer_array_count");
                    Require(count >= 0 && context.Word(compiled, "pointer_array_capacity") >= count &&
                        (count == 0 || StuNativeProfile.Readable(context.Ptr(compiled, "pointer_array_data"), count, false)),
                        "The original Stu script precompile returned an invalid byte array.");
                } finally {
                    try { if (constructed) destroy(compiled); }
                    finally { Marshal.FreeHGlobal(compiled); }
                }
            }

            private void ApplyStrategySource(StrategySelection selected, IntPtr preload, string source, Dictionary<string, object> result) {
                var assign = Abi.BindImport<AssignText>("assign_label_text");
                var generate = Abi.Bind<FinalizeStrategyBlock>("strategy_block_finalize");
                var modified = Abi.Bind<NativeResult>("strategy_block_modified");
                var nativeSave = Abi.Bind<NativeVoid>("strategy_preload_save");
                Require((modified(selected.Block.Object) & 0xff) == 0 &&
                    Object.Equals(context.Word(context.Root, "root_compile_valid"), result["original_project_compile_state_before"]),
                    "The selected Stu strategy or its project compile state changed before editing.");
                IntPtr wide = Marshal.StringToHGlobalUni(source);
                try {
                    result["read_only"] = false;
                    result["write_attempted"] = true;
                    result["native_project_compile_required"] = true;
                    result["operation_phase"] = "edit_strategy_source";
                    Abi.Bind<SetNativeFlag>("set_root_modified")(context.Root, 1);
                    Require(context.Word(context.Root, "document_dirty") == 1, "The original Stu project modified flag did not persist.");
                    IntPtr field = IntPtr.Add(selected.Program, Abi.Offset("strategy_program_source"));
                    Require(assign(field, wide) == field && StrategySource(selected.Program) == source,
                        "The original Stu Prog source did not take its exact requested value.");
                } finally { Marshal.FreeHGlobal(wide); }

                result["operation_phase"] = "generate_strategy_block";
                bool generated = generate(selected.Block.Object);
                result["native_strategy_compiled"] = generated;
                Require(generated, "The original Stu selected strategy generation failed.");
                RequireStrategySelection(selected);
                Require(StrategySource(selected.Program) == source, "The original Stu generation changed the selected source beyond its native projection.");
                result["operation_phase"] = "save_strategy_block";
                nativeSave(preload);
                result["native_strategy_preload_returned"] = true;

                result["operation_phase"] = "save_root";
                context.RequireProject();
                IntPtr filename = Marshal.StringToHGlobalUni(context.Project);
                try {
                    int saved = Abi.Bind<SaveRoot>("save_root")(context.Root, filename);
                    result["native_root_save_return"] = saved;
                    Require(saved == 1 && context.Word(context.Root, "document_dirty") == 0, "The original Stu root save did not complete.");
                } finally { Marshal.FreeHGlobal(filename); }
                result["root_save_verified"] = true;
                result["operation_phase"] = "verify_saved_strategy";
                result["original_project_compile_state_after"] = context.Word(context.Root, "root_compile_valid");
            }
        }
    }
}

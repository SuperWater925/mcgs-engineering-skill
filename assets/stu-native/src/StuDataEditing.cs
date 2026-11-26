using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string DataCatalogAction = "data-catalog", DataReadAction = "data-read", DataEditAction = "data-edit";
        private static readonly string[] DataTextFields = { "comment", "unit" };

        private static bool IsDataAction(string action) {
            return action == DataCatalogAction || action == DataReadAction || action == DataEditAction;
        }

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void SetVariableText(IntPtr service, int index, IntPtr value);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool SaveDataModule(IntPtr service);

            private sealed class VariableRecord {
                internal readonly IntPtr Object;
                internal int Index, Id, Kind;
                internal string Name, Comment, Unit, Initial;

                internal VariableRecord(IntPtr pointer, int index) { Object = pointer; Index = index; }
                internal string Field(string field) { return field == "comment" ? Comment : Unit; }

                internal Dictionary<string, object> Value() {
                    return new Dictionary<string, object> {
                        {"index", Index}, {"native_id", Id}, {"native_type", Kind}, {"name", Name},
                        {"comment", Comment}, {"unit", Unit}, {"initial_text", Initial}
                    };
                }
            }

            private sealed class VariableTextChange {
                internal string Field, After;
                internal SetVariableText Setter;
            }

            internal void ApplyDataAction(string action, IntPtr mainWindow, object rawOptions, Dictionary<string, object> result) {
                bool editing = action == DataEditAction;
                if (editing) {
                    result["write_attempted"] = result["native_result_may_be_partial"] = false;
                    result["data_module_saved"] = result["project_saved"] = false;
                    result["automatic_retry"] = false;
                    result["operation_phase"] = "validate_preimage";
                }
                var modified = new List<string>();
                if (editing) result["modified_fields"] = modified;
                AuthoringWorkbench workbench = null;
                VariableRecord original = null;
                IntPtr manager = IntPtr.Zero;
                try {
                    Abi.RequireFeature(DataCatalogAction);
                    var options = action == DataCatalogAction && rawOptions == null ? new Dictionary<string, object>() : StuNativeProfile.Map(rawOptions);
                    manager = DataManager();
                    var objects = ReadVariablePointers(manager);
                    if (action == DataCatalogAction) {
                        ReadVariableCatalog(manager, objects, options, result);
                        return;
                    }

                    Require(options.Count == (editing ? 5 : 3) && options.ContainsKey("name") && options.ContainsKey("native_id") &&
                        options.ContainsKey("native_type") && (!editing || (options.ContainsKey("before") && options.ContainsKey("after"))),
                        "The Stu data action requires the current variable name, ID and type and exact edit preimage.");
                    string name = NativeEngineeringDeliveryLayout.Value(options, "name");
                    int id = StuNativeProfile.Number(options["native_id"]), kind = StuNativeProfile.Number(options["native_type"]);
                    int index = FindVariable(objects, name, id, kind, editing);
                    original = ReadVariableRecord(objects[index], index);
                    result["record"] = original.Value();
                    if (!editing) return;

                    Require(kind == 1 || kind == 2 || kind == 3, "Only original Stu scalar variables support comment and unit edits.");
                    var changes = PlanVariableText(options, original);
                    if (changes.Count == 0) {
                        result["operation_phase"] = "complete";
                        result["status"] = "no_changes";
                        return;
                    }

                    VerifyFeature(Abi, DataEditAction);
                    IntPtr service = IntPtr.Add(manager, Abi.Offset("data_manager_service"));
                    foreach (var change in changes) {
                        Abi.RequireFeature("data-edit-" + change.Field);
                        string function = "set_data_" + change.Field;
                        Abi.CheckSlot(service, "data_service", change.Field == "comment" ? 37 : 30, function);
                        change.Setter = Abi.Bind<SetVariableText>(function);
                    }
                    Abi.CheckSlot(service, "data_service", 2, "save_data_module");
                    Abi.CheckSlot(service, "data_service", 40, "set_data_module_dirty");
                    Abi.CheckSlot(service, "data_service", 42, "prepare_data_save");
                    Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                    Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                    Abi.CheckSlot(context.Root, "root", 34, "save_root");
                    var baseline = new List<VariableRecord>(objects.Count);
                    for (int i = 0; i < objects.Count; i++) baseline.Add(i == index ? original : ReadVariableRecord(objects[i], i));
                    var isModified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                    IntPtr frame;
                    workbench = OpenAuthoringWorkbench(mainWindow, result, "authoring_data_list_index", "data_window_workbench", out frame);
                    workbench.Activate();
                    Require(DataManager() == manager && isModified(context.Root) == 0 && DataDirty(manager) == 0,
                        "The current Stu project or real-time database has unsaved changes.");
                    result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, isModified, false);
                    RequireVariableSelection(manager, original);
                    VerifyVariableRecord(original, ReadVariableRecord(original.Object, index), null);

                    result["operation_phase"] = "native_data_text";
                    result["read_only"] = false;
                    result["write_attempted"] = true;
                    foreach (var change in changes) {
                        workbench.RequireTargetActive();
                        IntPtr text = Marshal.StringToHGlobalUni(change.After);
                        try { change.Setter(service, index, text); }
                        finally { Marshal.FreeHGlobal(text); }
                        Require(context.Text(original.Object, "data_" + change.Field) == change.After && DataDirty(manager) == 1,
                            "The original Stu data setter did not retain the requested field: " + change.Field);
                        modified.Add(change.Field);
                    }
                    RequireVariableSelection(manager, original);
                    VerifyVariableRecord(original, ReadVariableRecord(original.Object, index), changes);
                    workbench.RequireTargetActive();
                    SaveVariableChanges(manager, service, result);
                    Require(DataManager() == manager, "The original Stu data manager changed after saving.");
                    var final = ReadVariablePointers(manager);
                    Require(final.Count == baseline.Count, "The original Stu data count changed after saving.");
                    for (int i = 0; i < final.Count; i++)
                        VerifyVariableRecord(baseline[i], ReadVariableRecord(final[i], i), i == index ? changes : null);
                    result["unselected_native_records_verified"] = true;
                    result["record"] = ReadVariableRecord(final[index], index).Value();
                    result["operation_phase"] = "refresh_data_workbench";
                    workbench.RefreshTarget();
                    result["operation_phase"] = "complete";
                    result["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    if (editing) {
                        FailPageWrite(result, error);
                        if (original != null && Object.Equals(result["write_attempted"], true)) {
                            try {
                                RequireVariableSelection(manager, original);
                                result["record"] = ReadVariableRecord(original.Object, original.Index).Value();
                            } catch (InvalidOperationException observation) { result["data_observation_error"] = observation.Message; }
                        }
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

            private IntPtr DataManager() {
                context.RequireProject();
                Abi.CheckTable(context.Ptr(context.Root, "root_window_model"), "root_window_model");
                IntPtr manager = Abi.Bind<GetModuleObject>("get_module_object")(2);
                Abi.CheckTable(manager, "data_manager");
                Abi.CheckTable(IntPtr.Add(manager, Abi.Offset("data_manager_service")), "data_service");
                Require(StuNativeProfile.ReadByte(manager, Abi.Offset("data_module_loaded")) == 1,
                    "The current Stu real-time database design module is unavailable.");
                return manager;
            }

            private byte DataDirty(IntPtr manager) { return StuNativeProfile.ReadByte(manager, Abi.Offset("data_module_dirty")); }

            private List<IntPtr> ReadVariablePointers(IntPtr manager) {
                IntPtr start = context.Ptr(manager, "data_vector_first"), end = context.Ptr(manager, "data_vector_end");
                IntPtr capacity = context.Ptr(manager, "data_vector_capacity");
                long firstAddress = unchecked((uint)start.ToInt32());
                long used = (long)unchecked((uint)end.ToInt32()) - firstAddress;
                long reserved = (long)unchecked((uint)capacity.ToInt32()) - firstAddress;
                Require(used >= 0 && reserved >= used && reserved <= Int32.MaxValue && used % IntPtr.Size == 0 &&
                    reserved % IntPtr.Size == 0 && (start != IntPtr.Zero || (end == IntPtr.Zero && capacity == IntPtr.Zero)),
                    "The original Stu variable vector has an invalid layout.");
                int count = (int)(used / IntPtr.Size);
                var objects = new List<IntPtr>();
                var unique = new HashSet<IntPtr>();
                for (int i = 0; i < count; i++) {
                    IntPtr pointer = StuNativeProfile.Pointer(start, i * IntPtr.Size);
                    if (i == 0) Abi.CheckTable(pointer, "data_object");
                    else Require(Abi.IsTable(pointer, "data_object"), "An original Stu variable has an unsupported object type.");
                    Require(unique.Add(pointer), "The original Stu variable vector repeats an object.");
                    objects.Add(pointer);
                }
                Require(context.Ptr(manager, "data_vector_first") == start && context.Ptr(manager, "data_vector_end") == end &&
                    context.Ptr(manager, "data_vector_capacity") == capacity, "The original Stu variable vector changed during the read.");
                return objects;
            }

            private VariableRecord ReadVariableRecord(IntPtr pointer, int index) {
                return new VariableRecord(pointer, index) {
                    Id = context.Word(pointer, "data_native_id"), Kind = context.Word(pointer, "data_native_type"),
                    Name = context.Text(pointer, "data_name"), Comment = context.Text(pointer, "data_comment"),
                    Unit = context.Text(pointer, "data_unit"), Initial = context.Text(pointer, "data_initial_text")
                };
            }

            private int FindVariable(List<IntPtr> objects, string name, int id, int kind, bool editing) {
                int index = -1, idCount = 0;
                for (int i = 0; i < objects.Count; i++) {
                    var pointer = objects[i];
                    int currentId = context.Word(pointer, "data_native_id");
                    if (currentId == id) idCount++;
                    if (context.Text(pointer, "data_name") != name) continue;
                    Require(index < 0 && currentId == id && context.Word(pointer, "data_native_type") == kind,
                        "The exact original Stu variable name, ID and type are ambiguous or changed.");
                    index = i;
                }
                Require(index >= 0 && (!editing || (id >= 0 && idCount == 1)), "The exact original Stu variable identity is absent or ambiguous.");
                return index;
            }

            private void RequireVariableSelection(IntPtr manager, VariableRecord original) {
                Require(DataManager() == manager, "The original Stu data manager changed.");
                IntPtr first = context.Ptr(manager, "data_vector_first"), end = context.Ptr(manager, "data_vector_end");
                long length = (long)unchecked((uint)end.ToInt32()) - unchecked((uint)first.ToInt32());
                Require(first != IntPtr.Zero && length >= (long)(original.Index + 1) * IntPtr.Size &&
                    StuNativeProfile.Pointer(first, original.Index * IntPtr.Size) == original.Object &&
                    Abi.IsTable(original.Object, "data_object") && context.Text(original.Object, "data_name") == original.Name &&
                    context.Word(original.Object, "data_native_id") == original.Id && context.Word(original.Object, "data_native_type") == original.Kind,
                    "The original Stu variable selector changed before write or readback.");
            }

            private void ReadVariableCatalog(IntPtr manager, List<IntPtr> objects, Dictionary<string, object> options, Dictionary<string, object> result) {
                foreach (string key in options.Keys)
                    Require(key == "name" || key == "offset" || key == "limit", "The Stu data catalog accepts name, offset and limit.");
                string name = options.ContainsKey("name") ? NativeEngineeringDeliveryLayout.Value(options, "name") : String.Empty;
                int offset = options.ContainsKey("offset") ? StuNativeProfile.Number(options["offset"]) : 0;
                int limit = options.ContainsKey("limit") ? StuNativeProfile.Number(options["limit"]) : 256;
                Require(offset >= 0 && offset <= objects.Count && limit > 0 && limit <= 4096, "The requested Stu data catalog page is invalid.");
                var records = new List<object>();
                int next = offset;
                while (next < objects.Count && records.Count < limit) {
                    int index = next++;
                    var pointer = objects[index];
                    if (name.Length == 0 || context.Text(pointer, "data_name").IndexOf(name, StringComparison.OrdinalIgnoreCase) >= 0)
                        records.Add(ReadVariableRecord(pointer, index).Value());
                }
                result["data_count"] = objects.Count;
                result["offset"] = offset;
                result["next_offset"] = next == objects.Count ? (object)null : next;
                result["data_module_dirty"] = DataDirty(manager);
                result["records"] = records;
            }

            private static List<VariableTextChange> PlanVariableText(Dictionary<string, object> options, VariableRecord original) {
                var before = StuNativeProfile.Map(options["before"]);
                var after = StuNativeProfile.Map(options["after"]);
                Require(before.Count != 0 && before.Count == after.Count && before.Count <= DataTextFields.Length,
                    "A Stu scalar edit needs matching original and desired comment or unit fields.");
                var result = new List<VariableTextChange>();
                foreach (var item in before) {
                    object requested;
                    string prior = item.Value as string;
                    Require(Array.IndexOf(DataTextFields, item.Key) >= 0 && prior != null && prior == original.Field(item.Key),
                        "The original Stu comment or unit differs from its edit preimage.");
                    Require(after.TryGetValue(item.Key, out requested) && requested is string, "The requested Stu data field value is not text.");
                    string next = (string)requested;
                    Require(next.Length <= 32768 && next.IndexOf('\0') < 0, "The requested Stu data text does not fit the native string contract.");
                    if (next != prior) result.Add(new VariableTextChange { Field = item.Key, After = next });
                }
                return result;
            }

            private static void VerifyVariableRecord(VariableRecord before, VariableRecord after, List<VariableTextChange> changes) {
                string comment = before.Comment, unit = before.Unit;
                if (changes != null) foreach (var change in changes) {
                    if (change.Field == "comment") comment = change.After;
                    else unit = change.After;
                }
                Require(before.Object == after.Object && before.Index == after.Index && before.Id == after.Id && before.Kind == after.Kind &&
                    before.Name == after.Name && before.Initial == after.Initial && comment == after.Comment && unit == after.Unit,
                    "The original Stu variable identity, requested text or unrelated data changed: " + before.Name);
            }

            private void SaveVariableChanges(IntPtr manager, IntPtr service, Dictionary<string, object> result) {
                context.RequireProject();
                Abi.Bind<SetNativeFlag>("set_root_modified")(context.Root, 1);
                Require(context.Word(context.Root, "document_dirty") == 1, "Stu did not mark the original root modified.");
                result["operation_phase"] = "save_data_module";
                bool moduleSaved = Abi.Bind<SaveDataModule>("save_data_module")(service);
                result["native_data_module_save_return"] = moduleSaved;
                Require(moduleSaved && DataDirty(manager) == 0, "The original Stu real-time database did not save.");
                result["data_module_saved"] = true;
                result["operation_phase"] = "save_root";
                IntPtr filename = Marshal.StringToHGlobalUni(context.Project);
                try {
                    int saved = Abi.Bind<SaveRoot>("save_root")(context.Root, filename);
                    result["native_root_save_return"] = saved;
                    Require(saved == 1 && context.Word(context.Root, "document_dirty") == 0, "The original Stu root did not save.");
                } finally { Marshal.FreeHGlobal(filename); }
                result["project_saved"] = true;
                result["operation_phase"] = "verify_saved_data";
            }
        }
    }
}

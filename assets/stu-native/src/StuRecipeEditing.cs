using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string RecipeCatalogAction = "recipe-catalog";
        private const string RecipeReadAction = "recipe-read";
        private const string RecipeEditAction = "recipe-cell-edit";

        private static bool IsRecipeAction(string action) {
            return action == RecipeCatalogAction || action == RecipeReadAction || action == RecipeEditAction;
        }

        private sealed partial class StuDocument {
            private static readonly UnicodeEncoding RecipeWireEncoding = new UnicodeEncoding(false, false, true);

            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void PutRecipeText(IntPtr row, int column, IntPtr text);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void SaveNamedRecipe(IntPtr recipe);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr ConstructRecipeBytes(IntPtr array);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void DestroyRecipeBytes(IntPtr array);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool ReadNamedRecipeBytes(IntPtr root, IntPtr key, IntPtr array);

            private sealed class RecipeRecord {
                internal readonly IntPtr Pointer, Columns, Rows;
                internal readonly string Name;
                internal readonly int ColumnCount, RowCount;

                internal RecipeRecord(IntPtr pointer, string name, IntPtr columns, int columnCount,
                    IntPtr rows, int rowCount) {
                    Pointer = pointer;
                    Name = name;
                    Columns = columns;
                    ColumnCount = columnCount;
                    Rows = rows;
                    RowCount = rowCount;
                }

                internal Dictionary<string, object> Summary() {
                    return new Dictionary<string, object> {
                        {"group_name", Name}, {"row_count", RowCount}, {"column_count", ColumnCount}
                    };
                }
            }

            internal void ApplyRecipeAction(string action, IntPtr mainWindow, object rawOptions,
                Dictionary<string, object> result) {
                bool editing = action == RecipeEditAction;
                if (editing) {
                    result["write_attempted"] = result["native_result_may_be_partial"] = false;
                    result["recipe_save_verified"] = result["root_save_verified"] = result["project_saved"] = false;
                    result["automatic_retry"] = false;
                    result["operation_phase"] = "validate_preimage";
                }
                AuthoringWorkbench workbench = null;
                try {
                    VerifyFeature(Abi, action);
                    IntPtr manager = RecipeManager();
                    result["recipe_module_dirty"] = (int)RecipeDirty(manager);
                    var recipes = ReadRecipeDirectory(manager);
                    if (action == RecipeCatalogAction) {
                        Require(rawOptions == null || StuNativeProfile.Map(rawOptions).Count == 0,
                            "The Stu recipe catalog takes no arguments.");
                        result["recipe_count"] = recipes.Count;
                        var summaries = new List<Dictionary<string, object>>(recipes.Count);
                        foreach (var recipe in recipes) summaries.Add(recipe.Summary());
                        result["recipes"] = summaries;
                        return;
                    }

                    var options = StuNativeProfile.Map(rawOptions);
                    string name = RecipeOptionText(options, "group_name", false);
                    RecipeRecord selected = SelectRecipe(recipes, name);
                    if (action == RecipeReadAction) {
                        foreach (string key in options.Keys)
                            Require(key == "group_name" || key == "offset" || key == "limit", "Unknown Stu recipe read option: " + key);
                        int offset = options.ContainsKey("offset") ? StuNativeProfile.Number(options["offset"]) : 0;
                        int limit = options.ContainsKey("limit") ? StuNativeProfile.Number(options["limit"]) : 100;
                        result["record"] = ReadRecipeRows(selected, offset, limit);
                        return;
                    }

                    Require(options.Count == 5, "Stu recipe edits require an exact group, zero-based row and column, expected and after.");
                    int rowIndex = RecipeIndex(options, "row_index", selected.RowCount);
                    int columnIndex = RecipeIndex(options, "column_index", selected.ColumnCount);
                    string before = RecipeOptionText(options, "expected", true);
                    string after = RecipeOptionText(options, "after", true);
                    Require(name.Length <= Abi.Offset("recipe_storage_max_name"), "The selected Stu recipe cannot fit its original storage key.");
                    ValidateRecipeValue(context.Word(RecipeColumn(selected, columnIndex), "recipe_column_kind"), after);
                    IntPtr row;
                    Require(RecipeCell(selected, rowIndex, columnIndex, out row) == before, "The live Stu recipe cell differs from the requested preimage.");
                    string keyName = "MCGS_RECIPE_" + name;
                    byte[] original = ReadRecipeArchive(keyName);
                    int begin, end;
                    Require(ReadArchivedRecipeCell(original, selected, rowIndex, columnIndex, out begin, out end) == before,
                        "The live and persisted Stu recipe preimages differ.");

                    result["group_name"] = name;
                    result["row_index"] = rowIndex;
                    result["column_index"] = columnIndex;
                    result["expected"] = before;
                    result["changed"] = before != after;
                    if (before == after) {
                        result["value"] = before;
                        result["native_named_recipe_readback"] = result["other_target_recipe_bytes_preserved"] = true;
                        result["operation_phase"] = "complete";
                        result["status"] = "no_changes";
                        return;
                    }

                    Abi.RequireFeature("recipe-edit-workbench");
                    IntPtr frame;
                    workbench = OpenAuthoringWorkbench(mainWindow, result, "authoring_data_list_index", "data_window_workbench", out frame);
                    workbench.Activate();
                    Require(RecipeManager() == manager, "The Stu recipe manager changed while activating the project workbench.");
                    var isModified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                    Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                    Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                    Abi.CheckSlot(context.Root, "root", 34, "save_root");
                    Require(isModified(context.Root) == 0 && RecipeDirty(manager) == 0, "The Stu project or recipe module has unsaved changes.");
                    result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, isModified, false);
                    RecipeRecord current = SelectRecipe(ReadRecipeDirectory(manager), name);
                    Require(SameRecipe(selected, current), "The Stu recipe changed before writing.");
                    IntPtr currentRow;
                    Require(RecipeCell(current, rowIndex, columnIndex, out currentRow) == before &&
                        currentRow == row, "The Stu recipe or target row changed before writing.");
                    var setter = Abi.Bind<PutRecipeText>("set_recipe_cell");
                    var save = Abi.Bind<SaveNamedRecipe>("save_named_recipe");
                    int nativeVersion = Abi.GlobalWord("recipe_wire_version");
                    workbench.RequireTargetActive();
                    result["read_only"] = false;
                    result["write_attempted"] = true;
                    result["operation_phase"] = "native_recipe_cell";
                    IntPtr newValue = Marshal.StringToHGlobalUni(after);
                    try { setter(currentRow, columnIndex, newValue); }
                    finally { Marshal.FreeHGlobal(newValue); }
                    Require(RecipeCell(current, rowIndex, columnIndex, out currentRow) == after &&
                        RecipeDirty(manager) == 0, "The original Stu cell setter did not retain the expected value and module state.");
                    result["operation_phase"] = "save_named_recipe";
                    save(current.Pointer);
                    VerifySavedRecipe(keyName, original, current, rowIndex, columnIndex, after, begin, end, nativeVersion);
                    result["recipe_save_verified"] = true;
                    result["operation_phase"] = "save_root";
                    SaveRecipeRoot(isModified);
                    result["root_save_verified"] = result["project_saved"] = true;

                    context.RequireProject();
                    Require(RecipeManager() == manager && RecipeDirty(manager) == 0,
                        "The Stu recipe manager or its modification state changed after saving.");
                    result["recipe_module_dirty"] = (int)RecipeDirty(manager);
                    result["root_document_dirty"] = isModified(context.Root);
                    var final = SelectRecipe(ReadRecipeDirectory(manager), name);
                    Require(SameRecipe(current, final) && RecipeCell(final, rowIndex, columnIndex, out currentRow) == after,
                        "The live Stu recipe differs from the requested value after root save.");
                    VerifySavedRecipe(keyName, original, final, rowIndex, columnIndex, after, begin, end, nativeVersion);
                    result["value"] = after;
                    result["native_named_recipe_readback"] = result["other_target_recipe_bytes_preserved"] = true;
                    result["original_archive_version_bits"] = BitConverter.ToInt32(original, 0);
                    result["saved_archive_version_bits"] = nativeVersion;
                    result["operation_phase"] = "complete";
                    result["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    if (editing) FailPageWrite(result, error);
                    else {
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

            private IntPtr RecipeManager() {
                context.RequireProject();
                Abi.CheckTable(context.Ptr(context.Root, "root_window_model"), "root_window_model");
                IntPtr manager = Abi.Bind<GetModuleObject>("get_module_object")(4);
                Abi.CheckTable(manager, "recipe_manager");
                Require(StuNativeProfile.ReadByte(manager, Abi.Offset("recipe_module_loaded")) == 1, "Stu has not loaded its original recipe module.");
                return manager;
            }

            private byte RecipeDirty(IntPtr manager) {
                return StuNativeProfile.ReadByte(manager, Abi.Offset("recipe_module_dirty"));
            }

            private List<RecipeRecord> ReadRecipeDirectory(IntPtr manager) {
                int count = context.Word(manager, "recipe_list_count");
                IntPtr sentinel = context.Ptr(manager, "recipe_list_sentinel");
                Require(count >= 0 && sentinel != IntPtr.Zero, "The Stu recipe directory header is invalid.");
                var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                var recipes = new List<RecipeRecord>();
                IntPtr previous = sentinel, node = context.Ptr(sentinel, "recipe_node_next");
                for (int i = 0; i < count; i++) {
                    Require(node != sentinel && context.Ptr(node, "recipe_node_previous") == previous, "The Stu recipe directory has invalid links.");
                    IntPtr recipe = context.Ptr(node, "recipe_node_value");
                    Abi.CheckTable(recipe, "recipe_object");
                    string name = context.Text(recipe, "recipe_name");
                    Require(name.Length != 0 && names.Add(name), "The Stu recipe directory contains an empty or duplicate group name.");
                    IntPtr columns = IntPtr.Add(recipe, Abi.Offset("recipe_columns"));
                    IntPtr rows = IntPtr.Add(recipe, Abi.Offset("recipe_rows"));
                    Abi.CheckTable(columns, "recipe_column_array");
                    Abi.CheckTable(rows, "recipe_row_pointer_array");
                    int columnCount, rowCount;
                    IntPtr columnData = RecipeArray(columns, Abi.Offset("recipe_column_stride"), out columnCount);
                    IntPtr rowData = RecipeArray(rows, IntPtr.Size, out rowCount);
                    recipes.Add(new RecipeRecord(recipe, name, columnData, columnCount, rowData, rowCount));
                    previous = node;
                    node = context.Ptr(node, "recipe_node_next");
                }
                Require(node == sentinel && context.Ptr(sentinel, "recipe_node_previous") == previous &&
                    count == context.Word(manager, "recipe_list_count"), "The Stu recipe directory changed during traversal.");
                return recipes;
            }

            private IntPtr RecipeArray(IntPtr array, int stride, out int count) {
                count = context.Word(array, "recipe_array_count");
                int capacity = context.Word(array, "recipe_array_capacity");
                IntPtr fields = context.Ptr(array, "recipe_array_data");
                Require(stride > 0 && count >= 0 && capacity >= count && count <= Int32.MaxValue / stride &&
                    (count == 0 || StuNativeProfile.Readable(fields, count * stride, false)),
                    "An original Stu recipe array has an invalid count, capacity or allocation.");
                return fields;
            }

            private IntPtr RecipeColumn(RecipeRecord recipe, int column) {
                IntPtr item = IntPtr.Add(recipe.Columns, checked(column * Abi.Offset("recipe_column_stride")));
                Abi.CheckTable(item, "recipe_column");
                Abi.CheckTable(IntPtr.Add(item, Abi.Offset("recipe_column_interface")), "recipe_column_interface");
                return item;
            }

            private IntPtr RecipeRow(RecipeRecord recipe, int index, out IntPtr row) {
                row = StuNativeProfile.Pointer(recipe.Rows, checked(index * IntPtr.Size));
                Abi.CheckRecipeMfcArray(row, "recipe_string_array");
                int count;
                IntPtr cells = RecipeArray(row, IntPtr.Size, out count);
                Require(count == recipe.ColumnCount, "An original Stu recipe row differs from its column definitions.");
                return cells;
            }

            private string RecipeCell(RecipeRecord recipe, int rowIndex, int column, out IntPtr row) {
                return StuNativeProfile.Text(RecipeRow(recipe, rowIndex, out row), checked(column * IntPtr.Size));
            }

            private Dictionary<string, object> ReadRecipeRows(RecipeRecord recipe, int offset, int limit) {
                Require(offset >= 0 && offset <= recipe.RowCount && limit > 0, "Stu recipe pagination is outside the original row count.");
                var result = recipe.Summary();
                var columns = new List<Dictionary<string, object>>(recipe.ColumnCount);
                for (int index = 0; index < recipe.ColumnCount; index++) {
                    IntPtr column = RecipeColumn(recipe, index);
                    columns.Add(new Dictionary<string, object> {
                        {"index", index}, {"variable_name", context.Text(column, "recipe_column_binding")},
                        {"caption", context.Text(column, "recipe_column_caption")}, {"native_kind", context.Word(column, "recipe_column_kind")}
                    });
                }
                var rows = new List<string[]>();
                int requested = Math.Min(limit, recipe.RowCount - offset);
                for (int index = 0; index < requested; index++) {
                    IntPtr row;
                    IntPtr cells = RecipeRow(recipe, offset + index, out row);
                    var values = new string[recipe.ColumnCount];
                    for (int column = 0; column < values.Length; column++) values[column] = StuNativeProfile.Text(cells, column * IntPtr.Size);
                    rows.Add(values);
                }
                result["columns"] = columns;
                result["row_offset"] = offset;
                result["rows"] = rows;
                return result;
            }

            private static RecipeRecord SelectRecipe(List<RecipeRecord> recipes, string name) {
                foreach (var recipe in recipes) if (recipe.Name == name) return recipe;
                throw new InvalidOperationException("The exact Stu recipe group name does not exist.");
            }

            private static bool SameRecipe(RecipeRecord before, RecipeRecord after) {
                return before.Pointer == after.Pointer && before.Name == after.Name &&
                    before.RowCount == after.RowCount && before.ColumnCount == after.ColumnCount;
            }

            private static int RecipeIndex(Dictionary<string, object> options, string name, int count) {
                object value;
                Require(options.TryGetValue(name, out value), "Missing Stu recipe index: " + name);
                int index = StuNativeProfile.Number(value);
                Require(index >= 0 && index < count, "The selected Stu recipe index is outside the original group: " + name);
                return index;
            }

            private static string RecipeOptionText(Dictionary<string, object> options, string name, bool allowEmpty) {
                object value;
                Require(options.TryGetValue(name, out value) && value is string, "Missing Stu recipe string: " + name);
                string text = (string)value;
                Require((allowEmpty || text.Length != 0) && text.IndexOf('\0') < 0, "Invalid Stu recipe string: " + name);
                if (name == "after") {
                    Require(text.Length <= 32768, "The requested value exceeds the original Stu live CString readback bounds.");
                    try { RecipeWireEncoding.GetByteCount(text); }
                    catch (EncoderFallbackException error) { throw new InvalidOperationException("The recipe value contains invalid UTF-16.", error); }
                }
                return text;
            }

            private static void ValidateRecipeValue(int kind, string value) {
                int integer;
                double real;
                var format = CultureInfo.InvariantCulture;
                var sign = NumberStyles.AllowLeadingSign;
                if (kind == 1) Require(Int32.TryParse(value, sign, format, out integer), "The Stu integer recipe column requires a signed 32-bit decimal value.");
                else if (kind == 2) Require(Double.TryParse(value, sign | NumberStyles.AllowDecimalPoint | NumberStyles.AllowExponent,
                    format, out real) && !Double.IsNaN(real) && !Double.IsInfinity(real), "The Stu numeric recipe column requires a finite decimal value.");
                else Require(kind == 3, "The selected Stu recipe column kind has no verified setter contract.");
            }

            private void SaveRecipeRoot(LifecycleIsModified isModified) {
                context.RequireProject();
                IntPtr filename = Marshal.StringToHGlobalUni(context.Project);
                try {
                    Abi.Bind<SetNativeFlag>("set_root_modified")(context.Root, 1);
                    Require(Abi.Bind<SaveRoot>("save_root")(context.Root, filename) == 1 && isModified(context.Root) == 0,
                        "The original Stu root save did not return a clean document.");
                } finally { Marshal.FreeHGlobal(filename); }
            }

            private byte[] ReadRecipeArchive(string key) {
                var construct = Abi.BindImport<ConstructRecipeBytes>("construct_recipe_byte_array");
                var destroy = Abi.BindImport<DestroyRecipeBytes>("destroy_recipe_byte_array");
                var read = Abi.Bind<ReadNamedRecipeBytes>("read_named_recipe_bytes");
                int size = Abi.Offset("recipe_byte_array_size");
                IntPtr storage = Marshal.AllocHGlobal(size);
                IntPtr name = IntPtr.Zero;
                bool created = false;
                try {
                    for (int offset = 0; offset < size; offset += sizeof(int)) Marshal.WriteInt32(storage, offset, 0);
                    name = Marshal.StringToHGlobalUni(key);
                    created = construct(storage) == storage;
                    Require(created, "Stu failed to construct the native recipe byte array.");
                    Abi.CheckRecipeMfcArray(storage, "recipe_byte_array");
                    context.RequireProject();
                    Require(read(context.Root, name, storage), "The original Stu root cannot read the selected named recipe archive.");
                    Abi.CheckRecipeMfcArray(storage, "recipe_byte_array");
                    int length;
                    IntPtr bytes = RecipeArray(storage, 1, out length);
                    Require(length >= sizeof(int), "The original Stu recipe archive is incomplete.");
                    var result = new byte[length];
                    Marshal.Copy(bytes, result, 0, length);
                    return result;
                } finally {
                    if (created) destroy(storage);
                    Marshal.FreeHGlobal(storage);
                    if (name != IntPtr.Zero) Marshal.FreeHGlobal(name);
                }
            }

            private static string ReadArchivedRecipeCell(byte[] archive, RecipeRecord recipe, int rowIndex, int column,
                out int begin, out int end) {
                try { return FindRecipeCell(archive, recipe, rowIndex, column, out begin, out end); }
                catch (EndOfStreamException error) { throw new InvalidOperationException("The original Stu recipe archive is truncated.", error); }
                catch (DecoderFallbackException error) { throw new InvalidOperationException("The original Stu recipe archive contains invalid UTF-16.", error); }
            }

            private static string FindRecipeCell(byte[] archive, RecipeRecord recipe, int rowIndex, int column,
                out int begin, out int end) {
                begin = end = 0;
                string value = null;
                using (var reader = new BinaryReader(new MemoryStream(archive, false))) {
                    reader.ReadInt32();
                    Require(ReadRecipeString(reader) == recipe.Name && reader.ReadInt32() == recipe.ColumnCount,
                        "The original Stu archive name or column count differs from the live recipe.");
                    for (int i = 0; i < recipe.ColumnCount; i++) {
                        ReadRecipeString(reader);
                        ReadRecipeString(reader);
                        reader.ReadInt32();
                    }
                    Require(reader.ReadInt32() == recipe.RowCount, "The original Stu archive row count differs from the live recipe.");
                    for (int row = 0; row < recipe.RowCount; row++) {
                        int width = reader.ReadUInt16();
                        if (width == UInt16.MaxValue) width = reader.ReadInt32();
                        Require(width == recipe.ColumnCount, "The original Stu archived row has a different column count.");
                        for (int i = 0; i < width; i++) {
                            int cursor = (int)reader.BaseStream.Position;
                            string cell = ReadRecipeString(reader);
                            if (row == rowIndex && i == column) {
                                begin = cursor;
                                end = (int)reader.BaseStream.Position;
                                value = cell;
                            }
                        }
                    }
                }
                Require(value != null, "The original Stu named archive does not contain the selected cell.");
                return value;
            }

            private static string ReadRecipeString(BinaryReader reader) {
                Require(reader.ReadByte() == Byte.MaxValue && reader.ReadUInt16() == 65534,
                    "The original Stu recipe string does not use the verified Unicode envelope.");
                int length = reader.ReadByte();
                if (length == Byte.MaxValue) {
                    length = reader.ReadUInt16();
                    if (length == UInt16.MaxValue) length = reader.ReadInt32();
                }
                Require(length >= 0 && length <= (reader.BaseStream.Length - reader.BaseStream.Position) / 2,
                    "The original Stu recipe string runs past the archive.");
                return RecipeWireEncoding.GetString(reader.ReadBytes(checked(length * 2)));
            }

            private void VerifySavedRecipe(string key, byte[] original, RecipeRecord recipe, int rowIndex, int column,
                string expected, int begin, int end, int version) {
                byte[] saved = ReadRecipeArchive(key);
                int actualBegin, actualEnd;
                Require(ReadArchivedRecipeCell(saved, recipe, rowIndex, column, out actualBegin, out actualEnd) == expected &&
                    BitConverter.ToInt32(saved, 0) == version && begin == actualBegin &&
                    saved.Length - actualEnd == original.Length - end &&
                    SameRecipeBytes(original, sizeof(int), saved, sizeof(int), begin - sizeof(int)) &&
                    SameRecipeBytes(original, end, saved, actualEnd, original.Length - end),
                    "The original Stu archive did not preserve bytes outside the selected cell and archive version.");
            }

            private static bool SameRecipeBytes(byte[] left, int start, byte[] right, int offset, int length) {
                for (int index = 0; index < length; index++) if (left[start + index] != right[offset + index]) return false;
                return true;
            }
        }
    }
}

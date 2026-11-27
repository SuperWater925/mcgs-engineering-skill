using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Xml;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string PictureCatalogAction = "picture-catalog", PictureImportAction = "picture-import",
            PictureCopyAction = "picture-copy", PictureReplaceAction = "picture-replace", PictureExportAction = "picture-export";

        private static bool IsPictureAction(string action) {
            return action == PictureCatalogAction || action == PictureImportAction || action == PictureCopyAction ||
                action == PictureReplaceAction || action == PictureExportAction;
        }

        private static void VerifyPictureFeature(string action, StuNativeProfile abi) {
            abi.RequireFeature(PictureCatalogAction);
            if (action == PictureCatalogAction) return;
            abi.RequireFeature(PictureExportAction);
            if (action == PictureExportAction) return;
            abi.RequireFeature("picture-mutate");
            abi.RequireFeature("page-authoring-common");
            if (action == PictureImportAction || action == PictureCopyAction) abi.RequireFeature(PictureCopyAction);
            if (action == PictureImportAction || action == PictureReplaceAction) abi.RequireFeature("picture-load-image");
            abi.RequireFeature(action);
        }

        private sealed partial class StuDocument {
            internal void ApplyPicture(string action, IntPtr mainWindow, object options, Dictionary<string, object> result) {
                bool catalog = action == PictureCatalogAction, export = action == PictureExportAction;
                bool writing = !catalog && !export;
                if (writing) {
                    result["write_attempted"] = result["native_result_may_be_partial"] = false;
                    result["native_module_saved"] = result["root_saved"] = false;
                }
                result["operation_phase"] = "validate_preimage";
                result["automatic_retry"] = false;
                try {
                    VerifyPictureFeature(action, Abi);
                    var spec = catalog && options == null ? new Dictionary<string, object>() : StuNativeProfile.Map(options);
                    IntPtr manager = PictureManager();
                    var before = ReadPictures(manager);
                    result["picture_count"] = before.Count;
                    if (catalog) {
                        Require(spec.Keys.All(key => key == "offset" || key == "limit"), "The Stu picture catalog accepts offset and limit.");
                        int offset = PictureOption(spec, "offset", 0, 0, before.Count);
                        int limit = PictureOption(spec, "limit", 128, 1, 4096);
                        result["records"] = before.Skip(offset).Take(limit).Select(row => row.Value()).ToList();
                        result["picture_module_dirty"] = (int)PictureDirty(manager);
                        result["root_document_dirty"] = context.Word(context.Root, "document_dirty");
                        return;
                    }
                    string name = NativeEngineeringDeliveryLayout.Value(spec, "name");
                    Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                    var modified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                    Require(modified(context.Root) == 0 && context.Word(context.Root, "document_dirty") == 0 && PictureDirty(manager) == 0,
                        "The original Stu project or picture library has unsaved changes.");
                    byte[] originalIndex = ReadPictureIndex(before, before.Count == 0 && writing);
                    if (export) {
                        PictureKeys(spec, "name", "expected_content_hash", "destination_file");
                        var selected = SelectedPicture(before, name, NativeEngineeringDeliveryLayout.Value(spec, "expected_content_hash"));
                        string path = PicturePath(NativeEngineeringDeliveryLayout.Value(spec, "destination_file"), true);
                        byte[] data = ReadSavedPicture(selected);
                        WritePictureExport(path, selected.Kind, data);
                        result["record"] = selected.Value();
                        result["destination_file"] = path;
                        result["file_written"] = true;
                        result["file_bytes"] = data.Length;
                        result["file_sha256"] = StuPictureHex(data);
                        result["operation_phase"] = "complete";
                        return;
                    }
                    Require(PictureOption(spec, "expected_count", -1, 0, MaxCatalogEntries) == before.Count,
                        "The original Stu picture count differs from its preimage.");
                    IntPtr frame = Abi.Bind<GetApplication>("get_main_frame")();
                    Abi.CheckTable(frame, "frame");
                    Require(context.Ptr(frame, "frame_hwnd") == mainWindow, "The active Stu workbench differs from the captured window.");
                    result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, modified, false);
                    IntPtr service = IntPtr.Add(manager, Abi.Offset("picture_service_offset"));
                    Abi.CheckSlot(service, "picture_service", 2, "picture_manager_save");
                    Abi.CheckSlot(service, "picture_service", 3, "picture_manager_dirty");
                    Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                    Abi.CheckSlot(context.Root, "root", 34, "save_root");
                    PictureRecord source = null, replace = null;
                    StuPictureFile input = null;
                    byte[] expected;
                    if (action == PictureReplaceAction) {
                        PictureKeys(spec, "name", "expected_count", "expected_content_hash", "source_file", "source_sha256");
                        replace = SelectedPicture(before, name, NativeEngineeringDeliveryLayout.Value(spec, "expected_content_hash"));
                        byte[] prior = ReadSavedPicture(replace);
                        input = PictureSource(spec);
                        Require(replace.Kind != input.Kind || !prior.SequenceEqual(input.Bytes), "The original Stu picture already contains these file bytes.");
                        expected = input.Bytes;
                    } else {
                        Require(name.Length <= 64 && name == name.Trim() && name.IndexOfAny(new[] { '\r', '\n', '\t', '/', '\\', '.' }) < 0 &&
                            !before.Any(row => String.Equals(row.Name, name, StringComparison.OrdinalIgnoreCase)),
                            "A new Stu picture needs a valid unique native name.");
                        if (action == PictureImportAction) {
                            PictureKeys(spec, "name", "expected_count", "source_file", "source_sha256");
                            input = PictureSource(spec);
                            expected = input.Bytes;
                        } else {
                            PictureKeys(spec, "name", "expected_count", "source_name", "source_content_hash");
                            source = SelectedPicture(before, NativeEngineeringDeliveryLayout.Value(spec, "source_name"),
                                NativeEngineeringDeliveryLayout.Value(spec, "source_content_hash"));
                            expected = ReadSavedPicture(source);
                        }
                    }
                    int index = replace == null ? before.Count : replace.Index;
                    var changed = UpdatePicture(manager, service, before, replace, source, name, input, result);
                    var after = SavePictures(manager, service, changed, modified, result);
                    byte[] savedIndex = ReadPictureIndex(after, false);
                    Require(replace == null || originalIndex.SequenceEqual(savedIndex), "Picture replacement changed the saved Stu library index.");
                    Require(ReadSavedPicture(after[index]).SequenceEqual(expected), "The saved Stu picture bytes differ from the requested source.");
                    result["record"] = after[index].Value();
                    result["picture_count"] = after.Count;
                    result["native_object_identity_preserved"] = replace != null;
                    result["native_catalog_preserved"] = true;
                    result["native_archive_readback_verified"] = true;
                    result["file_sha256"] = StuPictureHex(expected);
                    result["input_header_normalized"] = input != null && input.Normalized;
                    result["operation_phase"] = "complete";
                    result["status"] = "applied_and_saved";
                } catch (Exception error) {
                    if (!(error is InvalidOperationException || error is IOException || error is UnauthorizedAccessException ||
                        error is XmlException || error is DecoderFallbackException || error is OverflowException)) throw;
                    result["ok"] = false;
                    bool attempted = writing && Object.Equals(result["write_attempted"], true);
                    result["native_result_may_be_partial"] = attempted;
                    result["status"] = attempted ? "native_partial_state" : writing ? "native_preflight_rejected" : "native_read_rejected";
                    result["error"] = error.Message;
                }
            }

            private static void PictureKeys(Dictionary<string, object> spec, params string[] keys) {
                Require(spec.Count == keys.Length && keys.All(spec.ContainsKey), "The Stu picture specification has missing or unknown fields.");
            }

            private static int PictureOption(Dictionary<string, object> spec, string key, int fallback, int minimum, int maximum) {
                object value;
                int result = spec.TryGetValue(key, out value) ? StuNativeProfile.Number(value) : fallback;
                Require(result >= minimum && result <= maximum, "Invalid Stu picture option: " + key);
                return result;
            }

            private byte[] ReadPictureIndex(List<PictureRecord> records, bool allowMissing) {
                byte[] archive = ReadNamedArchive("MCGS_PICTURE_LIST", allowMissing, StuPictureImportLimit);
                if (archive == null) return null;
                using (var reader = new BinaryReader(new MemoryStream(archive, false))) {
                    Require(reader.ReadInt32() == records.Count, "The saved Stu picture count differs from the native catalog.");
                    foreach (var row in records)
                        Require(ReadRecipeString(reader) == row.Name, "The saved Stu picture index differs from the native name order.");
                    reader.ReadInt32();
                    Require(reader.BaseStream.Position == reader.BaseStream.Length, "The saved Stu picture index has unknown trailing fields.");
                }
                return archive;
            }

            private byte[] ReadSavedPicture(PictureRecord selected) {
                string key = "MCGS_PICTURE_DATA_" + selected.Index.ToString(CultureInfo.InvariantCulture);
                byte[] archive = ReadNamedArchive(key, maximumLength: StuPictureImportLimit);
                using (var reader = new BinaryReader(new MemoryStream(archive, false))) {
                    Require(ReadRecipeString(reader) == selected.Name && ReadRecipeString(reader) == selected.Hash,
                        "The saved Stu picture name or content hash differs from the native object.");
                    int kind = reader.ReadInt32();
                    Require(selected.Kind == StuPictureBmp ? kind == 0 || kind == 16 : kind == 2,
                        "The saved Stu picture encoding differs from the native format.");
                    int width = reader.ReadInt32(), height = reader.ReadInt32(), length = reader.ReadInt32();
                    StuPictureCheckDimensions(width, height);
                    Require(length > 0 && reader.BaseStream.Length - reader.BaseStream.Position == length &&
                        (selected.Kind == StuPictureBmp || selected.CacheLength == length), "The saved Stu picture byte extent is invalid.");
                    byte[] native = ReadNativePicture(IntPtr.Add(selected.Object, Abi.Offset("picture_image")), selected.Kind, width, height);
                    Require(native.SequenceEqual(reader.ReadBytes(length)), "The original Stu image bytes differ from the saved named archive.");
                    return StuPictureExternalBytes(selected.Kind, native);
                }
            }

            private StuPictureFile PictureSource(Dictionary<string, object> spec) {
                string path = PicturePath(NativeEngineeringDeliveryLayout.Value(spec, "source_file"), false);
                return StuPictureReadFile(path, NativeEngineeringDeliveryLayout.Value(spec, "source_sha256"));
            }

            private string PicturePath(string input, bool destination) {
                string path = NativeEngineeringDeliveryLayout.Absolute(input);
                Require(path.Length > 3 && path[1] == ':' && path.IndexOf(':', 2) < 0,
                    "Use a regular local filesystem path for the Stu picture.");
                string directory = Path.GetDirectoryName(path);
                for (var parent = new DirectoryInfo(directory); parent != null; parent = parent.Parent)
                    Require(parent.Exists && (parent.Attributes & FileAttributes.ReparsePoint) == 0,
                        "The Stu picture path includes a missing or redirected directory.");
                if (destination) Require(NativeEngineeringDeliveryLayout.Same(directory, Path.GetDirectoryName(context.Project)) &&
                    !File.Exists(path) && !Directory.Exists(path), "Export the Stu picture to a new file beside the current project.");
                else {
                    var info = new FileInfo(path);
                    Require(info.Exists && (info.Attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) == 0,
                        "The Stu image source must be a regular file.");
                }
                return path;
            }

            private static void WritePictureExport(string path, int kind, byte[] data) {
                Require(StuPictureKindFromPath(path) == kind, "The Stu export extension differs from the original image format.");
                string temporary = Path.Combine(Path.GetDirectoryName(path), ".stu-picture-" + Guid.NewGuid().ToString("N") + ".tmp");
                bool owned = false;
                try {
                    using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                        owned = true;
                        stream.Write(data, 0, data.Length);
                        stream.Flush(true);
                    }
                    Require(File.ReadAllBytes(temporary).SequenceEqual(data), "The new Stu export file failed byte readback.");
                    File.Move(temporary, path);
                    owned = false;
                } finally {
                    if (owned) File.Delete(temporary);
                }
            }
        }
    }
}

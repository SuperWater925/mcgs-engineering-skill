using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PictureFind(IntPtr manager, IntPtr name);
            [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
            private delegate IntPtr PictureAllocate(int size);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PictureConstruct(IntPtr self);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PictureDelete(IntPtr self, int release);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void PictureAssign(IntPtr self, IntPtr source);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool PictureAdoptOrName(IntPtr self, IntPtr value);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void PictureRefreshHash(IntPtr service, IntPtr name, int recompute);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PictureBorrowFile(IntPtr file, IntPtr bytes, uint length, uint growth);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr PictureOwnedFile(IntPtr file, uint growth);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int PictureTransferFile(IntPtr image, IntPtr file);

            private sealed class PictureRecord {
                internal IntPtr Object;
                internal int Index, Kind, CacheLength;
                internal string Name, Hash;
                internal bool ReferenceOnly;

                internal Dictionary<string, object> Value() {
                    return new Dictionary<string, object> {
                        {"index", Index}, {"name", Name}, {"content_hash", Hash}, {"image_kind", Kind},
                        {"cached_bytes", CacheLength}, {"file_format", StuPictureFormatName(Kind)}, {"reference_only", ReferenceOnly}
                    };
                }
            }

            private IntPtr PictureManager() {
                context.RequireProject();
                Abi.CheckTable(context.Ptr(context.Root, "root_window_model"), "root_window_model");
                IntPtr manager = Abi.Bind<GetModuleObject>("get_module_object")(11);
                Abi.CheckTable(manager, "picture_manager");
                Abi.CheckTable(IntPtr.Add(manager, Abi.Offset("picture_service_offset")), "picture_service");
                Require(StuNativeProfile.ReadByte(manager, Abi.Offset("picture_loaded")) == 1, "The original Stu picture library is unavailable.");
                return manager;
            }

            private byte PictureDirty(IntPtr manager) {
                byte dirty = StuNativeProfile.ReadByte(manager, Abi.Offset("picture_dirty"));
                Require(dirty <= 1, "The original Stu picture dirty flag is invalid.");
                return dirty;
            }

            private List<PictureRecord> ReadPictures(IntPtr manager) {
                Abi.CheckSlot(manager, "picture_manager", 16, "picture_find_by_name");
                var find = Abi.Bind<PictureFind>("picture_find_by_name");
                IntPtr first = context.Ptr(manager, "picture_vector_begin"), end = context.Ptr(manager, "picture_vector_end");
                IntPtr capacity = context.Ptr(manager, "picture_vector_capacity");
                long used = (long)(uint)end.ToInt32() - (uint)first.ToInt32();
                long space = (long)(uint)capacity.ToInt32() - (uint)first.ToInt32();
                Require(used >= 0 && space >= used && space <= sizeof(int) * MaxCatalogEntries &&
                    used % sizeof(int) == 0 && space % sizeof(int) == 0 && used / sizeof(int) == context.Word(manager, "picture_index_count") &&
                    (used == 0 || StuNativeProfile.Readable(first, (int)used, false)), "The original Stu picture index and name vector differ.");
                var names = new HashSet<string>(StringComparer.Ordinal);
                var pointers = new HashSet<IntPtr>();
                var rows = new List<PictureRecord>((int)(used / sizeof(int)));
                for (int offset = 0; offset < used; offset += sizeof(int)) {
                    string name = StuNativeProfile.Text(first, offset);
                    Require(!String.IsNullOrEmpty(name) && names.Add(name), "The original Stu picture list repeats a name.");
                    IntPtr picture = find(manager, IntPtr.Add(first, offset));
                    Abi.CheckTable(picture, "picture_object");
                    IntPtr image = IntPtr.Add(picture, Abi.Offset("picture_image"));
                    CheckPictureBitmap(image);
                    Require(pointers.Add(picture) && context.Text(picture, "picture_name") == name, "The original Stu picture lookup differs from its name index.");
                    int length;
                    RecipeArray(IntPtr.Add(image, Abi.Offset("picture_image_cache")), 1, out length);
                    rows.Add(new PictureRecord {
                        Object = picture, Index = rows.Count, Name = name, Hash = context.Text(picture, "picture_hash"),
                        Kind = context.Word(image, "picture_image_kind"), CacheLength = length,
                        ReferenceOnly = StuNativeProfile.ReadByte(image, Abi.Offset("picture_image_reference")) == 1
                    });
                }
                Require(context.Ptr(manager, "picture_vector_begin") == first && context.Ptr(manager, "picture_vector_end") == end &&
                    context.Ptr(manager, "picture_vector_capacity") == capacity && context.Word(manager, "picture_index_count") == rows.Count,
                    "The original Stu picture index changed while reading it.");
                return rows;
            }

            private void CheckPictureBitmap(IntPtr image) {
                Abi.CheckTable(image, "picture_bitmap");
                Abi.CheckTable(IntPtr.Add(image, Abi.Offset("picture_image_interface")), "picture_bitmap_interface");
                Require(StuNativeProfile.ReadByte(image, Abi.Offset("picture_image_reference")) <= 1, "The native Stu image ownership flag is invalid.");
            }

            private static PictureRecord SelectedPicture(List<PictureRecord> records, string name, string hash) {
                var record = records.Find(row => row.Name == name);
                Require(record != null && record.Hash == hash && !record.ReferenceOnly && StuPictureFormatName(record.Kind) != "unknown",
                    "Select one supported embedded Stu picture with its exact current name and native content hash.");
                return record;
            }

            private byte[] ReadNativePicture(IntPtr image, int kind, int width, int height) {
                CheckPictureBitmap(image);
                Require(StuNativeProfile.ReadByte(image, Abi.Offset("picture_image_reference")) == 0 &&
                    context.Word(image, "picture_image_kind") == kind && context.Word(image, "picture_image_width") == width &&
                    context.Word(image, "picture_image_height") == height, "The native Stu image format, ownership or dimensions differ.");
                if (kind == StuPictureBmp) return WriteNativeBitmap(image);
                int length;
                IntPtr data = RecipeArray(IntPtr.Add(image, Abi.Offset("picture_image_cache")), 1, out length);
                return CopyPictureMemory(data, length, 14);
            }

            private byte[] WriteNativeBitmap(IntPtr source) {
                IntPtr file = IntPtr.Zero, detached = IntPtr.Zero;
                bool fileReady = false, imageReady = false;
                var destroyFile = Abi.BindImport<NativeVoid>("page_mem_file_dtor");
                var destroyImage = Abi.Bind<NativeVoid>("picture_bitmap_destroy");
                try {
                    file = Marshal.AllocHGlobal(Abi.Offset("picture_mem_file_size"));
                    detached = Marshal.AllocHGlobal(Abi.Offset("picture_bitmap_size"));
                    fileReady = Abi.BindImport<PictureOwnedFile>("page_mem_file_ctor")(file, 1024) == file;
                    imageReady = Abi.Bind<PictureConstruct>("picture_bitmap_layout")(detached) == detached;
                    Require(fileReady && imageReady, "The original Stu bitmap export objects did not construct.");
                    CheckPictureBitmap(detached);
                    Abi.CheckSlot(detached, "picture_bitmap", 6, "picture_bitmap_assign");
                    Abi.CheckSlot(detached, "picture_bitmap", 14, "picture_bitmap_write");
                    Abi.Bind<PictureAssign>("picture_bitmap_assign")(detached, source);
                    Require(Abi.Bind<PictureTransferFile>("picture_bitmap_write")(detached, file) == 1, "The original Stu bitmap encoder refused the image.");
                    byte[] bytes = CopyPictureMemory(context.Ptr(file, "picture_mem_file_data"), context.Word(file, "picture_mem_file_length"), 54);
                    int length = BitConverter.ToInt32(bytes, 2);
                    Require(bytes[0] == 'B' && bytes[1] == 'M' && length >= 54 &&
                        (length == bytes.Length || length == bytes.Length - 8 && BitConverter.ToInt32(bytes, length) == 1),
                        "The original Stu bitmap file or optional suffix differs.");
                    return bytes.Take(length).ToArray();
                } finally {
                    if (imageReady) destroyImage(detached);
                    if (fileReady) destroyFile(file);
                    if (detached != IntPtr.Zero) Marshal.FreeHGlobal(detached);
                    if (file != IntPtr.Zero) Marshal.FreeHGlobal(file);
                }
            }

            private static byte[] CopyPictureMemory(IntPtr data, int length, int minimum) {
                Require(length >= minimum && length <= StuPictureImportLimit && StuNativeProfile.Readable(data, length, false),
                    "The original Stu image byte extent is invalid.");
                var bytes = new byte[length];
                Marshal.Copy(data, bytes, 0, length);
                return bytes;
            }

            private List<PictureRecord> UpdatePicture(IntPtr manager, IntPtr service, List<PictureRecord> before,
                PictureRecord replace, PictureRecord source, string name, StuPictureFile input, Dictionary<string, object> result) {
                var build = Abi.Bind<PictureConstruct>("picture_bitmap_layout");
                var destroy = Abi.Bind<NativeVoid>("picture_bitmap_destroy");
                var assign = Abi.Bind<PictureAssign>("picture_assign_bitmap");
                var setName = Abi.Bind<PictureAdoptOrName>("picture_set_name");
                IntPtr detached = Marshal.AllocHGlobal(Abi.Offset("picture_bitmap_size"));
                IntPtr picture = IntPtr.Zero;
                bool imageReady = false, pictureReady = false, adoptEntered = false;
                try {
                    imageReady = build(detached) == detached;
                    Require(imageReady, "The original Stu detached image did not construct.");
                    CheckPictureBitmap(detached);
                    if (source == null) LoadNativePicture(detached, input);
                    else {
                        Abi.CheckSlot(detached, "picture_bitmap", 6, "picture_bitmap_assign");
                        Abi.Bind<PictureAssign>("picture_bitmap_assign")(detached, IntPtr.Add(source.Object, Abi.Offset("picture_image")));
                    }
                    Require(StuNativeProfile.ReadByte(detached, Abi.Offset("picture_image_reference")) == 0, "The detached Stu picture has no embedded data.");
                    RequireSamePictures(before, ReadPictures(manager));
                    using (var label = new AuthoringPageString(Abi, name)) {
                        if (replace == null) {
                            picture = Abi.BindImport<PictureAllocate>("picture_allocate")(Abi.Offset("picture_object_size"));
                            Require(picture != IntPtr.Zero, "The original Stu picture allocation failed.");
                            pictureReady = Abi.Bind<PictureConstruct>("picture_object_layout")(picture) == picture;
                            Require(pictureReady, "The original Stu picture did not construct.");
                            Abi.CheckSlot(picture, "picture_object", 0, "picture_destroy_unadopted");
                            Abi.CheckSlot(picture, "picture_object", 10, "picture_set_name");
                            Require(setName(picture, label.Storage), "The original Stu new picture did not retain its name.");
                            assign(picture, detached);
                            Abi.CheckSlot(service, "picture_service", 4, "picture_manager_append");
                            context.RequireProject();
                            result["operation_phase"] = "native_picture_append";
                            result["read_only"] = false;
                            result["write_attempted"] = true;
                            adoptEntered = true;
                            Require(Abi.Bind<PictureAdoptOrName>("picture_manager_append")(service, picture), "The original Stu library refused the new object.");
                        } else {
                            picture = replace.Object;
                            Abi.CheckSlot(picture, "picture_object", 10, "picture_set_name");
                            Abi.CheckSlot(service, "picture_service", 13, "picture_manager_refresh_hash");
                            context.RequireProject();
                            result["operation_phase"] = "native_picture_replace";
                            result["read_only"] = false;
                            result["write_attempted"] = true;
                            assign(picture, detached);
                            Require(setName(picture, label.Storage), "The original Stu replacement did not retain its name.");
                            Abi.Bind<PictureRefreshHash>("picture_manager_refresh_hash")(service, label.Storage, 0);
                            Abi.Bind<NativeVoid>("picture_manager_dirty")(service);
                        }
                    }
                    Require(PictureDirty(manager) == 1, "The original Stu picture library did not enter the modified state.");
                    var current = ReadPictures(manager);
                    int index = replace == null ? before.Count : replace.Index;
                    Require(current.Count == before.Count + (replace == null ? 1 : 0), "The original Stu picture count differs after the write.");
                    var changed = current[index];
                    Require(changed.Object == picture && changed.Name == name && !String.IsNullOrEmpty(changed.Hash) && !changed.ReferenceOnly &&
                        changed.Kind == (input == null ? source.Kind : input.Kind), "The target native Stu picture differs after the write.");
                    if (source != null) Require(changed.Hash == source.Hash && changed.CacheLength == source.CacheLength,
                        "The original Stu picture copy differs from the embedded source.");
                    if (input != null) Require(ReadNativePicture(IntPtr.Add(changed.Object, Abi.Offset("picture_image")), input.Kind,
                        input.Width, input.Height).SequenceEqual(input.NativeBytes), "The original Stu target image differs before saving.");
                    RequireSamePictures(before.Where(row => row.Index != index), current.Where(row => row.Index != index));
                    return current;
                } finally {
                    if (pictureReady && !adoptEntered) Abi.Bind<PictureDelete>("picture_destroy_unadopted")(picture, 1);
                    if (imageReady) destroy(detached);
                    Marshal.FreeHGlobal(detached);
                }
            }

            private void LoadNativePicture(IntPtr detached, StuPictureFile input) {
                var enter = Abi.Bind<NativeVoid>("picture_import_begin");
                var leave = Abi.Bind<NativeVoid>("picture_import_end");
                var destroyFile = Abi.BindImport<NativeVoid>("page_mem_file_dtor");
                IntPtr file = IntPtr.Zero, buffer = IntPtr.Zero, scope = IntPtr.Zero;
                bool active = false, ready = false;
                Require(Abi.GlobalWord("picture_import_active") == 0, "The original Stu image loader is already busy.");
                try {
                    file = Marshal.AllocHGlobal(Abi.Offset("picture_mem_file_size"));
                    scope = Marshal.AllocHGlobal(Abi.Offset("picture_import_scope_size"));
                    buffer = Marshal.AllocHGlobal(input.NativeBytes.Length);
                    Marshal.WriteInt64(scope, 0);
                    Marshal.Copy(input.NativeBytes, 0, buffer, input.NativeBytes.Length);
                    enter(scope);
                    active = true;
                    Require(Abi.GlobalWord("picture_import_active") == 1 && StuNativeProfile.Word(scope, 0) == 0 &&
                        StuNativeProfile.ReadByte(scope, 4) == 0, "The original Stu image loader did not enter detached import scope.");
                    ready = Abi.BindImport<PictureBorrowFile>("picture_borrow_file")(file, buffer, (uint)input.NativeBytes.Length, 0) == file;
                    Require(ready && context.Word(file, "picture_mem_file_growth") == 0,
                        "The original Stu image input buffer was not borrowed correctly.");
                    Require(Abi.Bind<PictureTransferFile>("picture_bitmap_load")(detached, file) == 1, "The original Stu decoder refused the file.");
                } finally {
                    if (active) leave(scope);
                    if (ready) destroyFile(file);
                    if (file != IntPtr.Zero) Marshal.FreeHGlobal(file);
                    if (buffer != IntPtr.Zero) Marshal.FreeHGlobal(buffer);
                    if (scope != IntPtr.Zero) Marshal.FreeHGlobal(scope);
                }
                Require(Abi.GlobalWord("picture_import_active") == 0 &&
                    ReadNativePicture(detached, input.Kind, input.Width, input.Height).SequenceEqual(input.NativeBytes),
                    "Detached Stu decoding did not preserve the expected image and scope.");
            }

            private List<PictureRecord> SavePictures(IntPtr manager, IntPtr service, List<PictureRecord> expected,
                LifecycleIsModified modified, Dictionary<string, object> result) {
                context.RequireProject();
                result["operation_phase"] = "save_picture_module";
                Abi.Bind<SetNativeFlag>("set_root_modified")(context.Root, 1);
                Require(modified(context.Root) != 0 && PictureDirty(manager) == 1, "The original Stu project or picture dirty state differs.");
                Require(Abi.Bind<SaveDataModule>("picture_manager_save")(service) && PictureDirty(manager) == 0,
                    "The original Stu picture library did not save.");
                result["native_module_saved"] = true;
                result["operation_phase"] = "save_root";
                IntPtr filename = Marshal.StringToHGlobalUni(context.Project);
                try {
                    Require(Abi.Bind<SaveRoot>("save_root")(context.Root, filename) == 1 && modified(context.Root) == 0 &&
                        context.Word(context.Root, "document_dirty") == 0, "The original Stu root did not save the picture library.");
                } finally { Marshal.FreeHGlobal(filename); }
                result["root_saved"] = true;
                Require(PictureManager() == manager && PictureDirty(manager) == 0, "The original Stu picture manager changed during save.");
                var resultCatalog = ReadPictures(manager);
                RequireSamePictures(expected, resultCatalog);
                return resultCatalog;
            }

            private static void RequireSamePictures(IEnumerable<PictureRecord> before, IEnumerable<PictureRecord> after) {
                var original = before.ToList();
                var current = after.ToList();
                Require(original.Count == current.Count, "The count of preserved Stu pictures changed.");
                for (int i = 0; i < original.Count; i++) {
                    var left = original[i];
                    var right = current[i];
                    Require(left.Index == right.Index && left.Object == right.Object && left.Name == right.Name && left.Hash == right.Hash &&
                        left.Kind == right.Kind && left.CacheLength == right.CacheLength && left.ReferenceOnly == right.ReferenceOnly,
                        "An unrelated original Stu picture changed: " + left.Name);
                }
            }
        }
    }
}

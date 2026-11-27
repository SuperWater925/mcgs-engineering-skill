using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string LanguageCatalogAction = "language-catalog", LanguageTextEditAction = "language-text-edit",
            LanguageAddAction = "language-add";

        private sealed partial class StuDocument {
            private const int FirstProjectTextId = 10000;

            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int NextLanguageTextId(IntPtr service, byte saved);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate byte SetLanguageText(IntPtr service, int textId, int languageId, IntPtr value, byte saved);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate byte AppendLanguage(IntPtr service, int languageId);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate byte IsBuiltInLanguage(IntPtr service, IntPtr name);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void SetLanguageDirty(IntPtr service, byte value);

            private sealed class LanguageState {
                internal int[] Configured, Selectors;
                internal IntPtr FontManager;
                internal SortedDictionary<int, object[]> Definitions;
                internal SortedDictionary<int, SortedDictionary<int, string>> Text;
            }

            internal void ApplyLanguage(string action, IntPtr mainWindow, object rawOptions, Dictionary<string, object> result) {
                bool catalog = action == LanguageCatalogAction;
                if (!catalog) {
                    result["write_attempted"] = result["native_result_may_be_partial"] = false;
                    result["language_module_saved"] = result["root_save_verified"] = false;
                    result["automatic_retry"] = false;
                    result["operation_phase"] = "validate_preimage";
                }
                try {
                    Abi.RequireFeature(LanguageCatalogAction);
                    if (!catalog) Abi.RequireFeature(action);
                    var options = catalog && rawOptions == null ? new Dictionary<string, object>() : StuNativeProfile.Map(rawOptions);
                    var service = LanguageService();
                    var current = ReadLanguage(service);
                    var next = Abi.Bind<NextLanguageTextId>("language_next_project_text_id");
                    Abi.CheckSlot(service, "language_service", 30, "language_next_project_text_id");
                    if (catalog) {
                        ReportLanguageCatalog(service, current, next(service, 0), options, result);
                        return;
                    }

                    PrepareLanguageSave(service, mainWindow, current, result);
                    if (action == LanguageTextEditAction) EditLanguageText(service, current, next(service, 0), options, result);
                    else AddBuiltInLanguage(service, current, options, result);

                    SaveLanguage(service, result);
                    Require(LanguageService() == service && LanguageDirty(service) == 0,
                        "The original Stu language service or its saved state changed.");
                    VerifyLanguageState(current, ReadLanguage(service));
                    Require(SameLanguageText(current.Text, ReadLanguageTexts(service, "language_working_texts")),
                        "The original Stu language workspace differs from the saved translations.");
                    result["configured_language_ids"] = current.Configured;
                    result["current_language_id"] = current.Selectors[1];
                    result["preview_language_id"] = current.Selectors[2];
                    result["next_project_text_id"] = next(service, 0);
                    result["unselected_translations_verified"] = true;
                    result["language_selectors_preserved"] = true;
                    result["operation_phase"] = "complete";
                    result["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    if (!catalog) FailPageWrite(result, error);
                    else {
                        result["ok"] = false;
                        result["status"] = "native_read_rejected";
                        result["error"] = error.Message;
                    }
                }
            }

            private IntPtr LanguageService() {
                context.RequireProject();
                IntPtr service = context.Ptr(context.Root, "root_language_service");
                Abi.CheckTable(service, "language_service");
                return service;
            }

            private byte LanguageDirty(IntPtr service) {
                byte dirty = StuNativeProfile.ReadByte(service, Abi.Offset("language_dirty"));
                Require(dirty <= 1, "The original Stu language dirty flag is invalid.");
                return dirty;
            }

            private LanguageState ReadLanguage(IntPtr service) {
                int[] configured = LanguageVector(IntPtr.Add(service, Abi.Offset("language_configured_ids")), 4)
                    .Select(p => StuNativeProfile.Word(p, 0)).ToArray();
                var definitions = new SortedDictionary<int, object[]>();
                foreach (IntPtr node in LanguageNodes(IntPtr.Add(service, Abi.Offset("language_definitions")))) {
                    int id = context.Word(node, "language_node_key");
                    int primary = Abi.Offset("language_definition_primary_font"), alternate = Abi.Offset("language_definition_alternate_font");
                    definitions.Add(id, new object[] { context.Text(node, "language_definition_name"),
                        StuNativeProfile.Text(node, primary), StuNativeProfile.Word(node, primary + 4), StuNativeProfile.Word(node, primary + 8),
                        StuNativeProfile.Text(node, alternate), StuNativeProfile.Word(node, alternate + 4), StuNativeProfile.Word(node, alternate + 8) });
                }
                Require(configured.Length == context.Word(service, "language_configured_count") &&
                    configured.Distinct().Count() == configured.Length && configured.All(definitions.ContainsKey),
                    "The original Stu configured language order or definitions are inconsistent.");
                var font = context.Ptr(service, "language_font_manager");
                Require(StuNativeProfile.Readable(font, 16, false), "The original Stu language font manager is unavailable.");
                return new LanguageState {
                    Configured = configured,
                    Selectors = new[] { context.Word(service, "language_initial"), context.Word(service, "language_current"),
                        context.Word(service, "language_preview"), context.Word(service, "language_mode") },
                    FontManager = font,
                    Definitions = definitions,
                    Text = ReadLanguageTexts(service, "language_saved_texts")
                };
            }

            private void PrepareLanguageSave(IntPtr service, IntPtr mainWindow, LanguageState current, Dictionary<string, object> result) {
                Abi.CheckSlot(service, "language_service", 35, "save_language_module");
                Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                Abi.CheckSlot(context.Root, "root", 34, "save_root");
                var modified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                IntPtr frame = Abi.Bind<GetApplication>("get_main_frame")();
                Abi.CheckTable(frame, "frame");
                Require(context.Ptr(frame, "frame_hwnd") == mainWindow && modified(context.Root) == 0 &&
                    context.Word(context.Root, "document_dirty") == 0 && LanguageDirty(service) == 0,
                    "The original Stu project or language workspace has unsaved changes.");
                result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, modified, false);
                Require(SameLanguageText(current.Text, ReadLanguageTexts(service, "language_working_texts")),
                    "The original Stu language workspace has different unsaved translations.");
            }

            private void EditLanguageText(IntPtr service, LanguageState current, int next, Dictionary<string, object> spec,
                Dictionary<string, object> result) {
                Require(spec.Count == 4 && spec.ContainsKey("text_id") && spec.ContainsKey("language_id") &&
                    spec.ContainsKey("before") && spec.ContainsKey("after"), "A Stu translation edit requires a text ID, language ID, old and new text.");
                int id = StuNativeProfile.Number(spec["text_id"]), language = StuNativeProfile.Number(spec["language_id"]);
                string before = spec["before"] as string, after = spec["after"] as string;
                Require(id >= FirstProjectTextId && current.Configured.Contains(language) &&
                    (spec["before"] == null || ValidLanguageText(before)) && ValidLanguageText(after) && before != after,
                    "Select a project text and configured language with an exact before value and different Unicode translation.");
                SortedDictionary<int, string> translations;
                if (!current.Text.TryGetValue(id, out translations)) {
                    Require(before == null && id == next, "An unused Stu project text ID must be the current next project text ID.");
                    translations = new SortedDictionary<int, string>();
                    current.Text.Add(id, translations);
                }
                string actual;
                translations.TryGetValue(language, out actual);
                Require(actual == before, "The original Stu translation no longer matches its preimage.");
                translations[language] = after;

                Abi.CheckSlot(service, "language_service", 2, "language_set_translation");
                Abi.CheckSlot(service, "language_service", 41, "language_commit_translations");
                using (var text = new AuthoringPageString(Abi, after)) {
                    context.RequireProject();
                    result["operation_phase"] = "native_language_translation";
                    result["read_only"] = false;
                    result["write_attempted"] = true;
                    Require(Abi.Bind<SetLanguageText>("language_set_translation")(service, id, language, text.Storage, 0) != 0 &&
                        SameLanguageText(current.Text, ReadLanguageTexts(service, "language_working_texts")),
                        "The original Stu translation setter did not produce exactly the expected language workspace.");
                }
                result["operation_phase"] = "native_language_commit";
                Abi.Bind<NativeVoid>("language_commit_translations")(service);
                Require(LanguageDirty(service) == 1, "The original Stu language service did not mark the translations for saving.");
                VerifyLanguageState(current, ReadLanguage(service));
                result["text_id"] = id;
                result["language_id"] = language;
                result["text"] = after;
            }

            private void AddBuiltInLanguage(IntPtr service, LanguageState current, Dictionary<string, object> spec,
                Dictionary<string, object> result) {
                Require(spec.Count == 3 && spec.ContainsKey("language_id") && spec.ContainsKey("language_name") &&
                    spec.ContainsKey("expected_configured_language_ids"), "Stu language configuration requires the built-in ID, name and current configured order.");
                int id = StuNativeProfile.Number(spec["language_id"]);
                string name = spec["language_name"] as string;
                var configured = spec["expected_configured_language_ids"] as IList;
                object[] definition;
                Require(id >= 0 && ValidLanguageText(name) && !String.IsNullOrWhiteSpace(name) &&
                    current.Definitions.TryGetValue(id, out definition) && Object.Equals(definition[0], name) &&
                    configured != null && current.Configured.Length > 0 && !current.Configured.Contains(id) &&
                    current.Configured.SequenceEqual(configured.Cast<object>().Select(StuNativeProfile.Number)),
                    "The Stu built-in language or configured-language preimage differs.");
                Abi.CheckSlot(service, "language_service", 6, "language_append_builtin");
                Abi.CheckSlot(service, "language_service", 18, "language_check_builtin_name");
                Abi.CheckSlot(service, "language_service", 44, "language_refresh_fonts");
                Abi.CheckSlot(service, "language_service", 51, "set_language_module_dirty");
                using (var originalName = new AuthoringPageString(Abi, name))
                    Require(Abi.Bind<IsBuiltInLanguage>("language_check_builtin_name")(service, originalName.Storage) != 0,
                        "The original Stu language service does not recognize the selected built-in name.");
                current.Configured = current.Configured.Concat(new[] { id }).ToArray();
                context.RequireProject();
                result["operation_phase"] = "native_language_configuration";
                result["read_only"] = false;
                result["write_attempted"] = true;
                Require(Abi.Bind<AppendLanguage>("language_append_builtin")(service, id) != 0,
                    "The original Stu language service did not append the selected built-in language.");
                Abi.Bind<NativeVoid>("language_refresh_fonts")(service);
                Abi.Bind<SetLanguageDirty>("set_language_module_dirty")(service, 1);
                Require(LanguageDirty(service) == 1, "The original Stu language service did not mark the configuration for saving.");
                VerifyLanguageState(current, ReadLanguage(service));
                result["language_id"] = id;
                result["language_name"] = name;
                result["native_font_mapping_refreshed"] = true;
            }

            private void SaveLanguage(IntPtr service, Dictionary<string, object> result) {
                result["operation_phase"] = "save_language_module";
                Abi.Bind<NativeVoid>("save_language_module")(service);
                Require(LanguageDirty(service) == 0, "The original Stu language module did not save.");
                result["language_module_saved"] = true;
                result["operation_phase"] = "save_root";
                context.RequireProject();
                IntPtr file = Marshal.StringToHGlobalUni(context.Project);
                try {
                    Abi.Bind<SetNativeFlag>("set_root_modified")(context.Root, 1);
                    Require(Abi.Bind<SaveRoot>("save_root")(context.Root, file) == 1 && context.Word(context.Root, "document_dirty") == 0,
                        "The original Stu project did not save after the language edit.");
                } finally { Marshal.FreeHGlobal(file); }
                result["root_save_verified"] = true;
            }

            private void ReportLanguageCatalog(IntPtr service, LanguageState state, int next, Dictionary<string, object> options,
                Dictionary<string, object> result) {
                Require(options.Keys.All(key => key == "offset" || key == "limit" || key == "text_id") &&
                    (!options.ContainsKey("text_id") || options.Count == 1),
                    "Read a Stu translation by its exact text ID or use the project text offset and limit.");
                var texts = state.Text.Where(row => row.Key >= FirstProjectTextId).ToList();
                object filter;
                if (options.TryGetValue("text_id", out filter)) {
                    int id = StuNativeProfile.Number(filter);
                    Require(id >= FirstProjectTextId, "Use an original project text ID to read a Stu translation.");
                    texts = texts.Where(row => row.Key == id).ToList();
                } else {
                    object value;
                    int offset = options.TryGetValue("offset", out value) ? StuNativeProfile.Number(value) : 0;
                    int limit = options.TryGetValue("limit", out value) ? StuNativeProfile.Number(value) : 128;
                    Require(offset >= 0 && offset <= texts.Count && limit > 0 && limit <= 1024,
                        "Stu project text pagination is outside the original catalog.");
                    texts = texts.Skip(offset).Take(limit).ToList();
                }
                result["configured_language_ids"] = state.Configured;
                result["language_definitions"] = state.Definitions.Select(item => new Dictionary<string, object> {
                    {"language_id", item.Key}, {"name", item.Value[0]}, {"font_primary", item.Value[1]}, {"font_alternate", item.Value[4]} }).ToList();
                result["current_language_id"] = state.Selectors[1];
                result["preview_language_id"] = state.Selectors[2];
                result["next_project_text_id"] = next;
                result["project_text_count"] = state.Text.Keys.Count(id => id >= FirstProjectTextId);
                result["language_dirty"] = (int)LanguageDirty(service);
                result["project_texts"] = texts.Select(row => new Dictionary<string, object> {
                    {"text_id", row.Key}, {"translations", row.Value.Select(item => new Dictionary<string, object> {
                        {"language_id", item.Key}, {"text", item.Value} }).ToList()} }).ToList();
            }

            private static bool ValidLanguageText(string value) {
                if (value == null || value.Length > 32768 || value.IndexOf('\0') >= 0) return false;
                try { new UnicodeEncoding(false, false, true).GetByteCount(value); }
                catch (EncoderFallbackException) { return false; }
                return true;
            }

            private static void VerifyLanguageState(LanguageState expected, LanguageState actual) {
                Require(expected.Configured.SequenceEqual(actual.Configured) && expected.Selectors.SequenceEqual(actual.Selectors) &&
                    expected.FontManager == actual.FontManager && expected.Definitions.Keys.SequenceEqual(actual.Definitions.Keys) &&
                    expected.Definitions.All(item => item.Value.SequenceEqual(actual.Definitions[item.Key])) &&
                    SameLanguageText(expected.Text, actual.Text),
                    "The original Stu language state differs from the exact configuration and translation postimage.");
            }

            private static bool SameLanguageText(SortedDictionary<int, SortedDictionary<int, string>> expected,
                SortedDictionary<int, SortedDictionary<int, string>> actual) {
                return expected.Keys.SequenceEqual(actual.Keys) && expected.All(item => item.Value.SequenceEqual(actual[item.Key]));
            }

            private SortedDictionary<int, SortedDictionary<int, string>> ReadLanguageTexts(IntPtr service, string member) {
                var texts = new SortedDictionary<int, SortedDictionary<int, string>>();
                foreach (var node in LanguageNodes(IntPtr.Add(service, Abi.Offset(member)))) {
                    var translations = new SortedDictionary<int, string>();
                    foreach (var entry in LanguageVector(IntPtr.Add(node, Abi.Offset("language_text_translations")), 8)) {
                        int id = StuNativeProfile.Word(entry, 0);
                        Require(!translations.ContainsKey(id), "The original Stu project text repeats a translation language.");
                        translations.Add(id, context.Text(entry, "language_translation_name"));
                    }
                    texts.Add(context.Word(node, "language_node_key"), translations);
                }
                return texts;
            }

            private static IEnumerable<IntPtr> LanguageVector(IntPtr vector, int stride) {
                IntPtr first = StuNativeProfile.Pointer(vector, 0);
                long length = (long)(uint)StuNativeProfile.Pointer(vector, 4).ToInt32() - (uint)first.ToInt32();
                long capacity = (long)(uint)StuNativeProfile.Pointer(vector, 8).ToInt32() - (uint)first.ToInt32();
                Require(length >= 0 && capacity >= length && capacity % stride == 0 && length % stride == 0 &&
                    length / stride <= MaxCatalogEntries && (length == 0 || StuNativeProfile.Readable(first, (int)length, false)),
                    "The original Stu language vector extent is invalid.");
                for (int offset = 0; offset < length; offset += stride) yield return IntPtr.Add(first, offset);
            }

            private List<IntPtr> LanguageNodes(IntPtr tree) {
                IntPtr sentinel = StuNativeProfile.Pointer(tree, 0);
                int count = context.Word(tree, "language_tree_count");
                Require(count >= 0 && count <= MaxCatalogEntries &&
                    StuNativeProfile.ReadByte(sentinel, Abi.Offset("language_node_sentinel")) == 1,
                    "The original Stu language tree extent is invalid.");
                var nodes = new List<IntPtr>(count);
                VisitLanguageNode(context.Ptr(sentinel, "language_node_parent"), sentinel, sentinel, new HashSet<IntPtr>(), nodes, count, 0);
                Require(nodes.Count == count && StuNativeProfile.Pointer(sentinel, 0) == (count == 0 ? sentinel : nodes[0]) &&
                    context.Ptr(sentinel, "language_node_right") == (count == 0 ? sentinel : nodes[count - 1]),
                    "The original Stu language tree endpoints or count differ.");
                for (int i = 1; i < nodes.Count; i++)
                    Require(context.Word(nodes[i - 1], "language_node_key") < context.Word(nodes[i], "language_node_key"),
                        "The original Stu language tree keys are out of order.");
                return nodes;
            }

            private void VisitLanguageNode(IntPtr node, IntPtr parent, IntPtr sentinel, HashSet<IntPtr> seen,
                List<IntPtr> nodes, int count, int depth) {
                if (node == sentinel) return;
                Require(depth < 128 && seen.Count < count && seen.Add(node) && context.Ptr(node, "language_node_parent") == parent &&
                    StuNativeProfile.ReadByte(node, Abi.Offset("language_node_sentinel")) == 0,
                    "The original Stu language tree repeats a node or has an invalid parent.");
                VisitLanguageNode(StuNativeProfile.Pointer(node, 0), node, sentinel, seen, nodes, count, depth + 1);
                nodes.Add(node);
                VisitLanguageNode(context.Ptr(node, "language_node_right"), node, sentinel, seen, nodes, count, depth + 1);
            }
        }
    }
}

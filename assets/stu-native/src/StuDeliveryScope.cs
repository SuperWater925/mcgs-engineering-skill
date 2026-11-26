using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal sealed class NativeEngineeringDeliveryLayout {
        internal const string ExpectedConfigurationSha256 = "runtime:mcgs-portable-engine/v1";
        internal const string PortableEngineContract = "mcgs-portable-engine/v1";
        internal readonly string Sha256, EditorExecutable, ProfileSha256;
        internal readonly byte[] Profile;

        private NativeEngineeringDeliveryLayout(string sha256, string editorExecutable, string profileSha256, byte[] profile) {
            Sha256 = sha256;
            EditorExecutable = editorExecutable;
            ProfileSha256 = profileSha256;
            Profile = profile;
        }

        internal static NativeEngineeringDeliveryLayout Load() {
            string assembly = typeof(NativeEngineeringDeliveryLayout).Assembly.Location;
            Require(!String.IsNullOrEmpty(assembly), "Stu delivery has no local assembly file.");
            string scope = Path.ChangeExtension(assembly, ".scope.json");
            byte[] data = ReadLocal(scope, 32768);
            var map = Parse(data);
            Require(map.Count == 11 && Object.Equals(map["schema"], 1) &&
                Value(map, "portable_engine_contract") == PortableEngineContract, "Stu delivery scope schema differs.");
            string task = DirectoryPath(Value(map, "task_root"));
            string runtime = DirectoryPath(Value(map, "runtime_root"));
            string engineering = DirectoryPath(Value(map, "engineering_root"));
            string install = DirectoryPath(Value(map, "install_root"));
            string editor = Absolute(Value(map, "editor_executable"));
            string transport = Absolute(Value(map, "transport_client_file"));
            string transportSha = Value(map, "transport_client_sha256");
            Require(Within(runtime, task) && !Same(runtime, task) &&
                !Within(runtime, engineering) && !Within(engineering, runtime),
                "Stu delivery payload and task runtime have inconsistent paths.");
            Require(Within(editor, install) &&
                String.Equals(Path.GetFileName(editor), "McgsSetStu.exe", StringComparison.OrdinalIgnoreCase),
                "Stu delivery must select the actual installed editor executable.");
            Require((Within(transport, task) || Within(transport, engineering)) &&
                Regex.IsMatch(transportSha, @"\A[0-9a-f]{64}\z") && HashFile(transport) == transportSha,
                "Stu delivery transport does not match its own scope.");
            string bindingFile = Absolute(Value(map, "portable_binding_file"));
            Require(Within(bindingFile, engineering), "Stu binding escapes the engineering payload.");
            byte[] bindingBytes = ReadLocal(bindingFile, 1048576);
            Require(HashBytes(bindingBytes) == Value(map, "portable_binding_sha256"), "Stu delivery binding SHA differs.");
            var binding = Parse(bindingBytes);
            Require(Value(binding, "schema") == "mcgs-portable-engine-binding/v1" &&
                Value(binding, "engine_contract") == PortableEngineContract && Value(binding, "family") == "stu",
                "Stu delivery binding contract differs.");
            string profileFile = Absolute(Value(binding, "profile_index_file"));
            Require(Within(profileFile, Path.Combine(engineering, "task-evidence")), "Stu role index escapes the task evidence directory.");
            byte[] profile = ReadLocal(profileFile, 1048576);
            string profileSha = HashBytes(profile);
            Require(profileSha == Value(binding, "profile_index_sha256"), "Stu role index SHA differs.");
            return new NativeEngineeringDeliveryLayout(HashBytes(data), editor, profileSha, profile);
        }

        private static Dictionary<string, object> Parse(byte[] data) {
            var map = new JavaScriptSerializer { MaxJsonLength = 1048576 }.Deserialize<Dictionary<string, object>>(
                new UTF8Encoding(false, true).GetString(data).TrimStart('\uFEFF'));
            Require(map != null, "Stu delivery file must contain a JSON object.");
            return map;
        }

        private static byte[] ReadLocal(string file, int maximum) {
            var info = new FileInfo(file);
            Require(info.Exists && (info.Attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) == 0,
                "Stu delivery file is absent or is not local regular data: " + file);
            using (var stream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read)) {
                Require(stream.Length > 0 && stream.Length <= maximum, "Stu delivery file size is out of bounds: " + file);
                var bytes = new byte[(int)stream.Length];
                for (int consumed = 0; consumed < bytes.Length; ) {
                    int count = stream.Read(bytes, consumed, bytes.Length - consumed);
                    if (count == 0) throw new EndOfStreamException(file);
                    consumed += count;
                }
                return bytes;
            }
        }

        internal static string Value(Dictionary<string, object> map, string key) {
            object value;
            Require(map.TryGetValue(key, out value) && value is string && !String.IsNullOrEmpty((string)value) &&
                ((string)value).IndexOf('\0') < 0, "Missing or invalid Stu field: " + key);
            return (string)value;
        }

        internal static string Absolute(string text) {
            Require(!String.IsNullOrEmpty(text) && text.IndexOf('\0') < 0 &&
                Regex.IsMatch(text, @"\A(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|\z))"),
                "Stu requires an absolute Windows path.");
            string path = Path.GetFullPath(text);
            return Same(path, Path.GetPathRoot(path)) ? path : path.TrimEnd('\\', '/');
        }

        internal static bool Same(string a, string b) {
            return String.Equals(a, b, StringComparison.OrdinalIgnoreCase);
        }

        private static bool Within(string candidate, string root) {
            return Same(candidate, root) || candidate.StartsWith(root.TrimEnd('\\', '/') + "\\", StringComparison.OrdinalIgnoreCase);
        }

        private static string DirectoryPath(string text) {
            string path = Absolute(text);
            Require(Directory.Exists(path), "Stu delivery directory is absent: " + path);
            return path;
        }

        internal static string HashFile(string path) {
            using (var sha = SHA256.Create())
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                return Hex(sha.ComputeHash(stream));
        }

        private static string HashBytes(byte[] bytes) {
            using (var sha = SHA256.Create()) return Hex(sha.ComputeHash(bytes));
        }

        private static string Hex(byte[] data) {
            return BitConverter.ToString(data).Replace("-", "").ToLowerInvariant();
        }

        internal static void Require(bool ok, string message) {
            if (!ok) throw new InvalidOperationException(message);
        }
    }
}

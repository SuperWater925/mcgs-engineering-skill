using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal sealed class StuNativeProfile {
        private readonly Dictionary<string, object> capabilities, tables, functions, imports, layout;
        private readonly IntPtr image;
        private readonly int imageSize, preferredBase;
        private readonly Dictionary<string, IntPtr> verifiedFunctions = new Dictionary<string, IntPtr>(StringComparer.Ordinal);

        internal StuNativeProfile(IntPtr image, int imageSize, byte[] profile) {
            this.image = image;
            this.imageSize = imageSize;
            var p = new JavaScriptSerializer { MaxJsonLength = 1048576 }.Deserialize<Dictionary<string, object>>(
                new UTF8Encoding(false, true).GetString(profile).TrimStart('\uFEFF'));
            Require(p != null && Object.Equals(p["schema"], 1) && Object.Equals(p["product"], "stu"),
                "Stu ABI profile schema differs.");
            preferredBase = Number(p["preferred_image_base"]);
            capabilities = Map(p["capabilities"]);
            tables = Map(p["tables"]);
            functions = Map(p["functions"]);
            imports = p.ContainsKey("imports") ? Map(p["imports"]) : new Dictionary<string, object>();
            layout = Map(p["layout"]);
        }

        internal void RequireFeature(string name) {
            object entry;
            Require(capabilities.TryGetValue(name, out entry), "Stu " + name + " has no verified role profile.");
            var feature = Map(entry);
            if (!Object.Equals(feature["state"], "verified"))
                throw new InvalidOperationException("Stu " + name + " is unavailable: " + Convert.ToString(feature.ContainsKey("reason") ? feature["reason"] : feature["state"]));
            foreach (object role in (IEnumerable)feature["functions"]) Function((string)role);
            object imported;
            if (feature.TryGetValue("imports", out imported))
                foreach (object role in (IEnumerable)imported) Import((string)role);
        }

        internal int Offset(string name) {
            return Number(layout[name]);
        }

        internal int GlobalWord(string name) {
            return Word(Address(Offset(name), sizeof(int)), 0);
        }

        internal IntPtr GlobalPointer(string name) {
            return Pointer(Address(Offset(name), IntPtr.Size), 0);
        }

        internal T Bind<T>(string name) where T : class {
            return (T)(object)Marshal.GetDelegateForFunctionPointer(Function(name), typeof(T));
        }

        internal T BindImport<T>(string name) where T : class {
            return (T)(object)Marshal.GetDelegateForFunctionPointer(Import(name), typeof(T));
        }

        internal T BindPageMemorySeek<T>(IntPtr memoryFile) where T : class {
            int ordinal = Offset("page_mem_file_seek_ordinal");
            int slot = Offset("page_mem_file_seek_slot");
            IntPtr module = GetModuleHandleW("mfc110u.dll");
            Require(module != IntPtr.Zero && ordinal > 0 && ordinal <= UInt16.MaxValue && slot >= 0 && slot <= 64,
                "Stu native page memory-file seek has no verified MFC role.");
            IntPtr exported = GetProcAddress(module, new IntPtr(ordinal));
            IntPtr actual = Pointer(Pointer(memoryFile, 0), checked(slot * IntPtr.Size));
            Require(exported != IntPtr.Zero && actual == exported && Readable(actual, 1, true),
                "The original Stu page memory-file seek slot differs from its MFC export.");
            return (T)(object)Marshal.GetDelegateForFunctionPointer(actual, typeof(T));
        }

        internal void CheckRecipeMfcArray(IntPtr array, string role) {
            IntPtr module = GetModuleHandleW("mfc110u.dll");
            Require(module != IntPtr.Zero, "The original Stu MFC provider is not loaded.");
            IntPtr table = Pointer(array, 0);
            IntPtr runtimeClass = GetProcAddress(module, new IntPtr(Offset(role + "_runtime_class_ordinal")));
            IntPtr serialization = GetProcAddress(module, new IntPtr(Offset(role + "_serialize_ordinal")));
            Require(runtimeClass != IntPtr.Zero && serialization != IntPtr.Zero &&
                Pointer(table, 0) == runtimeClass && Pointer(table, 2 * IntPtr.Size) == serialization &&
                Readable(runtimeClass, 1, true) && Readable(serialization, 1, true),
                "The original Stu recipe array does not match its MFC runtime class and serializer.");
        }

        private IntPtr Import(string name) {
            var definition = Map(imports[name]);
            string dll = (string)definition["dll"];
            int ordinal = Number(definition["ordinal"]);
            Require(!String.IsNullOrEmpty(dll) && dll.IndexOfAny(new[] { '\\', '/', ':' }) < 0 &&
                ordinal > 0 && ordinal <= UInt16.MaxValue, "Stu native import role cannot be verified: " + name);
            IntPtr module = GetModuleHandleW(dll);
            IntPtr exported = module == IntPtr.Zero ? IntPtr.Zero : GetProcAddress(module, new IntPtr(ordinal));
            IntPtr actual = Pointer(Address(Number(definition["rva"]), 4), 0);
            Require(actual != IntPtr.Zero && actual == exported && Readable(actual, 1, true),
                "Stu native import differs from its resolved role: " + name);
            return actual;
        }

        private IntPtr Function(string name) {
            IntPtr ready;
            if (verifiedFunctions.TryGetValue(name, out ready)) return ready;
            var definition = Map(functions[name]);
            IntPtr address = Address(Number(definition["rva"]), 1);
            Require(Readable(address, 1, true), "Stu code role is not executable: " + name);
            int witnessCount = 0;
            uint delta = unchecked((uint)image.ToInt32() - (uint)preferredBase);
            foreach (object item in (IEnumerable)definition["guards"]) {
                var guard = Map(item);
                string hex = (string)guard["bytes"];
                Require(hex.Length > 0 && hex.Length % 2 == 0, "Stu function witness is invalid: " + name);
                var expected = new byte[hex.Length / 2];
                for (int i = 0; i < expected.Length; i++)
                    expected[i] = Byte.Parse(hex.Substring(i * 2, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                foreach (object relocation in (IEnumerable)guard["reloc_offsets"]) {
                    int offset = Number(relocation);
                    Require(offset >= 0 && offset + 4 <= expected.Length, "Stu relocation exceeds its witness: " + name);
                    BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(expected, offset) + delta)).CopyTo(expected, offset);
                }
                IntPtr site = Address(Number(guard["rva"]), expected.Length);
                Require(Readable(site, expected.Length, true), "Stu function witness is not executable: " + name);
                for (int i = 0; i < expected.Length; i++)
                    Require(Marshal.ReadByte(site, i) == expected[i], "Stu actual function role differs: " + name);
                witnessCount++;
            }
            Require(witnessCount > 0, "Stu function has no verified witness: " + name);
            verifiedFunctions.Add(name, address);
            return address;
        }

        internal bool IsTable(IntPtr instance, string name) {
            object current;
            if (!tables.TryGetValue(name, out current)) return false;
            var definition = Map(current);
            return Pointer(instance, 0) == Address(Number(definition["rva"]), 4);
        }

        internal IntPtr CheckTable(IntPtr instance, string name) {
            var definition = Map(tables[name]);
            IntPtr table = Pointer(instance, 0);
            IntPtr locator;
            Require(table == Address(Number(definition["rva"]), 4) && TryLocator(table, out locator) &&
                locator == Address(Number(definition["col_rva"]), 20) &&
                Word(locator, 4) == Number(definition["col_offset"]) &&
                RttiName(Pointer(locator, 12)) == (string)definition["rtti"],
                "Stu native object role differs: " + name);
            return table;
        }

        internal void CheckSlot(IntPtr instance, string tableName, int slot, string functionName) {
            IntPtr table = CheckTable(instance, tableName);
            var slots = Map(Map(tables[tableName])["slots"]);
            IntPtr address = Function(functionName);
            Require(address == Address(Number(slots[slot.ToString(CultureInfo.InvariantCulture)]), 1) &&
                Pointer(table, checked(slot * 4)) == address, "Stu virtual role differs: " + functionName);
        }

        // A control iterator may encounter foreign plug-ins. Only an in-image RTTI
        // object with the original nonvirtual drawing base is used for common fields.
        internal string Drawing(IntPtr view, out IntPtr complete) {
            complete = IntPtr.Zero;
            IntPtr locator;
            if (!TryLocator(Pointer(view, 0), out locator)) return "unknown";
            string rtti = RttiName(Pointer(locator, 12));
            if (rtti == null) return "unknown";
            int offset = Offset("control_view_offset");
            if (Word(locator, 4) != offset) return rtti;
            IntPtr hierarchy = Pointer(locator, 16);
            if (!Contains(hierarchy, 16) || Word(hierarchy, 0) != 0) return rtti;
            int count = Word(hierarchy, 8);
            IntPtr entries = Pointer(hierarchy, 12);
            if (count <= 0 || count > 64 || !Contains(entries, count * 4)) return rtti;
            for (int i = 0; i < count; i++) {
                IntPtr entry = Pointer(entries, i * 4);
                if (!Contains(entry, 20)) return rtti;
                if (RttiName(Pointer(entry, 0)) == ".?AVCDrawObj@@" && Word(entry, 8) == 0 &&
                    Word(entry, 12) == -1 && Word(entry, 16) == 0) {
                    complete = IntPtr.Subtract(view, offset);
                    break;
                }
            }
            return rtti;
        }

        private bool TryLocator(IntPtr table, out IntPtr locator) {
            locator = IntPtr.Zero;
            if (!Contains(IntPtr.Subtract(table, 4), 8)) return false;
            locator = Pointer(table, -4);
            return Contains(locator, 20) && Word(locator, 0) == 0 && Word(locator, 8) == 0;
        }

        private string RttiName(IntPtr type) {
            IntPtr start = IntPtr.Add(type, 8);
            var name = new List<byte>();
            for (int i = 0; i < 256; i++) {
                IntPtr current = IntPtr.Add(start, i);
                if (!Contains(current, 1) || !Readable(current, 1, false)) return null;
                byte value = Marshal.ReadByte(current);
                if (value == 0) return Encoding.ASCII.GetString(name.ToArray());
                name.Add(value);
            }
            return null;
        }

        private IntPtr Address(int relative, int size) {
            Require(relative > 0 && (long)relative + size <= imageSize, "Stu ABI role is outside the selected image.");
            return IntPtr.Add(image, relative);
        }

        private bool Contains(IntPtr address, int size) {
            long delta = (long)unchecked((uint)address.ToInt32()) - unchecked((uint)image.ToInt32());
            return delta >= 0 && delta + size <= imageSize && Readable(address, size, false);
        }

        internal static Dictionary<string, object> Map(object value) {
            var map = value as Dictionary<string, object>;
            Require(map != null, "Stu expected a JSON object.");
            return map;
        }

        internal static int Number(object value) {
            Require(value is int, "Stu expected a signed 32-bit integer.");
            return (int)value;
        }

        internal static IntPtr Pointer(IntPtr instance, int offset) {
            return new IntPtr(Word(instance, offset));
        }

        internal static int Word(IntPtr instance, int offset) {
            IntPtr address = IntPtr.Add(instance, offset);
            Require(instance != IntPtr.Zero && Readable(address, 4, false), "Stu native field cannot be read.");
            return Marshal.ReadInt32(address);
        }

        internal static byte ReadByte(IntPtr instance, int offset) {
            IntPtr address = IntPtr.Add(instance, offset);
            Require(instance != IntPtr.Zero && Readable(address, 1, false), "Stu native field cannot be read.");
            return Marshal.ReadByte(address);
        }

        internal static string Text(IntPtr instance, int offset, int maximumLength = 32768) {
            IntPtr data = Pointer(instance, offset);
            if (data == IntPtr.Zero) return String.Empty;
            return Marshal.PtrToStringUni(data, StringLength(data, maximumLength));
        }

        internal static bool IsEmptyString(IntPtr instance, int offset) {
            IntPtr data = Pointer(instance, offset);
            return data == IntPtr.Zero || StringLength(data) == 0;
        }

        private static int StringLength(IntPtr data, int maximumLength = 32768) {
            int length = Word(data, -12);
            Require(length >= 0 && length <= maximumLength && Word(data, -8) >= length &&
                Readable(data, (length + 1) * 2, false) && Marshal.ReadInt16(data, length * 2) == 0,
                "Stu native CString is malformed.");
            return length;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MemoryRegion {
            internal IntPtr Base, AllocationBase;
            internal uint AllocationProtection;
            internal UIntPtr Length;
            internal uint State, Protection, Type;
        }

        [DllImport("kernel32.dll")]
        private static extern UIntPtr VirtualQuery(IntPtr address, out MemoryRegion region, UIntPtr size);

        [DllImport("kernel32.dll", ExactSpelling = true, CharSet = CharSet.Unicode)]
        private static extern IntPtr GetModuleHandleW(string module);

        [DllImport("kernel32.dll", ExactSpelling = true)]
        private static extern IntPtr GetProcAddress(IntPtr module, IntPtr ordinal);

        internal static bool Readable(IntPtr address, int bytes, bool executable) {
            MemoryRegion region;
            if (address == IntPtr.Zero || bytes <= 0 || VirtualQuery(address, out region,
                new UIntPtr((uint)Marshal.SizeOf(typeof(MemoryRegion)))) == UIntPtr.Zero)
                return false;
            uint access = region.Protection & 0xff;
            ulong start = unchecked((uint)region.Base.ToInt32());
            ulong first = unchecked((uint)address.ToInt32());
            return region.State == 0x1000 && (region.Protection & 0x100) == 0 &&
                (access == 2 || access == 4 || access == 8 || access == 0x20 || access == 0x40 || access == 0x80) &&
                (!executable || access >= 0x20) && first >= start && first + (uint)bytes <= start + region.Length.ToUInt64();
        }

        internal static void Require(bool ok, string message) {
            if (!ok) throw new InvalidOperationException(message);
        }
    }
}

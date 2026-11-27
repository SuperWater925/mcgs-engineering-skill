using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string SerialDeviceReadAction = "device-serial-config-read";
        private const string SerialDeviceEditAction = "device-serial-config-edit";

        private static void VerifySerialDeviceFeature(StuNativeProfile abi, string action) {
            Require(action == SerialDeviceReadAction || action == SerialDeviceEditAction, "Unknown Stu serial device action.");
            abi.RequireFeature(SerialDeviceReadAction);
            if (action == SerialDeviceEditAction) {
                abi.RequireFeature(SerialDeviceEditAction);
                VerifyFeature(abi, "compile");
            }
        }

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate int SaveSerialDeviceDocument(IntPtr document, IntPtr database);

            private sealed class SerialDeviceRecord {
                internal IntPtr Manager, Document, Device;
                internal string Name, Driver;
                internal int Id;
                internal int[] Codes;

                internal Dictionary<string, object> Value() {
                    return new Dictionary<string, object> {
                        {"path", new[] { Name }}, {"name", Name}, {"driver_key", Driver},
                        {"native_class", "CDevHalComm"}, {"native_id", Id}, {"child_driver_count", 0},
                        {"port_number", Codes[0]}, {"baud_rate", Codes[1] == 6 ? 9600 : 19200},
                        {"data_bits", 8}, {"stop_bits", "1"}, {"parity", "none"},
                        {"native_codes", new Dictionary<string, int> {
                            {"port_number", Codes[0]}, {"baud_rate", Codes[1]}, {"data_bits", Codes[2]},
                            {"stop_bits", Codes[3]}, {"parity", Codes[4]}
                        }}
                    };
                }
            }

            internal void ApplySerialDeviceAction(string action, object rawOptions, Dictionary<string, object> result) {
                bool editing = action == SerialDeviceEditAction;
                result["explicit_driver_runtime_calls"] = 0;
                result["operation_phase"] = "validate_preimage";
                result["write_attempted"] = result["native_result_may_be_partial"] = false;
                result["automatic_retry"] = false;
                if (editing) result["device_document_saved"] = result["project_saved"] = false;
                try {
                    VerifySerialDeviceFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == (editing ? 5 : 1) && options.ContainsKey("path") &&
                        (!editing || (options.ContainsKey("native_id") && options.ContainsKey("field") &&
                        options.ContainsKey("before") && options.ContainsKey("after"))),
                        "Stu serial configuration requires one exact top-level path and an explicit baud rate preimage.");
                    var path = options["path"] as IList;
                    Require(path != null && path.Count == 1, "The Stu serial parent requires exactly one path component.");
                    string name = path[0] as string;
                    Require(!String.IsNullOrWhiteSpace(name) && name.IndexOf('\0') < 0,
                        "The Stu serial parent path must be the exact nonempty name.");
                    SerialDeviceRecord before = ReadIsolatedSerialDevice(name);
                    result["record"] = before.Value();
                    result["device_document_dirty"] = context.Word(before.Document, "document_dirty") != 0;
                    result["project_dirty"] = context.Word(context.Root, "document_dirty") != 0;
                    if (editing) {
                        Require(Object.Equals(options["field"], "baud_rate"), "Only the measured Stu serial baud rate field can be edited.");
                        int oldCode = SerialBaudCode(StuNativeProfile.Number(options["before"]));
                        int newCode = SerialBaudCode(StuNativeProfile.Number(options["after"]));
                        Require(StuNativeProfile.Number(options["native_id"]) == before.Id && before.Codes[1] == oldCode &&
                            oldCode != newCode, "The current Stu serial parent ID or baud rate differs from its edit preimage.");
                        SaveSerialBaud(before, newCode, result);
                    }
                    result["operation_phase"] = "complete";
                    result["status"] = editing ? "serial_config_saved" : "serial_config_read";
                } catch (InvalidOperationException error) {
                    FailSerialWrite(result, error);
                } catch (IOException error) {
                    FailSerialWrite(result, error);
                } catch (UnauthorizedAccessException error) {
                    FailSerialWrite(result, error);
                }
            }

            private SerialDeviceRecord ReadIsolatedSerialDevice(string expectedName) {
                context.RequireProject();
                Abi.CheckTable(context.Ptr(context.Root, "root_window_model"), "root_window_model");
                IntPtr manager = Abi.Bind<GetModuleObject>("get_module_object")(1);
                Abi.CheckTable(manager, "serial_device_manager");
                Abi.CheckTable(IntPtr.Add(manager, Abi.Offset("serial_device_manager_service")), "serial_device_manager_service");
                Require(StuNativeProfile.ReadByte(manager, Abi.Offset("serial_device_manager_loaded")) == 1,
                    "The original Stu device module is not loaded.");
                IntPtr document = context.Ptr(manager, "serial_device_manager_document");
                Abi.CheckTable(document, "lifecycle_device_document");
                IntPtr list = IntPtr.Add(document, Abi.Offset("serial_device_document_list"));
                Abi.CheckTable(list, "serial_device_list");
                Require(context.Word(list, "serial_device_list_count") == 1,
                    "The isolated Stu device document must have exactly one top-level device.");
                IntPtr node = context.Ptr(list, "serial_device_list_head");
                Require(node != IntPtr.Zero && node == context.Ptr(list, "serial_device_list_tail") &&
                    context.Ptr(node, "serial_device_node_next") == IntPtr.Zero &&
                    context.Ptr(node, "serial_device_node_previous") == IntPtr.Zero,
                    "The original Stu singleton device list has inconsistent boundaries.");
                IntPtr device = context.Ptr(node, "serial_device_node_object");
                Abi.CheckSlot(device, "serial_device_parent", 12, "serial_device_exchange");
                Abi.CheckSlot(device, "serial_device_parent", 14, "serial_device_editor");
                string name = context.Text(device, "serial_device_name");
                string driver = context.Text(device, "serial_device_driver");
                int id = context.Word(device, "serial_device_id");
                Require(name == expectedName && (driver == "通用串口父设备" || driver == "通用父设备_串口") && id >= 0 &&
                    context.Ptr(device, "serial_device_owner") == document &&
                    context.Ptr(device, "serial_device_parent_object") == IntPtr.Zero,
                    "The selected original Stu serial parent name, driver, or document identity differs.");
                IntPtr children = IntPtr.Add(device, Abi.Offset("serial_device_children"));
                Abi.CheckTable(children, "serial_device_children");
                Require(context.Word(children, "serial_device_array_count") == 0 &&
                    context.Word(device, "serial_device_binding_count") == 0,
                    "The isolated Stu serial parent must have no driver children or channel bindings.");
                var codes = new[] {
                    context.Word(device, "serial_device_port"), context.Word(device, "serial_device_baud"),
                    context.Word(device, "serial_device_data_bits"), context.Word(device, "serial_device_stop_bits"),
                    context.Word(device, "serial_device_parity")
                };
                Require(codes[0] == 1 && (codes[1] == 6 || codes[1] == 8) &&
                    codes[2] == 1 && codes[3] == 0 && codes[4] == 0,
                    "The Stu serial parent differs from the measured port 1, 8 data bits, 1 stop bit, and no parity profile.");
                Require(context.Ptr(manager, "serial_device_manager_document") == document &&
                    context.Word(list, "serial_device_list_count") == 1 && context.Ptr(node, "serial_device_node_object") == device,
                    "The original Stu serial owner changed during inspection.");
                return new SerialDeviceRecord { Manager = manager, Document = document, Device = device,
                    Name = name, Driver = driver, Id = id, Codes = codes };
            }

            private void SaveSerialBaud(SerialDeviceRecord before, int newCode, Dictionary<string, object> result) {
                IntPtr modifiedService = IntPtr.Add(before.Manager, Abi.Offset("serial_device_modified_service"));
                Abi.CheckSlot(modifiedService, "serial_device_modified_service", 3, "serial_device_mark_modified");
                Abi.CheckSlot(before.Document, "lifecycle_device_document", 83, "save_serial_device_document");
                Abi.CheckSlot(before.Document, "lifecycle_device_document", 26, "lifecycle_root_is_modified");
                Abi.CheckSlot(before.Document, "lifecycle_device_document", 27, "set_root_modified");
                Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                Abi.CheckSlot(context.Root, "root", 27, "set_root_modified");
                Abi.CheckSlot(context.Root, "root", 34, "save_root");
                var markDevice = Abi.Bind<SetNativeFlag>("serial_device_mark_modified");
                var markRoot = Abi.Bind<SetNativeFlag>("set_root_modified");
                var saveDevice = Abi.Bind<SaveSerialDeviceDocument>("save_serial_device_document");
                var saveRoot = Abi.Bind<SaveRoot>("save_root");
                var isModified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                IntPtr frame = Abi.Bind<GetApplication>("get_main_frame")();
                Abi.CheckTable(frame, "frame");
                Require(frame == context.Ptr(context.App, "lifecycle_app_main_frame"),
                    "The current Stu application and original main frame differ.");
                result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, isModified, false);
                IntPtr path = Marshal.StringToHGlobalUni(context.Project);
                try {
                    RequireSerialIdentity(before, ReadIsolatedSerialDevice(before.Name), before.Codes[1]);
                    Require(context.Word(context.Root, "document_dirty") == 0 && context.Word(before.Document, "document_dirty") == 0 &&
                        isModified(context.Root) == 0 && isModified(before.Document) == 0,
                        "The Stu project and serial device document must be saved before the original configuration check.");

                    result["operation_phase"] = "original_check_before_serial_write";
                    var check = new Dictionary<string, object> { {"ok", true} };
                    result["original_check"] = check;
                    CompileProject(context, check);
                    object verified;
                    Require(check.TryGetValue("native_compile_verified", out verified) && Object.Equals(verified, true),
                        "The current Stu project did not pass the original configuration check.");
                    result["operation_phase"] = "revalidate_after_original_check";
                    context.RequireProject();
                    RequireSerialIdentity(before, ReadIsolatedSerialDevice(before.Name), before.Codes[1]);
                    Require(context.Word(context.Root, "root_compile_valid") == 1 &&
                        context.Word(context.Root, "document_dirty") == 0 && context.Word(before.Document, "document_dirty") == 0 &&
                        isModified(context.Root) == 0 && isModified(before.Document) == 0,
                        "The Stu project or serial device changed during the original configuration check.");
                    result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, isModified, false);

                    result["previous_record"] = before.Value();
                    result["modified_field"] = "baud_rate";
                    result["operation_phase"] = "write_native_baud";
                    result["read_only"] = false;
                    result["write_attempted"] = true;
                    Marshal.WriteInt32(before.Device, Abi.Offset("serial_device_baud"), newCode);
                    RequireSerialIdentity(before, ReadIsolatedSerialDevice(before.Name), newCode);

                    result["operation_phase"] = "save_device_document";
                    markRoot(context.Root, 1);
                    markDevice(modifiedService, 1);
                    Require(context.Word(before.Document, "document_dirty") == 1 &&
                        saveDevice(before.Document, IntPtr.Zero) == 0, "The original Stu serial device document did not save.");
                    markDevice(modifiedService, 0);
                    Require(context.Word(before.Document, "document_dirty") == 0 && isModified(before.Document) == 0,
                        "The original Stu serial device document remains dirty.");
                    result["device_document_saved"] = true;
                    result["device_document_dirty"] = false;

                    result["operation_phase"] = "save_root";
                    Require(saveRoot(context.Root, path) == 1 && context.Word(context.Root, "document_dirty") == 0 &&
                        isModified(context.Root) == 0, "The original Stu root project did not save.");
                    result["project_saved"] = true;
                    result["project_dirty"] = false;
                    result["operation_phase"] = "verify_saved";
                    SerialDeviceRecord saved = ReadIsolatedSerialDevice(before.Name);
                    RequireSerialIdentity(before, saved, newCode);
                    Require(context.Word(saved.Document, "document_dirty") == 0,
                        "Reading back the saved Stu serial device exposed an unsaved change.");
                    result["record"] = saved.Value();
                } finally {
                    Marshal.FreeHGlobal(path);
                }
            }

            private static void RequireSerialIdentity(SerialDeviceRecord before, SerialDeviceRecord actual, int baud) {
                Require(before.Manager == actual.Manager && before.Document == actual.Document && before.Device == actual.Device &&
                    before.Name == actual.Name && before.Driver == actual.Driver && before.Id == actual.Id,
                    "The original Stu serial parent identity changed.");
                for (int index = 0; index < before.Codes.Length; index++)
                    Require(actual.Codes[index] == (index == 1 ? baud : before.Codes[index]),
                        "The original Stu serial configuration differs at field " + index + ".");
            }

            private static int SerialBaudCode(int value) {
                if (value == 9600) return 6;
                if (value == 19200) return 8;
                throw new InvalidOperationException("The verified Stu serial baud rates are 9600 and 19200.");
            }

            private static void FailSerialWrite(Dictionary<string, object> result, Exception error) {
                result["ok"] = false;
                result["error"] = error.Message;
                bool partial = Object.Equals(result["write_attempted"], true);
                result["native_result_may_be_partial"] = partial;
                result["status"] = partial ? "native_operation_incomplete" : "precondition_rejected";
            }
        }
    }
}

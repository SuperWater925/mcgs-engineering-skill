using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate IntPtr NativePointer(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate void NativeVoid(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate int NativeResult(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate int OriginalCheck(IntPtr self, IntPtr detail);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate void ResizeArray(IntPtr self, int size, int growBy);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate IntPtr ReadArrayMember(IntPtr self, int index);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate void SetPopupPolicy(IntPtr self, int enabled);

        private static void CompileProject(Context context, Dictionary<string, object> receipt) {
            context.RequireProject();
            var abi = context.Abi;
            abi.CheckSlot(context.Root, "root", 85, "root_check_slot");
            IntPtr frame = abi.Bind<GetApplication>("get_main_frame")();
            abi.CheckTable(frame, "frame");
            Require(context.Ptr(frame, "frame_hwnd") != IntPtr.Zero, "Stu original check has no main frame.");
            IntPtr dialog = context.Ptr(context.Root, "root_diagnostics");
            abi.CheckTable(dialog, "diagnostic_dialog");
            IntPtr callback = abi.Bind<NativePointer>("get_diagnostic_callback")(context.Root);
            Require(callback == IntPtr.Add(dialog, abi.Offset("diagnostics_callback")), "Stu original diagnostic callback owner differs.");
            abi.CheckSlot(callback, "diagnostic_callback", 1, "diagnostic_clear");
            abi.CheckSlot(callback, "diagnostic_callback", 6, "set_popup");
            abi.CheckSlot(callback, "diagnostic_callback", 7, "get_popup");

            var clear = abi.Bind<NativeVoid>("diagnostic_clear");
            var clearRoot = abi.Bind<NativeResult>("root_clear_diagnostic");
            var getPopup = abi.Bind<NativeResult>("get_popup");
            var setPopup = abi.Bind<SetPopupPolicy>("set_popup");
            var init = abi.Bind<NativePointer>("array_ctor");
            var resize = abi.Bind<ResizeArray>("array_resize");
            var check = abi.Bind<OriginalCheck>("check");
            var arrayCount = abi.Bind<NativeResult>("array_count");
            var arrayItem = abi.Bind<ReadArrayMember>("array_item");
            var destroy = abi.Bind<NativeVoid>("array_dtor");
            int size = abi.Offset("compile_array_size");
            Require(size == 64, "Stu original diagnostic array storage size differs.");
            int previousPopup = getPopup(callback) & 0xff;
            IntPtr array = Marshal.AllocHGlobal(size);
            bool constructed = false, policyChanged = false;
            try {
                Marshal.Copy(new byte[size], 0, array, size);
                init(array);
                constructed = true;
                resize(array, 0, -1);
                context.RequireProject();
                receipt["read_only"] = false;
                receipt["write_attempted"] = true;
                clear(callback);
                clearRoot(context.Root);
                setPopup(callback, 0);
                policyChanged = true;
                context.RequireProject();
                receipt["native_compile_executed"] = true;
                int result = check(context.Root, array);
                int errors = context.Word(callback, "callback_errors");
                int warnings = context.Word(callback, "callback_warnings");
                int valid = context.Word(context.Root, "root_compile_valid");
                int count = arrayCount(array);
                Require(errors >= 0 && warnings >= 0 && count >= 0 && count <= 65536, "Stu original diagnostic count cannot be decoded.");
                var limits = new List<string>();
                for (int i = 0; i < count; i++) limits.Add(StuNativeProfile.Text(arrayItem(array, i), 0));
                receipt["native_compile_verified"] = result == 0 && valid == 1 && errors == 0;
                receipt["compile_result"] = result;
                receipt["compile_valid"] = valid;
                receipt["errors"] = errors;
                receipt["warnings"] = warnings;
                receipt["compiler_limit_messages"] = limits;
                receipt["diagnostics"] = ReadDiagnostics(context, callback);
                receipt["first_error_object"] = context.Text(context.Root, "root_first_error_owner");
                receipt["first_error_message"] = context.Text(context.Root, "root_first_error_text");
                receipt["first_error_code"] = context.Word(context.Root, "root_first_error_code");
            } catch (InvalidOperationException error) {
                if (!receipt.ContainsKey("write_attempted")) throw;
                receipt["ok"] = false;
                receipt["native_compile_verified"] = false;
                receipt["native_result_may_be_partial"] = true;
                receipt["error"] = error.Message;
            } finally {
                try {
                    if (policyChanged) setPopup(callback, previousPopup);
                } finally {
                    try { if (constructed) destroy(array); }
                    finally { Marshal.FreeHGlobal(array); }
                }
            }
        }

        private static List<object> ReadDiagnostics(Context context, IntPtr callback) {
            IntPtr sentinel = context.Ptr(callback, "callback_list_sentinel");
            int count = context.Word(callback, "callback_list_count");
            Require(count >= 0 && count <= 65536, "Stu original diagnostic list count cannot be decoded.");
            IntPtr node = context.Ptr(sentinel, "list_next"), previous = sentinel;
            var visited = new HashSet<IntPtr>();
            var rows = new List<object>();
            for (int i = 0; i < count; i++) {
                Require(node != sentinel && visited.Add(node) && context.Ptr(node, "list_previous") == previous,
                    "Stu original diagnostic list nodes are inconsistent.");
                IntPtr row = IntPtr.Add(node, context.Abi.Offset("list_row"));
                rows.Add(new Dictionary<string, object> {
                    {"object", context.Text(row, "row_object")}, {"message", context.Text(row, "row_message")},
                    {"line_text", context.Text(row, "row_line")}, {"severity", context.Text(row, "row_severity")},
                    {"marker", context.Text(row, "row_marker")}
                });
                previous = node;
                node = context.Ptr(node, "list_next");
            }
            Require(node == sentinel && context.Ptr(sentinel, "list_previous") == previous, "Stu original diagnostic list tail differs.");
            return rows;
        }
    }
}

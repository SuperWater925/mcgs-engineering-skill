using System;
using System.Collections.Generic;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string TriggerCatalogAction = "strategy-trigger-catalog", TriggerReadAction = "strategy-trigger-read";

        private sealed partial class StuDocument {
            private static readonly string[] TriggerKinds = {"Start", "End", "Loop", "User", "Event"};
            private static readonly string[] TriggerPeriods = {"year", "month", "day", "hour", "minute"};
            private static readonly string[] TriggerCalendarFields = {"month", "day", "hour", "minute", "second"};

            internal void ReadTriggers(string action, object rawOptions, Dictionary<string, object> receipt) {
                VerifyFeature(Abi, action);
                var blocks = ReadStrategyBlocks();
                var read = new List<object>();
                var unavailable = new List<object>();
                if (action == TriggerReadAction) {
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == 2 && options.ContainsKey("block_id") && options.ContainsKey("block_name"),
                        "Select the exact original Stu strategy ID and name.");
                    int id = StuNativeProfile.Number(options["block_id"]);
                    string name = NativeEngineeringDeliveryLayout.Value(options, "block_name");
                    StrategyBlock selected = blocks.Find(block => block.Id == id && block.Name == name);
                    Require(selected != null, "The original Stu strategy selector is absent.");
                    receipt["strategy"] = selected.Value();
                    blocks = new List<StrategyBlock> {selected};
                }
                foreach (StrategyBlock block in blocks) {
                    try {
                        var trigger = ReadTrigger(block);
                        if (trigger == null) continue;
                        // Stock system triggers can share the stored raw trigger word.
                        // The verified strategy owner distinguishes their live entries.
                        read.Add(trigger);
                    } catch (InvalidOperationException error) {
                        unavailable.Add(new Dictionary<string, object> {
                            {"block_id", block.Id}, {"block_name", block.Name}, {"reason", error.Message}
                        });
                    }
                }
                if (action == TriggerReadAction) receipt["trigger"] = read.Count == 0 ? null : read[0];
                else {
                    receipt["triggers"] = read;
                    receipt["trigger_count"] = read.Count;
                }
                receipt["unavailable"] = unavailable;
                receipt["all_requested_features_available"] = unavailable.Count == 0;
            }

            private Dictionary<string, object> ReadTrigger(StrategyBlock block) {
                IntPtr trigger = context.Ptr(block.Complete, "strategy_block_trigger");
                if (trigger == IntPtr.Zero) return null;
                int found = -1;
                string table = null;
                for (int kind = 0; kind < TriggerKinds.Length; kind++) {
                    string item = "strategy_trigger_" + TriggerKinds[kind].ToLowerInvariant();
                    if (!Abi.IsTable(trigger, item)) continue;
                    found = kind;
                    table = item;
                    break;
                }
                Require(found >= 0, "The Stu trigger has an unrecognized original class.");
                string serialize = "strategy_trigger_common_archive";
                if (found == 2 || found == 4) {
                    string role = "strategy-trigger-" + TriggerKinds[found].ToLowerInvariant();
                    Abi.RequireFeature(role);
                    serialize = table + "_archive";
                }
                Abi.CheckSlot(trigger, table, 2, serialize);
                int id = context.Word(trigger, "trigger_id"), kindId = context.Word(trigger, "trigger_type");
                Require(id >= 0 && context.Word(trigger, "trigger_owner") == block.Id && kindId == found,
                    "The original Stu trigger identity, type or strategy owner differs.");
                int rawOffset = Abi.Offset("trigger_raw_word");
                var value = new Dictionary<string, object> {
                    {"block_id", block.Id}, {"block_name", block.Name}, {"trigger_id", id},
                    {"native_class", "CTrigger" + TriggerKinds[found]}, {"native_type", kindId},
                    {"note", context.Text(trigger, "trigger_note")},
                    {"raw_common_fields", ReadTriggerWords(trigger, rawOffset, 3)}
                };
                if (found == 2) {
                    int mode = context.Word(trigger, "trigger_loop_mode"), period = context.Word(trigger, "trigger_loop_period");
                    var schedule = new Dictionary<string, object> {
                        {"native_mode", mode}, {"mode", mode == 0 ? "interval" : mode == 1 ? "calendar" : null},
                        {"interval_ms", context.Word(trigger, "trigger_loop_interval")}, {"native_calendar_period", period},
                        {"calendar_period", period >= 0 && period < TriggerPeriods.Length ? TriggerPeriods[period] : null}
                    };
                    int start = Abi.Offset("trigger_loop_date_fields");
                    for (int i = 0; i < TriggerCalendarFields.Length; i++)
                        schedule.Add(TriggerCalendarFields[i], StuNativeProfile.Word(trigger, start + i * sizeof(int)));
                    value["schedule"] = schedule;
                } else if (found == 4) {
                    value["expression"] = context.Text(trigger, "trigger_event_expression");
                    value["raw_event_fields"] = ReadTriggerWords(trigger, Abi.Offset("trigger_event_words"), 2);
                }
                return value;
            }

            private static uint[] ReadTriggerWords(IntPtr trigger, int offset, int count) {
                var values = new uint[count];
                for (int i = 0; i < count; i++) values[i] = unchecked((uint)StuNativeProfile.Word(trigger, offset + i * sizeof(int)));
                return values;
            }
        }
    }
}

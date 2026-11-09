# Precompiled portable Pro engineering engine

The release contains an already compiled x86 managed business DLL. The same
bytes are copied to each connection; recipients do not build an engine, edit C#,
or need a C# compiler. This directory is maintained separately from the legacy
per-scope bound-source compiler, which remains available for old deployments.

`build_generic.py` is **release maintenance only**. It reads the exact owned raw
source manifest and classified source-address catalog, emits generic copies to
an external build directory, and writes `build-release.ps1`. The raw 163 sources
are preserved. The release compiler consumes those copies plus the runtime
layout, table resolver and existing ABI helper. A new DLL is built when our own
engine implementation changes, never when the user's Pro version changes.

`materialize.py` is **recipient initialization**. It discovers the selected
installation's actual modules, resolves current functions and native tables,
materializes profiles with their actual dependency SHA values, and emits JSON
address/guard/ordinal/module maps. It copies the published DLL without altering
a byte. It does not generate C#, invoke Csc, launch Pro or touch a project.
An immutable historical C# review artifact is deployed as text data. Its
reference and actual digest remain consistent.

The materializer reads the selected DLL's `EvidenceLayout` metadata. An engine
with `flat-v1` stores each evidence file once under `task-evidence/a` and uses a
short numbered name. Its binding maps the original logical names to these
files. The runtime still checks the SHA of the mapped file and uses the
original logical key for the ABI profile. Older DLLs use their existing
directory layout.

```powershell
python materialize.py --scope-base-json D:\task\base.json `
  --engine-file D:\bundle\engine\business\McgsEngineering.Portable.dll `
  --engine-sha256 <published-own-DLL-SHA256> `
  --output-directory D:\task\rt\engine
```

The base JSON uses the existing schema 1 fields: `task_root`, `engineering_root`,
`runtime_root`, `install_root`, `transport_client_file`,
`transport_client_sha256`, and optional `editor_executable`. All directories
must exist. The engineering directory must be empty; runtime and engineering
must be disjoint. The queue transport source must be directly in `runtime_root`
because its own directory selects the durable inbox/outbox/claim queue. Its
existing at-most-once implementation digest is unchanged.

The returned scope adds three fields: `portable_engine_contract`,
`portable_binding_file`, `portable_binding_sha256`. The sibling scope's actual
SHA is calculated at runtime and checked against each engineering request;
scope, binding and transport bytes are rechecked before engineering execution.
`portable-engine-binding.json` identifies the exact own source release and
contains the actual index SHA, 535 classified address rows, six guard rows,
16 ordinal rows, owned-artifact digests and current absolute module paths.
Counts describe the present source catalog, not a Pro version restriction.

Software version strings and author-machine vendor hashes are never admission
conditions. The resolver retains current function, calling convention, object
layout and source-guard contracts. A missing native feature reports its own
unavailable entry. A successful attachment does not stand for project save,
native check, close/reopen or simulation acceptance.

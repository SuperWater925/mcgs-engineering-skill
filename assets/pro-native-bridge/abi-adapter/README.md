# Current PE address preparation

This preparer reads PE32/I386 files; it never starts the editor, loads vendor
DLLs, or writes an engineering project. Install `requirements.txt` using the
same Python executable used by the skill. Offline editing does not need this
dependency.

## Portable inputs and contracts

`catalogs/reference.json.gz` uses gzip storage for the expanded
`mcgs-native-reference-catalog/v1` JSON document. It contains
sparse existing guard fragments, decoded instruction semantics, branch-target
contexts, export names, and MSVC RTTI/COL/hierarchy/vtable roles. It does not
contain vendor files or sections, and requires no author installation at use
time. `catalogs/source-addresses.json` describes classified source address
spans; object offsets, strides, slot indexes and ordinary constants are not PE
addresses and must not be rewritten as such.

`reference_modules` is keyed by logical alias. Every entry has `basename`,
observed `sha256`, `image_base`, PE facts, and optional
`install_relative_path` (relative to the selected installation root, using
forward slashes). Additional module aliases use their lowercase filename.
Driver guards declared as `driver-ui` inherit the exact containing driver's
path; distinct drivers must not share an arbitrary global `driver-ui` target.

Python API:

```python
catalog = create_catalog(reference_modules, profile_root, explicit_fields=None)
result = resolve_catalog(catalog, actual_modules, reference_modules=None,
                         prefer_content_cache=True)
attestation = write_resolved_profiles(catalog, result, output_dir,
                                      profile_root=profile_root)
# load_catalog(path) accepts plain .json and gzip .json.gz catalogs.
```

Module arguments are alias-to-local-file dictionaries. The optional reference
files are not required for the shipped catalog's sparse contexts. Catalog
creation discovers declared PE dependencies inside the selected installation;
missing or ambiguous modules remain explicit gaps.

CLI:

```text
abi_locator.py catalog --reference-module editor=EDITOR.exe --profiles PROFILE_ROOT --explicit-fields catalogs/source-addresses.json --out NEW_CATALOG.json
abi_locator.py locate --actual-module editor=EDITOR.exe --actual-module mfc=MFC.dll --profiles PROFILE_ROOT --resolved-directory NEW_DIRECTORY --out NEW_RESULT.json
```

`locate` defaults to `catalogs/reference.json.gz`. Pass all actual modules selected
for this installation. `--catalog` overrides the catalog; `--no-content-cache`
requests dynamic location even for byte-identical observations. None of these
commands installs software or requests a product upgrade.

The catalog generator also accepts `--out NEW_CATALOG.json.gz` and writes
deterministic gzip with its timestamp set to zero. Compression changes only
storage: result/attestation `catalog_sha256` still identifies the expanded
canonical JSON bytes. Package metadata records the compressed file's storage
SHA separately. No native engine inputs or function-location contracts change.

## Address and guard evidence

`mcgs-native-abi-adaptation/v1` results include `functions`, `types`, `proofs`,
`gaps` and `rva_maps`. Each map has the shape:

```json
{"editor":{"0x1234":{"actual_rva":22136,"kind":"function","proof_id":"...","proof_ids":["..."]}}}
```

Resolved functions include `actual_guard_bytes`,
`guard_bytes_at_reference_preferred_base` and `actual_relocation_offsets`.
Existing guards use the second representation, so their original
loaded-base-minus-reference-preferred-base HIGHLOW calculation remains valid.
Actual RVAs must not be reference-mapped a second time.

Only real HIGHLOW dwords and correctly decoded relative transfer operands are
normalized. Object-member displacements stay exact. Thunks require complete
body/target proof. Export/RTTI roles and uniquely proven caller referents may
disambiguate candidates; a reference RVA is never a tie breaker. A complete
content-equivalence cache is optional evidence for unchanged files, not a
hash whitelist: changed files still use dynamic location without an upgrade
requirement. Named/uniquely located exports prove any updated ordinal. Declared
loader-zero virtual data preserves its runtime zero guard rather than
inventing file-backed bytes.

## Partial profiles and limits

`write_resolved_profiles` produces every profile plus a real SHA and
`mcgs-native-resolved-profiles/v1` attestation. Entries in
`reference_profiles` identify original and derived hashes/paths, status
`resolved`, `partial` or `unresolved`, and precise `unresolved_fields` JSON
pointers. Retained unresolved reference numbers are explicitly not actual
addresses. Core `functions[]` and `vtable_guards[]` rows have
`_abi_resolution` with `status`, `details`, and `proof_ids` for per-entry use.
One unrelated missing entry must not disable every core function.

Absolute target paths appear only in local results/attestations, never in the
portable reference catalog. Existing object layout and calling-semantic
contracts remain in force. Code/RTTI location is not proof of changed object
layouts, successful native editing, or validation of every software release.

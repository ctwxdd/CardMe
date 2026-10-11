# CardMe

Native Apple Silicon macOS photo-card recovery. Source operations are read-only; reports and recovered copies are saved separately. Processing is local, with no uploads or account setup.

## Consumer flow

1. **Choose card…** lists connected physical external devices and removable SD cards, even when they are absent from Finder.
2. **Scan card** scans mounted photos directly in the direct-download edition. No second folder picker appears. Unmounted cards can proceed straight to Rescue. A mounted card with no visible photos offers Deep Rescue; “Find deleted or formatted photos…” is also available after a nonempty scan.
3. **Rescue** starts Normal rescue: choose a save folder, then the app reads only flagged photos. On mounted exFAT cards, Normal rescue automatically reads allocation metadata and selected photo regions through a read-only descriptor, tests fragmented JPEG chains and displaced-FAT hypotheses, and uses embedded camera previews to locate surviving tails. It generates fragment-map.json beside its report, without a prebuilt profile or whole-card image. Other filesystems fall back to readable-file decoding. Private card-specific profiles are not distributed. No full-card image or card-sized capacity check is required. Results clearly distinguish full-resolution decoded copies from previews/thumbnails.
4. If Normal rescue cannot restore every full-resolution photo, **Try Deep Rescue…** appears beside the results. Cards whose files are inaccessible go directly to this guidance. Deep explains the slower whole-card safety copy, asks where to save it, and requires free storage strictly greater than the physical card size plus room for outputs.
5. In the direct-download edition, macOS may ask to authorize read-only raw card access. Bundled GNU ddrescue makes `card.img` and a recovery map in a fresh safety-copy folder, then searches the image for contiguous JPEG streams and saves exact source-byte copies directly into a fresh results folder on the selected fixed disk or SSD. **Show rescued photos** opens the results. Quickly formatted or deleted files can be found without their directory entries, if their JPEG data survives contiguously. The search cannot reconstruct overwritten data or guarantee that a decoded photo has no pixel corruption.

The damaged-file list previews the original files while scanning. Use ↑/↓ to navigate, Space for Quick Look, and Show in Finder for available originals. Choose photo folder… remains available. Quick scans check thumbnail → EXIF → image header, stopping a file on its first failure; Details offers full pixel checks. Quick passes do not certify all pixels. RAW is excluded. Inaccessible folders are reported without aborting the whole scan.

## Editions and safety

- **Direct download:** no App Sandbox; includes automatic whole-card imaging. Apple's system `authopen` supplies a read-only descriptor, so neither the app nor ddrescue runs as root. GNU ddrescue receives that descriptor, never a writable card handle. No mount, repair or formatting operations are issued. Card connection identity and size are checked before and throughout copying. If raw access is denied or busy, the app stops safely rather than claiming success.
- **App Store target:** sandboxed. The system folder picker is required to grant source access, and whole-card imaging remains unavailable. Normal rescue reads user-authorized folders; Deep accepts an existing safety image after the capacity gate. This target does not bundle ddrescue.

Outputs never overwrite existing images or prior results. The save destination must be writable, not removable, and on another physical device. Whole-card imaging copies readable data first, then performs at most two retry passes for remaining bad sectors. Bad sectors are reported explicitly; unreadable gaps are not recovered bytes. Stop preserves the partial image and map. The current UI starts a fresh imaging attempt on retry; the saved map is available for external continuation. JPEG searching can pause and continue from its image/checkpoint, including through Continue previous rescue. Reusing a changed image or output is refused. A completed safety copy remains available even if photo recovery is unsupported or fails.

A capacity check is a preflight, not a reservation. Card imaging can take a long time. Hardware failures may prevent complete reads. The app does not invent missing pixels or promise that a damaged original can always be restored.

## Current recovery support

**General deleted/formatted-card recovery now supports contiguous JPEG primary streams.** Deep Rescue and “Use saved copy…” search every image byte, independently of FAT/exFAT directories. Baseline and progressive 8-bit JPEGs are supported. Marker lengths, scan boundaries, byte stuffing and restart markers determine stream ends; complete primary streams must decode before publication. Output JPEG bytes are copied unchanged from the image, without synthesized coefficients or pixels. Found JPEGs may include camera previews or live photos; original filenames and deleted/live status cannot generally be determined. Photos must be checked before use. JPEGs whose embedded thumbnail disagrees are explicitly marked for review. A decoded camera JPEG is counted as a full-size copy only when its longest edge exceeds 2048 pixels, camera make/model are present, and EXIF image dimensions match the decoded frame; size alone never qualifies. This is a conservative classification, not proof of the original capture resolution or authentic pixels. Completed older reports reclassify their hash-verified saved JPEGs without rescanning the card image or rewriting photos.

The general search uses bounded 8 MiB reads, a 128 MiB maximum encoded JPEG and a 64-million-pixel decode limit. It keeps an identity-bound checkpoint and source offsets, updates progress, preserves completed outputs on cancellation and refuses modified outputs or changed images on resume. Results go directly to the user-selected fixed disk/SSD, avoiding a second full set in private Mac storage. Swift checks destination/card identity; the engine independently refuses removable or read-only output volumes. Existing safety copies can reside on the same fixed disk as their results, in separate folders. The App Store edition searches user-authorized existing images; it cannot make raw-card images.

**Bounded exFAT fragmented JPEG analysis is available during Normal rescue; RAW recovery is not implemented.** A quick format may leave contiguous photos recoverable, and Deep Rescue also attempts bounded reconstruction when surviving MPF headers and a uniquely matched camera preview provide enough information. Automatic exFAT analysis requires surviving directory entries, headers and useful allocation links; it does not solve arbitrary fragments or overwritten/erased data.

The folder engine can export decoded primary images as re-encoded PNG copies, embedded previews or thumbnails. On sources without usable exFAT allocation metadata, those embedded fallbacks do not restore filesystem-hidden original fragments. Lower-resolution results are labeled. Nothing writes to the source card, source photos or safety image.

## Build

Requires Apple Silicon, macOS 14+, Xcode Command Line Tools, and a build-host Python 3. Runtime users need no installed Python or recovery tools.

```sh
python3 scripts/build-runtime.py
./scripts/build.py --direct-download --dmg
```

The runtime builder uses pinned upstream CPython 3.12.14 source, disables GNU readline and unnecessary optional modules, and links external dependencies only to macOS system libraries. The app builder uses a pinned Pillow arm64 wheel and compiles GNU ddrescue 1.30 from its included upstream source plus the disclosed input-descriptor patch. Source archive and wheel hashes are checked before packaging. Build artifacts and recovery data stay outside Git, under build/ and work/.

Output: `build/CardMe.app` and `build/CardMe.dmg`. Use `--build-dir /path/on/SSD` to keep app, DMG and staging off a full internal disk. The DMG includes an Applications shortcut. To sign a direct-download candidate:

```sh
./scripts/build.py --direct-download --dmg --sign-identity 'Developer ID Application: YOUR NAME (TEAMID)'
```

The default local build is ad-hoc signed, not notarized. Public distribution needs Developer ID signing, Apple notarization and stapling. With your configured credentials:

```sh
xcrun notarytool submit build/CardMe.dmg --keychain-profile YOUR_PROFILE --wait
xcrun stapler staple build/CardMe.dmg
```

No publishing or notarization upload is performed by the builder. The public downloaded candidate must be validated separately.

For the sandboxed build, run `./scripts/build.py` or open CardRescue.xcodeproj. The Xcode shared scheme stages the same audited runtime with App Sandbox, user-selected destination access and read-only source bookmarks. Select your Apple Developer team and registered identifier before distribution. Signing, listing/support/privacy-policy URLs, screenshots, distribution validation and Apple review remain release work.

## Licenses and source

**About CardMe** (the info button or app menu) displays notices and full licenses, and opens the included source/build instructions. Complete notices: THIRD_PARTY_NOTICES.md.

GNU ddrescue is a separate GPL-2.0-or-later executable with a disclosed read-only descriptor patch. Every direct-download app includes its complete corresponding source archive, license, authors, source patch and build instructions. Do not remove these or impose restrictions on recipients' GPL rights. This aggregation does not by itself place the Swift app under the GPL. CPython's source and license, and Pillow's complete combined codec/font license notices, also accompany the app. The prior readline-containing runtime is rejected by the builder.

## Validation

```sh
xcrun swiftc -D TESTING -parse-as-library -swift-version 5 Sources/CardRescue.swift Sources/ResultExport.swift tests/NavigationCheck.swift -o work/navigation-check
./work/navigation-check
work/python-runtime/bin/python3 -B tests/imaging-check.py
PYTHONHOME="$PWD/build/CardMe.app/Contents/Resources/python" \
  build/CardMe.app/Contents/Resources/python/bin/python3 -B tests/direct-card-check.py
python3 tests/direct-package-check.py
# With the bundled Python/Pillow runtime:
python3 tests/carving-check.py
```

Imaging checks use the real bundled ddrescue on disposable regular-file fixtures, including modeled bad sectors, cancellation and conflicting outputs. They never read a card. Package checks verify signatures, source/license contents, non-sandboxed direct-download executables and DMG integrity.

Run `tests/check.py` and `tests/folder-rescue-check.py` with the bundled interpreter and its PYTHONHOME to verify scanning and recovery under the actual relocated runtime. Private real-card benchmarks are excluded from this repository; fixtures use synthetic data. Temporary fixtures clean up after themselves. A real raw-card authorization and full imaging run require user interaction and have not been qualified by fixture tests.

Usage statistics checks run with an intercepted URLSession, without contacting production:

```sh
xcrun swiftc -D TESTING -parse-as-library -swift-version 5 Sources/CardRescue.swift Sources/ResultExport.swift tests/UsageStatisticsCheck.swift -o work/usage-check
work/usage-check
```

The frameless UI mark is generated from shared vector geometry with `swift scripts/brand.swift website/dist/assets`. The Dock icon retains its separate approved artwork.

Localized website copy lives in `website/locales/*.json`. Run `python3 scripts/build-website.py` and `python3 tests/website-check.py` after edits. The app UI remains English.

## EXIF assembly

After a completed general JPEG search, a unique MPF thumbnail relationship takes priority when primary size, child offset, child length and type match the recovered records, and existing camera/date metadata does not conflict. MP offsets are relative to the APP2 TIFF header; index matching has no 32 MiB distance limit. The header walk is bounded to 1 MiB. Without an index relationship, previews without orientation can be paired with camera photos within 32 MiB only when aspect ratios agree and embedded-thumbnail comparison scores are at most 5 with a margin of at least 2 over the next candidate. If thumbnail matching fails, nearby decoded primary images are compared at a common reduced size; a score at most 3 and a margin of at least 1.5 are required. This fallback creates the derived thumbnail from the preview itself and preserves the primary review status. The manifest records the comparison used. Bounded caches retain 64 thumbnails and 32 reduced primary images. Selected camera/date/orientation tags and an embedded thumbnail are written into separate `best_available/Metadata Copies` JPEGs; image streams, original files, original report hashes and card bytes remain unchanged. GPS, serials and MakerNote are not transplanted. Preview dimensions describe the preview, never the primary photo. Pairings and inferred metadata are recorded in `metadata-assembly.json`. Ambiguous matches stay untouched; no original filename or missing pixels are invented. Quick View uses the metadata copy when available.

Run `tests/metadata-assembly-check.py` with the bundled runtime for visual matching, ambiguity, thumbnail/EXIF assembly, unchanged image streams, idempotence and source safety.

## Preview-guided fragment fallback

Deep Rescue and saved-image recovery first retain their existing two/three-part reconstruction. When those methods find no valid join, baseline JPEGs without restart intervals can try bounded continuation ranking against a surviving camera preview. Ambiguous legacy joins and exhausted legacy budgets do not trigger this fallback. Current JPEG state and camera-preview luminance rank nearby clusters and the MPF tail hypothesis; verified reconstructed-source extents are excluded after rehashing the current image bytes. No historical allocation map is an input.

Each candidate has a shared 90-second budget, at most 16 joins, and a local window of 256 clusters in either direction. If the first locally ranked full cluster fails, try windows of 512 clusters around both the next physical cluster and the current MPF preview-derived tail position, under the same deadline. A 512-byte preview-luminance check discards poor short probes before the 4 KiB ranking check; after four validated joins a 1 KiB coarse probe selects at most eight positions for the original 4 KiB reranking. Full-cluster and final checks remain required. Strict marker extent, full decode, dimensions, thumbnail and reduced-preview agreement are required. Saved bytes come solely from recorded source extents. These greedy candidates remain **Full-size candidate · please check**, classified as manual review rather than confirmed recovery. This is not an exhaustive search or proof of unique reconstruction. Normal rescue uses its existing allocation-based engine.

Run `tests/preview-guided-check.py` with the bundled runtime for four-part recovery, checkpoint equivalence, cancellation, source-read failures, hash/ownership refusal, publication, resume, and preservation of legacy ambiguity refusals.

If the marker-derived prefix fails incremental JPEG decoding or exceeds the declared primary length, the engine observes cluster-by-cluster coding validity and camera-preview luminance within that length. The first failed boundary supplies an earlier prefix hypothesis. The retry shares the original deadline, keeps the original diagnostic unchanged, and records the chosen prefix in output provenance. Missing or ambiguous previews and continuation errors do not enable this retry.

## Native continuation ranking

After the existing preview-guided fallback fails or expires, `preview-ranked.py` searches allocation-cluster starts with a bundled C++ JPEG checkpoint ranker. The ranker receives the existing read-only source descriptor; no historical image, hardcoded card offset, profile, synthesized bytes, or external installation is used. Candidate state files live in a temporary directory and contain decoder state/reduced guide pixels, not original photo streams. The subprocess is polled for cancellation and the shared phase deadline, then killed and reaped on failure. Source identity remains checked in both readers.

The observed photo high-water plus 256 MiB forms the first band; the rest is ranked when no first-band full cluster passes. Each band keeps at most 512 probes. Luminance screening uses 16 KiB probes and takes the first full-cluster-valid choice, deferring up to four alternatives until the complete path fails (at most 32 replay paths). If unsuccessful, whole-cluster Y/Cb/Cr ranking validates at most the top eight probes. Each phase shares 900 seconds across its paths; each path has at most 16 joins. Prefix ownership is applied after observed rollback. Only hash-verified previously reconstructed full-resolution ranges are excluded; manual-review candidates cannot permanently remove search space. Full-step cache is bounded to eight exact byte sequences per join.

Strict coding checkpoints run in the native helper; complete primary JPEG marker walks, dimensions, full pixel decode, embedded thumbnail and full preview agreement remain authoritative in Python. Outputs are manual review with original source extents, not certified byte-exact originals. The bounded cluster-aligned search does not cover every possible fragmented JPEG. `tests/ranked-recovery-check.py` checks both ranking modes, byte-exact four-fragment fixtures, rollback/ownership, lazy replay, short reads and cancellation. Build the native checker with `clang++ -O3 -std=c++17 engine/native/jpeg-ranker.cpp -o engine/native/jpeg-ranker` for development; the app builder compiles/signs it automatically.

Full-cluster shortlist screening runs in one native batch before Python validates the survivors. Filtering retains the original scores, ordering and duplicate positions. The focused test compares native decisions against Python on valid, invalid and out-of-bounds candidates; it also checks timeout propagation.

The shared recovery caller first completes all quick two-part joins, then tries the remaining three-part/preview-guided/native searches. Failed quick joins retain an older algorithm version until the harder pass finishes, so stopping between passes cannot mark them complete. Ambiguity and legacy budget refusals remain final. Local preview-guided probes use the same early-luminance check, score ordering and coarse/refined ranking through native batches. Prefixes and full clusters advance through native checkpoints in at most 128 KiB steps. Tests compare every decoder state field, scores and complete continuation decisions against Python; unsupported native state falls back to Python in the local engine. Algorithm version 8 retries earlier unresolved checkpoints once.

For end-to-end qualification, run `tests/full-recovery-benchmark.py --image /path/card.img --output /path/fresh-run --expected /path/expected.json` with the bundled runtime. The expected file maps cohort names to `{source_offset: sha256}`; it is read only after the ordinary rescue CLI exits and is never passed to the search. The benchmark requires a fresh folder, writes timing/quality/hash results to `benchmark.json`, and fails for incomplete runs, changed source identity, missing outputs or different bytes. Exit 2 from rescue means manual-review results and is evaluated normally. Keep private images, reference manifests and results under ignored `work/`.

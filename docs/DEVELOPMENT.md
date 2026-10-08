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

**General deleted/formatted-card recovery now supports contiguous JPEG primary streams.** Deep Rescue and “Use saved copy…” search every image byte, independently of FAT/exFAT directories. Baseline and progressive 8-bit JPEGs are supported. Marker lengths, scan boundaries, byte stuffing and restart markers determine stream ends; complete primary streams must decode before publication. Output JPEG bytes are copied unchanged from the image, without synthesized coefficients or pixels. Found JPEGs may include camera previews or live photos; original filenames and deleted/live status cannot generally be determined. Photos must be checked before use. JPEGs whose embedded thumbnail disagrees are explicitly marked for review.

The general search uses bounded 8 MiB reads, a 128 MiB maximum encoded JPEG and a 64-million-pixel decode limit. It keeps an identity-bound checkpoint and source offsets, updates progress, preserves completed outputs on cancellation and refuses modified outputs or changed images on resume. Results go directly to the user-selected fixed disk/SSD, avoiding a second full set in private Mac storage. Swift checks destination/card identity; the engine independently refuses removable or read-only output volumes. Existing safety copies can reside on the same fixed disk as their results, in separate folders. The App Store edition searches user-authorized existing images; it cannot make raw-card images.

**Bounded exFAT fragmented JPEG analysis is available during Normal rescue; RAW recovery is not implemented.** A quick format may leave contiguous photos recoverable, but the whole-card JPEG search still only supports contiguous streams. Automatic exFAT analysis requires surviving directory entries, headers and useful allocation links; it does not solve arbitrary fragments or overwritten/erased data.

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

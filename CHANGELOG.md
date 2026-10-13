# Changelog

## 0.3.38 · build 51

- Extend Normal rescue on supported exFAT cards with bounded two/three-part JPEG joins and local preview-guided reconstruction after allocation-chain attempts fail. Keep sector-aligned read-only access, cancellation, source identity checks and separate outputs; no whole-card copy is required for this path.
- Preserve complete readable JPEGs without re-encoding, including surviving EXIF orientation and indexed previews. Label decoded full-size PNG fallback copies explicitly in English and Traditional Chinese. Reconstructed photos still require visual checking.

## 0.3.37 · build 50

- Add Traditional Chinese app copy with familiar Taiwanese terms throughout card selection, scanning, rescue, results, privacy, About and permission prompts. Follow macOS app language preferences and retain English fallback.
- Preserve recovery protocol strings, original filenames, read-only access and diagnostic/legal source text.

## 0.3.36 · build 49

- License future CardMe source and builds under GPL-3.0-only. Preserve the terms of earlier MIT-licensed distributions and all third-party licenses.
- Use dedicated CardMe telemetry infrastructure and link the public source repository from every website language.
- Prepare the public README with installation, recovery limits, read-only safety, privacy, contributing and redistribution guidance.

## 0.3.35 · build 48

- Rank independent fragment candidates on up to four CPU threads for saved-image searches. Merge exact scores and source-offset ties deterministically; preserve serial joins, read-only source access, cancellation and final JPEG validation.

- Restore unambiguous original filenames from current-image directory remnants; fall back to EXIF capture timestamps. Preserve JPEG bytes, handle name collisions without overwrites, and keep list selection and Quick View connected after renaming.

- Bundle native JPEG continuation ranking for harder fragmented photos, after existing fast rescue methods. Search current allocation-cluster boundaries across the saved image, prioritizing the observed photo region before the remainder.
- Try luminance ranking with lazy alternative paths, then whole-cluster color ranking. Observe the prefix before excluding saved ranges, reuse exact-byte decode checks, and retain strict full JPEG/thumbnail/preview validation.
- Batch full-cluster candidate filtering in the native checker while preserving shortlist order and final Python validation. Add a fresh-run benchmark that compares saved photo hashes only after rescue finishes.
- Complete quick two-part joins before harder reconstruction, and prefilter local probes in native batches without changing the Python ranking decisions. Interrupted pending candidates remain eligible on resume.
- Advance JPEG coding checkpoints and rank local probes natively, with state/score equivalence checks against Python. Keep complete-image decoding and thumbnail/preview checks before publication.
- Keep source access read-only through the existing descriptor, bounded search, cancellation, separate non-overwriting outputs and manual-review classification. No reference image, external compiler or recovery profile is required.

## 0.3.34 · build 47

- When local preview-guided continuation fails, search a bounded wider window around both the next source cluster and the current camera-preview tail anchor. Preserve already validated local choices and the shared 90-second limit.
- Reject poor short probes before the longer ranking decode, and use short coarse probes followed by longer bounded reranking after four validated joins to keep heavily fragmented photos within the existing deadline. Retain strict full-photo validation, current-source extent provenance, manual-review status and read-only source access. Retry older unresolved checkpoints once without overwriting saved photos.

## 0.3.33 · build 46

- When a marker-derived JPEG prefix cannot decode or extends past the declared primary length, retry by observing incremental coding state and preview luminance at cluster boundaries. Both attempts share the existing 90-second limit.
- Preserve original diagnostics, strict full-image/preview checks, source extent hashes, manual-review status and existing ambiguity refusals. Retry unresolved older checkpoints once without overwriting saved photos.

## 0.3.32 · build 45

- Add bounded camera-preview-guided multi-part JPEG reconstruction after existing two/three-part methods find no valid join. Preserve ambiguity refusals and source-byte provenance.
- Rank continuations using decoded JPEG block luminance; exclude other reconstructed source ranges only after checking their current hashes. Limit each attempt to 90 seconds and 16 joins.
- Save these candidates as needing review, with strict full decode and camera-preview agreement; do not count them as confirmed full-size rescues. Retry unresolved older checkpoints once without overwriting results.

## 0.3.31 · build 44

- Expand three-part JPEG tail-boundary search when nearby joins fail. Keep previously qualified nearby matches and the existing candidate budget, strict validation, cancellation and original-byte provenance.
- Allow a unique MPF indexed preview to validate a three-part photo when its embedded thumbnail disagrees. Require full preview matching and keep the result marked for review.
- Retry unresolved candidates once for the updated algorithm without overwriting recovered outputs. Source cards and images remain read only.

## 0.3.30 · build 43

- Try bounded three-part JPEG reconstruction, preserving source extents and requiring a unique decoded result that matches the camera preview.
- Search a bounded set of nearby positions inside unowned cluster runs, and allow a preview to share the primary tail allocation cluster.
- Reject clear mismatches with a reduced JPEG decode before full validation; bound comparison buffers for extreme aspect ratios.
- Rebuild fragmented indexed previews before retrying their full-size photo. Reuse endpoint hints from the existing scan.
- Keep original filename hints from checksum-valid directory remnants in recovery reports; never treat missing allocation chains as intact.
- Retry unresolved candidates once when the reconstruction algorithm changes. Keep source images read only and preserve existing results.

## 0.3.29 · build 42

- Automatically attempt bounded two-extent JPEG reconstruction after Deep Rescue finds surviving camera headers and previews. Preserve exact original-byte extents and separate review status.
- Validate joins against camera MPF lengths, strict JPEG decoding, and a larger preview comparison. Keep thumbnail disagreements marked for review.
- Show reconstruction progress and distinguish rebuilt full-size photos in the results list. Preserve source read-only access, cancellation, resume checkpoints, and existing outputs.

## 0.3.28 · build 41

- Use camera MPF child offsets and lengths to establish preview relationships across the saved card image, including visually ambiguous bursts.
- Prioritize unique validated index relationships, record their provenance, preserve originals and reuse unchanged existing metadata copies.

## 0.3.27 · build 40

- Compare nearby primary JPEG pixels when embedded thumbnails cannot identify a unique preview match.
- Create fallback thumbnails from the preview itself, preserve suspect-primary review status, and record the comparison used.

## 0.3.26 · build 39

- Pair nearby saved previews with camera JPEGs only when thumbnail comparisons give an unambiguous match.
- Save separate metadata copies with inferred orientation, camera, capture time and embedded thumbnail; preserve the original JPEG image stream and all rescued files.
- Record pairings and leave ambiguous candidates unchanged.

## 0.3.25 · build 38

- Recognize decoded large camera JPEGs whose camera EXIF dimensions match, so Deep Rescue reports full-size copies rather than counting every found photo as unclassified.
- Upgrade completed recovery reports from saved photos without rescanning the card image or rewriting recovered files; uncertain candidates remain for review.

## 0.3.24 · build 37

- Start the photo search automatically after creating a whole-card safety copy in the selected save folder.
- Keep saved-image selection visible in the card chooser and explain when a saved copy is ready but the search has not started.

## 0.3.23 · build 36

- Report anonymous scan totals, photos needing review and completed, failed or cancelled scan outcomes when usage statistics are enabled.
- Keep scan failures separate from unrecovered photos; earlier versions did not report scan totals.

## 0.3.22 · build 35

- Keep rescue results and actions visible while the photo list scrolls independently.
- Use a compact main window that grows only when the activity log is expanded.
- Give the Dock icon more breathing room.

## 0.3.21 · build 34

- Automatically analyze mounted exFAT cards for JPEG fragments using read-only card access, without a whole-card image or private recovery profile.
- Infer displaced allocation-table sectors, validate candidate photos against embedded thumbnails, and save generated byte extents beside the recovery report.
- Preserve readable-file fallback on other filesystems and stop on device or allocation changes.

## 0.3.20 · build 33

- Enlarge the shared recovery mark on one macOS icon tile for clearer Dock visibility.

## 0.3.19 · build 32

- Use a frameless recovery mark inside the app and website; retain the full macOS app icon.


## 0.3.18 · build 31

- Use the new double-arrow photo recovery icon in the app, website and repository page.
- Keep the recovery window as the primary launch scene, with Privacy available in Settings.


## 0.3.17 · build 30

- Add default-on usage statistics with a Privacy switch in Settings. No installation identifier, photos, filenames, paths or card details are sent.
- Report app opens, completed rescue result counts and coffee-link clicks in the background; network failures never block rescue. Coffee clicks do not indicate donations.
- Update privacy disclosures. No new startup popup.


Versions follow semantic versioning while CardMe remains a 0.x beta. Release dates use the maintainer’s local date.

## 0.3.16 — 2026-10-08

- First versioned release in the private CardMe repository.
- Add an MIT license for CardMe’s original code and include it in the app’s About page.
- Record version and build in VERSION.json, with checks against the built package and Xcode project.
- Add installation, safety, contribution, and release documentation, website source, and optional Ko-fi support.
- Exclude private card fingerprints, directory metadata, and investigation scripts from the repository source and app.

## 0.3.15 — 2026-10-08

- Earlier direct-download development release, subsequently signed and Apple notarized.
- Compact, stable card chooser with loading state and scrollable device list.
- Scanning, normal rescue, deeper JPEG searching, clear result categories, and optional support after recovery.

Earlier 0.3.x versions were development iterations, not separately published releases in this repository.

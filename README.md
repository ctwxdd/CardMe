# CardMe

<img src="website/dist/assets/cardme-mark.svg" width="88" height="74" alt="CardMe">

**Free photo recovery for memory cards, on your Mac.**

A faulty card adapter damaged my memory card and left me with photos I couldn’t open. Some of them were moments I could never photograph again. CardMe grew out of trying to get those photos back.

I’m sharing it so that others have a free option when the same thing happens. CardMe reads the card, saves recovered copies somewhere else, and tells you whether it found a full-size photo, a preview, or only a thumbnail. It won’t promise more than it recovered.

[Website](https://witty-meadow-00543f01e.6.azurestaticapps.net) · [繁體中文](https://witty-meadow-00543f01e.6.azurestaticapps.net/zh-hant) · [Download for Mac](https://witty-meadow-00543f01e.6.azurestaticapps.net) · [Releases](https://github.com/ctwxdd/CardMe/releases)

## Get started

Requires **macOS 14 or later and an Apple silicon Mac**. No account, subscription, or separately installed Python or recovery tools. The app supports English and Traditional Chinese and follows your macOS app language preference.

1. **Stop using the affected card.** Don’t take more photos or save files to it; new data can overwrite photos that are still recoverable.
2. Download the signed, Apple-notarized DMG from the [website](https://witty-meadow-00543f01e.6.azurestaticapps.net). Open it and drag **CardMe** into Applications.
3. Connect your card with a working reader. Open CardMe, choose the card, and scan it.
4. Click **Rescue to…** and choose a folder on your Mac or another fixed drive. Never save recovered photos back to the affected card.
5. Check the results. Use **↑ / ↓** to move through the list and **Space** for Quick Look. Full-size photos, previews, tiny thumbnails, and unsuccessful recovery are shown separately.

For deleted photos, a quick format, or photos that normal recovery cannot restore, try **Deep Rescue**. It makes a complete copy of the card before searching that copy. Prepare more free space than the card’s full capacity, plus room for recovered photos. Larger cards take longer to copy. An existing `card.img` can also be used.

The signed download may be older than the source on `main`. Check the [changelog](CHANGELOG.md) and release notes for the capabilities of a particular version. Development builds are not qualified public releases.

## What CardMe can do

The current source supports:

- Checking damaged JPEG files and recovering decoded photos or embedded previews and thumbnails.
- Searching for intact, contiguous JPEG data after deletion or a quick format.
- Bounded reconstruction of some fragmented camera JPEGs when enough allocation information or a matching camera preview survives. Uncertain candidates are saved for review.
- Restoring original filenames when surviving exFAT directory records provide an unambiguous name. Otherwise, using EXIF capture timestamps when available. Name collisions receive a suffix; existing files are never overwritten.
- Ranking harder fragmented JPEG candidates using the current safety copy and a surviving camera preview. Difficult candidates can take additional time; cancellation remains available and uncertain results require inspection.
- Keeping completed results when recovery is stopped, with checkpoint support for the image-search paths.

**RAW recovery, arbitrary fragmented-photo reconstruction, and overwritten data are currently not supported.** Recovery depends on what remains on the card.

Normal recovery first preserves complete readable JPEGs unchanged. On supported exFAT cards it also tries bounded original-byte fragment joins and preview-guided reconstruction directly through read-only card access, without a whole-card image. Surviving EXIF and indexed previews are retained when their original bytes can be assembled. PNG is only a fallback for a decoded image when a complete JPEG cannot be preserved, and is labelled as a PNG copy. Reconstructed candidates still need visual checking. Deep Rescue extends the search on a safety copy; neither mode generates missing image content or guarantees every pixel is correct.

A quick scan checks thumbnails, metadata, and image headers. It does not certify every pixel; full pixel checks are available in Details. See the [recovery flowcharts and step-by-step technical explanation](docs/RECOVERY_FLOW.md) for Normal and Deep Rescue, validation, fallbacks and limits. More implementation details are in [development documentation](docs/DEVELOPMENT.md).

## Your card stays read only

CardMe does not write to the source card, format it, repair it, delete its files, or save recovered photos back onto it. It also treats saved card images as read only. Output destinations are checked separately, and existing results are not overwritten.

For whole-card access, macOS supplies a read-only file descriptor through `authopen`. The bundled imaging tool receives that descriptor; neither CardMe nor the tool runs as root. CardMe checks device identity and refuses unsafe output destinations.

This is a software safety boundary, **not a hardware write blocker**. macOS, other apps, or a faulty reader can still affect the card. Read-only access also cannot stop failing hardware from deteriorating during reads. If the card has physical damage or repeatedly disconnects, stop and consider a professional recovery service.

## Privacy

Photo recovery runs on your Mac. Photos, filenames, paths, photo metadata, and card identifiers are not uploaded.

Anonymous usage statistics are **on by default** and can be disabled in **CardMe → Settings → Privacy**. They include app launches, app version, scan and recovery counts, outcomes, and clicks on the optional support link. There is no installation identifier. Launches are not unique users, and a support-link click does not mean someone donated.

See [privacy details](docs/PRIVACY.md) for the complete event list, retention, cancellation, and hosting information.

## Build from source

Requires Apple silicon, macOS 14+, Xcode Command Line Tools, and a build-host Python 3. Users of the packaged app do not need these tools.

```sh
git clone https://github.com/ctwxdd/CardMe.git
cd CardMe
python3 scripts/build-runtime.py
python3 scripts/build.py --direct-download --dmg
```

Outputs are `build/CardMe.app` and `build/CardMe.dmg`. Local builds are ad-hoc signed and not notarized. See [development and testing](docs/DEVELOPMENT.md) and [release instructions](docs/RELEASING.md) for focused checks, signing, notarization, and corresponding source.

The internal Xcode project and executable retain the name `CardRescue` for compatibility.

## Contributing and reporting issues

Bug reports and small, focused improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Please **don’t upload personal photos, card images, private recovery logs, credentials, or device identifiers** to public issues. Start with the CardMe version, macOS version, Mac model, and a description of what happened. Use synthetic photos for reproducible examples.

Recovery changes must preserve read-only source access, cancellation, output safety, and clear recovery classifications. Tests use disposable fixtures; never test source writes on a real memory card.

## License, copyright, and redistribution

Copyright © 2026 **CHUN-TING WU**. CardMe’s original application, engine, and website are licensed under **[GNU GPL version 3 only](LICENSE)** (`GPL-3.0-only`); see the [copyright notice](NOTICE). You keep ownership of your photos; this license covers the software, not recovered photographs.

You may use, study, modify, and redistribute CardMe, including commercially, under the GPL. When distributing the software or a modified version, preserve the copyright and license notices, identify modifications, and provide the corresponding source as required by the GPL. Modified and combined works covered by the GPL must retain its terms. The license does not grant rights to imply that a fork is an official CardMe release or endorsed by its author.

Third-party components keep their own licenses: GNU ddrescue is GPL-2.0-or-later; CPython, Pillow, and the bundled codecs have their upstream terms. Their notices and required source materials must remain with redistributed builds. See [third-party notices](THIRD_PARTY_NOTICES.md) and [licensing details](docs/LICENSING.md).

Earlier releases distributed under MIT retain those terms. This license change applies to the current source and future builds; it does not revoke previously granted licenses.

## Warranty and recovery disclaimer

CardMe is provided **“as is,” without warranty**, to the extent permitted by applicable law. Recovery may fail or produce incomplete or incorrect results. Signing and Apple notarization do not guarantee recovery, image integrity, or hardware safety.

The warranty disclaimer and limitation of liability are set out in sections 15–17 of the [GPL](LICENSE). This README summarizes them; it does not add restrictions or override the license or applicable law.

## Support

CardMe is free to use. No payment is required to recover or save photos.

If it helped you get important photos back, you’re welcome to [buy me a coffee ☕️](https://ko-fi.com/alittleseal). Thank you for your support.

The optional anonymous statistics service is maintained in [ControlPlane](ControlPlane/README.md), with dedicated CardMe infrastructure and administrator access. It is independent of the recovery engine and never receives photos.

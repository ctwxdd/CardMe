# Releasing CardMe

VERSION.json is the standalone builder’s version source. Update its semantic version and increasing build number, matching MARKETING_VERSION and CURRENT_PROJECT_VERSION in CardRescue.xcodeproj. Update CHANGELOG.md. Never reuse a version tag for changed binaries.

Build on Apple silicon with the audited runtime:

```sh
python3 scripts/build-runtime.py
python3 scripts/build.py --direct-download --dmg \
  --sign-identity 'Developer ID Application: YOUR NAME (TEAMID)' \
  --build-dir /path/to/release
python3 tests/direct-package-check.py --build-dir /path/to/release
xcrun notarytool submit /path/to/release/CardMe.dmg --keychain-profile YOUR_PROFILE --wait
xcrun stapler staple /path/to/release/CardMe.dmg
xcrun stapler validate /path/to/release/CardMe.dmg
spctl --assess --type open --context context:primary-signature --verbose=2 /path/to/release/CardMe.dmg
```

Only an Accepted notarization result permits publication. Verify the signed app with `codesign --verify --deep --strict` and `spctl --assess --type execute`. Test the relocated Python/Pillow runtime and source-safety fixtures. Check notices and included corresponding source with the package test. Signing and notarization do not replace these checks.

Tag the checked source commit `vX.Y.Z`. Publish a GitHub prerelease in `ctwxdd/CardMe` while the app is 0.x beta, attaching the signed, notarized, stapled `CardMe-X.Y.Z.dmg` and its SHA-256 file. Release notes include requirements, installation, usage, limitations, license/source information, and actual validation. Download the published file and compare its digest; check Gatekeeper again. Keep credentials and DMGs out of the source repository.

For future GPL-3.0-only builds, publish the matching complete corresponding source alongside the DMG. The release checkout must be clean, including submodules if introduced, so the tagged source represents every packaged code and build input. Create and checksum the archive from that exact tag:

```sh
git archive --format=tar.gz --prefix=CardMe-X.Y.Z/ \
  --output=/path/to/release/CardMe-X.Y.Z-source.tar.gz vX.Y.Z
shasum -a 256 /path/to/release/CardMe-X.Y.Z-source.tar.gz
```

Attach this source archive and checksum to the release. Check that it includes the matching application, engine, build/install scripts, notices, disclosed patches, and pinned dependency inputs. A private release or a moving branch is not a public source offer. Before publishing a GPL binary on the website, put a clear link to the corresponding freely accessible source archive beside its download and verify both downloads without authentication. Preserve third-party notices and source materials inside the app. Do not replace or relabel an existing MIT-licensed binary as GPL. See [licensing details](LICENSING.md).

Private GitHub release links must not be used as public download links. CardMe now has its own Azure Static Web App (resource group `CardMe`, app `CardMe`), deployed from this repository by `.github/workflows/website.yml`. Site files are rooted at `website/dist`; downloads link directly to release assets in the public `ctwxdd/CardMe` repository, alongside their tagged source. `ctwxdd/CardMe-releases` retains historical downloads only; do not publish new versions there. Update the generator download URL and localized public version only after signing, notarization, and checksum verification. Pickology deployments and downloads are independent.

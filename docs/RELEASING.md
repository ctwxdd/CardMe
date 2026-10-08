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

Tag the checked source commit `vX.Y.Z`. Publish a GitHub prerelease (private while the repository is private) while the app is 0.x beta, attaching the signed, notarized, stapled `CardMe-X.Y.Z.dmg` and its SHA-256 file. Release notes include requirements, installation, usage, limitations, license/source information, and actual validation. Download the published file and compare its digest; check Gatekeeper again. Keep credentials and DMGs out of the source repository.

Private GitHub release links must not be used as public download links. The product website is https://getpickology.com/cardme. Its Azure deployment belongs to the Pickology website repository; preserve both products’ downloads. A CardMe release does not authorize replacing the Pickology DMG. Update the website version and CardMe download separately when publishing a website deployment.

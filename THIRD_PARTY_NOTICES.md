# CardMe third-party software

CardMe’s original application, engine, and website code are MIT licensed; see LICENSE and ThirdPartyLicenses/CardMe-MIT.txt. Third-party components retain their own licenses.

Free distribution does not remove license obligations. The app includes the following notices and source materials in Contents/Resources. No additional installation is necessary.

- GNU ddrescue 1.30 (direct-download edition only), copyright 2004–2026 Antonio Diaz Diaz; GPL-2.0-or-later. Runs as a separate executable with the included CardRescue input-descriptor patch (October 7, 2026), also GPL-2.0-or-later. Full license and authors: ThirdPartyLicenses/ddrescue-GPL-2.0.txt and ddrescue-AUTHORS.txt. Complete corresponding source and build instructions: ThirdPartySources/ddrescue-1.30.tar.lz , ddrescue-BUILD.md and input-fd.patch. Recipients may copy, modify and redistribute ddrescue under its GPL terms, without additional restrictions.
- CPython 3.12: Python Software Foundation and historical contributor licenses. See ThirdPartyLicenses/Python-LICENSE.txt and python/lib/python3.12/LICENSE.txt. Preserve the copyright and license notices when redistributing.
- Pillow and bundled codec libraries: see ThirdPartyLicenses/Pillow-and-codecs-LICENSE.txt and python/lib/python3.12/site-packages/pillow-*.dist-info/licenses/LICENSE. This combined upstream license file includes Pillow and the native codec/font dependencies in the wheel; preserve it in full.
- Apple system frameworks and authopen are supplied by macOS; CardMe does not redistribute them.

The source archive and notices must remain with the distributed direct-download app. Do not impose an EULA restriction on recipients' rights to ddrescue. Developer ID signing and notarization are separate from these redistribution requirements.

The packaged CPython is built from the included Python 3.12.14 source with GNU readline and other unnecessary optional modules disabled. Its external libraries come from macOS; no GNU readline binary is redistributed. CPython source, including notices for its embedded code, is included at ThirdPartySources/Python-3.12.14.tar.xz, with Python-BUILD.md and build-runtime.py. The builder rejects the prior readline-containing runtime and checks non-system dynamic dependencies.

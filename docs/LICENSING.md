# CardMe licensing

## Current original code

Copyright (c) 2026 CHUN-TING WU.

CardMe's original application, recovery engine, build/test scripts, documentation, and website are licensed under the **GNU General Public License version 3 only** (`GPL-3.0-only`). The complete terms are in [LICENSE](../LICENSE).

GPL is an open-source license and permits commercial use and paid redistribution. It does not transfer ownership of the original copyright. It requires preservation of the applicable notices and corresponding source when distributing covered software. Modified works must carry notices of changes and relevant dates under the GPL. Using a modified program privately does not by itself require publishing it.

The license cannot stop someone from creating a fork or charging for GPL-compliant copies. It does not let them remove your copyright notices or treat your original work as their own. README summaries are guidance, not additional license conditions.

## Names and attribution

The software license grants copyright and relevant patent permissions under its terms; it does not grant trademark rights or permission to claim author endorsement. You may accurately refer to CardMe and identify the upstream project. Make it clear when a distributed build is modified or unofficial.

Recovered photographs remain governed by their owners' rights, not by CardMe's software license.

## Earlier distributions

Earlier copies distributed under MIT remain under that license. The historical text is preserved at [MIT-previous.txt](licenses/MIT-previous.txt). Changing the repository's visibility or the current license does not revoke rights already granted to recipients.

The signed public 0.3.23 DMG remains a separate, unchanged artifact. Its included license governs that distribution. Future GPL releases must include the GPL notices and the matching corresponding source.

## First public source publication

The private repository's history contains complete source snapshots with an MIT license. Making that history public also exposes those snapshots and their license notices. A GPL license at the newest commit does not erase them.

If the first public source release is intended to be GPL-only, publish a clean snapshot of the current GPL tree and preserve the existing repository/history privately. Do not rewrite or delete private history merely to hide old notices. A source archive contains the current files without Git history; the project owner must choose the public repository and release history before changing visibility.

## Third-party components

[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) identifies the bundled components and source materials. Their existing licenses are not replaced by CardMe's GPL notice.

- GNU ddrescue and CardMe's input-descriptor patch remain GPL-2.0-or-later. ddrescue runs as a separate executable. Preserve its complete corresponding source, patch, license, authors, and build instructions.
- CPython retains the PSF and historical licenses. Preserve its notices and the bundled source/build materials.
- Pillow and its bundled codecs retain their upstream licenses and complete combined notices.
- Apple system frameworks and `authopen` are supplied by macOS and are not redistributed by CardMe.

Do not impose extra restrictions on recipients' rights to these components.

## Future binary releases

A GPL binary release must provide matching complete corresponding source through a GPL-compliant method. This project uses a downloadable source archive made from the exact release tag, offered alongside the binary. Include the source needed to build and install the released program, scripts, disclosed patches, and the checked dependency inputs. A link to a moving branch or a private repository is insufficient for public redistribution.

See [release instructions](RELEASING.md). License and package checks are necessary, but they do not prove that public source downloads are accessible; verify them before publishing a binary.

## Disclaimer

The software is provided as is. The full warranty disclaimer, limitation of liability, and their interpretation are in sections 15–17 of [GPLv3](../LICENSE), subject to applicable law. This document does not create additional conditions or limit rights that the law does not allow to be limited.

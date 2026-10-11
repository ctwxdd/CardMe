# Next steps for fragmented JPEG recovery

Research checked on 2026-10-10. The papers' metadata and abstracts were verified through Crossref and OpenAlex. Publisher full text was unavailable in this run. The proposals below are adaptations to investigate, not claims of reproducing the published algorithms.

## Evidence from the current test image

The remaining 46 candidate headers are baseline JPEG (SOF0). None enables a primary-image restart interval (DRI); markers inside APP thumbnails must not be mistaken for primary-image markers. Their DHT segments form two groups: 44 use one Huffman table set, and two use another. A common table set constrains decoding but does not identify the owning photograph.

A read-only diagnostic evaluator used pre-format allocation metadata solely to check reference bytes, without exporting photos or passing old allocation positions into recovery:

- 39 candidates have a complete primary JPEG that strictly decodes in the reference order. All of those reference bytes still exist unchanged in the current image.
- Six old file chains are shorter than their JPEG MPF primary-size declarations. Reading those old chains does not yield a complete JPEG. They cannot supply a reliable whole-photo reference hash.
- One candidate has no original file-head mapping.

This establishes 39 useful reference hashes, not proof that every unresolved candidate has a known correct image. A strictly decoded, byte-identical reference can itself contain damage predating the safety copy; it is not a guarantee of photographic fidelity.

Existing first-failure classification assigns overlapping findings in this order: ten prefix-cut overshoots, four preview/thumbnail mismatches, fifteen cases with more than three physical runs, fourteen tail estimates outside the current four-boundary window, and three not isolated. The old allocation map explains the misses after the fact; none of these true boundaries may be supplied to the production search.

## Applicable research

1. Pal, Sencar and Memon, **Detecting file fragmentation point using sequential hypothesis testing** (2008), [DOI](https://doi.org/10.1016/j.diin.2008.05.015). The abstract describes serial comparisons of adjacent blocks to locate a fragmentation point. CardMe should stop treating the eventual marker error as the exact original prefix cut. Investigate earlier boundaries using entropy validity and decoded block continuity, with the surviving preview as additional evidence.
2. Sencar and Memon, **Identification and recovery of JPEG files with missing fragments** (2009), [DOI](https://doi.org/10.1016/j.diin.2009.06.007). The abstract proposes bit-sequence matching to identify fragments produced with the same Huffman tables, and pseudoheaders for standalone fragments. Here headers survive: use their real DHT, sampling and frame parameters to filter candidate joins. Do not create replacement image bytes or assume common encoding means common ownership.
3. Pal et al., **Automated reassembly of file fragmented images using greedy algorithms** (2006), [DOI](https://doi.org/10.1109/TIP.2005.863054). The abstract formulates reconstruction as a graph ordering problem and evaluates greedy heuristics. A bounded search retaining several candidate paths is a CardMe proposal for four or more runs; it must preserve competing hypotheses until final validation and reject unresolved ambiguity.
4. Garfinkel, **Carving contiguous and fragmented files with fast object validation** (2007), [DOI](https://doi.org/10.1016/j.diin.2007.06.017). Its abstract supports a multi-tier validator that cheaply discards candidates before expensive decoding. Extend the existing marker and reduced-preview checks with baseline entropy/MCU constraints before widening the search.

Karresand and Shahmehri, **Reassembly of Fragmented JPEG Images Containing Restart Markers** (2008), [DOI](https://doi.org/10.1109/EC2ND.2008.10), depends on restart markers. It is not a direct solution for these 46 primary streams because all have DRI disabled.

## Implementation and qualification order

1. Establish a deterministic private benchmark covering all 46, with the 39 validated hashes separated from seven cases lacking a complete reference. Give candidate search only the current image and its current scan inventory; provide reference hashes only to the evaluator. No old chains, true cuts or filenames enter search or ranking.
2. Implement baseline JPEG entropy/MCU validation and boundary observations. Reject impossible AC runs, coding transitions and frame counts cheaply; record what is observed rather than calling parser failure the true cut. A partial decode used for ranking is never a saved success.
3. Use those observations to rank earlier prefix and broader tail boundaries. Reuse source buffers and checkpoints; cap reads, candidates, memory and paths so failure remains bounded and cancellable.
4. Extend the path search beyond three extents only after boundary ranking is measured. Treat preview matches as evidence, not proof; require exact source provenance, expected frame structure, full strict decode and final preview checks. Preserve ambiguous candidates as unresolved.

Track exact reference matches, wrong-but-decodable outputs, ambiguous results, bytes read, elapsed time and cancellation. Preserve the six previously qualified reconstruction samples as regressions. New methods must improve this benchmark before being advertised as recovery support.

The initial literature and reference-validation phase added no recovery feature to version 0.3.30 and saved no reconstructed photo.


## Bounded current-image experiments

The subsequent experiment searched the original 46 unresolved current-scan candidates. Historical allocation positions, true cut points and filenames were excluded from search. The 39 reference hashes were evaluation inputs only.

| Experiment | Coverage | Result |
| --- | --- | --- |
| Broader forward tail boundaries, existing 8,192-join cap and a private 60-second per-candidate deadline | 46 | One new exact reference match; 36 without a match; nine timed out. Total 995 seconds. |
| Conservative occupancy hints, broader tails and a 1,024-join cap | 46 | No new matches; two timed out. Total 763 seconds. |
| Baseline Huffman/MCU observer | 46 | Eight earlier coding-failure observations, by 1–36 clusters. These are hypotheses, not proven cuts. |
| Earlier coding observations with the existing three-extent validator | Eight | No new matches. |
| Luna: prefix shifts 0–4 with a ten-boundary tail window | Eight of 38 unresolved candidates | No new matches; remaining 30 not completed. A further sweep without optional occupancy hints reached its 260-second budget before one case completed. |
| Earlier coding observations and tail search in both directions | Eight | No new matches; three timed out. |
| Four-extent gap-pair prototype | Two | Both timed out; no new match. This does not rule out four-extent recovery. |

The successful improvement is narrow: preserve an already qualified nearby three-extent join; if that window finds nothing, consider later logical tail boundaries up to the MPF preview anchor. Keep the original global join budget and refuse a result if the expanded search exhausts its budget before uniqueness is established. Algorithm version 3 retries prior unresolved candidates once. The synthetic regression places the true tail six clusters beyond its inferred boundary and verifies exact bytes, budget refusal, cancellation and short-read handling.

Only the proven tail-search change is included in source version 0.3.31. The coding observer, speculative earlier cuts and four-extent search remain private experiments. Recovery increases from the prior 90 diagnostic matches to 91, leaving 45 unresolved. Timeout is a search limit, not evidence that source bytes are gone. A matching historical hash verifies byte identity to that reference, not absence of damage that already existed before formatting.

Qualification preserved all six previous source-only sample hashes and separately reproduced the new reference hash from current bytes. The new match uses the accumulated current recovery inventory as occupancy evidence; it is not a guarantee of identical results with an earlier, smaller inventory. The synthetic widened-tail fixture fails with the original four-boundary search and passes with version 3. No fresh 128-GB end-to-end app run or new signed DMG was produced in this phase.


## Follow-up against the original answers

A post-hoc audit of the 45 cases remaining after the first gain found 38 byte-intact references and seven without complete references. It replayed occupancy from current recovery reports rather than an instrumented live trace. Of the 38, 15 need more than three physical runs; 23 have three runs. In the three-run group, ten marker-derived prefix cuts overshoot, one lacks a thumbnail-matching preview, and twelve have the correct prefix and a unique preview. Overlapping blockers in those twelve include seven true tail boundaries before the forward search start, two middle ranges masked as occupied, two interior starts outside the generated edge/top-64 set, and two otherwise eligible joins hitting the trial deadline. These observations diagnose candidate generation, not missing source bytes; old positions remain excluded from production.

The three-run preview mismatch then produced a second exact reference match using current bytes only. Version 0.3.31 now mirrors the existing two-part policy: a single structurally matching MPF child may validate the full three-part JPEG when its embedded thumbnail disagrees, but full preview matching remains required and the output is marked for review. Duplicate structural candidates fail closed. Four focused trials produced one new match; the others did not match.

The diagnostic total is now 92, with 44 unresolved: 37 still have complete reference bytes demonstrably present, and seven remain unclassified for full-byte survival. No confirmed byte-loss case was established. Wider search helps, but cannot reach paths that the current model never generates. Earlier tail candidates, occupancy ownership and four-or-more-part paths remain separate improvements to qualify.

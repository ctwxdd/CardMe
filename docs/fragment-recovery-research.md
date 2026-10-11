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

This research does not add recovery features to version 0.3.30 and does not count any new rescued photo. No image was written, repaired or reconstructed to disk during these diagnostic checks.

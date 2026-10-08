#!/usr/bin/env python3
"""Local evidence-based hypothesis ranking. Scores prioritize work, never certify repairs.
Input: JSON list with id, quality, verified_recipe, bytes, extents, and optional
source_hash_ok, decode_ok, thumbnail_difference. Unknown evidence is not a pass.
"""
import argparse, json

QUALITY = {'full_resolution': 3, 'camera_preview': 2, 'thumbnail_only': 1}

def rank(candidates):
    ranked = []
    for candidate in candidates:
        reasons = []
        blocked = candidate.get('source_hash_ok') is False or candidate.get('decode_ok') is False
        difference = candidate.get('thumbnail_difference')
        if difference is not None and difference > 5:
            blocked = True
            reasons.append('Thumbnail mismatch exceeds verified-repair threshold.')
        if blocked:
            reasons.append('Failed evidence gate; reject candidate.')
        verified = candidate.get('verified_recipe') is True
        quality = QUALITY.get(candidate.get('quality'), 0)
        reasons.append('Verified recipe for this snapshot.' if verified else 'Unverified hypothesis; requires validation and review.')
        # ponytail: transparent fixed rules, replace weights only with measured recovery evidence.
        score = (100 if verified else 0) + 10 * quality
        score -= min(5, max(0, candidate.get('bytes', 0)) / 10_000_000)
        score -= min(5, max(0, candidate.get('extents', 0)) / 100)
        ranked.append({**candidate, 'score': round(score, 3), 'decision': 'reject' if blocked else 'validate' if verified else 'review', 'reasons': reasons})
    return sorted(ranked, key=lambda r: (r['decision'] != 'reject', r['score']), reverse=True)

def self_test():
    items = rank([{'id': 'bad', 'quality': 'full_resolution', 'verified_recipe': True, 'decode_ok': False},
                  {'id': 'guess', 'quality': 'full_resolution'},
                  {'id': 'preview', 'quality': 'camera_preview', 'verified_recipe': True},
                  {'id': 'full', 'quality': 'full_resolution', 'verified_recipe': True}])
    assert [r['id'] for r in items] == ['full', 'preview', 'guess', 'bad']
    assert items[2]['decision'] == 'review' and items[3]['decision'] == 'reject'
    assert rank([{'thumbnail_difference': 30}])[0]['decision'] == 'reject'
    print('Decision model self-check passed.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidates', nargs='?')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.candidates:
        with open(args.candidates) as source:
            print(json.dumps(rank(json.load(source)), indent=2))
    else:
        parser.error('Provide a candidate JSON file or --self-test.')

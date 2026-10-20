#!/usr/bin/env python3
"""Audit actual Unity scene evaluation output. No simulated scores or human win-rate claims."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

LEVELS = ('Easy', 'Medium', 'Hard')
SEEDS = (17, 4016, 9001)


def summarize(report):
    if report.get('schema') != 1 or report.get('passed') is not True:
        raise ValueError('A complete passing schema-1 Unity report is required')
    for key in ('modelSha256', 'gameplayHash'):
        if len(report.get(key, '')) != 64 or any(c not in '0123456789abcdef' for c in report[key]):
            raise ValueError('Missing SHA256 provenance: ' + key)
    rows = report.get('cases', [])
    if len(rows) != 9 or {(r['difficulty'], r['seed']) for r in rows} != {(d, s) for d in LEVELS for s in SEEDS}:
        raise ValueError('Need exactly three distinct fixed seeds per difficulty')
    totals = []
    for r in rows:
        if r.get('near') != 'KOR' or r.get('far') != 'JPN':
            raise ValueError('This evaluation cohort requires KOR vs JPN')
        for key in ('points', 'nearPoints', 'farPoints', 'nearHits', 'aiHits', 'aiAttempts', 'aiRejected', 'humanServes', 'aiServes', 'learnedDecisions'):
            if type(r.get(key)) is not int or r[key] < 0:
                raise ValueError('Invalid count: ' + key)
        if r['points'] < 8 or r['points'] != r['nearPoints'] + r['farPoints'] or r['aiAttempts'] != r['aiHits'] + r['aiRejected']:
            raise ValueError('Point/attempt accounting disagrees')
        actions = r.get('actions', [])
        if len(actions) != 6 or any(type(n) is not int or n < 0 for n in actions) or sum(actions) != r['learnedDecisions']:
            raise ValueError('Learned action accounting disagrees')
        if min(r['nearHits'], r['aiHits'], r['learnedDecisions']) <= 0 or min(r['humanServes'], r['aiServes']) < 4:
            raise ValueError('Both service games, learned decisions and actual returns must occur')
    for level in LEVELS:
        cases = [r for r in rows if r['difficulty'] == level]
        total = {key: sum(r[key] for r in cases) for key in ('points', 'farPoints', 'aiHits', 'aiAttempts', 'aiRejected', 'learnedDecisions')}
        total.update(difficulty=level, cases=len(cases), actions=[sum(r['actions'][i] for r in cases) for i in range(6)])
        total['scriptedPointShare'] = total['farPoints'] / total['points']
        total['acceptedAttemptShare'] = total['aiHits'] / total['aiAttempts']
        totals.append(total)
    return dict(schema=1, scope=report['scope'], modelSha256=report['modelSha256'], gameplayHash=report['gameplayHash'], results=totals,
                limitations=['Nine short KOR/JPN scene cases against a scripted fixture; not human win rate.',
                             'Points within each case are correlated; no independent-sample confidence claim.',
                             'Difficulty ordering is measured, never forced by changing scores or tuning to these seeds.',
                             'PPO selects shot placement only; no movement/serve/skill end-to-end training.',
                             'Unity frame timing varies; fixed seeds do not promise bit-identical point totals.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--game-commit', required=True)
    args = parser.parse_args()
    if len(args.game_commit) != 40 or any(c not in '0123456789abcdef' for c in args.game_commit):
        parser.error('--game-commit must be the full tested source SHA')
    data = summarize(json.loads(args.report.read_text()))
    data.update(gameCommit=args.game_commit, inputSha256=hashlib.sha256(args.report.read_bytes()).hexdigest())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'match-evaluation.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    with (args.out/'match-evaluation.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['difficulty', 'cases', 'points', 'ai_points', 'scripted_point_share', 'ai_hits', 'ai_rejected', 'accepted_attempt_share', *['action_'+str(i) for i in range(6)]])
        for row in data['results']:
            writer.writerow([row['difficulty'], row['cases'], row['points'], row['farPoints'], row['scriptedPointShare'], row['aiHits'], row['aiRejected'], row['acceptedAttemptShare'], *row['actions']])
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

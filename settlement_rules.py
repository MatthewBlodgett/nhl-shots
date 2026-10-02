"""Conservative bookmaker settlement gate, separate from official SOG grading."""
import json
from pathlib import Path

REGISTRY = Path(__file__).with_name('sportsbook_rules.json')


def assess(quote, actual, now=None):
    registry = json.loads(REGISTRY.read_text())
    rule = registry['books'].get(quote['book'])
    reasons = []
    if rule is None:
        reasons.append('book_not_reviewed')
    else:
        if rule['status'] != 'verified': reasons.append('rules_incomplete')
        if quote.get('jurisdiction') != rule.get('jurisdiction'): reasons.append('jurisdiction_unknown_or_unmatched')
    if actual is None: reasons.append('participation_or_stat_missing')
    return {'status':'unresolved' if reasons else 'supported', 'reasons':reasons,
            'rule_revision':registry['revision'], 'book':quote['book'],
            'warning':'Official SOG result is a statistical paper outcome, not an executable settlement.'}

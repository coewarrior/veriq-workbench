"""Pure active UI case projection, also embedded in the no-install client."""

def is_superseded(case):
    """Only explicit, unexecuted aggregates are inactive; observed verdicts win."""
    return bool(case.get('superseded_by')) and case.get('status') in {'not_run', 'blocked'} and not (
        case.get('executed_at') or any(p.get('status') not in {'not_run', 'blocked'}
                                     for p in case.get('checkpoints', [])))


def active_cases(cases):
    return [case for case in cases if not is_superseded(case)]

"""Read-only report views shared only by one local report-processing batch."""


def _stamp(path):
    try:
        value = path.stat()
    except FileNotFoundError:
        return None
    return value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


class _ReportBatch:
    """Never retain this on a service; public batches also check file changes.

    Normalized analysis views and prior-failure views deliberately stay separate.
    Integration records are always read live, including human lifecycle decisions.
    """
    def __init__(self, store):
        self.store = store
        self._views = {}
        self._reports = {}

    def report(self, owner, pid, rid, *, normalize=False):
        from . import ui_report_corrections
        root = self.store.project_dir(owner, pid)
        location = root / 'analyses' / rid
        paths = [location / name for name in (
            'report.json', 'case-corrections.json', 'fixture-supplements.json')]
        from .ui_asset_withdrawals import path as withdrawal_path, report_view
        paths.append(withdrawal_path(self.store, owner))
        report_key = owner, pid, rid
        report_stamp = _stamp(paths[0])
        saved = self._reports.get(report_key)
        if saved and saved[0] == report_stamp:
            report = saved[1]
        else:
            report = self.store._read(paths[0])
            if report_stamp == _stamp(paths[0]):
                self._reports[report_key] = report_stamp, report
            else:
                self._reports.pop(report_key, None)
        # Derive normalization dependencies from the current report, never an
        # old view: a rewrite can remove a source that has since been deleted.
        projects = {pid}
        if normalize and report.get('project_id'):
            sources = {link['source_project_id'] for link in report.get('regression_links', [])
                       if link.get('source_project_id')}
            if sources:
                projects.update(sources | {report['project_id']})
        def stamps():
            # Resolve owned paths on every access; only body parsing is reused.
            metadata = [self.store.project_dir(owner, project_id) / 'metadata.json'
                        for project_id in sorted(projects)] if normalize else []
            return tuple(_stamp(path) for path in [*paths, *metadata])
        before = stamps()
        key = owner, pid, rid, normalize
        previous = self._views.get(key)
        if previous and previous[0] == before and before[0] == report_stamp:
            return previous[1]
        effective = ui_report_corrections.apply(report,
            ui_report_corrections.load(self.store, owner, pid, rid),
            **({'store': self.store, 'owner': owner} if normalize else {}))
        effective = report_view(self.store, owner, effective)
        if before == stamps() and before[0] == report_stamp:
            self._views[key] = before, effective
        else:
            self._views.pop(key, None)
        return effective

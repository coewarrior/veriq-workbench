"""Re-render saved HTML only. Run in the web container after upgrading its image."""
import hashlib
import html
import json
import os
import re
from pathlib import Path

from api_test_tool.reporting import write_report
from api_test_tool.task_reports import render_task_report


def refresh(root=Path('/data')):
    execution_count = analysis_count = defect_count = 0
    for result_file in root.glob('sessions/*/projects/*/runs/*/result.json'):
        bundle_file = result_file.with_name('bundle.json')
        if not bundle_file.exists():
            continue
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (result_file, bundle_file)}
        result, bundle = json.loads(result_file.read_text()), json.loads(bundle_file.read_text())
        target = result_file.with_name('index.html')
        titles = {}
        if target.exists():
            for card in re.findall(r'<article class="case".*?</article>', target.read_text(), re.S):
                cid, title = re.search(r'<code>(.*?)</code>', card, re.S), re.search(r'<h3>(.*?)</h3>', card, re.S)
                if cid and title:
                    titles[html.unescape(cid[1])] = html.unescape(title[1])
        temporary = target.with_suffix('.pending.html')
        write_report(result, bundle, temporary, display_titles=titles)
        os.replace(temporary, target)
        assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
        defect_count += target.read_text().count('class="copy-defect"')
        execution_count += 1
    for data in root.glob('sessions/*/projects/*/analyses/*/report.json'):
        before = hashlib.sha256(data.read_bytes()).hexdigest()
        target = data.with_name('index.html')
        temporary = target.with_suffix('.pending.html')
        temporary.write_text(render_task_report(json.loads(data.read_text())), encoding='utf-8')
        os.replace(temporary, target)
        assert hashlib.sha256(data.read_bytes()).hexdigest() == before
        analysis_count += 1
    print(json.dumps(dict(execution_reports=execution_count, analysis_reports=analysis_count,
                          defect_drafts=defect_count, evidence_unchanged=True)))


if __name__ == '__main__':
    refresh()

"""Invoke the real platform planner; never reimplement its decisions for a benchmark."""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api_test_tool import test_checkpoints  # noqa: E402


def evaluate(scoped):
    points = [dict(id=key, title=key, kind='browser', status='not_run',
                   question_ids=['unknown-policy'] if scoped and key == 'policy' else [],
                   dependencies=[], depends_on=[])
              for key in ('feedback', 'original-intact', 'policy')]
    case = dict(case_id='duplicate-upload', checkpoints=points, dependencies=[],
                question_ids=[] if scoped else ['unknown-policy'])
    record = dict(cases=[case], dependency_checks={}, requirement_design={
        'questions': [dict(id='unknown-policy', title='重复文件处理策略', status='open')]})
    return dict(input=copy.deepcopy(record), output=test_checkpoints.plan(record))


if __name__ == '__main__':
    source = Path(test_checkpoints.__file__)
    print(json.dumps(dict(source=str(source.relative_to(ROOT)),
                          sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                          baseline=evaluate(False), scoped=evaluate(True)), ensure_ascii=False))

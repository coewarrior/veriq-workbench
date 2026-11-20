"""Optional executor-reported measurements for one UI round, never test verdicts."""
from datetime import datetime
import re

from .execution import Redactor


TEXT_LIMITS = {'experiment_id': 128, 'variant': 128, 'model': 128,
               'reasoning_effort': 64, 'model_source_detail': 500}
MODEL_SOURCES = {'requested', 'reported', 'verified'}
TIMES = ('started_at', 'execution_started_at', 'execution_finished_at')
COUNTERS = ('tool_calls', 'tool_errors')
FIELDS = {*TEXT_LIMITS, 'model_source', *TIMES, *COUNTERS}
ISO_TIME = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$')


def report_timing(report):
    """Use a recorded execution window, never saving/editing/publication times."""
    if report.get('report_type') == 'total':
        return None
    experiment = report.get('ui_snapshot', {}).get('experiment') or {}
    start, finish = (experiment.get(key) for key in ('execution_started_at', 'execution_finished_at'))
    try:
        if not all(isinstance(value, str) and ISO_TIME.fullmatch(value) for value in (start, finish)):
            return None
        first, last = (datetime.fromisoformat(value.replace('Z', '+00:00')) for value in (start, finish))
        if last < first:
            return None
    except (TypeError, ValueError):
        return None
    return {'startedAt': start, 'finishedAt': finish, 'label': '执行窗口历时',
            'basis': '执行端记录的开始至结束，包含期间等待；不代表连续操作或模型推理耗时'}


def merge(previous, patch):
    """Omitted fields persist; explicit null removes a value without guessing it."""
    if not isinstance(patch, dict) or set(patch) - FIELDS:
        raise ValueError('experiment 仅支持实验组、模型来源、时间与工具计数，不接收凭据或其他字段')
    result = dict(previous or {})
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
            continue
        if key in TEXT_LIMITS:
            if not isinstance(value, str) or len(value) > TEXT_LIMITS[key]:
                raise ValueError(f'experiment.{key} 必须是最多 {TEXT_LIMITS[key]} 字符的文本')
            value = Redactor().snapshot(value.strip())
        elif key == 'model_source':
            if not isinstance(value, str) or value not in MODEL_SOURCES:
                raise ValueError('experiment.model_source 仅支持 requested、reported、verified')
        elif key in TIMES:
            try:
                if not isinstance(value, str) or not ISO_TIME.fullmatch(value):
                    raise ValueError()
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if parsed.utcoffset() is None:
                    raise ValueError()
            except ValueError:
                raise ValueError(f'experiment.{key} 必须是带时区的 ISO 8601 时间') from None
        elif type(value) is not int or value < 0:
            raise ValueError(f'experiment.{key} 必须是非负整数；未知时省略或填 null')
        result[key] = value
    times = [datetime.fromisoformat(result[key].replace('Z', '+00:00')) for key in TIMES if key in result]
    if any(finish < start for start, finish in zip(times, times[1:])):
        raise ValueError('experiment 时间须按 started_at、execution_started_at、execution_finished_at 顺序递增或相等')
    return result

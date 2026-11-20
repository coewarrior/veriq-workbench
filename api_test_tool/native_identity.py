"""Desktop thread identity at transport boundaries, without changing bindings.

Bare UUIDs and their thread: form identify the same real chat. Older opaque
identifiers remain exact-match only; stripping arbitrary prefixes could let a
different executor inherit another module's authority.
"""
from uuid import UUID


def thread_id(reference):
    if not isinstance(reference, str):
        return ''
    try:
        return str(UUID(reference.removeprefix('thread:')))
    except ValueError:
        return ''


def same_executor_ref(left, right):
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right:
        return False
    return left == right or bool(thread_id(left) and thread_id(left) == thread_id(right))


def native_thread_target(reference):
    # Retain the generator's legacy explicit thread: identifiers, while
    # accepting the actual bare UUID emitted by the desktop/dispatch APIs.
    actual = thread_id(reference)
    if actual:
        return actual
    return reference[7:] if isinstance(reference, str) and reference.startswith('thread:') else ''

"""An informational read must not resurrect an acknowledged stop."""
from api_test_tool.module_dispatch import observe_control


def test_context_after_exit_preserves_ack_and_new_commands_still_acknowledge():
    node = {'executor_dispatch': {'holder_id': 'worker'}, 'executor_controls': {
        'stop': {'holder_id': 'worker', 'state': 'pending'},
        'obsolete': {'holder_id': 'worker', 'state': 'obsolete'},
        'other': {'holder_id': 'other', 'state': 'pending'},
    }}
    observe_control(node, 'worker', 10, exited=True)
    node['executor_controls']['new'] = {'holder_id': 'worker', 'state': 'pending'}
    observe_control(node, 'worker', 20)
    controls = node['executor_controls']
    assert controls['stop']['state'] == 'exited'
    assert controls['stop']['exited_at'] == 10
    assert controls['obsolete']['state'] == 'obsolete'
    assert controls['other']['state'] == 'pending'
    assert controls['new']['state'] == 'received'
    observe_control(node, 'worker', 30, exited=True)
    assert controls['new']['state'] == 'exited'
    assert controls['new']['exited_at'] == 30
    assert controls['stop']['exited_at'] == 10

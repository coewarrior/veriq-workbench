from api_test_tool.module_dispatch import command, observe_control, node_dispatch, expire_dispatches


def node():
    return dict(id='node', revision=1, state='running', executor_dispatch={
        'holder_id':'old', 'dispatch_id':'dispatch-old', 'received_at':1},
        attempts=[{'lease_id':'lease'}], settlement_acks={'lease':{}}, executor_controls={})


def test_resume_does_not_wait_for_executor_that_already_exited():
    n=node()
    assert command({},n,'stop',2)['state']=='pending'
    observe_control(n,'old',3,exited=True)
    n.update(state='stopped',control_intent='stop')
    assert node_dispatch(n)['stop_complete']
    assert command({},n,'resume',4) is None
    assert not node_dispatch(n)['pending_controls']


def test_old_resume_is_obsolete_but_new_stop_requires_real_exit_ack():
    n=node()
    old=dict(n['executor_dispatch'],exit_acknowledged_at=3)
    n['executor_dispatch_history']=[old]
    n['executor_dispatch']={'holder_id':'new','dispatch_id':'dispatch-new'}
    n['executor_controls']['legacy']={'id':'legacy','holder_id':'old','action':'resume','created_at':4,'state':'pending'}
    expire_dispatches({'nodes':{'node':n},'leases':{}},6)
    current=command({},n,'stop',7)
    assert n['executor_controls']['legacy']['state']=='obsolete'
    assert 'exited_at' not in n['executor_controls']['legacy']
    n.update(state='stopped',control_intent='stop')
    assert not node_dispatch(n)['stop_complete']
    assert [c['id'] for c in node_dispatch(n)['pending_controls']]==[current['id']]
    observe_control(n,'new',8,exited=True)
    assert node_dispatch(n)['stop_complete']


def test_no_exit_evidence_never_retires_resume_or_stop():
    n=node()
    assert command({},n,'resume',2)['state']=='pending'
    assert command({},n,'stop',3)['state']=='pending'
    n.update(state='stopped',control_intent='stop')
    assert len(node_dispatch(n)['pending_controls'])==2
    assert not node_dispatch(n)['stop_complete']

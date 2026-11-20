"""One task's local observation receiver. No browser/model control or polling.

The owner starts it with the verified client. A FIFO carries only a short notification of a private observation
file; the existing record call owns credentials, lease validation and receipts.
"""
def start_native_observation_receiver(command, binding_file):
    root = Path(binding_file).resolve().parent
    with batch_lock(root / 'receiver-start'):
        status = root / 'native-receiver.json'
        try:
            with batch_lock(status):
                pass  # No live receiver owns the OS lock; safe to restart.
        except BlockingIOError:
            current = json.loads(read_utf8(status))
            if current.get('state') != 'ready' or not (root / 'native-observations.fifo').exists():
                raise ValueError('原接收器尚未就绪，保留现场，不启动第二个接收器')
            return {**current, 'reused': True}
        return _start_native_observation_receiver(command, binding_file)


def _start_native_observation_receiver(command, binding_file):
    """Return on the child's real readiness pipe, not a live terminal poll."""
    import os
    import subprocess
    root = Path(binding_file).resolve().parent
    read_fd, ready_fd = os.pipe()
    process = None
    try:
        log_fd = os.open(root / 'native-receiver.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(log_fd, 'ab') as log:
            process = subprocess.Popen([*command, 'native-observe-receive', '--binding-file', str(binding_file),
                '--ready-fd', str(ready_fd)], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                pass_fds=(ready_fd,), start_new_session=True)
        os.close(ready_fd)
        ready_fd = None
        with os.fdopen(read_fd, encoding='utf-8') as pipe:
            read_fd = None
            packet = json.loads(pipe.readline())
        if packet.get('receiver_ready') is not True or packet.get('pid') != process.pid:
            raise ValueError('接收器未确认就绪；停止在浏览器业务之前')
        return {'pid': process.pid, 'fifo': packet['fifo'], 'ready_at': packet['ready_at']}
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        raise
    finally:
        for fd in (read_fd, ready_fd):
            if fd is not None:
                os.close(fd)


def receive_native_observations(client, binding_file, prepared=None, ready_fd=None):
    import os
    import stat
    root = Path(binding_file).resolve().parent
    fifo = root / 'native-observations.fifo'
    status = root / 'native-receiver.json'
    response = root / 'native-receiver-response.json'
    with batch_lock(status):
        # Holding the original OS lock proves no active receiver owns this path.
        # A stopped/crashed receiver may be restarted without replaying its inbox.
        if fifo.is_symlink() or (fifo.exists() and not stat.S_ISFIFO(fifo.lstat().st_mode)):
            raise ValueError('观察入口类型改变，不能覆盖')
        if fifo.exists():
            fifo.unlink()
        os.mkfifo(fifo, 0o600)
        fd = os.open(fifo, os.O_RDWR)
        write_private_json(status, {'state': 'ready', 'pid': os.getpid(), 'fifo': str(fifo), 'protocol': 2, 'ready_at': datetime.now(timezone.utc).isoformat()})
        try:
            packet = {'receiver_ready': True, 'pid': os.getpid(), 'fifo': str(fifo),
                      'ready_at': datetime.now(timezone.utc).isoformat(),
                      **({'prepared': prepared} if prepared else {})}
            if ready_fd is None:
                print(json.dumps(packet), flush=True)
            else:
                with os.fdopen(ready_fd, 'w', encoding='utf-8') as ready:
                    ready.write(json.dumps(packet) + '\n')
            with os.fdopen(fd, 'r', encoding='utf-8') as stream:
                for line in stream:
                    if line.strip() == '{"stop":true}':
                        return {'stopped': True}
                    message = json.loads(line)
                    request_id = message['request_id']
                    import re
                    if not isinstance(request_id, str) or not re.fullmatch(r'[0-9]+-[a-f0-9]+', request_id):
                        raise ValueError('缺少本地观察请求标识')
                    if message.get('reconcile') is True:
                        try:
                            result = reconcile_native_observation(client, binding_file, request_id)
                        except Exception as error:
                            result = {'request_id': request_id, 'saved': False, 'state': 'unknown', 'reconciliation_error': str(error)}
                        write_private_json(root / ('native-receiver-response-' + request_id + '.json'), result)
                        write_private_json(response, result)
                        continue
                    pending_before = (root / 'observation-pending.json').exists()
                    timing = {'received_at': datetime.now(timezone.utc).isoformat()}
                    observation = {}
                    result = {'request_id': request_id, 'saved': False}
                    try:
                        observation = json.loads(read_utf8(root / ('observation-inbox-' + request_id + '.json')))
                        timing['save_started_at'] = datetime.now(timezone.utc).isoformat()
                        saved = observed_native_json(client, binding_file, observation,
                            root / 'observation-stream.json', root / ('receipt-stream-' + request_id + '.json'), request_id=request_id)
                        result.update(saved=True, receipt=saved)
                    except Exception as error:
                        # The original pending marker fences unknown writes.
                        # Do not retry or accept another business observation.
                        result.update(error=type(error).__name__, message=str(error), state='unknown')
                        marker = root / 'observation-pending.json'
                        pending = json.loads(read_utf8(marker)) if marker.exists() else {}
                        record_file = Path(pending['receipt_file']) if pending.get('receipt_file') else None
                        record = json.loads(read_utf8(record_file)) if record_file and record_file.exists() else {}
                        binding = json.loads(read_utf8(binding_file))
                        rejected = native_rejection_confirmed(record, binding)
                        if not pending_before and (rejected or
                                type(error) is ValueError and (not record_file or not record_file.exists())):
                            # Validation before the POST, or a definite HTTP rejection.
                            # Keep failure artifacts; allow Codex to correct the draft.
                            result['state'] = 'rejected' if rejected else 'not_sent'
                            marker.unlink(missing_ok=True)
                        if record_file:
                            result['record_receipt_file'] = str(record_file)
                        if getattr(error, 'native_receipt_state', None) in {'not_sent', 'rejected'}:
                            result['state'] = error.native_receipt_state
                            if getattr(error, 'native_receipt_file', None):
                                result['record_receipt_file'] = error.native_receipt_file
                    timing['save_finished_at'] = datetime.now(timezone.utc).isoformat()
                    result['timing'] = timing
                    result['exit'] = observation.get('exit') or {}
                    write_private_json(root / ('native-receiver-response-' + request_id + '.json'), result)
                    write_private_json(response, result)
                    # Keep the same receiver after a recoverable save error. The
                    # existing pending marker rejects new writes until reconciled.
                    # Only explicit lifecycle closeout sends the stop notification.
        finally:
            # Never remove a substituted path or an unrelated process's files.
            if fifo.exists() and stat.S_ISFIFO(fifo.lstat().st_mode):
                fifo.unlink()
            write_private_json(status, {'state': 'stopped', 'pid': os.getpid()})


def native_observed_closeout_arguments(binding_file):
    """Use only this run's actual saved exit, never a reconstructed success."""
    binding_file = Path(binding_file)
    binding = json.loads(read_utf8(binding_file))
    response_file = binding_file.parent / 'native-receiver-response.json'
    receipt = json.loads(read_utf8(response_file)) if response_file.exists() else {}
    exit_file = binding_file.parent / 'native-exit-observation.json'
    explicit_exit = binding_file.parent / 'native-explicit-exit.json'
    proof = (json.loads(read_utf8(explicit_exit)) if explicit_exit.exists() else
             json.loads(read_utf8(exit_file)) if exit_file.exists() else receipt)
    if explicit_exit.exists() and any(proof.get('binding', {}).get(key) != binding.get(key)
                                      for key in ('task_id', 'node_id', 'holder_id', 'lease_id')):
        raise ValueError('退出依据不属于当前原任务绑定')
    confirmed = {}
    def observation_saved(request_id):
        if request_id not in confirmed:
            answer_file = binding_file.parent / ('native-receiver-response-' + request_id + '.json')
            answer = json.loads(read_utf8(answer_file)) if answer_file.exists() else {}
            confirmed[request_id] = ((answer.get('request_id') == request_id and
                native_observation_settled(binding_file.parent, answer, binding))
                or native_observation_correction(binding_file.parent, request_id, binding))
        return confirmed[request_id]
    awaiting_file = binding_file.parent / 'native-observation-awaiting.json'
    waiting_saved = True
    if awaiting_file.exists():
        awaiting = json.loads(read_utf8(awaiting_file))
        waiting_saved = observation_saved(awaiting['request_id'])
    latest_file = binding_file.parent / 'native-last-observation.json'
    latest_saved = receipt.get('saved') is not False
    if latest_file.exists():
        latest = json.loads(read_utf8(latest_file))
        latest_saved = observation_saved(latest['request_id'])
    exit_state = proof.get('exit') or {}
    environment_file = binding_file.parent / 'browser-environment.json'
    if environment_file.exists():
        environment = json.loads(read_utf8(environment_file))
        if environment.get('schema') == 2 and (
                environment.get('state') != 'closed'
                or sorted(exit_state.get('context_ids') or []) != sorted(
                    row['context_id'] for row in environment.get('environments', []))):
            raise ValueError('退出依据不属于当前已关闭的浏览器环境，不能交还正在使用的账号')
    saved = (latest_saved and waiting_saved and not (binding_file.parent / 'observation-pending.json').exists() and
             (explicit_exit.exists() or (native_observation_settled(binding_file.parent, receipt, binding)
                and receipt.get('request_id') == proof.get('request_id'))))
    return native_closeout_arguments(binding, browser_stopped=exit_state.get('browser_stopped'),
        reason=exit_state.get('reason'), save_unconfirmed=not saved)


def stop_native_observation_receiver(binding_file):
    import os
    import stat
    fifo = Path(binding_file).resolve().parent / 'native-observations.fifo'
    if not fifo.exists():
        return
    if not stat.S_ISFIFO(fifo.lstat().st_mode):
        raise ValueError('观察入口类型改变，不能发送停止请求')
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as error:
        import errno
        if error.errno in {errno.ENOENT, errno.ENXIO}:
            return
        raise
    try:
        os.write(fd, b'{"stop":true}\n')
    finally:
        os.close(fd)


def reconcile_native_observation_correction(client, binding_file, request_id, correction_file):
    """Associate a later confirmed save, without converting the old unknown to ACK."""
    binding_file = Path(binding_file).absolute()
    root = binding_file.resolve().parent
    # Same order as receiver startup. A live receiver keeps sole ownership;
    # this explicit stopped-receiver operation never waits or runs a second writer.
    with batch_lock(root / 'receiver-start'), batch_lock(root / 'native-receiver.json'), batch_lock(binding_file):
        if binding_file.is_symlink() or binding_file.parent.is_symlink():
            raise ValueError('纠正关联不能替换原绑定文件')
        binding = json.loads(read_utf8(binding_file))
        if binding.get('workspace_url') != client.url:
            raise ValueError('纠正关联不属于当前测试台')
        import re
        if not isinstance(request_id, str) or not re.fullmatch(r'[0-9]+-[a-f0-9]+', request_id):
            raise ValueError('纠正关联缺少原观察 request_id')
        proof_file = root / ('native-observation-correction-' + request_id + '.json')
        previous = json.loads(read_utf8(proof_file)) if proof_file.exists() else None
        original, correction, evidence = native_correction_evidence(root, request_id, binding, correction_file,
            confirmed_revision=previous.get('revision') if previous else None)
        marker_file = root / 'observation-pending.json'
        marker = json.loads(read_utf8(marker_file)) if marker_file.exists() else None
        if marker is not None:
            case = original['payload']['cases'][0]
            if (marker_file.is_symlink() or marker.get('request_id') != request_id
                    or Path(marker.get('receipt_file', '')).resolve() != Path(evidence['original']['file']).resolve()
                    or any(marker.get(key) != case.get(key) for key in ('case_id', 'status', 'actual'))
                    or ('payload' in marker and marker['payload'] != original['payload'])
                    or (marker.get('binding') and any(marker['binding'].get(key) != binding.get(key)
                        for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')))):
                raise ValueError('其他请求或内容不匹配的 pending 仍受保护')
        reused = proof_file.exists()
        if reused:
            if not native_observation_correction(root, request_id, binding):
                raise ValueError('已有纠正关联的身份、修订或证据已变化；保留原证明')
            proof = json.loads(read_utf8(proof_file))
            if marker is not None and marker != proof.get('pending_marker'):
                raise ValueError('pending 与原纠正关联不一致')
        else:
            request = {key: binding[key] for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'account_id', 'dispatch_id', 'executor_ref') if key in binding}
            manifest_calls = int(client.manifest is None)
            record = client.call('direct_test_session', {**request, 'action': 'record', 'record_action': 'record',
                'arguments': {'project_id': binding['project_id'], 'execution_id': binding['execution_id']}})
            native_save_readback(correction, record, correction.get('case_baselines', {}))
            # Only submitted cases and fields needed by the existing exact
            # validator belong in this durable proof, never unrelated history.
            ids = {case['case_id'] for case in correction['payload'].get('cases', [])}
            content = correction['payload']
            keys = ['id', 'revision', *(key for key in ('review_notes', 'scene_outcome', 'experiment') if key in content)]
            if any('checkpoints' in case or 'checkpoint_updates' in case or
                   (correction.get('case_baselines', {}).get(case['case_id']) or {}).get('checkpoints')
                   for case in content.get('cases', [])):
                keys.extend(('dependency_checks', 'requirement_design'))
            selected = {key: copy.deepcopy(record[key]) for key in keys if key in record}
            for key in ('cases', 'superseded_cases'):
                selected[key] = [copy.deepcopy(case) for case in record.get(key, []) if case['case_id'] in ids]
            areas = {area['coverage_id'] for area in correction['payload'].get('coverage', [])}
            selected['coverage'] = [copy.deepcopy(area) for area in record.get('coverage', []) if area['coverage_id'] in areas]
            if (native_correction_scope(json.loads(read_utf8(binding_file))) != native_correction_scope(binding)
                    or native_correction_evidence(root, request_id, binding, correction_file)[2] != evidence
                    or (json.loads(read_utf8(marker_file)) if marker_file.exists() else None) != marker):
                raise ValueError('只读期间原绑定或证据已变化；保留 pending')
            proof = {'schema': 1, 'resolution': 'corrected_by_saved_receipt', 'request_id': request_id,
                'original_transport_state': 'unknown', 'binding': native_correction_scope(binding),
                'original_revision_before': original['revision_before'], 'revision': correction['result']['revision'],
                'evidence': evidence, 'record': selected, 'pending_marker': marker,
                'confirmed_at': datetime.now(timezone.utc).isoformat()}
            write_private_json(proof_file, proof)
        # Crash after durable proof is recoverable without another platform read.
        if marker is not None:
            if json.loads(read_utf8(marker_file)) != marker:
                raise ValueError('pending 已改变，不清理其他请求')
            marker_file.unlink()
        return {'request_id': request_id, 'resolution': proof['resolution'],
            'original_transport_state': 'unknown', 'revision': proof['revision'],
            'correction_receipt_file': str(proof_file), 'reused_receipt': reused,
            'http_calls': 0 if reused else 1 + manifest_calls}


def reconcile_native_observation(client, binding_file, request_id):
    """Read the original receipt and record if needed; never resubmit a save."""
    root = Path(binding_file).resolve().parent
    response_file = root / ('native-receiver-response-' + request_id + '.json')
    previous = json.loads(read_utf8(response_file)) if response_file.exists() else {'request_id': request_id, 'saved': False, 'state': 'unknown'}
    if previous.get('request_id') != request_id:
        return {'request_id':request_id,'saved':False,'state':'unknown','reconciliation':'Receiver response belongs to another request'}
    binding = json.loads(read_utf8(binding_file))
    if previous.get('state') == 'not_sent' or (previous.get('state') == 'rejected'
            and native_observation_settled(root, previous, binding)):
        return previous
    cached_saved = previous.get('saved') is True
    previous = {**previous, 'saved':False, 'state':'unknown'}
    observation = json.loads(read_utf8(root / ('observation-inbox-' + request_id + '.json')))
    payload = json.dumps(observation, sort_keys=True, ensure_ascii=False, allow_nan=False)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    receipt_file = root / ('receipt-stream-' + request_id + '-' + digest + '.json')
    marker_file = root / 'observation-pending.json'
    try:
        actual = observation_actual(observation)
    except ValueError:
        actual = None  # Invalid observations cannot have reached record POST.
    pending = json.loads(read_utf8(marker_file)) if marker_file.exists() else {}
    matching_pending = actual is not None and pending.get('request_id', request_id) == request_id and all(pending.get(key) == value for key, value in
        [('case_id', observation.get('case_id')), ('status', observation.get('status')), ('actual', actual)])
    candidates = [receipt_file]
    if matching_pending and pending.get('receipt_file'):
        candidates.append(Path(pending['receipt_file']))
    if previous.get('record_receipt_file'):
        candidates.append(Path(previous['record_receipt_file']))
    candidates.append(root / ('receipt-stream-' + digest + '.json'))  # Pre-0.17.71 receiver.
    for candidate in candidates:
        if candidate.resolve().parent != root or not candidate.exists():
            continue
        stored = json.loads(read_utf8(candidate))
        stored_cases = stored.get('payload', {}).get('cases') or []
        expected_case = {**(observation.get('case_changes') or {}), 'case_id': observation.get('case_id'),
                         'status': observation.get('status'), 'actual': actual}
        if len(stored_cases) == 1 and actual is not None and stored_cases[0] == expected_case:
            receipt_file = candidate
            break
        return {**previous, 'reconciliation': 'Existing write evidence differs; preserve original receipt'}
    def clear_own_marker():
        if marker_file.exists():
            pending = json.loads(read_utf8(marker_file))
            if (pending.get('receipt_file') == str(receipt_file)
                    and pending.get('request_id', request_id) == request_id):
                marker_file.unlink()
    # Receiver is the sole owner of its OS lock. No old local writer survives.
    # A POST always has its durable receipt first, so absence proves not sent.
    if not receipt_file.exists():
        if cached_saved:
            return {**previous, 'reconciliation':'Original saved write receipt is missing; preserve evidence'}
        clear_own_marker()
        return {**previous, 'saved': False, 'state': 'not_sent', 'reconciled': True}
    write_receipt = json.loads(read_utf8(receipt_file))
    binding = json.loads(read_utf8(binding_file))
    if native_rejection_confirmed(write_receipt, binding):
        clear_own_marker()
        return {**previous, 'saved': False, 'state': 'rejected', 'reconciled': True,
                'record_receipt_file': str(receipt_file)}
    if write_receipt.get('state') not in {'saved', 'pending', 'unknown', 'rejected'}:
        return {**previous, 'reconciliation': 'Original save state cannot be confirmed; preserve receipt'}
    # One implementation owns exact revision, full-field and checkpoint checks.
    # The existing receipt prevents native_record from issuing another save.
    try:
        saved = client.native_record(binding_file, write_receipt['payload'], receipt_file)
    except (ValueError, OSError) as error:
        return {**previous, 'saved': False, 'state': 'unknown', 'reconciliation': str(error)}
    current = json.loads(read_utf8(binding_file))
    confirmed = json.loads(read_utf8(receipt_file))
    if native_rejection_confirmed(confirmed, current):
        clear_own_marker()
        return {**previous, 'saved': False, 'state': 'rejected', 'reconciled': True,
                'record_receipt_file': str(receipt_file)}
    expected_payload = {'cases':[expected_case], **({'asset_files':observation['asset_files']} if 'asset_files' in observation else {})}
    if not native_pending_receipt_matches({'request_id':request_id,'payload':expected_payload},
                                          confirmed,current,request_id=request_id,client=client):
        return {**previous, 'reconciliation':'Original observation does not match the exact saved receipt'}
    if matching_pending:
        if not native_pending_receipt_matches(pending, confirmed, current, request_id=request_id, client=client):
            return {**previous, 'saved': False, 'state': 'unknown', 'reconciliation': 'Original pending marker does not match the exact saved receipt'}
    clear_own_marker()
    return {**previous, 'request_id': request_id, 'saved': True, 'state': 'saved', 'reconciled': True, 'receipt': saved}

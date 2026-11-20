"""Local process identity only: no business browser, service or model calls."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from api_test_tool.managed_browser import ManagedBrowser


def helper(tmp_path, monkeypatch):
    directory=tmp_path/'owned';directory.mkdir()
    alias=tmp_path/'alias';alias.symlink_to(directory, target_is_directory=True)
    binding={'lease_id':'lease','channel_id':'channel','pid':12345,'process_started':100.}
    (directory/'lease-binding.json').write_text(json.dumps(binding))
    process=Mock()
    process.pid=binding['pid']
    process.cmdline.return_value=['node','/skill/browser-session.cjs','serve',str(alias)]
    process.create_time.return_value=binding['process_started']
    process.children.return_value=[]
    monkeypatch.setattr(psutil,'Process',lambda pid:process)
    ledger=tmp_path/'processes.json'
    browser=SimpleNamespace(_process_path=lambda lid:ledger)
    return browser,directory,alias,binding,process,ledger


def test_canonical_alias_keeps_same_helper_owned(tmp_path, monkeypatch):
    browser,directory,alias,binding,process,ledger=helper(tmp_path,monkeypatch)
    assert ManagedBrowser.register_auxiliary(browser,'lease','channel',
        {'directory':str(alias),'pid':binding['pid']}) is False
    assert json.loads(ledger.read_text())==[
        {'pid':binding['pid'],'created':100.,'channel_id':'channel'}]


def test_different_directory_does_not_adopt_process(tmp_path, monkeypatch):
    browser,directory,alias,binding,process,ledger=helper(tmp_path,monkeypatch)
    other=tmp_path/'other';other.mkdir()
    process.cmdline.return_value=['node','/skill/browser-session.cjs','serve',str(other)]
    with pytest.raises(RuntimeError,match='进程已变化'):
        ManagedBrowser.register_auxiliary(browser,'lease','channel',
            {'directory':str(alias),'pid':binding['pid']})
    assert not ledger.exists()


def test_alias_does_not_accept_reused_pid(tmp_path, monkeypatch):
    browser,directory,alias,binding,process,ledger=helper(tmp_path,monkeypatch)
    process.create_time.return_value=200.
    with pytest.raises(RuntimeError,match='PID 已复用'):
        ManagedBrowser.register_auxiliary(browser,'lease','channel',
            {'directory':str(alias),'pid':binding['pid']})
    assert not ledger.exists()


def test_alias_does_not_accept_another_lease(tmp_path, monkeypatch):
    browser,directory,alias,binding,process,ledger=helper(tmp_path,monkeypatch)
    with pytest.raises(RuntimeError,match='归属核对失败'):
        ManagedBrowser.register_auxiliary(browser,'another-lease','channel',
            {'directory':str(alias),'pid':binding['pid']})
    assert not ledger.exists()


def test_timed_out_registration_with_confirmed_browser_close_is_settled(tmp_path, monkeypatch):
    browser,directory,alias,binding,process,ledger=helper(tmp_path,monkeypatch)
    (directory/'closed.json').write_text(json.dumps({'browserClosed':True}))
    assert ManagedBrowser.register_auxiliary(browser,'lease','channel',
        {'directory':str(alias),'pid':binding['pid']}) is True
    assert not ledger.exists()


def test_close_proof_does_not_accept_reused_live_pid(tmp_path, monkeypatch):
    browser,directory,alias,binding,process,ledger=helper(tmp_path,monkeypatch)
    (directory/'closed.json').write_text(json.dumps({'browserClosed':True}))
    process.create_time.return_value=200.
    with pytest.raises(RuntimeError,match='PID 已复用'):
        ManagedBrowser.register_auxiliary(browser,'lease','channel',{'directory':str(alias),'pid':binding['pid']})

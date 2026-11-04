from types import SimpleNamespace
import socket
import subprocess

import pytest

from services import network


def test_windows_ip_detection_filters_public_and_formats_urls(monkeypatch):
    monkeypatch.setattr(network.sys, 'platform', 'win32')
    monkeypatch.setattr(network, '_tailscale_executable', lambda: 'tailscale.exe')
    commands = []
    def run(command):
        commands.append(command)
        if command[0] == 'tailscale.exe':
            return SimpleNamespace(returncode=0, stdout='100.101.102.103\n8.8.8.8\n::1\n')
        return SimpleNamespace(returncode=0, stdout='["192.168.1.42","10.0.0.2","192.168.1.42","100.101.102.103","127.0.0.1","169.254.1.2","8.8.8.8"]')
    monkeypatch.setattr(network, '_run', run)
    result = network.detect_ips()
    assert result == {'tailscale': ['100.101.102.103'], 'lan': ['10.0.0.2', '192.168.1.42'], 'warnings': []}
    assert commands[0] == ['tailscale.exe', 'ip', '-4']
    assert network.format_urls(result) == [
        'Neste PC: http://127.0.0.1:8501',
        'Tailscale (VPN ligada): http://100.101.102.103:8501',
        'Rede local (mesmo Wi-Fi): http://10.0.0.2:8501',
        'Rede local (mesmo Wi-Fi): http://192.168.1.42:8501']


def test_missing_tailscale_does_not_prevent_lan(monkeypatch):
    monkeypatch.setattr(network.sys, 'platform', 'win32')
    monkeypatch.setattr(network, '_tailscale_executable', lambda: None)
    monkeypatch.setattr(network, '_run', lambda cmd: SimpleNamespace(returncode=0, stdout='"172.16.5.2"'))
    info = network.detect_ips()
    assert info['lan'] == ['172.16.5.2'] and info['tailscale'] == []
    assert any('nao encontrado' in message for message in info['warnings'])


@pytest.mark.parametrize('failure', ['exit', 'timeout', 'oserror'])
def test_unavailable_tailscale_is_warning(monkeypatch, failure):
    monkeypatch.setattr(network.sys, 'platform', 'win32')
    monkeypatch.setattr(network, '_tailscale_executable', lambda: 'tailscale.exe')
    def run(command):
        if command[0] == 'tailscale.exe':
            if failure == 'timeout': raise subprocess.TimeoutExpired(command, 8)
            if failure == 'oserror': raise OSError('cannot execute')
            return SimpleNamespace(returncode=1, stdout='')
        return SimpleNamespace(returncode=0, stdout='["192.168.1.2"]')
    monkeypatch.setattr(network, '_run', run)
    info = network.detect_ips()
    assert info['lan'] == ['192.168.1.2'] and info['warnings'] and not info['tailscale']


def test_failed_network_detection_warns_without_crashing(monkeypatch):
    monkeypatch.setattr(network.sys, 'platform', 'win32')
    monkeypatch.setattr(network, '_tailscale_executable', lambda: None)
    monkeypatch.setattr(network, '_run', lambda cmd: SimpleNamespace(returncode=0, stdout='not-json'))
    info = network.detect_ips()
    assert not info['lan']
    assert any('ipconfig' in warning for warning in info['warnings'])


def test_non_windows_no_internet_probes(monkeypatch):
    monkeypatch.setattr(network.sys, 'platform', 'linux')
    monkeypatch.setattr(network, '_tailscale_executable', lambda: None)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(None, None, None, None, ('192.168.0.2', 0))])
    assert network.detect_ips()['lan'] == ['192.168.0.2']


@pytest.mark.parametrize('port', [0, 65536, True, '8501'])
def test_invalid_port_rejected(port):
    with pytest.raises(ValueError):
        network.format_urls({}, port)


def test_urls_never_use_unvalidated_output():
    lines = network.format_urls({'lan': ['evil.example.com', '8.8.8.8', '192.168.1.2'],
                                 'tailscale': ['192.168.1.2', '100.64.0.1']})
    assert len(lines) == 3
    assert '100.64.0.1' in lines[1]
    assert '192.168.1.2' in lines[2]

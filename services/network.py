"""Descobre endereços locais sem consultar serviços na internet."""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

TAILSCALE_RANGE = ipaddress.ip_network("100.64.0.0/10")
LAN_RANGES = tuple(ipaddress.ip_network(value) for value in
                   ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _ipv4(values, networks):
    result = set()
    for value in values:
        try:
            address = ipaddress.ip_address(str(value).strip())
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address) and any(address in net for net in networks):
            result.add(str(address))
    return sorted(result, key=ipaddress.ip_address)


def _run(command):
    return subprocess.run(command, capture_output=True, text=True, timeout=8,
                          check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _tailscale_executable():
    found = shutil.which("tailscale")
    if found:
        return found
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def detect_ips():
    """Retorna listas IPv4 verificadas e avisos; Tailscale ausente não impede LAN."""
    warnings = []
    tailscale = []
    executable = _tailscale_executable()
    if executable is None:
        warnings.append("Tailscale nao encontrado. Instale/conecte o Tailscale para acessar fora de casa.")
    else:
        try:
            completed = _run([executable, "ip", "-4"])
            if completed.returncode == 0:
                tailscale = _ipv4(completed.stdout.splitlines(), [TAILSCALE_RANGE])
            if not tailscale:
                warnings.append("Tailscale sem IPv4 disponivel. Confira se esta conectado e tente novamente.")
        except (OSError, subprocess.TimeoutExpired):
            warnings.append("Nao foi possivel consultar o Tailscale. Confira o aplicativo e sua conexao.")
    lan = []
    try:
        if sys.platform == "win32":
            completed = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "$ErrorActionPreference='Stop'; @(Get-NetIPAddress -AddressFamily IPv4 | "
                "Where-Object {$_.AddressState -eq 'Preferred'} | "
                "Select-Object -ExpandProperty IPAddress) | ConvertTo-Json -Compress"])
            if completed.returncode != 0:
                raise OSError("Falha ao consultar interfaces")
            values = json.loads(completed.stdout or "[]")
            lan = _ipv4([values] if isinstance(values, str) else values, LAN_RANGES)
        else:
            lan = _ipv4([item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None,
                        family=socket.AF_INET)], LAN_RANGES)
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        warnings.append("Nao foi possivel identificar o IP da rede local; consulte ipconfig no Windows.")
    if not lan:
        warnings.append("Nenhum IPv4 de rede local encontrado. Conecte o PC ao Wi-Fi ou cabo de rede.")
    return {"tailscale": tailscale, "lan": lan, "warnings": warnings}


def format_urls(info, port=8501):
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Porta invalida.")
    lines = [f"Neste PC: http://127.0.0.1:{port}"]
    lines.extend(f"Tailscale (VPN ligada): http://{ip}:{port}"
                 for ip in _ipv4(info.get("tailscale", []), [TAILSCALE_RANGE]))
    lines.extend(f"Rede local (mesmo Wi-Fi): http://{ip}:{port}"
                 for ip in _ipv4(info.get("lan", []), LAN_RANGES))
    return lines


def main():
    info = detect_ips()
    for warning in info["warnings"]:
        print("AVISO: " + warning)
    for line in format_urls(info):
        print(line)
    print("No celular, mantenha o Tailscale ligado para acessar fora de casa.")


if __name__ == "__main__":
    main()

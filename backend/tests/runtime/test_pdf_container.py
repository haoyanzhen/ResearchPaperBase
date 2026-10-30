"""Explicit real-container gate; requires the locally built parser image.

Not part of default unit tests. Never skips or substitutes a mock when unavailable.
"""

import errno
import json
import socket
import subprocess
from uuid import uuid4

from rpb.adapters.pdf_processing import isolated, parse_pdf


def test_pc01_real_container_text_and_limits(tmp_path, monkeypatch):
    from backend.tests.unit.test_pdf_processing import sample

    result = parse_pdf(sample("Container evidence"), runner="docker")
    assert result["reason"] is None, result
    assert "Container evidence" in result["text"]
    assert result["segments"][0]["page"] == 1
    assert parse_pdf(sample(blank=True), runner="docker")["reason"] == "no_usable_text"
    assert parse_pdf(sample(encrypted=True), runner="docker")["reason"] == "encrypted_content"
    assert parse_pdf(b"%PDF-corrupt", runner="docker")["reason"] == "corrupt_content"


def test_pc02_real_container_denies_host_file_secrets_and_external_network(tmp_path, monkeypatch):
    marker = tmp_path / "private-project"
    marker.write_text("must not be visible")
    monkeypatch.setenv("RPB_SECRET", "must not cross")
    # Establish reachability first; a connection failure alone cannot prove isolation.
    from rpb.adapters.pdf_container import IMAGE

    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        listener.listen(4)
        port = listener.getsockname()[1]
        name = "rpb-pdf-control-" + uuid4().hex
        try:
            probe = subprocess.check_output(
                [
                    "docker",
                    "run",
                    "--name",
                    name,
                    "--pull=never",
                    "--add-host=host.docker.internal:host-gateway",
                    IMAGE,
                    "python",
                    "-c",
                    "import socket; ip=socket.gethostbyname('host.docker.internal'); "
                    f"socket.create_connection((ip, {port}), timeout=3).close(); print(ip)",
                ],
                timeout=20,
            )
            address = probe.decode().strip()
        finally:
            subprocess.run(
                ["docker", "rm", "--force", name],
                timeout=5,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        script = (
            """import json, os, socket, sys
from pathlib import Path
result = {'read': False, 'write_errno': None, 'network': False,
          'secret': os.environ.get('RPB_SECRET')}
try:
 Path(MARKER).read_text(); result['read'] = True
except OSError: pass
try:
 Path('/tmp/escape').write_text('escape')
except OSError as error: result['write_errno'] = error.errno
try:
 socket.create_connection((ADDRESS, PORT), timeout=0.5); result['network'] = True
except OSError: pass
Path(sys.argv[2]).write_text(json.dumps(result))
""".replace("MARKER", repr(str(marker)))
            .replace("ADDRESS", repr(address))
            .replace("PORT", str(port))
        )
        assert isolated(script, b"input", runner="docker") == {
            "read": False,
            "write_errno": errno.EROFS,
            "network": False,
            "secret": None,
        }
    assert marker.read_text() == "must not be visible"


def test_pc03_real_deadline_memory_output_and_cleanup(monkeypatch):
    from rpb.adapters import pdf_processing

    def containers():
        output = subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", "name=rpb-pdf-"], timeout=5
        )
        return set(output.split())

    before = containers()
    monkeypatch.setattr(pdf_processing, "PARSER_TIMEOUT", 3)
    assert isolated("while True: pass", b"input", runner="docker")["reason"] == "safety_limit"
    monkeypatch.setattr(pdf_processing, "PARSER_TIMEOUT", 20)
    monkeypatch.setattr(pdf_processing, "PARSER_RSS_KIB", 65536)
    assert (
        isolated("a=[]\nwhile True: a.append(bytearray(10_000_000))", b"input", runner="docker")[
            "reason"
        ]
        == "safety_limit"
    )
    assert (
        isolated("import sys\nsys.stdout.write('x' * 3_000_000)", b"input", runner="docker")[
            "reason"
        ]
        == "safety_limit"
    )
    assert containers() <= before, json.dumps([c.decode() for c in containers() - before])

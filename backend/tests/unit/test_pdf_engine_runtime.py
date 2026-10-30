"""Single-engine dispatch and fail-closed platform/runtime boundaries."""

import io
import json
import subprocess

import pytest

from rpb.adapters import pdf_container, pdf_engines, pdf_processing


def test_pe01_exactly_one_selected_engine_without_fallback(monkeypatch):
    monkeypatch.setattr(
        pdf_engines, "ENGINES", {"first": "first script", "second": "second script"}
    )
    calls = []

    def run(script, raw, *, runner):
        calls.append((script, raw, runner))
        return {"reason": "no_usable_text", "text": None, "segments": []}

    monkeypatch.setattr(pdf_processing, "isolated", run)
    assert pdf_engines.available_engines() == ("first", "second")
    assert pdf_processing.parse_pdf(b"%PDF-input", engine="second")["text"] is None
    assert calls == [("second script", b"%PDF-input", "auto")]
    with pytest.raises(ValueError, match="engine"):
        pdf_processing.parse_pdf(b"%PDF-input", engine="llm")
    assert len(calls) == 1


def test_pe02_current_engine_and_configuration_reject_unknowns(monkeypatch):
    assert pdf_engines.available_engines() == ("pypdf",)
    with pytest.raises(ValueError, match="engine"):
        pdf_processing.PDFProvider(engine="llm")
    monkeypatch.setenv("RPB_PDF_RUNNER", "unconfined")
    with pytest.raises(ValueError, match="runner"):
        pdf_processing.PDFProvider()
    assert pdf_processing.PDFProvider(runner="docker").runner == "docker"


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_pe03_windows_linux_choose_container_not_application_parser(platform, monkeypatch):
    monkeypatch.setattr(pdf_processing.sys, "platform", platform)
    calls = []

    def run(script, raw, **limits):
        calls.append((script, raw, limits))
        return pdf_container.failure("parser_unavailable")

    monkeypatch.setattr(pdf_processing, "container_extract", run)
    assert pdf_processing.isolated("script", b"input")["reason"] == "parser_unavailable"
    assert len(calls) == 1
    assert calls[0][2] == {"timeout": 20, "memory_kib": 262144}


def test_pe04_missing_runtime_is_unavailable(monkeypatch):
    monkeypatch.setattr(pdf_container.shutil, "which", lambda name: None)
    assert pdf_container.container_extract("script", b"pdf", timeout=1, memory_kib=262144) == {
        "reason": "parser_unavailable",
        "text": None,
        "segments": [],
    }


@pytest.mark.parametrize(
    "exit_code,expected",
    [
        (0, None),
        (125, "parser_unavailable"),
        (126, "parser_unavailable"),
        (127, "parser_unavailable"),
        (137, "safety_limit"),
    ],
)
def test_pe05_container_confinement_input_and_cleanup(monkeypatch, exit_code, expected):
    commands = []
    body = {"reason": None, "text": "Evidence", "segments": []}

    class Process:
        returncode = exit_code

        def __init__(self, command, *, stdin, stdout, stderr):
            commands.append(command)
            assert stdin.read() == b"private PDF"
            self.stdout = io.BytesIO(json.dumps(body).encode())

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(pdf_container.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(pdf_container.subprocess, "Popen", Process)
    monkeypatch.setattr(
        pdf_container.subprocess,
        "run",
        lambda cmd, **kw: (commands.append(cmd), subprocess.CompletedProcess(cmd, 0))[1],
    )
    result = pdf_container.container_extract(
        "script", b"private PDF", timeout=20, memory_kib=262144
    )
    assert result == (body if expected is None else pdf_container.failure(expected))
    command = commands[0]
    for flag in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--pids-limit=32",
        "--security-opt=no-new-privileges",
        "--memory=262144k",
        "--memory-swap=262144k",
        "--user=65534:65534",
        "--pull=never",
        "--log-driver=none",
    ):
        assert flag in command
    assert not any(arg in {"-v", "--mount", "-e", "--env", "--privileged"} for arg in command)
    assert commands[1] == ["docker", "rm", "--force", command[command.index("--name") + 1]]


def test_pe06_deadline_removes_container_and_reaps_cli(monkeypatch):
    actions = []

    class Process:
        returncode = None
        stdout = io.BytesIO(b"")

        def __init__(self, *args, **kwargs):
            pass

        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("docker", timeout)
            actions.append("reaped")

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9
            actions.append("killed")

    monkeypatch.setattr(pdf_container.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(pdf_container.subprocess, "Popen", Process)
    monkeypatch.setattr(
        pdf_container.subprocess,
        "run",
        lambda cmd, **kw: (actions.append("removed"), subprocess.CompletedProcess(cmd, 0))[1],
    )
    assert (
        pdf_container.container_extract("loop", b"pdf", timeout=0.1, memory_kib=262144)["reason"]
        == "safety_limit"
    )
    assert actions == ["killed", "reaped", "removed"]


@pytest.mark.parametrize(
    "result",
    [
        [],
        {"reason": [], "text": None, "segments": []},
        {"reason": None, "text": "x", "segments": []},
        {"reason": None, "text": 42, "segments": []},
        {
            "reason": None,
            "text": "x",
            "segments": [{"start_offset": 0, "end_offset": 2, "page": 1}],
        },
        {
            "reason": None,
            "text": "x",
            "segments": [{"start_offset": 0, "end_offset": 1, "page": True}],
        },
        {"reason": None, "text": "x" * 200001, "segments": []},
    ],
)
def test_pe07_invalid_engine_output_cannot_become_evidence(monkeypatch, result):
    monkeypatch.setattr(pdf_processing, "isolated", lambda *args, **kwargs: result)
    assert pdf_processing.parse_pdf(b"%PDF-input") == pdf_container.failure("safety_limit")


@pytest.mark.parametrize("cleanup_timeout", [False, True])
def test_pe08_cleanup_failure_cannot_report_success(monkeypatch, caplog, cleanup_timeout):
    class Process:
        returncode = 0
        stdout = io.BytesIO(b'{"reason": null, "text": "evidence", "segments": []}')

        def __init__(self, *args, **kwargs):
            pass

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    def cleanup(cmd, **kwargs):
        if cleanup_timeout:
            raise subprocess.TimeoutExpired(cmd, 5)
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(pdf_container.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(pdf_container.subprocess, "Popen", Process)
    monkeypatch.setattr(pdf_container.subprocess, "run", cleanup)
    assert pdf_container.container_extract("script", b"pdf", timeout=20, memory_kib=262144) == (
        pdf_container.failure("parser_unavailable")
    )
    assert "cleanup unconfirmed: rpb-pdf-" in caplog.text

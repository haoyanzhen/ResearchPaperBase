"""Local worker protocol must not dispatch without permission or accept bad vectors."""

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event

import pytest

from rpb.adapters.local_embeddings import EmbeddingUnavailable, LocalEmbeddings


def profile():
    result = {
        "model_id": "intfloat/multilingual-e5-base",
        "weights_revision": "d128750597153bb5987e10b1c3493a34e5a4502a",
        "weights_digest": "a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7",
        "tokenizer_revision": "721e17b7fb6b2a3388d0a9c6ff8a99784672cdacd98e2b6cb9cdab92237be08e",
        "dimension": 768,
        "normalization": "l2",
        "distance": "cosine",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "runtime_digest": "1" * 64,
    }
    result["profile_id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


@contextmanager
def permit():
    yield


def worker(tmp_path):
    path = tmp_path / "worker.py"
    path.write_text(
        "import json,sys,time\n"
        f"print(json.dumps({{'profile': {profile()!r}}}), flush=True)\n"
        "for line in sys.stdin:\n"
        " q=json.loads(line)\n"
        " if q['text']=='hang': time.sleep(30)\n"
        " if q['text']=='slow': time.sleep(0.5)\n"
        " v={'offsets': [[0, 1]], 'passage_length': 3} if q['kind']=='tokenize' "
        "else {'vector': ([10**400]+[0.0]*767) if q['text']=='huge' "
        "else ([1.0]+[0.0]*767) if q['text'] != 'bad' else [0.0]*768}\n"
        " print(json.dumps(v), flush=True)\n"
    )
    return [sys.executable, str(path)]


def test_private_worker_profile_tokenization_vector_and_shutdown(tmp_path):
    with LocalEmbeddings(worker(tmp_path), dict(os.environ), permit, profile(), timeout=3) as port:
        assert port.offsets("文") == [(0, 1)]
        assert port.passage_length("文") == 3
        assert port.embed("text") == [1.0] + [0.0] * 767
        with pytest.raises(EmbeddingUnavailable):
            port.embed("bad")
        process = port.process
    assert process.poll() is not None


def test_profile_mismatch_and_permission_denial_stop_dispatch(tmp_path):
    command = worker(tmp_path)
    wrong = {**profile(), "runtime_digest": "2" * 64}
    with pytest.raises(EmbeddingUnavailable):
        LocalEmbeddings(command, dict(os.environ), permit, wrong, timeout=3)

    @contextmanager
    def deny():
        raise PermissionError("revoked")
        yield

    with LocalEmbeddings(command, dict(os.environ), deny, profile(), timeout=3) as port:
        with pytest.raises(PermissionError):
            port.embed("secret source")


def test_worker_without_startup_response_times_out(tmp_path):
    path = tmp_path / "hang.py"
    path.write_text("import time; time.sleep(30)")
    with pytest.raises(EmbeddingUnavailable):
        LocalEmbeddings([sys.executable, str(path)], dict(os.environ), permit, timeout=0.1)


def test_missing_worker_and_overflow_response_fail_closed(tmp_path):
    with pytest.raises(EmbeddingUnavailable):
        LocalEmbeddings([str(tmp_path / "missing")], dict(os.environ), permit, timeout=1)
    with LocalEmbeddings(worker(tmp_path), dict(os.environ), permit, profile(), timeout=3) as port:
        with pytest.raises(EmbeddingUnavailable):
            port.embed("huge")
        assert port.process.poll() is not None


def test_stalled_inference_times_out_and_reaps_worker(tmp_path):
    with LocalEmbeddings(
        worker(tmp_path), dict(os.environ), permit, profile(), timeout=0.2
    ) as port:
        with pytest.raises(EmbeddingUnavailable):
            port.embed("hang")
        assert port.process.poll() is not None


def test_authorization_boundary_ends_before_inference_response(tmp_path):
    released = Event()

    @contextmanager
    def permit_dispatch():
        try:
            yield
        finally:
            released.set()

    with LocalEmbeddings(
        worker(tmp_path), dict(os.environ), permit_dispatch, profile(), timeout=3
    ) as port:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(port.embed, "slow")
            assert released.wait(1)
            assert not future.done()
            assert len(future.result(timeout=3)) == 768


def test_authorization_failure_after_dispatch_reaps_worker(tmp_path):
    @contextmanager
    def revoked_after_send():
        yield
        raise PermissionError("policy changed")

    with LocalEmbeddings(
        worker(tmp_path), dict(os.environ), revoked_after_send, profile(), timeout=3
    ) as port:
        with pytest.raises(PermissionError):
            port.embed("first text")
        assert port.process.poll() is not None
        with pytest.raises(EmbeddingUnavailable):
            port.embed("different text")


def test_concurrent_call_cannot_use_response_after_revocation(tmp_path):
    cleaning, release = Event(), Event()
    calls = iter([True, False])

    @contextmanager
    def permit_dispatch():
        revoked = next(calls)
        yield
        if revoked:
            raise PermissionError("revoked")

    with LocalEmbeddings(
        worker(tmp_path), dict(os.environ), permit_dispatch, profile(), timeout=3
    ) as port:
        original_close = port.close

        def slow_close():
            cleaning.set()
            assert release.wait(3)
            original_close()

        port.close = slow_close
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(port.embed, "first")
            assert cleaning.wait(2)
            second = pool.submit(port.embed, "second")
            assert not second.done()
            release.set()
            with pytest.raises(PermissionError):
                first.result(timeout=3)
            with pytest.raises(EmbeddingUnavailable):
                second.result(timeout=3)
        port.close = original_close

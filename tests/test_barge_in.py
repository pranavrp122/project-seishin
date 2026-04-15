"""Tests for barge-in cooperative cancellation in sei_engine.py."""
import ast
import re

SEI_ENGINE_PATH = "scripts/sei_engine.py"


def _get_source():
    with open(SEI_ENGINE_PATH) as f:
        return f.read()


def _get_function_args(source: str) -> dict[str, list[str]]:
    """Parse AST to get function names -> argument lists."""
    tree = ast.parse(source)
    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = [a.arg for a in node.args.args]
    return funcs


# --- drain_queue ---

def test_drain_queue_exists():
    """drain_queue must be a module-level function."""
    src = _get_source()
    funcs = _get_function_args(src)
    assert "drain_queue" in funcs, "drain_queue function not found"


def test_drain_queue_uses_get_nowait():
    """drain_queue must use get_nowait() for non-blocking drain."""
    src = _get_source()
    # Find drain_queue body
    assert "get_nowait()" in src, "drain_queue must use get_nowait()"


def test_drain_queue_is_sync():
    """drain_queue must be a regular (not async) function."""
    src = _get_source()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "drain_queue":
            return  # Found as regular function
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "drain_queue":
            raise AssertionError("drain_queue should be sync, not async")
    raise AssertionError("drain_queue not found")


# --- stream_llm ---

def test_stream_llm_has_cancel_event_param():
    """stream_llm must accept cancel_event parameter."""
    src = _get_source()
    funcs = _get_function_args(src)
    assert "cancel_event" in funcs.get("stream_llm", []), \
        "stream_llm missing cancel_event parameter"


def test_stream_llm_checks_cancel_in_loop():
    """stream_llm must check cancel_event.is_set() inside aiter_lines loop."""
    src = _get_source()
    # Find stream_llm body and check it contains is_set check
    in_stream_llm = False
    found_cancel_check = False
    for line in src.splitlines():
        if "async def stream_llm" in line:
            in_stream_llm = True
        elif in_stream_llm and (line.strip().startswith("async def ") or line.strip().startswith("def ")) and "stream_llm" not in line:
            break
        elif in_stream_llm and "cancel_event.is_set()" in line:
            found_cancel_check = True
    assert found_cancel_check, "stream_llm must check cancel_event.is_set() in loop"


# --- tts_sentence ---

def test_tts_sentence_has_cancel_event_param():
    """tts_sentence must accept cancel_event parameter."""
    src = _get_source()
    funcs = _get_function_args(src)
    assert "cancel_event" in funcs.get("tts_sentence", []), \
        "tts_sentence missing cancel_event parameter"


def test_tts_sentence_checks_cancel_in_loop():
    """tts_sentence must check cancel_event.is_set() inside aiter_bytes loop."""
    src = _get_source()
    in_tts_sentence = False
    found_cancel_check = False
    for line in src.splitlines():
        if "async def tts_sentence" in line:
            in_tts_sentence = True
        elif in_tts_sentence and (line.strip().startswith("async def ") or line.strip().startswith("def ")) and "tts_sentence" not in line:
            break
        elif in_tts_sentence and "cancel_event.is_set()" in line:
            found_cancel_check = True
    assert found_cancel_check, "tts_sentence must check cancel_event.is_set() in loop"


# --- handle_llm_response ---

def test_handle_llm_response_has_cancel_event_param():
    """handle_llm_response must accept cancel_event parameter."""
    src = _get_source()
    funcs = _get_function_args(src)
    assert "cancel_event" in funcs.get("handle_llm_response", []), \
        "handle_llm_response missing cancel_event parameter"


def test_tts_consumer_uses_wait_for():
    """tts_consumer must use asyncio.wait_for with timeout for interruptibility."""
    src = _get_source()
    assert "asyncio.wait_for(sentence_queue.get(), timeout=" in src, \
        "tts_consumer must use asyncio.wait_for(sentence_queue.get(), timeout=...)"


def test_interrupted_frame_sent():
    """handle_llm_response must send interrupted type when cancel_event is set."""
    src = _get_source()
    assert '"type": "interrupted"' in src or "'type': 'interrupted'" in src, \
        'Must send {"type": "interrupted"} frame on cancellation'


def test_done_frame_still_sent():
    """handle_llm_response must still send done type on normal completion."""
    src = _get_source()
    assert '"type": "done"' in src, 'Must still send {"type": "done"} on normal completion'


# --- Anti-patterns ---

def test_no_task_cancel_on_httpx():
    """No task.cancel() on any httpx streaming task (gen_task, tts_task)."""
    src = _get_source()
    # task.cancel() on gen_task or tts_task is forbidden
    assert "gen_task.cancel()" not in src, "Must not use gen_task.cancel()"
    assert "tts_task.cancel()" not in src, "Must not use tts_task.cancel()"

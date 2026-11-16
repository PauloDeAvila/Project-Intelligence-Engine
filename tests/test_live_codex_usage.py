import pytest

from pie.certification.live_codex import parse_codex_jsonl


def _trace(usage_extra):
    usage = {"input_tokens": 100, "cached_input_tokens": 10,
             "output_tokens": 50}
    usage.update(usage_extra)
    return '{"type":"turn.completed","usage":' + \
        __import__("json").dumps(usage) + '}'


def test_missing_reasoning_output_tokens_is_none():
    out = parse_codex_jsonl(_trace({}))
    assert out["usage"]["reasoning_output_tokens"] is None
    assert out["usage"]["input_tokens"] == 100
    assert out["usage"]["cached_input_tokens"] == 10
    assert out["usage"]["output_tokens"] == 50


def test_valid_usage_parses():
    out = parse_codex_jsonl(_trace({"reasoning_output_tokens": 20}))
    assert out["usage"]["reasoning_output_tokens"] == 20
    assert out["provider_reported"] is True


def test_reasoning_exceeding_output_fails():
    with pytest.raises(ValueError):
        parse_codex_jsonl(_trace({"reasoning_output_tokens": 60}))


@pytest.mark.parametrize("bad", ["20", 20.5, True])
def test_invalid_reasoning_output_tokens_type_fails(bad):
    with pytest.raises(ValueError):
        parse_codex_jsonl(_trace({"reasoning_output_tokens": bad}))


@pytest.mark.parametrize("missing", ["input_tokens", "cached_input_tokens",
                                     "output_tokens"])
def test_missing_required_tokens_fails(missing):
    trace = parse_codex_jsonl(_trace({"reasoning_output_tokens": 20}))
    usage = dict(trace["usage"])
    usage.pop(missing)
    line = '{"type":"turn.completed","usage":' + \
        __import__("json").dumps(usage) + '}'
    with pytest.raises(ValueError):
        parse_codex_jsonl(line)
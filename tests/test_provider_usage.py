from pie.certification.provider_usage import parse_provider_usage
from pie.certification import ProviderUsage


def test_parses_openai_compatible_usage_without_estimating_tokens():
    assert ProviderUsage.__name__ == "ProviderUsage"
    usage = parse_provider_usage(
        {
            "model": "fixture-model",
            "usage": {
                "prompt_tokens": 120,
                "prompt_tokens_details": {"cached_tokens": 40},
                "completion_tokens": 30,
                "completion_tokens_details": {"reasoning_tokens": 5},
            },
        },
        duration_ms=12.5,
    )
    assert usage.provider_usage_status == "available"
    assert usage.model == "fixture-model"
    assert usage.input_tokens == 120
    assert usage.cached_input_tokens == 40
    assert usage.uncached_input_tokens == 80
    assert usage.output_tokens == 30
    assert usage.reasoning_output_tokens == 5
    assert usage.total_tokens == 150
    assert usage.duration_ms == 12.5


def test_missing_usage_never_becomes_zero():
    missing = parse_provider_usage({"model": "fixture-model"})
    no_cache = parse_provider_usage(
        {"usage": {"input_tokens": 10, "output_tokens": 2}}
    )
    assert missing.provider_usage_status == "unavailable"
    assert missing.input_tokens is None
    assert no_cache.provider_usage_status == "unavailable"
    assert no_cache.cached_input_tokens is None
    assert no_cache.uncached_input_tokens is None


def test_invalid_usage_is_unavailable_and_preserves_observed_values():
    invalid = parse_provider_usage(
        {
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 11,
                "output_tokens": 2,
            }
        }
    )
    assert invalid.provider_usage_status == "unavailable"
    assert invalid.reason == "cached_input_exceeds_input"
    assert invalid.total_tokens == 12

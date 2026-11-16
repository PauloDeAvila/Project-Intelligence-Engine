from tools.verify_context_runtime import verify


def test_context_runtime_verifier_is_local_and_fail_closed():
    result = verify()
    assert result["status"] == "PASS_LOCAL"
    assert result["local_validation"] is True
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["external_provider_usage"] == "unavailable"
    assert result["pillars"]["continuous_certification"]["status"] == "PASS_SYNTHETIC_ONLY"

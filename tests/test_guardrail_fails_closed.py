from citizengraph.guardrail.validator import validate_cypher


def test_guardrail_placeholder_fails_closed():
    """Until the real guardrail exists, nothing may pass. Replace with the full suite."""
    assert validate_cypher("MATCH (s:Service) RETURN s LIMIT 1").ok is False

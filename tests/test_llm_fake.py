from citizengraph.llm.fake import FakeLLM


def test_fake_llm_records_prompts_and_returns_scripted():
    llm = FakeLLM(["MATCH (n) RETURN n LIMIT 1"])
    out = llm.generate("hello")
    assert out.startswith("MATCH")
    assert llm.prompts == ["hello"]

from ramp.observability import prompt_hash, redact, tracer


def test_redact_drops_images_and_truncates() -> None:
    messages = [
        {"role": "system", "content": "s" * 5000},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "judge"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        },
    ]
    out = redact(messages)
    assert out[0]["content"].endswith("…[truncated]")
    assert out[1]["content"][1] == {"type": "image", "bytes_base64": 26}
    assert "base64,AAAA" not in str(out)


def test_tracing_is_off_without_keys(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracer.cache_clear()
    assert tracer() is None
    assert prompt_hash("a") == prompt_hash("a") != prompt_hash("b")

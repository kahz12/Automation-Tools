"""with_retry() is the shared backoff loop for all three provider families.

It must never actually sleep in tests, so every case injects `sleep`.
Passing it explicitly also dodges the default-argument binding trap:
`sleep=time.sleep` is bound at def time and monkeypatching time.sleep
afterwards would have no effect.
"""
from automation_tools.ai.retry import is_rate_limit, with_retry


def test_is_rate_limit_recognises_transient_errors():
    assert is_rate_limit(Exception("Error 429 too many requests")) is True
    assert is_rate_limit(Exception("resource_exhausted")) is True
    assert is_rate_limit(Exception("503 Service Unavailable")) is True
    assert is_rate_limit(Exception("rate_limit_exceeded")) is True


def test_is_rate_limit_ignores_permanent_errors():
    assert is_rate_limit(Exception("invalid argument")) is False
    assert is_rate_limit(Exception("401 unauthorized")) is False


def test_returns_the_value_on_first_success():
    slept = []
    assert with_retry(lambda: "ok", label="Test", sleep=slept.append) == "ok"
    assert slept == []


def test_retries_rate_limits_with_doubling_backoff():
    attempts = []
    slept = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise Exception("429 rate limit")
        return "ok"

    assert with_retry(flaky, label="Test", sleep=slept.append) == "ok"
    assert len(attempts) == 3
    assert slept == [2.0, 4.0]  # doubles each retry


def test_gives_up_after_max_retries_and_returns_none():
    attempts = []
    slept = []

    def always_limited():
        attempts.append(1)
        raise Exception("429 rate limit")

    assert with_retry(always_limited, label="Test", max_retries=4, sleep=slept.append) is None
    assert len(attempts) == 4


def test_does_not_retry_a_permanent_error():
    attempts = []
    slept = []

    def bad_request():
        attempts.append(1)
        raise Exception("400 invalid model")

    assert with_retry(bad_request, label="Test", sleep=slept.append) is None
    assert len(attempts) == 1, "a permanent error must not be retried"
    assert slept == []


def test_reports_the_provider_label_when_it_gives_up(capsys):
    with_retry(lambda: (_ for _ in ()).throw(Exception("boom")),
               label="Groq", sleep=lambda _s: None)
    assert "Groq" in capsys.readouterr().out

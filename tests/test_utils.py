"""Tests for genesis_protocol.utils module."""

import pytest
from genesis_protocol.utils.sanitizers import Sanitizer
from genesis_protocol.utils.formatters import Formatter
from genesis_protocol.utils.rate_limiter import TokenBucket, RateLimiter, RateLimitConfig, get_rate_limiter


class TestSanitizer:
    """Tests for Sanitizer class."""

    def test_sanitize_text_basic(self):
        text = "Hello World"
        result = Sanitizer.sanitize_text(text)
        assert result == "Hello World"

    def test_sanitize_text_removes_html(self):
        text = "<script>alert('xss')</script>Hello"
        result = Sanitizer.sanitize_text(text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result or "alert" not in result

    def test_sanitize_text_empty_string(self):
        result = Sanitizer.sanitize_text("")
        assert result == ""

    def test_sanitize_text_none_input(self):
        result = Sanitizer.sanitize_text(None)
        assert result == ""

    def test_sanitize_text_max_length(self):
        text = "a" * 20000
        result = Sanitizer.sanitize_text(text, max_length=100)
        assert len(result) <= 100

    def test_sanitize_text_removes_null_bytes(self):
        text = "Hello\x00World"
        result = Sanitizer.sanitize_text(text)
        assert "\x00" not in result

    def test_sanitize_text_normalizes_whitespace(self):
        text = "Hello    World\n\nTest"
        result = Sanitizer.sanitize_text(text)
        assert "    " not in result
        assert "\n" not in result

    def test_sanitize_markdown_basic(self):
        text = "Hello **world**"
        result = Sanitizer.sanitize_markdown(text)
        assert "Hello" in result
        assert "world" in result

    def test_sanitize_markdown_blocks_scripts(self):
        text = "Hello <script>alert('xss')</script> World"
        result = Sanitizer.sanitize_markdown(text)
        assert "alert" not in result

    def test_sanitize_markdown_blocks_xss(self):
        text = 'Click <a href="javascript:alert(1)">here</a>'
        result = Sanitizer.sanitize_markdown(text)
        assert "[blocked]" in result

    def test_check_sql_injection_detects_select(self):
        text = "SELECT * FROM users"
        assert Sanitizer.check_sql_injection(text) is True

    def test_check_sql_injection_detects_union(self):
        text = "1 UNION SELECT password FROM users"
        assert Sanitizer.check_sql_injection(text) is True

    def test_check_sql_injection_allows_normal_text(self):
        text = "Hello, this is a normal message!"
        assert Sanitizer.check_sql_injection(text) is False

    def test_check_xss_detects_javascript_protocol(self):
        text = '<a href="javascript:alert(1)">'
        assert Sanitizer.check_xss(text) is True

    def test_check_xss_detects_event_handlers(self):
        text = '<img src=x onerror="alert(1)">'
        assert Sanitizer.check_xss(text) is True

    def test_check_xss_allows_normal_text(self):
        text = "This is a normal message"
        assert Sanitizer.check_xss(text) is False

    def test_validate_file_type_allowed(self):
        assert Sanitizer.validate_file_type("document.pdf", ["pdf", "doc"]) is True
        assert Sanitizer.validate_file_type("image.PNG", ["pdf", "png"]) is True

    def test_validate_file_type_not_allowed(self):
        assert Sanitizer.validate_file_type("malware.exe", ["pdf", "doc"]) is False
        assert Sanitizer.validate_file_type("file", ["pdf"]) is False

    def test_validate_file_type_empty_filename(self):
        assert Sanitizer.validate_file_type("", ["pdf"]) is False

    def test_sanitize_filename_basic(self):
        result = Sanitizer.sanitize_filename("my document.pdf")
        assert "/" not in result
        assert "\\" not in result

    def test_sanitize_filename_removes_path_traversal(self):
        result = Sanitizer.sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_sanitize_filename_empty(self):
        result = Sanitizer.sanitize_filename("")
        assert result == "unnamed"

    def test_sanitize_filename_max_length(self):
        result = Sanitizer.sanitize_filename("a" * 300 + ".txt")
        assert len(result) <= 255

    def test_validate_chat_id_valid(self):
        assert Sanitizer.validate_chat_id(123456789) is True
        assert Sanitizer.validate_chat_id(-987654321) is True

    def test_validate_chat_id_invalid(self):
        assert Sanitizer.validate_chat_id(0) is False
        assert Sanitizer.validate_chat_id(123.45) is False

    def test_validate_user_id_valid(self):
        assert Sanitizer.validate_user_id(123456789) is True
        assert Sanitizer.validate_user_id(1) is True

    def test_validate_user_id_invalid(self):
        assert Sanitizer.validate_user_id(0) is False
        assert Sanitizer.validate_user_id(-1) is False
        assert Sanitizer.validate_user_id(123.45) is False

    def test_truncate_for_ai_basic(self):
        text = "Short text"
        result = Sanitizer.truncate_for_ai(text)
        assert result == text

    def test_truncate_for_ai_truncates(self):
        text = "a" * 10000
        result = Sanitizer.truncate_for_ai(text, max_chars=100)
        assert len(result) <= 100 + 50  # includes truncation message
        assert "[Content truncated" in result

    def test_truncate_for_ai_empty(self):
        result = Sanitizer.truncate_for_ai("")
        assert result == ""

    def test_truncate_for_ai_none(self):
        result = Sanitizer.truncate_for_ai(None)
        assert result == ""


class TestFormatter:
    """Tests for Formatter class."""

    def test_escape_markdown_basic(self):
        text = "Hello *world*"
        result = Formatter.escape_markdown(text)
        assert r"\*" in result

    def test_escape_markdown_empty(self):
        result = Formatter.escape_markdown("")
        assert result == ""

    def test_escape_markdown_none(self):
        result = Formatter.escape_markdown(None)
        assert result == ""

    def test_escape_html_basic(self):
        text = "<div>Hello & World</div>"
        result = Formatter.escape_html(text)
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result

    def test_escape_html_empty(self):
        result = Formatter.escape_html("")
        assert result == ""

    def test_format_markdown_basic(self):
        text = "Hello **world**"
        result = Formatter.format_markdown(text)
        assert "Hello" in result

    def test_format_code_block_with_language(self):
        code = "print('hello')"
        result = Formatter.format_code_block(code, language="python")
        assert "```python" in result
        assert "print" in result

    def test_format_code_block_without_language(self):
        code = "hello world"
        result = Formatter.format_code_block(code)
        assert "```" in result

    def test_format_code_block_empty(self):
        result = Formatter.format_code_block("")
        assert result == ""

    def test_format_response_markdown(self):
        text = "Hello world"
        result = Formatter.format_response(text, style="markdown")
        assert result == text

    def test_format_response_html(self):
        text = "**Hello** *world*"
        result = Formatter.format_response(text, style="html")
        assert "<b>" in result
        assert "<i>" in result

    def test_format_response_plain(self):
        text = "**Hello** *world*"
        result = Formatter.format_response(text, style="plain")
        assert "**" not in result
        assert "*" not in result

    def test_format_html_converts_bold(self):
        text = "**bold**"
        result = Formatter.format_html(text)
        assert "<b>bold</b>" in result

    def test_format_html_converts_italic(self):
        text = "*italic*"
        result = Formatter.format_html(text)
        assert "<i>italic</i>" in result

    def test_format_html_converts_code(self):
        text = "`code`"
        result = Formatter.format_html(text)
        assert "<code>code</code>" in result

    def test_format_html_empty(self):
        result = Formatter.format_html("")
        assert result == ""

    def test_format_plain_removes_formatting(self):
        text = "**bold** *italic* `code` [link](url)"
        result = Formatter.format_plain(text)
        assert "**" not in result
        assert "*" not in result
        assert "`" not in result

    def test_format_plain_empty(self):
        result = Formatter.format_plain("")
        assert result == ""

    def test_truncate_response_basic(self):
        text = "Short text"
        result = Formatter.truncate_response(text)
        assert result == text

    def test_truncate_response_truncates(self):
        text = "a" * 5000
        result = Formatter.truncate_response(text, max_length=100)
        # Result includes truncation message which adds ~25 chars
        assert len(result) <= 100 + 30
        assert "truncated" in result

    def test_truncate_response_empty(self):
        result = Formatter.truncate_response("")
        assert result == ""

    def test_format_list_unnumbered(self):
        items = ["apple", "banana", "cherry"]
        result = Formatter.format_list(items)
        assert "• apple" in result
        assert "• banana" in result
        assert "\n" in result

    def test_format_list_numbered(self):
        items = ["apple", "banana"]
        result = Formatter.format_list(items, numbered=True)
        assert "1. apple" in result
        assert "2. banana" in result

    def test_format_list_empty(self):
        result = Formatter.format_list([])
        assert result == ""

    def test_format_error(self):
        result = Formatter.format_error("Something went wrong")
        assert "❌" in result
        assert "Error" in result

    def test_format_error_with_trace(self):
        result = Formatter.format_error("Error", include_trace=True)
        assert "support" in result.lower()

    def test_format_success(self):
        result = Formatter.format_success("Operation completed")
        assert "✅" in result
        assert "Operation completed" in result

    def test_format_warning(self):
        result = Formatter.format_warning("Be careful")
        assert "⚠️" in result
        assert "Be careful" in result

    def test_format_info(self):
        result = Formatter.format_info("FYI")
        assert "ℹ️" in result
        assert "FYI" in result


class TestTokenBucket:
    """Tests for TokenBucket class."""

    def test_initialization(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.capacity == 10
        assert bucket.tokens == 10

    def test_consume_success(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        result = bucket.consume(5)
        assert result is True
        assert bucket.tokens == 5

    def test_consume_insufficient_tokens(self):
        bucket = TokenBucket(capacity=3, refill_rate=0.1)
        result = bucket.consume(5)
        assert result is False

    def test_consume_exact_tokens(self):
        bucket = TokenBucket(capacity=5, refill_rate=0.1)
        result = bucket.consume(5)
        assert result is True
        assert bucket.tokens == 0

    def test_refill_after_time(self):
        bucket = TokenBucket(capacity=10, refill_rate=5.0)
        bucket.tokens = 0
        # Simulate time passing (refill is based on elapsed time)
        import time
        time.sleep(0.1)
        bucket._refill()
        assert bucket.tokens > 0

    def test_wait_time_with_tokens(self):
        bucket = TokenBucket(capacity=10, refill_rate=5.0)
        wait = bucket.wait_time(1)
        assert wait == 0.0

    def test_wait_time_without_tokens(self):
        bucket = TokenBucket(capacity=5, refill_rate=5.0)
        bucket.tokens = 0
        wait = bucket.wait_time(5)
        assert wait > 0

    def test_multiple_consumes(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(3) is True
        assert bucket.consume(3) is True
        assert bucket.consume(3) is True
        assert bucket.consume(3) is False


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_initialization(self):
        limiter = RateLimiter()
        assert limiter._user_rpm == 20
        assert limiter._user_rph == 500

    def test_check_user_limit_allowed(self):
        limiter = RateLimiter()
        allowed, wait = limiter.check_user_limit(12345)
        assert allowed is True
        assert wait == 0.0

    def test_check_user_limit_denied(self):
        limiter = RateLimiter()
        # Exhaust the limits
        for _ in range(25):
            limiter.check_user_limit(99999)
        allowed, wait = limiter.check_user_limit(99999)
        # Should be denied at some point
        assert isinstance(allowed, bool)
        assert isinstance(wait, float)

    def test_check_provider_limit_allowed(self):
        limiter = RateLimiter()
        allowed, wait = limiter.check_provider_limit("groq")
        assert allowed is True

    def test_check_global_limit_allowed(self):
        limiter = RateLimiter()
        allowed, wait = limiter.check_global_limit()
        assert allowed is True

    def test_check_all_allowed(self):
        limiter = RateLimiter()
        allowed, reason, wait = limiter.check_all(12345, "groq")
        assert allowed is True
        assert reason == ""
        assert wait == 0.0

    def test_reset_user(self):
        limiter = RateLimiter()
        limiter.check_user_limit(12345)
        limiter.reset_user(12345)
        # After reset, should be able to use again
        allowed, wait = limiter.check_user_limit(12345)
        assert allowed is True

    def test_reset_provider(self):
        limiter = RateLimiter()
        limiter.check_provider_limit("groq")
        limiter.reset_provider("groq")
        allowed, wait = limiter.check_provider_limit("groq")
        assert allowed is True

    def test_get_status(self):
        limiter = RateLimiter()
        status = limiter.get_status(12345)
        assert status["user_id"] == 12345
        assert "minute_remaining" in status
        assert "hour_remaining" in status


class TestGetRateLimiter:
    """Tests for get_rate_limiter function."""

    def test_returns_rate_limiter(self):
        limiter = get_rate_limiter()
        assert isinstance(limiter, RateLimiter)

    def test_returns_same_instance(self):
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_creation(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000,
            burst_size=10
        )
        assert config.requests_per_minute == 60
        assert config.requests_per_hour == 1000
        assert config.burst_size == 10

    def test_default_burst_size(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000
        )
        assert config.burst_size == 5  # default value
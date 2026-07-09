"""Tests for regex-based PII masking (docs Section 9, "PII that must be
redacted" and Section 10, "redaction happens before the LLM sees it")."""

from __future__ import annotations

from fitnova.core.constants import SpeakerLabel
from fitnova.processing.normalizer import NormalizedSegment
from fitnova.processing.pii_redaction import redact_segments, redact_text


def test_redacts_email_address():
    result = redact_text("please email me at customer@example.com for details")
    assert "customer@example.com" not in result.redacted_text
    assert "[REDACTED_EMAIL]" in result.redacted_text
    assert result.findings[0].category == "EMAIL"


def test_redacts_indian_mobile_number():
    result = redact_text("you can reach me at 9876543210 anytime")
    assert "9876543210" not in result.redacted_text
    assert "[REDACTED_PHONE]" in result.redacted_text


def test_redacts_indian_mobile_with_country_code():
    result = redact_text("my number is +91 9876543210")
    assert "9876543210" not in result.redacted_text
    assert "[REDACTED_PHONE]" in result.redacted_text


def test_redacts_twelve_digit_id_number():
    result = redact_text("my aadhaar is 1234 5678 9012 for verification")
    assert "1234 5678 9012" not in result.redacted_text
    assert "[REDACTED_ID]" in result.redacted_text


def test_redacts_card_like_number():
    result = redact_text("card number 4111 1111 1111 1111 expires soon")
    assert "4111 1111 1111 1111" not in result.redacted_text
    assert "[REDACTED_CARD]" in result.redacted_text


def test_redacts_pan_card_format():
    result = redact_text("PAN is ABCDE1234F on file")
    assert "ABCDE1234F" not in result.redacted_text
    assert "[REDACTED_ID]" in result.redacted_text


def test_does_not_redact_ordinary_short_numbers():
    result = redact_text("I lost 5 kg in 3 months on a budget of 2000 rupees")
    assert result.redacted_text == "I lost 5 kg in 3 months on a budget of 2000 rupees"
    assert result.findings == []


def test_redact_segments_preserves_structure_and_timestamps():
    segments = [
        NormalizedSegment(
            segment_index=0,
            speaker_label=SpeakerLabel.CUSTOMER,
            start_time=1.0,
            end_time=3.0,
            text="call me back at 9876543210 please",
            confidence=0.9,
        )
    ]
    redacted, findings = redact_segments(segments)

    assert len(redacted) == 1
    assert redacted[0].start_time == 1.0
    assert redacted[0].end_time == 3.0
    assert redacted[0].speaker_label == SpeakerLabel.CUSTOMER
    assert "9876543210" not in redacted[0].text
    assert len(findings) == 1
    assert findings[0].category == "PHONE"

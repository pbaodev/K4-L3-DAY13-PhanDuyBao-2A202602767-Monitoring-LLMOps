from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd_and_card_and_passport() -> None:
    out = scrub_text("CCCD 012345678901, card 4111 1111 1111 1111, passport B1234567")
    assert "012345678901" not in out
    assert "4111 1111 1111 1111" not in out
    assert "B1234567" not in out
    assert "REDACTED_CCCD" in out
    assert "REDACTED_CREDIT_CARD" in out
    assert "REDACTED_PASSPORT_VN" in out


def test_scrub_card_with_dashes_is_not_left_partially_visible() -> None:
    out = scrub_text("Pay with 4111-1111-1111-1111 please")
    assert "4111" not in out


def test_scrub_leaves_clean_text_untouched() -> None:
    text = "What is your refund policy?"
    assert scrub_text(text) == text

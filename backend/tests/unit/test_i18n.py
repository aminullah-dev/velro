"""Rendering a message on the server.

Only SMS needs this, and SMS is the sign-in path, so a mistake here is nobody
in Ghorband being able to sign in -- and being charged for the privilege.
"""

from __future__ import annotations

import pytest

from shared.i18n import MessageKeyUnknownError, render


class TestTheSignInMessage:
    def test_dari(self) -> None:
        assert render("auth.sms.otp", locale="fa-AF", code="12345", ttl_minutes=5) == (
            "کود ولرو شما 12345 است. تا 5 دقیقه اعتبار دارد."
        )

    def test_pashto(self) -> None:
        rendered = render("auth.sms.otp", locale="ps", code="12345", ttl_minutes=5)
        assert "12345" in rendered
        assert "ولرو" in rendered

    def test_english(self) -> None:
        assert render("auth.sms.otp", locale="en", code="12345", ttl_minutes=5) == (
            "Your VELRO code is 12345. It expires in 5 minutes."
        )

    def test_the_three_languages_differ(self) -> None:
        """A renderer that quietly serves one language for all three would pass
        every other test in this file."""
        rendered = {
            locale: render("auth.sms.otp", locale=locale, code="1", ttl_minutes=5)
            for locale in ("en", "fa-AF", "ps")
        }
        assert len(set(rendered.values())) == 3


class TestWhatIsRefused:
    def test_an_unknown_key_raises_rather_than_sending_itself(self) -> None:
        """A message reading "auth.sms.otp" costs exactly as much as one that
        says something."""
        with pytest.raises(MessageKeyUnknownError):
            render("auth.sms.nonexistent", locale="fa-AF")

    def test_a_missing_placeholder_raises_rather_than_leaving_a_hole(self) -> None:
        with pytest.raises(MessageKeyUnknownError) as raised:
            render("auth.sms.otp", locale="fa-AF", code="12345")
        assert "ttl_minutes" in str(raised.value)

    def test_an_unknown_locale_falls_back_to_dari(self) -> None:
        """A locale is a column value and could be anything. A key is not: the
        parity test guarantees all three files have the same keys, so a
        per-key fallback would only ever hide a missing translation."""
        assert render("auth.sms.otp", locale="fr", code="1", ttl_minutes=5) == render(
            "auth.sms.otp", locale="fa-AF", code="1", ttl_minutes=5
        )


def test_it_reads_the_same_files_the_apps_do() -> None:
    """Not a copy.

    resources/locales is what mobile copies at build time and what the admin
    syncs, so a sentence cannot say one thing on the handset and another in the
    text message about it.
    """
    from pathlib import Path

    from shared import i18n

    expected = Path(i18n.__file__).resolve().parent.parent / "resources" / "locales"
    assert expected == i18n._LOCALES
    assert (expected / "fa-AF.json").is_file()

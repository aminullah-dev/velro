"""What a deployment is allowed to be.

Most configuration mistakes announce themselves. Two do not, and both of them
are in the sign-in path, which is the only door into VELRO for everybody in
Ghorband -- so they are refused at startup rather than defaulted away.
"""

from __future__ import annotations

import pytest

from shared.config import ConfigurationError, load

BASE = {
    "VELRO_DATABASE_URL": "postgresql+psycopg://localhost/velro_test",
    "VELRO_JWT_SECRET": "a-secret-long-enough-to-be-plausible-32",
}


def settings(**overrides: str):
    return load(config_path="/nonexistent.toml", env={**BASE, **overrides})


class TestTheDebugEcho:
    """otp_debug_echo returns the sign-in code in the API response.

    Not a log leak -- a log needs server access. This needs a phone number.
    Anyone who has one can request a code, read it out of the reply, and sign in
    as that person: the driver whose earnings are in there, the woman whose
    journeys are.
    """

    def test_a_production_deployment_refuses_to_start_with_it_on(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            settings(VELRO_ENVIRONMENT="production", VELRO_OTP_DEBUG_ECHO="true",
                     VELRO_SMS_PROVIDER="twilio")
        assert "OTP_DEBUG_ECHO" in str(raised.value)

    def test_development_may_have_it_on(self) -> None:
        """Somebody has to be able to sign in with no SMS account at all."""
        assert settings(VELRO_OTP_DEBUG_ECHO="true").otp_debug_echo is True

    def test_it_is_off_unless_asked_for(self) -> None:
        assert settings().otp_debug_echo is False

    def test_production_is_fine_with_it_off(self) -> None:
        config = settings(VELRO_ENVIRONMENT="production", VELRO_SMS_PROVIDER="twilio")
        assert config.is_production
        assert config.otp_debug_echo is False


class TestTheConsoleSender:
    """The other silent one, failing the opposite way.

    ConsoleSmsSender writes a log line and delivers nothing. In production that
    is an authentication system that cannot sign anybody in -- and it looks
    healthy from every angle except a real person holding a real handset, which
    is the angle nobody has until launch day.
    """

    def test_a_production_deployment_refuses_to_start_with_it(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            settings(VELRO_ENVIRONMENT="production")
        assert "SMS_PROVIDER" in str(raised.value)

    def test_development_uses_it_by_default(self) -> None:
        assert settings().sms_provider == "console"


def test_the_required_settings_are_still_required() -> None:
    with pytest.raises(ConfigurationError) as raised:
        load(config_path="/nonexistent.toml", env={})
    assert "VELRO_DATABASE_URL" in str(raised.value)
    assert "VELRO_JWT_SECRET" in str(raised.value)


def test_an_unknown_key_is_refused_rather_than_ignored() -> None:
    """A typo in a production environment variable is a setting that silently
    stayed at its default."""
    with pytest.raises(ConfigurationError) as raised:
        load(
            config_path="/nonexistent.toml",
            env={**BASE, "VELRO_OTP_DEBUG_ECH": "true"},
        )
    assert "unknown" in str(raised.value).lower()

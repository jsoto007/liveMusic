"""Password hashing and policy.

bcrypt at cost 12. bcrypt silently truncates its input at 72 bytes, so a long
passphrase would otherwise have its tail ignored — we reject over-length input
explicitly rather than letting the user believe in strength that is not there.
"""

import re
import unicodedata

import bcrypt

BCRYPT_ROUNDS = 12
MIN_LENGTH = 12
MAX_BYTES = 72

# The handful of passwords that turn up in every breach corpus. Not a
# substitute for a real breach-list check, but it removes the worst offenders
# at zero cost.
_COMMON = {
    "password", "password1", "password123", "123456789012", "qwertyuiop12",
    "letmein12345", "iloveyou1234", "adminadmin12", "welcome12345",
    "changeme1234", "passw0rd1234", "qwerty123456", "111111111111",
}


class PasswordPolicyError(ValueError):
    """Raised with a user-facing message when a password fails policy."""


def normalize(raw: str) -> str:
    # NFKC so a password typed with composed vs decomposed accents (or on a
    # different keyboard layout) hashes to the same value on every platform.
    return unicodedata.normalize("NFKC", raw)


def validate_password(raw: str, *, email: str | None = None) -> str:
    if not isinstance(raw, str):
        raise PasswordPolicyError("Password must be text.")
    password = normalize(raw)

    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_LENGTH} characters."
        )
    if len(password.encode("utf-8")) > MAX_BYTES:
        raise PasswordPolicyError(
            "Password is too long. Please use 72 bytes or fewer."
        )
    if password.lower() in _COMMON:
        raise PasswordPolicyError("That password is too common. Please choose another.")
    if re.fullmatch(r"(.)\1*", password):
        raise PasswordPolicyError("Password cannot be a single repeated character.")
    if email:
        local_part = email.split("@")[0].lower()
        if local_part and len(local_part) >= 4 and local_part in password.lower():
            raise PasswordPolicyError("Password must not contain your email address.")
    return password


def hash_password(raw: str) -> str:
    password = normalize(raw)
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("utf-8")


def verify_password(raw: str, password_hash: str | None) -> bool:
    if not password_hash or not isinstance(raw, str):
        return False
    try:
        return bcrypt.checkpw(
            normalize(raw).encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        # A malformed stored hash must read as "wrong password", not crash the
        # login route into a 500 that distinguishes this account from others.
        return False


# A real bcrypt hash of a throwaway value, compared against when the email does
# not exist so that "no such user" costs the same wall-clock time as "wrong
# password". Without it, response timing enumerates the user table.
_DUMMY_HASH = hash_password("live-msc-timing-equalizer-value")


def waste_a_hash() -> None:
    bcrypt.checkpw(b"live-msc-timing-equalizer-value", _DUMMY_HASH.encode("utf-8"))

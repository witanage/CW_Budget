"""
Country-specific validation for licence plates and mobile numbers.

Only Sri Lanka ("LK") is implemented today.  To support another country, add a
``CountryRules`` entry to ``COUNTRIES`` with its own plate/mobile normalisers;
callers always go through ``normalize_plate`` / ``normalize_mobile`` with a
country code, and ``country_code`` is already persisted on users and vehicles.
"""

import re
from dataclasses import dataclass
from typing import Callable, Optional


class ValidationError(ValueError):
    """Raised when user input does not match the expected format."""


@dataclass(frozen=True)
class Plate:
    normalized: str      # canonical unique form, e.g. "CAB1234", "250-1234", "19SRI1234"
    display: str         # human form, e.g. "WP CAB-1234"
    region: Optional[str]  # province / state prefix if supplied, e.g. "WP"


@dataclass(frozen=True)
class CountryRules:
    code: str
    name: str
    normalize_plate: Callable[[str], Plate]
    normalize_mobile: Callable[[str], str]
    plate_hint: str
    mobile_hint: str


# ---------------------------------------------------------------------------
# Sri Lanka
# ---------------------------------------------------------------------------

LK_PROVINCES = ('WP', 'CP', 'SP', 'NW', 'NC', 'UP', 'SG', 'NP', 'EP')

# "ශ්‍රී" with and without the zero-width joiner that some keyboards omit.
_SRI_SINHALA = ('ශ්‍රී', 'ශ්රී')
_SRI_DISPLAY = 'ශ්‍රී'

_LK_MODERN = re.compile(r'^(?:(%s))?([A-Z]{2,3})(\d{4})$' % '|'.join(LK_PROVINCES))
_LK_SRI = re.compile(r'^(\d{1,2})SRI(\d{4})$')
_LK_NUMERIC = re.compile(r'^(\d{1,3})-(\d{4})$')


def _lk_normalize_plate(raw: str) -> Plate:
    if not raw or not isinstance(raw, str):
        raise ValidationError('Licence plate is required.')
    s = raw.strip().upper()
    if len(s) > 32:
        raise ValidationError('Licence plate is too long.')
    for sri in _SRI_SINHALA:
        s = s.replace(sri, 'SRI')
    s = s.replace('‍', '')

    # Old numeric series keep the separator because "65-1234" and "651234"
    # cannot otherwise be told apart from a 6-digit typo.
    numeric = re.sub(r'\s+', '-', s)
    numeric = re.sub(r'-+', '-', numeric)
    m = _LK_NUMERIC.match(numeric)
    if m:
        norm = f'{m.group(1)}-{m.group(2)}'
        return Plate(normalized=norm, display=norm, region=None)

    compact = re.sub(r'[\s\-]+', '', s)

    m = _LK_SRI.match(compact)
    if m:
        return Plate(normalized=f'{m.group(1)}SRI{m.group(2)}',
                     display=f'{m.group(1)} {_SRI_DISPLAY} {m.group(2)}', region=None)

    m = _LK_MODERN.match(compact)
    if m:
        region, letters, digits = m.groups()
        display = f'{letters}-{digits}'
        return Plate(normalized=f'{letters}{digits}',
                     display=f'{region} {display}' if region else display,
                     region=region)

    raise ValidationError(
        'Invalid Sri Lankan licence plate. Examples: CAB-1234, WP KA-1234, 250-1234, 19 ශ්‍රී 1234.')


def _lk_normalize_mobile(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raise ValidationError('Mobile number is required.')
    digits = re.sub(r'[\s\-().]', '', raw.strip())
    if digits.startswith('+'):
        digits = digits[1:]
    elif digits.startswith('00'):
        digits = digits[2:]
    if not digits.isdigit():
        raise ValidationError('Mobile number may only contain digits.')
    if digits.startswith('94'):
        local = digits[2:]
    elif digits.startswith('0'):
        local = digits[1:]
    else:
        local = digits
    if not re.fullmatch(r'7\d{8}', local):
        raise ValidationError('Invalid Sri Lankan mobile number. Example: 077 123 4567.')
    return f'+94{local}'


COUNTRIES = {
    'LK': CountryRules(
        code='LK',
        name='Sri Lanka',
        normalize_plate=_lk_normalize_plate,
        normalize_mobile=_lk_normalize_mobile,
        plate_hint='e.g. CAB-1234, WP KA-1234, 250-1234, 19 ශ්‍රී 1234',
        mobile_hint='e.g. 077 123 4567',
    ),
}

DEFAULT_COUNTRY = 'LK'


def get_country(code: Optional[str]) -> CountryRules:
    code = (code or DEFAULT_COUNTRY).upper()
    if code not in COUNTRIES:
        raise ValidationError('Unsupported country.')
    return COUNTRIES[code]


def normalize_plate(raw: str, country: Optional[str] = None) -> Plate:
    return get_country(country).normalize_plate(raw)


def normalize_mobile(raw: str, country: Optional[str] = None) -> str:
    return get_country(country).normalize_mobile(raw)


def normalize_any_mobile(raw: str, country: Optional[str] = None) -> str:
    """Scanner's optional number: accept the country's format, else any E.164."""
    try:
        return normalize_mobile(raw, country)
    except ValidationError:
        digits = re.sub(r'[\s\-().]', '', (raw or '').strip())
        if re.fullmatch(r'\+[1-9]\d{7,14}', digits):
            return digits
        raise ValidationError('Invalid mobile number. Use local format or +<country code>.')


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def clean_text(value, max_len: int) -> str:
    """Strip control characters and cap length of free text."""
    if value is None:
        return ''
    text = _CONTROL_CHARS.sub('', str(value)).strip()
    return text[:max_len]


def parse_coordinates(lat, lng, accuracy=None):
    """Return (lat, lng, accuracy) floats or (None, None, None) if absent/invalid."""
    if lat in (None, '') or lng in (None, ''):
        return None, None, None
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return None, None, None
    if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
        return None, None, None
    acc = None
    try:
        if accuracy not in (None, ''):
            acc = max(0, min(int(float(accuracy)), 100000))
    except (TypeError, ValueError):
        acc = None
    return round(lat_f, 6), round(lng_f, 6), acc


def validate_password(password: str) -> None:
    if not password or len(password) < 8:
        raise ValidationError('Password must be at least 8 characters.')
    if len(password) > 128:
        raise ValidationError('Password is too long.')

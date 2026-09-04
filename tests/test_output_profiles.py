from __future__ import annotations

import pytest

from output_profiles import OutputProfile, builtin_profiles, normalize_profile


def test_builtin_ssd1306_profile_preserves_current_vlsb_semantics():
    profile = builtin_profiles()['ssd1306_vlsb_c']

    assert profile.encoding.bit_axis == 'vertical'
    assert profile.encoding.group_order == 'row_major'
    assert profile.encoding.bit_order == 'lsb_first'
    assert profile.encoding.polarity == 'one_is_lit'
    assert profile.text.bytes_per_line == 16


def test_profile_rejects_unknown_placeholder_and_oversized_literal():
    raw = OutputProfile.default().to_dict()
    raw['text']['segment_prefix'] = '${unknown}'
    with pytest.raises(ValueError, match='unknown placeholder'):
        normalize_profile(raw)

    raw = OutputProfile.default().to_dict()
    raw['text']['line_prefix'] = 'x' * 1025
    with pytest.raises(ValueError, match='1024'):
        normalize_profile(raw)


def test_profile_rejects_invalid_enum_and_line_width():
    raw = OutputProfile.default().to_dict()
    raw['encoding']['bit_axis'] = 'diagonal'
    with pytest.raises(ValueError, match='bit_axis'):
        normalize_profile(raw)

    raw = OutputProfile.default().to_dict()
    raw['text']['bytes_per_line'] = 0
    with pytest.raises(ValueError, match='bytes_per_line'):
        normalize_profile(raw)


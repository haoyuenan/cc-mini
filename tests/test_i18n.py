import pytest

from core.i18n import DEFAULT_LOCALE, normalize_locale, t


def test_normalize_locale_maps_chinese_aliases():
    assert normalize_locale("zh") == "zh-CN"
    assert normalize_locale("zh-cn") == "zh-CN"
    assert normalize_locale("中文") == "zh-CN"


def test_normalize_locale_maps_english_aliases():
    assert normalize_locale("en") == "en"
    assert normalize_locale("english") == "en"


def test_normalize_locale_returns_none_for_unknown_values():
    assert normalize_locale("klingon") is None
    assert normalize_locale("") is None
    assert normalize_locale(None) is None


def test_translate_returns_chinese_for_localized_key():
    assert t("zh-CN", "repl.goodbye") == "再见。"


def test_translate_returns_english_for_default_locale():
    assert DEFAULT_LOCALE == "en"
    assert t("en", "repl.goodbye") == "Goodbye."


def test_translate_falls_back_to_english_for_unknown_locale():
    assert t("fr", "repl.goodbye") == "Goodbye."


def test_translate_raises_key_error_for_unknown_message_key():
    with pytest.raises(KeyError):
        t("en", "missing.key")

from app.text_encoding import clean_display_text


def test_clean_display_text_repairs_cp1251_decoded_utf8_mojibake():
    mojibake = "Низька надійність центру".encode("utf-8").decode("cp1251")

    assert clean_display_text(mojibake) == "Низька надійність центру"


def test_clean_display_text_keeps_valid_cyrillic_text():
    text = "\u0420\u0438\u043d\u043e\u043a \u043f\u0440\u0438\u0434\u0430\u0442\u043d\u0438\u0439"

    assert clean_display_text(text) == text

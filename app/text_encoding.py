MOJIBAKE_MARKERS = (
    "Рќ",
    "Рё",
    "Р·",
    "СЊ",
    "Рє",
    "Р°",
    "РЅ",
    "С–",
    "Р№",
    "СЃ",
    "С‚",
    "С†",
    "Рµ",
    "СЂ",
    "Рі",
    "Р»",
    "Рѕ",
    "Рґ",
    "С‡",
    "С€",
    "СЋ",
    "СЏ",
    "С—",
    "Ð",
    "Ñ",
    "Гђ",
    "Г‘",
)


def clean_display_text(value) -> str:
    text = "" if value is None else str(value)
    if not _looks_like_mojibake(text):
        return text

    candidates = [text]
    for source_encoding, target_encoding in (
        ("cp1251", "utf-8"),
        ("cp1252", "utf-8"),
        ("latin1", "utf-8"),
    ):
        try:
            candidates.append(text.encode(source_encoding).decode(target_encoding))
        except UnicodeError:
            pass

    return min(candidates, key=_mojibake_score)


def _looks_like_mojibake(text: str) -> bool:
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def _mojibake_score(text: str) -> int:
    score = 0
    for marker in MOJIBAKE_MARKERS:
        score += text.count(marker)
    return score

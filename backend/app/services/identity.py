from __future__ import annotations

import re
import unicodedata


CREATOR_NAME = "Lakhan Prajapat"

CREATOR_REPLIES = {
    "en": f"I was created by {CREATOR_NAME}.",
    "hi": "मुझे लखन प्रजापत ने बनाया है।",
    "es": f"Fui creado por {CREATOR_NAME}.",
    "fr": f"J’ai été créé par {CREATOR_NAME}.",
    "de": f"Ich wurde von {CREATOR_NAME} erstellt.",
    "pt": f"Fui criado por {CREATOR_NAME}.",
    "it": f"Sono stato creato da {CREATOR_NAME}.",
    "id": f"Saya dibuat oleh {CREATOR_NAME}.",
    "tr": f"{CREATOR_NAME} tarafından oluşturuldum.",
    "ru": "Меня создал Лакхан Праджапат.",
    "ar": "أنشأني لاخان براجابات.",
    "zh": f"我是由 {CREATOR_NAME} 创建的。",
    "ja": f"私は {CREATOR_NAME} によって作られました。",
    "ko": f"저는 {CREATOR_NAME}에 의해 만들어졌습니다.",
}

CREATOR_PHRASES = (
    "who made you",
    "who created you",
    "who is your creator",
    "who is your developer",
    "who developed you",
    "who built you",
    "who created vasuki ai",
    "who made vasuki ai",
    "tumhe kisne banaya",
    "tumko kisne banaya",
    "tujhe kisne banaya",
    "aapko kisne banaya",
    "kisne create kiya",
    "kisne created kiya",
    "tumhara creator kaun hai",
    "tumhara developer kaun hai",
    "vasuki ai ko kisne banaya",
    "तुम्हें किसने बनाया",
    "तुमको किसने बनाया",
    "आपको किसने बनाया",
    "तुम्हारा क्रिएटर कौन है",
    "तुम्हारा डेवलपर कौन है",
    "वासुकी एआई को किसने बनाया",
    "quien te creo",
    "quién te creó",
    "quien es tu creador",
    "quién es tu creador",
    "quien te desarrollo",
    "quién te desarrolló",
    "qui t a cree",
    "qui t’a créé",
    "qui vous a cree",
    "qui vous a créé",
    "qui est ton createur",
    "qui est votre créateur",
    "wer hat dich erstellt",
    "wer hat dich erschaffen",
    "wer hat dich entwickelt",
    "wer ist dein entwickler",
    "quem te criou",
    "quem criou voce",
    "quem criou você",
    "quem e seu criador",
    "quem é seu criador",
    "chi ti ha creato",
    "chi e il tuo creatore",
    "chi è il tuo creatore",
    "chi ti ha sviluppato",
    "siapa yang membuatmu",
    "siapa penciptamu",
    "siapa pengembangmu",
    "seni kim yaratti",
    "seni kim yarattı",
    "seni kim gelistirdi",
    "seni kim geliştirdi",
    "кто тебя создал",
    "кто тебя разработал",
    "кто твой создатель",
    "من صنعك",
    "من أنشأك",
    "من طورك",
    "من هو مطورك",
    "谁创造了你",
    "谁开发了你",
    "谁制作了你",
    "誰があなたを作った",
    "誰があなたを開発した",
    "あなたの開発者は誰",
    "누가 너를 만들었",
    "누가 당신을 만들었",
    "누가 너를 개발했",
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _detect_language(text: str) -> str:
    raw = unicodedata.normalize("NFKC", text)
    normalized = _normalize(raw)

    if re.search(r"[\u0900-\u097f]", raw):
        return "hi"
    if re.search(r"[\u0600-\u06ff]", raw):
        return "ar"
    if re.search(r"[\u0400-\u04ff]", raw):
        return "ru"
    if re.search(r"[\u3040-\u30ff]", raw):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", raw):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", raw):
        return "zh"

    hints = {
        "es": ("quien", "quién", "creador", "desarrollador", "creado"),
        "fr": ("qui t", "qui vous", "créateur", "createur", "développeur"),
        "de": ("wer hat", "erstellt", "erschaffen", "entwickelt", "entwickler"),
        "pt": ("quem te", "quem criou", "criador", "desenvolvedor"),
        "it": ("chi ti", "creatore", "sviluppatore"),
        "id": ("siapa", "pencipta", "pengembang"),
        "tr": ("seni kim", "yarattı", "yaratti", "geliştirdi", "gelistirdi"),
        "hi": ("kisne", "kaun", "banaya", "tumhe", "aapko"),
    }

    for language, language_hints in hints.items():
        if any(hint in normalized for hint in language_hints):
            return language

    return "en"


def fixed_identity_reply(query: str) -> str | None:
    """Return a creator answer in the same language as the question."""
    normalized = _normalize(query)

    if any(_normalize(phrase) in normalized for phrase in CREATOR_PHRASES):
        language = _detect_language(query)
        return CREATOR_REPLIES.get(language, CREATOR_REPLIES["en"])

    self_words = (
        "you",
        "your",
        "vasuki ai",
        "tum",
        "tumhe",
        "tumko",
        "tujhe",
        "aapko",
        "तुम",
        "आप",
        "वासुकी",
    )
    creator_words = (
        "made",
        "created",
        "creator",
        "developer",
        "built",
        "developed",
        "banaya",
        "बनाया",
        "डेवलपर",
        "क्रिएटर",
    )

    if any(word in normalized for word in self_words) and any(
        word in normalized for word in creator_words
    ):
        language = _detect_language(query)
        return CREATOR_REPLIES.get(language, CREATOR_REPLIES["en"])

    return None

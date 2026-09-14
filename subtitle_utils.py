"""
Tiện ích tạo file SRT subtitle.
"""
import re


def clean_text(text: str) -> str:
    """Làm sạch văn bản để tránh TTS bị vấp."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[-1] not in ".!?;:,…":
            line += "."
        lines.append(line)
    text = " ".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(
        r"[^\w\s\.,!\?;:…àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệ"
        r"ìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
        r"\-–—\(\)\[\]\"'\/%&\n]",
        " ", text, flags=re.UNICODE | re.IGNORECASE,
    )
    text = re.sub(r"([,.!?;:])\1+", r"\1", text)
    text = re.sub(r"\s+([,.!?;:…])", r"\1", text)
    text = re.sub(r"([,.!?;:])(?=[^\s\d])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_long_sentences(text: str, max_len: int = 180) -> str:
    """Chia câu dài thành câu ngắn để TTS không bị nghẹn."""
    parts = re.split(r"(?<=[.!?…])\s+", text)
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= max_len:
            result.append(p)
            continue
        sub = re.split(r"(?<=[,;:])\s+", p)
        cur = ""
        for s in sub:
            if len(cur) + len(s) + 1 <= max_len:
                cur = (cur + " " + s).strip()
            else:
                if cur:
                    result.append(cur)
                cur = s
        if cur:
            result.append(cur)
    return " ".join(result)

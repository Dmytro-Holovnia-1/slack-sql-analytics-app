import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def artifact_filename(prefix: str, question: str, extension: str) -> str:
    normalized = _NON_ALNUM_RE.sub("_", question.lower()).strip("_")
    stem = normalized[:40] or "artifact"
    return f"{prefix}_{stem}.{extension}"

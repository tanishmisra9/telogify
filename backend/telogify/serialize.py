"""Text serialization helpers. The house style forbids em dashes anywhere in rendered
output, so every web/email string passes through strip_em_dashes as a safety net on top
of the system-prompt rule."""


def strip_em_dashes(text: str | None) -> str | None:
    if not text:
        return text
    for dash in ("—", "―", "⸺", "⸻"):  # em dash and friends
        text = text.replace(f" {dash} ", ", ").replace(dash, ", ")
    text = text.replace(" – ", " - ").replace("–", "-")  # en dash -> hyphen
    return text

"""Visual severity helpers. Colours and the stylesheet live in desktop/config/ (theme.yml, style.qss)."""
from desktop import config_loader


def urgency_kind(level: int) -> str:
    """Visual severity for an urgency level: "high", "medium" or "low" (thresholds in settings.yml)."""
    settings = config_loader.settings()
    if level >= settings.high_urgency_level:
        return "high"
    if level >= settings.medium_urgency_level:
        return "medium"
    return "low"

"""EdgeHub qfluentwidgets theme configuration."""

from qfluentwidgets import Theme, setTheme, setThemeColor, FluentIcon as FI

EDGEHUB_PRIMARY = "#0078D4"
EDGEHUB_ONLINE = "#16C60C"
EDGEHUB_OFFLINE = "#E74856"
EDGEHUB_RECONNECTING = "#FF8C00"


def apply_theme(theme: Theme = Theme.DARK):
    """Apply the EdgeHub theme with custom accent color."""
    setTheme(theme)
    setThemeColor(EDGEHUB_PRIMARY)

"""Choose the desktop adapter and expose the interface used by settings."""

from .gnome import ANCHORS, AzClockHost, HostError
from .integration import install_bridge
from .session import APP_ID, Session

PLACEMENTS = tuple(ANCHORS)
discover = AzClockHost.discover
open_session = Session.discover

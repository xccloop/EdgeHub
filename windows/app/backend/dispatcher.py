"""Publish/subscribe data dispatcher for loose coupling between
WebSocket client and UI pages."""

from typing import Type, Callable, Dict, List, Any
from .models import Telemetry, Heartbeat, DeviceEvent

Subscriber = Callable[[Any], None]


class DataDispatcher:
    """Routes typed message objects to registered subscribers."""

    def __init__(self):
        self._subscribers: Dict[Type, List[Subscriber]] = {}

    def subscribe(self, model_type: Type, callback: Subscriber):
        """Register a callback for a specific model type."""
        if model_type not in self._subscribers:
            self._subscribers[model_type] = []
        self._subscribers[model_type].append(callback)

    def unsubscribe(self, model_type: Type, callback: Subscriber):
        """Remove a previously registered callback."""
        if model_type in self._subscribers:
            try:
                self._subscribers[model_type].remove(callback)
            except ValueError:
                pass

    def dispatch(self, model: Any):
        """Send a model to all subscribers of its type."""
        model_type = type(model)
        if model_type in self._subscribers:
            for cb in self._subscribers[model_type]:
                try:
                    cb(model)
                except Exception:
                    pass

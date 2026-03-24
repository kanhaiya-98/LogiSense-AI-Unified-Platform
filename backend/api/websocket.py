from fastapi import WebSocket
from typing import List
import json


class WebSocketManager:
    """Manages all active WebSocket connections to the React dashboard."""

    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f'Dashboard connected. Total connections: {len(self.active)}')

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        print(f'Dashboard disconnected. Total connections: {len(self.active)}')

    async def broadcast(self, event: dict):
        """Send AnomalyEvent to ALL connected dashboard clients."""
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.active:
                self.active.remove(ws)


# Global singleton — imported by main.py and observer agent
ws_manager = WebSocketManager()

"""
Hot Reload System with SSE
Watches frontend files and notifies clients
"""
import asyncio
from pathlib import Path
from typing import Set, Dict, AsyncGenerator
from datetime import datetime
import hashlib

from app.config import STATIC_DIR

class HotReloadManager:
    """
    Manages hot reload for frontend files
    Uses file watching and SSE to notify clients
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: Set[asyncio.Queue] = set()
            cls._instance._file_hashes: Dict[str, str] = {}
            cls._instance._watch_dir = STATIC_DIR
            cls._instance._is_watching = False
        return cls._instance

    async def subscribe(self) -> AsyncGenerator[Dict, None]:
        """
        Subscribe to hot reload events via SSE
        Yields events when files change
        """
        queue = asyncio.Queue()
        self._subscribers.add(queue)

        # Send initial ping
        yield {
            "event": "connected",
            "timestamp": datetime.now().isoformat(),
            "watching": str(self._watch_dir)
        }

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            # Cleanup on disconnect
            self._subscribers.discard(queue)

    async def broadcast(self, event: Dict):
        """Broadcast event to all subscribers"""
        # Remove closed queues
        dead_queues = set()
        for queue in self._subscribers:
            try:
                await queue.put(event)
            except Exception:
                dead_queues.add(queue)

        self._subscribers -= dead_queues

    def _compute_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash of file"""
        try:
            return hashlib.sha256(filepath.read_bytes()).hexdigest()
        except Exception:
            return ""

    async def watch_files(self):
        """
        Watch files for changes (polling-based)
        In production, use inotify/watchdog for better performance
        """
        if self._is_watching:
            return

        self._is_watching = True

        # Initialize file hashes
        for filepath in self._watch_dir.rglob("*"):
            if filepath.is_file() and not filepath.name.startswith("."):
                self._file_hashes[str(filepath)] = self._compute_hash(filepath)

        # Watch loop
        while self._is_watching:
            await asyncio.sleep(1)  # Poll every second

            for filepath in self._watch_dir.rglob("*"):
                if not filepath.is_file() or filepath.name.startswith("."):
                    continue

                path_str = str(filepath)
                current_hash = self._compute_hash(filepath)
                old_hash = self._file_hashes.get(path_str)

                # File changed or new
                if current_hash != old_hash:
                    self._file_hashes[path_str] = current_hash

                    # Determine reload type
                    ext = filepath.suffix.lower()
                    reload_type = {
                        ".css": "reload-css",
                        ".js": "reload-js",
                        ".html": "reload-html",
                    }.get(ext, "reload-page")

                    event = {
                        "event": reload_type,
                        "file": filepath.name,
                        "path": str(filepath.relative_to(self._watch_dir)),
                        "timestamp": datetime.now().isoformat()
                    }

                    await self.broadcast(event)

    def stop_watching(self):
        """Stop watching files"""
        self._is_watching = False

    async def trigger_reload(self, reload_type: str = "reload-page", file: str = "manual"):
        """Manually trigger a reload event"""
        event = {
            "event": reload_type,
            "file": file,
            "timestamp": datetime.now().isoformat(),
            "manual": True
        }
        await self.broadcast(event)

# Global instance
hot_reload = HotReloadManager()

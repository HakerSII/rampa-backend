import asyncio
from collections.abc import AsyncIterator
from pathlib import Path


class LocalFileStorage:
    """Stores files under media_dir, served by the app at /media/<name>."""

    def __init__(self, media_dir: str):
        self.root = Path(media_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, chunks: AsyncIterator[bytes], name: str) -> tuple[str, str]:
        path = self.root / name
        data = bytearray()
        async for chunk in chunks:
            data.extend(chunk)
        await asyncio.to_thread(path.write_bytes, bytes(data))
        return str(path), f"/media/{name}"

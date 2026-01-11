"""
Phi-3 Subprocess Client
Manages a subprocess for Phi-3 inference to isolate crashes.
"""
import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("phi3_client")

PHI3_SCRIPT = Path(__file__).parent.parent / "phi3_subprocess.py"
PYTHON_PATH = Path(__file__).parent.parent / "venv" / "bin" / "python"


class Phi3Client:
    """Async client for Phi-3 subprocess"""

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.ready = False
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        """Start the Phi-3 subprocess"""
        if self.process and self.process.returncode is None:
            return self.ready

        try:
            log.info("Starting Phi-3 subprocess...")
            self.process = await asyncio.create_subprocess_exec(
                str(PYTHON_PATH),
                str(PHI3_SCRIPT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for ready signal with timeout
            try:
                line = await asyncio.wait_for(
                    self.process.stdout.readline(),
                    timeout=120.0  # Model loading can take time
                )
                response = json.loads(line.decode().strip())
                if response.get("status") == "ready":
                    self.ready = True
                    log.info("Phi-3 subprocess ready")
                    return True
                else:
                    log.error(f"Phi-3 startup error: {response}")
                    return False
            except asyncio.TimeoutError:
                log.error("Phi-3 subprocess startup timeout")
                await self.stop()
                return False

        except Exception as e:
            log.error(f"Failed to start Phi-3 subprocess: {e}")
            return False

    async def stop(self):
        """Stop the Phi-3 subprocess"""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
            except Exception:
                pass
            finally:
                self.process = None
                self.ready = False
                log.info("Phi-3 subprocess stopped")

    async def generate(self, prompt: str, max_tokens: int = 384, temperature: float = 0.3, timeout: float = 60.0) -> str:
        """Generate response from Phi-3"""
        async with self._lock:
            # Check if process is alive
            if not self.process or self.process.returncode is not None:
                log.warning("Phi-3 subprocess not running, restarting...")
                if not await self.start():
                    raise RuntimeError("Failed to start Phi-3 subprocess")

            try:
                # Send request
                request = json.dumps({
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }) + "\n"
                self.process.stdin.write(request.encode())
                await self.process.stdin.drain()

                # Read response with timeout
                line = await asyncio.wait_for(
                    self.process.stdout.readline(),
                    timeout=timeout
                )

                if not line:
                    raise RuntimeError("Phi-3 subprocess closed unexpectedly")

                response = json.loads(line.decode().strip())

                if "error" in response:
                    raise RuntimeError(f"Phi-3 error: {response['error']}")

                return response.get("result", "")

            except asyncio.TimeoutError:
                log.error("Phi-3 generation timeout, restarting subprocess...")
                await self.stop()
                raise RuntimeError("Phi-3 generation timeout")
            except Exception as e:
                log.error(f"Phi-3 generation error: {e}")
                # Restart subprocess on error
                await self.stop()
                raise

    def is_ready(self) -> bool:
        """Check if subprocess is ready"""
        return self.ready and self.process and self.process.returncode is None


# Global client instance
phi3_client = Phi3Client()


async def init_phi3():
    """Initialize the Phi-3 subprocess"""
    return await phi3_client.start()


async def shutdown_phi3():
    """Shutdown the Phi-3 subprocess"""
    await phi3_client.stop()

"""
Platform-agnostic generation client layer.

Provides a ``GenerationProvider`` ABC and concrete implementations for each
supported AI video generation platform.  The existing ``HiggsfieldApiClient``
remains unchanged; a thin wrapper adapts it to this interface.

Each provider follows the same lifecycle:
    1. ``submit_text_to_video(prompt, ...)`` or ``submit_image_to_video(image_url, prompt, ...)``
    2. ``poll_status(request_id)`` until terminal state
    3. Result contains ``video_url`` and optional ``image_url``
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# =====================================================================
#  Shared data structures
# =====================================================================

@dataclass
class GenerationResult:
    """Uniform result from any provider."""

    request_id: str = ""
    platform_id: str = ""
    model_id: str = ""
    status: str = "pending"
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def success(self) -> bool:
        return self.status == "completed" and self.error is None


# =====================================================================
#  Base class
# =====================================================================

class GenerationProvider(ABC):
    """Abstract interface for AI video generation platforms."""

    platform_id: str = ""
    platform_name: str = ""

    def __init__(self, api_key: str = "", **kwargs):
        self.api_key = api_key

    @abstractmethod
    def submit_text_to_video(
        self,
        prompt: str,
        *,
        model: str = "",
        duration: int = 5,
        aspect_ratio: str = "16:9",
        **kwargs,
    ) -> GenerationResult:
        """Submit a text-to-video generation request."""

    @abstractmethod
    def submit_image_to_video(
        self,
        image_url: str,
        prompt: str,
        *,
        model: str = "",
        duration: int = 5,
        aspect_ratio: str = "16:9",
        **kwargs,
    ) -> GenerationResult:
        """Submit an image-to-video generation request."""

    @abstractmethod
    def poll_status(self, request_id: str) -> GenerationResult:
        """Check the status of a previously submitted request."""

    def cancel(self, request_id: str) -> bool:
        """Cancel a pending request. Returns True if successful."""
        return False

    # -- Helpers -------------------------------------------------------

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers=hdrs, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"{exc.code} {exc.reason}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc

    def _get_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        hdrs = {}
        if headers:
            hdrs.update(headers)
        req = Request(url, headers=hdrs, method="GET")
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"{exc.code} {exc.reason}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc

    def _bearer_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


# =====================================================================
#  Provider registry
# =====================================================================

PROVIDER_REGISTRY: Dict[str, type[GenerationProvider]] = {}


def _register(cls: type[GenerationProvider]) -> type[GenerationProvider]:
    PROVIDER_REGISTRY[cls.platform_id] = cls
    return cls


def get_provider(platform_id: str, api_key: str = "", **kwargs) -> Optional[GenerationProvider]:
    """Instantiate the provider for *platform_id*, or None."""
    cls = PROVIDER_REGISTRY.get(platform_id)
    if cls is None:
        return None
    return cls(api_key=api_key, **kwargs)


# =====================================================================
#  Higgsfield (wraps existing HiggsfieldApiClient)
# =====================================================================

@_register
class HiggsfieldProvider(GenerationProvider):
    """Wraps the existing HiggsfieldApiClient as a GenerationProvider."""

    platform_id = "higgsfield"
    platform_name = "Higgsfield"

    def __init__(self, api_key: str = "", api_key_secret: str = "", **kwargs):
        super().__init__(api_key=api_key)
        self.api_key_secret = api_key_secret
        self._client = None

    def _get_client(self):
        if self._client is None:
            from .higgsfield_api_client import HiggsfieldApiClient, ApiConfig
            self._client = HiggsfieldApiClient(ApiConfig(
                api_key=self.api_key,
                api_key_secret=self.api_key_secret,
            ))
        return self._client

    def submit_text_to_video(self, prompt, *, model="", duration=5, aspect_ratio="16:9", **kwargs):
        client = self._get_client()
        req = client.submit_video(
            prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            model_id=model or None,
        )
        return GenerationResult(
            request_id=req.request_id,
            platform_id=self.platform_id,
            model_id=req.model_id,
            status=req.status,
        )

    def submit_image_to_video(self, image_url, prompt, *, model="", duration=5, aspect_ratio="16:9", **kwargs):
        client = self._get_client()
        req = client.submit_video(
            prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            model_id=model or None,
            image_url=image_url,
        )
        return GenerationResult(
            request_id=req.request_id,
            platform_id=self.platform_id,
            model_id=req.model_id,
            status=req.status,
        )

    def poll_status(self, request_id):
        client = self._get_client()
        req = client.poll(request_id)
        return GenerationResult(
            request_id=req.request_id,
            platform_id=self.platform_id,
            model_id=req.model_id,
            status=req.status,
            video_url=req.video_url,
            image_url=req.image_url,
            error=req.error,
        )


# =====================================================================
#  Runway
# =====================================================================

@_register
class RunwayProvider(GenerationProvider):
    """Runway Gen-4/Gen-4.5 API client.

    API: POST https://api.dev.runwayml.com/v1/image_to_video
    Auth: Bearer token
    """

    platform_id = "runway"
    platform_name = "Runway"
    BASE_URL = "https://api.dev.runwayml.com/v1"

    def submit_text_to_video(self, prompt, *, model="gen4.5", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "model": model,
            "promptText": prompt,
            "duration": duration,
            "ratio": aspect_ratio.replace(":", ":"),
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/image_to_video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def submit_image_to_video(self, image_url, prompt, *, model="gen4.5", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "model": model,
            "promptImage": image_url,
            "promptText": prompt,
            "duration": duration,
            "ratio": aspect_ratio.replace(":", ":"),
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/image_to_video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def poll_status(self, request_id):
        try:
            resp = self._get_json(
                f"{self.BASE_URL}/tasks/{request_id}",
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(e),
            )

        status_map = {"SUCCEEDED": "completed", "FAILED": "failed", "RUNNING": "processing"}
        status = status_map.get(resp.get("status", ""), "pending")
        output = resp.get("output", [])
        video_url = output[0] if output else None

        return GenerationResult(
            request_id=request_id,
            platform_id=self.platform_id,
            status=status,
            video_url=video_url,
            error=resp.get("failure") or resp.get("failureCode"),
            raw_response=resp,
        )


# =====================================================================
#  Sora (OpenAI)
# =====================================================================

@_register
class SoraProvider(GenerationProvider):
    """OpenAI Sora video generation API.

    API: POST https://api.openai.com/v1/video/generations
    Auth: Bearer token (OpenAI API key)
    """

    platform_id = "sora"
    platform_name = "Sora"
    BASE_URL = "https://api.openai.com/v1"

    def submit_text_to_video(self, prompt, *, model="sora-2", duration=8, aspect_ratio="16:9", **kwargs):
        ar_map = {"16:9": "landscape", "9:16": "portrait", "1:1": "square"}
        payload = {
            "model": model,
            "input": prompt,
            "size": ar_map.get(aspect_ratio, "landscape"),
            "duration": duration,
            "n": 1,
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/video/generations",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def submit_image_to_video(self, image_url, prompt, *, model="sora-2", duration=8, aspect_ratio="16:9", **kwargs):
        ar_map = {"16:9": "landscape", "9:16": "portrait", "1:1": "square"}
        payload = {
            "model": model,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": image_url},
            ],
            "size": ar_map.get(aspect_ratio, "landscape"),
            "duration": duration,
            "n": 1,
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/video/generations",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def poll_status(self, request_id):
        try:
            resp = self._get_json(
                f"{self.BASE_URL}/video/generations/{request_id}",
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(e),
            )

        status = resp.get("status", "pending")
        video_url = None
        data = resp.get("data", [])
        if data and isinstance(data, list):
            video_url = data[0].get("url")

        return GenerationResult(
            request_id=request_id,
            platform_id=self.platform_id,
            status="completed" if status == "completed" else ("failed" if status == "failed" else "processing"),
            video_url=video_url,
            error=resp.get("error"),
            raw_response=resp,
        )


# =====================================================================
#  Kling
# =====================================================================

@_register
class KlingProvider(GenerationProvider):
    """Kling video generation API.

    API: POST https://klingapi.com/v1/videos/text2video
    Auth: Bearer token
    """

    platform_id = "kling"
    platform_name = "Kling"
    BASE_URL = "https://klingapi.com/v1"

    def submit_text_to_video(self, prompt, *, model="kling-3.0-pro", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "model_name": model,
            "prompt": prompt,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
            "mode": kwargs.get("mode", "std"),
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/videos/text2video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        task = resp.get("data", {})
        return GenerationResult(
            request_id=task.get("task_id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def submit_image_to_video(self, image_url, prompt, *, model="kling-3.0-pro", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "model_name": model,
            "prompt": prompt,
            "image": image_url,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
            "mode": kwargs.get("mode", "std"),
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/videos/image2video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        task = resp.get("data", {})
        return GenerationResult(
            request_id=task.get("task_id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def poll_status(self, request_id):
        try:
            resp = self._get_json(
                f"{self.BASE_URL}/videos/{request_id}",
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(e),
            )

        task = resp.get("data", {})
        status_raw = task.get("task_status", "submitted")
        status_map = {"succeed": "completed", "failed": "failed", "processing": "processing"}
        status = status_map.get(status_raw, "pending")
        works = task.get("task_result", {}).get("videos", [])
        video_url = works[0].get("url") if works else None

        return GenerationResult(
            request_id=request_id,
            platform_id=self.platform_id,
            status=status,
            video_url=video_url,
            error=task.get("task_status_msg"),
            raw_response=resp,
        )


# =====================================================================
#  Luma (Dream Machine)
# =====================================================================

@_register
class LumaProvider(GenerationProvider):
    """Luma Dream Machine (Ray 2) API.

    API: POST https://api.lumalabs.ai/dream-machine/v1/generations
    Auth: Bearer token
    """

    platform_id = "luma"
    platform_name = "Luma Dream Machine"
    BASE_URL = "https://api.lumalabs.ai/dream-machine/v1"

    def submit_text_to_video(self, prompt, *, model="ray-2", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
        }
        if kwargs.get("loop"):
            payload["loop"] = True
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/generations",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def submit_image_to_video(self, image_url, prompt, *, model="ray-2", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "keyframes": {
                "frame0": {"type": "image", "url": image_url},
            },
        }
        if kwargs.get("loop"):
            payload["loop"] = True
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/generations",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def poll_status(self, request_id):
        try:
            resp = self._get_json(
                f"{self.BASE_URL}/generations/{request_id}",
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(e),
            )

        state = resp.get("state", "queued")
        status_map = {"completed": "completed", "failed": "failed", "processing": "processing"}
        status = status_map.get(state, "pending")
        assets = resp.get("assets", {})
        video_url = assets.get("video")

        return GenerationResult(
            request_id=request_id,
            platform_id=self.platform_id,
            status=status,
            video_url=video_url,
            error=resp.get("failure_reason"),
            raw_response=resp,
        )


# =====================================================================
#  Veo (Google)
# =====================================================================

@_register
class VeoProvider(GenerationProvider):
    """Google Veo video generation via Generative Language API.

    API: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:predictVideo
    Auth: API key as query parameter
    """

    platform_id = "veo"
    platform_name = "Veo"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def submit_text_to_video(self, prompt, *, model="veo-3.0-generate", duration=6, aspect_ratio="16:9", **kwargs):
        ar_map = {"16:9": "16:9", "9:16": "9:16"}
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "aspectRatio": ar_map.get(aspect_ratio, "16:9"),
                "durationSeconds": duration,
                "sampleCount": 1,
            },
        }
        url = f"{self.BASE_URL}/models/{model}:predictVideo?key={self.api_key}"
        try:
            resp = self._post_json(url, payload)
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        op_name = resp.get("name", "")
        return GenerationResult(
            request_id=op_name,
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def submit_image_to_video(self, image_url, prompt, *, model="veo-3.0-generate", duration=6, aspect_ratio="16:9", **kwargs):
        ar_map = {"16:9": "16:9", "9:16": "9:16"}
        payload = {
            "instances": [{
                "prompt": prompt,
                "image": {"gcsUri": image_url} if image_url.startswith("gs://") else {"imageUrl": image_url},
            }],
            "parameters": {
                "aspectRatio": ar_map.get(aspect_ratio, "16:9"),
                "durationSeconds": duration,
                "sampleCount": 1,
            },
        }
        url = f"{self.BASE_URL}/models/{model}:predictVideo?key={self.api_key}"
        try:
            resp = self._post_json(url, payload)
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        op_name = resp.get("name", "")
        return GenerationResult(
            request_id=op_name,
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def poll_status(self, request_id):
        url = f"{self.BASE_URL}/{request_id}?key={self.api_key}"
        try:
            resp = self._get_json(url)
        except RuntimeError as e:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(e),
            )

        done = resp.get("done", False)
        if not done:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="processing", raw_response=resp,
            )

        error_detail = resp.get("error")
        if error_detail:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(error_detail.get("message", "")),
                raw_response=resp,
            )

        result_resp = resp.get("response", {})
        videos = result_resp.get("videos", [])
        video_url = videos[0].get("uri") if videos else None

        return GenerationResult(
            request_id=request_id,
            platform_id=self.platform_id,
            status="completed",
            video_url=video_url,
            raw_response=resp,
        )


# =====================================================================
#  Pika (via fal.ai)
# =====================================================================

@_register
class PikaProvider(GenerationProvider):
    """Pika video generation via fal.ai proxy.

    API: POST https://fal.run/fal-ai/pika/v2.2/text-to-video
    Auth: Bearer token (fal.ai key)
    """

    platform_id = "pika"
    platform_name = "Pika"
    BASE_URL = "https://fal.run/fal-ai/pika"

    def submit_text_to_video(self, prompt, *, model="pika-2.2", duration=5, aspect_ratio="16:9", **kwargs):
        version = model.split("-")[-1] if "-" in model else "2.2"
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        if "motion_strength" in kwargs:
            payload["motion_strength"] = kwargs["motion_strength"]
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/v{version}/text-to-video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("request_id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending" if resp.get("request_id") else "completed",
            video_url=resp.get("video", {}).get("url"),
            raw_response=resp,
        )

    def submit_image_to_video(self, image_url, prompt, *, model="pika-2.2", duration=5, aspect_ratio="16:9", **kwargs):
        version = model.split("-")[-1] if "-" in model else "2.2"
        payload = {
            "prompt": prompt,
            "image_url": image_url,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        if "motion_strength" in kwargs:
            payload["motion_strength"] = kwargs["motion_strength"]
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/v{version}/image-to-video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("request_id", ""),
            platform_id=self.platform_id,
            model_id=model,
            status="pending" if resp.get("request_id") else "completed",
            video_url=resp.get("video", {}).get("url"),
            raw_response=resp,
        )

    def poll_status(self, request_id):
        try:
            resp = self._get_json(
                f"https://queue.fal.run/fal-ai/pika/requests/{request_id}/status",
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(e),
            )

        status_raw = resp.get("status", "IN_QUEUE")
        status_map = {"COMPLETED": "completed", "FAILED": "failed", "IN_PROGRESS": "processing"}
        status = status_map.get(status_raw, "pending")
        video_url = None
        if status == "completed":
            result_resp = resp.get("response", {})
            video_url = result_resp.get("video", {}).get("url")

        return GenerationResult(
            request_id=request_id,
            platform_id=self.platform_id,
            status=status,
            video_url=video_url,
            raw_response=resp,
        )


# =====================================================================
#  Minimax / Hailuo (via AI/ML API)
# =====================================================================

@_register
class MinimaxProvider(GenerationProvider):
    """Minimax / Hailuo video generation via AI/ML API.

    API: POST https://api.aimlapi.com/v2/generate/video
    Auth: Bearer token
    """

    platform_id = "minimax"
    platform_name = "Minimax / Hailuo"
    BASE_URL = "https://api.aimlapi.com/v2"

    def submit_text_to_video(self, prompt, *, model="hailuo-2.3", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/generate/video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", resp.get("generation_id", "")),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def submit_image_to_video(self, image_url, prompt, *, model="hailuo-2.3", duration=5, aspect_ratio="16:9", **kwargs):
        payload = {
            "model": model,
            "prompt": prompt,
            "first_frame_image": image_url,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        try:
            resp = self._post_json(
                f"{self.BASE_URL}/generate/video",
                payload,
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(platform_id=self.platform_id, status="failed", error=str(e))

        return GenerationResult(
            request_id=resp.get("id", resp.get("generation_id", "")),
            platform_id=self.platform_id,
            model_id=model,
            status="pending",
        )

    def poll_status(self, request_id):
        try:
            resp = self._get_json(
                f"{self.BASE_URL}/generate/video/{request_id}",
                headers=self._bearer_headers(),
            )
        except RuntimeError as e:
            return GenerationResult(
                request_id=request_id, platform_id=self.platform_id,
                status="failed", error=str(e),
            )

        status_raw = resp.get("status", "queued")
        status_map = {"completed": "completed", "failed": "failed", "processing": "processing"}
        status = status_map.get(status_raw, "pending")
        video_url = resp.get("video_url") or resp.get("output", {}).get("video_url")

        return GenerationResult(
            request_id=request_id,
            platform_id=self.platform_id,
            status=status,
            video_url=video_url,
            error=resp.get("error"),
            raw_response=resp,
        )

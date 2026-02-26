"""
Higgsfield Platform API Client.

Async queue-based integration with the Higgsfield generation API.
Supports both text-to-image (hero frame) and image-to-video generation.

API reference: https://docs.higgsfield.ai

Full pipeline:
  1. Generate hero frame   — text-to-image via Soul / Nano Banana
  2. Generate video clip   — image-to-video via DoP / Kling / Seedance
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


BASE_URL = "https://platform.higgsfield.ai"

# ── Image generation models (text-to-image) ─────────────────────
IMAGE_MODELS = {
    "higgsfield-ai/soul/standard": "Soul Standard — creative character images",
    "higgsfield-ai/soul/2.0": "Soul 2.0 — fashion-forward, cultural fluency",
    "higgsfield-ai/nano-banana/pro": "Nano Banana Pro — 4K image generation",
}

# ── Video generation models (image-to-video) ────────────────────
VIDEO_MODELS = {
    "higgsfield-ai/dop/standard": "DoP Standard",
    "higgsfield-ai/dop/preview": "DoP Preview",
    "kling-video/v2.1/pro/image-to-video": "Kling 2.1 Pro",
    "kling-video/v3.0/pro/image-to-video": "Kling 3.0 Pro",
    "bytedance/seedance/v1/pro/image-to-video": "Seedance Pro",
}

AVAILABLE_MODELS = {**IMAGE_MODELS, **VIDEO_MODELS}


@dataclass
class GenerationRequest:
    """Represents a single generation request (image or video)."""

    request_id: str = ""
    model_id: str = ""
    status: str = "pending"
    status_url: str = ""
    cancel_url: str = ""
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    segment_number: int = 0


@dataclass
class PipelineResult:
    """Result of a full hero-frame-to-video pipeline run for one segment."""

    segment_number: int = 0
    hero_frame_url: Optional[str] = None
    video_url: Optional[str] = None
    image_request: Optional[GenerationRequest] = None
    video_request: Optional[GenerationRequest] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.video_url is not None and self.error is None


@dataclass
class ApiConfig:
    """Higgsfield API authentication and settings."""

    api_key: str = ""
    api_key_secret: str = ""
    webhook_url: str = ""
    image_model: str = "higgsfield-ai/soul/standard"
    video_model: str = "higgsfield-ai/dop/standard"

    @property
    def auth_header(self) -> str:
        return f"Key {self.api_key}:{self.api_key_secret}"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key_secret)

    def to_dict(self) -> Dict[str, str]:
        return {
            "api_key": self.api_key,
            "api_key_secret": self.api_key_secret,
            "webhook_url": self.webhook_url,
            "image_model": self.image_model,
            "video_model": self.video_model,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "ApiConfig":
        return cls(
            api_key=data.get("api_key", ""),
            api_key_secret=data.get("api_key_secret", ""),
            webhook_url=data.get("webhook_url", ""),
            image_model=data.get("image_model", "higgsfield-ai/soul/standard"),
            video_model=data.get("video_model", "higgsfield-ai/dop/standard"),
        )


class HiggsfieldApiClient:
    """Client for the Higgsfield Platform API.

    Supports both image generation (hero frames) and video generation.

    Usage — full pipeline::

        client = HiggsfieldApiClient(ApiConfig(
            api_key="...", api_key_secret="...",
            image_model="higgsfield-ai/soul/standard",
            video_model="higgsfield-ai/dop/standard",
        ))
        result = client.run_pipeline(
            keyframe_prompt="Medium Shot of detective in rain-soaked alley...",
            video_prompt="Camera slowly dollies in as subject turns head",
            duration=5,
            aspect_ratio="16:9",
        )
        print(result.hero_frame_url)  # Generated hero frame
        print(result.video_url)       # Final video clip

    Usage — image only::

        req = client.submit_text_to_image(
            prompt="Medium Shot of detective in rain-soaked alley...",
            aspect_ratio="16:9",
        )
        result = client.poll_until_complete(req.request_id)
        print(result.image_url)

    Usage — video from existing image::

        req = client.submit_image_to_video(
            image_url="https://example.com/hero-frame.jpg",
            prompt="Camera slowly dollies in as subject turns head",
            duration=5,
        )
        result = client.poll_until_complete(req.request_id)
        print(result.video_url)
    """

    def __init__(self, config: ApiConfig):
        self.config = config

    # ── Text-to-Image (Hero Frame Generation) ────────────────────

    def submit_text_to_image(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        model_id: Optional[str] = None,
    ) -> GenerationRequest:
        """Submit a text-to-image request to generate a hero frame.

        Uses the Soul or Nano Banana model to create the keyframe image
        that will serve as the starting point for video generation.
        """
        model = model_id or self.config.image_model
        url = f"{BASE_URL}/{model}"
        if self.config.webhook_url:
            url += f"?hf_webhook={self.config.webhook_url}"

        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }

        data = self._post(url, payload)

        return GenerationRequest(
            request_id=data.get("request_id", ""),
            model_id=model,
            status=data.get("status", "queued"),
            status_url=data.get("status_url", ""),
            cancel_url=data.get("cancel_url", ""),
        )

    # ── Image-to-Video ───────────────────────────────────────────

    def submit_image_to_video(
        self,
        image_url: str,
        prompt: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        model_id: Optional[str] = None,
    ) -> GenerationRequest:
        """Submit an image-to-video generation request.

        Takes a hero frame image URL and a video/motion prompt to produce
        an animated video clip.
        """
        model = model_id or self.config.video_model
        url = f"{BASE_URL}/{model}"
        if self.config.webhook_url:
            url += f"?hf_webhook={self.config.webhook_url}"

        payload = {
            "image_url": image_url,
            "prompt": prompt,
            "duration": duration,
        }

        data = self._post(url, payload)

        return GenerationRequest(
            request_id=data.get("request_id", ""),
            model_id=model,
            status=data.get("status", "queued"),
            status_url=data.get("status_url", ""),
            cancel_url=data.get("cancel_url", ""),
        )

    # ── Full Pipeline (Image + Video) ────────────────────────────

    def run_pipeline(
        self,
        keyframe_prompt: str,
        video_prompt: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        image_model_id: Optional[str] = None,
        video_model_id: Optional[str] = None,
        hero_frame_url: Optional[str] = None,
        segment_number: int = 0,
        max_wait_seconds: int = 600,
        poll_interval: float = 5.0,
        on_status_change: Optional[Callable[[str, GenerationRequest], None]] = None,
    ) -> PipelineResult:
        """Run the full hero-frame-to-video pipeline for one segment.

        Steps:
          1. Generate hero frame from keyframe_prompt (or use hero_frame_url)
          2. Generate video from hero frame + video_prompt

        Args:
            keyframe_prompt: Popcorn-style prompt for hero frame generation.
            video_prompt: Motion/camera/dialogue prompt for video generation.
            duration: Video clip duration in seconds.
            aspect_ratio: Frame aspect ratio (e.g. "16:9").
            resolution: Image resolution (e.g. "720p").
            image_model_id: Override image model (default from config).
            video_model_id: Override video model (default from config).
            hero_frame_url: Skip image generation — use this URL directly.
            segment_number: Segment identifier for tracking.
            max_wait_seconds: Max time to wait for each generation step.
            poll_interval: Seconds between status polls.
            on_status_change: Callback ``(stage, request)`` where stage is
                "image" or "video".
        """
        result = PipelineResult(segment_number=segment_number)

        def _notify(stage: str, req: GenerationRequest):
            if on_status_change:
                on_status_change(stage, req)

        # Step 1: Generate hero frame (or use existing URL)
        if hero_frame_url:
            result.hero_frame_url = hero_frame_url
        else:
            try:
                img_req = self.submit_text_to_image(
                    prompt=keyframe_prompt,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    model_id=image_model_id,
                )
                result.image_request = img_req

                img_result = self.poll_until_complete(
                    img_req.request_id,
                    max_wait_seconds=max_wait_seconds,
                    poll_interval=poll_interval,
                    on_status_change=lambda r: _notify("image", r),
                )
                result.image_request = img_result

                if img_result.status != "completed" or not img_result.image_url:
                    result.error = (
                        f"Hero frame generation failed: "
                        f"{img_result.error or img_result.status}"
                    )
                    return result

                result.hero_frame_url = img_result.image_url

            except ApiError as e:
                result.error = f"Hero frame API error: {e}"
                return result

        # Step 2: Generate video from hero frame
        try:
            vid_req = self.submit_image_to_video(
                image_url=result.hero_frame_url,
                prompt=video_prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                model_id=video_model_id,
            )
            result.video_request = vid_req

            vid_result = self.poll_until_complete(
                vid_req.request_id,
                max_wait_seconds=max_wait_seconds,
                poll_interval=poll_interval,
                on_status_change=lambda r: _notify("video", r),
            )
            result.video_request = vid_result

            if vid_result.status != "completed" or not vid_result.video_url:
                result.error = (
                    f"Video generation failed: "
                    f"{vid_result.error or vid_result.status}"
                )
                return result

            result.video_url = vid_result.video_url

        except ApiError as e:
            result.error = f"Video API error: {e}"

        return result

    # ── Status & Control ─────────────────────────────────────────

    def check_status(self, request_id: str) -> GenerationRequest:
        """Check the status of a generation request (image or video)."""
        url = f"{BASE_URL}/requests/{request_id}/status"
        data = self._get(url)

        req = GenerationRequest(
            request_id=data.get("request_id", request_id),
            status=data.get("status", "unknown"),
            status_url=data.get("status_url", ""),
            cancel_url=data.get("cancel_url", ""),
        )

        if data.get("video"):
            req.video_url = data["video"].get("url")
        if data.get("images"):
            req.image_url = data["images"][0].get("url") if data["images"] else None
        if data.get("error"):
            req.error = data["error"]

        return req

    def cancel_request(self, request_id: str) -> bool:
        """Cancel a queued request. Returns True if cancellation succeeded."""
        url = f"{BASE_URL}/requests/{request_id}/cancel"
        try:
            self._post(url, {})
            return True
        except ApiError as e:
            if e.status_code == 400:
                return False
            raise

    def poll_until_complete(
        self,
        request_id: str,
        max_wait_seconds: int = 600,
        poll_interval: float = 5.0,
        on_status_change: Optional[Callable[[GenerationRequest], None]] = None,
    ) -> GenerationRequest:
        """Poll the status endpoint until the request reaches a terminal state.

        Terminal states: completed, failed, nsfw.
        """
        terminal = {"completed", "failed", "nsfw"}
        start = time.time()
        last_status = ""

        while time.time() - start < max_wait_seconds:
            req = self.check_status(request_id)

            if req.status != last_status:
                last_status = req.status
                if on_status_change:
                    on_status_change(req)

            if req.status in terminal:
                return req

            time.sleep(poll_interval)

        req = self.check_status(request_id)
        if req.status not in terminal:
            req.status = "timeout"
            req.error = f"Polling timed out after {max_wait_seconds}s"
        return req

    # ── HTTP helpers ──────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.config.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, headers=self._headers(), method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            raise ApiError(
                f"HTTP {e.code}: {e.reason}",
                status_code=e.code,
                response_body=e.read().decode("utf-8", errors="replace"),
            ) from e
        except URLError as e:
            raise ApiError(f"Connection error: {e.reason}") from e

    def _get(self, url: str) -> Dict[str, Any]:
        req = Request(url, headers=self._headers(), method="GET")
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            raise ApiError(
                f"HTTP {e.code}: {e.reason}",
                status_code=e.code,
                response_body=e.read().decode("utf-8", errors="replace"),
            ) from e
        except URLError as e:
            raise ApiError(f"Connection error: {e.reason}") from e


class ApiError(Exception):
    """Raised when the Higgsfield API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        response_body: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

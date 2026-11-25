"""Value types for the Instagram publisher.

The shapes here mirror Meta's publishing parameters rather than inventing a
richer model: a container is created from media, then published. Anything Meta
does not support (native scheduling, binary upload, alt text on reels/stories)
is rejected here with a clear message instead of failing deep inside an API
call.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlparse

from .errors import ValidationError

# Instagram's documented caption limit. Kept as a guard so a client cannot
# queue a caption Meta will reject; confirm the current value in the reference
# before onboarding a client.
MAX_CAPTION_CHARS = 2200


class PostKind(StrEnum):
    """The publishable kinds this module supports."""

    IMAGE = "image"
    VIDEO = "video"
    REEL = "reel"
    STORY = "story"
    CAROUSEL = "carousel"


# Kinds that go through Meta's ``media_type`` parameter, and the value used.
MEDIA_TYPE_BY_KIND = {
    PostKind.VIDEO: "VIDEO",
    PostKind.REEL: "REELS",
    PostKind.STORY: "STORIES",
    PostKind.CAROUSEL: "CAROUSEL",
}


@dataclass(frozen=True)
class MediaItem:
    """One media object, hosted where Meta can fetch it.

    Meta cURLs the URL at publish time, so it must be publicly reachable then -
    not merely when the post was queued. ``alt_text`` is only valid for image
    posts: Meta's content-publishing guide states that reels and stories do not
    support the ``alt_text`` field, so we refuse it for those kinds.
    """

    url: str
    alt_text: str = ""

    def is_video(self) -> bool:
        path = urlparse(self.url).path.lower()
        return path.endswith((".mp4", ".mov", ".m4v"))


@dataclass(frozen=True)
class Post:
    """A post to publish, or to queue on the calendar."""

    account_id: str
    client_id: str
    kind: PostKind
    caption: str = ""
    media: tuple[MediaItem, ...] = field(default_factory=tuple)
    idempotency_key: str = ""
    scheduled_at: str = ""  # ISO-8601, only meaningful on the calendar

    def media_urls(self) -> tuple[str, ...]:
        return tuple(item.url for item in self.media)


@dataclass(frozen=True)
class PublishResult:
    """What happened when a post was published (or planned, in a dry run)."""

    account_id: str
    client_id: str
    kind: PostKind
    container_id: str = ""
    post_id: str = ""
    dry_run: bool = False
    steps: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "client_id": self.client_id,
            "kind": self.kind.value,
            "container_id": self.container_id,
            "post_id": self.post_id,
            "dry_run": self.dry_run,
            "steps": list(self.steps),
        }


def _is_public_https(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False, "media must be served over https"
    if parsed.username or parsed.password:
        return False, "media url must not embed credentials"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "media url has no host"
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False, "media must be on a public host, not localhost"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True, ""
    if address.is_private or address.is_loopback or address.is_reserved or address.is_link_local:
        return False, "media must be on a public host, not a private address"
    return True, ""


def validate_post(post: Post) -> None:
    """Raise ``ValidationError`` unless the post can be published as described.

    These are the constraints Meta documents (media fetched from a public URL,
    alt text only on images, carousels of up to 20 items) plus our own caption
    guard. Anything not verified against Meta's reference is deliberately not
    enforced here.
    """
    if not post.account_id:
        raise ValidationError("post has no account_id")
    if not post.client_id:
        raise ValidationError("post has no client_id")
    if len(post.caption) > MAX_CAPTION_CHARS:
        raise ValidationError(
            f"caption is {len(post.caption)} characters; the limit is {MAX_CAPTION_CHARS}"
        )

    if post.kind is PostKind.CAROUSEL:
        if len(post.media) < 2:
            raise ValidationError("a carousel needs at least 2 media items")
        if len(post.media) > 20:
            raise ValidationError("a carousel may contain at most 20 media items")
    elif len(post.media) != 1:
        raise ValidationError(f"{post.kind.value} posts need exactly one media item")

    for item in post.media:
        ok, reason = _is_public_https(item.url)
        if not ok:
            raise ValidationError(f"media {item.url!r}: {reason}")
        if item.alt_text and post.kind in (PostKind.STORY, PostKind.REEL):
            raise ValidationError(
                "alt_text is only supported on image posts; Meta states that "
                "reels and stories do not support it"
            )

    if post.kind is PostKind.REEL and not post.media[0].is_video():
        raise ValidationError("a reel needs a video media item")
    if post.kind is PostKind.VIDEO and not post.media[0].is_video():
        raise ValidationError("a video post needs a video media item")


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, assuming UTC when no offset is given."""
    if not value or not _ISO_RE.match(value):
        raise ValidationError(f"not an ISO-8601 timestamp: {value!r}")
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

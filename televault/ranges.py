from __future__ import annotations

from dataclasses import dataclass


class RangeNotSatisfiable(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int
    size: int
    partial: bool

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.end}/{self.size}"


def parse_range_header(header: str | None, size: int) -> ByteRange:
    if size <= 0:
        raise RangeNotSatisfiable("The media has no downloadable bytes.")
    if not header:
        return ByteRange(start=0, end=size - 1, size=size, partial=False)
    if not header.lower().startswith("bytes="):
        raise RangeNotSatisfiable("Only byte ranges are supported.")
    specification = header.split("=", 1)[1].strip()
    if not specification or "," in specification or "-" not in specification:
        raise RangeNotSatisfiable("Only one byte range may be requested.")
    first, last = (part.strip() for part in specification.split("-", 1))
    try:
        if not first:
            suffix_length = int(last)
            if suffix_length <= 0:
                raise RangeNotSatisfiable("The suffix range must be positive.")
            start = max(0, size - suffix_length)
            end = size - 1
        else:
            start = int(first)
            end = size - 1 if not last else min(int(last), size - 1)
    except ValueError as exc:
        raise RangeNotSatisfiable("The byte range is malformed.") from exc
    if start < 0 or start >= size or end < start:
        raise RangeNotSatisfiable("The byte range is outside the media.")
    return ByteRange(start=start, end=end, size=size, partial=True)


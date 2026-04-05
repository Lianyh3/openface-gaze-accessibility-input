from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KeyRect:
    key_id: str
    label: str
    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


def build_qwerty_layout() -> list[KeyRect]:
    """Build a normalized [0,1] x [0,1] simplified QWERTY rectangle layout."""
    rows = [
        "QWERTYUIOP",
        "ASDFGHJKL",
        "ZXCVBNM",
    ]

    keys: list[KeyRect] = []
    row_height = 0.24
    top_margin = 0.18

    for row_index, row in enumerate(rows):
        width = 1.0 / max(10, len(row))
        row_y0 = top_margin + row_index * row_height
        row_y1 = min(0.98, row_y0 + row_height * 0.8)

        row_total = len(row) * width
        offset = (1.0 - row_total) / 2.0

        for col_index, ch in enumerate(row):
            x0 = offset + col_index * width
            x1 = x0 + width
            keys.append(KeyRect(key_id=ch, label=ch, x0=x0, y0=row_y0, x1=x1, y1=row_y1))

    keys.append(KeyRect(key_id="SPACE", label="SPACE", x0=0.2, y0=0.80, x1=0.8, y1=0.96))
    keys.append(KeyRect(key_id="BACKSPACE", label="⌫", x0=0.82, y0=0.80, x1=0.98, y1=0.96))
    return keys

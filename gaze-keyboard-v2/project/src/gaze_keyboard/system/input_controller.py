from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InputController:
    text: str = ""
    fired_count: int = 0
    history: list[str] = field(default_factory=list)

    def apply_key(self, key_id: str) -> str:
        self.fired_count += 1

        if key_id == "SPACE":
            self.text += " "
            self.history.append("SPACE")
            return self.text

        if key_id == "BACKSPACE":
            self.text = self.text[:-1]
            self.history.append("BACKSPACE")
            return self.text

        if len(key_id) == 1:
            self.text += key_id
            self.history.append(key_id)
            return self.text

        self.history.append(f"UNKNOWN:{key_id}")
        return self.text

"""Project trial identities at evaluation model boundaries while retaining original evidence and references."""

import json
import re
from dataclasses import replace

from ..scenario.sealed import fold
from .hearing import opaque


class SessionLabels:
    """A reversible, stable vocabulary shared with the Curator's session references."""

    def __init__(self, names):
        self.labels = {name: opaque(name) for name in names if name}
        if (
            len(set(self.labels.values())) != len(self.labels)
            or len({fold(name) for name in self.labels}) != len(self.labels)
            or set(self.labels) & set(self.labels.values())
        ):
            raise ValueError("session labels collide with another session identity")
        self.names = {label: name for name, label in self.labels.items()}

    @classmethod
    def protected(cls, provider, names):
        """Only hidden trial identifiers need projection; ordinary words used as session names stay untouched."""
        names = {name for name in names if name}
        guard = getattr(provider, "guard", None)
        tokens = getattr(getattr(guard, "sealed", None), "tokens", ())
        matched = {
            name for name in names if any(fold(name) == token or fold(name).startswith(token + "-") for token in tokens)
        }
        bases = {token for token in tokens if any(fold(name).startswith(token + "-") for name in matched)}
        return cls(matched | (bases - {fold(name) for name in matched}))

    @staticmethod
    def _project(value, mapping):
        if not mapping:
            return value
        mapping = {fold(key): value for key, value in mapping.items()}

        def variant(char):
            if char == "-":
                return r"[-\u2010-\u2015\u2212\uff0d]"
            if 33 <= ord(char) <= 126:
                return "[" + re.escape(char + chr(ord(char) + 65248)) + "]"
            return re.escape(char)

        alternatives = "|".join(
            "".join(variant(char) for char in key) for key in sorted(mapping, key=len, reverse=True)
        )
        pattern = re.compile(r"(?<![\w-])(?:" + alternatives + r")(?![\w-])", re.IGNORECASE) if mapping else None

        def walk(item):
            if isinstance(item, str):
                if item.lstrip()[:1] in ("{", "["):
                    try:
                        decoded = json.loads(item)
                    except ValueError:
                        pass
                    else:
                        if isinstance(decoded, (dict, list)):
                            projected = walk(decoded)
                            return json.dumps(projected, ensure_ascii=False) if projected != decoded else item
                return pattern.sub(lambda match: mapping[fold(match.group())], item)
            if isinstance(item, dict):
                return {walk(key): walk(content) for key, content in item.items()}
            if isinstance(item, (list, tuple)):
                return type(item)(walk(content) for content in item)
            return item

        return walk(value)

    def encode(self, value):
        return self._project(value, self.labels)

    def decode(self, value):
        return self._project(value, self.names)

    def provider(self, provider):
        return LabelledProvider(provider, self) if self.labels else provider


class LabelledProvider:
    """Encode before the guarded provider scans; restore answers before evidence and quote validation."""

    def __init__(self, provider, labels):
        self.provider, self.labels = provider, labels

    async def chat_with_retry(self, messages, tools=None, **kwargs):
        response = await self.provider.chat_with_retry(
            messages=self.labels.encode(messages), tools=self.labels.encode(tools), **kwargs
        )
        return replace(
            response,
            content=self.labels.decode(response.content),
            reasoning_content=self.labels.decode(response.reasoning_content),
            tool_calls=[replace(call, arguments=self.labels.decode(call.arguments)) for call in response.tool_calls],
        )

    def __getattr__(self, name):
        return getattr(self.provider, name)

"""
ToolPlugin — contrato que cada arquivo em src/tools/ deve implementar.

Para criar um novo plugin:
1. Crie src/tools/meu_plugin.py
2. Defina PLUGIN = ToolPlugin(...)
3. Ele será descoberto e registrado automaticamente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Union

from ..agent_tools import AgentTool


@dataclass
class ToolPlugin:
    # identificador único do plugin
    name: str

    # tools que este plugin registra no agente
    tools: list[AgentTool]

    # guidance injetado no system prompt APENAS quando uma das tools é chamada
    # (via before_tool hook — não polui o prompt principal)
    prompt: str = ""

    # True = sempre ativo
    # False = nunca ativo
    # Callable[[cfg: dict], bool] = ativo condicionalmente
    enabled: Union[bool, Callable[[dict], bool]] = True

    def is_enabled(self, cfg: dict) -> bool:
        if callable(self.enabled):
            return self.enabled(cfg)
        return bool(self.enabled)

    @property
    def tool_names(self) -> set[str]:
        return {t.name for t in self.tools}

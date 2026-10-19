"""资源参数的 JSON Schema 扩展约定。

`x-resource` 是私有扩展键：标准 JSON Schema 校验器会忽略它，只有本项目的
执行层（`tools/registry.py` + executor）用它决定"调 MCP 之前要预检哪类资源"。

写入端：MCP 工具签名用 `FileId` / `KeyId` 声明。
读取端：从 `ToolSpec.input_schema["properties"][参数名]["x-resource"]` 读。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

RESOURCE_SCHEMA_KEY = "x-resource"


class ResourceKind(StrEnum):
    """资源类型；与 `packages/security/resources.py` 的解析函数一一对应。"""

    FILE = "file"
    KEY = "key"


def resource_marker(kind: ResourceKind) -> dict[str, str]:
    """生成 `json_schema_extra` 的内容。"""
    return {RESOURCE_SCHEMA_KEY: kind.value}


# 工具签名里直接使用这两个别名，避免每个函数重复写 Field(...)
FileId = Annotated[str, Field(json_schema_extra=resource_marker(ResourceKind.FILE))]
KeyId = Annotated[str, Field(json_schema_extra=resource_marker(ResourceKind.KEY))]

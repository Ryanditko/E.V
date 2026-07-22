from typing import Any 

from ev.tools.base import Tool

class ToolRegistry: 
    """Manage available tools."""

    def __init__(self): 
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool): 
        "Register a tool."
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool  | None: 
        "Get a tool by name."
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [tool.to_ollama_format() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs) -> str:
        "Execute a tool by name with given arguments."
        tool = self.get(name) 
        if tool is None: 
            return f"Error: Tool '{name}' not found."

        try: 
            return tool.execute(**kwargs)
        except Exception as e: 
            return f"Error executing {name}: {e}"
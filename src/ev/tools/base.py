from abc import ABC, abstractmethod 
from typing import Any

class Tool(ABC): 
    """Base class for all tools."""
    @property
    @abstractmethod 
    def name(self) -> str: 
        "unique identifier for the tool."
        pass


    @property
    @abstractmethod
    def description(self) -> str: 
        "Description of what the tool does (For LLM understand)."
        pass


    @property
    @abstractmethod
    def parameters(self) -> dict: 
        "JSON Schema of the tools parameters."
        pass

    @abstractmethod
    def execute(self, **kwargs) -> str: 
        "Execute the tool with given parameters."
        pass

    def to_ollama_format(self) -> dict: 
        """Convert tool to Ollama's expected format."""
        return {
            "type": "function", 
            "function": {
                "name": self.name, 
                "description": self.description, 
                "parameters": self.parameters
            }
        }


import json
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from ev.llm import OllamaClient
from ev.tools import ToolRegistry, WebSearchTool


def load_system_prompt() -> str:
    """Load system prompt from config file."""
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent
    prompt_file = project_root / "config" / "prompts" / "system.md"
    
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")

    return "You are E.V., a helpful personal AI assistant."


def main(): 
    console = Console()
    client = OllamaClient()

    # Setup tools
    registry = ToolRegistry()
    registry.register(WebSearchTool())

    messages = []

    system_prompt = {
        "role": "system", 
        "content": load_system_prompt()
    }
    messages.append(system_prompt)

    console.print("[bold green]E.V. - Personal AI Assistant[/bold green]")
    console.print("Type /help for commands, /quit to exit\n")

    if not client.is_available(): 
        console.print("[bold red]Error:[/bold red] Ollama is not running!")
        console.print("Start it with: ollama serve")
        return

    while True: 
        try: 
            user_input = console.input("[bold blue]>[/bold blue] ")
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.strip() == "/quit": 
            break
        if user_input.strip() == "/help": 
            console.print("Commands: /quit, /help, /clear")
            continue
        if user_input.strip() == "/clear":
            messages = [system_prompt]
            console.print("Conversation cleared.")
            continue
        if not user_input.strip(): 
            continue

        messages.append({"role": "user", "content": user_input})

        try: 
            # Agent loop - continues until no more tool calls
            while True:
                response = client.chat(messages, tools=registry.list_tools())
                
                if response.has_tool_calls:
                    # Process tool calls
                    for tool_call in response.tool_calls:
                        func = tool_call["function"]
                        tool_name = func["name"]
                        tool_args = json.loads(func["arguments"])
                        
                        console.print(f"\n[dim][Tool: {tool_name}][/dim]")
                        
                        # Execute tool
                        result = registry.execute(tool_name, **tool_args)
                        console.print(f"[dim]{result[:200]}...[/dim]" if len(result) > 200 else f"[dim]{result}[/dim]")
                        
                        # Add result to message history
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call]
                        })
                        messages.append({
                            "role": "tool",
                            "content": result
                        })
                else:
                    # Final response (no tool calls)
                    if response.content:
                        messages.append({"role": "assistant", "content": response.content})
                    break

            # Display final response
            if response.content:
                console.print()
                console.print(Markdown(response.content))
                console.print()

        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            messages.pop()


if __name__ == "__main__": 
    main()
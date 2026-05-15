from rich.console import Console
from rich.markdown import Markdown

from ev.llm import OllamaClient

def main(): 
    console = Console()
    client = OllamaClient()

    messages = []

    system_prompt = {
        "role": "system", 
        "content": "You are E.V., a helpful personal AI assistant."
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
            user_input = console.input("[bold blue]>[/bold blue]")
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
            response = client.chat(messages)
            messages.append({"role": "assistant", "content": response})

            console.print()
            console.print(Markdown(response))
            console.print()

        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            messages.pop()


if __name__ == "__main__": 
    main()
#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime
from enum import Enum
from typing import Optional
import typer
from rich.console import Console
from rich.prompt import Prompt
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Input, Markdown, Log, RichLog, LoadingIndicator
from textual.binding import Binding
from textual import work
from google.antigravity import Agent, LocalAgentConfig, GeminiConfig, GenerationConfig, CapabilitiesConfig
from google.antigravity.types import BuiltinTools

app = typer.Typer(help="Von - Agentic SDLC CLI", rich_markup_mode=None)
iterations_app = typer.Typer(help="Manage SDLC iterations", rich_markup_mode=None)
app.add_typer(iterations_app, name="iterations")

console = Console()

class IterationState(str, Enum):
    CREATED = "created"
    PRODUCT_REQUIREMENTS_GATHERING = "product_requirements_gathering"
    PRODUCT_REQUIREMENTS_GATHERED = "product_requirements_gathered"
    ENGINEERING_REQUIREMENTS_GATHERING = "engineering_requirements_gathering"
    ENGINEERING_REQUIREMENTS_GATHERED = "engineering_requirements_gathered"
    IMPLEMENTATION_IN_PROGRESS = "implementation_in_progress"
    IMPLEMENTATION_COMPLETED = "implementation_completed"
    COMPLETED = "completed"

def update_iteration_state(slug: str, new_state: IterationState):
    md_path = os.path.join(".von", "iterations", slug, "METADATA.md")
    with open(md_path, "r") as f:
        content = f.read()
        
    # Replace the existing status or add it if missing
    if re.search(r'^status:\s*(.+)$', content, re.MULTILINE):
        content = re.sub(r'^status:\s*(.+)$', f'status: {new_state.value}', content, flags=re.MULTILINE)
    else:
        content += f"status: {new_state.value}\n"
        
    with open(md_path, "w") as f:
        f.write(content)

class AgenticChatTUI(App):
    CSS = """
    #left-pane {
        width: 40%;
        border-right: solid green;
        background: transparent;
        padding-right: 2;
    }
    #right-pane {
        width: 60%;
        padding: 1;
    }
    #prompt-log {
        height: 1fr;
        width: 100%;
        overflow-x: hidden;
        background: transparent;
        scrollbar-background: transparent;
        padding-right: 2;
    }
    #loading-spinner {
        height: 1;
        width: 100%;
    }
    #prompt-input {
        dock: bottom;
        width: 100%;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, title: str, md_path: str, slug: str, phase_name: str, system_instruction: str, done_state: IterationState):
        super().__init__()
        self.title = title
        self.TITLE = title
        self.md_path = md_path
        self.slug = slug
        self.phase_name = phase_name
        self.system_instruction = system_instruction
        self.done_state = done_state
        self.md_content = ""
        self.chat_path = os.path.join(".von", "iterations", slug, f"{phase_name}_chat.json")
        self.chat_history = []
        
        if os.path.exists(self.chat_path):
            try:
                with open(self.chat_path, "r") as f:
                    self.chat_history = json.load(f)
            except Exception:
                self.chat_history = []

        if os.path.exists(md_path):
            with open(md_path, "r") as f:
                self.md_content = f.read()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                log = RichLog(id="prompt-log", wrap=True, markup=True)
                # To enforce horizontal wrapping over rendering a horizontal scrollbar, 
                # we must explicitly disable auto-scrolling on x-axis in some textual versions
                log.styles.overflow_x = "hidden"
                # Add a right padding margin explicitly to avoid text trimming near the scrollbar
                log.styles.padding = (0, 2, 0, 0)
                yield log
                yield LoadingIndicator(id="loading-spinner")
                yield Input(placeholder="Type product requirement...", id="prompt-input")
            with Vertical(id="right-pane"):
                yield Markdown(self.md_content, id="md-viewer")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#loading-spinner", LoadingIndicator).display = False
        self.init_agent()
        
        if not self.chat_history:
            self.append_chat_history("agent", "What are you trying to build? Elaborate your requirements.")
            self.render_chat_history()
        else:
            self.render_chat_history()

    def init_agent(self):
        # Initialize the Antigravity agent session
        try:
            system_instruction = """
            You are an expert Product Manager preparing a Product Requirements Document (PRD) for coding agents to execute.
            
            You will receive the user's requirements. Keep track of the current state of the PRD internally.
            
            Please respond to every message in exactly two parts using this exact format:
            
            PART1
            <Provide ONLY crisp bullet points of critical gaps, edge cases, and missing requirements as direct questions or suggestions to the user. Do not include fluff, conversational filler, or greetings. If the PRD is totally complete and ready for execution, just say: "Everything looks good. Type /done to proceed.">
            
            PART2
            ```markdown
            <The complete, updated Product Requirements Document>
            ```
            """
            
            config = LocalAgentConfig(
                gemini=GeminiConfig(
                    model_id="gemini-2.5-flash",
                    system_instruction=system_instruction,
                    generation_config=GenerationConfig(temperature=0.2)
                ),
                capabilities=CapabilitiesConfig(
                    enabled_tools=[BuiltinTools.VIEW_FILE, BuiltinTools.CREATE_FILE, BuiltinTools.EDIT_FILE, BuiltinTools.RUN_COMMAND]
                ),
                agent_id=f"prd-agent-{self.slug}"
            )
            
            self.agent = Agent(config)
            
        except Exception as e:
            self.agent = None
            self.query_one(RichLog).write(f"[bold red]Failed to initialize Antigravity agent: {str(e)}[/bold red]")

    def append_chat_history(self, role: str, text: str):
        self.chat_history.append({"role": role, "content": text})
        with open(self.chat_path, "w") as f:
            json.dump(self.chat_history, f, indent=2)

    def render_chat_history(self):
        log = self.query_one(RichLog)
        log.clear()
        from rich.markdown import Markdown as RichMarkdown
        
        for msg in self.chat_history:
            if msg["role"] == "agent":
                log.write("\n[bold green]Agent:[/bold green]")
                log.write(RichMarkdown(msg["content"]))
                log.write("\n")
            else:
                log.write(f"\n[bold blue]You:[/bold blue] {msg['content']}")

    @work(thread=True)
    def process_user_input(self, user_text: str):
        import asyncio
        
        async def _run():
            self.call_from_thread(self.set_loading, True)
            try:
                if getattr(self, 'agent', None) is None:
                    raise Exception("Agent session is not initialized.")
                    
                async with self.agent:
                    response = await self.agent.chat(user_text)
                    
                    full_text = ""
                    # We can optionally print chunks to standard out or to log incrementally,
                    # but since the output format demands PART1 and PART2 splits to format correctly,
                    # streaming directly into the log before we know which part is which breaks the right pane.
                    # We will collect the whole stream asynchronously first.
                    async for chunk in response:
                        if isinstance(chunk, str):
                            full_text += chunk
                    text = full_text
                    
                # Use explicit splitting to ensure we strictly get the requested structure
                if "PART1" in text and "PART2" in text:
                    parts = text.split("PART2")
                    reply = parts[0].replace("PART1", "").strip()
                    
                    md_raw = parts[1].strip()
                    if "```markdown" in md_raw:
                        md_part = md_raw.split("```markdown")[1].split("```")[0].strip()
                    else:
                        md_part = md_raw
                        
                    self.md_content = md_part
                    with open(self.md_path, "w") as f:
                        f.write(self.md_content)
                        f.flush()
                        os.fsync(f.fileno())
                        
                    self.call_from_thread(self.append_chat_history, "agent", reply)
                    self.call_from_thread(self.update_ui, reply, self.md_content)
                else:
                    self.call_from_thread(self.append_chat_history, "agent", text)
                    self.call_from_thread(self.write_log, f"\n[bold green]Agent:[/bold green]\n{text}")
            except Exception as e:
                self.call_from_thread(self.write_log, f"Error: {str(e)}")
            finally:
                self.call_from_thread(self.set_loading, False)
                
        asyncio.run(_run())

    def set_loading(self, is_loading: bool):
        spinner = self.query_one("#loading-spinner", LoadingIndicator)
        spinner.display = is_loading

    def write_log(self, text: str):
        log = self.query_one(RichLog)
        log.write(text)

    def update_ui(self, reply: str, new_md: str):
        from rich.markdown import Markdown as RichMarkdown
        
        self.write_log("\n[bold green]Agent:[/bold green]")
        self.query_one(RichLog).write(RichMarkdown(reply))
        self.write_log("\n")

        # Explicitly replace the Markdown widget with a fresh one to force re-render
        right_pane = self.query_one("#right-pane")
        old_md_viewer = self.query_one("#md-viewer")
        old_md_viewer.remove()
        
        new_md_viewer = Markdown(new_md, id="md-viewer")
        right_pane.mount(new_md_viewer)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        if not val:
            return
            
        event.input.value = ""
        
        if val == "/done":
            update_iteration_state(self.slug, self.done_state)
            self.exit()
            return
            
        if val == "/clear":
            self.chat_history = []
            if os.path.exists(self.chat_path):
                os.remove(self.chat_path)
            self.init_agent() # Reset agent memory
            
            self.append_chat_history("agent", "What are you trying to build? Elaborate your requirements.")
            self.render_chat_history()
            return
            
        self.append_chat_history("user", val)
        self.write_log(f"\n[bold blue]You:[/bold blue] {val}")
        self.process_user_input(val)

def handle_resume_iteration(slug: str, meta: dict):
    state = meta["status"]
    iteration_dir = os.path.join(".von", "iterations", slug)
    
    console.print(f"[green]Resuming iteration '{meta['name']}' ({slug}) from state '{state}'...[/green]")

    if state == IterationState.CREATED.value:
        update_iteration_state(slug, IterationState.PRODUCT_REQUIREMENTS_GATHERING)
        state = IterationState.PRODUCT_REQUIREMENTS_GATHERING.value
        console.print("[green]Transitioned to 'product_requirements_gathering'.[/green]")
        
    if state == IterationState.PRODUCT_REQUIREMENTS_GATHERING.value:
        pr_md_path = os.path.join(iteration_dir, "product_requirements.md")
        if not os.path.exists(pr_md_path):
            with open(pr_md_path, "w") as f:
                f.write(f"# Product Requirements: {meta['name']}\n\n")
                
        if not os.environ.get("GEMINI_API_KEY"):
            console.print("[bold red]Error: GEMINI_API_KEY environment variable is not set.[/bold red]")
            return
            
        system_instruction = """
        You are an expert Product Manager preparing a Product Requirements Document (PRD) for coding agents to execute.
        
        You will receive the user's requirements. Keep track of the current state of the PRD internally.
        
        Please respond to every message in exactly two parts using this exact format:
        
        PART1
        <Provide ONLY crisp bullet points of critical gaps, edge cases, and missing requirements as direct questions or suggestions to the user. Do not include fluff, conversational filler, or greetings. If the PRD is totally complete and ready for execution, just say: "Everything looks good. Type /done to proceed.">
        
        PART2
        ```markdown
        <The complete, updated Product Requirements Document>
        ```
        """
        
        app = AgenticChatTUI(
            title="Product Requirements",
            md_path=pr_md_path,
            slug=slug,
            phase_name="prd",
            system_instruction=system_instruction,
            done_state=IterationState.PRODUCT_REQUIREMENTS_GATHERED
        )
        app.run()
        return

    if state == IterationState.PRODUCT_REQUIREMENTS_GATHERED.value:
        # Next goes to engineering_requirements_gathering
        update_iteration_state(slug, IterationState.ENGINEERING_REQUIREMENTS_GATHERING)
        state = IterationState.ENGINEERING_REQUIREMENTS_GATHERING.value
        console.print("[green]Transitioned to 'engineering_requirements_gathering'.[/green]")
        # TODO: Implement engineering requirements TUI
        
    if state == IterationState.ENGINEERING_REQUIREMENTS_GATHERING.value:
        console.print("[yellow]Engineering requirements gathering TUI not implemented yet.[/yellow]")
        return
        
    if state == IterationState.ENGINEERING_REQUIREMENTS_GATHERED.value:
        update_iteration_state(slug, IterationState.IMPLEMENTATION_IN_PROGRESS)
        state = IterationState.IMPLEMENTATION_IN_PROGRESS.value
        console.print("[green]Transitioned to 'implementation_in_progress'.[/green]")
        
    if state == IterationState.IMPLEMENTATION_IN_PROGRESS.value:
        console.print("[yellow]Implementation in progress. Agentic coding UI goes here.[/yellow]")
        return

    if state == IterationState.IMPLEMENTATION_COMPLETED.value:
        update_iteration_state(slug, IterationState.COMPLETED)
        console.print("[green]Iteration marked as 'completed'.[/green]")
        return

@app.command("init")
def init_command():
    """Initialize a new Von project in the current directory."""
    ascii_von = """[bold yellow]
__      __  ____   _   _ 
\\ \\    / / / __ \\ | \\ | |
 \\ \\  / / | |  | ||  \\| |
  \\ \\/ /  | |  | || . ` |
   \\  /   | |__| || |\\  |
    \\/     \\____/ |_| \\_|
[/bold yellow]"""
    console.print(ascii_von, highlight=False)
    console.print()

    von_dir = ".von"
    if os.path.exists(von_dir):
        console.print("[bold yellow]This project is already a Von project.[/bold yellow]")
        console.print("Run [bold cyan]von iterations new[/bold cyan] to create a new iteration.")
        raise typer.Exit()

    # Get the name of the current directory
    current_dir = os.path.basename(os.path.abspath(os.getcwd()))
    if not current_dir:
        current_dir = "my-project"
        
    # Read project name from stdin with a default
    project_name = Prompt.ask(
        "[bold]Project name[/bold]",
        default=current_dir
    )
    
    console.print()
    console.print("[bold cyan]-- Setup --------------------------------------[/bold cyan]")
    console.print()
    
    # Create the .von directory for agentic SDLC
    von_dir = ".von"
    os.makedirs(von_dir, exist_ok=True)
    os.makedirs(os.path.join(von_dir, "agents"), exist_ok=True)
    os.makedirs(os.path.join(von_dir, "prompts"), exist_ok=True)
    os.makedirs(os.path.join(von_dir, "logs"), exist_ok=True)
    
    # Write the project configuration
    config_path = os.path.join(von_dir, "config.json")
    with open(config_path, "w") as f:
        json.dump({"project_name": project_name}, f, indent=2)
    
    # Print progress
    console.print(f"[dim]info:[/dim] {f'creating {von_dir}/ directory...':<35} [green]done[/green]")
    console.print(f"[dim]info:[/dim] {'initializing SDLC components...':<35} [green]done[/green]")
    console.print(f"[dim]info:[/dim] {f'writing {von_dir}/config.json...':<35} [green]done[/green]")
    
    console.print()
    console.print("[bold green]You are all set for full agentic SDLC.[/bold green]")
    console.print("Run [bold cyan]von iterations new[/bold cyan] to create a new iteration.")
    console.print()

@iterations_app.command("new")
def iterations_new():
    """Create a new iteration."""
    iteration_name = Prompt.ask("[bold]Iteration name[/bold]")
    slug = re.sub(r'[^a-z0-9]+', '-', iteration_name.lower()).strip('-')
    
    if not slug:
        console.print("[bold red]Invalid iteration name.[/bold red]")
        raise typer.Exit(1)
        
    iteration_dir = os.path.join(".von", "iterations", slug)
    if os.path.exists(iteration_dir):
        console.print(f"[bold red]Error: Iteration with slug '{slug}' already exists.[/bold red]")
        console.print(f"Either you resume it with [bold cyan]von iterations resume {slug}[/bold cyan] or create a new iteration with [bold cyan]von iterations new[/bold cyan].")
        raise typer.Exit(1)
        
    os.makedirs(iteration_dir, exist_ok=True)
    
    metadata_path = os.path.join(iteration_dir, "METADATA.md")
    current_time = datetime.now().isoformat()
    
    with open(metadata_path, "w") as f:
        f.write(f"---\nname: {iteration_name}\ntime: {current_time}\nstatus: {IterationState.CREATED.value}\n---\n")
        
    console.print(f"[green]Created new iteration '{iteration_name}' at {iteration_dir}[/green]")

@iterations_app.command("resume")
def iterations_resume(slug: Optional[str] = typer.Argument(None, help="The slug of the iteration to resume")):
    """Resume an existing iteration."""
    iterations_dir = os.path.join(".von", "iterations")
    if not os.path.exists(iterations_dir):
        console.print("[bold red]No iterations found. Run 'von iterations new' to create one.[/bold red]")
        raise typer.Exit(1)
        
    def get_metadata(s):
        md_path = os.path.join(iterations_dir, s, "METADATA.md")
        if not os.path.exists(md_path):
            return None
        with open(md_path, "r") as f:
            content = f.read()
        name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
        status_match = re.search(r'^status:\s*(.+)$', content, re.MULTILINE)
        return {
            "slug": s,
            "name": name_match.group(1) if name_match else s,
            "status": status_match.group(1) if status_match else "unknown"
        }
        
    if slug:
        iter_dir = os.path.join(iterations_dir, slug)
        if not os.path.exists(iter_dir):
            console.print(f"[bold red]Error: Iteration '{slug}' not found.[/bold red]")
            raise typer.Exit(1)
            
        meta = get_metadata(slug)
        if not meta:
            console.print(f"[bold red]Error: Metadata for '{slug}' not found.[/bold red]")
            raise typer.Exit(1)
            
        if meta["status"] == IterationState.COMPLETED.value:
            console.print("[bold red]Error: This iteration is marked complete and hence cannot be resumed.[/bold red]")
            raise typer.Exit(1)
            
        handle_resume_iteration(slug, meta)
    else:
        slugs = [d for d in os.listdir(iterations_dir) if os.path.isdir(os.path.join(iterations_dir, d))]
        active_iters = []
        for s in slugs:
            meta = get_metadata(s)
            if meta and meta["status"] != IterationState.COMPLETED.value:
                active_iters.append(meta)
                
        if not active_iters:
            console.print("[bold yellow]No active iterations found.[/bold yellow]")
            raise typer.Exit()
            
        console.print("[bold cyan]Active Iterations:[/bold cyan]")
        for i, meta in enumerate(active_iters, 1):
            console.print(f"[{i}] [bold]{meta['slug']}[/bold] - {meta['name']} (Status: {meta['status']})")
            
        choices = [str(i) for i in range(1, len(active_iters) + 1)]
        choice = Prompt.ask("Select an iteration to resume", choices=choices)
        
        selected = active_iters[int(choice) - 1]
        handle_resume_iteration(selected["slug"], selected)

def main():
    app()

if __name__ == "__main__":
    main()

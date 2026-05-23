#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime
from enum import Enum
import typer
from rich.console import Console
from rich.prompt import Prompt

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

def main():
    app()

if __name__ == "__main__":
    main()

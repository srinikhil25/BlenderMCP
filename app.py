import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from blender_script_templates import script_for_prompt


def resolve_blender_path() -> str:
    """
    Determine which Blender executable to use.
    Priority:
    1. BLENDER_PATH environment variable.
    2. 'blender' from PATH.
    """
    env_path = os.environ.get("BLENDER_PATH")
    if env_path:
        return env_path
    # Fallback: rely on system PATH
    return "blender"


def run_blender_with_script(script_text: str) -> int:
    """
    Write the given Blender Python script to a temp file and execute it
    using Blender in background mode.
    Returns Blender's exit code.
    """
    blender_exe = resolve_blender_path()

    # Write to a temporary .py file
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "generated_script.py"
        script_path.write_text(script_text, encoding="utf-8")

        cmd = [
            blender_exe,
            # "--background",  # run without UI; change/remove if you want GUI
            "--python",
            str(script_path),
        ]

        print(f"Running Blender: {' '.join(cmd)}")
        try:
            proc = subprocess.run(cmd, check=False)
            return proc.returncode
        except FileNotFoundError:
            print(
                "Blender executable not found. "
                "Set BLENDER_PATH or ensure 'blender' is on your PATH."
            )
            return 1


def generate_structure_from_prompt(prompt: str) -> int:
    """
    Core entry point:
    - Maps a natural language prompt to a Blender script.
    - Runs Blender with that script.
    Returns Blender's exit code.
    """
    script_text = script_for_prompt(prompt)
    return run_blender_with_script(script_text)


@click.command()
@click.argument("prompt", nargs=-1)
def main(prompt: tuple[str, ...]) -> None:
    """
    Simple CLI entry:

        python app.py "Draw a home"
    """
    if not prompt:
        click.echo("Please provide a prompt, e.g. 'Draw a home'.")
        sys.exit(1)

    full_prompt = " ".join(prompt)
    click.echo(f"Using prompt: {full_prompt!r}")
    exit_code = generate_structure_from_prompt(full_prompt)

    if exit_code == 0:
        click.echo("Blender script executed successfully.")
    else:
        click.echo(f"Blender exited with code {exit_code}.")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()


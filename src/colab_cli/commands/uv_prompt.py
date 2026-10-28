from typing import Optional, Tuple
import typer

MENU_TEXT = """Select GPU Accelerator for the Colab VM:
----------------------------------------------------------------------------------------
 [1] G4 GPU      (96 GB GDDR7)          - NVIDIA RTX PRO 6000 Blackwell Server Edition
 [2] A100 GPU    (40 GB HBM2e)          - NVIDIA A100 Tensor Core (High Compute)
 [3] L4 GPU      (24 GB GDDR6)          - NVIDIA L4 Ada Lovelace
 [4] T4 GPU      (16 GB GDDR6)          - NVIDIA T4 (Standard budget GPU)
 [5] H100 GPU    (80 GB HBM3)           - NVIDIA H100 Tensor Core (Google AI Ultra tier)
 [6] None        (No GPU / CPU runtime)
----------------------------------------------------------------------------------------"""


def parse_accelerator_choice(
    choice: str, high_ram_choice: str = "n"
) -> Tuple[Optional[str], Optional[str], bool]:
    """Maps a user selection to (gpu, tpu, high_mem)."""
    norm = choice.strip().lower() if choice else "6"
    high_ram = high_ram_choice.strip().lower() in ("y", "yes", "true", "1")

    if norm in ("1", "g4"):
        return ("g4", None, high_ram)
    elif norm in ("2", "a100"):
        return ("a100", None, high_ram)
    elif norm in ("3", "l4"):
        return ("l4", None, high_ram)
    elif norm in ("4", "t4"):
        return ("t4", None, high_ram)
    elif norm in ("5", "h100"):
        return ("h100", None, high_ram)
    elif norm in ("6", "none", "cpu", "no", "0"):
        return (None, None, high_ram)
    elif norm in ("v6e", "v6e1", "v6e-1"):
        return (None, "v6e1", False)
    elif norm in ("v5e", "v5e1", "v5e-1"):
        return (None, "v5e1", False)
    else:
        # Do not default to any GPU
        return (None, None, high_ram)


def prompt_accelerator(
    default_choice: str = "6",
    high_mem_default: bool = False,
    skip_high_mem_prompt: bool = False,
) -> Tuple[Optional[str], Optional[str], bool]:
    """Displays the interactive GPU & High-RAM menu and returns (gpu, tpu, high_mem)."""
    typer.echo(MENU_TEXT)
    choice = input(
        f"Select a GPU [1-6] (default: {default_choice} [None]): "
    ).strip()
    if not choice:
        choice = default_choice

    if skip_high_mem_prompt:
        high_ram_choice = "y" if high_mem_default else "n"
    else:
        default_str = "Y/n" if high_mem_default else "y/N"
        prompt_str = f"Request High-RAM machine shape? [{default_str}]: "
        ans = input(prompt_str).strip()
        if not ans:
            high_ram_choice = "y" if high_mem_default else "n"
        else:
            high_ram_choice = ans

    return parse_accelerator_choice(choice, high_ram_choice=high_ram_choice)



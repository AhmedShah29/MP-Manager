"""
Modpack Manager (mpm) - A CLI tool for creating and managing Minecraft modpacks

Usage:
    Interactive mode: python -m mpm
    CLI mode: python -m mpm [command]

Commands:
    -n          Create new modpack
    -imp        Import modpack from app export
    -imp-mr     Import from modrinth.index.json
    -mpe        Export modpack to JSON
    -omp        Open modpack
    -emp        Deactivate modpack
    -am         Add mod
    -rm         Remove mod
    -rmp        Remove modpack
    -lmp        List modpacks
    -lm         List mods
    -mpi        Show modpack info
    -mpb        Build modpack
    -mpvc       Change modpack version
    -mu         Check and apply mod updates

For more information: https://github.com/AhmedShah29/MP-Manager
"""

__version__ = "1.0.1"
__author__ = "AhmedShah29"
__license__ = "MIT"
__all__ = ["ModpackManager"]

from .core import ModpackManager

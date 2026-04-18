#!/usr/bin/env python3
"""
Modpack Manager CLI (mpm) - Main entry point
Run with: python -m mpm [command]
"""

import sys
from .core import ModpackManager, print_cli_help


def main():
    """Main entry point - supports both interactive and CLI modes"""
    manager = ModpackManager()
    
    # If arguments provided, run in CLI mode
    if len(sys.argv) > 1:
        # Parse command line arguments
        command = sys.argv[1]
        args = sys.argv[2:]
        
        # Map commands to methods
        command_map = {
            "-n": manager.cmd_new,
            "-imp": manager.cmd_import_modpack,
            "-imp-mr": manager.cmd_import_modrinth,
            "-mpe": manager.cmd_export_modpack,
            "-omp": lambda: manager.cmd_open(" ".join(args)) if args else print("Usage: mpm -omp <modpack_name>"),
            "-emp": manager.cmd_exit_modpack,
            "-am": lambda: manager.cmd_add_mod(args[0]) if args else manager.cmd_add_mod(),
            "-rm": manager.cmd_remove_mod,
            "-rmp": manager.cmd_remove_modpack,
            "-lmp": manager.cmd_list_modpacks,
            "-lm": manager.cmd_list_mods,
            "-mpi": manager.cmd_modpack_info,
            "-mpb": manager.cmd_build,
            "-mpvc": manager.cmd_version_change,
            "-mu": manager.cmd_update_mods,
            "--help": lambda: print_cli_help(),
            "-h": lambda: print_cli_help(),
        }
        
        if command in command_map:
            command_map[command]()
        else:
            print(f"Unknown command: {command}")
            print("Run 'mpm --help' for usage information")
            sys.exit(1)
    else:
        # Run in interactive mode
        manager.run_interactive()


if __name__ == "__main__":
    main()

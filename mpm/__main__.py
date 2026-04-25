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

    # Define valid commands
    VALID_COMMANDS = {
        "-n", "-imp", "-imp-mr", "-mpe", "-omp", "-emp", "-am", "-rm",
        "-rmp", "-lmp", "-lm", "-mpi", "-mpb", "-mpvc", "-mu", "-config",
        "-aam", "-lam", "-aa", "-ra",
        "--help", "-h", "-help"
    }

    def parse_flags(argv):
        """Parse --flag value pairs from command line."""
        flags = {}
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg.startswith("--"):
                flag_name = arg[2:].replace("-", "_")
                if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                    flags[flag_name] = argv[i + 1]
                    i += 2
                else:
                    flags[flag_name] = True
                    i += 1
            elif arg in ("-t", "--t"):
                flags["required"] = True
                i += 1
            elif arg in ("-f", "--f"):
                flags["required"] = False
                i += 1
            else:
                i += 1
        return flags

    def get_positional_args(argv):
        """Get positional args (non-flag args after command)."""
        args = []
        found_command = False
        for arg in argv[1:]:  # Skip program name
            if arg in VALID_COMMANDS:
                found_command = True
                continue
            if found_command and not arg.startswith("-"):
                args.append(arg)
        return args

    # Handle help before anything else
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h", "-help"):
        print_cli_help()
        return

    # If no arguments, run interactive mode
    if len(sys.argv) == 1:
        manager.run_interactive()
        return

    # Get the command (first arg that's a valid command)
    command = None
    for arg in sys.argv[1:]:
        if arg in VALID_COMMANDS:
            command = arg
            break

    if command is None:
        print(f"Unknown command: {sys.argv[1]}")
        print("Run 'mpm -help' for available commands.")
        sys.exit(1)

    # Parse flags and positional args
    flags = parse_flags(sys.argv[1:])
    positional = get_positional_args(sys.argv)

    try:
        if command == "-n":
            manager.cmd_new(
                name=flags.get("name"),
                loader=flags.get("loader"),
                mc_version=flags.get("mc_version"),
                loader_version=flags.get("loader_version")
            )
        elif command == "-imp":
            manager.cmd_import_modpack()
        elif command == "-imp-mr":
            manager.cmd_import_modrinth()
        elif command == "-mpe":
            manager.cmd_export_modpack()
        elif command == "-omp":
            if positional:
                manager.cmd_open(" ".join(positional))
            else:
                print("Usage: -omp <modpack_name>")
        elif command == "-emp":
            manager.cmd_exit_modpack()
        elif command == "-am":
            project_id = positional[0] if positional else None
            manager.cmd_add_mod(project_id, flags.get("required"))
        elif command == "-rm":
            manager.cmd_remove_mod()
        elif command == "-rmp":
            manager.cmd_remove_modpack()
        elif command == "-lmp":
            manager.cmd_list_modpacks()
        elif command == "-lm":
            manager.cmd_list_mods()
        elif command == "-mpi":
            manager.cmd_modpack_info()
        elif command == "-mpb":
            manager.cmd_build()
        elif command == "-mpvc":
            manager.cmd_version_change()
        elif command == "-mu":
            manager.cmd_update_mods()
        elif command == "-config":
            manager.cmd_config()
        elif command == "-aam":
            # -aam <loader> <project_id>
            loader = positional[0] if len(positional) > 0 else None
            project_id = positional[1] if len(positional) > 1 else None
            manager.cmd_add_auto_mod(loader, project_id)
        elif command == "-lam":
            manager.cmd_list_auto_mods()
        elif command == "-aa":
            # -aa [type] [path]
            file_type = positional[0] if len(positional) > 0 else None
            file_path = positional[1] if len(positional) > 1 else None
            manager.cmd_add_additional(file_type, file_path)
        elif command == "-ra":
            manager.cmd_remove_additional()
        elif command in ("--help", "-h", "-help"):
            print_cli_help()
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()

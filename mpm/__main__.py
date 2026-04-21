#!/usr/bin/env python3
"""
Modpack Manager CLI (mpm) - Main entry point
Run with: python -m mpm [command]
"""

import argparse
import sys
from .core import ModpackManager, print_cli_help


def main():
    """Main entry point - supports both interactive and CLI modes"""
    manager = ModpackManager()

    parser = argparse.ArgumentParser(
        prog="mpm",
        description="Modpack Manager CLI - Manage Minecraft modpacks via Modrinth",
        add_help=False
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # New modpack
    new_parser = subparsers.add_parser("-n", help="Create new modpack")
    new_parser.add_argument("--name", help="Modpack name")
    new_parser.add_argument("--loader", choices=["fabric", "forge", "quilt", "neoforge"], help="Mod loader")
    new_parser.add_argument("--mc-version", help="Minecraft version (e.g. 1.20.1)")
    new_parser.add_argument("--loader-version", help="Loader version (auto-fetched if omitted)")

    # Import
    subparsers.add_parser("-imp", help="Import modpack from app export")
    subparsers.add_parser("-imp-mr", help="Import from modrinth.index.json")

    # Export
    subparsers.add_parser("-mpe", help="Export modpack to JSON")

    # Open
    open_parser = subparsers.add_parser("-omp", help="Open modpack")
    open_parser.add_argument("name", nargs="+", help="Modpack name")

    # Exit
    subparsers.add_parser("-emp", help="Deactivate modpack")

    # Add mod
    add_parser = subparsers.add_parser("-am", help="Add mod by Project ID")
    add_parser.add_argument("project_id", nargs="?", help="Modrinth Project ID")
    add_parser.add_argument("--t", dest="required", action="store_true", help="Mark as required")
    add_parser.add_argument("--f", dest="required", action="store_false", help="Mark as optional")

    # Remove mod
    subparsers.add_parser("-rm", help="Remove mod")

    # Remove modpack
    subparsers.add_parser("-rmp", help="Remove modpack completely")

    # List
    subparsers.add_parser("-lmp", help="List modpacks")
    subparsers.add_parser("-lm", help="List mods")

    # Info
    subparsers.add_parser("-mpi", help="Show modpack info")

    # Build
    subparsers.add_parser("-mpb", help="Build modrinth.index.json")

    # Version change
    subparsers.add_parser("-mpvc", help="Change modpack version")

    # Update
    subparsers.add_parser("-mu", help="Check and apply mod updates")

    # Help
    subparsers.add_parser("--help", help="Show help")
    subparsers.add_parser("-h", help="Show help")
    subparsers.add_parser("-help", help="Show help")

    # Handle help before argparse to avoid conflicts
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h", "-help"):
        print_cli_help()
        return

    # If no arguments, run interactive mode
    if len(sys.argv) == 1:
        manager.run_interactive()
        return

    args = parser.parse_args()

    if args.command is None:
        print_cli_help()
        return

    try:
        if args.command == "-n":
            manager.cmd_new(
                name=args.name,
                loader=args.loader,
                mc_version=args.mc_version,
                loader_version=args.loader_version
            )
        elif args.command == "-imp":
            manager.cmd_import_modpack()
        elif args.command == "-imp-mr":
            manager.cmd_import_modrinth()
        elif args.command == "-mpe":
            manager.cmd_export_modpack()
        elif args.command == "-omp":
            manager.cmd_open(" ".join(args.name))
        elif args.command == "-emp":
            manager.cmd_exit_modpack()
        elif args.command == "-am":
            manager.cmd_add_mod(args.project_id, getattr(args, "required", None))
        elif args.command == "-rm":
            manager.cmd_remove_mod()
        elif args.command == "-rmp":
            manager.cmd_remove_modpack()
        elif args.command == "-lmp":
            manager.cmd_list_modpacks()
        elif args.command == "-lm":
            manager.cmd_list_mods()
        elif args.command == "-mpi":
            manager.cmd_modpack_info()
        elif args.command == "-mpb":
            manager.cmd_build()
        elif args.command == "-mpvc":
            manager.cmd_version_change()
        elif args.command == "-mu":
            manager.cmd_update_mods()
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()

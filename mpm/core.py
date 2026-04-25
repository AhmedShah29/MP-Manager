#!/usr/bin/env python3
"""
Modpack Manger CLI - A CLI tool for creating and managing Minecraft modpacks
"""

import functools
import json
import os
import shutil
import sys
import zipfile
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any

try:
    from platformdirs import user_config_dir
except ImportError:
    # Fallback if platformdirs not installed
    def user_config_dir(appname, appauthor=None):
        return Path.home() / ".config" / appname

# Modrinth API base URL
MODRINTH_API = "https://api.modrinth.com/v2"

# Loader mapping for dependencies
LOADER_DEPENDENCY_MAP = {
    "fabric": "fabric-loader",
    "forge": "forge",
    "quilt": "quilt-loader",
    "neoforge": "neoforge"
}


def handle_network_errors(func):
    """Decorator to catch network errors gracefully. KeyboardInterrupt propagates."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.Timeout:
            print("Error: Request timed out. Please check your internet connection.")
            return None
        except requests.ConnectionError:
            print("Error: Could not connect to the server. Please check your internet connection.")
            return None
    return wrapper


class ModpackManager:
    def __init__(self):
        # Store config in platform-specific user config directory
        self.config_dir = Path(user_config_dir("mpm", "Modpack Manager"))
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "config.json"
        self.config = self._load_config()
        # Allow overriding storage path via environment variable
        env_storage = os.environ.get("MPM_STORAGE_PATH")
        if env_storage:
            self.config["storage_path"] = env_storage
            self._save_config()
        self.active_modpack_path: Optional[Path] = None
        self._update_active_path()

    def _load_config(self) -> Dict:
        """Load config file or create it"""
        return self._read_json(self.config_path) or {"storage_path": None, "active_modpack": None}

    def _save_config(self):
        """Save config file"""
        self._write_json(self.config_path, self.config)

    def _update_active_path(self):
        """Update active modpack path"""
        if self.config.get("storage_path") and self.config.get("active_modpack"):
            self.active_modpack_path = Path(self.config["storage_path"]) / self.config["active_modpack"]
        else:
            self.active_modpack_path = None

    @staticmethod
    def _read_json(path: Path) -> Optional[Dict]:
        """Read JSON file safely"""
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    @staticmethod
    def _write_json(path: Path, data: Dict):
        """Write JSON file safely"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _cleanup_old_archives(self):
        """Remove oldest archived builds, keeping only the 10 most recent."""
        if not self.active_modpack_path:
            return
        archive_dir = self.active_modpack_path / "build_archive"
        if not archive_dir.exists():
            return
        archives = sorted(archive_dir.glob("build_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in archives[10:]:
            shutil.rmtree(old)

    def _ensure_storage_path(self) -> bool:
        """Ensure storage path exists"""
        if not self.config.get("storage_path"):
            print("Welcome to Modpack Manager CLI!")
            print("This is the first run. Please specify a storage path for modpacks.")
            path = input("Enter the absolute path to store modpacks: ").strip()
            if not path:
                print("Error: Path is required!")
                return False
            path_obj = Path(path)
            try:
                path_obj.mkdir(parents=True, exist_ok=True)
                self.config["storage_path"] = str(path_obj.absolute())
                self._save_config()
                print(f"Storage path set: {path_obj.absolute()}")
                return True
            except Exception as e:
                print(f"Error creating directory: {e}")
                return False
        return True

    def _load_modpack_data(self, modpack_name: str) -> Optional[Dict]:
        """Read modpack.json for modpack (unified format)"""
        if not self.config.get("storage_path"):
            return None
        modpack_path = Path(self.config["storage_path"]) / modpack_name / "modpack.json"
        return self._read_json(modpack_path)

    def _get_modpack_info(self, modpack_name: str) -> Optional[Dict]:
        """Get modpack metadata (compatibility wrapper)"""
        data = self._load_modpack_data(modpack_name)
        if data:
            return {
                "name": data.get("name", modpack_name),
                "version": data.get("version", "1.0.0"),
                "mc_version": data.get("mc_version", "unknown"),
                "loader": data.get("loader", "fabric"),
                "loader_version": data.get("loader_version", "unknown")
            }
        return None

    def _get_mods_list(self) -> Optional[List[Dict]]:
        """Get mods list from unified modpack.json"""
        if not self.active_modpack_path:
            return None
        data = self._load_modpack_data(self.config.get("active_modpack", ""))
        if data:
            return data.get("mods", [])
        return []

    def _save_modpack_data(self, name: str, version: str, mc_version: str,
                           loader: str, loader_version: str, mods: List[Dict]):
        """Save complete modpack data to single modpack.json"""
        if not self.active_modpack_path:
            return
        data = {
            "name": name,
            "version": version,
            "mc_version": mc_version,
            "loader": loader,
            "loader_version": loader_version,
            "mods": mods
        }
        self._write_json(self.active_modpack_path / "modpack.json", data)

    def _save_mods_list(self, mods: List[Dict]):
        """Update mods list in modpack.json"""
        if not self.active_modpack_path:
            return
        data = self._load_modpack_data(self.config.get("active_modpack", ""))
        if data:
            data["mods"] = mods
            self._write_json(self.active_modpack_path / "modpack.json", data)

    @staticmethod
    @functools.lru_cache(maxsize=128)
    @handle_network_errors
    def _fetch_modrinth_project(project_id: str) -> Optional[Dict]:
        """Fetch project data from Modrinth (cached)."""
        response = requests.get(f"{MODRINTH_API}/project/{project_id}", timeout=10)
        if response.status_code == 200:
            return response.json()
        print(f"Error: Project {project_id} not found (code: {response.status_code})")
        return None

    @staticmethod
    @functools.lru_cache(maxsize=256)
    @handle_network_errors
    def _fetch_compatible_version(project_id: str, loader: str, mc_version: str) -> Optional[Dict]:
        """Search for compatible mod version (cached)."""
        params = {
            "loaders": f'["{loader}"]',
            "game_versions": f'["{mc_version}"]'
        }
        response = requests.get(
            f"{MODRINTH_API}/project/{project_id}/version",
            params=params,
            timeout=10
        )
        if response.status_code == 200:
            versions = response.json()
            if versions:
                return versions[0]  # First compatible version
        return None

    def _extract_mod_data(self, version_data: Dict) -> Optional[Dict]:
        """Extract required data from version info"""
        if not version_data.get("files"):
            return None
        
        file_info = version_data["files"][0]
        return {
            "file_id": version_data["id"],
            "filename": file_info.get("filename", ""),
            "downloads": file_info.get("url", ""),
            "sha1": file_info.get("hashes", {}).get("sha1", ""),
            "sha512": file_info.get("hashes", {}).get("sha512", ""),
            "fileSize": file_info.get("size", 0)
        }

    @staticmethod
    @functools.lru_cache(maxsize=64)
    @handle_network_errors
    def _get_latest_loader_version(loader: str, mc_version: str) -> Optional[str]:
        """Fetch the latest version for a given loader and Minecraft version (cached)."""
        if loader == "fabric":
            response = requests.get("https://meta.fabricmc.net/v2/versions/loader", timeout=10)
            if response.status_code == 200:
                versions = response.json()
                if versions:
                    return versions[0].get("version")

        elif loader == "forge":
            response = requests.get(
                "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
                timeout=10
            )
            if response.status_code == 200:
                promos = response.json().get("promos", {})
                version = promos.get(f"{mc_version}-recommended") or promos.get(f"{mc_version}-latest")
                if version:
                    return f"{mc_version}-{version}"

        elif loader == "neoforge":
            response = requests.get(
                "https://maven.neoforged.net/api/v1/maven/versions/releases/net/neoforged/neoforge",
                timeout=10
            )
            if response.status_code == 200:
                versions = response.json().get("versions", [])
                if versions:
                    return versions[0]

        elif loader == "quilt":
            response = requests.get("https://meta.quiltmc.org/v3/versions/loader", timeout=10)
            if response.status_code == 200:
                versions = response.json()
                if versions:
                    return versions[0].get("version")

        return None

    @staticmethod
    @functools.lru_cache(maxsize=8)
    @handle_network_errors
    def _get_latest_minecraft_versions(limit: int = 5) -> List[str]:
        """Fetch recent Minecraft versions from Modrinth API (cached)."""
        response = requests.get(
            f"{MODRINTH_API}/tag/game_version",
            timeout=10
        )
        if response.status_code == 200:
            versions = response.json()
            # Filter for release versions (not snapshots) and sort by date (newest first)
            releases = [
                v for v in versions
                if v.get("version_type") == "release"
            ]
            # Sort by date descending (most recent first)
            releases.sort(key=lambda x: x.get("date", ""), reverse=True)
            return [v["version"] for v in releases[:limit]]
        return []

    @staticmethod
    @handle_network_errors
    def _lookup_mod_by_hash(sha1_hash: str):
        """Lookup mod project_id and file_id by sha1 hash via Modrinth API."""
        response = requests.get(
            f"{MODRINTH_API}/version_file/{sha1_hash}",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("project_id"), data.get("id")
        # Try alternative endpoint
        response = requests.get(
            f"{MODRINTH_API}/version_file/{sha1_hash}?algorithm=sha1",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("project_id"), data.get("id")
        return None, None

    def cmd_new(self, name: Optional[str] = None, loader: Optional[str] = None,
                mc_version: Optional[str] = None, loader_version: Optional[str] = None):
        """Create new modpack. Supports both interactive and scripted modes."""
        if not self._ensure_storage_path():
            return

        if name is None:
            name = input("Enter modpack name: ").strip()
        if not name:
            print("Error: Name is required!")
            return

        # Check if modpack with same name exists
        modpack_path = Path(self.config["storage_path"]) / name
        if modpack_path.exists():
            print(f"Error: Modpack '{name}' already exists!")
            return

        valid_loaders = {"1": "forge", "2": "fabric", "3": "quilt", "4": "neoforge"}
        if loader is None:
            print("Select loader:")
            print("1. Forge")
            print("2. Fabric")
            print("3. Quilt")
            print("4. NeoForge")
            loader_choice = input("Enter loader number (1-4): ").strip()
            if loader_choice not in valid_loaders:
                print("Error: Invalid choice!")
                return
            loader = valid_loaders[loader_choice]
        elif loader.lower() not in valid_loaders.values():
            print(f"Error: Unknown loader '{loader}'. Choose: fabric, forge, quilt, neoforge")
            return
        else:
            loader = loader.lower()

        if mc_version is None:
            # Fetch latest versions for suggestions
            latest_versions = ModpackManager._get_latest_minecraft_versions(5)
            if latest_versions:
                default_mc = latest_versions[0]
                mc_input = input(f"Enter the Minecraft version (latest {default_mc}): ").strip()
                mc_version = mc_input if mc_input else default_mc
            else:
                mc_version = input("Enter the Minecraft version (e.g. 26.1.2): ").strip()
        if not mc_version:
            print("Error: Minecraft version is required!")
            return

        # Handle loader version based on config mode
        mode = self.config.get("loader_version_mode", "ask")

        if loader_version is not None:
            # User provided explicit version via CLI args
            pass
        elif mode == "manual":
            # Always ask for manual input
            loader_version = input(f"Enter {loader.capitalize()} version: ").strip()
        else:
            # Auto or Ask mode - fetch latest
            print(f"🔍 Fetching latest {loader.capitalize()} version...")
            fetched_loader_version = ModpackManager._get_latest_loader_version(loader, mc_version)

            if fetched_loader_version:
                if mode == "auto":
                    # Auto-use without asking
                    loader_version = fetched_loader_version
                    print(f"✅ Auto-selected {loader.capitalize()} version: {fetched_loader_version}")
                else:  # mode == "ask"
                    # Show and ask for confirmation
                    print(f"✅ Found {loader.capitalize()} version: {fetched_loader_version}")
                    confirm = input("Use this version? (y/n): ").strip().lower()
                    if confirm == 'n':
                        loader_version = input(f"Enter {loader.capitalize()} version manually: ").strip()
                    else:
                        loader_version = fetched_loader_version
            else:
                print(f"⚠️ Could not auto-fetch {loader.capitalize()} version. Please enter manually.")
                loader_version = input(f"Enter {loader.capitalize()} version: ").strip()

        if not loader_version:
            print(f"Error: {loader.capitalize()} version is required!")
            return

        # Create folder and unified modpack.json
        try:
            modpack_path.mkdir(parents=True, exist_ok=True)

            # Create unified modpack.json
            modpack_data = {
                "name": name,
                "version": "1.0.0",
                "mc_version": mc_version,
                "loader": loader,
                "loader_version": loader_version,
                "mods": []
            }
            self._write_json(modpack_path / "modpack.json", modpack_data)

            # Set as active modpack
            self.config["active_modpack"] = name
            self._save_config()
            self._update_active_path()

            print(f"✅ Modpack '{name}' created successfully!")
            print(f"   Loader: {loader.capitalize()} {loader_version}")
            print(f"   Minecraft: {mc_version}")

            # Apply auto mods if configured
            self._apply_auto_mods(loader, mc_version)

        except Exception as e:
            print(f"Error creating modpack: {e}")
            if modpack_path.exists():
                shutil.rmtree(modpack_path)

    def cmd_open(self, name: str):
        """Set active modpack"""
        if not self._ensure_storage_path():
            return

        modpack_path = Path(self.config["storage_path"]) / name
        if not modpack_path.exists():
            print(f"Error: Modpack '{name}' not found!")
            return

        self.config["active_modpack"] = name
        self._save_config()
        self._update_active_path()
        print(f"✅ Activated modpack: {name}")

    def cmd_exit_modpack(self):
        """Deactivate modpack"""
        if not self.config.get("active_modpack"):
            print("No active modpack.")
            return

        name = self.config["active_modpack"]
        self.config["active_modpack"] = None
        self._save_config()
        self._update_active_path()
        print(f"✅ Deactivated modpack: {name}")

    def cmd_config(self):
        """Edit app configuration settings"""
        while True:
            print("=" * 50)
            print("   App Configuration")
            print("=" * 50)
            print()
            print("1. Auto mods")
            print("2. Loader version fetch mode")
            print("3. Modpacks storage path")
            print("4. Advanced storage options (copy/link/move)")
            print("5. Back to main menu")
            print()

            choice = input("Select option (1-5): ").strip()

            if choice == "1":
                self._config_auto_mods()
            elif choice == "2":
                current = self.config.get("loader_version_mode", "ask")
                modes = {
                    "auto": "Auto-use latest version (no prompt)",
                    "ask": "Ask before using latest (confirm with user)",
                    "manual": "Always ask for version (manual input)"
                }
                print(f"\nCurrent mode: {modes.get(current, current)}")
                print("\nSelect mode:")
                print("1. Auto-use latest version (fetch and use without asking)")
                print("2. Ask before using latest (show fetched version, confirm)")
                print("3. Always ask for version (manual input, no auto-fetch)")
                mode_choice = input("Select (1-3): ").strip()
                if mode_choice == "1":
                    self.config["loader_version_mode"] = "auto"
                elif mode_choice == "2":
                    self.config["loader_version_mode"] = "ask"
                elif mode_choice == "3":
                    self.config["loader_version_mode"] = "manual"
                else:
                    print("Invalid choice.")
                    continue
                self._save_config()
                print(f"✅ Loader version mode set to: {self.config['loader_version_mode']}")
            elif choice == "3":
                current = self.config.get("storage_path", "Not set")
                print(f"\nCurrent storage path: {current}")
                new_path = input("Enter new storage path (or press Enter to keep current): ").strip()
                if new_path:
                    path = Path(new_path).expanduser().resolve()
                    path.mkdir(parents=True, exist_ok=True)
                    self.config["storage_path"] = str(path)
                    self._save_config()
                    print(f"✅ Storage path updated: {path}")
                else:
                    print("No changes made.")
            elif choice == "4":
                self._config_advanced_storage()
            elif choice == "5":
                return
            else:
                print("Invalid option.")

    def _config_advanced_storage(self):
        """Configure advanced storage options (copy/link/move) for additional files"""
        # Initialize storage_mode config if not exists
        if "storage_mode" not in self.config:
            self.config["storage_mode"] = "copy"  # copy, link, move

        while True:
            print("\n" + "=" * 50)
            print("   Advanced Storage Options")
            print("=" * 50)
            print()
            current = self.config.get("storage_mode", "copy")
            modes = {
                "copy": "Copy (safe, portable - recommended)",
                "link": "Link (symlink - for advanced users)",
                "move": "Move (destructive - not recommended)"
            }
            print(f"Current mode: {modes.get(current, current)}")
            print()
            print("⚠️  Warning: Changing storage mode may break portability")
            print("    or cause data loss. Only proceed if you know what")
            print("    you are doing.")
            print()
            print("1. Copy - Safely copy files to modpack (recommended)")
            print("2. Link - Create symlinks (changes reflect instantly)")
            print("3. Move - Move files into modpack (destructive!)")
            print("4. Back")
            print()

            choice = input("Select option (1-4): ").strip()

            if choice == "1":
                self.config["storage_mode"] = "copy"
                self._save_config()
                print("✅ Storage mode set to: Copy (safe, portable)")
            elif choice == "2":
                print("\n⚠️  WARNING: Link mode creates symlinks that point to")
                print("    original files. Changes to the source files will")
                print("    instantly affect the modpack. This mode is NOT")
                print("    portable across different computers.")
                confirm = input("Are you sure? (yes/no): ").strip().lower()
                if confirm == "yes":
                    self.config["storage_mode"] = "link"
                    self._save_config()
                    print("✅ Storage mode set to: Link (symlink)")
                else:
                    print("Cancelled.")
            elif choice == "3":
                print("\n⚠️  WARNING: Move mode will MOVE (not copy) the original")
                print("    files into the modpack folder, removing them from")
                print("    their original location. This is DESTRUCTIVE and")
                print("    can cause PERMANENT DATA LOSS.")
                print("    This mode is NOT recommended for most users.")
                confirm = input("Type 'MOVE' to confirm (any other key to cancel): ").strip()
                if confirm == "MOVE":
                    self.config["storage_mode"] = "move"
                    self._save_config()
                    print("✅ Storage mode set to: Move (destructive)")
                else:
                    print("Cancelled.")
            elif choice == "4":
                return
            else:
                print("Invalid option.")

    def _config_auto_mods(self):
        """Configure auto mods submenu"""
        # Initialize auto_mods config if not exists
        if "auto_mods" not in self.config:
            self.config["auto_mods"] = {
                "mode": "ask",  # ask, auto, never
                "mods": {}  # {loader: [project_ids]}
            }

        while True:
            print("\n" + "=" * 50)
            print("   Auto Mods Configuration")
            print("=" * 50)
            print()
            mode = self.config["auto_mods"].get("mode", "ask")
            mode_desc = {"ask": "Ask before adding", "auto": "Auto-add without asking", "never": "Never add"}
            print(f"Current mode: {mode_desc.get(mode, mode)}")
            print()
            print("1. Change auto mod mode")
            print("2. Add auto mods (-aam)")
            print("3. List auto mods (-lam)")
            print("4. Remove auto mod")
            print("5. Back")
            print()

            choice = input("Select option (1-5): ").strip()

            if choice == "1":
                print("\nSelect mode:")
                print("1. Ask before adding (prompt when creating modpack)")
                print("2. Don't ask (auto-add to every new modpack)")
                print("3. Never add (disable auto mods)")
                mode_choice = input("Select (1-3): ").strip()
                if mode_choice == "1":
                    self.config["auto_mods"]["mode"] = "ask"
                elif mode_choice == "2":
                    self.config["auto_mods"]["mode"] = "auto"
                elif mode_choice == "3":
                    self.config["auto_mods"]["mode"] = "never"
                else:
                    print("Invalid choice.")
                    continue
                self._save_config()
                print(f"✅ Auto mod mode set to: {self.config['auto_mods']['mode']}")

            elif choice == "2":
                self._add_auto_mod_interactive()
            elif choice == "3":
                self._list_auto_mods()
            elif choice == "4":
                self._remove_auto_mod()
            elif choice == "5":
                return
            else:
                print("Invalid option.")

    def _add_auto_mod_interactive(self):
        """Interactive auto mod addition"""
        print("\nAdd auto mods that will be included in every new modpack")
        print("Select loader for this auto mod:")
        loaders = ["fabric", "forge", "quilt", "neoforge"]
        for i, loader in enumerate(loaders, 1):
            existing = self.config["auto_mods"]["mods"].get(loader, [])
            count = len(existing)
            print(f"{i}. {loader.capitalize()} ({count} auto mods)")
        print("5. Back")

        choice = input("Select loader (1-5): ").strip()
        if choice not in ("1", "2", "3", "4"):
            return

        loader = loaders[int(choice) - 1]

        while True:
            project_id = input(f"\nEnter Modrinth Project ID for {loader} auto mod (or 'done'): ").strip()
            if project_id.lower() == "done":
                break
            if not project_id:
                continue

            # Verify the mod exists
            project_data = ModpackManager._fetch_modrinth_project(project_id)
            if not project_data:
                print(f"❌ Could not find mod: {project_id}")
                retry = input("Try again? (y/n): ").strip().lower()
                if retry != 'y':
                    break
                continue

            # Add to auto mods
            if loader not in self.config["auto_mods"]["mods"]:
                self.config["auto_mods"]["mods"][loader] = []

            if project_id in self.config["auto_mods"]["mods"][loader]:
                print(f"⚠️ {project_id} is already an auto mod for {loader}")
            else:
                self.config["auto_mods"]["mods"][loader].append(project_id)
                self._save_config()
                print(f"✅ Added '{project_data.get('title', project_id)}' as auto mod for {loader}")

            add_more = input("Add another? (y/n): ").strip().lower()
            if add_more != 'y':
                break

    def _list_auto_mods(self):
        """List all configured auto mods"""
        print("\n" + "=" * 50)
        print("   Auto Mods List")
        print("=" * 50)

        auto_mods = self.config.get("auto_mods", {}).get("mods", {})
        if not auto_mods:
            print("\nNo auto mods configured.")
            return

        for loader, mods in auto_mods.items():
            print(f"\n{loader.capitalize()}:")
            if not mods:
                print("  (none)")
            for project_id in mods:
                project_data = ModpackManager._fetch_modrinth_project(project_id)
                name = project_data.get("title", project_id) if project_data else project_id
                print(f"  • {name} ({project_id})")

    def _remove_auto_mod(self):
        """Remove an auto mod"""
        print("\nRemove auto mod")
        auto_mods = self.config.get("auto_mods", {}).get("mods", {})

        if not auto_mods:
            print("No auto mods configured.")
            return

        # Show all auto mods with numbers
        all_mods = []
        for loader, mods in auto_mods.items():
            for project_id in mods:
                project_data = ModpackManager._fetch_modrinth_project(project_id)
                name = project_data.get("title", project_id) if project_data else project_id
                all_mods.append((loader, project_id, name))

        if not all_mods:
            print("No auto mods to remove.")
            return

        print("\nSelect auto mod to remove:")
        for i, (loader, pid, name) in enumerate(all_mods, 1):
            print(f"{i}. {name} ({pid}) [{loader}]")
        print("0. Cancel")

        choice = input("Select (0-{}): ".format(len(all_mods))).strip()
        if choice == "0" or not choice.isdigit():
            return

        idx = int(choice) - 1
        if 0 <= idx < len(all_mods):
            loader, project_id, name = all_mods[idx]
            self.config["auto_mods"]["mods"][loader].remove(project_id)
            self._save_config()
            print(f"✅ Removed '{name}' from {loader} auto mods")

    def cmd_add_auto_mod(self, loader: Optional[str] = None, project_id: Optional[str] = None):
        """Add auto mod via CLI (-aam command)"""
        if loader is None:
            print("Usage: -aam <loader> <project_id>")
            print("  loader: fabric, forge, quilt, neoforge")
            print("  project_id: Modrinth project ID")
            return

        if project_id is None:
            print("Error: Project ID required")
            print("Usage: -aam <loader> <project_id>")
            return

        if loader not in ("fabric", "forge", "quilt", "neoforge"):
            print(f"Error: Invalid loader '{loader}'. Use: fabric, forge, quilt, neoforge")
            return

        # Verify mod exists
        project_data = ModpackManager._fetch_modrinth_project(project_id)
        if not project_data:
            print(f"❌ Could not find mod: {project_id}")
            return

        # Initialize if needed
        if "auto_mods" not in self.config:
            self.config["auto_mods"] = {"mode": "ask", "mods": {}}

        if loader not in self.config["auto_mods"]["mods"]:
            self.config["auto_mods"]["mods"][loader] = []

        if project_id in self.config["auto_mods"]["mods"][loader]:
            print(f"⚠️ {project_id} is already an auto mod for {loader}")
            return

        self.config["auto_mods"]["mods"][loader].append(project_id)
        self._save_config()
        print(f"✅ Added '{project_data.get('title', project_id)}' as auto mod for {loader}")

    def cmd_list_auto_mods(self):
        """List auto mods via CLI (-lam command)"""
        self._list_auto_mods()

    def _apply_auto_mods(self, loader: str, mc_version: str):
        """Apply auto mods to newly created modpack"""
        auto_config = self.config.get("auto_mods", {})
        mode = auto_config.get("mode", "ask")

        if mode == "never":
            return

        mods_to_add = auto_config.get("mods", {}).get(loader, [])
        if not mods_to_add:
            return

        if mode == "ask":
            print(f"\n📦 This modpack has {len(mods_to_add)} auto mod(s) for {loader}:")
            for pid in mods_to_add:
                pdata = ModpackManager._fetch_modrinth_project(pid)
                name = pdata.get("title", pid) if pdata else pid
                print(f"  • {name}")
            add_them = input("Add these auto mods? (y/n): ").strip().lower()
            if add_them not in ('y', 'yes'):
                return

        # Add each auto mod
        print(f"\n🔧 Adding auto mods for {loader}...")
        for project_id in mods_to_add:
            # Check if already added (shouldn't happen on new modpack, but safety)
            existing_mods = self._get_mods_list()
            if any(m.get("project_id") == project_id for m in existing_mods):
                continue

            # Fetch compatible version
            version_data = ModpackManager._fetch_compatible_version(project_id, loader, mc_version)
            if not version_data:
                print(f"  ⚠️ No compatible version for {project_id}")
                continue

            mod_data = self._extract_mod_data(version_data)
            if not mod_data:
                print(f"  ⚠️ Could not extract data for {project_id}")
                continue

            project_data = ModpackManager._fetch_modrinth_project(project_id)

            new_mod = {
                "project_id": project_id,
                "file_id": mod_data["file_id"],
                "name": project_data.get("title", project_id) if project_data else project_id,
                "required": True,
                "filename": mod_data["filename"],
                "downloads": mod_data["downloads"],
                "sha1": mod_data["sha1"],
                "sha512": mod_data["sha512"],
                "fileSize": mod_data["fileSize"]
            }

            existing_mods.append(new_mod)
            print(f"  ✅ Added {new_mod['name']}")

        self._save_mods_list(existing_mods)

    def cmd_add_additional(self, file_type: Optional[str] = None, file_path: Optional[str] = None):
        """Add additional files to modpack (-aa command)

        Args:
            file_type: 'config', 'icon', 'overrides', or 'other'
            file_path: Path to the file
        """
        if not self.active_modpack_path:
            print("No active modpack. Use -omp to open a modpack first.")
            return

        data = self._load_modpack_data(self.config["active_modpack"])
        if not data:
            print("Error: Cannot read modpack data!")
            return

        # Initialize additional_files if not exists
        if "additional_files" not in data:
            data["additional_files"] = {"config": [], "overrides": [], "other": [], "icon": None}

        # Interactive mode - show menu
        if file_type is None:
            print("=" * 50)
            print("   Add Additional Files")
            print("=" * 50)
            print()
            print("Select file type:")
            print("1. Icon - .png icon for the modpack (root of .mrpack)")
            print("2. Config - config files (goes to overrides/config/)")
            print("3. Overrides - general files (goes to overrides/)")
            print("4. Other - README, licenses (root of .mrpack)")
            print("5. Back")
            print()

            choice = input("Select option (1-5): ").strip()

            if choice == "1":
                file_type = "icon"
            elif choice == "2":
                file_type = "config"
            elif choice == "3":
                file_type = "overrides"
            elif choice == "4":
                file_type = "other"
            elif choice == "5":
                return
            else:
                print("Invalid option.")
                return

        # Get file path if not provided
        if file_path is None:
            prompt = "Enter file/folder path: " if file_type != "icon" else "Enter icon path (.png): "
            file_path = input(prompt).strip()

        if not file_path:
            print("Error: Path is required!")
            return

        source_path = Path(file_path).expanduser().resolve()

        # Validate path
        if not source_path.exists():
            print(f"❌ Path not found: {file_path}")
            return

        # Validate icon
        if file_type == "icon":
            if source_path.suffix.lower() != '.png':
                print("❌ Icon must be a .png file!")
                return

        # Get storage mode
        storage_mode = self.config.get("storage_mode", "copy")

        # Create _mpm_files directory structure
        mpm_files_dir = self.active_modpack_path / "_mpm_files"
        type_dir = mpm_files_dir / file_type if file_type != "icon" else mpm_files_dir
        type_dir.mkdir(parents=True, exist_ok=True)

        # Calculate destination path in _mpm_files
        if file_type == "icon":
            dest_path = type_dir / "icon.png"
        else:
            dest_path = type_dir / source_path.name

        try:
            # Handle based on storage mode
            if storage_mode == "copy":
                if source_path.is_file():
                    shutil.copy2(str(source_path), str(dest_path))
                else:
                    if dest_path.exists():
                        shutil.rmtree(str(dest_path))
                    shutil.copytree(str(source_path), str(dest_path))
                print(f"📋 Copied to: {dest_path}")

            elif storage_mode == "link":
                # Create symlink
                if dest_path.exists() or dest_path.is_symlink():
                    dest_path.unlink()
                dest_path.symlink_to(source_path, target_is_directory=source_path.is_dir())
                print(f"🔗 Linked to: {dest_path}")

            elif storage_mode == "move":
                if dest_path.exists():
                    if dest_path.is_dir():
                        shutil.rmtree(str(dest_path))
                    else:
                        dest_path.unlink()
                shutil.move(str(source_path), str(dest_path))
                print(f"📦 Moved to: {dest_path}")

            # Store the reference in modpack data (pointing to _mpm_files location)
            stored_ref = str(dest_path.relative_to(self.active_modpack_path))

            if file_type == "icon":
                data["additional_files"]["icon"] = stored_ref
                print(f"✅ Icon added: {source_path.name}")
            else:
                current_list = data["additional_files"].get(file_type, [])
                if stored_ref in current_list:
                    print(f"⚠️ This {file_type} file is already added!")
                    return
                current_list.append(stored_ref)
                data["additional_files"][file_type] = current_list
                print(f"✅ Added {file_type} file: {source_path.name}")

            # Save updated data directly to modpack.json
            modpack_json_path = self.active_modpack_path / "modpack.json"
            self._write_json(modpack_json_path, data)

            print(f"   Storage mode: {storage_mode}")

        except Exception as e:
            print(f"❌ Error handling file: {e}")

    def cmd_remove_additional(self):
        """Remove additional files from modpack (-ra command)"""
        if not self.active_modpack_path:
            print("No active modpack. Use -omp to open a modpack first.")
            return

        data = self._load_modpack_data(self.config["active_modpack"])
        if not data:
            print("Error: Cannot read modpack data!")
            return

        additional_files = data.get("additional_files", {})

        # Collect all files for display
        all_items = []

        # Icon
        icon = additional_files.get("icon")
        if icon:
            path = Path(icon)
            all_items.append(("icon", icon, f"🎨 Icon: {path.name}"))

        # Config files
        config_files = additional_files.get("config", [])
        for cf in config_files:
            path = Path(cf)
            all_items.append(("config", cf, f"⚙️  Config: {path.name}"))

        # Overrides files
        overrides_files = additional_files.get("overrides", [])
        for of in overrides_files:
            path = Path(of)
            all_items.append(("overrides", of, f"📁 Overrides: {path.name}"))

        # Other files
        other_files = additional_files.get("other", [])
        for of in other_files:
            path = Path(of)
            all_items.append(("other", of, f"📄 Other: {path.name}"))

        if not all_items:
            print("No additional files configured for this modpack.")
            return

        print("=" * 50)
        print("   Remove Additional Files")
        print("=" * 50)
        print()
        print("Configured additional files:")

        for i, (ftype, fpath, display) in enumerate(all_items, 1):
            print(f"{i}. {display}")

        print("0. Cancel")
        print()

        choice = input(f"Select file to remove (0-{len(all_items)}): ").strip()

        if choice == "0":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_items):
                ftype, fpath, display = all_items[idx]

                # Remove from data
                if ftype == "icon":
                    data["additional_files"]["icon"] = None
                else:
                    data["additional_files"][ftype].remove(fpath)

                # Save updated data first
                modpack_json_path = self.active_modpack_path / "modpack.json"
                self._write_json(modpack_json_path, data)

                # Optionally delete physical file
                physical_path = self.active_modpack_path / fpath
                if physical_path.exists():
                    delete_phys = input(f"Delete physical file from _mpm_files? (y/n): ").strip().lower()
                    if delete_phys == 'y':
                        try:
                            if physical_path.is_dir():
                                shutil.rmtree(str(physical_path))
                            else:
                                physical_path.unlink()
                            print(f"🗑️  Deleted: {physical_path.name}")
                        except Exception as e:
                            print(f"⚠️  Could not delete file: {e}")

                print(f"✅ Removed {ftype} from modpack")
            else:
                print("Invalid selection!")
        except ValueError:
            print("Please enter a valid number!")


    def cmd_export_modpack(self):
        """Export modpack to JSON file for sharing"""
        if not self.active_modpack_path:
            print("No active modpack. Use -omp to open a modpack first.")
            return

        info = self._get_modpack_info(self.config["active_modpack"])
        mods = self._get_mods_list()

        if not info:
            print("Error: Cannot read modpack data!")
            return

        # Create export data structure
        export_data = {
            "format": "mpm-export",
            "formatVersion": 1,
            "modpack": {
                "name": info["name"],
                "version": info["version"],
                "mc_version": info["mc_version"],
                "loader": info["loader"],
                "loader_version": info["loader_version"]
            },
            "mods": mods if mods else []
        }

        # Get export path
        default_filename = f"{info['name'].replace(' ', '_')}_v{info['version']}.json"
        print(f"Default filename: {default_filename}")
        export_path = input("Enter export path (press Enter for default): ").strip()
        
        if not export_path:
            export_path = Path(self.config["storage_path"]) / default_filename
        else:
            export_path = Path(export_path).expanduser()

        # Ensure .json extension
        if not str(export_path).endswith('.json'):
            export_path = Path(str(export_path) + '.json')

        # Check if file exists
        if export_path.exists():
            overwrite = input(f"File '{export_path}' exists. Overwrite? (y/n): ").strip().lower()
            if overwrite != 'y':
                print("Export cancelled.")
                return

        try:
            self._write_json(export_path, export_data)

            print(f"\n✅ Modpack exported successfully!")
            print(f"📄 File: {export_path}")
            print(f"📦 {info['name']} v{info['version']}")
            print(f"🎮 MC {info['mc_version']} | {info['loader'].capitalize()} {info['loader_version']}")
            print(f"📊 Mods: {len(mods) if mods else 0}")
        except Exception as e:
            print(f"❌ Error exporting modpack: {e}")

    def cmd_import_modrinth(self):
        """Import modpack from modrinth.index.json file"""
        if not self._ensure_storage_path():
            return

        # Get the path to modrinth.index.json
        file_path = input("Enter path to modrinth.index.json file: ").strip()
        if not file_path:
            print("Error: File path is required!")
            return

        # Expand user path (~/...)
        file_path = Path(file_path).expanduser()
        
        if not file_path.exists():
            print(f"Error: File '{file_path}' not found!")
            return

        index_data = self._read_json(file_path)
        if index_data is None:
            print("Error: Could not read JSON file or file is empty!")
            return

        # Validate format
        if "formatVersion" not in index_data:
            print("Error: Invalid modrinth.index.json format!")
            return

        # Get modpack name
        default_name = index_data.get("name", "Imported Modpack")
        print(f"Default name: {default_name}")
        name = input(f"Enter modpack name (press Enter for '{default_name}'): ").strip()
        if not name:
            name = default_name

        # Check if modpack with same name exists
        modpack_path = Path(self.config["storage_path"]) / name
        if modpack_path.exists():
            print(f"Error: Modpack '{name}' already exists!")
            return

        # Extract dependencies
        dependencies = index_data.get("dependencies", {})
        mc_version = dependencies.get("minecraft", "unknown")
        
        # Detect loader
        loader = "unknown"
        loader_version = "unknown"
        for dep_key, dep_value in dependencies.items():
            if dep_key == "minecraft":
                continue
            if "fabric" in dep_key.lower():
                loader = "fabric"
                loader_version = dep_value
            elif "forge" in dep_key.lower():
                loader = "forge"
                loader_version = dep_value
            elif "quilt" in dep_key.lower():
                loader = "quilt"
                loader_version = dep_value

        # Get modpack version
        version = index_data.get("versionId", "1.0.0")

        # Create modpack folder
        modpack_path.mkdir(parents=True, exist_ok=True)

        # Process mods
        files = index_data.get("files", [])
        mods = []
        
        print(f"\n🔍 Processing {len(files)} mods...")
        
        for file_data in files:
            mod_filename = file_data.get("path", "").replace("mods/", "")
            hashes = file_data.get("hashes", {})
            downloads = file_data.get("downloads", [])
            
            if not mod_filename or not downloads:
                continue

            # Try to get project info from Modrinth API using hash
            project_id = None
            sha1_hash = hashes.get("sha1", "")
            
            if sha1_hash:
                project_id, file_id = ModpackManager._lookup_mod_by_hash(sha1_hash)

            # If we couldn't get project_id from API, use filename as placeholder
            if not project_id:
                project_id = f"unknown_{mod_filename}"
                file_id = "unknown"

            mod_entry = {
                "project_id": project_id,
                "file_id": file_id if file_id else "unknown",
                "name": mod_filename.replace(".jar", ""),
                "required": True,
                "filename": mod_filename,
                "downloads": downloads[0] if downloads else "",
                "sha1": hashes.get("sha1", ""),
                "sha512": hashes.get("sha512", ""),
                "fileSize": file_data.get("fileSize", 0)
            }
            mods.append(mod_entry)
            print(f"  • {mod_entry['name']}")

        # Create unified modpack.json
        modpack_data = {
            "name": name,
            "version": version,
            "mc_version": mc_version,
            "loader": loader,
            "loader_version": loader_version,
            "mods": mods
        }
        self._write_json(modpack_path / "modpack.json", modpack_data)

        # Create build folder with the imported index
        build_folder = modpack_path / "build"
        build_folder.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(file_path), str(build_folder / "modrinth.index.json"))

        # Activate the modpack
        self.config["active_modpack"] = name
        self._save_config()
        self._update_active_path()

        # Calculate required/optional counts
        required_count = sum(1 for m in mods if m.get("required", True))
        optional_count = len(mods) - required_count

        print(f"\n✅ Modpack '{name}' imported successfully!")
        print("=" * 50)
        print(f"📦 {name}")
        print("=" * 50)
        print(f"  Modpack Version: {version}")
        print(f"  Minecraft:       {mc_version}")
        print(f"  Loader:          {loader.capitalize()} {loader_version}")
        print(f"  Mods Count:      {len(mods)}")
        print(f"  Required Mods:   {required_count}")
        print(f"  Optional Mods:   {optional_count}")
        print(f"  Storage Path:    {modpack_path}")
        print(f"  Status:          ✅ Imported & Active")
        print("=" * 50)
        print(f"Note: Some mods may need project ID correction via Modrinth API")

    def cmd_import_modpack(self):
        """Import modpack from app export file"""
        if not self._ensure_storage_path():
            return

        # Get the path to export file
        file_path = input("Enter path to export .json file: ").strip()
        if not file_path:
            print("Error: File path is required!")
            return

        # Expand user path (~/...)
        file_path = Path(file_path).expanduser()
        
        if not file_path.exists():
            print(f"Error: File '{file_path}' not found!")
            return

        export_data = self._read_json(file_path)
        if export_data is None:
            print("Error: Could not read JSON file or file is empty!")
            return

        # Validate format
        if export_data.get("format") != "mpm-export":
            print("Error: Invalid export file format!")
            print("This command imports .json files exported by this app.")
            print("Use -imp-mr to import modrinth.index.json files.")
            return

        # Get modpack info from export
        modpack_info = export_data.get("modpack", {})
        default_name = modpack_info.get("name", "Imported Modpack")
        
        print(f"\n📦 Found modpack: {default_name}")
        print(f"   Version: {modpack_info.get('version', 'unknown')}")
        print(f"   MC: {modpack_info.get('mc_version', 'unknown')}")
        print(f"   Loader: {modpack_info.get('loader', 'unknown')} {modpack_info.get('loader_version', 'unknown')}")
        
        name = input(f"\nEnter modpack name (press Enter for '{default_name}'): ").strip()
        if not name:
            name = default_name

        # Check if modpack with same name exists
        modpack_path = Path(self.config["storage_path"]) / name
        if modpack_path.exists():
            print(f"Error: Modpack '{name}' already exists!")
            return

        # Create modpack folder
        modpack_path.mkdir(parents=True, exist_ok=True)

        # Get mods from export
        mods = export_data.get("mods", [])
        
        # Create unified modpack.json
        modpack_data = {
            "name": name,
            "version": modpack_info.get("version", "1.0.0"),
            "mc_version": modpack_info.get("mc_version", "1.20.1"),
            "loader": modpack_info.get("loader", "fabric"),
            "loader_version": modpack_info.get("loader_version", "unknown"),
            "mods": mods
        }
        self._write_json(modpack_path / "modpack.json", modpack_data)

        print(f"\n🔍 Imported {len(mods)} mods")
        for mod in mods:
            print(f"  • {mod.get('name', 'Unknown')}")

        # Activate the modpack
        self.config["active_modpack"] = name
        self._save_config()
        self._update_active_path()

        # Calculate required/optional counts
        required_count = sum(1 for m in mods if m.get("required", True))
        optional_count = len(mods) - required_count

        print(f"\n✅ Modpack '{name}' imported successfully!")
        print("=" * 50)
        print(f"📦 {name}")
        print("=" * 50)
        print(f"  Modpack Version: {modpack_data['version']}")
        print(f"  Minecraft:       {modpack_data['mc_version']}")
        print(f"  Loader:          {modpack_data['loader'].capitalize()} {modpack_data['loader_version']}")
        print(f"  Mods Count:      {len(mods)}")
        print(f"  Required Mods:   {required_count}")
        print(f"  Optional Mods:   {optional_count}")
        print(f"  Storage Path:    {modpack_path}")
        print(f"  Status:          ✅ Imported & Active")
        print("=" * 50)

    def cmd_add_mod(self, project_id: Optional[str] = None, required: Optional[bool] = None):
        """Add mod to active modpack
        
        Args:
            project_id: Modrinth Project ID (optional, will prompt if not provided)
            required: True for required mod, False for optional mod (optional, will prompt if not provided)
        """
        if not self.active_modpack_path:
            print("No active modpack. Use -n to create a modpack or -omp to open an existing one.")
            return

        if project_id is None:
            project_id = input("Enter Project ID from Modrinth: ").strip()
        if not project_id:
            print("Error: Project ID is required!")
            return

        # Fetch project data
        project_data = self._fetch_modrinth_project(project_id)
        if not project_data:
            return

        print(f"📦 Mod: {project_data.get('title', 'Unknown')}")
        
        if required is None:
            required_input = input("Is this mod required? (y/n): ").strip().lower()
            required = required_input == 'y'

        # Fetch active modpack info
        info = self._get_modpack_info(self.config["active_modpack"])
        if not info:
            print("Error: Cannot read modpack data!")
            return

        loader = info["loader"]
        mc_version = info["mc_version"]

        print(f"🔍 Searching for compatible version ({loader} + {mc_version})...")
        
        # Search for compatible version
        version_data = self._fetch_compatible_version(project_id, loader, mc_version)
        if not version_data:
            print(f"❌ No compatible version found for mod {project_id}")
            print(f"   Loader: {loader}")
            print(f"   Minecraft version: {mc_version}")
            return

        # Extract file data
        mod_data = self._extract_mod_data(version_data)
        if not mod_data:
            print("Error: Cannot extract file data from version!")
            return

        # Check if mod already exists
        mods = self._get_mods_list() or []
        for mod in mods:
            if mod["project_id"] == project_id:
                print(f"⚠️ Mod {project_id} already exists in this modpack!")
                return

        # Add mod
        new_mod = {
            "project_id": project_id,
            "file_id": mod_data["file_id"],
            "name": project_data.get("title", project_id),
            "required": required,
            "filename": mod_data["filename"],
            "downloads": mod_data["downloads"],
            "sha1": mod_data["sha1"],
            "sha512": mod_data["sha512"],
            "fileSize": mod_data["fileSize"]
        }

        mods.append(new_mod)

        # Resolve required dependencies
        deps = version_data.get("dependencies", [])
        required_deps = [d for d in deps if d.get("dependency_type") == "required"]
        if required_deps:
            print(f"\n📦 This mod has {len(required_deps)} required dependencies:")
            for dep in required_deps:
                dep_pid = dep.get("project_id", "unknown")
                dep_data = ModpackManager._fetch_modrinth_project(dep_pid)
                dep_name = dep_data.get("title", dep_pid) if dep_data else dep_pid
                print(f"  • {dep_name} ({dep_pid})")
            add_deps = input("Add all required dependencies? (y/n): ").strip().lower()
            if add_deps == 'y':
                for dep in required_deps:
                    dep_pid = dep.get("project_id")
                    if not dep_pid or any(m["project_id"] == dep_pid for m in mods):
                        continue
                    dep_version = ModpackManager._fetch_compatible_version(dep_pid, loader, mc_version)
                    if dep_version:
                        dep_project = ModpackManager._fetch_modrinth_project(dep_pid)
                        dep_mod_data = self._extract_mod_data(dep_version)
                        if dep_mod_data:
                            mods.append({
                                "project_id": dep_pid,
                                "file_id": dep_mod_data["file_id"],
                                "name": dep_project.get("title", dep_pid) if dep_project else dep_pid,
                                "required": True,
                                "filename": dep_mod_data["filename"],
                                "downloads": dep_mod_data["downloads"],
                                "sha1": dep_mod_data["sha1"],
                                "sha512": dep_mod_data["sha512"],
                                "fileSize": dep_mod_data["fileSize"]
                            })
                            print(f"  ✅ Added dependency '{dep_project.get('title', dep_pid) if dep_project else dep_pid}'")
                        else:
                            print(f"  ⚠️ Could not extract file data for dependency {dep_pid}")
                    else:
                        print(f"  ⚠️ No compatible version found for dependency {dep_pid}")

        self._save_mods_list(mods)

        print(f"\n✅ Added mod '{new_mod['name']}' successfully!")
        print(f"   File: {new_mod['filename']}")
        print(f"   Required: {'Yes' if required else 'No'}")

    def cmd_remove_mod(self):
        """Remove mod from active modpack"""
        if not self.active_modpack_path:
            print("No active modpack.")
            return

        mods = self._get_mods_list()
        if not mods:
            print("Modpack has no mods.")
            return

        print("📋 Mod list:")
        for i, mod in enumerate(mods, 1):
            req_status = "required" if mod.get("required", True) else "optional"
            print(f"{i}. {mod['name']} ({req_status})")

        choice = input("Enter mod number to remove (or 0 to cancel): ").strip()
        if choice == "0":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(mods):
                mod_name = mods[idx]['name']
                confirm = input(f"Delete '{mod_name}'? (y/n): ").strip().lower()
                if confirm == 'y':
                    removed = mods.pop(idx)
                    self._save_mods_list(mods)
                    print(f"✅ Removed mod '{removed['name']}' successfully!")
                else:
                    print("Deletion cancelled.")
            else:
                print("Invalid number!")
        except ValueError:
            print("Please enter a valid number!")

    def cmd_list_mods(self):
        """List mods in active modpack"""
        if not self.active_modpack_path:
            print("No active modpack.")
            return

        info = self._get_modpack_info(self.config["active_modpack"])
        mods = self._get_mods_list()

        if not mods:
            print(f"📦 Modpack: {info['name'] if info else 'Unknown'}")
            print("No mods added.")
            return

        print(f"📦 Modpack: {info['name'] if info else 'Unknown'} ({info.get('mc_version', 'Unknown')})")
        print("📋 Mod list:")
        for i, mod in enumerate(mods, 1):
            req_status = "✓ required" if mod.get("required", True) else "○ optional"
            print(f"{i}. {mod['name']} [{req_status}]")

        # Modify required status
        print("\nTo change required status, enter: required <number> y/n")
        print("Or press Enter to return")
        cmd = input("> ").strip()
        
        if cmd.startswith("required "):
            parts = cmd.split()
            if len(parts) >= 3:
                try:
                    idx = int(parts[1]) - 1
                    new_val = parts[2].lower() == 'y'
                    if 0 <= idx < len(mods):
                        mods[idx]["required"] = new_val
                        self._save_mods_list(mods)
                        status = "required" if new_val else "optional"
                        print(f"✅ Changed '{mods[idx]['name']}' to {status}")
                    else:
                        print("Invalid number!")
                except ValueError:
                    print("Use format: required <number> y/n")

    def cmd_list_modpacks(self):
        """List all modpacks"""
        if not self._ensure_storage_path():
            return

        storage_path = Path(self.config["storage_path"])
        if not storage_path.exists():
            print("No modpacks found.")
            return

        modpacks = [d for d in storage_path.iterdir() if d.is_dir()]
        
        if not modpacks:
            print("No modpacks found.")
            return

        active = self.config.get("active_modpack")
        print("📁 Modpack list:")
        
        for mp in modpacks:
            info = self._get_modpack_info(mp.name)
            status = " (active)" if mp.name == active else ""
            version = info.get("mc_version", "?") if info else "?"
            loader = info.get("loader", "?") if info else "?"
            print(f"  • {mp.name} [{loader} {version}]{status}")

    def cmd_modpack_info(self):
        """Show detailed info about active modpack"""
        if not self.active_modpack_path:
            print("No active modpack.")
            return

        info = self._get_modpack_info(self.config["active_modpack"])
        mods = self._get_mods_list()

        if not info:
            print("Error: Cannot read modpack data!")
            return

        print("=" * 50)
        print(f"📦 {info['name']}")
        print("=" * 50)
        print(f"  Modpack Version: {info['version']}")
        print(f"  Minecraft:       {info['mc_version']}")
        print(f"  Loader:          {info['loader'].capitalize()} {info['loader_version']}")
        print(f"  Mods Count:      {len(mods) if mods else 0}")
        print(f"  Storage Path:    {self.active_modpack_path}")
        
        if mods:
            required_count = sum(1 for m in mods if m.get("required", True))
            optional_count = len(mods) - required_count
            print(f"  Required Mods:   {required_count}")
            print(f"  Optional Mods:   {optional_count}")
        
        # Check if build folder exists
        build_folder = self.active_modpack_path / "build"
        archive_folder = self.active_modpack_path / "build_archive"
        
        if build_folder.exists() and (build_folder / "modrinth.index.json").exists():
            print(f"  Status:          ✅ Built (ready for export)")
        else:
            print(f"  Status:          ⚠️ Not built yet (use -mpb)")
        
        # Count archived builds
        if archive_folder.exists():
            archived_builds = list(archive_folder.glob("build_*"))
            if archived_builds:
                print(f"  Archived Builds: {len(archived_builds)}")
        
        print("=" * 50)

    def cmd_remove_modpack(self):
        """Remove modpack completely"""
        if not self._ensure_storage_path():
            return

        storage_path = Path(self.config["storage_path"])
        if not storage_path.exists():
            print("No modpacks found.")
            return

        modpacks = [d for d in storage_path.iterdir() if d.is_dir()]
        if not modpacks:
            print("No modpacks found.")
            return

        print("📁 Modpacks available for removal:")
        for i, mp in enumerate(modpacks, 1):
            info = self._get_modpack_info(mp.name)
            version = info.get("mc_version", "?") if info else "?"
            print(f"{i}. {mp.name} ({version})")

        choice = input("Enter modpack number to remove (or 0 to cancel): ").strip()
        if choice == "0":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(modpacks):
                target = modpacks[idx]
                confirm = input(f"Are you sure you want to delete '{target.name}'? (y/n): ").strip().lower()
                if confirm == 'y':
                    shutil.rmtree(target)
                    
                    # If deleted modpack was active, deactivate it
                    if self.config.get("active_modpack") == target.name:
                        self.config["active_modpack"] = None
                        self._update_active_path()
                    
                    self._save_config()
                    print(f"✅ Deleted modpack '{target.name}' successfully!")
                else:
                    print("Deletion cancelled.")
            else:
                print("Invalid number!")
        except ValueError:
            print("Please enter a valid number!")

    def cmd_build(self):
        """Build modrinth.index.json file"""
        if not self.active_modpack_path:
            print("No active modpack.")
            return

        info = self._get_modpack_info(self.config["active_modpack"])
        mods = self._get_mods_list()

        if not info:
            print("Error: Cannot read modpack data!")
            return

        if not mods:
            print("⚠️ Warning: Modpack has no mods!")

        # Build JSON structure - only include mods with complete data
        files_list = []
        supported_mods = []
        unsupported_mods = []
        
        for mod in mods:
            # Check if mod has required fields for building
            has_required_fields = (
                mod.get("file_id") and 
                mod.get("file_id") != "unknown" and
                mod.get("downloads") and
                mod.get("sha1") and
                mod.get("sha512")
            )
            
            if has_required_fields:
                files_list.append({
                    "path": f"mods/{mod['filename']}",
                    "hashes": {
                        "sha1": mod.get("sha1", ""),
                        "sha512": mod.get("sha512", "")
                    },
                    "env": {
                        "client": "required" if mod.get("required", True) else "optional",
                        "server": "required" if mod.get("required", True) else "optional"
                    },
                    "downloads": [mod.get("downloads", "")],
                    "fileSize": mod.get("fileSize", 0)
                })
                supported_mods.append(mod["name"])
            else:
                unsupported_mods.append(mod["name"])

        # تحديد حقل dependencies
        loader_dep = LOADER_DEPENDENCY_MAP.get(info["loader"], f"{info['loader']}-loader")
        
        index_data = {
            "formatVersion": 1,
            "game": "minecraft",
            "versionId": info["version"],
            "name": info["name"],
            "files": files_list,
            "dependencies": {
                loader_dep: info["loader_version"],
                "minecraft": info["mc_version"]
            }
        }

        # Create output folder
        output_folder = self.active_modpack_path / "build"
        output_folder.mkdir(parents=True, exist_ok=True)

        # Check if old .mrpack exists and ask about archiving
        mrpack_filename = f"{info['name'].replace(' ', '_')}-{info['version']}.mrpack"
        mrpack_path = output_folder / mrpack_filename

        archive_old = False
        if mrpack_path.exists():
            archive_choice = input("Old build exists. Archive it? (y/n): ").strip().lower()
            if archive_choice == 'y':
                archive_old = True

        # Archive old build if requested
        if archive_old:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_folder = self.active_modpack_path / "build_archive" / f"build_{timestamp}"
            archive_folder.mkdir(parents=True, exist_ok=True)

            # Move old .mrpack to archive
            shutil.move(str(mrpack_path), str(archive_folder / mrpack_filename))

            # Also copy modpack.json for complete backup
            modpack_json_path = self.active_modpack_path / "modpack.json"
            if modpack_json_path.exists():
                shutil.copy(str(modpack_json_path), str(archive_folder / "modpack.json"))

            print(f"📦 Old build archived: {archive_folder}")

            # Cleanup old archives (keep max 10)
            self._cleanup_old_archives()

        # Load additional files from full modpack data
        modpack_data = self._load_modpack_data(self.config["active_modpack"])
        additional_files = modpack_data.get("additional_files", {}) if modpack_data else {}

        # Structure to hold files with their destination paths in .mrpack
        # Each item: (source_path, arcname_in_zip)
        files_to_include = []
        icon_path = None

        def resolve_path(stored_path):
            """Resolve stored path to absolute path, handling symlinks"""
            if Path(stored_path).is_absolute():
                path = Path(stored_path).expanduser().resolve()
            else:
                # Relative to modpack directory
                path = (self.active_modpack_path / stored_path).resolve()
            # Resolve symlinks to get actual content
            if path.is_symlink():
                target = path.readlink()
                if not target.is_absolute():
                    target = path.parent / target
                path = target.resolve()
            return path if path.exists() else None

        # Load config files -> go to overrides/config/
        for cf in additional_files.get("config", []):
            path = resolve_path(cf)
            if path:
                if path.is_file():
                    files_to_include.append((path, f"overrides/config/{path.name}"))
                elif path.is_dir():
                    for file in path.rglob("*"):
                        if file.is_file():
                            arcname = f"overrides/config/{path.name}/{file.relative_to(path).as_posix()}"
                            files_to_include.append((file, arcname))

        # Load overrides files -> go to overrides/
        for of in additional_files.get("overrides", []):
            path = resolve_path(of)
            if path:
                if path.is_file():
                    files_to_include.append((path, f"overrides/{path.name}"))
                elif path.is_dir():
                    for file in path.rglob("*"):
                        if file.is_file():
                            arcname = f"overrides/{path.name}/{file.relative_to(path).as_posix()}"
                            files_to_include.append((file, arcname))

        # Load other files -> go to root of .mrpack
        for of in additional_files.get("other", []):
            path = resolve_path(of)
            if path:
                if path.is_file():
                    files_to_include.append((path, path.name))
                elif path.is_dir():
                    for file in path.rglob("*"):
                        if file.is_file():
                            arcname = f"{path.name}/{file.relative_to(path).as_posix()}"
                            files_to_include.append((file, arcname))

        # Load icon
        icon_file = additional_files.get("icon")
        if icon_file:
            path = resolve_path(icon_file)
            if path and path.suffix.lower() == '.png':
                icon_path = path

        # Create .mrpack ZIP file directly (no separate modrinth.index.json)
        try:
            with zipfile.ZipFile(mrpack_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Create modrinth.index.json in memory and add to zip
                index_json = json.dumps(index_data, indent=2, ensure_ascii=False)
                zf.writestr("modrinth.index.json", index_json)

                # Add modpack.json as metadata backup
                modpack_json_path = self.active_modpack_path / "modpack.json"
                if modpack_json_path.exists():
                    zf.write(modpack_json_path, "modpack.json")

                # Add icon if provided
                if icon_path:
                    zf.write(icon_path, "icon.png")

                # Add extra files with proper arcnames
                for source_path, arcname in files_to_include:
                    zf.write(source_path, arcname)

            print(f"\n✅ Modpack built successfully!")
            print(f"📁 Folder: {output_folder}")
            print(f"📦 .mrpack export: {mrpack_path}")
            print(f"📊 Total mods in modpack: {len(mods)}")
            print(f"✓ Included in build: {len(supported_mods)}")
            if unsupported_mods:
                print(f"⚠ Excluded from build: {len(unsupported_mods)} ({', '.join(unsupported_mods)})")
            if files_to_include:
                print(f"📎 Extra files included: {len(files_to_include)}")
            if icon_path:
                print(f"🎨 Icon included: {icon_path.name}")
            if archive_old:
                print(f"📦 Previous build archived")
        except Exception as e:
            print(f"❌ Error creating .mrpack file: {e}")

    def cmd_version_change(self):
        """Change modpack version and update all mods to latest versions"""
        if not self._ensure_storage_path():
            return

        storage_path = Path(self.config["storage_path"])
        modpacks = [d for d in storage_path.iterdir() if d.is_dir()]
        
        if not modpacks:
            print("No modpacks found.")
            return

        print("📁 Modpacks available for version change:")
        for i, mp in enumerate(modpacks, 1):
            info = self._get_modpack_info(mp.name)
            version = info.get("mc_version", "?") if info else "?"
            loader = info.get("loader", "?") if info else "?"
            mp_version = info.get("version", "?") if info else "?"
            print(f"{i}. {mp.name} [v{mp_version} | {loader} {version}]")

        choice = input("Enter modpack number: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(modpacks):
                target = modpacks[idx]
                info = self._get_modpack_info(target.name)
                
                if not info:
                    print("Error: Cannot read modpack data!")
                    return

                print(f"\n📦 Modpack: {info['name']}")
                print(f"Current modpack version: {info['version']}")
                print(f"Current Minecraft version: {info['mc_version']}")
                
                # Ask for new modpack version
                new_mp_version = input("Enter new modpack version (e.g., 2.0.0): ").strip()
                if not new_mp_version:
                    print("Operation cancelled.")
                    return
                
                # Ask if they want to change Minecraft version
                change_mc = input("Change Minecraft version too? (y/n): ").strip().lower()
                new_mc_version = info['mc_version']
                if change_mc == 'y':
                    new_mc_version = input(f"Enter new Minecraft version (current: {info['mc_version']}): ").strip()
                    if not new_mc_version:
                        new_mc_version = info['mc_version']

                loader = info["loader"]
                modpack_data = self._load_modpack_data(target.name)

                if not modpack_data:
                    print("Error: Cannot read modpack data!")
                    return

                # Validate loader availability for new MC version
                if change_mc == 'y':
                    print(f"🔍 Checking {loader.capitalize()} availability for MC {new_mc_version}...")
                    new_loader_version = ModpackManager._get_latest_loader_version(loader, new_mc_version)
                    if new_loader_version:
                        print(f"✅ Compatible {loader.capitalize()} version found: {new_loader_version}")
                        update_loader = input("Update loader version too? (y/n): ").strip().lower()
                        if update_loader == 'y':
                            modpack_data["loader_version"] = new_loader_version
                    else:
                        print(f"⚠️ No {loader.capitalize()} version found for MC {new_mc_version}. Mods may not work!")
                        proceed = input("Continue anyway? (y/n): ").strip().lower()
                        if proceed != 'y':
                            print("Version change cancelled.")
                            return

                current_mods = modpack_data.get("mods", [])

                if not current_mods:
                    print("No mods to update.")
                    # Update modpack version only
                    modpack_data["version"] = new_mp_version
                    modpack_data["mc_version"] = new_mc_version
                    self._save_modpack_data(
                        modpack_data["name"],
                        new_mp_version,
                        new_mc_version,
                        modpack_data["loader"],
                        modpack_data["loader_version"],
                        []
                    )
                    print(f"✅ Updated modpack to v{new_mp_version} (MC {new_mc_version})")
                    return

                print(f"\n🔍 Searching for latest mod versions for {loader} {new_mc_version}...")
                
                available = []
                unavailable = []
                
                for mod in current_mods:
                    print(f"  • {mod['name']} ...", end=" ", flush=True)
                    version_data = self._fetch_compatible_version(mod["project_id"], loader, new_mc_version)
                    
                    if version_data:
                        mod_data = self._extract_mod_data(version_data)
                        if mod_data:
                            # Check if this is actually a newer version
                            is_update = mod["file_id"] != mod_data["file_id"]
                            status_icon = "⬆️" if is_update else "✅"
                            available.append({
                                "project_id": mod["project_id"],
                                "file_id": mod_data["file_id"],
                                "name": mod["name"],
                                "required": mod.get("required", True),
                                "filename": mod_data["filename"],
                                "downloads": mod_data["downloads"],
                                "sha1": mod_data["sha1"],
                                "sha512": mod_data["sha512"],
                                "fileSize": mod_data["fileSize"]
                            })
                            print(f"{status_icon}")
                        else:
                            unavailable.append(mod["name"])
                            print("❌")
                    else:
                        unavailable.append(mod["name"])
                        print("❌")

                print(f"\n📊 Report:")
                print(f"  Updated: {len(available)}/{len(current_mods)}")
                if unavailable:
                    print(f"  Unavailable: {', '.join(unavailable)}")

                # Ask if user wants to keep unsupported mods
                keep_unsupported = 'n'
                if unavailable:
                    keep_unsupported = input("\nKeep unsupported mods with old versions? (y/n): ").strip().lower()
                
                confirm = input("\nProceed with version change? (y/n): ").strip().lower()
                if confirm == 'y':
                    # Build final mods list
                    final_mods = available.copy()
                    
                    # Add unsupported mods if user chose to keep them
                    if keep_unsupported == 'y':
                        for mod in current_mods:
                            if mod["name"] in unavailable:
                                # Check if not already in available (shouldn't happen)
                                if not any(m["project_id"] == mod["project_id"] for m in final_mods):
                                    final_mods.append(mod)
                                    print(f"  ⚠️ Kept '{mod['name']}' with old version (may be incompatible)")
                    
                    # Update files using unified modpack.json
                    modpack_data = {
                        "name": info["name"],
                        "version": new_mp_version,
                        "mc_version": new_mc_version,
                        "loader": info["loader"],
                        "loader_version": info["loader_version"],
                        "mods": final_mods
                    }
                    self._write_json(target / "modpack.json", modpack_data)

                    removed_count = len(unavailable) if keep_unsupported != 'y' else 0
                    kept_count = len(unavailable) if keep_unsupported == 'y' else 0
                    
                    print(f"✅ Modpack updated to v{new_mp_version} successfully!")
                    print(f"   Minecraft: {new_mc_version}")
                    print(f"   {len(available)} mods updated", end="")
                    if removed_count > 0:
                        print(f", {removed_count} mods removed")
                    elif kept_count > 0:
                        print(f", {kept_count} old versions kept")
                    else:
                        print()
                else:
                    print("Version change cancelled.")
            else:
                print("Invalid number!")
        except ValueError:
            print("Please enter a valid number!")

    def cmd_update_mods(self):
        """Check for mod updates and update selected mods"""
        if not self._ensure_storage_path():
            return
        
        if not self.active_modpack_path:
            print("No active modpack. Use -omp to open a modpack first.")
            return
        
        info = self._get_modpack_info(self.config["active_modpack"])
        if not info:
            print("Error: Cannot read modpack data!")
            return
        
        loader = info["loader"]
        mc_version = info["mc_version"]
        current_mods = self._get_mods_list()
        
        if not current_mods:
            print("No mods in active modpack.")
            return
        
        print(f"🔍 Checking for mod updates ({loader} {mc_version})...")
        print(f"   Modpack: {info['name']} v{info['version']}")
        print()
        
        updates_available = []
        up_to_date = []
        check_failed = []
        
        for i, mod in enumerate(current_mods, 1):
            print(f"  {i}/{len(current_mods)} {mod['name']} ...", end=" ", flush=True)
            
            version_data = self._fetch_compatible_version(mod["project_id"], loader, mc_version)
            
            if version_data:
                mod_data = self._extract_mod_data(version_data)
                if mod_data:
                    if mod["file_id"] != mod_data["file_id"]:
                        updates_available.append({
                            "index": i - 1,
                            "old_mod": mod,
                            "new_data": mod_data
                        })
                        print("⬆️ Update available")
                    else:
                        up_to_date.append(mod["name"])
                        print("✅ Up to date")
                else:
                    check_failed.append(mod["name"])
                    print("⚠️ Check failed")
            else:
                check_failed.append(mod["name"])
                print("⚠️ Check failed")
        
        print()
        
        if not updates_available:
            print("🎉 All mods are up to date!")
            if check_failed:
                print(f"   ({len(check_failed)} mods couldn't be checked)")
            return
        
        print(f"📊 Found {len(updates_available)} mod(s) with updates available:")
        print()
        for i, update in enumerate(updates_available, 1):
            old = update["old_mod"]
            new = update["new_data"]
            print(f"  {i}. {old['name']}")
            print(f"     Current: {old['filename']}")
            print(f"     Latest:  {new['filename']}")
            print()
        
        print("Update options:")
        print("  - Enter 'all' to update all mods")
        print("  - Enter numbers separated by commas (e.g., '1,3,5') to update specific mods")
        print("  - Press Enter to cancel")
        
        choice = input("\nChoice: ").strip().lower()
        
        if not choice:
            print("Update cancelled.")
            return
        
        selected_updates = []
        
        if choice == 'all':
            selected_updates = updates_available
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                for idx in indices:
                    if 0 <= idx < len(updates_available):
                        selected_updates.append(updates_available[idx])
                    else:
                        print(f"Warning: Invalid number {idx + 1} ignored")
            except ValueError:
                print("Invalid input! Please enter 'all' or numbers like '1,2,3'")
                return
        
        if not selected_updates:
            print("No mods selected for update.")
            return
        
        print(f"\n📝 Updating {len(selected_updates)} mod(s)...")
        
        # Apply updates
        updated_mods = current_mods.copy()
        for update in selected_updates:
            idx = update["index"]
            new_data = update["new_data"]
            old_name = updated_mods[idx]["name"]
            
            updated_mods[idx] = {
                "project_id": updated_mods[idx]["project_id"],
                "file_id": new_data["file_id"],
                "name": updated_mods[idx]["name"],
                "required": updated_mods[idx].get("required", True),
                "filename": new_data["filename"],
                "downloads": new_data["downloads"],
                "sha1": new_data["sha1"],
                "sha512": new_data["sha512"],
                "fileSize": new_data["fileSize"]
            }
            print(f"  ✓ Updated {old_name}")
        
        # Save updated mods
        self._save_mods_list(updated_mods)
        
        print(f"\n✅ Successfully updated {len(selected_updates)} mod(s)!")
        remaining = len(updates_available) - len(selected_updates)
        if remaining > 0:
            print(f"   {remaining} update(s) still available (run -mu again)")

    def run_interactive(self):
        """Run interactive interface"""
        print("=" * 50)
        print("   Modpack Manager CLI (mpm) - Minecraft Modpack Management Tool")
        print("=" * 50)
        print()
        
        # Ensure storage path exists
        self._ensure_storage_path()
        
        # Show active modpack
        if self.config.get("active_modpack"):
            print(f"📦 Active modpack: {self.config['active_modpack']}")
        else:
            print("📦 No active modpack")
        print()
        print("Available commands:")
        print("  -n          Create new modpack")
        print("  -imp        Import modpack from app export file")
        print("  -imp-mr     Import from modrinth.index.json")
        print("  -mpe        Export modpack to JSON file")
        print("  -omp <name> Open modpack")
        print("  -emp        Deactivate modpack")
        print("  -am         Add mod")
        print("  -rm         Remove mod")
        print("  -rmp        Remove modpack completely")
        print("  -lmp        List modpacks")
        print("  -lm         List mods")
        print("  -mpi        Show detailed modpack info")
        print("  -mpb        Build modpack")
        print("  -mpvc       Change modpack version & update mods")
        print("  -mu         Check and apply mod updates")
        print("  -aam        Add auto mod")
        print("  -lam        List auto mods")
        print("  -aa         Add additional files (config, icon, other)")
        print("  -ra         Remove additional files")
        print("  -config     Edit app settings")
        print("  exit        Exit")
        print()

        def _parse_flags(parts, *flag_names):
            """Parse --flag value pairs from command parts. Returns dict and remaining args."""
            flags = {f: None for f in flag_names}
            i = 1
            while i < len(parts):
                part = parts[i]
                if part.startswith("--"):
                    flag_name = part[2:].replace("-", "_")
                    if flag_name in flags:
                        if i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                            flags[flag_name] = parts[i + 1]
                            i += 2
                        else:
                            i += 1
                    else:
                        i += 1
                else:
                    i += 1
            return flags

        while True:
            try:
                cmd = input("mpm> ").strip()
                if not cmd:
                    continue

                parts = cmd.split()
                command = parts[0]

                if command == "exit":
                    print("👋 Goodbye!")
                    break
                elif command == "-n":
                    flags = _parse_flags(parts, "name", "loader", "mc_version", "loader_version")
                    self.cmd_new(
                        name=flags.get("name"),
                        loader=flags.get("loader"),
                        mc_version=flags.get("mc_version"),
                        loader_version=flags.get("loader_version")
                    )
                elif command == "-imp":
                    self.cmd_import_modpack()
                elif command == "-imp-mr":
                    self.cmd_import_modrinth()
                elif command == "-mpe":
                    self.cmd_export_modpack()
                elif command == "-omp":
                    if len(parts) >= 2:
                        # Join all remaining parts to handle spaces in modpack names
                        modpack_name = " ".join(parts[1:])
                        self.cmd_open(modpack_name)
                    else:
                        print("Usage: -omp <modpack_name>")
                elif command == "-emp":
                    self.cmd_exit_modpack()
                elif command == "-am":
                    flags = _parse_flags(parts, "required")
                    # Check for positional project_id (first non-flag arg)
                    project_id = None
                    for i, p in enumerate(parts[1:], 1):
                        if not p.startswith("-"):
                            project_id = p
                            break
                    required = flags.get("required")
                    if required is not None:
                        required = required.lower() in ("y", "yes", "true", "t")
                    self.cmd_add_mod(project_id, required)
                elif command == "-rm":
                    self.cmd_remove_mod()
                elif command == "-rmp":
                    self.cmd_remove_modpack()
                elif command == "-lmp":
                    self.cmd_list_modpacks()
                elif command == "-lm":
                    self.cmd_list_mods()
                elif command == "-mpi":
                    self.cmd_modpack_info()
                elif command == "-mpb":
                    self.cmd_build()
                elif command == "-mpvc":
                    self.cmd_version_change()
                elif command == "-mu":
                    self.cmd_update_mods()
                elif command == "-aam":
                    # Parse positional args for loader and project_id
                    loader = None
                    project_id = None
                    for i, p in enumerate(parts[1:], 1):
                        if not p.startswith("-"):
                            if loader is None:
                                loader = p
                            elif project_id is None:
                                project_id = p
                                break
                    self.cmd_add_auto_mod(loader, project_id)
                elif command == "-lam":
                    self.cmd_list_auto_mods()
                elif command == "-aa":
                    # Parse positional args for type and path
                    file_type = None
                    file_path = None
                    for i, p in enumerate(parts[1:], 1):
                        if not p.startswith("-"):
                            if file_type is None:
                                file_type = p
                            elif file_path is None:
                                file_path = p
                                break
                    self.cmd_add_additional(file_type, file_path)
                elif command == "-ra":
                    self.cmd_remove_additional()
                elif command == "-config":
                    self.cmd_config()
                else:
                    print(f"❓ Unknown command: {command}")
                    print("Type 'exit' to quit or use a valid command.")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"❌ Error: {e}")


def print_cli_help():
    """Print CLI help information"""
    print("Modpack Manager CLI (mpm) - Command Line Usage")
    print("=" * 50)
    print()
    print("Usage: mpm [command] [arguments]")
    print()
    print("Commands:")
    print("  -n                    Create new modpack")
    print("  -imp                  Import modpack from app export")
    print("  -imp-mr               Import from modrinth.index.json")
    print("  -mpe                  Export modpack to JSON")
    print("  -omp <name>           Open modpack")
    print("  -emp                  Deactivate modpack")
    print("  -am [project_id] [--t|--f]  Add mod (--t=required, --f=optional)")
    print("  -rm                   Remove mod")
    print("  -rmp                  Remove modpack completely")
    print("  -lmp                  List modpacks")
    print("  -lm                   List mods")
    print("  -mpi                  Show modpack info")
    print("  -mpb                  Build modpack")
    print("  -mpvc                 Change modpack version")
    print("  -mu                   Check and apply mod updates")
    print("  -aam <loader> <id>    Add auto mod for loader")
    print("  -lam                  List all auto mods")
    print("  -aa [type] [path]     Add additional files (config/icon/other)")
    print("  -ra                   Remove additional files")
    print("  -config               Edit app settings")
    print()
    print("Run 'mpm' without arguments for interactive mode")
    print()

#!/usr/bin/env python3
"""
Modpack Manger CLI - A CLI tool for creating and managing Minecraft modpacks
"""

import os
import json
import shutil
import hashlib
import argparse
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any

# Modrinth API base URL
MODRINTH_API = "https://api.modrinth.com/v2"

# Loader mapping for dependencies
LOADER_DEPENDENCY_MAP = {
    "fabric": "fabric-loader",
    "forge": "forge",
    "quilt": "quilt-loader",
    "neoforge": "neoforge"
}


class ModpackManager:
    def __init__(self):
        # Store config in user's home directory for package installation compatibility
        self.config_dir = Path.home() / ".mpm"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "config.json"
        self.config = self._load_config()
        self.active_modpack_path: Optional[Path] = None
        self._update_active_path()

    def _load_config(self) -> Dict:
        """Load config file or create it"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"storage_path": None, "active_modpack": None}

    def _save_config(self):
        """Save config file"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def _update_active_path(self):
        """Update active modpack path"""
        if self.config.get("storage_path") and self.config.get("active_modpack"):
            self.active_modpack_path = Path(self.config["storage_path"]) / self.config["active_modpack"]
        else:
            self.active_modpack_path = None

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
        if modpack_path.exists():
            with open(modpack_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

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
        modpack_path = self.active_modpack_path / "modpack.json"
        data = {
            "name": name,
            "version": version,
            "mc_version": mc_version,
            "loader": loader,
            "loader_version": loader_version,
            "mods": mods
        }
        with open(modpack_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save_mods_list(self, mods: List[Dict]):
        """Update mods list in modpack.json"""
        if not self.active_modpack_path:
            return
        # Load existing data
        data = self._load_modpack_data(self.config.get("active_modpack", ""))
        if data:
            data["mods"] = mods
            modpack_path = self.active_modpack_path / "modpack.json"
            with open(modpack_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def _fetch_modrinth_project(self, project_id: str) -> Optional[Dict]:
        """Fetch project data from Modrinth"""
        try:
            response = requests.get(f"{MODRINTH_API}/project/{project_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            print(f"Error: Project {project_id} not found (code: {response.status_code})")
            return None
        except requests.RequestException as e:
            print(f"Error connecting to Modrinth: {e}")
            return None

    def _fetch_compatible_version(self, project_id: str, loader: str, mc_version: str) -> Optional[Dict]:
        """Search for compatible mod version"""
        try:
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
        except requests.RequestException as e:
            print(f"Error fetching versions: {e}")
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

    def _get_latest_fabric_loader(self) -> Optional[str]:
        """Fetch the latest Fabric loader version from Fabric Meta API"""
        try:
            response = requests.get("https://meta.fabricmc.net/v2/versions/loader", timeout=10)
            if response.status_code == 200:
                versions = response.json()
                if versions and len(versions) > 0:
                    # First item is the latest stable version
                    return versions[0].get("version")
            return None
        except requests.RequestException as e:
            print(f"Error fetching Fabric loader versions: {e}")
            return None

    def _get_latest_forge_version(self, mc_version: str) -> Optional[str]:
        """Fetch the latest Forge version for a Minecraft version"""
        try:
            # Use Forge promotions API
            response = requests.get("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json", timeout=10)
            if response.status_code == 200:
                data = response.json()
                promos = data.get("promos", {})
                # Look for recommended version first, then latest
                recommended_key = f"{mc_version}-recommended"
                latest_key = f"{mc_version}-latest"
                
                version = promos.get(recommended_key) or promos.get(latest_key)
                if version:
                    return f"{mc_version}-{version}"
            return None
        except requests.RequestException as e:
            print(f"Error fetching Forge versions: {e}")
            return None

    def _get_latest_neoforge_version(self) -> Optional[str]:
        """Fetch the latest NeoForge version from NeoForged Maven"""
        try:
            response = requests.get("https://maven.neoforged.net/api/v1/maven/versions/releases/net/neoforged/neoforge", timeout=10)
            if response.status_code == 200:
                data = response.json()
                versions = data.get("versions", [])
                if versions and len(versions) > 0:
                    # Return the latest version (first in the list)
                    return versions[0]
            return None
        except requests.RequestException as e:
            print(f"Error fetching NeoForge versions: {e}")
            return None

    def _get_latest_quilt_loader(self) -> Optional[str]:
        """Fetch the latest Quilt loader version from Quilt Meta API"""
        try:
            response = requests.get("https://meta.quiltmc.org/v3/versions/loader", timeout=10)
            if response.status_code == 200:
                versions = response.json()
                if versions and len(versions) > 0:
                    # First item is the latest stable version
                    return versions[0].get("version")
            return None
        except requests.RequestException as e:
            print(f"Error fetching Quilt loader versions: {e}")
            return None

    def cmd_new(self):
        """Create new modpack"""
        if not self._ensure_storage_path():
            return

        name = input("Enter modpack name: ").strip()
        if not name:
            print("Error: Name is required!")
            return

        # Check if modpack with same name exists
        modpack_path = Path(self.config["storage_path"]) / name
        if modpack_path.exists():
            print(f"Error: Modpack '{name}' already exists!")
            return

        print("Select loader:")
        print("1. Forge")
        print("2. Fabric")
        print("3. Quilt")
        print("4. NeoForge")
        
        loader_choice = input("Enter loader number (1-4): ").strip()
        loaders = {"1": "forge", "2": "fabric", "3": "quilt", "4": "neoforge"}
        
        if loader_choice not in loaders:
            print("Error: Invalid choice!")
            return
        
        loader = loaders[loader_choice]
        
        mc_version = input("Enter Minecraft version (e.g. 1.20.1): ").strip()
        if not mc_version:
            print("Error: Minecraft version is required!")
            return

        # Auto-fetch loader version based on selected loader
        print(f"🔍 Fetching latest {loader.capitalize()} version...")
        loader_version = None
        
        if loader == "fabric":
            loader_version = self._get_latest_fabric_loader()
        elif loader == "forge":
            loader_version = self._get_latest_forge_version(mc_version)
        elif loader == "neoforge":
            loader_version = self._get_latest_neoforge_version()
        elif loader == "quilt":
            loader_version = self._get_latest_quilt_loader()
        
        if loader_version:
            print(f"✅ Auto-selected {loader.capitalize()} version: {loader_version}")
            confirm = input("Use this version? (y/n): ").strip().lower()
            if confirm == 'n':
                loader_version = input(f"Enter {loader.capitalize()} version manually: ").strip()
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
            with open(modpack_path / "modpack.json", 'w', encoding='utf-8') as f:
                json.dump(modpack_data, f, indent=2, ensure_ascii=False)
            
            # Set as active modpack
            self.config["active_modpack"] = name
            self._save_config()
            self._update_active_path()
            
            print(f"✅ Modpack '{name}' created successfully!")
            print(f"   Loader: {loader.capitalize()} {loader_version}")
            print(f"   Minecraft: {mc_version}")
            
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
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
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

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
        except json.JSONDecodeError:
            print("Error: Invalid JSON file!")
            return
        except Exception as e:
            print(f"Error reading file: {e}")
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
                try:
                    response = requests.get(
                        f"{MODRINTH_API}/version_file/{sha1_hash}",
                        timeout=10
                    )
                    if response.status_code == 200:
                        version_info = response.json()
                        project_id = version_info.get("project_id")
                        file_id = version_info.get("id")
                    else:
                        # Try alternative endpoint
                        response = requests.get(
                            f"{MODRINTH_API}/version_file/{sha1_hash}?algorithm=sha1",
                            timeout=10
                        )
                        if response.status_code == 200:
                            version_info = response.json()
                            project_id = version_info.get("project_id")
                            file_id = version_info.get("id")
                except Exception:
                    pass

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
        with open(modpack_path / "modpack.json", 'w', encoding='utf-8') as f:
            json.dump(modpack_data, f, indent=2, ensure_ascii=False)

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

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                export_data = json.load(f)
        except json.JSONDecodeError:
            print("Error: Invalid JSON file!")
            return
        except Exception as e:
            print(f"Error reading file: {e}")
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
        with open(modpack_path / "modpack.json", 'w', encoding='utf-8') as f:
            json.dump(modpack_data, f, indent=2, ensure_ascii=False)

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
        print(f"  Modpack Version: {info['version']}")
        print(f"  Minecraft:       {info['mc_version']}")
        print(f"  Loader:          {info['loader'].capitalize()} {info['loader_version']}")
        print(f"  Mods Count:      {len(mods)}")
        print(f"  Required Mods:   {required_count}")
        print(f"  Optional Mods:   {optional_count}")
        print(f"  Storage Path:    {modpack_path}")
        print(f"  Status:          ✅ Imported & Active")
        print("=" * 50)

    def cmd_add_mod(self, project_id: Optional[str] = None):
        """Add mod to active modpack"""
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
        self._save_mods_list(mods)
        
        print(f"✅ Added mod '{new_mod['name']}' successfully!")
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
        output_path = output_folder / "modrinth.index.json"
        
        # Check if old build exists and ask about archiving
        archive_old = False
        if output_path.exists():
            archive_choice = input("Old build exists. Archive it? (y/n): ").strip().lower()
            if archive_choice == 'y':
                archive_old = True
        
        # Archive old build if requested
        if archive_old:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_folder = self.active_modpack_path / "build_archive" / f"build_{timestamp}"
            archive_folder.mkdir(parents=True, exist_ok=True)
            
            # Move old build to archive
            archive_path = archive_folder / "modrinth.index.json"
            shutil.move(str(output_path), str(archive_path))
            
            # Also copy modpack.json for complete backup
            modpack_json_path = self.active_modpack_path / "modpack.json"
            if modpack_json_path.exists():
                shutil.copy(str(modpack_json_path), str(archive_folder / "modpack.json"))
            
            print(f"📦 Old build archived: {archive_folder}")
        
        # Write new file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=4, ensure_ascii=False)

        print(f"✅ Modpack built successfully!")
        print(f"📁 Folder: {output_folder}")
        print(f"📄 File: {output_path}")
        print(f"📊 Total mods in modpack: {len(mods)}")
        print(f"✓ Included in build: {len(supported_mods)}")
        if unsupported_mods:
            print(f"⚠ Excluded from build: {len(unsupported_mods)} ({', '.join(unsupported_mods)})")
            print(f"   (These mods stay in modpack.json but won't be in modrinth.index.json)")
        if archive_old:
            print(f"📦 Previous build archived")

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
                mods_path = target / "mods.json"
                
                if not mods_path.exists():
                    print("No mods to update.")
                    return

                with open(mods_path, 'r', encoding='utf-8') as f:
                    current_mods = json.load(f).get("mods", [])

                if not current_mods:
                    print("No mods to update.")
                    # Update modpack version only
                    info["version"] = new_mp_version
                    info["mc_version"] = new_mc_version
                    with open(target / "info.json", 'w', encoding='utf-8') as f:
                        json.dump(info, f, indent=2, ensure_ascii=False)
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
                    with open(target / "modpack.json", 'w', encoding='utf-8') as f:
                        json.dump(modpack_data, f, indent=2, ensure_ascii=False)
                    
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
        print("  exit        Exit")
        print()

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
                    self.cmd_new()
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
                    if len(parts) >= 2:
                        self.cmd_add_mod(parts[1])
                    else:
                        self.cmd_add_mod()
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
    print("  -am [project_id]      Add mod")
    print("  -rm                   Remove mod")
    print("  -rmp                  Remove modpack completely")
    print("  -lmp                  List modpacks")
    print("  -lm                   List mods")
    print("  -mpi                  Show modpack info")
    print("  -mpb                  Build modpack")
    print("  -mpvc                 Change modpack version")
    print("  -mu                   Check and apply mod updates")
    print()
    print("Run 'mpm' without arguments for interactive mode")
    print()


def main():
    """Main entry point - supports both interactive and CLI modes"""
    import sys
    
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

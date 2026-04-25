# Changelog

All notable changes to the Modpack Manager (mpm) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.3] - 2026-04-25

### Notes
- **Skipped version 1.0.2** - This version was skipped due to PyPI package uploading issues

### Added

#### Auto Mods System
- **`-aam` command** - Add auto mods that get automatically included in new modpacks based on loader type
- **`-lam` command** - List all configured auto mods
- **Auto mod modes** - Three modes: "Ask before adding", "Auto-add without asking", "Never add"
- **Per-loader auto mod configuration** - Configure different auto mods for Fabric, Forge, Quilt, and NeoForge
- **Auto mod application on modpack creation** - Auto mods are automatically offered/added when creating new modpacks

#### Build System
- **`.mrpack` export** - Build command now creates `.mrpack` files (Modrinth pack format) directly
- **Additional files management** - Extra files are now managed via `-aa` and `-ra` commands and stored in modpack.json
- **Archive cleanup** - Automatic cleanup of old builds (keeps max 10 archives)

#### Additional Files Commands
- **`-aa` command** - Add additional files to modpack with interactive menu:
  - `1. Icon` - .png icon for the modpack (root of .mrpack)
  - `2. Config` - Config files (goes to overrides/config/)
  - `3. Overrides` - General files (goes to overrides/)
  - `4. Other` - README, licenses (root of .mrpack)
- **`-ra` command** - Remove additional files from modpack (shows list with icons)

#### Configuration System
- **`-config` command** - New configuration menu with sub-options:
  - Auto mods management
  - **Loader version fetch mode** - Three options:
    - `auto` - Auto-use latest version without prompting
    - `ask` - Show fetched version and ask for confirmation (default)
    - `manual` - Always ask user to input version manually
  - **Advanced storage options** - Storage mode for additional files:
    - `copy` - Copy files to `_mpm_files/` (safe, portable - default)
    - `link` - Create symlinks to original files (instant reflection of changes)
    - `move` - Move files into modpack (destructive - with confirmation)
  - Modpacks storage path configuration
- **`MPM_STORAGE_PATH` environment variable** - Override storage path via environment variable
- **Config directory change** - Changed from `AhmedShah29` to `Modpack Manager` in platformdirs

#### CLI Improvements
- **Manual CLI argument parsing** - Replaced argparse subparsers with custom parsing to properly support dash-prefixed commands
- **Partial argument support in interactive mode** - Interactive mode now supports flags like `--name`, `--loader`, etc.
- **`-help` command** - Added `-help` as an alternative to `--help` and `-h`

#### Error Handling & Stability
- **`@handle_network_errors` decorator** - Consistent network error handling (timeout, connection errors)
- **KeyboardInterrupt propagation** - Clean exit on Ctrl+C without error messages
- **Graceful API failures** - Network errors show user-friendly messages instead of stack traces

#### Dependencies & Packaging
- **Added `platformdirs`** - For proper cross-platform config directory management
- **Excluded `test_mpm.py` from package** - Tests stay in repo but not in pip package
- **Removed `__pycache__` files** - Cleaned up Python cache files

### Changed

- **Build output** - Now creates only `.mrpack` file instead of separate `modrinth.index.json`
- **Config author name** - Changed from "AhmedShah29" to "Modpack Manager"
- **Loader version fetching** - Unified and cached with `@functools.lru_cache`
- **CLI help format** - Updated to show new commands and features

### Fixed

- **Argparse conflicts** - Fixed issues with dash-prefixed commands like `-n` in argparse
- **KeyboardInterrupt catching** - Decorator no longer catches KeyboardInterrupt
- **Minecraft version sorting** - Now sorts by date to properly detect latest versions
- **Undefined variable in `cmd_import_modpack`** - Fixed reference to `info` variable

## [1.0.1] - 2026-04-21

### Added (Initial Release)
- **Modpack Management** - Create & manage modpacks with custom names, versions, and Minecraft versions
- **Multi-Loader Support** - Fabric, Forge, Quilt, and NeoForge loaders
- **Auto Loader Version Detection** - Fetches latest loader versions automatically
- **Mod Management** - Add, remove, list mods with required/optional status
- **Import/Export** - Import from `modrinth.index.json` or export your own format
- **Build & Archive** - Generate `modrinth.index.json` with automatic build archiving
- **Version Management** - Update modpack and mod versions
- **Smart Updates** - Check for mod updates with selective update options
- **Direct CLI Mode** - All commands support non-interactive flags for scripting
- **Auto Minecraft Version Detection** - Fetches latest MC version from Modrinth API
- **Auto Dependency Resolution** - Optional automatic dependency installation when adding mods
- **API Caching** - Reduces redundant Modrinth API calls with `@functools.lru_cache`

---

## Version Numbering Guide

- **MAJOR** - Breaking changes that require user action
- **MINOR** - New features, backwards compatible
- **PATCH** - Bug fixes and improvements

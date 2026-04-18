# Modpack Manager (mpm)

An interactive CLI tool for creating and managing Minecraft (Java Edition) modpacks via the Modrinth platform.

## Features

- **Create & Manage Modpacks** with custom names, versions, and Minecraft versions
- **Multiple Loader Support**: Fabric, Forge, Quilt, and NeoForge
- **Auto Loader Version Detection** for all supported loaders
- **Mod Management**: Add, remove, list mods with required/optional status
- **Import/Export**: Import from modrinth.index.json or export your own format
- **Build & Archive**: Generate modrinth.index.json with automatic build archiving
- **Version Management**: Update modpack and mod versions
- **Smart Updates**: Check for mod updates with selective update options

## Installation

### From GitHub (Recommended)
```bash
pip install git+https://github.com/yourusername/mpm.git
```

### From Source
```bash
git clone https://github.com/yourusername/mpm.git
cd mpm
pip install .
```

## Usage

### Interactive Mode
```bash
mpm
```

### CLI Mode
```bash
mpm -n              # Create new modpack
mpm -mpb            # Build modpack
mpm -lmp            # List modpacks
mpm -omp "Name"     # Open modpack
mpm -am PROJECT_ID  # Add mod
mpm --help          # Show all commands
```

## Commands

| Command | Description |
|---------|-------------|
| `-n` | Create new modpack |
| `-imp` | Import from app export |
| `-imp-mr` | Import from modrinth.index.json |
| `-mpe` | Export modpack to JSON |
| `-omp <name>` | Open modpack |
| `-emp` | Deactivate modpack |
| `-am [id]` | Add mod |
| `-rm` | Remove mod (interactive) |
| `-rmp` | Remove modpack completely |
| `-lmp` | List modpacks |
| `-lm` | List mods |
| `-mpi` | Show modpack info |
| `-mpb` | Build modrinth.index.json |
| `-mpvc` | Change version & update mods |
| `-mu` | Check and apply updates |

## File Structure

```
~/.mpm/
└── config.json          # App configuration

{storage_path}/
└── {modpack}/
    ├── modpack.json              # Main data file
    ├── build/
    │   └── modrinth.index.json   # Export file
    └── build_archive/
        └── build_YYYYMMDD_HHMMSS/
            ├── modrinth.index.json
            └── modpack.json      # Backup of app data
```

## Key Features

### Smart Build System
- Mods with complete metadata are included in `modrinth.index.json`
- Mods with missing data stay in `modpack.json` but are excluded from build
- Clear reporting of included/excluded mods

### Archive System
When archiving old builds, both files are saved:
- `modrinth.index.json` - The Modrinth-compatible export
- `modpack.json` - Complete app data backup

### Update Handling
- `-mpvc`: Change MC version with option to keep unsupported mods
- `-mu`: Check for updates within same MC version
- Selective updates: choose specific mods or update all

## Requirements

- Python 3.7+
- requests library (auto-installed)

## Package Structure

```
mpm/
├── __init__.py      # Package init with version info
├── __main__.py      # Entry point for python -m mpm
├── core.py          # Main ModpackManager class (~1500 lines)
└── ...
```

## Notes

- Config stored in `~/.mpm/config.json` (user's home directory)
- Get Project IDs from mod pages on Modrinth
- Generated `modrinth.index.json` can be used for `.mrpack` files

## License

MIT License - See LICENSE file for details

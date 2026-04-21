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
- **Direct CLI Mode**: All commands support non-interactive flags for scripting
- **Auto Minecraft Version Detection**: Fetches latest MC version from Modrinth API automatically
- **Auto Dependency Resolution**: Optional automatic dependency installation when adding mods
- **API Caching**: Reduces redundant Modrinth API calls

## Installation

### From GitHub (Recommended)
```bash
pip install git+https://github.com/AhmedShah29/MP-Manager.git
```

### From Source
```bash
git clone https://github.com/AhmedShah29/MP-Manager.git
cd MP-Manager
pip install .
```

## Usage

### Interactive Mode
```bash
mpm
```

### Direct CLI Mode
```bash
# Create modpack non-interactively (auto-detects latest MC version)
mpm -n --name "MyPack" --loader fabric --mc-version 26.1.2

# Add mod
mpm -am AANobbMI --t        # required mod
mpm -am AANobbMI --f        # optional mod

# Open, build, list
mpm -omp "MyPack"
mpm -mpb
mpm -lmp

# Show help
mpm -help
mpm --help
mpm -h
```

## Commands

| Command | Description | Direct Flags |
|---------|-------------|--------------|
| `-n` | Create new modpack | `--name`, `--loader`, `--mc-version`, `--loader-version` |
| `-imp` | Import from app export | (interactive) |
| `-imp-mr` | Import from modrinth.index.json | (interactive) |
| `-mpe` | Export modpack to JSON | (interactive) |
| `-omp <name>` | Open modpack | `name` positional arg |
| `-emp` | Deactivate modpack | — |
| `-am [id]` | Add mod | `--t` (required), `--f` (optional) |
| `-rm` | Remove mod (interactive) | — |
| `-rmp` | Remove modpack completely | — |
| `-lmp` | List modpacks | — |
| `-lm` | List mods | — |
| `-mpi` | Show modpack info | — |
| `-mpb` | Build modrinth.index.json | — |
| `-mpvc` | Change version & update mods | — |
| `-mu` | Check and apply updates | — |
| `-help`, `-h`, `--help` | Show all commands | — |

## File Structure

```
# Config (platform-specific)
# Linux/macOS: ~/.config/mpm/config.json
# Windows:     %LOCALAPPDATA%\Modpack Manager\mpm\config.json

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
- **Auto-cleanup**: Only the 10 most recent archives are kept

### Update Handling
- `-mpvc`: Change MC version with option to keep unsupported mods
- `-mu`: Check for updates within same MC version
- Selective updates: choose specific mods or update all
- **Loader compatibility check**: Verifies loader exists for new MC version before updating

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `MPM_STORAGE_PATH` | Override the modpack storage path (stored in config) |

## Requirements

- Python 3.8+
- `requests` (auto-installed)
- `platformdirs` (auto-installed)

## Development

```bash
pip install -r requirements.txt
python -m unittest test_mpm -v
```

## Package Structure

```
mpm/
├── __init__.py      # Package init with version info
├── __main__.py      # Entry point with argparse CLI
├── core.py          # Main ModpackManager class
└── ...
```

## Notes

- Config stored in platform-specific config directory via `platformdirs`
- Get Project IDs from mod pages on Modrinth
- Generated `modrinth.index.json` can be used for `.mrpack` files

## License

MIT License - See LICENSE file for details

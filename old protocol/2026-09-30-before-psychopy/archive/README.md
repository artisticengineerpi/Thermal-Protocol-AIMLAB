# Archive Folder

**Purpose**: Contains old versions and development files for reference.

## Files in This Folder

### Legacy Versions
- **`thermal_motion_cli.py`** - Original CLI (v1.0)
  - Basic functionality, manual trial selection
  - Superseded by v2.2

### Development Versions
- **`thermal_motion_cli_v2_latin_ready.py`** - Development version (v2.1)
  - Browser display implementation testing
  - Superseded by v2.2

- **`thermal_motion_cli_latinsquare.py`** - Latin square testing
  - Experimental design algorithm testing
  - Now integrated into v2.2

### Debug and Backup
- **`thermal_motion_cli_v2_troublesome.py`** - Debug version
  - Extra logging for troubleshooting
  - Use v2.2 debug mode instead

- **`thermal_motion_cli_v2 - backup.py`** - Backup copy
  - Safety backup of working version
  - Keep for emergency rollback

## ⚠️ Important Notes

- **These files are NOT used by the main application**
- They are kept for reference and version history
- To run the current experiment, use `../a.bat` or `../thermal_motion_cli_v2.py`
- Do NOT modify these files unless you know what you're doing
- If you need to reference old functionality, check the file contents

## Running Archived Versions

If you need to run an old version for testing:

```bash
# From the archive folder
python thermal_motion_cli.py

# Or from root directory
python archive\thermal_motion_cli.py
```

**Note**: Old versions may not have all features and may require different setup.

---

**Maintained by**: Pi Ko (pi.ko@nyu.edu)  
**Last Updated**: 25 January 2026

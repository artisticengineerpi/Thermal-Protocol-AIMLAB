# Utilities Folder

**Purpose**: Standalone tools that can be run independently from the main experiment.

## Available Utilities

### 🔧 EEG Trigger Sender (`trigger_sender.py`)

**Version**: 2.0  
**Purpose**: Test EEG trigger box independently from the main experiment  
**Author**: Pi Ko (pi.ko@nyu.edu)

#### Features
- Standalone EEG trigger testing
- Automatic COM port management
- Process cleanup and port release
- Real-time trigger sending (no Enter key needed)
- Port scanning and listing
- Reconnection capability

#### When to Use
- **Troubleshooting**: Test if EEG trigger box is working
- **Verification**: Verify trigger codes are being sent correctly
- **Independent Testing**: Test triggers without running full experiment
- **Hardware Check**: Before starting experiment session

#### Usage

```bash
# Basic usage (default COM4)
cd utilities
python trigger_sender.py

# Specify port
python trigger_sender.py --port COM3

# Specify port and baud rate
python trigger_sender.py --port COM4 --baud 115200

# From root directory
python utilities\trigger_sender.py
```

#### Interactive Commands

Once running, press keys directly (no Enter needed):

**Experiment Type Triggers** (0x01-0x04):
- `1` - No Stimulation (0x01)
- `2` - Thermal Only (0x02)
- `3` - Vibrotactile Only (0x03)
- `4` - Thermal Motion (0x04)

**User Rating Triggers** (0x05-0x09):
- `5` - No Stimulation (0x05)
- `6` - Thermal Only (0x06)
- `7` - Vibrotactile Only (0x07)
- `8` - Thermal Motion (0x08)
- `9` - I don't know (0x09)

**Utility Commands**:
- `R` - Reconnect to COM port
- `L` - List available COM ports
- `M` - Show menu again
- `Q` - Quit

#### Troubleshooting with Trigger Sender

**Problem**: EEG not receiving triggers during experiment

**Solution Steps**:
1. Close main experiment
2. Run `python utilities\trigger_sender.py`
3. Press `L` to list ports
4. Verify COM4 is available
5. Press `1-9` to test each trigger
6. Check EEG system for received triggers
7. If working here but not in experiment, check main app configuration

**Problem**: "Access is denied" or "Port in use"

**Solution**:
1. Close all Python programs
2. Run trigger_sender with `--no-clear` flag:
   ```bash
   python trigger_sender.py --no-clear
   ```
3. Press `R` to reconnect
4. If still fails, restart computer

#### Requirements

```bash
pip install pyserial
```

The script will auto-install pyserial if missing.

#### Technical Details

- **Default Port**: COM4
- **Default Baud Rate**: 9600
- **Trigger Pulse Width**: 5ms
- **Auto-cleanup**: Kills conflicting processes on startup
- **Port Release**: Automatic on exit

---

## Adding New Utilities

To add a new standalone utility to this folder:

1. Create your Python script in `utilities/`
2. Add description to this README
3. Ensure it can run independently (no dependencies on main experiment)
4. Include proper error handling and cleanup
5. Add usage examples

---

**Maintained by**: Pi Ko (pi.ko@nyu.edu)  
**Last Updated**: 25 January 2026

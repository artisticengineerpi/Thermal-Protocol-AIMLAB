"""
Thermal Motion Experiment - Complete Documentation

Author: Pi Ko (pi.ko@nyu.edu)
AIMLAB - NYU Abu Dhabi
Date: 25 January 2026
Version: 2.2

Changelog:
v1.0 (25 January 2026):
    - Initial comprehensive documentation
    - Project overview and architecture
    - Setup and usage instructions
    - Hardware and software requirements
    - Troubleshooting guide
"""

# Thermal Motion Experiment System

## Table of Contents
1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Hardware Requirements](#hardware-requirements)
4. [Software Requirements](#software-requirements)
5. [Installation](#installation)
6. [System Architecture](#system-architecture)
7. [Usage Guide](#usage-guide)
8. [Experimental Protocols](#experimental-protocols)
9. [Configuration](#configuration)
10. [Troubleshooting](#troubleshooting)
11. [File Descriptions](#file-descriptions)

---

## Overview

The Thermal Motion Experiment System is a comprehensive Python-based experimental platform designed to investigate thermal and vibrotactile sensory perception. The system integrates multiple hardware components to deliver controlled thermal and haptic stimuli while synchronizing with EEG recording equipment.

### Key Features
- **Multi-modal Stimulation**: Thermal (Peltier) and vibrotactile (motor array) stimuli
- **EEG Integration**: Precise trigger synchronization for neurophysiological recordings
- **Experimental Modes**: Full experiment (160 trials with Latin square design), single trial, and debug modes
- **Browser Display**: Secondary monitor interface for participant instructions and responses
- **Audio Cues**: Temporal markers using 500Hz and 1000Hz tones
- **Auto-detection**: Intelligent Arduino device discovery with port caching
- **Real-time Control**: Responsive CLI with progress tracking

### Experimental Conditions
1. **No Stimulation** - Control condition
2. **Thermal Only** - Peltier heating/cooling
3. **Vibrotactile Only** - Motor array funneling illusion
4. **Thermal Motion** - Combined thermal and vibrotactile stimulation

---

## Project Structure

```
Thermal/
├── a.bat                                    # Windows launcher script
├── thermal.ico                              # Application icon
├── thermal_motion_cli_v2.py                 # Main application (v2.2) ⭐
├── thermal_motion_ports.json                # Cached device port assignments
├── README.md                                # This documentation
│
├── archive/                                 # Old versions and development files
│   ├── thermal_motion_cli.py                    # Original CLI (v1.0)
│   ├── thermal_motion_cli_latinsquare.py        # Latin square testing
│   ├── thermal_motion_cli_v2_latin_ready.py     # Development version (v2.1)
│   ├── thermal_motion_cli_v2_troublesome.py     # Debug version
│   └── thermal_motion_cli_v2 - backup.py        # Backup copy
│
└── utilities/                               # Standalone utility tools
    └── trigger_sender.py                        # EEG trigger testing tool
```

### Active Files (Root Directory)
Only the essential files needed to run the experiment are kept in the root:
- **`a.bat`** - Quick launcher (double-click to start)
- **`thermal_motion_cli_v2.py`** - Main application with all features
- **`thermal_motion_ports.json`** - Auto-generated device cache
- **`thermal.ico`** - Application icon
- **`README.md`** - This documentation

### Archive Folder
Contains old versions and development files for reference:
- Legacy versions (v1.0, v2.0, v2.1)
- Testing implementations
- Backup copies

### Utilities Folder
Standalone tools that can be run independently:
- **`trigger_sender.py`** - Test EEG triggers separately from main experiment

---

## Hardware Requirements

### 1. Peltier Controller (Arduino)
- **Function**: Thermoelectric heating/cooling control
- **Device ID**: `PELTIER_CONTROLLER_V3`
- **Baud Rate**: 115200
- **Commands**:
  - `IDENTIFY` - Device identification
  - `HOT:<pwm>` - Activate heating (PWM: 0-255)
  - `COLD:<pwm>` - Activate cooling (PWM: 0-255)
  - `OFF` - Turn off Peltier
  - `PING` - Connection test
  - `STATUS` - Get current status

### 2. Motor Controller (Arduino)
- **Function**: 4-channel vibration motor array (M0-M3)
- **Device ID**: `MOTOR_CONTROLLER_V3`
- **Baud Rate**: 115200
- **Commands**:
  - `IDENTIFY` - Device identification
  - `INTENSITY:<value>` - Set global intensity (0-255)
  - `MULT:<motor>:<value>` - Set motor multiplier (0.0-1.0)
  - `OVERLAP:<value>` - Set overlap factor for smooth transitions
  - `POS:<position>` - Set interpolated position (0.0-3.0)
  - `MOTOR:<num>` - Activate specific motor
  - `STOP` - Stop all motors
  - `PING` - Connection test

### 3. EEG Trigger Box
- **Function**: Send event markers to EEG system
- **Port**: COM4 (default)
- **Baud Rate**: 9600
- **Trigger Codes**:
  - **Experiment Types** (0x01-0x04): Condition markers
  - **User Ratings** (0x05-0x09): Response markers
- **Pulse Width**: 5ms

### 4. Audio System
- **Sound Files** (in `Downloads` folder):
  - `t0500hz.wav` - 500Hz tone (trial start, question prompt)
  - `t1000hz.wav` - 1000Hz tone (stimulation start)

### 5. Display Setup
- **Primary Monitor**: Experimenter control interface (CLI)
- **Secondary Monitor**: Participant display (browser-based)
  - Welcome screen
  - Fixation cross
  - Blank screen during stimulation
  - Response questions

---

## Software Requirements

### Python Version
- Python 3.7 or higher

### Required Packages
```bash
pip install pyserial tqdm colorama keyboard
```

### Package Details
- **pyserial** (≥3.5): Serial communication with Arduino devices
- **tqdm** (≥4.62): Progress bars and visual feedback
- **colorama** (≥0.4.4): Cross-platform colored terminal output
- **keyboard** (≥0.13): Real-time keyboard input capture

### Operating System
- **Windows 10/11**: Fully supported (PowerShell required)
- **Linux**: Supported (may require root for keyboard module)
- **macOS**: Supported with limitations

---

## Installation

### Step 1: Clone or Download
```bash
cd C:\Users\<your_username>\Desktop
# Place all files in the Thermal directory
```

### Step 2: Install Dependencies
```bash
pip install pyserial tqdm colorama keyboard
```

### Step 3: Prepare Audio Files
- Place `t0500hz.wav` and `t1000hz.wav` in your `Downloads` folder
- Default path: `C:\Users\<your_username>\Downloads\`

### Step 4: Connect Hardware
1. Connect Peltier Controller Arduino to USB
2. Connect Motor Controller Arduino to USB
3. Connect EEG Trigger Box to COM4 (or note the port)
4. Verify connections in Device Manager (Windows)

### Step 5: Test Connection
```bash
python thermal_motion_cli_v2.py
```

---

## System Architecture

### Component Hierarchy

```
ThermalMotionCLI (Main Application)
├── DeviceScanner
│   └── PortCacheManager
├── PeltierController (SerialDevice)
├── MotorController (SerialDevice)
├── TriggerController
├── StimulationExecutor
├── SoundPlayer
├── BrowserDisplayManager
├── ExperimentRunner
│   └── LatinSquareManager
└── ColoredLogger
```

### Data Flow

```
User Input → CLI Menu → Mode Selection
                ↓
        Device Connection
                ↓
    ┌───────────┴───────────┐
    │                       │
Experiment Mode        Debug Mode
    │                       │
    ├─ Browser Display      └─ Direct Stimulation
    ├─ Audio Cues
    ├─ EEG Triggers
    └─ Trial Sequence
        │
        ├─ Fixation (3-4.5s)
        ├─ Trigger (Experiment Type)
        ├─ Stimulation (5s total)
        ├─ Question Display
        └─ Response Trigger
```

### Communication Protocols

#### Serial Communication (Arduino)
- **Protocol**: ASCII text commands, newline-terminated
- **Timeout**: 0.1s read, 1.0s write
- **Buffer Management**: Auto-reset on connection
- **Thread Safety**: Lock-protected command sending

#### HTTP Server (Browser Display)
- **Port**: 8765 (configurable)
- **Protocol**: HTTP/1.1
- **Endpoints**:
  - `/` - Main display page
  - `/state` - State polling (300ms interval)
  - `/keypress?key=<key>` - Capture user responses
- **State Management**: Version-based polling for updates

---

## Usage Guide

### Quick Start (Windows)

#### Method 1: Double-click Launcher
```
Double-click: a.bat
```

#### Method 2: Command Line
```bash
cd C:\Users\<your_username>\Desktop\Thermal
python thermal_motion_cli_v2.py
```

### Mode Selection

#### 1. Full Experiment Mode
- **160 trials** (5 blocks × 32 trials)
- **Latin square counterbalanced design**
- **Inter-block breaks** (60 seconds, adjustable)
- **EEG triggers** enabled
- **Audio cues** enabled
- **Browser display** on secondary monitor
- **Automatic progress tracking**

**Use Case**: Running the complete experiment with participants

#### 2. Single Trial Mode
- **Manual condition selection**
- **EEG triggers** enabled
- **Audio cues** enabled
- **Browser display** enabled
- **Good for**: Testing specific conditions, practice trials

**Use Case**: Testing individual conditions, training participants

#### 3. Debug Mode
- **No triggers**
- **No audio cues**
- **No browser display**
- **Direct stimulation testing**

**Use Case**: Hardware testing, troubleshooting, development

### Keyboard Controls

#### Main Menu
- `1-4`: Select stimulation condition
- `M`: Change mode
- `R`: Reconnect devices
- `C`: Show configuration
- `S`: Show device status
- `Q`: Quit application
- `SPACEBAR`: Start trial/menu
- `ESC`: Cancel/quit

#### Response Collection (Experiment Mode)
- `Numpad 1`: No Stimulation
- `Numpad 2`: Thermal Only
- `Numpad 3`: Vibrotactile Only
- `Numpad 4`: Thermal Motion
- `Numpad 5`: I don't know

---

## Experimental Protocols

### Full Experiment Protocol (160 Trials)

#### Latin Square Design
```
Row 1: A B D C
Row 2: B C A D
Row 3: C D B A
Row 4: D A C B

Where:
A = No Stimulation
B = Thermal Only
C = Vibrotactile Only
D = Thermal Motion
```

#### Block Structure
- **5 blocks** total
- **32 trials per block** (4 rows × 2 repetitions × 4 conditions)
- **60-second breaks** between blocks
- **Total duration**: ~45-60 minutes (including breaks)

#### Trial Sequence (Experiment Mode)
1. **Audio Cue** (500Hz) - Trial start signal
2. **Fixation Cross** (3.0-4.5s, randomized) - Prepare participant
3. **EEG Trigger** - Experiment type marker (0x01-0x04)
4. **Audio Cue** (1000Hz) - Stimulation start signal
5. **Stimulation** (5s total):
   - Warmup phase (2s)
   - Stroke/motion phase (3s)
6. **Audio Cue** (500Hz) - Question prompt
7. **Response Question** (1s delay before options)
8. **User Response** (Numpad 1-5)
9. **EEG Trigger** - Response marker (0x05-0x09)

### Timing Parameters (Configurable)

```python
warmup_time = 2.0          # Warmup phase (seconds)
stroke_duration = 3.0      # Motion phase (seconds)
fixation_min = 3.0         # Min fixation (seconds)
fixation_max = 4.5         # Max fixation (seconds)
question_delay = 1.0       # Delay before options (seconds)
break_duration = 60        # Inter-block break (seconds)
```

---

## Configuration

### Main Configuration Class

All adjustable parameters are centralized in `ExperimentConfig`:

```python
@dataclass
class ExperimentConfig:
    # PELTIER SETTINGS
    pwm_value: int = 159                    # PWM intensity (0-255)
    swap_polarity: bool = False             # Swap hot/cold behavior
    
    # MOTOR SETTINGS
    motor_intensity: int = 255              # Motor intensity (0-255)
    multipliers: Tuple[float, ...] = (1.0, 1.0, 0.9, 0.8)  # M0-M3
    motor_overlap: float = 1.0              # Overlap factor
    
    # TIMING SETTINGS
    warmup_time: float = 2.0                # Warmup duration (s)
    stroke_duration: float = 3.0            # Stroke duration (s)
    step_resolution: int = 50               # Updates per second
    
    # FIXATION SETTINGS
    fixation_min: float = 3.0               # Min fixation (s)
    fixation_max: float = 4.5               # Max fixation (s)
    
    # QUESTION SETTINGS
    question_delay: float = 1.0             # Delay before options (s)
    
    # EXPERIMENT PROTOCOL
    total_blocks: int = 5                   # Number of blocks
    trials_per_block: int = 32              # Trials per block
    break_duration: int = 60                # Break duration (s)
    
    # BROWSER DISPLAY
    browser_port: int = 8765                # HTTP server port
    secondary_monitor: bool = True          # Use secondary monitor
    browser_fullscreen: bool = True         # Start fullscreen
    
    # SERIAL SETTINGS
    device_baud_rate: int = 115200          # Arduino baud rate
    trigger_baud_rate: int = 9600           # Trigger box baud rate
    trigger_port: str = "COM4"              # EEG trigger port
    trigger_pulse_width_ms: int = 5         # Trigger pulse width
```

### Modifying Configuration

Edit the values in the `ExperimentConfig` class at the top of the script:

```python
# Example: Change PWM intensity
CONFIG.pwm_value = 180

# Example: Adjust timing
CONFIG.warmup_time = 3.0
CONFIG.stroke_duration = 4.0

# Example: Change break duration
CONFIG.break_duration = 90  # 90 seconds
```

---

## Troubleshooting

### Common Issues

#### 1. Arduino Not Detected
**Symptoms**: "No serial ports found" or device not connecting

**Solutions**:
- Check USB connections
- Verify Arduino is powered on
- Check Device Manager (Windows) for COM port numbers
- Try different USB ports
- Restart Arduino devices
- Clear port cache: Delete `thermal_motion_ports.json`

#### 2. EEG Trigger Box Not Connecting
**Symptoms**: "Failed to connect to trigger box on COM4"

**Solutions**:
- Verify trigger box is on COM4 (or update `CONFIG.trigger_port`)
- Check if another program is using COM4
- Use `trigger_sender.py` to test independently
- Try reconnecting: Press `R` in menu

#### 3. Audio Files Not Found
**Symptoms**: "Sounds: ○ Not Found (check Downloads folder)"

**Solutions**:
- Place `t0500hz.wav` and `t1000hz.wav` in Downloads folder
- Verify file names match exactly (case-sensitive)
- Check path: `C:\Users\<username>\Downloads\`
- System will work without audio (non-critical)

#### 4. Browser Display Not Opening
**Symptoms**: Browser doesn't open or shows blank page

**Solutions**:
- Check if port 8765 is available
- Try disabling firewall temporarily
- Manually open: `http://localhost:8765`
- Check if Edge or Chrome is installed
- Disable secondary monitor: `CONFIG.secondary_monitor = False`

#### 5. Keyboard Input Not Working
**Symptoms**: Keys not responding, need to press Enter

**Solutions**:
- Run as Administrator (Windows)
- On Linux: `sudo python thermal_motion_cli_v2.py`
- Fallback: System will prompt for input if keyboard fails

#### 6. Port Already in Use
**Symptoms**: "SerialException: Access is denied"

**Solutions**:
- Close other programs using serial ports
- Kill Python processes:
  ```powershell
  Get-Process python* | Stop-Process -Force
  ```
- Wait 5 seconds and retry
- Restart computer if persistent

### Debug Mode Testing

Use Debug Mode to isolate issues:

1. Start application
2. Select `[3] DEBUG MODE`
3. Test each condition individually
4. Check device responses in console
5. Verify hardware functionality

### Log Files

The system provides real-time logging with timestamps:

```
[14:23:45.123] [INFO    ] Scanning for devices...
[14:23:45.456] [SUCCESS ] Peltier connected on COM5
[14:23:45.789] [SUCCESS ] Motor controller found on COM8
[14:23:46.012] [SUCCESS ] Trigger box connected on COM4
```

---

## File Descriptions

### 🟢 Active Files (Root Directory)

#### `a.bat` ⭐ Quick Launcher
**Purpose**: Windows batch script to launch the main application  
**Usage**: Double-click to start  
**Content**:
```batch
@echo off
cd /d "%~dp0"
python thermal_motion_cli_v2.py
pause
```

#### `thermal_motion_cli_v2.py` ⭐ Main Application
**Version**: 2.2  
**Date**: 12 December 2025  
**Location**: Root directory  
**Features**:
- Full experiment mode with Latin square (160 trials)
- Single trial mode with manual selection
- Debug mode for testing
- Browser display on secondary monitor
- EEG trigger integration
- Audio cues (500Hz/1000Hz tones)
- Auto-device detection with caching
- Progress tracking

**Use**: Primary production script for all experiments  
**Run**: Double-click `a.bat` or `python thermal_motion_cli_v2.py`

#### `thermal_motion_ports.json`
**Purpose**: Cache Arduino device port assignments  
**Auto-generated**: Yes  
**Format**:
```json
{
  "peltier_port": "COM5",
  "motor_port": "COM8",
  "timestamp": "2025-12-12T19:36:18.135442",
  "version": "2.0"
}
```
**Note**: Safe to delete to force device re-detection

#### `thermal.ico`
**Purpose**: Application icon  
**Use**: Visual identification, future GUI integration

---

### 📦 Archive Folder (`archive/`)

Contains old versions and development files for reference only. **Not used by the main application.**

#### `thermal_motion_cli.py`
**Version**: 1.0 (Legacy)  
**Features**: Basic CLI, manual trial selection  
**Status**: Superseded by v2.2

#### `thermal_motion_cli_latinsquare.py`
**Purpose**: Latin square algorithm testing  
**Status**: Integrated into v2.2

#### `thermal_motion_cli_v2_latin_ready.py`
**Version**: 2.1 (Development)  
**Features**: Browser display implementation  
**Status**: Development version, superseded by v2.2

#### `thermal_motion_cli_v2_troublesome.py`
**Purpose**: Debug version with extra logging  
**Status**: Use main v2.2 debug mode instead

#### `thermal_motion_cli_v2 - backup.py`
**Purpose**: Backup copy  
**Status**: Archived for rollback if needed

---

### 🔧 Utilities Folder (`utilities/`)

Standalone tools that run independently from the main experiment.

#### `trigger_sender.py` ⭐ EEG Trigger Test Tool
**Version**: 2.0  
**Date**: 12 December 2025  
**Location**: `utilities/trigger_sender.py`  
**Features**:
- Standalone EEG trigger testing
- COM port management
- Process cleanup and port release
- Real-time trigger sending
- Independent of main experiment

**Purpose**: Test EEG trigger box connection separately  
**Use When**:
- Troubleshooting EEG triggers
- Verifying trigger box connectivity
- Testing without running full experiment

**Usage**:
```bash
# From utilities folder
cd utilities
python trigger_sender.py

# With options
python trigger_sender.py --port COM4
python trigger_sender.py --port COM3 --baud 9600

# From root directory
python utilities\trigger_sender.py
```

**Trigger Keys**:
- `1-4`: Experiment type triggers (0x01-0x04)
- `5-9`: User rating triggers (0x05-0x09)
- `R`: Reconnect to port
- `L`: List available ports
- `Q`: Quit

### Configuration Files

#### `thermal_motion_ports.json`
**Purpose**: Cache Arduino device port assignments  
**Format**:
```json
{
  "peltier_port": "COM5",
  "motor_port": "COM8",
  "timestamp": "2025-12-12T19:36:18.135442",
  "version": "2.0"
}
```

**Regeneration**: Auto-created on device detection  
**Manual Edit**: Safe to delete to force re-detection

### Launcher Scripts

#### `a.bat`
**Purpose**: Windows launcher script  
**Content**:
```batch
@echo off
cd /d "%~dp0"
python thermal_motion_cli_v2.py
pause
```

**Use**: Double-click to start application

### Assets

#### `thermal.ico`
**Purpose**: Application icon  
**Use**: Visual identification, future GUI integration

---

## Best Practices

### Before Each Experiment Session

1. **Hardware Check**:
   - Verify all USB connections
   - Test Peltier temperature control
   - Test motor vibrations
   - Check trigger box connection

2. **Software Check**:
   - Run Debug Mode to test each condition
   - Verify audio files are present
   - Test browser display on secondary monitor
   - Check EEG trigger reception

3. **Participant Preparation**:
   - Explain the four conditions
   - Practice with 2-3 trials
   - Verify participant can use numpad
   - Ensure comfortable seating

### During Experiment

1. **Monitor Progress**:
   - Watch CLI for errors
   - Check participant responses
   - Note any technical issues

2. **Inter-Block Breaks**:
   - Allow participant to rest
   - Check equipment status
   - Verify data recording

3. **Emergency Procedures**:
   - Press `ESC` to abort trial
   - Press `Ctrl+C` for emergency shutdown
   - All devices automatically turn off on exit

### After Experiment

1. **Data Backup**:
   - Save EEG recordings
   - Note any technical issues
   - Document participant feedback

2. **Equipment Maintenance**:
   - Clean Peltier surface
   - Check motor functionality
   - Verify all connections

---

## Technical Notes

### Thread Safety
- All serial communication is lock-protected
- Logger uses thread-safe printing
- Browser server runs in daemon thread
- Keyboard input uses non-blocking reads

### Error Handling
- Graceful degradation (missing audio, browser, etc.)
- Auto-reconnection for serial devices
- Emergency stop on all errors
- Clean shutdown on Ctrl+C

### Performance
- Motor position updates: 50 Hz (configurable)
- Browser state polling: 300ms
- Serial timeout: 100ms read, 1000ms write
- Trigger pulse width: 5ms

### Compatibility
- **Windows 10/11**: Full support
- **Windows 7/8**: Partial support (no PowerShell features)
- **Linux**: Full support (may need root for keyboard)
- **macOS**: Partial support (keyboard limitations)

---

## Version History

### v2.2 (12 December 2025)
- Added full experiment mode with Latin square design (160 trials)
- Implemented inter-block breaks with countdown
- Added progress tracking in CLI
- Enhanced experiment runner with block management

### v2.1 (12 December 2025)
- Added browser display on secondary monitor
- Implemented dynamic content updates
- Added numpad response capture
- Fixed global Fore/Back/Style declarations

### v2.0 (December 2025)
- Added experiment and debug modes
- Implemented auto-device detection with caching
- Added EEG trigger integration
- Added audio cues and randomized fixation

### v1.0 (December 2025)
- Initial CLI implementation
- Basic stimulation control
- Manual device connection

---

## Support and Contact

**Author**: Pi Ko  
**Email**: pi.ko@nyu.edu  
**Lab**: AIMLAB - NYU Abu Dhabi  
**Project**: Thermal Motion Perception Study

For technical issues, questions, or contributions, please contact the author.

---

## License

This software is developed for research purposes at NYU Abu Dhabi.  
All rights reserved © 2025 Pi Ko, AIMLAB, NYU Abu Dhabi.

---

## Acknowledgments

- AIMLAB research team
- NYU Abu Dhabi facilities
- Participants in the thermal motion study

---

**End of Documentation**

*Last Updated: 25 January 2026*

#!/usr/bin/env python3
"""
Robust EEG Serial Trigger Sender

Features:
- Auto-clears and connects to COM4 (or specified port)
- Kills any processes holding the COM port
- Real-time keyboard input (no Enter needed)
- Comprehensive logging
- Graceful error handling and reconnection

Experiment Type (keys 1-4):
  1 = No Stimulation    (0x01)
  2 = Thermal Only      (0x02)
  3 = Vibrotactile Only (0x03)
  4 = Thermal Motion    (0x04)

User Rating (keys 5-9):
  5 = No Stimulation    (0x05)
  6 = Thermal Only      (0x06)
  7 = Vibrotactile Only (0x07)
  8 = Thermal Motion    (0x08)
  9 = I don't Know      (0x09)

Usage:
  python trigger_sender.py
  python trigger_sender.py --port COM4
  python trigger_sender.py --port COM3 --baud 9600

@author Pi Ko (pi.ko@nyu.edu)
@version 2.0
@date 12 December 2025
"""

import argparse
import sys
import time
import os
import subprocess
import atexit
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================

DEFAULT_PORT = "COM4"
DEFAULT_BAUD = 9600
PULSE_WIDTH_MS = 5

# Trigger definitions
TRIGGERS = {
    # Experiment types (1-4)
    "1": (0x01, "No Stimulation", "EXPERIMENT"),
    "2": (0x02, "Thermal Only", "EXPERIMENT"),
    "3": (0x03, "Vibrotactile Only", "EXPERIMENT"),
    "4": (0x04, "Thermal Motion", "EXPERIMENT"),
    # User ratings (5-9)
    "5": (0x05, "No Stimulation", "RATING"),
    "6": (0x06, "Thermal Only", "RATING"),
    "7": (0x07, "Vibrotactile Only", "RATING"),
    "8": (0x08, "Thermal Motion", "RATING"),
    "9": (0x09, "I don't Know", "RATING"),
}

# ============================================
# LOGGING
# ============================================

class Logger:
    """Simple logger with timestamps and colors"""
    
    # Check if colors are supported
    USE_COLORS = sys.platform != 'win32' or 'ANSICON' in os.environ or 'WT_SESSION' in os.environ
    
    COLORS = {
        'INFO': '\033[94m',      # Blue
        'SUCCESS': '\033[92m',   # Green
        'WARNING': '\033[93m',   # Yellow
        'ERROR': '\033[91m',     # Red
        'TRIGGER': '\033[95m',   # Magenta
        'RESET': '\033[0m',      # Reset
    }
    
    @staticmethod
    def _enable_windows_colors():
        """Enable ANSI colors on Windows"""
        if sys.platform == 'win32':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
                Logger.USE_COLORS = True
            except:
                Logger.USE_COLORS = False
    
    @staticmethod
    def _timestamp():
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    @staticmethod
    def _print(level, message):
        if Logger.USE_COLORS:
            color = Logger.COLORS.get(level, '')
            reset = Logger.COLORS['RESET']
        else:
            color = ''
            reset = ''
        timestamp = Logger._timestamp()
        print(f"{color}[{timestamp}] [{level}] {message}{reset}")
    
    @staticmethod
    def info(message):
        Logger._print('INFO', message)
    
    @staticmethod
    def success(message):
        Logger._print('SUCCESS', message)
    
    @staticmethod
    def warning(message):
        Logger._print('WARNING', message)
    
    @staticmethod
    def error(message):
        Logger._print('ERROR', message)
    
    @staticmethod
    def trigger(message):
        Logger._print('TRIGGER', message)


# Enable colors on Windows
Logger._enable_windows_colors()
log = Logger()

# ============================================
# DEPENDENCIES CHECK
# ============================================

def check_dependencies():
    """Check and install required dependencies"""
    try:
        import serial
        log.success("pyserial is installed")
        return True
    except ImportError:
        log.warning("pyserial not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyserial", "-q"])
            log.success("pyserial installed successfully")
            return True
        except Exception as e:
            log.error(f"Failed to install pyserial: {e}")
            log.error("Please run: pip install pyserial")
            return False


# ============================================
# COM PORT MANAGEMENT
# ============================================

class COMPortManager:
    """Manages COM port connections with robust cleanup"""
    
    def __init__(self, port=DEFAULT_PORT, baud=DEFAULT_BAUD):
        self.port = port
        self.baud = baud
        self.serial = None
        self.connected = False
        
        # Register cleanup on exit
        atexit.register(self.cleanup)
    
    def kill_processes_using_port(self):
        """Kill any processes that might be using the COM port"""
        log.info(f"Clearing any processes using {self.port}...")
        
        if sys.platform == 'win32':
            try:
                # PowerShell command to kill Python processes (except ourselves)
                our_pid = os.getpid()
                ps_cmd = f'''
                    Get-Process python*,py* -ErrorAction SilentlyContinue | 
                    Where-Object {{ $_.Id -ne {our_pid} }} | 
                    Stop-Process -Force -ErrorAction SilentlyContinue
                '''
                subprocess.run(
                    ['powershell', '-Command', ps_cmd],
                    capture_output=True,
                    timeout=5
                )
                log.success("Cleared existing Python processes")
            except subprocess.TimeoutExpired:
                log.warning("Timeout while killing processes")
            except Exception as e:
                log.warning(f"Could not kill processes: {e}")
        else:
            # Linux/Mac
            try:
                subprocess.run(['pkill', '-f', 'trigger_sender'], capture_output=True, timeout=5)
            except:
                pass
        
        # Wait for port to be released
        time.sleep(0.5)
    
    def list_available_ports(self):
        """List all available COM ports"""
        import serial.tools.list_ports
        
        ports = serial.tools.list_ports.comports()
        
        print("\n" + "=" * 60)
        print(f" AVAILABLE COM PORTS ({len(ports)} found)")
        print("=" * 60)
        
        if not ports:
            print("   No COM ports found!")
        else:
            for port in ports:
                status = " ← TARGET" if port.device == self.port else ""
                connected = " [CONNECTED]" if port.device == self.port and self.connected else ""
                print(f"   {port.device}: {port.description}{status}{connected}")
        
        print("=" * 60 + "\n")
        
        return [p.device for p in ports]
    
    def force_close_port(self):
        """Force close the serial port"""
        import serial
        
        if self.serial:
            try:
                if self.serial.is_open:
                    self.serial.reset_input_buffer()
                    self.serial.reset_output_buffer()
                    self.serial.close()
                log.info(f"Closed existing connection to {self.port}")
            except Exception as e:
                log.warning(f"Error closing port: {e}")
            finally:
                self.serial = None
                self.connected = False
        
        # Try to open and close to reset the port state
        try:
            temp = serial.Serial(self.port, self.baud, timeout=0.1)
            temp.close()
            log.info(f"Reset {self.port} state")
        except:
            pass
        
        time.sleep(0.3)
    
    def connect(self, retries=3):
        """Connect to the COM port with retries"""
        import serial
        
        log.info(f"Connecting to {self.port} @ {self.baud} baud...")
        
        for attempt in range(1, retries + 1):
            try:
                self.serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baud,
                    timeout=0.1,
                    write_timeout=1.0
                )
                
                if self.serial.is_open:
                    self.connected = True
                    log.success(f"✓ Connected to {self.port} @ {self.baud} baud")
                    return True
                    
            except serial.SerialException as e:
                log.warning(f"Attempt {attempt}/{retries} failed: {e}")
                
                if attempt < retries:
                    log.info("Trying to force release port...")
                    self.force_close_port()
                    self.kill_processes_using_port()
                    time.sleep(0.5)
            
            except Exception as e:
                log.error(f"Unexpected error: {e}")
        
        log.error(f"✗ Failed to connect to {self.port} after {retries} attempts")
        self.connected = False
        return False
    
    def reconnect(self):
        """Reconnect to the COM port"""
        log.info("Reconnecting...")
        self.force_close_port()
        self.kill_processes_using_port()
        time.sleep(0.3)
        return self.connect()
    
    def send_trigger(self, key):
        """Send a trigger pulse"""
        if key not in TRIGGERS:
            log.error(f"Invalid trigger key: {key}")
            return False
        
        code, label, trigger_type = TRIGGERS[key]
        
        if not self.connected or not self.serial or not self.serial.is_open:
            log.warning("Not connected. Attempting to reconnect...")
            if not self.reconnect():
                log.error("Failed to reconnect. Trigger not sent.")
                return False
        
        try:
            # Send trigger code
            self.serial.write(bytes([code]))
            self.serial.flush()
            
            # Hold for pulse width
            time.sleep(PULSE_WIDTH_MS / 1000.0)
            
            # Reset to 0
            self.serial.write(b'\x00')
            self.serial.flush()
            
            log.trigger(f"[{trigger_type}] 0x{code:02X} → {label}")
            return True
            
        except Exception as e:
            log.error(f"Failed to send trigger: {e}")
            self.connected = False
            return False
    
    def cleanup(self):
        """Cleanup resources"""
        log.info("Cleaning up...")
        if self.serial:
            try:
                if self.serial.is_open:
                    self.serial.reset_input_buffer()
                    self.serial.reset_output_buffer()
                    self.serial.close()
                log.success("Serial port closed cleanly")
            except Exception as e:
                log.warning(f"Cleanup error: {e}")
            self.serial = None
        self.connected = False


# ============================================
# USER INTERFACE
# ============================================

def print_banner():
    """Print the application banner"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║         EEG SERIAL TRIGGER SENDER v2.0                     ║")
    print("║         Real-time trigger sending for EEG experiments      ║")
    print("║         Author: Pi Ko (pi.ko@nyu.edu)                      ║")
    print("╚════════════════════════════════════════════════════════════╝")


def print_menu():
    """Print the trigger menu"""
    print("\n┌────────────────────────────────────────────────────────────┐")
    print("│  EXPERIMENT TYPE (Press 1-4)                               │")
    print("├────────────────────────────────────────────────────────────┤")
    for key in ['1', '2', '3', '4']:
        code, label, _ = TRIGGERS[key]
        print(f"│    [{key}]  0x{code:02X}  →  {label:<38} │")
    
    print("├────────────────────────────────────────────────────────────┤")
    print("│  USER RATING (Press 5-9)                                   │")
    print("├────────────────────────────────────────────────────────────┤")
    for key in ['5', '6', '7', '8', '9']:
        code, label, _ = TRIGGERS[key]
        print(f"│    [{key}]  0x{code:02X}  →  {label:<38} │")
    
    print("├────────────────────────────────────────────────────────────┤")
    print("│  COMMANDS                                                  │")
    print("├────────────────────────────────────────────────────────────┤")
    print("│    [R]  Reconnect to COM port                              │")
    print("│    [L]  List available COM ports                           │")
    print("│    [M]  Show this menu                                     │")
    print("│    [Q]  Quit                                               │")
    print("└────────────────────────────────────────────────────────────┘")
    print("\n  → Press any key (1-9) to send trigger instantly")
    print("  → No Enter key needed!\n")


def print_status(com_manager):
    """Print current connection status"""
    if com_manager.connected:
        status = "✓ CONNECTED"
        color = '\033[92m' if Logger.USE_COLORS else ''
    else:
        status = "✗ DISCONNECTED"
        color = '\033[91m' if Logger.USE_COLORS else ''
    reset = '\033[0m' if Logger.USE_COLORS else ''
    
    print(f"\n  Status: {color}{status}{reset} to {com_manager.port} @ {com_manager.baud} baud\n")


# ============================================
# MAIN APPLICATION
# ============================================

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Robust EEG Serial Trigger Sender",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trigger_sender.py                    # Use COM4 (default)
  python trigger_sender.py --port COM3        # Use COM3
  python trigger_sender.py --port COM4 --baud 115200
        """
    )
    parser.add_argument(
        "--port", "-p",
        default=DEFAULT_PORT,
        help=f"Serial port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--baud", "-b",
        type=int,
        default=DEFAULT_BAUD,
        help=f"Baud rate (default: {DEFAULT_BAUD})"
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Skip killing existing processes"
    )
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Import serial after dependency check
    import serial
    
    # Create COM port manager
    com = COMPortManager(port=args.port, baud=args.baud)
    
    # Kill existing processes (unless --no-clear)
    if not args.no_clear:
        com.kill_processes_using_port()
    
    # List available ports
    available = com.list_available_ports()
    
    # Check if target port exists
    if args.port not in available:
        log.warning(f"{args.port} not found in available ports!")
        log.info("Will attempt to connect anyway...")
    
    # Connect
    if not com.connect():
        log.error("Initial connection failed.")
        log.info("Press [R] to retry or [L] to list ports")
    
    # Print menu and status
    print_menu()
    print_status(com)
    
    # Main loop - using simple input since getch may not work everywhere
    log.info("Ready! Press keys 1-9 to send triggers, Q to quit")
    print("-" * 60)
    
    try:
        while True:
            try:
                # Use simple input - user presses key then Enter
                # This is more compatible across all systems
                key = input("  > ").strip().lower()
                
                if not key:
                    continue
                
                # Take first character only
                key = key[0]
                
                if key == 'q':
                    log.info("Quitting...")
                    break
                
                elif key == 'r':
                    log.info("Reconnecting...")
                    com.force_close_port()
                    com.kill_processes_using_port()
                    if com.connect():
                        print_status(com)
                    else:
                        log.error("Reconnection failed. Press R to retry.")
                
                elif key == 'l':
                    com.list_available_ports()
                
                elif key == 'm':
                    print_menu()
                    print_status(com)
                
                elif key in TRIGGERS:
                    com.send_trigger(key)
                
                else:
                    log.warning(f"Unknown key: '{key}'. Valid: 1-9, R, L, M, Q")
                    
            except EOFError:
                break
    
    except KeyboardInterrupt:
        log.info("\nInterrupted by user (Ctrl+C)")
    
    finally:
        com.cleanup()
        print("\n" + "=" * 60)
        log.success("Goodbye! Serial port released.")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

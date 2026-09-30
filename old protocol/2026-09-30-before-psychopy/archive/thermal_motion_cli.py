#!/usr/bin/env python3
"""
Thermal Motion Controller - Command Line Interface
A standalone Python CLI for controlling the thermal motion experimental setup.

Author: Pi Ko (pi.ko@nyu.edu)
Based on Electron app by Pi Ko at AIMLAB NYUAD
CLI Version: 1.0
Date: December 2025

Hardware:
- Peltier Controller (Arduino) - Thermoelectric heating/cooling
- Motor Controller (Arduino) - 4 vibration motors (M0-M3) for funneling illusion

Usage:
    python thermal_motion_cli.py

Requirements:
    pip install pyserial tqdm colorama keyboard

"""

import sys
import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List, Callable
from enum import Enum
import signal

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial not installed. Run: pip install pyserial")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("ERROR: tqdm not installed. Run: pip install tqdm")
    sys.exit(1)

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
except ImportError:
    print("ERROR: colorama not installed. Run: pip install colorama")
    sys.exit(1)

try:
    import keyboard
except ImportError:
    print("ERROR: keyboard not installed. Run: pip install keyboard")
    print("Note: On Linux, you may need to run as root or use: sudo pip install keyboard")
    sys.exit(1)


# ============================================
# CONFIGURATION - HARDCODED FROM JSON
# ============================================

@dataclass
class Config:
    """Configuration matching thermal-motion-config-2025-12-12T14-07-56.json"""
    # Peltier settings
    pwm_value: int = 159
    swap_polarity: bool = False
    
    # Motor settings
    motor_intensity: int = 255
    multipliers: Tuple[float, ...] = (1.0, 1.0, 0.9, 0.8)
    motor_overlap: float = 1.0
    
    # Timing settings (in seconds)
    warmup_time: float = 2.0
    stroke_duration: float = 3.0
    step_resolution: int = 50  # Steps per second
    
    # Serial settings
    baud_rate: int = 115200
    timeout: float = 0.1
    
    # Device identification strings
    peltier_id: str = "PELTIER_CONTROLLER_V3"
    motor_id: str = "MOTOR_CONTROLLER_V3"


CONFIG = Config()


# ============================================
# ENUMS AND TYPES
# ============================================

class StimulationType(Enum):
    """Experimental stimulation conditions"""
    NONE = 1
    THERMAL_ONLY = 2
    VIBROTACTILE_ONLY = 3
    THERMAL_MOTION = 4


class LogLevel(Enum):
    """Log levels with colors"""
    INFO = (Fore.CYAN, "INFO")
    SUCCESS = (Fore.GREEN, "SUCCESS")
    WARNING = (Fore.YELLOW, "WARNING")
    ERROR = (Fore.RED, "ERROR")
    PELTIER = (Fore.MAGENTA, "PELTIER")
    MOTOR = (Fore.BLUE, "MOTOR")
    SYSTEM = (Fore.WHITE, "SYSTEM")


# ============================================
# LOGGING SETUP
# ============================================

class ColoredLogger:
    """Custom colored logger for console output"""
    
    def __init__(self, name: str = "ThermalMotion"):
        self.name = name
        self._lock = threading.Lock()
    
    def _log(self, level: LogLevel, message: str):
        """Thread-safe colored log output"""
        color, label = level.value
        timestamp = time.strftime("%H:%M:%S")
        with self._lock:
            print(f"{Fore.WHITE}[{timestamp}] {color}[{label:^8}]{Style.RESET_ALL} {message}")
    
    def info(self, msg: str):
        self._log(LogLevel.INFO, msg)
    
    def success(self, msg: str):
        self._log(LogLevel.SUCCESS, msg)
    
    def warning(self, msg: str):
        self._log(LogLevel.WARNING, msg)
    
    def error(self, msg: str):
        self._log(LogLevel.ERROR, msg)
    
    def peltier(self, msg: str):
        self._log(LogLevel.PELTIER, msg)
    
    def motor(self, msg: str):
        self._log(LogLevel.MOTOR, msg)
    
    def system(self, msg: str):
        self._log(LogLevel.SYSTEM, msg)


log = ColoredLogger()


# ============================================
# SERIAL DEVICE CLASSES
# ============================================

class SerialDevice:
    """Base class for serial communication with Arduino devices"""
    
    def __init__(self, device_id: str, device_name: str):
        self.device_id = device_id
        self.device_name = device_name
        self.port: Optional[serial.Serial] = None
        self.connected = False
        self._read_thread: Optional[threading.Thread] = None
        self._running = False
        self._response_callback: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()
    
    def connect(self, port_path: str, baud_rate: int = CONFIG.baud_rate) -> bool:
        """Connect to serial port and verify device identity"""
        try:
            self.port = serial.Serial(
                port=port_path,
                baudrate=baud_rate,
                timeout=CONFIG.timeout,
                write_timeout=1.0
            )
            time.sleep(0.5)  # Wait for Arduino reset
            
            # Clear any startup messages
            self.port.reset_input_buffer()
            
            # Send identification request
            self.send_command("IDENTIFY", wait_response=False)
            time.sleep(0.3)
            
            # Read response
            response = self._read_all_available()
            
            if self.device_id in response:
                self.connected = True
                self._start_read_thread()
                return True
            else:
                self.port.close()
                self.port = None
                return False
                
        except serial.SerialException as e:
            log.error(f"Failed to connect to {port_path}: {e}")
            return False
        except Exception as e:
            log.error(f"Unexpected error connecting to {port_path}: {e}")
            return False
    
    def _read_all_available(self) -> str:
        """Read all available data from serial port"""
        response = ""
        try:
            while self.port and self.port.in_waiting > 0:
                line = self.port.readline().decode('utf-8', errors='ignore').strip()
                response += line + " "
                time.sleep(0.01)
        except Exception:
            pass
        return response
    
    def _start_read_thread(self):
        """Start background thread for reading responses"""
        self._running = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
    
    def _read_loop(self):
        """Background loop to read serial responses"""
        while self._running and self.port and self.port.is_open:
            try:
                if self.port.in_waiting > 0:
                    line = self.port.readline().decode('utf-8', errors='ignore').strip()
                    if line and self._response_callback:
                        self._response_callback(line)
                time.sleep(0.01)
            except Exception:
                break
    
    def send_command(self, command: str, wait_response: bool = False) -> Optional[str]:
        """Send command to device"""
        if not self.port or not self.port.is_open:
            log.error(f"{self.device_name} not connected")
            return None
        
        try:
            with self._lock:
                self.port.write(f"{command}\n".encode('utf-8'))
                self.port.flush()
                
                if wait_response:
                    time.sleep(0.05)
                    return self._read_all_available()
            return None
        except Exception as e:
            log.error(f"Failed to send command to {self.device_name}: {e}")
            return None
    
    def disconnect(self):
        """Disconnect from device"""
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=1.0)
        if self.port and self.port.is_open:
            try:
                self.port.close()
            except Exception:
                pass
        self.port = None
        self.connected = False


class PeltierController(SerialDevice):
    """Controller for Peltier thermoelectric device"""
    
    def __init__(self):
        super().__init__(CONFIG.peltier_id, "Peltier")
        self._response_callback = self._handle_response
    
    def _handle_response(self, response: str):
        """Handle responses from Peltier controller"""
        log.peltier(f"Response: {response}")
    
    def set_hot(self, pwm: int = CONFIG.pwm_value):
        """Activate heating mode"""
        cmd = f"HOT:{pwm}"
        self.send_command(cmd)
        log.peltier(f"Set HOT mode (PWM: {pwm})")
    
    def set_cold(self, pwm: int = CONFIG.pwm_value):
        """Activate cooling mode"""
        cmd = f"COLD:{pwm}"
        self.send_command(cmd)
        log.peltier(f"Set COLD mode (PWM: {pwm})")
    
    def turn_off(self):
        """Turn off Peltier"""
        self.send_command("OFF")
        log.peltier("Turned OFF")
    
    def get_status(self) -> Optional[str]:
        """Get current status"""
        return self.send_command("STATUS", wait_response=True)
    
    def ping(self) -> bool:
        """Check if device is responsive"""
        response = self.send_command("PING", wait_response=True)
        return response is not None and "PONG" in response


class MotorController(SerialDevice):
    """Controller for vibration motor array"""
    
    def __init__(self):
        super().__init__(CONFIG.motor_id, "Motor")
        self._response_callback = self._handle_response
    
    def _handle_response(self, response: str):
        """Handle responses from Motor controller"""
        log.motor(f"Response: {response}")
    
    def set_intensity(self, intensity: int = CONFIG.motor_intensity):
        """Set global motor intensity"""
        cmd = f"INTENSITY:{intensity}"
        self.send_command(cmd)
        log.motor(f"Set intensity: {intensity}")
    
    def set_multiplier(self, motor_num: int, value: float):
        """Set multiplier for specific motor"""
        cmd = f"MULT:{motor_num}:{value:.2f}"
        self.send_command(cmd)
    
    def set_overlap(self, overlap: float = CONFIG.motor_overlap):
        """Set motor overlap for smooth transitions"""
        cmd = f"OVERLAP:{overlap:.2f}"
        self.send_command(cmd)
        log.motor(f"Set overlap: {overlap:.2f}")
    
    def set_position(self, position: float):
        """Set interpolated position (0.0 to 3.0)"""
        position = max(0.0, min(3.0, position))
        cmd = f"POS:{position:.2f}"
        self.send_command(cmd)
    
    def activate_motor(self, motor_num: int, intensity: Optional[int] = None):
        """Activate specific motor"""
        if intensity is not None:
            cmd = f"MOTOR:{motor_num}:{intensity}"
        else:
            cmd = f"MOTOR:{motor_num}"
        self.send_command(cmd)
    
    def stop_all(self):
        """Stop all motors"""
        self.send_command("STOP")
        log.motor("All motors stopped")
    
    def ping(self) -> bool:
        """Check if device is responsive"""
        response = self.send_command("PING", wait_response=True)
        return response is not None and "PONG" in response


# ============================================
# DEVICE SCANNER
# ============================================

class DeviceScanner:
    """Scans and connects to Arduino devices"""
    
    @staticmethod
    def list_ports() -> List[str]:
        """List all available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]
    
    @staticmethod
    def find_and_connect(peltier: PeltierController, motor: MotorController) -> Tuple[bool, bool]:
        """
        Scan all ports and connect to devices.
        Returns (peltier_connected, motor_connected)
        """
        ports = DeviceScanner.list_ports()
        
        if not ports:
            log.warning("No serial ports found")
            return False, False
        
        log.info(f"Found {len(ports)} serial port(s): {', '.join(ports)}")
        
        peltier_connected = False
        motor_connected = False
        
        for port_path in ports:
            if peltier_connected and motor_connected:
                break
            
            # Skip already connected ports
            if peltier.connected and peltier.port and peltier.port.port == port_path:
                continue
            if motor.connected and motor.port and motor.port.port == port_path:
                continue
            
            log.info(f"Scanning {port_path}...")
            
            # Try to connect as Peltier
            if not peltier_connected:
                if peltier.connect(port_path):
                    log.success(f"Peltier controller found on {port_path}")
                    peltier_connected = True
                    continue
            
            # Try to connect as Motor
            if not motor_connected:
                if motor.connect(port_path):
                    log.success(f"Motor controller found on {port_path}")
                    motor_connected = True
                    continue
        
        return peltier_connected, motor_connected


# ============================================
# STIMULATION EXECUTOR
# ============================================

class StimulationExecutor:
    """Executes experimental stimulation protocols"""
    
    def __init__(self, peltier: PeltierController, motor: MotorController):
        self.peltier = peltier
        self.motor = motor
        self._abort = False
    
    def abort(self):
        """Signal to abort current stimulation"""
        self._abort = True
    
    def _check_abort(self) -> bool:
        """Check if abort was signaled"""
        if self._abort:
            self._abort = False
            return True
        return False
    
    def _setup_motors(self):
        """Configure motor settings before stimulation"""
        self.motor.set_intensity(CONFIG.motor_intensity)
        time.sleep(0.05)
        
        # Set multipliers
        for i, mult in enumerate(CONFIG.multipliers):
            self.motor.set_multiplier(i, mult)
            time.sleep(0.02)
        
        # Set overlap
        self.motor.set_overlap(CONFIG.motor_overlap)
        time.sleep(0.05)
    
    def _get_thermal_command(self) -> str:
        """Get the appropriate thermal command based on polarity setting"""
        # We want HOT sensation
        # If swap_polarity is True, send HOT command
        # If swap_polarity is False, send COLD command (hardware is inverted)
        return "HOT" if CONFIG.swap_polarity else "COLD"
    
    def execute_no_stimulation(self) -> bool:
        """
        Execute No Stimulation condition.
        Just wait for the full duration with progress display.
        """
        log.info("Starting No Stimulation trial")
        total_duration = CONFIG.warmup_time + CONFIG.stroke_duration
        
        try:
            with tqdm(total=100, desc="No Stimulation", 
                     bar_format='{l_bar}{bar}| {n:.1f}% [{elapsed}<{remaining}]',
                     colour='white') as pbar:
                
                start_time = time.time()
                last_progress = 0
                
                while True:
                    if self._check_abort():
                        log.warning("Stimulation aborted")
                        return False
                    
                    elapsed = time.time() - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    # Update progress bar
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    # Update description based on phase
                    if elapsed < CONFIG.warmup_time:
                        pbar.set_description(f"No Stim - Warmup ({elapsed:.1f}s)")
                    else:
                        pbar.set_description(f"No Stim - Waiting ({elapsed:.1f}s)")
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.02)
            
            log.success("No Stimulation trial completed")
            return True
            
        except Exception as e:
            log.error(f"Error during No Stimulation: {e}")
            return False
    
    def execute_thermal_only(self) -> bool:
        """
        Execute Thermal Only condition.
        Peltier active for full duration.
        """
        log.info("Starting Thermal Only trial")
        total_duration = CONFIG.warmup_time + CONFIG.stroke_duration
        
        try:
            # Turn on Peltier
            thermal_cmd = self._get_thermal_command()
            if thermal_cmd == "HOT":
                self.peltier.set_hot(CONFIG.pwm_value)
            else:
                self.peltier.set_cold(CONFIG.pwm_value)
            
            with tqdm(total=100, desc="Thermal Only", 
                     bar_format='{l_bar}{bar}| {n:.1f}% [{elapsed}<{remaining}]',
                     colour='red') as pbar:
                
                start_time = time.time()
                last_progress = 0
                
                while True:
                    if self._check_abort():
                        self.peltier.turn_off()
                        log.warning("Stimulation aborted")
                        return False
                    
                    elapsed = time.time() - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    if elapsed < CONFIG.warmup_time:
                        pbar.set_description(f"Thermal - Warmup ({elapsed:.1f}s)")
                    else:
                        pbar.set_description(f"Thermal - Heating ({elapsed:.1f}s)")
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.02)
            
            # Turn off Peltier
            self.peltier.turn_off()
            log.success("Thermal Only trial completed")
            return True
            
        except Exception as e:
            log.error(f"Error during Thermal Only: {e}")
            self.peltier.turn_off()
            return False
    
    def execute_vibrotactile_only(self) -> bool:
        """
        Execute Vibrotactile Only condition.
        Funneling sweep from M0 to M3.
        """
        log.info("Starting Vibrotactile Only trial")
        total_duration = CONFIG.warmup_time + CONFIG.stroke_duration
        step_interval = 1.0 / CONFIG.step_resolution
        
        try:
            # Setup motors
            self._setup_motors()
            
            with tqdm(total=100, desc="Vibrotactile", 
                     bar_format='{l_bar}{bar}| {n:.1f}% [{elapsed}<{remaining}]',
                     colour='blue') as pbar:
                
                start_time = time.time()
                last_progress = 0
                last_step_time = 0
                
                while True:
                    if self._check_abort():
                        self.motor.stop_all()
                        log.warning("Stimulation aborted")
                        return False
                    
                    current_time = time.time()
                    elapsed = current_time - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    # Send position commands at step interval
                    if current_time - last_step_time >= step_interval:
                        if elapsed < CONFIG.warmup_time:
                            # Warmup - motor at position 0
                            self.motor.set_position(0.0)
                            pbar.set_description(f"Vibro - Warmup M0 ({elapsed:.1f}s)")
                        else:
                            # Stroke - sweep from 0 to 3
                            stroke_elapsed = elapsed - CONFIG.warmup_time
                            stroke_progress = min(stroke_elapsed / CONFIG.stroke_duration, 1.0)
                            position = stroke_progress * 3.0
                            self.motor.set_position(position)
                            pbar.set_description(f"Vibro - Pos:{position:.2f} ({elapsed:.1f}s)")
                        
                        last_step_time = current_time
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.01)
            
            # Stop motors
            self.motor.stop_all()
            log.success("Vibrotactile Only trial completed")
            return True
            
        except Exception as e:
            log.error(f"Error during Vibrotactile Only: {e}")
            self.motor.stop_all()
            return False
    
    def execute_thermal_motion(self) -> bool:
        """
        Execute Thermal Motion condition.
        Combined Peltier + funneling sweep.
        """
        log.info("Starting Thermal Motion trial")
        total_duration = CONFIG.warmup_time + CONFIG.stroke_duration
        step_interval = 1.0 / CONFIG.step_resolution
        
        try:
            # Setup motors
            self._setup_motors()
            
            # Turn on Peltier
            thermal_cmd = self._get_thermal_command()
            if thermal_cmd == "HOT":
                self.peltier.set_hot(CONFIG.pwm_value)
            else:
                self.peltier.set_cold(CONFIG.pwm_value)
            
            with tqdm(total=100, desc="Thermal Motion", 
                     bar_format='{l_bar}{bar}| {n:.1f}% [{elapsed}<{remaining}]',
                     colour='magenta') as pbar:
                
                start_time = time.time()
                last_progress = 0
                last_step_time = 0
                
                while True:
                    if self._check_abort():
                        self.peltier.turn_off()
                        self.motor.stop_all()
                        log.warning("Stimulation aborted")
                        return False
                    
                    current_time = time.time()
                    elapsed = current_time - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    # Send position commands at step interval
                    if current_time - last_step_time >= step_interval:
                        if elapsed < CONFIG.warmup_time:
                            # Warmup - motor at position 0 + heating
                            self.motor.set_position(0.0)
                            pbar.set_description(f"TherMo - Warmup ({elapsed:.1f}s)")
                        else:
                            # Stroke - sweep from 0 to 3 with heating
                            stroke_elapsed = elapsed - CONFIG.warmup_time
                            stroke_progress = min(stroke_elapsed / CONFIG.stroke_duration, 1.0)
                            position = stroke_progress * 3.0
                            self.motor.set_position(position)
                            pbar.set_description(f"TherMo - Pos:{position:.2f} ({elapsed:.1f}s)")
                        
                        last_step_time = current_time
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.01)
            
            # Turn off everything
            self.peltier.turn_off()
            self.motor.stop_all()
            log.success("Thermal Motion trial completed")
            return True
            
        except Exception as e:
            log.error(f"Error during Thermal Motion: {e}")
            self.peltier.turn_off()
            self.motor.stop_all()
            return False
    
    def execute(self, stim_type: StimulationType) -> bool:
        """Execute the specified stimulation type"""
        self._abort = False
        
        if stim_type == StimulationType.NONE:
            return self.execute_no_stimulation()
        elif stim_type == StimulationType.THERMAL_ONLY:
            return self.execute_thermal_only()
        elif stim_type == StimulationType.VIBROTACTILE_ONLY:
            return self.execute_vibrotactile_only()
        elif stim_type == StimulationType.THERMAL_MOTION:
            return self.execute_thermal_motion()
        else:
            log.error(f"Unknown stimulation type: {stim_type}")
            return False
    
    def emergency_stop(self):
        """Emergency stop - turn off all devices"""
        self._abort = True
        try:
            if self.peltier.connected:
                self.peltier.turn_off()
        except Exception:
            pass
        try:
            if self.motor.connected:
                self.motor.stop_all()
        except Exception:
            pass
        log.warning("EMERGENCY STOP executed")


# ============================================
# MAIN APPLICATION
# ============================================

class ThermalMotionCLI:
    """Main CLI application"""
    
    def __init__(self):
        self.peltier = PeltierController()
        self.motor = MotorController()
        self.executor: Optional[StimulationExecutor] = None
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals"""
        print()  # New line after ^C
        log.warning("Interrupt received, shutting down...")
        self.shutdown()
        sys.exit(0)
    
    def print_banner(self):
        """Print application banner"""
        banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   {Fore.WHITE}████████╗██╗  ██╗███████╗██████╗ ███╗   ███╗ █████╗ ██╗{Fore.CYAN}        ║
║   {Fore.WHITE}╚══██╔══╝██║  ██║██╔════╝██╔══██╗████╗ ████║██╔══██╗██║{Fore.CYAN}        ║
║   {Fore.WHITE}   ██║   ███████║█████╗  ██████╔╝██╔████╔██║███████║██║{Fore.CYAN}        ║
║   {Fore.WHITE}   ██║   ██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══██║██║{Fore.CYAN}        ║
║   {Fore.WHITE}   ██║   ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║██║  ██║███████╗{Fore.CYAN}   ║
║   {Fore.WHITE}   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝{Fore.CYAN}   ║
║                                                                  ║
║        {Fore.YELLOW}███╗   ███╗ ██████╗ ████████╗██╗ ██████╗ ███╗   ██╗{Fore.CYAN}       ║
║        {Fore.YELLOW}████╗ ████║██╔═══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║{Fore.CYAN}       ║
║        {Fore.YELLOW}██╔████╔██║██║   ██║   ██║   ██║██║   ██║██╔██╗ ██║{Fore.CYAN}       ║
║        {Fore.YELLOW}██║╚██╔╝██║██║   ██║   ██║   ██║██║   ██║██║╚██╗██║{Fore.CYAN}       ║
║        {Fore.YELLOW}██║ ╚═╝ ██║╚██████╔╝   ██║   ██║╚██████╔╝██║ ╚████║{Fore.CYAN}       ║
║        {Fore.YELLOW}╚═╝     ╚═╝ ╚═════╝    ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝{Fore.CYAN}       ║
║                                                                  ║
║                  {Fore.GREEN}Command Line Controller v1.0{Fore.CYAN}                   ║
║                                                                  ║
║            {Fore.WHITE}Author: Pi Ko (pi.ko@nyu.edu){Fore.CYAN}                       ║
║            {Fore.WHITE}AIMLAB - NYU Abu Dhabi{Fore.CYAN}                              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}"""
        print(banner)
    
    def print_config(self):
        """Print current configuration"""
        print(f"\n{Fore.CYAN}{'─' * 50}")
        print(f"{Fore.WHITE}Configuration:")
        print(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}")
        print(f"  Peltier PWM:      {CONFIG.pwm_value}")
        print(f"  Swap Polarity:    {CONFIG.swap_polarity}")
        print(f"  Motor Intensity:  {CONFIG.motor_intensity}")
        print(f"  Motor Overlap:    {CONFIG.motor_overlap}")
        print(f"  Multipliers:      {CONFIG.multipliers}")
        print(f"  Warmup Time:      {CONFIG.warmup_time}s")
        print(f"  Stroke Duration:  {CONFIG.stroke_duration}s")
        print(f"  Total Duration:   {CONFIG.warmup_time + CONFIG.stroke_duration}s")
        print(f"  Step Resolution:  {CONFIG.step_resolution}/sec")
        print(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}\n")
    
    def connect_devices(self) -> bool:
        """Scan and connect to all devices"""
        print(f"\n{Fore.CYAN}Scanning for devices...{Style.RESET_ALL}\n")
        
        peltier_ok, motor_ok = DeviceScanner.find_and_connect(self.peltier, self.motor)
        
        print()
        
        # Show connection status
        print(f"{Fore.CYAN}{'─' * 50}")
        print(f"{Fore.WHITE}Device Status:")
        print(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}")
        
        if peltier_ok:
            print(f"  Peltier:  {Fore.GREEN}✓ Connected{Style.RESET_ALL}")
        else:
            print(f"  Peltier:  {Fore.RED}✗ Not found{Style.RESET_ALL}")
        
        if motor_ok:
            print(f"  Motors:   {Fore.GREEN}✓ Connected{Style.RESET_ALL}")
        else:
            print(f"  Motors:   {Fore.RED}✗ Not found{Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}\n")
        
        if peltier_ok and motor_ok:
            log.success("All devices connected successfully!")
            self.executor = StimulationExecutor(self.peltier, self.motor)
            return True
        else:
            log.warning("Some devices are missing. Proceeding anyway...")
            self.executor = StimulationExecutor(self.peltier, self.motor)
            return True  # Allow running even with missing devices
    
    def show_menu(self) -> Optional[StimulationType]:
        """Display stimulation selection menu and get user choice"""
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════╗")
        print(f"║       {Fore.WHITE}Select Stimulation Condition{Fore.CYAN}               ║")
        print(f"╠══════════════════════════════════════════════════╣")
        print(f"║                                                  ║")
        print(f"║   {Fore.WHITE}[1]{Fore.CYAN}  No Stimulation                            ║")
        print(f"║   {Fore.RED}[2]{Fore.CYAN}  Thermal Only                              ║")
        print(f"║   {Fore.BLUE}[3]{Fore.CYAN}  Vibrotactile Only                         ║")
        print(f"║   {Fore.MAGENTA}[4]{Fore.CYAN}  Thermal Motion (Combined)                 ║")
        print(f"║                                                  ║")
        print(f"║   {Fore.YELLOW}[Q]{Fore.CYAN}  Quit                                      ║")
        print(f"║   {Fore.YELLOW}[R]{Fore.CYAN}  Reconnect devices                         ║")
        print(f"║                                                  ║")
        print(f"╚══════════════════════════════════════════════════╝{Style.RESET_ALL}")
        print()
        
        while True:
            try:
                choice = input(f"{Fore.GREEN}Enter choice (1-4, Q, R): {Style.RESET_ALL}").strip().upper()
                
                if choice == '1':
                    return StimulationType.NONE
                elif choice == '2':
                    return StimulationType.THERMAL_ONLY
                elif choice == '3':
                    return StimulationType.VIBROTACTILE_ONLY
                elif choice == '4':
                    return StimulationType.THERMAL_MOTION
                elif choice == 'Q':
                    return None
                elif choice == 'R':
                    self.connect_devices()
                    return self.show_menu()  # Show menu again
                else:
                    log.warning("Invalid choice. Please enter 1-4, Q, or R.")
            except EOFError:
                return None
            except KeyboardInterrupt:
                return None
    
    def wait_for_spacebar(self):
        """Wait for spacebar press to show menu"""
        print(f"\n{Fore.YELLOW}╔══════════════════════════════════════════════════╗")
        print(f"║                                                  ║")
        print(f"║    Press {Fore.WHITE}[SPACEBAR]{Fore.YELLOW} to start experiment menu     ║")
        print(f"║                                                  ║")
        print(f"║    Press {Fore.WHITE}[ESC]{Fore.YELLOW} to quit                           ║")
        print(f"║                                                  ║")
        print(f"╚══════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
        
        while self.running:
            try:
                event = keyboard.read_event(suppress=False)
                if event.event_type == keyboard.KEY_DOWN:
                    if event.name == 'space':
                        return True
                    elif event.name == 'esc':
                        return False
            except Exception as e:
                # Fallback to input-based waiting
                log.warning(f"Keyboard hook failed: {e}")
                log.info("Falling back to input mode. Press ENTER to continue or 'q' to quit:")
                try:
                    user_input = input().strip().lower()
                    if user_input == 'q':
                        return False
                    return True
                except (EOFError, KeyboardInterrupt):
                    return False
        
        return False
    
    def run(self):
        """Main application loop"""
        try:
            self.print_banner()
            self.print_config()
            
            if not self.connect_devices():
                log.error("Failed to initialize. Exiting.")
                return
            
            log.info("System ready!")
            
            while self.running:
                if not self.wait_for_spacebar():
                    break
                
                stim_type = self.show_menu()
                
                if stim_type is None:
                    break
                
                # Execute the selected stimulation
                print()
                log.info(f"Executing: {stim_type.name}")
                print()
                
                success = self.executor.execute(stim_type)
                
                if success:
                    print()
                    log.success(f"Trial completed: {stim_type.name}")
                else:
                    print()
                    log.warning(f"Trial incomplete: {stim_type.name}")
                
                print()
                time.sleep(0.5)
        
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown of all resources"""
        self.running = False
        
        log.info("Shutting down...")
        
        # Emergency stop if executor exists
        if self.executor:
            self.executor.emergency_stop()
        
        # Disconnect devices
        if self.peltier.connected:
            try:
                self.peltier.turn_off()
            except Exception:
                pass
            self.peltier.disconnect()
            log.info("Peltier disconnected")
        
        if self.motor.connected:
            try:
                self.motor.stop_all()
            except Exception:
                pass
            self.motor.disconnect()
            log.info("Motors disconnected")
        
        log.success("Shutdown complete. Goodbye!")


# ============================================
# ENTRY POINT
# ============================================

def main():
    """Application entry point"""
    app = ThermalMotionCLI()
    app.run()


if __name__ == "__main__":
    main()

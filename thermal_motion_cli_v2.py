#!/usr/bin/env python3
"""
Thermal Motion Controller - Command Line Interface
A standalone Python CLI for controlling the thermal motion experimental setup.

Author: Pi Ko (pi.ko@nyu.edu)
AIMLAB - NYU Abu Dhabi
Version: 2.2
Date: 12 December 2025

Changelog:
v2.2 (12 December 2025):
    - Added full experiment mode with Latin square design (160 trials)
    - 5 blocks × 32 trials with counterbalanced Latin square
    - Inter-block breaks with countdown timer (adjustable duration)
    - Progress tracking in CLI (non-distractive)
    - Experiment complete screen
    - Three modes: Full Experiment, Single Trial, Debug

v2.1 (12 December 2025):
    - Added non-blocking browser display on secondary monitor
    - Browser shows welcome screen, fixation cross, blank during stimulation, and questions
    - Browser captures numpad input for responses
    - Browser automatically closes on shutdown
    - Fixed global Fore/Back/Style declaration for StimulationType enum

v2.0 (December 2025):
    - Initial release with experiment and debug modes
    - Auto-detection of Arduino devices with port caching
    - EEG trigger integration
    - Audio cues and randomized fixation periods

Hardware:
- Peltier Controller (Arduino) - Thermoelectric heating/cooling
- Motor Controller (Arduino) - 4 vibration motors (M0-M3) for funneling illusion
- EEG Trigger Box (COM4) - For sending experiment triggers

Features:
- Two modes: Experiment (with triggers) and Debug (without triggers)
- Auto-detection of Arduino devices with port caching
- EEG trigger integration
- Audio cues (500Hz/1000Hz tones)
- Randomized fixation periods
- Clean CLI interface with progress bars
- Secondary monitor browser display (experiment mode only)
- Non-blocking browser with dynamic content updates

Usage:
    python thermal_motion_cli_v2.py

Requirements:
    pip install pyserial tqdm colorama keyboard
"""

import sys
import os
import time
import threading
import json
import random
import signal
import atexit
import http.server
import socketserver
import webbrowser
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, List, Callable, Dict
from enum import Enum
from datetime import datetime
from urllib.parse import parse_qs, urlparse

# ============================================
# CONFIGURATION - ALL ADJUSTABLE PARAMETERS
# ============================================

@dataclass
class ExperimentConfig:
    """
    All adjustable experiment parameters.
    Modify these values to customize the experiment.
    """
    
    # ===== PELTIER SETTINGS =====
    pwm_value: int = 159                    # PWM intensity (0-255)
    swap_polarity: bool = False             # Swap hot/cold behavior
    
    # ===== MOTOR SETTINGS =====
    motor_intensity: int = 255              # Motor intensity (0-255)
    multipliers: Tuple[float, ...] = (1.0, 1.0, 0.9, 0.8)  # M0-M3 multipliers
    motor_overlap: float = 1.0              # Overlap factor for smooth transitions
    
    # ===== TIMING SETTINGS =====
    warmup_time: float = 2.0                # Warmup phase duration (seconds)
    stroke_duration: float = 3.0            # Stroke/motion phase duration (seconds)
    step_resolution: int = 50               # Motor position updates per second
    
    # ===== FIXATION SETTINGS =====
    fixation_min: float = 3.0               # Minimum fixation duration (seconds)
    fixation_max: float = 4.5               # Maximum fixation duration (seconds)
    
    # ===== QUESTION SETTINGS =====
    question_delay: float = 1.0             # Delay before showing answers (seconds)
    
    # ===== EXPERIMENT PROTOCOL SETTINGS =====
    total_blocks: int = 5                   # Number of blocks
    trials_per_block: int = 32              # Trials per block
    break_duration: int = 60                # Break duration in seconds (1 minute)
    latin_square_repetitions: int = 2       # How many times to repeat 4 rows per block
    
    # ===== BROWSER DISPLAY SETTINGS =====
    browser_port: int = 8765                # Local server port
    secondary_monitor: bool = True          # Use secondary monitor if available
    browser_fullscreen: bool = True         # Start browser in fullscreen
    
    # ===== SERIAL SETTINGS =====
    device_baud_rate: int = 115200          # Baud rate for Peltier/Motor controllers
    trigger_baud_rate: int = 9600           # Baud rate for EEG trigger box
    serial_timeout: float = 0.1             # Serial read timeout
    trigger_port: str = "COM4"              # Default EEG trigger port
    trigger_pulse_width_ms: int = 5         # Trigger pulse width in milliseconds
    
    # ===== DEVICE IDENTIFICATION =====
    peltier_id: str = "PELTIER_CONTROLLER_V3"
    motor_id: str = "MOTOR_CONTROLLER_V3"
    
    # ===== FILE PATHS =====
    port_cache_file: str = "thermal_motion_ports.json"
    sound_500hz: str = "t0500hz.wav"
    sound_1000hz: str = "t1000hz.wav"
    
    # ===== DISPLAY SETTINGS =====
    clear_lines: int = 50                   # Number of lines to clear for clean display
    
    @property
    def total_duration(self) -> float:
        """Total stimulation duration"""
        return self.warmup_time + self.stroke_duration


# Global configuration instance
CONFIG = ExperimentConfig()


# ============================================
# TRIGGER DEFINITIONS
# ============================================

TRIGGERS: Dict[str, Tuple[int, str, str]] = {
    # Experiment types (1-4)
    "1": (0x01, "No sensation", "EXPERIMENT"),
    "2": (0x02, "Static Thermal", "EXPERIMENT"),
    "3": (0x03, "Moving Vibrotactile", "EXPERIMENT"),
    "4": (0x04, "Moving Thermal", "EXPERIMENT"),
    # User ratings (5-9) - mapped from numpad 1-5
    "5": (0x05, "No sensation", "RATING"),
    "6": (0x06, "Static Thermal", "RATING"),
    "7": (0x07, "Moving Vibrotactile", "RATING"),
    "8": (0x08, "Moving Thermal", "RATING"),
    "9": (0x09, "I'm not sure", "RATING"),
}


# ============================================
# DEPENDENCY CHECKS
# ============================================

def check_and_import_dependencies():
    """Check and import all required dependencies"""
    missing = []
    
    try:
        global serial, list_ports
        import serial
        import serial.tools.list_ports as list_ports
    except ImportError:
        missing.append("pyserial")
    
    try:
        global tqdm
        from tqdm import tqdm
    except ImportError:
        missing.append("tqdm")
    
    try:
        global Fore, Back, Style
        from colorama import Fore, Back, Style, init as colorama_init
        colorama_init(autoreset=True)
    except ImportError:
        missing.append("colorama")
    
    try:
        global keyboard
        import keyboard
    except ImportError:
        missing.append("keyboard")
    
    if missing:
        print(f"ERROR: Missing dependencies: {', '.join(missing)}")
        print(f"Run: pip install {' '.join(missing)}")
        sys.exit(1)
    
    return True


# Run dependency check immediately
check_and_import_dependencies()


# ============================================
# SOUND PLAYER (Non-blocking)
# ============================================

class SoundPlayer:
    """Non-blocking sound player for audio cues"""
    
    def __init__(self):
        self.sound_dir = Path.home() / "Downloads"
        self._check_sounds()
    
    def _check_sounds(self):
        """Check if sound files exist"""
        self.sound_500hz_path = self.sound_dir / CONFIG.sound_500hz
        self.sound_1000hz_path = self.sound_dir / CONFIG.sound_1000hz
        
        self.sounds_available = (
            self.sound_500hz_path.exists() and 
            self.sound_1000hz_path.exists()
        )
    
    def _play_sound_thread(self, filepath: Path):
        """Play sound in background thread"""
        try:
            if sys.platform == 'win32':
                import winsound
                winsound.PlaySound(str(filepath), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                # Linux/Mac fallback
                os.system(f'aplay -q "{filepath}" &')
        except Exception as e:
            pass  # Silently fail if sound doesn't work
    
    def play_500hz(self):
        """Play 500Hz tone (non-blocking)"""
        if self.sounds_available:
            threading.Thread(
                target=self._play_sound_thread, 
                args=(self.sound_500hz_path,),
                daemon=True
            ).start()
    
    def play_1000hz(self):
        """Play 1000Hz tone (non-blocking)"""
        if self.sounds_available:
            threading.Thread(
                target=self._play_sound_thread, 
                args=(self.sound_1000hz_path,),
                daemon=True
            ).start()


# ============================================
# BROWSER DISPLAY MANAGER (Non-blocking)
# ============================================

class BrowserDisplayManager:
    """
    Manages a full-screen browser display on secondary monitor.
    Uses a local HTTP server to serve dynamic content.
    
    Author: Pi Ko (pi.ko@nyu.edu)
    Version: 2.1
    """
    
    # HTML Templates
    TEMPLATE_BASE = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Thermal Motion Experiment</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                background-color: #000000;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                height: 100vh;
                width: 100vw;
                display: flex;
                justify-content: center;
                align-items: center;
                overflow: hidden;
            }}
            .container {{
                text-align: center;
                max-width: 80%;
            }}
            h1 {{ font-size: 3em; margin-bottom: 0.5em; }}
            h2 {{ font-size: 2em; margin-bottom: 1em; color: #cccccc; }}
            p {{ font-size: 1.5em; line-height: 1.8; color: #aaaaaa; }}
            .cross {{
                font-size: 150px;
                font-weight: bold;
                color: #ffffff;
            }}
            .question {{ font-size: 2.5em; margin-bottom: 1em; }}
            .options {{ text-align: left; display: inline-block; }}
            .option {{ 
                font-size: 1.8em; 
                margin: 0.5em 0; 
                padding: 0.3em 0;
            }}
            .option-key {{ 
                color: #00ff00; 
                font-weight: bold;
                margin-right: 1em;
            }}
            .hidden {{ display: none; }}
        </style>
        <script>
            let currentState = '';
            let lastContent = '';
            
            async function checkState() {{
                try {{
                    const response = await fetch('/state');
                    const newState = await response.text();
                    if (newState !== currentState) {{
                        currentState = newState;
                        // Fetch new content instead of full reload
                        const pageResponse = await fetch('/');
                        const html = await pageResponse.text();
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(html, 'text/html');
                        const newContent = doc.querySelector('.container').innerHTML;
                        if (newContent !== lastContent) {{
                            document.querySelector('.container').innerHTML = newContent;
                            lastContent = newContent;
                        }}
                    }}
                }} catch(e) {{}}
                setTimeout(checkState, 200);
            }}
            checkState();
            
            // Capture ALL number keys (numpad and regular)
            document.addEventListener('keydown', async (e) => {{
                // Get the actual number pressed
                let key = null;
                
                // Numpad keys
                if (e.code === 'Numpad1') key = '1';
                else if (e.code === 'Numpad2') key = '2';
                else if (e.code === 'Numpad3') key = '3';
                else if (e.code === 'Numpad4') key = '4';
                else if (e.code === 'Numpad5') key = '5';
                // Regular number keys
                else if (e.key >= '1' && e.key <= '5') key = e.key;
                
                if (key) {{
                    e.preventDefault();
                    try {{
                        await fetch('/keypress?key=' + key);
                        console.log('Sent key:', key);
                    }} catch(err) {{
                        console.error('Failed to send key:', err);
                    }}
                }}
            }});
            
            // Keep focus on document for key capture
            document.body.focus();
            setInterval(() => document.body.focus(), 1000);
        </script>
    </head>
    <body>
        <div class="container">
            {content}
        </div>
    </body>
    </html>
    """
    
    CONTENT_WELCOME = """
        <h1>Thermal Motion Study</h1>
        <p style="font-size: 1.3em; color: #cccccc;">
            Focus on the screen and remain still during trials.
        </p>
    """
    
    CONTENT_FIXATION = """
        <div class="cross">+</div>
    """
    
    CONTENT_BLANK = """
        <div style="
            width: 120px;
            height: 120px;
            background-color: #ffffff;
            border-radius: 50%;
        "></div>
    """
    
    CONTENT_QUESTION = """
        <div class="question">Which sensation did you experience?</div>
    """
    
    CONTENT_QUESTION_WITH_OPTIONS = """
        <div class="question">Which sensation did you experience?</div>
        <div class="options">
            <div class="option"><span class="option-key">[1]</span> No sensation</div>
            <div class="option"><span class="option-key">[2]</span> Static Thermal</div>
            <div class="option"><span class="option-key">[3]</span> Moving Vibrotactile</div>
            <div class="option"><span class="option-key">[4]</span> Moving Thermal</div>
            <div class="option"><span class="option-key">[5]</span> I'm not sure</div>
        </div>
    """
    
    CONTENT_THANKYOU = """
        <h1>Thank You</h1>
        <p>The experiment has ended.<br>Please wait for further instructions.</p>
    """
    
    CONTENT_BREAK = """
        <h1>Break Time</h1>
        <h2>Please rest your eyes</h2>
        <div class="countdown" id="countdown" style="font-size: 5em; margin-top: 0.5em; color: #888888;">
            {seconds}
        </div>
        <p style="margin-top: 1em;">Next block will begin automatically</p>
    """
    
    CONTENT_BLOCK_START = """
        <h1>Block {block_num} of {total_blocks}</h1>
        <p style="font-size: 1.5em; margin-top: 1em;">
            {trials_in_block} trials in this block<br><br>
            Press any key when ready to continue
        </p>
    """
    
    CONTENT_EXPERIMENT_COMPLETE = """
        <h1>Experiment Complete</h1>
        <h2 style="color: #00ff00;">Thank you for participating!</h2>
        <p style="margin-top: 1em;">
            You have completed all {total_trials} trials.<br><br>
            Please wait for the researcher.
        </p>
    """
    
    def __init__(self):
        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.browser_process: Optional[subprocess.Popen] = None
        self.current_state = "welcome"
        self.current_content = self.CONTENT_WELCOME
        self.running = False
        self.last_keypress: Optional[str] = None
        self._keypress_lock = threading.Lock()
        self._state_version = 0
    
    def _create_handler(self):
        """Create HTTP request handler with access to display manager"""
        display_manager = self
        
        class DisplayHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress HTTP logs
            
            def do_GET(self):
                parsed = urlparse(self.path)
                
                try:
                    if parsed.path == '/state':
                        # Return current state version for polling
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.send_header('Cache-Control', 'no-cache')
                        self.end_headers()
                        self.wfile.write(f"{display_manager._state_version}".encode())
                        
                    elif parsed.path == '/keypress':
                        # Capture keypress from browser
                        query = parse_qs(parsed.query)
                        key = query.get('key', [None])[0]
                        if key:
                            with display_manager._keypress_lock:
                                display_manager.last_keypress = key
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(b'OK')
                        
                    else:
                        # Serve main page
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.send_header('Cache-Control', 'no-cache')
                        self.end_headers()
                        html = display_manager.TEMPLATE_BASE.format(
                            content=display_manager.current_content
                        )
                        self.wfile.write(html.encode())
                
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    # Client disconnected - ignore silently
                    pass
                except Exception:
                    # Ignore other connection errors
                    pass
        
        return DisplayHandler
    
    def start(self):
        """Start the display server and open browser"""
        if self.running:
            return
        
        self.running = True
        
        # Start HTTP server in background thread
        handler = self._create_handler()
        self.server = socketserver.TCPServer(("", CONFIG.browser_port), handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        
        log.info(f"Display server started on port {CONFIG.browser_port}")
        
        # Open browser on secondary monitor (Windows-specific)
        url = f"http://localhost:{CONFIG.browser_port}"
        
        # Try to open on secondary monitor using PowerShell
        if CONFIG.secondary_monitor and sys.platform == 'win32':
            self._open_browser_secondary_monitor(url)
        else:
            webbrowser.open(url)
        
        time.sleep(1)  # Give browser time to open
        
        # Send F11 for fullscreen (Windows)
        if CONFIG.browser_fullscreen and sys.platform == 'win32':
            self._make_fullscreen()
    
    def _open_browser_secondary_monitor(self, url: str):
        """Open browser on secondary monitor (Windows)"""
        try:
            # Get screen info using PowerShell
            ps_script = '''
            Add-Type -AssemblyName System.Windows.Forms
            $screens = [System.Windows.Forms.Screen]::AllScreens
            if ($screens.Count -gt 1) {{
                $secondary = $screens | Where-Object {{ -not $_.Primary }} | Select-Object -First 1
                $x = $secondary.Bounds.X
                $y = $secondary.Bounds.Y
                Write-Output "$x,$y"
            }} else {{
                Write-Output "0,0"
            }}
            '''
            result = subprocess.run(
                ['powershell', '-Command', ps_script],
                capture_output=True, text=True, timeout=5
            )
            coords = result.stdout.strip().split(',')
            x, y = int(coords[0]), int(coords[1])
            
            # Open Chrome/Edge with position (prefer Edge on Windows)
            edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            
            browser_path = None
            if os.path.exists(edge_path):
                browser_path = edge_path
            elif os.path.exists(chrome_path):
                browser_path = chrome_path
            
            if browser_path:
                # Open with window position on secondary monitor
                self.browser_process = subprocess.Popen([
                    browser_path,
                    f'--window-position={x},{y}',
                    '--new-window',
                    '--start-fullscreen',
                    f'--app={url}'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(url)
                
        except Exception as e:
            log.warning(f"Could not open on secondary monitor: {e}")
            webbrowser.open(url)
    
    def _make_fullscreen(self):
        """Send F11 to make browser fullscreen"""
        try:
            time.sleep(0.5)
            keyboard.send('f11')
        except Exception:
            pass
    
    def set_state(self, state: str):
        """Update display state"""
        if state == self.current_state:
            return
        
        self.current_state = state
        self._state_version += 1
        
        if state == "welcome":
            self.current_content = self.CONTENT_WELCOME
        elif state == "fixation":
            self.current_content = self.CONTENT_FIXATION
        elif state == "blank":
            self.current_content = self.CONTENT_BLANK
        elif state == "question":
            self.current_content = self.CONTENT_QUESTION
        elif state == "question_options":
            self.current_content = self.CONTENT_QUESTION_WITH_OPTIONS
        elif state == "thankyou":
            self.current_content = self.CONTENT_THANKYOU
    
    def get_keypress(self) -> Optional[str]:
        """Get and clear last keypress from browser"""
        with self._keypress_lock:
            key = self.last_keypress
            self.last_keypress = None
            return key
    
    def set_break_countdown(self, seconds: int):
        """Update break screen with countdown"""
        self.current_state = "break"
        self._state_version += 1
        self.current_content = self.CONTENT_BREAK.format(seconds=seconds)
    
    def set_block_start(self, block_num: int, total_blocks: int, trials_in_block: int):
        """Show block start screen"""
        self.current_state = "block_start"
        self._state_version += 1
        self.current_content = self.CONTENT_BLOCK_START.format(
            block_num=block_num,
            total_blocks=total_blocks,
            trials_in_block=trials_in_block
        )
    
    def set_experiment_complete(self, total_trials: int):
        """Show experiment complete screen"""
        self.current_state = "complete"
        self._state_version += 1
        self.current_content = self.CONTENT_EXPERIMENT_COMPLETE.format(
            total_trials=total_trials
        )
    
    def stop(self):
        """Stop server and close browser"""
        self.running = False
        
        # Close browser
        if self.browser_process:
            try:
                self.browser_process.terminate()
                self.browser_process.wait(timeout=2)
            except Exception:
                try:
                    self.browser_process.kill()
                except Exception:
                    pass
        
        # Stop server
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass
        
        log.info("Display server stopped")


# ============================================
# LATIN SQUARE EXPERIMENT MANAGER
# ============================================

class LatinSquareManager:
    """
    Manages the counterbalanced Latin square experimental design.
    
    Latin Square:
        Row 1: A B D C
        Row 2: B C A D
        Row 3: C D B A
        Row 4: D A C B
    
    Where:
        A = No Stimulation
        B = Thermal Only
        C = Vibrotactile Only
        D = Thermal Motion (Combined)
    
    Block Structure:
        - 4 rows × 2 repetitions = 32 trials per block
        - 5 blocks total = 160 trials
    
    Author: Pi Ko (pi.ko@nyu.edu)
    Version: 2.1
    """
    
    # The fixed Latin Square
    LATIN_SQUARE = [
        ['A', 'B', 'D', 'C'],  # Row 1
        ['B', 'C', 'A', 'D'],  # Row 2
        ['C', 'D', 'B', 'A'],  # Row 3
        ['D', 'A', 'C', 'B'],  # Row 4
    ]
    
    # Mapping from letters to StimulationType (will be set after StimulationType is defined)
    CONDITION_MAP = {}
    CONDITION_NAMES = {
        'A': 'No sensation',
        'B': 'Static Thermal',
        'C': 'Moving Vibrotactile',
        'D': 'Moving Thermal',
    }
    
    def __init__(self):
        self.current_block = 0
        self.current_trial_in_block = 0
        self.total_trial = 0
        self.block_sequence: List[str] = []
        self.full_sequence: List[str] = []
        
        # Generate full experiment sequence
        self._generate_full_sequence()
    
    def _generate_block_sequence(self) -> List[str]:
        """Generate one block of 32 trials (4 rows × 2 repetitions)"""
        block = []
        for _ in range(CONFIG.latin_square_repetitions):  # Default: 2 repetitions
            for row in self.LATIN_SQUARE:
                block.extend(row)
        return block
    
    def _generate_full_sequence(self):
        """Generate the complete experiment sequence (160 trials)"""
        self.full_sequence = []
        for _ in range(CONFIG.total_blocks):
            self.full_sequence.extend(self._generate_block_sequence())
    
    def set_condition_map(self, condition_map: Dict[str, 'StimulationType']):
        """Set the mapping from letters to StimulationType (called after StimulationType is defined)"""
        self.CONDITION_MAP = condition_map
    
    def get_current_condition(self) -> Optional['StimulationType']:
        """Get the stimulation type for current trial"""
        if self.total_trial >= len(self.full_sequence):
            return None
        condition_letter = self.full_sequence[self.total_trial]
        return self.CONDITION_MAP.get(condition_letter)
    
    def get_current_condition_letter(self) -> str:
        """Get the letter (A/B/C/D) for current trial"""
        if self.total_trial >= len(self.full_sequence):
            return "?"
        return self.full_sequence[self.total_trial]
    
    def get_current_condition_name(self) -> str:
        """Get the name for current trial condition"""
        letter = self.get_current_condition_letter()
        return self.CONDITION_NAMES.get(letter, "Unknown")
    
    def advance(self) -> bool:
        """
        Move to next trial.
        Returns True if there are more trials, False if experiment is complete.
        """
        self.total_trial += 1
        self.current_trial_in_block += 1
        
        # Check if block is complete
        if self.current_trial_in_block >= CONFIG.trials_per_block:
            self.current_block += 1
            self.current_trial_in_block = 0
        
        return self.total_trial < len(self.full_sequence)
    
    def is_block_complete(self) -> bool:
        """Check if current block just completed"""
        return self.current_trial_in_block == 0 and self.total_trial > 0
    
    def is_experiment_complete(self) -> bool:
        """Check if all trials are complete"""
        return self.total_trial >= len(self.full_sequence)
    
    def needs_break(self) -> bool:
        """Check if a break is needed (between blocks, not after last)"""
        return (self.is_block_complete() and 
                self.current_block < CONFIG.total_blocks)
    
    def get_progress_info(self) -> dict:
        """Get current progress information"""
        return {
            'total_trial': self.total_trial + 1,  # 1-indexed for display
            'total_trials': len(self.full_sequence),
            'current_block': self.current_block + 1,  # 1-indexed
            'total_blocks': CONFIG.total_blocks,
            'trial_in_block': self.current_trial_in_block + 1,  # 1-indexed
            'trials_per_block': CONFIG.trials_per_block,
            'condition_letter': self.get_current_condition_letter(),
            'condition_name': self.get_current_condition_name(),
            'progress_percent': (self.total_trial / len(self.full_sequence)) * 100 if len(self.full_sequence) > 0 else 0,
        }
    
    def get_block_summary(self) -> str:
        """Get summary of conditions in current block"""
        start_idx = self.current_block * CONFIG.trials_per_block
        end_idx = start_idx + CONFIG.trials_per_block
        block_conditions = self.full_sequence[start_idx:end_idx]
        
        counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        for c in block_conditions:
            counts[c] += 1
        
        return f"A:{counts['A']} B:{counts['B']} C:{counts['C']} D:{counts['D']}"
    
    def reset(self):
        """Reset to beginning of experiment"""
        self.current_block = 0
        self.current_trial_in_block = 0
        self.total_trial = 0


# ============================================
# DATA LOGGER
# ============================================

class DataLogger:
    """
    Logs experiment data to a timestamped file.
    Saves incrementally to prevent data loss.
    
    Author: Pi Ko (pi.ko@nyu.edu)
    Version: 2.2
    """
    
    def __init__(self):
        self.file_path: Optional[Path] = None
        self.file_handle = None
        self.start_time: Optional[datetime] = None
        self.trial_count = 0
    
    def _get_desktop_path(self) -> Path:
        """Get the user's Desktop path"""
        if sys.platform == 'win32':
            return Path.home() / "Desktop"
        elif sys.platform == 'darwin':  # macOS
            return Path.home() / "Desktop"
        else:  # Linux
            return Path.home() / "Desktop"
    
    def _generate_filename(self) -> str:
        """Generate filename with timestamp: 2025_Dec_12_5_30_33_pm_thermal.txt"""
        now = datetime.now()
        
        # Format: 2025_Dec_12_5_30_33_pm
        hour_12 = now.hour % 12
        if hour_12 == 0:
            hour_12 = 12
        am_pm = "am" if now.hour < 12 else "pm"
        
        filename = (
            f"{now.year}_"
            f"{now.strftime('%b')}_"
            f"{now.day}_"
            f"{hour_12}_"
            f"{now.minute}_"
            f"{now.second}_"
            f"{am_pm}_thermal.txt"
        )
        return filename
    
    def _get_unique_filepath(self, folder: Path, base_filename: str) -> Path:
        """Get unique filepath, adding _1, _2, etc. if file exists"""
        filepath = folder / base_filename
        
        if not filepath.exists():
            return filepath
        
        # File exists, add suffix
        name_without_ext = base_filename.rsplit('.', 1)[0]
        ext = base_filename.rsplit('.', 1)[1] if '.' in base_filename else 'txt'
        
        counter = 1
        while True:
            new_filename = f"{name_without_ext}_{counter}.{ext}"
            filepath = folder / new_filename
            if not filepath.exists():
                return filepath
            counter += 1
    
    def start(self) -> bool:
        """Initialize logging - create folder and file"""
        try:
            # Create folder on Desktop
            desktop = self._get_desktop_path()
            data_folder = desktop / "Thermal Experiment Data"
            data_folder.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename
            filename = self._generate_filename()
            self.file_path = self._get_unique_filepath(data_folder, filename)
            
            # Open file for writing
            self.file_handle = open(self.file_path, 'w', encoding='utf-8')
            
            # Record start time
            self.start_time = datetime.now()
            
            # Write header
            self._write_line("=" * 60)
            self._write_line("THERMAL MOTION EXPERIMENT DATA LOG")
            self._write_line("=" * 60)
            self._write_line("")
            self._write_line(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self._write_line(f"File: {self.file_path.name}")
            self._write_line("")
            self._write_line("-" * 60)
            self._write_line("TRIAL DATA")
            self._write_line("-" * 60)
            self._write_line("")
            self._write_line("Format: Trial# | Block | Trial_in_Block | Condition | Response | Correct | Timestamp")
            self._write_line("")
            
            log.success(f"Data logging started: {self.file_path}", force=True)
            return True
            
        except Exception as e:
            log.error(f"Failed to start data logging: {e}", force=True)
            return False
    
    def _write_line(self, text: str):
        """Write a line and flush immediately"""
        if self.file_handle:
            self.file_handle.write(text + "\n")
            self.file_handle.flush()
    
    def log_response(
        self,
        trial_number: int,
        block_number: int,
        trial_in_block: int,
        condition_letter: str,
        condition_name: str,
        response_number: int,
        response_name: str
    ):
        """Log a single trial response"""
        self.trial_count += 1
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Determine if response matches condition
        # Condition: A=1, B=2, C=3, D=4
        # Response: 1=None, 2=Thermal, 3=Vibro, 4=ThermalMotion, 5=DontKnow
        condition_to_correct = {'A': 1, 'B': 2, 'C': 3, 'D': 4}
        correct_response = condition_to_correct.get(condition_letter, 0)
        is_correct = "YES" if response_number == correct_response else "NO"
        
        # Format line
        line = (
            f"Trial {trial_number:3d} | "
            f"Block {block_number} | "
            f"T{trial_in_block:2d} | "
            f"{condition_letter} ({condition_name:20s}) | "
            f"Response: {response_number} ({response_name:20s}) | "
            f"Correct: {is_correct:3s} | "
            f"{timestamp}"
        )
        
        self._write_line(line)
        
    def log_trial_skipped(
        self,
        trial_number: int,
        block_number: int,
        trial_in_block: int,
        condition_letter: str,
        condition_name: str,
        reason: str = "No response"
    ):
        """Log a skipped/aborted trial"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        line = (
            f"Trial {trial_number:3d} | "
            f"Block {block_number} | "
            f"T{trial_in_block:2d} | "
            f"{condition_letter} ({condition_name:20s}) | "
            f"SKIPPED: {reason:30s} | "
            f"{timestamp}"
        )
        
        self._write_line(line)
    
    def end(self, completed: bool = True):
        """Finalize logging - write end time and close file"""
        if not self.file_handle:
            return
        
        try:
            end_time = datetime.now()
            
            self._write_line("")
            self._write_line("-" * 60)
            self._write_line("SUMMARY")
            self._write_line("-" * 60)
            self._write_line("")
            self._write_line(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if self.start_time:
                duration = end_time - self.start_time
                hours, remainder = divmod(int(duration.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                self._write_line(f"Duration: {hours:02d}:{minutes:02d}:{seconds:02d}")
            
            self._write_line(f"Trials Logged: {self.trial_count}")
            self._write_line(f"Status: {'COMPLETED' if completed else 'INCOMPLETE/ABORTED'}")
            self._write_line("")
            self._write_line("=" * 60)
            self._write_line("END OF LOG")
            self._write_line("=" * 60)
            
            self.file_handle.close()
            self.file_handle = None
            
            log.success(f"Data saved to: {self.file_path}", force=True)
            
        except Exception as e:
            log.error(f"Error finalizing data log: {e}", force=True)
    
    def __del__(self):
        """Ensure file is closed on cleanup"""
        if self.file_handle:
            try:
                self.file_handle.close()
            except:
                pass


# ============================================
# FULL EXPERIMENT RUNNER
# ============================================

class ExperimentRunner:
    """
    Manages the full 160-trial experiment with Latin square design.
    
    Author: Pi Ko (pi.ko@nyu.edu)
    Version: 2.1
    """
    
    def __init__(self, app: 'ThermalMotionCLI'):
        self.app = app
        self.latin_square = LatinSquareManager()
        self.data_logger = DataLogger()
        self.running = False
        self.paused = False
        
        # Set up condition mapping after StimulationType is available
        self.latin_square.set_condition_map({
            'A': StimulationType.NONE,
            'B': StimulationType.THERMAL_ONLY,
            'C': StimulationType.VIBROTACTILE_ONLY,
            'D': StimulationType.THERMAL_MOTION,
        })
    
    def get_progress_line(self) -> str:
        """Get a single-line progress string for display below tqdm/questions"""
        info = self.latin_square.get_progress_info()
        
        # Create compact progress string
        progress_str = (
            f"{Fore.CYAN}│ "
            f"{Fore.WHITE}Block {info['current_block']}/{info['total_blocks']} "
            f"{Fore.CYAN}│ "
            f"{Fore.WHITE}Trial {info['trial_in_block']}/{info['trials_per_block']} "
            f"{Fore.CYAN}│ "
            f"{Fore.YELLOW}[{info['condition_letter']}] {info['condition_name']} "
            f"{Fore.CYAN}│ "
            f"{Fore.GREEN}{info['progress_percent']:.1f}% complete "
            f"{Fore.CYAN}│ "
            f"{Fore.WHITE}({info['total_trial']}/{info['total_trials']})"
            f"{Style.RESET_ALL}"
        )
        return progress_str
    
    def print_progress_footer(self):
        """Print progress info footer (call after tqdm or questions)"""
        print(f"\n{Fore.CYAN}{'─' * 70}{Style.RESET_ALL}")
        print(self.get_progress_line())
        print(f"{Fore.CYAN}{'─' * 70}{Style.RESET_ALL}")
    
    def print_progress_header(self):
        """Print non-distractive progress info in CLI"""
        info = self.latin_square.get_progress_info()
        
        # Compact single-line progress
        progress_bar_width = 30
        filled = int(progress_bar_width * info['progress_percent'] / 100)
        bar = '█' * filled + '░' * (progress_bar_width - filled)
        
        print(f"\n{Fore.CYAN}{'─' * 70}{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Block {info['current_block']}/{info['total_blocks']}{Style.RESET_ALL} │ "
              f"{Fore.WHITE}Trial {info['trial_in_block']}/{info['trials_per_block']}{Style.RESET_ALL} │ "
              f"{Fore.YELLOW}Overall: {info['total_trial']}/{info['total_trials']}{Style.RESET_ALL} │ "
              f"{Fore.GREEN}[{bar}] {info['progress_percent']:.1f}%{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}Condition: {Fore.WHITE}{info['condition_letter']} - {info['condition_name']}{Style.RESET_ALL} │ "
              f"{Fore.CYAN}Block Mix: {self.latin_square.get_block_summary()}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'─' * 70}{Style.RESET_ALL}\n")
    
    def run_break(self):
        """Run inter-block break with countdown"""
        log.info(f"Starting {CONFIG.break_duration} second break...", force=True)
        
        for remaining in range(CONFIG.break_duration, 0, -1):
            if not self.running:
                return False
            
            # Update browser with countdown
            if self.app.browser_display:
                self.app.browser_display.set_break_countdown(remaining)
            
            # Update CLI (overwrite same line)
            mins = remaining // 60
            secs = remaining % 60
            print(f"\r  {Fore.YELLOW}Break: {mins:02d}:{secs:02d} remaining...{Style.RESET_ALL}    ", end='', flush=True)
            
            time.sleep(1)
        
        print(f"\r  {Fore.GREEN}Break complete!{Style.RESET_ALL}                    ")
        return True
    
    def run_single_trial(self) -> bool:
        """Run a single trial using the Latin square sequence"""
        stim_type = self.latin_square.get_current_condition()
        
        if stim_type is None:
            return False
        
        # Get progress info BEFORE the trial
        info = self.latin_square.get_progress_info()
        
        # Print progress
        self.print_progress_header()
        
        # Run the trial using existing infrastructure
        result = self.app.run_trial(stim_type)
        
        # Handle both old (bool) and new (tuple) return formats
        if isinstance(result, tuple):
            success, response_number, response_name = result
        else:
            success = result
            response_number = None
            response_name = None
        
        if success:
            # Log the response
            if response_number is not None:
                self.data_logger.log_response(
                    trial_number=info['total_trial'],
                    block_number=info['current_block'],
                    trial_in_block=info['trial_in_block'],
                    condition_letter=info['condition_letter'],
                    condition_name=info['condition_name'],
                    response_number=response_number,
                    response_name=response_name or "Unknown"
                )
            else:
                # No response recorded
                self.data_logger.log_trial_skipped(
                    trial_number=info['total_trial'],
                    block_number=info['current_block'],
                    trial_in_block=info['trial_in_block'],
                    condition_letter=info['condition_letter'],
                    condition_name=info['condition_name'],
                    reason="No response captured"
                )
            
            # Advance to next trial
            self.latin_square.advance()
        else:
            # Trial aborted
            self.data_logger.log_trial_skipped(
                trial_number=info['total_trial'],
                block_number=info['current_block'],
                trial_in_block=info['trial_in_block'],
                condition_letter=info['condition_letter'],
                condition_name=info['condition_name'],
                reason="Trial aborted"
            )
        
        return success
    
    def run_full_experiment(self) -> bool:
        """Run the complete 160-trial experiment"""
        self.running = True
        self.latin_square.reset()
        
        # Start data logging
        if not self.data_logger.start():
            log.warning("Data logging failed to start - continuing without logging", force=True)
        
        # Update executor with experiment runner reference
        if self.app.executor:
            self.app.executor.experiment_runner = self
        
        total_trials = CONFIG.total_blocks * CONFIG.trials_per_block
        
        log.success(f"Starting full experiment: {CONFIG.total_blocks} blocks × "
                   f"{CONFIG.trials_per_block} trials = {total_trials} total trials", force=True)
        
        # Show initial welcome
        if self.app.browser_display:
            self.app.browser_display.set_state("welcome")
        
        # Wait for experimenter to start
        clear_screen()
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗")
        print(f"║             {Fore.WHITE}FULL EXPERIMENT MODE{Fore.CYAN}                           ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.GREEN}Blocks: {CONFIG.total_blocks}{Fore.CYAN}                                              ║")
        print(f"║   {Fore.GREEN}Trials per block: {CONFIG.trials_per_block}{Fore.CYAN}                                  ║")
        print(f"║   {Fore.GREEN}Total trials: {total_trials}{Fore.CYAN}                                      ║")
        print(f"║   {Fore.GREEN}Break duration: {CONFIG.break_duration} seconds{Fore.CYAN}                            ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.YELLOW}Press SPACEBAR to begin experiment{Fore.CYAN}                       ║")
        print(f"║   {Fore.RED}Press ESC to cancel{Fore.CYAN}                                       ║")
        print(f"║                                                              ║")
        print(f"╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
        
        # Wait for start
        while self.running:
            try:
                event = keyboard.read_event(suppress=False)
                if event.event_type == keyboard.KEY_DOWN:
                    if event.name == 'space':
                        break
                    elif event.name == 'esc':
                        log.warning("Experiment cancelled", force=True)
                        self.running = False
                        return False
            except Exception:
                user_input = input("Press ENTER to start or 'q' to quit: ").strip().lower()
                if user_input == 'q':
                    return False
                break
        
        # Main experiment loop
        while self.running and not self.latin_square.is_experiment_complete():
            
            # Check if we need a break (between blocks)
            if self.latin_square.needs_break():
                log.info(f"Block {self.latin_square.current_block} of {CONFIG.total_blocks} starting after break", force=True)
                
                if not self.run_break():
                    break
                
                # Show block start info
                if self.app.browser_display:
                    self.app.browser_display.set_block_start(
                        self.latin_square.current_block + 1,
                        CONFIG.total_blocks,
                        CONFIG.trials_per_block
                    )
                
                # Brief pause before continuing
                time.sleep(2)
            
            # Run the trial
            success = self.run_single_trial()
            
            if not success and not self.latin_square.is_experiment_complete():
                # Trial was aborted - ask if continue
                log.warning("Trial interrupted", force=True)
                try:
                    cont = input(f"{Fore.YELLOW}Continue experiment? (y/n): {Style.RESET_ALL}").strip().lower()
                    if cont != 'y':
                        self.running = False
                        break
                except:
                    self.running = False
                    break
            
            # Small delay between trials
            time.sleep(0.3)
        
        # Experiment complete
        if self.latin_square.is_experiment_complete():
            log.success("=" * 50, force=True)
            log.success("EXPERIMENT COMPLETE!", force=True)
            log.success(f"Total trials completed: {self.latin_square.total_trial}", force=True)
            log.success("=" * 50, force=True)
            
            if self.app.browser_display:
                self.app.browser_display.set_experiment_complete(self.latin_square.total_trial)
            
            # Finalize data log - completed
            self.data_logger.end(completed=True)
        else:
            # Finalize data log - incomplete
            self.data_logger.end(completed=False)
        
        self.running = False
        return self.latin_square.is_experiment_complete()
    
    def stop(self):
        """Stop the experiment"""
        self.running = False
        
        # Save data on stop
        if self.data_logger.file_handle:
            self.data_logger.end(completed=False)


# ============================================
# LOGGING
# ============================================

class LogLevel(Enum):
    """Log levels with colors"""
    INFO = ("CYAN", "INFO")
    SUCCESS = ("GREEN", "SUCCESS")
    WARNING = ("YELLOW", "WARNING")
    ERROR = ("RED", "ERROR")
    PELTIER = ("MAGENTA", "PELTIER")
    MOTOR = ("BLUE", "MOTOR")
    TRIGGER = ("MAGENTA", "TRIGGER")
    SYSTEM = ("WHITE", "SYSTEM")


class ColoredLogger:
    """Thread-safe colored logger for console output"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._suppressed = False
    
    def suppress(self, state: bool = True):
        """Suppress logging temporarily"""
        self._suppressed = state
    
    def _get_color(self, color_name: str) -> str:
        """Get Fore color by name"""
        return getattr(Fore, color_name, Fore.WHITE)
    
    def _log(self, level: LogLevel, message: str, force: bool = False):
        """Thread-safe colored log output"""
        if self._suppressed and not force:
            return
        
        color_name, label = level.value
        color = self._get_color(color_name)
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        with self._lock:
            print(f"{Fore.WHITE}[{timestamp}] {color}[{label:^8}]{Style.RESET_ALL} {message}")
    
    def info(self, msg: str, force: bool = False):
        self._log(LogLevel.INFO, msg, force)
    
    def success(self, msg: str, force: bool = False):
        self._log(LogLevel.SUCCESS, msg, force)
    
    def warning(self, msg: str, force: bool = False):
        self._log(LogLevel.WARNING, msg, force)
    
    def error(self, msg: str, force: bool = False):
        self._log(LogLevel.ERROR, msg, force)
    
    def peltier(self, msg: str, force: bool = False):
        self._log(LogLevel.PELTIER, msg, force)
    
    def motor(self, msg: str, force: bool = False):
        self._log(LogLevel.MOTOR, msg, force)
    
    def trigger(self, msg: str, force: bool = False):
        self._log(LogLevel.TRIGGER, msg, force)
    
    def system(self, msg: str, force: bool = False):
        self._log(LogLevel.SYSTEM, msg, force)


# Global logger instance
log = ColoredLogger()


# ============================================
# UTILITY FUNCTIONS
# ============================================

def clear_screen():
    """Clear the terminal screen"""
    if sys.platform == 'win32':
        os.system('cls')
    else:
        os.system('clear')


def clear_lines(n: int = None):
    """Clear n lines above cursor"""
    if n is None:
        n = CONFIG.clear_lines
    # Move cursor up and clear lines
    for _ in range(n):
        print("\033[A\033[K", end="")


# ============================================
# PORT CACHE MANAGER
# ============================================

class PortCacheManager:
    """Manages caching of device port assignments"""
    
    def __init__(self, cache_file: str = None):
        self.cache_file = Path(cache_file or CONFIG.port_cache_file)
    
    def load(self) -> Dict[str, str]:
        """Load cached port assignments"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    log.info(f"Loaded cached ports from {self.cache_file}")
                    return data
        except Exception as e:
            log.warning(f"Failed to load port cache: {e}")
        return {}
    
    def save(self, ports: Dict[str, str]):
        """Save port assignments to cache"""
        try:
            data = {
                "peltier_port": ports.get("peltier"),
                "motor_port": ports.get("motor"),
                "timestamp": datetime.now().isoformat(),
                "version": "2.0"
            }
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            log.success(f"Port assignments cached to {self.cache_file}")
        except Exception as e:
            log.warning(f"Failed to save port cache: {e}")
    
    def clear(self):
        """Clear the port cache"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                log.info("Port cache cleared")
        except Exception as e:
            log.warning(f"Failed to clear port cache: {e}")


# ============================================
# SERIAL DEVICE CLASSES
# ============================================

class SerialDevice:
    """Base class for serial communication with Arduino devices"""
    
    def __init__(self, device_id: str, device_name: str):
        self.device_id = device_id
        self.device_name = device_name
        self.port: Optional[serial.Serial] = None
        self.port_path: Optional[str] = None
        self.connected = False
        self._read_thread: Optional[threading.Thread] = None
        self._running = False
        self._response_callback: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()
        self._suppress_logging = False
    
    def suppress_logging(self, state: bool = True):
        """Suppress response logging (e.g., during tqdm)"""
        self._suppress_logging = state
    
    def connect(self, port_path: str, baud_rate: int = None) -> bool:
        """Connect to serial port and verify device identity"""
        if baud_rate is None:
            baud_rate = CONFIG.device_baud_rate
        
        try:
            self.port = serial.Serial(
                port=port_path,
                baudrate=baud_rate,
                timeout=CONFIG.serial_timeout,
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
                self.port_path = port_path
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
                    if line and self._response_callback and not self._suppress_logging:
                        self._response_callback(line)
                time.sleep(0.01)
            except Exception:
                break
    
    def send_command(self, command: str, wait_response: bool = False) -> Optional[str]:
        """Send command to device"""
        if not self.port or not self.port.is_open:
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
        self.port_path = None


class PeltierController(SerialDevice):
    """Controller for Peltier thermoelectric device"""
    
    def __init__(self):
        super().__init__(CONFIG.peltier_id, "Peltier")
        self._response_callback = self._handle_response
    
    def _handle_response(self, response: str):
        """Handle responses from Peltier controller"""
        if not self._suppress_logging:
            log.peltier(f"Response: {response}")
    
    def set_hot(self, pwm: int = None):
        """Activate heating mode"""
        if pwm is None:
            pwm = CONFIG.pwm_value
        self.send_command(f"HOT:{pwm}")
    
    def set_cold(self, pwm: int = None):
        """Activate cooling mode"""
        if pwm is None:
            pwm = CONFIG.pwm_value
        self.send_command(f"COLD:{pwm}")
    
    def turn_off(self):
        """Turn off Peltier"""
        self.send_command("OFF")
    
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
        if not self._suppress_logging:
            log.motor(f"Response: {response}")
    
    def set_intensity(self, intensity: int = None):
        """Set global motor intensity"""
        if intensity is None:
            intensity = CONFIG.motor_intensity
        self.send_command(f"INTENSITY:{intensity}")
    
    def set_multiplier(self, motor_num: int, value: float):
        """Set multiplier for specific motor"""
        self.send_command(f"MULT:{motor_num}:{value:.2f}")
    
    def set_overlap(self, overlap: float = None):
        """Set motor overlap for smooth transitions"""
        if overlap is None:
            overlap = CONFIG.motor_overlap
        self.send_command(f"OVERLAP:{overlap:.2f}")
    
    def set_position(self, position: float):
        """Set interpolated position (0.0 to 3.0)"""
        position = max(0.0, min(3.0, position))
        self.send_command(f"POS:{position:.2f}")
    
    def stop_all(self):
        """Stop all motors"""
        self.send_command("STOP")
    
    def ping(self) -> bool:
        """Check if device is responsive"""
        response = self.send_command("PING", wait_response=True)
        return response is not None and "PONG" in response


# ============================================
# EEG TRIGGER CONTROLLER
# ============================================

class TriggerController:
    """EEG Trigger Box Controller (based on trigger_sender.py)"""
    
    def __init__(self, port: str = None):
        self.port_path = port or CONFIG.trigger_port
        self.serial: Optional[serial.Serial] = None
        self.connected = False
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        """Connect to trigger box"""
        try:
            self.serial = serial.Serial(
                port=self.port_path,
                baudrate=CONFIG.trigger_baud_rate,
                timeout=0.5,
                write_timeout=1.0
            )
            time.sleep(0.3)
            self.connected = True
            log.success(f"Trigger box connected on {self.port_path}")
            return True
        except Exception as e:
            log.error(f"Failed to connect to trigger box on {self.port_path}: {e}")
            self.connected = False
            return False
    
    def send_trigger(self, key: str) -> bool:
        """Send a trigger pulse"""
        if key not in TRIGGERS:
            log.error(f"Invalid trigger key: {key}")
            return False
        
        code, label, trigger_type = TRIGGERS[key]
        
        if not self.connected or not self.serial or not self.serial.is_open:
            log.warning("Trigger box not connected")
            return False
        
        try:
            with self._lock:
                # Send trigger code
                self.serial.write(bytes([code]))
                self.serial.flush()
                
                # Hold for pulse width
                time.sleep(CONFIG.trigger_pulse_width_ms / 1000.0)
                
                # Reset to 0
                self.serial.write(b'\x00')
                self.serial.flush()
            
            log.trigger(f"[{trigger_type}] 0x{code:02X} → {label}")
            return True
            
        except Exception as e:
            log.error(f"Failed to send trigger: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from trigger box"""
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
        self.connected = False


# ============================================
# DEVICE SCANNER
# ============================================

class DeviceScanner:
    """Scans and connects to Arduino devices with caching"""
    
    def __init__(self):
        self.cache_manager = PortCacheManager()
    
    @staticmethod
    def list_ports() -> List[str]:
        """List all available serial ports"""
        ports = list_ports.comports()
        return [p.device for p in ports]
    
    def find_and_connect(
        self, 
        peltier: PeltierController, 
        motor: MotorController
    ) -> Tuple[bool, bool]:
        """
        Scan all ports and connect to devices.
        Tries cached ports first for faster connection.
        Returns (peltier_connected, motor_connected)
        """
        # Try cached ports first
        cached = self.cache_manager.load()
        
        if cached:
            log.info("Trying cached ports first...")
            
            # Try cached Peltier port
            cached_peltier = cached.get("peltier_port")
            if cached_peltier and not peltier.connected:
                log.info(f"Trying cached Peltier port: {cached_peltier}")
                if peltier.connect(cached_peltier):
                    log.success(f"Peltier connected on cached port {cached_peltier}")
            
            # Try cached Motor port
            cached_motor = cached.get("motor_port")
            if cached_motor and not motor.connected:
                log.info(f"Trying cached Motor port: {cached_motor}")
                if motor.connect(cached_motor):
                    log.success(f"Motor connected on cached port {cached_motor}")
        
        # If both connected from cache, we're done
        if peltier.connected and motor.connected:
            log.success("Both devices connected from cache!")
            return True, True
        
        # Scan all ports for remaining devices
        ports = self.list_ports()
        
        if not ports:
            log.warning("No serial ports found")
            return peltier.connected, motor.connected
        
        log.info(f"Scanning {len(ports)} port(s): {', '.join(ports)}")
        
        for port_path in ports:
            if peltier.connected and motor.connected:
                break
            
            # Skip already connected ports
            if peltier.port_path == port_path or motor.port_path == port_path:
                continue
            
            log.info(f"Probing {port_path}...")
            
            # Try as Peltier
            if not peltier.connected:
                if peltier.connect(port_path):
                    log.success(f"Peltier found on {port_path}")
                    continue
            
            # Try as Motor
            if not motor.connected:
                if motor.connect(port_path):
                    log.success(f"Motor controller found on {port_path}")
                    continue
        
        # Save successful connections to cache
        if peltier.connected or motor.connected:
            self.cache_manager.save({
                "peltier": peltier.port_path,
                "motor": motor.port_path
            })
        
        return peltier.connected, motor.connected


# ============================================
# STIMULATION TYPES
# ============================================

class StimulationType(Enum):
    """Experimental stimulation conditions"""
    NONE = ("1", "No sensation", Fore.WHITE)
    THERMAL_ONLY = ("2", "Static Thermal", Fore.RED)
    VIBROTACTILE_ONLY = ("3", "Moving Vibrotactile", Fore.BLUE)
    THERMAL_MOTION = ("4", "Moving Thermal", Fore.MAGENTA)
    
    @property
    def trigger_key(self) -> str:
        return self.value[0]
    
    @property
    def label(self) -> str:
        return self.value[1]
    
    @property
    def color(self) -> str:
        return self.value[2]


# ============================================
# STIMULATION EXECUTOR
# ============================================

class StimulationExecutor:
    """Executes experimental stimulation protocols"""
    
    def __init__(
        self, 
        peltier: PeltierController, 
        motor: MotorController,
        experiment_runner: 'ExperimentRunner' = None
    ):
        self.peltier = peltier
        self.motor = motor
        self.experiment_runner = experiment_runner
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
        time.sleep(0.03)
        
        for i, mult in enumerate(CONFIG.multipliers):
            self.motor.set_multiplier(i, mult)
            time.sleep(0.02)
        
        self.motor.set_overlap(CONFIG.motor_overlap)
        time.sleep(0.03)
    
    def _get_thermal_command(self) -> str:
        """Get the appropriate thermal command based on polarity setting"""
        return "HOT" if CONFIG.swap_polarity else "COLD"
    
    def _suppress_device_logging(self, state: bool):
        """Suppress device response logging during tqdm"""
        self.peltier.suppress_logging(state)
        self.motor.suppress_logging(state)
        log.suppress(state)
    
    def execute_no_stimulation(self) -> bool:
        """Execute No Stimulation condition"""
        total_duration = CONFIG.total_duration
        
        try:
            self._suppress_device_logging(True)
            
            with tqdm(
                total=100, 
                desc=f"{Fore.WHITE}No Stimulation{Style.RESET_ALL}",
                bar_format='{l_bar}{bar}| {n:.0f}% [{elapsed}<{remaining}]',
                colour='white',
                leave=False
            ) as pbar:
                
                start_time = time.time()
                last_progress = 0
                
                while True:
                    if self._check_abort():
                        return False
                    
                    elapsed = time.time() - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.02)
            
            # Show progress footer
            if self.experiment_runner:
                self.experiment_runner.print_progress_footer()
            
            return True
            
        finally:
            self._suppress_device_logging(False)
    
    def execute_thermal_only(self) -> bool:
        """Execute Thermal Only condition"""
        total_duration = CONFIG.total_duration
        
        try:
            self._suppress_device_logging(True)
            
            # Turn on Peltier
            thermal_cmd = self._get_thermal_command()
            if thermal_cmd == "HOT":
                self.peltier.set_hot(CONFIG.pwm_value)
            else:
                self.peltier.set_cold(CONFIG.pwm_value)
            
            with tqdm(
                total=100,
                desc=f"{Fore.RED}Thermal Only{Style.RESET_ALL}",
                bar_format='{l_bar}{bar}| {n:.0f}% [{elapsed}<{remaining}]',
                colour='red',
                leave=False
            ) as pbar:
                
                start_time = time.time()
                last_progress = 0
                
                while True:
                    if self._check_abort():
                        self.peltier.turn_off()
                        return False
                    
                    elapsed = time.time() - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.02)
            
            self.peltier.turn_off()
            
            # Show progress footer
            if self.experiment_runner:
                self.experiment_runner.print_progress_footer()
            
            return True
            
        finally:
            self._suppress_device_logging(False)
            self.peltier.turn_off()
    
    def execute_vibrotactile_only(self) -> bool:
        """Execute Vibrotactile Only condition"""
        total_duration = CONFIG.total_duration
        step_interval = 1.0 / CONFIG.step_resolution
        
        try:
            self._suppress_device_logging(True)
            self._setup_motors()
            
            with tqdm(
                total=100,
                desc=f"{Fore.BLUE}Vibrotactile{Style.RESET_ALL}",
                bar_format='{l_bar}{bar}| {n:.0f}% [{elapsed}<{remaining}]',
                colour='blue',
                leave=False
            ) as pbar:
                
                start_time = time.time()
                last_progress = 0
                last_step_time = 0
                
                while True:
                    if self._check_abort():
                        self.motor.stop_all()
                        return False
                    
                    current_time = time.time()
                    elapsed = current_time - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    if current_time - last_step_time >= step_interval:
                        if elapsed < CONFIG.warmup_time:
                            self.motor.set_position(0.0)
                        else:
                            stroke_elapsed = elapsed - CONFIG.warmup_time
                            stroke_progress = min(stroke_elapsed / CONFIG.stroke_duration, 1.0)
                            position = stroke_progress * 3.0
                            self.motor.set_position(position)
                        
                        last_step_time = current_time
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.01)
            
            self.motor.stop_all()
            
            # Show progress footer
            if self.experiment_runner:
                self.experiment_runner.print_progress_footer()
            
            return True
            
        finally:
            self._suppress_device_logging(False)
            self.motor.stop_all()
    
    def execute_thermal_motion(self) -> bool:
        """Execute Thermal Motion (combined) condition"""
        total_duration = CONFIG.total_duration
        step_interval = 1.0 / CONFIG.step_resolution
        
        try:
            self._suppress_device_logging(True)
            self._setup_motors()
            
            # Turn on Peltier
            thermal_cmd = self._get_thermal_command()
            if thermal_cmd == "HOT":
                self.peltier.set_hot(CONFIG.pwm_value)
            else:
                self.peltier.set_cold(CONFIG.pwm_value)
            
            with tqdm(
                total=100,
                desc=f"{Fore.MAGENTA}Thermal Motion{Style.RESET_ALL}",
                bar_format='{l_bar}{bar}| {n:.0f}% [{elapsed}<{remaining}]',
                colour='magenta',
                leave=False
            ) as pbar:
                
                start_time = time.time()
                last_progress = 0
                last_step_time = 0
                
                while True:
                    if self._check_abort():
                        self.peltier.turn_off()
                        self.motor.stop_all()
                        return False
                    
                    current_time = time.time()
                    elapsed = current_time - start_time
                    progress = min((elapsed / total_duration) * 100, 100)
                    
                    delta = progress - last_progress
                    if delta > 0:
                        pbar.update(delta)
                        last_progress = progress
                    
                    if current_time - last_step_time >= step_interval:
                        if elapsed < CONFIG.warmup_time:
                            self.motor.set_position(0.0)
                        else:
                            stroke_elapsed = elapsed - CONFIG.warmup_time
                            stroke_progress = min(stroke_elapsed / CONFIG.stroke_duration, 1.0)
                            position = stroke_progress * 3.0
                            self.motor.set_position(position)
                        
                        last_step_time = current_time
                    
                    if elapsed >= total_duration:
                        break
                    
                    time.sleep(0.01)
            
            self.peltier.turn_off()
            self.motor.stop_all()
            
            # Show progress footer
            if self.experiment_runner:
                self.experiment_runner.print_progress_footer()
            
            return True
            
        finally:
            self._suppress_device_logging(False)
            self.peltier.turn_off()
            self.motor.stop_all()
    
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
            self.peltier.turn_off()
        except Exception:
            pass
        try:
            self.motor.stop_all()
        except Exception:
            pass


# ============================================
# MAIN APPLICATION
# ============================================

class ThermalMotionCLI:
    """Main CLI application"""
    
    def __init__(self):
        self.peltier = PeltierController()
        self.motor = MotorController()
        self.trigger: Optional[TriggerController] = None
        self.executor: Optional[StimulationExecutor] = None
        self.sound = SoundPlayer()
        self.scanner = DeviceScanner()
        self.browser_display: Optional[BrowserDisplayManager] = None
        self.experiment_runner: Optional[ExperimentRunner] = None
        
        self.running = True
        self.experiment_mode = False  # True = with triggers, False = debug mode
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        atexit.register(self.shutdown)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals"""
        print()
        log.warning("Interrupt received, shutting down...", force=True)
        self.shutdown()
        sys.exit(0)
    
    def print_banner(self):
        """Print application banner"""
        clear_screen()
        banner = f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║   {Fore.WHITE}████████╗██╗  ██╗███████╗██████╗ ███╗   ███╗ █████╗ ██╗{Fore.CYAN}             ║
║   {Fore.WHITE}╚══██╔══╝██║  ██║██╔════╝██╔══██╗████╗ ████║██╔══██╗██║{Fore.CYAN}             ║
║   {Fore.WHITE}   ██║   ███████║█████╗  ██████╔╝██╔████╔██║███████║██║{Fore.CYAN}             ║
║   {Fore.WHITE}   ██║   ██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══██║██║{Fore.CYAN}             ║
║   {Fore.WHITE}   ██║   ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║██║  ██║███████╗{Fore.CYAN}        ║
║   {Fore.WHITE}   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝{Fore.CYAN}        ║
║                                                                       ║
║        {Fore.YELLOW}███╗   ███╗ ██████╗ ████████╗██╗ ██████╗ ███╗   ██╗{Fore.CYAN}            ║
║        {Fore.YELLOW}████╗ ████║██╔═══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║{Fore.CYAN}            ║
║        {Fore.YELLOW}██╔████╔██║██║   ██║   ██║   ██║██║   ██║██╔██╗ ██║{Fore.CYAN}            ║
║        {Fore.YELLOW}██║╚██╔╝██║██║   ██║   ██║   ██║██║   ██║██║╚██╗██║{Fore.CYAN}            ║
║        {Fore.YELLOW}██║ ╚═╝ ██║╚██████╔╝   ██║   ██║╚██████╔╝██║ ╚████║{Fore.CYAN}            ║
║        {Fore.YELLOW}╚═╝     ╚═╝ ╚═════╝    ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝{Fore.CYAN}            ║
║                                                                       ║
║                    {Fore.GREEN}Command Line Controller v2.0{Fore.CYAN}                      ║
║                                                                       ║
║               {Fore.WHITE}Author: Pi Ko (pi.ko@nyu.edu){Fore.CYAN}                         ║
║               {Fore.WHITE}AIMLAB - NYU Abu Dhabi{Fore.CYAN}                                ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}"""
        print(banner)
    
    def print_config(self):
        """Print current configuration"""
        print(f"\n{Fore.CYAN}{'═' * 60}")
        print(f"{Fore.WHITE}  CONFIGURATION")
        print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}")
        print(f"  Peltier PWM:       {CONFIG.pwm_value}")
        print(f"  Swap Polarity:     {CONFIG.swap_polarity}")
        print(f"  Motor Intensity:   {CONFIG.motor_intensity}")
        print(f"  Motor Overlap:     {CONFIG.motor_overlap}")
        print(f"  Multipliers:       {CONFIG.multipliers}")
        print(f"  Warmup Time:       {CONFIG.warmup_time}s")
        print(f"  Stroke Duration:   {CONFIG.stroke_duration}s")
        print(f"  {Fore.GREEN}Total Duration:    {CONFIG.total_duration}s{Style.RESET_ALL}")
        print(f"  Fixation Range:    {CONFIG.fixation_min}s - {CONFIG.fixation_max}s")
        print(f"  Step Resolution:   {CONFIG.step_resolution}/sec")
        print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}\n")
    
    def print_device_status(self):
        """Print device connection status"""
        print(f"\n{Fore.CYAN}{'═' * 60}")
        print(f"{Fore.WHITE}  DEVICE STATUS")
        print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}")
        
        # Peltier status
        if self.peltier.connected:
            print(f"  Peltier:    {Fore.GREEN}✓ Connected ({self.peltier.port_path}){Style.RESET_ALL}")
        else:
            print(f"  Peltier:    {Fore.RED}✗ Not Connected{Style.RESET_ALL}")
        
        # Motor status
        if self.motor.connected:
            print(f"  Motors:     {Fore.GREEN}✓ Connected ({self.motor.port_path}){Style.RESET_ALL}")
        else:
            print(f"  Motors:     {Fore.RED}✗ Not Connected{Style.RESET_ALL}")
        
        # Trigger status (only in experiment mode)
        if self.experiment_mode:
            if self.trigger and self.trigger.connected:
                print(f"  Triggers:   {Fore.GREEN}✓ Connected ({self.trigger.port_path}){Style.RESET_ALL}")
            else:
                print(f"  Triggers:   {Fore.RED}✗ Not Connected{Style.RESET_ALL}")
        else:
            print(f"  Triggers:   {Fore.YELLOW}○ Debug Mode (disabled){Style.RESET_ALL}")
        
        # Sound status
        if self.sound.sounds_available:
            print(f"  Sounds:     {Fore.GREEN}✓ Available{Style.RESET_ALL}")
        else:
            print(f"  Sounds:     {Fore.YELLOW}○ Not Found (check Downloads folder){Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}\n")
    
    def select_mode(self) -> Optional[str]:
        """Let user select experiment mode. Returns 'full', 'single', 'debug', or None"""
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗")
        print(f"║                    {Fore.WHITE}SELECT MODE{Fore.CYAN}                               ║")
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║                                                              ║")
        print(f"║   {Fore.GREEN}[1]  FULL EXPERIMENT MODE{Fore.CYAN}                                 ║")
        print(f"║        - 160 trials (5 blocks × 32 trials)                   ║")
        print(f"║        - Latin square counterbalanced design                 ║")
        print(f"║        - EEG triggers, audio cues, breaks                    ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.YELLOW}[2]  SINGLE TRIAL MODE{Fore.CYAN}                                    ║")
        print(f"║        - Manual condition selection                          ║")
        print(f"║        - EEG triggers enabled                                ║")
        print(f"║        - Good for testing specific conditions                ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.BLUE}[3]  DEBUG MODE{Fore.CYAN}                                           ║")
        print(f"║        - No triggers, no audio                               ║")
        print(f"║        - Direct stimulation testing                          ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.RED}[Q]  QUIT{Fore.CYAN}                                                 ║")
        print(f"║                                                              ║")
        print(f"╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        print()
        
        while True:
            try:
                choice = input(f"{Fore.GREEN}Select mode (1/2/3/Q): {Style.RESET_ALL}").strip().upper()
                
                if choice == '1':
                    self.experiment_mode = True
                    log.success("Full experiment mode selected")
                    return 'full'
                elif choice == '2':
                    self.experiment_mode = True
                    log.success("Single trial mode selected")
                    return 'single'
                elif choice == '3':
                    self.experiment_mode = False
                    log.success("Debug mode selected")
                    return 'debug'
                elif choice == 'Q':
                    return None
                else:
                    log.warning("Invalid choice. Enter 1, 2, 3, or Q.")
            except (EOFError, KeyboardInterrupt):
                return None
    
    def connect_devices(self) -> bool:
        """Scan and connect to all devices"""
        print(f"\n{Fore.CYAN}Scanning for devices...{Style.RESET_ALL}\n")
        
        peltier_ok, motor_ok = self.scanner.find_and_connect(self.peltier, self.motor)
        
        # Connect trigger box in experiment mode
        if self.experiment_mode:
            self.trigger = TriggerController(CONFIG.trigger_port)
            self.trigger.connect()
            
            # Start browser display
            self.browser_display = BrowserDisplayManager()
            self.browser_display.start()
            self.browser_display.set_state("welcome")
        
        # Create executor
        self.executor = StimulationExecutor(self.peltier, self.motor, self.experiment_runner)
        
        self.print_device_status()
        
        if peltier_ok and motor_ok:
            log.success("All stimulation devices connected!")
        else:
            log.warning("Some devices missing. Continuing anyway...")
        
        return True
    
    def show_fixation(self) -> float:
        """
        Show fixation cross for randomized duration.
        Returns the actual duration used.
        """
        duration = random.uniform(CONFIG.fixation_min, CONFIG.fixation_max)
        
        # Update browser display
        if self.browser_display:
            self.browser_display.set_state("fixation")
        
        clear_screen()
        
        # Calculate vertical centering (approximately)
        print("\n" * 8)
        print(f"{Fore.WHITE}")
        print("                              ████                              ")
        print("                              ████                              ")
        print("                              ████                              ")
        print("                    ██████████████████████████                  ")
        print("                    ██████████████████████████                  ")
        print("                              ████                              ")
        print("                              ████                              ")
        print("                              ████                              ")
        print(f"{Style.RESET_ALL}")
        
        time.sleep(duration)
        
        return duration
    
    def show_question(self) -> Optional[str]:
        """
        Show response question and collect user answer.
        Returns the trigger key (5-9) or None if cancelled.
        Primarily relies on BROWSER for input.
        """
        clear_screen()
        
        # IMPORTANT: Clear any pending keypresses BEFORE showing question
        if self.browser_display:
            # Clear browser keypress buffer
            self.browser_display.get_keypress()  # Discard any stale keypress
            self.browser_display.get_keypress()  # Double clear to be safe
        
        # Clear keyboard buffer (consume any pending events)
        try:
            timeout_time = time.time() + 0.05  # Clear for 50ms
            while time.time() < timeout_time:
                try:
                    keyboard.read_event(suppress=False, timeout=0.01)
                except:
                    break
        except:
            pass
        
        # Small delay to let things settle and prevent accidental input
        time.sleep(0.2)
        
        # NOW set browser to question state (after clearing buffers)
        if self.browser_display:
            self.browser_display.set_state("question_options")
        
        print(f"\n\n")
        print(f"{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗")
        print(f"║     {Fore.WHITE}Which sensation did you experience?{Fore.CYAN}                    ║")
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║   {Fore.WHITE}[1]{Fore.CYAN} No sensation                                          ║")
        print(f"║   {Fore.RED}[2]{Fore.CYAN} Static Thermal                                        ║")
        print(f"║   {Fore.BLUE}[3]{Fore.CYAN} Moving Vibrotactile                                   ║")
        print(f"║   {Fore.MAGENTA}[4]{Fore.CYAN} Moving Thermal                                        ║")
        print(f"║   {Fore.YELLOW}[5]{Fore.CYAN} I'm not sure                                          ║")
        print(f"╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        
        # Show experiment progress
        if hasattr(self, 'experiment_runner') and self.experiment_runner:
            print(f"\n{Fore.CYAN}{'─' * 65}{Style.RESET_ALL}")
            print(self.experiment_runner.get_progress_line())
            print(f"{Fore.CYAN}{'─' * 65}{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}Waiting for response on participant display...{Style.RESET_ALL}")
        
        # Map keys to trigger codes
        key_map = {'1': '5', '2': '6', '3': '7', '4': '8', '5': '9'}
        
        # Clear browser buffer one more time right before listening
        if self.browser_display:
            self.browser_display.get_keypress()
        
        # Minimum wait time before accepting response (prevents accidental skips)
        min_wait_time = 0.3  # 300ms minimum
        start_time = time.time()
        
        # Primary: Check BROWSER for keypress (participant display)
        while self.running:
            elapsed = time.time() - start_time
            
            # Check browser keypress (primary input method)
            if self.browser_display:
                browser_key = self.browser_display.get_keypress()
                if browser_key and browser_key in key_map:
                    # Only accept if minimum wait time has passed
                    if elapsed >= min_wait_time:
                        log.info(f"Response from display: {browser_key}", force=True)
                        return key_map[browser_key]
                    else:
                        # Ignore early keypress (likely stale)
                        log.warning(f"Ignored early keypress: {browser_key} (too fast - {elapsed:.2f}s)", force=True)
            
            # Fallback: Check terminal keyboard (experimenter override)
            try:
                if elapsed >= min_wait_time:  # Also apply minimum wait to keyboard
                    if keyboard.is_pressed('1'): 
                        time.sleep(0.1)  # Debounce
                        return '5'
                    if keyboard.is_pressed('2'): 
                        time.sleep(0.1)
                        return '6'
                    if keyboard.is_pressed('3'): 
                        time.sleep(0.1)
                        return '7'
                    if keyboard.is_pressed('4'): 
                        time.sleep(0.1)
                        return '8'
                    if keyboard.is_pressed('5'): 
                        time.sleep(0.1)
                        return '9'
                if keyboard.is_pressed('esc'): 
                    return None
            except:
                pass
            
            time.sleep(0.05)
        
        return None
    
    def run_trial(self, stim_type: StimulationType):
        """
        Run a complete trial with the specified stimulation type.
        In experiment mode: fixation → trigger → stim → question → response trigger
        In debug mode: just run the stimulation
        """
        if self.experiment_mode:
            # === EXPERIMENT MODE ===
            
            # 1. Play 500Hz tone (trial start)
            self.sound.play_500hz()
            
            # Trigger is after fixation
            
            # 3. Show fixation cross (randomized duration)
            fixation_time = self.show_fixation()
            log.info(f"Fixation: {fixation_time:.2f}s", force=True)
            
            # 4. Set browser to blank immediately (before sound)
            if self.browser_display:
                self.browser_display.set_state("blank")
            
            # 5. Play 1000Hz tone (stimulation start)
            self.sound.play_1000hz()
            # 2. Send FIXATION trigger (experiment type) - at fixation start
            if self.trigger and self.trigger.connected:
                self.trigger.send_trigger(stim_type.trigger_key)
            
            # 6. Execute stimulation
            clear_screen()
            print(f"\n{Fore.CYAN}{'═' * 60}")
            print(f"{Fore.WHITE}  STIMULATION: {stim_type.color}{stim_type.label}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}")
            
            # Show experiment progress before stimulation
            if hasattr(self, 'experiment_runner') and self.experiment_runner:
                info = self.experiment_runner.latin_square.get_progress_info()
                print(f"  {Fore.CYAN}Block {info['current_block']}/{info['total_blocks']} │ "
                      f"Trial {info['trial_in_block']}/{info['trials_per_block']} │ "
                      f"Overall: {info['total_trial']}/{info['total_trials']} │ "
                      f"{info['progress_percent']:.1f}%{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
            
            print()
            
            success = self.executor.execute(stim_type)
            
            if not success:
                log.warning("Trial aborted", force=True)
                return False, None, None
            
            # 7. Play 500Hz tone (question prompt)
            self.sound.play_500hz()
            
            # 8. Show question and get response
            response_key = self.show_question()
            
            if response_key:
                # 9. Send response trigger
                if self.trigger and self.trigger.connected:
                    self.trigger.send_trigger(response_key)
                
                _, label, _ = TRIGGERS[response_key]
                log.success(f"Response recorded: {label}", force=True)
                
                # Return response info for logging
                # Map response_key to response number (5->1, 6->2, 7->3, 8->4, 9->5)
                response_number = int(response_key) - 4  # '5'->1, '6'->2, etc.
                return True, response_number, label
            else:
                log.warning("No response recorded", force=True)
            
            return True, None, None
            
        else:
            # === DEBUG MODE ===
            clear_screen()
            print(f"\n\n{Fore.CYAN}{'═' * 60}")
            print(f"{Fore.WHITE}  DEBUG: {stim_type.color}{stim_type.label}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}\n")
            
            success = self.executor.execute(stim_type)
            
            if success:
                log.success(f"Completed: {stim_type.label}", force=True)
                return True, None, None
            else:
                log.warning("Aborted", force=True)
                return False, None, None
            
            time.sleep(0.5)
    
    def show_stimulation_menu(self) -> Optional[StimulationType]:
        """Display stimulation selection menu"""
        clear_screen()
        
        mode_str = f"{Fore.GREEN}EXPERIMENT{Style.RESET_ALL}" if self.experiment_mode else f"{Fore.YELLOW}DEBUG{Style.RESET_ALL}"
        
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗")
        print(f"║         {Fore.WHITE}SELECT STIMULATION CONDITION{Fore.CYAN}                       ║")
        print(f"║                 Mode: {mode_str}{Fore.CYAN}                              ║")
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║                                                              ║")
        print(f"║   {Fore.WHITE}[1]  No sensation{Fore.CYAN}                                       ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.RED}[2]  Static Thermal{Fore.CYAN}                                     ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.BLUE}[3]  Moving Vibrotactile{Fore.CYAN}                                ║")
        print(f"║                                                              ║")
        print(f"║   {Fore.MAGENTA}[4]  Moving Thermal{Fore.CYAN}                                     ║")
        print(f"║                                                              ║")
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║   {Fore.YELLOW}[M]  Change Mode{Fore.CYAN}                                        ║")
        print(f"║   {Fore.YELLOW}[R]  Reconnect Devices{Fore.CYAN}                                  ║")
        print(f"║   {Fore.YELLOW}[C]  Show Configuration{Fore.CYAN}                                 ║")
        print(f"║   {Fore.YELLOW}[S]  Show Device Status{Fore.CYAN}                                 ║")
        print(f"║   {Fore.RED}[Q]  Quit{Fore.CYAN}                                               ║")
        print(f"║                                                              ║")
        print(f"╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        print()
        
        while True:
            try:
                choice = input(f"{Fore.GREEN}Enter choice (1-4, M/R/C/S/Q): {Style.RESET_ALL}").strip().upper()
                
                if choice == '1':
                    return StimulationType.NONE
                elif choice == '2':
                    return StimulationType.THERMAL_ONLY
                elif choice == '3':
                    return StimulationType.VIBROTACTILE_ONLY
                elif choice == '4':
                    return StimulationType.THERMAL_MOTION
                elif choice == 'M':
                    # Change mode
                    if self.select_mode():
                        if self.experiment_mode and (not self.trigger or not self.trigger.connected):
                            self.trigger = TriggerController(CONFIG.trigger_port)
                            self.trigger.connect()
                    return self.show_stimulation_menu()
                elif choice == 'R':
                    self.connect_devices()
                    return self.show_stimulation_menu()
                elif choice == 'C':
                    self.print_config()
                    input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
                    return self.show_stimulation_menu()
                elif choice == 'S':
                    self.print_device_status()
                    input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
                    return self.show_stimulation_menu()
                elif choice == 'Q':
                    return None
                else:
                    log.warning("Invalid choice. Enter 1-4, M, R, C, S, or Q.")
            except (EOFError, KeyboardInterrupt):
                return None
    
    def wait_for_spacebar(self) -> bool:
        """Wait for spacebar press"""
        clear_screen()
        
        # Reset browser to welcome
        if self.browser_display:
            self.browser_display.set_state("welcome")
        
        mode_str = f"{Fore.GREEN}EXPERIMENT MODE{Style.RESET_ALL}" if self.experiment_mode else f"{Fore.YELLOW}DEBUG MODE{Style.RESET_ALL}"
        
        print(f"\n\n\n")
        print(f"{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗")
        print(f"║                                                              ║")
        print(f"║               {Fore.WHITE}THERMAL MOTION CONTROLLER{Fore.CYAN}                     ║")
        print(f"║                                                              ║")
        print(f"║                    Current: {mode_str}{Fore.CYAN}                    ║")
        print(f"║                                                              ║")
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║                                                              ║")
        print(f"║        Press {Fore.WHITE}[SPACEBAR]{Fore.CYAN} to open experiment menu          ║")
        print(f"║                                                              ║")
        print(f"║        Press {Fore.YELLOW}[ESC]{Fore.CYAN} to quit                                ║")
        print(f"║                                                              ║")
        print(f"╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        print()
        
        # Device status summary
        peltier_status = f"{Fore.GREEN}●{Style.RESET_ALL}" if self.peltier.connected else f"{Fore.RED}○{Style.RESET_ALL}"
        motor_status = f"{Fore.GREEN}●{Style.RESET_ALL}" if self.motor.connected else f"{Fore.RED}○{Style.RESET_ALL}"
        
        trigger_status = f"{Fore.YELLOW}○{Style.RESET_ALL}"
        if self.experiment_mode:
            trigger_status = f"{Fore.GREEN}●{Style.RESET_ALL}" if (self.trigger and self.trigger.connected) else f"{Fore.RED}○{Style.RESET_ALL}"
        
        print(f"  {peltier_status} Peltier    {motor_status} Motors    {trigger_status} Triggers")
        print()
        
        while self.running:
            try:
                event = keyboard.read_event(suppress=False)
                if event.event_type == keyboard.KEY_DOWN:
                    if event.name == 'space':
                        return True
                    elif event.name == 'esc':
                        return False
            except Exception as e:
                log.warning(f"Keyboard hook failed: {e}", force=True)
                log.info("Press ENTER to continue or 'q' to quit:", force=True)
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
            
            # Select mode
            mode = self.select_mode()
            if mode is None:
                log.info("Goodbye!")
                return
            
            # Connect devices
            if not self.connect_devices():
                log.error("Failed to initialize. Exiting.")
                return
            
            log.success("System ready!")
            time.sleep(1)
            
            # Run based on mode
            if mode == 'full':
                # Full experiment with Latin square
                self.experiment_runner = ExperimentRunner(self)
                self.experiment_runner.run_full_experiment()
                
            elif mode == 'single':
                # Single trial mode (original experiment mode behavior)
                while self.running:
                    if not self.wait_for_spacebar():
                        break
                    
                    stim_type = self.show_stimulation_menu()
                    
                    if stim_type is None:
                        break
                    
                    self.run_trial(stim_type)
                    time.sleep(0.5)
                    
            else:
                # Debug mode (original debug behavior)
                while self.running:
                    if not self.wait_for_spacebar():
                        break
                    
                    stim_type = self.show_stimulation_menu()
                    
                    if stim_type is None:
                        break
                    
                    self.run_trial(stim_type)
                    time.sleep(0.5)
        
        except Exception as e:
            log.error(f"Unexpected error: {e}", force=True)
            import traceback
            traceback.print_exc()
        
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown of all resources"""
        self.running = False
        
        # Stop experiment runner
        if self.experiment_runner:
            self.experiment_runner.stop()
        
        log.info("Shutting down...", force=True)
        
        # Stop browser display
        if self.browser_display:
            self.browser_display.set_state("thankyou")
            time.sleep(1)  # Show thank you briefly
            self.browser_display.stop()
        
        # Emergency stop
        if self.executor:
            self.executor.emergency_stop()
        
        # Disconnect Peltier
        if self.peltier.connected:
            try:
                self.peltier.turn_off()
            except Exception:
                pass
            self.peltier.disconnect()
        
        # Disconnect Motors
        if self.motor.connected:
            try:
                self.motor.stop_all()
            except Exception:
                pass
            self.motor.disconnect()
        
        # Disconnect Triggers
        if self.trigger:
            self.trigger.disconnect()
        
        log.success("Shutdown complete. Goodbye!", force=True)


# ============================================
# ENTRY POINT
# ============================================

def main():
    """Application entry point"""
    app = ThermalMotionCLI()
    app.run()


if __name__ == "__main__":
    main()

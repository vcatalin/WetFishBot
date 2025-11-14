"""
WetFishBot v1.0.0 - OpenCV Edition
Automated fishing bot for World of Warcraft Classic
Detects bobbers using computer vision and audio cues
"""

import time
import os
import sys
import json
import tempfile
import subprocess

import numpy as np
import cv2
import soundcard as sc
import pyautogui
from PIL import Image
from pynput import keyboard as pynput_keyboard


# =============================================================================
# GLOBAL CONFIGURATION
# =============================================================================

# Flag for ESC key interruption
esc_pressed = False

# Game-specific timing configurations (in seconds)
GAME_TIMERS = {
    'era': 27,      # Era/SoD bobber timeout
    'wotlk': 12     # WotLK bobber timeout
}

# Audio detection settings
AUDIO_SAMPLE_RATE = 48000
AUDIO_THRESHOLD = 0.06  # Peak threshold for bite detection

# Lure application timing
LURE_COOLDOWN = 10 * 60   # 10 minutes in seconds
LURE_POST_WAIT = 5.1      # Wait time after applying lure
last_lure_time = None     # Timestamp of the last lure application

# Template matching settings
BOBBER_MATCH_THRESHOLD = 0.6  # Confidence threshold for bobber detection

# Global variables set during initialization
BOBBER_TEMPLATES_CV = []  # Preloaded OpenCV templates
BOBBER_REGION = None      # Screen region to search for bobber
wait_timer = None         # Game-specific wait timer
castingkey = None         # Key to cast fishing line
lurekey = None         # Macro key to apply lure
input_device = None       # Audio device selection


# =============================================================================
# KEYBOARD INPUT HANDLER
# =============================================================================

def on_press(key):
    """
    Handle keyboard press events.
    Sets global flag when ESC is pressed to exit the program.
    
    Args:
        key: The key that was pressed
    """
    global esc_pressed
    try:
        if key == pynput_keyboard.Key.esc:
            esc_pressed = True
            print("\n<< ESC pressed - Exiting soon... >>")
    except Exception:
        pass


# =============================================================================
# FISHING ACTIONS
# =============================================================================

def cast_line():
    """
    Simulate pressing the fishing cast key with randomized timing.
    Adds human-like variability to keypress duration.
    """
    # Random delay before casting
    time.sleep(np.random.uniform(0.3, 0.55))
    
    # Press and hold the cast key
    pyautogui.keyDown(f'{castingkey}')
    time.sleep(np.random.uniform(0.1, 0.3))
    pyautogui.keyUp(f'{castingkey}')
    

def find_bob():
    """
    Search for the fishing bobber in the defined screen region using template matching.
    Uses OpenCV's matchTemplate to find the bobber with the highest confidence.
    
    Sets global bob_found flag to True if bobber is detected.
    Moves mouse cursor to bobber location if found.
    """
    global bob_found
    bob_found = False

    # Check for exit signal
    if esc_pressed:
        print("<< Exiting >>")
        exit()

    # Capture the screen region
    try:
        time.sleep(np.random.uniform(0.3, 0.6))
        screenshot = pyautogui.screenshot(region=BOBBER_REGION)
        screenshot_np = np.array(screenshot)
        screenshot_gray = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2GRAY)
    except Exception as e:
        print(f"Error capturing screen region. Check region coordinates. {e}")
        time.sleep(1)
        return

    # Search through all preloaded templates
    best_match = None
    best_val = 0
    
    for template in BOBBER_TEMPLATES_CV:
        try:
            # Perform template matching using normalized correlation
            result = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # Update best match if this template has higher confidence
            if max_val > BOBBER_MATCH_THRESHOLD and max_val > best_val:
                best_val = max_val
                best_match = (max_loc, template.shape)
        except Exception as e:
            print(f"Error matching template: {e}")
            continue

    # Process the best match if found
    if best_match:
        loc, (h, w) = best_match
        
        # Convert relative coordinates to absolute screen coordinates
        abs_x = BOBBER_REGION[0] + loc[0]
        abs_y = BOBBER_REGION[1] + loc[1]

        print(f'Found the bobber at (absolute): ({abs_x}, {abs_y}) - Confidence: {best_val:.2f}')
        
        # Calculate center of bobber with small random offset for naturalness
        screen_loc_offset = (
            abs_x + w // 2 + np.random.uniform(-3, 3),
            abs_y + h // 2 + np.random.uniform(-3, 3)
        )
        
        # Move mouse to bobber location with easing
        print(f"<< Found Bob! Moving cursor... >>")
        pyautogui.moveTo(
            screen_loc_offset[0], 
            screen_loc_offset[1], 
            np.random.uniform(0.1, 0.25), 
            pyautogui.easeOutQuad
        )
        
        bob_found = True
        return
    
    print("<< Bobber not found in region. >>")


def reel_in():
    """
    Monitor audio for the fishing bite sound and reel in when detected.
    Continuously records audio and checks for peaks above threshold.
    
    Sets global reeled flag to True if successfully reeled in.
    Times out after wait_timer seconds if no bite detected.
    """
    global reeled
    reeled = False
    seconds_timer = 0
    
    # Initialize the appropriate audio device
    mic = get_audio_device()
    if mic is None:
        return
    
    # Monitor audio until bite detected or timeout
    while True:
        # Check for exit signal
        if esc_pressed:
            print("<< Exiting >>")
            exit()
            
        try:
            # Record 1 second of audio
            data = mic.record(samplerate=AUDIO_SAMPLE_RATE, numframes=AUDIO_SAMPLE_RATE)
            audio_peak = np.max(abs(data))
            seconds_timer += 1

            # Check if audio peak indicates a bite
            if audio_peak > AUDIO_THRESHOLD: 
                print("<< You (hopefully) caught something! >>\n")
                
                # Right-click to reel in
                pyautogui.mouseDown(button='right')
                time.sleep(np.random.uniform(0.03, 0.08))
                pyautogui.mouseUp(button='right')
                
                # Wait for bobber animation to complete
                time.sleep(np.random.uniform(1.8, 2.2))
                reeled = True
                break
            
            # Timeout if no bite detected
            if seconds_timer > wait_timer:
                print("<< Failed. Trying again. >>")
                break
                
        except Exception as e:
            print(f"Error during audio recording: {e}")
            break


# =============================================================================
# AUDIO DEVICE MANAGEMENT
# =============================================================================

def get_audio_device():
    """
    Initialize and return the selected audio input device.
    
    Returns:
        Microphone object if successful, None if error occurs
    """
    try:
        if input_device == '1':
            print("<< WARNING: Monitoring Default Speakers is not supported on macOS. >>")
            print("<< Listening to DEFAULT MICROPHONE instead. >>")
            return sc.default_microphone()
            
        elif input_device == '2':
            print("<< Monitoring 'VoiceMeeter Input' microphone... >>")
            return sc.get_microphone('VoiceMeeter Input')
            
        elif input_device == '3':
            print("<< Monitoring 'BlackHole' microphone... >>")
            return sc.get_microphone('BlackHole')
            
        else:
            print("<< Invalid audio device selected. Exiting. >>")
            exit()
            
    except Exception as e:
        print(f"\n--- !! Audio Device Error !! ---")
        print(f"Could not find the microphone for your selection (input_device='{input_device}').")
        print(f"Make sure the required audio device is installed and working.")
        print("Available microphones are:")
        try:
            print([m.name for m in sc.all_microphones(include_loopback=False)])
        except Exception:
            print("Could not list microphones.")
        print(f"Details: {e}\n")
        return None


# =============================================================================
# REGION SELECTION GUI
# =============================================================================

def get_region_with_gui():
    """
    Launch a separate process with a GUI to let user select screen region.
    User clicks and drags to define the rectangular area to search for bobber.
    
    Returns:
        Tuple of (left, top, width, height) if successful, None otherwise
    """
    print("\nStarting region selection tool in separate process...")
    print("Please click and drag to define your search area.")
    print("Press ESC to cancel.\n")
    
    # Create temporary file to store result
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    temp_path = temp_file.name
    temp_file.close()
    
    # Create the region selector script
    selector_script = create_selector_script(temp_path)
    
    # Write script to temporary file
    script_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py')
    script_file.write(selector_script)
    script_file.close()
    
    try:
        # Run the selector in a separate process
        subprocess.run([sys.executable, script_file.name], check=True)
        
        # Read the selected region
        with open(temp_path, 'r') as f:
            region = json.load(f)
        
        return region
        
    except subprocess.CalledProcessError as e:
        print(f"Error running region selector: {e}")
        return None
    except Exception as e:
        print(f"Error reading region result: {e}")
        return None
    finally:
        # Cleanup temporary files
        try:
            os.unlink(script_file.name)
            os.unlink(temp_path)
        except Exception:
            pass


def create_selector_script(temp_path):
    """
    Generate the Python code for the region selector GUI.
    
    Args:
        temp_path: Path to save the selected region coordinates
        
    Returns:
        String containing the complete selector script
    """
    return f'''
import tkinter as tk
import json

class RegionSelector:
    """GUI tool for selecting a rectangular screen region."""
    
    def __init__(self, root):
        self.root = root
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.region = None 

        # Setup fullscreen transparent overlay
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{{screen_width}}x{{screen_height}}+0+0") 
        self.root.attributes('-alpha', 0.2)
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        
        # Create canvas for drawing selection rectangle
        self.canvas = tk.Canvas(self.root, cursor="cross", bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mouse events
        self.canvas.bind("<Button-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.root.bind("<Escape>", self.quit)
        
        # Display instructions
        label = tk.Label(self.canvas, 
                         text="Click and drag to select a region.\\nPress 'Escape' to cancel.", 
                         font=('Arial', 14, 'bold'), 
                         bg='white', 
                         fg='black')
        self.canvas.create_window(screen_width / 2, 
                                  screen_height / 2, 
                                  window=label)

    def on_mouse_press(self, event):
        """Record starting position of selection."""
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = None

    def on_mouse_drag(self, event):
        """Update selection rectangle as user drags."""
        cur_x, cur_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, cur_x, cur_y,
            outline='red', width=2, fill='#BBBBBB'
        )

    def on_mouse_release(self, event):
        """Finalize selection and store coordinates."""
        end_x, end_y = event.x, event.y
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        width = abs(self.start_x - end_x)
        height = abs(self.start_y - end_y)

        if width > 0 and height > 0:
            self.region = (left, top, width, height)
            print(f"Captured region: {{self.region}}")
        else:
            print("Selection was too small.")
            self.region = None

        self.root.quit()

    def quit(self, event=None):
        """Cancel selection and exit."""
        print("Region selection cancelled.")
        self.region = None
        self.root.quit()

# Main execution
root = tk.Tk()
selector = RegionSelector(root)
root.mainloop()

# Save result to file
with open("{temp_path}", "w") as f:
    json.dump(selector.region, f)

root.destroy()
'''


# =============================================================================
# TEMPLATE LOADING
# =============================================================================

def load_bobber_templates():
    """
    Load all bobber template images from the /images directory.
    Converts images to grayscale for OpenCV template matching.
    
    Returns:
        List of grayscale OpenCV image arrays
    """
    print("Loading bobber templates with OpenCV...")
    
    current_dir = os.getcwd()
    bob_directory = os.path.join(current_dir, "images")
    templates = []
    
    try:
        # Load all PNG files in sorted order
        for file_name in sorted(os.listdir(bob_directory)):
            if file_name.endswith(".png"):
                file_path = os.path.join(bob_directory, file_name)
                img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
                
                if img is not None:
                    templates.append(img)
                    print(f"  - Loaded: {file_name} ({img.shape[1]}x{img.shape[0]})")
                else:
                    print(f"  - Failed to load: {file_name}")
        
        print(f"\nSuccessfully loaded {len(templates)} template(s).")
        
        if not templates:
            print("!! WARNING: No templates found in /images folder.")
            exit()
            
        return templates
            
    except FileNotFoundError:
        print(f"!! ERROR: 'images' directory not found at {bob_directory}")
        exit()


# =============================================================================
# USER INTERFACE & SETUP
# =============================================================================

def print_banner():
    """Display the application banner."""
    print('''
                 |
                 |
                ,|.
               ,\|/.
             ,' .V. `.
            / .     . \
           /_`       '_\
          ,' .:     ;, `.
          |@)|  . .  |(@|
     ,-._ `._';  .  :`_,' _,-.
    '--  `-\ /,-===-.\ /-'  --`
   (----  _|  ||___||  |_  ----)
    `._,-'  \  `-.-'  /  `-._,'
             `-.___,-'
    WetFish v1.0.0 - OpenCV Edition                                         
    ''')


def get_game_version():
    """
    Prompt user to select game version.
    
    Returns:
        Wait timer value for selected game version
    """
    gameversion = input("\nSelect your game version\n[1] Era/SoD [2] WotLK [3] Exit the app >> ")
    
    if gameversion == '1':
        return GAME_TIMERS['era']
    elif gameversion == '2':
        return GAME_TIMERS['wotlk']
    elif gameversion == '3':
        exit()
    else:
        print("\nWrong input. << Exiting >>")
        exit()


def get_audio_device_selection():
    """
    Prompt user to select audio device.
    
    Returns:
        String representing selected device ('1', '2', '3', or '4')
    """
    device = input("\nSelect your in-game Audio Output device\n[1] Default Speakers [2] VoiceMeeter [3] BlackHole [4] Exit the app >> ")
    
    if device == '4':
        exit()
    
    return device


def get_casting_key():
    """
    Prompt user for the fishing cast keybind.
    
    Returns:
        Lowercase string of the casting key
    """
    key = input("\nInput your casting key or type exit to quit the program >> ")
    key = key.lower()
    
    if key == 'exit':
        exit()
    
    return key

def get_lure_key():
    """
    Prompt user for the apply lure macro keybind.
    
    Returns:
        Lowercase string of the casting key
    """
    key = input("\nInput your Apply Lure macro key or type exit to quit the program >> ")
    key = key.lower()
    
    if key == 'exit':
        exit()
    
    return key



def countdown_to_start():
    """Display countdown before starting the bot."""
    print("\nStarting in 10 seconds. Activate the correct window.")
    time.sleep(7)
    print("\n3")
    time.sleep(1)
    print("2")
    time.sleep(1)
    print("1\n")
    time.sleep(1)


def apply_lure():
    """
    Checks if the lure needs to be reapplied based on a 10-minute cooldown.
    Applies the lure on the first run and every 10 minutes thereafter.
    Waits for LURE_POST_WAIT seconds after a successful application.
    """
    global last_lure_time
    
    current_time = time.time()
    
    # Check if it's the first time (last_lure_time is None)
    # OR if 10 minutes (LURE_COOLDOWN) have passed since the last application
    if last_lure_time is None or (current_time - last_lure_time) > LURE_COOLDOWN:
        
        print("\n<< Applying Lure... >>")
        
        # Simulate pressing the lure key
        pyautogui.keyDown(f'{lurekey}')
        time.sleep(np.random.uniform(0.1, 0.3)) # Human-like press
        pyautogui.keyUp(f'{lurekey}')
        
        # Update the timestamp to the current time
        last_lure_time = current_time
        
        # Wait the required 5.1 seconds after applying
        print(f"<< Waiting {LURE_POST_WAIT}s after lure application... >>")
        time.sleep(LURE_POST_WAIT)
        
    else:
        # It's not time to apply the lure, so do nothing and return immediately.
        pass



# =============================================================================
# MAIN EXECUTION LOOP
# =============================================================================

def main_loop():
    """
    Main fishing automation loop.
    Continuously casts, finds bobber, and reels in until interrupted.
    """
    try:
        while True:
            # Check for exit signal
            if esc_pressed:
                print("<< Exiting >>")
                exit()

            # Execute fishing sequence
            print("\n<< Casting >>")
            apply_lure()
            cast_line()
            find_bob()
            
            if bob_found:
                reel_in()
                if reeled:
                    continue  # Successfully reeled in, cast again
            else:
                # Bobber not found, wait and retry
                time.sleep(np.random.uniform(2.3, 3.7))
                print("<< Could not find Bob. Trying again. >>")
                
    except KeyboardInterrupt:
        print("\n<< Interrupted by user >>")
        exit()


# =============================================================================
# PROGRAM ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Display banner
    print_banner()
    
    # Load bobber templates
    BOBBER_TEMPLATES_CV = load_bobber_templates()
    
    # Get user configuration
    wait_timer = get_game_version()
    input_device = get_audio_device_selection()
    BOBBER_REGION = get_region_with_gui()
    
    # Validate region selection
    if BOBBER_REGION:
        print(f"\nYour script will search in this region:")
        print(f"BOBBER_REGION = {BOBBER_REGION}")
    else:
        print("\nNo region was selected. Exiting.")
        exit()
    
    # Get casting key
    castingkey = get_casting_key()
    # Get apply lure key
    lurekey = get_lure_key()
    
    # Start countdown
    countdown_to_start()
    
    # Start keyboard listener for ESC key
    print("Starting keyboard listener... Press ESC to exit anytime.")
    listener = pynput_keyboard.Listener(on_press=on_press)
    listener.start()
    
    # Run main loop
    main_loop()
    
    # Cleanup
    listener.stop()
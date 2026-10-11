import time
import datetime
from collections import deque
import csv
import os
import platform
import subprocess
import sys
from typing import Optional

# ============================================
# 1. DEPENDENCY CHECK AND INSTALLATION
# ============================================

def check_and_install_dependencies():
    """Check and install required packages"""
    required_packages = ['pynput']
    
    print("Checking dependencies...")
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} is already installed")
        except ImportError:
            print(f"⚠ {package} not found. Installing...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"✓ Successfully installed {package}")
            except Exception as e:
                print(f"✗ Failed to install {package}: {e}")
                print(f"Please install it manually: pip install {package}")
                return False
    return True

# ============================================
# 2. SETTINGS
# ============================================

class Settings:
    """All configurable settings in one place"""
    
    # Time window to analyze (in seconds)
    TIME_WINDOW = 30 * 60  # 30 minutes
    
    # Warning thresholds
    WARNING_THRESHOLD = 25  # Warn after 25 switches in 30 min
    CRITICAL_THRESHOLD = 40  # Critical after 40 switches
    
    # Data collection interval (seconds)
    UPDATE_INTERVAL = 2.0
    
    # Where to save data
    DATA_FILE = "focus_data.csv"
    
    # Enable/disable features
    ENABLE_NOTIFICATIONS = True
    LOG_TO_CONSOLE = True
    SAVE_TO_FILE = True

# ============================================
# 3. CROSS-PLATFORM APPLICATION DETECTION
# ============================================

def get_active_window_cross_platform() -> str:
    """Get current active application name (works on Windows, macOS, Linux)"""
    system = platform.system()
    
    try:
        if system == "Windows":
            return _get_active_window_windows()
        elif system == "Darwin":  # macOS
            return _get_active_window_mac()
        elif system == "Linux":
            return _get_active_window_linux()
        else:
            return "Unknown"
    except Exception as e:
        print(f"Note: Could not detect window title: {e}")
        return "Unknown"

def _get_active_window_windows() -> str:
    """Windows implementation using ctypes (no external dependencies)"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value if buff.value else "Desktop"
    except:
        return "Unknown"

def _get_active_window_mac() -> str:
    """macOS implementation using applescript (no external dependencies)"""
    try:
        script = '''
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
        end tell
        return frontApp
        '''
        result = subprocess.run(['osascript', '-e', script], 
                              capture_output=True, text=True)
        return result.stdout.strip()
    except:
        return "Unknown"

def _get_active_window_linux() -> str:
    """Linux implementation using xdotool or wmctrl"""
    try:
        # Try xdotool first
        result = subprocess.run(['xdotool', 'getwindowfocus', 'getwindowname'],
                              capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip() or "Unknown"
        
        # Try wmctrl as fallback
        result = subprocess.run(['wmctrl', '-l', '-x'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            # Find active window (simplified)
            return "Active Window"
    except:
        pass
    return "Unknown"

# ============================================
# 4. NOTIFICATION SYSTEM
# ============================================

def show_notification_cross_platform(title: str, message: str):
    """Show notification using platform-specific methods"""
    system = platform.system()
    
    try:
        if system == "Windows":
            # Windows - try multiple methods
            try:
                # Method 1: win10toast
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5)
                return
            except ImportError:
                # Method 2: ctypes
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
                return
        elif system == "Darwin":  # macOS
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(['osascript', '-e', script])
            return
        elif system == "Linux":
            subprocess.run(['notify-send', title, message])
            return
    except Exception as e:
        print(f"Note: Could not show notification: {e}")
    
    # Fallback to console output
    print(f"\n{'='*50}")
    print(f"📢 {title}")
    print(f"{message}")
    print(f"{'='*50}\n")

# ============================================
# 5. FOCUS MONITOR CLASS
# ============================================

class AppSwitchEvent:
    """Simple class to store app switch events"""
    
    def __init__(self, timestamp: float, from_app: str, to_app: str, duration: float):
        self.timestamp = timestamp
        self.from_app = from_app
        self.to_app = to_app
        self.duration = duration
    
    def to_dict(self):
        """Convert to dictionary for CSV saving"""
        return {
            'timestamp': self.timestamp,
            'time_human': datetime.datetime.fromtimestamp(self.timestamp).strftime('%H:%M:%S'),
            'from_app': self.from_app,
            'to_app': self.to_app,
            'duration_seconds': round(self.duration, 2)
        }

class FocusMonitor:
    """Main class that monitors app switching"""
    
    def __init__(self):
        self.current_app = None
        self.app_start_time = time.time()
        self.switch_history = deque(maxlen=1000)
        self.is_running = True
        self.last_switch_time = time.time()
        
        # For calculating switches per hour
        self.switch_count_last_30min = 0
        self.switch_timestamps = deque(maxlen=1000)
        
        # Setup CSV file
        if Settings.SAVE_TO_FILE and not os.path.exists(Settings.DATA_FILE):
            self.setup_csv()
    
    def setup_csv(self):
        """Create CSV file with headers if it doesn't exist"""
        try:
            with open(Settings.DATA_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'timestamp', 'time_human', 'from_app', 'to_app', 'duration_seconds'
                ])
                writer.writeheader()
            print(f"✓ Created data file: {Settings.DATA_FILE}")
        except Exception as e:
            print(f"✗ Could not create data file: {e}")
    
    def save_switch(self, switch: AppSwitchEvent):
        """Save switch event to CSV"""
        if Settings.SAVE_TO_FILE:
            try:
                with open(Settings.DATA_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'timestamp', 'time_human', 'from_app', 'to_app', 'duration_seconds'
                    ])
                    writer.writerow(switch.to_dict())
            except Exception as e:
                if Settings.LOG_TO_CONSOLE:
                    print(f"Note: Could not save to CSV: {e}")
    
    def check_app_switch(self):
        """Check if the active application has changed"""
        new_app = get_active_window_cross_platform()
        
        # First run - just set current app
        if self.current_app is None:
            self.current_app = new_app
            self.app_start_time = time.time()
            return
        
        # If app changed
        if new_app != self.current_app and new_app:
            duration = time.time() - self.app_start_time
            
            # Create switch event
            switch = AppSwitchEvent(
                timestamp=time.time(),
                from_app=self.current_app,
                to_app=new_app,
                duration=duration
            )
            
            # Store it
            self.switch_history.append(switch)
            self.switch_timestamps.append(time.time())
            self.save_switch(switch)
            
            # Update counters
            self.switch_count_last_30min = self.calculate_recent_switches()
            
            # Log if enabled
            if Settings.LOG_TO_CONSOLE:
                print(f"\n🔄 Switch #{len(self.switch_history)}")
                print(f"   From: {self.current_app[:40]}")
                print(f"   To: {new_app[:40]}")
                print(f"   Duration in previous app: {duration:.1f}s")
                print(f"   Total switches (30min): {self.switch_count_last_30min}")
            
            # Check thresholds
            self.check_thresholds()
            
            # Update current app
            self.current_app = new_app
            self.app_start_time = time.time()
            self.last_switch_time = time.time()
    
    def calculate_recent_switches(self) -> int:
        """Calculate how many switches in the last TIME_WINDOW seconds"""
        now = time.time()
        cutoff = now - Settings.TIME_WINDOW
        
        # Count timestamps within the window
        count = 0
        for timestamp in self.switch_timestamps:
            if timestamp > cutoff:
                count += 1
        
        return count
    
    def check_thresholds(self):
        """Check if we're switching too much and show notifications"""
        if not Settings.ENABLE_NOTIFICATIONS:
            return
        
        switches = self.switch_count_last_30min
        
        if switches >= Settings.CRITICAL_THRESHOLD:
            show_notification_cross_platform(
                "🚨 Critical Focus Alert",
                f"You've switched apps {switches} times in 30 minutes.\nConsider a 5-minute break!"
            )
        elif switches >= Settings.WARNING_THRESHOLD:
            show_notification_cross_platform(
                "⚠️ Focus Warning",
                f"High app switching: {switches} times in 30 minutes.\nTry to focus on one task."
            )
    
    def get_stats(self) -> dict:
        """Get current statistics"""
        if not self.switch_history:
            return {}
        
        recent_switches = list(self.switch_history)[-10:]  # Last 10 switches
        if recent_switches:
            avg_duration = sum(s.duration for s in recent_switches) / len(recent_switches)
        else:
            avg_duration = 0
        
        return {
            'current_app': self.current_app,
            'switches_last_30min': self.switch_count_last_30min,
            'avg_focus_duration': avg_duration,
            'last_switch_ago': time.time() - self.last_switch_time if self.last_switch_time else 0,
            'total_switches_today': len(self.switch_history)
        }
    
    def display_stats(self):
        """Display current statistics"""
        stats = self.get_stats()
        if stats:
            print(f"\n📊 Current Stats:")
            print(f"   • Current app: {stats['current_app'][:40] if stats['current_app'] else 'None'}")
            print(f"   • Switches (last 30min): {stats['switches_last_30min']}")
            print(f"   • Avg focus time: {stats['avg_focus_duration']:.1f}s")
            print(f"   • Time since last switch: {stats['last_switch_ago']:.1f}s")
            print("-" * 40)
    
    def run_monitoring(self):
        """Main monitoring loop"""
        print("=" * 60)
        print("🧠 REAL-TIME FOCUS MONITOR")
        print("=" * 60)
        print(f"Platform: {platform.system()}")
        print(f"Tracking app switches every {Settings.UPDATE_INTERVAL} seconds")
        print(f"Warning threshold: {Settings.WARNING_THRESHOLD} switches/30min")
        print(f"Critical threshold: {Settings.CRITICAL_THRESHOLD} switches/30min")
        print("=" * 60)
        print("Press Ctrl+C to stop monitoring\n")
        
        last_stat_display = time.time()
        
        try:
            while self.is_running:
                # Check for app switches
                self.check_app_switch()
                
                # Display stats every 30 seconds
                current_time = time.time()
                if current_time - last_stat_display >= 30:
                    self.display_stats()
                    last_stat_display = current_time
                
                # Wait before next check
                time.sleep(Settings.UPDATE_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
            self.stop()
        except Exception as e:
            print(f"\nError occurred: {e}")
            self.stop()
    
    def stop(self):
        """Stop the monitor and show final statistics"""
        self.is_running = False
        print("\n" + "=" * 60)
        print("📈 FINAL STATISTICS")
        print("=" * 60)
        
        stats = self.get_stats()
        if stats:
            print(f"Total app switches recorded: {stats['total_switches_today']}")
            print(f"Final app: {stats['current_app']}")
            
            # Calculate focus score
            if stats['avg_focus_duration'] > 120:  # More than 2 minutes average
                focus_score = "Excellent! 🎯"
            elif stats['avg_focus_duration'] > 60:
                focus_score = "Good 👍"
            elif stats['avg_focus_duration'] > 30:
                focus_score = "Needs Improvement 📉"
            else:
                focus_score = "Very Distracted 😵"
            
            print(f"Average focus duration: {stats['avg_focus_duration']:.1f}s ({focus_score})")
        
        if Settings.SAVE_TO_FILE and os.path.exists(Settings.DATA_FILE):
            print(f"\nData saved to: {Settings.DATA_FILE}")
            print("You can analyze this data in Excel or Python later!")
        
        print("\nThank you for using Focus Monitor! 👋")

# ============================================
# 6. SIMPLE ALTERNATIVE (NO EXTERNAL DEPENDENCIES)
# ============================================

def simple_focus_monitor():
    """
    Ultra-simple version with NO external dependencies
    Only uses standard Python libraries
    """
    print("=" * 60)
    print("🧠 SIMPLE FOCUS MONITOR")
    print("=" * 60)
    print("This version uses time-based simulation")
    print("Press Enter each time you switch tasks")
    print("Press 'q' then Enter to quit")
    print("=" * 60)
    
    task_start = time.time()
    switch_count = 0
    task_durations = []
    
    print("\nStart working on your first task...")
    print("When you switch to a new task, press Enter")
    
    try:
        while True:
            user_input = input("\nPress Enter when you switch tasks (or 'q' to quit): ")
            
            if user_input.lower() == 'q':
                break
            
            # Calculate duration of previous task
            task_end = time.time()
            duration = task_end - task_start
            task_durations.append(duration)
            switch_count += 1
            
            print(f"\n🔄 Switch #{switch_count}")
            print(f"   Task duration: {duration:.1f} seconds")
            print(f"   Total switches: {switch_count}")
            
            # Check thresholds
            if switch_count >= Settings.CRITICAL_THRESHOLD:
                print("\n🚨 CRITICAL: Too many switches! Take a 5-minute break!")
            elif switch_count >= Settings.WARNING_THRESHOLD:
                print("\n⚠️ WARNING: High switching rate. Try to focus!")
            
            # Reset for next task
            task_start = time.time()
            print("\nWorking on new task...")
            
    except KeyboardInterrupt:
        pass
    
    # Show final stats
    print("\n" + "=" * 60)
    print("📈 FINAL STATISTICS")
    print("=" * 60)
    print(f"Total switches: {switch_count}")
    if task_durations:
        avg_duration = sum(task_durations) / len(task_durations)
        print(f"Average task duration: {avg_duration:.1f} seconds")
        if avg_duration > 300:
            print("Focus Level: Excellent! 🎯")
        elif avg_duration > 120:
            print("Focus Level: Good 👍")
        elif avg_duration > 60:
            print("Focus Level: Fair 📊")
        else:
            print("Focus Level: Needs Improvement 📉")
    print("\nThank you for tracking your focus! 👋")

# ============================================
# 7. MAIN EXECUTION
# ============================================

def main():
    """Main function to run the monitor"""
    
    print("Setting up Real-Time Focus Monitor...")
    
    # Ask user which version they want
    print("\nChoose version:")
    print("1. Automatic tracking (requires pynput)")
    print("2. Simple manual tracking (no dependencies)")
    print("3. Install dependencies first")
    
    choice = input("\nEnter choice (1, 2, or 3): ").strip()
    
    if choice == "3":
        # Install dependencies first
        if check_and_install_dependencies():
            print("\nDependencies installed! Please run the program again.")
        else:
            print("\nSome dependencies failed to install. Try the simple version instead.")
        return
    elif choice == "2":
        # Run simple version
        simple_focus_monitor()
        return
    elif choice == "1":
        # Run automatic version
        if not check_and_install_dependencies():
            print("\nSome dependencies are missing. Switching to simple version...")
            time.sleep(2)
            simple_focus_monitor()
            return
    else:
        print("Invalid choice. Running automatic version...")
        if not check_and_install_dependencies():
            print("\nSwitching to simple version...")
            time.sleep(2)
            simple_focus_monitor()
            return
    
    # Create and run monitor
    try:
        # Try to import pynput now
        from pynput import keyboard, mouse
        monitor = FocusMonitor()
        monitor.run_monitoring()
    except ImportError as e:
        print(f"\n✗ Error: Could not import required module: {e}")
        print("Switching to simple version...")
        time.sleep(2)
        simple_focus_monitor()
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        print("Switching to simple version...")
        time.sleep(2)
        simple_focus_monitor()

# ============================================
# 8. START THE PROGRAM
# ============================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        print("Trying to run the simple version as fallback...")
        time.sleep(2)
        simple_focus_monitor()
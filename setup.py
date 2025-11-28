#!/usr/bin/env python3
"""
sdr2zello Setup Script - Linux Only
Handles installation and initial setup of the sdr2zello application for Linux
"""

import os
import sys
import subprocess
import platform
import shutil
import argparse
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        sys.exit(1)
    print(f"✅ Python version {sys.version.split()[0]} is compatible")


def check_linux_system():
    """Ensure we're running on Linux"""
    if platform.system() != "Linux":
        print("❌ Error: This script is designed for Linux only")
        print(f"Detected system: {platform.system()}")
        sys.exit(1)
    print("✅ Linux system detected")


def detect_linux_distribution():
    """Detect Linux distribution"""
    try:
        with open('/etc/os-release', 'r') as f:
            lines = f.readlines()

        for line in lines:
            if line.startswith('ID='):
                distro = line.split('=')[1].strip().strip('"')
                return distro
    except FileNotFoundError:
        pass

    # Fallback detection
    if shutil.which('apt'):
        return 'ubuntu'  # or debian-like
    elif shutil.which('dnf'):
        return 'fedora'
    elif shutil.which('pacman'):
        return 'arch'
    else:
        return 'unknown'


def install_system_dependencies():
    """Install system dependencies based on distribution"""
    print("\n📦 Installing system dependencies...")

    distro = detect_linux_distribution()
    print(f"   Detected distribution: {distro}")

    try:
        if distro in ['ubuntu', 'debian']:
            print("   Using apt package manager...")
            subprocess.run([
                "sudo", "apt", "update", "&&", "sudo", "apt", "install", "-y",
                "rtl-sdr", "librtlsdr-dev", "python3-pip", "python3-venv",
                "python3-pyaudio", "pulseaudio-utils", "git", "curl"
            ], shell=True, check=True)

        elif distro == 'fedora':
            print("   Using dnf package manager...")
            subprocess.run([
                "sudo", "dnf", "install", "-y",
                "rtl-sdr", "rtl-sdr-devel", "python3-pip", "python3-virtualenv",
                "python3-pyaudio", "pulseaudio-utils", "git", "curl"
            ], check=True)

        elif distro == 'arch':
            print("   Using pacman package manager...")
            subprocess.run([
                "sudo", "pacman", "-S", "--noconfirm",
                "rtl-sdr", "python-pip", "python-virtualenv",
                "python-pyaudio", "pulseaudio", "git", "curl"
            ], check=True)

        else:
            print(f"   ⚠️  Unknown distribution: {distro}")
            print("   Please install manually:")
            print("   - rtl-sdr, python3-pip, python3-venv, python3-pyaudio")
            print("   - pulseaudio-utils, git, curl")
            return False

        print("   ✅ System dependencies installed")
        return True

    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error installing dependencies: {e}")
        print("   Please install manually and try again")
        return False


def setup_rtl_sdr_udev():
    """Setup RTL-SDR udev rules"""
    print("\n📡 Setting up RTL-SDR udev rules...")

    udev_content = """# RTL-SDR
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="604b", GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"
"""

    try:
        with open('/tmp/20-rtl-sdr.rules', 'w') as f:
            f.write(udev_content)

        subprocess.run([
            "sudo", "cp", "/tmp/20-rtl-sdr.rules", "/etc/udev/rules.d/"
        ], check=True)

        # Add user to plugdev group
        import getpass
        username = getpass.getuser()
        subprocess.run([
            "sudo", "usermod", "-a", "-G", "plugdev", username
        ], check=True)

        print("   ✅ RTL-SDR udev rules configured")
        print(f"   👤 User '{username}' added to plugdev group")
        print("   🔄 You may need to logout/login for group changes to take effect")

        return True

    except Exception as e:
        print(f"   ❌ Error setting up udev rules: {e}")
        return False


def create_virtual_environment():
    """Create and setup Python virtual environment"""
    print("\n🐍 Creating Python virtual environment...")

    try:
        if os.path.exists("venv"):
            print("   Virtual environment already exists")
        else:
            subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
            print("   ✅ Virtual environment created")

        # Return path to pip in virtual environment
        return os.path.join("venv", "bin", "pip")

    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error creating virtual environment: {e}")
        sys.exit(1)


def install_python_dependencies(pip_path):
    """Install Python dependencies"""
    print("\n📋 Installing Python dependencies...")

    try:
        subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)
        subprocess.run([pip_path, "install", "-r", "requirements.txt"], check=True)
        print("   ✅ Python dependencies installed")
        
        # Verify MP3 encoding support
        try:
            import lameenc
            print("   ✅ MP3 encoding support available (lameenc)")
        except ImportError:
            print("   ⚠️  MP3 encoding not available (lameenc not installed)")
            print("   💡 Install with: pip install lameenc")

    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error installing Python dependencies: {e}")
        sys.exit(1)


def setup_pulseaudio_virtual_audio():
    """Setup PulseAudio virtual audio devices"""
    print("\n🔊 Setting up PulseAudio virtual audio devices...")

    try:
        # Check if PulseAudio is available
        result = subprocess.run(["pactl", "info"], capture_output=True, text=True)
        if result.returncode != 0:
            print("   ❌ PulseAudio not found")
            print("   💡 Please install PulseAudio: sudo apt install pulseaudio pulseaudio-utils")
            return False

        print("   🔧 Creating PulseAudio virtual sink...")

        # Create virtual sink (temporary)
        try:
            subprocess.run([
                "pactl", "load-module", "module-null-sink",
                "sink_name=sdr2zello",
                "sink_properties=device.description=sdr2zello_Virtual_Output"
            ], check=True)

            # Create loopback to default sink
            subprocess.run([
                "pactl", "load-module", "module-loopback",
                "source=sdr2zello.monitor",
                "sink=@DEFAULT_SINK@"
            ], check=True)

            print("   ✅ Temporary virtual audio devices created")

        except subprocess.CalledProcessError:
            print("   ⚠️  Virtual sink may already exist")

        # Setup permanent configuration
        pulse_config_dir = os.path.expanduser("~/.config/pulse")
        os.makedirs(pulse_config_dir, exist_ok=True)

        config_content = """
# sdr2zello Virtual Audio Configuration
load-module module-null-sink sink_name=sdr2zello sink_properties=device.description=sdr2zello_Virtual_Output
load-module module-loopback source=sdr2zello.monitor sink=@DEFAULT_SINK@
"""

        config_file = os.path.join(pulse_config_dir, "default.pa")

        # Check if configuration already exists
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                existing_config = f.read()

            if "sdr2zello" not in existing_config:
                with open(config_file, 'a') as f:
                    f.write(config_content)
                print("   ✅ Permanent PulseAudio configuration added")
            else:
                print("   ⚠️  PulseAudio configuration already exists")
        else:
            with open(config_file, 'w') as f:
                f.write(config_content)
            print("   ✅ PulseAudio configuration created")

        return True

    except Exception as e:
        print(f"   ❌ Error setting up virtual audio: {e}")
        print("   💡 Manual setup instructions:")
        print("   • pactl load-module module-null-sink sink_name=sdr2zello")
        print("   • pactl load-module module-loopback source=sdr2zello.monitor sink=@DEFAULT_SINK@")
        return False


def install_zello():
    """Install Zello for Linux"""
    print("\n📱 Installing Zello for Linux...")

    try:
        # Try Snap first
        snap_result = subprocess.run(["snap", "--version"], capture_output=True, text=True)
        if snap_result.returncode == 0:
            print("   📦 Installing Zello via Snap...")
            subprocess.run(["sudo", "snap", "install", "zello-unofficial"], check=True)
            print("   ✅ Zello installed via Snap")
            return True

        # Try Flatpak
        flatpak_result = subprocess.run(["flatpak", "--version"], capture_output=True, text=True)
        if flatpak_result.returncode == 0:
            print("   📦 Installing Zello via Flatpak...")
            subprocess.run([
                "flatpak", "remote-add", "--if-not-exists", "flathub",
                "https://flathub.org/repo/flathub.flatpakrepo"
            ], check=True)
            subprocess.run([
                "flatpak", "install", "-y", "flathub", "com.zello.Zello"
            ], check=True)
            print("   ✅ Zello installed via Flatpak")
            return True

        # No package managers found
        print("   ❌ No suitable package manager found (Snap/Flatpak)")
        print("   💡 Please install Zello manually:")
        print("   • Web version: https://web.zello.com")
        print("   • Or install Snap/Flatpak first")
        return False

    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error installing Zello: {e}")
        print("   💡 Alternative: Use Zello Web at https://web.zello.com")
        return False


def setup_configuration():
    """Setup configuration files"""
    print("\n⚙️  Setting up configuration files...")

    try:
        # Create config.yaml file if it doesn't exist
        if not os.path.exists("config.yaml"):
            import yaml
            
            config_data = {
                'server': {
                    'host': 'localhost',
                    'port': 8000,
                    'debug': False,
                    'log_level': 'INFO'
                },
                'sdr': {
                    'device_index': 0,
                    'sample_rate': 2048000,
                    'gain': 49.6
                },
                'audio': {
                    'sample_rate': 48000,
                    'channels': 1,
                    'chunk_size': 1024,
                    'device_name': 'sdr2zello'
                },
                'scanning': {
                    'delay': 0.1,
                    'squelch_threshold': -50.0,
                    'transmission_timeout': 5.0
                },
                'priority_scanning': {
                    'enabled': True,
                    'multiplier': 2.0,
                    'min_priority_weight': 0.5,
                    'scan_mode': 'weighted'
                },
                'recording': {
                    'directory': 'recordings',
                    'format': 'wav',  # 'wav' or 'mp3' (mp3 requires lameenc)
                    'mp3_bitrate': '192k'  # MP3 bitrate if format is mp3
                },
                'dsp': {
                    'noise_gate': {
                        'enabled': True,
                        'threshold': -40.0,
                        'attack_time': 0.001,
                        'release_time': 0.1
                    },
                    'agc': {
                        'enabled': True,
                        'target_level': -20.0,
                        'attack_time': 0.003,
                        'release_time': 0.1,
                        'max_gain': 40.0
                    },
                    'noise_reduction': {
                        'enabled': False,
                        'alpha': 2.0,
                        'frame_size': 1024
                    },
                    'equalizer': {
                        'enabled': False,
                        'sub_bass_gain': 0.0,
                        'bass_gain': 0.0,
                        'low_mid_gain': 0.0,
                        'mid_gain': 0.0,
                        'high_mid_gain': 0.0,
                        'presence_gain': 0.0,
                        'brilliance_gain': 0.0,
                        'air_gain': 0.0
                    }
                },
                'database': {
                    'url': 'sqlite:///sdr2zello.db'
                },
                'default_frequencies': [
                    118000000,
                    121500000,
                    122800000,
                    145500000,
                    446000000,
                    155160000,
                    162550000
                ],
                'paths': {
                    'static_files': 'static',
                    'templates': 'templates',
                    'recordings': 'recordings'
                }
            }
            
            with open("config.yaml", "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            print("   ✅ Configuration file created (config.yaml)")
        else:
            print("   ⚠️  Configuration file already exists")

        # Create directories
        os.makedirs("recordings", exist_ok=True)
        os.makedirs("logs", exist_ok=True)

        print("   ✅ Directories created")
        return True

    except Exception as e:
        print(f"   ❌ Error setting up configuration: {e}")
        return False


def display_next_steps():
    """Display next steps for user"""
    print("\n🎉 sdr2zello Linux Setup Complete!")
    print("="*50)
    print("\n📋 Next Steps:")
    print("1. 🔌 Connect your RTL-SDR device")
    print("2. 🔄 Logout and login (for USB permissions)")
    print("3. ▶️  Start sdr2zello:")
    print("   cd", os.getcwd())
    print("   source venv/bin/activate")
    print("   python main.py")
    print("4. 🌐 Open web interface: http://localhost:8000")

    print("\n🔧 Zello Configuration:")
    print("   • Open Zello application")
    print("   • Go to Settings → Audio")
                print("   • Set microphone input to 'sdr2zello_Virtual_Output'")
    print("   • Or use PulseAudio Volume Control (pavucontrol)")

    print("\n🧪 Testing:")
    print("   • Test RTL-SDR: rtl_test")
    print("   • Check audio devices: pactl list sinks | grep sdr2zello")
    print("   • Monitor logs: journalctl -f")


def main():
    """Main setup function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='sdr2zello Linux Setup Script')
    parser.add_argument('--install-audio-cable', action='store_true',
                        help='Install PulseAudio virtual devices automatically')
    parser.add_argument('--install-zello', action='store_true',
                        help='Install Zello automatically')
    args = parser.parse_args()

    print("🐧 sdr2zello Linux Setup Script")
    print("=" * 50)

    # Check system requirements
    check_python_version()
    check_linux_system()

    # If only installing specific components, do that and exit
    if args.install_audio_cable and not args.install_zello:
        setup_pulseaudio_virtual_audio()
        return

    if args.install_zello and not args.install_audio_cable:
        install_zello()
        return

    # Full setup process
    print("\n🚀 Starting full Linux setup...")

    # Install system dependencies
    deps_ok = install_system_dependencies()

    # Setup RTL-SDR
    rtl_ok = setup_rtl_sdr_udev()

    # Create virtual environment and install Python dependencies
    pip_path = create_virtual_environment()
    install_python_dependencies(pip_path)

    # Setup configuration
    config_ok = setup_configuration()

    # Setup audio
    audio_ok = setup_pulseaudio_virtual_audio()

    # Install Zello
    zello_ok = install_zello()

    # Display results and next steps
    display_next_steps()

    # Summary
    print("\n📊 Setup Summary:")
    print(f"   System Dependencies: {'✅' if deps_ok else '❌'}")
    print(f"   RTL-SDR Setup: {'✅' if rtl_ok else '❌'}")
    print(f"   Configuration: {'✅' if config_ok else '❌'}")
    print(f"   Audio Setup: {'✅' if audio_ok else '❌'}")
    print(f"   Zello Installation: {'✅' if zello_ok else '❌'}")

    if not all([deps_ok, rtl_ok, config_ok, audio_ok]):
        print("\n⚠️  Some components failed to setup.")
        print("Please check the logs above and install manually if needed.")


if __name__ == "__main__":
    main()
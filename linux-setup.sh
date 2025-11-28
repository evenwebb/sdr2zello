#!/bin/bash
# sdr2zello Linux Setup Script
# Optimized for Ubuntu/Debian, Fedora, and Arch-based distributions

set -e

echo "🐧 sdr2zello Linux Setup Script"
echo "================================="

# Detect Linux distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
else
    echo "❌ Cannot detect Linux distribution"
    exit 1
fi

echo "📋 Detected: $PRETTY_NAME"

# Update package lists
echo "🔄 Updating package lists..."
case $DISTRO in
    ubuntu|debian)
        sudo apt update
        ;;
    fedora)
        sudo dnf check-update || true
        ;;
    arch|manjaro)
        sudo pacman -Sy
        ;;
esac

# Install RTL-SDR dependencies
echo "📡 Installing RTL-SDR dependencies..."
case $DISTRO in
    ubuntu|debian)
        sudo apt install -y rtl-sdr librtlsdr-dev python3-pip python3-venv \
                           python3-pyaudio pulseaudio-utils git curl
        ;;
    fedora)
        sudo dnf install -y rtl-sdr rtl-sdr-devel python3-pip python3-virtualenv \
                           python3-pyaudio pulseaudio-utils git curl
        ;;
    arch|manjaro)
        sudo pacman -S --noconfirm rtl-sdr python-pip python-virtualenv \
                      python-pyaudio pulseaudio git curl
        ;;
esac

# Configure RTL-SDR udev rules
echo "⚙️  Setting up RTL-SDR udev rules..."
sudo tee /etc/udev/rules.d/20-rtl-sdr.rules > /dev/null << 'EOF'
# RTL-SDR
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="604b", GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"
EOF

# Add user to plugdev group
echo "👤 Adding user to plugdev group..."
sudo usermod -a -G plugdev $USER

# Setup PulseAudio virtual sinks
echo "🔊 Configuring PulseAudio virtual audio..."
if command -v pactl >/dev/null 2>&1; then
    # Create temporary virtual sink
    pactl load-module module-null-sink sink_name=sdr2zello_temp sink_properties=device.description=sdr2zello_Virtual_Output || true

    # Add permanent configuration to PulseAudio
    mkdir -p ~/.config/pulse
    echo "# sdr2zello Virtual Audio Configuration" >> ~/.config/pulse/default.pa
    echo "load-module module-null-sink sink_name=sdr2zello sink_properties=device.description=sdr2zello_Virtual_Output" >> ~/.config/pulse/default.pa
    echo "load-module module-loopback source=sdr2zello.monitor sink=@DEFAULT_SINK@" >> ~/.config/pulse/default.pa

    echo "✅ PulseAudio virtual sinks configured"
else
    echo "❌ PulseAudio not found"
fi

# Install Zello (multiple options)
echo "📱 Installing Zello..."
if command -v snap >/dev/null 2>&1; then
    echo "   📦 Installing via Snap..."
    sudo snap install zello-unofficial || echo "   ⚠️  Snap installation failed, trying Flatpak..."
fi

if ! snap list zello-unofficial >/dev/null 2>&1; then
    if command -v flatpak >/dev/null 2>&1; then
        echo "   📦 Installing via Flatpak..."
        flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
        flatpak install -y flathub com.zello.Zello || echo "   ⚠️  Flatpak installation failed"
    fi
fi

# Setup sdr2zello
echo "🚀 Setting up sdr2zello..."
cd "$(dirname "$0")"

# Run Python setup
python3 setup.py --install-audio-cable --install-zello --non-interactive

echo ""
echo "🎉 Setup Complete!"
echo "================="
echo "📋 Next steps:"
echo "   1. Logout and login (for group permissions)"
echo "   2. Connect your RTL-SDR device"
echo "   3. Run: python3 main.py"
echo "   4. Open: http://localhost:8000"
echo ""
echo "🔧 Manual configuration:"
echo "   • Configure Zello input: Set to 'sdr2zello_Virtual_Output'"
echo "   • Test RTL-SDR: rtl_test"
echo "   • Check audio: pactl list sinks | grep sdr2zello"
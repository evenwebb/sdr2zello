# 🐧 Linux Deployment Guide for sdr2zello

sdr2zello is optimized for Linux and provides excellent performance on various distributions.

## 🚀 Quick Start

### 1. Automated Setup (Recommended)
```bash
# Clone the repository
git clone <your-repo-url>
cd sdr2zello

# Run the Linux setup script
chmod +x linux-setup.sh
sudo ./linux-setup.sh
```

### 2. Manual Setup

#### Install System Dependencies
**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y rtl-sdr librtlsdr-dev python3-pip python3-venv \
                   python3-pyaudio pulseaudio-utils git curl
```

**Fedora:**
```bash
sudo dnf install -y rtl-sdr rtl-sdr-devel python3-pip python3-virtualenv \
                   python3-pyaudio pulseaudio-utils git curl
```

**Arch Linux:**
```bash
sudo pacman -S rtl-sdr python-pip python-virtualenv \
               python-pyaudio pulseaudio git curl
```

#### Configure RTL-SDR
```bash
# Add udev rules for RTL-SDR access
sudo tee /etc/udev/rules.d/20-rtl-sdr.rules > /dev/null << 'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", GROUP="plugdev", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", GROUP="plugdev", MODE="0666"
EOF

# Add user to plugdev group
sudo usermod -a -G plugdev $USER
```

#### Setup Virtual Audio (PulseAudio)
```bash
# Create permanent virtual audio sink
mkdir -p ~/.config/pulse
cat >> ~/.config/pulse/default.pa << 'EOF'
# sdr2zello Virtual Audio
load-module module-null-sink sink_name=sdr2zello sink_properties=device.description=sdr2zello_Virtual_Output
load-module module-loopback source=sdr2zello.monitor sink=@DEFAULT_SINK@
EOF

# Restart PulseAudio
pulseaudio -k && pulseaudio --start
```

## 🔧 Linux Audio Routing

### PulseAudio Configuration
sdr2zello uses PulseAudio virtual sinks for audio routing:

```
RTL-SDR → sdr2zello → Virtual Sink → Zello
                          ↓
                      Speakers/Headphones
```

### Audio Devices Created:
- **sdr2zello**: Virtual output sink for Zello input
- **sdr2zello.monitor**: Monitor source for audio splitting

### Testing Audio Setup:
```bash
# List audio sinks
pactl list sinks | grep sdr2zello

# Test virtual sink
pactl play-sample audio-test sdr2zello
```

## 📱 Zello Installation Options

### Option 1: Snap Package (Recommended)
```bash
sudo snap install zello-unofficial
```

### Option 2: Flatpak
```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub com.zello.Zello
```

### Option 3: Web Version
Use Zello Web at https://web.zello.com

## 🖥️ System Service Setup

### Install as System Service
```bash
# Create service user
sudo useradd -r -s /bin/false sdr2zello

# Copy files to system location
sudo cp -r . /opt/sdr2zello
sudo chown -R sdr2zello:sdr2zello /opt/sdr2zello

# Install systemd service
sudo cp sdr2zello.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sdr2zello
sudo systemctl start sdr2zello
```

### Service Management
```bash
# Check status
sudo systemctl status sdr2zello

# View logs
sudo journalctl -u sdr2zello -f

# Restart service
sudo systemctl restart sdr2zello
```

## ⚡ Performance Optimizations

### 1. CPU Scheduling
```bash
# Set real-time priority for SDR process
sudo setcap cap_sys_nice+ep /opt/sdr2zello/venv/bin/python
```

### 2. USB Buffer Size
```bash
# Increase USB buffer for better RTL-SDR performance
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="0bda", ATTR{idProduct}=="2832", ATTR{bConfigurationValue}="1"' | sudo tee -a /etc/udev/rules.d/20-rtl-sdr.rules
```

### 3. Audio Latency
```bash
# Optimize PulseAudio for low latency
cat >> ~/.pulse/daemon.conf << 'EOF'
high-priority = yes
nice-level = -11
default-sample-format = s16le
default-sample-rate = 44100
default-sample-channels = 2
default-fragments = 4
default-fragment-size-msec = 5
EOF
```

## 🔍 Troubleshooting

### RTL-SDR Issues
```bash
# Test RTL-SDR device
rtl_test

# Check USB permissions
lsusb | grep -E "(0bda|1d50)"
```

### Audio Issues
```bash
# Restart PulseAudio
pulseaudio -k && pulseaudio --start

# Check virtual sinks
pactl list sinks | grep sdr2zello

# Test audio routing
pactl play-sample audio-test sdr2zello
```

### Permission Issues
```bash
# Check user groups
groups $USER

# Add user to audio groups
sudo usermod -a -G audio,pulse-access $USER
```

### Service Issues
```bash
# Check service logs
sudo journalctl -u sdr2zello --since "1 hour ago"

# Check service status
sudo systemctl status sdr2zello
```

## 🌐 Web Interface Access

### Local Access
- **URL**: http://localhost:8000
- **Version Info**: http://localhost:8000/api/v1/versions

### Remote Access (Optional)
To access from other devices on the network:

1. **Configure Firewall**:
```bash
# Ubuntu/Debian
sudo ufw allow 8000

# Fedora
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

2. **Bind to All Interfaces**:
Edit `config.yaml` file:
```yaml
server:
  host: "0.0.0.0"
  port: 8000
```

Or use environment variable:
```bash
export sdr2zello_HOST=0.0.0.0
export sdr2zello_PORT=8000
```

## 🔒 Security Considerations

### Firewall Configuration
```bash
# Allow only local network access
sudo ufw allow from 192.168.0.0/16 to any port 8000
sudo ufw allow from 10.0.0.0/8 to any port 8000
```

### Service Hardening
The included systemd service file includes security hardening:
- NoNewPrivileges
- ProtectSystem
- PrivateTmp
- Resource limits

## 📊 Monitoring

### System Monitoring
```bash
# CPU/Memory usage
top -p $(pgrep -f sdr2zello)

# Network connections
ss -tlpn | grep 8000

# Audio processes
ps aux | grep pulse
```

### Log Monitoring
```bash
# Real-time logs
sudo journalctl -u sdr2zello -f

# Error logs only
sudo journalctl -u sdr2zello -p err
```

## 🔧 Configuration Files

### Important Files:
- `config.yaml` - Main configuration file
- `recordings/` - Audio recordings (WAV or MP3 format, configurable)
- `sdr2zello.db` - SQLite database
- `~/.config/pulse/default.pa` - PulseAudio config

### Recording Format:
Recordings can be saved as WAV (default) or MP3 format. To enable MP3:
1. Ensure `lameenc` is installed: `pip install lameenc` (included in requirements.txt)
2. Edit `config.yaml`:
   ```yaml
   recording:
     format: "mp3"        # Change from "wav" to "mp3"
     mp3_bitrate: "192k"  # Options: "128k", "192k", "256k", "320k"
   ```
3. Restart the application

### Backup Configuration:
```bash
# Backup configuration
tar -czf sdr2zello-backup.tar.gz config.yaml sdr2zello.db recordings/
```

## 📱 Zello Configuration

### Audio Input Setup:
1. Open Zello application
2. Go to Settings → Audio
3. Set input device to "sdr2zello_Virtual_Output"
4. Adjust input gain as needed

### Testing:
1. Start sdr2zello service
2. Configure frequencies in web interface
3. Start scanning
4. Watch transmission log for activity
5. Test Zello push-to-talk functionality
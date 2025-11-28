# sdr2zello - RTL-SDR to Zello Bridge

A comprehensive Python application that bridges RTL-SDR devices to Zello walkie-talkie app, featuring a modern web interface for complete control and monitoring.

## 🚀 Features

### Core Functionality
- **Multi-frequency scanning**: Monitor aviation, amateur radio, and general VHF/UHF frequencies
- **Intelligent transmission detection**: Advanced squelch and signal processing
- **Audio routing**: Automatic transmission forwarding to Zello via virtual audio
- **Recording & logs**: Capture and review all transmissions with timestamps

### Web Interface
- **Real-time monitoring**: Live signal strength visualization and frequency displays
- **Mobile responsive**: Full control from smartphones, tablets, and desktops
- **Frequency management**: Add, edit, and organize frequency lists
- **Toast notifications**: Real-time alerts for transmissions and system events

### Technical Features
- **Simulation mode**: Test without RTL-SDR hardware
- **Modular architecture**: Easy to extend and customize
- **Automatic setup**: Smart installation of virtual audio cables
- **REST API**: Programmatic control and integration
- **WebSocket communication**: Real-time updates and control
- **Smart scanning algorithms**: Activity-based and priority-weighted frequency selection
- **Frequency groups & tags**: Organize frequencies by category and custom tags
- **Health monitoring**: System metrics, service status, and performance tracking
- **Priority-based scanning**: Higher priority frequencies scanned more frequently
- **DSP audio processing**: Noise gate, AGC, noise reduction, and equalizer

## 📋 Requirements

### Hardware
- RTL-SDR compatible USB dongle (RTL2832U + R820T/R820T2/R828D)
- Linux computer with USB port (Ubuntu, Fedora, Arch, etc.)

### Software (Linux Only)
- Python 3.8+ (tested with Python 3.9-3.12)
- Zello walkie-talkie app (via Snap/Flatpak or web version)
- PulseAudio virtual audio device (automatically configured by setup script)

### Optional
- RTL-SDR drivers and libraries (for hardware mode)
- PyAudio (for audio output functionality)

## 🛠️ Installation

### Method 1: Automatic Setup (Recommended)

1. **Clone or download the project**:
   ```bash
   git clone https://github.com/your-username/sdr2zello.git
   cd sdr2zello
   ```

2. **Run the setup script**:
   ```bash
   python3 setup.py
   ```

3. **Activate virtual environment** (if not done automatically):
   ```bash
   source venv/bin/activate
   ```

4. **Start the application**:
   ```bash
   python main.py
   ```

### Method 2: Manual Setup

1. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or install core dependencies manually:
   ```bash
   pip install fastapi uvicorn jinja2 python-multipart sqlalchemy pydantic pydantic-settings python-dotenv psutil numpy scipy aiohttp websockets alembic
   ```

3. **Install optional dependencies** (for full functionality):
   ```bash
   # For RTL-SDR hardware support
   pip install pyrtlsdr scipy

   # For audio output (may require system audio libraries)
   pip install pyaudio

   # For MP3 recording support (included in requirements.txt)
   pip install lameenc
   ```

4. **Configure application** (optional):
   ```bash
   # Edit config.yaml file with your settings
   # See Configuration section below for available options
   ```

5. **Start the application**:
   ```bash
   python main.py
   ```


## ⚙️ Configuration

### Configuration File

Edit the `config.yaml` file to customize your installation. The configuration file uses YAML format for easy editing:

```yaml
# Server Configuration
server:
  host: "localhost"          # Server host (0.0.0.0 for external access)
  port: 8000                 # Web interface port
  debug: false               # Enable debug mode
  log_level: "INFO"          # Logging level: DEBUG, INFO, WARNING, ERROR

# RTL-SDR Configuration
sdr:
  device_index: 0            # RTL-SDR device index
  sample_rate: 2048000        # Sample rate in Hz (2.048 MHz)
  gain: 49.6                 # Gain in dB (or 'auto' for automatic gain)

# Audio Configuration
audio:
  sample_rate: 48000         # Audio sample rate
  channels: 1                # Audio channels (1 = mono)
  chunk_size: 1024           # Audio chunk size
  device_name: ""           # Audio device name (empty = default device)

# Scanning Configuration
scanning:
  delay: 0.1                 # Delay between frequency changes (seconds)
  squelch_threshold: -50.0   # Signal threshold in dBm
  transmission_timeout: 5.0  # Seconds to wait for transmission end

# Priority Scanning Configuration
priority_scanning:
  enabled: true              # Enable priority-based scanning
  multiplier: 2.0            # Priority weight multiplier (1.0-10.0)
  min_priority_weight: 0.5   # Minimum weight for low priority frequencies
  scan_mode: "weighted"      # "weighted" or "round_robin"

# Audio Recording
recording:
  directory: "recordings"    # Directory for audio recordings
  format: "wav"             # Recording format: "wav" or "mp3" (mp3 requires lameenc)
  mp3_bitrate: "192k"       # MP3 bitrate (if format is mp3): "128k", "192k", "256k", "320k"

# DSP Configuration (Audio Processing)
dsp:
  noise_gate:
    enabled: true
    threshold: -40.0         # Noise gate threshold in dB
  agc:
    enabled: true
    target_level: -20.0      # AGC target level in dB
  noise_reduction:
    enabled: false           # Enable noise reduction (CPU intensive)
  equalizer:
    enabled: false           # Enable audio equalizer
```

### Environment Variables (Optional)

You can also override any setting using environment variables with the `sdr2zello_` prefix. Environment variables take precedence over the config file. For example:

```bash
export sdr2zello_HOST=0.0.0.0
export sdr2zello_PORT=8080
```

### Default Frequencies

The application comes pre-configured with common frequencies:

- **Aviation (AM)**: 118.0, 121.5, 122.8 MHz
- **Amateur Radio (FM)**: 145.5, 446.0 MHz
- **Marine VHF (FM)**: 155.16 MHz
- **Weather Radio (FM)**: 162.55 MHz

## 🔧 System Setup

### RTL-SDR Driver Installation

#### Linux (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install rtl-sdr librtlsdr-dev
# Block kernel driver
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee -a /etc/modprobe.d/blacklist-rtl.conf
```


### Virtual Audio Cable Setup

**Automatic Installation (Recommended):**
The setup script can automatically install and configure virtual audio cable software:

```bash
python3 setup.py
# Answer 'y' when prompted about virtual audio cable installation
```

**Manual Installation:**

#### Linux - PulseAudio:
- **Automatic**: Setup script creates virtual sinks using pactl
- **Manual**:
  ```bash
  pactl load-module module-null-sink sink_name=sdr2zello
  pactl load-module module-loopback source=sdr2zello.monitor sink=@DEFAULT_SINK@
  ```

## 📱 Usage

### Web Interface

1. **Open browser** and navigate to `http://localhost:8000`
2. **Add frequencies**: Click "Add Frequency" and enter details
3. **Start scanning**: Click the "Start" button in the status bar
4. **Monitor activity**: Watch the real-time signal monitor and transmission log
5. **Configure audio**: Toggle audio output and check Zello integration

### Frequency Management

- **Add frequency**: Specify frequency in MHz, modulation (AM/FM), description, priority, group, and tags
- **Enable/disable**: Toggle frequencies in the scan list
- **Import/export**: Backup and share frequency lists as JSON files
- **Priority scanning**: Higher priority frequencies are scanned more often (0-100 scale)
- **Groups & tags**: Organize frequencies by group (e.g., "Aviation", "Ham") and custom tags
- **Filtering**: Filter frequencies by group, tag, or enabled status

### Zello Integration

The setup script provides automatic configuration instructions for your platform:

**Quick Setup:**
1. **Install Zello**: Download from [zello.com](https://zello.com/app) or app stores
2. **Run setup script**: Includes detailed Zello configuration for your OS
3. **Configure audio input**:
   - Set microphone to "sdr2zello" virtual device in Zello settings
4. **Test**: Enable audio output in sdr2zello, transmissions will route to Zello

**Manual Configuration:**
- Open Zello settings → Audio/Devices
- Set microphone input to virtual audio cable
- Ensure push-to-talk is properly configured
- Test with sdr2zello scanner running

## 🔍 Troubleshooting

### Common Issues

#### "No RTL-SDR device found"
- Check USB connection and drivers
- Verify device with `rtl_test` command
- Try different USB port
- Check device permissions (Linux)

#### "PyAudio not available"
- Install system audio libraries:
  ```bash
  sudo apt-get install portaudio19-dev python3-pyaudio
  ```

#### Web interface not loading
- Check if port 8000 is available
- Try different port in `config.yaml` file
- Check firewall settings
- Look for error messages in console

#### No audio in Zello
- Verify virtual audio cable installation
- Check Zello audio input settings
- Test audio routing with other applications
- Enable audio output in sdr2zello interface

### Debug Mode

Enable debug logging for detailed troubleshooting:

```yaml
# In config.yaml file
server:
  debug: true
  log_level: "DEBUG"
```

Or using environment variable:
```bash
export sdr2zello_DEBUG=true
export sdr2zello_LOG_LEVEL=DEBUG
```

Check logs in the `logs/` directory for detailed error information.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   RTL-SDR       │───▶│   sdr2zello     │───▶│   Zello App     │
│   USB Dongle    │    │   Application   │    │   (PTT Client)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Web Interface  │
                       │  (localhost:8000) │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Mobile/Tablet  │
                       │  Remote Control │
                       └─────────────────┘
```

### Component Overview

- **SDR Manager**: Handles RTL-SDR communication and frequency scanning with smart algorithms
- **Audio Manager**: Processes transmission audio with DSP (noise gate, AGC, equalizer) and routes to Zello
- **Web Server**: FastAPI-based REST API and WebSocket server
- **Database**: SQLite storage for frequencies, logs, and configuration
- **Frontend**: Real-time web interface with signal visualization and mobile support
- **Health Monitor**: System metrics, service status, and performance tracking

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pytest black flake8
   ```
4. Run tests: `pytest`
5. Format code: `black src/`
6. Submit pull request

## 📄 License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0) - see the [LICENSE](LICENSE) file for details.

## ⚠️ Legal Notice

**Important**: This software is for educational and authorized use only. Users are responsible for:

- Complying with local laws and regulations regarding radio frequency monitoring
- Respecting privacy and only monitoring legally permitted transmissions
- Following amateur radio licensing requirements where applicable
- Not using this software for illegal surveillance or interception

## 🙏 Acknowledgments

- **RTL-SDR community** for excellent hardware and driver support
- **FastAPI** for the fantastic web framework
- **Zello** for the versatile PTT platform
- **Contributors** and testers who help improve this project

## 📞 Support

- **Documentation**: Check this README and inline code comments
- **Issues**: Report bugs and feature requests on GitHub Issues
- **Discussions**: Join community discussions in GitHub Discussions
- **Email**: Contact maintainers for security issues

---

**Made with ❤️ for the radio monitoring community**
/**
 * sdr2zello Frontend Application
 * Handles UI interactions, WebSocket communication, and real-time updates
 */

class SDR2ZelloApp {
    constructor() {
        this.websocket = null;
        this.isConnected = false;
        this.frequencies = [];
        this.transmissions = [];
        this.scannerRunning = false;
        this.audioEnabled = true;
        this.currentFrequency = 0;

        // Chart context for signal monitor
        this.signalCanvas = null;
        this.signalCtx = null;
        this.signalData = [];
        this.maxSignalData = 200;
        this.peakSignal = -100;
        this.signalSum = 0;
        this.signalCount = 0;
        this.activeFrequencies = new Map(); // frequency -> {strength, timestamp, friendly_name}
        this.squelchThreshold = -50;
        
        // Logs pagination
        this.logsPage = 1;
        this.logsPerPage = 20;
        this.logsSortBy = 'newest';
        this.logsDateFilter = null;

        this.init();
    }

    async init() {
        console.log('Initializing sdr2zello App...');

        // Initialize UI elements
        this.initializeElements();
        this.setupEventListeners();
        
        // Initialize signal monitor only if canvas exists
        this.signalCanvas = document.getElementById('signal-canvas');
        if (this.signalCanvas) {
            this.signalCtx = this.signalCanvas.getContext('2d');
            this.setupCanvas();
            this.initializeSignalMonitor();
            this.setupMonitorControls();
        }

        // Connect WebSocket
        this.connectWebSocket();

        // Load initial data (only if elements exist)
        if (this.elements.frequencyList) {
            await this.loadFrequencies();
            this.setupFrequencyFilters();
        }
        // Always load transmissions for dashboard stats and recent transmissions
        await this.loadTransmissions();
        if (this.elements.scannerStatus || this.elements.sdrStatus) {
            await this.updateStatus();
        }
        const versionGrid = document.getElementById('version-grid');
        if (versionGrid) {
            await this.loadVersions();
        }

        console.log('sdr2zello App initialized');
    }

    initializeElements() {
        // Cache frequently used DOM elements
        this.elements = {
            scannerStatus: document.getElementById('scanner-status'),
            scannerToggle: document.getElementById('scanner-toggle'),
            audioStatus: document.getElementById('audio-status'),
            audioToggle: document.getElementById('audio-toggle'),
            sdrStatus: document.getElementById('sdr-status'),
            currentFrequency: document.getElementById('current-frequency'),
            frequencyList: document.getElementById('frequency-list'),
            transmissionLog: document.getElementById('transmission-log'),
            transmissionAlert: document.getElementById('transmission-alert'),
            alertFrequency: document.getElementById('alert-frequency'),
            alertSignalStrength: document.getElementById('alert-signal-strength'),
            totalTransmissions: document.getElementById('total-transmissions'),
            activeFrequencies: document.getElementById('active-frequencies'),
            avgSignal: document.getElementById('avg-signal'),
            scanTime: document.getElementById('scan-time'),
            logFilter: document.getElementById('log-filter')
        };
    }

    setupEventListeners() {
        // Scanner controls
        if (this.elements.scannerToggle) {
            this.elements.scannerToggle.addEventListener('click', () => this.toggleScanner());
        }
        if (this.elements.audioToggle) {
            this.elements.audioToggle.addEventListener('click', () => this.toggleAudio());
        }

        // Frequency management
        const addFreqBtn = document.getElementById('add-frequency');
        if (addFreqBtn) {
            addFreqBtn.addEventListener('click', () => this.showAddFrequencyModal());
        }
        const importFreqBtn = document.getElementById('import-frequencies');
        if (importFreqBtn) {
            importFreqBtn.addEventListener('click', () => this.importFrequencies());
        }
        const exportFreqBtn = document.getElementById('export-frequencies');
        if (exportFreqBtn) {
            exportFreqBtn.addEventListener('click', () => this.exportFrequencies());
        }

        // Settings management
        const settingsBtn = document.getElementById('settings-btn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => this.showSettingsModal());
        }
        const mobileSettingsBtn = document.getElementById('mobile-settings-btn');
        if (mobileSettingsBtn) {
            mobileSettingsBtn.addEventListener('click', () => this.showSettingsModal());
        }

        // Version management
        const refreshVersionsBtn = document.getElementById('refresh-versions');
        if (refreshVersionsBtn) {
            refreshVersionsBtn.addEventListener('click', () => this.refreshVersions());
        }

        // Log controls
        const clearLogsBtn = document.getElementById('clear-logs');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', () => this.clearLogs());
        }
        if (this.elements.logFilter) {
            this.elements.logFilter.addEventListener('change', () => {
                this.logsPage = 1; // Reset to first page
                this.filterLogs();
            });
        }

        // Setup log controls if on logs page
        if (document.getElementById('log-sort')) {
            this.setupLogControls();
        }

        // Setup refresh stats button
        const refreshStatsBtn = document.getElementById('refresh-stats');
        if (refreshStatsBtn) {
            refreshStatsBtn.addEventListener('click', async () => {
                await this.loadTransmissions();
                this.updateStatistics();
                this.showToast('Statistics refreshed', 'success');
            });
        }

        // Mobile navigation
        this.setupMobileNavigation();

        // Touch interactions
        this.setupTouchInteractions();

        // Modal close events
        document.querySelectorAll('.close').forEach(closeBtn => {
            closeBtn.addEventListener('click', (e) => {
                const modal = e.target.closest('.modal');
                if (modal) this.closeModal(modal.id);
            });
        });

        // Click outside modal to close
        window.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                this.closeModal(e.target.id);
            }
        });

        // Auto-refresh data every 10 seconds (only if elements exist)
        setInterval(() => {
            if (this.elements.scannerStatus || this.elements.sdrStatus) {
                this.updateStatus();
            }
        }, 10000);
        setInterval(() => {
            if (this.elements.transmissionLog) {
                this.loadTransmissions();
            }
        }, 30000);

        // Setup settings tabs
        this.setupSettingsTabs();

        // Setup range input updates
        this.setupRangeInputs();
    }

    setupCanvas() {
        if (!this.signalCanvas) return;
        
        // Make canvas responsive
        const container = this.signalCanvas.parentElement;
        const resizeCanvas = () => {
            const rect = container.getBoundingClientRect();
            this.signalCanvas.width = rect.width - 30; // Account for padding
            this.signalCanvas.height = 400;
        };
        
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);
    }

    initializeSignalMonitor() {
        if (!this.signalCanvas || !this.signalCtx) {
            return; // Canvas not available on this page
        }

        // Start signal monitor animation
        this.animateSignalMonitor();
    }

    setupMonitorControls() {
        const clearBtn = document.getElementById('clear-signal-data');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearSignalData());
        }
    }

    clearSignalData() {
        this.signalData = [];
        this.peakSignal = -100;
        this.signalSum = 0;
        this.signalCount = 0;
        this.activeFrequencies.clear();
        this.updateActiveFrequencies();
        this.showToast('Signal data cleared', 'info');
    }

    dismissAlert() {
        if (this.elements.transmissionAlert) {
            this.elements.transmissionAlert.classList.add('hidden');
        }
    }

    connectWebSocket() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/ws`;

        try {
            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.showToast('Connected to sdr2zello', 'success');
            };

            this.websocket.onmessage = (event) => {
                this.handleWebSocketMessage(JSON.parse(event.data));
            };

            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.isConnected = false;
                this.showToast('Disconnected from server', 'warning');

                // Attempt to reconnect after 5 seconds
                setTimeout(() => this.connectWebSocket(), 5000);
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.showToast('Connection error', 'error');
            };
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'signal_strength':
                this.updateSignalStrength(data);
                break;
            case 'transmission_start':
                this.handleTransmissionStart(data);
                break;
            case 'transmission_end':
                this.handleTransmissionEnd(data);
                break;
            case 'scanner_status':
                this.updateScannerStatus(data);
                break;
            case 'frequency_update':
                this.updateCurrentFrequency(data.frequency);
                break;
            default:
                console.log('Unknown WebSocket message:', data);
        }
    }

    updateSignalStrength(data) {
        // Add signal data point
        this.signalData.push({
            frequency: data.frequency,
            strength: data.signal_strength,
            timestamp: Date.now()
        });

        // Keep only recent data
        if (this.signalData.length > this.maxSignalData) {
            const removed = this.signalData.shift();
            // Update sum if removing data
            if (removed) {
                this.signalSum -= removed.strength;
                this.signalCount--;
            }
        }

        // Update statistics
        this.signalSum += data.signal_strength;
        this.signalCount++;
        
        if (data.signal_strength > this.peakSignal) {
            this.peakSignal = data.signal_strength;
        }

        // Update signal info displays
        this.updateSignalInfo(data.signal_strength);

        // Track active frequencies
        if (data.signal_strength > this.squelchThreshold) {
            const freq = this.frequencies.find(f => Math.abs(f.frequency - data.frequency) < 1000);
            this.activeFrequencies.set(data.frequency, {
                strength: data.signal_strength,
                timestamp: Date.now(),
                friendly_name: freq ? freq.friendly_name : null,
                frequency: data.frequency
            });
        } else {
            // Remove if below threshold for more than 2 seconds
            const active = this.activeFrequencies.get(data.frequency);
            if (active && Date.now() - active.timestamp > 2000) {
                this.activeFrequencies.delete(data.frequency);
            }
        }

        this.updateActiveFrequencies();
    }

    updateSignalInfo(currentSignal) {
        const currentEl = document.getElementById('current-signal');
        const peakEl = document.getElementById('peak-signal');
        const avgEl = document.getElementById('avg-signal');
        const monitorFreqEl = document.getElementById('monitor-current-frequency');

        if (currentEl) {
            currentEl.textContent = `${currentSignal.toFixed(1)} dBm`;
            // Color code based on signal strength
            if (currentSignal > -30) {
                currentEl.style.color = '#4CAF50';
            } else if (currentSignal > -60) {
                currentEl.style.color = '#FFC107';
            } else {
                currentEl.style.color = '#f44336';
            }
        }

        if (peakEl) {
            peakEl.textContent = `${this.peakSignal.toFixed(1)} dBm`;
        }

        if (avgEl && this.signalCount > 0) {
            const avg = this.signalSum / this.signalCount;
            avgEl.textContent = `${avg.toFixed(1)} dBm`;
        }

        if (monitorFreqEl && this.currentFrequency) {
            const freq = this.frequencies.find(f => Math.abs(f.frequency - this.currentFrequency) < 1000);
            const freqDisplay = freq && freq.friendly_name ? 
                `${freq.friendly_name} (${(this.currentFrequency / 1e6).toFixed(3)} MHz)` :
                `${(this.currentFrequency / 1e6).toFixed(3)} MHz`;
            monitorFreqEl.textContent = freqDisplay;
        }
    }

    updateActiveFrequencies() {
        const container = document.getElementById('active-frequencies-list');
        if (!container) return;

        if (this.activeFrequencies.size === 0) {
            container.innerHTML = `
                <div class="no-active-frequencies">
                    <i class="fas fa-info-circle"></i>
                    <p>No active frequencies detected</p>
                </div>
            `;
            return;
        }

        const sortedFreqs = Array.from(this.activeFrequencies.entries())
            .sort((a, b) => b[1].strength - a[1].strength);

        container.innerHTML = sortedFreqs.map(([freq, data]) => {
            const displayName = data.friendly_name || `${(freq / 1e6).toFixed(3)} MHz`;
            const signalClass = data.strength > -30 ? 'strong' : data.strength > -60 ? 'medium' : 'weak';
            return `
                <div class="active-frequency-item active">
                    <div class="active-frequency-info">
                        <div class="active-frequency-name">${this.escapeHtml(displayName)}</div>
                        <div class="active-frequency-details">
                            <span>${(freq / 1e6).toFixed(3)} MHz</span>
                            <span class="active-frequency-signal">
                                <span class="signal-indicator"></span>
                                ${data.strength.toFixed(1)} dBm
                            </span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    handleTransmissionStart(data) {
        console.log('Transmission started:', data);

        // Show transmission alert
        this.elements.transmissionAlert.classList.remove('hidden');
        // Find frequency friendly name
        const freq = this.frequencies.find(f => Math.abs(f.frequency - data.frequency) < 1000);
        const freqDisplay = freq && freq.friendly_name ? 
            `${freq.friendly_name} (${(data.frequency / 1e6).toFixed(3)} MHz)` :
            `${(data.frequency / 1e6).toFixed(3)} MHz`;
        this.elements.alertFrequency.textContent = freqDisplay;
        this.elements.alertSignalStrength.textContent = `${data.signal_strength.toFixed(1)} dBm`;

        // Play notification sound (if available)
        this.playNotificationSound();
    }

    handleTransmissionEnd(data) {
        console.log('Transmission ended:', data);

        // Hide transmission alert
        setTimeout(() => {
            this.elements.transmissionAlert.classList.add('hidden');
        }, 2000);

        // Reload transmission log
        this.loadTransmissions();

        // Update statistics
        this.updateStatistics();
    }

    updateScannerStatus(data) {
        this.scannerRunning = data.is_scanning;
        this.updateScannerUI();

        if (data.current_frequency) {
            this.updateCurrentFrequency(data.current_frequency);
        }
    }

    updateCurrentFrequency(frequency) {
        this.currentFrequency = frequency;
        // Find frequency friendly name
        const freq = this.frequencies.find(f => Math.abs(f.frequency - frequency) < 1000);
        const freqDisplay = freq && freq.friendly_name ? 
            `${freq.friendly_name} (${(frequency / 1e6).toFixed(3)} MHz)` :
            `${(frequency / 1e6).toFixed(3)} MHz`;
        this.elements.currentFrequency.textContent = freqDisplay;
    }

    animateSignalMonitor() {
        const animate = () => {
            this.drawSignalMonitor();
            requestAnimationFrame(animate);
        };
        animate();
    }

    drawSignalMonitor() {
        const canvas = this.signalCanvas;
        const ctx = this.signalCtx;
        if (!canvas || !ctx) return;
        
        const width = canvas.width;
        const height = canvas.height;

        // Clear canvas with gradient background
        const gradient = ctx.createLinearGradient(0, 0, 0, height);
        gradient.addColorStop(0, '#0a0a0a');
        gradient.addColorStop(1, '#000000');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, width, height);

        if (this.signalData.length === 0) {
            // Draw "No Data" message
            ctx.fillStyle = '#666';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Waiting for signal data...', width / 2, height / 2);
            ctx.textAlign = 'left';
            return;
        }

        // Draw grid with better styling
        ctx.strokeStyle = '#222';
        ctx.lineWidth = 1;

        // Horizontal lines (signal strength levels)
        const signalLevels = [0, -25, -50, -75, -100];
        signalLevels.forEach((level, i) => {
            const y = (i / (signalLevels.length - 1)) * height;
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
            
            // Draw level labels
            ctx.fillStyle = '#666';
            ctx.font = '10px Arial';
            ctx.fillText(`${level}`, 5, y - 2);
        });

        // Vertical lines (time markers)
        for (let i = 0; i <= 10; i++) {
            const x = (i / 10) * width;
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();
        }

        // Draw squelch threshold line
        const minSignal = -100;
        const maxSignal = 0;
        const signalRange = maxSignal - minSignal;
        const squelchY = height - ((this.squelchThreshold - minSignal) / signalRange) * height;
        ctx.strokeStyle = 'rgba(255, 193, 7, 0.6)';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(0, squelchY);
        ctx.lineTo(width, squelchY);
        ctx.stroke();
        ctx.setLineDash([]);
        
        // Draw squelch label
        ctx.fillStyle = 'rgba(255, 193, 7, 0.8)';
        ctx.font = '10px Arial';
        ctx.fillText(`Squelch: ${this.squelchThreshold} dBm`, width - 120, squelchY - 5);

        // Draw signal strength data with gradient
        if (this.signalData.length > 1) {
            // Create gradient for signal line
            const lineGradient = ctx.createLinearGradient(0, 0, 0, height);
            lineGradient.addColorStop(0, '#4CAF50');
            lineGradient.addColorStop(0.5, '#8BC34A');
            lineGradient.addColorStop(1, '#FFC107');
            
            ctx.strokeStyle = lineGradient;
            ctx.lineWidth = 2.5;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.beginPath();

            this.signalData.forEach((point, index) => {
                const x = (index / (this.maxSignalData - 1)) * width;
                const normalizedSignal = (point.strength - minSignal) / signalRange;
                const y = height - (normalizedSignal * height);

                if (index === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            });

            ctx.stroke();

            // Draw filled area under curve
            if (this.signalData.length > 0) {
                const areaGradient = ctx.createLinearGradient(0, 0, 0, height);
                areaGradient.addColorStop(0, 'rgba(76, 175, 80, 0.3)');
                areaGradient.addColorStop(1, 'rgba(76, 175, 80, 0.05)');
                
                ctx.fillStyle = areaGradient;
                ctx.beginPath();
                ctx.moveTo(0, height);
                
                this.signalData.forEach((point, index) => {
                    const x = (index / (this.maxSignalData - 1)) * width;
                    const normalizedSignal = (point.strength - minSignal) / signalRange;
                    const y = height - (normalizedSignal * height);
                    ctx.lineTo(x, y);
                });
                
                ctx.lineTo(width, height);
                ctx.closePath();
                ctx.fill();
            }

            // Draw current value indicator
            if (this.signalData.length > 0) {
                const lastPoint = this.signalData[this.signalData.length - 1];
                const x = ((this.signalData.length - 1) / (this.maxSignalData - 1)) * width;
                const normalizedSignal = (lastPoint.strength - minSignal) / signalRange;
                const y = height - (normalizedSignal * height);
                
                // Draw circle at current point
                ctx.fillStyle = '#4CAF50';
                ctx.beginPath();
                ctx.arc(x, y, 4, 0, Math.PI * 2);
                ctx.fill();
                
                // Draw current value text
                ctx.fillStyle = '#fff';
                ctx.font = 'bold 12px Arial';
                ctx.textAlign = 'right';
                ctx.fillText(`${lastPoint.strength.toFixed(1)} dBm`, x - 8, y - 8);
                ctx.textAlign = 'left';
            }
        }

        // Draw title and axis labels
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 14px Arial';
        ctx.textAlign = 'left';
        ctx.fillText('Signal Strength (dBm)', 10, 20);
        
        // Update squelch line position in overlay
        const squelchLine = document.getElementById('squelch-line');
        if (squelchLine) {
            squelchLine.style.top = `${squelchY}px`;
        }
    }

    async toggleScanner() {
        try {
            // Add haptic feedback
            this.triggerHapticFeedback('medium');

            const endpoint = this.scannerRunning ? '/api/v1/scanner/stop' : '/api/v1/scanner/start';
            const response = await fetch(endpoint, { method: 'POST' });

            if (response.ok) {
                const data = await response.json();
                this.showToast(data.message, 'success');
                await this.updateStatus();
            } else {
                throw new Error('Failed to toggle scanner');
            }
        } catch (error) {
            console.error('Error toggling scanner:', error);
            this.showToast('Error controlling scanner', 'error');
        }
    }

    async toggleAudio() {
        try {
            const endpoint = this.audioEnabled ? '/api/v1/audio/disable' : '/api/v1/audio/enable';
            const response = await fetch(endpoint, { method: 'POST' });

            if (response.ok) {
                const data = await response.json();
                this.showToast(data.message, 'success');
                await this.updateStatus();
            } else {
                throw new Error('Failed to toggle audio');
            }
        } catch (error) {
            console.error('Error toggling audio:', error);
            this.showToast('Error controlling audio', 'error');
        }
    }

    async updateStatus() {
        try {
            // Get scanner status
            const scannerResponse = await fetch('/api/v1/scanner/status');
            if (scannerResponse.ok) {
                const scannerData = await scannerResponse.json();
                this.scannerRunning = scannerData.is_scanning;
                this.updateScannerUI();

                if (scannerData.current_frequency) {
                    this.updateCurrentFrequency(scannerData.current_frequency);
                }

                // Update SDR status
                this.elements.sdrStatus.textContent = scannerData.sdr_connected ? 'CONNECTED' : 'DISCONNECTED';
                this.elements.sdrStatus.className = `status ${scannerData.sdr_connected ? 'enabled' : 'disabled'}`;
            }

            // Get audio status
            const audioResponse = await fetch('/api/v1/audio/status');
            if (audioResponse.ok) {
                const audioData = await audioResponse.json();
                this.audioEnabled = audioData.audio_enabled;
                this.updateAudioUI();
            }
        } catch (error) {
            console.error('Error updating status:', error);
        }
    }

    updateScannerUI() {
        this.elements.scannerStatus.textContent = this.scannerRunning ? 'RUNNING' : 'STOPPED';
        this.elements.scannerStatus.className = `status ${this.scannerRunning ? 'running' : 'stopped'}`;

        // Update button text - check if it has btn-text span or just text content
        const btnText = this.elements.scannerToggle.querySelector('.btn-text');
        const newText = this.scannerRunning ? 'Stop' : 'Start';

        if (btnText) {
            btnText.textContent = newText;
        } else {
            this.elements.scannerToggle.textContent = newText;
        }
    }

    updateAudioUI() {
        this.elements.audioStatus.textContent = this.audioEnabled ? 'ENABLED' : 'DISABLED';
        this.elements.audioStatus.className = `status ${this.audioEnabled ? 'enabled' : 'disabled'}`;

        // Update button text - check if it has btn-text span or just text content
        const btnText = this.elements.audioToggle.querySelector('.btn-text');
        const newText = this.audioEnabled ? 'Disable' : 'Enable';

        if (btnText) {
            btnText.textContent = newText;
        } else {
            this.elements.audioToggle.textContent = newText;
        }
    }

    async loadFrequencies() {
        try {
            const response = await fetch('/api/v1/frequencies');
            if (response.ok) {
                this.frequencies = await response.json();
                this.renderFrequencies();
                this.updateLogFilter();
            }
        } catch (error) {
            console.error('Error loading frequencies:', error);
            this.showToast('Error loading frequencies', 'error');
        }
    }

    renderFrequencies(filteredFrequencies = null) {
        const freqsToRender = filteredFrequencies || this.frequencies;
        
        // Update statistics
        this.updateFrequencyStats();

        const html = freqsToRender.map(freq => {
            const displayName = freq.friendly_name || `${(freq.frequency / 1e6).toFixed(3)} MHz`;
            const freqDisplay = freq.friendly_name ? `${(freq.frequency / 1e6).toFixed(3)} MHz` : '';
            return `
            <div class="frequency-item ${!freq.enabled ? 'disabled' : ''}">
                <div class="frequency-header">
                    <span class="frequency-value">${this.escapeHtml(displayName)}</span>
                    <span class="frequency-modulation">${freq.modulation}</span>
                </div>
                ${freq.friendly_name && freqDisplay ? `<div class="frequency-details"><span class="frequency-freq">${freqDisplay}</span></div>` : ''}
                ${freq.description ? `<div class="frequency-description">${this.escapeHtml(freq.description)}</div>` : ''}
                ${freq.group ? `<div class="frequency-group"><i class="fas fa-tag"></i> ${this.escapeHtml(freq.group)}</div>` : ''}
                <div class="frequency-actions">
                    <button class="btn btn-info" onclick="app.editFrequency(${freq.id})">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-${freq.enabled ? 'warning' : 'success'}"
                            onclick="app.toggleFrequency(${freq.id}, ${!freq.enabled})">
                        <i class="fas fa-${freq.enabled ? 'pause' : 'play'}"></i>
                    </button>
                    <button class="btn btn-danger" onclick="app.deleteFrequency(${freq.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        }).join('');

        this.elements.frequencyList.innerHTML = html || '<div class="no-frequencies"><p>No frequencies found</p></div>';
    }

    updateFrequencyStats() {
        const total = this.frequencies.length;
        const enabled = this.frequencies.filter(f => f.enabled).length;
        const disabled = total - enabled;
        const groups = new Set(this.frequencies.filter(f => f.group).map(f => f.group)).size;

        const totalEl = document.getElementById('total-frequencies');
        const enabledEl = document.getElementById('enabled-frequencies-count');
        const disabledEl = document.getElementById('disabled-frequencies-count');
        const groupsEl = document.getElementById('total-groups');

        if (totalEl) totalEl.textContent = total;
        if (enabledEl) enabledEl.textContent = enabled;
        if (disabledEl) disabledEl.textContent = disabled;
        if (groupsEl) groupsEl.textContent = groups;

        // Update group filter
        const groupFilter = document.getElementById('frequency-group-filter');
        if (groupFilter) {
            const groups = [...new Set(this.frequencies.filter(f => f.group).map(f => f.group))];
            const currentValue = groupFilter.value;
            groupFilter.innerHTML = '<option value="">All Groups</option>' +
                groups.map(g => `<option value="${this.escapeHtml(g)}">${this.escapeHtml(g)}</option>`).join('');
            groupFilter.value = currentValue;
        }
    }

    setupFrequencyFilters() {
        const searchInput = document.getElementById('frequency-search');
        const groupFilter = document.getElementById('frequency-group-filter');
        const enableAllBtn = document.getElementById('enable-all-frequencies');
        const disableAllBtn = document.getElementById('disable-all-frequencies');

        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterFrequencies();
            });
        }

        if (groupFilter) {
            groupFilter.addEventListener('change', () => {
                this.filterFrequencies();
            });
        }

        if (enableAllBtn) {
            enableAllBtn.addEventListener('click', () => this.enableAllFrequencies());
        }

        if (disableAllBtn) {
            disableAllBtn.addEventListener('click', () => this.disableAllFrequencies());
        }
    }

    filterFrequencies() {
        const searchTerm = document.getElementById('frequency-search')?.value.toLowerCase() || '';
        const groupFilter = document.getElementById('frequency-group-filter')?.value || '';

        let filtered = this.frequencies;

        if (searchTerm) {
            filtered = filtered.filter(freq => {
                const freqStr = (freq.frequency / 1e6).toFixed(3);
                const friendlyName = (freq.friendly_name || '').toLowerCase();
                const description = (freq.description || '').toLowerCase();
                const group = (freq.group || '').toLowerCase();
                const tags = (freq.tags || '').toLowerCase();
                
                return freqStr.includes(searchTerm) ||
                       friendlyName.includes(searchTerm) ||
                       description.includes(searchTerm) ||
                       group.includes(searchTerm) ||
                       tags.includes(searchTerm);
            });
        }

        if (groupFilter) {
            filtered = filtered.filter(freq => freq.group === groupFilter);
        }

        this.renderFrequencies(filtered);
    }

    async enableAllFrequencies() {
        if (!confirm('Enable all frequencies?')) return;
        
        try {
            for (const freq of this.frequencies) {
                if (!freq.enabled) {
                    await fetch(`/api/v1/frequencies/${freq.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled: true })
                    });
                }
            }
            this.showToast('All frequencies enabled', 'success');
            await this.loadFrequencies();
        } catch (error) {
            console.error('Error enabling frequencies:', error);
            this.showToast('Error enabling frequencies', 'error');
        }
    }

    async disableAllFrequencies() {
        if (!confirm('Disable all frequencies?')) return;
        
        try {
            for (const freq of this.frequencies) {
                if (freq.enabled) {
                    await fetch(`/api/v1/frequencies/${freq.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled: false })
                    });
                }
            }
            this.showToast('All frequencies disabled', 'success');
            await this.loadFrequencies();
        } catch (error) {
            console.error('Error disabling frequencies:', error);
            this.showToast('Error disabling frequencies', 'error');
        }
    }
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    updateLogFilter() {
        const filterHtml = '<option value="">All Frequencies</option>' +
            this.frequencies.map(freq => {
                const displayName = freq.friendly_name || `${(freq.frequency / 1e6).toFixed(3)} MHz`;
                const suffix = freq.description ? ` - ${freq.description}` : '';
                return `<option value="${freq.frequency}">${displayName}${suffix}</option>`;
            }).join('');

        this.elements.logFilter.innerHTML = filterHtml;
    }

    async loadTransmissions() {
        try {
            const response = await fetch('/api/v1/transmissions?limit=50');
            if (response.ok) {
                this.transmissions = await response.json();
                // Only render if transmission log element exists
                if (this.elements.transmissionLog) {
                    this.renderTransmissions();
                }
                // Always update statistics (for dashboard)
                this.updateStatistics();
            }
        } catch (error) {
            console.error('Error loading transmissions:', error);
            // Only show error toast if on logs page
            if (this.elements.transmissionLog) {
                this.showToast('Error loading transmission log', 'error');
            }
        }
    }

    renderTransmissions() {
        // Only render if transmission log element exists
        if (!this.elements.transmissionLog) {
            return;
        }

        let filteredTransmissions = this.filterTransmissionsByFrequency();
        
        // Apply date filter
        if (this.logsDateFilter) {
            const filterDate = new Date(this.logsDateFilter);
            filterDate.setHours(0, 0, 0, 0);
            filteredTransmissions = filteredTransmissions.filter(trans => {
                const transDate = new Date(trans.timestamp);
                transDate.setHours(0, 0, 0, 0);
                return transDate.getTime() === filterDate.getTime();
            });
        }

        // Sort transmissions
        filteredTransmissions = this.sortTransmissions(filteredTransmissions);

        // Update log statistics
        this.updateLogStats(filteredTransmissions);

        // Paginate
        const totalPages = Math.ceil(filteredTransmissions.length / this.logsPerPage);
        const startIndex = (this.logsPage - 1) * this.logsPerPage;
        const endIndex = startIndex + this.logsPerPage;
        const paginatedTransmissions = filteredTransmissions.slice(startIndex, endIndex);

        // Update pagination controls
        this.updateLogPagination(totalPages, filteredTransmissions.length);

        const html = paginatedTransmissions.map(trans => {
            const date = new Date(trans.timestamp);
            const signalClass = trans.signal_strength > -30 ? 'strong' :
                               trans.signal_strength > -60 ? '' : 'weak';
            
            // Find frequency friendly name
            const freq = this.frequencies.find(f => Math.abs(f.frequency - trans.frequency) < 1000);
            const freqDisplay = freq && freq.friendly_name ? 
                `${this.escapeHtml(freq.friendly_name)} (${(trans.frequency / 1e6).toFixed(3)} MHz)` :
                `${(trans.frequency / 1e6).toFixed(3)} MHz`;
            
            // Zello status display
            let zelloStatusHtml = '';
            if (trans.zello_audio_enabled !== undefined) {
                if (!trans.zello_audio_enabled) {
                    zelloStatusHtml = '<span class="zello-status disabled"><i class="fas fa-volume-mute"></i> Audio Disabled</span>';
                } else if (trans.zello_sent !== undefined) {
                    if (trans.zello_success) {
                        zelloStatusHtml = '<span class="zello-status success"><i class="fas fa-check-circle"></i> Sent to Zello</span>';
                    } else if (trans.zello_sent) {
                        zelloStatusHtml = `<span class="zello-status error"><i class="fas fa-exclamation-circle"></i> Failed: ${trans.zello_error || 'Unknown error'}</span>`;
                    } else {
                        zelloStatusHtml = '<span class="zello-status not-sent"><i class="fas fa-times-circle"></i> Not Sent</span>';
                    }
                }
            }

            return `
                <div class="log-entry">
                    <div class="log-header">
                        <span class="log-frequency">${freqDisplay}</span>
                        <span class="log-time">${date.toLocaleTimeString()}</span>
                    </div>
                    <div class="log-signal ${signalClass}">
                        Signal: ${trans.signal_strength.toFixed(1)} dBm | Duration: ${trans.duration.toFixed(1)}s
                    </div>
                    ${zelloStatusHtml ? `<div class="log-zello">${zelloStatusHtml}</div>` : ''}
                    ${trans.description ? `<div class="log-description">${this.escapeHtml(trans.description)}</div>` : ''}
                </div>
            `;
        }).join('');

        this.elements.transmissionLog.innerHTML = html || '<p>No transmissions recorded</p>';
    }

    sortTransmissions(transmissions) {
        const sorted = [...transmissions];
        
        switch (this.logsSortBy) {
            case 'newest':
                return sorted.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            case 'oldest':
                return sorted.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            case 'signal-high':
                return sorted.sort((a, b) => b.signal_strength - a.signal_strength);
            case 'signal-low':
                return sorted.sort((a, b) => a.signal_strength - b.signal_strength);
            case 'duration-long':
                return sorted.sort((a, b) => (b.duration || 0) - (a.duration || 0));
            case 'duration-short':
                return sorted.sort((a, b) => (a.duration || 0) - (b.duration || 0));
            default:
                return sorted;
        }
    }

    updateLogStats(transmissions) {
        const total = transmissions.length;
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const todayCount = transmissions.filter(t => {
            const transDate = new Date(t.timestamp);
            return transDate >= today;
        }).length;
        
        const avgSignal = total > 0 ?
            transmissions.reduce((sum, t) => sum + t.signal_strength, 0) / total : 0;
        
        const totalDuration = transmissions.reduce((sum, t) => sum + (t.duration || 0), 0);
        const hours = Math.floor(totalDuration / 3600);
        const minutes = Math.floor((totalDuration % 3600) / 60);

        const totalEl = document.getElementById('log-total-count');
        const todayEl = document.getElementById('log-today-count');
        const avgEl = document.getElementById('log-avg-signal');
        const durationEl = document.getElementById('log-total-duration');

        if (totalEl) totalEl.textContent = total;
        if (todayEl) todayEl.textContent = todayCount;
        if (avgEl) avgEl.textContent = `${avgSignal.toFixed(1)} dBm`;
        if (durationEl) durationEl.textContent = `${hours}h ${minutes}m`;
    }

    updateLogPagination(totalPages, totalItems) {
        const currentPageEl = document.getElementById('log-current-page');
        const totalPagesEl = document.getElementById('log-total-pages');
        const showingEl = document.getElementById('log-showing-count');
        const prevBtn = document.getElementById('log-prev');
        const nextBtn = document.getElementById('log-next');

        if (currentPageEl) currentPageEl.textContent = this.logsPage;
        if (totalPagesEl) totalPagesEl.textContent = totalPages;
        if (showingEl) {
            const start = (this.logsPage - 1) * this.logsPerPage + 1;
            const end = Math.min(this.logsPage * this.logsPerPage, totalItems);
            showingEl.textContent = `${start}-${end}`;
        }

        if (prevBtn) {
            prevBtn.disabled = this.logsPage <= 1;
        }
        if (nextBtn) {
            nextBtn.disabled = this.logsPage >= totalPages;
        }
    }

    setupLogControls() {
        const sortSelect = document.getElementById('log-sort');
        const dateFilter = document.getElementById('log-date-filter');
        const prevBtn = document.getElementById('log-prev');
        const nextBtn = document.getElementById('log-next');
        const exportBtn = document.getElementById('export-logs');

        if (sortSelect) {
            sortSelect.addEventListener('change', (e) => {
                this.logsSortBy = e.target.value;
                this.logsPage = 1; // Reset to first page
                this.renderTransmissions();
            });
        }

        if (dateFilter) {
            dateFilter.addEventListener('change', (e) => {
                this.logsDateFilter = e.target.value || null;
                this.logsPage = 1; // Reset to first page
                this.renderTransmissions();
            });
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (this.logsPage > 1) {
                    this.logsPage--;
                    this.renderTransmissions();
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                const totalPages = Math.ceil(
                    this.filterTransmissionsByFrequency().length / this.logsPerPage
                );
                if (this.logsPage < totalPages) {
                    this.logsPage++;
                    this.renderTransmissions();
                }
            });
        }

        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportLogs());
        }
    }

    async exportLogs() {
        try {
            const filtered = this.filterTransmissionsByFrequency();
            const dataStr = JSON.stringify(filtered, null, 2);
            const dataBlob = new Blob([dataStr], { type: 'application/json' });

            const link = document.createElement('a');
            link.href = URL.createObjectURL(dataBlob);
            link.download = `sdr2zello_logs_${new Date().toISOString().split('T')[0]}.json`;
            link.click();

            this.showToast('Logs exported successfully', 'success');
        } catch (error) {
            console.error('Error exporting logs:', error);
            this.showToast('Error exporting logs', 'error');
        }
    }

    filterTransmissionsByFrequency() {
        const filterFreq = this.elements.logFilter?.value;
        if (!filterFreq) return this.transmissions;

        return this.transmissions.filter(trans =>
            Math.abs(trans.frequency - parseFloat(filterFreq)) < 1000
        );
    }

    filterLogs() {
        this.renderTransmissions();
    }

    updateStatistics() {
        const totalTransmissions = this.transmissions.length;
        const uniqueFrequencies = new Set(this.transmissions.map(t => t.frequency)).size;
        const avgSignal = totalTransmissions > 0 ?
            this.transmissions.reduce((sum, t) => sum + t.signal_strength, 0) / totalTransmissions : 0;

        // Update dashboard stats
        if (this.elements.totalTransmissions) {
            this.elements.totalTransmissions.textContent = totalTransmissions;
        }
        if (this.elements.activeFrequencies) {
            this.elements.activeFrequencies.textContent = uniqueFrequencies;
        }
        if (this.elements.avgSignal) {
            this.elements.avgSignal.textContent = `${avgSignal.toFixed(1)} dBm`;
        }

        // Update dashboard with additional info
        this.updateDashboardStats();
        this.updateRecentTransmissions();
    }

    async updateDashboardStats() {
        // Load recordings stats
        try {
            const response = await fetch('/api/v1/recordings?limit=1');
            if (response.ok) {
                const recordings = await response.json();
                const totalRecordings = recordings.length;
                const totalEl = document.getElementById('total-recordings');
                if (totalEl) {
                    totalEl.textContent = totalRecordings;
                }
            }
        } catch (error) {
            console.error('Error loading recordings stats:', error);
        }
    }

    updateRecentTransmissions() {
        const container = document.getElementById('recent-transmissions-list');
        if (!container) return;

        const recent = this.transmissions.slice(0, 5);
        
        if (recent.length === 0) {
            container.innerHTML = `
                <div class="no-transmissions">
                    <i class="fas fa-info-circle"></i>
                    <p>No recent transmissions</p>
                </div>
            `;
            return;
        }

        container.innerHTML = recent.map(trans => {
            const date = new Date(trans.timestamp);
            const freq = this.frequencies.find(f => Math.abs(f.frequency - trans.frequency) < 1000);
            const freqDisplay = freq && freq.friendly_name ? 
                `${freq.friendly_name} (${(trans.frequency / 1e6).toFixed(3)} MHz)` :
                `${(trans.frequency / 1e6).toFixed(3)} MHz`;
            
            return `
                <div class="recent-transmission-item">
                    <div class="recent-transmission-info">
                        <div class="recent-transmission-frequency">${this.escapeHtml(freqDisplay)}</div>
                        <div class="recent-transmission-details">
                            <span>${trans.signal_strength.toFixed(1)} dBm</span>
                            <span>${trans.duration.toFixed(1)}s</span>
                            ${trans.zello_success ? '<span class="zello-status-success"><i class="fas fa-check"></i> Sent</span>' : ''}
                        </div>
                    </div>
                    <div class="recent-transmission-time">${date.toLocaleTimeString()}</div>
                </div>
            `;
        }).join('');
    }

    showAddFrequencyModal() {
        document.getElementById('add-frequency-modal').style.display = 'block';
    }

    closeModal(modalId) {
        document.getElementById(modalId).style.display = 'none';
    }

    async addFrequency() {
        const frequency = parseFloat(document.getElementById('freq-value').value) * 1e6; // Convert MHz to Hz
        const modulation = document.getElementById('freq-modulation').value;
        const friendly_name = document.getElementById('freq-friendly-name').value.trim();
        const description = document.getElementById('freq-description').value;
        const enabled = document.getElementById('freq-enabled').checked;

        if (!frequency || frequency <= 0) {
            this.showToast('Please enter a valid frequency', 'error');
            return;
        }

        try {
            const response = await fetch('/api/v1/frequencies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frequency, modulation, friendly_name, description, enabled })
            });

            if (response.ok) {
                this.showToast('Frequency added successfully', 'success');
                this.closeModal('add-frequency-modal');
                await this.loadFrequencies();

                // Reset form
                document.getElementById('add-frequency-form').reset();
            } else {
                const error = await response.json();
                this.showToast(error.detail || 'Error adding frequency', 'error');
            }
        } catch (error) {
            console.error('Error adding frequency:', error);
            this.showToast('Error adding frequency', 'error');
        }
    }

    async editFrequency(id) {
        const freq = this.frequencies.find(f => f.id === id);
        if (!freq) {
            this.showToast('Frequency not found', 'error');
            return;
        }

        // Populate edit form
        document.getElementById('edit-freq-id').value = freq.id;
        document.getElementById('edit-freq-value').value = (freq.frequency / 1e6).toFixed(3);
        document.getElementById('edit-freq-friendly-name').value = freq.friendly_name || '';
        document.getElementById('edit-freq-modulation').value = freq.modulation || 'FM';
        document.getElementById('edit-freq-description').value = freq.description || '';
        document.getElementById('edit-freq-enabled').checked = freq.enabled !== false;

        // Show modal
        document.getElementById('edit-frequency-modal').style.display = 'block';
    }

    async updateFrequency() {
        const id = parseInt(document.getElementById('edit-freq-id').value);
        const friendly_name = document.getElementById('edit-freq-friendly-name').value.trim();
        const modulation = document.getElementById('edit-freq-modulation').value;
        const description = document.getElementById('edit-freq-description').value;
        const enabled = document.getElementById('edit-freq-enabled').checked;

        try {
            const response = await fetch(`/api/v1/frequencies/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ friendly_name, modulation, description, enabled })
            });

            if (response.ok) {
                this.showToast('Frequency updated successfully', 'success');
                this.closeModal('edit-frequency-modal');
                await this.loadFrequencies();
            } else {
                const error = await response.json();
                this.showToast(error.detail || 'Error updating frequency', 'error');
            }
        } catch (error) {
            console.error('Error updating frequency:', error);
            this.showToast('Error updating frequency', 'error');
        }
    }

    async deleteFrequency(id) {
        if (!confirm('Are you sure you want to delete this frequency?')) return;

        try {
            const response = await fetch(`/api/v1/frequencies/${id}`, { method: 'DELETE' });
            if (response.ok) {
                this.showToast('Frequency deleted successfully', 'success');
                await this.loadFrequencies();
            } else {
                throw new Error('Failed to delete frequency');
            }
        } catch (error) {
            console.error('Error deleting frequency:', error);
            this.showToast('Error deleting frequency', 'error');
        }
    }

    async toggleFrequency(id, enabled) {
        try {
            const response = await fetch(`/api/v1/frequencies/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });

            if (response.ok) {
                this.showToast(`Frequency ${enabled ? 'enabled' : 'disabled'}`, 'success');
                await this.loadFrequencies();
            } else {
                throw new Error('Failed to update frequency');
            }
        } catch (error) {
            console.error('Error updating frequency:', error);
            this.showToast('Error updating frequency', 'error');
        }
    }

    playNotificationSound() {
        // Create a simple beep sound using Web Audio API
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            oscillator.frequency.value = 800;
            oscillator.type = 'sine';

            gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);

            oscillator.start(audioCtx.currentTime);
            oscillator.stop(audioCtx.currentTime + 0.3);
        } catch (error) {
            console.log('Audio notification not available');
        }
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;

        document.getElementById('toast-container').appendChild(toast);

        // Auto remove after 4 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    // Export/Import functionality
    async exportFrequencies() {
        try {
            const response = await fetch('/api/v1/frequencies');
            if (response.ok) {
                const frequencies = await response.json();
                const dataStr = JSON.stringify(frequencies, null, 2);
                const dataBlob = new Blob([dataStr], { type: 'application/json' });

                const link = document.createElement('a');
                link.href = URL.createObjectURL(dataBlob);
                link.download = 'sdr2zello_frequencies.json';
                link.click();

                this.showToast('Frequencies exported successfully', 'success');
            }
        } catch (error) {
            console.error('Error exporting frequencies:', error);
            this.showToast('Error exporting frequencies', 'error');
        }
    }

    importFrequencies() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';

        input.onchange = async (event) => {
            const file = event.target.files[0];
            if (!file) return;

            try {
                const text = await file.text();
                const frequencies = JSON.parse(text);

                // Import each frequency
                for (const freq of frequencies) {
                    try {
                        await fetch('/api/v1/frequencies', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                frequency: freq.frequency,
                                modulation: freq.modulation || 'FM',
                                friendly_name: freq.friendly_name || '',
                                description: freq.description || '',
                                enabled: freq.enabled !== undefined ? freq.enabled : true,
                                priority: freq.priority || 0,
                                group: freq.group || '',
                                tags: freq.tags || ''
                            })
                        });
                    } catch (error) {
                        console.error('Error importing frequency:', freq, error);
                    }
                }

                this.showToast('Frequencies imported successfully', 'success');
                await this.loadFrequencies();
            } catch (error) {
                console.error('Error importing frequencies:', error);
                this.showToast('Error importing frequencies file', 'error');
            }
        };

        input.click();
    }

    async clearLogs() {
        if (!confirm('Are you sure you want to clear all transmission logs?')) return;

        try {
            const response = await fetch('/api/v1/maintenance/cleanup?days=0', { method: 'POST' });
            if (response.ok) {
                this.showToast('Transmission logs cleared', 'success');
                await this.loadTransmissions();
            }
        } catch (error) {
            console.error('Error clearing logs:', error);
            this.showToast('Error clearing logs', 'error');
        }
    }

    // Settings Management Methods
    setupSettingsTabs() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const targetTab = button.dataset.tab;

                // Remove active class from all tabs and contents
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabContents.forEach(content => content.classList.remove('active'));

                // Add active class to clicked tab and corresponding content
                button.classList.add('active');
                document.getElementById(targetTab).classList.add('active');
            });
        });
    }

    setupRangeInputs() {
        const rangeInputs = document.querySelectorAll('input[type="range"]');
        rangeInputs.forEach(input => {
            const outputId = input.id + '-value';
            const output = document.getElementById(outputId);
            if (output) {
                // Update output value when range changes
                input.addEventListener('input', () => {
                    output.textContent = input.value;
                });
            }
        });
    }

    setupMobileNavigation() {
        const mobileNavToggle = document.getElementById('mobile-nav-toggle');
        const mobileNavMenu = document.getElementById('mobile-nav-menu');
        const mobileNavLinks = document.querySelectorAll('.mobile-nav-link');

        if (mobileNavToggle && mobileNavMenu) {
            // Toggle mobile menu
            mobileNavToggle.addEventListener('click', () => {
                this.toggleMobileMenu();
            });

            // Handle mobile navigation links
            mobileNavLinks.forEach(link => {
                link.addEventListener('click', (e) => {
                    // If it's an anchor link, handle smooth scrolling
                    if (link.getAttribute('href') && link.getAttribute('href').startsWith('#')) {
                        e.preventDefault();
                        const targetId = link.getAttribute('href').substring(1);
                        this.scrollToSection(targetId);
                        this.closeMobileMenu();
                    }
                });
            });

            // Close mobile menu when clicking outside
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.mobile-nav') && mobileNavMenu.classList.contains('active')) {
                    this.closeMobileMenu();
                }
            });

            // Close mobile menu on resize if it gets too wide
            window.addEventListener('resize', () => {
                if (window.innerWidth > 768 && mobileNavMenu.classList.contains('active')) {
                    this.closeMobileMenu();
                }
            });
        }
    }

    toggleMobileMenu() {
        const mobileNavMenu = document.getElementById('mobile-nav-menu');
        const mobileNavToggle = document.getElementById('mobile-nav-toggle');

        if (mobileNavMenu && mobileNavToggle) {
            const isActive = mobileNavMenu.classList.contains('active');

            if (isActive) {
                this.closeMobileMenu();
            } else {
                this.openMobileMenu();
            }
        }
    }

    openMobileMenu() {
        const mobileNavMenu = document.getElementById('mobile-nav-menu');
        const mobileNavToggle = document.getElementById('mobile-nav-toggle');

        if (mobileNavMenu && mobileNavToggle) {
            mobileNavMenu.classList.add('active');
            mobileNavToggle.classList.add('active');
            document.body.style.overflow = 'hidden'; // Prevent background scrolling
        }
    }

    closeMobileMenu() {
        const mobileNavMenu = document.getElementById('mobile-nav-menu');
        const mobileNavToggle = document.getElementById('mobile-nav-toggle');

        if (mobileNavMenu && mobileNavToggle) {
            mobileNavMenu.classList.remove('active');
            mobileNavToggle.classList.remove('active');
            document.body.style.overflow = ''; // Restore scrolling
        }
    }

    scrollToSection(sectionId) {
        const section = document.getElementById(sectionId);
        if (section) {
            // Account for mobile navigation height
            const mobileNavHeight = document.querySelector('.mobile-nav')?.offsetHeight || 0;
            const offset = mobileNavHeight + 20; // Add some padding

            const elementPosition = section.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - offset;

            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
        }
    }

    setupTouchInteractions() {
        // Add touch feedback for buttons
        const buttons = document.querySelectorAll('.btn, .frequency-item, .version-item');

        buttons.forEach(button => {
            button.addEventListener('touchstart', (e) => {
                button.classList.add('touch-active');
            });

            button.addEventListener('touchend', (e) => {
                setTimeout(() => {
                    button.classList.remove('touch-active');
                }, 150);
            });

            button.addEventListener('touchcancel', (e) => {
                button.classList.remove('touch-active');
            });
        });

        // Add swipe gesture for mobile navigation
        this.setupSwipeGestures();

        // Optimize for touch scrolling
        this.setupTouchScrolling();

        // Add double-tap zoom prevention for buttons
        this.preventDoubleTabZoom();
    }

    setupSwipeGestures() {
        let startX = 0;
        let startY = 0;
        let endX = 0;
        let endY = 0;

        document.addEventListener('touchstart', (e) => {
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
        });

        document.addEventListener('touchend', (e) => {
            endX = e.changedTouches[0].clientX;
            endY = e.changedTouches[0].clientY;

            const deltaX = endX - startX;
            const deltaY = endY - startY;

            // Check if it's a horizontal swipe
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {
                const mobileNavMenu = document.getElementById('mobile-nav-menu');

                if (deltaX > 0 && startX < 20) {
                    // Swipe right from left edge - open menu
                    this.openMobileMenu();
                } else if (deltaX < -50 && mobileNavMenu && mobileNavMenu.classList.contains('active')) {
                    // Swipe left - close menu if open
                    this.closeMobileMenu();
                }
            }
        });
    }

    setupTouchScrolling() {
        // Enable momentum scrolling on iOS
        const scrollableElements = document.querySelectorAll(
            '.transmission-log, .frequency-list, .version-grid, .modal-body'
        );

        scrollableElements.forEach(element => {
            element.style.webkitOverflowScrolling = 'touch';
        });

        // Prevent pull-to-refresh on mobile when at top of page
        let lastTouchY = 0;
        document.addEventListener('touchstart', (e) => {
            if (e.touches.length !== 1) return;
            lastTouchY = e.touches[0].clientY;
        });

        document.addEventListener('touchmove', (e) => {
            if (e.touches.length !== 1) return;

            const touchY = e.touches[0].clientY;
            const touchYDelta = touchY - lastTouchY;
            lastTouchY = touchY;

            if (window.scrollY === 0 && touchYDelta > 0) {
                e.preventDefault();
            }
        }, { passive: false });
    }

    preventDoubleTabZoom() {
        // Prevent double-tap zoom on buttons and interactive elements
        const interactiveElements = document.querySelectorAll(
            '.btn, .frequency-item, .version-item, .mobile-nav-link, .tab-btn'
        );

        interactiveElements.forEach(element => {
            let lastTouchEnd = 0;
            element.addEventListener('touchend', (e) => {
                const now = new Date().getTime();
                if (now - lastTouchEnd <= 300) {
                    e.preventDefault();
                }
                lastTouchEnd = now;
            }, false);
        });
    }

    // Add haptic feedback for supported devices
    triggerHapticFeedback(type = 'light') {
        if ('vibrate' in navigator) {
            switch (type) {
                case 'light':
                    navigator.vibrate(10);
                    break;
                case 'medium':
                    navigator.vibrate(20);
                    break;
                case 'heavy':
                    navigator.vibrate([30, 10, 30]);
                    break;
            }
        }
    }

    showSettingsModal() {
        this.loadCurrentSettings();
        document.getElementById('settings-modal').style.display = 'block';
    }

    async loadCurrentSettings() {
        try {
            const response = await fetch('/api/v1/settings');
            if (response.ok) {
                const settings = await response.json();
                this.populateSettingsForm(settings);
            }
        } catch (error) {
            console.error('Error loading settings:', error);
            // Load defaults if API fails
            this.populateSettingsForm({});
        }
    }

    populateSettingsForm(settings) {
        // SDR Settings
        document.getElementById('sdr-device-index').value = settings.sdr_device_index || 0;
        document.getElementById('sdr-sample-rate').value = settings.sdr_sample_rate || 2048000;
        document.getElementById('sdr-gain').value = settings.sdr_gain || 49.6;
        document.getElementById('sdr-gain-value').textContent = settings.sdr_gain || 49.6;
        document.getElementById('squelch-threshold').value = settings.squelch_threshold || -50;
        document.getElementById('squelch-threshold-value').textContent = settings.squelch_threshold || -50;

        // Audio Settings
        document.getElementById('audio-sample-rate').value = settings.audio_sample_rate || 48000;
        document.getElementById('audio-channels').value = settings.audio_channels || 1;
        document.getElementById('audio-chunk-size').value = settings.audio_chunk_size || 1024;
        document.getElementById('audio-device-name').value = settings.audio_device_name || '';

        // Scanning Settings
        document.getElementById('scan-delay').value = settings.scan_delay || 0.1;
        document.getElementById('scan-delay-value').textContent = settings.scan_delay || 0.1;
        document.getElementById('transmission-timeout').value = settings.transmission_timeout || 5;
        document.getElementById('transmission-timeout-value').textContent = settings.transmission_timeout || 5;
        document.getElementById('priority-multiplier').value = settings.priority_multiplier || 2.0;
        document.getElementById('priority-multiplier-value').textContent = settings.priority_multiplier || 2.0;
        document.getElementById('enable-recording').checked = settings.enable_recording || false;

        // System Settings
        document.getElementById('log-level').value = settings.log_level || 'INFO';
        document.getElementById('max-log-entries').value = settings.max_log_entries || 1000;
        document.getElementById('auto-cleanup-days').value = settings.auto_cleanup_days || 30;
        document.getElementById('enable-notifications').checked = settings.enable_notifications !== false;
        document.getElementById('enable-sound-alerts').checked = settings.enable_sound_alerts !== false;
    }

    async saveSettings() {
        const settings = this.collectSettingsFromForm();

        try {
            const response = await fetch('/api/v1/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });

            if (response.ok) {
                this.showToast('Settings saved successfully', 'success');
                this.closeModal('settings-modal');

                // Optionally reload page to apply settings
                if (confirm('Settings saved. Restart scanner to apply changes?')) {
                    if (this.scannerRunning) {
                        await this.toggleScanner(); // Stop
                        setTimeout(() => this.toggleScanner(), 1000); // Start after delay
                    }
                }
            } else {
                const error = await response.json();
                this.showToast(error.detail || 'Error saving settings', 'error');
            }
        } catch (error) {
            console.error('Error saving settings:', error);
            this.showToast('Error saving settings', 'error');
        }
    }

    collectSettingsFromForm() {
        return {
            // SDR Settings
            sdr_device_index: parseInt(document.getElementById('sdr-device-index').value),
            sdr_sample_rate: parseInt(document.getElementById('sdr-sample-rate').value),
            sdr_gain: parseFloat(document.getElementById('sdr-gain').value),
            squelch_threshold: parseFloat(document.getElementById('squelch-threshold').value),

            // Audio Settings
            audio_sample_rate: parseInt(document.getElementById('audio-sample-rate').value),
            audio_channels: parseInt(document.getElementById('audio-channels').value),
            audio_chunk_size: parseInt(document.getElementById('audio-chunk-size').value),
            audio_device_name: document.getElementById('audio-device-name').value,

            // Scanning Settings
            scan_delay: parseFloat(document.getElementById('scan-delay').value),
            transmission_timeout: parseFloat(document.getElementById('transmission-timeout').value),
            priority_multiplier: parseFloat(document.getElementById('priority-multiplier').value),
            enable_recording: document.getElementById('enable-recording').checked,

            // System Settings
            log_level: document.getElementById('log-level').value,
            max_log_entries: parseInt(document.getElementById('max-log-entries').value),
            auto_cleanup_days: parseInt(document.getElementById('auto-cleanup-days').value),
            enable_notifications: document.getElementById('enable-notifications').checked,
            enable_sound_alerts: document.getElementById('enable-sound-alerts').checked
        };
    }

    resetSettings() {
        if (!confirm('Are you sure you want to reset all settings to defaults?')) return;

        // Reset to default values
        this.populateSettingsForm({});
        this.showToast('Settings reset to defaults', 'info');
    }

    // Version Management Methods
    async loadVersions() {
        try {
            const response = await fetch('/api/v1/versions');
            if (response.ok) {
                const versions = await response.json();
                this.renderVersions(versions);
            } else {
                throw new Error('Failed to load version information');
            }
        } catch (error) {
            console.error('Error loading versions:', error);
            this.renderVersionsError('Error loading version information');
        }
    }

    async refreshVersions() {
        try {
            // Show loading state
            this.renderVersionsLoading();

            const response = await fetch('/api/v1/versions/refresh', { method: 'POST' });
            if (response.ok) {
                const data = await response.json();
                this.renderVersions(data.versions);
                this.showToast('Version information refreshed', 'success');
            } else {
                throw new Error('Failed to refresh version information');
            }
        } catch (error) {
            console.error('Error refreshing versions:', error);
            this.showToast('Error refreshing version information', 'error');
            this.renderVersionsError('Error refreshing version information');
        }
    }

    renderVersionsLoading() {
        const versionGrid = document.getElementById('version-grid');
        versionGrid.innerHTML = `
            <div class="version-item loading">
                <div class="loading-spinner"></div>
                <div>Refreshing version information...</div>
            </div>
        `;
    }

    renderVersionsError(message) {
        const versionGrid = document.getElementById('version-grid');
        versionGrid.innerHTML = `
            <div class="version-item error">
                <i class="fas fa-exclamation-triangle" style="color: #f44336;"></i>
                <div>${message}</div>
            </div>
        `;
    }

    renderVersions(versions) {
        const versionGrid = document.getElementById('version-grid');

        if (!versions || typeof versions !== 'object') {
            this.renderVersionsError('Invalid version data received');
            return;
        }

        const versionItems = [];

        // Process each component
        for (const [componentKey, versionInfo] of Object.entries(versions)) {
            if (componentKey === 'last_updated') continue;

            if (versionInfo && typeof versionInfo === 'object') {
                versionItems.push(this.createVersionItem(versionInfo));
            }
        }

        if (versionItems.length === 0) {
            versionGrid.innerHTML = `
                <div class="version-item">
                    <div>No version information available</div>
                </div>
            `;
        } else {
            versionGrid.innerHTML = versionItems.join('');
        }
    }

    createVersionItem(versionInfo) {
        const {
            name,
            current,
            latest,
            update_available,
            status
        } = versionInfo;

        // Determine status class and display
        let statusClass = 'unknown';
        let statusDisplay = 'Unknown';

        if (status === 'installed') {
            statusClass = 'installed';
            statusDisplay = 'Installed';
        } else if (status === 'not_installed') {
            statusClass = 'not-installed';
            statusDisplay = 'Not Installed';
        }

        // Determine item classes
        const itemClasses = ['version-item'];
        if (update_available) itemClasses.push('update-available');
        if (status === 'not_installed') itemClasses.push('not-installed');

        // Create actions based on status
        let actions = '';
        if (status === 'not_installed') {
            actions = `
                <div class="version-actions">
                    <button class="btn btn-primary" onclick="app.installComponent('${name.toLowerCase()}')">
                        <i class="fas fa-download"></i> Install
                    </button>
                </div>
            `;
        } else if (update_available) {
            actions = `
                <div class="version-actions">
                    <button class="btn btn-warning" onclick="app.updateComponent('${name.toLowerCase()}')">
                        <i class="fas fa-arrow-up"></i> Update
                    </button>
                </div>
            `;
        }

        return `
            <div class="${itemClasses.join(' ')}">
                ${update_available ? '<div class="update-indicator">!</div>' : ''}
                <div class="version-header">
                    <div class="version-name">${name}</div>
                    <div class="version-status ${statusClass}">${statusDisplay}</div>
                </div>
                <div class="version-details">
                    <div class="version-info">
                        <span class="label">Current Version</span>
                        <span class="value">${current || 'Not installed'}</span>
                    </div>
                    <div class="version-info">
                        <span class="label">Latest Version</span>
                        <span class="value ${update_available ? 'update' : ''}">${latest || 'Unknown'}</span>
                    </div>
                </div>
                ${actions}
            </div>
        `;
    }

    async installComponent(componentName) {
        try {
            // Show loading toast
            this.showToast(`Installing ${componentName}...`, 'info');

            const response = await fetch(`/api/v1/install/${componentName}`, {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast(data.message, 'success');
                // Refresh version information after successful installation
                await this.refreshVersions();
            } else {
                this.showToast(data.message || 'Installation failed', 'error');
            }

        } catch (error) {
            console.error('Error installing component:', error);
            this.showToast(`Error installing ${componentName}: ${error.message}`, 'error');
        }
    }

    async updateComponent(componentName) {
        try {
            // Show loading toast
            this.showToast(`Updating ${componentName}...`, 'info');

            const response = await fetch(`/api/v1/update/${componentName}`, {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast(data.message, 'success');
                // Refresh version information after successful update
                await this.refreshVersions();
            } else {
                this.showToast(data.message || 'Update failed', 'error');
            }

        } catch (error) {
            console.error('Error updating component:', error);
            this.showToast(`Error updating ${componentName}: ${error.message}`, 'error');
        }
    }

    // DSP Control Methods
    resetEqualizer() {
        // Reset all EQ sliders to 0
        const eqBands = ['bass', 'low-mid', 'mid', 'high-mid', 'presence', 'brilliance'];
        eqBands.forEach(band => {
            const slider = document.getElementById(`eq-${band}`);
            const output = document.getElementById(`eq-${band}-value`);
            if (slider && output) {
                slider.value = 0;
                output.textContent = '0';
            }
        });

        this.showToast('Equalizer reset to flat response', 'info');
    }

    async refreshDspStats() {
        try {
            const response = await fetch('/api/v1/audio/dsp/stats');
            if (response.ok) {
                const stats = await response.json();
                this.updateDspStatsDisplay(stats);
                this.showToast('DSP statistics refreshed', 'success');
            } else {
                throw new Error('Failed to refresh DSP statistics');
            }
        } catch (error) {
            console.error('Error refreshing DSP stats:', error);
            this.showToast('Error refreshing DSP statistics', 'error');
        }
    }

    async resetDspStats() {
        try {
            const response = await fetch('/api/v1/audio/dsp/stats/reset', { method: 'POST' });
            if (response.ok) {
                await this.refreshDspStats();
                this.showToast('DSP statistics reset', 'info');
            } else {
                throw new Error('Failed to reset DSP statistics');
            }
        } catch (error) {
            console.error('Error resetting DSP stats:', error);
            this.showToast('Error resetting DSP statistics', 'error');
        }
    }

    updateDspStatsDisplay(stats) {
        const framesElement = document.getElementById('dsp-frames-processed');
        const avgLevelElement = document.getElementById('dsp-avg-level');
        const peakLevelElement = document.getElementById('dsp-peak-level');

        if (framesElement) framesElement.textContent = stats.frames_processed || '0';
        if (avgLevelElement) avgLevelElement.textContent = `${(stats.average_level || 0).toFixed(1)} dB`;
        if (peakLevelElement) peakLevelElement.textContent = `${(stats.peak_level || 0).toFixed(1)} dB`;
    }

    async updateDspSetting(setting, value) {
        try {
            const response = await fetch('/api/v1/audio/dsp/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [setting]: value })
            });

            if (response.ok) {
                console.log(`DSP setting ${setting} updated to ${value}`);
            } else {
                throw new Error('Failed to update DSP setting');
            }
        } catch (error) {
            console.error('Error updating DSP setting:', error);
            this.showToast(`Error updating ${setting}`, 'error');
        }
    }

    async setEqGain(band, gain) {
        try {
            const response = await fetch('/api/v1/audio/dsp/eq', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ band: band, gain: parseFloat(gain) })
            });

            if (response.ok) {
                console.log(`EQ band ${band} set to ${gain} dB`);
            } else {
                throw new Error('Failed to set EQ gain');
            }
        } catch (error) {
            console.error('Error setting EQ gain:', error);
            this.showToast(`Error setting EQ gain for ${band}`, 'error');
        }
    }
}

// Global app instance
let app;

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    app = new SDR2ZelloApp();
});

// Global functions for HTML onclick handlers
function closeModal(modalId) {
    if (app) app.closeModal(modalId);
}

function addFrequency() {
    if (app) app.addFrequency();
}

function saveSettings() {
    if (app) app.saveSettings();
}

function resetSettings() {
    if (app) app.resetSettings();
}

// DSP Control Functions
function resetEqualizer() {
    if (app) app.resetEqualizer();
}

function refreshDspStats() {
    if (app) app.refreshDspStats();
}

function resetDspStats() {
    if (app) app.resetDspStats();
}
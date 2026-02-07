/**
 * app.js - Main application logic
 * FameForecastTextView Web Interface
 *
 * Mirrors the behavior of gui.py MultiDashboard class
 */

class FameForecastApp {
    constructor() {
        this.socket = null;
        this.tabManager = null;
        this.connected = false;

        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        console.log('[App] Initializing FameForecastTextView...');

        // Initialize tab manager
        this.tabManager = new TabManager('#tab-container');

        // Initialize socket connection
        this._initSocket();

        // Bind UI events
        this._bindEvents();

        console.log('[App] Initialized');
    }

    /**
     * Initialize WebSocket connection and handlers
     */
    _initSocket() {
        // Connect using the global socket client
        this.socket = window.socketClient.connect();

        // Connection status
        this.socket.on('connect', () => {
            this.connected = true;
            this._updateStatus('Connected', 'connected');
            // Request active channels after connection is established
            console.log('[App] Connected, requesting active channels...');
            this.socket.emit('get_active_channels');
        });

        this.socket.on('disconnect', () => {
            this.connected = false;
            this._updateStatus('Disconnected', 'disconnected');
        });

        // Chat messages (mirrors gui_queue processing in update_gui)
        this.socket.on('chat_message', (data) => {
            console.log('[App] Chat message:', data.channel, data.tag, data.text);
            this._handleMessage(data);
        });

        // Channel metadata updates
        this.socket.on('channel_meta', (data) => {
            this._handleMetadata(data);
        });

        // Stream online prompt
        this.socket.on('stream_online', (data) => {
            this._handleStreamOnline(data);
        });

        // Channel joined confirmation
        this.socket.on('channel_joined', (data) => {
            console.log('[App] Channel joined:', data.channel);
            this.tabManager.createTab(data.channel);
        });

        // Active channels list (received on connect/reconnect)
        this.socket.on('active_channels', (data) => {
            console.log('[App] Received active channels:', data.channels);
            if (data.channels && data.channels.length > 0) {
                data.channels.forEach(channel => {
                    console.log('[App] Creating tab for:', channel);
                    this.tabManager.createTab(channel);
                });
            } else {
                console.log('[App] No active channels received');
            }
        });

        // Chat sent confirmation
        this.socket.on('chat_sent', (data) => {
            // Message was sent successfully
            console.log('[App] Chat sent:', data.channel, data.message);
        });
    }

    /**
     * Bind UI event handlers
     */
    _bindEvents() {
        // Exit button
        const exitBtn = document.getElementById('btn-exit');
        if (exitBtn) {
            exitBtn.addEventListener('click', () => {
                window.modalManager.confirm(
                    'Exit',
                    'Are you sure you want to exit?',
                    () => {
                        // Close the window/tab
                        window.close();
                        // Fallback: navigate away
                        window.location.href = 'about:blank';
                    }
                );
            });
        }

        // Join button in stream prompt
        const joinBtn = document.getElementById('btn-join');
        const skipBtn = document.getElementById('btn-skip');

        if (joinBtn && skipBtn) {
            joinBtn.addEventListener('click', () => {
                const modal = document.getElementById('modal-stream-online');
                const channel = modal.dataset.channel;
                if (channel) {
                    this._joinChannel(channel);
                }
                window.modalManager.hide('modal-stream-online');
            });

            skipBtn.addEventListener('click', () => {
                const modal = document.getElementById('modal-stream-online');
                const channel = modal.dataset.channel;
                if (channel) {
                    this.socket.emit('skip_channel', { channel });
                }
                window.modalManager.hide('modal-stream-online');
            });
        }
    }

    /**
     * Update connection status display
     */
    _updateStatus(text, className) {
        const label = document.getElementById('status-label');
        if (label) {
            label.textContent = `Status: ${text}`;
            label.className = `status-${className}`;
        }
    }

    /**
     * Handle incoming chat message
     * Mirrors gui.py update_gui() message routing
     */
    _handleMessage(data) {
        const { channel, tag, text, timestamp } = data;

        // Add message to appropriate tab
        this.tabManager.addMessage(channel, tag, text, timestamp);
    }

    /**
     * Handle channel metadata update
     * Mirrors gui.py GUI_UPDATE_META handling
     */
    _handleMetadata(data) {
        const { channel, game, viewers, thumbnail } = data;

        this.tabManager.updateMeta(channel, {
            game,
            viewers,
            thumbnail
        });
    }

    /**
     * Handle stream online notification
     * Mirrors gui.py handle_online_prompt()
     */
    _handleStreamOnline(data) {
        const channel = data.channel || data.user || 'Unknown';

        console.log('[App] Stream online:', channel);

        window.modalManager.showStreamPrompt(
            channel,
            data.info,
            // On Join
            (ch) => {
                this._joinChannel(ch);
            },
            // On Skip
            (ch) => {
                this.socket.emit('skip_channel', { channel: ch });
            }
        );
    }

    /**
     * Join a channel
     */
    _joinChannel(channel) {
        console.log('[App] Joining channel:', channel);
        this.socket.emit('join_channel', { channel });
    }

    /**
     * Send a chat message
     */
    sendChat(channel, message) {
        if (!message || !message.trim()) {
            return;
        }

        if (!this.connected) {
            console.warn('[App] Cannot send, not connected');
            return;
        }

        // Emit to server
        this.socket.emit('send_chat', {
            channel: channel,
            message: message.trim()
        });

        // Add to local display immediately (optimistic update)
        // Server will echo back as 'SELF' tag if successful
    }

    /**
     * Get the active tab's channel name
     */
    getActiveChannel() {
        return this.tabManager.getActiveTab();
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.connected;
    }
}

// Export to global scope
window.FameForecastApp = FameForecastApp;

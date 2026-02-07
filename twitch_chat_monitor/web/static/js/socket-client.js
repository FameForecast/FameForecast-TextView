/**
 * socket-client.js - WebSocket connection handler
 * Manages connection to Flask-SocketIO server
 */

class SocketClient {
    constructor() {
        this.socket = null;
        this.connected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.eventHandlers = {};
    }

    /**
     * Connect to the WebSocket server
     */
    connect() {
        this.socket = io({
            reconnection: true,
            reconnectionAttempts: this.maxReconnectAttempts,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        });

        this._bindCoreEvents();
        return this;
    }

    /**
     * Bind core connection events
     */
    _bindCoreEvents() {
        this.socket.on('connect', () => {
            console.log('[Socket] Connected');
            this.connected = true;
            this.reconnectAttempts = 0;
            this._hideReconnecting();
            this._trigger('connect');
        });

        this.socket.on('disconnect', (reason) => {
            console.log('[Socket] Disconnected:', reason);
            this.connected = false;
            this._trigger('disconnect', reason);
        });

        this.socket.on('connect_error', (error) => {
            console.log('[Socket] Connection error:', error);
            this._trigger('connect_error', error);
        });

        this.socket.on('reconnecting', (attemptNumber) => {
            console.log('[Socket] Reconnecting, attempt:', attemptNumber);
            this.reconnectAttempts = attemptNumber;
            this._showReconnecting();
            this._trigger('reconnecting', attemptNumber);
        });

        this.socket.on('reconnect', (attemptNumber) => {
            console.log('[Socket] Reconnected after', attemptNumber, 'attempts');
            this._hideReconnecting();
            // Request current state after reconnect
            this.emit('get_active_channels');
            this._trigger('reconnect', attemptNumber);
        });

        this.socket.on('reconnect_failed', () => {
            console.log('[Socket] Reconnection failed');
            this._trigger('reconnect_failed');
        });

        // Server confirmation
        this.socket.on('connected', (data) => {
            console.log('[Socket] Server confirmed connection:', data);
        });

        // Pong response
        this.socket.on('pong', (data) => {
            this._trigger('pong', data);
        });
    }

    /**
     * Show reconnecting overlay
     */
    _showReconnecting() {
        const overlay = document.getElementById('reconnecting-overlay');
        if (overlay) {
            overlay.classList.remove('hidden');
        }
    }

    /**
     * Hide reconnecting overlay
     */
    _hideReconnecting() {
        const overlay = document.getElementById('reconnecting-overlay');
        if (overlay) {
            overlay.classList.add('hidden');
        }
    }

    /**
     * Register an event handler
     */
    on(event, handler) {
        // Register with socket
        this.socket.on(event, handler);

        // Also track locally
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(handler);

        return this;
    }

    /**
     * Emit an event to the server
     */
    emit(event, data) {
        if (this.socket && this.connected) {
            this.socket.emit(event, data);
        } else {
            console.warn('[Socket] Cannot emit, not connected');
        }
        return this;
    }

    /**
     * Trigger local event handlers
     */
    _trigger(event, data) {
        const handlers = this.eventHandlers[event];
        if (handlers) {
            handlers.forEach(h => h(data));
        }
    }

    /**
     * Send a ping to check connection
     */
    ping() {
        this.emit('ping');
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.connected;
    }

    /**
     * Disconnect from server
     */
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
        }
    }
}

// Create global instance
window.socketClient = new SocketClient();

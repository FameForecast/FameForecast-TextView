/**
 * tabs.js - Tab management
 * Mimics tkinter's ttk.Notebook behavior
 */

class TabManager {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        this.headersContainer = document.getElementById('tab-headers');
        this.panelsContainer = document.getElementById('tab-panels');
        this.tabs = {};
        this.activeTab = null;
    }

    /**
     * Check if a tab exists
     */
    hasTab(name) {
        return name in this.tabs;
    }

    /**
     * Create a new tab for a channel
     * Mirrors gui.py create_channel_tab() structure
     */
    createTab(name) {
        if (this.tabs[name]) {
            return this.tabs[name];
        }

        // Create tab header
        const header = document.createElement('div');
        header.className = 'tab-header';
        header.textContent = name;
        header.dataset.channel = name;
        header.addEventListener('click', () => this.switchTo(name));
        this.headersContainer.appendChild(header);

        // Create tab panel with channel HUD, chat log, and input
        const panel = document.createElement('div');
        panel.className = 'tab-panel';
        panel.id = `panel-${this._sanitizeId(name)}`;
        panel.dataset.channel = name;

        panel.innerHTML = `
            <div class="channel-hud">
                <img class="hud-thumbnail" alt="Stream thumbnail" src="">
                <div class="hud-info">
                    <div class="hud-game">Waiting for signal...</div>
                    <div class="hud-viewers">Viewers: --</div>
                </div>
            </div>
            <div class="chat-log" id="log-${this._sanitizeId(name)}"></div>
            <div class="chat-input">
                <input type="text"
                       placeholder="Type a message..."
                       id="input-${this._sanitizeId(name)}"
                       data-channel="${name}">
                <button type="button"
                        class="btn btn-primary"
                        data-channel="${name}">Send</button>
            </div>
        `;

        this.panelsContainer.appendChild(panel);

        // Bind input events
        const input = panel.querySelector('input');
        const sendBtn = panel.querySelector('button');

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this._sendMessage(name, input);
            }
        });

        sendBtn.addEventListener('click', () => {
            this._sendMessage(name, input);
        });

        // Store references
        this.tabs[name] = {
            header: header,
            panel: panel,
            log: panel.querySelector('.chat-log'),
            input: input,
            hudGame: panel.querySelector('.hud-game'),
            hudViewers: panel.querySelector('.hud-viewers'),
            hudThumbnail: panel.querySelector('.hud-thumbnail')
        };

        // If this is the first tab, activate it
        if (!this.activeTab) {
            this.switchTo(name);
        }

        // Hide empty state
        const emptyState = document.getElementById('empty-state');
        if (emptyState) {
            emptyState.classList.add('hidden');
        }

        return this.tabs[name];
    }

    /**
     * Switch to a specific tab
     */
    switchTo(name) {
        if (!this.tabs[name]) {
            return;
        }

        // Deactivate all tabs
        Object.values(this.tabs).forEach(tab => {
            tab.header.classList.remove('active');
            tab.panel.classList.remove('active');
        });

        // Activate selected tab
        this.tabs[name].header.classList.add('active');
        this.tabs[name].panel.classList.add('active');
        this.activeTab = name;

        // Focus input
        this.tabs[name].input.focus();
    }

    /**
     * Get active tab name
     */
    getActiveTab() {
        return this.activeTab;
    }

    /**
     * Get tab data
     */
    getTab(name) {
        return this.tabs[name];
    }

    /**
     * Update channel metadata (game, viewers, thumbnail)
     */
    updateMeta(name, meta) {
        const tab = this.tabs[name];
        if (!tab) return;

        if (meta.game) {
            tab.hudGame.textContent = `Playing: ${meta.game}`;
        }

        if (meta.viewers !== undefined) {
            tab.hudViewers.textContent = `Viewers: ${meta.viewers.toLocaleString()}`;
        }

        if (meta.thumbnail) {
            tab.hudThumbnail.src = `data:image/jpeg;base64,${meta.thumbnail}`;
        }
    }

    /**
     * Add a message to a tab's chat log
     * Mirrors gui.py log_to_tab() behavior
     */
    addMessage(name, tag, text, timestamp) {
        // Create tab if it doesn't exist
        if (!this.tabs[name]) {
            this.createTab(name);
        }

        const tab = this.tabs[name];
        const log = tab.log;

        // Create message element
        const line = document.createElement('div');
        line.className = `message tag-${tag.toLowerCase()}`;

        // Format timestamp
        const ts = timestamp || new Date().toLocaleTimeString('en-US', { hour12: false });

        // Escape HTML and format
        const escapedText = this._escapeHtml(text);

        // Replace @mentions with clickable spans
        const formattedText = escapedText.replace(
            /@(\w+)/g,
            '<span class="mention" data-username="$1">@$1</span>'
        );

        line.innerHTML = `<span class="timestamp">[${ts}]</span> ${formattedText}`;

        // Bind mention click handlers
        line.querySelectorAll('.mention').forEach(mention => {
            mention.addEventListener('click', () => {
                this._insertMention(name, mention.dataset.username);
            });
        });

        // Append to log
        log.appendChild(line);

        // Limit lines (matches tkinter's 2000 line limit)
        while (log.children.length > 2000) {
            log.removeChild(log.firstChild);
        }

        // Auto-scroll to bottom
        log.scrollTop = log.scrollHeight;
    }

    /**
     * Insert @mention into input
     */
    _insertMention(tabName, username) {
        const tab = this.tabs[tabName];
        if (!tab) return;

        const input = tab.input;
        const current = input.value.trim();

        if (!current) {
            input.value = `@${username} `;
        } else {
            input.value = `${current} @${username} `;
        }

        input.focus();
    }

    /**
     * Send message from input
     */
    _sendMessage(channel, input) {
        const message = input.value.trim();
        if (message && window.app) {
            window.app.sendChat(channel, message);
            input.value = '';
        }
    }

    /**
     * Sanitize ID for use in DOM
     */
    _sanitizeId(name) {
        return name.replace(/[^a-zA-Z0-9]/g, '_');
    }

    /**
     * Escape HTML entities
     */
    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Get all tab names
     */
    getAllTabs() {
        return Object.keys(this.tabs);
    }

    /**
     * Remove a tab
     */
    removeTab(name) {
        const tab = this.tabs[name];
        if (!tab) return;

        tab.header.remove();
        tab.panel.remove();
        delete this.tabs[name];

        // If this was the active tab, switch to another
        if (this.activeTab === name) {
            const remaining = Object.keys(this.tabs);
            if (remaining.length > 0) {
                this.switchTo(remaining[0]);
            } else {
                this.activeTab = null;
                // Show empty state
                const emptyState = document.getElementById('empty-state');
                if (emptyState) {
                    emptyState.classList.remove('hidden');
                }
            }
        }
    }
}

// Export for use by app.js
window.TabManager = TabManager;

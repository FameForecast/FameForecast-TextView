/**
 * modals.js - Modal dialog handling
 * Mimics tkinter's Toplevel dialogs (PromptDialog, etc.)
 */

class ModalManager {
    constructor() {
        this.activeModal = null;
        this.promptQueue = [];
        this.processing = false;
    }

    /**
     * Show a modal by ID
     */
    show(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
            this.activeModal = modalId;

            // Focus first button
            const btn = modal.querySelector('button');
            if (btn) btn.focus();
        }
    }

    /**
     * Hide a modal by ID
     */
    hide(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('hidden');
            if (this.activeModal === modalId) {
                this.activeModal = null;
            }
        }
    }

    /**
     * Hide the currently active modal
     */
    hideActive() {
        if (this.activeModal) {
            this.hide(this.activeModal);
        }
    }

    /**
     * Show stream online prompt
     * Mirrors gui.py PromptDialog behavior
     */
    showStreamPrompt(channel, info, onJoin, onSkip) {
        // Queue the prompt (in case multiple streams go live)
        this.promptQueue.push({ channel, info, onJoin, onSkip });
        this._processPromptQueue();
    }

    /**
     * Process prompt queue one at a time
     */
    _processPromptQueue() {
        if (this.processing || this.promptQueue.length === 0) {
            return;
        }

        this.processing = true;
        const prompt = this.promptQueue.shift();

        const modal = document.getElementById('modal-stream-online');
        if (!modal) {
            this.processing = false;
            return;
        }

        // Update content
        const title = modal.querySelector('#prompt-channel-name');
        if (title) {
            title.textContent = `${prompt.channel} IS LIVE`;
        }

        // Store channel for handlers
        modal.dataset.channel = prompt.channel;

        // Bind button handlers
        const joinBtn = document.getElementById('btn-join');
        const skipBtn = document.getElementById('btn-skip');

        const handleJoin = () => {
            this._cleanupPrompt(joinBtn, skipBtn, handleJoin, handleSkip);
            if (prompt.onJoin) prompt.onJoin(prompt.channel);
            this.hide('modal-stream-online');
            this.processing = false;
            this._processPromptQueue();
        };

        const handleSkip = () => {
            this._cleanupPrompt(joinBtn, skipBtn, handleJoin, handleSkip);
            if (prompt.onSkip) prompt.onSkip(prompt.channel);
            this.hide('modal-stream-online');
            this.processing = false;
            this._processPromptQueue();
        };

        joinBtn.addEventListener('click', handleJoin);
        skipBtn.addEventListener('click', handleSkip);

        // Show modal
        this.show('modal-stream-online');
    }

    /**
     * Remove event listeners from prompt buttons
     */
    _cleanupPrompt(joinBtn, skipBtn, handleJoin, handleSkip) {
        joinBtn.removeEventListener('click', handleJoin);
        skipBtn.removeEventListener('click', handleSkip);
    }

    /**
     * Show a simple alert modal
     */
    alert(title, message) {
        // Create dynamic alert modal if needed
        let modal = document.getElementById('modal-alert');

        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'modal-alert';
            modal.className = 'modal hidden';
            modal.innerHTML = `
                <div class="modal-overlay"></div>
                <div class="modal-content">
                    <h2 class="alert-title"></h2>
                    <p class="alert-message"></p>
                    <div class="modal-buttons">
                        <button type="button" class="btn btn-primary" id="btn-alert-ok">OK</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        modal.querySelector('.alert-title').textContent = title;
        modal.querySelector('.alert-message').textContent = message;

        const okBtn = modal.querySelector('#btn-alert-ok');
        const handleOk = () => {
            okBtn.removeEventListener('click', handleOk);
            this.hide('modal-alert');
        };
        okBtn.addEventListener('click', handleOk);

        this.show('modal-alert');
    }

    /**
     * Show a confirmation modal
     */
    confirm(title, message, onConfirm, onCancel) {
        let modal = document.getElementById('modal-confirm');

        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'modal-confirm';
            modal.className = 'modal hidden';
            modal.innerHTML = `
                <div class="modal-overlay"></div>
                <div class="modal-content">
                    <h2 class="confirm-title"></h2>
                    <p class="confirm-message"></p>
                    <div class="modal-buttons">
                        <button type="button" class="btn btn-primary" id="btn-confirm-yes">Yes</button>
                        <button type="button" class="btn btn-secondary" id="btn-confirm-no">No</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        modal.querySelector('.confirm-title').textContent = title;
        modal.querySelector('.confirm-message').textContent = message;

        const yesBtn = modal.querySelector('#btn-confirm-yes');
        const noBtn = modal.querySelector('#btn-confirm-no');

        const handleYes = () => {
            cleanup();
            if (onConfirm) onConfirm();
        };

        const handleNo = () => {
            cleanup();
            if (onCancel) onCancel();
        };

        const cleanup = () => {
            yesBtn.removeEventListener('click', handleYes);
            noBtn.removeEventListener('click', handleNo);
            this.hide('modal-confirm');
        };

        yesBtn.addEventListener('click', handleYes);
        noBtn.addEventListener('click', handleNo);

        this.show('modal-confirm');
    }

    /**
     * Close modal on overlay click
     */
    bindOverlayClose(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            const overlay = modal.querySelector('.modal-overlay');
            if (overlay) {
                overlay.addEventListener('click', () => this.hide(modalId));
            }
        }
    }

    /**
     * Close modal on Escape key
     */
    bindEscapeClose() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.activeModal) {
                this.hideActive();
            }
        });
    }
}

// Create global instance
window.modalManager = new ModalManager();

// Bind escape key handler
document.addEventListener('DOMContentLoaded', () => {
    window.modalManager.bindEscapeClose();
});

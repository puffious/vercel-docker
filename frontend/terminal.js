class WebTerminal {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.sessionId = null;
        this.commandHistory = [];
        this.historyIndex = -1;
        this.currentDirectory = '~';
        this.username = 'user';
        this.init();
    }

    init() {
        this.createTerminalElements();
        this.bindEvents();
        this.displayWelcome();
        this.focusInput();
    }

    createTerminalElements() {
        this.container.innerHTML = `
            <div class="terminal-header">
                <div class="terminal-controls">
                    <span class="control-btn close"></span>
                    <span class="control-btn minimize"></span>
                    <span class="control-btn maximize"></span>
                </div>
                <div class="terminal-title">Terminal - Vercel Shell</div>
            </div>
            <div class="terminal-body">
                <div id="terminal-output" class="terminal-output"></div>
                <div class="terminal-input-line">
                    <span id="terminal-prompt" class="terminal-prompt">user@vercel-shell:~$ </span>
                    <input type="text" id="terminal-input" class="terminal-input" autocomplete="off" spellcheck="false">
                </div>
            </div>
        `;

        this.output = document.getElementById('terminal-output');
        this.input = document.getElementById('terminal-input');
        this.prompt = document.getElementById('terminal-prompt');
    }

    bindEvents() {
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        this.input.addEventListener('keyup', (e) => this.handleKeyup(e));
        
        // Focus input when clicking anywhere in terminal
        this.container.addEventListener('click', () => this.focusInput());
        
        // Handle paste
        this.input.addEventListener('paste', (e) => {
            setTimeout(() => this.handleAutocomplete(), 0);
        });
    }

    handleKeydown(e) {
        switch(e.key) {
            case 'Enter':
                e.preventDefault();
                this.executeCommand();
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.navigateHistory('up');
                break;
            case 'ArrowDown':
                e.preventDefault();
                this.navigateHistory('down');
                break;
            case 'Tab':
                e.preventDefault();
                this.handleTabCompletion();
                break;
            case 'c':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.handleCtrlC();
                }
                break;
            case 'l':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.clearTerminal();
                }
                break;
        }
    }

    handleKeyup(e) {
        // Auto-suggest as user types (debounced)
        clearTimeout(this.autocompleteTimeout);
        this.autocompleteTimeout = setTimeout(() => {
            if (e.key !== 'Tab' && e.key !== 'Enter' && !e.key.startsWith('Arrow')) {
                this.handleAutocomplete();
            }
        }, 300);
    }

    async executeCommand() {
        const command = this.input.value.trim();
        if (!command) return;

        // Add command to history
        this.commandHistory.push(command);
        this.historyIndex = this.commandHistory.length;

        // Display command in output
        this.appendOutput(`${this.prompt.textContent}${command}`, 'command');
        
        // Clear input
        this.input.value = '';
        this.input.disabled = true;

        try {
            const response = await fetch('/shell', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command: command,
                    session_id: this.sessionId
                })
            });

            const result = await response.json();

            if (response.ok) {
                // Update session info
                if (result.session_id) {
                    this.sessionId = result.session_id;
                }
                if (result.prompt) {
                    this.prompt.textContent = result.prompt;
                }
                if (result.cwd) {
                    this.currentDirectory = result.cwd;
                }

                // Display output
                if (result.stdout) {
                    this.appendOutput(result.stdout, 'output');
                }
                if (result.stderr) {
                    this.appendOutput(result.stderr, 'error');
                }
                if (result.return_code !== 0 && !result.stderr) {
                    this.appendOutput(`Command exited with code: ${result.return_code}`, 'error');
                }
            } else {
                this.appendOutput(`Error: ${result.error || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            this.appendOutput(`Network error: ${error.message}`, 'error');
        } finally {
            this.input.disabled = false;
            this.focusInput();
        }
    }

    async handleTabCompletion() {
        const command = this.input.value;
        if (!command.trim()) return;

        try {
            const response = await fetch('/shell/autocomplete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command: command,
                    session_id: this.sessionId
                })
            });

            const result = await response.json();
            if (result.suggestions && result.suggestions.length > 0) {
                if (result.suggestions.length === 1) {
                    // Single match - complete it
                    const suggestion = result.suggestions[0];
                    const parts = command.split(' ');
                    parts[parts.length - 1] = suggestion;
                    this.input.value = parts.join(' ') + ' ';
                } else {
                    // Multiple matches - show them
                    this.appendOutput(result.suggestions.join('  '), 'suggestion');
                }
            }
        } catch (error) {
            // Silently fail autocomplete
        }
    }

    handleAutocomplete() {
        // Visual feedback for potential completions could go here
    }

    navigateHistory(direction) {
        if (this.commandHistory.length === 0) return;

        if (direction === 'up') {
            if (this.historyIndex > 0) {
                this.historyIndex--;
                this.input.value = this.commandHistory[this.historyIndex];
            }
        } else if (direction === 'down') {
            if (this.historyIndex < this.commandHistory.length - 1) {
                this.historyIndex++;
                this.input.value = this.commandHistory[this.historyIndex];
            } else {
                this.historyIndex = this.commandHistory.length;
                this.input.value = '';
            }
        }
    }

    handleCtrlC() {
        this.appendOutput('^C', 'control');
        this.input.value = '';
    }

    clearTerminal() {
        this.output.innerHTML = '';
        this.displayWelcome();
    }

    appendOutput(text, type = 'output') {
        const div = document.createElement('div');
        div.className = `terminal-line terminal-${type}`;
        
        // Handle ANSI escape sequences for clear screen
        if (text.includes('\033[2J\033[H')) {
            this.clearTerminal();
            return;
        }
        
        div.textContent = text;
        this.output.appendChild(div);
        this.scrollToBottom();
    }

    scrollToBottom() {
        this.output.scrollTop = this.output.scrollHeight;
    }

    focusInput() {
        this.input.focus();
    }

    displayWelcome() {
        const welcomeMessages = [
            '🚀 Welcome to Vercel Web Shell!',
            '📦 Docker container running Ubuntu 22.04',
            '💡 Features: persistent sessions, command history, tab completion',
            '⚡ Use Ctrl+L to clear, Ctrl+C to cancel, ↑/↓ for history',
            '🔒 Security: Commands run in isolated container environment',
            ''
        ];

        welcomeMessages.forEach(msg => {
            this.appendOutput(msg, 'welcome');
        });
    }
}

// Initialize terminal when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.terminal = new WebTerminal('terminal-container');
});
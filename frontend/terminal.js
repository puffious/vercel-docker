class WebTerminal {
    constructor() {
        this.sessionId = null;
        this.commandHistory = [];
        this.historyIndex = -1;
        this.currentDirectory = '~';
        this.username = 'user';
        this.init();
    }

    init() {
        this.output = document.getElementById('output');
        this.input = document.getElementById('commandInput');
        this.prompt = document.getElementById('prompt');
        this.loading = document.getElementById('loading');
        
        if (!this.output || !this.input || !this.prompt) {
            console.error('Terminal elements not found!');
            return;
        }
        
        this.bindEvents();
        this.displayWelcome();
        this.focusInput();
    }

    bindEvents() {
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        
        // Focus input when clicking anywhere in terminal
        document.addEventListener('click', () => this.focusInput());
    }

    handleKeydown(e) {
        switch (e.key) {
            case 'Enter':
                e.preventDefault();
                this.executeCommand();
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.navigateHistory(-1);
                break;
            case 'ArrowDown':
                e.preventDefault();
                this.navigateHistory(1);
                break;
            case 'Tab':
                e.preventDefault();
                this.handleTabCompletion();
                break;
            case 'l':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.clearTerminal();
                }
                break;
        }
    }

    async executeCommand() {
        const command = this.input.value.trim();
        if (!command) return;
        
        // Add to history
        this.commandHistory.push(command);
        this.historyIndex = this.commandHistory.length;
        
        // Display command
        this.appendOutput(`${this.prompt.textContent} ${command}`, 'terminal-command');
        
        // Clear input
        this.input.value = '';
        
        // Show loading
        this.showLoading(true);
        
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
            
            if (result.session_id) {
                this.sessionId = result.session_id;
            }
            
            if (result.output) {
                this.appendOutput(result.output, result.success ? 'terminal-result' : 'terminal-error');
            }
            
            if (result.cwd) {
                this.currentDirectory = result.cwd;
                this.updatePrompt();
            }
            
        } catch (error) {
            this.appendOutput(`Error: ${error.message}`, 'terminal-error');
        } finally {
            this.showLoading(false);
            this.focusInput();
        }
    }

    navigateHistory(direction) {
        if (this.commandHistory.length === 0) return;
        
        if (direction === -1 && this.historyIndex > 0) {
            this.historyIndex--;
        } else if (direction === 1 && this.historyIndex < this.commandHistory.length - 1) {
            this.historyIndex++;
        } else if (direction === 1 && this.historyIndex === this.commandHistory.length - 1) {
            this.historyIndex = this.commandHistory.length;
            this.input.value = '';
            return;
        }
        
        if (this.historyIndex >= 0 && this.historyIndex < this.commandHistory.length) {
            this.input.value = this.commandHistory[this.historyIndex];
        }
    }

    handleTabCompletion() {
        const command = this.input.value;
        const commonCommands = ['ls', 'cd', 'pwd', 'mkdir', 'rm', 'cat', 'echo', 'ps', 'top', 'htop', 'ssh', 'curl'];
        
        const matches = commonCommands.filter(cmd => cmd.startsWith(command));
        if (matches.length === 1) {
            this.input.value = matches[0] + ' ';
        }
    }

    appendOutput(text, className = '') {
        const line = document.createElement('div');
        line.className = `terminal-line ${className}`;
        line.textContent = text;
        this.output.appendChild(line);
        this.scrollToBottom();
    }

    displayWelcome() {
        this.appendOutput('╔═══════════════════════════════════════════════╗', 'terminal-welcome');
        this.appendOutput('║         Vercel Web Terminal - SSH Ready      ║', 'terminal-welcome');
        this.appendOutput('╚═══════════════════════════════════════════════╝', 'terminal-welcome');
        this.appendOutput('', '');
        this.appendOutput('SSH Server: Running on port 2222', 'terminal-welcome');
        this.appendOutput('Type commands and press Enter. Ctrl+L to clear.', 'terminal-welcome');
        this.appendOutput('', '');
    }

    updatePrompt() {
        const shortDir = this.currentDirectory.replace(/\/home\/[^\/]+/, '~');
        this.prompt.textContent = `${this.username}@vercel:${shortDir}$ `;
    }

    showLoading(show) {
        if (this.loading) {
            this.loading.classList.toggle('active', show);
        }
    }

    focusInput() {
        if (this.input) {
            this.input.focus();
        }
    }

    scrollToBottom() {
        if (this.output) {
            this.output.scrollTop = this.output.scrollHeight;
        }
    }

    clearTerminal() {
        if (this.output) {
            this.output.innerHTML = '';
            this.displayWelcome();
        }
    }
}

// Initialize terminal when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing terminal...');
    window.terminal = new WebTerminal();
});
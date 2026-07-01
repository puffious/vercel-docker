from flask import Flask, jsonify, request, session
from flask_socketio import SocketIO, emit
import os
import subprocess
import uuid
import threading
import time
import signal
import shlex
from collections import defaultdict, deque
import json
import asyncio

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*")

# Session storage for persistent shell sessions
sessions = {}
command_history = defaultdict(lambda: deque(maxlen=1000))
running_processes = {}
tunnel_processes = {}

@app.route('/')
def home():
    # This route is technically now handled by the static frontend,
    # but good to keep for direct backend testing or if routing changes.
    return "Backend is running. Use /shell endpoint from the frontend."

@app.route('/info')
def info():
    try:
        result = subprocess.run(["lsb_release", "-a"], capture_output=True, text=True, check=True)
        ubuntu_details = result.stdout.strip()
    except FileNotFoundError:
        ubuntu_details = "lsb_release command not found."
    except subprocess.CalledProcessError as e:
        ubuntu_details = f"Error running lsb_release: {e.stderr.strip()}"

    return jsonify({
        "message": "This function is running inside an Ubuntu Docker container.",
        "os_details": ubuntu_details,
        "container_port_expected": os.environ.get("PORT", "80"),
        "process_id": os.getpid(),
        "env_vars": dict(os.environ)
    })

class ShellSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.cwd = os.path.expanduser('~')
        self.env = dict(os.environ)
        self.env['PS1'] = r'\u@vercel-shell:\w$ '
        self.history = deque(maxlen=1000)
        self.last_activity = time.time()
        
    def execute_command(self, command):
        self.last_activity = time.time()
        self.history.append(command)
        
        # Handle built-in commands
        if command.strip() == 'clear':
            return {'stdout': '\033[2J\033[H', 'stderr': '', 'return_code': 0}
        
        if command.strip().startswith('cd '):
            return self._handle_cd(command)
        
        if command.strip() == 'pwd':
            return {'stdout': self.cwd, 'stderr': '', 'return_code': 0}
        
        if command.strip() == 'history':
            history_output = '\n'.join([f'{i+1:4d}  {cmd}' for i, cmd in enumerate(self.history)])
            return {'stdout': history_output, 'stderr': '', 'return_code': 0}
        
        # Execute external commands
        try:
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.cwd,
                env=self.env
            )
            
            # Update cwd if command might have changed it
            if any(cmd in command for cmd in ['cd', 'pushd', 'popd']):
                try:
                    result = subprocess.run('pwd', shell=True, capture_output=True, text=True, cwd=self.cwd)
                    if result.returncode == 0:
                        self.cwd = result.stdout.strip()
                except:
                    pass
            
            return {
                'stdout': process.stdout,
                'stderr': process.stderr,
                'return_code': process.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'error': 'Command timed out (30s limit)',
                'stdout': '',
                'stderr': '',
                'return_code': 124
            }
        except Exception as e:
            return {
                'error': f'Execution error: {str(e)}',
                'stdout': '',
                'stderr': '',
                'return_code': 1
            }
    
    def _handle_cd(self, command):
        parts = shlex.split(command.strip())
        if len(parts) == 1:  # just 'cd'
            target = os.path.expanduser('~')
        else:
            target = parts[1]
        
        target = os.path.expanduser(target)
        if not os.path.isabs(target):
            target = os.path.join(self.cwd, target)
        
        target = os.path.normpath(target)
        
        if os.path.isdir(target):
            self.cwd = target
            return {'stdout': '', 'stderr': '', 'return_code': 0}
        else:
            return {'stdout': '', 'stderr': f'cd: {target}: No such file or directory', 'return_code': 1}
    
    def get_prompt(self):
        username = self.env.get('USER', 'user')
        short_cwd = self.cwd.replace(os.path.expanduser('~'), '~')
        return f'{username}@vercel-shell:{short_cwd}$ '

@app.route('/shell', methods=['POST'])
def shell_executor():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    command = data.get('command')
    session_id = data.get('session_id')

    if not command:
        return jsonify({"error": "No command provided"}), 400
    
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # Get or create session
    if session_id not in sessions:
        sessions[session_id] = ShellSession(session_id)
    
    shell_session = sessions[session_id]
    result = shell_session.execute_command(command)
    
    # Add session info to response
    result['session_id'] = session_id
    result['prompt'] = shell_session.get_prompt()
    result['cwd'] = shell_session.cwd
    
    return jsonify(result)

@app.route('/shell/autocomplete', methods=['POST'])
def autocomplete():
    data = request.get_json()
    partial_command = data.get('command', '')
    session_id = data.get('session_id')
    
    if session_id not in sessions:
        return jsonify({'suggestions': []})
    
    shell_session = sessions[session_id]
    
    try:
        # Simple file/directory completion
        if ' ' not in partial_command.strip():
            # Command completion
            result = subprocess.run(
                f'compgen -c {partial_command}',
                shell=True,
                capture_output=True,
                text=True,
                cwd=shell_session.cwd
            )
            suggestions = result.stdout.strip().split('\n')[:10] if result.stdout.strip() else []
        else:
            # File completion for last argument
            parts = shlex.split(partial_command)
            last_part = parts[-1] if parts else ''
            
            result = subprocess.run(
                f'compgen -f {last_part}',
                shell=True,
                capture_output=True,
                text=True,
                cwd=shell_session.cwd
            )
            suggestions = result.stdout.strip().split('\n')[:10] if result.stdout.strip() else []
        
        return jsonify({'suggestions': [s for s in suggestions if s]})
    except:
        return jsonify({'suggestions': []})

@app.route('/shell/history', methods=['GET'])
def get_history():
    session_id = request.args.get('session_id')
    if session_id not in sessions:
        return jsonify({'history': []})
    
@app.route('/tunnel/start', methods=['POST'])
def start_tunnel():
    """Start various types of reverse tunnels for SSH access"""
    data = request.get_json()
    tunnel_type = data.get('type', 'serveo')  # serveo, ngrok, cloudflare, localtunnel
    
    if tunnel_type in tunnel_processes:
        return jsonify({'error': f'{tunnel_type} tunnel already running', 'pid': tunnel_processes[tunnel_type]})
    
    try:
        if tunnel_type == 'serveo':
            # Serveo.net reverse SSH tunnel - map remote port 22 to local SSH port 2222
            cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', 
                   '-R', '0:localhost:2222', 'serveo.net']
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                     text=True, bufsize=1, universal_newlines=True)
            
            # Wait for tunnel URL from Serveo
            tunnel_url = None
            tunnel_host = None
            tunnel_port = None
            
            for i in range(60):  # Wait up to 60 seconds
                if process.poll() is not None:
                    break
                try:
                    # Read output line by line
                    line = process.stdout.readline()
                    if line:
                        print(f"Serveo output: {line.strip()}")
                        # Look for forwarding info like "Forwarding SSH traffic from https://abc123.serveo.net"
                        # Or "ssh://serveo.net:12345" format
                        import re
                        
                        # Pattern 1: "Forwarding SSH traffic from https://xxx.serveo.net"
                        url_match = re.search(r'https://([a-zA-Z0-9.-]+\.serveo\.net)', line)
                        if url_match:
                            tunnel_host = url_match.group(1)
                            tunnel_url = url_match.group(0)
                            break
                            
                        # Pattern 2: "tcp://serveo.net:port" or similar
                        tcp_match = re.search(r'tcp://serveo\.net:(\d+)', line)
                        if tcp_match:
                            tunnel_port = tcp_match.group(1)
                            tunnel_host = 'serveo.net'
                            tunnel_url = f'ssh://serveo.net:{tunnel_port}'
                            break
                            
                        # Pattern 3: Direct port assignment
                        port_match = re.search(r'Allocated port (\d+) for', line)
                        if port_match:
                            tunnel_port = port_match.group(1)
                            tunnel_host = 'serveo.net'
                            tunnel_url = f'ssh://serveo.net:{tunnel_port}'
                            break
                except Exception as e:
                    print(f"Error reading Serveo output: {e}")
                time.sleep(0.5)
            
        elif tunnel_type == 'serveo-custom':
            # Custom subdomain with serveo
            subdomain = data.get('subdomain', f'vercel-{uuid.uuid4().hex[:8]}')
            cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
                   '-R', f'{subdomain}:22:localhost:2222', 'serveo.net']
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            tunnel_url = f'ssh://{subdomain}.serveo.net:22'
            tunnel_host = f'{subdomain}.serveo.net'
            tunnel_port = '22'
            
        elif tunnel_type == 'localtunnel':
            # Using localtunnel for HTTP tunnel, then SSH through it
            cmd = ['npx', 'localtunnel', '--port', '2222']
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            tunnel_url = None  # Would need to parse localtunnel output
            
        elif tunnel_type == 'cloudflare':
            # Cloudflare tunnel (requires cloudflared)
            tunnel_name = data.get('tunnel_name', 'vercel-ssh')
            cmd = ['cloudflared', 'tunnel', '--url', 'ssh://localhost:2222']
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            tunnel_url = None  # Would need to parse cloudflare output
            
        else:
            return jsonify({'error': 'Unsupported tunnel type'}), 400
        
        tunnel_processes[tunnel_type] = {
            'pid': process.pid,
            'process': process,
            'url': tunnel_url,
            'host': tunnel_host,
            'port': tunnel_port
        }
        
        # Start SSH server if not running
        start_ssh_server()
        
        response_data = {
            'success': True,
            'tunnel_type': tunnel_type,
            'pid': process.pid,
            'message': f'{tunnel_type} tunnel started',
            'ssh_port': 2222
        }
        
        if tunnel_url and tunnel_host:
            response_data['tunnel_url'] = tunnel_url
            response_data['tunnel_host'] = tunnel_host
            if tunnel_port:
                response_data['tunnel_port'] = tunnel_port
                response_data['ssh_command'] = f'ssh -p {tunnel_port} root@{tunnel_host}'
            else:
                response_data['ssh_command'] = f'ssh root@{tunnel_host}'
        elif not tunnel_url:
            response_data['warning'] = 'Tunnel started but URL not detected. Check logs.'
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Failed to start {tunnel_type} tunnel: {str(e)}'}), 500

@app.route('/tunnel/stop', methods=['POST'])
def stop_tunnel():
    """Stop a running tunnel"""
    data = request.get_json()
    tunnel_type = data.get('type')
    
    if tunnel_type not in tunnel_processes:
        return jsonify({'error': f'No {tunnel_type} tunnel running'})
    
    try:
        tunnel_info = tunnel_processes[tunnel_type]
        # Handle both old (pid only) and new (dict with pid/process/url) formats
        if isinstance(tunnel_info, dict):
            pid = tunnel_info['pid']
            process = tunnel_info.get('process')
        else:
            pid = tunnel_info
            process = None
        
        # Try to terminate gracefully first
        if process:
            process.terminate()
        else:
            os.kill(pid, signal.SIGTERM)
        
        del tunnel_processes[tunnel_type]
        
        return jsonify({
            'success': True,
            'message': f'{tunnel_type} tunnel stopped'
        })
    except Exception as e:
        return jsonify({'error': f'Failed to stop tunnel: {str(e)}'}), 500

@app.route('/tunnel/status')
def tunnel_status():
    """Get status of all tunnels"""
    active_tunnels = {}
    
    for tunnel_type, tunnel_info in list(tunnel_processes.items()):
        try:
            # Handle both old (pid only) and new (dict with pid/process/url) formats
            if isinstance(tunnel_info, dict):
                pid = tunnel_info['pid']
                tunnel_url = tunnel_info.get('url')
                tunnel_host = tunnel_info.get('host')
                tunnel_port = tunnel_info.get('port')
            else:
                pid = tunnel_info
                tunnel_url = None
                tunnel_host = None
                tunnel_port = None
            
            # Check if process is still running
            os.kill(pid, 0)
            tunnel_data = {'pid': pid, 'status': 'running'}
            if tunnel_url:
                tunnel_data['url'] = tunnel_url
            if tunnel_host:
                tunnel_data['host'] = tunnel_host
                if tunnel_port:
                    tunnel_data['port'] = tunnel_port
                    tunnel_data['ssh_command'] = f'ssh -p {tunnel_port} root@{tunnel_host}'
                else:
                    tunnel_data['ssh_command'] = f'ssh root@{tunnel_host}'
            active_tunnels[tunnel_type] = tunnel_data
        except OSError:
            # Process not running, remove from dict
            del tunnel_processes[tunnel_type]
    
    return jsonify({
        'active_tunnels': active_tunnels,
        'ssh_server_port': 2222,
        'available_types': ['serveo', 'serveo-custom', 'localtunnel', 'cloudflare']
    })

def start_ssh_server():
    """Start SSH server if not already running"""
    try:
        # Check if SSH server is running
        result = subprocess.run(['pgrep', 'sshd'], capture_output=True)
        if result.returncode != 0:
            # Start SSH server
            subprocess.Popen(['/usr/sbin/sshd', '-D', '-p', '2222'], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            time.sleep(1)  # Give it time to start
    except Exception as e:
        print(f"Error starting SSH server: {e}")

@app.route('/ssh/info')
def ssh_info():
    """Get SSH connection information"""
    return jsonify({
        'ssh_port': 2222,
        'users': {
            'root': 'vercel123',
            'shelluser': 'shell123'
        },
        'connection_examples': {
            'direct': 'ssh -p 2222 root@<tunnel-url>',
            'with_key': 'ssh -p 2222 -i ~/.ssh/id_rsa root@<tunnel-url>',
            'port_forward': 'ssh -p 2222 -L 8080:localhost:80 root@<tunnel-url>'
        },
        'security_note': 'Change default passwords in production!'
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 80))
    print(f"Flask app starting on 0.0.0.0:{port}")
    
    # Start SSH server in background
    try:
        start_ssh_server()
        print("SSH server started on port 2222")
    except Exception as e:
        print(f"Warning: Could not start SSH server: {e}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
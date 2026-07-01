from flask import Flask, jsonify, request
import os
import subprocess

app = Flask(__name__)

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

@app.route('/shell', methods=['POST'])
def shell_executor():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    command = data.get('command')

    if not command:
        return jsonify({"error": "No command provided"}), 400

    # --- SECURITY WARNING ---
    # Running arbitrary commands from user input is EXTREMELY DANGEROUS.
    # For a real application, you must sanitize input,
    # whitelist commands, or prevent direct execution.
    # This POC uses shell=True for simplicity, but it's risky.
    # --- END SECURITY WARNING ---

    try:
        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return jsonify({
            "command": command,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
            "return_code": process.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            "error": "Command timed out",
            "command": command
        }), 408
    except Exception as e:
        return jsonify({
            "error": f"An unexpected error occurred: {str(e)}",
            "command": command
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 80))
    print(f"Flask app starting on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port)
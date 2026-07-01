from flask import Flask, jsonify
import os
import subprocess

# Corrected: Use __name__ to initialize the Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return "Hello from an Ubuntu Docker image running on Vercel! Try /info for details."

@app.route('/info')
def info():
    # Execute lsb_release to confirm Ubuntu details
    try:
        result = subprocess.run(["lsb_release", "-a"], capture_output=True, text=True, check=True)
        ubuntu_details = result.stdout.strip()
    except FileNotFoundError:
        ubuntu_details = "lsb_release command not found (unlikely if apt-get ran correctly)."
    except subprocess.CalledProcessError as e:
        ubuntu_details = f"Error running lsb_release: {e.stderr.strip()}"

    return jsonify({
        "message": "This function is running inside an Ubuntu Docker container.",
        "os_details": ubuntu_details,
        "container_port_expected": os.environ.get("PORT", "80"), # Show which port Flask is trying to bind to
        "process_id": os.getpid(),
        "env_vars": dict(os.environ) # Show all environment variables, useful for debugging
    })

if __name__ == '__main__':
    # Get the port from the environment variable (default to 80 if not set)
    port = int(os.environ.get("PORT", 80))
    print(f"Flask app starting on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port)
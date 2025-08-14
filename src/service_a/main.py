import os
import importlib.util
from flask import Flask, request
from google.cloud import storage

# Initialize Flask app
app = Flask(__name__)

# Download and load the shared module from GCS
try:
    # Get config from environment variables
    module_bucket_name = os.environ["MODULE_BUCKET"]
    module_name = os.environ["MODULE_NAME"] # e.g., "helper.py"

    local_module_path = f"/tmp/{module_name}"

    # Download the module file
    storage_client = storage.Client()
    bucket = storage_client.bucket(module_bucket_name)
    blob = bucket.blob(module_name)
    blob.download_to_filename(local_module_path)

    # Dynamically import the module
    spec = importlib.util.spec_from_file_location("helper", local_module_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

except Exception as e:
    # If the module fails to load, create a dummy module to allow the app to start
    # This helps with initial deployment and debugging.
    print(f"Error loading module from GCS: {e}")
    print("Creating a dummy 'helper' module.")
    class DummyHelper:
        def greet(self, name):
            return f"Hello, {name}! (dummy module)"
        def add(self, a, b):
            return a + b
    helper = DummyHelper()


@app.route("/")
def index():
    return "Service A is running."

@app.route("/greet")
def greet_endpoint():
    name = request.args.get("name", "World")
    return helper.greet(name)

@app.route("/add")
def add_endpoint():
    try:
        a = int(request.args.get("a", 0))
        b = int(request.args.get("b", 0))
        result = helper.add(a, b)
        return str(result)
    except ValueError:
        return "Invalid input. Please provide integers for 'a' and 'b'.", 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

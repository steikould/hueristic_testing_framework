import os
import json
import datetime
import requests
import functions_framework
from google.cloud import storage

# --- Configuration ---
CONFIG_BUCKET = os.environ.get("CONFIG_BUCKET")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET")
CONFIG_NAME = os.environ.get("CONFIG_NAME", "config.json")

# Service URLs are injected as environment variables
SERVICE_URLS = {
    "service-a": os.environ.get("SERVICE_A_URL"),
    "service-b": os.environ.get("SERVICE_B_URL"),
}

storage_client = storage.Client()

# --- Assertion Logic ---
def perform_assertion(assertion, response, response_text):
    """Performs a single assertion and returns a result dictionary."""
    source = assertion["source"]
    comparison = assertion["comparison"]
    expected = assertion["expected_value"]

    actual = None
    if source == "status_code":
        actual = response.status_code
    elif source == "body":
        actual = response_text
    elif source == "headers":
        actual = response.headers.get(assertion["property"])

    passed = False
    if comparison == "equals":
        passed = (actual == expected)
    elif comparison == "contains":
        passed = (expected in actual)

    return {
        "assertion": f"{source} {comparison} {expected}",
        "passed": passed,
        "actual": actual
    }

# --- Test Execution ---
def run_single_test(test_config):
    """Runs a single test case and returns the results."""
    service_name = test_config["service"]
    base_url = SERVICE_URLS.get(service_name)

    if not base_url:
        return {"test_name": test_config["test_name"], "error": f"Service URL for '{service_name}' not configured."}

    full_url = base_url + test_config["endpoint"]
    method = test_config["method"]
    params = test_config.get("params")

    try:
        response = requests.request(method, full_url, params=params, timeout=10)
        response_text = response.text
    except requests.RequestException as e:
        return {"test_name": test_config["test_name"], "error": str(e)}

    # Perform assertions
    assertion_results = []
    for assertion in test_config["assertions"]:
        result = perform_assertion(assertion, response, response_text)
        assertion_results.append(result)

    overall_passed = all(r["passed"] for r in assertion_results)

    return {
        "test_name": test_config["test_name"],
        "passed": overall_passed,
        "service": service_name,
        "url": full_url,
        "status_code": response.status_code,
        "response_body": response_text,
        "assertions": assertion_results
    }


# --- Cloud Function Entry Point ---
@functions_framework.http
def run_tests(request):
    """HTTP-triggered Cloud Function to run the testing framework."""

    # --- 1. Load Test Configuration from GCS ---
    try:
        config_bucket = storage_client.bucket(CONFIG_BUCKET)
        config_blob = config_bucket.blob(CONFIG_NAME)
        config_data = json.loads(config_blob.download_as_string())
        tests = config_data["tests"]
    except Exception as e:
        print(f"Error loading config: {e}")
        return f"Error loading test configuration from GCS: {e}", 500

    # --- 2. Run Tests ---
    test_results = [run_single_test(test) for test in tests]

    # --- 3. Store Results in GCS ---
    results_data = {
        "run_timestamp_utc": datetime.datetime.utcnow().isoformat(),
        "results": test_results
    }

    try:
        results_bucket = storage_client.bucket(RESULTS_BUCKET)
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        results_filename = f"results-{timestamp}.json"
        results_blob = results_bucket.blob(results_filename)
        results_blob.upload_from_string(json.dumps(results_data, indent=2))
    except Exception as e:
        print(f"Error saving results: {e}")
        return f"Error saving test results to GCS: {e}", 500

    # --- 4. Return Summary ---
    summary = {
        "message": f"Test run complete. Results saved to {results_filename}",
        "total_tests": len(test_results),
        "passed": sum(1 for r in test_results if r.get("passed")),
        "failed": sum(1 for r in test_results if not r.get("passed")),
    }

    return json.dumps(summary), 200

import argparse
import json
from google.cloud import storage

def get_latest_result_files(bucket_name):
    """Finds the two most recent result files in a GCS bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix="results-"))

    if len(blobs) < 2:
        print("Error: Fewer than two result files found in the bucket.")
        return None, None

    # Sort blobs by creation time, descending
    blobs.sort(key=lambda x: x.time_created, reverse=True)

    latest_file = blobs[0].name
    previous_file = blobs[1].name

    print(f"Found latest files: {latest_file}, {previous_file}")
    return latest_file, previous_file

def download_result_file(bucket_name, filename):
    """Downloads a result file from GCS and returns its JSON content."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        data = json.loads(blob.download_as_string())
        return data
    except Exception as e:
        print(f"Error downloading or parsing {filename}: {e}")
        return None

def compare_results(old_results, new_results):
    """Compares two sets of test results and prints a summary."""

    old_tests = {r["test_name"]: r for r in old_results["results"]}
    new_tests = {r["test_name"]: r for r in new_results["results"]}

    regressions = []
    fixes = []

    for name, new_test in new_tests.items():
        if name in old_tests:
            old_test = old_tests[name]
            if old_test.get("passed") and not new_test.get("passed"):
                regressions.append(name)
            elif not old_test.get("passed") and new_test.get("passed"):
                fixes.append(name)

    added_tests = set(new_tests.keys()) - set(old_tests.keys())
    removed_tests = set(old_tests.keys()) - set(new_tests.keys())

    print("\n--- Test Comparison Summary ---")
    print(f"Comparing '{old_results['run_timestamp_utc']}' (Old) with '{new_results['run_timestamp_utc']}' (New)\n")

    if fixes:
        print(f"✅ Fixes ({len(fixes)}):")
        for name in fixes:
            print(f"  - {name}")

    if regressions:
        print(f"\n❌ Regressions ({len(regressions)}):")
        for name in regressions:
            print(f"  - {name}")

    if added_tests:
        print(f"\n✨ Added Tests ({len(added_tests)}):")
        for name in added_tests:
            print(f"  - {name}")

    if removed_tests:
        print(f"\n🗑️ Removed Tests ({len(removed_tests)}):")
        for name in removed_tests:
            print(f"  - {name}")

    if not any([fixes, regressions, added_tests, removed_tests]):
        print("No changes in test outcomes between the two runs.")

def main():
    parser = argparse.ArgumentParser(description="Compare two test result files from GCS.")
    parser.add_argument("bucket_name", help="The GCS bucket where results are stored.")
    parser.add_argument("--files", nargs=2, help="Optional: Two specific result filenames to compare.", metavar=("FILE1", "FILE2"))

    args = parser.parse_args()

    if args.files:
        file1, file2 = args.files
    else:
        print("No specific files provided. Finding the two latest result files...")
        file1, file2 = get_latest_result_files(args.bucket_name)
        if not file1:
            return

    # file1 should be the older one, file2 the newer one
    if file1 > file2:
        file1, file2 = file2, file1

    print(f"\nDownloading and comparing '{file1}' (Old) and '{file2}' (New)...")
    old_data = download_result_file(args.bucket_name, file1)
    new_data = download_result_file(args.bucket_name, file2)

    if old_data and new_data:
        compare_results(old_data, new_data)

if __name__ == "__main__":
    main()

"""Cloud Run function entry point: each call stores one snapshot in the bronze
bucket. Deployed to europe-central2, because the Warsaw API only accepts
connections from Polish addresses."""

import functions_framework

from bronze_data_collector_warsaw_gcp import collect


@functions_framework.http
def collect_snapshot(request):
    # Cloud Run's trace id ties the stored file to this call's logs
    trace_id = request.headers.get("X-Cloud-Trace-Context", "").split("/")[0]
    count, target = collect(collector="cloud_run", run_id=trace_id or None)
    message = f"Saved {count} parkings to {target}"
    print(message)
    return message

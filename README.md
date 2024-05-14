# GKE Node Pool Observability Script

## Overview
This Python script collects node pool metrics (current node count, maximum node count, and node usage percentage) from multiple GKE clusters and sends them to New Relic using the New Relic Telemetry SDK.

### Features
- Retrieves all GKE clusters and their node pools within the specified GCP projects and regions.
- Calculates node pool usage metrics: current node count, max node count, and node usage percentage.
- Sends node pool metrics to New Relic.


### Main Execution

The script defines a list of GCP project IDs and a region, and then collects metrics from all clusters and node pools within these projects. Finally, it sends the collected metrics to New Relic.

### Required Environment Variables

- **NEW_RELIC_API_KEY:** The New Relic Insights Insert API Key for authentication.
  
### Example Usage

```bash
export GCP_PROJECT_IDS="staging,production,other-env"
export GCP_REGION="us-central1"
export NEW_RELIC_API_KEY="your-new-relic-api-key"
export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/gsa-key.json"

python gke_node_pool_observability.py
```

### Dependencies

Install dependencies using:

```bash
pip install google-cloud-container google-cloud-compute newrelic-telemetry-sdk tenacity
```

from google.cloud import container_v1, compute_v1
from newrelic_telemetry_sdk import MetricClient, GaugeMetric
import os
import time
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

RETRY_ATTEMPTS = 5
RETRY_WAIT = 2  # seconds

@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT), retry=retry_if_exception_type(Exception))
def get_all_clusters_and_node_pools(project_id, region):
    """
    Retrieves all clusters and their node pools within a specific project and region.

    Args:
        project_id (str): GCP project ID.
        region (str): GCP region.

    Returns:
        dict: A dictionary containing cluster names as keys and a list of their node pools as values.
    """
    client = container_v1.ClusterManagerClient()
    parent = f"projects/{project_id}/locations/{region}"

    clusters = client.list_clusters(parent=parent).clusters

    cluster_node_pools = {}
    for cluster in clusters:
        node_pools = client.list_node_pools(parent=f"projects/{project_id}/locations/{region}/clusters/{cluster.name}").node_pools
        cluster_node_pools[cluster.name] = [node_pool.name for node_pool in node_pools]

    return cluster_node_pools


@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT), retry=retry_if_exception_type(Exception))
def get_instance_group_node_count(instance_group_url):
    """
    Retrieves the current node count in a specific instance group.

    Args:
        instance_group_url (str): Full URL of the GCP instance group.

    Returns:
        int: The current node count in the instance group.
    """
    parts = instance_group_url.split('/')
    project = parts[6]
    zone = parts[8]
    instance_group = parts[10]

    client = compute_v1.InstanceGroupsClient()
    response = client.list_instances(project=project, zone=zone, instance_group=instance_group).items

    return len(response) if response else 0


@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT), retry=retry_if_exception_type(Exception))
def get_node_pool_info(project_id, region, cluster_name, node_pool_name):
    """
    Retrieves the current and maximum node count for a specific node pool in a GKE cluster.

    Args:
        project_id (str): GCP project ID.
        region (str): GCP region where the cluster is hosted.
        cluster_name (str): GKE cluster name.
        node_pool_name (str): GKE node pool name.

    Returns:
        dict: A dictionary containing the current node count, max node count, and node usage percentage.
    """
    client = container_v1.ClusterManagerClient()
    node_pool_path = f"projects/{project_id}/locations/{region}/clusters/{cluster_name}/nodePools/{node_pool_name}"

    node_pool = client.get_node_pool(name=node_pool_path)

    current_node_count = sum(get_instance_group_node_count(url) for url in node_pool.instance_group_urls)
    max_node_count = node_pool.autoscaling.max_node_count

    return {
        "current_node_count": current_node_count,
        "max_node_count": max_node_count,
        "node_usage_percent": (current_node_count / max_node_count) * 100 if max_node_count else 0
    }

@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT), retry=retry_if_exception_type(Exception))
def send_metrics_to_newrelic(metrics_client, project_id, region, cluster_name, node_pool_name, node_pool_info):
    """
    Sends node pool metrics to New Relic.

    Args:
        metrics_client (MetricsClient): The New Relic Telemetry SDK Metrics client.
        project_id (str): GCP project ID.
        region (str): GCP region where the cluster is hosted.
        cluster_name (str): GKE cluster name.
        node_pool_name (str): GKE node pool name.
        node_pool_info (dict): The node pool information containing current and max node count and usage percentage.
    """
    tags = {
        "project_id": project_id,
        "region": region,
        "cluster_name": cluster_name,
        "node_pool_name": node_pool_name
    }

    metrics = [
        GaugeMetric("gke.node_pool.current_node_count", node_pool_info["current_node_count"], tags=tags),
        GaugeMetric("gke.node_pool.max_node_count", node_pool_info["max_node_count"], tags=tags),
        GaugeMetric("gke.node_pool.node_usage_percent", node_pool_info["node_usage_percent"], tags=tags)
    ]

    response = metrics_client.send_batch(metrics)
    response.raise_for_status()
    print("Sent metrics successfully!")


@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT), retry=retry_if_exception_type(Exception))
def list_clusters_and_node_pools_info_and_send_metrics(project_ids, region):
    """
    Lists clusters and their node pools' current and maximum node counts for multiple projects
    and sends the metrics to New Relic.

    Args:
        project_ids (list): List of GCP project IDs.
        region (str): GCP region where the clusters are hosted.

    Returns:
        None
    """
    metrics_client = MetricClient(os.getenv("NEW_RELIC_API_KEY"))
    

    for project_id in project_ids:
        print(f"\nProject: {project_id}")
        clusters_and_pools = get_all_clusters_and_node_pools(project_id, region)

        for cluster_name, node_pools in clusters_and_pools.items():
            print(f"  Cluster: {cluster_name}")
            for node_pool_name in node_pools:
                node_pool_info = get_node_pool_info(project_id, region, cluster_name, node_pool_name)
                print(
                    f"    Node Pool: {node_pool_name}\n"
                    f"      Current Node Count: {node_pool_info['current_node_count']}\n"
                    f"      Max Node Count: {node_pool_info['max_node_count']}\n"
                    f"      Node Usage Percent: {node_pool_info['node_usage_percent']:.2f}%\n"
                )
                send_metrics_to_newrelic(metrics_client, project_id, region, cluster_name, node_pool_name, node_pool_info)


if __name__ == "__main__":
    PROJECT_IDS_STR = os.getenv("GCP_PROJECT_IDS", "")
    REGION = os.getenv("GCP_REGION", "us-central1")

    PROJECT_IDS = PROJECT_IDS_STR.split(",") if PROJECT_IDS_STR else []

    if not PROJECT_IDS:
        print("No project IDs found. Set the GCP_PROJECT_IDS environment variable.")
    else:
        list_clusters_and_node_pools_info_and_send_metrics(PROJECT_IDS, REGION)

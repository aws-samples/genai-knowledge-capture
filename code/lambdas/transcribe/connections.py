import os
import boto3


class Connections:
    """
    Manage connections
    """

    namespace = "DocumentGenerator"
    service_name = os.environ["POWERTOOLS_SERVICE_NAME"]
    region_name = os.environ["AWS_REGION"]
    s3_bucket_transcribe = os.environ["DATA_SOURCE_BUCKET_NAME"]

    transcribe_client = boto3.client("transcribe", region_name=region_name)
    s3_client = boto3.client("s3", region_name=region_name)

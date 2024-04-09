import os
import boto3
from aws_lambda_powertools import Logger, Tracer, Metrics

tracer = Tracer()
logger = Logger(log_uncaught_exceptions=True, serialize_stacktrace=True)
metrics = Metrics()


class Connections:
    """
    A class to maintain connections to external dependencies

    Attributes
    ----------
    region_name : str
        The AWS Region name where the AWS Lambda function is running.
        Depends on the environmental variable 'AWS_REGION'
    s3_bucket_name : str
        Name of the S3 bucket to use for storing the generated documents.
    service_name: str
        Name of the service assigned and configured through AWS Powertools for
        logging. Depends on the environmental variable 'POWERTOOLS_SERVICE_NAME'
    s3_client : boto3.client
        Boto3 client to interact with AWS S3 bucket
    """

    region_name = os.environ["AWS_REGION"]
    s3_bucket_name = os.environ["DATA_SOURCE_BUCKET_NAME"]
    service_name = os.environ["POWERTOOLS_SERVICE_NAME"]

    s3_client = boto3.client(service_name="s3", region_name=region_name)

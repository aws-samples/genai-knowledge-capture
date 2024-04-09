from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.parser import event_parser, BaseModel
from connections import Connections, tracer, logger, metrics
from dataclasses import dataclass
from exceptions import CodeError
from s3url import S3Url
from typing import List

s3_client = Connections.s3_client


@dataclass
class Response:
    """
    A class for representing the Output format of the AWS Lambda

    Attributes:
    -----------
    statusCode: int
        A HTTP status code that denotes the output status of validation.
        A `200` values means validation completed successfully
    documentName: str
        A string that denotes the name of the document that is being processed.
    audioFilesS3Uris: List[str]
        A list of string containing the S3 object URLs of the audio files in the
        given path as input
    serviceName: str
        The name of the AWS Lambda as configured through AWS powertools
    """

    statusCode: int
    documentName: str
    audioFilesS3Uris: List[str]
    serviceName: str = Connections.service_name


class Request(BaseModel):
    """
    A class for representing the Input format of the AWS Lambda

    Attributes:
    -----------
    audioFileFolderUri: str
        The S3 folder path containing the audio files to be processed.
    documentName: str
        A string that denotes the name of the document that is being processed.
    """

    documentName: str
    audioFileFolderUri: str


@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
@event_parser(model=Request)
def lambda_handler(event: Request, context: LambdaContext):
    """
    This is main function that is invoked when AWS Lambda is triggered.
    It validates the input and identifies the audio files present in the
    S3 folder path mentioned.

    Arguments:
    ----------
        event (dict): The input data from Step function
        context (LambdaContext): This object provides methods and
            properties that provide information about the invocation,
            function, and execution environment.

    Returns:
    --------
        Response: The output data from Step function in json format
    """
    metrics.add_metric(name="TotalPreprocessInvocation", unit=MetricUnit.Count, value=1)
    logger.info(f"Input event: {event}")

    # Validate the input event
    if not event.audioFileFolderUri:
        msg = "The input event is missing the required 'audioFileFolderUri' field"
        logger.error(msg)
        raise CodeError(
            "Invalid input event",
            msg,
        )

    # Validate the input event
    if not event.documentName:
        msg = "The input event is missing the required 'documentName' field"
        logger.error(msg)
        raise CodeError(
            "Invalid input event",
            msg,
        )

    # Identify the audio files present in the S3 folder path
    audio_files_s3_uris = get_audio_files_s3_uris(event.audioFileFolderUri)
    logger.info(f"Audio files S3 URIs are {audio_files_s3_uris}")

    statusCode = 200 if len(audio_files_s3_uris) > 0 else 400
    response = Response(
        statusCode=statusCode,
        documentName=event.documentName,
        audioFilesS3Uris=audio_files_s3_uris,
    ).__dict__
    metrics.add_metric(name="PreprocessingSuccessful", unit=MetricUnit.Count, value=1)

    logger.debug(f"Lambda Output: {response}")

    return response


@tracer.capture_method
def get_audio_files_s3_uris(audio_file_folder_uri: str) -> List[str]:
    """
    This function identifies the audio files present in the S3 folder path
    mentioned.

    Arguments:
    ----------
        audio_file_folder_uri (str): The S3 folder path containing the
            audio files to be processed.

    Returns:
    --------
        List[str]: A list of string containing the S3 object URLs of the
            audio files in the given path as input
    """
    # Identify the audio files present in the S3 folder path
    audio_files_s3_uris = []
    try:
        logger.info("Parsing input S3 URI")
        audio_file_folder_uri_parsed = S3Url(audio_file_folder_uri)
        logger.debug(f"Parsed input S3 URI: {audio_file_folder_uri_parsed}")

        # List the objects in the S3 folder path
        response = s3_client.list_objects_v2(
            Bucket=audio_file_folder_uri_parsed.bucket,
            Prefix=audio_file_folder_uri_parsed.key,
        )
        for content in response.get("Contents", []):
            audio_files_s3_uris.append(
                f's3://{audio_file_folder_uri_parsed.bucket}/{content["Key"]}'
            )
    except Exception as e:
        msg = f"Error while identifying audio files: {e}"
        logger.warning(msg, stack_info=True)
        raise CodeError(
            msg,
            f"Error while identifying audio files in the S3 folder path: {audio_file_folder_uri}",
        )

    if len(audio_files_s3_uris) == 0:
        msg = f"No audio files found in the S3 folder path: {audio_file_folder_uri}"
        raise CodeError(msg)

    return audio_files_s3_uris

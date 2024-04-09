import time
from dataclasses import dataclass
from topic_classification import answer_anomaly_detection
from utils import generate_dataframe_from_files
from connections import Connections, tracer, logger, metrics
from exceptions import CodeError
from typing import List
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.parser import event_parser, BaseModel


@dataclass
class Response:
    statusCode: int
    documentName: str
    validAnswersS3Uris: List[str]
    continueSummarization: bool
    invalidAnswersS3Uris: List[str]
    serviceName: str = Connections.service_name


class Request(BaseModel):
    """
    A class for representing the Input format of the AWS Lambda

    Attributes:
    -----------
    statusCode: int
        A HTTP status code that denotes the output status of validation.
        A `200` values means validation completed successfully
    documentName: str
        A string that denotes the output status of validation.
    transcribedFilesS3Uris: List (str)
        A list of S3 URIs that contain the transcribed files.
    serviceName: str
        The name of the AWS Lambda as configured through AWS powertools.
    """

    statusCode: int
    documentName: str
    transcribedFilesS3Uris: List[str]
    serviceName: str


@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
@event_parser(model=Request)
def lambda_handler(event: Request, context: LambdaContext) -> str:
    metrics.add_metric(
        name="TotalTopicAnalysisInvocation", unit=MetricUnit.Count, value=1
    )

    logger.info("Running Topic Analysis")
    logger.debug(f"Received event: {event}")

    # Topic Modeling Analysis
    transcribedFilesS3Uris = event.transcribedFilesS3Uris
    statusCode = None

    # Retrieve all answers for the given answerTextPath
    df_input = generate_dataframe_from_files(transcribedFilesS3Uris)
    logger.debug(f"Input Dataframe size for topic analysis (validate): {len(df_input)}")

    # Build a dictionary mapping index to uris
    index_uri_dict = dict(zip(df_input["index"], df_input["list_of_answer_text_uris"]))

    # Convert the answer_id and answer into a list of JSON files
    answer_id_list = df_input["index"].astype(str).tolist()
    list_answers_w_index = df_input[["index", "answer"]].to_dict(orient="records")
    question = df_input.question.iloc[0]

    # Logic:
    # Option 1: if all decision are None, do topic analysis, then update the answers table by 'decision' column.
    continueSummarization = False
    on_topic_answer_id_list = []
    off_topic_answer_id_list = []
    response_time = 0

    # Define the maximum number of retry attempts
    max_retries = 3
    retry_count = 0
    base_wait_time = 2
    logger.info(f"Start Topic Analysis for the question {question}")

    while retry_count < max_retries:
        try:
            # Start timer
            start_time = time.time()
            ans = answer_anomaly_detection(
                model_name="Claude3",
                list_answers_w_index=list_answers_w_index,
                input_question=question,
            )
            logger.debug(f"Off-topic answers list: {ans}")
            # End timer
            end_time = time.time()
            # Calculate response time in seconds
            response_time = end_time - start_time
            off_topic_answer_id_list = ans.off_topic_answers
            break  # If the function succeeds, exit the loop
        except Exception as e:
            logger.debug(f"An error occurred during topic analysis: {e}")
            wait_time = base_wait_time * (2**retry_count)
            logger.warning(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            retry_count += 1

    if retry_count == max_retries:
        on_topic_answer_id_list = []
        off_topic_answer_id_list = []
        logger.error("Max retries reached. The function could not be executed.")
        raise CodeError("An error occurred during topic analysis")
    else:
        logger.info("Function executed successfully.")

    on_topic_answer_uri_list = []
    off_topic_answer_uri_list = []
    if off_topic_answer_id_list != []:
        if off_topic_answer_id_list != ["-1"]:
            off_topic_answer_uri_list = [
                index_uri_dict[idx] for idx in off_topic_answer_id_list
            ]
            # Log the answers that failed
            logger.info(
                f"The answers with uris {off_topic_answer_uri_list} are off topic for the question {question}."
            )
            # Get the answer_ids that passed
            on_topic_answer_id_list = list(
                set(answer_id_list) - set(off_topic_answer_id_list)
            )
            on_topic_answer_uri_list = [
                index_uri_dict[idx] for idx in on_topic_answer_id_list
            ]
            logger.info(
                f"The answers with uris {on_topic_answer_uri_list} are on topic for the question {question}."
            )
            continueSummarization = (
                len(on_topic_answer_id_list) > len(answer_id_list) * 0.5
            )
            if continueSummarization:
                statusCode = 200
            else:
                statusCode = 400
        else:
            # Update the answers table
            logger.info(f"All answers for the question {question} are on topic.")
            on_topic_answer_uri_list = transcribedFilesS3Uris
            statusCode = 200
            continueSummarization = True

    # Add metrics
    metrics.add_metric(
        name="LLMResponseTime",
        unit=MetricUnit.Seconds,
        value=response_time,
    )
    response = Response(
        statusCode=statusCode,
        documentName=event.documentName,
        validAnswersS3Uris=on_topic_answer_uri_list,
        continueSummarization=continueSummarization,
        invalidAnswersS3Uris=off_topic_answer_uri_list,
    ).__dict__
    logger.info(f"Lambda Output: {response}")

    return response

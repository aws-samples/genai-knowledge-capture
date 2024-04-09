import time
from typing import List, Literal
from dataclasses import dataclass
from summarization import summarization
from connections import Connections, tracer, logger, metrics
from utils import generate_dataframe_from_files, extract_base_s3_path, upload_to_s3
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.parser import event_parser, BaseModel


@dataclass
class Response:
    statusCode: int
    documentName: str
    summarizedAnswerS3Uri: str
    serviceName: str = Connections.service_name


class Request(BaseModel):
    statusCode: int
    documentName: str
    validAnswersS3Uris: List[str]
    continueSummarization: bool
    invalidAnswersS3Uris: List[str]
    serviceName: str = Connections.service_name


@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
@event_parser(model=Request)
def lambda_handler(event: Request, context: LambdaContext) -> str:
    metrics.add_metric(
        name="TotalSummarizationInvocation", unit=MetricUnit.Count, value=1
    )
    logger.info(f"Summarization event: {event}")

    # Extract info
    validAnswersS3Uris = event.validAnswersS3Uris

    # Retrieve all answers for the given question id, if decision is PASS or decision_override is true
    df_input = generate_dataframe_from_files(validAnswersS3Uris)
    logger.debug(f"Input Dataframe size for summarization: {len(df_input)}")

    # Summarizing answers
    if len(df_input) > 0:
        # extract the summary format info, which can be tabular or string
        question = df_input.question.iloc[0]
        logger.info(f"Summarizing answers for question id: {question}...")
        list_of_answers = df_input.answer.tolist()
        logger.info(f"Question: {question}")
        logger.info(f"List of answers: {list_of_answers}")

        # Start timer
        start_time = time.time()

        # Calling LLM to summarize the answers for the given question
        summary_text = summarization(question, list_of_answers, model_name="Claude3")
        logger.debug(f"Summarized answer: \n {summary_text}")

        # End timer
        end_time = time.time()

        # Calculate response time in seconds
        response_time = end_time - start_time

        # Add metrics
        metrics.add_metric(
            name="SummarizationLLMResponseTime",
            unit=MetricUnit.Seconds,
            value=response_time,
        )

        # # upload the summary into the s3 folder
        # df_summary = pd.DataFrame(
        #     data=[[question, summary_text]], columns=["question", "summary"]
        # )
        answerSummaryPath = extract_base_s3_path(validAnswersS3Uris[0])
        logger.info(f"answerSummaryPath: {answerSummaryPath}")
        updated, summarizedAnswerS3Uri = upload_to_s3(summary_text, answerSummaryPath)

        statusCode: Literal[200] | Literal[400] = 200 if updated else 400
        summarizedAnswerS3Uri: str = summarizedAnswerS3Uri

    else:
        logger.info("No valid answers retrieved for question")
        statusCode = 400
        summarizedAnswerS3Uri = summarizedAnswerS3Uri

    response = Response(
        statusCode=statusCode,
        documentName=event.documentName,
        summarizedAnswerS3Uri=summarizedAnswerS3Uri,
    ).__dict__

    logger.info(f"Lambda Output: {response}")

    return response

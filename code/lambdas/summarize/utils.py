from connections import Connections, logger
from botocore.exceptions import BotoCoreError, ClientError
from io import StringIO
import pandas as pd
from typing import List, Tuple
import os


def generate_dataframe_from_files(list_of_answer_text_uris: List[str]) -> pd.DataFrame:
    """
    Generate a Pandas DataFrame from text files specified in S3 URIs. Checks if all URIs have the same parent folder.

    Args:
        list_of_answer_text_uris (List[str]): A list of the text files' S3 URIs.

    Returns:
        pd.DataFrame: The generated DataFrame.
    """
    if not list_of_answer_text_uris:
        raise ValueError("The input list is empty")

    # Initialize variables
    parent_folders = set()
    data = []

    # Initialize an S3 client
    s3 = Connections.s3_client

    for uri in list_of_answer_text_uris:
        # Extract the parent folder by removing the filename
        parent_folder = uri.rsplit("/", 1)[0] + "/"

        # Add the found parent folder to the set
        parent_folders.add(parent_folder)

        # Check if all parent folders are the same
        if len(parent_folders) > 1:
            raise ValueError("The input texts come from different questions.")

        # Parse the S3 bucket name and key from the URI
        bucket_name, key = uri[5:].split("/", 1)

        try:
            # Get the object's content
            response = s3.get_object(Bucket=bucket_name, Key=key)
            content = response["Body"].read().decode("utf-8")
        except ClientError as e:
            logger.error(e)
            continue

        # Extract the filename without extension
        filename = os.path.basename(key)
        index_name = os.path.splitext(filename)[0]
        question = parent_folder.rstrip("/").split("/")[-1]

        # Append a dictionary item to the list
        data.append({"index": index_name, "answer": content, "question": question})

    # Assuming all checks passed and all parent folders are the same
    # Create a DataFrame using the list of dictionary items
    df = pd.DataFrame(data)

    # Set the 'index' column as the index of the DataFrame and reset it to make it a regular column
    df.set_index("index", inplace=True)
    df.reset_index(inplace=True)

    # Add a list_of_answer_text_uris and a decision column
    df["list_of_answer_text_uris"] = list_of_answer_text_uris
    df["decision"] = None

    return df


def format_inputs(input_texts):
    """
    To format a list of input texts into the format that fit into the prompt for Claude models

    Args:
        input_texts: a list of input_texts

    Returns:
        a str

    """

    input_text_list = []
    for (
        i,
        text,
    ) in enumerate(input_texts):
        prefix = f"<input_text_{i + 1}>"
        suffix = f"</input_text_{i + 1}>"
        input_text = prefix + text + suffix + "\n\n"
        input_text_list.append(input_text)

    return " ".join(input_text_list)


def parse_summary(summary):
    """
    Parse the output summary from XMLParser

    Args:
        summary: a JSON file from XMLParser output

    Returns:
        summary_text (str)
    """
    try:
        summary_text = summary["Output"][0]["Summary"]
    except Exception as e:
        logger.debug("An error occurred when parse summary:", e)
    return summary_text


def extract_base_s3_path(s3_uri: str) -> str:
    """
    Extracts the base path of an S3 URI up to the last folder.

    Args:
        s3_uri (str): The full S3 URI from which the base path is to be extracted.

    Returns:
        str: The base path of the S3 URI.
    """

    # Check if the URI ends with a slash and remove it if it does
    if s3_uri.endswith("/"):
        s3_uri = s3_uri[:-1]

    # Find the last occurrence of '/' and slice the string up to that point
    base_path = s3_uri.rsplit("/", 1)[0] + "/"

    return base_path


def upload_to_s3(
    data: str, answerSummaryPath: str, filename: str = "summary/data.txt"
) -> Tuple[bool, str]:
    """
    Uploads a given string to an S3 bucket.

    Args:
        data (str): The string data to be uploaded.
        answerSummaryPath (str): The S3 path where the data should be uploaded, starting with 's3://'.
        filename (str): The filename under which the data should be saved. Defaults to 'summary/data.txt'.

    Returns:
        Tuple[bool, str]: A tuple containing a boolean indicating the success of the upload and the full S3 path to the uploaded file.
    """
    # Convert string to StringIO object
    data_buffer = StringIO(data)

    # Initialize boto3 S3 client
    s3_client = Connections.s3_client

    # Extract bucket and file path in S3
    s3_path = answerSummaryPath[5:]  # Remove the 's3://' prefix
    bucket_name, file_path = s3_path.split(
        "/", 1
    )  # Split the string to separate the bucket name from the file path

    # Ensure the file path ends with '/'
    if not file_path.endswith("/"):
        file_path += "/"
    file_path = f"{file_path}{filename}"  # Append the filename to the file path

    try:
        # Upload data to S3
        s3_client.put_object(
            Bucket=bucket_name, Key=file_path, Body=data_buffer.getvalue()
        )

        logger.info(
            f"Data has been successfully uploaded to s3://{bucket_name}/{file_path}"
        )
        return True, f"s3://{bucket_name}/{file_path}"
    except (BotoCoreError, ClientError) as e:
        logger.exception(
            f"Failed to upload data to s3://{bucket_name}/{file_path}, error: {e}"
        )
        return False, f"s3://{bucket_name}/{file_path}"

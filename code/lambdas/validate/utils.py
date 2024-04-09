import pandas as pd
import os
from connections import Connections, logger
from botocore.exceptions import ClientError
from typing import List


def generate_dataframe_from_files(list_of_answer_text_uris: List[str]) -> pd.DataFrame:
    """
    Generate a Pandas DataFrame from text files specified in S3 URIs. Checks if all URIs have the same parent folder.

    Args:
        list_of_answer_text_uris (List[str]): A list of the text files' S3 URIs.

    Returns:
        pd.DataFrame: The generated DataFrame.
    """
    if not list_of_answer_text_uris:
        logger.error("The input list is empty")
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
            logger.error("The input texts come from different questions.")
            raise ValueError("The input texts come from different questions.")

        # Parse the S3 bucket name and key from the URI
        bucket_name, key = uri[5:].split("/", 1)

        try:
            # Get the object's content
            response = s3.get_object(Bucket=bucket_name, Key=key)
            content = response["Body"].read().decode("utf-8")
        except ClientError as e:
            logger.exception(e)
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

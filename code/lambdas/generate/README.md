# Generate Lambda

## Introduction

The primary objective of this AWS Lambda is to validate the input received from previous step and generate PDF file. This AWS Lambda receives S3 URi location of the summarized answers as input from the `summarize` lambda. Using the summarized text, this lambda utilizes `markdown` and `weasyprint` libraries to generate the final PDF.

## Component Details

#### Prerequisites

- [Python 3.12](https://www.python.org/downloads/release/python-3120/) or later
- [AWS Lambda Powertools 2.35.1](https://docs.powertools.aws.dev/lambda/python/2.35.1/)
- [weasyprint version 61.2](https://doc.courtbouillon.org/weasyprint/stable/) for Python
- [markdown version 3.6](https://python-markdown.github.io/) for Python
- [dominate version 2.9.1](https://github.com/Knio/dominate) for Python
- [pandas version 2.2.1](https://pandas.pydata.org/) for Python

#### Technology stack

- [AWS Lambda](https://aws.amazon.com/lambda/)
- [Amazon Bedrock](https://aws.amazon.com/bedrock/)
- [Amazon S3](https://aws.amazon.com/s3/)

#### Package Details

| Files                                          | Description                                                                                                    |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| [connections.py](connections.py)               | Python file with `Connections` class for establishing connections with external dependencies of the lambda     |
| [Dockerfile](Dockerfile)                       | File containing Docker commands to build and run the AWS Lambda                                                |
| [document_generator.py](document_generator.py) | Python file containing helper functions for building and rendering PDF document                                |
| [exceptions.py](exceptions.py)                 | Python file containing custom exception classes `CodeError` and `ConnectionError`                              |
| [generate.py](generate.py)                     | Python file containing the `lambda_handler` function that acts as the starting point for AWS Lambda invocation |
| [requirements.txt](requirements.txt)           | Python requirements file containing Python library dependencies for Lambda to run.                             |

#### Input

The AWS Lambda is part of a AWS Step Function and it requires following string as input.

```json
{
  "documentName": "data.pdf",
  "answerTextPath": "s3://<your_bucket>/assets/audio_samples_text/<filename>"
}
```

The input for the lambda is received from Amazon SQS queue message via EventBridge pipes. Hence the `event` dictionary received by validation lambda is of type `str`.

| Field            | Description                                      | Type   |
| ---------------- | ------------------------------------------------ | ------ |
| `documentName`   | The final name of the rendered PDF document.     | String |
| `answerTextPath` | The S3 location of the summarized answers output | String |

#### Output

The AWS Lambda is part of a AWS Step Function and it generates the following JSON as output.

```json
{
  "statusCode": 200,
  "s3Url": "https://dummy.s3.us-east-1.amazonaws.com/file",
  "documentName": "data.pdf",
  "serviceName": "validate"
}
```

| Field          | Description                                                                                                          | Data Type |
| -------------- | -------------------------------------------------------------------------------------------------------------------- | --------- |
| `statusCode`   | A HTTP status code that denotes the output status of validation. A `200` value means document generated successfully | Number    |
| `s3Url`        | Denotes S3 URL of the generated PDF document                                                                         | String    |
| `documentName` | Denotes name of the document in DB                                                                                   | String    |
| `serviceName`  | The name of the AWS Lambda as configured through AWS Powertools metrics namespace                                    | String    |

#### Environmental Variables

| Field                     | Description                                                     | Data Type |
| ------------------------- | --------------------------------------------------------------- | --------- |
| `DATA_SOURCE_BUCKET_NAME` | S3 bucket where audio files are stored                          | String    |
| `POWERTOOLS_SERVICE_NAME` | Sets service key that will be present across all log statements | String    |
| `AWS_REGION`              | AWS Region where the solution is deployed                       | String    |

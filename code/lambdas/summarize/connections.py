import os
import re
import boto3
import json
from aws_lambda_powertools import Logger, Tracer, Metrics
from langchain_community.chat_models import BedrockChat
from botocore.client import Config

tracer = Tracer()
logger = Logger(log_uncaught_exceptions=True, serialize_stacktrace=True)
metrics = Metrics()


class Connections:
    """
    Manage connections
    """

    namespace = os.environ["POWERTOOLS_METRICS_NAMESPACE"]
    service_name = os.environ["POWERTOOLS_SERVICE_NAME"]
    region_name = os.environ["AWS_REGION"]
    s3_bucket_transcribe = os.environ["DATA_SOURCE_BUCKET_NAME"]

    transcribe_client = boto3.client("transcribe", region_name=region_name)
    s3_client = boto3.client("s3", region_name=region_name)

    config = Config(read_timeout=1000)
    bedrock_client = boto3.client(
        "bedrock-runtime", region_name=region_name, config=config
    )

    @staticmethod
    def get_bedrock_llm(model_name="ClaudeInstant", max_tokens=256, cache=True):
        """
        Initialize and return a Bedrock LLM client.
        """
        logger.debug("Creating Bedrock LLM client.")
        MODELID_MAPPING = {
            "Titan": "amazon.titan-tg1-large",
            "Claude2": "anthropic.claude-v2",
            "ClaudeInstant": "anthropic.claude-instant-v1",
            "Claude3": "anthropic.claude-3-sonnet-20240229-v1:0",
        }

        MODEL_KWARGS_MAPPING = {
            "Titan": {
                "maxTokenCount": max_tokens,
                "temperature": 0,
                "topP": 1,
            },
            "Claude2": {
                "max_tokens": max_tokens,
                "temperature": 0,
                "top_p": 1,
                "top_k": 50,
                "stop_sequences": ["\n\nHuman"],
            },
            "Claude3": {
                "max_tokens": max_tokens,
                "temperature": 0,
                "top_p": 1,
                "top_k": 50,
                "stop_sequences": ["\n\nHuman"],
            },
            "ClaudeInstant": {
                "max_tokens": max_tokens,
                "temperature": 0,
                "top_p": 1,
                "top_k": 50,
                "stop_sequences": ["\n\nHuman"],
            },
        }

        model = model_name
        llm = BedrockChat(
            client=Connections.bedrock_client,
            model_id=MODELID_MAPPING[model],
            model_kwargs=MODEL_KWARGS_MAPPING[model],
            cache=cache,
            # model_kwargs=json.loads(body)
        )
        return llm

    @staticmethod
    def invoke_claude3(messages, llm_claude3):
        """
        Invoke the Claude3 model.
        """
        model_kwargs = llm_claude3.model_kwargs
        if "max_tokens_to_sample" in model_kwargs:
            value = model_kwargs.pop("max_tokens_to_sample")
            model_kwargs["max_tokens"] = value
        model_kwargs["anthropic_version"] = ""
        body = str.encode(
            json.dumps(
                {
                    **model_kwargs,
                    "messages": messages,
                }
            )
        )

        response = json.loads(
            Connections.bedrock_client.invoke_model(
                body=body, modelId="anthropic.claude-3-sonnet-20240229-v1:0"
            )["body"].read()
        )
        response_message = response.get("content")[0].get("text")
        return response_message

    @staticmethod
    def convert_prompt_to_messages(prompt):
        """
        Convert a prompt to a list of messages, so it is compatible with the Claude3 Message API.
        """
        messages = []
        role_regex = re.compile(
            r"(Human:|Assistant:)\s?(.*?)(?=Human:|Assistant:|$)", re.DOTALL
        )

        for match in role_regex.finditer(prompt):
            role, content = match.groups()
            role = role.strip(":").lower()
            if role == "human" or role == "Human":
                role = "user"
            else:
                role = "assistant"
            messages.append({"role": role, "content": content.strip()})

        return messages

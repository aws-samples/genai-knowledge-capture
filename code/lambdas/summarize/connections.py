import os
import re
import boto3
import json
from aws_lambda_powertools import Logger, Tracer, Metrics
from langchain_aws import ChatBedrock
from botocore.client import Config

tracer = Tracer()
logger = Logger(log_uncaught_exceptions=True, serialize_stacktrace=True)
metrics = Metrics()

# Amazon Bedrock model IDs for the latest Anthropic model generation.
#
# These are cross-region *inference profile* IDs, not bare foundation-model
# IDs: current Anthropic models cannot be invoked with on-demand throughput
# through a foundation-model ID and return a ValidationException instructing
# the caller to use an inference profile instead.
MODELID_MAPPING = {
    "ClaudeOpus": "us.anthropic.claude-opus-5",
    "ClaudeSonnet": "us.anthropic.claude-sonnet-5",
    "ClaudeHaiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}

DEFAULT_MODEL_NAME = "ClaudeSonnet"


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
    def get_bedrock_llm(
        model_name: str = DEFAULT_MODEL_NAME, max_tokens: int = 256, cache: bool = True
    ) -> ChatBedrock:
        """
        Initialize and return a Bedrock chat model client.
        """
        logger.debug("Creating Bedrock LLM client.")

        try:
            model_id = MODELID_MAPPING[model_name]
        except KeyError as error:
            raise ValueError(
                f"Unknown model name '{model_name}'. "
                f"Expected one of: {', '.join(MODELID_MAPPING)}"
            ) from error

        # The latest Anthropic models accept only max_tokens and stop_sequences.
        # temperature, top_p and top_k are deprecated and are rejected by the
        # Bedrock API with a ValidationException.
        llm = ChatBedrock(
            client=Connections.bedrock_client,
            model_id=model_id,
            model_kwargs={"max_tokens": max_tokens},
            cache=cache,
        )
        return llm

    @staticmethod
    def invoke_claude3(messages, llm_claude3):
        """
        Invoke the default Anthropic model directly.
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
                body=body, modelId=MODELID_MAPPING[DEFAULT_MODEL_NAME]
            )["body"].read()
        )
        response_message = response.get("content")[0].get("text")
        return response_message

    @staticmethod
    def convert_prompt_to_messages(prompt):
        """
        Convert a prompt to a list of messages, so it is compatible with the Anthropic Messages API.
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

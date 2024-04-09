from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from prompt_templates import SYSTEM_PROMPT, TOPIC_CLASSIFICATION_TEMPLATE
from connections import Connections
from typing import List
from langchain_core.pydantic_v1 import BaseModel, Field


class AnswerAnomaly(BaseModel):
    """
    Define output data structure.
    """

    off_topic_answers: List[str] = Field(
        description="list of index values of answers that are off topic to the input question"
    )


def answer_anomaly_detection(
    model_name: str, list_answers_w_index: List[str], input_question: str
) -> str:
    """
    Use LLM to detect the answers to a given question that is not on topic.

    Inputs:
        model_name (str): Model name in Amazon Bedrock service
        list_answers_w_index (list): List of answers for the given input question
        input_question: (str): The input question.

    Returns:
        str: The detected answer.
    """
    # Define the parser
    parser = PydanticOutputParser(pydantic_object=AnswerAnomaly)

    # Prompt from a template & parser
    system_message_template = SystemMessagePromptTemplate.from_template(SYSTEM_PROMPT)
    human_message_template = HumanMessagePromptTemplate.from_template(
        TOPIC_CLASSIFICATION_TEMPLATE
    )
    prompt = ChatPromptTemplate.from_messages(
        [system_message_template, human_message_template]
    )
    # LLM object
    llm = Connections.get_bedrock_llm(
        model_name=model_name, max_tokens=128, cache=False
    )

    # Chain the elements together
    chain = prompt | llm | parser

    # Define input dict
    input_dict = {
        "answer_json": list_answers_w_index,
        "format_instructions": parser.get_format_instructions(),
        "input_question": input_question,
    }

    # Invoke the chain
    ans = chain.invoke(input_dict)

    return ans

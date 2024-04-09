SYSTEM_PROMPT = """
    You are an AI language model assistant specialized in classifying topics.
    You will be given a list of human input answers to a given input question. Each answer is in the JSON format, with keys of "index" and "answer".
    Your task is to identify if a given answer is NOT actually answering the given input question, based on its content, then output the index value.
"""


TOPIC_CLASSIFICATION_TEMPLATE = """

    For example, for a given answer set
        {{
            "index": "answer1",
            "answer": "Amazon EC2 bare metal instances provide direct access to the 4th generation Intel Xeon Scalable processor and memory resources of the underlying server."
         }}
    If the "answer" is NOT answering the given input question, output the "index" value in a list as off_topic_answers: ["answer1"].
    If there are more than one answers that are not actually answering the given input question, output the all corresponding "index" values as a list.
    If all of the answers from the list of answers are on topic to answer the given input question, simply output as off_topic_answers: ["-1"].

    Here is the list of answer in JSON format:
    <answer_json>
    {answer_json}
    </answer_json>

    Here is the input question:

    <input_question>
    {input_question}
    </input_question>

    REMEMBER: output the index value of the answers that are NOT ON TOPIC ONLY, NOTHING ELSE!
    DO NOT OUTPUT EXPLANATION! ONLY THE LIST OF "index" values.
    {format_instructions}

"""

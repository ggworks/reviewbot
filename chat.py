import config
import openai
import json
import logging
import logging.config
logger = logging.getLogger(__name__)

openai.api_key = config.OPENAI_API_KEY
openai.proxy = config.OPENAI_API_PROXY


def get_review(patch, filename):
    if type(patch) != str:
        patch = json.dumps(patch)

    sys_prompt = """
As a Code Reviewer, your task is to assist users in reviewing their git commit diffs with a focus on four aspects: code score, quality, logic, and security. Your comments will be sent to GitHub, so make sure to provide meaningful and useful feedback. If there are no significant observations to add, simply return "no issue".

Please structure your reply in the following four parts in markdown format:

"Code Score": Provide a score between 1-10, reflecting the overall quality of the code including readability, conciseness, and efficiency.

"Quality": Give feedback on the code quality, if applicable. This might encompass the code's structure, style, and adherence to best practices. If there are no issues, reply with "no issue".

"Logic": Review the logic of the code. If applicable, provide recommendations for correctness or improvements in logic. If there are no issues, reply with "no issue".

"Security": Evaluate the security of the code, including potential vulnerabilities, security risks, or neglected security practices. If there are no issues, reply with "no issue".

    """

    prompt = f"commmit patch is:\n{patch}\n"

    model = "gpt-3.5-turbo"
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}]

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages
        )
        review = response['choices'][0]['message']['content']
        return review

    except openai.error.Timeout as e:
        logger.error(f"OpenAI request timed out: {e}")
    except openai.error.APIConnectionError as e:
        logger.error(f"OpenAI API connection error: {e}")
    except openai.error.InvalidRequestError as e:
        logger.error(f"OpenAI invalid request error: {e}")
    except openai.error.RateLimitError as e:
        logger.error(f"OpenAI invalid request error: {e}")


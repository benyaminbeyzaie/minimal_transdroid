import os
from dotenv import load_dotenv
import openai


load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = API_KEY


class BenGPT:
    @classmethod
    def sort_candidates(cls, src_event, candidates):
        """
        The `sort_candidates` function uses OpenAI's Chat API to generate a response that contains the top 5
        most similar events to `src_event` from the given `candidates` list, based on specific factors, and
        returns the response as a JSON array.

        :param cls: The parameter `cls` is a reference to the class itself. It is commonly used in class
        methods to access class-level variables or methods. In this case, it seems that the
        `sort_candidates` method is defined within a class, and `cls` is used as a placeholder for the class
        reference
        :param src_event: The source event that you want to find similar events to
        :param candidates: The `candidates` parameter is a list of events that you want to sort and find the
        top 5 most similar events to `src_event`. Each event in the `candidates` list should be a dictionary
        with the following keys:
        :return: The code is returning the content of the response received from the OpenAI ChatCompletion
        API.
        """

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # "gpt-4" or "gpt-3.5-turbo" --> 4k token or "gpt-3.5-turbo-16k" --> 16k token
            messages=[
                {
                    "role": "user",
                    "content": f"""
                        Compare the 'src_event' with the 'candidates' and find the top 5 candidates that are most similar in terms of their attributes. most important attributes is text
                        After that you should compare id in src_event with resource-id in candidates
                        Also content-desc in candidates have description of that candidate use it to find similarity between src_event and candidate
                        
                        don't change the candidates at all but add a sim_score a number between 0 and 1 based on how much the candidate is similar to the src_event
                        try to find at least one element with sim_score more than 0
                        don't include candidates with 0 sim_score in your response

                        your response must contain just a json file and nothing more.

                        Dont write any code to find similar events based on your own intuition.

                        src_event: {src_event}
                        candidates: {candidates}

                        your response should be an array of json without any addition
                    """,
                }
            ],
        )

        return response.choices[0].message["content"]

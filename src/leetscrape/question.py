import json
import time
import warnings

import pandas as pd
import requests

from ._constants import HEADERS, NO_PYTHON_STUB, PREMIUM_CUSTOMER_PYTHON_STUB
from ._helper import camel_case
from .models import Question

# Leetcode's graphql api endpoint
BASE_URL = "https://leetcode.com/graphql"


class GetQuestion:
    """
    A class to acquire the statement, constraints, hints, basic test cases, related questions, and code stubs of the given question.

    Args:
        titleSlug (str): The title slug of the question.
    """

    def __init__(self, titleSlug: str):
        self.titleSlug = titleSlug
        self.questions_info = self.fetch_all_questions_id_and_stub()

    @staticmethod
    def fetch_all_questions_id_and_stub():
        response = requests.get(
            "https://leetcode.com/api/problems/all/", headers=HEADERS
        )
        response.raise_for_status()  # Raise an exception for bad status codes
        try:
            req = response.json()
        except requests.exceptions.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON response from LeetCode API. "
                f"Status code: {response.status_code}. "
                f"Response: {response.text[:200]}"
            ) from e
        question_data = pd.json_normalize(req["stat_status_pairs"]).rename(
            columns={
                "stat.frontend_question_id": "QID",
                "stat.question__title_slug": "titleSlug",
            }
        )[["QID", "titleSlug"]]

        return question_data.sort_values("QID").set_index("titleSlug")

    def scrape(self) -> Question:
        """This method calls the Leetcode graphql api to query for the hints, companyTags (currently returning null as this is a premium feature), code snippets, and content of the question.

        Raises:
            ValueError: When the connection to Leetcode's graphql api is not established.

        Returns:
            QuestionInfo: Contains the QID, titleSlug, Hints, Companies, Similar Questions, Code stubs, and the body of the question.
        """
        data = {
            "query": """query questionHints($titleSlug: String!) {
                question(titleSlug: $titleSlug) {
                    questionFrontendId
                    title
                    hints
                    difficulty
                    companyTags {
                        name
                        slug
                        imgUrl
                    }
                    topicTags {
                        name
                    }
                    similarQuestions
                    codeSnippets {
                        lang
                        langSlug
                        code
                    }
                    content
                    isPaidOnly
                }
            }
        """,
            "variables": {"titleSlug": self.titleSlug},
        }
        response = requests.post(BASE_URL, json=data, headers=HEADERS)
        if response.status_code == 404:
            raise ValueError("Leetcode's graphql API can't be found.")
        while response.status_code in (429, 400, 500, 502, 503, 504):
            time.sleep(10)
            response = requests.post(BASE_URL, json=data, headers=HEADERS)
            if response.status_code == 404:
                raise ValueError("Leetcode's graphql API can't be found.")
        
        # Check if response is successful before parsing JSON
        if not response.ok:
            raise ValueError(
                f"LeetCode API returned error status {response.status_code}. "
                f"Response: {response.text[:200]}"
            )
        
        try:
            response_data = response.json()
        except requests.exceptions.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON response from LeetCode API. "
                f"Status code: {response.status_code}. "
                f"Response: {response.text[:200]}"
            ) from e
        return Question(
            QID=response_data["data"]["question"]["questionFrontendId"],
            title=response_data["data"]["question"]["title"],
            titleSlug=self.titleSlug,
            difficulty=response_data["data"]["question"]["difficulty"],
            Hints=response_data["data"]["question"]["hints"],
            Companies=response_data["data"]["question"]["companyTags"],
            topics=[
                topic["name"] for topic in response_data["data"]["question"]["topicTags"]
            ],
            isPaidOnly=response_data["data"]["question"]["isPaidOnly"],
            Body=self._get_question_body(response_data),
            Code=self._get_code_snippet(response_data),
            SimilarQuestions=self._get_similar_questions(response_data),
        )

    def _get_question_body(self, response_data) -> str:  # type: ignore
        if not response_data["data"]["question"]["isPaidOnly"]:
            return response_data["data"]["question"]["content"]
        else:
            warnings.warn("This questions is only for paid Leetcode subscribers.")
            return "This questions is only for paid Leetcode subscribers."

    # Similar questions
    def _get_similar_questions(self, response_data) -> list[int]:
        """A helper method to extract the list of similar questions of the
        given question.

        Returns:
            list[int]: The list of QIDs of the questions similar to the given question.
        """
        similar_questions = []
        for qs in json.loads(response_data["data"]["question"]["similarQuestions"]):
            similar_questions.append(self.questions_info.loc[qs["titleSlug"]].QID)
        return similar_questions

    # Code Snippet
    def _get_code_snippet(self, response_data) -> str:  # type: ignore
        """A helper method to extract the code snippets from the query response.
        Currently, this method returns the Python3 code snippet if available,
        else it returns a barebones Python3 code snippet with the class name and
        method named after the titleSlug.

        Returns:
            str: Python3 code snippet
        """
        if not response_data["data"]["question"]["isPaidOnly"]:
            python_code_snippet = [
                code_snippet
                for code_snippet in response_data["data"]["question"]["codeSnippets"]
                if code_snippet["langSlug"] == "python3"
            ]
            if len(python_code_snippet) > 0:
                return python_code_snippet[0]["code"]
            else:
                return NO_PYTHON_STUB.format(camel_case(self.titleSlug))
        else:
            warnings.warn("This questions is only for paid Leetcode subscribers.")
            return PREMIUM_CUSTOMER_PYTHON_STUB.format(camel_case(self.titleSlug))

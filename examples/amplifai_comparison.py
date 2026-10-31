import json

from dotenv import load_dotenv
from pydantic import BaseModel

import clairic
from clairic import Clairic

TEXT = (
    "John Doe is 25 years old. "
    "He lives in Paris and can be reached at +33 6 12 34 56 78 or at firstname.name@gmail.com"
)


class PersonExtraction(BaseModel):
    name : clairic.TextAnswer
    age : clairic.NumberAnswer[int]
    phone_number : clairic.TextAnswer
    email_address : clairic.TextAnswer


def main() -> None:
    load_dotenv()
    with Clairic() as clairic:
        result = clairic.extract(TEXT, PersonExtraction)
        with open("clairic_result.json", "w") as f:
            json.dump(result.model_dump(mode="json"), f, indent=2)

if __name__ == "__main__":
    main()
"""A deterministic chat model double. Used by the tests, the CI and the durable resume check.

It returns canned answers and never calls the network.
"""

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agent.schemas import CheckOutput, ExtractionOutput


class FakeLLM:
    """Mimics the two methods the nodes use: with_structured_output() and invoke().

    check_answers maps a requirement code to the CheckOutput to return.
    Codes without an entry are answered "present" with evidence taken from the first file.
    """

    def __init__(self, check_answers: dict[str, CheckOutput] | None = None, fail_on_file: str | None = None):
        self.check_answers = check_answers or {}
        self.fail_on_file = fail_on_file
        self.calls: list[str] = []

    def with_structured_output(self, schema):
        if schema is ExtractionOutput:
            return RunnableLambda(self._extract)
        if schema is CheckOutput:
            return RunnableLambda(self._check)
        raise AssertionError(f"Unexpected schema {schema}")

    def invoke(self, messages):
        self.calls.append("summary")
        return AIMessage(content="Plain language summary.")

    def _extract(self, messages):
        self.calls.append("extract")
        text = messages[-1].content
        name = text.split("File name: ")[1].split("\n")[0]
        if name == self.fail_on_file:
            raise RuntimeError("model error")
        return ExtractionOutput(document_type=f"type of {name}", summary=f"summary of {name}")

    def _check(self, messages):
        self.calls.append("check")
        text = messages[-1].content
        code = text.split("Requirement ")[1].split(":")[0]
        if code in self.check_answers:
            return self.check_answers[code]
        # Default: present, quoting the first line of the first file in the prompt.
        first_file_id = text.split('<file id="')[1].split('"')[0]
        first_line = text.split(">\n", 1)[1].split("\n")[0]
        return CheckOutput(status="present", file_id=first_file_id, evidence=first_line, reasoning="matches")

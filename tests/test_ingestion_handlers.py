from contextus.llm import LLMResponse
from contextus.ingestion.handlers.figure import FigureHandler
from contextus.ingestion.handlers.formula import FormulaHandler
from contextus.ingestion.handlers.table import TableHandler


def test_formula_handler_normalizes_symbolic_text():
    handler = FormulaHandler()
    latex = handler.simple_text_to_latex('x \u2264 y and z \u2260 0')

    assert latex is not None
    assert '\\leq' in latex
    assert '\\neq' in latex


class MockVisionLLM:
    def complete_with_image(self, system: str, user: str, image_bytes: bytes, *, mime_type: str = "image/png", temperature: float = 0.0):
        if '"format":"formula"' in system:
            return LLMResponse(
                '{"format":"formula","figure_type":"formula","raw_text":"x_i\' <= y","structured_content":{"latex":"x_i^\\prime \\leq y","mathml":null},"literal_description":null,"source_confidence":0.97,"needs_review":false,"rationale":"clear"}'
            )
        if '"format":"table"' in system:
            return LLMResponse(
                '{"format":"table","figure_type":"table","raw_text":"Name Value Alpha 10","structured_content":{"headers":["Name","Value"],"rows":[["Alpha","10"]],"markdown":"| Name | Value |\\n| --- | --- |\\n| Alpha | 10 |"},"literal_description":null,"source_confidence":0.94,"needs_review":false,"rationale":"clear"}'
            )
        return LLMResponse(
            '{"format":"figure","figure_type":"chart","raw_text":"Q1 Q2 Revenue","structured_content":{"chart_type":"bar","axes":{"x_label":"Quarter","y_label":"Revenue"},"series":[{"name":"Revenue","values":[{"x":"Q1","y":"10"},{"x":"Q2","y":"12"}]}],"findings":["Revenue rises from Q1 to Q2"]},"literal_description":null,"source_confidence":0.91,"needs_review":false,"rationale":"clear"}'
        )


def test_formula_handler_prefers_llm_formula_transcription():
    handler = FormulaHandler(llm_client=MockVisionLLM())

    result = handler._transcribe_with_llm(b"fake-image", raw_text="x_i' <= y")

    assert result is not None
    assert result["content"]["structured_content"]["latex"] == "x_i^\\prime \\leq y"
    assert result["content"]["figure_type"] == "formula"
    assert result["needs_review"] is False


def test_table_handler_prefers_llm_structured_extraction():
    handler = TableHandler(llm_client=MockVisionLLM())

    result = handler._extract_with_llm(b"fake-image", raw_text="Name Value Alpha 10")

    assert result is not None
    assert result["content"]["figure_type"] == "table"
    assert result["content"]["structured_content"]["headers"] == ["Name", "Value"]
    assert result["content"]["structured_content"]["rows"] == [["Alpha", "10"]]


def test_figure_handler_prefers_llm_chart_extraction():
    handler = FigureHandler(llm_client=MockVisionLLM())

    result = handler._extract_with_llm(b"fake-image", raw_text="Q1 Q2 Revenue", element_type="chart")

    assert result is not None
    assert result["content"]["figure_type"] == "chart"
    assert result["content"]["structured_content"]["chart_type"] == "bar"
    assert result["content"]["structured_content"]["findings"] == ["Revenue rises from Q1 to Q2"]

from contextus.ingestion.handlers.formula import FormulaHandler


def test_formula_handler_normalizes_symbolic_text():
    handler = FormulaHandler()
    latex = handler.simple_text_to_latex('x \u2264 y and z \u2260 0')

    assert latex is not None
    assert '\\leq' in latex
    assert '\\neq' in latex

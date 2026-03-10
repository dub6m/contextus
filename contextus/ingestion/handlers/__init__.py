"""Content handlers for detected document elements."""

from .figure import FigureHandler
from .formula import FormulaHandler
from .table import TableHandler
from .text import TextHandler

__all__ = ["FigureHandler", "FormulaHandler", "TableHandler", "TextHandler"]

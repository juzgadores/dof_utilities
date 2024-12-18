from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, TypeAlias, TypedDict

import pandas as pd
import pdfplumber
from pdfplumber.page import Page

TableRow: TypeAlias = list[str | None]
TableData: TypeAlias = list[TableRow]
ExtractedTable: TypeAlias = tuple[int, str, TableData]
BBox: TypeAlias = tuple[float, float, float, float]


class TableState(TypedDict):
    tables: list[ExtractedTable]
    table: TableData
    heading: str
    table_id: int


class TableValidator(Protocol):
    """Protocol for table validation"""

    def is_valid_table(self, table: TableData) -> bool: ...
    def is_new_table(self, table: TableData) -> bool: ...
    def extract_table_heading(self, page: Page, table_bbox: BBox) -> str: ...


@dataclass(frozen=True)
class TableSettings:
    """Default Settings for PDF table extraction"""

    vertical_strategy: str = "lines"
    horizontal_strategy: str = "lines"
    snap_tolerance: int = 3
    join_tolerance: int = 3
    edge_min_length: int = 50


class PDFTableExtractor:
    """Generic PDF table extractor"""

    def __init__(
        self,
        validator: TableValidator,
        post_process: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
        settings: TableSettings = TableSettings(),
    ):
        self.settings = settings
        self.validator = validator
        self.post_process = post_process or (lambda x: x)

    def process_table_data(
        self, table_data: TableData, heading: str, current_state: TableState
    ) -> None:
        """Process extracted table data and update current state."""
        # Replace newlines with spaces in all table data cells
        table_data = [
            [cell.replace("\n", " ") if cell is not None else "" for cell in row]
            for row in table_data
        ]

        if not table_data or not self.validator.is_valid_table(table_data):
            return

        if self.validator.is_new_table(table_data):
            if current_state["table"]:
                current_state["tables"].append(
                    (
                        current_state["table_id"],
                        current_state["heading"],
                        current_state["table"],
                    )
                )
            current_state.update(
                {
                    "table": table_data,
                    "heading": heading,
                    "table_id": current_state["table_id"] + 1,
                }
            )
        else:
            current_state["table"].extend(table_data[1:])

    def extract_tables(self, pdf_path: Path) -> list[ExtractedTable]:
        """Extract and merge tables from PDF with their headings."""
        state: TableState = {
            "tables": [],
            "table": [],
            "heading": "",
            "table_id": 0,
        }

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for table in page.find_tables(self.settings.__dict__):
                    self.process_table_data(
                        table.extract(),
                        self.validator.extract_table_heading(page, table.bbox),
                        state,
                    )

        if state["table"]:
            state["tables"].append(
                (state["table_id"], state["heading"], state["table"])
            )

        return state["tables"]

    def extract_to_dataframes(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        """Extract tables and convert them to DataFrames."""
        merged_tables = self.extract_tables(pdf_path)

        return {
            f"{table_id}": self.post_process(
                pd.DataFrame(table[1:], columns=table[0]).assign(heading=heading)
            )
            for table_id, heading, table in merged_tables
        }

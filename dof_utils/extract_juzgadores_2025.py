import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pdfplumber.page import Page
from rich.console import Console
from rich.table import Table

from dof_utils import BBox, PDFTableExtractor, TableData, TableValidator


@dataclass(frozen=True)
class JuzgadosConfig:
    """Configuration for Juzgados PDF extraction"""

    sequence_column: str = "Núm."
    heading_start: str = "LISTADO DE PERSONAS ELEGIBLES PARA"
    heading_end: str = "SUJETOS AL PROCESO ELECTORAL EXTRAORDINARIO 2024-2025"


class JuzgadosTableValidator(TableValidator):
    """Validator for Juzgados tables"""

    config = JuzgadosConfig

    def is_valid_table(self, table: TableData) -> bool:
        """Check if table has valid structure."""
        return bool(
            table
            and table[0]
            and (
                table[0][0] == self.config.sequence_column
                or (len(table) > 1 and table[1][0] == "1")
            )
        )

    def is_new_table(self, table: TableData) -> bool:
        """Check if this is the start of a new table."""
        return bool(table and len(table) > 1 and table[1] and table[1][0] == "1")

    def extract_table_heading(self, page: Page, table_bbox: BBox) -> str:
        """Extract heading text above the table."""
        above_box = page.crop(
            (
                table_bbox[0],  # x0
                0,  # Top of page
                table_bbox[2],  # x1
                table_bbox[1],  # Bottom of heading
            )
        )
        above_lines = above_box.extract_text().split("\n")

        heading_lines = []
        capture = False
        for line in above_lines:
            if line.startswith(self.config.heading_start):
                capture = True
            if capture:
                heading_lines.append(line.strip())
            if self.config.heading_end in line or line in self.config.heading_end:
                break

        full_heading = " ".join(heading_lines)

        # Strip away the heading_start and heading_end
        clean_heading = full_heading
        if clean_heading.startswith(self.config.heading_start):
            clean_heading = clean_heading[len(self.config.heading_start) :].lstrip()
        if clean_heading.endswith(self.config.heading_end):
            clean_heading = clean_heading[: -len(self.config.heading_end)].rstrip()

        return clean_heading.replace("\n", " ").strip()


def create_summary_table(merged_data: dict[str, pd.DataFrame]) -> Table:
    """Create a rich summary table of extracted data."""
    summary = Table(title="Exported Tables Summary")
    summary.add_column("Table Name", style="bold magenta")
    summary.add_column("Heading", style="cyan")
    summary.add_column("Rows", justify="right", style="green")
    summary.add_column("First Record", style="yellow", overflow="fold")

    for table_name, df in merged_data.items():
        sample_record = df.drop(columns=["heading"]).head(1)
        summary.add_row(
            table_name,
            df["heading"].iloc[0],
            str(len(df)),
            sample_record.to_string(index=False, max_rows=1, max_colwidth=30),
        )

    return summary


def main() -> None:
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python juzgadores_extract.py <input_pdf> [<output_dir>]")
        sys.exit(1)

    input_pdf = Path(sys.argv[1])

    # Initialize extractor with Juzgados-specific validator
    tables = PDFTableExtractor(
        validator=JuzgadosTableValidator(),
    ).extract_to_dataframes(input_pdf)

    print(tables)

    if len(sys.argv) >= 3:
        output_dir = Path(sys.argv[2])
        output_dir.mkdir(parents=True, exist_ok=True)

        for table_name, df in tables.items():
            df.to_csv(output_dir / f"{table_name}.csv", index=False)

    # Display summary
    console = Console()
    summary_table = create_summary_table(tables)
    console.print(summary_table)


if __name__ == "__main__":
    main()

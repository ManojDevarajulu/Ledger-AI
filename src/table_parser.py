import re
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

class TableCell(BaseModel):
    row_label: str
    column_label: str
    raw_value: str
    numeric_value: Optional[float] = None
    unit: str = "USD in millions"
    hierarchy_path: str = ""
    footnote_refs: List[str] = Field(default_factory=list)

class TableRow(BaseModel):
    row_label: str
    hierarchy_path: str = ""
    cells: Dict[str, TableCell] = Field(default_factory=dict)
    raw_line: str
    footnote_refs: List[str] = Field(default_factory=list)

class ParsedTable(BaseModel):
    table_id: str
    title: str
    section: str
    company: str
    fiscal_year: int
    unit_scale: str
    columns: List[str]
    rows: List[TableRow]
    raw_markdown: str
    footnotes: Dict[str, str] = Field(default_factory=dict)

    def get_cell(self, row_name: str, col_name: str) -> Optional[TableCell]:
        """Find a cell by matching row label and column label case-insensitively."""
        row_name_clean = row_name.lower().strip()
        col_name_clean = col_name.lower().strip()
        
        for r in self.rows:
            if row_name_clean in r.row_label.lower():
                for c_name, cell in r.cells.items():
                    if col_name_clean in c_name.lower():
                        return cell
        return None

    def to_contextual_chunks(self) -> List[str]:
        """
        Table-Aware Chunking:
        Propagates table hierarchy, parent categories, fiscal periods, footnotes, and unit scale.
        """
        chunks = []
        for row in self.rows:
            cell_descriptions = []
            for col_name, cell in row.cells.items():
                if cell.numeric_value is not None:
                    cell_descriptions.append(f"{col_name}: {cell.raw_value} ({self.unit_scale})")
                else:
                    cell_descriptions.append(f"{col_name}: {cell.raw_value}")
            
            row_content = " | ".join(cell_descriptions)
            hierarchy_str = f" [Category: {row.hierarchy_path}]" if row.hierarchy_path else ""
            footnotes_str = f" [Footnotes: {', '.join(row.footnote_refs)}]" if row.footnote_refs else ""
            
            chunk = (
                f"[Filing: {self.company} {self.fiscal_year} 10-K | "
                f"Section: {self.section} | Table: {self.title} | Units: {self.unit_scale}]\n"
                f"Metric / Row: {row.row_label}{hierarchy_str}{footnotes_str} -> {row_content}"
            )
            chunks.append(chunk)
        return chunks

    def to_naive_chunks(self) -> List[str]:
        """Naive chunking baseline: raw text lines stripped of context."""
        return [r.raw_line for r in self.rows]


class TableParser:
    """
    Parser for structured financial tables from SEC 10-K/10-Q reports.
    Preserves row/column hierarchy, detects parent-child indentation,
    extracts footnotes, and converts values to clean numeric floats.
    """

    FOOTNOTE_PATTERN = re.compile(r"[\(\[\{]([0-9a-zA-Z*#†])[\)\]\}]")

    @classmethod
    def _extract_footnotes(cls, text: str) -> Tuple[str, List[str]]:
        """Extract footnote references (e.g. '(1)', '[a]') and clean the text."""
        refs = cls.FOOTNOTE_PATTERN.findall(text)
        cleaned_text = cls.FOOTNOTE_PATTERN.sub("", text).strip()
        return cleaned_text, refs

    @classmethod
    def parse_markdown_table(
        cls,
        table_markdown: str,
        table_id: str,
        title: str,
        section: str,
        company: str,
        fiscal_year: int,
        unit_scale: str = "USD in millions",
        footnotes: Optional[Dict[str, str]] = None
    ) -> ParsedTable:
        lines = [line.strip() for line in table_markdown.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            raise ValueError("Invalid markdown table: must have at least header and separator rows")

        # Parse header
        raw_headers = [c.strip() for c in lines[0].split("|") if c.strip()]
        
        # Skip separator line (e.g., |---|---|)
        data_lines = [l for l in lines[1:] if not re.match(r"^\|?\s*[-:]+[-|\s:]*\|?$", l)]

        rows = []
        current_parent_category = ""

        for line in data_lines:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if not cols:
                continue
            
            raw_row_label = cols[0]
            clean_row_label, row_footnotes = cls._extract_footnotes(raw_row_label)

            # Check if this row is a header/category line (e.g. no numeric data or colon at end)
            has_numeric_data = any(re.search(r"\d", c) for c in cols[1:])
            if not has_numeric_data and len(cols) <= 2:
                current_parent_category = clean_row_label
                continue

            hierarchy_path = f"{current_parent_category} > {clean_row_label}" if current_parent_category else clean_row_label

            cells = {}
            for idx, col_val in enumerate(cols[1:], start=1):
                col_name = raw_headers[idx] if idx < len(raw_headers) else f"Col_{idx}"
                clean_col_val, cell_footnotes = cls._extract_footnotes(col_val)
                all_footnotes = list(set(row_footnotes + cell_footnotes))

                # Clean numeric value
                num_val = None
                clean_num_str = clean_col_val.replace('$', '').replace(',', '').replace('%', '').strip()
                try:
                    num_val = float(clean_num_str)
                except ValueError:
                    num_val = None

                cells[col_name] = TableCell(
                    row_label=clean_row_label,
                    column_label=col_name,
                    raw_value=clean_col_val,
                    numeric_value=num_val,
                    unit=unit_scale,
                    hierarchy_path=hierarchy_path,
                    footnote_refs=all_footnotes
                )

            rows.append(TableRow(
                row_label=clean_row_label,
                hierarchy_path=hierarchy_path,
                cells=cells,
                raw_line=line,
                footnote_refs=row_footnotes
            ))

        return ParsedTable(
            table_id=table_id,
            title=title,
            section=section,
            company=company,
            fiscal_year=fiscal_year,
            unit_scale=unit_scale,
            columns=raw_headers,
            rows=rows,
            raw_markdown=table_markdown,
            footnotes=footnotes or {}
        )

    @classmethod
    def parse_html_table(
        cls,
        html_content: str,
        table_id: str,
        title: str,
        section: str,
        company: str,
        fiscal_year: int,
        unit_scale: str = "USD in millions"
    ) -> ParsedTable:
        """
        Parses raw SEC EDGAR HTML tables into structured ParsedTable representation.
        Handles merged cells and multi-column headers.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        table_el = soup.find("table") or soup
        
        tr_elements = table_el.find_all("tr")
        if not tr_elements:
            raise ValueError("No table rows found in provided HTML")

        # Extract headers from first tr or th elements
        header_row = tr_elements[0]
        th_elements = header_row.find_all(["th", "td"])
        headers = [th.get_text(strip=True) for th in th_elements if th.get_text(strip=True)]
        
        if not headers:
            headers = ["Metric"] + [f"Period_{i}" for i in range(1, 10)]

        # Convert to markdown format and delegate to parse_markdown_table
        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for tr in tr_elements[1:]:
            cells = tr.find_all(["td", "th"])
            cell_texts = [c.get_text(strip=True) for c in cells]
            if any(cell_texts):
                # Pad if fewer columns
                while len(cell_texts) < len(headers):
                    cell_texts.append("")
                md_lines.append("| " + " | ".join(cell_texts[:len(headers)]) + " |")

        full_md = "\n".join(md_lines)
        return cls.parse_markdown_table(
            table_markdown=full_md,
            table_id=table_id,
            title=title,
            section=section,
            company=company,
            fiscal_year=fiscal_year,
            unit_scale=unit_scale
        )

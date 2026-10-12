"""How a person reads a delivered or handed-over file: a workbook as its cells, sheet by sheet."""

import zipfile

from experimental.harness.participation.files import read_delivered

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _workbook(path):
    with zipfile.ZipFile(path, "w") as book:
        book.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{MAIN}"><sheets><sheet name="Orders" sheetId="1"/><sheet name="Prices" sheetId="2"/>'
            "</sheets></workbook>",
        )
        book.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="{MAIN}"><si><t>order</t></si><si><r><t>full </t></r><r><t>pay</t></r></si></sst>',
        )
        book.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{MAIN}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr">'
            '<is><t>amount</t></is></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><f>1+1</f><v>2</v></c>'
            "</row></sheetData></worksheet>",
        )
        book.writestr(
            "xl/worksheets/sheet2.xml",
            f'<worksheet xmlns="{MAIN}"><sheetData><row r="1"><c r="A1"><v>680</v></c></row></sheetData></worksheet>',
        )


def test_a_workbook_reads_as_its_cells_sheet_by_sheet(tmp_path):
    path = tmp_path / "orders.xlsx"
    _workbook(path)
    assert read_delivered(path) == "## Orders\norder\tamount\nfull pay\t2\n## Prices\n680"
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a zip")
    assert "could not be read" in read_delivered(broken)

"""Minimal dependency-free XLSX exporter for GitHub Actions."""
from __future__ import annotations
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

def _column(index):
    result=""
    while index:
        index, remainder=divmod(index-1,26)
        result=chr(65+remainder)+result
    return result

def _sheet(rows):
    parts=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for ri,row in enumerate(rows,1):
        cells=[]
        for ci,value in enumerate(row,1):
            if value is None:
                continue
            cell=_column(ci)+str(ri)
            if isinstance(value,bool):
                cells.append(f'<c r="{cell}" t="b"><v>{int(value)}</v></c>')
            elif isinstance(value,(int,float)):
                cells.append(f'<c r="{cell}"><v>{value}</v></c>')
            else:
                text=escape(str(value),{'"':'&quot;'})
                cells.append(f'<c r="{cell}" t="inlineStr"><is><t>{text}</t></is></c>')
        parts.append(f'<row r="{ri}">{"".join(cells)}</row>')
    parts.append('</sheetData></worksheet>')
    return "".join(parts)

def export_xlsx(path:Path, sheets):
    path=Path(path)
    names=list(sheets)
    workbook='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>') + ''.join(
        f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i,name in enumerate(names,1))+'</sheets></workbook>'
    rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">') + ''.join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1,len(names)+1))+'</Relationships>'
    types='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>') + ''.join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1,len(names)+1))+'</Types>'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml',types)
        archive.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml',workbook)
        archive.writestr('xl/_rels/workbook.xml.rels',rels)
        for i,name in enumerate(names,1):
            archive.writestr(f'xl/worksheets/sheet{i}.xml',_sheet(sheets[name]))

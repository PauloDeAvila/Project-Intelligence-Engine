"""Generate auditable per-attempt CSV and optional XLSX for every 9Router run."""
import argparse
import csv
import json
from pathlib import Path

COLUMNS=("task","mode","model","ok","correct","error","error_detail",
         "calls","searches","prompt_tokens","completion_tokens",
         "model_ms_total","retrieval_ms_total","model_ms_mean","retrieval_ms_mean")

def summarize(source: Path, directory: Path):
    directory.mkdir(parents=True,exist_ok=True)
    raw=json.loads(source.read_text(encoding="utf8")) if source.is_file() else {}
    attempts=raw.get("results",[])
    records=[]
    for x in attempts:
        model_times=x.get("model_ms",[])
        retrieval_times=x.get("search_ms",[])
        records.append({
          "task":x.get("task"),"mode":x.get("mode"),"model":x.get("model"),
          "ok":x.get("ok"),"correct":x.get("correct"),"error":x.get("error"),
          "error_detail":x.get("error_detail"),"calls":x.get("calls"),
          "searches":x.get("searches"),"prompt_tokens":x.get("prompt_tokens"),
          "completion_tokens":x.get("completion_tokens"),
          "model_ms_total":round(sum(model_times),3) if model_times else None,
          "retrieval_ms_total":round(sum(retrieval_times),3) if retrieval_times else None,
          "model_ms_mean":round(sum(model_times)/len(model_times),3) if model_times else None,
          "retrieval_ms_mean":round(sum(retrieval_times)/len(retrieval_times),3) if retrieval_times else None,
        })
    with (directory/"attempts.csv").open("w",newline="",encoding="utf8") as stream:
        writer=csv.DictWriter(stream,fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    completed=[x for x in records if x["ok"] is True]
    measured=[x for x in completed if x["prompt_tokens"] is not None]
    summary={
      "attempts":len(records),"completed":len(completed),
      "failures":len(records)-len(completed),
      "correct_completed":sum(x["correct"] is True for x in completed),
      "prompt_tokens_reported":sum(x["prompt_tokens"] for x in measured),
      "token_coverage":len(measured),
      "results_by_mode":{
        mode:{"attempts":sum(x["mode"]==mode for x in records),
              "completed":sum(x["mode"]==mode and x["ok"] is True for x in records),
              "correct":sum(x["mode"]==mode and x["correct"] is True for x in records)}
        for mode in ("pie","baseline")},
      "note":"Missing metrics are null, not zero. Completeness and quality are distinct."}
    (directory/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    try:
        from artifact_tool import Workbook, SpreadsheetFile
        book=Workbook.create()
        sheet=book.worksheets.add("Tentativas")
        sheet.get_range("A1:O1").values=[list(COLUMNS)]
        sheet.get_range("A1:O1").format={"fill":"#17324A","font":{"bold":True,"color":"#FFFFFF"}}
        for start in range(0,len(records),100):
            chunk=records[start:start+100]
            cells=[[row[c] for c in COLUMNS] for row in chunk]
            sheet.get_range(f"A{start+2}:O{start+1+len(chunk)}").values=cells
        sheet.freeze_panes.freeze_rows(1)
        overview=book.worksheets.add("Resumo")
        values=list(summary.items())
        overview.get_range("A1:B1").values=[["Metrica","Valor"]]
        overview.get_range("A1:B1").format={"fill":"#17324A","font":{"bold":True,"color":"#FFFFFF"}}
        for i,(key,value) in enumerate(values,2):
            overview.get_range(f"A{i}:B{i}").values=[[key,json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value]]
        SpreadsheetFile.export_xlsx(book).save(str(directory/"pie-agent-report.xlsx"))
    except (ImportError,AttributeError,RuntimeError,ValueError) as exc:
        (directory/"excel_error.txt").write_text(type(exc).__name__+": "+str(exc)[:300],encoding="utf8")
    print("REPORT",json.dumps(summary))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="pie-agent-9router-results.json")
    ap.add_argument("--out",default="pie-agent-report")
    args=ap.parse_args()
    summarize(Path(args.input),Path(args.out))

"""Adapter for official SEC quarterly 13F TSV ZIP datasets."""

from io import BytesIO
from zipfile import ZipFile
import pandas as pd
from crowding.normalization.holdings import validate


def parse_archive(content, value_unit="auto"):
    if value_unit not in {"auto", "usd", "thousands"}:
        raise ValueError("Invalid value unit")
    with ZipFile(BytesIO(content)) as archive:

        def table(name):
            candidates = [n for n in archive.namelist() if n.upper().endswith(name + ".TSV")]
            if len(candidates) != 1:
                raise ValueError(f"Missing or ambiguous {name}.tsv")
            info = archive.getinfo(candidates[0])
            if info.file_size > 2_000_000_000:
                raise ValueError("Archive member too large")
            return pd.read_csv(archive.open(candidates[0]), sep="\t", dtype=str, keep_default_na=False)

        submission, cover, info = table("SUBMISSION"), table("COVERPAGE"), table("INFOTABLE")
    f = submission.merge(cover, on="ACCESSION_NUMBER", validate="one_to_one")
    f = f[f.SUBMISSIONTYPE.isin(["13F-HR", "13F-HR/A"])].copy()
    kinds = {
        "RESTATEMENT": "restatement",
        "NEW HOLDINGS": "addition",
        "ADDS NEW HOLDINGS ENTRIES": "addition",
    }
    f["amendment"] = [
        kinds.get(t.strip().upper(), "unknown") if typ.endswith("/A") else "original"
        for t, typ in zip(f.AMENDMENTTYPE, f.SUBMISSIONTYPE)
    ]
    f = f.rename(
        columns={
            "ACCESSION_NUMBER": "accession",
            "CIK": "cik",
            "FILINGMANAGER_NAME": "manager",
            "PERIODOFREPORT": "report_date",
            "FILING_DATE": "filing_date",
        }
    )
    for col in ["report_date", "filing_date"]:
        f[col] = pd.to_datetime(f[col], format="%d-%b-%Y")
    # Official unit transition; explicit override retained for exceptional source errors.
    factor = f.filing_date.map(lambda d: 1000 if d < pd.Timestamp("2023-01-03") else 1)
    if value_unit != "auto":
        factor[:] = 1 if value_unit == "usd" else 1000
    f["value_multiplier"] = factor
    f["unit_policy"] = value_unit
    p = info[info.ACCESSION_NUMBER.isin(f.accession)].copy()
    p = p[p.PUTCALL.str.strip().eq("") & p.SSHPRNAMTTYPE.str.upper().eq("SH")]
    p = p.rename(columns={"ACCESSION_NUMBER": "accession", "CUSIP": "security_id", "SSHPRNAMT": "shares"})
    p["value_usd"] = pd.to_numeric(p.VALUE) * p.accession.map(f.set_index("accession").value_multiplier)
    p["security_id"] = p.security_id.str.strip().str.upper()
    if not p.security_id.str.fullmatch(r"[A-Z0-9*@#]{9}").all():
        raise ValueError("Invalid CUSIP shape")
    return validate(f, p[["accession", "security_id", "shares", "value_usd"]])

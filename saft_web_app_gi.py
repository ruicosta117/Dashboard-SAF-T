from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


WEEKDAYS_PT = [
    "Segunda",
    "Terça",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sábado",
    "Domingo",
]

TIME_BANDS = [
    (0, 5, "00-05 Madrugada"),
    (6, 10, "06-10 Manhã"),
    (11, 14, "11-14 Almoço"),
    (15, 18, "15-18 Tarde"),
    (19, 22, "19-22 Jantar/Noite"),
    (23, 23, "23-23 Encerramento"),
]

PAYMENT_METHOD_LABELS = {
    "MB": "MB - Multibanco",
    "NU": "NU - Numerário",
    "NM": "NM - Numerário",
    "TB": "TB - Transferência",
}

FAMILY_NAMES_FILENAME = "saft_family_names.json"


@dataclass
class SaftData:
    invoices: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    products: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


def local_name(tag: str) -> str:
    if not tag:
        return ""
    return tag.split("}", 1)[1] if "}" in tag else tag


def direct_children_by_name(elem, child_name: str):
    return [child for child in list(elem) if local_name(child.tag) == child_name]


def find_first_text(elem, names: Iterable[str]) -> str:
    wanted = set(names)
    for child in elem.iter():
        if local_name(child.tag) in wanted:
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def safe_float(value) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(" ", "")
    if not text:
        return 0.0
    if text.count(",") == 1 and text.count(".") > 1:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0.0


def parse_date_only(text: str):
    text = (text or "").strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(text[:26], fmt).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "")).date()
    except Exception:
        return None


def parse_datetime(text: str):
    text = (text or "").strip()
    if not text:
        return None
    candidates = [text, text.replace("Z", "")]
    for candidate in candidates:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(candidate[:26], fmt)
            except Exception:
                pass
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            pass
    return None


def month_date_range(text: str):
    text = (text or "").strip()
    if not text:
        return None, None
    try:
        dt = datetime.strptime(text, "%Y-%m")
    except Exception:
        return None, None
    start = date(dt.year, dt.month, 1)
    if dt.month == 12:
        end = date(dt.year + 1, 1, 1)
    else:
        end = date(dt.year, dt.month + 1, 1)
    return start, end


def code_sort_key(code: str):
    text = (code or "").strip()
    if not text:
        return (1, "")
    if text.isdigit():
        return (0, int(text), text)
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return (0, int(digits), text.upper())
    return (1, text.upper())


def family_key_from_code(code: str):
    text = (code or "").strip()
    if not text:
        return 999999, "Sem família"
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return 999999, f"Outros ({text})"
    number = int(digits)
    start = (number // 100) * 100
    end = start + 99
    return start, f"{start:03d}-{end:03d}"


def family_display_label(family_start, family_label, family_names=None):
    family_names = family_names or {}
    key = str(int(family_start)) if str(family_start).isdigit() else str(family_start)
    custom_name = (family_names.get(key, "") or "").strip()
    return f"{family_label} - {custom_name}" if custom_name else family_label


def payment_method_label(code: str) -> str:
    code = (code or "").strip().upper()
    if not code:
        return "Sem meio"
    return PAYMENT_METHOD_LABELS.get(code, code)


def time_band_from_hour(hour: int | None) -> str:
    if hour is None:
        return "Sem hora"
    for start, end, label in TIME_BANDS:
        if start <= hour <= end:
            return label
    return "Sem hora"


def money(value: float) -> str:
    s = f"{value:,.2f} €"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def number_fmt(value: float) -> str:
    s = f"{value:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ticket_medio(total: float, quantidade: int) -> float:
    return total / quantidade if quantidade else 0.0


def sort_group_items(df: pd.DataFrame, group: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if group == "Hora":
        out["__sort"] = out.iloc[:, 0].map(lambda x: 99 if x == "Sem hora" else int(str(x)[:2]))
        out = out.sort_values("__sort")
        return out.drop(columns=["__sort"])
    if group == "Dia semana":
        order = {name: i for i, name in enumerate(WEEKDAYS_PT)}
        out["__sort"] = out.iloc[:, 0].map(lambda x: order.get(x, 99))
        out = out.sort_values("__sort")
        return out.drop(columns=["__sort"])
    return out.sort_values(out.columns[0])


FAMILY_NAMES_PATH = Path(__file__).with_name(FAMILY_NAMES_FILENAME)


def load_family_names() -> dict[str, str]:
    if FAMILY_NAMES_PATH.exists():
        try:
            data = json.loads(FAMILY_NAMES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
    return {}


def save_family_names(data: dict[str, str]):
    cleaned = {str(k): str(v).strip() for k, v in data.items() if str(v).strip()}
    FAMILY_NAMES_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


@st.cache_data(show_spinner=False)
def parse_saft_bytes(file_bytes: bytes) -> SaftData:
    data = SaftData()
    context = ET.iterparse(io.BytesIO(file_bytes), events=("end",))

    for _event, elem in context:
        tag = local_name(elem.tag)

        if tag == "Product":
            code = find_first_text(elem, ["ProductCode"])
            desc = find_first_text(elem, ["ProductDescription", "Description"])
            if code:
                data.products[code] = desc or code
            elem.clear()
            continue

        if tag == "Invoice":
            row, lines = parse_invoice(elem, data.products)
            if row is not None:
                data.invoices.append(row)
                data.lines.extend(lines)
            elem.clear()
            continue

        if tag == "Payment":
            row = parse_payment(elem)
            if row is not None:
                data.payments.append(row)
            elem.clear()
            continue

    dates = [x["date"] for x in data.invoices if x.get("date")]
    data.stats = {
        "invoice_count": len(data.invoices),
        "line_count": len(data.lines),
        "payment_count": len(data.payments),
        "product_count": len(data.products),
        "total_sales": sum(x["gross_total"] for x in data.invoices),
        "total_qty": sum(x["qty"] for x in data.lines),
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
    }
    return data


def parse_invoice(invoice_elem, product_map: dict[str, str]):
    status = find_first_text(invoice_elem, ["InvoiceStatus", "Status"])
    if status.upper().startswith("A"):
        return None, []

    invoice_no = find_first_text(invoice_elem, ["InvoiceNo", "DocumentNumber"])
    invoice_type = find_first_text(invoice_elem, ["InvoiceType"])
    source_id = find_first_text(invoice_elem, ["SourceID", "UserID", "CashierID", "OperatorID", "Salesperson", "SellerID"])
    system_entry = find_first_text(invoice_elem, ["SystemEntryDate"])
    invoice_date_text = find_first_text(invoice_elem, ["InvoiceDate"])
    dt = parse_datetime(system_entry) or parse_datetime(invoice_date_text)
    d = dt.date() if dt else parse_date_only(invoice_date_text or system_entry)
    hour = dt.hour if dt else None
    gross_total = safe_float(find_first_text(invoice_elem, ["GrossTotal", "SettlementAmount", "NetTotal"]))
    net_total = safe_float(find_first_text(invoice_elem, ["NetTotal"]))
    tax_payable = safe_float(find_first_text(invoice_elem, ["TaxPayable"]))

    row = {
        "date": d,
        "datetime": dt,
        "hour": hour,
        "month": d.strftime("%Y-%m") if d else "Sem data",
        "weekday": WEEKDAYS_PT[d.weekday()] if d else "Sem data",
        "time_band": time_band_from_hour(hour),
        "invoice_no": invoice_no or "(sem nº)",
        "invoice_type": invoice_type or "(sem tipo)",
        "operator": source_id or "Sem operador",
        "gross_total": gross_total,
        "net_total": net_total,
        "tax_payable": tax_payable,
        "doc_count": 1,
    }

    lines = []
    for line in direct_children_by_name(invoice_elem, "Line"):
        product_code = find_first_text(line, ["ProductCode", "ProductNumberCode"])
        description = find_first_text(line, ["ProductDescription", "Description"])
        if not description and product_code:
            description = product_map.get(product_code, "")
        qty = safe_float(find_first_text(line, ["Quantity"]))
        amount = safe_float(find_first_text(line, ["CreditAmount", "DebitAmount", "Amount"]))
        unit_price = safe_float(find_first_text(line, ["UnitPrice"]))
        if amount == 0.0 and qty and unit_price:
            amount = qty * unit_price

        lines.append(
            {
                "date": d,
                "month": d.strftime("%Y-%m") if d else "Sem data",
                "weekday": WEEKDAYS_PT[d.weekday()] if d else "Sem data",
                "hour": hour,
                "time_band": time_band_from_hour(hour),
                "operator": source_id or "Sem operador",
                "invoice_no": invoice_no or "(sem nº)",
                "product_code": product_code or "Sem código",
                "description": description or "Sem descrição",
                "qty": qty,
                "amount": amount,
            }
        )

    return row, lines


def parse_payment(payment_elem):
    status = find_first_text(payment_elem, ["PaymentStatus", "Status"])
    if status.upper().startswith("A"):
        return None

    payment_ref = find_first_text(payment_elem, ["PaymentRefNo", "ReceiptNo", "DocumentNumber", "TransactionID", "PaymentID"])
    payment_method_code = find_first_text(payment_elem, ["PaymentMechanism", "PaymentMethod", "PaymentType", "Tender", "TenderType", "MeansOfPayment"])
    source_id = find_first_text(payment_elem, ["SourceID", "UserID", "CashierID", "OperatorID", "SellerID"])
    date_text = find_first_text(payment_elem, ["SystemEntryDate", "TransactionDate", "PaymentDate", "SettlementDate"])
    dt = parse_datetime(date_text)
    d = dt.date() if dt else parse_date_only(date_text)
    hour = dt.hour if dt else None
    gross_total = safe_float(find_first_text(payment_elem, ["PaymentAmount", "SettlementAmount", "GrossTotal", "NetTotal", "Amount"]))

    if not payment_ref:
        payment_ref = f"{payment_method_code or 'SEM'}-{date_text or 'SEM-DATA'}-{gross_total:.2f}"

    return {
        "date": d,
        "datetime": dt,
        "hour": hour,
        "month": d.strftime("%Y-%m") if d else "Sem data",
        "weekday": WEEKDAYS_PT[d.weekday()] if d else "Sem data",
        "time_band": time_band_from_hour(hour),
        "payment_ref": payment_ref or "(sem ref)",
        "payment_method": payment_method_label(payment_method_code),
        "operator": source_id or "Sem operador",
        "gross_total": gross_total,
        "count": 1,
    }


def to_dataframes(data: SaftData):
    invoices_df = pd.DataFrame(data.invoices)
    lines_df = pd.DataFrame(data.lines)
    payments_df = pd.DataFrame(data.payments)

    for df in (invoices_df, lines_df, payments_df):
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return invoices_df, lines_df, payments_df


def apply_date_filter(df: pd.DataFrame, start_date: date | None, end_date: date | None):
    if df.empty or "date" not in df.columns:
        return df.copy()
    out = df.copy()
    if start_date is not None:
        out = out[out["date"] >= start_date]
    if end_date is not None:
        out = out[out["date"] <= end_date]
    return out


def draw_bar_chart(df: pd.DataFrame, x_col: str, y_col: str, title: str, ylabel: str):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    if df.empty:
        ax.text(0.5, 0.5, "Sem dados para apresentar", ha="center", va="center")
        ax.set_axis_off()
        st.pyplot(fig, use_container_width=True)
        return
    ax.bar(range(len(df)), df[y_col].tolist())
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(df[x_col].tolist(), rotation=45, ha="right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)


def build_periods_table(invoices: pd.DataFrame, group: str):
    if invoices.empty:
        return pd.DataFrame(columns=["Período", "Valor", "Documentos", "Ticket médio"])

    group_col_map = {
        "Hora": invoices["hour"].apply(lambda x: "Sem hora" if pd.isna(x) else f"{int(x):02d}:00"),
        "Faixa horária": invoices["time_band"],
        "Dia semana": invoices["weekday"],
        "Dia": invoices["date"].astype(str).fillna("Sem data"),
        "Mês": invoices["month"],
    }
    temp = invoices.copy()
    temp["group_key"] = group_col_map[group]
    grouped = (
        temp.groupby("group_key", dropna=False)
        .agg(Valor=("gross_total", "sum"), Documentos=("doc_count", "sum"))
        .reset_index()
        .rename(columns={"group_key": "Período"})
    )
    grouped["Ticket médio"] = grouped.apply(lambda r: ticket_medio(r["Valor"], int(r["Documentos"])), axis=1)
    return sort_group_items(grouped, group)


def build_articles_table(lines: pd.DataFrame, group_mode: str, sort_mode: str, family_names: dict[str, str]):
    if lines.empty:
        base_cols = ["Código" if group_mode == "Artigos" else "Família", "Descrição", "Quantidade", "Valor", "selection_key"]
        return pd.DataFrame(columns=base_cols)

    temp = lines.copy()
    if group_mode == "Famílias (100)":
        fam_info = temp["product_code"].apply(family_key_from_code)
        temp["family_start"] = fam_info.apply(lambda x: x[0])
        temp["family_label"] = fam_info.apply(lambda x: x[1])
        grouped = (
            temp.groupby(["family_start", "family_label"], dropna=False)
            .agg(Quantidade=("qty", "sum"), Valor=("amount", "sum"), Codigos=("product_code", "nunique"))
            .reset_index()
        )
        grouped["Família"] = grouped.apply(
            lambda r: family_display_label(r["family_start"], r["family_label"], family_names), axis=1
        )
        grouped["Descrição"] = grouped.apply(
            lambda r: family_names.get(str(int(r["family_start"])), "") or f"{int(r['Codigos'])} código(s)", axis=1
        )
        grouped["selection_key"] = grouped["family_start"].astype(int).astype(str)
        if sort_mode == "Código":
            grouped = grouped.sort_values(["family_start", "family_label"])
        elif sort_mode == "Quantidade":
            grouped = grouped.sort_values("Quantidade", ascending=False)
        else:
            grouped = grouped.sort_values("Valor", ascending=False)
        return grouped[["Família", "Descrição", "Quantidade", "Valor", "selection_key"]]

    grouped = (
        temp.groupby("product_code", dropna=False)
        .agg(Quantidade=("qty", "sum"), Valor=("amount", "sum"), Descrição=("description", "first"))
        .reset_index()
        .rename(columns={"product_code": "Código"})
    )
    grouped["Descrição"] = grouped["Descrição"].fillna("Sem descrição")
    grouped["selection_key"] = grouped["Código"]
    if sort_mode == "Código":
        grouped = grouped.sort_values("Código", key=lambda s: s.map(code_sort_key))
    elif sort_mode == "Quantidade":
        grouped = grouped.sort_values("Quantidade", ascending=False)
    else:
        grouped = grouped.sort_values("Valor", ascending=False)
    return grouped[["Código", "Descrição", "Quantidade", "Valor", "selection_key"]]


def build_distribution_table(lines: pd.DataFrame, selection_key: str, group_mode: str, dist_group: str):
    if lines.empty or not selection_key:
        return pd.DataFrame(columns=["Período", "Quantidade", "Valor"])

    temp = lines.copy()
    if group_mode == "Famílias (100)":
        temp["match"] = temp["product_code"].apply(lambda code: str(family_key_from_code(code)[0]) == str(selection_key))
    else:
        temp["match"] = temp["product_code"].astype(str) == str(selection_key)
    temp = temp[temp["match"]]
    if temp.empty:
        return pd.DataFrame(columns=["Período", "Quantidade", "Valor"])

    if dist_group == "Hora":
        temp["group_key"] = temp["hour"].apply(lambda x: "Sem hora" if pd.isna(x) else f"{int(x):02d}:00")
    elif dist_group == "Faixa horária":
        temp["group_key"] = temp["time_band"]
    elif dist_group == "Dia semana":
        temp["group_key"] = temp["weekday"]
    elif dist_group == "Dia":
        temp["group_key"] = temp["date"].astype(str).fillna("Sem data")
    else:
        temp["group_key"] = temp["month"]

    grouped = (
        temp.groupby("group_key", dropna=False)
        .agg(Quantidade=("qty", "sum"), Valor=("amount", "sum"))
        .reset_index()
        .rename(columns={"group_key": "Período"})
    )
    return sort_group_items(grouped, dist_group)


def build_article_hour_table(lines: pd.DataFrame, group_mode: str, metric: str, family_names: dict[str, str], top_n: int, sort_mode: str = "Valor"):
    id_col = "Código" if group_mode == "Artigos" else "Família"
    hour_cols = [f"{hour:02d}:00" for hour in range(24)] + ["Sem hora"]
    base_columns = [id_col, "Descrição"] + hour_cols + ["Total"]
    if lines.empty:
        return pd.DataFrame(columns=base_columns)

    temp = lines.copy()
    temp["hour_label"] = temp["hour"].apply(lambda x: "Sem hora" if pd.isna(x) else f"{int(x):02d}:00")
    value_col = "amount" if metric == "Valor" else "qty"

    if group_mode == "Famílias (100)":
        fam_info = temp["product_code"].apply(family_key_from_code)
        temp["family_start"] = fam_info.apply(lambda x: x[0])
        temp["family_label"] = fam_info.apply(lambda x: x[1])
        totals = (
            temp.groupby(["family_start", "family_label"], dropna=False)
            .agg(Total=(value_col, "sum"), Codigos=("product_code", "nunique"))
            .reset_index()
        )
        totals["Família"] = totals.apply(
            lambda r: family_display_label(r["family_start"], r["family_label"], family_names), axis=1
        )
        totals["Descrição"] = totals.apply(
            lambda r: family_names.get(str(int(r["family_start"])), "") or f"{int(r['Codigos'])} código(s)", axis=1
        )
        if sort_mode == "Código":
            totals = totals.sort_values(["family_start", "family_label"])
        else:
            totals = totals.sort_values("Total", ascending=False)
        selected = totals.head(int(top_n)).copy()
        if selected.empty:
            return pd.DataFrame(columns=base_columns)
        selected_starts = set(selected["family_start"].astype(int).tolist())
        temp = temp[temp["family_start"].astype(int).isin(selected_starts)]
        pivot = temp.pivot_table(index="family_start", columns="hour_label", values=value_col, aggfunc="sum", fill_value=0.0)
        result = selected.set_index("family_start")[["Família", "Descrição", "Total"]].join(pivot, how="left").fillna(0.0)
        for col in hour_cols:
            if col not in result.columns:
                result[col] = 0.0
        result = result[["Família", "Descrição"] + hour_cols + ["Total"]].reset_index(drop=True)
        return result

    totals = (
        temp.groupby("product_code", dropna=False)
        .agg(Total=(value_col, "sum"), Descrição=("description", "first"))
        .reset_index()
        .rename(columns={"product_code": "Código"})
    )
    totals["Descrição"] = totals["Descrição"].fillna("Sem descrição")
    if sort_mode == "Código":
        totals = totals.sort_values("Código", key=lambda s: s.map(code_sort_key))
    else:
        totals = totals.sort_values("Total", ascending=False)
    selected = totals.head(int(top_n)).copy()
    if selected.empty:
        return pd.DataFrame(columns=base_columns)
    selected_codes = set(selected["Código"].astype(str).tolist())
    temp = temp[temp["product_code"].astype(str).isin(selected_codes)]
    pivot = temp.pivot_table(index="product_code", columns="hour_label", values=value_col, aggfunc="sum", fill_value=0.0)
    result = selected.set_index("Código")[["Descrição", "Total"]].join(pivot, how="left").fillna(0.0)
    for col in hour_cols:
        if col not in result.columns:
            result[col] = 0.0
    result = result[["Descrição"] + hour_cols + ["Total"]].reset_index()
    return result


def build_top_entities_for_hour(lines: pd.DataFrame, group_mode: str, metric: str, family_names: dict[str, str], selected_hour_label: str, top_n: int):
    id_col = "Código" if group_mode == "Artigos" else "Família"
    if lines.empty:
        return pd.DataFrame(columns=[id_col, "Descrição", "Quantidade", "Valor"])

    temp = lines.copy()
    if selected_hour_label == "Sem hora":
        temp = temp[temp["hour"].isna()]
    else:
        try:
            hour_value = int(str(selected_hour_label)[:2])
        except Exception:
            return pd.DataFrame(columns=[id_col, "Descrição", "Quantidade", "Valor"])
        temp = temp[temp["hour"].fillna(-1).astype(int) == hour_value]
    if temp.empty:
        return pd.DataFrame(columns=[id_col, "Descrição", "Quantidade", "Valor"])

    if group_mode == "Famílias (100)":
        fam_info = temp["product_code"].apply(family_key_from_code)
        temp["family_start"] = fam_info.apply(lambda x: x[0])
        temp["family_label"] = fam_info.apply(lambda x: x[1])
        grouped = (
            temp.groupby(["family_start", "family_label"], dropna=False)
            .agg(Quantidade=("qty", "sum"), Valor=("amount", "sum"), Codigos=("product_code", "nunique"))
            .reset_index()
        )
        grouped["Família"] = grouped.apply(
            lambda r: family_display_label(r["family_start"], r["family_label"], family_names), axis=1
        )
        grouped["Descrição"] = grouped.apply(
            lambda r: family_names.get(str(int(r["family_start"])), "") or f"{int(r['Codigos'])} código(s)", axis=1
        )
        sort_col = "Valor" if metric == "Valor" else "Quantidade"
        grouped = grouped.sort_values(sort_col, ascending=False)
        return grouped[["Família", "Descrição", "Quantidade", "Valor"]].head(int(top_n))

    grouped = (
        temp.groupby("product_code", dropna=False)
        .agg(Quantidade=("qty", "sum"), Valor=("amount", "sum"), Descrição=("description", "first"))
        .reset_index()
        .rename(columns={"product_code": "Código"})
    )
    grouped["Descrição"] = grouped["Descrição"].fillna("Sem descrição")
    sort_col = "Valor" if metric == "Valor" else "Quantidade"
    grouped = grouped.sort_values(sort_col, ascending=False)
    return grouped[["Código", "Descrição", "Quantidade", "Valor"]].head(int(top_n))


def format_article_hour_display(df: pd.DataFrame, metric: str):
    display = df.copy()
    if display.empty:
        return display
    numeric_cols = [col for col in display.columns if col not in ("Código", "Família", "Descrição")]
    for col in numeric_cols:
        display[col] = display[col].map(money if metric == "Valor" else number_fmt)
    return display


def build_payments_table(payments: pd.DataFrame):
    if payments.empty:
        return pd.DataFrame(columns=["Meio", "Valor", "Pagamentos", "Ticket médio"])
    grouped = (
        payments.groupby("payment_method", dropna=False)
        .agg(Valor=("gross_total", "sum"), Pagamentos=("count", "sum"))
        .reset_index()
        .rename(columns={"payment_method": "Meio"})
        .sort_values("Valor", ascending=False)
    )
    grouped["Ticket médio"] = grouped.apply(lambda r: ticket_medio(r["Valor"], int(r["Pagamentos"])), axis=1)
    return grouped


def build_operators_table(invoices: pd.DataFrame):
    if invoices.empty:
        return pd.DataFrame(columns=["Operador", "Valor", "Documentos", "Ticket médio"])
    grouped = (
        invoices.groupby("operator", dropna=False)
        .agg(Valor=("gross_total", "sum"), Documentos=("doc_count", "sum"))
        .reset_index()
        .rename(columns={"operator": "Operador"})
        .sort_values("Valor", ascending=False)
    )
    grouped["Ticket médio"] = grouped.apply(lambda r: ticket_medio(r["Valor"], int(r["Documentos"])), axis=1)
    return grouped


def make_downloadable_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def render_family_editor(lines: pd.DataFrame):
    st.subheader("Nomes das famílias")
    if lines.empty:
        st.info("Carrega um SAF-T para editar os nomes das famílias.")
        return

    temp = lines.copy()
    fam_info = temp["product_code"].apply(family_key_from_code)
    family_ranges = sorted({(int(start), label) for start, label in fam_info.tolist()}, key=lambda x: x[0])
    if not family_ranges:
        st.info("Não foram encontradas famílias numéricas nos artigos do ficheiro.")
        return

    current_names = st.session_state.get("family_names", load_family_names())
    rows = []
    for start, label in family_ranges:
        rows.append({"Início": start, "Família": label, "Nome": current_names.get(str(start), "")})
    editor_df = pd.DataFrame(rows)

    edited = st.data_editor(
        editor_df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key="family_editor",
        column_config={
            "Início": st.column_config.NumberColumn(disabled=True),
            "Família": st.column_config.TextColumn(disabled=True),
            "Nome": st.column_config.TextColumn(help="Ex.: Bebidas, Francesinhas, Sobremesas"),
        },
    )

    col_a, col_b = st.columns([1, 3])
    if col_a.button("Guardar nomes das famílias", use_container_width=True):
        names = {str(int(row["Início"])): str(row["Nome"]).strip() for _, row in edited.iterrows() if str(row["Nome"]).strip()}
        save_family_names(names)
        st.session_state["family_names"] = names
        st.success("Nomes das famílias guardados com sucesso.")
    if col_b.button("Recarregar nomes gravados", use_container_width=True):
        st.session_state["family_names"] = load_family_names()
        st.rerun()


def main():
    st.set_page_config(page_title="Dashboard SAF-T | Gestão Inteligente", layout="wide")
    st.title("Dashboard SAF-T | Gestão Inteligente")
    st.caption("App web em Python para análise de vendas por períodos, artigos, pagamentos e operadores.")

    if "family_names" not in st.session_state:
        st.session_state["family_names"] = load_family_names()

    uploaded = st.sidebar.file_uploader("Selecionar ficheiro SAF-T XML", type=["xml"])
    st.sidebar.markdown("---")

    if not uploaded:
        st.info("Carrega um ficheiro SAF-T XML na barra lateral para começar.")
        st.stop()

    with st.spinner("A analisar o ficheiro SAF-T..."):
        data = parse_saft_bytes(uploaded.getvalue())
    invoices_df, lines_df, payments_df = to_dataframes(data)

    min_date = data.stats.get("min_date")
    max_date = data.stats.get("max_date")
    available_months = sorted([m for m in invoices_df.get("month", pd.Series(dtype=str)).dropna().unique().tolist() if m and m != "Sem data"])

    st.sidebar.subheader("Filtros")
    month_choice = st.sidebar.selectbox("Mês", options=["Todos"] + available_months, index=0)

    if month_choice != "Todos":
        start_date, end_exclusive = month_date_range(month_choice)
        end_date = date.fromordinal(end_exclusive.toordinal() - 1) if end_exclusive else None
    else:
        default_start = min_date or date.today()
        default_end = max_date or date.today()
        start_date = st.sidebar.date_input("Data inicial", value=default_start)
        end_date = st.sidebar.date_input("Data final", value=default_end)

    if start_date and end_date and end_date < start_date:
        st.sidebar.error("A data final tem de ser igual ou posterior à inicial.")
        st.stop()

    inv = apply_date_filter(invoices_df, start_date, end_date)
    lines = apply_date_filter(lines_df, start_date, end_date)
    pays = apply_date_filter(payments_df, start_date, end_date)

    total_sales = float(inv["gross_total"].sum()) if not inv.empty else 0.0
    total_docs = int(inv["doc_count"].sum()) if not inv.empty else 0
    total_lines = len(lines)
    total_payments = int(pays["count"].sum()) if not pays.empty else 0
    period_label = f"{start_date.isoformat()} a {end_date.isoformat()}" if start_date and end_date else "Sem filtro"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Faturas", f"{total_docs:,}".replace(",", "."))
    c2.metric("Total vendas", money(total_sales))
    c3.metric("Ticket médio", money(ticket_medio(total_sales, total_docs)))
    c4.metric("Linhas", f"{total_lines:,}".replace(",", "."))
    c5.metric("Pagamentos", f"{total_payments:,}".replace(",", "."))
    c6.metric("Período", period_label)

    tab_periods, tab_articles, tab_article_hours, tab_payments, tab_operators, tab_summary = st.tabs(
        ["Períodos", "Artigos", "Art./Fam. por hora", "Pagamentos", "Operadores", "Resumo"]
    )

    with tab_periods:
        left, right = st.columns([1.05, 1.2])
        with left:
            period_group = st.selectbox("Agrupar por", ["Hora", "Faixa horária", "Dia semana", "Dia", "Mês"], key="period_group")
            period_metric = st.radio("Métrica do gráfico", ["Valor", "Documentos"], horizontal=True, key="period_metric")
            periods_table = build_periods_table(inv, period_group)
            display = periods_table.copy()
            if not display.empty:
                display["Valor"] = display["Valor"].map(money)
                display["Documentos"] = display["Documentos"].map(lambda x: f"{int(x):,}".replace(",", "."))
                display["Ticket médio"] = display["Ticket médio"].map(money)
            st.dataframe(display, use_container_width=True, hide_index=True)
            st.download_button(
                "Exportar períodos para CSV",
                data=make_downloadable_csv(periods_table),
                file_name="periodos_saft.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with right:
            metric_col = "Valor" if period_metric == "Valor" else "Documentos"
            ylabel = "Valor (€)" if period_metric == "Valor" else "Documentos"
            draw_bar_chart(periods_table, "Período", metric_col, f"Períodos por {period_group.lower()}", ylabel)

    with tab_articles:
        top_controls = st.columns([1, 1, 1, 1, 1])
        group_mode = top_controls[0].selectbox("Agrupar", ["Artigos", "Famílias (100)"], key="article_group_mode")
        sort_mode = top_controls[1].selectbox("Ordenar por", ["Valor", "Quantidade", "Código"], key="article_sort_mode")
        article_metric = top_controls[2].radio("Métrica", ["Valor", "Quantidade"], horizontal=True, key="article_metric")
        top_n = top_controls[3].number_input("Top N", min_value=5, max_value=500, value=20, step=5, key="article_top_n")
        dist_group = top_controls[4].selectbox("Distribuição por", ["Hora", "Faixa horária", "Dia semana", "Dia", "Mês"], key="article_dist_group")

        with st.expander("Editar nomes das famílias", expanded=False):
            render_family_editor(lines)

        articles_table = build_articles_table(lines, group_mode, sort_mode, st.session_state.get("family_names", {}))
        visible_articles = articles_table.head(int(top_n)).copy()

        left, right = st.columns([1.05, 1.2])
        with left:
            display = visible_articles.copy()
            if not display.empty:
                display["Quantidade"] = display["Quantidade"].map(number_fmt)
                display["Valor"] = display["Valor"].map(money)
            st.dataframe(display.drop(columns=["selection_key"], errors="ignore"), use_container_width=True, hide_index=True)
            st.download_button(
                "Exportar artigos para CSV",
                data=make_downloadable_csv(articles_table.drop(columns=["selection_key"], errors="ignore")),
                file_name="artigos_saft.csv",
                mime="text/csv",
                use_container_width=True,
            )

            if visible_articles.empty:
                st.info("Sem artigos para o filtro atual.")
                selected_key = ""
            else:
                label_col = "Família" if group_mode == "Famílias (100)" else "Código"
                selection_options = [
                    (row["selection_key"], f"{row[label_col]} | {row['Descrição']}")
                    for _, row in visible_articles.iterrows()
                ]
                selected_label = st.selectbox(
                    "Selecionar artigo/família para distribuição",
                    options=[opt[1] for opt in selection_options],
                    key="article_selection_label",
                )
                selected_key = next((key for key, label in selection_options if label == selected_label), "")

        with right:
            dist_table = build_distribution_table(lines, selected_key, group_mode, dist_group)
            if group_mode == "Famílias (100)" and selected_key:
                family_start = int(selected_key)
                family_label = family_display_label(family_start, f"{family_start:03d}-{family_start + 99:03d}", st.session_state.get("family_names", {}))
                base_title = f"Distribuição da família {family_label}"
                selection_lines = lines[lines["product_code"].apply(lambda code: str(family_key_from_code(code)[0]) == str(selected_key))]
                unique_codes = int(selection_lines["product_code"].nunique()) if not selection_lines.empty else 0
                st.info(
                    f"Família selecionada: {family_label} | Códigos: {unique_codes} | Quantidade: {number_fmt(selection_lines['qty'].sum()) if not selection_lines.empty else '0,00'} | Valor: {money(selection_lines['amount'].sum()) if not selection_lines.empty else money(0)}"
                )
            elif selected_key:
                selection_lines = lines[lines["product_code"].astype(str) == str(selected_key)]
                desc = selection_lines["description"].dropna().iloc[0] if not selection_lines.empty else "Sem descrição"
                st.info(
                    f"Artigo selecionado: {selected_key} | {desc} | Quantidade: {number_fmt(selection_lines['qty'].sum()) if not selection_lines.empty else '0,00'} | Valor: {money(selection_lines['amount'].sum()) if not selection_lines.empty else money(0)}"
                )
                base_title = f"Distribuição do artigo {selected_key}"
            else:
                base_title = "Distribuição"
            metric_col = "Valor" if article_metric == "Valor" else "Quantidade"
            ylabel = "Valor (€)" if article_metric == "Valor" else "Quantidade"
            draw_bar_chart(dist_table, "Período", metric_col, f"{base_title} por {dist_group.lower()}", ylabel)

    with tab_article_hours:
        st.subheader("Análise de artigos/famílias por horas")
        controls = st.columns([1, 1, 1, 1, 1])
        hour_group_mode = controls[0].selectbox("Analisar", ["Artigos", "Famílias (100)"], key="hour_group_mode")
        hour_metric = controls[1].radio("Métrica", ["Valor", "Quantidade"], horizontal=True, key="hour_metric")
        hour_sort_mode = controls[2].selectbox("Ordenar por", ["Valor", "Quantidade", "Código"], key="hour_sort_mode")
        hour_top_n = controls[3].number_input("Top N da matriz", min_value=5, max_value=500, value=20, step=5, key="hour_top_n")
        selected_hour_label = controls[4].selectbox(
            "Hora em destaque",
            options=[f"{hour:02d}:00" for hour in range(24)] + ["Sem hora"],
            index=12,
            key="selected_hour_label",
        )

        hour_matrix = build_article_hour_table(
            lines,
            hour_group_mode,
            hour_metric,
            st.session_state.get("family_names", {}),
            int(hour_top_n),
            hour_sort_mode,
        )

        left, right = st.columns([1.35, 1.0])
        with left:
            st.caption("Linhas = artigos ou famílias | Colunas = horas do dia")
            matrix_display = format_article_hour_display(hour_matrix, hour_metric)
            st.dataframe(matrix_display, use_container_width=True, hide_index=True, height=520)
            st.download_button(
                "Exportar matriz por hora para CSV",
                data=make_downloadable_csv(hour_matrix),
                file_name="artigos_familias_por_hora.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with right:
            top_hour_entities = build_top_entities_for_hour(
                lines,
                hour_group_mode,
                hour_metric,
                st.session_state.get("family_names", {}),
                selected_hour_label,
                int(hour_top_n),
            )
            if top_hour_entities.empty:
                st.info("Sem dados para a hora selecionada.")
            else:
                chart_metric_col = "Valor" if hour_metric == "Valor" else "Quantidade"
                label_col = "Família" if hour_group_mode == "Famílias (100)" else "Código"
                draw_bar_chart(
                    top_hour_entities,
                    label_col,
                    chart_metric_col,
                    f"Top {hour_group_mode.lower()} às {selected_hour_label}",
                    "Valor (€)" if hour_metric == "Valor" else "Quantidade",
                )
                display = top_hour_entities.copy()
                display["Quantidade"] = display["Quantidade"].map(number_fmt)
                display["Valor"] = display["Valor"].map(money)
                st.dataframe(display, use_container_width=True, hide_index=True)
                st.download_button(
                    "Exportar top da hora para CSV",
                    data=make_downloadable_csv(top_hour_entities),
                    file_name=f"top_{hour_group_mode.lower().replace(' ', '_')}_{selected_hour_label.replace(':', '')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    with tab_payments:
        left, right = st.columns([1.05, 1.2])
        with left:
            payments_table = build_payments_table(pays)
            display = payments_table.copy()
            if not display.empty:
                display["Valor"] = display["Valor"].map(money)
                display["Pagamentos"] = display["Pagamentos"].map(lambda x: f"{int(x):,}".replace(",", "."))
                display["Ticket médio"] = display["Ticket médio"].map(money)
            st.dataframe(display, use_container_width=True, hide_index=True)
            st.download_button(
                "Exportar pagamentos para CSV",
                data=make_downloadable_csv(payments_table),
                file_name="pagamentos_saft.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with right:
            draw_bar_chart(payments_table, "Meio", "Valor", "Pagamentos por meio", "Valor (€)")

    with tab_operators:
        left, right = st.columns([1.05, 1.2])
        with left:
            operators_table = build_operators_table(inv)
            display = operators_table.copy()
            if not display.empty:
                display["Valor"] = display["Valor"].map(money)
                display["Documentos"] = display["Documentos"].map(lambda x: f"{int(x):,}".replace(",", "."))
                display["Ticket médio"] = display["Ticket médio"].map(money)
            st.dataframe(display, use_container_width=True, hide_index=True)
            st.download_button(
                "Exportar operadores para CSV",
                data=make_downloadable_csv(operators_table),
                file_name="operadores_saft.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with right:
            draw_bar_chart(operators_table, "Operador", "Valor", "Vendas por operador", "Valor (€)")

    with tab_summary:
        st.subheader("Resumo técnico")
        summary_rows = [
            ("Ficheiro carregado", uploaded.name),
            ("Faturas", f"{data.stats.get('invoice_count', 0):,}".replace(",", ".")),
            ("Linhas", f"{data.stats.get('line_count', 0):,}".replace(",", ".")),
            ("Pagamentos", f"{data.stats.get('payment_count', 0):,}".replace(",", ".")),
            ("Produtos", f"{data.stats.get('product_count', 0):,}".replace(",", ".")),
            ("Total bruto do ficheiro", money(float(data.stats.get('total_sales', 0.0)))),
            ("Período global", f"{data.stats.get('min_date')} a {data.stats.get('max_date')}"),
        ]
        summary_df = pd.DataFrame(summary_rows, columns=["Campo", "Valor"])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Top 10 artigos por valor")
            top_articles = build_articles_table(lines, "Artigos", "Valor", st.session_state.get("family_names", {})).head(10)
            if not top_articles.empty:
                display = top_articles[["Código", "Descrição", "Quantidade", "Valor"]].copy()
                display["Quantidade"] = display["Quantidade"].map(number_fmt)
                display["Valor"] = display["Valor"].map(money)
                st.dataframe(display, use_container_width=True, hide_index=True)
            else:
                st.info("Sem dados.")
        with col_b:
            st.subheader("Top 10 meios de pagamento")
            payments_table = build_payments_table(pays).head(10)
            if not payments_table.empty:
                display = payments_table.copy()
                display["Valor"] = display["Valor"].map(money)
                display["Pagamentos"] = display["Pagamentos"].map(lambda x: f"{int(x):,}".replace(",", "."))
                display["Ticket médio"] = display["Ticket médio"].map(money)
                st.dataframe(display, use_container_width=True, hide_index=True)
            else:
                st.info("Sem dados.")


if __name__ == "__main__":
    main()

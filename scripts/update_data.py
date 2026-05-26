#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch Eastmoney A-share quotes and write data.json for GitHub Pages."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data.json"

EASTMONEY_URLS = [
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://7.push2.eastmoney.com/api/qt/clist/get",
    "https://16.push2.eastmoney.com/api/qt/clist/get",
    "https://60.push2.eastmoney.com/api/qt/clist/get",
    "https://72.push2.eastmoney.com/api/qt/clist/get",
    "https://92.push2.eastmoney.com/api/qt/clist/get",
]

FIELDS = ",".join([
    "f2", "f3", "f5", "f6", "f8", "f9", "f12", "f14", "f20", "f21", "f23", "f62", "f115",
])
FS = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
DATACENTER_TOKEN = "894050c76af8597a853f5b408b759f5d"
SINA_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
TENCENT_URL = "https://qt.gtimg.cn/q="
CHIP_CACHE: dict[str, float | None] = {}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def request_json(url: str, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://quote.eastmoney.com/center/gridlist.html",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_jsonp(url: str, callback: str = "callback", timeout: int = 15) -> dict[str, Any]:
    name = f"em_cb_{int(time.time() * 1000)}"
    sep = "&" if "?" in url else "?"
    raw = request_text(f"{url}{sep}{callback}={name}", timeout=timeout)
    prefix = f"{name}("
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    if raw.endswith(");"):
        raw = raw[:-2]
    elif raw.endswith(")"):
        raw = raw[:-1]
    return json.loads(raw)


def request_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://datacenter.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def fetch_page(page: int, page_size: int, retries: int, timeout: int) -> list[dict[str, Any]]:
    params = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": FS,
        "fields": FIELDS,
        "_": int(time.time() * 1000),
    }
    last_error: Exception | None = None
    for base in EASTMONEY_URLS:
        url = base + "?" + urllib.parse.urlencode(params)
        for attempt in range(retries + 1):
            try:
                payload = request_json(url, timeout=timeout)
                diff = payload.get("data", {}).get("diff") or []
                if isinstance(diff, dict):
                    return list(diff.values())
                return diff
            except Exception as exc:
                last_error = exc
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"读取东方财富第 {page} 页失败：{last_error}")


def fetch_all(page_size: int, max_pages: int, retries: int, timeout: int, sleep: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        page_rows = fetch_page(page, page_size, retries, timeout)
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        time.sleep(sleep)
    return rows


def fetch_datacenter_page(page: int, page_size: int, timeout: int) -> list[dict[str, Any]]:
    params = {
        "sortColumns": "SECURITY_CODE",
        "sortTypes": "1",
        "pageSize": page_size,
        "pageNumber": page,
        "reportName": "RPT_DMSK_TS_STOCKNEW",
        "quoteColumns": ",".join([
            "f2~01~SECURITY_CODE~CLOSE_PRICE",
            "f8~01~SECURITY_CODE~TURNOVERRATE",
            "f3~01~SECURITY_CODE~CHANGE_RATE",
            "f9~01~SECURITY_CODE~PE_DYNAMIC",
            "f6~01~SECURITY_CODE~AMOUNT",
            "f23~01~SECURITY_CODE~PB",
        ]),
        "quoteType": "0",
        "columns": "ALL",
        "filter": "",
        "token": DATACENTER_TOKEN,
        "_": int(time.time() * 1000),
    }
    url = DATACENTER_URL + "?" + urllib.parse.urlencode(params)
    payload = request_jsonp(url, callback="callback", timeout=timeout)
    return payload.get("result", {}).get("data") or []


def fetch_datacenter_all(page_size: int, max_pages: int, timeout: int, sleep: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        page_rows = fetch_datacenter_page(page, page_size, timeout)
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        time.sleep(sleep)
    return rows


def fetch_sina_page(page: int, page_size: int, timeout: int) -> list[dict[str, Any]]:
    params = {
        "page": page,
        "num": page_size,
        "sort": "symbol",
        "asc": 1,
        "node": "hs_a",
        "symbol": "",
        "_s_r_a": "page",
        "_": int(time.time() * 1000),
    }
    url = SINA_URL + "?" + urllib.parse.urlencode(params)
    return json.loads(request_text(url, timeout=timeout))


def fetch_sina_all(page_size: int, max_pages: int, timeout: int, sleep: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        page_rows = fetch_sina_page(page, page_size, timeout)
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        time.sleep(sleep)
    return rows


def normalize_code(code: str) -> str:
    code = str(code or "").strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        code = code[2:]
    if "." in code:
        code = code.split(".")[0]
    return code.zfill(6) if code.isdigit() else code


def tencent_prefix(code: str) -> str:
    code = normalize_code(code)
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith("8"):
        return f"bj{code}"
    return f"sz{code}"


def request_tencent_text(codes: list[str], timeout: int) -> str:
    url = TENCENT_URL + ",".join(tencent_prefix(code) for code in codes)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://gu.qq.com/",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("gbk", errors="ignore")


def parse_tencent_line(line: str) -> dict[str, Any] | None:
    if not line.strip() or "=" not in line or '"' not in line:
        return None
    key = line.split("=", 1)[0].split("_")[-1]
    vals = line.split('"', 2)[1].split("~")
    if len(vals) < 53:
        return None
    code = normalize_code(key)
    name = vals[1]
    price = to_float(vals[3])
    pct = to_float(vals[32])
    if not code or not name or price is None or pct is None:
        return None
    amount_wan = to_float(vals[37])
    total_cap_yi = to_float(vals[44])
    float_cap_yi = to_float(vals[45])
    return {
        "code": code,
        "name": name,
        "price": price,
        "pct": pct,
        "amount": amount_wan * 10_000 if amount_wan is not None else None,
        "turnover": to_float(vals[38]),
        "pe": to_float(vals[52]),
        "pe_ttm": to_float(vals[39]),
        "pb": to_float(vals[46]),
        "total_cap": total_cap_yi * 100_000_000 if total_cap_yi is not None else None,
        "float_cap": float_cap_yi * 100_000_000 if float_cap_yi is not None else None,
        "main_net": None,
        "concepts": [],
    }


def fetch_tencent_quotes(codes: list[str], batch_size: int, retries: int, timeout: int, sleep: float) -> list[dict[str, Any]]:
    stocks: list[dict[str, Any]] = []
    unique_codes = list(dict.fromkeys(normalize_code(code) for code in codes if normalize_code(code)))
    for start in range(0, len(unique_codes), batch_size):
        batch = unique_codes[start:start + batch_size]
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                text = request_tencent_text(batch, timeout=timeout)
                for line in text.strip().split(";"):
                    stock = parse_tencent_line(line)
                    if stock:
                        stocks.append(stock)
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.8 * (attempt + 1))
        else:
            print(f"tencent batch {start // batch_size + 1} failed: {last_error}")
        time.sleep(sleep)
    return stocks


def fetch_tencent_all(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Use a-stock-data's Tencent quote recipe for real-time fields."""
    codes: list[str] = []
    try:
        dc_rows = fetch_datacenter_all(args.page_size, args.max_pages, args.timeout, args.sleep)
        codes = [normalize_code(row.get("SECURITY_CODE") or "") for row in dc_rows]
    except Exception as exc:
        print(f"datacenter universe failed, fallback to sina universe: {exc}")
    if not codes:
        sina_rows = fetch_sina_all(args.page_size, args.max_pages, args.timeout, args.sleep)
        codes = [normalize_code(row.get("code") or row.get("symbol") or "") for row in sina_rows]
    if not codes:
        raise RuntimeError("无法获取 A 股代码池")
    return fetch_tencent_quotes(codes, args.tencent_batch_size, args.retries, args.timeout, args.sleep)


def parse_stock(item: dict[str, Any]) -> dict[str, Any] | None:
    price = to_float(item.get("f2"))
    pct = to_float(item.get("f3"))
    code = str(item.get("f12") or "")
    name = str(item.get("f14") or "")
    if not code or not name or price is None or pct is None:
        return None
    return {
        "code": code,
        "name": name,
        "price": price,
        "pct": pct,
        "amount": to_float(item.get("f6")),
        "turnover": to_float(item.get("f8")),
        "pe": to_float(item.get("f9")),
        "pe_ttm": to_float(item.get("f115")),
        "pb": to_float(item.get("f23")),
        "total_cap": to_float(item.get("f20")),
        "float_cap": to_float(item.get("f21")),
        "main_net": to_float(item.get("f62")),
        "concepts": [],
    }


def parse_datacenter_stock(item: dict[str, Any]) -> dict[str, Any] | None:
    price = to_float(item.get("CLOSE_PRICE"))
    pct = to_float(item.get("CHANGE_RATE"))
    code = str(item.get("SECURITY_CODE") or "")
    name = str(item.get("SECURITY_NAME_ABBR") or "")
    if not code or not name or price is None or pct is None:
        return None
    return {
        "code": code,
        "name": name,
        "price": price,
        "pct": pct,
        "amount": to_float(item.get("AMOUNT")),
        "turnover": to_float(item.get("TURNOVERRATE")),
        "pe": to_float(item.get("PE_DYNAMIC")),
        "pe_ttm": None,
        "pb": to_float(item.get("PB")),
        "total_cap": None,
        "float_cap": None,
        "main_net": to_float(item.get("PRIME_INFLOW")),
        "concepts": [],
    }


def parse_sina_stock(item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "")
    if not (symbol.startswith("sh") or symbol.startswith("sz")):
        return None
    price = to_float(item.get("trade"))
    pct = to_float(item.get("changepercent"))
    code = str(item.get("code") or symbol[2:])
    name = str(item.get("name") or "")
    if not code or not name or price is None or pct is None:
        return None
    # Sina mktcap/nmc are commonly ten-thousand CNY.
    total_cap = to_float(item.get("mktcap"))
    float_cap = to_float(item.get("nmc"))
    return {
        "code": code,
        "name": name,
        "price": price,
        "pct": pct,
        "amount": to_float(item.get("amount")),
        "turnover": to_float(item.get("turnoverratio")),
        "pe": to_float(item.get("per")),
        "pe_ttm": None,
        "pb": to_float(item.get("pb")),
        "total_cap": total_cap * 10_000 if total_cap is not None else None,
        "float_cap": float_cap * 10_000 if float_cap is not None else None,
        "main_net": None,
        "concepts": [],
    }


def score(stock: dict[str, Any]) -> float:
    amount_score = min((stock.get("amount") or 0) / 100_000_000, 3.0) * 16
    turnover_score = min((stock.get("turnover") or 0), 8.0) * 4
    inflow_score = max(min((stock.get("main_net") or 0) / 10_000_000, 8.0), -8.0) * 2
    pb = stock.get("pb") if stock.get("pb") and stock.get("pb") > 0 else 3.0
    pe = stock.get("pe") if stock.get("pe") and stock.get("pe") > 0 else stock.get("pe_ttm")
    pe = pe if pe and pe > 0 else 50.0
    valuation_score = max(0.0, 30.0 - pb * 4.0 - pe * 0.18)
    momentum_score = 8.0 - abs(stock.get("pct") or 0) * 0.7
    cap_score = min((stock.get("float_cap") or 0) / 10_000_000_000, 2.0) * 4
    return round(amount_score + turnover_score + inflow_score + valuation_score + momentum_score + cap_score, 2)


def fetch_chip_concentration(code: str) -> float | None:
    """Return latest 90% chip concentration as a percentage, e.g. 11.8."""
    if code in CHIP_CACHE:
        return CHIP_CACHE[code]
    try:
        rows = fetch_chip_kline(code)
        if len(rows) < 30:
            CHIP_CACHE[code] = None
            return None
        value = calc_chip_concentration_90(rows)
        if value is None or not math.isfinite(value):
            CHIP_CACHE[code] = None
            return None
        CHIP_CACHE[code] = round(value, 2)
        return CHIP_CACHE[code]
    except Exception:
        CHIP_CACHE[code] = None
        return None


def eastmoney_secid(code: str) -> str:
    code = normalize_code(code)
    market = "1" if code.startswith(("6", "9")) else "0"
    return f"{market}.{code}"


def fetch_chip_kline(code: str, timeout: int = 12) -> list[dict[str, float]]:
    params = {
        "secid": eastmoney_secid(code),
        "klt": 101,
        "fqt": 1,
        "lmt": 260,
        "end": "20500101",
        "iscca": 1,
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "_": int(time.time() * 1000),
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
    payload = request_json(url, timeout=timeout)
    klines = payload.get("data", {}).get("klines") or []
    rows: list[dict[str, float]] = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 11:
            continue
        close = to_float(parts[2])
        high = to_float(parts[3])
        low = to_float(parts[4])
        turnover = to_float(parts[10])
        if close is None or high is None or low is None or turnover is None:
            continue
        rows.append({"close": close, "high": high, "low": low, "turnover": turnover})
    return rows


def calc_chip_concentration_90(rows: list[dict[str, float]], index: int | None = None) -> float | None:
    """Pure-Python port of the public CYQ algorithm used by AKShare/Eastmoney."""
    if not rows:
        return None
    index = len(rows) - 1 if index is None else index
    start = max(0, index - 120)
    window = rows[start:index + 1]
    max_price = max(row["high"] for row in window)
    min_price = min(row["low"] for row in window)
    factor = 150
    accuracy = max(0.01, (max_price - min_price) / (factor - 1))
    chips = [0.0] * factor

    for row in rows[:index + 1]:
        turnover = max(0.0, min(1.0, row["turnover"] / 100.0))
        avg_price = (row["high"] + row["low"] + row["close"]) / 3.0
        if accuracy <= 0:
            continue
        min_offset = math.floor((row["low"] - min_price) / accuracy)
        max_offset = math.ceil((row["high"] - min_price) / accuracy)
        start_offset = max(0, min(factor - 1, min_offset))
        end_offset = max(0, min(factor - 1, max_offset))
        if end_offset < start_offset:
            continue
        weights: list[tuple[int, float]] = []
        for slot in range(start_offset, end_offset + 1):
            price = min_price + slot * accuracy
            height = max(0.0, 1.0 - abs(price - avg_price) / max(accuracy, row["high"] - row["low"] + accuracy))
            if height > 0:
                weights.append((slot, height))
        weight_sum = sum(weight for _, weight in weights)
        if weight_sum <= 0:
            continue
        keep = 1.0 - turnover
        chips = [value * keep for value in chips]
        for slot, weight in weights:
            chips[slot] += turnover * weight / weight_sum

    total = sum(chips)
    if total <= 0:
        return None

    def cost_at(percent: float) -> float:
        target = total * percent
        acc = 0.0
        for slot, value in enumerate(chips):
            acc += value
            if acc >= target:
                return min_price + slot * accuracy
        return min_price + (factor - 1) * accuracy

    low_90 = cost_at(0.05)
    high_90 = cost_at(0.95)
    denominator = low_90 + high_90
    if denominator <= 0:
        return None
    return (high_90 - low_90) / denominator * 100.0


def accepted_base(stock: dict[str, Any], threshold: float) -> bool:
    name_upper = stock["name"].upper()
    if stock["price"] <= 0 or stock["price"] >= threshold:
        return False
    if "ST" in name_upper or "退" in stock["name"]:
        return False
    if stock["pct"] <= -9.5:
        return False
    return True


def accepted(stock: dict[str, Any], threshold: float, chip_threshold: float | None, require_chip: bool) -> bool:
    if not accepted_base(stock, threshold):
        return False
    if chip_threshold is None:
        return True
    chip = stock.get("chip_concentration_90")
    if chip is None:
        return not require_chip
    return chip <= chip_threshold


def enrich_chip_concentration(stocks: list[dict[str, Any]], scan_limit: int, sleep: float) -> dict[str, int]:
    candidates = [s for s in stocks if accepted_base(s, 10.0)]
    candidates.sort(key=lambda s: s.get("score") or 0, reverse=True)
    candidates = candidates[:scan_limit]
    ok = 0
    failed = 0
    for index, stock in enumerate(candidates, start=1):
        value = fetch_chip_concentration(stock["code"])
        stock["chip_concentration_90"] = value
        if value is None:
            failed += 1
        else:
            ok += 1
        if index % 20 == 0:
            print(f"chip {index}/{len(candidates)} ok={ok} failed={failed}")
        time.sleep(sleep)
    return {"scanned": len(candidates), "ok": ok, "failed": failed}


def fetch_concepts(code: str, timeout: int = 12) -> list[str]:
    params = {
        "reportName": "RPT_F10_CORETHEME_BOARDTYPE",
        "columns": "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_CODE,BOARD_NAME,IS_PRECISE,BOARD_RANK,BOARD_TYPE",
        "filter": f'(SECURITY_CODE="{code}")',
        "sortColumns": "BOARD_RANK",
        "sortTypes": "1",
        "source": "HSF10",
        "client": "PC",
        "_": int(time.time() * 1000),
    }
    url = "https://datacenter.eastmoney.com/securities/api/data/v1/get?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://emweb.securities.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = payload.get("result", {}).get("data") or []
    concepts: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = row.get("BOARD_NAME")
        if name and name not in seen:
            seen.add(name)
            concepts.append(name)
        if len(concepts) >= 6:
            break
    return concepts


def add_concepts(buckets: dict[str, list[dict[str, Any]]], concept_limit: int, sleep: float) -> None:
    unique: dict[str, dict[str, Any]] = {}
    for bucket in buckets.values():
        for stock in bucket:
            unique.setdefault(stock["code"], stock)
    for index, stock in enumerate(list(unique.values())[:concept_limit], start=1):
        try:
            stock["concepts"] = fetch_concepts(stock["code"])
        except Exception:
            stock["concepts"] = []
        if index % 10 == 0:
            print(f"concepts {index}/{min(len(unique), concept_limit)}")
        time.sleep(sleep)


def make_payload(args: argparse.Namespace) -> dict[str, Any]:
    source = "tencent"
    try:
        stocks = fetch_tencent_all(args)
    except Exception as tencent_exc:
        print(f"tencent failed, fallback to eastmoney-push2: {tencent_exc}")
        try:
            raw_rows = fetch_all(args.page_size, args.max_pages, args.retries, args.timeout, args.sleep)
            stocks = [stock for item in raw_rows if (stock := parse_stock(item))]
            source = "eastmoney-push2"
        except Exception as exc:
            print(f"push2 failed, fallback to datacenter-web: {exc}")
            try:
                raw_rows = fetch_datacenter_all(args.page_size, args.max_pages, args.timeout, args.sleep)
                stocks = [stock for item in raw_rows if (stock := parse_datacenter_stock(item))]
                source = "eastmoney-datacenter"
            except Exception as dc_exc:
                print(f"datacenter failed, fallback to sina: {dc_exc}")
                raw_rows = fetch_sina_all(args.page_size, args.max_pages, args.timeout, args.sleep)
                stocks = [stock for item in raw_rows if (stock := parse_sina_stock(item))]
                source = "sina"
    if not stocks:
        raise RuntimeError("所有行情源均未返回有效股票数据")
    for stock in stocks:
        stock["score"] = score(stock)

    chip_stats = {"scanned": 0, "ok": 0, "failed": 0}
    if args.chip_threshold is not None:
        chip_stats = enrich_chip_concentration(stocks, args.chip_scan_limit, args.chip_sleep)

    buckets: dict[str, list[dict[str, Any]]] = {}
    for threshold in args.thresholds:
        selected = [s.copy() for s in stocks if accepted(s, threshold, args.chip_threshold, args.require_chip)]
        selected.sort(key=lambda s: s["score"], reverse=True)
        buckets[str(int(threshold) if threshold.is_integer() else threshold)] = selected[: args.limit]

    if args.concepts:
        add_concepts(buckets, args.concept_limit, args.concept_sleep)

    return {
        "ok": True,
        "stale": False,
        "updated_at": now_iso(),
        "generated_at": now_iso(),
        "source": source,
        "total_count": len(stocks),
        "message": "success",
        "thresholds": args.thresholds,
        "limit": args.limit,
        "chip_threshold": args.chip_threshold,
        "require_chip": args.require_chip,
        "chip_stats": chip_stats,
        "buckets": buckets,
    }


def load_previous(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--thresholds", nargs="+", type=float, default=[10.0, 5.0, 2.0])
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--tencent-batch-size", type=int, default=60)
    parser.add_argument("--concepts", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--concept-limit", type=int, default=180)
    parser.add_argument("--concept-sleep", type=float, default=0.04)
    parser.add_argument("--chip-threshold", type=float, default=12.0)
    parser.add_argument("--chip-scan-limit", type=int, default=360)
    parser.add_argument("--chip-sleep", type=float, default=0.08)
    parser.add_argument("--require-chip", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    output = Path(args.output)
    try:
        payload = make_payload(args)
    except Exception as exc:
        previous = load_previous(output)
        if previous and previous.get("buckets"):
            previous["ok"] = True
            previous["stale"] = True
            previous["message"] = f"云端本次刷新未成功，当前显示最近一次成功数据。原因：{exc}"
            previous["generated_at"] = now_iso()
            payload = previous
        else:
            payload = {
                "ok": False,
                "updated_at": "",
                "generated_at": now_iso(),
                "source": "eastmoney",
                "total_count": 0,
                "message": f"更新失败：{exc}",
                "thresholds": args.thresholds,
                "limit": args.limit,
                "buckets": {"10": [], "5": [], "2": []},
            }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

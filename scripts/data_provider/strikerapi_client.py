"""REST client dry-run mặc định, contract pin và budget bảo thủ qua các lần chạy."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3

from dotenv import dotenv_values
import requests

from scripts.inference.common import ROOT,write_json

BASE_URL="https://mcp.strikerapi.com"
POC_DIR=ROOT/"outputs/provider_poc"
CONTRACT_PATH=Path(__file__).with_name("strikerapi_contract.json")
MAX_CREDITS=25


class POCError(ValueError):
    """Thông điệp cố định không chứa body/header/exception của transport."""
    def __init__(self,code,message,*,http_status=None):
        super().__init__(message);self.code=code;self.http_status=http_status
    def result(self):
        return dict(status="error",error=dict(code=self.code,message=str(self),http_status=self.http_status))


def need(condition,code,message):
    if not condition:raise POCError(code,message)


def utc_now():return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)


def digest(value):return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strip_schema(value):
    if isinstance(value,dict):return {k:strip_schema(v) for k,v in value.items() if k not in {"description","summary","$schema","title"}}
    if isinstance(value,list):return [strip_schema(v) for v in value]
    return value


def validate_shape(value,schema):
    """Subset JSON Schema thực sự có trong contract pin; không phải validator tổng quát."""
    types=schema.get("type",[]);types=[types] if isinstance(types,str) else types
    valid={"object":isinstance(value,dict),"array":isinstance(value,list),"string":isinstance(value,str),
        "number":type(value) in (float,int) and math.isfinite(value),"integer":type(value) is int,
        "boolean":type(value) is bool,"null":value is None}
    need(not types or any(valid.get(t,False) for t in types),"SCHEMA_MISMATCH","Response/request sai kiểu theo contract đã xác minh.")
    if "enum" in schema:need(value in schema["enum"],"SCHEMA_MISMATCH","Giá trị ngoài enum contract.")
    if type(value) in (int,float):
        need(math.isfinite(value) and ("minimum" not in schema or value>=schema["minimum"])
             and ("maximum" not in schema or value<=schema["maximum"]),"SCHEMA_MISMATCH","Giá trị ngoài khoảng contract.")
    if isinstance(value,dict):
        props=schema.get("properties",{})
        need(set(schema.get("required",[])).issubset(value),"SCHEMA_MISMATCH","Thiếu trường bắt buộc trong contract.")
        if schema.get("additionalProperties") is False:
            need(set(value).issubset(props),"SCHEMA_MISMATCH","Có trường mới ngoài contract; dừng để review schema drift.")
        for key,item in value.items():
            if key in props:validate_shape(item,props[key])
    if isinstance(value,list) and "items" in schema:
        for item in value:validate_shape(item,schema["items"])


def load_credentials(root=ROOT):
    # Không override môi trường, không interpolate, không ghi .env hoặc đưa key vào repr/log.
    path=Path(root)/".env"
    values=dotenv_values(path,interpolate=False) if path.is_file() else {}
    key=os.environ.get("STRIKERAPI_API_KEY",values.get("STRIKERAPI_API_KEY"))
    if not isinstance(key,str) or not key.strip() or key.strip() in {"YOUR_REAL_API_KEY","YOUR_API_KEY"}:return None
    need(not any(c in key for c in "\r\n"),"INVALID_CREDENTIAL_FORMAT","Credential không hợp lệ; không hiển thị giá trị.")
    return key.strip()


def sanitize(value,key=None):
    sensitive=re.compile(r"api.?key|authorization|cookie|access.?token|secret|credential",re.I)
    if isinstance(value,dict):return {k:sanitize(v,key) for k,v in value.items() if not sensitive.search(k)}
    if isinstance(value,list):return [sanitize(v,key) for v in value]
    if isinstance(value,str):
        value=value.replace(key,"[REDACTED]") if key else value
        return re.sub(r"https?://[^\s\"<>]*[?&](?:key|token|api_key)=[^\s\"<>]*","[REDACTED_URL]",value,flags=re.I)
    return value


def safe_credit_headers(headers):
    # Không dump tất cả HTTP headers; chưa suy đoán semantics của tên header mới.
    return {name.lower():str(value) for name,value in headers.items()
        if re.fullmatch(r"[a-zA-Z0-9-]+",name) and "credit" in name.lower()
        and re.fullmatch(r"-?\d+(?:\.\d+)?",str(value))}


class StrikerAPIClient:
    def __init__(self,*,execute=False,max_credits=MAX_CREDITS,root=ROOT,output_dir=POC_DIR,session=None,logger=None):
        need(type(max_credits) is int and 0<=max_credits<=MAX_CREDITS,"INVALID_BUDGET","PoC giới hạn budget từ 0 đến 25 credits.")
        self.execute=bool(execute);self.max_credits=max_credits;self.root=Path(root);self.output_dir=Path(output_dir)
        self.contract=json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.session=requests.Session() if session is None else session
        self.logger=logger if logger is not None else self._display_plan
        self._key=None;self._verified=False;self.public_schema_gets=0;self.billable_posts=0
        self.request_history=[]

    def __repr__(self):return f"StrikerAPIClient(execute={self.execute},max_credits={self.max_credits})"

    @staticmethod
    def _display_plan(event):
        import sys
        print(json.dumps(event,ensure_ascii=True),file=sys.stderr,flush=True)

    @property
    def ledger_path(self):return self.output_dir/"raw/credit_ledger.sqlite3"

    def _connection(self):
        self.ledger_path.parent.mkdir(parents=True,exist_ok=True)
        con=sqlite3.connect(self.ledger_path)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS requests (fingerprint TEXT PRIMARY KEY, tool TEXT, cost INTEGER, status TEXT, fetched_at TEXT, http_status INTEGER, credit_headers TEXT)")
            con.commit();return con
        except Exception:
            con.close()  # Ledger hỏng cũng phải nhả handle Windows trước khi raise.
            raise

    def spent(self):
        if not self.ledger_path.exists():return 0
        try:
            with closing(self._connection()) as con:return int(con.execute("SELECT COALESCE(SUM(cost),0) FROM requests").fetchone()[0])
        except (sqlite3.Error,OSError):
            raise POCError("BUDGET_UNVERIFIABLE","Không đọc được credit ledger; dừng trước mọi request trả phí.") from None

    def verify_public_contract(self):
        need(self.execute,"DRY_RUN","Không đọc mạng trong dry-run.")
        try:
            documents=[]
            for path in ("/v1/tools","/openapi.json"):
                response=self.session.get(BASE_URL+path,timeout=(10,30),allow_redirects=False)
                self.public_schema_gets+=1
                need(response.status_code==200,"PUBLIC_SCHEMA_UNAVAILABLE","Không đọc được schema công khai; chưa gọi endpoint tính phí.")
                documents.append(response.json())
            tools,api=documents
            need(tools.get("base_url")==BASE_URL,"SCHEMA_DRIFT","Base URL catalogue khác contract pin.")
            by_name={t["name"]:t for t in tools["tools"]}
            for name,pinned in self.contract["tools"].items():
                live=by_name[name];post=api["paths"]["/v1/"+name]["post"]
                need(live["credits"]==post["x-credits"]==pinned["credits"]
                     and strip_schema(live["input_schema"])==pinned["request"]
                     and strip_schema(post["requestBody"]["content"]["application/json"]["schema"])==pinned["request"]
                     and strip_schema(post["responses"]["200"]["content"]["application/json"]["schema"])==pinned["response"],
                     "SCHEMA_DRIFT","Schema hoặc credit cost thay đổi; dừng trước billable requests.")
            self._verified=True
        except POCError:raise
        except Exception:raise POCError("PUBLIC_SCHEMA_UNAVAILABLE","Không xác minh được catalogue/OpenAPI; không thực hiện billable request.") from None

    def _reserve(self,fingerprint,tool,cost):
        with closing(self._connection()) as con:
            with con:
                con.execute("BEGIN IMMEDIATE")
                need(con.execute("SELECT 1 FROM requests WHERE fingerprint=?",(fingerprint,)).fetchone() is None,
                     "PREVIOUS_ATTEMPT_UNRESOLVED","Request đã từng được thử nhưng không có cache hợp lệ; không tự retry hoặc chi thêm credits.")
                spent=int(con.execute("SELECT COALESCE(SUM(cost),0) FROM requests").fetchone()[0])
                need(spent+cost<=self.max_credits,"BUDGET_EXCEEDED","Request vượt cumulative credit budget của PoC.")
                con.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?)",(fingerprint,tool,cost,"reserved",utc_now(),None,"{}"))
        return spent+cost

    def _record(self,fingerprint,status,http_status=None,credit_headers=None):
        with closing(self._connection()) as con,con:
            con.execute("UPDATE requests SET status=?,http_status=?,credit_headers=? WHERE fingerprint=?",
                (status,http_status,canonical(credit_headers or {}),fingerprint))

    def call(self,tool,params):
        need(tool in self.contract["tools"],"UNSUPPORTED_ENDPOINT","Endpoint chưa được duyệt trong PoC.")
        need(isinstance(params,dict) and params.get("league")=="laliga","INVALID_LEAGUE","Mọi request phải khai báo league=laliga.")
        spec=self.contract["tools"][tool]
        validate_shape(params,spec["request"])
        fingerprint=digest(dict(tool=tool,params=params));cache=self.output_dir/"raw"/(fingerprint+".json")
        if cache.is_file():
            try:
                record=json.loads(cache.read_text(encoding="utf-8"))
                need(record["tool"]==tool and record["params"]==params and record["data_sha256"]==digest(record["data"]),
                     "CACHE_CORRUPT","Cache không khớp request/hash; không tự gọi lại API.")
                validate_shape({"data":record["data"]},spec["response"])
                result=dict(record,cache_hit=True)
                self.request_history.append({key:result[key] for key in ("tool","params","http_status","credit_headers","documented_credits","cache_hit","fetched_at","data_sha256")})
                return result
            except POCError:raise
            except Exception:raise POCError("CACHE_CORRUPT","Không đọc được cache; không tự gọi lại API.") from None
        cost=spec["credits"];spent=self.spent()
        plan=dict(endpoint="POST /v1/"+tool,documented_credits=cost,cumulative_reserved_credits=spent,
                  estimated_cumulative_after=spent+cost,max_credits=self.max_credits,execute=self.execute)
        self.logger(plan)
        need(spent+cost<=self.max_credits,"BUDGET_EXCEEDED","Request vượt credit budget.")
        if not self.execute:return dict(status="dry_run",plan=plan,params=params)
        self._key=load_credentials(self.root)
        need(self._key is not None,"MISSING_CREDENTIAL","Chưa có STRIKERAPI_API_KEY hợp lệ; không hiển thị credential.")
        if not self._verified:self.verify_public_contract()
        cumulative=self._reserve(fingerprint,tool,cost)
        status=None;credits={}
        try:
            self.billable_posts+=1
            response=self.session.post(BASE_URL+"/v1/"+tool,json=params,
                headers={"Content-Type":"application/json","x-api-key":self._key},timeout=(10,45),allow_redirects=False)
            status=response.status_code;credits=sanitize(safe_credit_headers(response.headers),self._key)
            if status!=200:
                codes={400:"PROVIDER_BAD_REQUEST",401:"PROVIDER_AUTH_FAILED",402:"PROVIDER_INSUFFICIENT_CREDITS",
                       403:"PROVIDER_FORBIDDEN",429:"PROVIDER_RATE_LIMIT"}
                code=codes.get(status,"PROVIDER_SERVER_ERROR" if status>=500 else "PROVIDER_HTTP_ERROR")
                raise POCError(code,"Provider trả lỗi HTTP; không retry, không ghi body hoặc auth headers.",http_status=status)
            try:envelope=response.json()
            except Exception:raise POCError("INVALID_JSON","Provider trả JSON không hợp lệ; không retry.",http_status=status) from None
            validate_shape(envelope,spec["response"])
            data=sanitize(envelope["data"],self._key)
            record=dict(tool=tool,params=params,data=data,data_sha256=digest(data),fetched_at=utc_now(),
                http_status=status,credit_headers=credits,documented_credits=cost,cumulative_reserved_credits=cumulative)
            write_json(cache,record,exclusive=True)
            self._record(fingerprint,"cached",status,credits)
            result=dict(record,cache_hit=False)
            self.request_history.append({key:result[key] for key in ("tool","params","http_status","credit_headers","documented_credits","cache_hit","fetched_at","data_sha256")})
            return result
        except POCError:
            self._record(fingerprint,"failed_or_uncertain",status,credits)
            raise
        except Exception:
            self._record(fingerprint,"failed_or_uncertain",status,credits)
            raise POCError("TRANSPORT_ERROR","Request thất bại hoặc chưa rõ đã tính phí; giữ reservation và không tự retry.",http_status=status) from None


def run_cli(function):
    import sys
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8")
    try:result=function()
    except POCError as exc:result=exc.result()
    print(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2))
    return 2 if result.get("status")=="error" else 0

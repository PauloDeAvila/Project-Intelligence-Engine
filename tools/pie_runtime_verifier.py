"""Executed behavioral assertions for a fixed, synthetic mini-order fixture."""
from __future__ import annotations
from pathlib import Path
import os
import json
import subprocess
import sys

SCRIPT = """
import json
import sys
from decimal import Decimal
from mini_order import config
from mini_order.inventory import Inventory
from mini_order.payment import PaymentGateway
from mini_order.models import Order
import mini_order.service as service

scenario=sys.argv[1]
stock=Inventory({"A":2})
gateway=PaymentGateway(failures_before_success=99)
order=Order("A",1,Decimal("5"))
if scenario=="MAX_RETRIES":
    config.MAX_RETRIES=0
    try:
        service.OrderService(stock,gateway).checkout(order)
    except Exception as error:
        error_type=type(error).__name__
    else:
        error_type=None
    result={"attempts":gateway.calls,
            "additional_retries":max(0,gateway.calls-1),
            "rollback_on_payment_error":stock.stock["A"]==2,
            "error_type":error_type}
elif scenario=="release":
    del Inventory.release
    try:
        service.OrderService(stock,gateway).checkout(order)
    except Exception as error:
        error_type=type(error).__name__
        context_type=type(error.__context__).__name__ if error.__context__ else None
    else:
        error_type=context_type=None
    result={"error_type":error_type,
            "original_error_masked":error_type!="PaymentError" and context_type=="PaymentError",
            "stock_restored":stock.stock["A"]==2,
            "rollback_succeeds":error_type is None}
elif scenario=="charge_with_retry":
    service.charge_with_retry=lambda gateway,amount:None
    try:
        value=service.OrderService(stock,gateway).checkout(order)
        error_type=None
    except Exception as error:
        value="EXCEPTION"
        error_type=type(error).__name__
    result={"checkout_returns_none":value is None,
            "release_called":stock.stock["A"]==2,
            "stock_restored":stock.stock["A"]==2,
            "payment_error_propagates":error_type=="PaymentError"}
else:
    raise ValueError("Unexpected scenario")
print(json.dumps(result,sort_keys=True))
"""

def observe_case(root:Path,scenario:str)->dict:
    if scenario not in {"MAX_RETRIES","release","charge_with_retry"}:
        raise ValueError("Unknown scenario")
    source=Path(root).resolve()
    env={**os.environ,"PYTHONPATH":str(source)}
    p=subprocess.run([sys.executable,"-c",SCRIPT,scenario],cwd=source,env=env,
                     capture_output=True,text=True,timeout=15)
    if p.returncode:raise RuntimeError(f"Fixture validation failed: {p.returncode}")
    result=json.loads(p.stdout)
    if not isinstance(result,dict):raise RuntimeError("Invalid result")
    return result

from __future__ import annotations
import ast, hashlib, json, operator, time, uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from app.v11 import store

READ_ACTIONS={"web.search","files.read","calculator.run","github.read","project.read","memory.read"}
WRITE_ACTIONS={"files.write","files.delete","github.pr.create","github.branch.create","github.file.write","deploy.trigger","message.send","memory.write","schedule.create"}

def permission_level(action: str)->str:
    return "read" if action in READ_ACTIONS or action.endswith(".read") else "write"

def action_fingerprint(user_id: str, action: str, args: dict[str,Any])->str:
    raw=json.dumps({"user":user_id,"action":action,"args":args},sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()

async def grant_once(settings, *, user_id: str, action: str, args: dict[str,Any], expires_seconds: int=600)->dict[str,Any]:
    token=str(uuid.uuid4()); now=int(time.time())
    row={"id":token,"user_id":user_id,"action":action,"fingerprint":action_fingerprint(user_id,action,args),"expires_at_epoch":now+max(60,min(3600,expires_seconds)),"used":False}
    if store.configured(settings): await store.request(settings,"POST","v11_tool_permissions",json_body=row)
    return row

async def consume_permission(settings, *, user_id: str, action: str, args: dict[str,Any], token: str|None)->bool:
    if permission_level(action)=="read": return True
    if not token or not store.configured(settings): return False
    rows=await store.request(settings,"GET","v11_tool_permissions",params={"id":f"eq.{token}","user_id":f"eq.{user_id}","action":f"eq.{action}","used":"eq.false","select":"*"}) or []
    if not rows:return False
    row=rows[0]
    if int(row.get("expires_at_epoch") or 0)<int(time.time()):return False
    if str(row.get("fingerprint") or "")!=action_fingerprint(user_id,action,args):return False
    await store.request(settings,"PATCH","v11_tool_permissions",params={"id":f"eq.{token}"},json_body={"used":True})
    return True

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str,tuple[str,Callable[...,Awaitable[Any]]]]={}
    def register(self,name: str,level: str,fn: Callable[...,Awaitable[Any]])->None:
        self._tools[name]=(level,fn)
    def describe(self)->list[dict[str,str]]:
        return [{"name":name,"permission":level} for name,(level,_) in sorted(self._tools.items())]
    def level(self,name: str)->str:
        if name not in self._tools: raise KeyError(name)
        return self._tools[name][0]
    async def execute(self,name: str,**kwargs)->Any:
        if name not in self._tools: raise KeyError(name)
        return await self._tools[name][1](**kwargs)

TOOLS=ToolRegistry()

def registry_snapshot()->dict[str,Any]:
    return {"tools":TOOLS.describe(),"policy":{"read":"automatic","write_delete_send_deploy":"explicit one-time authorization"}}


_BINOPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.FloorDiv:operator.floordiv,ast.Mod:operator.mod,ast.Pow:operator.pow}
_UNARY={ast.UAdd:operator.pos,ast.USub:operator.neg}

def safe_calculate(expression: str)->float|int:
    tree=ast.parse(expression,mode="eval")
    def walk(node):
        if isinstance(node,ast.Expression):return walk(node.body)
        if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):return node.value
        if isinstance(node,ast.BinOp) and type(node.op) in _BINOPS:
            left,right=walk(node.left),walk(node.right)
            if type(node.op) is ast.Pow and abs(right)>12: raise ValueError("Exponent too large.")
            return _BINOPS[type(node.op)](left,right)
        if isinstance(node,ast.UnaryOp) and type(node.op) in _UNARY:return _UNARY[type(node.op)](walk(node.operand))
        raise ValueError("Only basic numeric arithmetic is allowed.")
    value=walk(tree)
    if isinstance(value,float) and (value!=value or abs(value)==float("inf")): raise ValueError("Non-finite result.")
    return value

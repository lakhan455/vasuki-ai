from __future__ import annotations
import ast, hashlib, json, re, uuid
from dataclasses import dataclass
from typing import Any
from app.services.chat_v10 import route_chat_v10

@dataclass(slots=True)
class Graph:
    nodes: list[dict[str,Any]]
    edges: list[dict[str,Any]]

def _lang(path: str) -> str:
    suffix=path.lower().rsplit(".",1)[-1] if "." in path else ""
    return {"py":"python","js":"javascript","jsx":"javascript","ts":"typescript","tsx":"typescript","sql":"sql","html":"html","css":"css"}.get(suffix,suffix or "text")

def build_knowledge_graph(files: dict[str,str]) -> Graph:
    nodes=[]; edges=[]; seen=set()
    def add_node(kind,name,path,meta=None):
        key=(kind,name,path)
        if key in seen:return
        seen.add(key); nodes.append({"id":hashlib.sha1("|".join(key).encode()).hexdigest()[:16],"kind":kind,"name":name,"path":path,"meta":meta or {}})
    for path,content in files.items():
        add_node("file",path,path,{"language":_lang(path),"chars":len(content)})
        if path.endswith(".py"):
            try:
                tree=ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                        add_node("function",node.name,path,{"line":node.lineno})
                    elif isinstance(node,ast.ClassDef):
                        add_node("class",node.name,path,{"line":node.lineno})
                    elif isinstance(node,(ast.Import,ast.ImportFrom)):
                        names=[a.name for a in node.names]
                        for name in names: edges.append({"from":path,"to":name,"type":"imports"})
            except SyntaxError:
                pass
        else:
            for m in re.finditer(r"\b(?:function|class|const|let|var|interface|type)\s+([A-Za-z_$][\w$]*)",content):
                add_node("symbol",m.group(1),path,{"offset":m.start()})
            for m in re.finditer(r"(?:from\s+|require\()\s*['\"]([^'\"]+)['\"]",content):
                edges.append({"from":path,"to":m.group(1),"type":"imports"})
        for m in re.finditer(r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]",content):
            add_node("api",f"{m.group(1).upper()} {m.group(2)}",path)
        for m in re.finditer(r"\b(?:from|join|update|into)\s+([A-Za-z_][A-Za-z0-9_]*)",content,re.I):
            if path.endswith(".sql"): add_node("db_table",m.group(1),path)
    return Graph(nodes,edges)

def syntax_check(path: str, code: str) -> dict[str,Any]:
    language=_lang(path)
    if language=="python":
        try:
            ast.parse(code)
            return {"ok":True,"language":"python","errors":[]}
        except SyntaxError as exc:
            return {"ok":False,"language":"python","errors":[{"line":exc.lineno,"offset":exc.offset,"message":exc.msg}]}
    # Server intentionally does not execute untrusted JS. Browser sandbox handles JS runtime.
    pairs={"(":")","[":"]","{":"}"}
    stack=[]; quote=None; escape=False
    for ch in code:
        if quote:
            if escape: escape=False
            elif ch=="\\": escape=True
            elif ch==quote: quote=None
            continue
        if ch in "'\"`": quote=ch
        elif ch in pairs: stack.append(pairs[ch])
        elif ch in pairs.values():
            if not stack or stack.pop()!=ch:return {"ok":False,"language":language,"errors":[{"message":"Unbalanced delimiter"}]}
    return {"ok":not stack and quote is None,"language":language,"errors":[] if not stack and quote is None else [{"message":"Unclosed delimiter or string"}]}

def extract_files_from_answer(answer: str) -> dict[str,str]:
    files={}
    pattern=re.compile(r"```([A-Za-z0-9_+#.-]*)\s*(?:file=([^\n]+))?\n([\s\S]*?)```")
    for index,m in enumerate(pattern.finditer(answer or ""),1):
        lang=(m.group(1) or "txt").lower(); named=(m.group(2) or "").strip()
        ext={"python":"py","py":"py","javascript":"js","js":"js","typescript":"ts","ts":"ts","tsx":"tsx","jsx":"jsx","html":"html","css":"css","sql":"sql"}.get(lang,"txt")
        path=named or f"generated_{index}.{ext}"
        files[path]=m.group(3).rstrip()
    return files

async def analyze_plan_patch(instruction: str, files: dict[str,str], settings) -> dict[str,Any]:
    graph=build_knowledge_graph(files)
    inventory="\n".join(f"--- {p} ---\n{c[:14000]}" for p,c in list(files.items())[:30])
    prompt=f"""You are Vasuki Autonomous Coding Agent V2.
Perform ANALYZE -> PLAN -> PATCH. Do not execute commands.
Instruction: {instruction}
Project graph summary: {len(graph.nodes)} nodes, {len(graph.edges)} edges.
Files:
{inventory}

Return:
1) short analysis
2) numbered plan
3) complete replacement code for every changed file, each fenced exactly as:
```language file=relative/path
...
```
Do not use ellipses or TODO placeholders."""
    answer,provider=await route_chat_v10("auto",[{"role":"user","content":prompt}],settings,"")
    proposed=extract_files_from_answer(answer)
    checks={path:syntax_check(path,code) for path,code in proposed.items()}
    return {"analysis":answer,"provider":provider,"files":proposed,"checks":checks,"graph":{"nodes":graph.nodes,"edges":graph.edges}}

async def repair_loop(instruction: str, original_files: dict[str,str], settings, *, max_attempts: int=3, external_test_errors: str="") -> dict[str,Any]:
    current=dict(original_files); attempts=[]
    error_text=external_test_errors.strip()
    for attempt in range(1,max(1,min(5,max_attempts))+1):
        request=instruction if attempt==1 else f"{instruction}\nRepair attempt {attempt}. Previous validation/test errors:\n{error_text}"
        result=await analyze_plan_patch(request,current,settings)
        current.update(result["files"])
        failed={p:v for p,v in result["checks"].items() if not v.get("ok")}
        attempts.append({"attempt":attempt,"provider":result["provider"],"checks":result["checks"],"changed_files":list(result["files"])})
        if not failed and not error_text:
            return {"ok":True,"attempts":attempts,"files":current,"last":result}
        error_text=json.dumps(failed,ensure_ascii=False) if failed else ""
    return {"ok":not bool(error_text),"attempts":attempts,"files":current,"last":attempts[-1] if attempts else None}

def sandbox_policy() -> dict[str,Any]:
    return {
        "server_execution":False,
        "reason":"Arbitrary generated code is never executed inside the FastAPI/Render process.",
        "javascript":{"mode":"browser sandboxed iframe/Web Worker","network":"browser-origin policy applies"},
        "python":{"mode":"browser Pyodide Web Worker","timeout_supported":True,"server_filesystem_access":False},
    }

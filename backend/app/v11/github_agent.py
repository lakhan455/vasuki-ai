from __future__ import annotations
import re
from typing import Any
import httpx

API="https://api.github.com"

def configured(settings)->bool:
    return bool(str(getattr(settings,"v11_github_token","") or "").strip())

def _headers(settings)->dict[str,str]:
    token=str(getattr(settings,"v11_github_token","") or "").strip()
    return {"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}

def _repo(value: str)->tuple[str,str]:
    value=value.strip().strip("/")
    value=re.sub(r"^https?://github\.com/","",value)
    parts=value.split("/")
    if len(parts)<2: raise ValueError("Repository must be owner/name.")
    return parts[0],parts[1]

async def request(settings, method: str, path: str, *, json_body: Any=None, params: dict[str,Any]|None=None)->Any:
    if not configured(settings): raise RuntimeError("V11 GitHub integration is not configured.")
    async with httpx.AsyncClient(timeout=25.0) as client:
        r=await client.request(method,f"{API}{path}",headers=_headers(settings),json=json_body,params=params)
    if r.status_code>=400: raise RuntimeError(f"GitHub API {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else None

async def read_repo_file(settings, repo: str, path: str, ref: str="main")->dict[str,Any]:
    owner,name=_repo(repo)
    return await request(settings,"GET",f"/repos/{owner}/{name}/contents/{path}",params={"ref":ref})

async def issue(settings, repo: str, number: int)->dict[str,Any]:
    owner,name=_repo(repo)
    return await request(settings,"GET",f"/repos/{owner}/{name}/issues/{number}")

async def compare(settings, repo: str, base: str, head: str)->dict[str,Any]:
    owner,name=_repo(repo)
    return await request(settings,"GET",f"/repos/{owner}/{name}/compare/{base}...{head}")

async def create_pr(settings, repo: str, *, title: str, head: str, base: str, body: str)->dict[str,Any]:
    owner,name=_repo(repo)
    return await request(settings,"POST",f"/repos/{owner}/{name}/pulls",json_body={"title":title,"head":head,"base":base,"body":body})


async def create_branch(settings, repo: str, *, branch: str, from_ref: str="main")->dict[str,Any]:
    owner,name=_repo(repo)
    ref=await request(settings,"GET",f"/repos/{owner}/{name}/git/ref/heads/{from_ref}")
    sha=str(ref.get("object",{}).get("sha") or "")
    if not sha: raise RuntimeError("Could not resolve base branch SHA.")
    return await request(settings,"POST",f"/repos/{owner}/{name}/git/refs",json_body={"ref":f"refs/heads/{branch}","sha":sha})

async def put_file(settings, repo: str, *, path: str, content_b64: str, message: str, branch: str, sha: str|None=None)->dict[str,Any]:
    owner,name=_repo(repo)
    payload={"message":message,"content":content_b64,"branch":branch}
    if sha: payload["sha"]=sha
    return await request(settings,"PUT",f"/repos/{owner}/{name}/contents/{path}",json_body=payload)

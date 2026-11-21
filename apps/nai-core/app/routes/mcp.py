"""
nAI Core MCP Server
Model Context Protocol endpoint so AI assistants (Claude Desktop/Code, other MCP clients)
can search and read the files nAI has indexed, with the calling user's access rights.

Transport: Streamable HTTP at ``/mcp``, stateless, JSON responses (no server-initiated
streams, so ``GET /mcp`` returns 405). Authenticate with ``Authorization: Bearer <API key>``.

Tools (all read-only): ``search_files``, ``read_document``, ``list_sources``.
"""

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from ..config import Settings, get_config
from ..models.schemas import User
from ..security import get_scope, require_auth
from ..services.access import AccessScope
from ..services.indexer import IndexerService, get_indexer
from ..services.retriever import RetrieverService, get_retriever
from ..services.sources import SourceService, get_source_service
from ..utils.logging import get_logger

router = APIRouter(tags=["MCP"])
logger = get_logger(__name__)

SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
LATEST_VERSION = SUPPORTED_VERSIONS[0]
READ_LIMIT = 20_000  # default max characters returned by read_document

INSTRUCTIONS = (
    "nAI indexes the files on the user's NAS (documents, scans, notes, code). Use search_files to find "
    "passages (keyword + semantic, multilingual), then read_document with a doc_id for the full text. "
    "Cite files by their path and page."
)

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_files",
        "title": "Search files",
        "description": (
            "Search the user's NAS files by keywords or meaning (works across languages). Returns the best "
            "matching passages with file path, page, section and doc_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for, in natural language or keywords",
                },
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                "source": {
                    "type": "string",
                    "description": "Only search this source (folder) name, as listed by list_sources",
                },
            },
            "required": ["query"],
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "read_document",
        "title": "Read document",
        "description": "Read the extracted text of a file found by search_files (optionally one page).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "doc_id from search_files"},
                "page": {"type": "integer", "minimum": 1, "description": "Only this page (PDFs)"},
                "max_chars": {"type": "integer", "minimum": 500, "maximum": 100_000, "default": READ_LIMIT},
            },
            "required": ["doc_id"],
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "list_sources",
        "title": "List sources",
        "description": "List the folders (sources) the user can search, with file counts and last sync time.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": READ_ONLY,
    },
]


class ToolError(Exception):
    """A tool failed in a way the model should see (returned with isError: true)."""


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _location(source_name: str | None, path: str, filename: str | None, page: Any, heading: Any) -> str:
    where = f"{source_name}/{path}" if source_name else (filename or path)
    if page is not None:
        where += f", page {page}"
    if heading:
        where += f", section '{heading}'"
    return where


class McpTools:
    def __init__(
        self,
        scope: AccessScope,
        retriever: RetrieverService,
        indexer: IndexerService,
        sources: SourceService,
    ):
        self.scope = scope
        self.retriever = retriever
        self.indexer = indexer
        self.sources = sources

    def _source_scope(self, name: str | None) -> AccessScope:
        if not name:
            return self.scope
        for s in self.sources.list_sources(include_paths=False):
            if s.name.lower() == name.strip().lower() and self.scope.allows(s.id):
                return self.scope.narrow([s.id], include_uploads=False)
        raise ToolError(f"Unknown source '{name}'. Call list_sources to see the available names.")

    def search_files(self, query: str, top_k: int = 8, source: str | None = None) -> str:
        if not query.strip():
            raise ToolError("query must not be empty")
        top_k = max(1, min(int(top_k), 20))
        results, method = self.retriever.search(query, top_k, "auto", self._source_scope(source))
        if not results:
            return f"No matching passages for: {query}"
        lines = [f"{len(results)} passages ({method} search):", ""]
        for i, r in enumerate(results, 1):
            snippet = " ".join(r.text.split())
            if len(snippet) > 700:
                snippet = snippet[:700] + "…"
            lines.append(f"[{i}] {_location(r.source_name, r.doc_path, r.filename, r.page, r.heading)}")
            lines.append(f"    doc_id: {r.doc_id}")
            lines.append(f"    {snippet}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def read_document(self, doc_id: str, page: int | None = None, max_chars: int = READ_LIMIT) -> str:
        doc = self.indexer.get_document(doc_id, self.scope)
        if doc is None:
            raise ToolError(f"No accessible document with doc_id '{doc_id}'")
        chunks = self.indexer.get_chunks(doc_id)
        if page is not None:
            chunks = [c for c in chunks if c["page"] == page]
            if not chunks:
                raise ToolError(f"Page {page} has no text (pages: {doc.metadata.get('pages', 'unknown')})")
        parts: list[str] = []
        current_page = None
        for c in chunks:
            if c["page"] is not None and c["page"] != current_page:
                current_page = c["page"]
                parts.append(f"\n[page {current_page}]")
            parts.append(c["text"])
        text = "\n".join(parts).strip()
        header = _location(doc.source_name, doc.path, doc.filename, page, None)
        limit = max(500, min(int(max_chars), 100_000))
        if len(text) > limit:
            text = (
                text[:limit] + f"\n\n[truncated at {limit} of {len(text)} characters; pass page or max_chars]"
            )
        return f"{header}\n\n{text}"

    def list_sources(self) -> str:
        visible = [s for s in self.sources.list_sources(include_paths=False) if self.scope.allows(s.id)]
        lines = [
            f"- {s.name}: {s.document_count} files, last synced {s.last_scan_finished or 'never'}"
            for s in visible
        ]
        if self.scope.uploads:
            lines.append("- (uploads): documents uploaded through nAI")
        return "Sources you can search:\n" + "\n".join(lines) if lines else "No sources available."

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        handlers: dict[str, Callable[..., str]] = {
            "search_files": self.search_files,
            "read_document": self.read_document,
            "list_sources": self.list_sources,
        }
        handler = handlers.get(name)
        if handler is None:
            raise RpcError(-32602, f"Unknown tool: {name}")
        try:
            return handler(**arguments)
        except TypeError as e:
            raise ToolError(f"Invalid arguments for {name}: {e}") from e


async def _handle(message: Any, tools: McpTools, settings: Settings) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Returns the response, or None for notifications."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
        if (
            isinstance(message, dict)
            and "method" not in message
            and ("result" in message or "error" in message)
        ):
            return None  # a response from the client (we never send requests): ignore
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}

    msg_id = message.get("id")
    method = message["method"]
    params = message.get("params") or {}
    is_notification = "id" not in message

    try:
        if method == "initialize":
            requested = params.get("protocolVersion")
            result: dict[str, Any] = {
                "protocolVersion": requested if requested in SUPPORTED_VERSIONS else LATEST_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "nai", "title": "nAI", "version": settings.app_version},
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise RpcError(-32602, "tools/call needs 'name' and an 'arguments' object")
            try:
                text = await run_in_threadpool(tools.call, name, arguments)
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            except ToolError as e:
                result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        elif method.startswith("notifications/"):
            return None
        else:
            raise RpcError(-32601, f"Method not found: {method}")
    except RpcError as e:
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": e.code, "message": e.message}}
    except Exception as e:  # never leak a 500 to the client for a tool bug
        logger.error(f"MCP {method} failed: {e}")
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": "Internal error"}}

    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _origin_allowed(request: Request, settings: Settings) -> bool:
    """Reject cross-site browser requests (DNS-rebinding protection required by the MCP spec)."""
    origin = request.headers.get("origin")
    if not origin or settings.cors_allow_all:
        return True
    if origin in settings.cors_origins:
        return True
    host = request.headers.get("host", "")
    return origin.split("://", 1)[-1] == host


@router.post("/mcp", response_model=None)
async def mcp_endpoint(
    request: Request,
    _user: User = Depends(require_auth),
    scope: AccessScope = Depends(get_scope),
    settings: Settings = Depends(get_config),
    retriever: RetrieverService = Depends(get_retriever),
    indexer: IndexerService = Depends(get_indexer),
    sources: SourceService = Depends(get_source_service),
) -> Response:
    """MCP Streamable HTTP endpoint (JSON-RPC 2.0)."""
    if not _origin_allowed(request, settings):
        return JSONResponse({"error": "Origin not allowed"}, status_code=403)
    version = request.headers.get("mcp-protocol-version")
    if version and version not in SUPPORTED_VERSIONS:
        return JSONResponse({"error": f"Unsupported MCP-Protocol-Version: {version}"}, status_code=400)

    try:
        payload = json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    tools = McpTools(scope, retriever, indexer, sources)
    if isinstance(payload, list):  # JSON-RPC batch (protocol 2025-03-26)
        responses = [r for r in [await _handle(m, tools, settings) for m in payload] if r is not None]
        return JSONResponse(responses) if responses else Response(status_code=202)
    response = await _handle(payload, tools, settings)
    return JSONResponse(response) if response is not None else Response(status_code=202)


@router.get("/mcp")
@router.delete("/mcp")
def mcp_no_stream() -> Response:
    """This server is stateless and never pushes messages: no SSE stream, no sessions."""
    return Response(status_code=405, headers={"Allow": "POST"})

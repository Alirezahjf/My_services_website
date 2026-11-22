import asyncio
import json
import os
import socket
import subprocess
import sys
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.extensions import db
from app.models import AgentConnection
from app.services.agent_service import issue_token


def test_official_mcp_client_initialize_list_call_and_approval(app, tmp_path):
    with app.app_context():
        agent = AgentConnection(name="Protocol test", permissions=["products.read", "pages.read", "pages.create", "pages.publish"], rate_limit_per_minute=100)
        token = issue_token(agent)
        db.session.add(agent)
        db.session.commit()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    env = os.environ.copy()
    env["DATABASE_URL"] = app.config["SQLALCHEMY_DATABASE_URI"]
    env["SECRET_KEY"] = "test-secret"
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "mcp_server:asgi_app", "--host", "127.0.0.1", "--port", str(port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # The server needs a moment to come up. Waiting for the port to
        # accept a connection is not enough on a busy machine: the
        # connection can be refused while the application is still being
        # set up, and the client then gives up with a connection error
        # that says nothing about the cause.
        ready = False
        for _ in range(300):
            if process.poll() is not None:
                raise AssertionError("MCP server exited before accepting the official client")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=.5).close()
                ready = True
                break
            except OSError:
                time.sleep(.1)
        assert ready, "the MCP server did not start in time"
        async def verify():
            async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp", headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
                async with ClientSession(read, write) as session:
                    info = await session.initialize()
                    assert info.serverInfo.name == "HJF Website Manager"
                    tools = await session.list_tools()
                    from app.services.agent_service import TOOLS
                    assert len(tools.tools) == len(TOOLS) and len(tools.tools) >= 43
                    created = await session.call_tool("create_page", {"slug": "mcp/protocol", "title": "Protocol", "heading": "Verified", "html_content": "<p>Safe</p><script>bad()</script>"})
                    page = json.loads(created.content[0].text)["result"]
                    assert not created.isError and page.get("status") == "draft" and "script" not in page.get("html_content", ""), page
                    resources = await session.list_resources()
                    assert any(str(item.uri).startswith("hjf://products/") for item in resources.resources)
                    product_resource = await session.read_resource(resources.resources[0].uri)
                    assert "title" in product_resource.contents[0].text
                    page_uri = next(item.uri for item in resources.resources if str(item.uri).startswith("hjf://pages/"))
                    page_resource = await session.read_resource(page_uri)
                    assert "title" in page_resource.contents[0].text
                    prompts = await session.list_prompts()
                    assert {item.name for item in prompts.prompts} >= {"summarize_product", "audit_product", "generate_black_friday_card"}
                    prompt = await session.get_prompt("summarize_product", {"product_id": "1"})
                    assert prompt.messages and "Persian" in prompt.messages[0].content.text
                    pending = json.loads((await session.call_tool("publish_page", {"page_id": page["id"]})).content[0].text)
                    assert pending["pending_approval"] is True
                    denied = await session.call_tool("delete_product", {"product_id": 1})
                    assert denied.isError and "permission_denied" in denied.content[0].text
        asyncio.run(verify())
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

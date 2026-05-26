import sys
import json
import subprocess
import shlex

def main():
    # Read stdin line by line (MCP stdio transport)
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "initialize":
            respond(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "windows-shell-mcp",
                    "version": "1.0.0"
                }
            })
        elif method == "tools/list":
            respond(msg_id, {
                "tools": [
                    {
                        "name": "run",
                        "description": "Execute a shell command on Windows host",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "Shell command to execute"
                                },
                                "cwd": {
                                    "type": "string",
                                    "description": "Working directory (optional)"
                                },
                                "timeout": {
                                    "type": "integer",
                                    "description": "Timeout in seconds (default 30)"
                                }
                            },
                            "required": ["command"]
                        }
                    }
                ]
            })
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})

            if tool_name == "run":
                cmd = args.get("command", "")
                cwd = args.get("cwd", None)
                timeout = args.get("timeout", 30)

                try:
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        cwd=cwd,
                        timeout=timeout
                    )
                    respond(msg_id, {
                        "content": [
                            {
                                "type": "text",
                                "text": result.stdout + (("\n--- STDERR ---\n" + result.stderr) if result.stderr else "")
                            }
                        ]
                    }, is_error=result.returncode != 0)
                except subprocess.TimeoutExpired:
                    respond(msg_id, {
                        "content": [{"type": "text", "text": f"Command timed out after {timeout}s"}]
                    }, is_error=True)
                except Exception as e:
                    respond(msg_id, {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}]
                    }, is_error=True)
            else:
                respond(msg_id, {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]
                }, is_error=True)
        elif method == "notifications/initialized":
            pass  # No response needed
        else:
            respond(msg_id, {
                "content": [{"type": "text", "text": f"Unknown method: {method}"}]
            }, is_error=True)

def respond(msg_id, result, is_error=False):
    response = {
        "jsonrpc": "2.0",
        "id": msg_id
    }
    if is_error:
        response["error"] = {
            "code": -32000,
            "message": "Execution error",
            "data": result
        }
    else:
        response["result"] = result
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main()

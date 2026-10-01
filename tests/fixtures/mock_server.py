"""Lightweight Mock OpenAI Server for End-to-End Testing."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

TRANSLATION_MAP = {
    "Start New Game": "开始新游戏",
    "Load Saved Game": "加载存档",
    "Settings & Options": "设置与选项",
    "Exit to Desktop": "退出到桌面",
    "Hero %s has reached Level %d!": "英雄 %s 已达到等级 %d！",
    "You opened the ancient chest and acquired ${gold_amount} Gold and {{item_name}}!": "你打开了古老的宝箱，获得了 ${gold_amount} 金币和 {{item_name}}！",
    "Welcome back, {player_name}! You have {quest_count} active quests.": "欢迎回来，{player_name}！你当前有 {quest_count} 个进行中的任务。",
    'Click <a href="%s">here</a> to read the latest patch notes.': '点击<a href="%s">此处</a>阅读最新补丁说明。',
    "Safe travels, adventurer!": "祝你一路顺风，冒险家！",
    "Until we meet again under the stars.": "愿我们在群星之下再次相逢。",
    "Critical Hit! Dealt %d damage to [ENEMY].": "暴击！对 [ENEMY] 造成了 %d 点伤害。",
}


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class MockOpenAIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet logger
        pass

    def do_GET(self):
        if self.path.endswith("/models"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": "gpt-4o"}]}).encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path.endswith("/shutdown"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "shutting down"}')
            threading_shutdown = getattr(self.server, "shutdown", None)
            if threading_shutdown:
                import threading
                threading.Thread(target=self.server.shutdown).start()
            return

        if self.path.endswith("/chat/completions"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            data = json.loads(body)
            messages = data.get("messages", [])

            # Extract user message payload
            user_msg = messages[-1]["content"] if messages else "[]"
            try:
                parsed_msg = json.loads(user_msg)
                if isinstance(parsed_msg, dict):
                    items = parsed_msg.get("entries", [])
                elif isinstance(parsed_msg, list):
                    items = parsed_msg
                else:
                    items = []
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                items = []

            results = []
            for item in items:
                item_id = item.get("id")
                source = item.get("text", "") or item.get("source", "")
                trans = TRANSLATION_MAP.get(source)
                if not trans:
                    trans = f"[译] {source}"
                results.append({"id": item_id, "translation": trans})

            response_payload = {
                "id": "chatcmpl-mock-12345",
                "object": "chat.completion",
                "created": 1700000000,
                "model": data.get("model", "gpt-4o"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"translations": results}, ensure_ascii=False),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 50,
                    "total_tokens": 100,
                },
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(response_payload, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def run(port: int = 8999):
    server = ThreadedHTTPServer(("127.0.0.1", port), MockOpenAIHandler)
    print(f"Mock OpenAI server running on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8999
    run(port)

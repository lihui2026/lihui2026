import configparser
import sys
import json

try:
    import requests
except ImportError:
    print("缺少 requests，请先安装：pip install requests")
    sys.exit(1)

def main():
    cfg = configparser.ConfigParser()
    cfg.read("config.ini", encoding="utf-8")
    
    llm = cfg["LLM"]
    base_url = llm.get("base_url", "").rstrip("/")
    model = llm.get("model", "")
    api_key = llm.get("api_key", "")
    
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    while True:
        try:
            user_input = input("输入问题：")
            if not user_input:
                continue
            data = {
                "model": model,
                "messages": [{"role": "user", "content": user_input}],
                "stream": True
            }
            resp = requests.post(url, headers=headers, json=data, timeout=60, stream=True)
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                        delta = chunk["choices"][0]["delta"]
                        if "content" in delta and delta["content"]:
                            print(delta["content"], end="", flush=True)
                    except:
                        pass
            print("\n")
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n错误：{e}\n")

if __name__ == "__main__":
    main()

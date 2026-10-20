import configparser
import sys

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
    user_input = input("输入问题：")
    data = {
        "model": model,
        "messages": [{"role": "user", "content": user_input}]
    }
    
    resp = requests.post(url, headers=headers, json=data, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    print(result["choices"][0]["message"]["content"])

if __name__ == "__main__":
    main()

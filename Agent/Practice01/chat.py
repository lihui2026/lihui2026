import configparser
import time

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8-sig")

client = OpenAI(
    api_key=config["llm"]["api_key"],
    base_url=config["llm"]["base_url"],
)

messages = []

while True:
    prompt = input("提示词: ")
    print("---")

    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=config["llm"]["model"],
        messages=messages,
        stream=True,
    )
    reply = ""
    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        for char in content:
            print(char, end="", flush=True)
            time.sleep(0.02)
        reply += content
    print()

    messages.append({"role": "assistant", "content": reply})

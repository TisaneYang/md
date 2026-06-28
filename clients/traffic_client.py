"""
交通指挥者客户端

发送自然语言指令到服务端
"""

import argparse
import requests


def send_command(server_url: str, command: str):
    """发送交通指挥指令到服务端"""
    url = f"{server_url}/traffic/command"

    response = requests.post(url, json={"command": command})

    if response.status_code == 200:
        payload = response.json()
        print("指令发送成功")
        print(f"- command: {payload.get('command')}")
        if payload.get("message"):
            print(f"- message: {payload.get('message')}")
    else:
        print(f"指令发送失败: {response.status_code} - {response.text}")

    return response


def main():
    parser = argparse.ArgumentParser(description='交通指挥者客户端')
    parser.add_argument('--server', default='http://localhost:5000', help='服务端地址')
    parser.add_argument('--command', required=True, help='交通指挥指令')

    args = parser.parse_args()
    send_command(args.server, args.command)


if __name__ == '__main__':
    main()

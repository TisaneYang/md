"""
测试定期触发功能

测试场景：
1. 启动定期分析
2. 检查定期分析状态
3. 更新配置
4. 停止定期分析
"""

import requests
import time

BASE_URL = "http://localhost:5000"


def test_periodic_status():
    """测试获取定期分析状态"""
    print("\n=== 测试1: 获取定期分析状态 ===")
    resp = requests.get(f"{BASE_URL}/periodic/status")
    print(f"状态码: {resp.status_code}")
    print(f"响应: {resp.json()}")
    return resp.json()


def test_start_periodic():
    """测试启动定期分析"""
    print("\n=== 测试2: 启动定期分析 ===")
    resp = requests.post(f"{BASE_URL}/periodic/start")
    print(f"状态码: {resp.status_code}")
    print(f"响应: {resp.json()}")
    return resp.json()


def test_stop_periodic():
    """测试停止定期分析"""
    print("\n=== 测试3: 停止定期分析 ===")
    resp = requests.post(f"{BASE_URL}/periodic/stop")
    print(f"状态码: {resp.status_code}")
    print(f"响应: {resp.json()}")
    return resp.json()


def test_update_config():
    """测试更新配置"""
    print("\n=== 测试4: 更新定期分析配置 ===")
    resp = requests.put(
        f"{BASE_URL}/periodic/config",
        params={"interval": 5, "skip_if_no_vehicle": False}
    )
    print(f"状态码: {resp.status_code}")
    print(f"响应: {resp.json()}")
    return resp.json()


def main():
    print("开始测试定期触发功能...")
    print(f"服务端地址: {BASE_URL}")

    try:
        # 测试1: 获取初始状态
        status = test_periodic_status()

        # 测试2: 启动定期分析
        test_start_periodic()
        time.sleep(1)

        # 检查状态
        status = test_periodic_status()
        assert status['enabled'], "定期分析应该已启动"
        print("✓ 定期分析已成功启动")

        # 等待几秒观察定期分析
        print("\n等待10秒观察定期分析...")
        time.sleep(10)

        # 测试3: 更新配置
        test_update_config()

        # 测试4: 停止定期分析
        test_stop_periodic()
        time.sleep(1)

        # 检查状态
        status = test_periodic_status()
        assert not status['enabled'], "定期分析应该已停止"
        print("✓ 定期分析已成功停止")

        print("\n所有测试通过！")

    except requests.exceptions.ConnectionError:
        print(f"\n错误: 无法连接到服务端 {BASE_URL}")
        print("请确保服务端正在运行: python server/main.py")
    except AssertionError as e:
        print(f"\n测试失败: {e}")
    except Exception as e:
        print(f"\n发生错误: {e}")


if __name__ == "__main__":
    main()

"""
路侧摄像头客户端

发送摄像头图片到服务端
"""

import argparse
import io
import requests
import numpy as np
import cv2


def send_image(server_url: str, camera_id: str, image_path: str):
    """发送图片到服务端"""
    url = f"{server_url}/camera/upload"

    with open(image_path, 'rb') as f:
        files = {'image': (image_path, f, 'image/jpeg')}
        data = {'camera_id': camera_id}

        response = requests.post(url, files=files, data=data)

    if response.status_code == 200:
        print(f"图片上传成功: {response.json()}")
    else:
        print(f"图片上传失败: {response.status_code} - {response.text}")

    return response


def send_image_array(server_url: str, camera_id: str, image_array: np.ndarray, format: str = 'jpeg'):
    """发送 ndarray 图片到服务端

    Args:
        server_url: 服务端地址
        camera_id: 摄像头ID
        image_array: numpy ndarray 格式的图片 (BGR 或 RGB)
        format: 图片编码格式，'jpeg' 或 'png'
    """
    url = f"{server_url}/camera/upload"

    # 将 ndarray 编码为图片字节流
    if format == 'jpeg':
        success, encoded = cv2.imencode('.jpg', image_array)
        content_type = 'image/jpeg'
        filename = 'image.jpg'
    else:
        success, encoded = cv2.imencode('.png', image_array)
        content_type = 'image/png'
        filename = 'image.png'

    if not success:
        raise ValueError("图片编码失败")

    # 创建字节流
    image_bytes = io.BytesIO(encoded.tobytes())

    files = {'image': (filename, image_bytes, content_type)}
    data = {'camera_id': camera_id}

    response = requests.post(url, files=files, data=data)

    if response.status_code == 200:
        print(f"图片上传成功: {response.json()}")
    else:
        print(f"图片上传失败: {response.status_code} - {response.text}")

    return response


def main():
    parser = argparse.ArgumentParser(description='路侧摄像头客户端')
    parser.add_argument('--server', default='http://localhost:5000', help='服务端地址')
    parser.add_argument('--camera', required=True, help='摄像头ID (如 camera_1)')
    parser.add_argument('--image', required=True, help='图片路径')

    args = parser.parse_args()
    send_image(args.server, args.camera, args.image)


if __name__ == '__main__':
    main()

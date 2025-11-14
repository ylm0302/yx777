import requests
import time
import re
import os
import subprocess

# CF 官方带宽测试端点 (10MB 随机数据)
TEST_URL = 'https://speed.cloudflare.com/__down?bytes=10485760'  # 10MB
HOST = 'speed.cloudflare.com'
PORT = 443
FILE_SIZE = 10485760  # 字节，用于验证

# 默认端口
DEFAULT_PORT = 8443

# 英文国家名到中文翻译字典 (扩展更多常见国家，包括特殊 fallback)
EN_TO_CN = {
    'United States': '美国',
    'Canada': '加拿大',
    'China': '中国',
    'United Kingdom': '英国',
    'Germany': '德国',
    'France': '法国',
    'Japan': '日本',
    'Australia': '澳大利亚',
    'India': '印度',
    'Brazil': '巴西',
    'Russia': '俄罗斯',
    'South Korea': '韩国',
    'Netherlands': '荷兰',
    'Singapore': '新加坡',
    'Hong Kong': '香港',
    'Taiwan': '台湾',
    'Reserved': '预留',
    'Global': '全球',
    'Unknown': '未知'
    # 可继续添加
}

def get_chinese_country(ip, max_retries=3):
    """查询 IP 国家，并返回中文名（优化：HTTPS、重试、调试日志）"""
    for attempt in range(max_retries):
        try:
            # 改用 HTTPS，更稳定
            url = f'https://ip-api.com/json/{ip}?fields=status,country'
            print(f"  查询 {ip} (尝试 {attempt+1})...")
            response = requests.get(url, timeout=10)  # 加大超时
            print(f"  Status: {response.status_code}, Text len: {len(response.text)}")  # 调试日志
            
            if response.status_code != 200:
                print(f"  HTTP {response.status_code} 错误")
                raise ValueError(f"HTTP {response.status_code}")
            
            data = response.json()
            if data['status'] == 'success':
                en_country = data.get('country', 'Unknown')
                cn_country = EN_TO_CN.get(en_country, en_country)  # fallback 原英文，避免全未知
                print(f"  国家: {en_country} -> {cn_country}")
                return cn_country
            else:
                print(f"  API fail: {data.get('message', 'Unknown')}")
                raise ValueError(data.get('message', 'API error'))
        except requests.exceptions.Timeout:
            print(f"  超时 (尝试 {attempt+1})")
        except requests.exceptions.ConnectionError as e:
            print(f"  连接失败 (尝试 {attempt+1}): {e}")
        except ValueError as e:
            print(f"  值错误: {e}")
        except Exception as e:  # 包括 JSON 错误
            print(f"  异常 (尝试 {attempt+1}): {e}")
            if 'Expecting value' in str(e) and len(response.text) == 0:
                print("  疑似空响应，可能是限速/网络")
        
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # 指数退避：1s, 2s, 4s，防限速
    
    print(f"  国家查询最终失败 {ip}")
    return '未知'  # 最终 fallback

def test_speed(ip, retries=1):
    """用 curl --resolve 测试 CF 带宽 (MB/s)，重试失败"""
    for attempt in range(retries + 1):
        cmd = [
            'curl', '-s',
            '--resolve', f'{HOST}:{PORT}:{ip}',
            TEST_URL,
            '-o', '/dev/null',
            '-w', 'speed_download:%{speed_download}\nsize:%{size_download}\n',
            '--max-time', '30',
            '--connect-timeout', '10',
            '--retry', '1',
            '--insecure'
        ]
        try:
            print(f" 测试 {ip}:443 (尝试 {attempt+1})...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            if result.returncode == 0:
                output = result.stdout.strip()
                speed_bps = 0
                downloaded = 0
                for line in output.split('\n'):
                    if line.startswith('speed_download:'):
                        speed_bps = float(line.split(':')[1])
                    elif line.startswith('size:'):
                        downloaded = float(line.split(':')[1])
                if downloaded >= FILE_SIZE * 0.9:
                    speed_mbps = speed_bps / 1048576
                    if speed_mbps > 0:
                        print(f" 成功！下载 {downloaded/1048576:.1f}MB, 速度: {round(speed_mbps, 1)}MB/s")
                        return round(speed_mbps, 1)
                print(f" 下载不完整 (code {result.returncode}): {output}")
                return 0.0
            else:
                print(f" curl 失败 (code {result.returncode}): {result.stderr.strip() if result.stderr else 'Timeout'}")
                if attempt < retries:
                    time.sleep(2)
                else:
                    return 0.0
        except subprocess.TimeoutExpired:
            print(f" curl 超时 (30s)")
            return 0.0
        except Exception as e:
            print(f" curl 异常: {e}")
            return 0.0
    return 0.0

def main():
    print("=== 脚本开始运行 ===")
    try:
        if not os.path.exists('ip.txt'):
            print("ip.txt 不存在！")
            return
        with open('ip.txt', 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#') and not line.startswith('-')]
        print(f"读取到 {len(lines)} 个 IP")
        if not lines:
            print("ip.txt 中无有效 IP！")
            return
        results = []
        failed_count = 0
        for line in lines:
            # 提取 IP 和可选端口 (格式: IP:PORT#US 或 IP#US)
            match = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::(\d+))?\s*#(.*)$', line)
            if not match:
                print(f"跳过无效行: {line}")
                continue
            ip = match.group(1)
            port = match.group(2) or str(DEFAULT_PORT)  # 优先自带端口，没有默认8443
            ip_port = f"{ip}:{port}"
            cn_country = get_chinese_country(ip)
            print(f"\n测试 {ip_port} - {cn_country}")
            speed = test_speed(ip)
            time.sleep(0.5)  # 加小延时，防 API 限速（查询+测速间隔）
            if speed > 0:
                result = f"{ip_port}#{cn_country} {speed}MB/s"  # 格式: IP:端口#国家 速率
                results.append(result)
                print(f" -> 成功: {result}")
            else:
                failed_count += 1
                print(f" -> 失败: 连接不通")
        # 写入 speed_ip.txt (纯列表，无头部，按速度降序)
        with open('speed_ip.txt', 'w', encoding='utf-8') as f:
            for res in sorted(results, key=lambda x: float(re.search(r'(\d+\.?\d*)MB/s', x).group(1)), reverse=True):
                f.write(res + '\n')
        print(f"\n完成！共 {len(results)} 个成功 IP 保存到 speed_ip.txt (失败 {failed_count} 个)")
    except Exception as e:
        print(f"脚本异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

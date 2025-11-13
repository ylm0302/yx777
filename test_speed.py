import requests
import time
import re
import os
import subprocess
import sys

# CF 官方带宽测试端点 (10MB 随机数据)
TEST_URL = 'https://speed.cloudflare.com/__down?bytes=10485760'  # 10MB
HOST = 'speed.cloudflare.com'
PORT = 443
FILE_SIZE = 10485760  # 字节，用于验证

def generate_flag_from_code(code):
    """根据 ISO alpha-2 代码动态生成国旗 Emoji"""
    if len(code) != 2 or not code.isalpha():
        return '❓'
    # Unicode 公式：A=1F1E6 (Regional Indicator A)
    flag = ''.join(chr(ord(c.upper()) - ord('A') + 0x1F1E6) for c in code)
    return flag

def get_country_flag(ip):
    """查询 IP 国家代码并生成国旗"""
    try:
        print(f"  查询 API for {ip}...", flush=True)
        response = requests.get(f'http://ip-api.com/json/{ip}?fields=status,countryCode', timeout=5)
        data = response.json()
        print(f"  API 返回: {data}", flush=True)
        if data['status'] == 'success':
            code = data.get('countryCode', '').strip()
            flag = generate_flag_from_code(code)
            country = data.get('country', 'Unknown')  # 需要加 country fields
            print(f"  代码: {code}, 国旗: {flag}, 国家: {country}", flush=True)
            return flag, country
        return '❓', 'Unknown'
    except Exception as e:
        print(f"  国家查询失败 {ip}: {e}", flush=True)
        return '❓', 'Unknown'

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
            print(f"  测试 {ip}:443 (尝试 {attempt+1})...", flush=True)
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
                        print(f"  成功！下载 {downloaded/1048576:.1f}MB, 速度: {round(speed_mbps, 1)}MB/s", flush=True)
                        return round(speed_mbps, 1)
                print(f"  下载不完整 (code {result.returncode}): {output}", flush=True)
                return 0.0
            else:
                print(f"  curl 失败 (code {result.returncode}): {result.stderr.strip() if result.stderr else 'Timeout'}", flush=True)
                if attempt < retries:
                    time.sleep(2)
                else:
                    return 0.0
        except subprocess.TimeoutExpired:
            print(f"  curl 超时 (30s)", flush=True)
            return 0.0
        except Exception as e:
            print(f"  curl 异常: {e}", flush=True)
            return 0.0
    return 0.0

def main():
    print("=== 脚本开始运行 ===", flush=True)
    try:
        print("检查 ip.txt...", flush=True)
        if not os.path.exists('ip.txt'):
            print("ERROR: ip.txt 不存在！", flush=True)
            return

        with open('ip.txt', 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#') and not line.startswith('-')]

        print(f"读取到 {len(lines)} 个 IP", flush=True)

        if not lines:
            print("ip.txt 中无有效 IP！", flush=True)
            return

        results = []
        failed_count = 0
        for line in lines:
            match = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::\d+)?\s*#(.*)$', line)
            if not match:
                print(f"跳过无效行: {line}", flush=True)
                continue
            ip = match.group(1)

            flag, country = get_country_flag(ip)
            print(f"\n测试 {ip} - 国家: {country} {flag}", flush=True)

            speed = test_speed(ip)
            time.sleep(1)

            if speed > 0:
                result = f"{ip}#{flag}+{speed}MB/s"
                results.append(result)
                print(f"  -> 成功: {result}", flush=True)
            else:
                failed_count += 1
                print(f"  -> 失败: 连接不通", flush=True)

        with open('speed_ip.txt', 'w', encoding='utf-8') as f:
            f.write('# IP 带宽测速结果 (动态国旗: IP#国旗+速率，所有成功 IP)\n')
            f.write('# 生成时间: ' + time.strftime('%Y-%m-%d %H:%M:%S UTC') + '\n')
            f.write(f'# 总测试: {len(lines)}, 成功: {len(results)}, 失败: {failed_count}\n\n')
            for res in sorted(results, key=lambda x: float(x.split('+')[1].replace('MB/s', '')), reverse=True):
                f.write(res + '\n')

        print(f"\n完成！共 {len(results)} 个成功 IP 保存到 speed_ip.txt (失败 {failed_count} 个)", flush=True)
        print("=== 脚本结束 ===", flush=True)
    except Exception as e:
        print(f"脚本异常: {e}", flush=True)
        import traceback
        traceback.print_exc(flush=True)

if __name__ == '__main__':
    main()

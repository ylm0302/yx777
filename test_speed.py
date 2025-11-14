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

# 国家映射：支持 code (US) 和 full name (United States)
EN_TO_CN = {
    # Codes
    'US': '美国',
    'CA': '加拿大',
    'CN': '中国',
    'GB': '英国',
    'DE': '德国',
    'FR': '法国',
    'JP': '日本',
    'AU': '澳大利亚',
    'IN': '印度',
    'BR': '巴西',
    'RU': '俄罗斯',
    'KR': '韩国',
    'NL': '荷兰',
    'SG': '新加坡',
    'HK': '香港',
    'TW': '台湾',
    # Full names (fallback)
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
}

# 浏览器 UA，绕检测
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

def get_chinese_country(ip, max_retries=1):
    """查询 IP 国家（新 API：IPinfo 主 + ipgeolocation 备用，只当主无信息时用备用）"""
    headers = {'User-Agent': USER_AGENT}
    for attempt in range(max_retries):
        try:
            # 主 API: IPinfo.io (免费 50k/月，高准，无 key)
            url = f'https://ipinfo.io/{ip}/country'
            print(f"  查询 {ip} (尝试 {attempt+1}, 主 API IPinfo)...")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"  Status: {response.status_code}, Text len: {len(response.text)}")
            print(f"  响应预览: {response.text[:50]}...")  # 调试
            
            if response.status_code == 200:
                en_country = response.text.strip()
                if en_country and en_country != 'Unknown':  # 有有效信息（非空、非Unknown）
                    cn_country = EN_TO_CN.get(en_country, en_country)
                    print(f"  国家: {en_country} -> {cn_country}")
                    return cn_country
                else:
                    print("  IPinfo 无有效归属地信息，尝试备用 API...")
                    # 只有主无信息时，才调用备用: ipgeolocation.io
                    backup_url = f'https://api.ipgeolocation.io/ipgeo?apiKey=demo&ip={ip}&fields=country_name'  # demo key 免费
                    backup_resp = requests.get(backup_url, headers=headers, timeout=10)
                    if backup_resp.status_code == 200:
                        data = backup_resp.json()
                        en_country_backup = data.get('country_name', 'Unknown')
                        if en_country_backup != 'Unknown':  # 备用也检查有效
                            cn_country = EN_TO_CN.get(en_country_backup, en_country_backup)
                            print(f"  备用成功: {en_country_backup} -> {cn_country}")
                            return cn_country
                        else:
                            print("  备用也无有效信息")
                    else:
                        print(f"  备用失败: {backup_resp.status_code}")
            elif response.status_code in [403, 429]:
                print(f"  主 API {response.status_code} 限速，无信息，尝试备用...")
                # 限速也视为无信息，调用备用
                backup_url = f'https://api.ipgeolocation.io/ipgeo?apiKey=demo&ip={ip}&fields=country_name'
                backup_resp = requests.get(backup_url, headers=headers, timeout=10)
                if backup_resp.status_code == 200:
                    data = backup_resp.json()
                    en_country_backup = data.get('country_name', 'Unknown')
                    if en_country_backup != 'Unknown':
                        cn_country = EN_TO_CN.get(en_country_backup, en_country_backup)
                        print(f"  备用成功: {en_country_backup} -> {cn_country}")
                        return cn_country
                    else:
                        print("  备用也无有效信息")
                else:
                    print(f"  备用失败: {backup_resp.status_code}")
            else:
                print(f"  主 API 其他错误 {response.status_code}，无信息，尝试备用...")
                # 其他错误也调用备用
                backup_url = f'https://api.ipgeolocation.io/ipgeo?apiKey=demo&ip={ip}&fields=country_name'
                backup_resp = requests.get(backup_url, headers=headers, timeout=10)
                if backup_resp.status_code == 200:
                    data = backup_resp.json()
                    en_country_backup = data.get('country_name', 'Unknown')
                    if en_country_backup != 'Unknown':
                        cn_country = EN_TO_CN.get(en_country_backup, en_country_backup)
                        print(f"  备用成功: {en_country_backup} -> {cn_country}")
                        return cn_country
                    else:
                        print("  备用也无有效信息")
                else:
                    print(f"  备用失败: {backup_resp.status_code}")
        except Exception as e:
            print(f"  异常 (尝试 {attempt+1}): {e}")
            # 异常也视为无信息，但 max_retries=1，无下轮备用
        
        if attempt < max_retries - 1:
            time.sleep(1)  # 短延时
    
    print(f"  国家查询最终失败 {ip}，默认全球 (CF 常见)")
    return '全球'  # CF IPs 常 anycast，fallback 全球

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
                print(f" 下载不完整: {output}")
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
            match = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::(\d+))?\s*#(.*)$', line)
            if not match:
                print(f"跳过无效行: {line}")
                continue
            ip = match.group(1)
            port = match.group(2) or str(DEFAULT_PORT)
            ip_port = f"{ip}:{port}"
            cn_country = get_chinese_country(ip)
            print(f"\n测试 {ip_port} - {cn_country}")
            speed = test_speed(ip)
            time.sleep(1)  # 延时防限速
            if speed > 0:
                result = f"{ip_port}#{cn_country} {speed}MB/s"
                results.append(result)
                print(f" -> 成功: {result}")
            else:
                failed_count += 1
                print(f" -> 失败: 连接不通")
        # 按速度降序排序，取前 50 个写入 speed_ip.txt
        sorted_results = sorted(results, key=lambda x: float(re.search(r'(\d+\.?\d*)MB/s', x).group(1)), reverse=True)
        top_50 = sorted_results[:50]  # 只取前 50
        with open('speed_ip.txt', 'w', encoding='utf-8') as f:
            for res in top_50:
                f.write(res + '\n')
        print(f"\n完成！共 {len(results)} 个成功 IP，按速度排序后取前 {len(top_50)} 个保存到 speed_ip.txt (失败 {failed_count} 个)")
    except Exception as e:
        print(f"脚本异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

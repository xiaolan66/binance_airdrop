import requests
import time
import asyncio
from datetime import datetime, timedelta
import json
import tweepy


# Twitter API 配置
TWITTER_CONFIG = {
    "consumer_key": "input",
    "consumer_secret": "input",
    "access_token": "input",
    "access_token_secret": "input"
}


def wait_for_trigger_time():
    """
    修正后的等待触发时间函数，确保以下触发点：
    1. 每小时55分01秒
    2. 每小时59分01秒 
    3. 每个整点01秒
    4. 其他时间每5分钟过1秒触发（05:01, 10:01,...,50:01）
    
    仅在12:00-24:00时间段内运行
    
    返回:
        datetime: 触发时间的datetime对象
        None: 如果不在运行时间段内
        
    示例:
        >>> result = wait_for_trigger_time()
        等待 [秒数] 秒到触发时间: [时间]
        >>> isinstance(result, datetime)
        True
    """
    while True:
        now = datetime.now()
        current_hour = now.hour
        
        # 检查是否在运行时间段内(12:00-24:00)
        if current_hour < 12:
            # 计算到12:00的等待时间
            next_run_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
            if next_run_time <= now:
                next_run_time += timedelta(days=1)
            
            wait_seconds = (next_run_time - now).total_seconds()
            print(f"当前时间 {now.strftime('%H:%M:%S')} 不在运行时间段(12:00-24:00)，等待 {wait_seconds:.1f} 秒到12:00")
            time.sleep(wait_seconds)
            continue
        
        current_min = now.minute
        current_sec = now.second
        
        # 定义所有可能的触发点
        special_triggers = [
            (55, 1),  # 55:01
            (59, 1),  # 59:01
            (0, 1)    # 整点01
        ]
        
        # 常规5分钟触发点 (05:01, 10:01,...,50:01)
        regular_triggers = [(minute, 1) for minute in range(5, 55, 5)]
        
        # 合并所有触发点并按时间排序
        all_triggers = sorted(special_triggers + regular_triggers)
        
        # 查找下一个触发点
        next_trigger = None
        for minute, second in all_triggers:
            # 创建触发时间对象
            trigger_time = now.replace(minute=minute, second=second, microsecond=0)
            
            # 如果触发时间已过当前时间，则考虑下一个小时
            if trigger_time <= now:
                trigger_time += timedelta(hours=1)
            
            # 检查是否超出运行时间段(24:00)
            if trigger_time.hour >= 24:
                trigger_time = trigger_time.replace(hour=12, minute=0, second=0) + timedelta(days=1)
            
            # 找到第一个未来的触发时间
            if next_trigger is None or trigger_time < next_trigger:
                next_trigger = trigger_time
        
        # 计算等待时间
        wait_seconds = (next_trigger - now).total_seconds()
        
        # 确保不会出现负等待时间
        if wait_seconds <= 0:
            continue
            
        print(f"等待 {wait_seconds:.1f} 秒到触发时间: {next_trigger.strftime('%H:%M:%S')}")
        time.sleep(wait_seconds)
        return next_trigger


def is_timestamp_matching(timestamp_ms, expected_time):
    """
    检查13位毫秒级时间戳是否与预期时间匹配（误差在3分钟内）
    
    Args:
        timestamp_ms (int): 毫秒级时间戳
        expected_time (datetime): 预期的时间点
        
    Returns:
        tuple: (是否匹配, 转换后的datetime对象)
    """
    # 将毫秒级时间戳转换为datetime对象
    timestamp_sec = timestamp_ms / 1000.0
    claim_time = datetime.fromtimestamp(timestamp_sec)
    
    # 计算时间差（秒）
    time_diff = abs((claim_time - expected_time).total_seconds())
    
    # 判断是否在允许的误差范围内（3分钟）
    return time_diff <= 180, claim_time


async def send_feishu_notification(message, feishu_hook_urls):
    """
    异步向多个飞书Webhook地址发送通知
    
    Args:
        message (dict): 通知消息内容
        feishu_hook_urls (list): 飞书Webhook地址列表
        
    Returns:
        bool: 是否全部发送成功
    """
    all_success = True
    
    for url in feishu_hook_urls:
        try:
            # 在异步上下文中执行同步请求
            response = await asyncio.get_running_loop().run_in_executor(
                None, lambda: requests.post(url, json=message)
            )
            response.raise_for_status()  # 检查HTTP状态码
            
            print(f"\n飞书通知发送到 {url} 成功!")
            if "content" in message and "post" in message["content"]:
                content = message["content"]["post"].get("zh_cn", {}).get("content", [])
                if content:
                    print(f"通知内容：{content}")
                    
        except requests.RequestException as e:
            all_success = False
            print(f"飞书通知发送到 {url} 失败: {str(e)}")
            
    return all_success


def get_token_price(token_address):
    """
    从指定的API中获取指定代币地址的priceInfo中的price值。
    如果获取失败返回0。
    :param token_address: 代币合约地址
    :return: priceInfo中的price值或0。
    """
    url = f'https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/token/full/info?chainId=56&contractAddress={token_address}'
    try:
        response = requests.get(url, timeout=10)  # 添加超时
        if response.status_code != 200:
            return 0

        data = response.json()
        if not isinstance(data, dict) or 'data' not in data:
            return 0
        if not isinstance(data['data'], dict) or 'priceInfo' not in data['data']:
            return 0
        if not isinstance(data['data']['priceInfo'], dict) or 'price' not in data['data']['priceInfo']:
            return 0

        return float(data['data']['priceInfo']['price'])
    except (requests.RequestException, json.JSONDecodeError, ValueError, Exception):
        return 0


async def get_airdrop_info(url, headers, payload, retry_count=0):
    """
    获取币安Alpha空投信息（带重试机制）
    
    Args:
        url (str): 请求URL
        headers (dict): 请求头
        payload (dict): 请求体
        retry_count (int): 当前重试次数
        
    Returns:
        dict: 解析后的空投信息，失败时返回None
    """
    max_retries = 3
    
    # 达到最大重试次数后返回失败
    if retry_count >= max_retries:
        return None
        
    try:
        # 异步执行请求
        response = await asyncio.get_running_loop().run_in_executor(
            None, lambda: requests.post(url, headers=headers, json=payload)
        )
        response.raise_for_status()
        
        return response.json()
        
    except requests.RequestException as e:
        print(f"获取空投信息失败，重试 {retry_count + 1}/{max_retries}: {str(e)}")
        await asyncio.sleep(2)  # 等待5秒后重试
        return await get_airdrop_info(url, headers, payload, retry_count + 1)


def generate_notification_message(config, token_price, claim_start_time):
    """
    生成飞书通知消息内容
    
    Args:
        config (dict): 空投配置信息
        token_price (float): 代币价格
        claim_start_time (int): 领取开始时间（毫秒级时间戳）
        
    Returns:
        dict: 格式化后的飞书消息结构
    """
    # 计算空投总价值
    airdrop_amount = config['airdropAmount']
    total_value = token_price * airdrop_amount
    formatted_value = "{:.2f}".format(total_value) if total_value > 0 else "获取报价失败-0"
    
    # 转换领取时间格式
    claim_time_obj = datetime.fromtimestamp(claim_start_time / 1000.0)
    
    # 构建飞书消息结构
    message = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": "Binance Alpha空投来了",
                    "content": [
                        [{"tag": "text", "text": "📅 领取开始时间："},
                         {"tag": "text", "text": f"{claim_time_obj.strftime('%Y-%m-%d %H:%M:%S')}"}],
                        [{"tag": "text", "text": "💰 代币名称："},
                         {"tag": "text", "text": f"{config['tokenSymbol']}"}],
                        [{"tag": "text", "text": "🎯 积分门槛："},
                         {"tag": "text", "text": f"{config['pointsThreshold']}"}],
                        [{"tag": "text", "text": "🔢 消耗积分："},
                         {"tag": "text", "text": f"{config['deductPoints']}"}],
                        [{"tag": "text", "text": "🔢 空投数量："},
                         {"tag": "text", "text": f"{config['airdropAmount']}"}],
                        [{"tag": "text", "text": "💸 总价值："},
                         {"tag": "text", "text": f"{formatted_value}USD"}],
                        [{"tag": "text", "text": "📌 合约地址："},
                         {
                             "tag": "a",
                             "text": f"{config['contractAddress']}",
                             "href": f"https://www.binance.com/zh-CN/alpha/bsc/{config['contractAddress']}"
                         }]
                    ]
                }
            }
        }
    }
    
    return message


async def send_new_api_notifications(message, fanwan_apis):
    """
    异步向多个第三方API发送通知
    
    Args:
        message (dict): 通知消息内容
        fanwan_apis (list): API地址列表
    """
    for api in fanwan_apis:
        try:
            # 异步执行请求
            response = await asyncio.get_running_loop().run_in_executor(
                None, lambda: requests.post(api, json=message)
            )
            response.raise_for_status()
            
            print(f"\n新API通知发送到 {api} 成功!")
            
        except requests.RequestException as e:
            print(f"新API通知发送到 {api} 失败: {str(e)}")


def generate_tweet_message(config, token_price, claim_start_time):
    """
    生成Twitter推文内容
    
    Args:
        config (dict): 空投配置信息
        token_price (float): 代币价格
        claim_start_time (int): 领取开始时间（毫秒级时间戳）
        
    Returns:
        str: 格式化后的推文内容
    """
    # 计算空投总价值
    airdrop_amount = config['airdropAmount']
    total_value = token_price * airdrop_amount
    formatted_value = "{:.2f}".format(total_value) if total_value > 0 else "获取报价失败-0"
    
    # 转换领取时间格式
    claim_time_obj = datetime.fromtimestamp(claim_start_time / 1000.0)
    
    # 构建推文内容
    tweet_lines = [
        "📢 Binance Alpha空投来袭!",
        f"📅 领取时间: {claim_time_obj.strftime('%Y-%m-%d %H:%M:%S')}",
        f"💰 代币名称: {config['tokenSymbol']}",
        f"🎯 积分门槛: {config['pointsThreshold']}积分",
        f"🔢 消耗积分: {config['deductPoints']}积分",
        f"🔢 空投数量: {config['airdropAmount']}",
        f"💸 总价值: ${formatted_value}",
        f"#{config['tokenSymbol']} #Binance #币安钱包 #币安alpha #币安空投"
    ]
    
    return '\n'.join(tweet_lines)


def send_to_twitter(tweet_content):
    """
    发送推文到Twitter
    
    Args:
        tweet_content (str): 推文内容
        
    Returns:
        bool: 是否发送成功
    """
    try:
        # 初始化Tweepy客户端
        client = tweepy.Client(
            consumer_key=TWITTER_CONFIG["consumer_key"],
            consumer_secret=TWITTER_CONFIG["consumer_secret"],
            access_token=TWITTER_CONFIG["access_token"],
            access_token_secret=TWITTER_CONFIG["access_token_secret"]
        )
        
        # 发送推文
        response = client.create_tweet(text=tweet_content)
        print(f"推文发送成功！推文 ID: {response.data['id']}")
        return True
        
    except tweepy.TweepyException as e:
        print(f"Twitter发送失败：{e}")
        return False
    except Exception as e:
        print(f"未知错误：{e}")
        return False


async def handle_airdrop_claim(expected_time, feishu_hook_urls, fanwan_apis):
    """
    处理空投通知主逻辑
    
    Args:
        expected_time (datetime): 预期触发时间
        feishu_hook_urls (list): 飞书Webhook地址列表
        fanwan_apis (list): 第三方API地址列表
    """
    # 获取空投信息
    url = 'https://www.binance.com/bapi/defi/v1/friendly/wallet-direct/buw/growth/query-alpha-airdrop'
    headers = {'Content-Type': 'application/json'}
    payload = {"page": 1, "rows": 20}
    
    airdrop_info = await get_airdrop_info(url, headers, payload)
    
    if airdrop_info:
        # 获取首个空投配置
        first_config = airdrop_info['data']['configs'][0]
        display_start_time = first_config['displayStartTime']
        claim_start_time = first_config['claimStartTime']
        
        # 检查时间匹配性
        is_matching, claim_time = is_timestamp_matching(display_start_time, expected_time)
        
        if is_matching:
            # 获取代币价格并生成通知
            token_address = first_config['contractAddress']
            token_price = get_token_price(token_address)
            
            # 生成并发送通知
            message = generate_notification_message(first_config, token_price, claim_start_time)
            await send_new_api_notifications(message, fanwan_apis)
            
            # 发送飞书通知并决定是否发推文
            feishu_success = await send_feishu_notification(message, feishu_hook_urls)
            if feishu_success:
                tweet_content = generate_tweet_message(first_config, token_price, claim_start_time)
                send_to_twitter(tweet_content)
            else:
                print("飞书通知发送失败，取消Twitter发送")
        else:
            print(f"\n✗ 时间不匹配! Claim时间: {claim_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        # 发送错误通知
        error_message = {
            "msg_type": "text",
            "content": {"text": "获取空投信息失败，已达到最大重试次数"}
        }
        hardcoded_error_url = ["https://open.feishu.cn/open-apis/bot/v2/hook/"]
        await send_feishu_notification(error_message, hardcoded_error_url)
        #await send_feishu_notification(error_message, feishu_hook_urls)


# 配置信息
config = {
    "feishu_hook_urls": [
        "https://open.feishu.cn/open-apis/bot/v2/hook/",
        # "https://another-open.feishu.cn/open-apis/bot/v2/hook/another-id"
    ],
    "fanwan_apis": [
        "https://fwalert.com/"
    ]
}


def main():
    """
    主函数：循环监控币安Alpha空投并发送通知
    """
    while True:
        # 等待触发时间
        expected_hour = wait_for_trigger_time()
        print(f"\n=== 在 {datetime.now()} 触发执行 ===")
        print(f"预期Claim时间: {expected_hour.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 处理空投通知
        asyncio.run(handle_airdrop_claim(expected_hour, config["feishu_hook_urls"], config["fanwan_apis"]))
        
        # 短暂延迟避免重复触发
        time.sleep(1)


if __name__ == "__main__":
    main()

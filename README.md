# 币安Alpha空投监控通知系统

## 概述

本文文档详细介绍了币安Alpha空投监控通知系统的技术原理与实现方式。该系统能够定时监控币安Alpha平台的空投信息，在特定时间点触发检查，并通过飞书(Feishu)、第三方API及Twitter等渠道发送通知，帮助用户及时获取空投机会。

## 功能说明

系统主要实现以下核心功能：
- 按预设制定时策略触发监控任务（特定时间点执行）
- 从币安API获取最新空投信息
- 验证空投时间与预期时间的匹配性
- 计算空投代币的当前价值
- 多渠道发送格式化通知（飞书、第三方API、Twitter）
- 包含错误处理与重试机制

## 技术原理

### 1. 定时触发机制

系统采用基于时间的触发机制，确保在预设时间点执行监控任务，具体触发策略：
- 特殊时间点：每小时55分01秒、59分01秒、整点01秒
- 常规时间点：每小时的05:01、10:01...50:01（每5分钟）
- 运行时间段限制：仅在12:00-24:00之间运行

实现原理：通过`wait_for_trigger_time()`函数计算下一个触发时间，使用`time.sleep()`进行等待，确保任务在精确时间点执行。

### 2. 数据获取与处理

- **空投信息获取**：通过币安公开API`query-alpha-airdrop`接口获取空投配置信息
- **代币价格获取**：从币安API获取指定代币的当前价格
- **时间验证**：将API返回的时间戳与预期触发时间进行比对，允许3分钟误差范围

### 3. 异步通知机制

系统采用异步处理方式发送通知，提高效率：
- 使用`asyncio`实现异步任务调度
- 对飞书和第三方API通知采用异步HTTP请求
- 对同步的`requests`库通过`run_in_executor`在异步上下文中执行

### 4. 错误处理与重试

- 网络请求失败时自动重试（最多3次）
- 异常捕获与处理（网络错误、JSON解析错误等）
- 失败通知机制（获取信息失败时发送错误通知）

## 实现方式

### 核心模块结构

1. **定时模块**
   - `wait_for_trigger_time()`：计算并等待下一个触发时间
   - 时间检查逻辑确保仅在12:00-24:00运行

2. **数据获取模块**
   - `get_airdrop_info()`：获取空投信息（带重试机制）
   - `get_token_price()`：获取代币当前价格
   - `is_timestamp_matching()`：验证时间匹配性

3. **通知模块**
   - `send_feishu_notification()`：发送飞书通知
   - `send_new_api_notifications()`：发送第三方API通知
   - `send_to_twitter()`：发送Twitter推文
   - 消息生成函数：`generate_notification_message()`和`generate_tweet_message()`

4. **主控制模块**
   - `handle_airdrop_claim()`：处理空投通知主逻辑
   - `main()`：程序入口，循环执行监控任务

### 关键流程

1. 程序启动后进入无限循环
2. 计算并等待下一个触发时间点
3. 到达触发时间后，从币安API获取空投信息
4. 验证空投时间与预期时间是否匹配
5. 如匹配，获取代币价格并生成通知内容
6. 发送通知到各渠道（飞书、第三方API、Twitter）
7. 完成后等待下一个触发周期

### 配置说明

系统配置位于代码底部的`config`字典和`TWITTER_CONFIG`字典：

```python
# Twitter API配置
TWITTER_CONFIG = {
    "consumer_key": "input",
    "consumer_secret": "input",
    "access_token": "input",
    "access_token_secret": "input"
}

# 通知渠道配置
config = {
    "feishu_hook_urls": [
        "https://open.feishu.cn/open-apis/bot/v2/hook/",
        # 可添加更多飞书Webhook地址
    ],
    "fanwan_apis": [
        "https://fwalert.com/"
        # 可添加更多第三方API地址
    ]
}
```

## 依赖说明

系统依赖以下Python库：
- `requests`：处理HTTP请求
- `asyncio`：实现异步操作
- `tweepy`：Twitter API交互
- `datetime`和`time`：时间处理
- `json`：JSON数据处理

## 注意事项

1. 需要先配置有效的API密钥和Webhook地址才能正常运行
2. 网络环境需要能够访问币安API和Twitter API
3. 系统设计为长期运行的服务型程序
4. 时间匹配存在3分钟误差容忍度，适应网络延迟等情况
5. 所有外部API请求都包含超时和错误处理

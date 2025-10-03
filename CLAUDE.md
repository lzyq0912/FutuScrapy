# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个富途牛牛新闻爬虫项目，专门用于爬取港股和美股的新闻数据。项目具有完整的Docker化部署方案，支持测试和自动化运行模式。

### 核心功能
- 批量爬取港股(HK)和美股(US)新闻数据
- 支持多线程并发爬取，显著提升效率
- 内置IP代理池管理，避免被API限制
- 智能数据管理：自动清理旧数据，支持增量更新
- 定时任务：每天晚上8点北京时间自动运行

## 项目架构

### 核心文件结构
```
futuScrapy/
├── futu_news_scraper.py    # 主要爬虫程序（核心逻辑）
├── run.py                  # Docker管理脚本
├── all_stocks_info.csv     # 股票基础数据源
├── requirements.txt        # Python依赖
├── Dockerfile             # Docker镜像配置
├── docker-compose.yml     # Docker编排文件
└── output/                # 输出目录（自动创建）
```

### 主要类和模块

#### FutuNewsScraper 类 (futu_news_scraper.py:127-774)
核心爬虫类，主要功能：
- `load_stock_data()`: 加载和筛选股票数据
- `batch_scrape_news()`: 批量多线程爬取新闻
- `get_stock_news()`: 单股票新闻获取（并发控制）
- `parse_news_data()`: 新闻数据解析和结构化
- `save_news_to_csv()`: 数据保存和分类输出

#### ProxyManager 类 (futu_news_scraper.py:18-100)
IP代理池管理器：
- 自动从第三方API获取代理IP
- 实现代理轮换和失效检测
- 线程安全的代理队列管理

#### FutuTokenGenerator 类 (futu_news_scraper.py:102-125)
富途API认证令牌生成器：
- 基于JS逆向工程实现
- 生成quote-token用于API认证

## 开发环境设置

### 本地开发
```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 直接运行（测试模式）
python futu_news_scraper.py --mode test

# 运行自动模式
python futu_news_scraper.py --mode auto
```

### Docker开发
```bash
# 初始化目录
python run.py init

# 构建并运行测试
python run.py test

# 运行自动模式（后台）
python run.py auto

# 查看状态和日志
python run.py status
python run.py logs

# 停止所有服务
python run.py stop
```

## 关键配置参数

### 并发控制参数
- `MAX_WORKERS`: 线程池大小（默认30，建议10-50）
- `MAX_CONCURRENT`: 同时请求数（默认25，建议5-30）
- `REQUEST_DELAY`: 请求间隔秒数（默认0.1秒）

### 数据控制参数
- `max_stocks`: 每个市场最大股票数
- `max_news_per_stock`: 每只股票最大新闻数
- `keep_days`: 数据保留天数（默认3天）

### 运行模式
- `test`: 测试模式（50只港股+50只美股，每股票10条新闻）
- `auto`: 自动模式（200只港股+200只美股，每股票15条新闻，定时运行）
- `fulltest`: 全量测试（不限股票数量，获取所有港美股）

## 测试相关

### 运行测试
```bash
# Docker测试模式（推荐）
python run.py test

# 直接运行测试
python futu_news_scraper.py --mode test --max-workers 10 --use-proxy false

# 全量测试
python futu_news_scraper.py --mode fulltest
```

### 性能预期
- 100只股票约2-3分钟完成
- 400只股票约8-12分钟完成
- 平均效率30-50条新闻/秒

## 数据输出

### 文件命名规则
- 测试模式: `news_YYYYMMDD_HHMMSS.csv`
- 自动模式: `news_HK_YYYYMMDD_HHMMSS.csv`, `news_US_YYYYMMDD_HHMMSS.csv`
- 按时效性: `news_3days_*.csv`, `news_today_*.csv`

### CSV字段说明
主要字段包括：股票代码、公司名称、新闻ID、新闻标题、发布时间、新闻来源、重要性级别等。

## 部署和运维

### 生产部署
建议部署到 `/etc/FUTUNews` 目录，使用Docker Compose管理。

### 监控和维护
```bash
# 查看运行状态
python run.py status

# 查看实时日志
python run.py logs

# 手动清理旧数据（保留1天）
docker exec -it futu-news-auto python -c "
from futu_news_scraper import FutuNewsScraper
scraper = FutuNewsScraper()
scraper.cleanup_old_news(keep_days=1)
"
```

## 故障排除

### 常见问题
1. **网络连接失败**: 检查是否能访问 `futunn.com`
2. **代理池异常**: 代理API可能不稳定，可设置 `--use-proxy false` 禁用
3. **权限问题**: 确保输出目录有写入权限
4. **容器无法启动**: 检查Docker镜像构建和环境变量配置

### 调试技巧
- 使用测试模式验证功能
- 调整并发参数避免被限流
- 查看Docker容器日志定位问题
- 使用单线程模式(`--max-workers 1`)排查并发问题

## 安全注意事项

- 代理API密钥已硬编码，生产环境应移到环境变量
- 请求频率控制避免对目标网站造成压力
- 数据仅用于合规的信息收集用途
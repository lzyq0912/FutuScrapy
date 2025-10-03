# 富途新闻爬虫 Docker 部署指南

## 📋 概述

本项目提供了富途牛牛新闻爬虫的 Docker 部署方案，支持两种运行模式：
- **测试模式**: 一次性爬取 100 只股票验证功能
- **自动模式**: 每天晚上 8 点北京时间定时运行，智能数据管理

## 📁 文件结构

```
futuScrapy/
├── futu_news_scraper.py      # 主要爬虫程序（已修改为Docker版本）
├── all_stocks_info.csv       # 股票信息数据
├── requirements.txt          # Python依赖
├── Dockerfile               # Docker镜像配置 
├── docker-compose.yml       # Docker编排文件
├── run.py                   # 便捷启动脚本
└── README_Docker.md         # 本文档
```

## 🚀 快速开始

### 1. 准备环境

确保VPS上已安装：
- Docker 
- Docker Compose
- Python 3.x（用于运行管理脚本）

```bash
# 安装Docker（Ubuntu/Debian）
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装Docker Compose
sudo pip3 install docker-compose
```

### 2. 部署到VPS

```bash
# 1. 上传项目文件到VPS的 /etc/FUTUNews 目录
sudo mkdir -p /etc/FUTUNews
cd /etc/FUTUNews

# 2. 上传所有项目文件到此目录
# 包括：futu_news_scraper.py, all_stocks_info.csv, requirements.txt, 
#      Dockerfile, docker-compose.yml, run.py

# 3. 设置执行权限
sudo chmod +x run.py
```

### 3. 运行模式

#### 方式一：使用管理脚本（推荐）

```bash
# 初始化目录
python3 run.py init

# 测试模式（一次性运行100只股票）
python3 run.py test

# 自动模式（每天8PM定时运行）
python3 run.py auto

# 查看运行状态
python3 run.py status

# 查看日志
python3 run.py logs

# 停止所有服务
python3 run.py stop
```

#### 方式二：直接使用Docker Compose

```bash
# 测试模式（一次性运行，完成后自动清理）
docker-compose run --rm futu-news-test

# 自动模式（后台运行）
docker-compose --profile auto up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose --profile auto down
```

## 🎯 运行模式

### 测试模式 (test)
- **用途**: 验证爬虫功能，快速测试
- **股票数量**: 50只港股 + 50只美股
- **每股新闻数**: 10条
- **运行方式**: 一次性运行后自动退出并清理容器
- **容器清理**: 运行完成后容器自动删除，不留残余
- **输出**: CSV文件保存到 `/etc/FUTUNews/output`

### 自动模式 (auto)
- **用途**: 生产环境持续运行
- **调度时间**: 每天晚上8点北京时间
- **智能管理**: 
  - 首次运行：爬取近3天历史数据
  - 日常运行：增量更新今日数据
  - 自动清理：保留3天数据，清理旧文件
- **股票数量**: 200只港股 + 200只美股
- **每股新闻数**: 15条
- **输出**: 按日期和市场分类的CSV文件

## 🚀 性能优化

本版本采用多线程并行化设计，显著提升爬取效率：

### 并发参数
- **线程池大小**: 默认10个工作线程
- **最大并发请求**: 默认5个同时请求
- **请求间隔**: 默认0.2秒
- **重试机制**: 失败自动重试2次

### 预期性能
- **爬取速度**: 比原版提升5-10倍
- **100只股票**: 约2-3分钟完成
- **400只股票**: 约8-12分钟完成
- **平均效率**: 30-50条新闻/秒

### 输出优化
- 简化日志信息，只显示关键进度
- 实时进度条：`进度: 123/500 (24.6%) | 新闻: 1,840 | 错误: 2 | 剩余: 3分25秒`
- 完成后显示性能统计和错误汇总

### 输出目录
所有数据保存在 `/etc/FUTUNews/output/` 目录下

## 📊 数据输出

### 文件命名规则
- 测试模式: `news_YYYYMMDD_HHMMSS.csv`
- 自动模式: `news_HK_YYYYMMDD_HHMMSS.csv` 和 `news_US_YYYYMMDD_HHMMSS.csv`

### CSV字段说明
| 字段 | 说明 |
|------|------|
| 股票代码 | 如 HK.01117, US.AAPL |
| 公司名称 | 公司中文名称 |  
| 股票ID | 富途内部ID |
| 市场 | HK/US |
| 新闻ID | 新闻唯一标识 |
| 新闻标题 | 新闻标题 |
| 发布时间 | YYYY-MM-DD HH:MM:SS |
| 新闻来源 | 新闻来源媒体 |
| 新闻摘要 | 新闻摘要（部分为空）|
| 新闻链接 | 富途新闻链接 |
| 重要性级别 | 0-5数值 |
| 重要性标签 | 重要性文字描述 |
| 链接类型 | 链接类型编号 |
| 发布日期 | YYYY-MM-DD |
| 发布小时 | 0-23小时 |

## 🔧 高级配置

### 修改并发参数

编辑 `futu_news_scraper.py` 中的初始化参数：

```python
# 创建爬虫实例时指定参数
scraper = FutuNewsScraper(
    max_workers=15,        # 线程池大小（默认10）
    max_concurrent=8,      # 最大并发请求（默认5）
    request_delay=0.1      # 请求间隔秒数（默认0.2）
)
```

### 修改运行参数

编辑 `futu_news_scraper.py` 中的相关参数：

```python
# 自动模式参数
max_stocks=200,          # 每个市场最大股票数
max_news_per_stock=15,   # 每只股票最大新闻数
keep_days=3              # 数据保留天数

# 测试模式参数  
max_stocks=50,           # 每个市场最大股票数
max_news_per_stock=10,   # 每只股票最大新闻数
```

### 修改调度时间

编辑 `futu_news_scraper.py` 中的调度设置：

```python
# 每天晚上8点运行
schedule.every().day.at("20:00").do(job)

# 修改为其他时间，如每天上午9点
schedule.every().day.at("09:00").do(job)
```

### 自定义输出目录

修改 `futu_news_scraper.py` 中的输出目录：

```python
self.output_dir = '/etc/FUTUNews/output'  # 修改为其他路径
```

同时更新 `docker-compose.yml` 中的卷挂载：

```yaml
volumes:
  - /your/custom/path:/etc/FUTUNews/output
```

## 📝 监控和维护

### 查看运行状态
```bash
python3 run.py status
```

### 查看实时日志
```bash
python3 run.py logs
```

### 手动清理数据
```bash
# 进入容器执行清理
docker exec -it futu-news-auto python -c "
from futu_news_scraper import FutuNewsScraper
scraper = FutuNewsScraper()
scraper.cleanup_old_news(keep_days=1)  # 只保留1天数据
"
```

### 重启服务
```bash
# 停止服务
python3 run.py stop

# 重新启动自动模式
python3 run.py auto
```

## ⚠️ 注意事项

1. **权限问题**: 确保 `/etc/FUTUNews/output` 目录有写入权限
2. **网络问题**: VPS需要能够访问富途API（`futunn.com`）
3. **时区设置**: 容器已配置为北京时区（Asia/Shanghai）
4. **资源消耗**: 建议VPS至少1GB内存，爬取过程会消耗一定CPU和内存
5. **数据存储**: 每天约产生几十MB数据，注意磁盘空间
6. **API限制**: 已内置请求频率控制，避免被API限制

## 🛠️ 故障排除

### 容器无法启动
```bash
# 查看详细错误信息
docker-compose logs

# 检查镜像是否构建成功
docker images | grep futu
```

### 无数据输出
```bash
# 检查输出目录权限
ls -la /etc/FUTUNews/output

# 查看容器日志
docker logs futu-news-auto
```

### 网络连接问题
```bash
# 测试网络连接
docker exec -it futu-news-auto ping futunn.com

# 检查DNS解析
docker exec -it futu-news-auto nslookup futunn.com
```

## 📞 技术支持

如有问题，请检查：
1. Docker和Docker Compose版本
2. VPS网络连接
3. 目录权限设置
4. 系统资源使用情况

---
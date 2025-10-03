import hashlib
import hmac
import json
import requests
import pandas as pd
import time
import os
import argparse
import schedule
import pytz
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, Any, List
from tqdm import tqdm
import queue

class ProxyManager:
    """IP代理池管理器"""
    
    def __init__(self):
        self.api_url = "https://find.xiaoxiongip.com/find_http"
        self.api_params = {
            'key': '2034f1ac357f2622',
            'count': '50',  # 增加到50个IP提高池容量
            'type': 'text',
            'only': '0',
            'textSep': '3',
            'pw': 'no'
        }
        self.proxy_queue = queue.Queue()
        self.refresh_interval = 150  # 2分半 = 150秒
        self.last_refresh = 0
        self.lock = threading.Lock()
        self.is_refreshing = False  # 添加刷新状态标记
        self.failed_refresh_count = 0  # 记录连续失败次数
        self.max_failed_attempts = 3  # 最大失败尝试次数
        
        # 初始化代理池
        self.refresh_proxies()
    
    def get_proxies_from_api(self) -> List[str]:
        """从API获取代理IP列表"""
        try:
            response = requests.get(self.api_url, params=self.api_params, timeout=10)
            if response.status_code == 200:
                # 新API返回格式: 换行分割的IP:PORT
                proxy_list = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
                print(f"🌐 从API获取到 {len(proxy_list)} 个代理IP")
                return proxy_list
            elif response.status_code == 502:
                print(f"❌ 代理API服务不可用 (502)，可能是服务商问题")
                return []
            else:
                print(f"❌ 代理API请求失败: HTTP {response.status_code}")
                return []
        except requests.exceptions.RequestException as e:
            print(f"❌ 代理API网络异常: {e}")
            return []
        except Exception as e:
            print(f"❌ 获取代理IP异常: {e}")
            return []
    
    def refresh_proxies(self):
        """刷新代理池（线程安全）"""
        with self.lock:
            # 如果已经在刷新中，跳过
            if self.is_refreshing:
                print("🔄 代理池正在刷新中，跳过重复刷新...")
                return
            
            # 检查是否已经连续失败太多次
            if self.failed_refresh_count >= self.max_failed_attempts:
                print(f"⚠️ 代理API连续失败{self.failed_refresh_count}次，暂时停止刷新")
                return
            
            self.is_refreshing = True
            print("🔄 刷新代理池...")
            
            try:
                proxy_list = self.get_proxies_from_api()
                
                if not proxy_list:
                    self.failed_refresh_count += 1
                    print(f"❌ 代理获取失败 ({self.failed_refresh_count}/{self.max_failed_attempts})")
                    return
                
                # 成功获取，重置失败计数
                self.failed_refresh_count = 0
                
                # 清空旧队列
                while not self.proxy_queue.empty():
                    try:
                        self.proxy_queue.get_nowait()
                    except queue.Empty:
                        break
                
                # 添加新代理到队列
                valid_count = 0
                for proxy in proxy_list:
                    if ':' in proxy and len(proxy.split(':')) == 2:
                        self.proxy_queue.put({
                            'http': f'http://{proxy}',
                            'https': f'http://{proxy}'
                        })
                        valid_count += 1
                
                self.last_refresh = time.time()
                print(f"✅ 代理池已刷新，有效代理: {valid_count} 个 (总获取: {len(proxy_list)})")
                
            finally:
                self.is_refreshing = False
    
    def get_proxy(self) -> Dict[str, str]:
        """获取一个可用代理（优化多线程处理）"""
        # 检查是否需要定时刷新
        if time.time() - self.last_refresh > self.refresh_interval:
            self.refresh_proxies()
        
        # 尝试获取代理
        try:
            return self.proxy_queue.get_nowait()
        except queue.Empty:
            # 检查当前代理池状态
            current_size = self.proxy_queue.qsize()
            
            # 如果代理池为空且没有在刷新，尝试刷新
            if current_size == 0 and not self.is_refreshing:
                print("⚠️ 代理池为空，尝试刷新...")
                self.refresh_proxies()
                
                # 再次尝试获取
                try:
                    return self.proxy_queue.get_nowait()
                except queue.Empty:
                    print("❌ 刷新后仍无可用代理")
                    return None
            elif self.is_refreshing:
                print("⏳ 代理池刷新中，等待...")
                # 等待一小段时间后重试
                time.sleep(0.1)
                try:
                    return self.proxy_queue.get_nowait()
                except queue.Empty:
                    print("❌ 等待后仍无可用代理")
                    return None
            else:
                print("❌ 无可用代理")
                return None
    
    def return_proxy(self, proxy: Dict[str, str], is_valid: bool = True):
        """归还代理到池中（只归还有效的代理）"""
        if proxy and is_valid:
            # 检查代理格式是否正确
            if 'http' in proxy and 'https' in proxy:
                self.proxy_queue.put(proxy)
            else:
                print(f"⚠️ 代理格式无效，不归还: {proxy}")
        elif proxy and not is_valid:
            print(f"🚫 代理无效，不归还到池中: {proxy.get('http', 'Unknown')}")
    
    def get_pool_status(self):
        """获取代理池状态信息"""
        return {
            'current_size': self.proxy_queue.qsize(),
            'is_refreshing': self.is_refreshing,
            'last_refresh': self.last_refresh,
            'time_since_refresh': time.time() - self.last_refresh
        }

class FutuTokenGenerator:
    """富途牛牛token生成器，基于JS逆向分析"""
    
    def hmac_sha512(self, text: str, key: str) -> str:
        return hmac.new(key.encode(), text.encode(), hashlib.sha512).hexdigest()
    
    def sha256(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()
    
    def serialize_params(self, params: Dict[str, Any]) -> str:
        filtered_params = {}
        for key, value in params.items():
            if value is not None:
                filtered_params[key] = str(value)
        return json.dumps(filtered_params, separators=(',', ':'))
    
    def generate_quote_token(self, params: Dict[str, Any]) -> str:
        serialized = self.serialize_params(params) if params else "{}"
        if len(serialized) <= 0:
            serialized = "quote"
        hmac_result = self.hmac_sha512(serialized, "quote_web")
        hmac_slice = hmac_result[:10]
        sha_result = self.sha256(hmac_slice)
        return sha_result[:10]

class FutuNewsScraper:
    """富途牛牛新闻爬虫 - 批量获取港美股新闻（多线程版本）"""
    
    def __init__(self, max_workers: int = 30, max_concurrent: int = 25, request_delay: float = 0.1, 
                 output_dir: str = None, use_proxy: bool = True):
        self.token_generator = FutuTokenGenerator()
        self.base_url = "https://www.futunn.com"
        
        # 代理管理
        self.use_proxy = use_proxy
        self.proxy_downgraded = False  # 标记是否已降级
        print(f"🔍 代理配置调试: use_proxy={use_proxy}")
        if use_proxy:
            print("🌐 初始化IP代理池...")
            try:
                self.proxy_manager = ProxyManager()
                # 显示初始代理池状态
                status = self.proxy_manager.get_pool_status()
                print(f"✅ 代理池初始化成功，当前状态: {status['current_size']}个代理")
                
                # 检查代理池是否为空（API失败的情况）
                if status['current_size'] == 0 and self.proxy_manager.failed_refresh_count >= 1:
                    print("⚠️ 代理池初始化后为空，可能是API问题，建议降级到无代理模式")
                    
            except Exception as e:
                print(f"❌ 代理池初始化失败: {e}")
                self.proxy_manager = None
        else:
            print("🚫 代理池已禁用")
            self.proxy_manager = None
        
        # 并发控制参数（提升性能）
        self.max_workers = max_workers
        self.max_concurrent = max_concurrent
        self.request_delay = request_delay
        self.semaphore = threading.Semaphore(max_concurrent)
        
        # 基础headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': 'https://www.futunn.com',
            'Referer': 'https://www.futunn.com/quote/us',
        }
        
        # 输出目录配置
        self.output_dir = output_dir or 'output'  # 默认本地output目录
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 市场类型映射
        self.market_type_map = {
            'HK': 1,  # 港股
            'US': 2,  # 美股
        }
        
        # 进度跟踪
        self.progress_lock = threading.Lock()
        self.processed_stocks = 0
        self.total_news = 0
        self.valid_news = 0
        self.skipped_stocks = 0
        self.error_count = 0
        self.start_time = None
        self.progress_bar = None
    
    def load_stock_data(self) -> pd.DataFrame:
        """加载股票数据，筛选港股和美股"""
        try:
            df = pd.read_csv('all_stocks_info.csv')
            print(f"📊 加载股票数据: {len(df)} 条记录")
            
            # 筛选港股和美股
            hk_us_stocks = df[df['code'].str.startswith(('HK.', 'US.'))]
            print(f"🎯 港股和美股数量: {len(hk_us_stocks)} 条")
            
            # 按市场分组统计
            market_counts = hk_us_stocks['code'].str[:2].value_counts()
            for market, count in market_counts.items():
                print(f"  - {market}股: {count} 只")
            
            return hk_us_stocks
            
        except Exception as e:
            print(f"❌ 加载股票数据失败: {e}")
            return pd.DataFrame()
    
    def is_news_within_days(self, news_timestamp: int, days_limit: int = 0) -> bool:
        """检查新闻是否在指定天数内，days_limit=0表示今天"""
        try:
            news_date = datetime.fromtimestamp(news_timestamp).date()
            current_date = datetime.now().date()
            days_diff = (current_date - news_date).days
            return days_diff <= days_limit
        except:
            return False
    
    def format_date(self, dt: datetime = None, format_type: str = 'datetime') -> str:
        """统一日期格式化工具"""
        if dt is None:
            dt = datetime.now()
        
        formats = {
            'date': '%Y%m%d',           # 20250730
            'datetime': '%Y-%m-%d %H:%M:%S',  # 2025-07-30 21:30:00
            'date_dash': '%Y-%m-%d',    # 2025-07-30
            'timestamp': '%H%M%S'       # 213000
        }
        return dt.strftime(formats.get(format_type, formats['datetime']))
    
    def update_progress(self, valid_news_count: int = 0, total_news_count: int = 0, 
                       skipped: bool = False, error: bool = False):
        """更新进度信息（线程安全）"""
        with self.progress_lock:
            self.processed_stocks += 1
            self.valid_news += valid_news_count
            self.total_news += total_news_count
            if skipped:
                self.skipped_stocks += 1
            if error:
                self.error_count += 1
            
            # 更新进度条
            if self.progress_bar:
                self.progress_bar.update(1)
                # 更新进度条描述
                desc = f"新闻:{self.valid_news} 跳过:{self.skipped_stocks} 错误:{self.error_count}"
                self.progress_bar.set_description(desc)
    
    def get_stock_news(self, stock_info: Dict[str, str], max_news_per_stock: int = 15, 
                      retry_times: int = 2) -> List[Dict[str, Any]]:
        """获取单只股票的新闻列表（优化版）"""
        stock_id = stock_info['stock_id']
        stock_code = stock_info['code']
        market_prefix = stock_code[:2]
        market_type = self.market_type_map.get(market_prefix, 2)
        
        # 创建会话
        session = requests.Session()
        session.headers.update(self.headers)
        all_news = []
        
        # 信号量控制并发数
        with self.semaphore:
            for attempt in range(retry_times + 1):
                try:
                    current_seq_mark = None
                    
                    # 最多获取5页数据，确保充分获取
                    for page in range(5):
                        params = {
                            'stock_id': stock_id,
                            'market_type': market_type,
                            'type': 0,
                            'subType': 0,
                        }
                        
                        if current_seq_mark:
                            params['seq_mark'] = current_seq_mark
                        
                        # 生成quote-token
                        quote_token = self.token_generator.generate_quote_token(params)
                        url = f"{self.base_url}/quote-api/quote-v2/get-news-list"
                        
                        request_headers = self.headers.copy()
                        request_headers['quote-token'] = quote_token
                        
                        # 获取代理并发送请求
                        proxy = None
                        proxy_is_valid = True
                        
                        # 检查代理池状态，如果持续无效则降级
                        if (self.use_proxy and self.proxy_manager and 
                            not self.proxy_downgraded and 
                            self.proxy_manager.failed_refresh_count >= self.proxy_manager.max_failed_attempts):
                            print("🔻 代理池持续失效，自动降级为无代理模式")
                            self.proxy_downgraded = True
                        
                        if (self.use_proxy and self.proxy_manager and not self.proxy_downgraded):
                            proxy = self.proxy_manager.get_proxy()
                            if not proxy:
                                print("⚠️ 暂无可用代理，本次请求使用直连")
                        
                        try:
                            response = session.get(url, params=params, headers=request_headers, 
                                                 proxies=proxy, timeout=15)
                        except (requests.exceptions.ProxyError, 
                               requests.exceptions.ConnectTimeout,
                               requests.exceptions.ConnectionError) as e:
                            # 代理相关错误，标记代理无效
                            proxy_is_valid = False
                            raise
                        finally:
                            # 归还代理（只归还有效的代理）
                            if proxy and self.proxy_manager:
                                self.proxy_manager.return_proxy(proxy, proxy_is_valid)
                        
                        if response.status_code == 200:
                            data = response.json()
                            if data.get('code') == 0 and data.get('data', {}).get('list'):
                                news_list = data['data']['list']
                                all_news.extend(news_list)
                                
                                if len(all_news) >= max_news_per_stock:
                                    all_news = all_news[:max_news_per_stock]
                                    break
                                
                                next_seq_mark = data['data'].get('seq_mark')
                                if not next_seq_mark or next_seq_mark == current_seq_mark:
                                    break
                                
                                current_seq_mark = next_seq_mark
                            else:
                                break
                        elif response.status_code == 429:
                            # IP被限流，不归还这个代理，直接获取新代理重试
                            if attempt < retry_times:
                                time.sleep(0.2)  # 短暂延迟
                                continu 
                    
                            else:
                                break
                        elif response.status_code == 403:
                            # IP被禁，切换代理重试
                            if attempt < retry_times:
                                time.sleep(0.2)
                                continue
                            else:
                                break
                        else:
                            if attempt < retry_times:
                                time.sleep(0.5 * (attempt + 1))  # 递增延迟重试
                                continue
                            else:
                                break
                        
                        # 请求间隔
                        time.sleep(self.request_delay)
                    
                    # 解析新闻数据（只保留今日新闻）
                    if all_news:
                        parsed_news = self.parse_news_data(all_news, stock_info, only_today=True)
                        self.update_progress(valid_news_count=len(parsed_news), total_news_count=len(all_news))
                        return parsed_news
                    else:
                        self.update_progress(skipped=True)
                        return []
                        
                except requests.exceptions.RequestException:
                    if attempt < retry_times:
                        print(f"    🔄 重试 {stock_code} (尝试 {attempt+2}/{retry_times+1}): 网络请求异常")
                        time.sleep(1 * (attempt + 1))
                        continue
                    else:
                        print(f"    ❌ {stock_code} 最终失败: 网络请求异常")
                        self.update_progress(error=True)
                        return []
                except Exception:
                    if attempt < retry_times:
                        print(f"    🔄 重试 {stock_code} (尝试 {attempt+2}/{retry_times+1}): 未知错误")
                        time.sleep(1 * (attempt + 1))
                        continue
                    else:
                        print(f"    ❌ {stock_code} 最终失败: 未知错误")
                        self.update_progress(error=True)
                        return []
        
        print(f"    ❌ {stock_code} 所有重试失败")
        self.update_progress(error=True)
        return []
    
    def parse_news_data(self, news_list: List[Dict[str, Any]], 
                       stock_info: Dict[str, str], only_today: bool = True) -> List[Dict[str, Any]]:
        """解析新闻数据为结构化格式，可选择只保留今日新闻"""
        parsed_news = []
        
        for news_item in news_list:
            try:
                # 检查必要字段
                news_timestamp = news_item.get('time', 0)
                if not news_timestamp:
                    continue  # 跳过无时间戳的新闻
                
                # 如果开启今日新闻过滤，只保留今天的新闻
                if only_today and not self.is_news_within_days(news_timestamp, 0):
                    continue
                
                # 基础股票信息
                record = {
                    '股票代码': stock_info.get('code', ''),
                    '公司名称': stock_info.get('stock_name', ''),
                    '股票ID': stock_info.get('stock_id', ''),
                    '市场': stock_info.get('code', '')[:2],  # HK 或 US
                }
                
                # 新闻信息 - 使用API实际返回的字段名
                record.update({
                    '新闻ID': news_item.get('id', ''),
                    '新闻标题': news_item.get('title', ''),
                    '发布时间': self.format_date(
                        datetime.fromtimestamp(int(news_timestamp))
                    ),
                    '新闻来源': news_item.get('source', ''),
                    '新闻摘要': news_item.get('abstract', ''),  # 大部分为空，但保留字段
                    '新闻链接': news_item.get('url', ''),
                    '重要性级别': news_item.get('impt_lvl', 0),
                    '重要性标签': news_item.get('impt_tag', ''),
                    '链接类型': news_item.get('link_type', 0),
                })
                
                # 处理发布日期
                publish_date = datetime.fromtimestamp(int(news_timestamp))
                record['发布日期'] = self.format_date(publish_date, format_type='date_dash')
                record['发布小时'] = publish_date.hour
                
                # 添加时效性标记（用于后续分析，但不过滤）
                days_diff = (datetime.now() - publish_date).days
                record['天数差'] = days_diff
                record['是否3天内'] = days_diff <= 3
                
                parsed_news.append(record)
                
            except Exception:
                # 记录解析错误，但继续处理其他新闻
                print(f"    ⚠️ 解析新闻失败")
                continue
        
        return parsed_news
    
    def batch_scrape_news(self, target_date: str = None, 
                         max_stocks: int = 100, 
                         max_news_per_stock: int = 15,
                         market_filter: str = 'all') -> List[Dict[str, Any]]:
        """批量爬取新闻（多线程优化版）"""
        
        if not target_date:
            target_date = self.format_date(format_type='date')
        
        print(f"🚀 开始多线程爬取新闻 ({self.max_workers}线程, {self.max_concurrent}并发)")
        print(f"📅 目标日期: {target_date} | 🎯 最大股票数: {max_stocks}")
        print(f"📰 每股票最大新闻数: {max_news_per_stock} | 🏢 市场过滤: {market_filter}")
        
        # 加载股票数据
        stock_df = self.load_stock_data()
        if stock_df.empty:
            print("❌ 没有加载到股票数据")
            return []
        
        # 按市场过滤
        if market_filter != 'all':
            stock_df = stock_df[stock_df['code'].str.startswith(f'{market_filter}.')]
        
        # 限制股票数量
        if max_stocks < len(stock_df):
            stock_df = stock_df.head(max_stocks)
        
        # 准备股票信息列表
        stock_list = []
        for _, row in stock_df.iterrows():
            stock_list.append({
                'stock_id': str(row['stock_id']),
                'code': row['code'],
                'stock_name': row['stock_name'],
            })
        
        # 初始化进度跟踪
        self.processed_stocks = 0
        self.valid_news = 0
        self.total_news = 0
        self.skipped_stocks = 0
        self.error_count = 0
        self.start_time = time.time()
        
        # 创建进度条（线程安全）
        with self.progress_lock:
            self.progress_bar = tqdm(
                total=len(stock_list), 
                desc="新闻:0 跳过:0 错误:0",
                unit="股票",
                ncols=100,
                position=0,
                leave=True
            )
        
        all_news = []
        
        try:
            # 使用线程池并行处理
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_stock = {
                    executor.submit(self.get_stock_news, stock_info, max_news_per_stock): stock_info 
                    for stock_info in stock_list
                }
                
                # 收集结果
                for future in as_completed(future_to_stock):
                    try:
                        news_list = future.result()
                        if news_list:
                            all_news.extend(news_list)
                    except Exception:
                        # 错误已在get_stock_news中处理
                        pass
        finally:
            # 关闭进度条
            self.progress_bar.close()
        
        # 完成统计
        elapsed_time = time.time() - self.start_time
        effective_stocks = len(stock_list) - self.skipped_stocks - self.error_count
        
        print(f"\n📊 爬取完成")
        print(f"⏰ 总耗时: {int(elapsed_time//60)}分{int(elapsed_time%60)}秒")
        print(f"✅ 有效股票: {effective_stocks}/{len(stock_list)}")
        print(f"📭 跳过股票: {self.skipped_stocks}只 (无新闻数据)")
        print(f"❌ 失败股票: {self.error_count}只 (网络或其他错误)")
        print(f"📰 总新闻数: {len(all_news)}条 (原始获取: {self.total_news}条)")
        
        # 统计时效性分布
        if all_news:
            recent_news = len([n for n in all_news if n.get('是否3天内', False)])
            print(f"🕐 时效分布: 3天内{recent_news}条 ({recent_news/len(all_news)*100:.1f}%), 超过3天{len(all_news)-recent_news}条")
        
        if elapsed_time > 0:
            print(f"📈 平均效率: {len(all_news)/elapsed_time:.1f}条/秒")
        
        # 保存到CSV
        if all_news:
            self.save_news_to_csv(all_news, target_date, market_filter)
        
        return all_news
    
    def save_news_to_csv(self, news_data: List[Dict[str, Any]], 
                        date_str: str, market_filter: str = 'all'):
        """保存新闻数据到CSV文件"""
        if not news_data:
            print("⚠️ 没有新闻数据需要保存")
            return
        
        df = pd.DataFrame(news_data)
        
        # 按发布时间排序
        df = df.sort_values('发布时间', ascending=False)
        
        # 1. 保存所有新闻（3天内的）
        recent_df = df[df['是否3天内'] == True].copy()
        if len(recent_df) > 0:
            # 构建文件名
            timestamp = self.format_date(format_type='timestamp')
            if market_filter == 'all':
                filename = f"news_3days_{date_str}_{timestamp}.csv"
            else:
                filename = f"news_{market_filter}_3days_{date_str}_{timestamp}.csv"
            
            filepath = os.path.join(self.output_dir, filename)
            
            # 保存为CSV，包含BOM以支持中文
            recent_df.to_csv(filepath, index=False, encoding='utf-8-sig')
            print(f"✅ 3天内新闻已保存: {filename}")
            print(f"📊 共保存 {len(recent_df)} 条新闻记录")
        
        # 2. 单独保存当天新闻
        today_str = self.format_date(format_type='date_dash')
        today_df = df[df['发布日期'] == today_str].copy()
        if len(today_df) > 0:
            timestamp = self.format_date(format_type='timestamp')
            if market_filter == 'all':
                today_filename = f"news_today_{date_str}_{timestamp}.csv"
            else:
                today_filename = f"news_{market_filter}_today_{date_str}_{timestamp}.csv"
            
            today_filepath = os.path.join(self.output_dir, today_filename)
            today_df.to_csv(today_filepath, index=False, encoding='utf-8-sig')
            print(f"✅ 当天新闻已保存: {today_filename}")
            print(f"📊 当天新闻 {len(today_df)} 条")
        
        # 显示数据汇总（基于3天内新闻）
        if len(recent_df) > 0:
            print(f"\n📈 数据汇总 (3天内新闻):")
            print(f"总新闻: {len(recent_df)} 条 | 涉及股票: {recent_df['股票代码'].nunique()} 只 | 市场: {', '.join(recent_df['市场'].unique())}")
            
            if '新闻来源' in recent_df.columns:
                top_sources = recent_df['新闻来源'].value_counts().head(3)
                sources_str = ' | '.join([f"{source}({count})" for source, count in top_sources.items()])
                print(f"主要来源: {sources_str}")
            
            has_summary = len(recent_df[recent_df['新闻摘要'].str.len() > 0])
            print(f"有摘要: {has_summary}/{len(recent_df)} ({has_summary/len(recent_df)*100:.1f}%)")
            
            return filepath if len(recent_df) > 0 else None
        
        return None
    
    def cleanup_old_news(self, keep_days: int = 3):
        """清理旧新闻文件，保持指定天数的数据"""
        try:
            output_dir = self.output_dir
            if not os.path.exists(output_dir):
                return
            
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            cutoff_str = self.format_date(cutoff_date, format_type='date')
            
            removed_count = 0
            for filename in os.listdir(output_dir):
                if filename.startswith('news_') and filename.endswith('.csv'):
                    # 提取文件中的日期
                    parts = filename.split('_')
                    if len(parts) >= 2:
                        try:
                            file_date = parts[1]  # news_20250720_xxxx.csv
                            if len(file_date) == 8 and file_date < cutoff_str:
                                file_path = os.path.join(output_dir, filename)
                                os.remove(file_path)
                                removed_count += 1
                                print(f"🗑️ 删除旧文件: {filename}")
                        except:
                            continue
            
            if removed_count > 0:
                print(f"✅ 清理完成，删除了 {removed_count} 个旧文件")
            else:
                print("📁 没有需要清理的旧文件")
                
        except Exception as e:
            print(f"⚠️ 清理旧文件失败: {e}")
    
    def check_existing_data(self) -> bool:
        """检查是否存在历史数据"""
        if not os.path.exists(self.output_dir):
            return False
        
        # 检查是否有3天内的新闻文件
        try:
            cutoff_date = datetime.now() - timedelta(days=3)
            cutoff_str = self.format_date(cutoff_date, format_type='date')
            
            for filename in os.listdir(self.output_dir):
                if filename.startswith('news_') and filename.endswith('.csv'):
                    parts = filename.split('_')
                    if len(parts) >= 2 and len(parts[1]) == 8 and parts[1] >= cutoff_str:
                        print(f"📊 发现近期数据文件")
                        return True
            return False
        except Exception:
            return False
    
    def run_auto_mode(self):
        """自动模式：智能数据管理 + 定时运行"""
        print("🤖 启动自动模式")
        
        # 检查是否存在历史数据
        has_existing_data = self.check_existing_data()
        
        if not has_existing_data:
            print("🆕 首次运行，爬取3天历史数据")
            # 首次运行，爬取3天数据
            for i in range(3):
                target_date = self.format_date(datetime.now() - timedelta(days=i), format_type='date')
                print(f"\n📅 爬取日期: {target_date}")
                
                # 分别爬取港股和美股
                self.batch_scrape_news(
                    target_date=target_date,
                    max_stocks=200,
                    max_news_per_stock=15,
                    market_filter='HK'
                )
                
                self.batch_scrape_news(
                    target_date=target_date,
                    max_stocks=200,
                    max_news_per_stock=15,
                    market_filter='US'
                )
                
                time.sleep(2)  # 避免请求过快
        else:
            print("📈 增量更新模式，爬取今日数据")
            # 增量更新，只爬取今天的数据
            today = self.format_date(format_type='date')
            
            # 分别爬取港股和美股
            self.batch_scrape_news(
                target_date=today,
                max_stocks=200,
                max_news_per_stock=15,
                market_filter='HK'
            )
            
            self.batch_scrape_news(
                target_date=today,
                max_stocks=200,
                max_news_per_stock=15,
                market_filter='US'
            )
        
        # 清理3天前的旧数据
        print("\n🧹 清理旧数据")
        self.cleanup_old_news(keep_days=3)
        
        print("✅ 自动模式运行完成")
    
    def run_test_mode(self):
        """测试模式：爬取100只股票验证功能"""
        print("🧪 启动测试模式")
        
        today = self.format_date(format_type='date')
        
        # 测试爬取：50只港股 + 50只美股
        print("\n--- 测试港股 ---")
        self.batch_scrape_news(
            target_date=today,
            max_stocks=50,
            max_news_per_stock=10,
            market_filter='HK'
        )
        
        print("\n--- 测试美股 ---")
        self.batch_scrape_news(
            target_date=today,
            max_stocks=50,
            max_news_per_stock=10,
            market_filter='US'
        )
        
        print("✅ 测试模式运行完成")
    
    def run_full_test_mode(self):
        """全量测试模式：爬取所有港美股3天新闻"""
        print("🚀 启动全量测试模式")
        
        today = self.format_date(format_type='date')
        
        # 全量爬取：所有港股
        print("\n--- 全量爬取港股 ---")
        self.batch_scrape_news(
            target_date=today,
            max_stocks=99999,  # 不限制数量
            max_news_per_stock=15,  # 每只股票最多15条新闻
            market_filter='HK'
        )
        
        # 全量爬取：所有美股
        print("\n--- 全量爬取美股 ---")
        self.batch_scrape_news(
            target_date=today,
            max_stocks=99999,  # 不限制数量
            max_news_per_stock=15,  # 每只股票最多15条新闻
            market_filter='US'
        )
        
        print("✅ 全量测试模式运行完成")
    
    def schedule_auto_mode(self):
        """调度自动模式，每天晚上8点北京时间运行"""
        # 设置北京时区
        beijing_tz = pytz.timezone('Asia/Shanghai')
        
        def job():
            print(f"\n⏰ {datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')} 北京时间 - 开始定时任务")
            self.run_auto_mode()
        
        # 每天晚上8点运行
        schedule.every().day.at("20:00").do(job)
        
        print("📅 定时任务已设置：每天晚上8点北京时间运行")
        print(f"🕐 当前北京时间：{datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 立即运行一次
        print("\n🚀 首次运行...")
        job()
        
        # 持续监听调度
        print("\n⏳ 等待下次调度...")
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次

def main():
    """主函数：解析命令行参数并运行相应模式"""
    parser = argparse.ArgumentParser(description='富途新闻爬虫 - Docker版本')
    parser.add_argument('--mode', choices=['auto', 'test', 'fulltest'], default='test',
                       help='运行模式：auto(自动定时) 或 test(测试运行) 或 fulltest(全量测试)')
    parser.add_argument('--output-dir', default=None,
                       help='输出目录路径，默认为当前目录下的output文件夹')
    parser.add_argument('--max-workers', type=int, default=None,
                       help='最大工作线程数')
    parser.add_argument('--max-concurrent', type=int, default=None,
                       help='最大并发请求数')
    parser.add_argument('--request-delay', type=float, default=None,
                       help='请求延迟(秒)')
    parser.add_argument('--use-proxy', choices=['true', 'false'], default=None,
                       help='是否使用代理池')
    
    args = parser.parse_args()
    
    # 从环境变量和命令行参数获取配置
    def get_config(env_name, arg_value, default_value, converter=str):
        if arg_value is not None:
            return converter(arg_value)
        env_value = os.getenv(env_name)
        if env_value is not None:
            return converter(env_value)
        return default_value
    
    # 并发参数配置
    max_workers = get_config('MAX_WORKERS', args.max_workers, 30, int)
    max_concurrent = get_config('MAX_CONCURRENT', args.max_concurrent, 25, int)
    request_delay = get_config('REQUEST_DELAY', args.request_delay, 0.1, float)
    
    # 代理配置
    use_proxy_str = get_config('USE_PROXY', args.use_proxy, 'true', str)
    use_proxy = use_proxy_str.lower() in ['true', '1', 'yes']
    
    # 输出目录配置
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.getenv('OUTPUT_DIR')
        if not output_dir:
            # 根据运行环境自动选择
            if os.path.exists('/.dockerenv'):  # Docker环境检测
                output_dir = '/etc/FUTUNews/output'
            else:  # 本地开发环境
                output_dir = 'output'
    
    # 创建爬虫实例
    scraper = FutuNewsScraper(
        max_workers=max_workers,
        max_concurrent=max_concurrent,
        request_delay=request_delay,
        output_dir=output_dir,
        use_proxy=use_proxy
    )
    
    print("=== 富途新闻爬虫 Docker版 ===")
    print(f"🎯 运行模式: {args.mode}")  
    print(f"📁 输出目录: {scraper.output_dir}")
    print(f"🚀 并发配置: {max_workers}线程, {max_concurrent}并发, {request_delay}s延迟")
    print(f"🌐 代理配置: {'启用' if use_proxy else '禁用'}")
    
    # 调试环境变量读取
    print(f"🔍 环境变量调试:")
    print(f"  MAX_WORKERS环境变量: {os.getenv('MAX_WORKERS', 'None')}")
    print(f"  MAX_CONCURRENT环境变量: {os.getenv('MAX_CONCURRENT', 'None')}")
    print(f"  USE_PROXY环境变量: {os.getenv('USE_PROXY', 'None')}")
    print(f"  实际使用的use_proxy值: {use_proxy} (来源: {use_proxy_str})")
    
    try:
        if args.mode == 'auto':
            # 自动模式：定时运行
            scraper.schedule_auto_mode()
        elif args.mode == 'test':
            # 测试模式：一次性运行
            scraper.run_test_mode()
        elif args.mode == 'fulltest':
            # 全量测试模式：爬取所有港美股
            scraper.run_full_test_mode()
        else:
            print("❌ 无效的运行模式")
            return 1
            
    except KeyboardInterrupt:
        print("\n👋 程序被用户中断")
        return 0
    except Exception as e:
        print(f"❌ 程序运行异常: {e}")
        return 1
    
    print("\n🎉 程序运行完成！")
    return 0


if __name__ == "__main__":
    exit(main())
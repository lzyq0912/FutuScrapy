#!/usr/bin/env python3
"""
富途新闻爬虫 Docker 启动脚本
用法：
  python run.py test    # 运行测试模式（100只股票）
  python run.py auto    # 运行自动模式（每天8PM定时运行）
  python run.py init    # 初始化目录
  python run.py stop    # 停止所有服务
  python run.py logs    # 查看日志
  python run.py status  # 查看状态
  python run.py config  # 显示配置信息
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime

def run_command(cmd, check=True):
    """执行shell命令"""
    print(f"🔧 执行命令: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, check=check, 
                              capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ 命令执行失败: {e}")
        if e.stderr:
            print(f"错误信息: {e.stderr}")
        return None

def show_config():
    """显示当前配置"""
    print("⚙️ 当前Docker配置:")
    print("\n📊 并发参数:")
    print("  MAX_WORKERS=30        # 最大工作线程数")
    print("  MAX_CONCURRENT=25     # 最大并发请求数") 
    print("  REQUEST_DELAY=0.1     # 请求延迟(秒)")
    
    print("\n🌐 代理配置:")
    print("  USE_PROXY=true        # 是否使用代理池")
    
    print("\n📁 输出配置:")
    print("  OUTPUT_DIR=/etc/FUTUNews/output  # 输出目录")
    
    print("\n🔧 修改方法:")
    print("1. 直接编辑 docker-compose.yml 中的环境变量")
    print("2. 或使用命令行参数运行:")
    print("   python futu_news_scraper.py --max-workers 20 --use-proxy false")
    
    print("\n📖 详细说明:")
    print("- MAX_WORKERS: 控制线程池大小，建议10-50")
    print("- MAX_CONCURRENT: 控制同时请求数，建议5-30")
    print("- REQUEST_DELAY: 请求间延迟，代理池可用0.1s，无代理建议0.5s+")
    print("- USE_PROXY: true启用代理池，false禁用代理")

def init_directories():
    """初始化目录"""
    print("📁 初始化目录...")
    
    # 确保输出目录存在
    output_dir = "/etc/FUTUNews/output"
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"✅ 目录创建成功: {output_dir}")
    except PermissionError:
        print(f"⚠️ 权限不足，请使用sudo创建目录: {output_dir}")
        print(f"   建议运行: sudo mkdir -p {output_dir} && sudo chmod 755 {output_dir}")
        return False
    
    return True

def build_image():
    """构建Docker镜像"""
    print("🔨 构建Docker镜像...")
    # 添加时间戳参数强制重建，避免缓存问题
    import time
    build_date = str(int(time.time()))
    return run_command(f"docker-compose build --no-cache --build-arg BUILD_DATE={build_date}")

def run_test():
    """运行测试模式"""
    print("🧪 启动测试模式...")
    
    if not build_image():
        return False
    
    # 清理可能存在的测试容器
    run_command("docker-compose --profile test down", check=False)
    
    # 使用 run --rm 运行测试，完成后自动删除容器
    print("📦 运行测试容器（完成后自动清理）...")
    result = run_command("docker-compose run --rm futu-news-test")
    
    if result:
        print("✅ 测试完成，容器已自动清理")
        return True
    else:
        print("❌ 测试失败")
        return False

def run_auto():
    """运行自动模式"""
    print("🤖 启动自动模式...")
    
    if not build_image():
        return False
    
    # 停止现有的自动容器
    run_command("docker-compose --profile auto down", check=False)
    
    # 后台运行自动模式
    return run_command("docker-compose --profile auto up -d")

def clean_docker():
    """清理Docker资源"""
    print("🧹 清理Docker资源...")
    
    # 停止并删除容器
    run_command("docker-compose --profile test down", check=False)
    run_command("docker-compose --profile auto down", check=False)
    run_command("docker-compose --profile init down", check=False)
    
    # 删除相关镜像
    run_command("docker images | grep futu-news | awk '{print $3}' | xargs -r docker rmi -f", check=False)
    
    # 清理悬挂镜像和缓存
    run_command("docker system prune -f", check=False)
    
    print("✅ Docker资源清理完成")

def stop_all():
    """停止所有服务"""
    print("🛑 停止所有服务...")
    run_command("docker-compose --profile test down", check=False)
    run_command("docker-compose --profile auto down", check=False)
    run_command("docker-compose --profile init down", check=False)

def show_logs():
    """显示日志"""
    print("📋 显示日志...")
    
    # 检查哪个容器在运行
    result = run_command("docker ps --format '{{.Names}}' | grep futu-news", check=False)
    if result and result.stdout.strip():
        containers = result.stdout.strip().split('\n')
        for container in containers:
            print(f"\n--- {container} 日志 ---")
            run_command(f"docker logs --tail 50 {container}")
    else:
        print("📭 没有运行中的富途新闻爬虫容器")

def show_status():
    """显示状态"""
    print("📊 服务状态:")
    
    # 显示容器状态
    result = run_command("docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' | grep futu-news", check=False)
    if not result or not result.stdout.strip():
        print("📭 没有富途新闻爬虫容器")
        return
    
    print(result.stdout)
    
    # 显示输出目录状态
    output_dir = "/etc/FUTUNews/output"
    if os.path.exists(output_dir):
        try:
            files = [f for f in os.listdir(output_dir) if f.endswith('.csv')]
            print(f"\n📁 输出目录: {output_dir}")
            print(f"📊 CSV文件数量: {len(files)}")
            
            if files:
                # 显示最近的文件
                files.sort(reverse=True)
                print("🕐 最近的文件:")
                for f in files[:5]:
                    file_path = os.path.join(output_dir, f)
                    try:
                        stat = os.stat(file_path)
                        size_mb = stat.st_size / (1024 * 1024)
                        mtime = datetime.fromtimestamp(stat.st_mtime)
                        print(f"  - {f} ({size_mb:.1f}MB, {mtime.strftime('%Y-%m-%d %H:%M')})")
                    except:
                        print(f"  - {f}")
        except PermissionError:
            print(f"⚠️ 无权限访问目录: {output_dir}")
    else:
        print(f"❌ 输出目录不存在: {output_dir}")

def main():
    parser = argparse.ArgumentParser(description='富途新闻爬虫 Docker 管理脚本')
    parser.add_argument('action', choices=['test', 'auto', 'init', 'stop', 'logs', 'status', 'config', 'clean'],
                       help='要执行的操作')
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
    print("=== 富途新闻爬虫 Docker 管理器 ===")
    print(f"🎯 操作: {args.action}")
    print(f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.action == 'clean':
        clean_docker()
    
    elif args.action == 'init':
        if init_directories():
            print("✅ 初始化完成")
        else:
            print("❌ 初始化失败")
    
    elif args.action == 'test':
        if not init_directories():
            return
        
        if run_test():
            print("✅ 测试模式启动成功")
        else:
            print("❌ 测试模式启动失败")
    
    elif args.action == 'auto':
        if not init_directories():
            return
        
        if run_auto():
            print("✅ 自动模式启动成功")
            print("📅 爬虫将在每天晚上8点北京时间运行")
            print("📋 查看日志: python run.py logs")
        else:
            print("❌ 自动模式启动失败")
    
    elif args.action == 'stop':
        stop_all()
        print("✅ 所有服务已停止")
    
    elif args.action == 'logs':
        show_logs()
    
    elif args.action == 'status':
        show_status()
    
    elif args.action == 'config':
        show_config()
    
    else:
        print(f"❌ 未知操作: {args.action}")

print("\n=== 使用说明 ===")
print("🔧 修复Docker缓存问题的推荐流程:")
print("1. python run.py clean    # 清理所有Docker资源")
print("2. python run.py test     # 重新构建并测试")
print("3. python run.py auto     # 启动自动模式")
print("\n如果仍有问题，请检查futu_news_scraper.py是否为最新版本")

if __name__ == '__main__':
    main()
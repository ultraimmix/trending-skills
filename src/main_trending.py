#!/usr/bin/env python3
"""
Skills Trending 主入口
自动获取 skills.sh 技能排行榜，AI 分析，生成趋势报告并发送邮件
"""
import sys
import os
from datetime import datetime, timezone

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.config import (
    ZHIPU_API_KEY,
    RESEND_API_KEY,
    EMAIL_TO,
    RESEND_FROM_EMAIL,
    DB_PATH,
    DB_RETENTION_DAYS,
    TOP_N_DETAILS
)
from src.skills_fetcher import SkillsFetcher
from src.detail_fetcher import DetailFetcher
from src.claude_summarizer import ClaudeSummarizer
from src.database import Database
from src.trend_analyzer import TrendAnalyzer
from src.html_reporter import HTMLReporter
from src.resend_sender import ResendSender


def print_banner():
    """打印程序横幅"""
    banner = """
╔════════════════════════════════════════════════════════════╗
║                                                              ║
║   Skills Trending Daily - 技能趋势追踪系统                   ║
║                                                              ║
║   自动获取 skills.sh 排行榜 · AI 智能分析                    ║
║   趋势计算 · HTML 邮件报告 · Resend 发送                    ║
║                                                              ║
╚════════════════════════════════════════════════════════════╝
"""
    print(banner)


def get_today_date() -> str:
    """获取今日日期 YYYY-MM-DD"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    """主函数"""
    print_banner()

    # 检查环境变量
    if not ZHIPU_API_KEY:
        print("❌ 错误: ZHIPU_API_KEY 环境变量未设置")
        print("   请设置 Claude API 的 Key")
        sys.exit(1)

    if not RESEND_API_KEY:
        print("❌ 错误: RESEND_API_KEY 环境变量未设置")
        print("   请设置 Resend API Key")
        sys.exit(1)

    if not EMAIL_TO:
        print("❌ 错误: EMAIL_TO 环境变量未设置")
        print("   请设置收件人邮箱")
        sys.exit(1)

    # 获取今日日期
    today = get_today_date()
    print(f"[目标日期] {today}")
    print(f"   (北京时间: {datetime.now(timezone.utc)} + 8h)")
    print()

    try:
        # 1. 获取今日榜单
        print(f"[步骤 1/7] 获取技能排行榜...")
        fetcher = SkillsFetcher()
        today_skills = fetcher.fetch()
        print(f"   成功获取 {len(today_skills)} 个技能")
        print()

        # 2. 抓取 Top N 详情
        print(f"[步骤 2/7] 抓取 Top {TOP_N_DETAILS} 详情...")
        detail_fetcher = DetailFetcher()
        top_details = detail_fetcher.fetch_top20_details(today_skills)
        print(f"   成功抓取 {len(top_details)} 个技能详情")
        print()

        # 3. AI 总结和分类
        print(f"[步骤 3/7] AI 分析和分类...")
        summarizer = ClaudeSummarizer()
        ai_summaries = summarizer.summarize_and_classify(top_details)

        # 构建 AI 摘要映射
        ai_summary_map = {s["name"]: s for s in ai_summaries}
        print()

        # 4. 保存到数据库
        print(f"[步骤 4/7] 保存到数据库...")
        db = Database(DB_PATH)
        db.init_db()
        db.save_skill_details(ai_summaries)
        print()

        # 5. 计算趋势
        print(f"[步骤 5/7] 计算趋势...")
        analyzer = TrendAnalyzer(db)
        trends = analyzer.calculate_trends(today_skills, today, ai_summary_map)

        # 输出趋势摘要
        print(f"   Top 20: {len(trends['top_20'])} 个")
        print(f"   上升: {len(trends['rising_top5'])} 个")
        print(f"   下降: {len(trends['falling_top5'])} 个")
        print(f"   新晋: {len(trends['new_entries'])} 个")
        print(f"   跌出: {len(trends['dropped_entries'])} 个")
        print(f"   暴涨: {len(trends['surging'])} 个")
        print()

        # 6. 生成 HTML 邮件
        print(f"[步骤 6/7] 生成 HTML 邮件...")
        reporter = HTMLReporter()
        html_content = reporter.generate_email_html(trends, today)
        print(f"   HTML 长度: {len(html_content)} 字符")
        print()

        # 7. 发送邮件
        print(f"[步骤 7/7] 发送邮件...")
        sender = ResendSender(RESEND_API_KEY)
        result = sender.send_email(
            to=EMAIL_TO,
            subject=f"📊 Skills Trending Daily - {today}",
            html_content=html_content,
            from_email=RESEND_FROM_EMAIL
        )

        if result["success"]:
            print(f"   ✅ 邮件发送成功! ID: {result['id']}")
        else:
            print(f"   ❌ 邮件发送失败: {result['message']}")
        print()

        # 8. 清理过期数据
        print(f"[清理] 清理 {DB_RETENTION_DAYS} 天前的数据...")
        deleted = db.cleanup_old_data(DB_RETENTION_DAYS)
        print()

        # 完成 - 简洁输出（避免终端字符宽度问题）
        print()
        print("=" * 40)
        print("  ✅ 任务完成!")
        print("=" * 40)
        print(f"  日期:   {today}")
        print(f"  技能数: {len(today_skills)}")
        print(f"  新晋:   {len(trends['new_entries'])}")
        print(f"  跌出:   {len(trends['dropped_entries'])}")
        print(f"  暴涨:   {len(trends['surging'])}")
        print("=" * 40)

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(130)

    except Exception as e:
        print(f"\n[错误] 执行过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

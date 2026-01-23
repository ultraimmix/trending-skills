"""
Skills Fetcher - 从 skills.sh/trending 获取技能排行榜
"""
import re
from typing import Dict, List
import requests

from src.config import SKILLS_TRENDING_URL, SKILLS_BASE_URL


class SkillsFetcher:
    """从 skills.sh/trending 获取排行榜"""

    def __init__(self, timeout: int = 30):
        """初始化"""
        self.base_url = SKILLS_BASE_URL
        self.trending_url = SKILLS_TRENDING_URL
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; SkillsTrendingBot/1.0)"
        })

    def fetch(self) -> List[Dict]:
        """
        获取 Top 100 技能列表

        Returns:
            [
                {
                    "rank": 1,
                    "name": "remotion-best-practices",
                    "owner": "remotion-dev/skills",
                    "installs": 5600,
                    "url": "https://skills.sh/remotion-dev/skills/remotion-best-practices"
                },
                ...
            ]
        """
        print(f"📡 正在获取榜单: {self.trending_url}")

        try:
            html_content = self.fetch_trending_page()
            skills = self.parse_leaderboard(html_content)

            if skills:
                print(f"✅ 成功获取 {len(skills)} 个技能")
                return skills

            raise Exception("无法从页面解析技能列表")

        except Exception as e:
            print(f"❌ 获取榜单失败: {e}")
            raise

    def fetch_trending_page(self) -> str:
        """获取页面 HTML"""
        try:
            response = self.session.get(self.trending_url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            raise Exception(f"请求失败: {e}")

    def parse_leaderboard(self, html_content: str) -> List[Dict]:
        """
        解析排行榜 - skills.sh 页面使用 Markdown 表格格式

        格式示例:
        ## Skills Leaderboard
        ...
        1\\n\\n### remotion-best-practices\\n\\nremotion-dev/skills\\n\\n5.6K
        2\\n\\n### vercel-react-best-practices\\n\\n...
        """
        skills = []

        # 查找排行榜开始位置
        # 查找 "## Skills Leaderboard" 标题之后的内容
        leaderboard_start = html_content.find("## Skills Leaderboard")
        if leaderboard_start == -1:
            raise Exception("未找到 Skills Leaderboard 标题")

        # 提取排行榜部分内容
        content = html_content[leaderboard_start:]

        # 使用正则表达式解析每个技能条目
        # 格式: 数字\n\n### skill-name\n\nowner\n\ninstalls
        pattern = r'(\d+)\n\n### ([\w-]+)\n\n([\w-]+/[\w-]+)\n\n([\d.]+K?)'

        matches = re.findall(pattern, content)

        for match in matches:
            rank = int(match[0])
            name = match[1]
            owner = match[2]
            installs_str = match[3]

            # 处理安装量 (5.6K -> 5600)
            installs = self._parse_installs(installs_str)

            skills.append({
                "rank": rank,
                "name": name,
                "owner": owner,
                "installs": installs,
                "url": f"{self.base_url}/{owner}/{name}"
            })

        return skills

    def _parse_installs(self, installs_str: str) -> int:
        """解析安装量字符串"""
        installs_str = installs_str.strip().upper()

        if "K" in installs_str:
            return int(float(installs_str.replace("K", "")) * 1000)

        try:
            return int(installs_str)
        except ValueError:
            return 0

    def get_date_range(self) -> tuple:
        """获取可用日期范围"""
        return None, None


def fetch_skills() -> List[Dict]:
    """便捷函数：获取技能列表"""
    fetcher = SkillsFetcher()
    return fetcher.fetch()

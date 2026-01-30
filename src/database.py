"""
SQLite 数据库操作模块
管理技能趋势数据的存储和查询
"""
import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.config import DB_PATH, DB_RETENTION_DAYS


class Database:
    """SQLite 数据库操作类"""

    def __init__(self, db_path: str = None):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认使用配置中的路径
        """
        self.db_path = db_path or DB_PATH
        self._ensure_db_dir()
        self.conn = None

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    def connect(self):
        """建立数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 返回字典格式

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def init_db(self) -> None:
        """初始化数据库表"""
        self.connect()
        cursor = self.conn.cursor()

        # 1. skills_snapshot - 快照表（每次抓取一条记录）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                date TEXT NOT NULL,
                rank INTEGER NOT NULL,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                installs INTEGER NOT NULL,
                installs_delta INTEGER DEFAULT 0,
                installs_rate REAL DEFAULT 0,
                rank_delta INTEGER DEFAULT 0,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_time, name)
            )
        """)

        # 兼容旧表：如果存在 skills_daily 则迁移数据后删除
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='skills_daily'
        """)
        if cursor.fetchone():
            # 检查是否已迁移
            cursor.execute("SELECT COUNT(*) FROM skills_snapshot")
            if cursor.fetchone()[0] == 0:
                print("📦 迁移旧数据 skills_daily -> skills_snapshot...")
                cursor.execute("""
                    INSERT OR IGNORE INTO skills_snapshot
                    (snapshot_time, date, rank, name, owner, installs, installs_delta, installs_rate, rank_delta, url, created_at)
                    SELECT
                        date || ' 00:00:00' as snapshot_time,
                        date, rank, name, owner, installs, installs_delta, installs_rate, rank_delta, url, created_at
                    FROM skills_daily
                """)
            # 删除旧表
            print("🗑️ 删除旧表 skills_daily...")
            cursor.execute("DROP TABLE skills_daily")

        # 2. skills_details - 技能详情缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                summary TEXT NOT NULL,
                description TEXT,
                use_case TEXT,
                solves TEXT,
                category TEXT NOT NULL,
                category_zh TEXT NOT NULL,
                rules_count INTEGER,
                owner TEXT NOT NULL,
                url TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. skills_history - 历史趋势表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                date TEXT NOT NULL,
                rank INTEGER NOT NULL,
                installs INTEGER NOT NULL,
                UNIQUE(skill_name, date)
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_time ON skills_snapshot(snapshot_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_date ON skills_snapshot(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_name ON skills_snapshot(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_rank ON skills_snapshot(snapshot_time, rank)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_details_category ON skills_details(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_details_owner ON skills_details(owner)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_name ON skills_history(skill_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_date ON skills_history(date)")

        self.conn.commit()
        print(f"✅ 数据库初始化完成: {self.db_path}")

    def save_snapshot(self, snapshot_time: str, date: str, skills: List[Dict]) -> None:
        """
        保存快照数据

        Args:
            snapshot_time: 快照时间 YYYY-MM-DD HH:MM:SS
            date: 日期 YYYY-MM-DD
            skills: 技能列表
        """
        self.connect()
        cursor = self.conn.cursor()

        for skill in skills:
            cursor.execute("""
                INSERT OR REPLACE INTO skills_snapshot
                (snapshot_time, date, rank, name, owner, installs, installs_delta, installs_rate, rank_delta, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_time,
                date,
                skill.get("rank"),
                skill.get("name"),
                skill.get("owner"),
                skill.get("installs"),
                skill.get("installs_delta", 0),
                skill.get("installs_rate", 0),
                skill.get("rank_delta", 0),
                skill.get("url", "")
            ))

            # 同时写入历史表
            cursor.execute("""
                INSERT OR REPLACE INTO skills_history
                (skill_name, date, rank, installs)
                VALUES (?, ?, ?, ?)
            """, (
                skill.get("name"),
                date,
                skill.get("rank"),
                skill.get("installs")
            ))

        self.conn.commit()
        print(f"✅ 保存快照数据: {len(skills)} 条记录 ({snapshot_time})")

    # 兼容旧方法
    def save_today_data(self, date: str, skills: List[Dict]) -> None:
        """兼容旧方法，自动生成快照时间"""
        snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_snapshot(snapshot_time, date, skills)

    def get_skills_by_date(self, date: str) -> List[Dict]:
        """
        获取指定日期最新一次快照的数据

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            技能列表
        """
        self.connect()
        cursor = self.conn.cursor()

        # 获取该日期最新的快照时间
        cursor.execute("""
            SELECT MAX(snapshot_time) as latest
            FROM skills_snapshot
            WHERE date = ?
        """, (date,))

        row = cursor.fetchone()
        if not row or not row["latest"]:
            return []

        latest_time = row["latest"]

        cursor.execute("""
            SELECT rank, name, owner, installs, installs_delta, installs_rate, rank_delta, url
            FROM skills_snapshot
            WHERE snapshot_time = ?
            ORDER BY rank
        """, (latest_time,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_last_snapshot(self, before_time: str = None) -> List[Dict]:
        """
        获取上一次快照的数据

        Args:
            before_time: 在此时间之前的快照，格式 YYYY-MM-DD HH:MM:SS
                        如果不指定，返回最新的快照

        Returns:
            技能列表
        """
        self.connect()
        cursor = self.conn.cursor()

        if before_time:
            # 获取指定时间之前的最新快照
            cursor.execute("""
                SELECT DISTINCT snapshot_time
                FROM skills_snapshot
                WHERE snapshot_time < ?
                ORDER BY snapshot_time DESC
                LIMIT 1
            """, (before_time,))
        else:
            # 获取最新的快照
            cursor.execute("""
                SELECT DISTINCT snapshot_time
                FROM skills_snapshot
                ORDER BY snapshot_time DESC
                LIMIT 1
            """)

        row = cursor.fetchone()
        if not row:
            return []

        snapshot_time = row["snapshot_time"]

        cursor.execute("""
            SELECT rank, name, owner, installs, installs_delta, installs_rate, rank_delta, url
            FROM skills_snapshot
            WHERE snapshot_time = ?
            ORDER BY rank
        """, (snapshot_time,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_yesterday_data(self, date: str) -> List[Dict]:
        """
        获取上一次快照的数据（兼容旧方法）

        Args:
            date: 当前日期（不再使用，保留参数兼容）

        Returns:
            上一次快照的技能列表
        """
        # 获取当前时间，查找之前的快照
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self.get_last_snapshot(before_time=current_time)

    def save_skill_details(self, details: List[Dict]) -> None:
        """
        保存/更新技能详情

        Args:
            details: AI 分析的技能详情列表
        """
        self.connect()
        cursor = self.conn.cursor()

        for detail in details:
            solves_json = json.dumps(detail.get("solves", []), ensure_ascii=False)

            cursor.execute("""
                INSERT OR REPLACE INTO skills_details
                (name, summary, description, use_case, solves, category, category_zh, rules_count, owner, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                detail.get("name"),
                detail.get("summary"),
                detail.get("description"),
                detail.get("use_case"),
                solves_json,
                detail.get("category"),
                detail.get("category_zh"),
                detail.get("rules_count"),
                detail.get("owner"),
                detail.get("url")
            ))

        self.conn.commit()
        print(f"✅ 保存技能详情: {len(details)} 条记录")

    def get_skill_details(self, name: str) -> Optional[Dict]:
        """
        获取技能详情

        Args:
            name: 技能名称

        Returns:
            技能详情字典，如果不存在返回 None
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT name, summary, description, use_case, solves, category, category_zh, rules_count, owner, url
            FROM skills_details
            WHERE name = ?
        """, (name,))

        row = cursor.fetchone()
        if row:
            result = dict(row)
            # 解析 JSON 字段
            if result.get("solves"):
                result["solves"] = json.loads(result["solves"])
            return result
        return None

    def get_all_skill_details(self) -> Dict[str, Dict]:
        """
        获取所有技能详情

        Returns:
            {skill_name: detail_dict} 的字典
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT name, summary, description, use_case, solves, category, category_zh, rules_count, owner, url
            FROM skills_details
        """)

        result = {}
        for row in cursor.fetchall():
            detail = dict(row)
            if detail.get("solves"):
                detail["solves"] = json.loads(detail["solves"])
            result[detail["name"]] = detail

        return result

    def cleanup_old_data(self, days: int = None) -> int:
        """
        清理过期数据

        Args:
            days: 保留天数，默认使用配置中的值

        Returns:
            删除的记录数
        """
        retention_days = days or DB_RETENTION_DAYS
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")

        self.connect()
        cursor = self.conn.cursor()

        # 清理快照数据
        cursor.execute("""
            DELETE FROM skills_snapshot
            WHERE date < ?
        """, (cutoff_date,))

        deleted_snapshot = cursor.rowcount

        # 清理历史数据
        cursor.execute("""
            DELETE FROM skills_history
            WHERE date < ?
        """, (cutoff_date,))

        deleted_history = cursor.rowcount

        self.conn.commit()
        total_deleted = deleted_snapshot + deleted_history

        if total_deleted > 0:
            print(f"🗑️ 清理过期数据: {total_deleted} 条记录 (早于 {cutoff_date})")

        return total_deleted

    def get_skill_history(self, name: str, days: int = 7) -> List[Dict]:
        """
        获取技能历史趋势

        Args:
            name: 技能名称
            days: 查询天数

        Returns:
            历史数据列表，按日期升序排列
        """
        self.connect()
        cursor = self.conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT date, rank, installs
            FROM skills_history
            WHERE skill_name = ? AND date >= ?
            ORDER BY date ASC
        """, (name, cutoff_date))

        return [dict(row) for row in cursor.fetchall()]

    def get_available_dates(self, limit: int = 30) -> List[str]:
        """
        获取可用的日期列表

        Args:
            limit: 返回的最大日期数

        Returns:
            日期列表，按降序排列（最新的在前）
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT DISTINCT date
            FROM skills_snapshot
            ORDER BY date DESC
            LIMIT ?
        """, (limit,))

        return [row["date"] for row in cursor.fetchall()]

    def get_available_snapshots(self, limit: int = 50) -> List[Dict]:
        """
        获取可用的快照列表

        Args:
            limit: 返回的最大快照数

        Returns:
            快照列表，包含 snapshot_time 和 date
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT DISTINCT snapshot_time, date, COUNT(*) as skill_count
            FROM skills_snapshot
            GROUP BY snapshot_time
            ORDER BY snapshot_time DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    def get_category_stats(self, date: str) -> List[Dict]:
        """
        获取指定日期的分类统计

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            分类统计列表
        """
        self.connect()
        cursor = self.conn.cursor()

        # 获取该日期最新快照时间
        cursor.execute("""
            SELECT MAX(snapshot_time) as latest
            FROM skills_snapshot
            WHERE date = ?
        """, (date,))

        row = cursor.fetchone()
        if not row or not row["latest"]:
            return []

        latest_time = row["latest"]

        cursor.execute("""
            SELECT d.category, d.category_zh, COUNT(*) as count
            FROM skills_snapshot s
            LEFT JOIN skills_details d ON s.name = d.name
            WHERE s.snapshot_time = ?
            GROUP BY d.category
            ORDER BY count DESC
        """, (latest_time,))

        return [dict(row) for row in cursor.fetchall()]

    def get_top_movers(self, date: str, limit: int = 5) -> Dict[str, List[Dict]]:
        """
        获取排名变化最大的技能

        Args:
            date: 日期 YYYY-MM-DD
            limit: 返回数量

        Returns:
            {"rising": [...], "falling": [...]}
        """
        self.connect()
        cursor = self.conn.cursor()

        # 获取该日期最新快照时间
        cursor.execute("""
            SELECT MAX(snapshot_time) as latest
            FROM skills_snapshot
            WHERE date = ?
        """, (date,))

        row = cursor.fetchone()
        if not row or not row["latest"]:
            return {"rising": [], "falling": []}

        latest_time = row["latest"]

        # 上升最多
        cursor.execute("""
            SELECT s.name, s.rank, s.rank_delta, d.summary, d.category
            FROM skills_snapshot s
            LEFT JOIN skills_details d ON s.name = d.name
            WHERE s.snapshot_time = ? AND s.rank_delta > 0
            ORDER BY s.rank_delta DESC, s.rank ASC
            LIMIT ?
        """, (latest_time, limit))

        rising = [dict(row) for row in cursor.fetchall()]

        # 下降最多
        cursor.execute("""
            SELECT s.name, s.rank, s.rank_delta, d.summary, d.category
            FROM skills_snapshot s
            LEFT JOIN skills_details d ON s.name = d.name
            WHERE s.snapshot_time = ? AND s.rank_delta < 0
            ORDER BY s.rank_delta ASC, s.rank ASC
            LIMIT ?
        """, (latest_time, limit))

        falling = [dict(row) for row in cursor.fetchall()]

        return {"rising": rising, "falling": falling}


def get_database() -> Database:
    """获取数据库实例（便捷函数）"""
    return Database()

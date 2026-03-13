from __future__ import annotations

import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "teaching.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "smart-teaching-demo-secret"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(DATABASE_PATH)
    cursor = db.cursor()
    cursor.executescript(
        """
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS courses;
        DROP TABLE IF EXISTS assignments;
        DROP TABLE IF EXISTS resources;
        DROP TABLE IF EXISTS notifications;
        DROP TABLE IF EXISTS activity_logs;

        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            major TEXT NOT NULL,
            interests TEXT NOT NULL,
            bio TEXT NOT NULL
        );

        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            teacher TEXT NOT NULL,
            tags TEXT NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL,
            score INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );

        CREATE TABLE resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            tags TEXT NOT NULL,
            url TEXT NOT NULL,
            downloads INTEGER NOT NULL,
            rating REAL NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );

        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resource_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            weight REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(resource_id) REFERENCES resources(id)
        );
        """
    )

    users = [
        ("曾美茜", "student", "计算机科学与技术", "python,推荐算法,数据分析,web开发", "希望获得更适合毕业设计和算法课程的学习资源。"),
        ("林老师", "teacher", "计算机学院", "数据库,软件工程,系统设计", "负责数据库系统与软件工程课程。"),
        ("陈老师", "teacher", "计算机学院", "机器学习,推荐系统,人工智能", "负责数据挖掘与推荐系统课程。"),
        ("教学管理员", "admin", "教务处", "教学管理,通知发布,统计分析", "维护教学资源与公告。"),
        ("张同学", "student", "数据科学与大数据技术", "机器学习,深度学习,数据可视化", "经常浏览算法和数据分析资源。"),
        ("李同学", "student", "软件工程", "java,系统架构,前端开发", "偏好工程实践类课程资源。"),
    ]
    cursor.executemany("INSERT INTO users (name, role, major, interests, bio) VALUES (?, ?, ?, ?, ?)", users)

    courses = [
        ("Python程序设计", "编程基础", "林老师", "python,基础语法,算法", "面向初学者的 Python 编程课程，覆盖语法、函数和项目实践。"),
        ("数据库系统原理", "专业核心", "林老师", "数据库,sql,建模", "介绍关系数据库、范式设计、SQL 查询与事务。"),
        ("机器学习导论", "人工智能", "陈老师", "机器学习,分类,回归", "围绕监督学习与模型评估建立机器学习基础。"),
        ("推荐系统实践", "人工智能", "陈老师", "推荐算法,协同过滤,内容推荐", "从用户画像、召回到排序实现推荐系统核心流程。"),
        ("Web全栈开发", "工程实践", "林老师", "web开发,flask,前端", "通过项目制方式完成前后端一体化开发。"),
    ]
    cursor.executemany("INSERT INTO courses (title, category, teacher, tags, description) VALUES (?, ?, ?, ?, ?)", courses)

    assignments = [
        (1, "Python项目实验一", "2026-03-20", "待提交", 0, "请完成数据清洗脚本并提交报告。"),
        (2, "数据库建模作业", "2026-03-18", "已批改", 92, "E-R 图设计完整，范式说明还可更细。"),
        (3, "机器学习模型对比实验", "2026-03-25", "待提交", 0, "比较 KNN、SVM 与随机森林的效果。"),
        (4, "推荐算法课程论文", "2026-03-28", "已提交", 0, "围绕混合推荐的冷启动问题写一篇综述。"),
        (5, "Flask课程设计", "2026-03-22", "已批改", 95, "页面结构清晰，接口设计较规范。"),
    ]
    cursor.executemany("INSERT INTO assignments (course_id, title, due_date, status, score, feedback) VALUES (?, ?, ?, ?, ?, ?)", assignments)

    resources = [
        (1, "Python函数与模块课件", "课件", "python,函数,模块", "https://example.com/python-modules", 132, 4.7),
        (1, "算法入门视频", "视频", "python,算法,入门", "https://example.com/algorithm-video", 156, 4.8),
        (2, "SQL查询实战手册", "文档", "sql,数据库,查询优化", "https://example.com/sql-guide", 117, 4.6),
        (2, "数据库范式案例集", "文档", "数据库,建模,范式", "https://example.com/db-cases", 88, 4.5),
        (3, "机器学习评估指标笔记", "文档", "机器学习,precision,recall,f1", "https://example.com/ml-metrics", 163, 4.9),
        (3, "分类算法对比视频", "视频", "机器学习,分类,模型评估", "https://example.com/classifier-video", 96, 4.4),
        (4, "协同过滤代码示例", "课件", "推荐算法,协同过滤,python", "https://example.com/cf-demo", 174, 4.9),
        (4, "内容推荐特征工程", "文档", "推荐算法,内容推荐,特征工程", "https://example.com/content-features", 141, 4.8),
        (4, "热门资源冷启动策略", "文档", "推荐算法,冷启动,热门资源", "https://example.com/cold-start", 102, 4.3),
        (5, "Flask项目模板", "课件", "flask,web开发,模板", "https://example.com/flask-starter", 127, 4.7),
        (5, "前端表单交互示例", "视频", "web开发,前端,交互", "https://example.com/form-demo", 84, 4.2),
    ]
    cursor.executemany("INSERT INTO resources (course_id, title, resource_type, tags, url, downloads, rating) VALUES (?, ?, ?, ?, ?, ?, ?)", resources)

    notifications = [
        ("数据库课程作业提醒", "作业", "数据库建模作业将于 2026-03-18 截止，请及时提交。", "2026-03-13 09:00"),
        ("推荐系统实验开放", "实验", "推荐系统实践课程实验环境已经开放，支持在线运行示例。", "2026-03-13 10:30"),
        ("教学资源上新", "资源", "新增《内容推荐特征工程》文档与《分类算法对比视频》。", "2026-03-13 13:20"),
    ]
    cursor.executemany("INSERT INTO notifications (title, category, content, created_at) VALUES (?, ?, ?, ?)", notifications)

    activities = [
        (1, 1, "view", 1.0, "2026-03-10 08:00"), (1, 2, "favorite", 2.5, "2026-03-10 10:00"),
        (1, 5, "view", 1.2, "2026-03-11 11:00"), (1, 7, "favorite", 3.0, "2026-03-11 14:00"),
        (1, 8, "rate", 3.5, "2026-03-12 09:00"), (1, 10, "view", 1.0, "2026-03-12 18:20"),
        (5, 5, "favorite", 3.0, "2026-03-10 09:20"), (5, 7, "view", 1.0, "2026-03-11 11:40"),
        (5, 8, "favorite", 2.8, "2026-03-11 20:20"), (5, 9, "view", 1.1, "2026-03-12 09:45"),
        (6, 3, "favorite", 2.7, "2026-03-10 07:30"), (6, 4, "view", 1.0, "2026-03-10 16:00"),
        (6, 10, "favorite", 2.6, "2026-03-11 19:10"), (6, 11, "view", 1.0, "2026-03-12 08:00"),
    ]
    cursor.executemany("INSERT INTO activity_logs (user_id, resource_id, action, weight, created_at) VALUES (?, ?, ?, ?, ?)", activities)
    db.commit()
    db.close()


def parse_tags(tag_string: str) -> list[str]:
    return [item.strip() for item in tag_string.split(",") if item.strip()]


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    numerator = sum(left[key] * right[key] for key in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def build_user_interest_vector(db: sqlite3.Connection, user_id: int) -> dict[str, float]:
    user = db.execute("SELECT interests FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    vector: Counter[str] = Counter()
    for tag in parse_tags(user["interests"]):
        vector[tag] += 2.5
    rows = db.execute(
        "SELECT resources.tags, activity_logs.weight FROM activity_logs JOIN resources ON resources.id = activity_logs.resource_id WHERE activity_logs.user_id = ?",
        (user_id,),
    ).fetchall()
    for row in rows:
        for tag in parse_tags(row["tags"]):
            vector[tag] += float(row["weight"])
    return dict(vector)


def build_resource_vector(resource: sqlite3.Row) -> dict[str, float]:
    vector: Counter[str] = Counter()
    for tag in parse_tags(resource["tags"]):
        vector[tag] += 1.0
    vector[resource["resource_type"]] += 0.6
    return dict(vector)


def collaborative_scores(db: sqlite3.Connection, user_id: int) -> dict[int, float]:
    rows = db.execute("SELECT user_id, resource_id, weight FROM activity_logs ORDER BY user_id").fetchall()
    user_resource_weights: dict[int, dict[int, float]] = defaultdict(dict)
    for row in rows:
        user_resource_weights[row["user_id"]][row["resource_id"]] = row["weight"]
    target = user_resource_weights.get(user_id, {})
    if not target:
        return {}
    similarities: dict[int, float] = {}
    for other_user_id, weights in user_resource_weights.items():
        if other_user_id == user_id:
            continue
        similarity = cosine_similarity({str(key): value for key, value in target.items()}, {str(key): value for key, value in weights.items()})
        if similarity > 0:
            similarities[other_user_id] = similarity
    scores: dict[int, float] = defaultdict(float)
    for other_user_id, similarity in similarities.items():
        for resource_id, weight in user_resource_weights[other_user_id].items():
            if resource_id not in target:
                scores[resource_id] += similarity * weight
    return scores


def content_scores(db: sqlite3.Connection, user_id: int) -> dict[int, float]:
    interest_vector = build_user_interest_vector(db, user_id)
    resources = db.execute("SELECT * FROM resources").fetchall()
    return {resource["id"]: cosine_similarity(interest_vector, build_resource_vector(resource)) for resource in resources}


def hot_scores(db: sqlite3.Connection) -> dict[int, float]:
    rows = db.execute("SELECT id, downloads, rating FROM resources").fetchall()
    max_downloads = max((row["downloads"] for row in rows), default=1) or 1
    return {row["id"]: 0.6 * (row["downloads"] / max_downloads) + 0.4 * (row["rating"] / 5.0) for row in rows}


def recommend_resources(db: sqlite3.Connection, user_id: int, top_n: int = 5) -> list[dict[str, Any]]:
    seen_ids = {row["resource_id"] for row in db.execute("SELECT DISTINCT resource_id FROM activity_logs WHERE user_id = ?", (user_id,)).fetchall()}
    by_content = content_scores(db, user_id)
    by_collab = collaborative_scores(db, user_id)
    by_hot = hot_scores(db)
    resources = {
        row["id"]: row for row in db.execute("SELECT resources.*, courses.title AS course_title FROM resources JOIN courses ON courses.id = resources.course_id").fetchall()
    }
    ranked: list[dict[str, Any]] = []
    for resource_id, resource in resources.items():
        if resource_id in seen_ids:
            continue
        content = by_content.get(resource_id, 0.0)
        collab = by_collab.get(resource_id, 0.0)
        hot = by_hot.get(resource_id, 0.0)
        ranked.append(
            {
                "id": resource_id,
                "title": resource["title"],
                "course_title": resource["course_title"],
                "resource_type": resource["resource_type"],
                "tags": parse_tags(resource["tags"]),
                "url": resource["url"],
                "score": round(0.5 * content + 0.35 * collab + 0.15 * hot, 3),
                "content_score": round(content, 3),
                "collab_score": round(collab, 3),
                "hot_score": round(hot, 3),
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_n]


def dashboard_metrics(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    top_tags = build_user_interest_vector(db, user_id)
    average_score = db.execute("SELECT AVG(score) FROM assignments WHERE score > 0").fetchone()[0]
    return {
        "user": user,
        "course_count": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "resource_count": db.execute("SELECT COUNT(*) FROM resources").fetchone()[0],
        "pending_assignments": db.execute("SELECT COUNT(*) FROM assignments WHERE status != '已批改'").fetchone()[0],
        "average_score": round(average_score or 0, 1),
        "active_days": db.execute("SELECT COUNT(DISTINCT substr(created_at, 1, 10)) FROM activity_logs WHERE user_id = ?", (user_id,)).fetchone()[0],
        "top_tags": sorted(top_tags.items(), key=lambda item: item[1], reverse=True)[:5],
    }


@app.template_filter("split_tags")
def split_tags_filter(value: str) -> list[str]:
    return parse_tags(value)


@app.route("/")
def index() -> str:
    db = get_db()
    user_id = int(request.args.get("user_id", 1))
    return render_template(
        "index.html",
        metrics=dashboard_metrics(db, user_id),
        users=db.execute("SELECT id, name, role FROM users ORDER BY id").fetchall(),
        selected_user_id=user_id,
        courses=db.execute("SELECT * FROM courses ORDER BY id").fetchall(),
        assignments=db.execute("SELECT assignments.*, courses.title AS course_title FROM assignments JOIN courses ON courses.id = assignments.course_id ORDER BY due_date").fetchall(),
        notifications=db.execute("SELECT * FROM notifications ORDER BY created_at DESC").fetchall(),
        recommendations=recommend_resources(db, user_id),
    )


@app.route("/resources")
def resources() -> str:
    db = get_db()
    query = request.args.get("q", "").strip().lower()
    rows = db.execute("SELECT resources.*, courses.title AS course_title FROM resources JOIN courses ON courses.id = resources.course_id ORDER BY downloads DESC, rating DESC").fetchall()
    if query:
        rows = [row for row in rows if query in " ".join([row["title"], row["course_title"], row["resource_type"], row["tags"]]).lower()]
    return render_template("resources.html", resources=rows, query=query)


@app.route("/recommendations")
def recommendations() -> str:
    db = get_db()
    user_id = int(request.args.get("user_id", 1))
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    return render_template(
        "recommendations.html",
        user=user,
        users=db.execute("SELECT id, name, role FROM users ORDER BY id").fetchall(),
        selected_user_id=user_id,
        items=recommend_resources(db, user_id, top_n=10),
        interest_vector=sorted(build_user_interest_vector(db, user_id).items(), key=lambda item: item[1], reverse=True)[:8],
    )


@app.route("/activity/log", methods=["POST"])
def log_activity() -> Any:
    db = get_db()
    weight_map = {"view": 1.0, "favorite": 2.5, "rate": 3.0}
    db.execute(
        "INSERT INTO activity_logs (user_id, resource_id, action, weight, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            int(request.form["user_id"]),
            int(request.form["resource_id"]),
            request.form["action"],
            weight_map.get(request.form["action"], 1.0),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    db.commit()
    flash("学习行为已记录，推荐结果已更新。")
    return redirect(url_for("recommendations", user_id=int(request.form["user_id"])))


@app.route("/reset")
def reset() -> Any:
    init_db()
    flash("演示数据已重置。")
    return redirect(url_for("index"))


if __name__ == "__main__":
    if not DATABASE_PATH.exists():
        init_db()
    app.run(debug=True)

from __future__ import annotations

import io
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "teaching.db"
UPLOAD_DIR = BASE_DIR / "uploads"
RESOURCE_UPLOAD_DIR = UPLOAD_DIR / "resources"
RESOURCE_TYPES = ["文档", "视频", "案例", "课件", "数据集", "代码", "网站", "试题"]

app = Flask(__name__)
app.config["SECRET_KEY"] = "smart-teaching-platform-secret"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


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


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def parse_tags(tag_string: str) -> list[str]:
    return [item.strip() for item in tag_string.split(",") if item.strip()]


def current_user_id() -> int:
    raw = request.values.get("user_id") or request.args.get("user_id") or "1"
    try:
        return int(raw)
    except ValueError:
        return 1


def page_arg(name: str, default: int = 1) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, value)


def paginate_rows(rows: list[Any], page: int, page_size: int = 6) -> dict[str, Any]:
    total = len(rows)
    total_pages = max(1, math.ceil(total / page_size))
    page = min(page, total_pages)
    start = (page - 1) * page_size
    return {
        "items": rows[start:start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def require_roles(*roles: str) -> sqlite3.Row:
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (current_user_id(),)).fetchone()
    if user is None:
        abort(404)
    if roles and user["role"] not in roles:
        abort(403)
    return user


def save_resource_upload(upload: Any) -> tuple[str | None, str | None]:
    if upload is None or not getattr(upload, "filename", ""):
        return None, None
    RESOURCE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(upload.filename)
    stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    stored_path = RESOURCE_UPLOAD_DIR / stored_name
    upload.save(stored_path)
    return str(stored_path.resolve()), upload.filename


def init_db() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    RESOURCE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH)
    cursor = db.cursor()
    cursor.executescript(
        """
        DROP TABLE IF EXISTS activity_logs;
        DROP TABLE IF EXISTS resource_ratings;
        DROP TABLE IF EXISTS submissions;
        DROP TABLE IF EXISTS notifications;
        DROP TABLE IF EXISTS resources;
        DROP TABLE IF EXISTS assignments;
        DROP TABLE IF EXISTS enrollments;
        DROP TABLE IF EXISTS courses;
        DROP TABLE IF EXISTS users;

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
            teacher_id INTEGER NOT NULL,
            tags TEXT NOT NULL,
            description TEXT NOT NULL,
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        );

        CREATE TABLE enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            UNIQUE(user_id, course_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );

        CREATE TABLE assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            due_date TEXT NOT NULL,
            max_score INTEGER NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );

        CREATE TABLE resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            tags TEXT NOT NULL,
            url TEXT NOT NULL,
            summary TEXT NOT NULL,
            file_path TEXT,
            original_filename TEXT,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );

        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            recipient_id INTEGER,
            course_id INTEGER,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            priority TEXT NOT NULL,
            FOREIGN KEY(author_id) REFERENCES users(id),
            FOREIGN KEY(recipient_id) REFERENCES users(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );

        CREATE TABLE submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            score INTEGER,
            feedback TEXT,
            graded_by INTEGER,
            graded_at TEXT,
            UNIQUE(assignment_id, student_id),
            FOREIGN KEY(assignment_id) REFERENCES assignments(id),
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(graded_by) REFERENCES users(id)
        );

        CREATE TABLE resource_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(resource_id, user_id),
            FOREIGN KEY(resource_id) REFERENCES resources(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resource_id INTEGER,
            course_id INTEGER,
            action TEXT NOT NULL,
            weight REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(resource_id) REFERENCES resources(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );

        CREATE TABLE course_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            parent_id INTEGER,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id),
            FOREIGN KEY(author_id) REFERENCES users(id),
            FOREIGN KEY(parent_id) REFERENCES course_messages(id)
        );

        CREATE TABLE quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE TABLE quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL,
            explanation TEXT NOT NULL,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id)
        );

        CREATE TABLE quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            score REAL NOT NULL,
            completed_at TEXT NOT NULL,
            UNIQUE(quiz_id, student_id),
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id),
            FOREIGN KEY(student_id) REFERENCES users(id)
        );

        CREATE TABLE quiz_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            selected_option TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            FOREIGN KEY(attempt_id) REFERENCES quiz_attempts(id),
            FOREIGN KEY(question_id) REFERENCES quiz_questions(id)
        );
        """
    )

    users = [
        ("曾美茜", "student", "计算机科学与技术", "python,推荐算法,数据分析,web开发", "关注毕业设计、推荐算法和工程化实现，希望资源推荐更贴合当前学习节奏。"),
        ("林老师", "teacher", "计算机学院", "数据库,软件工程,系统设计", "负责数据库系统与软件工程课程，注重课程过程管理与结果反馈。"),
        ("陈老师", "teacher", "计算机学院", "机器学习,推荐系统,人工智能", "负责机器学习与推荐系统课程，重点关注学习行为与推荐效果。"),
        ("教学管理员", "admin", "教务处", "教学管理,通知发布,统计分析", "维护课程资源、消息通知与平台数据看板。"),
        ("张同学", "student", "数据科学与大数据技术", "机器学习,深度学习,数据可视化", "经常浏览算法和实验类资源，偏好高密度学习内容。"),
        ("李同学", "student", "软件工程", "java,系统架构,前端开发", "偏好工程实践与项目案例，关注作业进度与资源整合。"),
    ]
    cursor.executemany("INSERT INTO users (name, role, major, interests, bio) VALUES (?, ?, ?, ?, ?)", users)

    courses = [
        ("Python程序设计", "编程基础", 2, "python,基础语法,算法", "从语法、函数到项目实践，帮助学生建立工程化编程能力。"),
        ("数据库系统原理", "专业核心", 2, "数据库,sql,建模", "覆盖关系数据库、范式设计、SQL 查询优化与事务管理。"),
        ("机器学习导论", "人工智能", 3, "机器学习,分类,回归", "通过模型训练与评估案例建立机器学习基础认知。"),
        ("推荐系统实践", "人工智能", 3, "推荐算法,协同过滤,内容推荐", "围绕用户画像、召回、排序与冷启动策略展开课程实践。"),
        ("Web全栈开发", "工程实践", 2, "web开发,flask,前端", "以项目为主线完成前后端协同开发和系统发布。"),
    ]
    cursor.executemany(
        "INSERT INTO courses (title, category, teacher_id, tags, description) VALUES (?, ?, ?, ?, ?)",
        courses,
    )

    enrollments = [
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5),
        (5, 3), (5, 4), (5, 5),
        (6, 1), (6, 2), (6, 5),
    ]
    cursor.executemany("INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)", enrollments)

    assignments = [
        (1, "Python项目实验一", "完成数据清洗脚本并提交实验报告。", "2026-03-20", 100),
        (2, "数据库建模作业", "完成教务系统 E-R 图和三范式设计。", "2026-03-18", 100),
        (3, "机器学习模型对比实验", "比较 KNN、SVM 与随机森林在公开数据集上的表现。", "2026-03-25", 100),
        (4, "推荐算法课程论文", "围绕混合推荐的冷启动问题完成一篇课程论文。", "2026-03-28", 100),
        (5, "Flask课程设计", "实现一个带登录、上传和权限控制的小型系统。", "2026-03-22", 100),
    ]
    cursor.executemany(
        "INSERT INTO assignments (course_id, title, description, due_date, max_score) VALUES (?, ?, ?, ?, ?)",
        assignments,
    )

    resources = [
        (1, "Python 官方教程", "文档", "python,语法,教程", "https://docs.python.org/3/tutorial/", "Python 官方教程，适合课程入门和函数、模块学习。"),
        (1, "Sorting HOW TO", "文档", "python,排序,算法", "https://docs.python.org/3/howto/sorting.html", "Python 官方排序指南，可对应算法与数据处理内容。"),
        (2, "SQLite 官方文档", "文档", "数据库,sql,sqlite", "https://www.sqlite.org/docs.html", "SQLite 官方文档入口，适合数据库系统原理课程查阅。"),
        (2, "SQLite Query Language", "文档", "sql,查询,数据库", "https://www.sqlite.org/lang.html", "SQLite SQL 语法索引，适合查询、建模和事务学习。"),
        (3, "scikit-learn 入门", "文档", "机器学习,sklearn,教程", "https://scikit-learn.org/stable/", "scikit-learn 官方稳定版首页，包含 Getting Started 与用户指南入口。"),
        (3, "scikit-learn 用户指南", "文档", "机器学习,分类,回归", "https://scikit-learn.org/stable/user_guide.html", "scikit-learn 官方用户指南入口。"),
        (4, "Google Recommendation Overview", "文档", "推荐算法,推荐系统,概览", "https://developers.google.com/machine-learning/recommendation", "Google 机器学习课程中的推荐系统总览。"),
        (4, "Content-based Filtering", "文档", "推荐算法,内容推荐,特征工程", "https://developers.google.com/machine-learning/recommendation/content-based/basics", "Google 推荐系统课程中的内容推荐基础。"),
        (4, "Collaborative Filtering", "文档", "推荐算法,协同过滤,相似度", "https://developers.google.com/machine-learning/recommendation/collaborative/basics", "Google 推荐系统课程中的协同过滤基础。"),
        (5, "Flask Quickstart", "文档", "flask,web开发,后端", "https://flask.palletsprojects.com/en/stable/quickstart/", "Flask 官方快速开始文档。"),
        (5, "MDN Forms Guide", "文档", "前端,表单,交互", "https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Your_first_form", "MDN 表单入门文档，适合资源上传与页面交互学习。"),
    ]
    cursor.executemany(
        "INSERT INTO resources (course_id, title, resource_type, tags, url, summary) VALUES (?, ?, ?, ?, ?, ?)",
        resources,
    )

    notifications = [
        (2, "数据库课程作业提醒", "作业", "数据库建模作业将于 2026-03-18 截止，请及时完成并核对提交格式。", "2026-03-13 09:00", "高"),
        (3, "推荐系统实验开放", "实验", "推荐系统实践课程实验环境已开放，支持在线运行协同过滤示例。", "2026-03-13 10:30", "中"),
        (4, "资源中心更新", "资源", "新增内容推荐与协同过滤学习资料，资源中心可直接访问。", "2026-03-13 13:20", "中"),
    ]
    cursor.executemany(
        "INSERT INTO notifications (author_id, title, category, content, created_at, priority) VALUES (?, ?, ?, ?, ?, ?)",
        notifications,
    )

    sample_files = {
        "python_report.txt": "Python 项目实验一提交内容：数据清洗流程、代码截图与结果分析。",
        "db_model.pdf": "数据库建模作业：E-R 图、关系模式设计和范式说明。",
        "flask_design.zip": "Flask 课程设计：页面原型、接口文档和数据库设计。",
    }
    for filename, content in sample_files.items():
        (UPLOAD_DIR / filename).write_text(content, encoding="utf-8")

    submissions = [
        (2, 1, "db_model.pdf", str((UPLOAD_DIR / "db_model.pdf").resolve()), "2026-03-12 14:00", 92, "E-R 图完整，范式说明可以再细化。", 2, "2026-03-13 09:30"),
        (5, 1, "flask_design.zip", str((UPLOAD_DIR / "flask_design.zip").resolve()), "2026-03-12 18:10", 95, "页面结构清晰，接口组织规范。", 2, "2026-03-13 11:00"),
    ]
    cursor.executemany(
        """
        INSERT INTO submissions (assignment_id, student_id, filename, stored_path, submitted_at, score, feedback, graded_by, graded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        submissions,
    )

    ratings = [
        (1, 1, 5, "官方教程结构清晰。", "2026-03-10 08:30"),
        (2, 1, 4, "排序讲解简洁。", "2026-03-10 09:10"),
        (5, 1, 5, "适合做算法实验前的复习。", "2026-03-11 11:30"),
        (7, 5, 5, "推荐系统概览很适合入门。", "2026-03-11 20:20"),
        (8, 5, 4, "内容推荐部分比较实用。", "2026-03-12 09:45"),
        (10, 6, 5, "Flask 官方文档适合搭项目。", "2026-03-11 19:10"),
    ]
    cursor.executemany(
        "INSERT INTO resource_ratings (resource_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
        ratings,
    )

    activities = [
        (1, 1, 1, "view", 1.0, "2026-03-10 08:00"),
        (1, 2, 1, "favorite", 2.5, "2026-03-10 10:00"),
        (1, 5, 3, "view", 1.0, "2026-03-11 11:00"),
        (1, 7, 4, "favorite", 2.5, "2026-03-11 14:00"),
        (1, 8, 4, "rate", 3.0, "2026-03-12 09:00"),
        (1, 10, 5, "download", 1.3, "2026-03-12 18:20"),
        (5, 5, 3, "favorite", 2.5, "2026-03-10 09:20"),
        (5, 7, 4, "view", 1.0, "2026-03-11 11:40"),
        (5, 8, 4, "favorite", 2.5, "2026-03-11 20:20"),
        (5, 9, 4, "download", 1.3, "2026-03-12 09:45"),
        (6, 3, 2, "favorite", 2.5, "2026-03-10 07:30"),
        (6, 4, 2, "view", 1.0, "2026-03-10 16:00"),
        (6, 10, 5, "favorite", 2.5, "2026-03-11 19:10"),
        (6, 11, 5, "view", 1.0, "2026-03-12 08:00"),
    ]
    cursor.executemany(
        """
        INSERT INTO activity_logs (user_id, resource_id, course_id, action, weight, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        activities,
    )

    db.commit()
    db.close()


def course_progress_for_user(db: sqlite3.Connection, user_id: int, course_id: int) -> int:
    total_resources = db.execute("SELECT COUNT(*) FROM resources WHERE course_id = ?", (course_id,)).fetchone()[0]
    if total_resources == 0:
        return 0
    engaged_resources = db.execute(
        """
        SELECT COUNT(DISTINCT resource_id)
        FROM activity_logs
        WHERE user_id = ? AND course_id = ? AND resource_id IS NOT NULL
        """,
        (user_id, course_id),
    ).fetchone()[0]
    return round((engaged_resources / total_resources) * 100)


def course_submission_rate(db: sqlite3.Connection, course_id: int) -> int:
    student_count = db.execute("SELECT COUNT(*) FROM enrollments WHERE course_id = ?", (course_id,)).fetchone()[0]
    assignment_count = db.execute("SELECT COUNT(*) FROM assignments WHERE course_id = ?", (course_id,)).fetchone()[0]
    if student_count == 0 or assignment_count == 0:
        return 0
    submission_count = db.execute(
        """
        SELECT COUNT(*)
        FROM submissions
        JOIN assignments ON assignments.id = submissions.assignment_id
        WHERE assignments.course_id = ?
        """,
        (course_id,),
    ).fetchone()[0]
    total_slots = student_count * assignment_count
    return round((submission_count / total_slots) * 100)


def resource_stats(db: sqlite3.Connection, resource_id: int) -> dict[str, float]:
    rating_row = db.execute(
        "SELECT AVG(rating) AS avg_rating, COUNT(*) AS total FROM resource_ratings WHERE resource_id = ?",
        (resource_id,),
    ).fetchone()
    downloads = db.execute(
        "SELECT COUNT(*) FROM activity_logs WHERE resource_id = ? AND action = 'download'",
        (resource_id,),
    ).fetchone()[0]
    views = db.execute(
        "SELECT COUNT(*) FROM activity_logs WHERE resource_id = ? AND action IN ('view', 'favorite', 'rate', 'download')",
        (resource_id,),
    ).fetchone()[0]
    favorites = db.execute(
        "SELECT COUNT(*) FROM activity_logs WHERE resource_id = ? AND action = 'favorite'",
        (resource_id,),
    ).fetchone()[0]
    return {
        "avg_rating": round(float(rating_row["avg_rating"] or 0), 2),
        "rating_count": int(rating_row["total"]),
        "downloads": downloads,
        "views": views,
        "favorites": favorites,
    }


def message_threads_for_course(db: sqlite3.Connection, course_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT course_messages.*, users.name AS author_name, users.role AS author_role
        FROM course_messages
        JOIN users ON users.id = course_messages.author_id
        WHERE course_messages.course_id = ?
        ORDER BY course_messages.created_at ASC, course_messages.id ASC
        """,
        (course_id,),
    ).fetchall()
    items: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in rows:
        node = {**dict(row), "replies": []}
        items[row["id"]] = node
        if row["parent_id"] is None:
            roots.append(node)
        elif row["parent_id"] in items:
            items[row["parent_id"]]["replies"].append(node)
    return roots


def quiz_rows_for_course(db: sqlite3.Connection, course_id: int, user_id: int | None = None) -> list[dict[str, Any]]:
    quizzes = db.execute("SELECT * FROM quizzes WHERE course_id = ? ORDER BY id DESC", (course_id,)).fetchall()
    rows: list[dict[str, Any]] = []
    for quiz in quizzes:
        questions = [dict(row) for row in db.execute("SELECT * FROM quiz_questions WHERE quiz_id = ? ORDER BY id", (quiz["id"],)).fetchall()]
        attempts = [dict(row) for row in db.execute(
            "SELECT quiz_attempts.*, users.name AS student_name FROM quiz_attempts JOIN users ON users.id = quiz_attempts.student_id WHERE quiz_id = ? ORDER BY completed_at DESC",
            (quiz["id"],),
        ).fetchall()]
        my_attempt = None
        answer_details: list[dict[str, Any]] = []
        if user_id:
            my_attempt_row = db.execute("SELECT * FROM quiz_attempts WHERE quiz_id = ? AND student_id = ?", (quiz["id"], user_id)).fetchone()
            my_attempt = dict(my_attempt_row) if my_attempt_row else None
            if my_attempt:
                answer_details = [
                    dict(row)
                    for row in db.execute(
                        """
                        SELECT quiz_answers.selected_option, quiz_answers.is_correct, quiz_questions.question_text,
                               quiz_questions.correct_option, quiz_questions.explanation
                        FROM quiz_answers
                        JOIN quiz_questions ON quiz_questions.id = quiz_answers.question_id
                        WHERE quiz_answers.attempt_id = ?
                        ORDER BY quiz_questions.id
                        """,
                        (my_attempt["id"],),
                    ).fetchall()
                ]
        students = db.execute(
            "SELECT users.id, users.name FROM enrollments JOIN users ON users.id = enrollments.user_id WHERE enrollments.course_id = ? AND users.role = 'student' ORDER BY users.name",
            (course_id,),
        ).fetchall()
        score_map = {item["student_id"]: item["score"] for item in attempts}
        completion = [
            {
                "student_id": student["id"],
                "student_name": student["name"],
                "completed": student["id"] in score_map,
                "score": score_map.get(student["id"]),
            }
            for student in students
        ]
        rows.append({
            **dict(quiz),
            "questions": questions,
            "question_count": len(questions),
            "attempts": attempts,
            "my_attempt": my_attempt,
            "answer_details": answer_details,
            "completion": completion,
        })
    return rows


def course_rows(db: sqlite3.Connection, user_id: int | None = None) -> list[dict[str, Any]]:
    role = None
    if user_id:
        role_row = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        role = role_row["role"] if role_row else None
    rows = db.execute(
        """
        SELECT courses.*, users.name AS teacher_name
        FROM courses
        JOIN users ON users.id = courses.teacher_id
        ORDER BY courses.id
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        is_enrolled = False
        if user_id:
            is_enrolled = db.execute(
                "SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ?",
                (user_id, row["id"]),
            ).fetchone() is not None
        if role == "student" and not is_enrolled:
            continue
        if role == "teacher" and row["teacher_id"] != user_id:
            continue

        resources = []
        for resource in db.execute(
            "SELECT * FROM resources WHERE course_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall():
            completed = False
            if user_id:
                completed = db.execute(
                    "SELECT 1 FROM activity_logs WHERE user_id = ? AND course_id = ? AND resource_id = ? LIMIT 1",
                    (user_id, row["id"], resource["id"]),
                ).fetchone() is not None
            stats = resource_stats(db, resource["id"])
            resources.append(
                {
                    **dict(resource),
                    **stats,
                    "tags": parse_tags(resource["tags"]),
                    "completed": completed,
                }
            )

        assignments = []
        for assignment in db.execute(
            "SELECT * FROM assignments WHERE course_id = ? ORDER BY due_date, id",
            (row["id"],),
        ).fetchall():
            pending_students = [
                dict(student)
                for student in db.execute(
                    """
                    SELECT users.id, users.name
                    FROM enrollments
                    JOIN users ON users.id = enrollments.user_id
                    WHERE enrollments.course_id = ?
                    AND users.role = 'student'
                    AND NOT EXISTS (
                        SELECT 1
                        FROM submissions
                        WHERE submissions.assignment_id = ?
                        AND submissions.student_id = users.id
                    )
                    ORDER BY users.name
                    """,
                    (row["id"], assignment["id"]),
                ).fetchall()
            ]
            my_submission = None
            if role == "student" and user_id:
                my_submission = db.execute(
                    "SELECT id AS submission_id, filename, submitted_at, score, feedback FROM submissions WHERE assignment_id = ? AND student_id = ?",
                    (assignment["id"], user_id),
                ).fetchone()
            assignments.append(
                {
                    **dict(assignment),
                    "pending_students": pending_students,
                    "pending_count": len(pending_students),
                    "my_submission": dict(my_submission) if my_submission else None,
                }
            )

        result.append(
            {
                **dict(row),
                "students": db.execute("SELECT COUNT(*) FROM enrollments WHERE course_id = ?", (row["id"],)).fetchone()[0],
                "progress": course_progress_for_user(db, user_id, row["id"]) if user_id else course_submission_rate(db, row["id"]),
                "submission_rate": course_submission_rate(db, row["id"]),
                "is_enrolled": is_enrolled,
                "resources": resources,
                "assignments": assignments,
                "messages": message_threads_for_course(db, row["id"]),
                "quizzes": quiz_rows_for_course(db, row["id"], user_id),
            }
        )
    return result


def student_assignment_rows(db: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT assignments.*, courses.title AS course_title, submissions.id AS submission_id,
               submissions.filename, submissions.submitted_at, submissions.score, submissions.feedback,
               submissions.graded_at
        FROM assignments
        JOIN courses ON courses.id = assignments.course_id
        JOIN enrollments ON enrollments.course_id = assignments.course_id AND enrollments.user_id = ?
        LEFT JOIN submissions ON submissions.assignment_id = assignments.id AND submissions.student_id = ?
        ORDER BY assignments.due_date
        """,
        (user_id, user_id),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if row["submission_id"] is None:
            item["status"] = "待提交"
        elif row["score"] is None:
            item["status"] = "待批改"
        else:
            item["status"] = "已批改"
        result.append(item)
    return result


def teacher_submission_rows(db: sqlite3.Connection, teacher_id: int | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT submissions.*, assignments.title AS assignment_title, assignments.max_score,
               courses.title AS course_title, students.name AS student_name, teachers.name AS teacher_name
        FROM submissions
        JOIN assignments ON assignments.id = submissions.assignment_id
        JOIN courses ON courses.id = assignments.course_id
        JOIN users AS students ON students.id = submissions.student_id
        JOIN users AS teachers ON teachers.id = courses.teacher_id
    """
    params: tuple[Any, ...] = ()
    if teacher_id is not None:
        query += " WHERE courses.teacher_id = ?"
        params = (teacher_id,)
    query += " ORDER BY submissions.submitted_at DESC"
    return db.execute(query, params).fetchall()


def resource_rows(db: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT resources.*, courses.title AS course_title
        FROM resources
        JOIN courses ON courses.id = resources.course_id
        ORDER BY resources.id
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item.update(resource_stats(db, row["id"]))
        my_rating = db.execute(
            "SELECT rating FROM resource_ratings WHERE resource_id = ? AND user_id = ?",
            (row["id"], user_id),
        ).fetchone()
        item["my_rating"] = my_rating["rating"] if my_rating else None
        item["is_favorited"] = db.execute(
            "SELECT 1 FROM activity_logs WHERE user_id = ? AND resource_id = ? AND action = 'favorite' LIMIT 1",
            (user_id, row["id"]),
        ).fetchone() is not None
        item["comments"] = [
            dict(comment)
            for comment in db.execute(
                """
                SELECT resource_ratings.rating, resource_ratings.comment, resource_ratings.created_at, users.name AS author_name
                FROM resource_ratings
                JOIN users ON users.id = resource_ratings.user_id
                WHERE resource_ratings.resource_id = ? AND trim(resource_ratings.comment) != ''
                ORDER BY resource_ratings.created_at DESC, resource_ratings.id DESC
                """,
                (row["id"],),
            ).fetchall()
        ]
        result.append(item)
    return result


def favorite_resource_rows(db: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    return [row for row in resource_rows(db, user_id) if row["is_favorited"]]


def notification_rows(db: sqlite3.Connection, user_id: int, role: str) -> list[sqlite3.Row]:
    if role == "student":
        return db.execute(
            """
            SELECT notifications.*, authors.name AS author_name, recipients.name AS recipient_name
            FROM notifications
            JOIN users AS authors ON authors.id = notifications.author_id
            LEFT JOIN users AS recipients ON recipients.id = notifications.recipient_id
            WHERE notifications.recipient_id IS NULL OR notifications.recipient_id = ?
            ORDER BY notifications.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return db.execute(
        """
        SELECT notifications.*, authors.name AS author_name, recipients.name AS recipient_name
        FROM notifications
        JOIN users AS authors ON authors.id = notifications.author_id
        LEFT JOIN users AS recipients ON recipients.id = notifications.recipient_id
        ORDER BY notifications.created_at DESC
        """
    ).fetchall()


def can_manage_course(user_id: int, course_id: int) -> bool:
    db = get_db()
    user = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return False
    if user["role"] == "admin":
        return True
    return db.execute("SELECT 1 FROM courses WHERE id = ? AND teacher_id = ?", (course_id, user_id)).fetchone() is not None


def pending_assignments_count(db: sqlite3.Connection, user_id: int) -> int:
    return sum(1 for row in student_assignment_rows(db, user_id) if row["status"] == "待提交")


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
        """
        SELECT resources.tags, activity_logs.weight
        FROM activity_logs
        JOIN resources ON resources.id = activity_logs.resource_id
        WHERE activity_logs.user_id = ? AND activity_logs.resource_id IS NOT NULL
        """,
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
    vector[resource["resource_type"]] += 0.5
    return dict(vector)


def collaborative_scores(db: sqlite3.Connection, user_id: int) -> dict[int, float]:
    rows = db.execute("SELECT user_id, resource_id, weight FROM activity_logs WHERE resource_id IS NOT NULL").fetchall()
    matrix: dict[int, dict[int, float]] = defaultdict(dict)
    for row in rows:
        matrix[row["user_id"]][row["resource_id"]] = matrix[row["user_id"]].get(row["resource_id"], 0) + row["weight"]
    target = matrix.get(user_id, {})
    if not target:
        return {}
    similarities: dict[int, float] = {}
    for other_user_id, weights in matrix.items():
        if other_user_id == user_id:
            continue
        similarity = cosine_similarity(
            {str(key): value for key, value in target.items()},
            {str(key): value for key, value in weights.items()},
        )
        if similarity > 0:
            similarities[other_user_id] = similarity
    scores: dict[int, float] = defaultdict(float)
    for other_user_id, similarity in similarities.items():
        for resource_id, weight in matrix[other_user_id].items():
            if resource_id not in target:
                scores[resource_id] += similarity * weight
    max_score = max(scores.values(), default=0)
    if max_score > 0:
        scores = defaultdict(float, {resource_id: value / max_score for resource_id, value in scores.items()})
    return dict(scores)


def content_scores(db: sqlite3.Connection, user_id: int) -> dict[int, float]:
    interest_vector = build_user_interest_vector(db, user_id)
    rows = db.execute("SELECT * FROM resources").fetchall()
    return {row["id"]: cosine_similarity(interest_vector, build_resource_vector(row)) for row in rows}


def hot_scores(db: sqlite3.Connection) -> dict[int, float]:
    rows = db.execute("SELECT * FROM resources").fetchall()
    rating_map = {row["id"]: resource_stats(db, row["id"]) for row in rows}
    max_downloads = max((stats["downloads"] for stats in rating_map.values()), default=1) or 1
    return {
        resource_id: 0.55 * (stats["downloads"] / max_downloads) + 0.45 * (stats["avg_rating"] / 5 if stats["avg_rating"] else 0)
        for resource_id, stats in rating_map.items()
    }


def recommend_resources(db: sqlite3.Connection, user_id: int, top_n: int = 6) -> list[dict[str, Any]]:
    seen_ids = {
        row["resource_id"]
        for row in db.execute(
            """
            SELECT DISTINCT resource_id
            FROM activity_logs
            WHERE user_id = ? AND resource_id IS NOT NULL AND action = 'favorite'
            """,
            (user_id,),
        ).fetchall()
    }
    by_content = content_scores(db, user_id)
    by_collab = collaborative_scores(db, user_id)
    by_hot = hot_scores(db)
    rows = db.execute(
        """
        SELECT resources.*, courses.title AS course_title
        FROM resources
        JOIN courses ON courses.id = resources.course_id
        """
    ).fetchall()
    ranked: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] in seen_ids:
            continue
        content = by_content.get(row["id"], 0.0)
        collab = by_collab.get(row["id"], 0.0)
        hot = by_hot.get(row["id"], 0.0)
        ranked.append(
            {
                "id": row["id"],
                "title": row["title"],
                "course_title": row["course_title"],
                "resource_type": row["resource_type"],
                "tags": parse_tags(row["tags"]),
                "url": row["url"],
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
    resource_avg = db.execute("SELECT AVG(rating) FROM resource_ratings").fetchone()[0] or 0
    active_days = db.execute(
        "SELECT COUNT(DISTINCT substr(created_at, 1, 10)) FROM activity_logs WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    return {
        "user": user,
        "course_count": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "resource_count": db.execute("SELECT COUNT(*) FROM resources").fetchone()[0],
        "pending_assignments": pending_assignments_count(db, user_id) if user["role"] == "student" else db.execute("SELECT COUNT(*) FROM submissions WHERE score IS NULL").fetchone()[0],
        "average_score": round(db.execute("SELECT AVG(score) FROM submissions WHERE score IS NOT NULL").fetchone()[0] or 0, 1),
        "active_days": active_days,
        "announcement_count": db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0],
        "resource_average_rating": round(resource_avg, 2),
        "top_tags": sorted(build_user_interest_vector(db, user_id).items(), key=lambda item: item[1], reverse=True)[:5],
    }


def analytics_snapshot(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    enrolled_courses = db.execute("SELECT course_id FROM enrollments WHERE user_id = ?", (user_id,)).fetchall()
    course_progress = [course_progress_for_user(db, user_id, row["course_id"]) for row in enrolled_courses]
    assignments = student_assignment_rows(db, user_id)
    submitted_count = sum(1 for row in assignments if row["status"] != "待提交")
    behavior_mix = db.execute(
        "SELECT action, COUNT(*) AS total FROM activity_logs WHERE user_id = ? GROUP BY action ORDER BY total DESC",
        (user_id,),
    ).fetchall()
    return {
        "course_completion": round(sum(course_progress) / len(course_progress), 1) if course_progress else 0,
        "assignment_submission": round((submitted_count / len(assignments)) * 100, 1) if assignments else 0,
        "resource_rating": round(db.execute("SELECT AVG(rating) FROM resource_ratings").fetchone()[0] or 0, 2),
        "behavior_mix": behavior_mix,
        "interest_vector": sorted(build_user_interest_vector(db, user_id).items(), key=lambda item: item[1], reverse=True)[:8],
    }


def student_dashboard_data(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    assignments = student_assignment_rows(db, user_id)
    courses = []
    quiz_reminders: list[dict[str, Any]] = []
    for row in course_rows(db, user_id):
        if not db.execute("SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ?", (user_id, row["id"])).fetchone():
            continue
        course_assignments = [item for item in assignments if item["course_id"] == row["id"]]
        total = len(course_assignments)
        submitted = sum(1 for item in course_assignments if item["status"] != "待提交")
        for quiz in row.get("quizzes", []):
            if not quiz.get("my_attempt"):
                quiz_reminders.append({
                    "id": quiz["id"],
                    "kind": "quiz",
                    "title": quiz["title"],
                    "course_id": row["id"],
                    "course_title": row["title"],
                    "status": "待完成测试",
                    "description": quiz["description"],
                    "detail_link": url_for("courses", user_id=user_id, course_id=row["id"]),
                })
        courses.append({
            **row,
            "progress_link": url_for("courses", user_id=user_id, course_id=row["id"]),
            "submission_link": url_for("assignments", user_id=user_id, course_id=row["id"]),
            "assignment_breakdown": course_assignments,
            "submission_rate": round((submitted / total) * 100) if total else 0,
        })
    enriched_assignments = []
    for item in assignments[:6]:
        enriched_assignments.append({
            **item,
            "kind": "assignment",
            "detail_link": url_for("assignments", user_id=user_id, assignment_id=item["id"]),
        })
    pending_items = sorted(quiz_reminders + enriched_assignments, key=lambda item: item["title"])[:8]
    return {"courses": courses, "assignments": pending_items, "recommendations": recommend_resources(db, user_id, top_n=4)}


def teacher_dashboard_data(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    courses = [row for row in course_rows(db, user_id) if row["teacher_id"] == user_id]
    submissions = []
    for row in teacher_submission_rows(db, user_id)[:6]:
        submissions.append({
            **dict(row),
            "grading_link": url_for("assignments", user_id=user_id, submission_id=row["id"]),
        })
    return {"courses": courses, "submissions": submissions}


def admin_dashboard_data(db: sqlite3.Connection) -> dict[str, Any]:
    return {
        "site_courses": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "site_users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "site_submissions": db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0],
        "notifications": notification_rows(db, current_user_id(), g.current_user["role"])[:6],
    }


def admin_management_data(db: sqlite3.Connection) -> dict[str, Any]:
    users = [dict(row) for row in db.execute("SELECT * FROM users ORDER BY role, id DESC").fetchall()]
    courses = [dict(row) for row in db.execute(
        """
        SELECT courses.*, users.name AS teacher_name
        FROM courses
        JOIN users ON users.id = courses.teacher_id
        ORDER BY courses.id DESC
        """
    ).fetchall()]
    resources = [dict(row) for row in db.execute(
        """
        SELECT resources.*, courses.title AS course_title
        FROM resources
        JOIN courses ON courses.id = resources.course_id
        ORDER BY resources.id DESC
        """
    ).fetchall()]
    for item in resources:
        item.update(resource_stats(db, item["id"]))
    enrollments = [dict(row) for row in db.execute(
        """
        SELECT enrollments.id, students.name AS student_name, students.id AS student_id, courses.title AS course_title, courses.id AS course_id
        FROM enrollments
        JOIN users AS students ON students.id = enrollments.user_id
        JOIN courses ON courses.id = enrollments.course_id
        ORDER BY enrollments.id DESC
        """
    ).fetchall()]
    students = [user for user in users if user["role"] == "student"]
    teachers = [user for user in users if user["role"] == "teacher"]
    return {
        "students": paginate_rows(students, page_arg("student_page")),
        "teachers": paginate_rows(teachers, page_arg("teacher_page")),
        "courses": paginate_rows(courses, page_arg("course_page")),
        "resources": paginate_rows(resources, page_arg("resource_page")),
        "enrollments": paginate_rows(enrollments, page_arg("enrollment_page")),
        "teachers_all": teachers,
        "students_all": students,
        "courses_all": courses,
    }


@app.before_request
def ensure_database() -> None:
    if not DATABASE_PATH.exists():
        init_db()
    db = get_db()

    notification_columns = [row["name"] for row in db.execute("PRAGMA table_info(notifications)").fetchall()]
    if "recipient_id" not in notification_columns:
        db.execute("ALTER TABLE notifications ADD COLUMN recipient_id INTEGER")
        db.commit()
    if "course_id" not in notification_columns:
        db.execute("ALTER TABLE notifications ADD COLUMN course_id INTEGER")
        db.commit()

    resource_columns = [row["name"] for row in db.execute("PRAGMA table_info(resources)").fetchall()]
    if "file_path" not in resource_columns:
        db.execute("ALTER TABLE resources ADD COLUMN file_path TEXT")
        db.commit()
    if "original_filename" not in resource_columns:
        db.execute("ALTER TABLE resources ADD COLUMN original_filename TEXT")
        db.commit()

    db.executescript("""
    CREATE TABLE IF NOT EXISTS course_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        author_id INTEGER NOT NULL,
        parent_id INTEGER,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL,
        option_d TEXT NOT NULL,
        correct_option TEXT NOT NULL,
        explanation TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        score REAL NOT NULL,
        completed_at TEXT NOT NULL,
        UNIQUE(quiz_id, student_id)
    );
    CREATE TABLE IF NOT EXISTS quiz_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        selected_option TEXT NOT NULL,
        is_correct INTEGER NOT NULL
    );
    """)
    db.commit()

    g.current_user = db.execute("SELECT * FROM users WHERE id = ?", (current_user_id(),)).fetchone()


@app.context_processor
def inject_globals() -> dict[str, Any]:
    db = get_db()
    users = db.execute("SELECT id, name, role FROM users ORDER BY id").fetchall()
    return {"current_user": g.current_user, "users": users, "user_id": current_user_id(), "resource_types": RESOURCE_TYPES}


@app.route("/switch-user")
def switch_user() -> Any:
    selected_user_id = current_user_id()
    user = get_db().execute("SELECT id FROM users WHERE id = ?", (selected_user_id,)).fetchone()
    if user is None:
        abort(404)
    return redirect(url_for("index", user_id=selected_user_id))


@app.template_filter("split_tags")
def split_tags_filter(value: str) -> list[str]:
    return parse_tags(value)


@app.route("/")
def index() -> str:
    db = get_db()
    return render_template(
        "index.html",
        metrics=dashboard_metrics(db, current_user_id()),
        student_data=student_dashboard_data(db, current_user_id()) if g.current_user["role"] == "student" else None,
        teacher_data=teacher_dashboard_data(db, current_user_id()) if g.current_user["role"] == "teacher" else None,
        admin_data=admin_dashboard_data(db) if g.current_user["role"] == "admin" else None,
    )


@app.route("/student")
def student_portal() -> str:
    require_roles("student")
    return render_template("student.html", data=student_dashboard_data(get_db(), current_user_id()))


@app.route("/teacher")
def teacher_portal() -> str:
    require_roles("teacher")
    return render_template("teacher.html", data=teacher_dashboard_data(get_db(), current_user_id()))


@app.route("/admin")
def admin_portal() -> str:
    require_roles("admin")
    db = get_db()
    return render_template("admin.html", data=admin_dashboard_data(db), manage=admin_management_data(db))


@app.route("/admin/users/create", methods=["POST"])
def admin_create_user() -> Any:
    require_roles("admin")
    db = get_db()
    db.execute(
        "INSERT INTO users (name, role, major, interests, bio) VALUES (?, ?, ?, ?, ?)",
        (
            request.form["name"].strip(),
            request.form["role"].strip(),
            request.form["major"].strip(),
            request.form["interests"].strip(),
            request.form["bio"].strip(),
        ),
    )
    db.commit()
    flash("用户已新增。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/users/<int:user_id>/update", methods=["POST"])
def admin_update_user(user_id: int) -> Any:
    require_roles("admin")
    db = get_db()
    db.execute(
        "UPDATE users SET name = ?, role = ?, major = ?, interests = ?, bio = ? WHERE id = ?",
        (
            request.form["name"].strip(),
            request.form["role"].strip(),
            request.form["major"].strip(),
            request.form["interests"].strip(),
            request.form["bio"].strip(),
            user_id,
        ),
    )
    db.commit()
    flash("用户已更新。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
def admin_delete_user(user_id: int) -> Any:
    require_roles("admin")
    db = get_db()
    db.execute("DELETE FROM resource_ratings WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM activity_logs WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM submissions WHERE student_id = ? OR graded_by = ?", (user_id, user_id))
    db.execute("DELETE FROM enrollments WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM notifications WHERE author_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("用户已删除。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/courses/create", methods=["POST"])
def admin_create_course() -> Any:
    require_roles("admin")
    db = get_db()
    db.execute(
        "INSERT INTO courses (title, category, teacher_id, tags, description) VALUES (?, ?, ?, ?, ?)",
        (
            request.form["title"].strip(),
            request.form["category"].strip(),
            int(request.form["teacher_id"]),
            request.form["tags"].strip(),
            request.form["description"].strip(),
        ),
    )
    db.commit()
    flash("课程已新增。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/courses/<int:course_id>/update", methods=["POST"])
def admin_update_course(course_id: int) -> Any:
    require_roles("admin")
    db = get_db()
    db.execute(
        "UPDATE courses SET title = ?, category = ?, teacher_id = ?, tags = ?, description = ? WHERE id = ?",
        (
            request.form["title"].strip(),
            request.form["category"].strip(),
            int(request.form["teacher_id"]),
            request.form["tags"].strip(),
            request.form["description"].strip(),
            course_id,
        ),
    )
    db.commit()
    flash("课程已更新。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/courses/<int:course_id>/delete", methods=["POST"])
def admin_delete_course(course_id: int) -> Any:
    require_roles("admin")
    db = get_db()
    assignment_ids = [row["id"] for row in db.execute("SELECT id FROM assignments WHERE course_id = ?", (course_id,)).fetchall()]
    if assignment_ids:
        placeholders = ",".join("?" for _ in assignment_ids)
        db.execute(f"DELETE FROM submissions WHERE assignment_id IN ({placeholders})", tuple(assignment_ids))
    db.execute("DELETE FROM activity_logs WHERE course_id = ?", (course_id,))
    db.execute("DELETE FROM resources WHERE course_id = ?", (course_id,))
    db.execute("DELETE FROM assignments WHERE course_id = ?", (course_id,))
    db.execute("DELETE FROM enrollments WHERE course_id = ?", (course_id,))
    db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    db.commit()
    flash("课程已删除。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/resources/create", methods=["POST"])
def admin_create_resource() -> Any:
    require_roles("admin")
    db = get_db()
    file_path, original_filename = save_resource_upload(request.files.get("resource_file"))
    url = request.form.get("url", "").strip()
    if not url and not file_path:
        flash("请至少提供资源链接或上传本地文件。")
        return redirect(url_for("admin_portal", user_id=current_user_id()))
    db.execute(
        "INSERT INTO resources (course_id, title, resource_type, tags, url, summary, file_path, original_filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(request.form["course_id"]),
            request.form["title"].strip(),
            request.form["resource_type"].strip(),
            request.form["tags"].strip(),
            url,
            request.form["summary"].strip(),
            file_path,
            original_filename,
        ),
    )
    db.commit()
    flash("资源已新增。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/resources/<int:resource_id>/update", methods=["POST"])
def admin_update_resource(resource_id: int) -> Any:
    require_roles("admin")
    db = get_db()
    current = db.execute("SELECT file_path, original_filename FROM resources WHERE id = ?", (resource_id,)).fetchone()
    file_path, original_filename = save_resource_upload(request.files.get("resource_file"))
    db.execute(
        "UPDATE resources SET course_id = ?, title = ?, resource_type = ?, tags = ?, url = ?, summary = ?, file_path = ?, original_filename = ? WHERE id = ?",
        (
            int(request.form["course_id"]),
            request.form["title"].strip(),
            request.form["resource_type"].strip(),
            request.form["tags"].strip(),
            request.form.get("url", "").strip(),
            request.form["summary"].strip(),
            file_path or current["file_path"],
            original_filename or current["original_filename"],
            resource_id,
        ),
    )
    db.commit()
    flash("资源已更新。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/resources/<int:resource_id>/delete", methods=["POST"])
def admin_delete_resource(resource_id: int) -> Any:
    require_roles("admin")
    db = get_db()
    db.execute("DELETE FROM resource_ratings WHERE resource_id = ?", (resource_id,))
    db.execute("DELETE FROM activity_logs WHERE resource_id = ?", (resource_id,))
    db.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
    db.commit()
    flash("资源已删除。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/enrollments/create", methods=["POST"])
def admin_create_enrollment() -> Any:
    require_roles("admin")
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)",
        (int(request.form["student_id"]), int(request.form["course_id"])),
    )
    db.commit()
    flash("选课关系已新增。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/admin/enrollments/<int:enrollment_id>/delete", methods=["POST"])
def admin_delete_enrollment(enrollment_id: int) -> Any:
    require_roles("admin")
    db = get_db()
    db.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
    db.commit()
    flash("选课关系已删除。")
    return redirect(url_for("admin_portal", user_id=current_user_id()))


@app.route("/courses")
def courses() -> str:
    if g.current_user["role"] == "admin":
        return redirect(url_for("admin_portal", user_id=current_user_id()))
    focus_course_id = request.args.get("course_id", type=int)
    rows = course_rows(get_db(), current_user_id())
    if focus_course_id:
        rows = [row for row in rows if row["id"] == focus_course_id]
    return render_template("courses.html", courses=rows, focus_course_id=focus_course_id)


@app.route("/courses/<int:course_id>/enroll", methods=["POST"])
def enroll_course(course_id: int) -> Any:
    abort(403)


@app.route("/courses/<int:course_id>/resources/create", methods=["POST"])
def create_course_resource(course_id: int) -> Any:
    require_roles("teacher", "admin")
    if not can_manage_course(current_user_id(), course_id):
        abort(403)
    db = get_db()
    file_path, original_filename = save_resource_upload(request.files.get("resource_file"))
    url = request.form.get("url", "").strip()
    if not url and not file_path:
        flash("请至少提供资源链接或上传本地文件。")
        return redirect(url_for("courses", user_id=current_user_id(), course_id=course_id))
    db.execute(
        "INSERT INTO resources (course_id, title, resource_type, tags, url, summary, file_path, original_filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            course_id,
            request.form["title"].strip(),
            request.form["resource_type"].strip(),
            request.form["tags"].strip(),
            url,
            request.form["summary"].strip(),
            file_path,
            original_filename,
        ),
    )
    db.commit()
    flash("课程资源已新增。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=course_id))


@app.route("/courses/<int:course_id>/resources/<int:resource_id>/update", methods=["POST"])
def update_course_resource(course_id: int, resource_id: int) -> Any:
    require_roles("teacher", "admin")
    if not can_manage_course(current_user_id(), course_id):
        abort(403)
    db = get_db()
    current = db.execute("SELECT file_path, original_filename FROM resources WHERE id = ? AND course_id = ?", (resource_id, course_id)).fetchone()
    file_path, original_filename = save_resource_upload(request.files.get("resource_file"))
    db.execute(
        """
        UPDATE resources
        SET title = ?, resource_type = ?, tags = ?, url = ?, summary = ?, file_path = ?, original_filename = ?
        WHERE id = ? AND course_id = ?
        """,
        (
            request.form["title"].strip(),
            request.form["resource_type"].strip(),
            request.form["tags"].strip(),
            request.form.get("url", "").strip(),
            request.form["summary"].strip(),
            file_path or current["file_path"],
            original_filename or current["original_filename"],
            resource_id,
            course_id,
        ),
    )
    db.commit()
    flash("课程资源已更新。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=course_id))


@app.route("/courses/<int:course_id>/assignments/create", methods=["POST"])
def create_course_assignment(course_id: int) -> Any:
    require_roles("teacher", "admin")
    if not can_manage_course(current_user_id(), course_id):
        abort(403)

    db = get_db()
    db.execute(
        """
        INSERT INTO assignments (course_id, title, description, due_date, max_score)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            course_id,
            request.form["title"].strip(),
            request.form["description"].strip(),
            request.form["due_date"].strip(),
            int(request.form["max_score"]),
        ),
    )
    assignment_title = request.form["title"].strip()
    due_date = request.form["due_date"].strip()
    course = db.execute("SELECT title FROM courses WHERE id = ?", (course_id,)).fetchone()
    students = db.execute(
        "SELECT users.id FROM enrollments JOIN users ON users.id = enrollments.user_id WHERE enrollments.course_id = ? AND users.role = 'student'",
        (course_id,),
    ).fetchall()

    for student in students:
        db.execute(
            "INSERT INTO notifications (author_id, recipient_id, course_id, title, category, content, created_at, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                current_user_id(),
                student["id"],
                course_id,
                f"新作业：{assignment_title}",
                "作业",
                f"{course['title']} 发布了新作业《{assignment_title}》，截止日期 {due_date}。",
                now_string(),
                "高",
            ),
        )

    db.commit()
    flash("课程作业已发布，并已向学生发送提醒。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=course_id))


@app.route("/assignments/<int:assignment_id>/remind", methods=["POST"])
def remind_assignment_pending_students(assignment_id: int) -> Any:
    require_roles("teacher", "admin")
    db = get_db()
    assignment = db.execute(
        """
        SELECT assignments.*, courses.title AS course_title
        FROM assignments
        JOIN courses ON courses.id = assignments.course_id
        WHERE assignments.id = ?
        """,
        (assignment_id,),
    ).fetchone()
    if assignment is None:
        abort(404)
    if not can_manage_course(current_user_id(), assignment["course_id"]):
        abort(403)

    pending_students = db.execute(
        """
        SELECT users.id, users.name
        FROM enrollments
        JOIN users ON users.id = enrollments.user_id
        WHERE enrollments.course_id = ?
        AND users.role = 'student'
        AND NOT EXISTS (
            SELECT 1
            FROM submissions
            WHERE submissions.assignment_id = ?
            AND submissions.student_id = users.id
        )
        ORDER BY users.name
        """,
        (assignment["course_id"], assignment_id),
    ).fetchall()

    for student in pending_students:
        db.execute(
            "INSERT INTO notifications (author_id, recipient_id, course_id, title, category, content, created_at, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                current_user_id(),
                student["id"],
                assignment["course_id"],
                f"作业催交通知：{assignment['title']}",
                "作业催交",
                f"{student['name']}，请尽快提交《{assignment['title']}》，课程：{assignment['course_title']}，截止日期：{assignment['due_date']}。",
                now_string(),
                "高",
            ),
        )

    db.commit()
    flash(f"已向 {len(pending_students)} 名未提交学生发送提醒。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=assignment["course_id"]))


@app.route("/courses/<int:course_id>/messages/create", methods=["POST"])
def create_course_message(course_id: int) -> Any:
    require_roles("student")
    db = get_db()
    enrolled = db.execute("SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ?", (current_user_id(), course_id)).fetchone()
    if enrolled is None:
        abort(403)
    db.execute(
        "INSERT INTO course_messages (course_id, author_id, parent_id, content, created_at) VALUES (?, ?, NULL, ?, ?)",
        (course_id, current_user_id(), request.form["content"].strip(), now_string()),
    )
    db.commit()
    flash("问题已发布到课程留言板。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=course_id))


@app.route("/courses/<int:course_id>/messages/<int:message_id>/reply", methods=["POST"])
def reply_course_message(course_id: int, message_id: int) -> Any:
    require_roles("teacher", "admin")
    if not can_manage_course(current_user_id(), course_id):
        abort(403)
    db = get_db()
    db.execute(
        "INSERT INTO course_messages (course_id, author_id, parent_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (course_id, current_user_id(), message_id, request.form["content"].strip(), now_string()),
    )
    db.commit()
    flash("回复已发布。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=course_id))


@app.route("/courses/<int:course_id>/quizzes/create", methods=["POST"])
def create_quiz(course_id: int) -> Any:
    require_roles("teacher", "admin")
    if not can_manage_course(current_user_id(), course_id):
        abort(403)
    db = get_db()
    cursor = db.execute(
        "INSERT INTO quizzes (course_id, title, description, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (course_id, request.form["title"].strip(), request.form["description"].strip(), current_user_id(), now_string()),
    )
    quiz_id = cursor.lastrowid
    for index in range(1, 6):
        question = request.form.get(f"question_text_{index}", "").strip()
        if not question:
            continue
        option_a = request.form.get(f"option_a_{index}", "").strip()
        option_b = request.form.get(f"option_b_{index}", "").strip()
        option_c = request.form.get(f"option_c_{index}", "").strip()
        option_d = request.form.get(f"option_d_{index}", "").strip()
        if not all([option_a, option_b, option_c, option_d]):
            continue
        db.execute(
            "INSERT INTO quiz_questions (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                quiz_id,
                question,
                option_a,
                option_b,
                option_c,
                option_d,
                request.form.get(f"correct_option_{index}", "A").strip(),
                request.form.get(f"explanation_{index}", "").strip(),
            ),
        )
    db.commit()
    flash("在线测试已发布。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=course_id))


@app.route("/quizzes/<int:quiz_id>/submit", methods=["POST"])
def submit_quiz(quiz_id: int) -> Any:
    require_roles("student")
    db = get_db()
    quiz = db.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        abort(404)
    enrolled = db.execute("SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ?", (current_user_id(), quiz["course_id"])).fetchone()
    if enrolled is None:
        abort(403)
    existing = db.execute("SELECT id FROM quiz_attempts WHERE quiz_id = ? AND student_id = ?", (quiz_id, current_user_id())).fetchone()
    if existing:
        flash("该测试已完成，不能再次作答。")
        return redirect(url_for("courses", user_id=current_user_id(), course_id=quiz["course_id"]))
    questions = db.execute("SELECT * FROM quiz_questions WHERE quiz_id = ? ORDER BY id", (quiz_id,)).fetchall()
    if not questions:
        flash("该测试还没有题目。")
        return redirect(url_for("courses", user_id=current_user_id(), course_id=quiz["course_id"]))
    correct = 0
    answers = []
    for question in questions:
        selected = request.form.get(f"question_{question['id']}", "").strip().upper() or "未作答"
        is_correct = int(selected == question["correct_option"])
        correct += is_correct
        answers.append((question["id"], selected, is_correct))
    score = round(correct / len(questions) * 100, 1)
    cursor = db.execute(
        "INSERT INTO quiz_attempts (quiz_id, student_id, score, completed_at) VALUES (?, ?, ?, ?)",
        (quiz_id, current_user_id(), score, now_string()),
    )
    attempt_id = cursor.lastrowid
    db.executemany(
        "INSERT INTO quiz_answers (attempt_id, question_id, selected_option, is_correct) VALUES (?, ?, ?, ?)",
        [(attempt_id, qid, selected, is_correct) for qid, selected, is_correct in answers],
    )
    db.commit()
    flash(f"测试已提交，得分 {score}。")
    return redirect(url_for("courses", user_id=current_user_id(), course_id=quiz["course_id"]))


@app.route("/assignments")
def assignments() -> str:
    db = get_db()
    course_id = request.args.get("course_id", type=int)
    assignment_id = request.args.get("assignment_id", type=int)
    submission_id = request.args.get("submission_id", type=int)

    if g.current_user["role"] == "admin":
        return redirect(url_for("admin_portal", user_id=current_user_id()))

    if g.current_user["role"] == "student":
        rows = student_assignment_rows(db, current_user_id())
        if course_id:
            rows = [row for row in rows if row["course_id"] == course_id]
        return render_template(
            "assignments.html",
            student_assignments=rows,
            review_rows=None,
            focus_assignment_id=assignment_id,
            focus_submission_id=submission_id,
        )

    reviewer_id = current_user_id() if g.current_user["role"] == "teacher" else None
    rows = teacher_submission_rows(db, reviewer_id)
    if course_id:
        rows = [row for row in rows if row["course_id"] == course_id]
    return render_template(
        "assignments.html",
        student_assignments=None,
        review_rows=rows,
        focus_assignment_id=assignment_id,
        focus_submission_id=submission_id,
    )



@app.route("/assignments/submit", methods=["POST"])
def submit_assignment() -> Any:
    require_roles("student")
    db = get_db()
    assignment_id = int(request.form["assignment_id"])
    upload = request.files.get("submission_file")
    if upload is None or not upload.filename:
        flash("请先选择要上传的作业文件。")
        return redirect(url_for("assignments", user_id=current_user_id()))
    filename = secure_filename(upload.filename)
    stored_name = f"{current_user_id()}_{assignment_id}_{filename}"
    stored_path = UPLOAD_DIR / stored_name
    upload.save(stored_path)
    existing = db.execute(
        "SELECT id FROM submissions WHERE assignment_id = ? AND student_id = ?",
        (assignment_id, current_user_id()),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE submissions
            SET filename = ?, stored_path = ?, submitted_at = ?, score = NULL, feedback = NULL, graded_by = NULL, graded_at = NULL
            WHERE id = ?
            """,
            (filename, str(stored_path.resolve()), now_string(), existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO submissions (assignment_id, student_id, filename, stored_path, submitted_at) VALUES (?, ?, ?, ?, ?)",
            (assignment_id, current_user_id(), filename, str(stored_path.resolve()), now_string()),
        )
    db.commit()
    flash("作业已提交，待提交数量会根据最新状态自动更新。")
    return redirect(url_for("assignments", user_id=current_user_id()))


@app.route("/submissions/<int:submission_id>/download")
def download_submission(submission_id: int) -> Any:
    row = get_db().execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    if row is None:
        abort(404)
    return send_file(row["stored_path"], as_attachment=True, download_name=row["filename"])


@app.route("/submissions/<int:submission_id>/grade", methods=["POST"])
def grade_submission(submission_id: int) -> Any:
    require_roles("teacher", "admin")
    db = get_db()
    score = int(request.form["score"])
    feedback = request.form["feedback"].strip()
    db.execute(
        "UPDATE submissions SET score = ?, feedback = ?, graded_by = ?, graded_at = ? WHERE id = ?",
        (score, feedback, current_user_id(), now_string(), submission_id),
    )
    db.commit()
    flash("作业批改已完成。")
    return redirect(url_for("assignments", user_id=current_user_id()))


@app.route("/resources")
def resources() -> str:
    db = get_db()
    query = request.args.get("q", "").strip().lower()
    rows = resource_rows(db, current_user_id())
    if query:
        rows = [row for row in rows if query in " ".join([row["title"], row["course_title"], row["resource_type"], row["tags"]]).lower()]
    return render_template("resources.html", resources=rows, favorites=favorite_resource_rows(db, current_user_id()), query=query)


@app.route("/resources/<int:resource_id>/open")
def open_resource(resource_id: int) -> Any:
    db = get_db()
    row = db.execute("SELECT course_id, url, file_path, original_filename FROM resources WHERE id = ?", (resource_id,)).fetchone()
    if row is None:
        abort(404)
    db.execute(
        "INSERT INTO activity_logs (user_id, resource_id, course_id, action, weight, created_at) VALUES (?, ?, ?, 'view', 1.0, ?)",
        (current_user_id(), resource_id, row["course_id"], now_string()),
    )
    db.commit()
    if row["file_path"]:
        return send_file(row["file_path"], as_attachment=False, download_name=row["original_filename"] or Path(row["file_path"]).name)
    if not row["url"]:
        flash("该资源暂未配置链接或本地文件。")
        return redirect(url_for("resources", user_id=current_user_id()))
    return redirect(row["url"])



@app.route("/resources/<int:resource_id>/download")
def download_resource(resource_id: int) -> Any:
    db = get_db()
    row = db.execute(
        """
        SELECT resources.*, courses.title AS course_title
        FROM resources
        JOIN courses ON courses.id = resources.course_id
        WHERE resources.id = ?
        """,
        (resource_id,),
    ).fetchone()
    if row is None:
        abort(404)
    db.execute(
        "INSERT INTO activity_logs (user_id, resource_id, course_id, action, weight, created_at) VALUES (?, ?, ?, 'download', 1.3, ?)",
        (current_user_id(), resource_id, row["course_id"], now_string()),
    )
    db.commit()
    if row["file_path"]:
        return send_file(row["file_path"], as_attachment=True, download_name=row["original_filename"] or Path(row["file_path"]).name)
    content = (
        f"资源标题：{row['title']}\n"
        f"所属课程：{row['course_title']}\n"
        f"资源类型：{row['resource_type']}\n"
        f"标签：{row['tags']}\n"
        f"资源说明：{row['summary']}\n"
        f"在线访问：{row['url']}\n"
    )
    return send_file(
        io.BytesIO(content.encode("utf-8")),
        as_attachment=True,
        download_name=f"{secure_filename(row['title']) or 'resource'}.txt",
        mimetype="text/plain",
    )



@app.route("/resources/<int:resource_id>/favorite", methods=["POST"])
def favorite_resource(resource_id: int) -> Any:
    require_roles("student", "teacher", "admin")
    db = get_db()
    resource = db.execute("SELECT course_id FROM resources WHERE id = ?", (resource_id,)).fetchone()
    if resource is None:
        abort(404)
    exists = db.execute(
        "SELECT 1 FROM activity_logs WHERE user_id = ? AND resource_id = ? AND action = 'favorite' LIMIT 1",
        (current_user_id(), resource_id),
    ).fetchone()
    if exists is None:
        db.execute(
            "INSERT INTO activity_logs (user_id, resource_id, course_id, action, weight, created_at) VALUES (?, ?, ?, 'favorite', 2.5, ?)",
            (current_user_id(), resource_id, resource["course_id"], now_string()),
        )
        db.commit()
        flash("资源已加入收藏。")
    else:
        flash("该资源已在收藏记录中。")
    return redirect(url_for("resources", user_id=current_user_id()))


@app.route("/resources/<int:resource_id>/unfavorite", methods=["POST"])
def unfavorite_resource(resource_id: int) -> Any:
    require_roles("student", "teacher", "admin")
    db = get_db()
    db.execute(
        "DELETE FROM activity_logs WHERE user_id = ? AND resource_id = ? AND action = 'favorite'",
        (current_user_id(), resource_id),
    )
    db.commit()
    flash("已取消收藏，资源会从个人收藏栏移除。")
    return redirect(url_for("resources", user_id=current_user_id()))


@app.route("/resources/<int:resource_id>/rate", methods=["POST"])
def rate_resource(resource_id: int) -> Any:
    db = get_db()
    rating = max(1, min(5, int(request.form["rating"])))
    comment = request.form.get("comment", "").strip()
    existing = db.execute(
        "SELECT id FROM resource_ratings WHERE resource_id = ? AND user_id = ?",
        (resource_id, current_user_id()),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE resource_ratings SET rating = ?, comment = ?, created_at = ? WHERE id = ?",
            (rating, comment, now_string(), existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO resource_ratings (resource_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (resource_id, current_user_id(), rating, comment, now_string()),
        )
    course_id = db.execute("SELECT course_id FROM resources WHERE id = ?", (resource_id,)).fetchone()["course_id"]
    db.execute(
        "INSERT INTO activity_logs (user_id, resource_id, course_id, action, weight, created_at) VALUES (?, ?, ?, 'rate', 3.0, ?)",
        (current_user_id(), resource_id, course_id, now_string()),
    )
    db.commit()
    flash("资源评分已更新，资源平均评分和推荐画像都会随之变化。")
    return redirect(url_for("resources", user_id=current_user_id()))


@app.route("/announcements")
def announcements() -> str:
    db = get_db()
    publish_courses = []
    if g.current_user["role"] == "teacher":
        publish_courses = db.execute("SELECT id, title FROM courses WHERE teacher_id = ? ORDER BY id", (current_user_id(),)).fetchall()
    elif g.current_user["role"] == "admin":
        publish_courses = db.execute("SELECT id, title FROM courses ORDER BY id").fetchall()
    return render_template(
        "announcements.html",
        notifications=notification_rows(db, current_user_id(), g.current_user["role"]),
        publish_courses=publish_courses,
    )


@app.route("/announcements/create", methods=["POST"])
def create_announcement() -> Any:
    require_roles("teacher", "admin")
    db = get_db()
    title = request.form["title"].strip()
    category = request.form["category"].strip()
    content = request.form["content"].strip()
    priority = request.form["priority"].strip()
    target = request.form.get("target", "all")
    course_id = request.form.get("course_id", type=int)

    if target == "course":
        if not course_id:
            flash("请选择要定向发送的课程。")
            return redirect(url_for("announcements", user_id=current_user_id()))
        if g.current_user["role"] == "teacher" and not can_manage_course(current_user_id(), course_id):
            abort(403)
        students = db.execute(
            "SELECT users.id FROM enrollments JOIN users ON users.id = enrollments.user_id WHERE enrollments.course_id = ? AND users.role = 'student'",
            (course_id,),
        ).fetchall()
        for student in students:
            db.execute(
                "INSERT INTO notifications (author_id, recipient_id, course_id, title, category, content, created_at, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (current_user_id(), student["id"], course_id, title, category, content, now_string(), priority),
            )
        db.commit()
        flash(f"通知已定向发送给该课程的 {len(students)} 名学生。")
    else:
        db.execute(
            "INSERT INTO notifications (author_id, recipient_id, course_id, title, category, content, created_at, priority) VALUES (?, NULL, ?, ?, ?, ?, ?, ?)",
            (current_user_id(), course_id, title, category, content, now_string(), priority),
        )
        db.commit()
        flash("通知已发布。")
    return redirect(url_for("announcements", user_id=current_user_id()))


@app.route("/announcements/<int:notification_id>/delete", methods=["POST"])
def delete_announcement(notification_id: int) -> Any:
    require_roles("teacher", "admin")
    db = get_db()
    row = db.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,)).fetchone()
    if row is None:
        abort(404)
    if g.current_user["role"] == "teacher" and row["author_id"] != current_user_id():
        abort(403)
    db.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    db.commit()
    flash("通知已删除。")
    return redirect(url_for("announcements", user_id=current_user_id()))



@app.route("/analytics")
def analytics() -> str:
    require_roles("student")
    return render_template("analytics.html", analytics=analytics_snapshot(get_db(), current_user_id()))


@app.route("/recommendations")
def recommendations() -> str:
    require_roles("student")
    db = get_db()
    return render_template(
        "recommendations.html",
        items=recommend_resources(db, current_user_id(), top_n=10),
        behavior_mix=db.execute(
            "SELECT action, COUNT(*) AS total FROM activity_logs WHERE user_id = ? GROUP BY action ORDER BY total DESC",
            (current_user_id(),),
        ).fetchall(),
        interest_vector=sorted(build_user_interest_vector(db, current_user_id()).items(), key=lambda item: item[1], reverse=True)[:8],
    )


@app.route("/activity/log", methods=["POST"])
def log_activity() -> Any:
    require_roles("student")
    db = get_db()
    resource_id = int(request.form["resource_id"])
    action = request.form["action"]
    weight_map = {"view": 1.0, "favorite": 2.5, "rate": 3.0}
    course_id = db.execute("SELECT course_id FROM resources WHERE id = ?", (resource_id,)).fetchone()["course_id"]
    db.execute(
        "INSERT INTO activity_logs (user_id, resource_id, course_id, action, weight, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (current_user_id(), resource_id, course_id, action, weight_map.get(action, 1.0), now_string()),
    )
    if action == "rate":
        existing = db.execute(
            "SELECT id FROM resource_ratings WHERE resource_id = ? AND user_id = ?",
            (resource_id, current_user_id()),
        ).fetchone()
        if existing is None:
            db.execute(
                "INSERT INTO resource_ratings (resource_id, user_id, rating, comment, created_at) VALUES (?, ?, 5, ?, ?)",
                (resource_id, current_user_id(), "来自推荐模块的高评分反馈", now_string()),
            )
    db.commit()
    flash("行为已记录，行为构成和 Top-N 推荐会根据最新数据即时变化。")
    return redirect(url_for("recommendations", user_id=current_user_id()))


@app.route("/refresh", methods=["POST"])
def refresh() -> Any:
    init_db()
    flash("系统已重置为默认演示数据。")
    return redirect(url_for("index", user_id=current_user_id()))


if __name__ == "__main__":
    if not DATABASE_PATH.exists():
        init_db()
    app.run(debug=True)

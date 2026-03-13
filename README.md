# 智慧教学推荐系统

这是一个可运行的教学平台 MVP，重点不是静态展示，而是把最基本的教学业务流程跑通：

- 学生端、教师端、管理端分页面
- 课程中心、作业中心、资源中心、通知中心
- 作业文件上传、教师批改、分数与反馈回写
- 资源打开、下载、评分和推荐行为记录
- 通知发布权限控制
- 基于行为日志、评分和热度的 Top-N 推荐

## 技术栈

- Python 3.9+
- Flask
- SQLite

## 快速启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

打开 `http://127.0.0.1:5000`。

## 当前实现的动态逻辑

- 课程进度：按学生已浏览资源数 / 课程资源总数计算
- 作业提交率：按课程提交记录 / 应提交总槽位计算
- 资源平均评分：按 `resource_ratings` 全站实时计算
- 待提交作业：按当前学生尚未提交的作业数实时计算
- 推荐行为构成：按 `activity_logs` 中浏览、收藏、评分、下载等行为统计
- Top-N 推荐：融合内容相似度、协同过滤和资源热度

## 页面说明

- `/`：系统总览
- `/student`：学生端
- `/teacher`：教师端
- `/admin`：管理端
- `/courses`：课程中心
- `/assignments`：作业中心
- `/resources`：资源中心
- `/announcements`：通知中心
- `/analytics`：学习分析
- `/recommendations`：个性化推荐
- `/refresh`：重置并刷新平台数据

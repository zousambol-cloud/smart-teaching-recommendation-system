# 智慧教学推荐系统

基于开题报告《智慧教学推荐系统》实现的一个可运行毕业设计原型，覆盖用户管理、课程管理、作业管理、资源共享、通知发布、学习行为分析和混合推荐算法。

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

浏览器打开 `http://127.0.0.1:5000`。

## 推荐算法

- 内容推荐：使用用户兴趣标签和历史行为构建兴趣向量，与资源标签向量计算余弦相似度
- 协同过滤：根据用户-资源行为权重矩阵计算相似用户的偏好
- 热门兜底：结合资源下载量和评分缓解冷启动

最终评分公式：

```text
total_score = 0.5 * content_score + 0.35 * collaborative_score + 0.15 * hot_score
```

## 页面说明

- `/`：系统总览与模块入口
- `/courses`：课程中心
- `/assignments`：作业中心
- `/resources`：资源中心
- `/announcements`：通知中心
- `/analytics`：学习分析
- `/recommendations`：推荐解释页，可模拟浏览、收藏、评分行为
- `/refresh`：刷新平台内容

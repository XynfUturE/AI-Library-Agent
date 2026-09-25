# AI Library Agent

一个基于大型语言模型（LLM）和 Tool Calling 架构开发的智能图书馆管理系统。

本项目将传统的 **Python + SQLite Library Management System** 与 AI Agent 结合，使用户可以通过自然语言完成图书搜索、借阅、归还、逾期查询、罚款查询、罚款支付、借阅历史查询以及图书推荐等操作。

AI Agent 不直接修改数据库，而是根据用户请求选择预先定义的 Python Tools，由后端业务逻辑执行实际操作，再将真实的数据库结果返回给 Agent。

---

## 1. 项目简介

AI Library Agent 的主要目标不是简单地制作一个聊天机器人，而是探索如何让 LLM 与真实的软件系统进行交互。

用户可以直接使用自然语言提出请求，例如：

* `Borrow Python Programming`
* `Do I have any overdue books?`
* `Show me the borrowing history.`
* `Do I have any unpaid fines?`
* `Recommend an available programming book.`

Agent 会：

```text
用户请求
   ↓
DeepSeek LLM
   ↓
判断需要使用的 Tool
   ↓
执行 Python Tool
   ↓
访问 SQLite Database
   ↓
获得真实结果
   ↓
更新 Agent State
   ↓
返回最终结果
```

因此，AI 主要负责**理解、决策和工具选择**，而具体的数据操作和业务规则仍然由 Python 程序控制。

---

## 2. 主要功能

### 2.1 图书管理

系统支持：

* 按标题或关键字搜索图书
* 检查图书可用性
* 借阅图书
* 归还图书
* 到期前续借
* 借不到的书也有下一步：馆内有就排队预约，馆内没有就留下荐购
* 归还时自动把下一位读者的预约置为可取
* 查看当前借阅
* 查看逾期图书
* 查看借阅历史
* 查看当前可借图书
* 管理端辅助接口：`POST /api/admin/books/lookup-isbn`（OpenLibrary 查书目）、`GET /api/admin/analytics`（流通统计）

例如：

```text
Search Python
```

或者：

```text
Borrow Database Systems
```

---

### 2.2 Fine Management

系统支持完整的罚款处理流程：

* 计算当前罚款
* 查询未支付罚款
* 支付罚款
* 防止支付 active loan 的 estimated fine
* 防止重复支付同一笔罚款
* 防止支付其他用户的罚款

当前系统规则：

```text
Loan Period: 14 days
Fine: $0.50 per overdue calendar day
```

对于还没有归还的图书，系统显示的是：

```text
Estimated Fine
```

图书归还之后，系统记录：

```text
Final Fine
```

只有最终罚款才能进入支付流程。

---

## 3. AI Agent 架构

整个系统采用 Tool Calling Agent Architecture。

```text
                  ┌─────────────────┐
                  │      User       │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   DeepSeek LLM │
                  └────────┬────────┘
                           │
                    Tool Selection
                           │
                           ▼
                  ┌─────────────────┐
                  │   Python Tool   │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  SQLite Database│
                  └────────┬────────┘
                           │
                      Tool Result
                           │
                           ▼
                  ┌─────────────────┐
                  │   Agent State   │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Final Response  │
                  └─────────────────┘
```

这里最重要的设计原则是：

**LLM 不直接操作数据库。**

Agent 只能通过系统提供的 Tools 与数据库交互。

这样可以让 AI 的自然语言能力和后端的确定性业务逻辑分离。

---

## 4. Borrowing Decision Workflow

当用户通过书名借书时，Agent 遵循明确的决策流程。

例如用户输入：

```text
Borrow Database Systems
```

Agent 应执行：

```text
search_books
      ↓
identify actual book
      ↓
check_book_availability
      ↓
if available
      ↓
borrow_book
```

也就是说：

1. 先搜索图书。
2. 使用数据库返回的真实 Book ID。
3. 检查实际可用性。
4. 只有确认可以借阅后才执行 `borrow_book`。
5. 借阅成功后结束当前任务。

Agent 不允许自己创造：

* Book ID
* Book Title
* Author
* Availability（"无在借记录"的缓存值：启动时自动修复，管理端 API 拒绝把在借图书改回可借）
* Due Date
* Fine Amount
* Borrowing Result

这保证了 AI 输出始终建立在真实数据库数据之上。

---

## 5. Alternative Book Workflow

当用户想借的图书不可用时，Agent 不会自动替换图书，而是先征求用户意见。

例如：

```text
Python Programming is unavailable.
Would you like me to find an available alternative?
```

如果用户输入：

```text
yes
```

则执行：

```text
list_available_books
        ↓
select actual available book
        ↓
borrow_book
```

如果用户输入：

```text
no
```

则结束当前任务。

这种设计可以避免 AI 在未经用户同意的情况下执行实际借阅操作。

---

## 6. AI Tools

当前 Agent 一共提供 16 个 Tools：

| Tool                         | 功能          |
| ---------------------------- | ----------- |
| `search_books`               | 根据图书标题关键字搜索 |
| `check_book_availability`    | 检查指定图书是否可借  |
| `borrow_book`                | 借阅图书        |
| `return_book`                | 归还当前用户借阅的图书 |
| `renew_book`                 | 续借未逾期的借阅        |
| `request_book`               | 排队预约，或提交荐购      |
| `get_my_holds`               | 查看自己的预约与荐购      |
| `cancel_hold`                | 撤回自己提交的请求       |
| `get_current_borrowed_books` | 查看当前借阅      |
| `get_overdue_books`          | 查看当前逾期图书    |
| `get_book_loan_details`      | 查看指定图书的借阅详情 |
| `calculate_fine`             | 计算当前或最终罚款   |
| `get_unpaid_fines`           | 查询未支付罚款     |
| `pay_fine`                   | 支付未支付的最终罚款  |
| `get_borrow_history`         | 查看借阅历史      |
| `list_available_books`       | 查看所有当前可借图书  |

Tools 的定义（schema）与系统提示词位于：

```text
agent/core.py
```

Agent 循环只实现一次（`LibraryAgent`，Web 与 `main.py` CLI 共用同一个实例逻辑），实际业务逻辑主要位于：

```text
agent/tools.py
```

---

## 7. Agent State

每个会话持有一个 `LibraryAgent` 实例，Agent 状态只包含：

```text
user_id            当前登录用户（由系统注入，LLM 无法指定）
messages           对话历史
trim window        限制每轮 prompt 大小的裁剪窗口
```

多步骤流程不需要额外的状态机：模型通过 tool call 表达每一步动作，最终回答只以 tool 返回的真实结果为依据。例如：

```text
User Request
    ↓
search_books（不可借）
    ↓
Agent 说明情况并给出可借替代
    ↓
User: yes
    ↓
borrow_book
```

这样就不存在"状态机与数据库不同步"的问题，Tool Result 是唯一事实来源。

---

## 8. Authentication

系统包含完整的用户认证功能：

* User Registration
* Login
* Demo Login
* Logout
* Password Validation
* Password Hashing
* Password Verification
* Change Password
* Profile Update

用户登录后，系统会把当前用户保存到：

```text
LibraryAgent.user_id
```

后续所有需要用户身份的 Tool 都自动使用这个 ID。

用户不需要手动输入：

```text
user_id
```

---

## 9. User Data Isolation

数据隔离是本项目的重要设计之一。

系统不会只在前端显示不同用户名，而是在后端 Tool 和 SQL 查询中真正使用：

```text
user_id
```

例如：

```text
Authenticated User
        ↓
LibraryAgent.user_id
        ↓
execute_tool()
        ↓
user-specific tool
        ↓
SQL query with user_id
```

因此用户只能访问属于自己的：

* Current Loans
* Overdue Books
* Unpaid Fines
* Borrowing History

写操作同样进行数据隔离。

例如：

```text
User A
↓
Borrow Book 1

User B
↓
Return Book 1
```

User B 无法归还 User A 的借阅记录。

同样：

```text
User A
↓
Fine for Book 1

User B
↓
Pay Book 1 Fine
```

User B 也无法支付 User A 的罚款。

这种设计可以防止 Cross-user Data Access。

---

## 10. Borrowing History

系统不会让 LLM 自己生成 Markdown Table。

Agent 只负责调用：

```text
get_borrow_history
```

然后由 Python + Rich 渲染表格。

系统会根据终端宽度自动调整显示：

```text
Narrow Terminal
        ↓
简化字段

Medium Terminal
        ↓
中等字段数量

Wide Terminal
        ↓
完整字段
```

因此 Borrowing History 在不同终端宽度下都能够保持较好的可读性。

---

## 11. Fine System

罚款按照 overdue calendar days 计算：

```text
$0.50 × overdue days
```

例如：

```text
Due Date:
2026-08-20

Returned:
2026-08-30

Late Days:
10

Fine:
$5.00
```

返回结果中可以包含：

```text
fine_amount
fine_amount_cents
fine_status
fine_paid
fine_paid_at
```

使用 cents 存储金额：

```text
500 cents = $5.00
```

这种方式可以减少直接使用浮点数保存货币金额产生的问题。

---

## 12. Payment Workflow

罚款支付必须满足：

```text
Book Returned
      ↓
Final Fine Recorded
      ↓
Fine Unpaid
      ↓
pay_fine
      ↓
Fine Paid
```

系统不会允许：

```text
Active Loan
      ↓
Estimated Fine
      ↓
Pay Fine
```

也不会允许：

```text
Already Paid Fine
      ↓
Pay Again
```

`pay_fine()` 使用事务保护，并在更新后检查数据库实际修改行数，以减少重复支付的风险。

---

## 13. Book Recommendation

Recommendation 与 Borrowing 是两个不同的任务。

例如：

```text
Recommend an available programming book.
```

只代表：

> 推荐一本合适的书。

并不意味着：

> 自动借这本书。

因此 Recommendation Workflow 是：

```text
User Request
      ↓
list_available_books
      ↓
Evaluate actual books
      ↓
Rank according to request
      ↓
Recommend
```

推荐系统只能选择数据库中真实存在且当前可用的图书。

例如：

```text
Recommend something about databases.
```

Agent 会从当前可用图书中寻找最匹配的真实书籍，而不会虚构书名、作者或者图书内容。

---

## 14. Conversation Context

Agent 可以理解部分上下文引用，例如：

```text
that one
this book
the recommended one
your recommendation
it
another one
```

例如：

```text
User:
Recommend a programming book.

Agent:
Python Programming is currently available.

User:
Can I borrow that one?
```

当上下文明确时，Agent 可以理解：

```text
that one
```

指的是刚才推荐的书。

如果同时存在多个可能的目标，Agent 应该请求用户进一步说明，而不是自行猜测。

### 每轮成本的控制手段

Agent 循环的每一步都会重发系统提示词、Tool Schema 与完整对话，而一个问题可能要走多步。三处限制把开销封顶：

* `MAX_STEPS`（5）限制单轮对话的 LLM 调用次数。
* 对话窗口只保留最近的用户轮次，而且是攒够一批再裁剪，避免每一步都打掉 prompt 缓存前缀。
* 工具结果进入上下文前会被截断：超过 25 行的列表会变成 `{"total": n, "returned": 25, "truncated": true, "items": [...]}`，模型仍然知道真实条数。只有 LLM 看到这份截断副本，Web 界面拿到的仍是完整数据。

stdout 上的 `[usage]` 行会按步打印 `prompt` / `cache_hit` / `cache_miss` / `completion` / `reasoning`，这是判断 token 花在哪最快的方式。

---

## 15. Error Handling

项目对错误进行了分层处理。

用户不会直接看到：

* SQL statements
* Stack traces
* Internal exceptions
* Implementation details
* API secrets

正常用户看到的是：

```text
The library operation could not be completed.
```

或者更具体的用户友好信息。

开发过程中可以通过：

```python
DEBUG_MODE = True
```

获取更多调试信息。

正常运行时则保持：

```python
DEBUG_MODE = False
```

---

## 16. Database Design

系统使用 SQLite 作为持久化数据库。

主要包含以下核心表。

### `users`

用于保存：

* User ID
* Username
* Password Hash
* Full Name
* Email
* Account Status（`active`）
* Role（`member` / `admin`）
* Created Time

---

### `books`

用于保存：

* Book ID
* Title
* Author
* Availability
* Category ID（分类引用）
* ISBN
* Publisher
* Pub Date
* Language
* Location

---

### `categories`

用于保存分类树（目录可多级嵌套）：

* Category ID
* Parent ID（自引用，一级分类为 `NULL`）
* Name
* Sort Order
* Is Active

---

### `borrow_records`

用于保存：

* Loan ID
* User ID
* Book ID
* Book Title
* Borrowed At
* Due Date
* Returned At
* Fine Amount
* Fine Payment Status
* Fine Payment Time
* Renewals（续借次数）

---

### `holds`

需求队列，预约与荐购共用一张表：

* 请求 ID、读者 ID
* 图书引用（荐购时为 `NULL`）
* 读者填写的书名
* kind：`hold`（馆内有但已借空）或 `suggestion`（馆内没有）
* status：`waiting` → `ready`（归还后被留给他）→ `cancelled`
* 创建时间、变为可取的时间

---

## 17. Database Transaction Safety

数据库写操作使用：

```python
try:
    ...
    connection.commit()

except Exception:
    connection.rollback()

finally:
    connection.close()
```

这样可以保证：

```text
Success
→ commit

Failure
→ rollback

Always
→ close connection
```

对于 Borrowing 和 Payment 等关键写操作，还使用：

```text
BEGIN IMMEDIATE
```

以减少并发操作造成状态冲突的风险。

---

## 18. Authentication and Security

项目目前采用以下安全措施：

* API Key 使用环境变量保存
* `.env` 被 `.gitignore` 排除
* `.env.example` 不包含真实 API Key
* Password 使用 hashing 保存
* Login 使用 password verification
* Tool 自动使用 authenticated user
* Cross-user operations 在后端拒绝
* Database operations 使用 transactions
* Internal errors 不直接显示给普通用户

实际 API Key 不应该写入：

```python
api_key = "..."
```

而应该使用：

```python
api_key = os.getenv("DEEPSEEK_API_KEY")
```

---

## 19. Technology Stack

| 技术            | 用途                                  |
| ------------- | ------------------------------------- |
| Python 3.10+  | 主程序与业务逻辑                          |
| FastAPI       | Web API 框架                           |
| uvicorn       | ASGI 服务器                            |
| Jinja2        | HTML 模板引擎                           |
| SQLite        | 数据持久化                              |
| DeepSeek API  | LLM / AI Agent（OpenAI 兼容接口）        |
| OpenAI SDK    | API 调用                              |
| python-dotenv | 环境变量管理                            |
| Rich          | Terminal UI（CLI）                     |
| Vanilla JS    | 浏览器前端（无需构建步骤）                  |
| CSS           | Token 化设计系统                        |

模型名称通过 `agent/core.py` 中的常量 `MODEL_NAME` 统一配置。

---

## 20. Project Structure

```text
.
├── main.py                 # 终端 CLI（LibraryAgent 的瘦客户端）
├── requirements.txt
├── requirements-dev.txt    # 仅测试依赖
├── requirements-mcp.txt    # 可选的 MCP 依赖
├── pytest.ini
├── render.yaml             # Render 一键部署蓝图
├── Dockerfile
├── .dockerignore
├── .env.example
├── .gitignore
├── README.md
├── README_CN.md
│
├── agent/                  # 共享业务层
│   ├── analytics.py        # 馆员统计查询
│   ├── auth.py
│   ├── catalog.py
│   ├── core.py             # 唯一的 Agent 循环 + Tool Schema
│   ├── database.py         # SQLite 表结构、迁移 + 种子数据
│   ├── isbn.py             # ISBN 查书目（OpenLibrary）
│   └── tools.py            # 图书馆业务逻辑
│
├── scripts/
│   ├── due_reminders.py    # 供 cron 调用的到期/逾期清单
│   ├── isbn_lookup.py      # 命令行 ISBN 查书
│   └── mcp_server.py       # 可选 MCP 服务端（需 requirements-mcp.txt）
│
├── tests/                  # pytest 测试（离线、临时数据库）
│   ├── conftest.py
│   ├── test_agent_loop.py
│   ├── test_analytics.py
│   ├── test_catalog.py
│   ├── test_due_reminders.py
│   ├── test_fines.py
│   ├── test_holds.py
│   ├── test_isbn.py
│   ├── test_loans.py
│   ├── test_mcp_server.py
│   ├── test_reminders.py
│   └── test_web_api.py
│
├── .github/workflows/ci.yml
│
└── web/                    # FastAPI 应用
    ├── app.py
    ├── models.py
    ├── session.py          # 内存会话存储
    ├── templates/
    │   └── index.html
    └── static/
        ├── assets/
        ├── css/
        │   ├── tokens.css
        │   ├── base.css
        │   ├── components.css
        │   └── views/
        └── js/
            ├── app.js
            ├── lib/
            └── views/
```

其中 `database/` 目录在运行时创建，用于存放本地 SQLite 数据文件；该目录已被 Git 忽略，不会提交到仓库。

---

## 21. Installation

### 创建 Virtual Environment

Windows：

```powershell
python -m venv .venv
```

激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

---

## 22. Environment Configuration

创建本地：

```text
.env
```

内容：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
ENABLE_DEMO_LOGIN=1
CHAT_RATE_LIMIT_PER_MINUTE=20
# LIBRARY_DB_PATH=/data/library.db
```

程序通过：

```python
os.getenv("DEEPSEEK_API_KEY")
```

读取 API Key。

`CHAT_RATE_LIMIT_PER_MINUTE` 限制单个会话每分钟的聊天请求数（默认 20，设为 0 关闭）。聊天是唯一会真实花钱的接口，所以默认开启限流。

到期提醒的发送配置是独立的（只有 `scripts/due_reminders.py` 会对外发消息）：

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=library@example.com
SMTP_PASSWORD=your_smtp_password
SMTP_FROM=library@example.com
SMTP_TLS=1
```

没有 `SMTP_HOST` 时，脚本仍可打印清单，但 `--email` 会明确报错退出。

`LIBRARY_DB_PATH` 可选，用于把 SQLite 指向其他路径（测试或挂载持久化卷时使用），默认 `database/library.db`。

项目同时提供：

```text
.env.example
```

供新的开发环境参考。

---

## 23. Running the Application

### 方式 A：Web 界面（推荐）

启动 FastAPI 服务器：

```powershell
python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
```

在浏览器打开 http://127.0.0.1:8000 。

Web 界面提供：

* 登录 / 注册 / Demo 演示登录
* 聊天界面：SSE 流式回复、实时工具调用步骤卡（可展开查看参数）
* "My Shelf" 仪表盘：借阅统计、在借列表（含到期徽章）、未付罚金、借阅历史、可搜索的图书目录
* 可折叠侧边栏（含图书馆快捷操作）、浅色/深色主题（跟随系统 + 手动切换）、刷新后自动恢复登录态

借书、还书、缴罚金等写操作统一通过聊天视图中的 AI Agent 完成，仪表盘保持只读。

### 方式 B：终端 CLI

启动：

```powershell
python main.py
```

启动后进入认证界面：

```text
1. Login
2. Register
3. Continue as Demo
4. Exit
```

登录以后直接进入对话界面。除了自然语言，还支持不消耗 token 的斜杠命令（直接调用工具）：

```text
/search <text>   搜索图书
/borrow <id>     借书
/return <id>     还书
/check <id>      查询是否可借
/request <id|title>  预约排队或荐购
/cancel <hold id>    撤回请求
/available       可借图书列表
/loans           当前借阅
/holds           我的预约与荐购
/overdue         逾期图书
/fines           未付罚金
/history         借阅历史
/help            命令列表
/quit            退出
```

CLI 与 Web 共用同一个 `LibraryAgent`：输入的自然语言会带上当前登录用户身份交给 Agent 处理。

### 方式 D：MCP 服务端（可选）

同一批工具也可以直接暴露给任意 MCP 客户端（Codex、Claude Desktop 等），不经过自带的聊天界面：

```powershell
pip install -r requirements.txt -r requirements-mcp.txt
python scripts/mcp_server.py --user-id 1
```

MCP 没有会话概念，因此服务端在启动时绑定一个图书馆用户，并在每次调用中注入该 user_id，逻辑与 Web 聊天一致。MCP SDK 会额外引入约十个依赖包，所以单独放在 requirements-mcp.txt 中。

### 方式 E：部署

`render.yaml` 是本仓库的 Render 蓝图：构建 `Dockerfile`、健康检查指向 `/`，并把 `DEEPSEEK_API_KEY` 留给控制台填写（`sync: false`），不会把密钥提交进仓库。

```text
Render：New + → Blueprint → 选择本仓库
Zeabur：新建项目 → 从 Git 部署（Dockerfile 已处理 $PORT）
```

两个平台都会注入 `PORT`，入口已经兼容。Render 免费层没有持久盘，每次部署都会用种子数据重建 `database/library.db`；要保留数据就挂载磁盘并设置 `LIBRARY_DB_PATH`。

到期提醒和备份不属于 Web 进程，请用调度器（Render 定时任务、GitHub Actions schedule 或 Windows 任务计划）运行 `scripts/due_reminders.py`，传 `--email` 或 `--webhook`。

---

## 24. Demo Environment

项目包含一个本地 Demo Account，方便快速体验系统。

最终 Demo 数据库保持少量真实数据，以便直接展示：

* Borrowing History
* Current Loans
* Book Availability
* Fine Checking
* AI Agent Interaction

开发过程中使用的测试用户和测试数据与正式 Demo 数据分开处理。

---

## 25. Testing

目前项目已经完成多个层面的测试。

### 自动化测试

测试完全离线：LLM 客户端被替换为假实现，数据库是临时文件（见 `tests/conftest.py`），因此不需要 API Key，也不会动 `database/library.db`。

```powershell
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

| 测试文件                 | 覆盖内容                                     |
| -------------------- | ---------------------------------------- |
| `test_fines.py`      | 罚金计算、按自然日边界                              |
| `test_loans.py`      | 借书 / 还书 / 逾期罚金 / 重复缴费、跨用户隔离               |
| `test_catalog.py`    | 图书创建 / 更新 / CSV 导入、ISBN 唯一性、可借状态一致性      |
| `test_reminders.py`  | 到期清单、续借规则（次数上限、逾期、他人借阅）                  |
| `test_agent_loop.py` | 工具分发、SSE 事件、失败回滚、Schema 与分发一致性            |
| `test_web_api.py`    | 会话校验、Demo 登录、聊天、429 限流                    |
| `test_mcp_server.py` | MCP 工具与 Agent Tool Schema 一致（未安装 requirements-mcp.txt 时自动跳过） |
| `test_isbn.py`       | ISBN 校验、OpenLibrary 解析、作者补全、各类失败路径        |
| `test_analytics.py`  | 概览计数、热门图书、月度借阅分桶                        |
| `test_due_reminders.py` | 提醒摘要、SMTP 发送、Webhook POST、失败上报           |
| `test_holds.py`      | 预约排队位置、归还是提升队列、荐购、撤回               |

GitHub Actions 会在每次 push 与 pull request 上运行同一命令（`.github/workflows/ci.yml`）。

---

### Functional Testing

测试：

* Book Search
* Availability Check
* Borrowing
* Returning
* Current Loans
* Overdue Detection
* Fine Calculation
* Fine Payment
* Borrowing History
* Recommendations

---

### AI Agent Testing

测试：

* Tool Selection
* Multi-step Tool Calling
* Borrowing Decision Rules
* Availability Verification
* Alternative Book Workflow
* Context Handling
* Error Handling
* Duplicate Tool-call Protection

---

### Authentication Testing

测试：

* Registration
* Login
* Demo Login
* Logout
* Password Verification

---

### Data Isolation Testing

测试：

* User-specific Borrowing History
* User-specific Current Loans
* User-specific Fines
* Cross-user Return Protection
* Cross-user Payment Protection

---

### Database Integrity Testing

测试：

* Orphan Record Detection
* Duplicate Active Loan Detection
* Active Loan Consistency
* Book Availability Consistency

---

## 26. Git Version Control

项目使用 Git 管理版本，`main` 分支始终对应当前可用的稳定状态。提交以聚焦、可自描述的方式组织，具体演进可查看仓库提交历史。

---

## 27. Future Improvements

这个项目目前已经完成了第一版完整 Agent Workflow，但仍然具有较大的扩展空间。

未来可以继续加入：

### AI / Agent

* Semantic Book Search
* RAG
* Long-term Memory
* Better Recommendation Ranking
* Multi-Agent Architecture
* Agent Planning
* Agent Tracing / Observability

### Library System

* Reservation System
* Waiting List
* Borrowing Limits
* Automatic Fine Notifications
* Admin Dashboard

### Software Architecture

* Token-level Streaming（Web 界面中最终回答的逐字流式输出）
* Server-side Session Persistence（当前会话保存在内存中）
* Cloud Database
* Automated Test Suite
* Logging System
* Monitoring
* Deployment Pipeline

---

## 28. Current Project Goal

AI Library Agent 的核心目标是探索：

> 如何让一个 LLM 不只是“回答问题”，而是真正成为一个可以安全调用工具、访问实时数据、执行多步骤任务并遵守业务规则的软件 Agent。

整个系统最终形成：

```text
Natural Language
       +
LLM
       +
Tool Calling
       +
Agent State
       +
Business Logic
       +
SQLite
       +
Authentication
       +
Data Isolation
       +
Persistent Data
```

从而构建一个真正能够执行实际任务的 AI-powered application。

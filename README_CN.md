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
* 查看当前借阅
* 查看逾期图书
* 查看借阅历史
* 查看当前可借图书

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
* Availability
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

当前 Agent 一共提供 12 个 Tools：

| Tool                         | 功能          |
| ---------------------------- | ----------- |
| `search_books`               | 根据图书标题关键字搜索 |
| `check_book_availability`    | 检查指定图书是否可借  |
| `borrow_book`                | 借阅图书        |
| `return_book`                | 归还当前用户借阅的图书 |
| `get_current_borrowed_books` | 查看当前借阅      |
| `get_overdue_books`          | 查看当前逾期图书    |
| `get_book_loan_details`      | 查看指定图书的借阅详情 |
| `calculate_fine`             | 计算当前或最终罚款   |
| `get_unpaid_fines`           | 查询未支付罚款     |
| `pay_fine`                   | 支付未支付的最终罚款  |
| `get_borrow_history`         | 查看借阅历史      |
| `list_available_books`       | 查看所有当前可借图书  |

Tools 的定义（schema）与系统提示词位于（Web 引擎与 `main.py` CLI 共用同一份）：

```text
agent/core.py
```

而实际业务逻辑主要位于：

```text
agent/tools.py
```

---

## 7. Agent State

`AgentState` 用于保存 Agent 当前任务相关的信息。

主要包含：

```text
current_user_id
current_username
current_user_name

goal

requested_book
requested_book_id
requested_book_available

alternative_book
alternative_book_id

borrowed_at
due_date
returned_at

is_overdue
late_days

fine_amount
fine_paid
fine_paid_at

payment_amount
payment_status

completed
waiting_for_confirmation
last_action
```

例如，在 Alternative Workflow 中：

```text
User Request
    ↓
Book unavailable
    ↓
waiting_for_confirmation = True
    ↓
User: yes
    ↓
Find alternative
    ↓
Borrow alternative
    ↓
completed = True
```

因此 `AgentState` 不只是保存信息，也帮助系统管理多步骤 Agent Workflow。

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
AgentState.current_user_id
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
AgentState.current_user_id
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

主要包含三个核心表。

### `users`

用于保存：

* User ID
* Username
* Password Hash
* Full Name
* Email
* Account Status
* Created Time

---

### `books`

用于保存：

* Book ID
* Title
* Author
* Availability

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

| 技术            | 用途             |
| ------------- | -------------- |
| Python        | 主程序与业务逻辑       |
| SQLite        | 数据持久化          |
| DeepSeek API  | LLM / AI Agent |
| OpenAI SDK    | API 调用         |
| Rich          | Terminal UI    |
| python-dotenv | 环境变量管理         |

当前 Agent 使用的模型配置位于 `main.py`：

```python
model="deepseek-v4-flash"
```

---

## 20. Project Structure

```text
AI-Agent-Learning/
│
├── main.py
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── agent/
│   ├── __init__.py
│   ├── auth.py
│   ├── core.py
│   ├── database.py
│   ├── errors.py
│   ├── state.py
│   └── tools.py
│
├── database/
│   └── library.db
│
├── web/
│   ├── app.py
│   ├── models.py
│   ├── session.py
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── assets/
│       ├── css/
│       │   ├── tokens.css
│       │   ├── base.css
│       │   ├── components.css
│       │   └── views/
│       └── js/
│           ├── app.js
│           ├── lib/
│           └── views/
│
└── tests/
    └── ...
```

其中：

```text
.env
```

保留在本地环境中，但不进入 Git。

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
```

程序通过：

```python
os.getenv("DEEPSEEK_API_KEY")
```

读取 API Key。

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

登录以后进入主菜单：

```text
1. Search for a book
2. Check book availability
3. Borrow a book
4. Return a book
5. View borrowing history
6. View available books
7. View fines
8. My current borrowed books
9. My overdue books
10. Chat with AI Agent
11. Logout
```

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

项目使用 Git 管理稳定版本。

基本工作方式：

```text
Stable Version
      ↓
Development
      ↓
Testing
      ↓
git add
      ↓
git commit
      ↓
New Stable Version
```

例如：

```powershell
git add .
git commit -m "Add recommendation workflow"
```

这样即使后续开发过程中出现问题，也可以回到之前已经验证过的稳定版本。

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
* MCP-based Tools
* Agent Planning
* Agent Tracing / Observability

### Library System

* Book Categories
* Book Metadata
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

## 28. Project Development Direction

这个项目最重要的部分不是“Library”本身，而是它提供了一个实际的 Agent Application 场景。

当前项目已经形成了：

```text
LLM
+
Tool Calling
+
Agent State
+
Business Logic
+
Database
+
Authentication
+
Data Isolation
+
Natural Language
+
Error Handling
```

因此，它可以继续作为以后学习和开发更复杂 AI Agent 系统的基础。

下一阶段可以逐步从：

```text
Single Agent
```

发展到：

```text
Agent + RAG
```

再进一步发展到：

```text
Multi-Agent
```

以及：

```text
Agent + MCP + External Services
```

---

## 29. Current Project Goal

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
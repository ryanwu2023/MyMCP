# 公司名称查询股东大会议题设计

## 背景

现有 `get_shareholder_meetings` 工具只能按完整 Wind 股票代码查询股东大会。例如，用户必须知道海大集团的代码是 `002311.SZ`，才能获取会议及议案。实际用户更常使用证券简称或公司全称，因此工具需要先识别公司，再复用现有股东大会查询。

Wind 数据表提供了所需关系：

- `WIND_IMP.ASHAREDESCRIPTION` 保存 Wind 代码、证券简称和公司全称；
- `WIND_IMP.ASHAREINTRODUCTION` 保存公司基本资料；
- 两表通过 `S_INFO_WINDCODE` 关联；
- `WIND_IMP.ASHAREHOLDERSMEETING` 和 `WIND_IMP.ASHAREINTERNETVOTING` 继续提供会议及逐项议案。

海大集团在样例数据中对应 `002311.SZ`，公司全称为“广东海大集团股份有限公司”。

## 目标

扩展现有工具，使以下调用都能查询同一家公司的最近股东大会：

- `002311.SZ`
- `海大集团`
- `广东海大集团股份有限公司`

结果同时返回公司简称、全称、基本资料、最近股东大会和逐项议案。原有按 Wind 代码调用的客户端必须继续可用。

## 非目标

- 不支持模糊名称搜索、拼音搜索或别名推断；
- 不接受用户提供的 SQL；
- 不引入公司资料内存缓存；
- 不改变会议日期过滤、数量上限或议案结果标准化规则；
- 不新增功能重复的 MCP 工具。

## 方案选择

采用两阶段查询：先解析公司，再查询会议。

相比单条大型联表 SQL，该方案避免公司资料、会议和议案多层一对多关联产生的重复行，且更容易独立处理名称歧义。相比内存缓存，该方案没有数据刷新和多进程一致性问题。代价是一次调用通常需要两次数据库查询，该开销对当前本机及局域网只读服务可以接受。

## 架构

改动限定在现有 `shareholder_meeting` 领域：

- Repository 增加公司解析查询，并保留现有会议查询；
- Service 负责识别输入类型、处理解析结果和编排两阶段查询；
- Models 增加公司资料模型，并将其加入现有结果模型；
- Tools 保留 `get_shareholder_meetings` 名称和 `wind_code` 参数，仅扩展参数语义及工具描述；
- Server 的注册方式保持不变。

Repository 只保存固定、参数化、只读 SQL。用户输入始终通过 Oracle 绑定参数传入。

## 公司解析

Service 对 `wind_code` 参数去除首尾空格：

1. 若输入符合 `六位数字.SH/SZ/BJ` 格式，按大写 Wind 代码精确匹配；
2. 否则同时按 `AShareDescription.S_INFO_NAME` 和 `S_INFO_COMPNAME` 精确匹配；
3. 不使用 `%` 模糊查询，不自动选择近似名称。

公司解析查询以 `AShareDescription` 为名称和代码的权威来源，并通过 `S_INFO_WINDCODE` 关联 `AShareIntroduction`。若公司简介表存在多条历史记录，按 `ANN_DT DESC NULLS LAST, OPDATE DESC NULLS LAST, OBJECT_ID DESC` 选取最新一条。公司简介缺失时使用左连接，名称和会议查询仍可成功。

公司匹配结果按 Wind 代码去重：

- 零个匹配：返回明确的“未找到公司”错误；
- 一个匹配：继续查询会议；
- 多个不同 Wind 代码匹配：返回候选代码、简称和全称，要求用户改用 Wind 代码，不静默猜测。

## 数据流

以“海大集团”为例：

1. MCP 工具收到 `wind_code="海大集团"`；
2. Service 判断该输入不是 Wind 代码；
3. Repository 在 `AShareDescription` 中精确匹配简称或全称；
4. 唯一解析为 `002311.SZ`，并读取最新公司简介；
5. Service 使用 `002311.SZ` 调用现有会议查询；
6. Repository 按会议日期倒序返回最近会议，并通过事件 ID 关联议案；
7. Service 返回公司资料和结构化会议结果。

`meeting_date` 和 `limit` 的语义不变。`limit` 仍表示会议场数，而不是议案条数。

## 返回结构

现有根节点字段 `count`、`truncated` 和 `items` 保留，新增必需的 `company` 字段。`company` 包含：

- `wind_code`
- `short_name`
- `full_name`
- `province`
- `city`
- `chairman`
- `president`
- `board_secretary`
- `registered_capital`
- `founded_date`
- `company_introduction`
- `company_type`
- `website`
- `email`
- `office_address`
- `country`
- `business_scope`
- `total_employees`
- `main_business`

除 Wind 代码、简称和全称外，公司简介字段允许为空。会议与议案的现有返回结构不变。

## 输入验证和错误处理

- 空字符串或纯空白：提示必须提供 Wind 代码、证券简称或公司全称；
- 格式正确但不存在的 Wind 代码：提示未找到公司；
- 名称无匹配：提示未找到公司；
- 名称对应多个 Wind 代码：错误中列出有限数量的候选公司，并提示使用 Wind 代码；
- 公司存在但无股东大会：正常返回公司资料，`count=0`、`items=[]`；
- 公司简介缺失：正常返回名称和会议，简介字段为空；
- 日期无效或 `limit` 超界：沿用现有校验及错误信息。

候选列表设置明确上限，避免错误响应无限增长。所有数据库操作继续服从现有调用超时。

## 兼容性

- MCP 工具名称保持 `get_shareholder_meetings`；
- 参数名称保持 `wind_code`，已有客户端无需修改；
- 完整 Wind 代码仍按现有规则规范化为大写；
- 现有会议字段不删除、不改名；
- 返回根节点新增 `company`，属于扩展性变更；
- README 和工具描述明确说明 `wind_code` 也可传证券简称或公司全称。

## 测试

### Repository

- Wind 代码、简称和全称都通过绑定参数查询；
- 公司资料字段映射正确；
- 多条简介记录只选择最新记录；
- 无简介记录时仍返回公司身份；
- 多个 Wind 代码匹配时保留候选，不能任取一条；
- 现有会议查询和议案分组行为保持不变。

### Service

- `002311.SZ`、`海大集团` 和 `广东海大集团股份有限公司` 都解析为同一公司；
- 输入空白、公司不存在和名称歧义分别产生明确错误；
- 日期和会议数量校验保持不变；
- 公司无会议、无简介时返回结构正确；
- 议案结果继续映射为 `passed`、`rejected` 或 `unknown`。

### MCP 契约和回归

- 原有 Wind 代码调用继续成功；
- 名称调用返回 `company` 和会议议题；
- 工具描述能引导模型将自然语言公司名传入该工具；
- 完整测试套件通过，指数查询能力不受影响。

## 文档与验收

README 增加公司名称查询说明和“海大集团”示例。

最终验收场景为：用户说“查询海大集团最近的股东大会议题”，模型调用 `get_shareholder_meetings`，服务将“海大集团”解析为 `002311.SZ`，并展示公司简称、全称、基本信息以及按日期倒序排列的最近会议和议案。

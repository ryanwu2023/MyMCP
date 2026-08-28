# A 股标的识别与股东大会议题查询设计

## 背景

现有 `get_shareholder_meetings` 工具只能按完整 Wind 股票代码查询股东大会。例如，用户必须知道海大集团的代码是 `002311.SZ`，才能获取会议及议案。实际用户更常使用六位股票代码、证券简称、公司全称或名称片段。

标的识别不仅服务于股东大会，未来的个股行情、财务、公告等功能也需要把用户输入统一解析为唯一 Wind 代码。因此，公司识别必须成为独立、可复用的领域模块和 MCP 工具，股东大会领域只消费其解析结果。

Wind 数据表提供了所需关系：

- `WIND_IMP.ASHAREDESCRIPTION` 保存 Wind 代码、证券简称和公司全称；
- `WIND_IMP.ASHAREINTRODUCTION` 保存公司基本资料；
- 两表通过 `S_INFO_WINDCODE` 关联；
- `WIND_IMP.ASHAREHOLDERSMEETING` 和 `WIND_IMP.ASHAREINTERNETVOTING` 继续提供会议及逐项议案。

海大集团在样例数据中对应 `002311.SZ`，公司全称为“广东海大集团股份有限公司”。

## 目标

新增独立 A 股标的识别工具，使以下输入都能识别同一家公司：

- `002311.SZ`
- `002311`
- `海大集团`
- `广东海大集团股份有限公司`
- `海大`

标的识别工具在唯一匹配时返回公司身份和基本资料，在多匹配时返回候选列表。扩展现有股东大会工具以复用该识别能力，并返回公司简称、全称、基本资料、最近股东大会和逐项议案。原有按 Wind 代码调用的客户端必须继续可用。

## 非目标

- 不支持拼音搜索、错别字纠正、别名推断或基于编辑距离的相似度搜索；
- 不接受用户提供的 SQL；
- 不引入公司资料内存缓存；
- 不改变会议日期过滤、数量上限或议案结果标准化规则；
- 不为行情、财务或公告实现具体查询；本次只提供可供这些领域复用的标的解析能力。

## 方案选择

采用独立解析服务加业务编排：`stock_identity` 领域负责把用户输入解析为零个、一个或多个 A 股候选；股东大会领域在得到唯一 Wind 代码后继续使用现有会议查询。

名称解析采用“精确优先、无精确结果再包含匹配”。相比所有名称直接包含匹配，该方案不会让完整简称或全称产生不必要的歧义；相比编辑距离或全文检索，该方案不依赖 Oracle 扩展能力，结果可解释且容易稳定测试。

相比把解析和会议合并为单条大型 SQL，独立服务避免公司资料、会议和议案多层一对多关联产生的重复行，也能被未来行情等领域直接复用。相比内存缓存，该方案没有数据刷新和多进程一致性问题。股东大会名称查询通常需要两次数据库查询，该开销对当前本机及局域网只读服务可以接受。

## 架构

新增独立领域：

```text
src/index_mcp/domains/stock_identity/
├─ models.py
├─ repository.py
├─ service.py
└─ tools.py
```

- `stock_identity.repository` 保存代码、名称和公司资料查询 SQL；
- `stock_identity.service` 负责输入规范化、匹配优先级、去重、候选截断和解析状态；
- `stock_identity.models` 定义候选、公司资料和解析结果；
- `stock_identity.tools` 注册独立 MCP 工具 `resolve_a_share`；
- `shareholder_meeting.service` 注入并复用 `StockIdentityService`，不直接访问 `AShareDescription`；
- `shareholder_meeting.repository` 继续只负责会议和议案查询；
- Server 在同一数据库连接池上构造两个服务，并注册两个领域的工具。

Repository 只保存固定、参数化、只读 SQL。用户输入始终通过 Oracle 绑定参数传入。

## A 股标的解析

`StockIdentityService` 对 `query` 去除首尾空格，并按以下优先级解析：

1. 符合 `六位数字.SH/SZ/BJ` 格式时，按大写 Wind 代码精确匹配；
2. 符合六位数字格式时，按 `S_INFO_CODE` 精确匹配；
3. 其他输入先按 `S_INFO_NAME` 和 `S_INFO_COMPNAME` 精确匹配；
4. 名称精确匹配为零时，再对简称和全称做包含匹配。

包含匹配使用 `LIKE :name_pattern ESCAPE '\\'` 和绑定参数。Repository 对用户输入中的 `%`、`_` 和 `\` 转义，然后再添加 `%`，避免输入被解释为额外通配符。

公司解析查询以 `AShareDescription` 为名称和代码的权威来源，并通过 `S_INFO_WINDCODE` 关联 `AShareIntroduction`。若公司简介表存在多条历史记录，按 `ANN_DT DESC NULLS LAST, OPDATE DESC NULLS LAST, OBJECT_ID DESC` 选取最新一条。公司简介缺失时使用左连接，名称和会议查询仍可成功。

公司匹配结果按 Wind 代码去重：

- 零个匹配：`status=not_found`；
- 一个匹配：`status=resolved`；
- 多个不同 Wind 代码匹配：`status=ambiguous`，不静默猜测。

候选最多返回 `limit` 条，默认 10、最大 50。搜索额外读取一条以判断 `candidates_truncated`。候选稳定排序为：简称命中优先、名称长度较短优先、Wind 代码升序。

## 独立 MCP 工具

新增 `resolve_a_share(query, limit=10)`，返回：

- `status`: `resolved | ambiguous | not_found`
- `match_type`: `wind_code | stock_code | exact_short_name | exact_full_name | fuzzy_name | none`
- `query`: 规范化后的查询文本
- `count`: 当前返回的候选数量
- `candidates_truncated`: 是否还有未返回候选
- `candidates`: 候选公司列表
- `company`: 仅 `resolved` 时返回的唯一公司及其基本资料，否则为空

每个候选包含 Wind 代码、六位股票代码、证券简称、公司全称、上市日期和退市日期。`ambiguous` 和 `not_found` 是正常搜索结果，不作为 MCP 调用错误。

## 数据流

以“海大集团”为例：

1. `get_shareholder_meetings` 收到 `wind_code="海大集团"`；
2. `ShareholderMeetingService` 把输入交给 `StockIdentityService`；
3. 解析服务先精确匹配简称，唯一解析为 `002311.SZ`，并读取最新公司简介；
4. 股东大会 Service 使用 `002311.SZ` 调用现有会议 Repository；
5. Repository 按会议日期倒序返回最近会议，并通过事件 ID 关联议案；
6. Service 返回公司资料和结构化会议结果。

若输入“海大”且模糊搜索仅产生一个候选，同样继续查询会议。若产生多个候选，停止会议查询并提示用户使用候选中的 Wind 代码或更完整名称。

`meeting_date` 和 `limit` 的语义不变。`limit` 仍表示会议场数，而不是议案条数。

## 股东大会返回结构

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

除 Wind 代码、简称和全称外，公司简介字段允许为空。该公司模型由 `stock_identity.models` 定义并在两个工具之间复用。会议与议案的现有返回结构不变。

## 输入验证和错误处理

- 空字符串或纯空白：提示必须提供 Wind 代码、六位股票代码、证券简称、公司全称或名称片段；
- 格式正确但不存在的 Wind 代码：提示未找到公司；
- 独立解析工具无匹配：正常返回 `not_found`；
- 独立解析工具多匹配：正常返回 `ambiguous` 和有限候选；
- 股东大会工具无匹配：停止会议查询并返回明确业务错误；
- 股东大会工具多匹配：停止会议查询，错误中列出有限候选并提示使用 Wind 代码；
- 公司存在但无股东大会：正常返回公司资料，`count=0`、`items=[]`；
- 公司简介缺失：正常返回名称和会议，简介字段为空；
- 日期无效或 `limit` 超界：沿用现有校验及错误信息。

候选列表设置明确上限，避免错误响应无限增长。所有数据库操作继续服从现有调用超时。

## 兼容性

- 新增 MCP 工具 `resolve_a_share`；
- 原 MCP 工具名称保持 `get_shareholder_meetings`；
- 参数名称保持 `wind_code`，已有客户端无需修改；
- 完整 Wind 代码仍按现有规则规范化为大写；
- `wind_code` 参数扩展为也接受六位代码、证券简称、公司全称和名称片段；
- 现有会议字段不删除、不改名；
- 返回根节点新增 `company`，属于扩展性变更；
- README 和工具描述说明独立解析工具，并明确 `wind_code` 的扩展语义。

## 测试

### Stock Identity Repository

- Wind 代码、六位代码、简称、全称和名称片段都通过绑定参数查询；
- `%`、`_` 和 `\` 被正确转义；
- 公司资料字段映射正确；
- 多条简介记录只选择最新记录；
- 无简介记录时仍返回公司身份；
- 多个 Wind 代码匹配时保留候选，不能任取一条；
- 候选截断和稳定排序正确。

### Stock Identity Service

- `002311.SZ`、`002311`、`海大集团`、`广东海大集团股份有限公司` 和唯一的“海大”模糊结果都解析为同一公司；
- 精确匹配优先于模糊匹配；
- 空白输入校验明确；
- 无匹配返回 `not_found`；
- 多匹配返回 `ambiguous`，不任取一条；
- `limit` 范围和候选截断正确。

### Shareholder Meeting

- 股东大会 Service 通过注入的 `StockIdentityService` 获取唯一 Wind 代码；
- 代码、简称、全称和唯一模糊匹配都进入相同会议查询；
- `ambiguous` 和 `not_found` 不执行会议 Repository 查询；
- 日期和会议数量校验保持不变；
- 公司无会议、无简介时返回结构正确；
- 议案结果继续映射为 `passed`、`rejected` 或 `unknown`。

### MCP 契约和回归

- 原有 Wind 代码调用继续成功；
- `resolve_a_share` 的 `resolved`、`ambiguous` 和 `not_found` 契约正确；
- 名称和名称片段调用股东大会工具返回 `company` 和会议议题；
- 工具描述能引导模型在需要消歧时先使用独立解析工具；
- 完整测试套件通过，指数查询能力不受影响。

## 文档与验收

README 增加独立标的解析工具说明、候选消歧流程和“海大集团”示例。

最终验收场景为：

1. 用户说“查询海大集团最近的股东大会议题”，模型调用 `get_shareholder_meetings`，服务将“海大集团”解析为 `002311.SZ`，并展示公司简称、全称、基本信息以及按日期倒序排列的最近会议和议案；
2. 用户提供一个匹配多只股票的名称片段时，`resolve_a_share` 返回候选列表，模型请用户指定后再调用股东大会工具；
3. 未来个股行情领域可以注入并调用 `StockIdentityService`，无需复制代码、名称或模糊匹配逻辑。
